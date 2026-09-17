"""FEAT-164 — battle-service side of passive regeneration.

* Every end-of-battle write to ``character_attributes`` (normal finish,
  pvp_training loser heal, admin / timeout force-finish) also resets
  ``regen_anchor_at = UTC_TIMESTAMP()`` so battle time is never credited as rest.
* Before character-attributes-service migration 008 is applied the anchored
  UPDATE fails with "Unknown column"; the old statement is retried (WARNING),
  any OTHER error is not masked.
* The SQL is executed for real against SQLite (with a UTC_TIMESTAMP shim) so a
  typo in a column name cannot hide behind a string-matching fake.
* ``battle_participants.joined_at`` is set on battle creation (one timestamp
  for all participants) and has a model default for every other insert path.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

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

import crud  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from schemas import BattleRewards  # noqa: E402

from _feat163_harness import (  # noqa: E402
    FakeDB, FakeRedis, make_participant, patch_main, seed_battle, utc_now,
)

REWARDS = BattleRewards(xp=10, gold=1, items=[])


@pytest.fixture
def rds():
    return FakeRedis()


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def spies(monkeypatch, db, rds):
    return patch_main(monkeypatch, main, db, rds, rewards=REWARDS)


def _killing_blow(db, rds, battle_type="pve"):
    parts = {1: make_participant(10, team=0, hp=0),
             2: make_participant(20, team=1, hp=55)}
    return seed_battle(db, rds, 1, parts, next_actor=2,
                       deadline_at=utc_now() + timedelta(hours=3),
                       battle_type=battle_type)


# ---------------------------------------------------------------------------
# The three end-of-battle writers
# ---------------------------------------------------------------------------

class TestAnchorResetOnBattleEnd:

    @pytest.mark.asyncio
    async def test_normal_finish_resets_anchor_for_every_participant(self, db, rds, spies):
        state = _killing_blow(db, rds)
        await main._finalize_battle(
            db_session=db, battle_id=1, battle_state=state,
            winner_team=1, turn_events=[], turn_number=5,
        )
        assert sorted(db.anchor_resets) == [10, 20]
        assert sorted(s["cid"] for s in db.resource_syncs) == [10, 20]
        sync_sql = [q for q in db.sql_log if q.startswith("update character_attributes set current_health = :hp")]
        assert sync_sql and all("regen_anchor_at = utc_timestamp()" in q for q in sync_sql)

    @pytest.mark.asyncio
    async def test_pvp_training_loser_heal_resets_anchor(self, db, rds, spies):
        state = _killing_blow(db, rds, battle_type="pvp_training")
        await main._finalize_battle(
            db_session=db, battle_id=1, battle_state=state,
            winner_team=1, turn_events=[], turn_number=5,
        )
        assert db.pvp_training_heals == [10]
        heal_sql = [q for q in db.sql_log if q.startswith("update character_attributes set current_health = 1")]
        assert len(heal_sql) == 1
        assert "regen_anchor_at = utc_timestamp()" in heal_sql[0]
        # resource sync (2) + heal (1)
        assert sorted(db.anchor_resets) == [10, 10, 20]

    @pytest.mark.asyncio
    async def test_force_finish_resets_anchor(self, db, rds, spies):
        state = _killing_blow(db, rds)
        await main._force_finish_battle(db, 1, state, reason="Админ")
        assert sorted(db.anchor_resets) == [10, 20]

    @pytest.mark.asyncio
    async def test_force_finish_without_state_touches_nothing(self, db, rds, spies):
        _killing_blow(db, rds)
        await main._force_finish_battle(db, 1, None, reason="Истёк срок")
        assert db.anchor_resets == []

    @pytest.mark.asyncio
    async def test_unmigrated_attributes_fall_back_to_legacy_update(self, db, rds, spies, caplog):
        db.missing_anchor_column = True
        state = _killing_blow(db, rds, battle_type="pvp_training")
        with caplog.at_level(logging.WARNING):
            await main._finalize_battle(
                db_session=db, battle_id=1, battle_state=state,
                winner_team=1, turn_events=[], turn_number=5,
            )
        # resources still synced (legacy statement), loser still healed
        assert sorted(s["cid"] for s in db.resource_syncs) == [10, 20]
        assert db.pvp_training_heals == [10]
        assert db.anchor_resets == []
        assert db.rollbacks >= 3
        assert any("regen_anchor_at" in r.getMessage() and r.levelno == logging.WARNING
                   for r in caplog.records)
        assert db.battles[1]["status"] == "finished"


# ---------------------------------------------------------------------------
# Fallback helper semantics
# ---------------------------------------------------------------------------

class TestAnchorFallback:

    @pytest.mark.parametrize("msg,expected", [
        ("(1054, \"Unknown column 'regen_anchor_at' in 'field list'\")", True),
        ("no such column: regen_anchor_at", True),
        ("(1054, \"Unknown column 'current_hp' in 'field list'\")", False),
        ("(1213, 'Deadlock found when trying to get lock')", False),
        ("regen_anchor_at: data too long", False),
    ])
    def test_missing_column_detection(self, msg, expected):
        assert main._is_missing_anchor_column(Exception(msg)) is expected

    @pytest.mark.asyncio
    async def test_other_errors_are_not_masked(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("Deadlock found"))
        with pytest.raises(RuntimeError):
            await main._sync_final_resources(
                session, 7, {"hp": 1, "mana": 1, "energy": 1, "stamina": 1},
            )
        assert session.execute.await_count == 1  # legacy NOT tried

    @pytest.mark.asyncio
    async def test_sync_params_are_clamped(self):
        session = AsyncMock()
        await main._sync_final_resources(
            session, 7, {"hp": -5, "mana": 3.9, "energy": 0, "stamina": -1},
        )
        stmt, params = session.execute.await_args.args
        assert "regen_anchor_at = UTC_TIMESTAMP()" in str(stmt)
        assert params == {"hp": 0, "mana": 3, "energy": 0, "stamina": 0, "cid": 7}
        session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Real SQL against SQLite (column names are load-bearing)
# ---------------------------------------------------------------------------

_ATTR_DDL = """
CREATE TABLE character_attributes (
    id INTEGER PRIMARY KEY,
    character_id INTEGER UNIQUE,
    current_health INTEGER, current_mana INTEGER,
    current_energy INTEGER, current_stamina INTEGER,
    regen_anchor_at DATETIME NULL,
    regen_carry_health FLOAT NOT NULL DEFAULT 0,
    regen_carry_mana FLOAT NOT NULL DEFAULT 0,
    regen_carry_energy FLOAT NOT NULL DEFAULT 0,
    regen_carry_stamina FLOAT NOT NULL DEFAULT 0
)
"""

FIXED_NOW = "2026-09-17 12:00:00"


def _conn(with_anchor=True):
    conn = sqlite3.connect(":memory:")
    conn.create_function("UTC_TIMESTAMP", 0, lambda: FIXED_NOW)
    ddl = _ATTR_DDL if with_anchor else _ATTR_DDL.replace("regen_anchor_at DATETIME NULL,", "")
    conn.execute(ddl)
    conn.execute(
        "INSERT INTO character_attributes (character_id, current_health, current_mana, current_energy, "
        "current_stamina, regen_carry_health) VALUES (7, 50, 50, 50, 50, 0.75)"
        if with_anchor else
        "INSERT INTO character_attributes (character_id, current_health, current_mana, current_energy, "
        "current_stamina) VALUES (7, 50, 50, 50, 50)"
    )
    return conn


class TestSqlExecutesForReal:

    def test_resource_sync_sets_values_and_anchor_keeps_carry(self):
        conn = _conn()
        conn.execute(str(main._RESOURCE_SYNC_SQL),
                     {"hp": 3, "mana": 4, "energy": 5, "stamina": 6, "cid": 7})
        row = conn.execute(
            "SELECT current_health, current_mana, current_energy, current_stamina, "
            "regen_anchor_at, regen_carry_health FROM character_attributes WHERE character_id = 7"
        ).fetchone()
        assert row == (3, 4, 5, 6, FIXED_NOW, 0.75)

    def test_training_loser_sql(self):
        conn = _conn()
        conn.execute(str(main._TRAINING_LOSER_SQL), {"cid": 7})
        row = conn.execute(
            "SELECT current_health, regen_anchor_at FROM character_attributes WHERE character_id = 7"
        ).fetchone()
        assert row == (1, FIXED_NOW)

    @pytest.mark.parametrize("stmt_name", ["_RESOURCE_SYNC_SQL", "_TRAINING_LOSER_SQL"])
    def test_anchored_sql_fails_on_unmigrated_table_with_detectable_error(self, stmt_name):
        conn = _conn(with_anchor=False)
        params = {"hp": 1, "mana": 1, "energy": 1, "stamina": 1, "cid": 7}
        with pytest.raises(sqlite3.OperationalError) as exc:
            conn.execute(str(getattr(main, stmt_name)), params)
        assert main._is_missing_anchor_column(exc.value)

    @pytest.mark.parametrize("stmt_name,params", [
        ("_RESOURCE_SYNC_SQL_LEGACY", {"hp": 9, "mana": 9, "energy": 9, "stamina": 9, "cid": 7}),
        ("_TRAINING_LOSER_SQL_LEGACY", {"cid": 7}),
    ])
    def test_legacy_sql_works_on_unmigrated_table(self, stmt_name, params):
        conn = _conn(with_anchor=False)
        cur = conn.execute(str(getattr(main, stmt_name)), params)
        assert cur.rowcount == 1
        assert "regen_anchor_at" not in str(getattr(main, stmt_name))


# ---------------------------------------------------------------------------
# joined_at
# ---------------------------------------------------------------------------

class TestJoinedAt:

    def test_model_has_joined_at_with_default(self):
        col = models.BattleParticipant.__table__.c.joined_at
        assert col.nullable is True
        assert col.default is not None
        before = datetime.utcnow()
        value = col.default.arg(None) if col.default.is_callable else col.default.arg
        assert before - timedelta(seconds=5) <= value <= datetime.utcnow() + timedelta(seconds=5)

    @pytest.mark.asyncio
    async def test_create_battle_sets_one_joined_at_for_all(self):
        session = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        added = []
        session.add = lambda obj: setattr(obj, "id", 55)
        session.add_all = lambda objs: added.extend(objs)

        before = datetime.utcnow()
        battle, participants = await crud.create_battle(session, [1, 2, 3], [0, 1, 1])
        after = datetime.utcnow()

        assert len(added) == 3
        stamps = {p.joined_at for p in participants}
        assert len(stamps) == 1
        stamp = stamps.pop()
        assert stamp is not None and before <= stamp <= after
        assert all(p.battle_id == 55 for p in participants)

    def test_joined_at_is_utc_naive(self):
        # regen compares against naive UTC; utcnow() default must be naive
        col = models.BattleParticipant.__table__.c.joined_at
        value = col.default.arg(None) if col.default.is_callable else col.default.arg
        assert value.tzinfo is None
