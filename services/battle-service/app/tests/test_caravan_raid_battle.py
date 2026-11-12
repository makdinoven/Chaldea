"""FEAT-211 QA (task 13): caravan raid battles in battle-service.

Covers:
  * POST /battles/internal/caravan-raid (B1): internal token, body validation, leader checks
    (missing / elsewhere / in battle / activity-locked), guard checks (NPC / alive / KO /
    location / duplicates / busy / locked), the team-size cap, the solo and group rosters,
    the `caravan` gate (type + target, consumed last, never on an earlier refusal), the
    `caravan_raid_id` tag and the response (`attacker_character_ids`);
  * `_consume_action_gate` / `_consume_combat_gate` payloads and failure handling;
  * `_squad_roster` / `_free_squadmates` (shared with the party mob attack);
  * regression of POST /battles/party/mob-attack: the error order is unchanged
    (roster -> mob -> squad availability -> combat gate) and no caravan tag is passed;
  * `_assemble_battle` forwards `caravan_raid_id` only when set;
  * the raid-result callback: payload, `aborted`, untagged battles, lookup errors, retries,
    inside `_finalize_battle` (after the law notify) and `_force_finish_battle` (aborted=True);
    a failing callback never breaks the battle ending;
  * GET /battles/internal/{id}/result carries `caravan_raid_id`;
  * POST /battles/{id}/join-request refuses a raid battle;
  * migration 010 chain (revision / down_revision / single head / idempotent up & down).

FEAT-212 QA (task 11), sections 10-13: B1 `escort_character_ids` (dedupe, total cap, skip rules,
team 1, leader-escort 409, the "rat" attackers filter, guard-id overlap), the
`autobattle_forbidden` flag (assemble payload -> Redis state -> runtime), `fallen_character_ids`
in the callback and in /internal/{id}/result, and the activity-lock fallback chain
(`_is_missing_column`) against an old schema.

Preamble copied from test_law_guard_battle.py (FEAT-163 harness for the finalize paths).
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
LEADER = 1
MATE_A = 2
MATE_B = 3
G1 = 901
G2 = 902
RAID = 55
CARAVAN = 17
LOCATION = 100
MOB = 99
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
    """Mock AsyncSession over a tiny `characters` table (dicts by id)."""

    def __init__(self, chars):
        self.chars = chars
        self.queries = []
        self.db = AsyncMock()
        self.db.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, query, params=None):
        q = str(query)
        self.queries.append(q)
        p = params or {}
        c = self.chars.get(p.get("cid", p.get("gid")))
        if "SELECT is_npc, npc_status, unconscious_until, current_location_id" in q:
            if c is None:
                return _res(None)
            return _res((c.get("is_npc", 0), c.get("status", "alive"), c.get("unconscious"),
                         c.get("location")))
        if "SELECT is_npc, npc_status, unconscious_until FROM characters" in q:
            if c is None:
                return _res(None)
            return _res((c.get("is_npc", 0), c.get("status", "alive"), c.get("unconscious")))
        if "SELECT is_npc, current_location_id FROM characters" in q:  # FEAT-212 _escort_available
            return _res((c.get("is_npc", 0), c.get("location")) if c else None)
        if "SELECT current_location_id, is_npc FROM characters" in q:
            return _res((c.get("location"), c.get("is_npc", 0)) if c else None)
        if "SELECT current_location_id FROM characters" in q:
            return _res((c.get("location"),) if c else None)
        if "SELECT current_health FROM character_attributes" in q:
            return _res((c["hp"],) if c and "hp" in c else None)
        return _res(None)


def _player(**kw):
    base = {"is_npc": 0, "user_id": 10, "location": LOCATION}
    base.update(kw)
    return base


def _guard(**kw):
    base = {"is_npc": 1, "status": "alive", "location": LOCATION}
    base.update(kw)
    return base


def _world(**overrides):
    chars = {LEADER: _player(), MATE_A: _player(user_id=11), MATE_B: _player(user_id=12),
             G1: _guard(), G2: _guard(), MOB: _guard()}
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


def _assembled(n=3):
    battle = MagicMock()
    battle.id = 777
    parts = []
    for i in range(n):
        p = MagicMock()
        p.id = 31 + i
        parts.append(p)
    return battle, parts, 31, datetime.utcnow() + timedelta(hours=1)


class _Resp:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


class _FakeHttp:
    """Routes main's httpx calls by URL: party active-members, gathering-status, gate consume."""

    def __init__(self, members=None, party_id=1, party_down=False, gathering=(),
                 gathering_down=False, gate=True, gate_status=200, gate_down=False):
        self.members = [LEADER, MATE_A, MATE_B] if members is None else members
        self.party_id = party_id
        self.party_down = party_down
        self.gathering = list(gathering)
        self.gathering_down = gathering_down
        self.gate = gate
        self.gate_status = gate_status
        self.gate_down = gate_down
        self.calls = []

    async def get(self, url, params=None, headers=None, **kw):
        self.calls.append(("GET", url, params, headers))
        if url.endswith("/party/internal/active-members"):
            if self.party_down:
                raise RuntimeError("party down")
            return _Resp(200, {"party_id": self.party_id, "member_character_ids": self.members})
        return _Resp(404)

    async def post(self, url, json=None, headers=None, **kw):
        self.calls.append(("POST", url, json, headers))
        if url.endswith("/locations/internal/gathering-status"):
            if self.gathering_down:
                raise RuntimeError("locations down")
            return _Resp(200, {"gathering_character_ids": self.gathering})
        if url.endswith("/locations/internal/action-gate/consume"):
            if self.gate_down:
                raise RuntimeError("locations down")
            return _Resp(self.gate_status, {"consumed": self.gate})
        return _Resp(404)

    def urls(self):
        return [c[1].rsplit("/", 1)[1] for c in self.calls]

    def gate_calls(self):
        return [c for c in self.calls if c[1].endswith("/action-gate/consume")]

    def factory(self):
        http = self

        class _CM:
            async def __aenter__(self_inner):
                return http

            async def __aexit__(self_inner, *a):
                return False

        return MagicMock(return_value=_CM())


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _locks(monkeypatch, locked=(), escorting=()):
    """Activity lock per character id: ids in `locked` are in a dungeon run, ids in
    `escorting` ride as caravan escorts (FEAT-212)."""
    locked = set(locked)
    escorting = set(escorting)

    async def get_lock(db, cid):
        return activity_lock.compute_lock(7 if cid in locked else None, None,
                                          escort_caravan_id=CARAVAN if cid in escorting else None)

    monkeypatch.setattr(activity_lock, "get_activity_lock", get_lock)


def _payload(**kw):
    body = {"caravan_raid_id": RAID, "caravan_id": CARAVAN, "leader_character_id": LEADER,
            "group": False, "guard_character_ids": [G1, G2], "location_id": LOCATION}
    body.update(kw)
    return body


def _post_raid(monkeypatch, chars=None, body=None, busy=(), locked=(), http=None, headers=HDR,
               escorting=()):
    _locks(monkeypatch, locked, escorting)
    db = _Chars(_world() if chars is None else chars).db
    http = http or _FakeHttp()

    async def active(_db, cid):
        return MagicMock() if cid in busy else None

    n = 1 + len((body or _payload())["guard_character_ids"])
    with patch("main.get_active_battle_for_character", side_effect=active), \
            patch("main.httpx.AsyncClient", http.factory()), \
            patch("main._assemble_battle", new_callable=AsyncMock, return_value=_assembled(n)) as assemble:
        r = _client(db).post("/battles/internal/caravan-raid", json=body or _payload(), headers=headers)
    return r, assemble, http


# ===========================================================================
# 1. POST /battles/internal/caravan-raid (B1)
# ===========================================================================

