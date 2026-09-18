"""
FEAT-168 #6, reviews #3 and #4 — WHERE the XP-book lookup may happen.

Round 2 resolved the multiplier at the entry point of every request. That was
right about transactions and wrong about everything else:

  * 25 — the helper is a **blocking** `httpx.get`, and it had started being
    called from `async def` handlers, stalling the event loop for 5 s per
    degraded lookup, for every concurrent request on that worker.
  * 26 — a **circular call**, measured live: equipping an item opens an
    inventory-service transaction, which calls character-service
    `internal/evaluate-titles`, which called *back into inventory-service* for
    the multiplier. Two callbacks per equip, each pinning an inventory worker and
    a DB connection while waiting on a service that is waiting on inventory. That
    is the exact shape of the 2026-09-04 pool exhaustion.
  * 27 / 28 — an unconditional inventory call was added to the two hottest read
    paths (`full_profile`, `GET /{id}/titles`) for a branch taken almost never.

The resulting rule, which this module pins:

  1. `async def` handlers use `crud.get_character_xp_multiplier_async`; the
     blocking variant is only for handlers declared with a plain `def` (FastAPI
     runs those in a threadpool).
  2. Every automatic title path (the equip callback, the titles listing,
     `full_profile`, an admin level change) goes through
     `main._evaluate_titles_with_book`: decide (read-only) -> look the book up
     **only if a title actually unlocked and carries passive XP** -> grant. So an
     equip that unlocks nothing makes zero callbacks, and a title that does
     unlock still gets the book (review #4).
  3. Read paths never pay for the lookup on the common path.
  4. crud award functions never look anything up themselves.
"""

import asyncio
import inspect
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy import String, text

import models

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
INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}

TITLE = "character_xp_title_bonus"


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


def _create_character(session, character_id=1, level=1):
    char = models.Character(
        id=character_id, name=f"Герой{character_id}", id_subrace=1,
        biography="bio", personality="pers", id_class=1, currency_balance=0,
        user_id=10, appearance="appearance", sex="male", id_race=1,
        avatar="/avatar.jpg", is_npc=False, level=level, stat_points=0,
    )
    session.add(char)
    session.commit()
    return char


