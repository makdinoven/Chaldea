"""FEAT-216 QA (task 13): POST /battles/internal/customs-fight (B1).

Covers:
  * internal token required (none / wrong / unset -> fail closed / user JWT only);
  * body validation (422) and the exactly-one-mode rule (both / none -> 400);
  * team-size caps (guards + escorts, the enforcer team) -> 400;
  * an id present in both `enforcer_npc_ids` and `guard_character_ids` -> 400;
  * leader mode: leader checks (missing / elsewhere / busy / locked / is an escort), solo and
    group squads, escorts filtered out of the attackers, NO action gate consumed;
  * NPC-enforcer mode: enforcer checks, never asks the party / locations services, escorts on
    team 1, 409 «Защитников каравана нет» when no escort is placed;
  * 409 no defenders in leader mode (no guards, no placed escort);
  * the battle is `pve`, tagged with `caravan_raid_id`, escorts flagged autobattle_forbidden.

Preamble and mocks copied from test_caravan_raid_battle.py (FEAT-211/212).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
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
from fastapi.testclient import TestClient  # noqa: E402

app.router.on_startup.clear()

URL = "/battles/internal/customs-fight"
TOKEN = "test-internal-token"
HDR = {"X-Internal-Token": TOKEN}
LEADER = 1
MATE_A = 2
MATE_B = 3
G1 = 901
G2 = 902
N1 = 801
N2 = 802
N3 = 803
E1 = 21
E2 = 22
RAID = 55
CARAVAN = 17
LOCATION = 100
SOON = datetime.utcnow() + timedelta(hours=2)
NEUTRAL_LOCK = "Персонаж: действие сейчас недоступно"


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
        self.db = AsyncMock()
        self.db.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, query, params=None):
        q = str(query)
        p = params or {}
        c = self.chars.get(p.get("cid", p.get("gid")))
        if "SELECT is_npc, npc_status, unconscious_until, current_location_id" in q:
            if c is None:
                return _res(None)
            return _res((c.get("is_npc", 0), c.get("status", "alive"), c.get("unconscious"),
                         c.get("location")))
        if "SELECT is_npc, current_location_id FROM characters" in q:
            return _res((c.get("is_npc", 0), c.get("location")) if c else None)
        if "SELECT current_location_id FROM characters" in q:
            return _res((c.get("location"),) if c else None)
        return _res(None)


def _player(**kw):
    base = {"is_npc": 0, "user_id": 10, "location": LOCATION}
    base.update(kw)
    return base


def _npc(**kw):
    base = {"is_npc": 1, "status": "alive", "location": LOCATION}
    base.update(kw)
    return base


def _world(**overrides):
    chars = {LEADER: _player(), MATE_A: _player(user_id=11), MATE_B: _player(user_id=12),
             E1: _player(user_id=21), E2: _player(user_id=22),
             G1: _npc(), G2: _npc(), N1: _npc(), N2: _npc(), N3: _npc()}
    for k, v in overrides.items():
        cid = int(k[1:])
        if v is None:
            chars.pop(cid, None)
        else:
            chars[cid] = v
    return chars


def _client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
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
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


class _FakeHttp:
    """Routes main's httpx calls by URL: party active-members, gathering-status, gate consume."""

    def __init__(self, members=None, gathering=(), gate=True):
        self.members = [LEADER, MATE_A, MATE_B] if members is None else members
        self.gathering = list(gathering)
        self.gate = gate
        self.calls = []

    async def get(self, url, params=None, headers=None, **kw):
        self.calls.append(("GET", url, params, headers))
        if url.endswith("/party/internal/active-members"):
            return _Resp(200, {"party_id": 1, "member_character_ids": self.members})
        return _Resp(404)

    async def post(self, url, json=None, headers=None, **kw):
        self.calls.append(("POST", url, json, headers))
        if url.endswith("/locations/internal/gathering-status"):
            return _Resp(200, {"gathering_character_ids": self.gathering})
        if url.endswith("/locations/internal/action-gate/consume"):
            return _Resp(200, {"consumed": self.gate})
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
    """`locked` ids are in a dungeon run, `escorting` ids ride as caravan escorts."""
    locked = set(locked)
    escorting = set(escorting)

    async def get_lock(db, cid):
        return activity_lock.compute_lock(7 if cid in locked else None, None,
                                          escort_caravan_id=CARAVAN if cid in escorting else None)

    monkeypatch.setattr(activity_lock, "get_activity_lock", get_lock)