class TestRaidAuth:
    @pytest.mark.parametrize("headers", [{}, {"X-Internal-Token": "nope"}], ids=["none", "wrong"])
    def test_requires_internal_token(self, monkeypatch, headers):
        r, assemble, http = _post_raid(monkeypatch, headers=headers)
        assert r.status_code == 401
        assemble.assert_not_called()
        assert http.calls == []

    def test_unset_token_fails_closed(self, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        r, assemble, _ = _post_raid(monkeypatch)
        assert r.status_code == 503
        assemble.assert_not_called()

    def test_not_reachable_with_a_user_jwt_only(self, monkeypatch):
        """A player JWT is not the internal token."""
        r, assemble, _ = _post_raid(monkeypatch, headers={"Authorization": "Bearer x"})
        assert r.status_code == 401
        assemble.assert_not_called()


class TestRaidBodyValidation:
    @pytest.mark.parametrize("body", [
        _payload(guard_character_ids=[]),
        _payload(guard_character_ids=[901, 902, 903, 904, 905, 906]),
        {k: v for k, v in _payload().items() if k != "caravan_raid_id"},
        {k: v for k, v in _payload().items() if k != "caravan_id"},
        {k: v for k, v in _payload().items() if k != "location_id"},
        _payload(leader_character_id="'; DROP TABLE battles --"),
        _payload(caravan_id="1 OR 1=1"),
    ], ids=["no-guards", "six-guards", "no-raid-id", "no-caravan", "no-location", "sql-leader", "sql-caravan"])
    def test_422(self, monkeypatch, body):
        r, assemble, http = _post_raid(monkeypatch, body=body)
        assert r.status_code == 422, r.text
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_group_defaults_to_solo(self, monkeypatch):
        body = {k: v for k, v in _payload().items() if k != "group"}
        r, assemble, http = _post_raid(monkeypatch, body=body)
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER]
        assert "active-members" not in http.urls()

    def test_guard_count_above_team_cap_is_400(self, monkeypatch):
        monkeypatch.setattr(main.settings, "BATTLE_MAX_TEAM_SIZE", 2)
        r, assemble, http = _post_raid(monkeypatch, body=_payload(guard_character_ids=[G1, G2, 903]))
        assert r.status_code == 400
        assert "2" in r.json()["detail"]
        assemble.assert_not_called()
        assert http.gate_calls() == []


class TestRaidSolo:
    def test_happy_path_creates_tagged_pve_battle(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["battle_id"] == 777
        assert body["participants"] == [31, 32, 33]
        assert body["next_actor"] == 31
        assert body["attacker_character_ids"] == [LEADER]
        assert set(body) == {"battle_id", "participants", "next_actor", "deadline_at",
                             "attacker_character_ids", "escort_character_ids"}  # FEAT-212
        assert body["escort_character_ids"] == []
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, G1, G2]
        assert args[2] == [main.CARAVAN_RAIDER_TEAM, main.CARAVAN_GUARD_TEAM, main.CARAVAN_GUARD_TEAM]
        assert args[2] == [0, 1, 1]
        assert args[3] == "pve"
        assert args[4] == LOCATION
        assert kwargs == {"caravan_raid_id": RAID}

    def test_consumes_a_caravan_gate_naming_the_caravan(self, monkeypatch):
        r, _, http = _post_raid(monkeypatch)
        assert r.status_code == 201, r.text
        gates = http.gate_calls()
        assert len(gates) == 1
        _, url, payload, headers = gates[0]
        assert url.startswith(main.settings.LOCATIONS_SERVICE_URL)
        assert payload == {"character_id": LEADER, "location_id": LOCATION,
                           "action_type": "caravan", "target_ref": CARAVAN}
        assert "X-Internal-Token" in headers

    def test_gate_names_the_caravan_not_the_raid_or_a_guard(self, monkeypatch):
        r, _, http = _post_raid(monkeypatch, body=_payload(caravan_id=4242, caravan_raid_id=1))
        assert r.status_code == 201
        assert http.gate_calls()[0][2]["target_ref"] == 4242

    @pytest.mark.parametrize("http", [
        _FakeHttp(gate=False), _FakeHttp(gate_status=404), _FakeHttp(gate_down=True),
    ], ids=["not-consumed", "404", "down"])
    def test_no_gate_is_403(self, monkeypatch, http):
        r, assemble, _ = _post_raid(monkeypatch, http=http)
        assert r.status_code == 403
        assert r.json()["detail"] == main.CARAVAN_GATE_REQUIRED
        assemble.assert_not_called()

    def test_leader_missing_404(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, chars=_world(c1=None))
        assert r.status_code == 404
        assert r.json()["detail"] == "Персонаж не найден"
        assemble.assert_not_called()
        assert http.gate_calls() == []

    @pytest.mark.parametrize("loc", [LOCATION + 1, None], ids=["elsewhere", "nowhere"])
    def test_leader_not_at_the_caravan_400(self, monkeypatch, loc):
        r, assemble, http = _post_raid(monkeypatch, chars=_world(c1=_player(location=loc)))
        assert r.status_code == 400
        assert r.json()["detail"] == main.CARAVAN_NOT_HERE
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_body_location_must_match_the_leader(self, monkeypatch):
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(location_id=LOCATION + 5))
        assert r.status_code == 400
        assert r.json()["detail"] == main.CARAVAN_NOT_HERE
        assemble.assert_not_called()

    def test_leader_in_battle_409(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, busy={LEADER})
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж уже в бою"
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_leader_activity_locked_409(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, locked={LEADER})
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж находится в подземелье"
        assemble.assert_not_called()
        assert http.gate_calls() == []


class TestRaidGuards:
    @pytest.mark.parametrize("guard", [
        None,
        _player(),
        _guard(status="dead"),
        _guard(unconscious=SOON),
        _guard(unconscious=SOON.isoformat(sep=" ")),
        _guard(location=LOCATION + 1),
        _guard(location=None),
    ], ids=["missing", "player", "dead", "ko", "ko-string", "elsewhere", "nowhere"])
    def test_unavailable_guard_409(self, monkeypatch, guard):
        r, assemble, http = _post_raid(monkeypatch, chars=_world(c902=guard))
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == main.CARAVAN_GUARDS_UNAVAILABLE
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_ko_expired_guard_is_fine(self, monkeypatch):
        r, _, _ = _post_raid(monkeypatch, chars=_world(c902=_guard(unconscious=PAST)))
        assert r.status_code == 201, r.text

    def test_duplicate_guard_ids_409(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, body=_payload(guard_character_ids=[G1, G1]))
        assert r.status_code == 409
        assert r.json()["detail"] == main.CARAVAN_GUARDS_UNAVAILABLE
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_busy_guard_409(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, busy={G2})
        assert r.status_code == 409
        assert r.json()["detail"] == main.CARAVAN_GUARDS_UNAVAILABLE
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_locked_guard_409(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, locked={G1})
        assert r.status_code == 409
        assert r.json()["detail"] == main.CARAVAN_GUARDS_UNAVAILABLE
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_single_guard(self, monkeypatch):
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(guard_character_ids=[G1]))
        assert r.status_code == 201
        assert assemble.call_args.args[1] == [LEADER, G1]
        assert assemble.call_args.args[2] == [0, 1]

    def test_five_guards(self, monkeypatch):
        ids = [901, 902, 903, 904, 905]
        chars = _world(**{f"c{i}": _guard() for i in ids})
        r, assemble, _ = _post_raid(monkeypatch, chars=chars, body=_payload(guard_character_ids=ids))
        assert r.status_code == 201, r.text
        assert assemble.call_args.args[1] == [LEADER] + ids
        assert assemble.call_args.args[2] == [0] + [1] * 5


class TestRaidGroup:
    def test_pulls_the_free_squad_onto_team_0(self, monkeypatch):
        http = _FakeHttp(gathering=[MATE_B])
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(group=True), http=http)
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER, MATE_A]
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, MATE_A, G1, G2]
        assert args[2] == [0, 0, 1, 1]
        assert kwargs == {"caravan_raid_id": RAID}
        # roster asked for the leader at the raid location
        roster = [c for c in http.calls if c[1].endswith("/active-members")]
        assert roster[0][2] == {"character_id": LEADER, "location_id": LOCATION}
        # the gate is consumed for the leader only, after the roster
        assert http.urls() == ["active-members", "gathering-status", "consume"]
        assert http.gate_calls()[0][2]["character_id"] == LEADER

    def test_busy_and_locked_mates_are_skipped(self, monkeypatch):
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(group=True), busy={MATE_A}, locked={MATE_B})
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER]
        assert assemble.call_args.args[1] == [LEADER, G1, G2]

    def test_squad_capped_at_team_size(self, monkeypatch):
        monkeypatch.setattr(main.settings, "BATTLE_MAX_TEAM_SIZE", 2)
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(group=True, guard_character_ids=[G1]))
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER, MATE_A]

    @pytest.mark.parametrize("http,status,detail", [
        (_FakeHttp(party_id=None, members=[]), 400, "Вы не состоите в отряде"),
        (_FakeHttp(members=[]), 400, "Нет соотрядцев на этой локации"),
        (_FakeHttp(party_down=True), 503, "Сервис отрядов недоступен"),
        (_FakeHttp(gathering=[LEADER]), 400, "Вы сейчас заняты (сбор или бой)"),
    ], ids=["no-party", "nobody-here", "party-down", "leader-gathering"])
    def test_roster_errors_never_consume_the_gate(self, monkeypatch, http, status, detail):
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(group=True), http=http)
        assert r.status_code == status
        assert r.json()["detail"] == detail
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_gathering_service_down_is_tolerated(self, monkeypatch):
        r, _, _ = _post_raid(monkeypatch, body=_payload(group=True), http=_FakeHttp(gathering_down=True))
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER, MATE_A, MATE_B]

    def test_solo_never_asks_party_service(self, monkeypatch):
        http = _FakeHttp(party_down=True)
        r, _, _ = _post_raid(monkeypatch, http=http)
        assert r.status_code == 201
        assert http.urls() == ["consume"]

    def test_group_without_gate_403(self, monkeypatch):
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(group=True), http=_FakeHttp(gate=False))
        assert r.status_code == 403
        assert r.json()["detail"] == main.CARAVAN_GATE_REQUIRED
        assemble.assert_not_called()


