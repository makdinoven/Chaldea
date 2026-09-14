"""FEAT-163 T9 — the turn-timeout sweeper.

Background: ``TURN_TIMEOUT_HOURS`` was decorative. The deadline was written to
three places and read by none, so a battle whose player walked away stayed
``in_progress`` forever and locked BOTH participants out of movement, RP posts,
twelve inventory operations and any new battle. The sweeper is the missing
reader.

What these tests pin:

* a **backdated deadline** is swept and the participant dropped;
* a **1v1** ends with the opponent credited, ``battle_history`` written and the
  rewards payload produced;
* a **team battle** keeps going and the turn advances to the next living actor;
* the **lock is released** for the dropout — asserted by running the four real
  guard predicates (their SQL extracted from the services' own source) against
  a SQLite database built from ``models.py``, not against a hand-written mirror;
* **idempotency, one layer at a time.** The design has three independent layers
  (atomic ZREM claim, per-battle mutex, preconditions re-read inside the
  handler). A happy-path test would pass with two of them deleted, so each layer
  is exercised with the other two neutralised;
* the **reconciliation pass** recovers a wedged battle that has no ZSET member;
* a **malformed ZSET member** is removed without raising, and a handler that
  raises leaves the member behind for a later pass.

No real Redis, MySQL or Mongo is touched (see ``_feat163_harness``), so there
are no battles, keys or Mongo documents to clean up.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

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

# Heavy external clients — only mocked if nobody imported them for real yet, so
# this file behaves the same alone or inside the full suite.
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
import models  # noqa: E402
from config import settings  # noqa: E402

from _feat163_harness import (  # noqa: E402
    FakeDB, FakeRedis, STATE_TTL_HOURS, ZSET_DEADLINES, deadline_epoch,
    make_participant, make_state, patch_main, seed_battle, state_key, utc_now,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def rds():
    return FakeRedis()


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def spies(monkeypatch, db, rds):
    return patch_main(monkeypatch, main, db, rds)


PAST = -2  # hours: comfortably older than any deadline arithmetic
FUTURE = 5


def _deadline(hours_from_now):
    return utc_now() + timedelta(hours=hours_from_now)


def _duel(db, rds, battle_id=1, **kwargs):
    """1v1: participant 1 (char 10, team 0) is overdue, 2 (char 20, team 1) waits."""
    parts = {1: make_participant(10, team=0, hp=40),
             2: make_participant(20, team=1, hp=70)}
    seed_battle(db, rds, battle_id, parts, next_actor=1,
                deadline_at=_deadline(PAST), **kwargs)
    return parts


def _team_battle(db, rds, battle_id=1):
    """3v3: participant 1 (team 0) is overdue; 2 and 3 are its teammates."""
    parts = {
        1: make_participant(10, team=0, hp=40),
        2: make_participant(20, team=0, hp=55),
        3: make_participant(30, team=0, hp=60),
        4: make_participant(40, team=1, hp=80),
        5: make_participant(50, team=1, hp=80),
        6: make_participant(60, team=1, hp=80),
    }
    seed_battle(db, rds, battle_id, parts, next_actor=1, deadline_at=_deadline(PAST))
    return parts


def _state(rds, battle_id=1):
    return json.loads(rds.kv[state_key(battle_id)])


# ===========================================================================
# (a) The sweep itself
# ===========================================================================
class TestBackdatedDeadlineIsSwept:

    @pytest.mark.asyncio
    async def test_backdated_deadline_is_swept_and_participant_dropped(self, db, rds, spies):
        _duel(db, rds)
        assert rds.members_for_battle(1) == ["1:1"]

        handled = await main._sweep_due_deadlines(db, rds)

        assert handled == 1
        assert db.participant(1)["dropped_out_at"] is not None
        assert db.participant(2)["dropped_out_at"] is None
        assert rds.members_for_battle(1) == []

    @pytest.mark.asyncio
    async def test_future_deadline_is_not_swept(self, db, rds, spies):
        parts = {1: make_participant(10, team=0), 2: make_participant(20, team=1)}
        seed_battle(db, rds, 1, parts, next_actor=1, deadline_at=_deadline(FUTURE))

        handled = await main._sweep_due_deadlines(db, rds)

        assert handled == 0
        assert db.participant(1)["dropped_out_at"] is None
        assert rds.members_for_battle(1) == ["1:1"]

    @pytest.mark.asyncio
    async def test_1v1_finishes_with_opponent_credited_and_history_written(self, db, rds, spies):
        _duel(db, rds)

        outcome = await main.handle_expired_turn(db, 1, 1)

        assert outcome == "battle_finished"
        assert db.battles[1]["status"] == "finished"
        assert spies.finish_battle_calls == [1]

        # battle_history: one row per participant, the survivor wins.
        assert len(db.history) == 2
        by_char = {h.character_id: h for h in db.history}
        assert by_char[20].result == models.BattleResult.victory
        assert by_char[10].result == models.BattleResult.defeat
        # Resources synced back for both, ZSET emptied, WS told everyone.
        assert {s["cid"] for s in db.resource_syncs} == {10, 20}
        assert rds.zsets.get(ZSET_DEADLINES, {}) == {}
        assert "battle_finished" in rds.published_types()

    @pytest.mark.asyncio
    async def test_1v1_dropout_and_opponent_are_both_notified(self, db, rds, spies):
        _duel(db, rds)

        await main.handle_expired_turn(db, 1, 1)

        kinds = {n["ws_type"] for n in spies.notifications}
        assert "battle_timeout_dropout" in kinds
        assert "battle_participant_dropped" in kinds

    @pytest.mark.asyncio
    async def test_team_battle_continues_and_turn_advances_to_next_living_actor(
            self, db, rds, spies):
        _team_battle(db, rds)

        outcome = await main.handle_expired_turn(db, 1, 1)

        assert outcome == "participant_dropped"
        assert db.battles[1]["status"] == "in_progress"
        # Only the dropout is stamped — teammates are not punished.
        assert db.participant(1)["dropped_out_at"] is not None
        assert [p["id"] for p in db.participants if p["dropped_out_at"]] == [1]

        state = _state(rds)
        assert state["next_actor"] == 2
        assert state["participants"]["1"]["dropped_out"] is True
        assert state["participants"]["1"]["hp"] == 0
        assert state["turn_number"] == 4
        # The next actor is armed with a FULL fresh window.
        expected = utc_now() + timedelta(hours=settings.TURN_TIMEOUT_HOURS)
        assert abs((main.parse_deadline(state["deadline_at"]) - expected).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_team_battle_skips_dead_participants_when_advancing(self, db, rds, spies):
        parts = {
            1: make_participant(10, team=0, hp=40),
            2: make_participant(20, team=0, hp=0),      # already dead
            3: make_participant(30, team=0, hp=60),
            4: make_participant(40, team=1, hp=80),
        }
        seed_battle(db, rds, 1, parts, next_actor=1, deadline_at=_deadline(PAST))

        await main.handle_expired_turn(db, 1, 1)

        assert _state(rds)["next_actor"] == 3

    @pytest.mark.asyncio
    async def test_last_member_of_a_team_dropping_out_ends_the_battle(self, db, rds, spies):
        parts = {
            1: make_participant(10, team=0, hp=40),     # sole survivor of team 0
            2: make_participant(20, team=0, hp=0),
            3: make_participant(30, team=1, hp=80),
            4: make_participant(40, team=1, hp=70),
        }
        seed_battle(db, rds, 1, parts, next_actor=1, deadline_at=_deadline(PAST))

        outcome = await main.handle_expired_turn(db, 1, 1)

        assert outcome == "battle_finished"
        assert db.battles[1]["status"] == "finished"
        winners = {h.character_id for h in db.history
                   if h.result == models.BattleResult.victory}
        assert winners == {30, 40}

    @pytest.mark.asyncio
    async def test_zset_holds_exactly_one_member_per_battle_after_a_dropout(
            self, db, rds, spies):
        """Task-1 hygiene, from the sweeper side: no leak of the old member."""
        _team_battle(db, rds)

        await main._sweep_due_deadlines(db, rds)

        assert rds.members_for_battle(1) == ["1:2"]


# ===========================================================================
# (b) Idempotency — each layer with the other two neutralised
# ===========================================================================
class TestIdempotency:
    """Two passes must never drop the same participant twice.

    The implementation has three independent layers. A test that only walks the
    happy path would still pass with two of them deleted, so each test here
    disables the other two.
    """

    @pytest.mark.asyncio
    async def test_layer1_atomic_zrem_claim_alone_prevents_double_handling(
            self, db, rds, spies, monkeypatch):
        # Layer 2 neutralised: every call gets its own mutex key, so the mutex
        # can never collide. Layer 3 neutralised: the handler is a stub that
        # never changes state, so no precondition can ever fail.
        calls = []

        async def _stub(db_, battle_id, participant_id):
            calls.append((battle_id, participant_id))
            await asyncio.sleep(0)
            return "stub"

        counter = iter(range(1000))
        monkeypatch.setattr(main, "handle_expired_turn", _stub)
        monkeypatch.setattr(main, "_battle_timeout_lock_key",
                            lambda bid: f"unique:{bid}:{next(counter)}")
        _duel(db, rds)

        await asyncio.gather(
            main._sweep_due_deadlines(db, rds),
            main._sweep_due_deadlines(FakeDB(), rds),
        )

        assert calls == [(1, 1)], f"ZREM claim let the member through twice: {calls}"

    @pytest.mark.asyncio
    async def test_layer2_per_battle_mutex_alone_prevents_double_handling(
            self, db, rds, spies, monkeypatch):
        # Layer 1 neutralised: ZREM always reports a successful claim, so both
        # concurrent passes believe they own the member. Layer 3 neutralised:
        # the handler is a stub.
        calls = []

        async def _stub(db_, battle_id, participant_id):
            calls.append((battle_id, participant_id))
            await asyncio.sleep(0.01)
            return "stub"

        async def _always_claimed(key, member):
            rds.zsets.get(key, {}).pop(member, None)
            return 1

        monkeypatch.setattr(main, "handle_expired_turn", _stub)
        monkeypatch.setattr(rds, "zrem", _always_claimed)
        _duel(db, rds)

        await asyncio.gather(
            main._sweep_due_deadlines(db, rds),
            main._sweep_due_deadlines(FakeDB(), rds),
        )

        assert calls == [(1, 1)], f"per-battle mutex did not serialise: {calls}"

    @pytest.mark.asyncio
    async def test_layer3_preconditions_alone_prevent_a_second_drop(self, db, rds, spies):
        # Layers 1 and 2 bypassed entirely: the handler is called twice directly,
        # with no ZSET claim and no mutex in the way.
        _team_battle(db, rds)

        first = await main.handle_expired_turn(db, 1, 1)
        stamped_at = db.participant(1)["dropped_out_at"]
        history_after_first = len(db.history)

        second = await main.handle_expired_turn(db, 1, 1)

        assert first == "participant_dropped"
        assert second == "not_current_actor"
        assert db.participant(1)["dropped_out_at"] == stamped_at
        assert len(db.history) == history_after_first

    @pytest.mark.asyncio
    async def test_layer3_already_out_when_the_actor_pointer_did_not_move(
            self, db, rds, spies):
        """The narrower layer-3 guard: same actor, but already hp<=0/dropped."""
        parts = {1: make_participant(10, team=0, hp=0, dropped_out=True),
                 2: make_participant(20, team=1, hp=70)}
        seed_battle(db, rds, 1, parts, next_actor=1, deadline_at=_deadline(PAST))

        assert await main.handle_expired_turn(db, 1, 1) == "already_out"
        assert db.participant(1)["dropped_out_at"] is None
        assert db.battles[1]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_two_full_sweeps_drop_exactly_once(self, db, rds, spies):
        """End-to-end: run the sweeper twice over the same state."""
        _duel(db, rds)

        await main._sweep_due_deadlines(db, rds)
        stamped_at = db.participant(1)["dropped_out_at"]
        history_rows = len(db.history)
        finishes = list(spies.finish_battle_calls)

        # Re-arm the member by hand: a crash could have left one behind.
        rds.zsets.setdefault(ZSET_DEADLINES, {})["1:1"] = deadline_epoch(_deadline(PAST))
        await main._sweep_due_deadlines(db, rds)

        assert db.participant(1)["dropped_out_at"] == stamped_at
        assert len(db.history) == history_rows
        assert spies.finish_battle_calls == finishes


# ===========================================================================
# (f) Preconditions — each one a no-op
# ===========================================================================
class TestPreconditions:

    @pytest.mark.asyncio
    async def test_missing_battle_is_a_noop(self, db, rds, spies):
        assert await main.handle_expired_turn(db, 404, 1) == "no_battle"

    @pytest.mark.asyncio
    async def test_finished_battle_member_is_just_cleaned_up(self, db, rds, spies):
        _duel(db, rds)
        db.battles[1]["status"] = "finished"

        assert await main.handle_expired_turn(db, 1, 1) == "not_in_progress"
        assert db.participant(1)["dropped_out_at"] is None

    @pytest.mark.asyncio
    async def test_paused_battle_is_never_dropped(self, db, rds, spies):
        _duel(db, rds)
        db.battles[1]["is_paused"] = True
        state = _state(rds)
        state["paused"] = True
        rds.kv[state_key(1)] = json.dumps(state)

        assert await main.handle_expired_turn(db, 1, 1) == "paused"
        assert db.participant(1)["dropped_out_at"] is None
        assert db.battles[1]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_stale_member_whose_actor_moved_on_is_a_noop(self, db, rds, spies):
        _duel(db, rds)
        state = _state(rds)
        state["next_actor"] = 2
        rds.kv[state_key(1)] = json.dumps(state)

        assert await main.handle_expired_turn(db, 1, 1) == "not_current_actor"
        assert db.participant(1)["dropped_out_at"] is None

    @pytest.mark.asyncio
    async def test_deadline_not_actually_past_is_a_noop(self, db, rds, spies):
        """The authoritative state outranks a stale ZSET score."""
        parts = {1: make_participant(10, team=0), 2: make_participant(20, team=1)}
        seed_battle(db, rds, 1, parts, next_actor=1, deadline_at=_deadline(FUTURE))
        # A stale/backdated score in the ZSET must not be enough on its own.
        rds.zsets[ZSET_DEADLINES]["1:1"] = deadline_epoch(_deadline(PAST))

        assert await main.handle_expired_turn(db, 1, 1) == "deadline_not_passed"
        assert db.participant(1)["dropped_out_at"] is None

    @pytest.mark.asyncio
    async def test_legacy_moscow_offset_deadline_is_still_understood(self, db, rds, spies):
        """Pre-FEAT-161 states carry a +03:00 string; it must still expire."""
        parts = {1: make_participant(10, team=0), 2: make_participant(20, team=1)}
        seed_battle(db, rds, 1, parts, next_actor=1, deadline_at=_deadline(PAST))
        state = _state(rds)
        legacy = (utc_now() - timedelta(hours=2)).replace(microsecond=0)
        state["deadline_at"] = (legacy + timedelta(hours=3)).isoformat() + "+03:00"
        rds.kv[state_key(1)] = json.dumps(state)

        assert await main.handle_expired_turn(db, 1, 1) == "battle_finished"

    @pytest.mark.asyncio
    async def test_unknown_participant_is_a_noop(self, db, rds, spies):
        _duel(db, rds)
        assert await main.handle_expired_turn(db, 1, 999) == "unknown_participant"


# ===========================================================================
# (g) Redis state expired while the row is still in_progress
# ===========================================================================
class TestExpiredState:

    @pytest.mark.asyncio
    async def test_expired_state_abandon_finishes_and_clears_members_from_mysql(
            self, db, rds, spies):
        _duel(db, rds)
        # 48h passed: the state key is gone, but the ZSET member survives.
        del rds.kv[state_key(1)]

        outcome = await main.handle_expired_turn(db, 1, 1)

        assert outcome == "abandoned"
        assert db.battles[1]["status"] == "finished"
        # Participants enumerated from MySQL — this is what finally closes the leak.
        assert rds.members_for_battle(1) == []
        assert all(p["dropped_out_at"] is not None for p in db.participants)
        assert any(n["ws_type"] == "battle_force_finished" for n in spies.notifications)

    @pytest.mark.asyncio
    async def test_abandon_finish_removes_a_member_for_a_participant_not_in_the_zset(
            self, db, rds, spies):
        _duel(db, rds)
        del rds.kv[state_key(1)]
        # Both members present (e.g. left over from a crash mid-turn).
        rds.zsets[ZSET_DEADLINES]["1:2"] = deadline_epoch(_deadline(PAST))

        await main.handle_expired_turn(db, 1, 1)

        assert rds.members_for_battle(1) == []


# ===========================================================================
# (h) Reconciliation — battles with NO ZSET member at all
# ===========================================================================
class TestReconciliation:

    @pytest.mark.asyncio
    async def test_reconciliation_recovers_a_wedged_battle_with_no_zset_member(
            self, db, rds, spies):
        _duel(db, rds, arm_zset=False)
        del rds.kv[state_key(1)]
        db.battles[1]["updated_at"] = utc_now() - timedelta(hours=STATE_TTL_HOURS + 5)

        recovered = await main._reconcile_stale_battles(db, rds)

        assert recovered == 1
        assert db.battles[1]["status"] == "finished"
        assert all(p["dropped_out_at"] is not None for p in db.participants)

    @pytest.mark.asyncio
    async def test_reconciliation_leaves_a_battle_whose_state_key_still_exists(
            self, db, rds, spies):
        _duel(db, rds, arm_zset=False)
        db.battles[1]["updated_at"] = utc_now() - timedelta(hours=STATE_TTL_HOURS + 5)
        # State key present → quiet, but alive. Two guards, not one.

        assert await main._reconcile_stale_battles(db, rds) == 0
        assert db.battles[1]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_reconciliation_leaves_a_young_battle_alone(self, db, rds, spies):
        _duel(db, rds, arm_zset=False)
        del rds.kv[state_key(1)]
        db.battles[1]["updated_at"] = utc_now() - timedelta(hours=1)

        assert await main._reconcile_stale_battles(db, rds) == 0
        assert db.battles[1]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_reconciliation_runs_only_every_nth_tick(self, db, rds, spies, monkeypatch):
        _duel(db, rds, arm_zset=False)
        del rds.kv[state_key(1)]
        db.battles[1]["updated_at"] = utc_now() - timedelta(hours=STATE_TTL_HOURS + 5)
        monkeypatch.setattr(settings, "BATTLE_TIMEOUT_RECONCILE_EVERY", 60)

        stats = await main._deadline_sweeper_tick(tick=7)
        assert "reconciled" not in stats
        assert db.battles[1]["status"] == "in_progress"

        rds.kv.pop(main.SWEEPER_LEASE_KEY, None)
        stats = await main._deadline_sweeper_tick(tick=60)
        assert stats["reconciled"] == 1
        assert db.battles[1]["status"] == "finished"


# ===========================================================================
# (k) Robustness — a corrupt member or a raising handler must not kill the loop
# ===========================================================================
class TestRobustness:

    @pytest.mark.asyncio
    async def test_malformed_zset_member_is_removed_without_raising(self, db, rds, spies):
        zset = rds.zsets.setdefault(ZSET_DEADLINES, {})
        past = deadline_epoch(_deadline(PAST))
        for junk in ("garbage", "1:abc", "abc:1", "", ":", "7"):
            zset[junk] = past

        handled = await main._sweep_due_deadlines(db, rds)

        assert handled == 0
        assert rds.zsets.get(ZSET_DEADLINES, {}) == {}

    @pytest.mark.asyncio
    async def test_a_malformed_member_does_not_stop_a_valid_one(self, db, rds, spies):
        _duel(db, rds)
        rds.zsets[ZSET_DEADLINES]["garbage"] = deadline_epoch(_deadline(PAST)) - 100

        handled = await main._sweep_due_deadlines(db, rds)

        assert handled == 1
        assert db.participant(1)["dropped_out_at"] is not None

    @pytest.mark.asyncio
    async def test_handler_exception_leaves_the_member_for_a_later_pass(
            self, db, rds, spies, monkeypatch):
        _duel(db, rds)
        original_score = rds.zsets[ZSET_DEADLINES]["1:1"]

        async def _boom(*_a, **_kw):
            raise RuntimeError("engine exploded")

        monkeypatch.setattr(main, "handle_expired_turn", _boom)

        await main._sweep_due_deadlines(db, rds)  # must not raise

        assert rds.zsets[ZSET_DEADLINES]["1:1"] == original_score
        assert db.rollbacks >= 1
        # And the per-battle mutex was released, so the retry is not blocked.
        assert main._battle_timeout_lock_key(1) not in rds.kv

    @pytest.mark.asyncio
    async def test_loop_survives_a_failing_tick(self, db, rds, spies, monkeypatch):
        calls = []

        async def _flaky(tick):
            calls.append(tick)
            raise RuntimeError("tick exploded")

        monkeypatch.setattr(main, "_deadline_sweeper_tick", _flaky)
        monkeypatch.setattr(settings, "BATTLE_TIMEOUT_SWEEP_INTERVAL_SECONDS", 1)

        real_sleep = asyncio.sleep

        async def _fast_sleep(_seconds):
            await real_sleep(0)

        monkeypatch.setattr(main.asyncio, "sleep", _fast_sleep)

        task = asyncio.ensure_future(main._deadline_sweeper_loop())
        for _ in range(20):
            await real_sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(calls) > 1, "the loop died on the first failing tick"

    @pytest.mark.asyncio
    async def test_advisory_lease_stops_a_second_replica_doing_the_same_work(
            self, db, rds, spies):
        _duel(db, rds)
        rds.kv[main.SWEEPER_LEASE_KEY] = "some-other-instance"

        stats = await main._deadline_sweeper_tick(tick=1)

        assert stats == {"skipped": 1}
        assert db.participant(1)["dropped_out_at"] is None

    @pytest.mark.asyncio
    async def test_tick_sweeps_when_it_owns_the_lease(self, db, rds, spies):
        _duel(db, rds)

        stats = await main._deadline_sweeper_tick(tick=1)

        assert stats["deadlines"] == 1
        assert db.participant(1)["dropped_out_at"] is not None

    def test_kill_switch_starts_no_task(self, monkeypatch):
        monkeypatch.setattr(settings, "BATTLE_TIMEOUT_SWEEPER_ENABLED", 0)
        created = []
        monkeypatch.setattr(main.asyncio, "create_task",
                            lambda coro: created.append(coro))

        asyncio.new_event_loop().run_until_complete(main.startup_deadline_sweeper())

        assert created == []


# ===========================================================================
# (j) Lock release — the four REAL guard predicates
# ===========================================================================
#
# Releasing the lock is the entire point of the feature, so this is asserted
# against the genuine SQL: each guard's statement is pulled out of its own
# service source with ``ast`` (the adjacent string literals are concatenated by
# the parser, so the call's first argument is a single constant) and executed
# against a SQLite database whose two tables are created from battle-service's
# ``models.py`` — not from a hand-written mirror of the schema.
# ---------------------------------------------------------------------------
SERVICES_DIR = os.path.abspath(os.path.join(APP_DIR, "..", ".."))

GUARDS = {
    "battle-service.get_active_battle_for_character": (
        os.path.join(APP_DIR, "crud.py"), "get_active_battle_for_character"),
    "locations-service.check_not_in_battle": (
        os.path.join(SERVICES_DIR, "locations-service", "app", "main.py"),
        "check_not_in_battle"),
    "character-service._is_in_battle": (
        os.path.join(SERVICES_DIR, "character-service", "app", "main.py"),
        "_is_in_battle"),
    "inventory-service.is_character_in_battle": (
        os.path.join(SERVICES_DIR, "inventory-service", "app", "crud.py"),
        "is_character_in_battle"),
}


def _extract_guard_sql(path, func_name):
    """Pull the literal SQL out of ``text(...)`` inside the named function."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                fn = sub.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                if name == "text" and sub.args and isinstance(sub.args[0], ast.Constant):
                    return sub.args[0].value
    raise AssertionError(f"no text(...) SQL found in {func_name} ({path})")