def _leader_body(**kw):
    body = {"caravan_raid_id": RAID, "caravan_id": CARAVAN, "location_id": LOCATION,
            "leader_character_id": LEADER, "group": False,
            "guard_character_ids": [G1, G2], "escort_character_ids": []}
    body.update(kw)
    return body


def _npc_body(**kw):
    body = {"caravan_raid_id": RAID, "caravan_id": CARAVAN, "location_id": LOCATION,
            "enforcer_npc_ids": [N1, N2], "guard_character_ids": [G1],
            "escort_character_ids": [E1]}
    body.update(kw)
    return body


def _post(monkeypatch, body, chars=None, busy=(), locked=(), escorting=(), http=None, headers=HDR):
    _locks(monkeypatch, locked, escorting)
    db = _Chars(_world() if chars is None else chars).db
    http = http or _FakeHttp()

    async def active(_db, cid):
        return MagicMock() if cid in busy else None

    with patch("main.get_active_battle_for_character", side_effect=active), \
            patch("main.httpx.AsyncClient", http.factory()), \
            patch("main._assemble_battle", new_callable=AsyncMock,
                  return_value=_assembled(4)) as assemble:
        r = _client(db).post(URL, json=body, headers=headers)
    return r, assemble, http


# ===========================================================================
# 1. auth
# ===========================================================================

