"""FEAT-198 QA (task 10): law in battle-service.

Covers:
  * the activity-lock copy: reason priority (jail > law_encounter > unconscious > dungeon >
    asleep > reading), the relative «— осталось …» messages, the unknown-column fallback of the
    shared-DB read (deploy skew: character-service migration 039 not applied yet);
  * POST /battles/internal/guard: internal token, the lock exemption ONLY for the matching
    encounter id, the guard checks (role / alive / KO / location / busy / locked);
  * the law callback: payload, sent AFTER the NPC-death loop of `_finalize_battle`, `aborted`
    on force-finish, nothing for a battle without the tag, retries;
  * GET /battles/internal/{id}/result carries `law_encounter_id`;
  * «Нападение» (POST /battles/) on a dead or knocked-out NPC -> 409;
  * FEAT-200: ... and on an NPC with ``current_health <= 0`` (409); no attributes row passes.

Preamble copied from test_npc_death_reputation.py (FEAT-163 harness for the finalize paths).
"""

from __future__ import annotations

import asyncio
import itertools
import os
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

pytestmark = pytest.mark.real_activity_lock

TOKEN = "test-internal-token"
PLAYER = 1
GUARD = 900
ENCOUNTER = 12
LOCATION = 100
SOON = datetime.utcnow() + timedelta(hours=2)
PAST = datetime.utcnow() - timedelta(minutes=5)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _row(*values):
    return tuple(values)


def _res(row):
    r = MagicMock()
    r.fetchone.return_value = row
    r.fetchall.return_value = [row] if row is not None else []
    return r


def _lock_row(dungeon=None, unconscious=None, asleep=None, reading=None, jailed=None, encounter=None):
    return _row(dungeon, unconscious, asleep, reading, jailed, encounter)


class _Chars:
    """Mock AsyncSession over a tiny `characters` table (dicts by id)."""

    def __init__(self, chars):
        self.chars = chars
        self.db = AsyncMock()
        self.db.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, query, params=None):
        q = str(query)
        p = params or {}
        cid = p.get("cid", p.get("gid"))
        c = self.chars.get(cid)
        if "jailed_until, law_encounter_id FROM characters" in q:
            if c is None:
                return _res(None)
            return _res(_lock_row(c.get("dungeon"), c.get("unconscious"), None, None,
                                  c.get("jailed"), c.get("encounter")))
        if "SELECT is_npc, npc_role, npc_status, unconscious_until, current_location_id" in q:
            if c is None:
                return _res(None)
            return _res(_row(c.get("is_npc", 0), c.get("role"), c.get("status", "alive"),
                             c.get("unconscious"), c.get("location")))
        if "SELECT is_npc, npc_status, unconscious_until FROM characters" in q:
            if c is None:
                return _res(None)
            return _res(_row(c.get("is_npc", 0), c.get("status", "alive"), c.get("unconscious")))
        if "SELECT user_id FROM characters" in q:
            return _res(_row(c.get("user_id")) if c else None)
        if "SELECT current_location_id FROM characters" in q:
            return _res(_row(c.get("location")) if c else None)
        if "SELECT current_health FROM character_attributes" in q:
            # FEAT-200: no "hp" key = no attributes row
            return _res(_row(c["hp"]) if c and "hp" in c else None)
        return _res(None)


def _player(**kw):
    base = {"is_npc": 0, "user_id": 10, "location": LOCATION, "encounter": ENCOUNTER}
    base.update(kw)
    return base


def _guard(**kw):
    base = {"is_npc": 1, "role": "guard", "status": "alive", "location": LOCATION, "user_id": None}
    base.update(kw)
    return base


def _client(db, user=None):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        app.dependency_overrides[get_current_user_via_http] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


# ===========================================================================
# 1. activity_lock copy: priority, messages, fallback
# ===========================================================================

REASONS = ["jail", "law_encounter", "unconscious", "dungeon", "asleep", "reading"]


def _kwargs_for(present):
    now_plus = datetime.utcnow() + timedelta(hours=3)
    return {
        "jailed_until": now_plus if "jail" in present else None,
        "law_encounter_id": 5 if "law_encounter" in present else None,
        "unconscious_until": now_plus if "unconscious" in present else None,
        "dungeon_session_id": 7 if "dungeon" in present else None,
        "asleep_since": datetime.utcnow() if "asleep" in present else None,
        "reading_since": datetime.utcnow() if "reading" in present else None,
    }


