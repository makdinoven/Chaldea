"""
FEAT-168 §3.9-bis D — XP books at the character-service award sites.

Two character-XP write points live in this service and both must ask
inventory-service for the multiplier of *their own* source:

  * ``crud.add_rewards_to_character`` — battle/PvE XP by default, the battle
    pass source when ``POST /characters/{cid}/add_rewards`` carries
    ``xp_source: "character_xp_pass_bonus"``.
  * ``crud._grant_title_xp`` — title XP, **passive part only**.

Covered here:
  A) the multiplier actually reaches ``character_attributes.passive_experience``
     (not just "the HTTP call happened")
  B) the exact ``buff_type`` that leaves the service for every source — these
     tests fail the moment a caller stops sending its XP source
  C) ``int(xp * multiplier)`` truncation, the profession-XP rounding rule
  D) fail-open: a broken / slow / non-200 inventory-service costs the bonus,
     never the XP itself
  E) ``xp_source`` validation — 422 «Недопустимый источник опыта»

All cross-service HTTP is mocked; no test touches a real inventory-service.
"""

import logging
from unittest.mock import patch, MagicMock

import httpx
import pytest
from sqlalchemy import String, text

import database
import models

# Patch Enum columns to String for SQLite compatibility (same as test_add_rewards)
for tbl in [
    models.Character,
    models.CharacterRequest,
    models.MobTemplate,
    models.MobLootTable,
    models.MobTemplateSkill,
    models.LocationMobSpawn,
    models.ActiveMob,
]:
    for col in tbl.__table__.columns:
        if type(col.type).__name__ == "Enum":
            col.type = String(50)

from fastapi.testclient import TestClient
from main import app, get_db

import crud
import auth_http

auth_http.INTERNAL_SERVICE_TOKEN = "test-internal-token"

BATTLE = "character_xp_battle_bonus"
POST = "character_xp_post_bonus"
QUEST = "character_xp_quest_bonus"
TITLE = "character_xp_title_bonus"
PASS = "character_xp_pass_bonus"


# ---------------------------------------------------------------------------
# Helpers
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


def _create_character(session, character_id=1, currency_balance=0):
    char = models.Character(
        id=character_id,
        name=f"Герой{character_id}",
        id_subrace=1,
        biography="bio",
        personality="pers",
        id_class=1,
        currency_balance=currency_balance,
        user_id=10,
        appearance="appearance",
        sex="male",
        id_race=1,
        avatar="/avatar.jpg",
        is_npc=False,
        level=1,
        stat_points=0,
    )
    session.add(char)
    session.commit()
    return char


def _insert_attributes(session, character_id, passive=0, active=0):
    session.execute(
        text(
            "INSERT INTO character_attributes "
            "(character_id, passive_experience, active_experience) "
            "VALUES (:cid, :p, :a)"
        ),
        {"cid": character_id, "p": passive, "a": active},
    )
    session.commit()


def _read_attributes(session, character_id):
    row = session.execute(
        text(
            "SELECT passive_experience, active_experience "
            "FROM character_attributes WHERE character_id = :cid"
        ),
        {"cid": character_id},
    ).fetchone()
    return (row[0], row[1])