class TestAuth:
    @pytest.mark.parametrize("headers", [{}, {"X-Internal-Token": "nope"},
                                         {"Authorization": "Bearer x"}],
                             ids=["none", "wrong", "user-jwt"])
    def test_requires_internal_token(self, monkeypatch, headers):
        r, assemble, http = _post(monkeypatch, _leader_body(), headers=headers)
        assert r.status_code == 401
        assemble.assert_not_called()
        assert http.calls == []

    def test_unset_token_fails_closed(self, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        r, assemble, _ = _post(monkeypatch, _npc_body())
        assert r.status_code == 503
        assemble.assert_not_called()

    def test_route_is_internal(self):
        paths = {getattr(rt, "path", None) for rt in app.routes}
        assert URL in paths


# ===========================================================================
# 2. body validation / mode rule / caps
# ===========================================================================

class TestBodyValidation:
    @pytest.mark.parametrize("body", [
        {k: v for k, v in _leader_body().items() if k != "caravan_raid_id"},
        {k: v for k, v in _leader_body().items() if k != "caravan_id"},
        {k: v for k, v in _leader_body().items() if k != "location_id"},
        _npc_body(enforcer_npc_ids=[801, 802, 803, 804, 805, 806]),
        _leader_body(guard_character_ids=[901, 902, 903, 904, 905, 906]),
        _leader_body(escort_character_ids=[21, 22, 23, 24, 25]),
        _leader_body(leader_character_id="'; DROP TABLE battles --"),
        _npc_body(enforcer_npc_ids=["1 OR 1=1"]),
    ], ids=["no-raid-id", "no-caravan", "no-location", "six-enforcers", "six-guards",
            "five-escorts", "sql-leader", "sql-enforcer"])
    def test_422(self, monkeypatch, body):
        r, assemble, http = _post(monkeypatch, body)
        assert r.status_code == 422, r.text
        assemble.assert_not_called()
        assert http.calls == []

    def test_both_modes_400(self, monkeypatch):
        r, assemble, http = _post(monkeypatch, _leader_body(enforcer_npc_ids=[N1]))
        assert r.status_code == 400
        assert r.json()["detail"] == main.CUSTOMS_MODE_REQUIRED
        assemble.assert_not_called()
        assert http.calls == []

    @pytest.mark.parametrize("body", [
        _leader_body(leader_character_id=None),
        _npc_body(enforcer_npc_ids=[]),
        {"caravan_raid_id": RAID, "caravan_id": CARAVAN, "location_id": LOCATION},
    ], ids=["leader-null", "empty-enforcers", "bare"])
    def test_no_mode_400(self, monkeypatch, body):
        r, assemble, http = _post(monkeypatch, body)
        assert r.status_code == 400
        assert r.json()["detail"] == main.CUSTOMS_MODE_REQUIRED
        assemble.assert_not_called()
        assert http.calls == []

    def test_mode_message_is_russian(self):
        assert main.CUSTOMS_MODE_REQUIRED == "Нужен либо таможенник, либо стража"
        assert main.CUSTOMS_NO_DEFENDERS == "Защитников каравана нет"
        assert main.CUSTOMS_ENFORCERS_UNAVAILABLE == "Стража недоступна"

    def test_guards_plus_escorts_over_the_cap_400(self, monkeypatch):
        r, assemble, http = _post(monkeypatch, _leader_body(
            guard_character_ids=[G1, G2], escort_character_ids=[E1, E2, 23, 24]))
        assert r.status_code == 400
        assert str(main.settings.BATTLE_MAX_TEAM_SIZE) in r.json()["detail"]
        assemble.assert_not_called()
        assert http.calls == []

    def test_cap_checked_after_escort_dedupe(self, monkeypatch):
        """Duplicated escort ids count once: 4 guards + [E1, E1] = 5 fits a team of 5."""
        ids = [G1, G2, 903, 904]
        chars = _world(c903=_npc(), c904=_npc())
        r, assemble, _ = _post(monkeypatch, _leader_body(guard_character_ids=ids,
                                                         escort_character_ids=[E1, E1]),
                               chars=chars, escorting={E1})
        assert r.status_code == 201, r.text
        assert assemble.call_args.args[2] == [0, 1, 1, 1, 1, 1]

    def test_enforcer_team_over_the_cap_400(self, monkeypatch):
        monkeypatch.setattr(main.settings, "BATTLE_MAX_TEAM_SIZE", 2)
        r, assemble, _ = _post(monkeypatch, _npc_body(enforcer_npc_ids=[N1, N2, N3],
                                                      guard_character_ids=[]),
                               escorting={E1})
        assert r.status_code == 400
        assert "2" in r.json()["detail"]
        assemble.assert_not_called()

    @pytest.mark.parametrize("enforcers,guards", [
        ([N1], [N1]), ([N1, N2], [G1, N2]), ([G1], [G1, G2]),
    ], ids=["same", "one-overlap", "guard-as-enforcer"])
    def test_id_in_both_enforcers_and_guards_400(self, monkeypatch, enforcers, guards):
        r, assemble, http = _post(monkeypatch, _npc_body(enforcer_npc_ids=enforcers,
                                                         guard_character_ids=guards),
                                  escorting={E1})
        assert r.status_code == 400
        assert r.json()["detail"] == main.CUSTOMS_ENFORCERS_UNAVAILABLE
        assemble.assert_not_called()
        assert http.calls == []


# ===========================================================================
# 3. leader (customs officer) mode
# ===========================================================================

class TestLeaderMode:
    def test_solo_creates_tagged_pve_battle_without_a_gate(self, monkeypatch):
        r, assemble, http = _post(monkeypatch, _leader_body())
        assert r.status_code == 201, r.text
        body = r.json()
        assert set(body) == {"battle_id", "participants", "next_actor", "deadline_at",
                             "attacker_character_ids", "escort_character_ids"}
        assert body["battle_id"] == 777
        assert body["next_actor"] == 31
        assert body["attacker_character_ids"] == [LEADER]
        assert body["escort_character_ids"] == []
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, G1, G2]
        assert args[2] == [main.CUSTOMS_ENFORCER_TEAM, main.CUSTOMS_CARAVAN_TEAM,
                           main.CUSTOMS_CARAVAN_TEAM]
        assert args[2] == [0, 1, 1]
        assert args[3] == "pve"
        assert args[4] == LOCATION
        assert kwargs == {"caravan_raid_id": RAID}
        # A legal action: no action gate, no outbound call at all in solo mode.
        assert http.gate_calls() == []
        assert http.calls == []

    def test_solo_works_even_if_the_gate_would_be_refused(self, monkeypatch):
        r, _, http = _post(monkeypatch, _leader_body(), http=_FakeHttp(gate=False))
        assert r.status_code == 201, r.text
        assert http.gate_calls() == []

    def test_tag_is_the_raid_id_not_the_caravan(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(caravan_raid_id=4242, caravan_id=1))
        assert r.status_code == 201
        assert assemble.call_args.kwargs["caravan_raid_id"] == 4242

    def test_group_pulls_the_free_squad_and_consumes_no_gate(self, monkeypatch):
        http = _FakeHttp(gathering=[MATE_B])
        r, assemble, _ = _post(monkeypatch, _leader_body(group=True), http=http)
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER, MATE_A]
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, MATE_A, G1, G2]
        assert args[2] == [0, 0, 1, 1]
        assert kwargs == {"caravan_raid_id": RAID}
        assert http.urls() == ["active-members", "gathering-status"]
        assert http.gate_calls() == []

    def test_group_skips_busy_and_locked_mates(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(group=True), busy={MATE_A}, locked={MATE_B})
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER]

    def test_squadmate_escort_is_filtered_out_of_the_enforcers(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(group=True, escort_character_ids=[MATE_A]))
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [LEADER, MATE_B]
        assert r.json()["escort_character_ids"] == [MATE_A]
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, MATE_B, G1, G2, MATE_A]
        assert args[2] == [0, 0, 1, 1, 1]
        assert kwargs == {"caravan_raid_id": RAID, "autobattle_forbidden_character_ids": [MATE_A]}

    def test_escort_locked_squadmate_never_enforces(self, monkeypatch):
        r, _, _ = _post(monkeypatch, _leader_body(group=True, escort_character_ids=[MATE_A]),
                        escorting={MATE_A})
        assert r.status_code == 201, r.text
        assert MATE_A not in r.json()["attacker_character_ids"]
        assert r.json()["escort_character_ids"] == [MATE_A]

    def test_escorts_join_team_1_and_are_flagged(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(escort_character_ids=[E1, E2]),
                               escorting={E1, E2})
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == [E1, E2]
        args, kwargs = assemble.call_args
        assert args[1] == [LEADER, G1, G2, E1, E2]
        assert args[2] == [0, 1, 1, 1, 1]
        assert kwargs == {"caravan_raid_id": RAID, "autobattle_forbidden_character_ids": [E1, E2]}

    def test_unavailable_escort_silently_skipped(self, monkeypatch):
        chars = _world(c21=_player(location=LOCATION + 1))
        r, assemble, _ = _post(monkeypatch, _leader_body(escort_character_ids=[E1, E2]),
                               chars=chars, escorting={E2})
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == [E2]
        assert assemble.call_args.args[1] == [LEADER, G1, G2, E2]

    def test_escorts_only_no_guards(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(guard_character_ids=[],
                                                         escort_character_ids=[E1]),
                               escorting={E1})
        assert r.status_code == 201, r.text
        assert assemble.call_args.args[1] == [LEADER, E1]
        assert assemble.call_args.args[2] == [0, 1]

    def test_no_guards_and_no_escorts_409(self, monkeypatch):
        r, assemble, http = _post(monkeypatch, _leader_body(guard_character_ids=[]))
        assert r.status_code == 409
        assert r.json()["detail"] == main.CUSTOMS_NO_DEFENDERS
        assemble.assert_not_called()
        assert http.gate_calls() == []

    def test_no_guards_and_every_escort_skipped_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(guard_character_ids=[],
                                                         escort_character_ids=[E1]),
                               busy={E1})
        assert r.status_code == 409
        assert r.json()["detail"] == main.CUSTOMS_NO_DEFENDERS
        assemble.assert_not_called()

    def test_leader_missing_404(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(), chars=_world(c1=None))
        assert r.status_code == 404
        assemble.assert_not_called()

    @pytest.mark.parametrize("loc", [LOCATION + 1, None], ids=["elsewhere", "nowhere"])
    def test_leader_not_at_the_caravan_400(self, monkeypatch, loc):
        r, assemble, _ = _post(monkeypatch, _leader_body(), chars=_world(c1=_player(location=loc)))
        assert r.status_code == 400
        assert r.json()["detail"] == main.CARAVAN_NOT_HERE
        assemble.assert_not_called()

    def test_leader_in_battle_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(), busy={LEADER})
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж уже в бою"
        assemble.assert_not_called()

    def test_leader_activity_locked_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(), locked={LEADER})
        assert r.status_code == 409
        assemble.assert_not_called()

    def test_leader_listed_as_escort_gets_the_neutral_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(escort_character_ids=[LEADER]),
                               escorting={LEADER})
        assert r.status_code == 409
        assert r.json()["detail"] == NEUTRAL_LOCK
        assert "карав" not in r.json()["detail"].lower()
        assemble.assert_not_called()

    def test_unavailable_caravan_guard_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _leader_body(), chars=_world(c902=_npc(status="dead")))
        assert r.status_code == 409
        assert r.json()["detail"] == main.CARAVAN_GUARDS_UNAVAILABLE
        assemble.assert_not_called()