@pytest.mark.parametrize(
    "present",
    [set(c) for n in range(len(REASONS) + 1) for c in itertools.combinations(REASONS, n)],
    ids=lambda s: "+".join(sorted(s)) or "free",
)
def test_reason_priority_matrix(present):
    kw = _kwargs_for(present)
    lock = activity_lock.compute_lock(
        kw["dungeon_session_id"], kw["unconscious_until"],
        asleep_since=kw["asleep_since"], reading_since=kw["reading_since"],
        jailed_until=kw["jailed_until"], law_encounter_id=kw["law_encounter_id"],
    )
    expected = next((r for r in REASONS if r in present), None)
    assert lock["reason"] == expected
    assert lock["locked"] is (expected is not None)
    assert lock["law_encounter_id"] == (5 if expected == "law_encounter" else None)
    assert lock["dungeon_session_id"] == (7 if expected == "dungeon" else None)
    assert set(lock) == {"locked", "reason", "until", "dungeon_session_id", "law_encounter_id"}


def test_past_jail_term_is_free_and_falls_through():
    lock = activity_lock.compute_lock(None, None, jailed_until=PAST)
    assert lock["locked"] is False
    lock = activity_lock.compute_lock(3, None, jailed_until=PAST)
    assert lock["reason"] == "dungeon"


def test_jail_until_from_sqlite_string():
    until = (datetime.utcnow() + timedelta(hours=1)).isoformat(sep=" ")
    lock = activity_lock.compute_lock(None, None, jailed_until=until)
    assert lock["reason"] == "jail"
    assert lock["until"]


@pytest.mark.parametrize("bad", [0, -1, None, "7"])
def test_non_positive_or_non_int_encounter_id_is_not_a_lock(bad):
    assert activity_lock.compute_lock(None, None, law_encounter_id=bad)["locked"] is False


def test_messages_are_relative():
    jail = activity_lock.compute_lock(None, None,
                                      jailed_until=datetime.utcnow() + timedelta(days=2, hours=5, seconds=30))
    assert activity_lock.lock_message(jail) == "Персонаж в тюрьме — осталось 2 д 5 ч"
    assert activity_lock.lock_message(jail, subject="Цель") == "Цель в тюрьме — осталось 2 д 5 ч"
    enc = activity_lock.compute_lock(None, None, law_encounter_id=3)
    assert activity_lock.lock_message(enc) == \
        "Персонаж остановлен стражей — сначала нужно решить, как поступить"
    ko = activity_lock.compute_lock(None, datetime.utcnow() + timedelta(minutes=12, seconds=30))
    assert activity_lock.lock_message(ko) == "Персонаж без сознания — осталось 13 мин"
    for lock in (jail, enc, ko):
        assert "МСК" not in activity_lock.lock_message(lock)
    assert activity_lock.lock_message({"locked": True, "reason": "jail", "until": None}) == "Персонаж в тюрьме"


@pytest.mark.parametrize("delta,expected", [
    (timedelta(seconds=1), "1 мин"),
    (timedelta(minutes=59, seconds=1), "1 ч"),
    (timedelta(hours=3), "3 ч"),
    (timedelta(hours=3, minutes=10), "3 ч 10 мин"),
    (timedelta(days=1), "1 д"),
    (timedelta(days=7), "7 д"),
    (timedelta(days=6, hours=23, minutes=30), "6 д 23 ч"),
    (timedelta(seconds=-30), "1 мин"),
])
def test_format_remaining(delta, expected):
    now = datetime(2026, 11, 4, 12, 0, 0)
    assert activity_lock.format_remaining(now + delta, now) == expected


