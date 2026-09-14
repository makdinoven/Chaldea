"""FEAT-162 task #9 — POST /characters/admin/{character_id}/move.

The feature exists to guarantee **one** property, and it is a negative one:

    there is no ordering in which the character ends up in the new location
    while a mandatory cleanup has not run.

A happy-path test cannot see that property at all, so most of this file is
about the failure paths: each cleanup is forced to fail in turn and the
character row, the travel cooldown and the audit journal are all asserted
*unchanged*. `TestCleanupInvariant` additionally inspects the database from
inside the mocked cleanup call, proving the write has not happened yet at the
moment the cleanup runs.

Authorisation gets the same treatment. The real regression risk is not the
anonymous caller (obvious) but the **moderator**, who holds every other
`characters:*` permission — `characters:update` would have let them through,
which is precisely why the feature introduced `characters:teleport`.

Both locations-service calls are mocked (`locations_client.cancel_gathering`,
`locations_client.notify_character_left_location`); the gate rows themselves
live in locations-service and are asserted in that service's own suite
(`tests/test_character_left_location.py`).
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text

import crud
import database
import locations_client
import models
from auth_http import OAUTH2_SCHEME, UserRead, get_current_user_via_http
from database import Base
from main import app, get_db


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOC_FROM = 501
LOC_TO = 502
LOC_UNKNOWN = 999_999

ADMIN_USER = UserRead(
    id=7,
    username="root_admin",
    role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve", "characters:teleport",
    ],
)

# A moderator holds every characters:* permission EXCEPT teleport — this is the
# exact shape of the seeded role (FEAT-162 §2.5), and the reason the feature
# could not simply reuse `characters:update`.
MODERATOR_USER = UserRead(
    id=8,
    username="mod",
    role="moderator",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve",
    ],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Tables owned by other services that the endpoint reads through raw SQL on the
# shared database. Created with plain DDL (IF NOT EXISTS) so this file works
# whether or not another test module has already declared them on Base.
_FOREIGN_TABLES_DDL = (
    'CREATE TABLE IF NOT EXISTS "Locations" '
    '(id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL)',
    "CREATE TABLE IF NOT EXISTS battles "
    "(id INTEGER PRIMARY KEY, status VARCHAR(20))",
    "CREATE TABLE IF NOT EXISTS battle_participants "
    "(id INTEGER PRIMARY KEY, battle_id INTEGER, character_id INTEGER, "
    "dropped_out_at DATETIME)",
    "CREATE TABLE IF NOT EXISTS dungeon_sessions "
    "(id INTEGER PRIMARY KEY, status VARCHAR(20))",
    "CREATE TABLE IF NOT EXISTS dungeon_session_members "
    "(id INTEGER PRIMARY KEY, session_id INTEGER, character_id INTEGER)",
)

_FOREIGN_TABLES = (
    "dungeon_session_members", "dungeon_sessions",
    "battle_participants", "battles", "Locations",
)


@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)

    for ddl in _FOREIGN_TABLES_DDL:
        session.execute(sa_text(ddl))
    for loc_id, name in ((LOC_FROM, "Пирс"), (LOC_TO, "Бар «Три Галки»")):
        session.execute(
            sa_text('INSERT INTO "Locations" (id, name) VALUES (:i, :n)'),
            {"i": loc_id, "n": name},
        )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        with database.engine.begin() as conn:
            for table in _FOREIGN_TABLES:
                conn.execute(sa_text(f'DROP TABLE IF EXISTS "{table}"'))
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def character(db_session):
    """A player standing in LOC_FROM with an active travel cooldown."""
    char = models.Character(
        name="Подопытный",
        id_race=1, id_subrace=1, id_class=1,
        appearance="test", avatar="t.jpg",
        is_npc=False, npc_role=None,
        current_location_id=LOC_FROM,
        level=1, stat_points=0, currency_balance=0,
        travel_cooldown_until=datetime.utcnow() + timedelta(minutes=30),
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


def _override(db_session, user=None):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        app.dependency_overrides[get_current_user_via_http] = lambda: user
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"


@pytest.fixture
def admin_client(db_session):
    _override(db_session, ADMIN_USER)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def moderator_client(db_session):
    _override(db_session, MODERATOR_USER)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def anon_client(db_session):
    _override(db_session, None)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def cleanup_mocks():
    """Both locations-service calls, mocked and succeeding by default."""
    with patch.object(
        locations_client, "cancel_gathering", new_callable=AsyncMock,
    ) as cancel, patch.object(
        locations_client, "notify_character_left_location", new_callable=AsyncMock,
    ) as notify:
        cancel.return_value = {"cancelled": False, "reason": "no_active_session"}
        notify.return_value = {
            "ok": True, "gates_expired": 0,
            "gate_requests_expired": 0, "party_pruned": False,
        }
        yield {"cancel": cancel, "notify": notify}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _move(client, character_id, to_id=LOC_TO):
    return client.post(
        f"/characters/admin/{character_id}/move",
        json={"new_location_id": to_id},
    )


def _reload(db_session, character_id):
    db_session.expire_all()
    return db_session.query(models.Character).filter_by(id=character_id).first()


def _teleport_logs(db_session, character_id):
    return (
        db_session.query(models.CharacterLog)
        .filter_by(character_id=character_id, event_type="admin_teleport")
        .all()
    )


def _assert_untouched(db_session, char, *, expected_location=LOC_FROM):
    """The whole feature in one assertion block: nothing moved, nothing logged,
    the cooldown still standing."""
    fresh = _reload(db_session, char.id)
    assert fresh.current_location_id == expected_location
    assert fresh.travel_cooldown_until is not None
    assert _teleport_logs(db_session, char.id) == []


# ===========================================================================
# 1. Authorisation
# ===========================================================================

class TestAuthorisation:
    def test_anonymous_is_rejected(self, anon_client, db_session, character):
        resp = _move(anon_client, character.id)
        assert resp.status_code == 401
        _assert_untouched(db_session, character)

    def test_moderator_is_forbidden(self, moderator_client, db_session, character):
        """The regression that matters: a moderator holds every other
        characters:* permission, so only `characters:teleport` keeps them out."""
        resp = _move(moderator_client, character.id)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Недостаточно прав"
        _assert_untouched(db_session, character)

    def test_moderator_with_delegated_permission_passes(
        self, db_session, character, cleanup_mocks,
    ):
        """§3.6 documents delegation via user_permissions as deliberate:
        the guard is the permission, never the role string."""
        delegated = UserRead(
            id=9, username="mod2", role="moderator",
            permissions=["characters:update", "characters:teleport"],
        )
        _override(db_session, delegated)
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = _move(client, character.id)
            assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.clear()

    def test_plain_user_is_forbidden(self, db_session, character):
        _override(db_session, UserRead(
            id=10, username="pleb", role="user", permissions=[],
        ))
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = _move(client, character.id)
            assert resp.status_code == 403
            _assert_untouched(db_session, character)
        finally:
            app.dependency_overrides.clear()


# ===========================================================================
# 2. Not-found and validation
# ===========================================================================

class TestNotFoundAndValidation:
    def test_unknown_character_returns_404(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        resp = _move(admin_client, 123_456)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Персонаж не найден"
        # No cleanup may fire for a character that does not exist.
        cleanup_mocks["cancel"].assert_not_called()
        cleanup_mocks["notify"].assert_not_called()

    def test_unknown_destination_returns_404(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        resp = admin_client.post(
            f"/characters/admin/{character.id}/move",
            json={"new_location_id": LOC_UNKNOWN},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Локация назначения не найдена"
        cleanup_mocks["cancel"].assert_not_called()
        cleanup_mocks["notify"].assert_not_called()
        _assert_untouched(db_session, character)

    def test_missing_body_returns_422(self, admin_client, character):
        resp = admin_client.post(f"/characters/admin/{character.id}/move", json={})
        assert resp.status_code == 422

    @pytest.mark.parametrize("bad", [0, -1, -999])
    def test_non_positive_location_id_returns_422(
        self, admin_client, db_session, character, cleanup_mocks, bad,
    ):
        resp = admin_client.post(
            f"/characters/admin/{character.id}/move",
            json={"new_location_id": bad},
        )
        assert resp.status_code == 422
        _assert_untouched(db_session, character)

    @pytest.mark.parametrize("payload", [
        {"new_location_id": "1 OR 1=1"},
        {"new_location_id": "'; DROP TABLE characters; --"},
        {"new_location_id": None},
        {"new_location_id": {"id": 1}},
    ])
    def test_injection_and_type_abuse_never_reaches_sql(
        self, admin_client, db_session, character, payload,
    ):
        """`new_location_id` is a typed int; anything else dies in validation
        and the characters table is still there afterwards."""
        resp = admin_client.post(
            f"/characters/admin/{character.id}/move", json=payload,
        )
        assert resp.status_code == 422
        assert db_session.query(models.Character).filter_by(id=character.id).first()


# ===========================================================================
# 3. Same location — an unconditional no-op
# ===========================================================================

class TestSameLocationNoOp:
    def test_same_location_writes_nothing_at_all(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        before_cooldown = _reload(db_session, character.id).travel_cooldown_until
        log_count_before = db_session.query(models.CharacterLog).count()

        resp = admin_client.post(
            f"/characters/admin/{character.id}/move",
            json={"new_location_id": LOC_FROM},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["moved"] is False
        assert body["detail"] == "Персонаж уже находится в этой локации"
        assert body["from_location_id"] == LOC_FROM
        assert body["to_location_id"] == LOC_FROM
        assert body["gathering_cancelled"] is False

        # Nothing written, nothing cleaned up, no journal row.
        fresh = _reload(db_session, character.id)
        assert fresh.current_location_id == LOC_FROM
        assert fresh.travel_cooldown_until == before_cooldown
        assert db_session.query(models.CharacterLog).count() == log_count_before
        cleanup_mocks["cancel"].assert_not_called()
        cleanup_mocks["notify"].assert_not_called()

    def test_same_location_short_circuits_before_the_battle_check(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        """The no-op is unconditional: even a character in a battle gets a
        harmless 200, because nothing is written for them either."""
        _put_in_battle(db_session, character.id)

        resp = admin_client.post(
            f"/characters/admin/{character.id}/move",
            json={"new_location_id": LOC_FROM},
        )
        assert resp.status_code == 200
        assert resp.json()["moved"] is False
        cleanup_mocks["notify"].assert_not_called()


# ===========================================================================
# 4. Refusals — battle and dungeon
# ===========================================================================

def _put_in_battle(session, character_id, status="in_progress"):
    session.execute(
        sa_text("INSERT INTO battles (id, status) VALUES (1, :s)"), {"s": status},
    )
    session.execute(
        sa_text(
            "INSERT INTO battle_participants (id, battle_id, character_id) "
            "VALUES (1, 1, :c)"
        ),
        {"c": character_id},
    )
    session.commit()


def _put_in_dungeon(session, character_id, status="active"):
    session.execute(
        sa_text("INSERT INTO dungeon_sessions (id, status) VALUES (1, :s)"),
        {"s": status},
    )
    session.execute(
        sa_text(
            "INSERT INTO dungeon_session_members (id, session_id, character_id) "
            "VALUES (1, 1, :c)"
        ),
        {"c": character_id},
    )
    session.commit()


class TestRefusals:
    @pytest.mark.parametrize("status", ["pending", "in_progress"])
    def test_character_in_battle_returns_409(
        self, admin_client, db_session, character, cleanup_mocks, status,
    ):
        _put_in_battle(db_session, character.id, status)

        resp = _move(admin_client, character.id)
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Персонаж находится в бою — перенос невозможен"
        # A refusal must happen BEFORE any cleanup: a refused move may not
        # cancel the victim's gathering or burn their gates.
        cleanup_mocks["cancel"].assert_not_called()
        cleanup_mocks["notify"].assert_not_called()
        _assert_untouched(db_session, character)

    def test_finished_battle_does_not_block(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        _put_in_battle(db_session, character.id, "finished")
        resp = _move(admin_client, character.id)
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize("status", ["forming", "active"])
    def test_character_in_dungeon_returns_409(
        self, admin_client, db_session, character, cleanup_mocks, status,
    ):
        _put_in_dungeon(db_session, character.id, status)

        resp = _move(admin_client, character.id)
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Персонаж находится в подземелье — перенос невозможен"
        cleanup_mocks["cancel"].assert_not_called()
        cleanup_mocks["notify"].assert_not_called()
        _assert_untouched(db_session, character)

    def test_finished_dungeon_run_does_not_block(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        _put_in_dungeon(db_session, character.id, "completed")
        resp = _move(admin_client, character.id)
        assert resp.status_code == 200, resp.text

    def test_another_characters_battle_does_not_block(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        _put_in_battle(db_session, character.id + 5000)
        resp = _move(admin_client, character.id)
        assert resp.status_code == 200, resp.text


# ===========================================================================
# 5. Happy path
# ===========================================================================

class TestHappyPath:
    def test_move_writes_location_clears_cooldown_and_logs_once(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        resp = _move(admin_client, character.id)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["moved"] is True
        assert body["detail"] == "Персонаж перенесён"
        assert body["character_id"] == character.id
        assert body["from_location_id"] == LOC_FROM
        assert body["from_location_name"] == "Пирс"
        assert body["to_location_id"] == LOC_TO
        assert body["to_location_name"] == "Бар «Три Галки»"
        assert body["gathering_cancelled"] is False

        fresh = _reload(db_session, character.id)
        assert fresh.current_location_id == LOC_TO
        # «Перенос не должен наказывать игрока невозможностью ходить дальше.»
        assert fresh.travel_cooldown_until is None

        logs = _teleport_logs(db_session, character.id)
        assert len(logs) == 1
        meta = logs[0].metadata_
        assert meta["from_location_id"] == LOC_FROM
        assert meta["from_location_name"] == "Пирс"
        assert meta["to_location_id"] == LOC_TO
        assert meta["to_location_name"] == "Бар «Три Галки»"
        assert meta["admin_user_id"] == ADMIN_USER.id
        assert meta["admin_username"] == ADMIN_USER.username
        assert meta["admin_action"] is True
        assert meta["gathering_cancelled"] is False
        assert "Пирс" in logs[0].description
        assert "Бар «Три Галки»" in logs[0].description

    def test_both_cleanups_are_called_with_the_pre_move_location(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        _move(admin_client, character.id)

        cleanup_mocks["cancel"].assert_awaited_once()
        assert cleanup_mocks["cancel"].await_args.args[0] == character.id
        cleanup_mocks["notify"].assert_awaited_once()
        # The location being LEFT, not the destination.
        assert cleanup_mocks["notify"].await_args.args == (character.id, LOC_FROM)

    def test_character_with_no_location_can_be_placed(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        character.current_location_id = None
        db_session.commit()

        resp = _move(admin_client, character.id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["from_location_id"] is None
        assert _reload(db_session, character.id).current_location_id == LOC_TO
        assert cleanup_mocks["notify"].await_args.args == (character.id, None)

    def test_gathering_is_cancelled_then_the_character_moves(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        cleanup_mocks["cancel"].return_value = {
            "cancelled": True, "session_id": 42, "stamina_refunded": 3,
        }

        resp = _move(admin_client, character.id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["gathering_cancelled"] is True
        # The admin reason must be threaded through — otherwise the session row
        # is mislabelled `interrupted_by_battle`.
        assert cleanup_mocks["cancel"].await_args.kwargs["reason"] == "admin_teleport"

        assert _reload(db_session, character.id).current_location_id == LOC_TO
        logs = _teleport_logs(db_session, character.id)
        assert len(logs) == 1
        assert logs[0].metadata_["gathering_cancelled"] is True

    def test_two_moves_write_two_journal_rows(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        assert _move(admin_client, character.id, LOC_TO).status_code == 200
        assert _move(admin_client, character.id, LOC_FROM).status_code == 200
        assert len(_teleport_logs(db_session, character.id)) == 2
        assert _reload(db_session, character.id).current_location_id == LOC_FROM


# ===========================================================================
# 6. THE INVARIANT — no cleanup, no move
# ===========================================================================

class TestCleanupInvariant:
    """§3.3: every cleanup runs BEFORE the state change, and the state change
    is a single local commit. Each of these tests breaks one cleanup and then
    asserts the *absence* of a move."""

    def test_gate_cleanup_failure_aborts_with_502_and_does_not_move(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        cleanup_mocks["notify"].side_effect = locations_client.LocationsServiceError(
            "гашение намерений в покидаемой локации",
        )

        with patch.object(crud, "apply_admin_move", wraps=crud.apply_admin_move) as spy:
            resp = _move(admin_client, character.id)

        assert resp.status_code == 502
        assert "Перенос отменён" in resp.json()["detail"]
        # The write was never even attempted.
        spy.assert_not_called()
        _assert_untouched(db_session, character)

    def test_gathering_cancel_failure_aborts_before_the_gate_cleanup(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        cleanup_mocks["cancel"].side_effect = locations_client.LocationsServiceError(
            "отмена сбора ресурсов",
        )

        with patch.object(crud, "apply_admin_move", wraps=crud.apply_admin_move) as spy:
            resp = _move(admin_client, character.id)

        assert resp.status_code == 502
        assert "Перенос отменён" in resp.json()["detail"]
        # Nothing at all ran after it.
        cleanup_mocks["notify"].assert_not_called()
        spy.assert_not_called()
        _assert_untouched(db_session, character)

    def test_character_is_still_in_the_old_location_while_cleanup_runs(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        """Ordering, observed rather than assumed: at the instant the gate
        cleanup executes, the database still holds the OLD location. If the
        write ever moved ahead of the cleanup, this fails."""
        observed = {}

        async def _observe(character_id, from_location_id):
            row = db_session.execute(
                sa_text("SELECT current_location_id FROM characters WHERE id = :c"),
                {"c": character_id},
            ).fetchone()
            observed["location_during_cleanup"] = row[0]
            observed["from_location_id"] = from_location_id
            return {"ok": True, "gates_expired": 1,
                    "gate_requests_expired": 0, "party_pruned": False}

        cleanup_mocks["notify"].side_effect = _observe

        resp = _move(admin_client, character.id)

        assert resp.status_code == 200, resp.text
        assert observed["location_during_cleanup"] == LOC_FROM
        assert observed["from_location_id"] == LOC_FROM
        assert _reload(db_session, character.id).current_location_id == LOC_TO

    def test_a_failed_commit_leaves_the_character_where_they_were(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        """The last row of the §3.3 table: a DB failure after the cleanups is
        the harmless "left and came back" state — never a half-written move."""
        from sqlalchemy.exc import SQLAlchemyError

        with patch.object(
            crud, "apply_admin_move", side_effect=SQLAlchemyError("boom"),
        ):
            resp = _move(admin_client, character.id)

        assert resp.status_code == 500
        _assert_untouched(db_session, character)

    def test_no_journal_row_survives_an_aborted_move(
        self, admin_client, db_session, character, cleanup_mocks,
    ):
        """An `admin_teleport` row is a claim that the move happened. An
        aborted move must not leave that claim behind."""
        cleanup_mocks["notify"].side_effect = locations_client.LocationsServiceError("x")
        _move(admin_client, character.id)

        assert db_session.query(models.CharacterLog).filter_by(
            event_type="admin_teleport",
        ).count() == 0
