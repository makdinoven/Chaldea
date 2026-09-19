"""FEAT-168, review #2 gap 2 (character-service half) — the XP reward paths run
against a REAL session, end to end.

The earlier guard tests handed the reward helpers an `AsyncMock()` / `MagicMock()`
session. A mock session has no transaction, no flush, no identity map and no
expiry, so it can only prove that the code calls what it calls — it cannot prove
that the *whole operation* survived the cross-service XP-book lookup that
FEAT-168 put on these paths. In locations-service exactly that hole let a broken
quest reward ship green (XP written, quest left active). The same three paths
exist here, so they get the same treatment:

  * `POST /characters/{cid}/add_rewards` — battle rewards, and the battle-pass
    variant that carries its own `xp_source`;
  * `crud.grant_title` — the title reward, XP and the `character_titles` row.

Every assertion reads the result back out of the database, and each test checks
**both halves** of the operation (the XP *and* the record that proves the
operation completed), because a half-applied reward is the failure mode under
test. Only the network boundary (`crud.httpx.get`) is mocked; no helper name is
patched, so these tests do not care how the reward path is factored internally.

The last class is the concurrency case: `grant_title`'s duplicate check is a
SELECT followed by an INSERT, so a second grant that lands in between must still
answer `already_has` rather than a 500.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient

import crud
import models
import auth_http
from main import app, get_db

# FEAT-169: POST /characters/{cid}/add_rewards закрыт internal-токеном.
auth_http.INTERNAL_SERVICE_TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


CHARACTER_ID = 1
TITLE_ID = 3
START_XP = 1000
START_ACTIVE_XP = 40
START_GOLD = 250

BATTLE = "character_xp_battle_bonus"
PASS = "character_xp_pass_bonus"
TITLE = "character_xp_title_bonus"


# ---------------------------------------------------------------------------
# Helpers (same shapes as test_xp_books.py)
# ---------------------------------------------------------------------------

def _seed_reference_data(session):
    if not session.query(models.Race).filter_by(id_race=1).first():
        session.add(models.Race(id_race=1, name="Человек"))
    session.flush()
    if not session.query(models.Subrace).filter_by(id_subrace=1).first():
        session.add(models.Subrace(id_subrace=1, id_race=1, name="Норд"))
    session.flush()
    if not session.query(models.Class).filter_by(id_class=1).first():
        session.add(models.Class(id_class=1, name="Воин"))
    session.commit()


def _create_character(session, character_id=CHARACTER_ID, currency_balance=START_GOLD):
    char = models.Character(
        id=character_id, name=f"Герой{character_id}", id_subrace=1,
        biography="bio", personality="pers", id_class=1,
        currency_balance=currency_balance, user_id=10, appearance="appearance",
        sex="male", id_race=1, avatar="/avatar.jpg", is_npc=False,
        level=1, stat_points=0,
    )
    session.add(char)
    session.commit()
    return char


def _create_title(session, *, passive=0, active=0, title_id=TITLE_ID):
    title = models.Title(
        id_title=title_id, name=f"Титул{title_id}", description="d",
        rarity="common", reward_passive_exp=passive, reward_active_exp=active,
        sort_order=0, is_active=True,
    )
    session.add(title)
    session.commit()
    return title


def _insert_attributes(session, character_id=CHARACTER_ID,
                       passive=START_XP, active=START_ACTIVE_XP):
    session.execute(
        text("INSERT INTO character_attributes "
             "(character_id, passive_experience, active_experience) "
             "VALUES (:cid, :p, :a)"),
        {"cid": character_id, "p": passive, "a": active},
    )
    session.commit()


def _read_attributes(session, character_id=CHARACTER_ID):
    row = session.execute(
        text("SELECT passive_experience, active_experience "
             "FROM character_attributes WHERE character_id = :cid"),
        {"cid": character_id},
    ).fetchone()
    return (row[0], row[1])


def _read_gold(session, character_id=CHARACTER_ID):
    return session.execute(
        text("SELECT currency_balance FROM characters WHERE id = :cid"),
        {"cid": character_id},
    ).fetchone()[0]


def _read_title_rows(session, character_id=CHARACTER_ID, title_id=TITLE_ID):
    return session.execute(
        text("SELECT character_id, title_id, is_custom FROM character_titles "
             "WHERE character_id = :cid AND title_id = :tid"),
        {"cid": character_id, "tid": title_id},
    ).fetchall()


def _multiplier_response(value):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"character_id": CHARACTER_ID, "multiplier": value}
    return resp


def _buff_types_sent(mock_get):
    return [c.kwargs["params"]["buff_type"] for c in mock_get.call_args_list]


# ---------------------------------------------------------------------------
# Fixtures — a real SQLite session with the cross-service attributes table
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(test_engine, test_session_factory):
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    session.execute(text("DROP TABLE IF EXISTS character_attributes"))
    session.execute(text(
        "CREATE TABLE character_attributes ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  character_id INTEGER NOT NULL,"
        "  passive_experience INTEGER DEFAULT 0,"
        "  active_experience INTEGER DEFAULT 0"
        ")"
    ))
    session.commit()
    _seed_reference_data(session)
    _create_character(session)
    _insert_attributes(session)
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client_with_db(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Battle rewards through the real endpoint and a real session
# ═══════════════════════════════════════════════════════════════════════════

class TestAddRewardsOnARealSession:

    @patch("crud.httpx.get")
    def test_xp_and_gold_both_land_and_the_response_agrees(self, mock_get,
                                                           client_with_db, db_session):
        mock_get.return_value = _multiplier_response(1.35)

        resp = client_with_db.post(
            f"/characters/{CHARACTER_ID}/add_rewards",
            json={"xp": 100, "gold": 50}, headers=INTERNAL_HEADERS
        )

        assert resp.status_code == 200, resp.text
        passive, active = _read_attributes(db_session)
        assert passive == START_XP + 135
        assert active == START_ACTIVE_XP, "skill points are not accelerated by books"
        assert _read_gold(db_session) == START_GOLD + 50
        assert resp.json()["new_xp"] == START_XP + 135
        assert resp.json()["new_balance"] == START_GOLD + 50

    @patch("crud.httpx.get")
    def test_xp_only_reward_still_writes_everything(self, mock_get,
                                                    client_with_db, db_session):
        """The shape that broke the quest path: XP but no gold, so the session
        stays clean until the XP write."""
        mock_get.return_value = _multiplier_response(1.35)

        resp = client_with_db.post(
            f"/characters/{CHARACTER_ID}/add_rewards", json={"xp": 100, "gold": 0}, headers=INTERNAL_HEADERS)

        assert resp.status_code == 200, resp.text
        assert _read_attributes(db_session)[0] == START_XP + 135
        assert _read_gold(db_session) == START_GOLD
        assert resp.json()["new_xp"] == START_XP + 135

    @patch("crud.httpx.get")
    def test_default_source_is_battle(self, mock_get, client_with_db, db_session):
        mock_get.return_value = _multiplier_response(1.0)
        client_with_db.post(f"/characters/{CHARACTER_ID}/add_rewards",
                            json={"xp": 10, "gold": 0}, headers=INTERNAL_HEADERS)
        assert _buff_types_sent(mock_get) == [BATTLE]

    @patch("crud.httpx.get")
    def test_battle_pass_source_travels_and_is_applied(self, mock_get,
                                                       client_with_db, db_session):
        mock_get.return_value = _multiplier_response(1.5)

        resp = client_with_db.post(
            f"/characters/{CHARACTER_ID}/add_rewards",
            json={"xp": 100, "gold": 0, "xp_source": PASS}, headers=INTERNAL_HEADERS
        )

        assert resp.status_code == 200, resp.text
        assert _buff_types_sent(mock_get) == [PASS], \
            "the battle pass must not be boosted by the battle book"
        assert _read_attributes(db_session)[0] == START_XP + 150

    @patch("crud.httpx.get")
    def test_fail_open_awards_the_base_xp_and_still_commits_the_gold(
            self, mock_get, client_with_db, db_session):
        mock_get.side_effect = RuntimeError("inventory-service недоступен")

        resp = client_with_db.post(
            f"/characters/{CHARACTER_ID}/add_rewards", json={"xp": 100, "gold": 50}, headers=INTERNAL_HEADERS)

        assert resp.status_code == 200, resp.text
        assert _read_attributes(db_session)[0] == START_XP + 100
        assert _read_gold(db_session) == START_GOLD + 50

    @patch("crud.httpx.get")
    def test_zero_xp_never_asks_inventory(self, mock_get, client_with_db, db_session):
        client_with_db.post(f"/characters/{CHARACTER_ID}/add_rewards",
                            json={"xp": 0, "gold": 50}, headers=INTERNAL_HEADERS)
        mock_get.assert_not_called()
        assert _read_attributes(db_session)[0] == START_XP
        assert _read_gold(db_session) == START_GOLD + 50

    @patch("crud.httpx.get")
    def test_unknown_character_changes_nothing(self, mock_get, client_with_db, db_session):
        mock_get.return_value = _multiplier_response(1.35)
        resp = client_with_db.post("/characters/9999/add_rewards",
                                   json={"xp": 100, "gold": 50}, headers=INTERNAL_HEADERS)
        assert resp.status_code == 404
        assert _read_attributes(db_session)[0] == START_XP
        assert _read_gold(db_session) == START_GOLD

    @patch("crud.httpx.get")
    def test_invalid_xp_source_is_refused_in_russian_and_writes_nothing(
            self, mock_get, client_with_db, db_session):
        resp = client_with_db.post(
            f"/characters/{CHARACTER_ID}/add_rewards",
            json={"xp": 100, "gold": 50, "xp_source": "xp_bonus"}, headers=INTERNAL_HEADERS
        )
        assert resp.status_code == 422
        assert "Недопустимый источник опыта" in str(resp.json()["detail"])
        mock_get.assert_not_called()
        assert _read_attributes(db_session)[0] == START_XP
        assert _read_gold(db_session) == START_GOLD


# ═══════════════════════════════════════════════════════════════════════════
# The title path on a real session
# ═══════════════════════════════════════════════════════════════════════════

class TestGrantTitleOnARealSession:

    @patch("crud.httpx.get")
    def test_title_row_and_xp_both_land(self, mock_get, db_session):
        mock_get.return_value = _multiplier_response(1.35)
        _create_title(db_session, passive=100, active=10)

        # Множитель приходит от эндпоинта (ревью #3: grant_title сам в сеть не ходит)
        ok, status = crud.grant_title(db_session, CHARACTER_ID, TITLE_ID, xp_multiplier=1.35)

        assert (ok, status) == (True, "granted")
        mock_get.assert_not_called()
        rows = _read_title_rows(db_session)
        assert len(rows) == 1, "the title record must exist — half a grant is a bug"
        passive, active = _read_attributes(db_session)
        assert passive == START_XP + 135
        assert active == START_ACTIVE_XP + 10, "skill points are never multiplied"

    @patch("crud.httpx.get")
    def test_a_passive_only_title_still_records_the_grant(self, mock_get, db_session):
        mock_get.return_value = _multiplier_response(2.0)
        _create_title(db_session, passive=50, active=0)

        ok, status = crud.grant_title(db_session, CHARACTER_ID, TITLE_ID, xp_multiplier=2.0)

        assert (ok, status) == (True, "granted")
        assert len(_read_title_rows(db_session)) == 1
        assert _read_attributes(db_session) == (START_XP + 100, START_ACTIVE_XP)

    @patch("crud.httpx.get")
    def test_no_multiplier_grants_the_title_with_base_xp(self, mock_get, db_session):
        """`None` (книги нет или inventory-service не ответил) = базовый опыт."""
        _create_title(db_session, passive=100, active=0)

        ok, status = crud.grant_title(db_session, CHARACTER_ID, TITLE_ID, xp_multiplier=None)

        assert (ok, status) == (True, "granted")
        assert len(_read_title_rows(db_session)) == 1
        assert _read_attributes(db_session)[0] == START_XP + 100

    @patch("crud.httpx.get")
    def test_second_grant_is_idempotent_and_awards_no_extra_xp(self, mock_get, db_session):
        mock_get.return_value = _multiplier_response(1.35)
        _create_title(db_session, passive=100, active=0)

        crud.grant_title(db_session, CHARACTER_ID, TITLE_ID, xp_multiplier=1.35)
        ok, status = crud.grant_title(db_session, CHARACTER_ID, TITLE_ID, xp_multiplier=1.35)

        assert (ok, status) == (True, "already_has")
        assert len(_read_title_rows(db_session)) == 1
        assert _read_attributes(db_session)[0] == START_XP + 135

    @patch("crud.httpx.get")
    def test_a_title_without_rewards_writes_no_xp(self, mock_get, db_session):
        _create_title(db_session, passive=0, active=0)
        ok, status = crud.grant_title(db_session, CHARACTER_ID, TITLE_ID, xp_multiplier=2.0)
        assert (ok, status) == (True, "granted")
        assert len(_read_title_rows(db_session)) == 1
        assert _read_attributes(db_session) == (START_XP, START_ACTIVE_XP)

    @patch("crud.httpx.get")
    def test_unknown_title_writes_nothing(self, mock_get, db_session):
        result, status = crud.grant_title(db_session, CHARACTER_ID, 999)
        assert (result, status) == (None, "title_not_found")
        assert _read_attributes(db_session) == (START_XP, START_ACTIVE_XP)


# ═══════════════════════════════════════════════════════════════════════════
# Concurrency — the duplicate check is a SELECT then an INSERT
# ═══════════════════════════════════════════════════════════════════════════

class TestGrantTitleConcurrentDuplicate:
    """Two requests can grant the same title at the same time: both pass the
    "already has it?" check, and the second INSERT hits the primary key.

    The rule the player-facing API needs is simple: a duplicate grant is a no-op
    that reports `already_has`, never a 500.

    **How the race is simulated (updated when the bug was fixed).** The original
    version wrote the competing row from a `before_flush` hook. That row landed
    in *our own* transaction, so the fix's `rollback()` removed it too and the
    "exactly one row survives" assertion could never hold — an artefact of the
    single StaticPool in-memory connection, not a production behaviour. Here the
    competing row is **committed first** (that is what the winning request does)
    and the duplicate check is blinded for one call, which is exactly the state a
    losing request finds: the SELECT saw nothing, the row exists at INSERT time.
    """

    @staticmethod
    def _commit_the_competing_row(session, character_id=CHARACTER_ID, title_id=TITLE_ID):
        """The winning request's row: already committed by another connection."""
        session.execute(
            text("INSERT INTO character_titles (character_id, title_id, is_custom) "
                 "VALUES (:cid, :tid, 1)"),
            {"cid": character_id, "tid": title_id},
        )
        session.commit()

    @staticmethod
    def _blind_the_duplicate_check(session):
        """Make the `already has it?` SELECT miss — the losing request's view."""
        real_query = session.query

        def blind_query(*entities, **kw):
            q = real_query(*entities, **kw)
            if entities and entities[0] is models.CharacterTitle:
                return q.filter(models.CharacterTitle.title_id == -1)
            return q

        return patch.object(session, "query", blind_query)

    @patch("crud.httpx.get")
    def test_a_lost_race_reports_already_has_and_not_a_500(self, mock_get, db_session):
        mock_get.return_value = _multiplier_response(1.35)
        _create_title(db_session, passive=100, active=0)
        self._commit_the_competing_row(db_session)

        with self._blind_the_duplicate_check(db_session):
            try:
                ok, status = crud.grant_title(db_session, CHARACTER_ID, TITLE_ID)
            except IntegrityError as exc:
                pytest.fail(
                    "grant_title let a duplicate-key IntegrityError escape "
                    f"(the endpoint turns this into a 500): {exc.orig}"
                )

        assert (ok, status) == (True, "already_has")

    @patch("crud.httpx.get")
    def test_a_lost_race_does_not_double_award_the_xp(self, mock_get, db_session):
        mock_get.return_value = _multiplier_response(1.35)
        _create_title(db_session, passive=100, active=0)
        self._commit_the_competing_row(db_session)

        with self._blind_the_duplicate_check(db_session):
            try:
                crud.grant_title(db_session, CHARACTER_ID, TITLE_ID)
            except IntegrityError:
                pytest.fail("grant_title let a duplicate-key IntegrityError escape")

        db_session.rollback()
        assert len(_read_title_rows(db_session)) == 1, "exactly one title row"
        assert _read_attributes(db_session)[0] == START_XP,             "a lost race must award no title XP at all"