class TestSharedDbRead:
    @pytest.mark.asyncio
    async def test_reads_the_law_columns(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_res(_lock_row(jailed=SOON)))
        lock = await activity_lock.get_activity_lock(db, 1)
        assert lock["reason"] == "jail"
        sql = str(db.execute.await_args.args[0])
        assert "jailed_until" in sql and "law_encounter_id" in sql

    @pytest.mark.asyncio
    async def test_unknown_column_falls_back_to_legacy_select(self):
        calls = []

        async def execute(query, params=None):
            calls.append(str(query))
            if "jailed_until" in str(query):
                raise RuntimeError(
                    "(pymysql.err.OperationalError) (1054, \"Unknown column 'jailed_until' in 'field list'\")")
            return _res(_row(4, None, None, None))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        lock = await activity_lock.get_activity_lock(db, 1)
        assert lock["reason"] == "dungeon"
        assert len(calls) == 2 and "jailed_until" not in calls[1]

    @pytest.mark.asyncio
    async def test_other_errors_are_not_swallowed(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("(1054, \"Unknown column 'foo' in 'field list'\")"))
        with pytest.raises(RuntimeError):
            await activity_lock.get_activity_lock(db, 1)
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_check_raises_409_for_law_encounter(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_res(_lock_row(encounter=9)))
        with pytest.raises(HTTPException) as exc:
            await activity_lock.check_not_activity_locked(db, 1)
        assert exc.value.status_code == 409
        assert exc.value.detail.startswith("Персонаж остановлен стражей")

    @pytest.mark.asyncio
    async def test_missing_character_is_free(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_res(None))
        assert (await activity_lock.get_activity_lock(db, 1))["locked"] is False


# ===========================================================================
# 2. POST /battles/internal/guard
# ===========================================================================

def _assembled():
    battle = MagicMock()
    battle.id = 777
    p1, p2 = MagicMock(), MagicMock()
    p1.id, p2.id = 31, 32
    return battle, [p1, p2], 31, datetime.utcnow() + timedelta(hours=1)


PAYLOAD = {"law_encounter_id": ENCOUNTER, "character_id": PLAYER, "guard_npc_id": GUARD}


def _post_guard(chars, busy=(), headers=None):
    db = _Chars(chars).db

    async def active(_db, cid):
        return MagicMock() if cid in busy else None

    with patch("main.get_active_battle_for_character", side_effect=active), \
            patch("main._assemble_battle", new_callable=AsyncMock, return_value=_assembled()) as assemble:
        r = _client(db).post("/battles/internal/guard", json=PAYLOAD,
                             headers={"X-Internal-Token": TOKEN} if headers is None else headers)
    return r, assemble