# ===========================================================================
# 2. action-gate helpers
# ===========================================================================

class TestActionGate:
    @pytest.mark.asyncio
    async def test_combat_wrapper_keeps_the_combat_type(self):
        http = _FakeHttp()
        with patch("main.httpx.AsyncClient", http.factory()):
            assert await main._consume_combat_gate(LEADER, LOCATION, MOB) is True
        assert http.gate_calls()[0][2] == {"character_id": LEADER, "location_id": LOCATION,
                                           "action_type": "combat", "target_ref": MOB}

    @pytest.mark.asyncio
    async def test_generic_gate_payload(self):
        http = _FakeHttp()
        with patch("main.httpx.AsyncClient", http.factory()):
            assert await main._consume_action_gate(LEADER, LOCATION, main.CARAVAN_GATE_TYPE, CARAVAN) is True
        assert http.gate_calls()[0][2]["action_type"] == "caravan"
        assert http.gate_calls()[0][2]["target_ref"] == CARAVAN

    @pytest.mark.asyncio
    @pytest.mark.parametrize("http", [
        _FakeHttp(gate=False), _FakeHttp(gate_status=500), _FakeHttp(gate_down=True),
    ], ids=["not-consumed", "500", "down"])
    async def test_failures_mean_not_consumed(self, http):
        with patch("main.httpx.AsyncClient", http.factory()):
            assert await main._consume_action_gate(LEADER, LOCATION, "caravan", CARAVAN) is False

    def test_constants(self):
        assert main.COMBAT_GATE_TYPE == "combat"
        assert main.CARAVAN_GATE_TYPE == "caravan"


# ===========================================================================
# 3. _squad_roster / _free_squadmates
# ===========================================================================

class TestSquadHelpers:
    @pytest.mark.asyncio
    async def test_roster_returns_members(self):
        http = _FakeHttp()
        with patch("main.httpx.AsyncClient", http.factory()):
            assert await main._squad_roster(LEADER, LOCATION) == [LEADER, MATE_A, MATE_B]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("http,status", [
        (_FakeHttp(party_id=None), 400), (_FakeHttp(members=[]), 400), (_FakeHttp(party_down=True), 503),
    ], ids=["no-party", "empty", "down"])
    async def test_roster_errors(self, http, status):
        with patch("main.httpx.AsyncClient", http.factory()), pytest.raises(HTTPException) as exc:
            await main._squad_roster(LEADER, LOCATION)
        assert exc.value.status_code == status

    @pytest.mark.asyncio
    async def test_free_squadmates_with_prefetched_members_skips_party(self, monkeypatch):
        _locks(monkeypatch)
        http = _FakeHttp(party_down=True)
        with patch("main.httpx.AsyncClient", http.factory()), \
                patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=None):
            out = await main._free_squadmates(AsyncMock(), LEADER, LOCATION, members=[LEADER, MATE_A])
        assert out == [LEADER, MATE_A]
        assert http.urls() == ["gathering-status"]

    @pytest.mark.asyncio
    async def test_free_squadmates_filters_and_caps(self, monkeypatch):
        _locks(monkeypatch, locked={MATE_B})
        monkeypatch.setattr(main.settings, "BATTLE_MAX_TEAM_SIZE", 2)
        members = [LEADER, MATE_A, MATE_B, 4, 5, 6]
        http = _FakeHttp(members=members, gathering=[4])

        async def active(_db, cid):
            return MagicMock() if cid == 5 else None

        with patch("main.httpx.AsyncClient", http.factory()), \
                patch("main.get_active_battle_for_character", side_effect=active):
            out = await main._free_squadmates(AsyncMock(), LEADER, LOCATION)
        assert out == [LEADER, MATE_A]                     # 6 is free but over the cap

    @pytest.mark.asyncio
    async def test_locked_leader_gets_the_lock_message(self, monkeypatch):
        _locks(monkeypatch, locked={LEADER})
        http = _FakeHttp()
        with patch("main.httpx.AsyncClient", http.factory()), \
                patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=None), \
                pytest.raises(HTTPException) as exc:
            await main._free_squadmates(AsyncMock(), LEADER, LOCATION)
        assert exc.value.status_code == 409


# ===========================================================================
# 4. Regression: POST /battles/party/mob-attack (error order unchanged)
# ===========================================================================

def _party_attack(monkeypatch, chars=None, http=None, busy=(), locked=()):
    _locks(monkeypatch, locked)
    chars = _world() if chars is None else chars
    db = _Chars(chars).db
    http = http or _FakeHttp()
    leader = chars.get(LEADER)
    info = {"user_id": leader["user_id"], "current_location_id": leader["location"],
            "character_id": LEADER} if leader else None

    async def active(_db, cid):
        return MagicMock() if cid in busy else None

    with patch("main._get_character_info", new_callable=AsyncMock, return_value=info), \
            patch("main.get_active_battle_for_character", side_effect=active), \
            patch("main.httpx.AsyncClient", http.factory()), \
            patch("main._assemble_battle", new_callable=AsyncMock, return_value=_assembled(4)) as assemble:
        r = _client(db, USER).post("/battles/party/mob-attack",
                                   json={"leader_character_id": LEADER, "mob_character_id": MOB})
    return r, assemble, http


class TestPartyMobAttackRegression:
    def test_happy_path_unchanged(self, monkeypatch):
        r, assemble, http = _party_attack(monkeypatch, http=_FakeHttp(gathering=[MATE_B]))
        assert r.status_code == 201, r.text
        assert set(r.json()) == {"battle_id", "participants", "next_actor", "deadline_at"}
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, MATE_A, MOB]
        assert args[2] == [0, 0, 1]
        assert args[3] == "pve"
        assert args[4] == LOCATION
        assert kwargs == {}                                 # no caravan / law tag
        assert http.gate_calls()[0][2] == {"character_id": LEADER, "location_id": LOCATION,
                                           "action_type": "combat", "target_ref": MOB}
        assert http.urls() == ["active-members", "gathering-status", "consume"]

    def test_foreign_character_403(self, monkeypatch):
        r, assemble, http = _party_attack(monkeypatch, chars=_world(c1=_player(user_id=999)))
        assert r.status_code == 403
        assert http.calls == []

    def test_roster_error_comes_before_the_mob_check(self, monkeypatch):
        """Not in a party + missing mob -> the party error (roster is fetched first)."""
        r, _, http = _party_attack(monkeypatch, chars=_world(c99=None), http=_FakeHttp(party_id=None))
        assert r.status_code == 400
        assert r.json()["detail"] == "Вы не состоите в отряде"

    def test_party_down_comes_before_the_mob_check(self, monkeypatch):
        r, _, _ = _party_attack(monkeypatch, chars=_world(c99=None), http=_FakeHttp(party_down=True))
        assert r.status_code == 503

    def test_mob_check_comes_before_the_availability_check(self, monkeypatch):
        """Leader busy + missing mob -> 404 for the mob (as before the extraction)."""
        r, _, http = _party_attack(monkeypatch, chars=_world(c99=None), busy={LEADER})
        assert r.status_code == 404
        assert r.json()["detail"] == "Моб не найден"
        assert "gathering-status" not in http.urls()

    @pytest.mark.parametrize("mob,status,detail", [
        (_player(), 400, "Групповая атака доступна только по мобам"),
        (_guard(location=LOCATION + 1), 400, "Моб находится в другой локации"),
        (_guard(status="dead"), 409, None),
    ], ids=["player", "elsewhere", "dead"])
    def test_mob_errors_before_squad_and_gate(self, monkeypatch, mob, status, detail):
        r, assemble, http = _party_attack(monkeypatch, chars=_world(c99=mob), busy={LEADER})
        assert r.status_code == status
        if detail:
            assert r.json()["detail"] == detail
        assert http.urls() == ["active-members"]
        assemble.assert_not_called()

    def test_busy_leader_after_valid_mob(self, monkeypatch):
        r, assemble, http = _party_attack(monkeypatch, busy={LEADER})
        assert r.status_code == 400
        assert r.json()["detail"] == "Вы сейчас заняты (сбор или бой)"
        assert http.gate_calls() == []
        assemble.assert_not_called()

    def test_gate_refused_keeps_the_group_message(self, monkeypatch):
        r, assemble, _ = _party_attack(monkeypatch, http=_FakeHttp(gate=False))
        assert r.status_code == 403
        assert r.json()["detail"] == "Нужен боевой пост с этой целью, чтобы напасть группой"
        assemble.assert_not_called()


