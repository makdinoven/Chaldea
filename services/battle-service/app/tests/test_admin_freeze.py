"""FEAT-163 T10 — admin freeze / unfreeze and its interaction with the sweeper.

A freeze is the escape valve for the dropout rule: a player warns the other
side, they agree, an admin freezes the battle until they are back. It reuses the
existing pause machinery, which means the dangerous parts are the *interactions*,
not the endpoints:

* a frozen battle has no ZSET member, so the deadline sweep cannot see it — and
  ``handle_expired_turn`` refuses a stale member through the ``paused``
  precondition;
* the **reconciliation pass must skip frozen battles.** This is the one that
  would have destroyed legitimate freezes: a pause writes raw SQL, so
  ``updated_at`` is NOT bumped, and after the state TTL a week-old freeze
  matches every other condition in the SELECT. The ``AND is_paused = 0`` guard
  is load-bearing;
* the **keep-alive** re-``EXPIRE``s a frozen battle's state key, because a
  freeze is meant to last days while the key lives 48 h — and
  ``resume_battle_if_ready`` restores nothing when the state is gone;
* **unfreeze restores the remaining time, not a fresh 24 hours.** A reset would
  look like success, so the arithmetic is asserted, not just the flag.

Nothing here touches a real Redis, MySQL or Mongo (see ``_feat163_harness``).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# --- env before config/database are imported (they have no defaults) --------
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
from config import settings  # noqa: E402
from database import get_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from _feat163_harness import (  # noqa: E402
    FakeDB, FakeRedis, STATE_TTL_HOURS, ZSET_DEADLINES, deadline_epoch,
    make_participant, patch_main, seed_battle, state_key, utc_now,
)

main.app.router.on_startup.clear()  # never start the sweeper in tests

ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["battles:manage"]}
EDITOR = {"id": 2, "username": "editor", "role": "editor", "permissions": []}
PLAYER = {"id": 3, "username": "player", "role": "user", "permissions": []}


def _auth_response(user):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = user
    return resp


@pytest.fixture
def rds():
    return FakeRedis()


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def spies(monkeypatch, db, rds):
    return patch_main(monkeypatch, main, db, rds)


@pytest.fixture
def client(db):
    async def _override_get_db():
        yield db

    main.app.dependency_overrides[get_db] = _override_get_db
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def _seed_duel(db, rds, battle_id=1, hours_left=6, **kwargs):
    parts = {1: make_participant(10, team=0, hp=40),
             2: make_participant(20, team=1, hp=70)}
    seed_battle(db, rds, battle_id, parts,
                next_actor=1, deadline_at=utc_now() + timedelta(hours=hours_left),
                **kwargs)
    return parts


def _state(rds, battle_id=1):
    return json.loads(rds.kv[state_key(battle_id)])


# ===========================================================================
# (a) A paused battle is NEVER swept
# ===========================================================================
class TestFrozenBattleIsNeverSwept:

    @pytest.mark.asyncio
    async def test_freeze_removes_every_deadline_member(self, db, rds, spies):
        _seed_duel(db, rds)
        assert rds.members_for_battle(1) == ["1:1"]

        await main.pause_battle(db, 1, reason="Игрок в отъезде", by_admin=True)

        assert rds.members_for_battle(1) == []
        # …so the deadline sweep is structurally blind to it.
        assert await main._sweep_due_deadlines(db, rds) == 0

    @pytest.mark.asyncio
    async def test_a_stale_member_on_a_frozen_battle_is_a_noop(self, db, rds, spies):
        """Belt and braces: a member that survived a crash mid-pause."""
        _seed_duel(db, rds, hours_left=-2)
        await main.pause_battle(db, 1, reason="Игрок в отъезде", by_admin=True)
        # Re-arm by hand, as a crash mid-pause would leave it.
        rds.zsets.setdefault(ZSET_DEADLINES, {})["1:1"] = deadline_epoch(
            utc_now() - timedelta(hours=2))

        outcome = await main.handle_expired_turn(db, 1, 1)

        assert outcome == "paused"
        assert db.participant(1)["dropped_out_at"] is None
        assert db.battles[1]["status"] == "in_progress"
        assert db.battles[1]["is_paused"] is True

    @pytest.mark.asyncio
    async def test_freeze_stops_the_clock_and_keeps_the_remainder(self, db, rds, spies):
        _seed_duel(db, rds, hours_left=6)

        await main.pause_battle(db, 1, reason="Игрок в отъезде", by_admin=True)

        state = _state(rds)
        assert state["paused"] is True
        assert abs(state["remaining_deadline_seconds"] - 6 * 3600) < 5
        assert db.battles[1]["paused_by_admin"] is True


# ===========================================================================
# (b) The reconciliation pass skips frozen battles — the destructive case
# ===========================================================================
class TestReconciliationSkipsFrozenBattles:

    @pytest.mark.asyncio
    async def test_a_week_old_freeze_with_no_state_key_is_not_reconciled(
            self, db, rds, spies):
        """Without `AND is_paused = 0` this battle would be destroyed.

        A pause writes raw SQL, so `updated_at` is not bumped (no ORM onupdate,
        no MySQL ON UPDATE CURRENT_TIMESTAMP) — a week-old freeze matches the
        age condition, and after the state TTL its Redis key is gone too.
        """
        _seed_duel(db, rds, arm_zset=False)
        await main.pause_battle(db, 1, reason="Оба игрока согласились", by_admin=True)
        db.battles[1]["updated_at"] = utc_now() - timedelta(days=7)
        del rds.kv[state_key(1)]          # 48 h passed mid-freeze

        recovered = await main._reconcile_stale_battles(db, rds)

        assert recovered == 0
        assert db.battles[1]["status"] == "in_progress"
        assert db.battles[1]["is_paused"] is True
        assert all(p["dropped_out_at"] is None for p in db.participants)

    @pytest.mark.asyncio
    async def test_an_unfrozen_battle_in_the_same_state_is_still_reconciled(
            self, db, rds, spies):
        """The control: only the pause flag separates these two battles."""
        _seed_duel(db, rds, arm_zset=False)
        db.battles[1]["updated_at"] = utc_now() - timedelta(days=7)
        del rds.kv[state_key(1)]

        assert await main._reconcile_stale_battles(db, rds) == 1
        assert db.battles[1]["status"] == "finished"

    @pytest.mark.asyncio
    async def test_a_join_request_pause_is_also_protected(self, db, rds, spies):
        """`is_paused = 0` protects any pause, not only an admin freeze."""
        _seed_duel(db, rds, arm_zset=False)
        await main.pause_battle(db, 1)          # default: join-request pause
        db.battles[1]["updated_at"] = utc_now() - timedelta(days=7)
        del rds.kv[state_key(1)]

        assert await main._reconcile_stale_battles(db, rds) == 0
        assert db.battles[1]["status"] == "in_progress"


# ===========================================================================
# (c) The keep-alive — a freeze must outlive BATTLE_STATE_TTL_HOURS
# ===========================================================================
class TestFrozenStateKeepAlive:

    @pytest.mark.asyncio
    async def test_keep_alive_refreshes_the_state_ttl_of_a_frozen_battle(
            self, db, rds, spies):
        _seed_duel(db, rds)
        await main.pause_battle(db, 1, reason="Заморожено", by_admin=True)
        rds.ttls[state_key(1)] = 30          # nearly expired

        refreshed = await main._keep_alive_frozen_battles(db, rds)

        assert refreshed == 1
        assert rds.ttls[state_key(1)] == STATE_TTL_HOURS * 3600

    @pytest.mark.asyncio
    async def test_keep_alive_leaves_a_running_battle_alone(self, db, rds, spies):
        _seed_duel(db, rds)
        rds.ttls[state_key(1)] = 30

        assert await main._keep_alive_frozen_battles(db, rds) == 0
        assert rds.ttls[state_key(1)] == 30

    @pytest.mark.asyncio
    async def test_keep_alive_survives_a_frozen_battle_whose_key_is_already_gone(
            self, db, rds, spies):
        _seed_duel(db, rds)
        await main.pause_battle(db, 1, reason="Заморожено", by_admin=True)
        del rds.kv[state_key(1)]

        assert await main._keep_alive_frozen_battles(db, rds) == 0

    @pytest.mark.asyncio
    async def test_keep_alive_runs_on_every_tick(self, db, rds, spies):
        _seed_duel(db, rds)
        await main.pause_battle(db, 1, reason="Заморожено", by_admin=True)
        rds.ttls[state_key(1)] = 30

        stats = await main._deadline_sweeper_tick(tick=3)

        assert stats["frozen_refreshed"] == 1
        assert rds.ttls[state_key(1)] == STATE_TTL_HOURS * 3600


# ===========================================================================
# (d) Unfreeze restores the REMAINING time, not a fresh 24 h
# ===========================================================================
class TestUnfreezeRestoresRemainingTime:

    @pytest.mark.asyncio
    async def test_unfreeze_restores_the_remainder_and_not_a_fresh_window(
            self, db, rds, spies):
        _seed_duel(db, rds, hours_left=6)
        await main.pause_battle(db, 1, reason="Игрок в отъезде", by_admin=True)
        await asyncio.sleep(0)
        remaining = _state(rds)["remaining_deadline_seconds"]

        db.battles[1]["paused_by_admin"] = False       # what unfreeze does first
        resumed = await main.resume_battle_if_ready(db, 1)

        assert resumed is True
        new_deadline = main.parse_deadline(_state(rds)["deadline_at"])
        expected = utc_now() + timedelta(seconds=remaining)
        assert abs((new_deadline - expected).total_seconds()) < 5, (
            "unfreeze must restore the stored remainder"
        )
        fresh_window = utc_now() + timedelta(hours=settings.TURN_TIMEOUT_HOURS)
        assert abs((new_deadline - fresh_window).total_seconds()) > 3600, (
            "unfreeze handed out a fresh full window instead of the remainder"
        )
        # And the deadline is armed again, so the sweeper can see the battle.
        assert rds.members_for_battle(1) == ["1:1"]
        assert abs(rds.zsets[ZSET_DEADLINES]["1:1"]
                   - deadline_epoch(new_deadline)) < 1

    @pytest.mark.asyncio
    async def test_a_long_freeze_does_not_consume_the_remaining_time(
            self, db, rds, spies):
        """The clock genuinely stops: a week frozen still leaves 6 h to move."""
        _seed_duel(db, rds, hours_left=6)
        await main.pause_battle(db, 1, reason="Отпуск", by_admin=True)
        # Pretend a week passed: nothing in the state changes while paused.
        db.battles[1]["updated_at"] = utc_now() - timedelta(days=7)

        db.battles[1]["paused_by_admin"] = False
        await main.resume_battle_if_ready(db, 1)

        left = (main.parse_deadline(_state(rds)["deadline_at"]) - utc_now()).total_seconds()
        assert 6 * 3600 - 60 < left <= 6 * 3600 + 5

    @pytest.mark.asyncio
    async def test_freezing_an_already_paused_battle_keeps_the_original_remainder(
            self, db, rds, spies):
        """An admin upgrading a join-request pause must not restart the clock."""
        _seed_duel(db, rds, hours_left=6)
        await main.pause_battle(db, 1)                      # join-request pause
        first_remainder = _state(rds)["remaining_deadline_seconds"]

        await main.pause_battle(db, 1, reason="Заморожено админом", by_admin=True)

        assert _state(rds)["remaining_deadline_seconds"] == first_remainder
        assert _state(rds)["pause_reason"] == "Заморожено админом"


# ===========================================================================
# (e)/(f) An admin freeze outranks the join-request pause
# ===========================================================================
class TestAdminFreezeOutranksJoinRequests:

    @pytest.mark.asyncio
    async def test_resolving_a_join_request_does_not_lift_an_admin_freeze(
            self, db, rds, spies):
        _seed_duel(db, rds)
        await main.pause_battle(db, 1, reason="Заморожено админом", by_admin=True)
        db.join_requests_pending[1] = 0          # the request was just resolved

        resumed = await main.resume_battle_if_ready(db, 1)

        assert resumed is False
        assert db.battles[1]["is_paused"] is True
        assert db.battles[1]["paused_by_admin"] is True
        assert rds.members_for_battle(1) == []

    @pytest.mark.asyncio
    async def test_resume_still_works_for_an_ordinary_join_request_pause(
            self, db, rds, spies):
        _seed_duel(db, rds)
        await main.pause_battle(db, 1)
        db.join_requests_pending[1] = 0

        assert await main.resume_battle_if_ready(db, 1) is True
        assert db.battles[1]["is_paused"] is False

    def test_unfreeze_with_a_pending_join_request_stays_paused_and_says_so(
            self, db, rds, spies, client):
        _seed_duel(db, rds)
        db.battles[1].update(is_paused=True, paused_by_admin=True,
                             pause_reason="Заморожено")
        db.join_requests_pending[1] = 1

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/unfreeze",
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["is_paused"] is True
        assert body["reason"] == main.JOIN_REQUEST_PAUSE_REASON
        assert "заявка на присоединение" in body["message"]
        assert db.battles[1]["is_paused"] is True


# ===========================================================================
# (g) The reason reaches every render site
# ===========================================================================
class TestPauseReasonRendering:

    @pytest.mark.asyncio
    async def test_admin_reason_is_stored_in_mysql_and_mirrored_into_redis(
            self, db, rds, spies):
        _seed_duel(db, rds)

        await main.pause_battle(db, 1, reason="Игрок в отъезде до понедельника",
                                by_admin=True)

        assert db.battles[1]["pause_reason"] == "Игрок в отъезде до понедельника"
        assert _state(rds)["pause_reason"] == "Игрок в отъезде до понедельника"

    @pytest.mark.asyncio
    async def test_ws_battle_paused_payload_carries_the_reason(self, db, rds, spies):
        _seed_duel(db, rds)

        await main.pause_battle(db, 1, reason="Игрок в отъезде", by_admin=True)

        payloads = [json.loads(m) for _c, m in rds.published]
        paused = [p for p in payloads if p.get("type") == "battle_paused"]
        assert paused and paused[-1]["data"]["reason"] == "Игрок в отъезде"

    @pytest.mark.asyncio
    async def test_build_runtime_renders_the_admin_reason(self, db, rds, spies):
        _seed_duel(db, rds)
        await main.pause_battle(db, 1, reason="Игрок в отъезде", by_admin=True)

        runtime = main._build_runtime(_state(rds))

        assert runtime["is_paused"] is True
        assert runtime["paused_reason"] == "Игрок в отъезде"

    @pytest.mark.asyncio
    async def test_build_runtime_falls_back_for_a_state_without_a_reason(
            self, db, rds, spies):
        _seed_duel(db, rds)
        state = _state(rds)
        state["paused"] = True                 # pre-deploy state, no pause_reason
        assert main._build_runtime(state)["paused_reason"] == \
            main.JOIN_REQUEST_PAUSE_REASON

    @pytest.mark.asyncio
    async def test_build_runtime_reports_no_reason_while_running(self, db, rds, spies):
        _seed_duel(db, rds)
        runtime = main._build_runtime(_state(rds))
        assert runtime["is_paused"] is False
        assert runtime["paused_reason"] is None

    @pytest.mark.asyncio
    async def test_get_state_renders_the_admin_reason(self, db, rds, spies):
        _seed_duel(db, rds)
        await main.pause_battle(db, 1, reason="Игрок в отъезде", by_admin=True)

        payload = await main.get_state(1, db, SimpleNamespace(id=1010))

        assert payload["runtime"]["is_paused"] is True
        assert payload["runtime"]["paused_reason"] == "Игрок в отъезде"

    @pytest.mark.asyncio
    async def test_get_state_keeps_the_join_request_reason(self, db, rds, spies):
        _seed_duel(db, rds)
        await main.pause_battle(db, 1)

        payload = await main.get_state(1, db, SimpleNamespace(id=1010))

        assert payload["runtime"]["paused_reason"] == main.JOIN_REQUEST_PAUSE_REASON

    @pytest.mark.asyncio
    async def test_spectate_renders_the_admin_reason(self, db, rds, spies):
        _seed_duel(db, rds)
        db.character_locations[10] = 5
        await main.pause_battle(db, 1, reason="Игрок в отъезде", by_admin=True)

        payload = await main.spectate_battle(1, db, SimpleNamespace(id=1010))

        assert payload["runtime"]["paused_reason"] == "Игрок в отъезде"


# ===========================================================================
# (h)/(i) Endpoints: permissions, lookup errors and reason validation
# ===========================================================================
class TestFreezeEndpoints:

    def test_freeze_pauses_the_battle_with_the_admin_reason(self, db, rds, spies, client):
        _seed_duel(db, rds)

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/freeze",
                               json={"reason": "Оба игрока согласились"},
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"ok": True, "battle_id": 1, "is_paused": True,
                        "reason": "Оба игрока согласились", "message": "Бой заморожен"}
        assert db.battles[1]["is_paused"] is True
        assert db.battles[1]["paused_by_admin"] is True
        assert rds.members_for_battle(1) == []
        assert any(n["ws_type"] == "battle_frozen" for n in spies.notifications)

    def test_freeze_without_a_reason_uses_the_default(self, db, rds, spies, client):
        _seed_duel(db, rds)

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/freeze", json={},
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["reason"] == main.ADMIN_FREEZE_DEFAULT_REASON

    def test_freeze_with_a_blank_reason_uses_the_default(self, db, rds, spies, client):
        _seed_duel(db, rds)

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/freeze", json={"reason": "   "},
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["reason"] == main.ADMIN_FREEZE_DEFAULT_REASON

    def test_freeze_rejects_a_reason_over_255_characters(self, db, rds, spies, client):
        _seed_duel(db, rds)

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/freeze",
                               json={"reason": "я" * 256},
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code in (400, 422), resp.text
        assert db.battles[1]["is_paused"] is False

    def test_freeze_rejects_control_characters_in_the_reason(self, db, rds, spies, client):
        _seed_duel(db, rds)

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/freeze",
                               json={"reason": "плохо\x00плохо"},
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code in (400, 422), resp.text
        assert db.battles[1]["is_paused"] is False

    def test_freeze_stores_the_reason_verbatim_without_escaping(self, db, rds, spies, client):
        """It is rendered as text by the frontend, so it must survive intact."""
        _seed_duel(db, rds)
        hostile = "<script>alert('xss')</script> & 'кавычки'"

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/freeze", json={"reason": hostile},
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["reason"] == hostile
        assert db.battles[1]["pause_reason"] == hostile

    def test_freeze_404_for_a_missing_battle(self, db, rds, spies, client):
        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/999/freeze", json={},
                               headers={"Authorization": "Bearer t"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Бой не найден"

    def test_freeze_400_for_a_finished_battle(self, db, rds, spies, client):
        _seed_duel(db, rds)
        db.battles[1]["status"] = "finished"

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/freeze", json={},
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Бой уже завершён"

    @pytest.mark.parametrize("user", [EDITOR, PLAYER])
    def test_freeze_403_without_battles_manage(self, user, db, rds, spies, client):
        _seed_duel(db, rds)

        with patch("auth_http.requests.get", return_value=_auth_response(user)):
            resp = client.post("/battles/admin/1/freeze", json={},
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 403
        assert db.battles[1]["is_paused"] is False

    @pytest.mark.parametrize("user", [EDITOR, PLAYER])
    def test_unfreeze_403_without_battles_manage(self, user, db, rds, spies, client):
        _seed_duel(db, rds)
        db.battles[1]["is_paused"] = True

        with patch("auth_http.requests.get", return_value=_auth_response(user)):
            resp = client.post("/battles/admin/1/unfreeze",
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 403
        assert db.battles[1]["is_paused"] is True

    def test_freeze_401_without_a_token(self, db, rds, spies, client):
        _seed_duel(db, rds)
        resp = client.post("/battles/admin/1/freeze", json={})
        assert resp.status_code == 401

    def test_unfreeze_404_for_a_missing_battle(self, db, rds, spies, client):
        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/999/unfreeze",
                               headers={"Authorization": "Bearer t"})
        assert resp.status_code == 404

    def test_unfreeze_400_when_the_battle_is_not_paused(self, db, rds, spies, client):
        _seed_duel(db, rds)

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            resp = client.post("/battles/admin/1/unfreeze",
                               headers={"Authorization": "Bearer t"})

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Бой не приостановлен"

    def test_freeze_then_unfreeze_round_trip_restores_the_remainder(
            self, db, rds, spies, client):
        _seed_duel(db, rds, hours_left=6)

        with patch("auth_http.requests.get", return_value=_auth_response(ADMIN)):
            frozen = client.post("/battles/admin/1/freeze",
                                 json={"reason": "Игрок вернётся в понедельник"},
                                 headers={"Authorization": "Bearer t"})
            assert frozen.status_code == 200, frozen.text
            assert rds.members_for_battle(1) == []

            thawed = client.post("/battles/admin/1/unfreeze",
                                 headers={"Authorization": "Bearer t"})

        assert thawed.status_code == 200, thawed.text
        assert thawed.json()["is_paused"] is False
        assert db.battles[1]["is_paused"] is False
        assert db.battles[1]["paused_by_admin"] is False
        left = (main.parse_deadline(_state(rds)["deadline_at"]) - utc_now()).total_seconds()
        assert 6 * 3600 - 60 < left <= 6 * 3600 + 5
        assert rds.members_for_battle(1) == ["1:1"]