class TestInternalGuardBattle:
    def test_requires_internal_token(self):
        r, assemble = _post_guard({PLAYER: _player(), GUARD: _guard()}, headers={})
        assert r.status_code == 401
        assemble.assert_not_called()

    def test_wrong_internal_token(self):
        r, assemble = _post_guard({PLAYER: _player(), GUARD: _guard()}, headers={"X-Internal-Token": "nope"})
        assert r.status_code == 401
        assemble.assert_not_called()

    def test_matching_encounter_creates_tagged_pvp_attack(self):
        r, assemble = _post_guard({PLAYER: _player(), GUARD: _guard()})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["battle_id"] == 777
        assert body["participants"] == [31, 32]
        args, kwargs = assemble.call_args
        assert args[1] == [PLAYER, GUARD]
        assert args[2] == [1, 2]                      # player team 1, guard team 2
        assert args[3] == "pvp_attack"
        assert args[4] == LOCATION
        assert kwargs["law_encounter_id"] == ENCOUNTER

    def test_ko_expired_guard_is_fine(self):
        r, _ = _post_guard({PLAYER: _player(), GUARD: _guard(unconscious=PAST)})
        assert r.status_code == 201, r.text

    def test_other_encounter_id_is_refused(self):
        r, assemble = _post_guard({PLAYER: _player(encounter=ENCOUNTER + 1), GUARD: _guard()})
        assert r.status_code == 409
        assert r.json()["detail"] == main.NOT_THIS_ENCOUNTER
        assemble.assert_not_called()

    def test_unlocked_player_is_refused(self):
        r, assemble = _post_guard({PLAYER: _player(encounter=None), GUARD: _guard()})
        assert r.status_code == 409
        assert r.json()["detail"] == main.NOT_THIS_ENCOUNTER
        assemble.assert_not_called()

    def test_jailed_player_gets_the_jail_message(self):
        """Jail outranks the encounter lock -> the exemption never applies."""
        r, assemble = _post_guard({PLAYER: _player(jailed=SOON), GUARD: _guard()})
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Персонаж в тюрьме — осталось")
        assemble.assert_not_called()

    def test_dungeon_player_without_encounter_gets_the_dungeon_message(self):
        r, assemble = _post_guard({PLAYER: _player(encounter=None, dungeon=4), GUARD: _guard()})
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж находится в подземелье"
        assemble.assert_not_called()

    def test_player_already_in_battle(self):
        r, assemble = _post_guard({PLAYER: _player(), GUARD: _guard()}, busy={PLAYER})
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж уже в бою"
        assemble.assert_not_called()

    @pytest.mark.parametrize("guard,detail", [
        (None, main.GUARD_NOT_FOUND),
        ({"is_npc": 0, "role": None, "location": LOCATION}, main.GUARD_NOT_FOUND),
        ({"is_npc": 1, "role": "merchant", "status": "alive", "location": LOCATION}, main.GUARD_NOT_FOUND),
        ({"is_npc": 1, "role": None, "status": "alive", "location": LOCATION}, main.GUARD_NOT_FOUND),
        (_guard(status="dead"), main.GUARD_UNAVAILABLE),
        (_guard(unconscious=SOON), main.GUARD_UNAVAILABLE),
        (_guard(location=LOCATION + 1), main.GUARD_ELSEWHERE),
        (_guard(dungeon=5), main.GUARD_UNAVAILABLE),           # locked otherwise (dungeon run)
    ], ids=["missing", "player", "merchant", "no-role", "dead", "ko", "elsewhere", "locked"])
    def test_guard_checks(self, guard, detail):
        chars = {PLAYER: _player()}
        if guard is not None:
            chars[GUARD] = guard
        r, assemble = _post_guard(chars)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == detail
        assemble.assert_not_called()

    def test_player_without_location_cannot_meet_a_guard(self):
        r, assemble = _post_guard({PLAYER: _player(location=None), GUARD: _guard(location=None)})
        assert r.status_code == 409
        assert r.json()["detail"] == main.GUARD_ELSEWHERE
        assemble.assert_not_called()

    def test_busy_guard(self):
        r, assemble = _post_guard({PLAYER: _player(), GUARD: _guard()}, busy={GUARD})
        assert r.status_code == 409
        assert r.json()["detail"] == main.GUARD_BUSY
        assemble.assert_not_called()

    def test_validation_error_on_missing_field(self):
        db = _Chars({}).db
        r = _client(db).post("/battles/internal/guard", json={"character_id": 1},
                             headers={"X-Internal-Token": TOKEN})
        assert r.status_code == 422


class TestAssembleBattlePassesTheTag:
    @pytest.mark.asyncio
    async def test_tag_only_when_set(self, monkeypatch):
        """`_assemble_battle` forwards law_encounter_id to crud.create_battle only when given."""
        seen = []

        async def fake_create(db, ids, teams, **kw):
            seen.append(kw)
            raise RuntimeError("stop")  # stop right after create_battle

        monkeypatch.setattr(main, "create_battle", fake_create)
        for tag in (None, 44):
            with pytest.raises(RuntimeError):
                await main._assemble_battle(AsyncMock(), [1, 2], [1, 2], "pvp_attack", 5, law_encounter_id=tag)
        assert "law_encounter_id" not in seen[0]
        assert seen[1]["law_encounter_id"] == 44


# ===========================================================================
# 3. «Нападение» (POST /battles/) on a dead / knocked-out NPC
# ===========================================================================

USER = UserRead(id=10, username="u", role="user", permissions=[])


def _attack(npc):
    chars = {PLAYER: {"is_npc": 0, "user_id": 10, "location": LOCATION}, GUARD: npc}
    db = _Chars(chars).db
    with patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=None), \
            patch("main._assemble_battle", new_callable=AsyncMock, return_value=_assembled()) as assemble:
        r = _client(db, USER).post("/battles/", json={
            "players": [{"character_id": PLAYER, "team": 0}, {"character_id": GUARD, "team": 1}],
            "battle_type": "pvp_attack",
        })
    return r, assemble