# ===========================================================================
# 5. _assemble_battle forwards the tag only when set
# ===========================================================================

class TestAssembleBattleTag:
    @pytest.mark.asyncio
    async def test_caravan_tag_only_when_set(self, monkeypatch):
        seen = []

        async def fake_create(db, ids, teams, **kw):
            seen.append(kw)
            raise RuntimeError("stop")

        monkeypatch.setattr(main, "create_battle", fake_create)
        for tag in (None, RAID):
            with pytest.raises(RuntimeError):
                await main._assemble_battle(AsyncMock(), [1, 2], [0, 1], "pve", 5, caravan_raid_id=tag)
        with pytest.raises(RuntimeError):
            await main._assemble_battle(AsyncMock(), [1, 2], [0, 1], "pve", 5, law_encounter_id=3,
                                        caravan_raid_id=RAID)
        assert "caravan_raid_id" not in seen[0] and "law_encounter_id" not in seen[0]
        assert seen[1]["caravan_raid_id"] == RAID and "law_encounter_id" not in seen[1]
        assert seen[2]["caravan_raid_id"] == RAID and seen[2]["law_encounter_id"] == 3

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
                                     caravan_raid_id=RAID)
        except Exception:
            pass  # only the Battle row matters here
        battle = db.add.call_args_list[0].args[0]
        assert battle.caravan_raid_id == RAID
        assert battle.law_encounter_id is None

    def test_model_column(self):
        import models
        col = models.Battle.__table__.c.caravan_raid_id
        assert col.nullable is True
        assert col.index is True


# ===========================================================================
# 6. The raid-result callback
# ===========================================================================

def _tag_db(raid_id):
    db = AsyncMock()

    async def execute(query, params=None):
        if "SELECT caravan_raid_id FROM battles" in str(query):
            return _res((raid_id,) if raid_id is not None else None)
        return _res(None)

    db.execute = AsyncMock(side_effect=execute)
    return db


class TestNotifyCaravanBattleEnd:
    @pytest.mark.asyncio
    async def test_tagged_battle_posts_payload(self):
        with patch("main._post_caravan_callback", new_callable=AsyncMock) as post:
            await main._notify_caravan_battle_end(_tag_db(RAID), 501, 0)
            await asyncio.sleep(0)
        post.assert_awaited_once()
        assert post.call_args.args[0] == {
            "battle_id": 501, "caravan_raid_id": RAID, "winner_team": 0, "aborted": False,
            "fallen_character_ids": [],  # FEAT-212: no state passed
        }

    @pytest.mark.asyncio
    async def test_aborted_flag(self):
        with patch("main._post_caravan_callback", new_callable=AsyncMock) as post:
            await main._notify_caravan_battle_end(_tag_db(RAID), 502, None, aborted=True)
            await asyncio.sleep(0)
        assert post.call_args.args[0]["aborted"] is True
        assert post.call_args.args[0]["winner_team"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", [None, "7", MagicMock()], ids=["null", "string", "mock"])
    async def test_untagged_battle_posts_nothing(self, value):
        db = _tag_db(RAID)

        async def execute(query, params=None):
            return _res((value,))

        db.execute = AsyncMock(side_effect=execute)
        with patch("main._post_caravan_callback", new_callable=AsyncMock) as post:
            await main._notify_caravan_battle_end(db, 503, 1)
            await asyncio.sleep(0)
        post.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_battle_posts_nothing(self):
        with patch("main._post_caravan_callback", new_callable=AsyncMock) as post:
            await main._notify_caravan_battle_end(_tag_db(None), 504, 1)
            await asyncio.sleep(0)
        post.assert_not_called()

    @pytest.mark.asyncio
    async def test_lookup_error_never_breaks_the_ending(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("Unknown column 'caravan_raid_id'"))
        with patch("main._post_caravan_callback", new_callable=AsyncMock) as post:
            await main._notify_caravan_battle_end(db, 505, 1)
            await asyncio.sleep(0)
        post.assert_not_called()


def _cm(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    return cm


class TestPostCaravanCallback:
    @pytest.mark.asyncio
    async def test_url_token_and_stop_on_2xx(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text=""))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_caravan_callback({"battle_id": 1, "caravan_raid_id": 2})
        assert client.post.await_count == 1
        call = client.post.await_args
        assert call.args[0] == f"{main.settings.CHARACTER_SERVICE_URL}/characters/internal/caravans/raid-result"
        assert call.kwargs["json"] == {"battle_id": 1, "caravan_raid_id": 2}
        assert "X-Internal-Token" in call.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_retries_on_5xx_then_stops(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[MagicMock(status_code=502, text=""),
                                             MagicMock(status_code=200, text="")])
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_caravan_callback({"battle_id": 1})
        assert client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_4xx_is_final(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=409, text="raid mismatch"))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_caravan_callback({"battle_id": 1})
        assert client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_gives_up_after_three_network_errors(self, monkeypatch):
        import httpx
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_caravan_callback({"battle_id": 1})     # no exception
        assert client.post.await_count == 3

    @pytest.mark.asyncio
    async def test_gives_up_after_three_5xx(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=500, text=""))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_caravan_callback({"battle_id": 1})
        assert client.post.await_count == 3


# --- the callback inside the real endings (FEAT-163 harness) ----------------

BATTLE_ID = 7070


class _CaravanFakeDB(FakeDB):
    def __init__(self, caravan_raid_id=None, fail_lookup=False):
        super().__init__()
        self.caravan_raid_id = caravan_raid_id
        self.fail_lookup = fail_lookup

    def _dispatch(self, q, p):
        if q.startswith("select caravan_raid_id from battles"):
            if self.fail_lookup:
                raise RuntimeError("db gone")
            return FakeResult([(self.caravan_raid_id,)] if p.get("bid") in self.battles else [])
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


def _raid_fight(db, rds, raider_hp=40, guard_hp=0):
    parts = {
        1: make_participant(LEADER, team=0, hp=raider_hp),
        2: make_participant(G1, team=1, hp=guard_hp),
    }
    state = seed_battle(db, rds, BATTLE_ID, parts, next_actor=1,
                        deadline_at=utc_now() + timedelta(hours=1), battle_type="pve")
    db.characters[G1]["is_npc"] = True
    db.characters[G1]["user_id"] = None
    db.characters[G1]["npc_role"] = None
    return state


async def _finalize_recording(monkeypatch, db, state, winner_team):
    events = []
    orig_law, orig_caravan = main._notify_law_battle_end, main._notify_caravan_battle_end

    async def law_spy(*a, **kw):
        events.append("law")
        return await orig_law(*a, **kw)

    async def caravan_spy(*a, **kw):
        events.append("caravan")
        return await orig_caravan(*a, **kw)

    async def faction_spy(*a, **kw):
        events.append("faction")

    post_cb = AsyncMock()
    monkeypatch.setattr(main, "_notify_law_battle_end", law_spy)
    monkeypatch.setattr(main, "_notify_caravan_battle_end", caravan_spy)
    monkeypatch.setattr(main, "_notify_faction_battle_end", faction_spy)
    monkeypatch.setattr(main, "_post_caravan_callback", post_cb)
    monkeypatch.setattr(main, "_post_law_callback", AsyncMock())
    with patch.object(main.httpx, "AsyncClient") as client_cls:
        client = client_cls.return_value.__aenter__.return_value
        client.put = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        await main._finalize_battle(db_session=db, battle_id=BATTLE_ID, battle_state=state,
                                    winner_team=winner_team, turn_events=[], turn_number=5)
        await asyncio.sleep(0)
    return events, post_cb


