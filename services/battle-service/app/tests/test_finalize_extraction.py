"""FEAT-163 T11 — regression guard for the two endings that were extracted.

Task 6 moved ~300 lines out of ``_make_action_core`` into module-level
``_finalize_battle`` and ~80 lines out of ``admin_force_finish_battle`` into
``_force_finish_battle``, so the turn-timeout sweeper could reach the *same*
endings instead of growing a parallel one. The refactor was supposed to change
nothing observable.

These tests pin the observable outcome of ``_finalize_battle`` when it is
reached the ordinary way — a killing blow, ``winner_team`` set, the loser on
``hp <= 0`` — across every consequence the inlined block used to produce, in
order: MySQL status, join-request auto-reject, resource sync, durability sync,
the final Redis save plus the 300 s expire, deadline ZSET cleanup, the
``battle_finished`` event, PvP consequences, PvE rewards, NPC death,
``battle_history``, cumulative stats, ``save_log`` and the two WS publishes.

The existing suites (``test_pvp_consequences``, ``test_pve_rewards``,
``test_battle_history``, ``test_cumulative_stats``, ``test_rewards_in_state``)
cover the action path end to end and still pass unchanged; this file covers the
extracted coroutine directly, which is what the sweeper calls.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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
import models  # noqa: E402
from schemas import BattleRewards  # noqa: E402

from _feat163_harness import (  # noqa: E402
    FakeDB, FakeRedis, ZSET_DEADLINES, deadline_epoch, make_participant,
    patch_main, seed_battle, state_key, utc_now,
)

REWARDS = BattleRewards(xp=120, gold=45, items=[])


@pytest.fixture
def rds():
    return FakeRedis()


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def spies(monkeypatch, db, rds):
    return patch_main(monkeypatch, main, db, rds, rewards=REWARDS)


def _killing_blow(db, rds, battle_type="pve", battle_id=1):
    """Participant 1 (team 0) has just been killed by participant 2 (team 1)."""
    parts = {1: make_participant(10, team=0, hp=0),
             2: make_participant(20, team=1, hp=55)}
    parts[1]["hp"] = -7                   # over-kill: must be clamped to 0
    parts[2]["equipment_durability"] = {
        "weapon": {"current_durability": 41, "max_durability": 50}}
    state = seed_battle(db, rds, battle_id, parts, next_actor=2,
                        deadline_at=utc_now() + timedelta(hours=3),
                        battle_type=battle_type)
    return state


def _state(rds, battle_id=1):
    return json.loads(rds.kv[state_key(battle_id)])


class TestFinalizeBattleFromAKillingBlow:

    @pytest.mark.asyncio
    async def test_status_history_rewards_and_cleanup(self, db, rds, spies):
        state = _killing_blow(db, rds)
        events = [{"event": "damage", "who": 2, "amount": 47}]

        rewards = await main._finalize_battle(
            db_session=db, battle_id=1, battle_state=state,
            winner_team=1, turn_events=events, turn_number=9,
        )

        # --- status -------------------------------------------------------
        assert spies.finish_battle_calls == [1]
        assert db.battles[1]["status"] == "finished"
        assert db.join_requests_rejected == [1]

        # --- rewards ------------------------------------------------------
        assert rewards == REWARDS
        assert _state(rds)["rewards"] == REWARDS.dict()

        # --- battle_history ----------------------------------------------
        assert len(db.history) == 2
        by_char = {h.character_id: h for h in db.history}
        assert by_char[20].result == models.BattleResult.victory
        assert by_char[10].result == models.BattleResult.defeat
        assert by_char[20].opponent_character_ids == [10]
        assert by_char[10].opponent_character_ids == [20]
        assert by_char[10].battle_id == 1
        assert by_char[10].character_name == "Персонаж #10"   # no snapshot → fallback

        # --- resource sync, clamped --------------------------------------
        synced = {s["cid"]: s for s in db.resource_syncs}
        assert set(synced) == {10, 20}
        assert synced[10]["hp"] == 0, "negative HP must be clamped before the DB write"

        # --- durability sync ---------------------------------------------
        spies.update_durability.assert_awaited_once()
        char_id, entries = spies.update_durability.await_args.args
        assert char_id == 20
        assert entries == [{"slot_type": "weapon", "new_durability": 41}]

        # --- Redis cleanup -------------------------------------------------
        assert rds.ttls[state_key(1)] == 300
        assert rds.zsets.get(ZSET_DEADLINES, {}) == {}

        # --- events + log --------------------------------------------------
        assert events[-1] == {"event": "battle_finished", "winner_team": 1}
        spies.save_log.delay.assert_called_once_with(1, 9, events)
        spies.track_cumulative.assert_awaited_once()
        assert spies.track_cumulative.await_args.kwargs["winner_team"] == 1
        assert spies.track_cumulative.await_args.kwargs["turn_number"] == 9

        # --- WS: final state, then the finish ------------------------------
        types = rds.published_types()
        assert types[-2:] == ["battle_state", "battle_finished"]
        finished = json.loads(rds.published[-1][1])
        assert finished["data"]["winner_team"] == 1
        assert finished["data"]["rewards"] == REWARDS.dict()

    @pytest.mark.asyncio
    async def test_runtime_in_the_final_ws_payload_marks_the_loser(self, db, rds, spies):
        state = _killing_blow(db, rds)
        state["participants"]["1"]["dropped_out"] = True

        await main._finalize_battle(
            db_session=db, battle_id=1, battle_state=state,
            winner_team=1, turn_events=[], turn_number=9,
        )

        final_state = [json.loads(m) for _c, m in rds.published
                       if json.loads(m).get("type") == "battle_state"][-1]
        runtime = final_state["data"]["runtime"]
        assert runtime["participants"]["1"]["dropped_out"] is True
        assert runtime["participants"]["2"]["dropped_out"] is False

    @pytest.mark.asyncio
    async def test_no_winner_means_no_rewards_and_no_victory_row(self, db, rds, spies):
        state = _killing_blow(db, rds)

        rewards = await main._finalize_battle(
            db_session=db, battle_id=1, battle_state=state,
            winner_team=None, turn_events=[], turn_number=9,
        )

        assert rewards is None
        spies.distribute_rewards.assert_not_awaited()
        assert all(h.result == models.BattleResult.defeat for h in db.history)
        assert db.battles[1]["status"] == "finished"

    @pytest.mark.asyncio
    async def test_pvp_training_sets_the_loser_hp_to_one(self, db, rds, spies):
        state = _killing_blow(db, rds, battle_type="pvp_training")

        await main._finalize_battle(
            db_session=db, battle_id=1, battle_state=state,
            winner_team=1, turn_events=[], turn_number=9,
        )

        assert db.pvp_training_heals == [10]

    @pytest.mark.asyncio
    async def test_pvp_death_unlinks_the_loser_and_notifies_them(self, db, rds, spies):
        state = _killing_blow(db, rds, battle_type="pvp_death")
        unlink = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))

        with patch.object(main.httpx, "AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = unlink
            await main._finalize_battle(
                db_session=db, battle_id=1, battle_state=state,
                winner_team=1, turn_events=[], turn_number=9,
            )

        unlink.assert_awaited_once()
        assert unlink.await_args.kwargs["json"] == {"character_id": 10}
        assert any(n["ws_type"] == "pvp_death_character_lost"
                   for n in spies.notifications)

    @pytest.mark.asyncio
    async def test_by_timeout_flag_changes_nothing_observable(self, db, rds, spies):
        """A timeout is a loss like any other (Architecture Decision 3.11)."""
        def _snapshot(fake_db, fake_rds):
            return {
                "status": fake_db.battles[1]["status"],
                "history": sorted((h.character_id, h.result.value) for h in fake_db.history),
                "syncs": sorted(s["cid"] for s in fake_db.resource_syncs),
                "ws": fake_rds.published_types(),
                "zset": dict(fake_rds.zsets.get(ZSET_DEADLINES, {})),
            }

        state = _killing_blow(db, rds)
        await main._finalize_battle(
            db_session=db, battle_id=1, battle_state=state,
            winner_team=1, turn_events=[], turn_number=9, by_timeout=False,
        )
        normal = _snapshot(db, rds)

        db2, rds2 = FakeDB(), FakeRedis()
        with pytest.MonkeyPatch.context() as mp:
            patch_main(mp, main, db2, rds2, rewards=REWARDS)
            state2 = _killing_blow(db2, rds2)
            await main._finalize_battle(
                db_session=db2, battle_id=1, battle_state=state2,
                winner_team=1, turn_events=[], turn_number=9, by_timeout=True,
            )
        assert _snapshot(db2, rds2) == normal


class TestForceFinishExtraction:

    @pytest.mark.asyncio
    async def test_force_finish_with_state_cleans_everything_up(self, db, rds, spies):
        state = _killing_blow(db, rds)
        rds.zsets[ZSET_DEADLINES]["1:1"] = deadline_epoch(utc_now())

        await main._force_finish_battle(db, 1, state, reason="Админ")

        assert db.battles[1]["status"] == "finished"
        assert rds.members_for_battle(1) == []
        assert state_key(1) not in rds.kv
        assert f"battle:1:snapshot" not in rds.kv
        assert ("battle:1:your_turn", "force_finished") in rds.published
        # No winner ⇒ no history, no rewards, no PvP consequences.
        assert db.history == []
        assert db.pvp_training_heals == []

    @pytest.mark.asyncio
    async def test_force_finish_without_state_enumerates_members_from_mysql(
            self, db, rds, spies):
        """The leak the brief describes: once the state key is gone, nothing
        else could ever enumerate the participants to clean the ZSET."""
        _killing_blow(db, rds)
        del rds.kv[state_key(1)]
        rds.zsets[ZSET_DEADLINES] = {
            "1:1": deadline_epoch(utc_now()),
            "1:2": deadline_epoch(utc_now()),
            "2:7": deadline_epoch(utc_now()),      # another battle: must survive
        }

        await main._force_finish_battle(db, 1, None, reason="Истёк срок")

        assert db.battles[1]["status"] == "finished"
        assert rds.members_for_battle(1) == []
        assert rds.members_for_battle(2) == ["2:7"]
        assert db.resource_syncs == [], "no state ⇒ no resources to sync"

    @pytest.mark.asyncio
    async def test_abandon_finish_stamps_everyone_and_notifies(self, db, rds, spies):
        _killing_blow(db, rds)
        del rds.kv[state_key(1)]

        await main._abandon_finish_battle(db, 1)

        assert all(p["dropped_out_at"] is not None for p in db.participants)
        assert db.battles[1]["status"] == "finished"
        messages = [n["message"] for n in spies.notifications]
        assert main.TIMEOUT_ABANDON_REASON in messages
        assert all(n["ws_type"] == "battle_force_finished" for n in spies.notifications)