class TestAttackOnUnavailableNpc:
    @pytest.mark.parametrize("npc", [
        _guard(status="dead"),
        _guard(unconscious=SOON),
        {"is_npc": 1, "role": "merchant", "status": "dead", "location": LOCATION},
        {"is_npc": 1, "role": None, "status": "alive", "unconscious": SOON.isoformat(sep=" "),
         "location": LOCATION},
    ], ids=["dead-guard", "ko-guard", "dead-merchant", "ko-string"])
    def test_refused_409(self, npc):
        r, assemble = _attack(npc)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == main.NPC_UNAVAILABLE
        assemble.assert_not_called()

    @pytest.mark.parametrize("npc", [_guard(), _guard(unconscious=PAST)], ids=["alive", "ko-expired"])
    def test_available_npc_reaches_assembly(self, npc):
        r, assemble = _attack(npc)
        assert r.status_code == 201, r.text
        assemble.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_players_and_unknown_ids_pass_the_npc_check(self):
        db = _Chars({PLAYER: {"is_npc": 0, "status": "dead", "unconscious": SOON}}).db
        await main._ensure_npc_available(db, PLAYER)
        await main._ensure_npc_available(db, 4242)


class TestAttackOnNpcWithoutHealth:
    """FEAT-200 (fix 1): an NPC with no health left is not a valid target (409); no attributes row passes."""

    @pytest.mark.parametrize("hp", [0, -5, 0.0], ids=["zero", "negative", "zero-float"])
    def test_npc_without_health_is_refused_409(self, hp):
        r, assemble = _attack(_guard(hp=hp))
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == main.NPC_UNAVAILABLE
        assemble.assert_not_called()

    def test_non_guard_npc_without_health_is_refused_too(self):
        r, assemble = _attack({"is_npc": 1, "role": "merchant", "status": "alive", "location": LOCATION, "hp": 0})
        assert r.status_code == 409 and r.json()["detail"] == main.NPC_UNAVAILABLE
        assemble.assert_not_called()

    @pytest.mark.parametrize("hp", [1, 100], ids=["one", "full"])
    def test_npc_with_health_reaches_assembly(self, hp):
        r, assemble = _attack(_guard(hp=hp))
        assert r.status_code == 201, r.text
        assemble.assert_awaited_once()

    def test_npc_without_an_attributes_row_reaches_assembly(self):
        r, assemble = _attack(_guard())                       # no "hp" -> the SELECT returns no row
        assert r.status_code == 201, r.text
        assemble.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_helper(self):
        db = _Chars({GUARD: _guard(hp=0), 901: _guard(hp=None), 902: _guard(hp=3), 903: _guard(),
                     PLAYER: {"is_npc": 0, "hp": 0}}).db
        with pytest.raises(HTTPException) as exc:
            await main._ensure_npc_available(db, GUARD)
        assert (exc.value.status_code, exc.value.detail) == (409, main.NPC_UNAVAILABLE)
        await main._ensure_npc_available(db, 901)             # NULL health = no data, passes
        await main._ensure_npc_available(db, 902)
        await main._ensure_npc_available(db, 903)
        await main._ensure_npc_available(db, PLAYER)          # a player with 0 hp is not checked here

    @pytest.mark.asyncio
    async def test_dead_npc_is_refused_before_the_health_read(self):
        chars = _Chars({GUARD: _guard(status="dead", hp=100)})
        with pytest.raises(HTTPException):
            await main._ensure_npc_available(chars.db, GUARD)
        assert not any("character_attributes" in str(c.args[0]) for c in chars.db.execute.call_args_list)


# ===========================================================================
# 4. The law callback
# ===========================================================================

