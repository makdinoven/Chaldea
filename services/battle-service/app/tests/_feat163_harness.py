"""Shared test harness for FEAT-163 (turn-timeout sweeper + admin freeze).

Why a harness instead of plain ``MagicMock``s: the behaviour under test is
*stateful* — an atomic ZSET claim, a per-battle mutex, preconditions re-read
from Redis, a MySQL pass whose WHERE clause is load-bearing. A mock that
returns a canned value cannot tell a correct implementation from a broken one,
so this module provides two small in-memory doubles that actually implement the
semantics the production code relies on:

* :class:`FakeRedis` — real ZSET/keyspace semantics, including ``ZREM``
  returning the number of members it actually removed (idempotency layer 1) and
  ``SET NX`` returning ``None`` when the key exists (layer 2). ``zrangebyscore``
  deliberately snapshots the matching members *before* yielding to the event
  loop, so two concurrent sweeps genuinely race over the same member.
* :class:`FakeDB` — a tiny table store whose ``execute`` *interprets* the WHERE
  clause of the statements this feature issues (``is_paused = 0``,
  ``is_paused = 1``, ``updated_at < …``, ``dropped_out_at IS NULL``) instead of
  pattern-matching whole strings. Deleting ``AND is_paused = 0`` from the
  reconciliation SELECT therefore changes what comes back, which is what makes
  the freeze-safety test bite.

The table shapes here mirror ``models.Battle`` / ``models.BattleParticipant``,
which were verified against the live MySQL schema (``SHOW COLUMNS``) on
2026-09-14: ``battles(id, status, created_at, updated_at, battle_type,
location_id, is_paused, pause_reason, paused_by_admin)`` and
``battle_participants(id, battle_id, character_id, team, dropped_out_at)``.

Nothing here touches a real Redis, MySQL or Mongo, so there is nothing to clean
up after a run.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# ---------------------------------------------------------------------------
# The REAL redis_state helpers.
#
# Other test files in this suite replace ``redis_state`` in ``sys.modules`` with
# a MagicMock before importing ``main``, so ``main.utc_now`` / ``parse_deadline``
# / ``deadline_epoch`` / ``state_key`` / ``STATE_TTL_HOURS`` may already be
# MagicMock attributes by the time these tests are collected. Load the real
# module from disk under a private name — this does NOT touch ``sys.modules``
# and so cannot disturb any other test file — and bind the genuine helpers into
# ``main`` for the duration of each test.
# ---------------------------------------------------------------------------
_spec = importlib.util.spec_from_file_location(
    "_real_redis_state_for_feat163", os.path.join(APP_DIR, "redis_state.py")
)
real_redis_state = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(real_redis_state)

utc_now = real_redis_state.utc_now
parse_deadline = real_redis_state.parse_deadline
deadline_epoch = real_redis_state.deadline_epoch
state_key = real_redis_state.state_key
STATE_TTL_HOURS = real_redis_state.STATE_TTL_HOURS
ZSET_DEADLINES = real_redis_state.ZSET_DEADLINES

assert ZSET_DEADLINES == "battle:deadlines"


# ===========================================================================
# FakeRedis
# ===========================================================================
class FakeRedis:
    """In-memory Redis double with the semantics this feature depends on."""

    def __init__(self) -> None:
        self.kv: Dict[str, str] = {}
        self.ttls: Dict[str, int] = {}
        self.zsets: Dict[str, Dict[str, float]] = {}
        self.published: List[tuple] = []

    # --- strings ----------------------------------------------------------
    async def set(self, key, value, nx: bool = False, ex: Optional[int] = None):
        # No await before the check: SET NX must be atomic w.r.t. the loop.
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key):
        return self.kv.get(key)

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if self.kv.pop(key, None) is not None:
                removed += 1
            self.ttls.pop(key, None)
        return removed

    async def exists(self, key):
        return 1 if key in self.kv else 0

    async def expire(self, key, ttl):
        if key not in self.kv:
            return False
        self.ttls[key] = ttl
        return True

    async def ttl(self, key):
        if key not in self.kv:
            return -2
        return self.ttls.get(key, -1)

    # --- sorted sets ------------------------------------------------------
    async def zadd(self, key, mapping):
        zset = self.zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in zset:
                added += 1
            zset[member] = float(score)
        return added

    async def zrem(self, key, member):
        # Atomic on purpose: no await inside. This is idempotency layer 1 —
        # of any number of concurrent callers exactly one gets 1.
        zset = self.zsets.get(key, {})
        return 1 if zset.pop(member, None) is not None else 0

    async def zscore(self, key, member):
        return self.zsets.get(key, {}).get(member)

    async def zcard(self, key):
        return len(self.zsets.get(key, {}))

    async def zrange(self, key, start, end, withscores: bool = False):
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        sliced = items[start: (None if end == -1 else end + 1)]
        return sliced if withscores else [m for m, _ in sliced]

    async def zrangebyscore(self, key, min, max, start=0, num=None, withscores=False):
        lo = float("-inf") if min in ("-inf", "-INF") else float(min)
        hi = float("inf") if max in ("+inf", "inf") else float(max)
        items = sorted(
            ((m, s) for m, s in self.zsets.get(key, {}).items() if lo <= s <= hi),
            key=lambda kv: kv[1],
        )
        if num is not None:
            items = items[start:start + num]
        # Snapshot BEFORE yielding: two concurrent sweeps must both see the
        # member and then race on the ZREM claim, which is the point.
        await asyncio.sleep(0)
        return items if withscores else [m for m, _ in items]

    # --- pub/sub ----------------------------------------------------------
    async def publish(self, channel, message):
        self.published.append((channel, message))
        return 1

    # --- test helpers -----------------------------------------------------
    def members_for_battle(self, battle_id: int) -> List[str]:
        prefix = f"{battle_id}:"
        return [m for m in self.zsets.get(ZSET_DEADLINES, {}) if m.startswith(prefix)]

    def published_types(self) -> List[str]:
        types = []
        for _channel, message in self.published:
            try:
                types.append(json.loads(message).get("type"))
            except (ValueError, TypeError):
                types.append(message)
        return types


# ===========================================================================
# FakeDB
# ===========================================================================
class FakeResult:
    def __init__(self, rows=None, rowcount=0, scalar=None):
        self._rows = list(rows or [])
        self.rowcount = rowcount
        self._scalar = scalar

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", str(sql)).strip().lower()


class FakeDB:
    """Minimal async-session double that interprets the SQL this feature runs."""

    def __init__(self) -> None:
        self.battles: Dict[int, Dict[str, Any]] = {}
        self.participants: List[Dict[str, Any]] = []
        self.characters: Dict[int, Dict[str, Any]] = {}
        self.join_requests_pending: Dict[int, int] = {}
        self.history: List[Any] = []
        self.resource_syncs: List[Dict[str, Any]] = []
        self.pvp_training_heals: List[int] = []
        # FEAT-164: character ids whose regen_anchor_at was reset by a sync,
        # and a switch simulating character-attributes-service before
        # migration 008 (the column does not exist yet).
        self.anchor_resets: List[int] = []
        self.missing_anchor_column = False
        self.join_requests_rejected: List[int] = []
        self.character_locations: Dict[int, Optional[int]] = {}
        self.sql_log: List[str] = []
        self.commits = 0
        self.rollbacks = 0
        self.now = utc_now()

    # --- seeding ----------------------------------------------------------
    def add_battle(self, battle_id, status="in_progress", battle_type="pve",
                   is_paused=False, paused_by_admin=False, pause_reason=None,
                   updated_at=None, location_id=5):
        self.battles[battle_id] = {
            "id": battle_id,
            "status": status,
            "battle_type": battle_type,
            "is_paused": bool(is_paused),
            "paused_by_admin": bool(paused_by_admin),
            "pause_reason": pause_reason,
            "updated_at": updated_at or self.now,
            "location_id": location_id,
        }
        return self.battles[battle_id]

    def add_participant(self, participant_id, battle_id, character_id, team=0,
                        dropped_out_at=None, name=None, user_id=None, is_npc=False):
        self.participants.append({
            "id": participant_id,
            "battle_id": battle_id,
            "character_id": character_id,
            "team": team,
            "dropped_out_at": dropped_out_at,
        })
        self.characters[character_id] = {
            "id": character_id,
            "user_id": user_id if user_id is not None else (None if is_npc else 1000 + character_id),
            "is_npc": bool(is_npc),
            "name": name or f"Герой {character_id}",
        }

    def participant(self, participant_id):
        for p in self.participants:
            if p["id"] == participant_id:
                return p
        return None

    # --- session API ------------------------------------------------------
    def add(self, obj):
        self.history.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def flush(self):
        return None

    async def refresh(self, obj):
        return None

    async def execute(self, stmt, params=None):
        q = _norm(stmt)
        params = params or {}
        self.sql_log.append(q)
        return self._dispatch(q, params)

    # --- dispatch ---------------------------------------------------------
    def _dispatch(self, q, p):  # noqa: C901 — a router, flat by nature
        # battle_participants: dropped_out_at stamping
        if q.startswith("update battle_participants set dropped_out_at"):
            touched = 0
            for row in self.participants:
                if row["battle_id"] != p.get("bid"):
                    continue
                if "and id = :pid" in q and row["id"] != p.get("pid"):
                    continue
                if "dropped_out_at is null" in q and row["dropped_out_at"] is not None:
                    continue
                row["dropped_out_at"] = self.now
                touched += 1
            return FakeResult(rowcount=touched)

        # pause / resume / unfreeze writes
        if q.startswith("update battles set is_paused = 1"):
            b = self.battles.get(p.get("bid"))
            if b:
                b["is_paused"] = True
                b["pause_reason"] = p.get("reason")
                b["paused_by_admin"] = bool(p.get("by_admin"))
            return FakeResult(rowcount=1 if b else 0)

        if q.startswith("update battles set is_paused = 0"):
            b = self.battles.get(p.get("bid"))
            if b:
                b["is_paused"] = False
                b["pause_reason"] = None
                b["paused_by_admin"] = False
            return FakeResult(rowcount=1 if b else 0)

        if q.startswith("update battles set paused_by_admin = 0"):
            b = self.battles.get(p.get("bid"))
            if b:
                b["paused_by_admin"] = False
            return FakeResult(rowcount=1 if b else 0)

        if q.startswith("select paused_by_admin from battles"):
            b = self.battles.get(p.get("bid"))
            return FakeResult([(1 if b and b["paused_by_admin"] else 0,)] if b else [])

        # join requests
        if "count(*) from battle_join_requests" in q:
            return FakeResult(scalar=self.join_requests_pending.get(p.get("bid"), 0))

        if q.startswith("update battle_join_requests"):
            self.join_requests_rejected.append(p.get("bid"))
            self.join_requests_pending[p.get("bid")] = 0
            return FakeResult(rowcount=1)

        # resource / pvp-training sync
        if q.startswith("update character_attributes") and "regen_anchor_at" in q:
            if self.missing_anchor_column:
                raise RuntimeError(
                    "(pymysql.err.OperationalError) (1054, \"Unknown column "
                    "'regen_anchor_at' in 'field list'\")"
                )
            if "regen_anchor_at = utc_timestamp()" in q:
                self.anchor_resets.append(p.get("cid"))

        if q.startswith("update character_attributes set current_health = 1"):
            self.pvp_training_heals.append(p.get("cid"))
            return FakeResult(rowcount=1)

        if q.startswith("update character_attributes set current_health"):
            self.resource_syncs.append(dict(p))
            return FakeResult(rowcount=1)

        # scalar look-ups
        if q.startswith("select battle_type from battles"):
            b = self.battles.get(p.get("bid"))
            return FakeResult([(b["battle_type"],)] if b else [])

        if q.startswith("select user_id from characters"):
            c = self.characters.get(p.get("cid"))
            return FakeResult([(c["user_id"],)] if c else [])

        if q.startswith("select id, current_location_id from characters"):
            return FakeResult([
                (c["id"], self.character_locations.get(c["id"], 5))
                for c in self.characters.values()
                if c["user_id"] == p.get("uid")
            ])

        if q.startswith("select name from characters"):
            c = self.characters.get(p.get("cid"))
            return FakeResult([(c["name"],)] if c else [])

        if q.startswith("select is_npc, npc_role from characters"):
            c = self.characters.get(p.get("cid"))
            if c and c["is_npc"]:
                return FakeResult([(1, None)])
            return FakeResult([])

        # participant enumeration (force-finish, state gone)
        if q.startswith("select id from battle_participants where battle_id"):
            return FakeResult([(r["id"],) for r in self.participants
                               if r["battle_id"] == p.get("bid")])

        # notification enumerations
        if q.startswith("select distinct c.user_id from battle_participants"):
            seen, rows = set(), []
            for r in self.participants:
                if r["battle_id"] != p.get("bid"):
                    continue
                c = self.characters.get(r["character_id"], {})
                if c.get("is_npc"):
                    continue
                if c.get("user_id") in seen:
                    continue
                seen.add(c.get("user_id"))
                rows.append((c.get("user_id"),))
            return FakeResult(rows)

        if q.startswith("select c.id, c.user_id from battle_participants"):
            rows = []
            for r in self.participants:
                if r["battle_id"] != p.get("bid"):
                    continue
                c = self.characters.get(r["character_id"], {})
                if c.get("is_npc") or c.get("user_id") is None:
                    continue
                rows.append((c["id"], c["user_id"]))
            return FakeResult(rows)

        # --- the two sweeper passes: WHERE clause is INTERPRETED ----------
        if q.startswith("select id from battles where"):
            rows = []
            for b in self.battles.values():
                if "status = 'in_progress'" in q and b["status"] != "in_progress":
                    continue
                if "is_paused = 0" in q and b["is_paused"]:
                    continue
                if "is_paused = 1" in q and not b["is_paused"]:
                    continue
                if "updated_at <" in q:
                    ttl_hours = int(p.get("ttl", STATE_TTL_HOURS))
                    if b["updated_at"] >= self.now - timedelta(hours=ttl_hours):
                        continue
                rows.append((b["id"],))
            return FakeResult(rows)

        return FakeResult()


# ===========================================================================
# Battle-state builders
# ===========================================================================
def make_participant(character_id, team=0, hp=100, dropped_out=False):
    return {
        "character_id": character_id,
        "team": team,
        "hp": hp,
        "mana": 50,
        "energy": 100,
        "stamina": 90,
        "max_hp": 100,
        "max_mana": 60,
        "max_energy": 100,
        "max_stamina": 100,
        "cooldowns": {},
        "fast_slots": [],
        "equipment_durability": {},
        "dropped_out": dropped_out,
    }


def make_state(participants: Dict[int, Dict], next_actor: int,
               deadline_at: datetime, turn_number: int = 3,
               paused: bool = False, pause_reason=None,
               remaining_deadline_seconds=None) -> Dict:
    turn_order = sorted(participants)
    state = {
        "turn_number": turn_number,
        "deadline_at": deadline_at.isoformat(),
        "next_actor": next_actor,
        "first_actor": turn_order[0],
        "turn_order": turn_order,
        "total_turns": turn_number,
        "last_turn": turn_number - 1,
        "first_cycle": False,
        "participants": {str(pid): data for pid, data in participants.items()},
        "active_effects": {},
        "paused": paused,
    }
    if pause_reason is not None:
        state["pause_reason"] = pause_reason
    if remaining_deadline_seconds is not None:
        state["remaining_deadline_seconds"] = remaining_deadline_seconds
    return state


def seed_battle(db: FakeDB, rds: FakeRedis, battle_id: int,
                participants: Dict[int, Dict], next_actor: int,
                deadline_at: datetime, battle_type="pve", arm_zset=True,
                **battle_kwargs) -> Dict:
    """Seed MySQL rows, the Redis state key and the deadline ZSET together."""
    db.add_battle(battle_id, battle_type=battle_type, **battle_kwargs)
    for pid, data in participants.items():
        db.add_participant(pid, battle_id, data["character_id"], team=data["team"])
    state = make_state(participants, next_actor, deadline_at)
    rds.kv[state_key(battle_id)] = json.dumps(state)
    rds.ttls[state_key(battle_id)] = STATE_TTL_HOURS * 3600
    if arm_zset:
        rds.zsets.setdefault(ZSET_DEADLINES, {})[f"{battle_id}:{next_actor}"] = \
            deadline_epoch(deadline_at)
    return state


# ===========================================================================
# main patching
# ===========================================================================
def make_battle_row(db: FakeDB, battle_id: int):
    """Battle row double carrying the REAL enums, so both `.status.value` and
    `status in (BattleStatus.pending, …)` behave as they do in production."""
    import models

    b = db.battles.get(battle_id)
    if b is None:
        return None
    return SimpleNamespace(
        id=b["id"],
        status=models.BattleStatus(b["status"]),
        battle_type=models.BattleType(b["battle_type"]),
        location_id=b.get("location_id"),
        is_paused=b["is_paused"],
        pause_reason=b["pause_reason"],
        paused_by_admin=b["paused_by_admin"],
        created_at=db.now,
        updated_at=b["updated_at"],
    )


def patch_main(monkeypatch, main, db: FakeDB, rds: FakeRedis, *,
               rewards=None, cumulative=None):
    """Bind main's externals to the harness. Returns a bag of spies."""
    from unittest.mock import AsyncMock, MagicMock

    # Real time/key helpers (they may be MagicMocks from another test file).
    for name, fn in (
        ("utc_now", utc_now),
        ("parse_deadline", parse_deadline),
        ("deadline_epoch", deadline_epoch),
        ("state_key", state_key),
        ("ZSET_DEADLINES", ZSET_DEADLINES),
        ("STATE_TTL_HOURS", STATE_TTL_HOURS),
    ):
        monkeypatch.setattr(main, name, fn)

    async def _load_state(battle_id):
        raw = rds.kv.get(state_key(battle_id))
        return json.loads(raw) if raw else None

    async def _save_state(battle_id, state, ttl=None):
        rds.kv[state_key(battle_id)] = json.dumps(state, default=str)
        rds.ttls.setdefault(state_key(battle_id), STATE_TTL_HOURS * 3600)

    async def _get_redis_client():
        return rds

    async def _get_battle(_db, battle_id):
        return make_battle_row(db, battle_id)

    async def _finish_battle(_db, battle_id):
        b = db.battles.get(battle_id)
        if b:
            b["status"] = "finished"
        spies.finish_battle_calls.append(battle_id)

    monkeypatch.setattr(main, "load_state", _load_state)
    monkeypatch.setattr(main, "save_state", _save_state)
    monkeypatch.setattr(main, "get_redis_client", _get_redis_client)
    monkeypatch.setattr(main, "get_battle", _get_battle)
    monkeypatch.setattr(main, "finish_battle", _finish_battle)

    spies = SimpleNamespace(
        finish_battle_calls=[],
        notifications=[],
        save_log=MagicMock(),
        track_cumulative=AsyncMock(),
        distribute_rewards=AsyncMock(return_value=rewards),
        update_durability=AsyncMock(),
    )
    spies.save_log.delay = MagicMock()

    async def _publish_notification(target_user_id, message, ws_type=None, ws_data=None):
        spies.notifications.append({
            "user_id": target_user_id, "message": message,
            "ws_type": ws_type, "ws_data": ws_data,
        })

    monkeypatch.setattr(main, "publish_notification", _publish_notification)
    monkeypatch.setattr(main, "save_log", spies.save_log)
    monkeypatch.setattr(main, "_track_cumulative_stats", spies.track_cumulative)
    monkeypatch.setattr(main, "_distribute_pve_rewards", spies.distribute_rewards)
    monkeypatch.setattr(main, "update_durability", spies.update_durability)
    monkeypatch.setattr(main, "get_cached_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(main, "load_snapshot", AsyncMock(return_value=None))

    class _Session:
        async def __aenter__(self_inner):
            return db

        async def __aexit__(self_inner, *exc):
            return False

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _Session())
    return spies