@pytest.fixture
def guard_engine():
    """SQLite built from the real battle-service models (schema, not a mirror)."""
    from sqlalchemy import create_engine, text as sa_text

    engine = create_engine("sqlite://")
    models.Battle.__table__.create(engine)
    models.BattleParticipant.__table__.create(engine)
    now = datetime.utcnow()
    with engine.begin() as conn:
        conn.execute(sa_text(
            "INSERT INTO battles (id, status, battle_type, created_at, updated_at,"
            " location_id, is_paused, pause_reason, paused_by_admin)"
            " VALUES (1, 'in_progress', 'pve', :t, :t, NULL, 0, NULL, 0)"
        ), {"t": now})
        conn.execute(sa_text(
            "INSERT INTO battle_participants (id, battle_id, character_id, team,"
            " dropped_out_at) VALUES (1, 1, 10, 0, NULL)"
        ))
        conn.execute(sa_text(
            "INSERT INTO battle_participants (id, battle_id, character_id, team,"
            " dropped_out_at) VALUES (2, 1, 20, 1, :d)"
        ), {"d": now})
    yield engine
    engine.dispose()


class TestLockRelease:

    def test_all_four_guards_are_findable(self):
        missing = [name for name, (path, _) in GUARDS.items() if not os.path.exists(path)]
        if missing:
            pytest.skip(
                "sibling services are not on this filesystem "
                f"(battle-service runs from a container mount): {missing}"
            )
        for name, (path, func) in GUARDS.items():
            assert "dropped_out_at" in _extract_guard_sql(path, func), name

    @pytest.mark.parametrize("guard_name", sorted(GUARDS))
    def test_guard_releases_the_lock_for_a_dropped_out_participant(
            self, guard_name, guard_engine):
        from sqlalchemy import text as sa_text

        path, func = GUARDS[guard_name]
        if not os.path.exists(path):
            pytest.skip(f"{guard_name}: source not available on this filesystem")
        sql = _extract_guard_sql(path, func)

        with guard_engine.connect() as conn:
            still_locked = conn.execute(sa_text(sql), {"cid": 10}).fetchone()
            released = conn.execute(sa_text(sql), {"cid": 20}).fetchone()

        assert still_locked is not None, f"{guard_name} stopped locking a live participant"
        assert released is None, f"{guard_name} still locks a dropped-out participant"

    def test_dropped_out_participant_of_a_finished_battle_is_also_free(self, guard_engine):
        """Sanity: the 1v1 path releases via status alone, as designed."""
        from sqlalchemy import text as sa_text

        path, func = GUARDS["battle-service.get_active_battle_for_character"]
        sql = _extract_guard_sql(path, func)
        with guard_engine.begin() as conn:
            conn.execute(sa_text("UPDATE battles SET status = 'finished' WHERE id = 1"))
        with guard_engine.connect() as conn:
            assert conn.execute(sa_text(sql), {"cid": 10}).fetchone() is None