class TestNotifyLawBattleEnd:
    @staticmethod
    def _db(encounter_id):
        db = AsyncMock()

        async def execute(query, params=None):
            if "SELECT law_encounter_id FROM battles" in str(query):
                return _res(_row(encounter_id) if encounter_id is not None else None)
            return _res(None)

        db.execute = AsyncMock(side_effect=execute)
        return db

    @pytest.mark.asyncio
    async def test_guard_battle_posts_payload(self):
        with patch("main._post_law_callback", new_callable=AsyncMock) as post:
            await main._notify_law_battle_end(self._db(ENCOUNTER), 501, 2)
            await asyncio.sleep(0)
        post.assert_awaited_once()
        assert post.call_args.args[0] == {
            "battle_id": 501, "law_encounter_id": ENCOUNTER, "winner_team": 2, "aborted": False,
        }

    @pytest.mark.asyncio
    async def test_aborted_flag(self):
        with patch("main._post_law_callback", new_callable=AsyncMock) as post:
            await main._notify_law_battle_end(self._db(ENCOUNTER), 502, None, aborted=True)
            await asyncio.sleep(0)
        assert post.call_args.args[0]["aborted"] is True
        assert post.call_args.args[0]["winner_team"] is None

    @pytest.mark.asyncio
    async def test_untagged_battle_posts_nothing(self):
        with patch("main._post_law_callback", new_callable=AsyncMock) as post:
            await main._notify_law_battle_end(self._db(None), 503, 1)
            await asyncio.sleep(0)
        post.assert_not_called()

    @pytest.mark.asyncio
    async def test_lookup_error_never_breaks_the_ending(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db gone"))
        with patch("main._post_law_callback", new_callable=AsyncMock) as post:
            await main._notify_law_battle_end(db, 504, 1)
            await asyncio.sleep(0)
        post.assert_not_called()


def _cm(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


class TestPostLawCallback:
    @pytest.mark.asyncio
    async def test_url_token_and_stop_on_2xx(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text=""))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_law_callback({"battle_id": 1, "law_encounter_id": 2})
        assert client.post.await_count == 1
        call = client.post.await_args
        assert call.args[0].endswith("/characters/internal/law/battle-result")
        assert call.kwargs["json"] == {"battle_id": 1, "law_encounter_id": 2}
        assert "X-Internal-Token" in call.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_retries_on_5xx_then_stops(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[MagicMock(status_code=503, text=""),
                                             MagicMock(status_code=200, text="")])
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_law_callback({"battle_id": 1})
        assert client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_4xx_is_final(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=409, text="battle mismatch"))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_law_callback({"battle_id": 1})
        assert client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_gives_up_after_three_network_errors(self, monkeypatch):
        import httpx
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_law_callback({"battle_id": 1})
        assert client.post.await_count == 3


# --- the callback inside the real endings (FEAT-163 harness) ----------------

BATTLE_ID = 6060


class _LawFakeDB(FakeDB):
    def __init__(self, law_encounter_id=None):
        super().__init__()
        self.law_encounter_id = law_encounter_id

    def _dispatch(self, q, p):
        if q.startswith("select law_encounter_id from battles"):
            return FakeResult([(self.law_encounter_id,)] if p.get("bid") in self.battles else [])
        if q.startswith("select is_npc, npc_role from characters"):
            c = self.characters.get(p.get("cid"))
            if c and c["is_npc"]:
                return FakeResult([(1, c.get("npc_role"))])
            return FakeResult([])
        return super()._dispatch(q, p)


@pytest.fixture
def rds():
    return FakeRedis()


def _guard_fight(db, rds, player_hp=40, guard_hp=0):
    parts = {
        1: make_participant(PLAYER, team=1, hp=player_hp),
        2: make_participant(GUARD, team=2, hp=guard_hp),
    }
    state = seed_battle(db, rds, BATTLE_ID, parts, next_actor=1,
                        deadline_at=utc_now() + timedelta(hours=1), battle_type="pvp_attack")
    db.characters[GUARD]["is_npc"] = True
    db.characters[GUARD]["user_id"] = None
    db.characters[GUARD]["npc_role"] = "guard"
    return state


async def _finalize_recording(monkeypatch, db, state, winner_team):
    events = []
    original_notify = main._notify_law_battle_end

    async def notify_spy(*a, **kw):
        events.append(("notify", a[2] if len(a) > 2 else kw.get("winner_team")))
        return await original_notify(*a, **kw)

    async def put(url, *a, **kw):
        events.append(("npc-status", url.rsplit("/", 1)[1]))
        return MagicMock(status_code=200, text="ok")

    post_cb = AsyncMock()
    monkeypatch.setattr(main, "_notify_law_battle_end", notify_spy)
    monkeypatch.setattr(main, "_post_law_callback", post_cb)
    with patch.object(main.httpx, "AsyncClient") as client_cls:
        client = client_cls.return_value.__aenter__.return_value
        client.put = AsyncMock(side_effect=put)
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        await main._finalize_battle(db_session=db, battle_id=BATTLE_ID, battle_state=state,
                                    winner_team=winner_team, turn_events=[], turn_number=5)
        await asyncio.sleep(0)
    return events, post_cb