def _create_title(session, *, title_id=1, passive=100, conditions=None):
    session.add(models.Title(
        id_title=title_id, name=f"Титул{title_id}", rarity="common",
        reward_passive_exp=passive, reward_active_exp=0, is_active=True,
        conditions=conditions if conditions is not None else [
            {"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 1},
        ],
    ))
    session.commit()


def _create_cumulative_stats(session, character_id, pvp_wins=0):
    session.execute(text("DROP TABLE IF EXISTS character_cumulative_stats"))
    session.execute(text(
        "CREATE TABLE character_cumulative_stats ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, pvp_wins INTEGER DEFAULT 0)"
    ))
    session.execute(
        text("INSERT INTO character_cumulative_stats (character_id, pvp_wins) VALUES (:c, :w)"),
        {"c": character_id, "w": pvp_wins},
    )
    session.commit()


@pytest.fixture
def db_session(test_engine, test_session_factory):
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    session.execute(text("DROP TABLE IF EXISTS character_attributes"))
    session.execute(text(
        "CREATE TABLE character_attributes ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL,"
        " passive_experience INTEGER DEFAULT 0, active_experience INTEGER DEFAULT 0)"
    ))
    session.execute(text(
        "INSERT INTO character_attributes (character_id, passive_experience, active_experience)"
        " VALUES (1, 0, 0)"
    ))
    session.commit()
    _seed_reference_data(session)
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# 25 — the helper must not block the event loop
# ═══════════════════════════════════════════════════════════════════════════

class TestAsyncHelperExists:
    def test_async_variant_is_a_coroutine_function(self):
        assert inspect.iscoroutinefunction(crud.get_character_xp_multiplier_async)

    def test_sync_variant_stays_sync_for_threadpool_handlers(self):
        assert not inspect.iscoroutinefunction(crud.get_character_xp_multiplier)

    def test_async_variant_uses_an_async_client_not_the_blocking_get(self):
        payload = MagicMock()
        payload.raise_for_status = MagicMock()
        payload.json.return_value = {"multiplier": 1.4}

        fake_client = AsyncMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.get = AsyncMock(return_value=payload)

        with patch("crud.httpx.get") as blocking_get, \
             patch("crud.httpx.AsyncClient", return_value=fake_client):
            result = asyncio.run(crud.get_character_xp_multiplier_async(7, TITLE))

        assert result == 1.4
        blocking_get.assert_not_called()
        assert fake_client.get.await_args.kwargs["params"] == {"buff_type": TITLE}

    def test_async_variant_fails_open(self):
        with patch("crud.httpx.AsyncClient", side_effect=RuntimeError("inventory down")):
            assert asyncio.run(crud.get_character_xp_multiplier_async(7, TITLE)) == 1.0

    def test_async_variant_clamps_nan(self):
        payload = MagicMock()
        payload.raise_for_status = MagicMock()
        payload.json.return_value = {"multiplier": float("nan")}
        fake_client = AsyncMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.get = AsyncMock(return_value=payload)

        with patch("crud.httpx.AsyncClient", return_value=fake_client):
            assert asyncio.run(crud.get_character_xp_multiplier_async(7, TITLE)) == 1.0

    def test_unknown_source_never_opens_a_client(self):
        with patch("crud.httpx.AsyncClient") as client_cls:
            assert asyncio.run(crud.get_character_xp_multiplier_async(7, "bogus")) == 1.0
        client_cls.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 26 — the equip callback must never call inventory-service back
# ═══════════════════════════════════════════════════════════════════════════

class TestEquipCallbackLooksUpOnlyWhenATitleUnlocks:
    """`internal/evaluate-titles` is what inventory-service calls after an equip,
    while its own transaction is open. A lookup **per equip** closes the loop that
    exhausted the pool on 2026-09-04; a lookup only when a title actually unlocks
    is rare enough to be safe, and keeps the book working (review #4)."""

    @staticmethod
    def _async_multiplier(value=2.0):
        payload = MagicMock()
        payload.raise_for_status = MagicMock()
        payload.json.return_value = {"multiplier": value}
        fake = AsyncMock()
        fake.__aenter__ = AsyncMock(return_value=fake)
        fake.__aexit__ = AsyncMock(return_value=False)
        fake.get = AsyncMock(return_value=payload)
        return fake

    @patch("crud.httpx.AsyncClient")
    @patch("crud.httpx.get")
    def test_equip_that_grants_nothing_makes_zero_callbacks(
        self, blocking_get, async_client, client, db_session,
    ):
        """The common case — every equip that unlocks no title."""
        _create_character(db_session, 1)
        _create_title(db_session, passive=100)
        _create_cumulative_stats(db_session, 1, pvp_wins=0)  # condition not met

        resp = client.post(
            "/characters/internal/evaluate-titles",
            json={"character_id": 1},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 200
        assert resp.json()["newly_unlocked_titles"] == []
        blocking_get.assert_not_called()
        async_client.assert_not_called()

    @patch("main.send_title_unlocked_notification", new_callable=AsyncMock)
    @patch("crud.httpx.get")
    def test_a_granted_title_costs_exactly_one_lookup_and_applies_the_book(
        self, blocking_get, _notify, client, db_session,
    ):
        _create_character(db_session, 1)
        _create_title(db_session, passive=100)
        _create_cumulative_stats(db_session, 1, pvp_wins=10)
        fake = self._async_multiplier(2.0)

        with patch("crud.httpx.AsyncClient", return_value=fake) as client_cls:
            resp = client.post(
                "/characters/internal/evaluate-titles",
                json={"character_id": 1},
                headers=INTERNAL_HEADERS,
            )

        assert resp.status_code == 200
        assert len(resp.json()["newly_unlocked_titles"]) == 1
        assert client_cls.call_count == 1, "exactly one lookup per unlock"
        assert fake.get.await_args.kwargs["params"] == {"buff_type": TITLE}
        blocking_get.assert_not_called()   # never the loop-blocking variant
        xp = db_session.execute(text(
            "SELECT passive_experience FROM character_attributes WHERE character_id = 1"
        )).scalar()
        assert xp == 200, "the book must apply to an automatically granted title"

    @patch("main.send_title_unlocked_notification", new_callable=AsyncMock)
    @patch("crud.httpx.AsyncClient", side_effect=RuntimeError("inventory down"))
    def test_fail_open_still_grants_the_title(self, async_client, _notify, client, db_session):
        _create_character(db_session, 1)
        _create_title(db_session, passive=100)
        _create_cumulative_stats(db_session, 1, pvp_wins=10)

        resp = client.post(
            "/characters/internal/evaluate-titles",
            json={"character_id": 1},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 200
        assert len(resp.json()["newly_unlocked_titles"]) == 1
        xp = db_session.execute(text(
            "SELECT passive_experience FROM character_attributes WHERE character_id = 1"
        )).scalar()
        assert xp == 100, "a degraded inventory-service costs the bonus, never the XP"

    @patch("main.send_title_unlocked_notification", new_callable=AsyncMock)
    @patch("crud.httpx.AsyncClient")
    @patch("crud.httpx.get")
    def test_a_title_without_passive_xp_needs_no_lookup(
        self, blocking_get, async_client, _notify, client, db_session,
    ):
        """No passive reward, no book to apply, no reason to call anyone."""
        _create_character(db_session, 1)
        _create_title(db_session, passive=0)
        _create_cumulative_stats(db_session, 1, pvp_wins=10)

        resp = client.post(
            "/characters/internal/evaluate-titles",
            json={"character_id": 1},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 200
        assert len(resp.json()["newly_unlocked_titles"]) == 1
        blocking_get.assert_not_called()
        async_client.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 27 / 28 — the hot read paths
# ═══════════════════════════════════════════════════════════════════════════

class TestReadPathsDoNotPayForTheLookup:
    @patch("crud.httpx.AsyncClient")
    @patch("crud.httpx.get")
    def test_titles_listing_never_asks_inventory(
        self, blocking_get, async_client, client, db_session,
    ):
        _create_character(db_session, 1)
        _create_title(db_session, passive=100)
        _create_cumulative_stats(db_session, 1, pvp_wins=0)  # nothing to grant

        resp = client.get("/characters/1/titles")

        assert resp.status_code == 200
        blocking_get.assert_not_called()
        async_client.assert_not_called()

    @patch("crud.httpx.get")
    def test_titles_listing_pays_one_lookup_only_when_it_grants(
        self, blocking_get, client, db_session,
    ):
        """review #4: the book applies here too, but only on the rare grant."""
        _create_character(db_session, 1)
        _create_title(db_session, passive=100)
        _create_cumulative_stats(db_session, 1, pvp_wins=10)  # will grant
        fake = TestEquipCallbackLooksUpOnlyWhenATitleUnlocks._async_multiplier(2.0)

        with patch("crud.httpx.AsyncClient", return_value=fake) as client_cls:
            resp = client.get("/characters/1/titles")

        assert resp.status_code == 200
        assert client_cls.call_count == 1
        blocking_get.assert_not_called()
        xp = db_session.execute(text(
            "SELECT passive_experience FROM character_attributes WHERE character_id = 1"
        )).scalar()
        assert xp == 200

    @patch("crud.find_unlockable_titles", return_value=[])
    @patch("crud.check_and_update_level")
    @patch("crud.httpx.get")
    def test_full_profile_without_a_level_up_never_asks_inventory(
        self, blocking_get, mock_level, mock_eval, client, db_session,
    ):
        """The lookup is lazy: no level-up, no call — this is the hottest read."""
        char = _create_character(db_session, 1, level=3)
        mock_level.return_value = char  # same level ⇒ the grant branch is skipped

        called = {"async": False}

        async def _tripwire(*a, **kw):
            called["async"] = True
            return 1.0

        with patch("crud.get_character_xp_multiplier_async", _tripwire):
            client.get("/characters/1/full_profile")

        assert called["async"] is False, "full_profile looked the book up for nothing"
        blocking_get.assert_not_called()
        mock_eval.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 4 — crud award functions never look anything up
# ═══════════════════════════════════════════════════════════════════════════

class TestAwardFunctionsNeverLookUp:
    @patch("crud.httpx.AsyncClient")
    @patch("crud.httpx.get")
    def test_add_rewards_to_character_makes_no_call(
        self, blocking_get, async_client, db_session,
    ):
        _create_character(db_session, 1)

        crud.add_rewards_to_character(db_session, 1, 100, 0, xp_multiplier=1.5)

        blocking_get.assert_not_called()
        async_client.assert_not_called()
        xp = db_session.execute(text(
            "SELECT passive_experience FROM character_attributes WHERE character_id = 1"
        )).scalar()
        assert xp == 150

    def test_evaluate_titles_signature_takes_the_multiplier(self):
        sig = inspect.signature(crud.evaluate_titles)
        assert sig.parameters["xp_multiplier"].default is None

    def test_no_award_function_calls_the_blocking_helper(self):
        """Grep-style guard: crud award paths must not reference the sync helper."""
        import ast
        import pathlib

        source = pathlib.Path(crud.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        guarded = {
            "add_rewards_to_character", "_grant_title_xp",
            "grant_title", "evaluate_titles",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in guarded:
                names = {
                    n.func.id for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                }
                assert "get_character_xp_multiplier" not in names, node.name
                assert "get_character_xp_multiplier_async" not in names, node.name