class TestCallbackInEndings:
    @pytest.mark.asyncio
    async def test_raiders_won(self, monkeypatch, rds):
        db = _CaravanFakeDB(caravan_raid_id=RAID)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds)
        events, post_cb = await _finalize_recording(monkeypatch, db, state, winner_team=0)
        assert events == ["law", "caravan", "faction"]       # after the law notify
        post_cb.assert_awaited_once()
        payload = dict(post_cb.call_args.args[0])
        # FEAT-212: fallen = hp <= 0 / dropped out in the final state (the guards here).
        assert payload.pop("fallen_character_ids") == main._fallen_from_state(state)
        assert payload == {
            "battle_id": BATTLE_ID, "caravan_raid_id": RAID, "winner_team": 0, "aborted": False,
        }

    @pytest.mark.asyncio
    async def test_raiders_repelled(self, monkeypatch, rds):
        db = _CaravanFakeDB(caravan_raid_id=RAID)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds, raider_hp=0, guard_hp=50)
        _, post_cb = await _finalize_recording(monkeypatch, db, state, winner_team=1)
        assert post_cb.call_args.args[0]["winner_team"] == 1
        assert post_cb.call_args.args[0]["aborted"] is False

    @pytest.mark.asyncio
    async def test_untagged_battle_sends_no_caravan_callback(self, monkeypatch, rds):
        db = _CaravanFakeDB(caravan_raid_id=None)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds)
        events, post_cb = await _finalize_recording(monkeypatch, db, state, winner_team=0)
        assert "caravan" in events
        post_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_lookup_failure_does_not_break_the_ending(self, monkeypatch, rds):
        db = _CaravanFakeDB(caravan_raid_id=RAID, fail_lookup=True)
        spies = patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds)
        events, post_cb = await _finalize_recording(monkeypatch, db, state, winner_team=0)
        post_cb.assert_not_called()
        assert events[-1] == "faction"                       # the ending went on
        assert BATTLE_ID in spies.finish_battle_calls

    @pytest.mark.asyncio
    async def test_failing_callback_does_not_break_the_ending(self, monkeypatch, rds):
        """The callback itself blowing up (network, bug) stays inside its own task."""
        import httpx
        db = _CaravanFakeDB(caravan_raid_id=RAID)
        spies = patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds)
        crashing = AsyncMock(side_effect=httpx.ConnectError("character-service down"))
        orig = main._notify_caravan_battle_end

        async def notify(*a, **kw):
            return await orig(*a, **kw)

        monkeypatch.setattr(main, "_notify_law_battle_end", AsyncMock())
        monkeypatch.setattr(main, "_notify_faction_battle_end", AsyncMock())
        monkeypatch.setattr(main, "_post_caravan_callback", crashing)
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
        db = _CaravanFakeDB(caravan_raid_id=RAID)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds, guard_hp=50)
        post_cb = AsyncMock()
        monkeypatch.setattr(main, "_post_caravan_callback", post_cb)
        monkeypatch.setattr(main, "_post_law_callback", AsyncMock())
        monkeypatch.setattr(main, "_notify_dungeon_battle_end", AsyncMock())
        await main._force_finish_battle(db, BATTLE_ID, state, reason="Админ")
        await asyncio.sleep(0)
        assert db.battles[BATTLE_ID]["status"] == "finished"
        post_cb.assert_awaited_once()
        assert post_cb.call_args.args[0] == {
            "battle_id": BATTLE_ID, "caravan_raid_id": RAID, "winner_team": None, "aborted": True,
            "fallen_character_ids": [],  # FEAT-212: force-finish passes no state
        }

    @pytest.mark.asyncio
    async def test_force_finish_untagged_sends_nothing(self, monkeypatch, rds):
        db = _CaravanFakeDB(caravan_raid_id=None)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds, guard_hp=50)
        post_cb = AsyncMock()
        monkeypatch.setattr(main, "_post_caravan_callback", post_cb)
        monkeypatch.setattr(main, "_notify_dungeon_battle_end", AsyncMock())
        await main._force_finish_battle(db, BATTLE_ID, state, reason="Админ")
        await asyncio.sleep(0)
        post_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_finish_survives_a_lookup_failure(self, monkeypatch, rds):
        db = _CaravanFakeDB(caravan_raid_id=RAID, fail_lookup=True)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds, guard_hp=50)
        post_cb = AsyncMock()
        monkeypatch.setattr(main, "_post_caravan_callback", post_cb)
        monkeypatch.setattr(main, "_notify_dungeon_battle_end", AsyncMock())
        await main._force_finish_battle(db, BATTLE_ID, state, reason="Админ")
        await asyncio.sleep(0)
        assert db.battles[BATTLE_ID]["status"] == "finished"
        post_cb.assert_not_called()


# ===========================================================================
# 7. GET /battles/internal/{id}/result
# ===========================================================================

class TestInternalResult:
    def _get(self, caravan_raid_id, status="finished", rows=((0, "victory"), (1, "defeat")),
             headers=HDR, **extra):
        battle = SimpleNamespace(id=501, status=SimpleNamespace(value=status), dungeon_session_id=None,
                                 law_encounter_id=None, caravan_raid_id=caravan_raid_id, **extra)
        db = AsyncMock()
        res = MagicMock()
        res.fetchall.return_value = [tuple(r) for r in rows]
        db.execute = AsyncMock(return_value=res)
        with patch("main.get_battle", new_callable=AsyncMock, return_value=battle):
            return _client(db).get("/battles/internal/501/result", headers=headers)

    def test_carries_caravan_raid_id(self):
        r = self._get(RAID)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["caravan_raid_id"] == RAID
        assert body["winner_team"] == 0
        assert body["aborted"] is False
        assert body["law_encounter_id"] is None

    def test_untagged_is_null(self):
        assert self._get(None).json()["caravan_raid_id"] is None

    def test_non_int_tag_is_null(self):
        assert self._get(MagicMock()).json()["caravan_raid_id"] is None

    def test_force_finished_raid_is_aborted(self):
        body = self._get(RAID, rows=()).json()
        assert body["aborted"] is True
        assert body["winner_team"] is None
        assert body["caravan_raid_id"] == RAID

    def test_in_progress(self):
        body = self._get(RAID, status="in_progress").json()
        assert body["status"] == "in_progress"
        assert body["aborted"] is False
        assert body["caravan_raid_id"] == RAID

    def test_requires_token(self):
        assert self._get(RAID, headers={}).status_code == 401


# ===========================================================================
# 8. POST /battles/{id}/join-request into a raid
# ===========================================================================

class TestJoinRequestRefusal:
    def _join(self, caravan_raid_id, status="in_progress", team=0):
        battle = SimpleNamespace(id=501, status=SimpleNamespace(value=status), location_id=LOCATION,
                                 caravan_raid_id=caravan_raid_id)
        stop = HTTPException(403, "stop-after-raid-check")
        with patch("main.get_battle", new_callable=AsyncMock, return_value=battle), \
                patch("main.verify_character_ownership", new_callable=AsyncMock,
                      side_effect=stop) as owner:
            r = _client(AsyncMock(), USER).post("/battles/501/join-request",
                                                json={"character_id": LEADER, "team": team})
        return r, owner

    @pytest.mark.parametrize("team", [0, 1])
    def test_raid_battle_refused(self, team):
        r, owner = self._join(RAID, team=team)
        assert r.status_code == 400
        assert r.json()["detail"] == main.CARAVAN_JOIN_FORBIDDEN
        assert r.json()["detail"] == "К налёту на караван нельзя присоединиться"
        owner.assert_not_called()

    def test_pending_raid_battle_refused(self):
        r, _ = self._join(RAID, status="pending")
        assert r.status_code == 400
        assert r.json()["detail"] == main.CARAVAN_JOIN_FORBIDDEN

    def test_finished_raid_is_inactive_first(self):
        r, _ = self._join(RAID, status="finished")
        assert r.status_code == 404
        assert r.json()["detail"] == "Бой не активен"

    @pytest.mark.parametrize("tag", [None, MagicMock()], ids=["null", "non-int"])
    def test_untagged_battle_goes_on(self, tag):
        r, owner = self._join(tag)
        assert r.status_code == 403
        assert r.json()["detail"] == "stop-after-raid-check"
        owner.assert_awaited_once()


# ===========================================================================
# 9. Migration 010
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