# ===========================================================================
# (i) ZSET hygiene on a normal turn advance (FEAT-163 task 1)
# ===========================================================================
class TestZsetHygieneOnTurnAdvance:
    """`_make_action_core` must ZREM the previous actor before arming the next.

    Structural rather than behavioural: `_make_action_core` is ~400 lines of
    engine wiring, and the observable effect of the missing ZREM (a ZSET that
    grows forever) only appears across many turns of a real battle. The
    functional side of the same rule is covered above by
    ``test_zset_holds_exactly_one_member_per_battle_after_a_dropout``.
    """

    def test_previous_actor_is_removed_before_the_next_is_armed(self):
        with open(os.path.join(APP_DIR, "main.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        func = next(n for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == "_make_action_core")

        zrems, zadds = [], []
        for node in ast.walk(func):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "zrem" and node.args:
                zrems.append((node.lineno, ast.dump(node)))
            elif node.func.attr == "zadd" and node.args:
                zadds.append(node.lineno)

        assert zadds, "_make_action_core no longer arms a deadline"
        prev_actor_zrems = [ln for ln, dumped in zrems
                            if "participant_id" in dumped and "request" in dumped]
        assert prev_actor_zrems, (
            "_make_action_core never removes the acting participant's deadline "
            "member — battle:deadlines will leak one member per turn"
        )
        assert min(prev_actor_zrems) < max(zadds), (
            "the previous actor's ZREM must come before the next actor's ZADD"
        )