class TestCallbackInEndings:
    @pytest.mark.asyncio
    async def test_player_won_callback_after_npc_death_loop(self, monkeypatch, rds):
        db = _LawFakeDB(law_encounter_id=ENCOUNTER)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _guard_fight(db, rds)
        events, post_cb = await _finalize_recording(monkeypatch, db, state, winner_team=1)
        assert events == [("npc-status", str(GUARD)), ("notify", 1)]
        post_cb.assert_awaited_once()
        assert post_cb.call_args.args[0] == {
            "battle_id": BATTLE_ID, "law_encounter_id": ENCOUNTER, "winner_team": 1, "aborted": False,
        }

    @pytest.mark.asyncio
    async def test_player_lost_reports_the_guard_team(self, monkeypatch, rds):
        db = _LawFakeDB(law_encounter_id=ENCOUNTER)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _guard_fight(db, rds, player_hp=0, guard_hp=50)
        events, post_cb = await _finalize_recording(monkeypatch, db, state, winner_team=2)
        assert events == [("notify", 2)]                  # no NPC died
        assert post_cb.call_args.args[0]["winner_team"] == 2
        assert post_cb.call_args.args[0]["aborted"] is False

    @pytest.mark.asyncio
    async def test_untagged_battle_sends_no_law_callback(self, monkeypatch, rds):
        db = _LawFakeDB(law_encounter_id=None)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _guard_fight(db, rds)
        events, post_cb = await _finalize_recording(monkeypatch, db, state, winner_team=1)
        assert ("npc-status", str(GUARD)) in events
        post_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_finish_reports_aborted(self, monkeypatch, rds):
        db = _LawFakeDB(law_encounter_id=ENCOUNTER)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _guard_fight(db, rds, guard_hp=50)
        post_cb = AsyncMock()
        monkeypatch.setattr(main, "_post_law_callback", post_cb)
        monkeypatch.setattr(main, "_notify_dungeon_battle_end", AsyncMock())
        await main._force_finish_battle(db, BATTLE_ID, state, reason="Админ")
        await asyncio.sleep(0)
        assert db.battles[BATTLE_ID]["status"] == "finished"
        post_cb.assert_awaited_once()
        assert post_cb.call_args.args[0] == {
            "battle_id": BATTLE_ID, "law_encounter_id": ENCOUNTER, "winner_team": None, "aborted": True,
        }

    @pytest.mark.asyncio
    async def test_force_finish_untagged_sends_nothing(self, monkeypatch, rds):
        db = _LawFakeDB(law_encounter_id=None)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _guard_fight(db, rds, guard_hp=50)
        post_cb = AsyncMock()
        monkeypatch.setattr(main, "_post_law_callback", post_cb)
        monkeypatch.setattr(main, "_notify_dungeon_battle_end", AsyncMock())
        await main._force_finish_battle(db, BATTLE_ID, state, reason="Админ")
        await asyncio.sleep(0)
        post_cb.assert_not_called()


# ===========================================================================
# 5. GET /battles/internal/{id}/result
# ===========================================================================

class TestInternalResult:
    def _get(self, law_encounter_id, status="finished", rows=((1, "victory"), (2, "defeat"))):
        battle = SimpleNamespace(id=501, status=SimpleNamespace(value=status), dungeon_session_id=None,
                                 law_encounter_id=law_encounter_id)
        db = AsyncMock()
        res = MagicMock()
        res.fetchall.return_value = [tuple(r) for r in rows]
        db.execute = AsyncMock(return_value=res)
        with patch("main.get_battle", new_callable=AsyncMock, return_value=battle):
            return _client(db).get("/battles/internal/501/result", headers={"X-Internal-Token": TOKEN})

    def test_carries_law_encounter_id(self):
        r = self._get(ENCOUNTER)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["law_encounter_id"] == ENCOUNTER
        assert body["winner_team"] == 1
        assert body["aborted"] is False

    def test_untagged_is_null(self):
        assert self._get(None).json()["law_encounter_id"] is None

    def test_force_finished_guard_battle_is_aborted(self):
        body = self._get(ENCOUNTER, rows=()).json()
        assert body["aborted"] is True
        assert body["winner_team"] is None
        assert body["law_encounter_id"] == ENCOUNTER

    def test_in_progress(self):
        body = self._get(ENCOUNTER, status="in_progress").json()
        assert body["status"] == "in_progress"
        assert body["aborted"] is False

    def test_requires_token(self):
        r = _client(AsyncMock()).get("/battles/internal/501/result")
        assert r.status_code == 401