class TestMigration010:
    def test_chain(self):
        mig = _load_migration("010_battle_caravan_raid.py")
        assert mig.revision == "010_battle_caravan_raid"
        assert mig.down_revision == "009_battle_law_encounter"
        assert len(mig.revision) <= 32                         # alembic_version varchar(32)

    def test_single_head_is_010(self):
        revs = _revisions()
        assert "009_battle_law_encounter" in revs
        parents = {d for d in revs.values() if d}
        heads = [r for r in revs if r not in parents]
        assert heads == ["010_battle_caravan_raid"]
        assert all(len(r) <= 32 for r in revs)

    def _run(self, fn, columns, indexes):
        mig = _load_migration("010_battle_caravan_raid.py")
        op = MagicMock()
        mig.op = op
        mig._battle_columns = lambda: list(columns)
        mig._battle_indexes = lambda: list(indexes)
        getattr(mig, fn)()
        return op

    def test_upgrade_adds_nullable_column_and_index(self):
        op = self._run("upgrade", ["id", "law_encounter_id"], ["ix_battles_law_encounter_id"])
        table, column = op.add_column.call_args.args
        assert table == "battles"
        assert column.name == "caravan_raid_id"
        assert column.nullable is True
        op.create_index.assert_called_once_with("ix_battles_caravan_raid_id", "battles", ["caravan_raid_id"])

    def test_upgrade_is_idempotent(self):
        op = self._run("upgrade", ["id", "caravan_raid_id"], ["ix_battles_caravan_raid_id"])
        op.add_column.assert_not_called()
        op.create_index.assert_not_called()

    def test_downgrade_drops_index_then_column(self):
        op = self._run("downgrade", ["id", "caravan_raid_id"], ["ix_battles_caravan_raid_id"])
        op.drop_index.assert_called_once_with("ix_battles_caravan_raid_id", table_name="battles")
        op.drop_column.assert_called_once_with("battles", "caravan_raid_id")
        names = [c[0] for c in op.method_calls]
        assert names.index("drop_index") < names.index("drop_column")

    def test_downgrade_is_idempotent(self):
        op = self._run("downgrade", ["id"], [])
        op.drop_index.assert_not_called()
        op.drop_column.assert_not_called()


# ===========================================================================
# 10. FEAT-212: B1 with escorts
# ===========================================================================

E1 = 21
E2 = 22


def _escort_world(**overrides):
    base = {f"c{E1}": _player(user_id=21), f"c{E2}": _player(user_id=22)}
    base.update(overrides)
    return _world(**base)


class TestRaidEscorts:
    def test_escorts_join_team_1_and_are_flagged(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, chars=_escort_world(),
                                       body=_payload(escort_character_ids=[E1, E2]),
                                       escorting={E1, E2})
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == [E1, E2]
        assert r.json()["attacker_character_ids"] == [LEADER]
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, G1, G2, E1, E2]
        assert args[2] == [0, 1, 1, 1, 1]
        assert kwargs == {"caravan_raid_id": RAID, "autobattle_forbidden_character_ids": [E1, E2]}
        assert len(http.gate_calls()) == 1

    def test_unlocked_escort_is_also_fine(self, monkeypatch):
        """No lock at all (e.g. the escort row was just written) is not a reason to skip."""
        r, _, _ = _post_raid(monkeypatch, chars=_escort_world(), body=_payload(escort_character_ids=[E1]))
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == [E1]

    @pytest.mark.parametrize("escort,busy,locked", [
        (None, (), ()),
        (_guard(), (), ()),
        (_player(location=LOCATION + 1), (), ()),
        (_player(location=None), (), ()),
        (_player(), (E1,), ()),
        (_player(), (), (E1,)),
    ], ids=["missing", "npc", "elsewhere", "nowhere", "in-battle", "other-lock"])
    def test_unavailable_escort_is_silently_skipped(self, monkeypatch, escort, busy, locked):
        r, assemble, _ = _post_raid(monkeypatch, chars=_escort_world(**{f"c{E1}": escort}),
                                    body=_payload(escort_character_ids=[E1, E2]),
                                    busy=busy, locked=locked, escorting={E2})
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == [E2]
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, G1, G2, E2]
        assert args[2] == [0, 1, 1, 1]
        assert kwargs["autobattle_forbidden_character_ids"] == [E2]

    def test_all_escorts_skipped_keeps_the_old_call_shape(self, monkeypatch):
        r, assemble, _ = _post_raid(monkeypatch, chars=_escort_world(),
                                    body=_payload(escort_character_ids=[E1]), locked={E1})
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == []
        assert assemble.call_args.kwargs == {"caravan_raid_id": RAID}

    def test_duplicates_are_removed(self, monkeypatch):
        r, assemble, _ = _post_raid(monkeypatch, chars=_escort_world(),
                                    body=_payload(escort_character_ids=[E1, E1, E1, E1]),
                                    escorting={E1})
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == [E1]
        assert assemble.call_args.args[1] == [LEADER, G1, G2, E1]

    def test_guards_plus_escorts_over_the_cap_is_400(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, body=_payload(escort_character_ids=[E1, E2, 23, 24]))
        assert r.status_code == 400
        assert str(main.settings.BATTLE_MAX_TEAM_SIZE) in r.json()["detail"]
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_exactly_the_cap_is_fine(self, monkeypatch):
        ids = [E1, E2, 23, 24]
        chars = _escort_world(c23=_player(user_id=23), c24=_player(user_id=24))
        r, assemble, _ = _post_raid(monkeypatch, chars=chars,
                                    body=_payload(guard_character_ids=[G1], escort_character_ids=ids),
                                    escorting=set(ids))
        assert r.status_code == 201, r.text
        assert assemble.call_args.args[2] == [0, 1, 1, 1, 1, 1]

    def test_more_than_four_escorts_is_422(self, monkeypatch):
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(guard_character_ids=[G1],
                                                               escort_character_ids=[21, 22, 23, 24, 25]))
        assert r.status_code == 422
        assemble.assert_not_called()

    def test_leader_who_is_an_escort_gets_the_neutral_409(self, monkeypatch):
        r, assemble, http = _post_raid(monkeypatch, body=_payload(escort_character_ids=[LEADER]),
                                       escorting={LEADER})
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail == "Персонаж: действие сейчас недоступно"
        assert "карав" not in detail.lower()
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_escort_lock_on_the_leader_alone_is_also_refused(self, monkeypatch):
        """The rat: the leader is an escort but is not listed — his own lock refuses."""
        r, assemble, _ = _post_raid(monkeypatch, escorting={LEADER})
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж: действие сейчас недоступно"
        assemble.assert_not_called()

    def test_squadmate_escort_is_never_a_raider(self, monkeypatch):
        """Defence in depth: an (unlocked) squadmate listed as an escort is filtered out of
        the attackers and lands on the caravan team only."""
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(group=True, escort_character_ids=[MATE_A]))
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER, MATE_B]
        assert r.json()["escort_character_ids"] == [MATE_A]
        args = assemble.call_args.args
        assert args[1] == [LEADER, MATE_B, G1, G2, MATE_A]
        assert args[2] == [0, 0, 1, 1, 1]

    def test_escort_locked_squadmate_is_skipped_as_a_raider(self, monkeypatch):
        r, _, _ = _post_raid(monkeypatch, body=_payload(group=True, escort_character_ids=[MATE_A]),
                             escorting={MATE_A})
        assert r.status_code == 201, r.text
        assert MATE_A not in r.json()["attacker_character_ids"]
        assert r.json()["escort_character_ids"] == [MATE_A]

    def test_escort_id_equal_to_a_guard_is_ignored(self, monkeypatch):
        r, assemble, _ = _post_raid(monkeypatch, body=_payload(escort_character_ids=[G1]))
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == []
        assert assemble.call_args.args[1] == [LEADER, G1, G2]


class TestEscortAvailable:
    @staticmethod
    def _db(row):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_res(row))
        return db

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reason_kw,expected", [
        ({}, True),
        ({"escort_caravan_id": 5}, True),
        ({"dungeon_session_id": 3}, False),
        ({"law_encounter_id": 4}, False),
        ({"asleep_since": datetime.utcnow()}, False),
    ], ids=["free", "escort-lock", "dungeon", "law", "asleep"])
    async def test_only_the_escort_lock_is_exempt(self, monkeypatch, reason_kw, expected):
        async def get_lock(db, cid):
            kw = dict(reason_kw)
            return activity_lock.compute_lock(kw.pop("dungeon_session_id", None), None, **kw)

        monkeypatch.setattr(activity_lock, "get_activity_lock", get_lock)
        with patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=None):
            assert await main._escort_available(self._db((0, LOCATION)), E1, LOCATION) is expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("row", [None, (1, LOCATION), (True, LOCATION), (0, LOCATION + 1), (0, None)],
                             ids=["missing", "npc", "npc-bool", "elsewhere", "nowhere"])
    async def test_row_checks(self, row):
        with patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=None):
            assert await main._escort_available(self._db(row), E1, LOCATION) is False

    @pytest.mark.asyncio
    async def test_in_battle(self):
        with patch("main.get_active_battle_for_character", new_callable=AsyncMock, return_value=MagicMock()):
            assert await main._escort_available(self._db((0, LOCATION)), E1, LOCATION) is False