def _multiplier_response(value):
    """A successful inventory-service /xp-multiplier answer."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"character_id": 1, "multiplier": value}
    return resp


def _buff_types_sent(mock_get):
    """Every ``buff_type`` query param that left the service."""
    return [c.kwargs["params"]["buff_type"] for c in mock_get.call_args_list]


# ---------------------------------------------------------------------------
# Fixtures
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
    yield TestClient(app, raise_server_exceptions=False), db_session
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# A) get_character_xp_multiplier — the lookup itself
# ═══════════════════════════════════════════════════════════════════════════

class TestGetCharacterXpMultiplier:
    @patch("crud.httpx.get")
    def test_returns_multiplier_from_inventory(self, mock_get):
        mock_get.return_value = _multiplier_response(1.35)
        assert crud.get_character_xp_multiplier(7, BATTLE) == 1.35

    @patch("crud.httpx.get")
    def test_sends_the_requested_buff_type(self, mock_get):
        """Anti-silent-failure: the source must travel as ``buff_type``."""
        mock_get.return_value = _multiplier_response(1.0)
        for source in (BATTLE, POST, QUEST, TITLE, PASS):
            mock_get.reset_mock()
            crud.get_character_xp_multiplier(7, source)
            assert mock_get.call_args.kwargs["params"] == {"buff_type": source}

    @patch("crud.httpx.get")
    def test_calls_the_internal_xp_multiplier_url_with_token(self, mock_get):
        mock_get.return_value = _multiplier_response(1.0)
        crud.get_character_xp_multiplier(42, QUEST)
        url = mock_get.call_args.args[0]
        assert url.endswith("internal/characters/42/xp-multiplier")
        assert mock_get.call_args.kwargs["headers"] == crud._internal_token_headers()

    @patch("crud.httpx.get")
    def test_unknown_source_does_not_call_inventory(self, mock_get):
        assert crud.get_character_xp_multiplier(7, "character_xp_pvp_bonus") == 1.0
        mock_get.assert_not_called()

    @patch("crud.httpx.get")
    def test_multiplier_below_one_is_clamped(self, mock_get):
        mock_get.return_value = _multiplier_response(0.5)
        assert crud.get_character_xp_multiplier(7, BATTLE) == 1.0

    @patch("crud.httpx.get", side_effect=httpx.TimeoutException("timeout"))
    def test_timeout_fails_open(self, mock_get):
        assert crud.get_character_xp_multiplier(7, BATTLE) == 1.0

    @patch("crud.httpx.get", side_effect=httpx.ConnectError("down"))
    def test_connection_error_fails_open_and_warns(self, mock_get, caplog):
        with caplog.at_level(logging.WARNING):
            assert crud.get_character_xp_multiplier(7, BATTLE) == 1.0
        assert any("множитель опыта" in r.message.lower() for r in caplog.records)

    @patch("crud.httpx.get")
    def test_http_error_status_fails_open(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(),
        )
        mock_get.return_value = resp
        assert crud.get_character_xp_multiplier(7, BATTLE) == 1.0

    @patch("crud.httpx.get")
    def test_garbage_payload_fails_open(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"multiplier": "не число"}
        mock_get.return_value = resp
        assert crud.get_character_xp_multiplier(7, BATTLE) == 1.0

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    @patch("crud.httpx.get")
    def test_nan_and_infinity_fail_open(self, mock_get, bad):
        """NaN passes every comparison; int(xp * nan) would raise and lose the XP."""
        mock_get.return_value = _multiplier_response(bad)
        assert crud.get_character_xp_multiplier(7, BATTLE) == 1.0

    @patch("crud.httpx.get")
    def test_nan_multiplier_still_awards_base_xp(self, mock_get):
        mock_get.return_value = _multiplier_response(float("nan"))
        assert crud.multiply_xp(100, crud.get_character_xp_multiplier(7, BATTLE)) == 100

    @patch("crud.httpx.get")
    def test_uses_a_five_second_timeout(self, mock_get):
        mock_get.return_value = _multiplier_response(1.0)
        crud.get_character_xp_multiplier(7, BATTLE)
        assert mock_get.call_args.kwargs["timeout"] == crud.XP_MULTIPLIER_TIMEOUT_SECONDS
        assert crud.XP_MULTIPLIER_TIMEOUT_SECONDS == 5.0


class TestMultiplyXp:
    """Pure arithmetic — the lookup is a separate, caller-owned step (review #2)."""

    def test_truncates_instead_of_rounding(self):
        # 101 * 1.25 = 126.25 → 126, not 127
        assert crud.multiply_xp(101, 1.25) == 126

    def test_no_multiplier_returns_the_base_xp(self):
        assert crud.multiply_xp(50, None) == 50

    def test_zero_and_negative_are_returned_untouched(self):
        assert crud.multiply_xp(0, 2.0) == 0
        assert crud.multiply_xp(-5, 2.0) == -5

    def test_no_in_transaction_lookup_helper_survives(self):
        """`_release_db_connection` was removed: it rolled back the caller's session."""
        assert not hasattr(crud, "_release_db_connection")
        assert not hasattr(crud, "fetch_character_xp_multiplier")


# ═══════════════════════════════════════════════════════════════════════════
# B) add_rewards_to_character — battle XP and the battle-pass source
# ═══════════════════════════════════════════════════════════════════════════

class TestAddRewardsXpBook:
    @patch("crud.httpx.get")
    def test_passive_xp_written_to_db_is_multiplied(self, mock_get, client_with_db):
        """The boosted value lands in the DB, not just in the response."""
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1, passive=100)
        mock_get.return_value = _multiplier_response(1.5)

        resp = client.post("/characters/1/add_rewards", json={"xp": 200, "gold": 0})

        assert resp.status_code == 200
        assert resp.json()["new_xp"] == 400          # 100 + int(200 * 1.5)
        passive, _active = _read_attributes(session, 1)
        assert passive == 400

    @patch("crud.httpx.get")
    def test_default_source_is_battle(self, mock_get, client_with_db):
        """No ``xp_source`` in the body ⇒ the battle book is asked for.

        Anti-silent-failure guard: this fails if battle rewards stop naming
        their source (battle-service / dungeon-service send no field).
        """
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1)
        mock_get.return_value = _multiplier_response(1.0)

        client.post("/characters/1/add_rewards", json={"xp": 10, "gold": 0})

        assert _buff_types_sent(mock_get) == [BATTLE]

    @patch("crud.httpx.get")
    def test_battle_pass_source_is_forwarded(self, mock_get, client_with_db):
        """A battle-pass reward must ask for the *pass* book, not the battle one."""
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1, passive=0)
        mock_get.return_value = _multiplier_response(2.0)

        resp = client.post(
            "/characters/1/add_rewards",
            json={"xp": 50, "gold": 0, "xp_source": PASS},
        )

        assert resp.status_code == 200
        assert _buff_types_sent(mock_get) == [PASS]
        assert resp.json()["new_xp"] == 100
        assert _read_attributes(session, 1)[0] == 100

    @pytest.mark.parametrize("source", [BATTLE, POST, QUEST, TITLE, PASS])
    @patch("crud.httpx.get")
    def test_every_character_source_is_accepted(self, mock_get, client_with_db, source):
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1)
        mock_get.return_value = _multiplier_response(1.0)

        resp = client.post(
            "/characters/1/add_rewards",
            json={"xp": 10, "gold": 0, "xp_source": source},
        )

        assert resp.status_code == 200
        assert _buff_types_sent(mock_get) == [source]

    @patch("crud.httpx.get")
    def test_gold_is_not_multiplied(self, mock_get, client_with_db):
        client, session = client_with_db
        _create_character(session, 1, currency_balance=100)
        _insert_attributes(session, 1)
        mock_get.return_value = _multiplier_response(3.0)

        resp = client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 50})

        assert resp.json()["new_balance"] == 150

    @patch("crud.httpx.get")
    def test_truncation_at_the_award_site(self, mock_get, client_with_db):
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1, passive=0)
        mock_get.return_value = _multiplier_response(1.35)

        resp = client.post("/characters/1/add_rewards", json={"xp": 7, "gold": 0})

        # 7 * 1.35 = 9.45 → 9
        assert resp.json()["new_xp"] == 9

    @patch("crud.httpx.get", side_effect=httpx.ConnectError("inventory down"))
    def test_fail_open_awards_base_xp_when_inventory_is_down(
        self, mock_get, client_with_db, caplog,
    ):
        """XP is never lost because the buff lookup failed."""
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1, passive=40)

        with caplog.at_level(logging.WARNING):
            resp = client.post("/characters/1/add_rewards", json={"xp": 60, "gold": 0})

        assert resp.status_code == 200
        assert resp.json()["new_xp"] == 100
        assert _read_attributes(session, 1)[0] == 100
        assert any("множитель опыта" in r.message.lower() for r in caplog.records)

    @patch("crud.httpx.get", side_effect=httpx.TimeoutException("slow"))
    def test_fail_open_on_timeout(self, mock_get, client_with_db):
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1, passive=0)

        resp = client.post("/characters/1/add_rewards", json={"xp": 25, "gold": 0})

        assert resp.status_code == 200
        assert resp.json()["new_xp"] == 25

    @patch("crud.httpx.get")
    def test_zero_xp_never_asks_inventory(self, mock_get, client_with_db):
        client, session = client_with_db
        _create_character(session, 1, currency_balance=10)
        _insert_attributes(session, 1, passive=5)

        resp = client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 5})

        assert resp.status_code == 200
        mock_get.assert_not_called()
        assert resp.json()["new_xp"] == 5

    @patch("crud.httpx.get")
    def test_level_up_uses_the_boosted_xp(self, mock_get, client_with_db):
        """The level check sees the multiplied total, not the base one."""
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1, passive=0)
        mock_get.return_value = _multiplier_response(2.0)

        with patch("crud.check_and_update_level") as mock_level:
            client.post("/characters/1/add_rewards", json={"xp": 100, "gold": 0})

        mock_level.assert_called_once_with(session, 1, 200)


