"""
Tests for FEAT-123 — character-service teleport flow + admin links CRUD (T15).

Covers:
- POST /characters/npcs/{id}/teleport — success, insufficient gold, cooldown,
  broken link, source not teleport master, player not in source location.
- GET /characters/npcs/{id}/teleport-options — happy path + auto-filtering.
- Admin CRUD /characters/admin/teleport-links — bidirectional/non-bidirectional
  create, validation, duplicates, delete with reverse, auth (401/403).
- NPC role change side-effect: purge of links when role moves away from
  teleport_master (covered via direct CRUD purge — endpoint hits cross-service
  HTTP that is out of scope here).
- Concurrency smoke: cooldown blocks the second teleport.
- FEAT-162 task #6/#11: the shared "character left a location" cleanup is now
  called after every successful teleport, with the PRE-teleport location, and
  is best-effort — a failing locations-service must not fail the teleport.

Note on `requests` (FEAT-162 task #11): `crud.execute_teleport` now makes a real
outbound HTTP call through `locations_client.notify_character_left_location_sync`.
The autouse `_stub_internal_http` fixture below intercepts it, so the suite never
touches a live locations-service — before that fixture existed, running these
tests inside the compose network expired real gates in the dev database.
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    text as sa_text,
)

import database
from database import Base
import models
import crud
from main import app, get_db
from auth_http import (
    get_admin_user,
    get_current_user_via_http,
    OAUTH2_SCHEME,
    UserRead,
)


# ---------------------------------------------------------------------------
# Extra tables required by raw SQL inside crud.execute_teleport / options
#   - users (current_character lookup — ЭТО НАСТОЯЩЕЕ имя колонки в БД;
#     `current_character_id` существует только в ответе user-service /users/me)
#   - Locations (location name lookup)
# Both belong to other services in production but live in the same DB.
# ---------------------------------------------------------------------------

class _UsersTable(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    current_character = Column(Integer, nullable=True)
    username = Column(String(80), nullable=True)


class _LocationsTable(Base):
    __tablename__ = "Locations"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAYER_USER_ID = 100
LOC_A_ID = 10
LOC_B_ID = 20

_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=[
        "npcs:read", "npcs:create", "npcs:update", "npcs:delete",
        "characters:read",
    ],
)

_PLAYER_USER = UserRead(
    id=PLAYER_USER_ID,
    username="player",
    role="user",
    permissions=[],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)

    # Seed Locations
    session.execute(
        sa_text("INSERT INTO Locations (id, name) VALUES (:id, :name)"),
        {"id": LOC_A_ID, "name": "Локация A"},
    )
    session.execute(
        sa_text("INSERT INTO Locations (id, name) VALUES (:id, :name)"),
        {"id": LOC_B_ID, "name": "Локация B"},
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


def _make_character(
    session,
    *,
    name,
    is_npc,
    npc_role,
    location_id,
    user_id=None,
    currency_balance=0,
    last_teleport_at=None,
):
    char = models.Character(
        name=name,
        id_race=1,
        id_subrace=1,
        id_class=1,
        appearance="test",
        avatar="test.jpg",
        is_npc=is_npc,
        npc_role=npc_role,
        npc_status="alive" if is_npc else None,
        current_location_id=location_id,
        level=1,
        stat_points=0,
        currency_balance=currency_balance,
        user_id=user_id,
        last_teleport_at=last_teleport_at,
    )
    session.add(char)
    session.commit()
    session.refresh(char)
    return char


@pytest.fixture
def world(db_session):
    """Create two teleport-master NPCs in two locations + a player in loc A."""
    npc_a = _make_character(
        db_session, name="Мастер A", is_npc=True,
        npc_role="teleport_master", location_id=LOC_A_ID,
    )
    npc_b = _make_character(
        db_session, name="Мастер B", is_npc=True,
        npc_role="teleport_master", location_id=LOC_B_ID,
    )
    player = _make_character(
        db_session, name="Игрок", is_npc=False, npc_role=None,
        location_id=LOC_A_ID, user_id=PLAYER_USER_ID, currency_balance=500,
    )

    # link A -> B (cost 100), and B -> A (cost 100)
    link_ab = models.TeleportLink(
        from_npc_id=npc_a.id, to_npc_id=npc_b.id, cost_gold=100,
    )
    link_ba = models.TeleportLink(
        from_npc_id=npc_b.id, to_npc_id=npc_a.id, cost_gold=100,
    )
    db_session.add_all([link_ab, link_ba])
    db_session.commit()
    db_session.refresh(link_ab)
    db_session.refresh(link_ba)

    # users row pointing at our player
    db_session.execute(
        sa_text(
            "INSERT INTO users (id, current_character, username) "
            "VALUES (:id, :cid, :u)"
        ),
        {"id": PLAYER_USER_ID, "cid": player.id, "u": "player"},
    )
    db_session.commit()

    return {
        "npc_a": npc_a,
        "npc_b": npc_b,
        "player": player,
        "link_ab": link_ab,
        "link_ba": link_ba,
    }


def _player_overrides(db_session):
    def override_get_db():
        yield db_session

    def override_user():
        return _PLAYER_USER

    def override_token():
        return "fake-player-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_user
    app.dependency_overrides[OAUTH2_SCHEME] = override_token


def _admin_overrides(db_session):
    def override_get_db():
        yield db_session

    def override_admin():
        return _ADMIN_USER

    def override_token():
        return "fake-admin-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token


@pytest.fixture(autouse=True)
def _stub_internal_http():
    """Intercept the outbound cleanup POST of `execute_teleport`.

    Patched at the `requests` level rather than at
    `locations_client.notify_character_left_location_sync`, so the helper's own
    contract — never raise, return a bool — stays under test instead of being
    mocked away. Tests that need a failing locations-service simply re-patch
    `requests.post` inside their own body.
    """
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        yield mock_post


@pytest.fixture
def player_client(db_session):
    _player_overrides(db_session)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_session):
    _admin_overrides(db_session)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ===========================================================================
# 1. POST /characters/npcs/{id}/teleport — happy path
# ===========================================================================

class TestTeleportSuccess:
    def test_teleport_success_path(self, player_client, db_session, world):
        """Gold deducted, location moved, last_teleport_at set, gold tx logged."""
        before_balance = world["player"].currency_balance

        with patch.object(crud, "log_gold_transaction", wraps=crud.log_gold_transaction) as spy:
            resp = player_client.post(
                f"/characters/npcs/{world['npc_a'].id}/teleport",
                json={"link_id": world["link_ab"].id},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["new_location_id"] == LOC_B_ID
        assert body["new_location_name"] == "Локация B"
        assert body["currency_balance"] == before_balance - 100
        assert body["last_teleport_at"] is not None

        # log_gold_transaction must have been called once with negative amount
        assert spy.called
        kwargs = spy.call_args.kwargs
        assert kwargs["amount"] == -100
        assert kwargs["transaction_type"] == "teleport"

        # DB-level assertions
        db_session.expire_all()
        player = db_session.query(models.Character).filter_by(id=world["player"].id).first()
        assert player.current_location_id == LOC_B_ID
        assert player.currency_balance == before_balance - 100
        assert player.last_teleport_at is not None

        tx = (
            db_session.query(models.GoldTransaction)
            .filter_by(character_id=player.id, transaction_type="teleport")
            .first()
        )
        assert tx is not None
        assert tx.amount == -100


# ===========================================================================
# 2. POST teleport — error paths
# ===========================================================================

class TestTeleportErrors:
    def test_insufficient_gold_returns_402(self, player_client, db_session, world):
        # Drain the player's gold
        world["player"].currency_balance = 10
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 402
        detail = resp.json()["detail"]
        assert detail["error"] == "insufficient_gold"
        assert detail["required"] == 100

        # Player must NOT have moved
        db_session.expire_all()
        player = db_session.query(models.Character).filter_by(id=world["player"].id).first()
        assert player.current_location_id == LOC_A_ID

    def test_cooldown_active_returns_409(self, player_client, db_session, world):
        # Set last_teleport_at to 1 hour ago
        world["player"].last_teleport_at = datetime.utcnow() - timedelta(hours=1)
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["error"] == "cooldown_active"
        assert detail["cooldown_seconds_remaining"] > 0
        assert detail["cooldown_seconds_remaining"] <= 23 * 3600 + 60

    def test_broken_link_target_role_downgraded_returns_422(
        self, player_client, db_session, world
    ):
        # Demote target NPC away from teleport_master
        world["npc_b"].npc_role = "merchant"
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 422

    def test_broken_link_filtered_from_options(self, player_client, db_session, world):
        """If target NPC role is downgraded, options endpoint hides the link."""
        world["npc_b"].npc_role = "guard"
        db_session.commit()

        resp = player_client.get(
            f"/characters/npcs/{world['npc_a'].id}/teleport-options"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["options"] == []

    def test_source_not_teleport_master_returns_422(
        self, player_client, db_session, world
    ):
        # Demote source NPC
        world["npc_a"].npc_role = "merchant"
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 422

    def test_player_not_in_source_npc_location_returns_422(
        self, player_client, db_session, world
    ):
        # Move the player elsewhere
        world["player"].current_location_id = 999
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 422


# ===========================================================================
# 3. GET teleport-options
# ===========================================================================

class TestTeleportOptions:
    def test_options_returns_target_location_name(
        self, player_client, db_session, world
    ):
        resp = player_client.get(
            f"/characters/npcs/{world['npc_a'].id}/teleport-options"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["from_npc_id"] == world["npc_a"].id
        assert body["cooldown_seconds_remaining"] == 0
        assert len(body["options"]) == 1
        opt = body["options"][0]
        assert opt["to_npc_id"] == world["npc_b"].id
        assert opt["to_location_id"] == LOC_B_ID
        assert opt["to_location_name"] == "Локация B"
        assert opt["cost_gold"] == 100

    def test_options_404_when_not_teleport_master(
        self, player_client, db_session, world
    ):
        world["npc_a"].npc_role = "guard"
        db_session.commit()

        resp = player_client.get(
            f"/characters/npcs/{world['npc_a'].id}/teleport-options"
        )
        assert resp.status_code == 404


# ===========================================================================
# 4. Admin CRUD /admin/teleport-links
# ===========================================================================

class TestAdminTeleportLinksCRUD:
    def test_create_bidirectional_creates_two_rows(self, admin_client, db_session):
        # Two fresh teleport masters
        npc1 = _make_character(
            db_session, name="M1", is_npc=True,
            npc_role="teleport_master", location_id=LOC_A_ID,
        )
        npc2 = _make_character(
            db_session, name="M2", is_npc=True,
            npc_role="teleport_master", location_id=LOC_B_ID,
        )

        resp = admin_client.post(
            "/characters/admin/teleport-links",
            json={
                "from_npc_id": npc1.id,
                "to_npc_id": npc2.id,
                "cost_gold": 50,
                "bidirectional": True,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == 2

        rows = (
            db_session.query(models.TeleportLink)
            .filter(
                (models.TeleportLink.from_npc_id == npc1.id)
                | (models.TeleportLink.from_npc_id == npc2.id)
            )
            .all()
        )
        assert len(rows) == 2

    def test_create_non_bidirectional_creates_one_row(self, admin_client, db_session):
        npc1 = _make_character(
            db_session, name="N1", is_npc=True,
            npc_role="teleport_master", location_id=LOC_A_ID,
        )
        npc2 = _make_character(
            db_session, name="N2", is_npc=True,
            npc_role="teleport_master", location_id=LOC_B_ID,
        )

        resp = admin_client.post(
            "/characters/admin/teleport-links",
            json={
                "from_npc_id": npc1.id,
                "to_npc_id": npc2.id,
                "cost_gold": 75,
                "bidirectional": False,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == 1

    def test_create_with_non_teleport_master_returns_422(
        self, admin_client, db_session
    ):
        npc1 = _make_character(
            db_session, name="TM", is_npc=True,
            npc_role="teleport_master", location_id=LOC_A_ID,
        )
        npc2 = _make_character(
            db_session, name="Merchant", is_npc=True,
            npc_role="merchant", location_id=LOC_B_ID,
        )

        resp = admin_client.post(
            "/characters/admin/teleport-links",
            json={
                "from_npc_id": npc1.id,
                "to_npc_id": npc2.id,
                "cost_gold": 50,
                "bidirectional": True,
            },
        )
        assert resp.status_code == 422

    def test_create_duplicate_pair_returns_409(self, admin_client, db_session, world):
        # link A->B already exists in `world`
        resp = admin_client.post(
            "/characters/admin/teleport-links",
            json={
                "from_npc_id": world["npc_a"].id,
                "to_npc_id": world["npc_b"].id,
                "cost_gold": 100,
                "bidirectional": False,
            },
        )
        assert resp.status_code == 409

    def test_delete_with_delete_reverse_true_removes_both(
        self, admin_client, db_session, world
    ):
        link_id = world["link_ab"].id
        resp = admin_client.delete(
            f"/characters/admin/teleport-links/{link_id}",
            params={"delete_reverse": "true"},
        )
        assert resp.status_code == 200

        remaining = (
            db_session.query(models.TeleportLink)
            .filter(
                (
                    (models.TeleportLink.from_npc_id == world["npc_a"].id)
                    & (models.TeleportLink.to_npc_id == world["npc_b"].id)
                )
                | (
                    (models.TeleportLink.from_npc_id == world["npc_b"].id)
                    & (models.TeleportLink.to_npc_id == world["npc_a"].id)
                )
            )
            .all()
        )
        assert remaining == []


# ===========================================================================
# 5. Admin CRUD — auth
# ===========================================================================

class TestAdminTeleportLinksAuth:
    def test_unauthenticated_request_rejected(self, db_session):
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/characters/admin/teleport-links")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()

    def test_regular_user_rejected(self, db_session):
        regular_user = UserRead(
            id=2, username="player", role="user", permissions=[]
        )

        def override_get_db():
            yield db_session

        def override_user():
            return regular_user

        def override_token():
            return "fake-user-token"

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user_via_http] = override_user
        app.dependency_overrides[OAUTH2_SCHEME] = override_token
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/characters/admin/teleport-links")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ===========================================================================
# 6. NPC role change side-effect — purge_teleport_links_for_npc
# ===========================================================================

class TestNpcRoleChangeSideEffect:
    def test_purge_removes_all_links_for_npc(self, db_session, world):
        """Direct CRUD test: purge removes both incoming and outgoing links."""
        # Sanity: both links exist
        assert db_session.query(models.TeleportLink).count() == 2

        crud.purge_teleport_links_for_npc(db_session, world["npc_a"].id)
        db_session.commit()

        rows = db_session.query(models.TeleportLink).all()
        # Both A->B and B->A involved npc_a, so both should be gone
        assert rows == []


# ===========================================================================
# 7. Concurrency smoke — second teleport blocked by cooldown
# ===========================================================================

class TestTeleportConcurrencySmoke:
    def test_second_teleport_blocked_by_cooldown(
        self, player_client, db_session, world
    ):
        """Two sequential teleports: first succeeds, second fails with 409.

        SQLite in-memory cannot model true row-locking races, but the cooldown
        guarantees only one of N requests can succeed in a 24h window — which
        is the same end-state guaranteed by FOR UPDATE in production MySQL.
        """
        resp1 = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp1.status_code == 200, resp1.text

        # Player is now in B; to attempt a second teleport from B we need the
        # B->A link, with the player already in loc B (which they are after
        # the first teleport). Cooldown should kick in.
        resp2 = player_client.post(
            f"/characters/npcs/{world['npc_b'].id}/teleport",
            json={"link_id": world["link_ba"].id},
        )
        assert resp2.status_code == 409
        assert resp2.json()["detail"]["error"] == "cooldown_active"


# ===========================================================================
# 8. FEAT-162 task #6 — the shared cleanup after a Teleport Master jump
# ===========================================================================

class TestTeleportLeavesNoGatesBehind:
    """Before FEAT-162 the Teleport Master wrote `current_location_id` and did
    nothing else, so a teleported character kept live action gates in the
    location they had left — they could still attack, and be attacked by,
    people who were no longer anywhere near them. The fix routes the teleport
    through the same `POST /locations/internal/character-left-location` cleanup
    the admin move uses.

    Unlike the admin move, this call is deliberately best-effort and runs
    AFTER the commit (§3.5): the player has already been charged gold and the
    function holds a row lock it must not carry across the network. So the
    tests here assert two different things — that the call is made with the
    right arguments, and that failing it never costs the player their teleport.
    """

    def test_cleanup_is_called_with_the_pre_teleport_location(
        self, player_client, db_session, world, _stub_internal_http,
    ):
        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 200, resp.text

        assert _stub_internal_http.call_count == 1
        call = _stub_internal_http.call_args
        assert "/locations/internal/character-left-location" in call.args[0]
        payload = call.kwargs["json"]
        assert payload["character_id"] == world["player"].id
        # The location being LEFT (A), never the destination (B). Sending B
        # would expire the gates the character has just arrived to use.
        assert payload["from_location_id"] == LOC_A_ID
        assert "X-Internal-Token" in call.kwargs["headers"]

    def test_cleanup_is_not_called_when_the_teleport_is_refused(
        self, player_client, db_session, world, _stub_internal_http,
    ):
        """A refused teleport leaves the character where they are, so their
        gates there must stay alive."""
        world["player"].currency_balance = 1
        db_session.commit()

        resp = player_client.post(
            f"/characters/npcs/{world['npc_a'].id}/teleport",
            json={"link_id": world["link_ab"].id},
        )
        assert resp.status_code == 402
        _stub_internal_http.assert_not_called()

    def test_teleport_succeeds_when_locations_service_is_down(
        self, player_client, db_session, world,
    ):
        """locations-service unreachable: the player paid, so the teleport
        completes anyway and the failure is only logged."""
        with patch("requests.post", side_effect=OSError("connection refused")):
            resp = player_client.post(
                f"/characters/npcs/{world['npc_a'].id}/teleport",
                json={"link_id": world["link_ab"].id},
            )

        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        player = db_session.query(models.Character).filter_by(
            id=world["player"].id,
        ).first()
        assert player.current_location_id == LOC_B_ID
        assert player.currency_balance == 400

    def test_teleport_succeeds_when_the_cleanup_returns_an_error_status(
        self, player_client, db_session, world,
    ):
        with patch("requests.post", return_value=MagicMock(status_code=500)):
            resp = player_client.post(
                f"/characters/npcs/{world['npc_a'].id}/teleport",
                json={"link_id": world["link_ab"].id},
            )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        player = db_session.query(models.Character).filter_by(
            id=world["player"].id,
        ).first()
        assert player.current_location_id == LOC_B_ID

    def test_helper_never_raises_and_reports_the_outcome(self):
        """The contract `execute_teleport` relies on, tested directly."""
        import locations_client

        with patch("requests.post", side_effect=RuntimeError("boom")):
            assert locations_client.notify_character_left_location_sync(1, 2) is False
        with patch("requests.post", return_value=MagicMock(status_code=401)):
            assert locations_client.notify_character_left_location_sync(1, 2) is False
        with patch("requests.post", return_value=MagicMock(status_code=200)):
            assert locations_client.notify_character_left_location_sync(1, 2) is True


# ===========================================================================
# 9. The fixture itself — it must model the REAL database
# ===========================================================================

class TestFixtureMirrorsProductionSchema:
    """`crud.execute_teleport` reads `users.current_character` with raw SQL.
    This suite once declared that mirror column as `current_character_id`,
    a name that exists only in the user-service `/users/me` response — so the
    tests passed green against a schema the database does not have while the
    Teleport Master returned 500 in production for the whole life of FEAT-123.

    A fixture that models a different database than production tests nothing,
    so the column name is pinned here explicitly rather than left implicit in
    a table definition nobody re-reads.
    """

    def test_users_mirror_has_the_production_column_name(self, db_session):
        columns = {
            row[1] for row in db_session.execute(
                sa_text("PRAGMA table_info(users)")
            ).fetchall()
        }
        assert "current_character" in columns
        assert "current_character_id" not in columns

    def test_the_raw_sql_of_execute_teleport_runs_against_the_fixture(
        self, db_session, world,
    ):
        """The exact statement from `crud.execute_teleport` — if the mirror
        table drifts from the real schema again, this is where it shows."""
        row = db_session.execute(
            sa_text("SELECT current_character FROM users WHERE id = :uid"),
            {"uid": PLAYER_USER_ID},
        ).fetchone()
        assert row is not None
        assert row[0] == world["player"].id