# ===========================================================================
# 11. FEAT-212: autobattle_forbidden flag (assemble -> state -> runtime)
# ===========================================================================

class TestAutobattleForbiddenFlag:
    @pytest.mark.asyncio
    async def test_assemble_flags_only_the_listed_characters(self, monkeypatch):
        battle = SimpleNamespace(id=4040)
        parts = [SimpleNamespace(id=31 + i, character_id=cid, team=t)
                 for i, (cid, t) in enumerate([(LEADER, 0), (G1, 1), (E1, 1)])]
        monkeypatch.setattr(main, "create_battle", AsyncMock(return_value=(battle, parts)))

        async def info(cid, pid):
            return {"participant_id": pid, "character_id": cid}

        monkeypatch.setattr(main, "build_participant_info", info)
        monkeypatch.setattr(main, "_participant_payload",
                            lambda snap, objs: {"participant_id": snap["participant_id"],
                                                "character_id": snap["character_id"]})
        monkeypatch.setattr(main, "_saber_seed", AsyncMock(return_value={}))
        monkeypatch.setattr(main, "save_snapshot", AsyncMock())
        monkeypatch.setattr(main, "cache_snapshot", AsyncMock())
        monkeypatch.setattr(main, "get_redis_client", AsyncMock(return_value=AsyncMock()))
        init = AsyncMock()
        monkeypatch.setattr(main, "init_battle_state", init)

        async def execute(query, params=None):
            return _res((1 if params["cid"] == G1 else 0,))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        http = MagicMock()
        client = http.return_value.__aenter__.return_value
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        monkeypatch.setattr(main.httpx, "AsyncClient", http)

        await main._assemble_battle(db, [LEADER, G1, E1], [0, 1, 1], "pve", LOCATION,
                                    caravan_raid_id=RAID, autobattle_forbidden_character_ids=[E1])
        payload = {p["character_id"]: p for p in init.call_args.kwargs["participants_payload"]}
        assert payload[E1]["autobattle_forbidden"] is True
        assert "autobattle_forbidden" not in payload[LEADER]
        assert "autobattle_forbidden" not in payload[G1]
        # only the NPC guard is registered with autobattle, never the escort
        regs = [c.kwargs["json"]["participant_id"] for c in client.post.call_args_list]
        assert regs == [32]

    @pytest.mark.asyncio
    async def test_init_battle_state_copies_the_flag(self):
        import json as _json
        # A private copy of the real module: other test files swap `redis_state` for a mock.
        spec = importlib.util.spec_from_file_location("_feat212_redis_state",
                                                      os.path.join(APP_DIR, "redis_state.py"))
        redis_state = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(redis_state)
        real_init = redis_state.init_battle_state
        rds = AsyncMock()

        def payload(pid, cid, team, **extra):
            p = {"participant_id": pid, "character_id": cid, "team": team, "hp": 100, "mana": 10,
                 "energy": 10, "stamina": 10, "max_hp": 100, "max_mana": 10, "max_energy": 10,
                 "max_stamina": 10, "fast_slots": []}
            p.update(extra)
            return p

        with patch.object(redis_state, "get_redis_client", new=AsyncMock(return_value=rds)):
            await real_init(battle_id=4041,
                            participants_payload=[payload(1, LEADER, 0),
                                                  payload(2, E1, 1, autobattle_forbidden=True)],
                            first_actor_participant_id=1,
                            deadline_at=datetime.utcnow() + timedelta(hours=1))
        state = _json.loads(rds.set.call_args.args[1])
        assert state["participants"]["2"]["autobattle_forbidden"] is True
        assert state["participants"]["1"]["autobattle_forbidden"] is False

    @staticmethod
    def _state():
        from _feat163_harness import make_state
        parts = {1: make_participant(LEADER, team=0), 2: make_participant(E1, team=1)}
        parts[2]["autobattle_forbidden"] = True
        return make_state(parts, next_actor=1, deadline_at=utc_now() + timedelta(hours=1))

    def test_runtime_exposes_the_flag_with_a_false_default(self):
        runtime = main._build_runtime(self._state())["participants"]
        runtime = {str(k): v for k, v in runtime.items()}
        assert runtime["2"]["autobattle_forbidden"] is True
        assert runtime["1"]["autobattle_forbidden"] is False   # old state without the key

    def test_internal_state_exposes_the_flag(self, monkeypatch):
        state = self._state()
        state.setdefault("total_turns", 0)
        state.setdefault("last_turn", 0)
        monkeypatch.setattr(main, "load_state", AsyncMock(return_value=state))
        monkeypatch.setattr(main, "get_redis_client", AsyncMock(return_value=AsyncMock()))
        monkeypatch.setattr(main, "get_cached_snapshot", AsyncMock(return_value=[]))
        r = _client(AsyncMock()).get("/battles/internal/4042/state", headers=HDR)
        assert r.status_code == 200, r.text
        participants = r.json()["runtime"]["participants"]
        assert participants["2"]["autobattle_forbidden"] is True
        assert participants["1"]["autobattle_forbidden"] is False


# ===========================================================================
# 12. FEAT-212: fallen_character_ids (callback + /internal/{id}/result)
# ===========================================================================

def _res_rows(rows):
    r = MagicMock()
    r.fetchall.return_value = [tuple(x) for x in rows]
    r.fetchone.return_value = tuple(rows[0]) if rows else None
    return r


class TestFallenIds:
    def test_from_state(self):
        state = {"participants": {
            "1": {"character_id": LEADER, "hp": 0},
            "2": {"character_id": G1, "hp": 30},
            "3": {"character_id": E1, "hp": -4},
            "4": {"character_id": E2, "hp": 50, "dropped_out": True},
            "5": {"character_id": "x", "hp": 0},          # junk id ignored
            "6": {"character_id": MATE_A},                 # no hp -> alive
        }}
        assert main._fallen_from_state(state) == sorted([LEADER, E1, E2])

    @pytest.mark.parametrize("state", [None, {}, {"participants": None}], ids=["none", "empty", "null"])
    def test_empty(self, state):
        assert main._fallen_from_state(state) == []

    @pytest.mark.asyncio
    async def test_callback_carries_the_fallen(self):
        state = {"participants": {"1": {"character_id": LEADER, "hp": 20, "team": 0},
                                  "2": {"character_id": G1, "hp": 0, "team": 1},
                                  "3": {"character_id": E1, "hp": 0, "team": 1}}}
        with patch("main._post_caravan_callback", new_callable=AsyncMock) as post:
            await main._notify_caravan_battle_end(_tag_db(RAID), 601, 0, state=state)
            await asyncio.sleep(0)
        assert post.call_args.args[0]["fallen_character_ids"] == [E1, G1]

    @pytest.mark.asyncio
    async def test_finalize_passes_the_final_state(self, monkeypatch, rds):
        db = _CaravanFakeDB(caravan_raid_id=RAID)
        patch_main(monkeypatch, main, db, rds, rewards=None)
        state = _raid_fight(db, rds, raider_hp=40, guard_hp=0)
        _, post_cb = await _finalize_recording(monkeypatch, db, state, winner_team=0)
        assert post_cb.call_args.args[0]["fallen_character_ids"] == [G1]

    @staticmethod
    def _result(monkeypatch, caravan_raid_id=RAID, state=None, state_exc=None, rows=()):
        battle = SimpleNamespace(id=501, status=SimpleNamespace(value="finished"), dungeon_session_id=None,
                                 law_encounter_id=None, caravan_raid_id=caravan_raid_id)
        load = AsyncMock(side_effect=state_exc) if state_exc else AsyncMock(return_value=state)
        monkeypatch.setattr(main, "load_state", load)

        async def execute(query, params=None):
            q = str(query)
            if "SELECT character_id, team, dropped_out_at FROM battle_participants" in q:
                return _res_rows(rows)
            if "battle_history" in q:   # winner = team 1
                return _res_rows([(0, "defeat"), (1, "victory")])
            return _res(None)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        with patch("main.get_battle", new_callable=AsyncMock, return_value=battle):
            r = _client(db).get("/battles/internal/501/result", headers=HDR)
        assert r.status_code == 200, r.text
        return r.json(), load

    def test_result_from_redis_state(self, monkeypatch):
        state = {"participants": {"1": {"character_id": LEADER, "hp": 0},
                                  "2": {"character_id": E1, "hp": 3, "dropped_out": True},
                                  "3": {"character_id": G1, "hp": 9}}}
        body, _ = self._result(monkeypatch, state=state, rows=[(G1, 1, None)])
        assert body["fallen_character_ids"] == [LEADER, E1]
        assert body["winner_team"] == 1

    @pytest.mark.parametrize("state_exc", [None, RuntimeError("redis down")], ids=["expired", "unreadable"])
    def test_result_db_fallback(self, monkeypatch, state_exc):
        rows = [(LEADER, 0, None), (MATE_A, 0, None),       # losing team -> fallen
                (G1, 1, None), (E1, 1, datetime.utcnow()),  # dropped out on the winning team
                (E2, 1, None)]
        body, _ = self._result(monkeypatch, state=None, state_exc=state_exc, rows=rows)
        assert body["fallen_character_ids"] == sorted([LEADER, MATE_A, E1])

    def test_untagged_battle_has_empty_fallen_and_skips_the_lookup(self, monkeypatch):
        body, load = self._result(monkeypatch, caravan_raid_id=None,
                                  state={"participants": {"1": {"character_id": 1, "hp": 0}}})
        assert body["fallen_character_ids"] == []
        load.assert_not_called()