class TestAddRewardsXpSourceValidation:
    def test_unknown_source_rejected_with_russian_message(self, client_with_db):
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1)

        resp = client.post(
            "/characters/1/add_rewards",
            json={"xp": 10, "gold": 0, "xp_source": "character_xp_hacker_bonus"},
        )

        assert resp.status_code == 422
        assert "Недопустимый источник опыта" in resp.text

    def test_profession_source_is_not_a_character_source(self, client_with_db):
        """`xp_bonus` keeps meaning profession XP and must not be selectable here."""
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1)

        resp = client.post(
            "/characters/1/add_rewards",
            json={"xp": 10, "gold": 0, "xp_source": "xp_bonus"},
        )

        assert resp.status_code == 422

    def test_umbrella_source_is_not_selectable_by_callers(self, client_with_db):
        """The umbrella is folded in server-side; callers name a concrete source."""
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1)

        resp = client.post(
            "/characters/1/add_rewards",
            json={"xp": 10, "gold": 0, "xp_source": "character_xp_bonus"},
        )

        assert resp.status_code == 422

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE character_attributes; --",
        "<script>alert(1)</script>",
        "character_xp_battle_bonus OR 1=1",
    ])
    def test_malicious_source_is_rejected_not_executed(self, client_with_db, payload):
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1, passive=3)

        resp = client.post(
            "/characters/1/add_rewards",
            json={"xp": 10, "gold": 0, "xp_source": payload},
        )

        assert resp.status_code == 422
        # The table is still there and untouched
        assert _read_attributes(session, 1) == (3, 0)

    def test_xp_source_must_be_a_string(self, client_with_db):
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1)

        resp = client.post(
            "/characters/1/add_rewards",
            json={"xp": 10, "gold": 0, "xp_source": {"a": 1}},
        )

        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# C) _grant_title_xp — passive part only