# ===========================================================================
# 4. NPC-enforcer (patrol) mode
# ===========================================================================

class TestNpcEnforcerMode:
    def test_enforcers_vs_guards_and_escorts(self, monkeypatch):
        r, assemble, http = _post(monkeypatch, _npc_body(), escorting={E1})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["attacker_character_ids"] == [N1, N2]
        assert body["escort_character_ids"] == [E1]
        args, kwargs = assemble.call_args
        assert args[1] == [N1, N2, G1, E1]
        assert args[2] == [0, 0, 1, 1]
        assert args[3] == "pve"
        assert args[4] == LOCATION
        assert kwargs == {"caravan_raid_id": RAID, "autobattle_forbidden_character_ids": [E1]}
        # Never asks party / locations, never consumes a gate.
        assert http.calls == []

    def test_patrol_without_caravan_mobs(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _npc_body(guard_character_ids=[]), escorting={E1})
        assert r.status_code == 201, r.text
        assert assemble.call_args.args[1] == [N1, N2, E1]
        assert assemble.call_args.args[2] == [0, 0, 1]

    def test_group_flag_is_ignored_in_npc_mode(self, monkeypatch):
        r, _, http = _post(monkeypatch, _npc_body(group=True), escorting={E1})
        assert r.status_code == 201, r.text
        assert r.json()["attacker_character_ids"] == [N1, N2]
        assert http.calls == []

    def test_no_escorts_409_even_with_caravan_mobs(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _npc_body(escort_character_ids=[]))
        assert r.status_code == 409
        assert r.json()["detail"] == main.CUSTOMS_NO_DEFENDERS
        assemble.assert_not_called()

    @pytest.mark.parametrize("busy,locked,chars", [
        ({E1}, (), None),
        ((), {E1}, None),
        ((), (), _world(c21=_player(location=LOCATION + 1))),
        ((), (), _world(c21=None)),
        ((), (), _world(c21=_npc())),
    ], ids=["in-battle", "other-lock", "elsewhere", "missing", "npc"])
    def test_every_escort_skipped_409(self, monkeypatch, busy, locked, chars):
        r, assemble, _ = _post(monkeypatch, _npc_body(), chars=chars, busy=busy, locked=locked)
        assert r.status_code == 409
        assert r.json()["detail"] == main.CUSTOMS_NO_DEFENDERS
        assemble.assert_not_called()

    def test_escort_id_equal_to_an_enforcer_is_ignored(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _npc_body(escort_character_ids=[N1, E1]), escorting={E1})
        assert r.status_code == 201, r.text
        assert r.json()["escort_character_ids"] == [E1]
        assert assemble.call_args.args[1] == [N1, N2, G1, E1]

    def test_escort_id_equal_to_a_guard_only_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _npc_body(escort_character_ids=[G1]))
        assert r.status_code == 409
        assert r.json()["detail"] == main.CUSTOMS_NO_DEFENDERS
        assemble.assert_not_called()

    @pytest.mark.parametrize("enforcer", [
        None,
        _player(),
        _npc(status="dead"),
        _npc(unconscious=SOON),
        _npc(location=LOCATION + 1),
    ], ids=["missing", "player", "dead", "ko", "elsewhere"])
    def test_unavailable_enforcer_409(self, monkeypatch, enforcer):
        r, assemble, _ = _post(monkeypatch, _npc_body(), chars=_world(c802=enforcer), escorting={E1})
        assert r.status_code == 409
        assert r.json()["detail"] == main.CUSTOMS_ENFORCERS_UNAVAILABLE
        assemble.assert_not_called()

    def test_busy_enforcer_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _npc_body(), busy={N1}, escorting={E1})
        assert r.status_code == 409
        assert r.json()["detail"] == main.CUSTOMS_ENFORCERS_UNAVAILABLE
        assemble.assert_not_called()

    def test_duplicate_enforcer_ids_409(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _npc_body(enforcer_npc_ids=[N1, N1]), escorting={E1})
        assert r.status_code == 409
        assert r.json()["detail"] == main.CUSTOMS_ENFORCERS_UNAVAILABLE
        assemble.assert_not_called()

    def test_unavailable_caravan_mob_keeps_the_caravan_message(self, monkeypatch):
        r, assemble, _ = _post(monkeypatch, _npc_body(), chars=_world(c901=_npc(status="dead")),
                               escorting={E1})
        assert r.status_code == 409
        assert r.json()["detail"] == main.CARAVAN_GUARDS_UNAVAILABLE
        assemble.assert_not_called()
