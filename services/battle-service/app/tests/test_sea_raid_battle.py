"""FEAT-214 QA (task 8): sea raid battles in battle-service.

Covers:
  * POST /battles/internal/sea-raid: internal token, body validation (1..5 players / mobs,
    required ids, injection strings), monster checks via `_ensure_caravan_guards` with the sea
    message (missing / player / dead / KO / elsewhere / duplicate / busy / locked -> 409),
    player placement (silent skips: NPC, missing, elsewhere, nowhere, in battle,
    activity-locked, HP <= 0 / no attributes row; dedupe; mob id in the player list),
    nobody left -> 409, team layout (players 0, mobs 1), `pve`, `sea_raid_id` tag, response;
  * `_ensure_caravan_guards` keeps the caravan text by default;
  * `_assemble_battle` / `crud.create_battle` forward and store `sea_raid_id` only when set;
  * `_notify_sea_battle_end` payload / aborted / untagged / lookup errors, `_post_sea_callback`
    URL + token + retries, the callback inside `_finalize_battle` and `_force_finish_battle`;
  * GET /battles/internal/{id}/result carries `sea_raid_id`;
  * POST /battles/{id}/join-request into a sea raid: team 0 goes on, team 1 -> 400;
  * migration 011 chain + idempotent up / down.

Harness modelled on test_caravan_raid_battle.py (FEAT-211 / FEAT-163).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database  # noqa: E402

database.engine = MagicMock()

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())
for _mod in ("mongo_client", "mongo_helpers", "tasks", "inventory_client",
             "character_client", "skills_client", "rabbitmq_publisher"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
_tasks = sys.modules["tasks"]
if isinstance(_tasks, MagicMock):
    _tasks.save_log = MagicMock()
    _tasks.save_log.delay = MagicMock()

import main  # noqa: E402
import activity_lock  # noqa: E402
import auth_http  # noqa: E402
from main import app  # noqa: E402
from database import get_db  # noqa: E402
from auth_http import get_current_user_via_http, UserRead  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from _feat163_harness import (  # noqa: E402
    FakeDB, FakeRedis, FakeResult, make_participant, patch_main, seed_battle, utc_now,
)

app.router.on_startup.clear()

TOKEN = "test-internal-token"
HDR = {"X-Internal-Token": TOKEN}
P1, P2, P3, P4, P5 = 1, 2, 3, 4, 5
M1, M2 = 901, 902
SEA_RAID = 66
DECK = 300
SOON = datetime.utcnow() + timedelta(hours=2)
PAST = datetime.utcnow() - timedelta(minutes=5)
USER = UserRead(id=10, username="u", role="user", permissions=[])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _res(row):
    r = MagicMock()
    r.fetchone.return_value = row
    r.fetchall.return_value = [row] if row is not None else []
    return r


class _Chars:
    """Mock AsyncSession over a tiny `characters` (+ `character_attributes.current_health`) table."""

    def __init__(self, chars):
        self.chars = chars
        self.queries = []
        self.db = AsyncMock()
        self.db.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, query, params=None):
        q = str(query)
        self.queries.append((q, dict(params or {})))
        p = params or {}
        c = self.chars.get(p.get("cid", p.get("gid")))
        if "SELECT is_npc, npc_status, unconscious_until, current_location_id" in q:
            if c is None:
                return _res(None)
            return _res((c.get("is_npc", 0), c.get("status", "alive"), c.get("unconscious"),
                         c.get("location")))
        if "SELECT is_npc, current_location_id FROM characters" in q:
            return _res((c.get("is_npc", 0), c.get("location")) if c else None)
        if "SELECT current_health FROM character_attributes" in q:
            return _res((c["hp"],) if c and "hp" in c else None)
        return _res(None)


def _player(**kw):
    base = {"is_npc": 0, "location": DECK, "hp": 50}
    base.update(kw)
    return base


def _mob(**kw):
    base = {"is_npc": 1, "status": "alive", "location": DECK}
    base.update(kw)
    return base


def _world(**overrides):
    chars = {P1: _player(), P2: _player(), P3: _player(), P4: _player(), P5: _player(),
             M1: _mob(), M2: _mob()}
    for k, v in overrides.items():
        cid = int(k[1:])
        if v is None:
            chars.pop(cid, None)
        else:
            chars[cid] = v
    return chars


def _client(db, user=None):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        app.dependency_overrides[get_current_user_via_http] = lambda: user
    return TestClient(app)


def _assembled(n):
    battle = MagicMock()
    battle.id = 888
    parts = []
    for i in range(n):
        p = MagicMock()
        p.id = 41 + i
        parts.append(p)
    return battle, parts, 41, datetime.utcnow() + timedelta(hours=1)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _locks(monkeypatch, locked=(), escorts=()):
    locked, escorts = set(locked), set(escorts)

    async def get_lock(db, cid):
        return activity_lock.compute_lock(7 if cid in locked else None, None,
                                          escort_caravan_id=42 if cid in escorts else None)

    monkeypatch.setattr(activity_lock, "get_activity_lock", get_lock)


def _payload(**kw):
    body = {"sea_raid_id": SEA_RAID, "location_id": DECK,
            "player_character_ids": [P1, P2], "mob_character_ids": [M1, M2]}
    body.update(kw)
    return body


def _post(monkeypatch, chars=None, body=None, busy=(), locked=(), headers=HDR, escorts=()):
    _locks(monkeypatch, locked, escorts)
    holder = _Chars(_world() if chars is None else chars)
    body = body or _payload()

    async def active(_db, cid):
        return MagicMock() if cid in busy else None

    n = 10
    if isinstance(body.get("player_character_ids"), list) and isinstance(body.get("mob_character_ids"), list):
        n = len(body["player_character_ids"]) + len(body["mob_character_ids"])
    http = MagicMock(side_effect=AssertionError("no HTTP expected"))
    with patch("main.get_active_battle_for_character", side_effect=active), \
            patch("main.httpx.AsyncClient", http), \
            patch("main._assemble_battle", new_callable=AsyncMock, return_value=_assembled(n)) as assemble:
        r = _client(holder.db).post("/battles/internal/sea-raid", json=body, headers=headers)
    return r, assemble, holder


# ===========================================================================
# 1. POST /battles/internal/sea-raid — auth & body
# ===========================================================================

class TestSeaRaidAuth:
    @pytest.mark.parametrize("headers", [{}, {"X-Internal-Token": "nope"},
                                         {"Authorization": "Bearer x"}],
                             ids=["none", "wrong", "user-jwt"])
    def test_requires_internal_token(self, monkeypatch, headers):
        r, assemble, holder = _post(monkeypatch, headers=headers)
        assert r.status_code == 401
        assemble.assert_not_called()
        assert holder.queries == []

    def test_unset_token_fails_closed(self, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        r, assemble, _ = _post(monkeypatch)
        assert r.status_code == 503
        assemble.assert_not_called()


class TestSeaRaidBodyValidation:
    @pytest.mark.parametrize("body", [
        _payload(player_character_ids=[]),
        _payload(player_character_ids=[1, 2, 3, 4, 5, 6]),
        _payload(mob_character_ids=[]),
        _payload(mob_character_ids=[901, 902, 903, 904, 905, 906]),
        {k: v for k, v in _payload().items() if k != "sea_raid_id"},
        {k: v for k, v in _payload().items() if k != "location_id"},
        {k: v for k, v in _payload().items() if k != "player_character_ids"},
        {k: v for k, v in _payload().items() if k != "mob_character_ids"},
        _payload(sea_raid_id="'; DROP TABLE battles --"),
        _payload(location_id="1 OR 1=1"),
        _payload(player_character_ids=["1; DELETE FROM characters"]),
    ], ids=["no-players", "six-players", "no-mobs", "six-mobs", "no-raid-id", "no-location",
            "no-player-key", "no-mob-key", "sql-raid", "sql-location", "sql-player"])
    def test_422(self, monkeypatch, body):
        r, assemble, holder = _post(monkeypatch, body=body)
        assert r.status_code == 422, r.text
        assemble.assert_not_called()
        assert holder.queries == []


# ===========================================================================
# 2. Happy path, team layout, tag
# ===========================================================================

class TestSeaRaidHappyPath:
    def test_creates_tagged_pve_battle(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch)
        assert r.status_code == 201, r.text
        body = r.json()
        assert set(body) == {"battle_id", "participants", "next_actor", "deadline_at",
                             "player_character_ids"}
        assert body["battle_id"] == 888
        assert body["participants"] == [41, 42, 43, 44]
        assert body["next_actor"] == 41
        assert body["player_character_ids"] == [P1, P2]
        args, kwargs = assemble.call_args
        assert args[1] == [P1, P2, M1, M2]
        assert args[2] == [main.SEA_CREW_TEAM] * 2 + [main.SEA_MONSTER_TEAM] * 2
        assert args[2] == [0, 0, 1, 1]
        assert args[3] == "pve"
        assert args[4] == DECK
        assert kwargs == {"sea_raid_id": SEA_RAID}

    def test_no_http_calls(self, monkeypatch):
        """Server-initiated: no action gate, no party lookup (httpx patched to explode)."""
        r, _, _ = _post(monkeypatch)
        assert r.status_code == 201, r.text

    def test_five_by_five(self, monkeypatch):
        mobs = [901, 902, 903, 904, 905]
        chars = _world(**{f"c{i}": _mob() for i in mobs})
        r, assemble, _ = _post(monkeypatch, chars=chars, body=_payload(
            player_character_ids=[P1, P2, P3, P4, P5], mob_character_ids=mobs))
        assert r.status_code == 201, r.text
        assert r.json()["player_character_ids"] == [P1, P2, P3, P4, P5]
        assert assemble.call_args.args[1] == [P1, P2, P3, P4, P5] + mobs
        assert assemble.call_args.args[2] == [0] * 5 + [1] * 5

    def test_one_by_one(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, body=_payload(player_character_ids=[P3],
                                                          mob_character_ids=[M2]))
        assert r.status_code == 201, r.text
        assert assemble.call_args.args[1] == [P3, M2]
        assert assemble.call_args.args[2] == [0, 1]

    def test_player_order_is_kept(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, body=_payload(player_character_ids=[P4, P1, P3]))
        assert r.status_code == 201
        assert r.json()["player_character_ids"] == [P4, P1, P3]
        assert assemble.call_args.args[1][:3] == [P4, P1, P3]

    def test_raid_id_is_forwarded_verbatim(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, body=_payload(sea_raid_id=12345))
        assert r.status_code == 201
        assert assemble.call_args.kwargs == {"sea_raid_id": 12345}


# ===========================================================================
# 3. Player placement — silent skips
# ===========================================================================

class TestSeaRaidPlayerSkips:
    @pytest.mark.parametrize("p2", [
        None,
        _player(is_npc=1),
        _player(location=DECK + 1),
        _player(location=None),
        _player(hp=0),
        _player(hp=-3),
        _player(hp=None),
        {"is_npc": 0, "location": DECK},          # no character_attributes row
    ], ids=["missing", "npc", "elsewhere", "nowhere", "hp-0", "hp-negative", "hp-null", "no-attrs"])
    def test_unavailable_player_is_skipped(self, monkeypatch, p2):
        r, assemble, _ = _post(monkeypatch, chars=_world(c2=p2))
        assert r.status_code == 201, r.text
        assert r.json()["player_character_ids"] == [P1]
        assert assemble.call_args.args[1] == [P1, M1, M2]
        assert assemble.call_args.args[2] == [0, 1, 1]

    def test_player_in_battle_is_skipped(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, busy={P1})
        assert r.status_code == 201, r.text
        assert r.json()["player_character_ids"] == [P2]
        assert assemble.call_args.args[1] == [P2, M1, M2]

    def test_activity_locked_player_is_skipped(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, locked={P2})
        assert r.status_code == 201, r.text
        assert r.json()["player_character_ids"] == [P1]

    def test_caravan_escort_fights_monsters(self, monkeypatch):
        """FEAT-215: the caravan-escort lock is the only exemption — an escort aboard is placed,
        any other lock still skips."""
        r, assemble, _ = _post(monkeypatch, locked={P1}, escorts={P2})
        assert r.status_code == 201, r.text
        assert r.json()["player_character_ids"] == [P2]
        assert assemble.call_args.args[1] == [P2, M1, M2]

    def test_hp_one_is_enough(self, monkeypatch):
        r, _, _ = _post(monkeypatch, chars=_world(c2=_player(hp=1)))
        assert r.status_code == 201
        assert r.json()["player_character_ids"] == [P1, P2]

    def test_duplicates_removed(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, body=_payload(player_character_ids=[P1, P2, P1, P2, P1]))
        assert r.status_code == 201, r.text
        assert r.json()["player_character_ids"] == [P1, P2]
        assert assemble.call_args.args[1] == [P1, P2, M1, M2]
        assert assemble.call_args.args[2] == [0, 0, 1, 1]

    def test_mob_id_in_player_list_is_skipped(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, body=_payload(player_character_ids=[M1, P1]))
        assert r.status_code == 201, r.text
        assert r.json()["player_character_ids"] == [P1]
        assert assemble.call_args.args[1] == [P1, M1, M2]

    def test_mixed_skips(self, monkeypatch):
        chars = _world(c3=_player(hp=0), c4=_player(location=DECK + 9))
        r, assemble, _ = _post(monkeypatch, chars=chars, busy={P5}, locked={P2},
                               body=_payload(player_character_ids=[P1, P2, P3, P4, P5]))
        assert r.status_code == 201, r.text
        assert r.json()["player_character_ids"] == [P1]
        assert assemble.call_args.args[2] == [0, 1, 1]

    def test_location_query_is_parameterised(self, monkeypatch):
        r, _, holder = _post(monkeypatch)
        assert r.status_code == 201
        sel = [p for q, p in holder.queries if "SELECT is_npc, current_location_id FROM characters" in q]
        assert {p["cid"] for p in sel} == {P1, P2}


class TestSeaRaidNobodyLeft:
    @pytest.mark.parametrize("kw", [
        {"chars": _world(c1=_player(hp=0), c2=_player(hp=0))},
        {"busy": {P1, P2}},
        {"locked": {P1, P2}},
        {"chars": _world(c1=None, c2=_player(is_npc=1))},
        {"chars": _world(c1=_player(location=DECK + 1), c2=_player(location=None))},
    ], ids=["all-0hp", "all-busy", "all-locked", "missing-npc", "elsewhere"])
    def test_409(self, monkeypatch, kw):
        r, assemble, _ = _post(monkeypatch, **kw)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == main.SEA_NO_FIGHTERS
        assert r.json()["detail"] == "Некому защищать палубу"
        assemble.assert_not_called()

    def test_only_mob_ids_as_players_is_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, body=_payload(player_character_ids=[M1, M2]))
        assert r.status_code == 409
        assert r.json()["detail"] == main.SEA_NO_FIGHTERS
        assemble.assert_not_called()


# ===========================================================================
# 4. Monster checks (reuse of _ensure_caravan_guards with the sea text)
# ===========================================================================

class TestSeaRaidMobs:
    @pytest.mark.parametrize("mob", [
        None,
        _player(),
        _mob(status="dead"),
        _mob(unconscious=SOON),
        _mob(unconscious=SOON.isoformat(sep=" ")),
        _mob(location=DECK + 1),
        _mob(location=None),
    ], ids=["missing", "player", "dead", "ko", "ko-string", "elsewhere", "nowhere"])
    def test_unavailable_mob_409(self, monkeypatch, mob):
        r, assemble, _ = _post(monkeypatch, chars=_world(c902=mob))
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == main.SEA_MOBS_UNAVAILABLE
        assert r.json()["detail"] == "Морские монстры недоступны"
        assemble.assert_not_called()

    def test_ko_expired_mob_is_fine(self, monkeypatch):
        r, _, _ = _post(monkeypatch, chars=_world(c902=_mob(unconscious=PAST)))
        assert r.status_code == 201, r.text

    def test_duplicate_mob_ids_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, body=_payload(mob_character_ids=[M1, M1]))
        assert r.status_code == 409
        assert r.json()["detail"] == main.SEA_MOBS_UNAVAILABLE
        assemble.assert_not_called()

    def test_busy_mob_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, busy={M2})
        assert r.status_code == 409
        assert r.json()["detail"] == main.SEA_MOBS_UNAVAILABLE
        assemble.assert_not_called()

    def test_locked_mob_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, locked={M1})
        assert r.status_code == 409
        assert r.json()["detail"] == main.SEA_MOBS_UNAVAILABLE
        assemble.assert_not_called()

    def test_mobs_checked_before_players(self, monkeypatch):
        """Unavailable monsters win over 'nobody left' (and no player is even read)."""
        chars = _world(c901=None, c1=_player(hp=0), c2=_player(hp=0))
        r, _, holder = _post(monkeypatch, chars=chars)
        assert r.status_code == 409
        assert r.json()["detail"] == main.SEA_MOBS_UNAVAILABLE
        assert not any("SELECT is_npc, current_location_id" in q for q, _ in holder.queries)


class TestEnsureGuardsDefaultMessage:
    @pytest.mark.asyncio
    async def test_caravan_text_by_default(self):
        with pytest.raises(HTTPException) as exc:
            await main._ensure_caravan_guards(AsyncMock(), [1, 1], DECK)
        assert exc.value.status_code == 409
        assert exc.value.detail == main.CARAVAN_GUARDS_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_custom_message(self):
        with pytest.raises(HTTPException) as exc:
            await main._ensure_caravan_guards(AsyncMock(), [1, 1], DECK, message="x")
        assert exc.value.detail == "x"


# ===========================================================================
# 5. _assemble_battle / crud.create_battle / model
# ===========================================================================

class TestAssembleBattleSeaTag:
    @pytest.mark.asyncio
    async def test_sea_tag_only_when_set(self, monkeypatch):
        seen = []

        async def fake_create(db, ids, teams, **kw):
            seen.append(kw)
            raise RuntimeError("stop")

        monkeypatch.setattr(main, "create_battle", fake_create)
        for tag in (None, SEA_RAID):
            with pytest.raises(RuntimeError):
                await main._assemble_battle(AsyncMock(), [1, 2], [0, 1], "pve", 5, sea_raid_id=tag)
        with pytest.raises(RuntimeError):
            await main._assemble_battle(AsyncMock(), [1, 2], [0, 1], "pve", 5)
        assert "sea_raid_id" not in seen[0]
        assert seen[1]["sea_raid_id"] == SEA_RAID
        assert "caravan_raid_id" not in seen[1] and "law_encounter_id" not in seen[1]
        assert "sea_raid_id" not in seen[2]

    @pytest.mark.asyncio
    async def test_crud_create_battle_stores_the_tag(self):
        import crud
        db = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        try:
            await crud.create_battle(db, [1, 2], [0, 1], battle_type="pve", location_id=5,
                                     sea_raid_id=SEA_RAID)
        except Exception:
            pass  # only the Battle row matters here
        battle = db.add.call_args_list[0].args[0]
        assert battle.sea_raid_id == SEA_RAID
        assert battle.caravan_raid_id is None
        assert battle.law_encounter_id is None

    @pytest.mark.asyncio
    async def test_crud_create_battle_defaults_to_null(self):
        import crud
        db = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        try:
            await crud.create_battle(db, [1, 2], [0, 1], battle_type="pve", location_id=5)
        except Exception:
            pass
        assert db.add.call_args_list[0].args[0].sea_raid_id is None

    def test_model_column(self):
        import models
        col = models.Battle.__table__.c.sea_raid_id
        assert col.nullable is True
        assert col.index is True


# ===========================================================================
# 6. The raid-result callback
# ===========================================================================

def _tag_db(raid_id):
    db = AsyncMock()

    async def execute(query, params=None):
        if "SELECT sea_raid_id FROM battles" in str(query):
            return _res((raid_id,) if raid_id is not None else None)
        return _res(None)

    db.execute = AsyncMock(side_effect=execute)
    return db


class TestNotifySeaBattleEnd:
    @pytest.mark.asyncio
    async def test_tagged_battle_posts_payload(self):
        with patch("main._post_sea_callback", new_callable=AsyncMock) as post:
            await main._notify_sea_battle_end(_tag_db(SEA_RAID), 601, 0)
            await asyncio.sleep(0)
        post.assert_awaited_once()
        assert post.call_args.args[0] == {
            "battle_id": 601, "sea_raid_id": SEA_RAID, "winner_team": 0, "aborted": False,
        }

    @pytest.mark.asyncio
    async def test_monsters_won(self):
        with patch("main._post_sea_callback", new_callable=AsyncMock) as post:
            await main._notify_sea_battle_end(_tag_db(SEA_RAID), 602, 1)
            await asyncio.sleep(0)
        assert post.call_args.args[0]["winner_team"] == 1
        assert post.call_args.args[0]["aborted"] is False

    @pytest.mark.asyncio
    async def test_aborted_flag(self):
        with patch("main._post_sea_callback", new_callable=AsyncMock) as post:
            await main._notify_sea_battle_end(_tag_db(SEA_RAID), 603, None, aborted=True)
            await asyncio.sleep(0)
        assert post.call_args.args[0] == {
            "battle_id": 603, "sea_raid_id": SEA_RAID, "winner_team": None, "aborted": True,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", [None, "7", MagicMock()], ids=["null", "string", "mock"])
    async def test_untagged_battle_posts_nothing(self, value):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_res((value,)))
        with patch("main._post_sea_callback", new_callable=AsyncMock) as post:
            await main._notify_sea_battle_end(db, 604, 1)
            await asyncio.sleep(0)
        post.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_battle_posts_nothing(self):
        with patch("main._post_sea_callback", new_callable=AsyncMock) as post:
            await main._notify_sea_battle_end(_tag_db(None), 605, 1)
            await asyncio.sleep(0)
        post.assert_not_called()

    @pytest.mark.asyncio
    async def test_lookup_error_never_breaks_the_ending(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("Unknown column 'sea_raid_id'"))
        with patch("main._post_sea_callback", new_callable=AsyncMock) as post:
            await main._notify_sea_battle_end(db, 606, 1)
            await asyncio.sleep(0)
        post.assert_not_called()

    @pytest.mark.asyncio
    async def test_caravan_tag_does_not_trigger_sea(self):
        """A caravan raid battle (sea_raid_id NULL) never reaches the sea endpoint."""
        db = AsyncMock()

        async def execute(query, params=None):
            q = str(query)
            if "SELECT caravan_raid_id FROM battles" in q:
                return _res((55,))
            return _res((None,))

        db.execute = AsyncMock(side_effect=execute)
        with patch("main._post_sea_callback", new_callable=AsyncMock) as post:
            await main._notify_sea_battle_end(db, 607, 0)
            await asyncio.sleep(0)
        post.assert_not_called()


def _cm(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


class TestPostSeaCallback:
    @pytest.mark.asyncio
    async def test_url_token_and_stop_on_2xx(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text=""))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_sea_callback({"battle_id": 1, "sea_raid_id": 2})
        assert client.post.await_count == 1
        call = client.post.await_args
        assert call.args[0] == f"{main.settings.CHARACTER_SERVICE_URL}/characters/internal/sea/raid-result"
        assert call.kwargs["json"] == {"battle_id": 1, "sea_raid_id": 2}
        assert "X-Internal-Token" in call.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_retries_on_5xx_then_stops(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[MagicMock(status_code=502, text=""),
                                             MagicMock(status_code=200, text="")])
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_sea_callback({"battle_id": 1})
        assert client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_4xx_is_final(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=404, text="unknown"))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_sea_callback({"battle_id": 1})
        assert client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_gives_up_after_three_network_errors(self, monkeypatch):
        import httpx
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_sea_callback({"battle_id": 1})     # no exception
        assert client.post.await_count == 3

    @pytest.mark.asyncio
    async def test_gives_up_after_three_5xx(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=500, text=""))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_sea_callback({"battle_id": 1})
        assert client.post.await_count == 3


# --- the callback inside the real endings (FEAT-163 harness) ----------------

BATTLE_ID = 8080


class _SeaFakeDB(FakeDB):
    def __init__(self, sea_raid_id=None, fail_lookup=False):
        super().__init__()
        self.sea_raid_id = sea_raid_id
        self.fail_lookup = fail_lookup

    def _dispatch(self, q, p):
        if q.startswith("select sea_raid_id from battles"):
            if self.fail_lookup:
                raise RuntimeError("db gone")
            return FakeResult([(self.sea_raid_id,)] if p.get("bid") in self.battles else [])
        if q.startswith("select caravan_raid_id from battles"):
            return FakeResult([(None,)] if p.get("bid") in self.battles else [])
        if q.startswith("select law_encounter_id from battles"):
            return FakeResult([(None,)] if p.get("bid") in self.battles else [])
        if q.startswith("select is_npc, npc_role from characters"):
            c = self.characters.get(p.get("cid"))
            if c and c["is_npc"]:
                return FakeResult([(1, c.get("npc_role"))])
            return FakeResult([])
        return super()._dispatch(q, p)


@pytest.fixture
def rds():
    return FakeRedis()


def _sea_fight(db, rds, crew_hp=40, mob_hp=0):
    parts = {
        1: make_participant(P1, team=0, hp=crew_hp),
        2: make_participant(M1, team=1, hp=mob_hp),
    }
    state = seed_battle(db, rds, BATTLE_ID, parts, next_actor=1,
                        deadline_at=utc_now() + timedelta(hours=1), battle_type="pve")
    db.characters[M1]["is_npc"] = True
    db.characters[M1]["user_id"] = None
    db.characters[M1]["npc_role"] = None
    return state


async def _finalize_recording(monkeypatch, db, state, winner_team):
    events = []
    orig_caravan, orig_sea = main._notify_caravan_battle_end, main._notify_sea_battle_end

    async def law_spy(*a, **kw):
        events.append("law")

    async def caravan_spy(*a, **kw):
        events.append("caravan")
        return await orig_caravan(*a, **kw)

    async def sea_spy(*a, **kw):
        events.append("sea")
        return await orig_sea(*a, **kw)

    async def faction_spy(*a, **kw):
        events.append("faction")

    post_sea = AsyncMock()
    post_caravan = AsyncMock()
    monkeypatch.setattr(main, "_notify_law_battle_end", law_spy)
    monkeypatch.setattr(main, "_notify_caravan_battle_end", caravan_spy)
    monkeypatch.setattr(main, "_notify_sea_battle_end", sea_spy)
    monkeypatch.setattr(main, "_notify_faction_battle_end", faction_spy)
    monkeypatch.setattr(main, "_post_sea_callback", post_sea)
    monkeypatch.setattr(main, "_post_caravan_callback", post_caravan)
    with patch.object(main.httpx, "AsyncClient") as client_cls:
        client = client_cls.return_value.__aenter__.return_value
        client.put = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        await main._finalize_battle(db_session=db, battle_id=BATTLE_ID, battle_state=state,
                                    winner_team=winner_team, turn_events=[], turn_number=5)
        await asyncio.sleep(0)
    return events, post_sea, post_caravan


class TestSeaCallbackInEndings:
    @pytest.mark.asyncio
    async def test_crew_won(self, monkeypatch, rds):
        db = _SeaFakeDB(sea_raid_id=SEA_RAID)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _sea_fight(db, rds)
        events, post_sea, post_caravan = await _finalize_recording(monkeypatch, db, state, 0)
        assert events == ["law", "caravan", "sea", "faction"]
        post_sea.assert_awaited_once()
        assert post_sea.call_args.args[0] == {
            "battle_id": BATTLE_ID, "sea_raid_id": SEA_RAID, "winner_team": 0, "aborted": False,
        }
        post_caravan.assert_not_called()

    @pytest.mark.asyncio
    async def test_monsters_won(self, monkeypatch, rds):
        db = _SeaFakeDB(sea_raid_id=SEA_RAID)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _sea_fight(db, rds, crew_hp=0, mob_hp=50)
        _, post_sea, _ = await _finalize_recording(monkeypatch, db, state, 1)
        assert post_sea.call_args.args[0]["winner_team"] == 1
        assert post_sea.call_args.args[0]["aborted"] is False

    @pytest.mark.asyncio
    async def test_untagged_battle_sends_no_sea_callback(self, monkeypatch, rds):
        db = _SeaFakeDB(sea_raid_id=None)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _sea_fight(db, rds)
        events, post_sea, _ = await _finalize_recording(monkeypatch, db, state, 0)
        assert "sea" in events
        post_sea.assert_not_called()

    @pytest.mark.asyncio
    async def test_lookup_failure_does_not_break_the_ending(self, monkeypatch, rds):
        db = _SeaFakeDB(sea_raid_id=SEA_RAID, fail_lookup=True)
        spies = patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _sea_fight(db, rds)
        events, post_sea, _ = await _finalize_recording(monkeypatch, db, state, 0)
        post_sea.assert_not_called()
        assert events[-1] == "faction"
        assert BATTLE_ID in spies.finish_battle_calls

    @pytest.mark.asyncio
    async def test_failing_callback_does_not_break_the_ending(self, monkeypatch, rds):
        import httpx
        db = _SeaFakeDB(sea_raid_id=SEA_RAID)
        spies = patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _sea_fight(db, rds)
        crashing = AsyncMock(side_effect=httpx.ConnectError("character-service down"))
        monkeypatch.setattr(main, "_notify_law_battle_end", AsyncMock())
        monkeypatch.setattr(main, "_notify_faction_battle_end", AsyncMock())
        monkeypatch.setattr(main, "_post_caravan_callback", AsyncMock())
        monkeypatch.setattr(main, "_post_sea_callback", crashing)
        with patch.object(main.httpx, "AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.put = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
            client.post = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
            await main._finalize_battle(db_session=db, battle_id=BATTLE_ID, battle_state=state,
                                        winner_team=0, turn_events=[], turn_number=5)
            await asyncio.sleep(0)
        crashing.assert_awaited_once()
        assert BATTLE_ID in spies.finish_battle_calls

    @pytest.mark.asyncio
    async def test_force_finish_reports_aborted(self, monkeypatch, rds):
        db = _SeaFakeDB(sea_raid_id=SEA_RAID)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _sea_fight(db, rds, mob_hp=50)
        post_sea = AsyncMock()
        monkeypatch.setattr(main, "_post_sea_callback", post_sea)
        monkeypatch.setattr(main, "_post_caravan_callback", AsyncMock())
        monkeypatch.setattr(main, "_post_law_callback", AsyncMock())
        monkeypatch.setattr(main, "_notify_dungeon_battle_end", AsyncMock())
        await main._force_finish_battle(db, BATTLE_ID, state, reason="Админ")
        await asyncio.sleep(0)
        assert db.battles[BATTLE_ID]["status"] == "finished"
        post_sea.assert_awaited_once()
        assert post_sea.call_args.args[0] == {
            "battle_id": BATTLE_ID, "sea_raid_id": SEA_RAID, "winner_team": None, "aborted": True,
        }

    @pytest.mark.asyncio
    async def test_force_finish_untagged_sends_nothing(self, monkeypatch, rds):
        db = _SeaFakeDB(sea_raid_id=None)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _sea_fight(db, rds, mob_hp=50)
        post_sea = AsyncMock()
        monkeypatch.setattr(main, "_post_sea_callback", post_sea)
        monkeypatch.setattr(main, "_post_caravan_callback", AsyncMock())
        monkeypatch.setattr(main, "_notify_dungeon_battle_end", AsyncMock())
        await main._force_finish_battle(db, BATTLE_ID, state, reason="Админ")
        await asyncio.sleep(0)
        post_sea.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_finish_survives_a_lookup_failure(self, monkeypatch, rds):
        db = _SeaFakeDB(sea_raid_id=SEA_RAID, fail_lookup=True)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _sea_fight(db, rds, mob_hp=50)
        post_sea = AsyncMock()
        monkeypatch.setattr(main, "_post_sea_callback", post_sea)
        monkeypatch.setattr(main, "_post_caravan_callback", AsyncMock())
        monkeypatch.setattr(main, "_notify_dungeon_battle_end", AsyncMock())
        await main._force_finish_battle(db, BATTLE_ID, state, reason="Админ")
        await asyncio.sleep(0)
        assert db.battles[BATTLE_ID]["status"] == "finished"
        post_sea.assert_not_called()


# ===========================================================================
# 7. GET /battles/internal/{id}/result
# ===========================================================================

class TestInternalResultSea:
    def _get(self, sea_raid_id, status="finished", rows=((0, "victory"), (1, "defeat")),
             headers=HDR, **extra):
        attrs = dict(id=601, status=SimpleNamespace(value=status), dungeon_session_id=None,
                     law_encounter_id=None, caravan_raid_id=None, sea_raid_id=sea_raid_id)
        attrs.update(extra)
        battle = SimpleNamespace(**attrs)
        db = AsyncMock()
        res = MagicMock()
        res.fetchall.return_value = [tuple(r) for r in rows]
        db.execute = AsyncMock(return_value=res)
        with patch("main.get_battle", new_callable=AsyncMock, return_value=battle):
            return _client(db).get("/battles/internal/601/result", headers=headers)

    def test_carries_sea_raid_id(self):
        r = self._get(SEA_RAID)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sea_raid_id"] == SEA_RAID
        assert body["winner_team"] == 0
        assert body["aborted"] is False
        assert body["caravan_raid_id"] is None
        assert body["fallen_character_ids"] == []

    def test_untagged_is_null(self):
        assert self._get(None).json()["sea_raid_id"] is None

    def test_non_int_tag_is_null(self):
        assert self._get(MagicMock()).json()["sea_raid_id"] is None

    def test_old_battle_object_without_attribute(self):
        battle = SimpleNamespace(id=601, status=SimpleNamespace(value="finished"),
                                 dungeon_session_id=None, law_encounter_id=None, caravan_raid_id=None)
        db = AsyncMock()
        res = MagicMock()
        res.fetchall.return_value = [(0, "victory")]
        db.execute = AsyncMock(return_value=res)
        with patch("main.get_battle", new_callable=AsyncMock, return_value=battle):
            r = _client(db).get("/battles/internal/601/result", headers=HDR)
        assert r.status_code == 200, r.text
        assert r.json()["sea_raid_id"] is None

    def test_force_finished_sea_raid_is_aborted(self):
        body = self._get(SEA_RAID, rows=()).json()
        assert body["aborted"] is True
        assert body["winner_team"] is None
        assert body["sea_raid_id"] == SEA_RAID

    def test_monsters_won(self):
        body = self._get(SEA_RAID, rows=((0, "defeat"), (1, "victory"))).json()
        assert body["winner_team"] == 1
        assert body["sea_raid_id"] == SEA_RAID

    def test_in_progress(self):
        body = self._get(SEA_RAID, status="in_progress").json()
        assert body["status"] == "in_progress"
        assert body["aborted"] is False
        assert body["sea_raid_id"] == SEA_RAID

    def test_requires_token(self):
        assert self._get(SEA_RAID, headers={}).status_code == 401


# ===========================================================================
# 8. POST /battles/{id}/join-request into a sea raid
# ===========================================================================

class TestJoinRequestSea:
    def _join(self, sea_raid_id, status="in_progress", team=0, caravan_raid_id=None):
        battle = SimpleNamespace(id=601, status=SimpleNamespace(value=status), location_id=DECK,
                                 caravan_raid_id=caravan_raid_id, sea_raid_id=sea_raid_id)
        stop = HTTPException(403, "stop-after-raid-check")
        with patch("main.get_battle", new_callable=AsyncMock, return_value=battle), \
                patch("main.verify_character_ownership", new_callable=AsyncMock,
                      side_effect=stop) as owner:
            r = _client(AsyncMock(), USER).post("/battles/601/join-request",
                                                json={"character_id": P1, "team": team})
        return r, owner

    def test_team_1_refused(self):
        r, owner = self._join(SEA_RAID, team=1)
        assert r.status_code == 400
        assert r.json()["detail"] == main.SEA_JOIN_TEAM
        assert r.json()["detail"] == "Против морских монстров можно встать только на сторону экипажа"
        owner.assert_not_called()

    def test_team_1_refused_while_pending(self):
        r, owner = self._join(SEA_RAID, status="pending", team=1)
        assert r.status_code == 400
        assert r.json()["detail"] == main.SEA_JOIN_TEAM
        owner.assert_not_called()

    @pytest.mark.parametrize("status", ["in_progress", "pending"])
    def test_team_0_goes_on(self, status):
        r, owner = self._join(SEA_RAID, status=status, team=0)
        assert r.status_code == 403
        assert r.json()["detail"] == "stop-after-raid-check"
        owner.assert_awaited_once()

    def test_finished_sea_raid_is_inactive_first(self):
        r, owner = self._join(SEA_RAID, status="finished", team=1)
        assert r.status_code == 404
        assert r.json()["detail"] == "Бой не активен"
        owner.assert_not_called()

    def test_invalid_team_rejected_first(self):
        r, owner = self._join(SEA_RAID, team=2)
        assert r.status_code == 400
        assert r.json()["detail"] == "Команда должна быть 0 или 1"
        owner.assert_not_called()

    @pytest.mark.parametrize("tag", [None, MagicMock(), "66"], ids=["null", "mock", "string"])
    def test_untagged_battle_team_1_goes_on(self, tag):
        r, owner = self._join(tag, team=1)
        assert r.status_code == 403
        assert r.json()["detail"] == "stop-after-raid-check"
        owner.assert_awaited_once()

    def test_caravan_rule_unchanged(self):
        r, _ = self._join(None, team=0, caravan_raid_id=55)
        assert r.status_code == 400
        assert r.json()["detail"] == main.CARAVAN_JOIN_FORBIDDEN


# ===========================================================================
# 9. Migration 011
# ===========================================================================

VERSIONS_DIR = os.path.join(APP_DIR, "alembic", "versions")


def _load_migration(filename):
    spec = importlib.util.spec_from_file_location(f"_mig_{filename[:-3]}", os.path.join(VERSIONS_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _revisions():
    out = {}
    for name in os.listdir(VERSIONS_DIR):
        if not name.endswith(".py") or name.startswith("__"):
            continue
        src = open(os.path.join(VERSIONS_DIR, name), encoding="utf-8").read()
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", src, re.M).group(1)
        down = re.search(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", src, re.M)
        out[rev] = down.group(1) if down else None
    return out


class TestMigration011:
    def test_chain(self):
        mig = _load_migration("011_battle_sea_raid.py")
        assert mig.revision == "011_battle_sea_raid"
        assert mig.down_revision == "010_battle_caravan_raid"
        assert len(mig.revision) <= 32

    def test_single_head(self):
        revs = _revisions()
        parents = {d for d in revs.values() if d}
        heads = [r for r in revs if r not in parents]
        assert len(heads) == 1
        assert "011_battle_sea_raid" in revs
        # Only one migration builds on 010 (no branch).
        assert [r for r, d in revs.items() if d == "010_battle_caravan_raid"] == ["011_battle_sea_raid"]
        assert all(len(r) <= 32 for r in revs)

    def _run(self, fn, columns, indexes):
        mig = _load_migration("011_battle_sea_raid.py")
        op = MagicMock()
        mig.op = op
        mig._battle_columns = lambda: list(columns)
        mig._battle_indexes = lambda: list(indexes)
        getattr(mig, fn)()
        return op

    def test_upgrade_adds_nullable_column_and_index(self):
        op = self._run("upgrade", ["id", "caravan_raid_id"], ["ix_battles_caravan_raid_id"])
        table, column = op.add_column.call_args.args
        assert table == "battles"
        assert column.name == "sea_raid_id"
        assert column.nullable is True
        op.create_index.assert_called_once_with("ix_battles_sea_raid_id", "battles", ["sea_raid_id"])
        op.create_foreign_key.assert_not_called()

    def test_upgrade_is_idempotent(self):
        op = self._run("upgrade", ["id", "sea_raid_id"], ["ix_battles_sea_raid_id"])
        op.add_column.assert_not_called()
        op.create_index.assert_not_called()

    def test_upgrade_adds_missing_index_only(self):
        op = self._run("upgrade", ["id", "sea_raid_id"], [])
        op.add_column.assert_not_called()
        op.create_index.assert_called_once()

    def test_downgrade_drops_index_then_column(self):
        op = self._run("downgrade", ["id", "sea_raid_id"], ["ix_battles_sea_raid_id"])
        op.drop_index.assert_called_once_with("ix_battles_sea_raid_id", table_name="battles")
        op.drop_column.assert_called_once_with("battles", "sea_raid_id")
        names = [c[0] for c in op.method_calls]
        assert names.index("drop_index") < names.index("drop_column")

    def test_downgrade_is_idempotent(self):
        op = self._run("downgrade", ["id"], [])
        op.drop_index.assert_not_called()
        op.drop_column.assert_not_called()