# ═══════════════════════════════════════════════════════════════════════════

class TestGrantTitleXp:
    """`_grant_title_xp` never looks the multiplier up (review #2).

    It runs deep inside the caller's transaction, so the value is a required
    keyword argument resolved by the entry point. `None` = «no book».
    """

    def test_passive_xp_is_multiplied(self, db_session):
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5, passive=10, active=0)

        crud._grant_title_xp(db_session, 5, 50, 0, xp_multiplier=2.0)

        passive, _active = _read_attributes(db_session, 5)
        assert passive == 110  # 10 + int(50 * 2.0)

    def test_active_xp_is_never_multiplied(self, db_session):
        """Skill points (active XP) are not accelerated by any book."""
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5, passive=0, active=7)

        crud._grant_title_xp(db_session, 5, 10, 4, xp_multiplier=3.0)

        passive, active = _read_attributes(db_session, 5)
        assert passive == 30   # int(10 * 3.0)
        assert active == 11    # 7 + 4, untouched by the book

    def test_no_multiplier_awards_base_xp(self, db_session):
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5, passive=0, active=0)

        crud._grant_title_xp(db_session, 5, 40, 2, xp_multiplier=None)

        assert _read_attributes(db_session, 5) == (40, 2)

    @patch("crud.httpx.get")
    def test_never_calls_inventory_itself(self, mock_get, db_session):
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5)

        crud._grant_title_xp(db_session, 5, 10, 0, xp_multiplier=1.5)

        mock_get.assert_not_called()

    def test_empty_reward_is_a_no_op(self, db_session):
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5, passive=1, active=1)

        crud._grant_title_xp(db_session, 5, 0, 0, xp_multiplier=2.0)

        assert _read_attributes(db_session, 5) == (1, 1)

    def test_multiplier_is_keyword_only_and_required(self):
        """Nobody may forget it and silently award unboosted XP."""
        import inspect
        param = inspect.signature(crud._grant_title_xp).parameters["xp_multiplier"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is inspect.Parameter.empty


class TestGrantTitleIsAtomic:
    """review #2: the duplicate check and the INSERT must share one transaction."""

    def _seed_title(self, session, title_id=3, passive=20, active=0):
        session.add(models.Title(
            id_title=title_id, name=f"Титул{title_id}", rarity="common",
            reward_passive_exp=passive, reward_active_exp=active,
        ))
        session.commit()

    @patch("crud.httpx.get")
    def test_second_grant_returns_already_has(self, mock_get, db_session):
        """A repeated grant is answered, not crashed with an IntegrityError."""
        mock_get.return_value = _multiplier_response(1.0)
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5)
        self._seed_title(db_session)

        first, status_first = crud.grant_title(db_session, 5, 3, xp_multiplier=1.0)
        second, status_second = crud.grant_title(db_session, 5, 3, xp_multiplier=1.0)

        assert (first, status_first) == (True, "granted")
        assert (second, status_second) == (True, "already_has")

    @patch("crud.httpx.get")
    def test_xp_is_granted_once_not_twice(self, mock_get, db_session):
        mock_get.return_value = _multiplier_response(1.0)
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5, passive=0)
        self._seed_title(db_session, passive=20)

        crud.grant_title(db_session, 5, 3, xp_multiplier=2.0)
        crud.grant_title(db_session, 5, 3, xp_multiplier=2.0)

        assert _read_attributes(db_session, 5)[0] == 40  # int(20 * 2.0), once

    @patch("crud.httpx.get")
    def test_grant_title_never_calls_inventory_itself(self, mock_get, db_session):
        """review #3: the lookup belongs to the endpoint, never to the crud call.

        `grant_title` runs the duplicate check, the INSERT and the XP write in one
        transaction; a network call anywhere in there would hold it open.
        """
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5)
        self._seed_title(db_session)

        crud.grant_title(db_session, 5, 3, xp_multiplier=1.5)

        mock_get.assert_not_called()

    @patch("crud.httpx.get")
    def test_without_a_multiplier_the_title_xp_is_base(self, mock_get, db_session):
        _create_character(db_session, 5)
        _insert_attributes(db_session, 5, passive=0)
        self._seed_title(db_session, passive=20)

        crud.grant_title(db_session, 5, 3)

        mock_get.assert_not_called()
        assert _read_attributes(db_session, 5)[0] == 20