# ===========================================================================
# 13. FEAT-212: activity lock — escort reason + deploy-skew fallback chain
# ===========================================================================

def _lock_db(schema):
    """Mock AsyncSession over a `characters` table with only the given lock columns.
    An unknown column raises the MySQL error (whose text also echoes the whole SQL)."""
    calls = []

    async def execute(query, params=None):
        q = str(query)
        calls.append(q)
        cols = [c.strip() for c in q.split("SELECT", 1)[1].split("FROM", 1)[0].split(",")]
        for c in cols:
            if c not in schema:
                raise RuntimeError(f"(pymysql.err.OperationalError) (1054, \"Unknown column '{c}' "
                                   f"in 'field list'\") [SQL: {q}]")
        return _res(tuple(schema[c] for c in cols))

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute)
    return db, calls


_LEGACY_COLS = {"dungeon_session_id": None, "unconscious_until": None, "asleep_since": None,
                "reading_since": None}
_LAW_COLS = dict(_LEGACY_COLS, jailed_until=None, law_encounter_id=None)
_FULL_COLS = dict(_LAW_COLS, escort_caravan_id=None)


@pytest.mark.real_activity_lock
class TestEscortLockChain:
    def test_neutral_message_for_every_subject(self):
        lock = activity_lock.compute_lock(None, None, escort_caravan_id=3)
        assert lock["reason"] == "caravan_escort" and lock["locked"] is True
        for subject in ("Персонаж", "Ваш персонаж", "Цель"):
            msg = activity_lock.lock_message(lock, subject=subject)
            assert msg == f"{subject}: действие сейчас недоступно"
            assert "карав" not in msg.lower() and "охран" not in msg.lower()

    @pytest.mark.parametrize("kw,expected", [
        ({"escort_caravan_id": 3, "dungeon_session_id": 2}, "dungeon"),
        ({"escort_caravan_id": 3, "asleep_since": datetime.utcnow()}, "caravan_escort"),
        ({"escort_caravan_id": 3, "law_encounter_id": 1}, "law_encounter"),
        ({"escort_caravan_id": 0}, None),
        ({"escort_caravan_id": "3"}, None),
    ], ids=["dungeon-wins", "beats-asleep", "law-wins", "zero", "non-int"])
    def test_priority(self, kw, expected):
        kw = dict(kw)
        lock = activity_lock.compute_lock(kw.pop("dungeon_session_id", None), None, **kw)
        assert lock["reason"] == expected

    def test_lock_for_character_reads_the_attribute(self):
        assert activity_lock.lock_for_character(SimpleNamespace(escort_caravan_id=4))["reason"] == "caravan_escort"

    @pytest.mark.asyncio
    async def test_full_schema_one_query(self):
        db, calls = _lock_db(dict(_FULL_COLS, escort_caravan_id=8))
        assert (await activity_lock.get_activity_lock(db, 1))["reason"] == "caravan_escort"
        assert len(calls) == 1 and "escort_caravan_id" in calls[0]

    @pytest.mark.asyncio
    async def test_no_escort_column_falls_back_to_the_law_sql(self):
        db, calls = _lock_db(dict(_LAW_COLS, law_encounter_id=6))
        assert (await activity_lock.get_activity_lock(db, 1))["reason"] == "law_encounter"
        assert len(calls) == 2
        assert "escort_caravan_id" not in calls[1] and "law_encounter_id" in calls[1]

    @pytest.mark.asyncio
    async def test_no_law_columns_jumps_straight_to_legacy(self):
        db, calls = _lock_db(dict(_LEGACY_COLS, dungeon_session_id=4))
        assert (await activity_lock.get_activity_lock(db, 1))["reason"] == "dungeon"
        assert len(calls) == 2                     # full -> legacy, the law SQL is skipped
        assert "jailed_until" not in calls[1]

    @pytest.mark.asyncio
    async def test_escort_then_law_missing_walks_the_whole_chain(self):
        """The DB names `escort_caravan_id` first, then the law SQL fails too -> legacy."""
        calls = []

        async def execute(query, params=None):
            q = str(query)
            calls.append(q)
            if "escort_caravan_id" in q:
                raise RuntimeError(f"(1054, \"Unknown column 'escort_caravan_id' in 'field list'\") [SQL: {q}]")
            if "jailed_until" in q:
                raise RuntimeError(f"(1054, \"Unknown column 'law_encounter_id' in 'field list'\") [SQL: {q}]")
            return _res((None, None, None, datetime.utcnow()))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        assert (await activity_lock.get_activity_lock(db, 1))["reason"] == "reading"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_sqlite_wording_is_recognised(self):
        calls = []

        async def execute(query, params=None):
            calls.append(str(query))
            if "escort_caravan_id" in str(query):
                raise RuntimeError("(sqlite3.OperationalError) no such column: escort_caravan_id")
            return _res((None, None, None, None, None, None))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        assert (await activity_lock.get_activity_lock(db, 1))["locked"] is False
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_other_missing_column_is_not_mistaken_for_ours(self):
        """The error echoes the SQL (which names escort_caravan_id) — only the column the DB
        names counts, so an unrelated missing column propagates."""
        async def execute(query, params=None):
            raise RuntimeError(f"(1054, \"Unknown column 'dungeon_session_id' in 'field list'\") [SQL: {query}]")

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        with pytest.raises(RuntimeError):
            await activity_lock.get_activity_lock(db, 1)
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_law_sql_failing_for_another_reason_propagates(self):
        async def execute(query, params=None):
            if "escort_caravan_id" in str(query):
                raise RuntimeError("(1054, \"Unknown column 'escort_caravan_id' in 'field list'\")")
            raise RuntimeError("connection lost")

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        with pytest.raises(RuntimeError, match="connection lost"):
            await activity_lock.get_activity_lock(db, 1)

    @pytest.mark.parametrize("msg,names,expected", [
        ("(1054, \"Unknown column 'escort_caravan_id' in 'field list'\")", ("escort_caravan_id",), True),
        ("(1054, \"Unknown column 'characters.escort_caravan_id' in 'field list'\")", ("escort_caravan_id",), True),
        ("no such column: jailed_until", ("jailed_until", "law_encounter_id"), True),
        ("(1054, \"Unknown column 'foo' in 'field list'\") [SQL: SELECT escort_caravan_id]",
         ("escort_caravan_id",), False),
        ("connection lost escort_caravan_id", ("escort_caravan_id",), False),
    ], ids=["mysql", "qualified", "sqlite", "echoed-sql", "no-pattern"])
    def test_is_missing_column(self, msg, names, expected):
        assert activity_lock._is_missing_column(RuntimeError(msg), names) is expected

    @pytest.mark.asyncio
    async def test_check_raises_409_neutral(self):
        db, _ = _lock_db(dict(_FULL_COLS, escort_caravan_id=2))
        with pytest.raises(HTTPException) as exc:
            await activity_lock.check_not_activity_locked(db, 1, subject="Ваш персонаж")
        assert exc.value.status_code == 409
        assert exc.value.detail == "Ваш персонаж: действие сейчас недоступно"