class TestMultiplierIsResolvedBeforeAnyDbWork:
    """review #2: the session must not be inside a transaction during the lookup."""

    @patch("crud.httpx.get")
    def test_add_rewards_looks_up_before_opening_a_transaction(
        self, mock_get, client_with_db,
    ):
        client, session = client_with_db
        _create_character(session, 1)
        _insert_attributes(session, 1, passive=0)
        session.commit()  # fresh session, nothing held

        seen = {}

        def assert_no_transaction(*a, **kw):
            seen["in_transaction"] = session.in_transaction()
            return _multiplier_response(1.5)

        mock_get.side_effect = assert_no_transaction
        resp = client.post("/characters/1/add_rewards", json={"xp": 100, "gold": 0})

        assert resp.status_code == 200
        assert seen["in_transaction"] is False, "lookup ran inside a transaction"
        assert resp.json()["new_xp"] == 150

    @patch("crud.httpx.get")
    def test_endpoint_skips_the_lookup_for_zero_xp(self, mock_get, client_with_db):
        client, session = client_with_db
        _create_character(session, 1, currency_balance=0)
        _insert_attributes(session, 1)

        client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 10})

        mock_get.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# D) Constants — the vocabulary must not drift from §3.9-bis table A
# ═══════════════════════════════════════════════════════════════════════════

class TestXpSourceConstants:
    def test_the_five_character_sources(self):
        assert crud.CHARACTER_XP_SOURCES == frozenset({BATTLE, POST, QUEST, TITLE, PASS})

    def test_named_constants_match_the_contract(self):
        assert crud.XP_SOURCE_BATTLE == BATTLE
        assert crud.XP_SOURCE_POST == POST
        assert crud.XP_SOURCE_QUEST == QUEST
        assert crud.XP_SOURCE_TITLE == TITLE
        assert crud.XP_SOURCE_PASS == PASS

    def test_add_rewards_defaults_to_battle(self):
        import inspect
        sig = inspect.signature(crud.add_rewards_to_character)
        assert sig.parameters["xp_source"].default == BATTLE


# ═══════════════════════════════════════════════════════════════════════════
# F) A failed lookup must be VISIBLE (review #5, finding 36)
# ═══════════════════════════════════════════════════════════════════════════

class TestFailedLookupIsVisible:
    """Fail-open must not mean fail-silent.

    Before this, «книги нет» and «спросить не получилось» were the same 1.0 to
    every caller and to the logs, which is how a 5 s timeout shipped green.
    The behaviour stays fail-open — only the visibility changes.
    """

    @patch("crud.httpx.get", side_effect=httpx.TimeoutException("slow"))
    def test_timeout_is_logged_at_error_level(self, mock_get, caplog):
        with caplog.at_level(logging.ERROR):
            result = crud.lookup_character_xp_multiplier(7, BATTLE)

        assert result.multiplier == 1.0        # fail-open, XP never lost
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, "провал запроса должен быть виден в логах уровнем error"
        message = errors[0].getMessage()
        assert "7" in message, "в сообщении должен быть id персонажа"
        assert BATTLE in message, "в сообщении должен быть источник опыта"
        assert "мс" in message, "в сообщении должно быть затраченное время"

    @patch("crud.httpx.get", side_effect=httpx.ConnectError("down"))
    def test_failure_is_flagged_not_just_logged(self, mock_get):
        result = crud.lookup_character_xp_multiplier(7, BATTLE)
        assert result.ok is False
        assert result.reason == "request_failed"
        assert result.elapsed_ms >= 0

    @patch("crud.httpx.get")
    def test_no_book_is_a_success_not_a_failure(self, mock_get):
        """The whole point: 1.0 from a healthy service is distinguishable."""
        mock_get.return_value = _multiplier_response(1.0)
        result = crud.lookup_character_xp_multiplier(7, BATTLE)
        assert (result.multiplier, result.ok, result.reason) == (1.0, True, None)

    @patch("crud.httpx.get")
    def test_bad_payload_is_flagged(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"multiplier": "не число"}
        mock_get.return_value = resp

        result = crud.lookup_character_xp_multiplier(7, BATTLE)

        assert result.multiplier == 1.0
        assert result.ok is False
        assert result.reason == "bad_payload"

    @patch("crud.httpx.get")
    def test_out_of_range_multiplier_is_flagged(self, mock_get):
        mock_get.return_value = _multiplier_response(float("nan"))
        result = crud.lookup_character_xp_multiplier(7, BATTLE)
        assert (result.multiplier, result.ok, result.reason) == (1.0, False, "out_of_range")

    @patch("crud.httpx.get")
    def test_unknown_source_is_flagged_without_a_request(self, mock_get):
        result = crud.lookup_character_xp_multiplier(7, "character_xp_pvp_bonus")
        assert (result.multiplier, result.ok, result.reason) == (1.0, False, "unknown_source")
        mock_get.assert_not_called()

    def test_async_variant_reports_the_same_way(self, caplog):
        import asyncio
        with patch("crud.httpx.AsyncClient", side_effect=RuntimeError("inventory down")):
            with caplog.at_level(logging.ERROR):
                result = asyncio.run(crud.lookup_character_xp_multiplier_async(7, TITLE))

        assert (result.multiplier, result.ok, result.reason) == (1.0, False, "request_failed")
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors and TITLE in errors[0].getMessage()

    def test_thin_float_wrappers_keep_the_old_contract(self):
        """Callers that only multiply stay untouched."""
        with patch("crud.httpx.get", side_effect=RuntimeError("down")):
            assert crud.get_character_xp_multiplier(7, BATTLE) == 1.0
