"""FEAT-197 QA (task 11): the NPC-death call of ``_finalize_battle`` carries the reputation inputs.

``PUT /characters/internal/npc-status/{id}`` must get ``battle_id`` and ``killer_character_ids`` = every character of
the WINNING team (alive or fallen, players and NPC allies alike — character-service keeps only players), sorted and
unique. Losers, mobs and players are never reported as dead NPCs. Driven through the extracted coroutine with the
FEAT-163 harness (fake DB / Redis), HTTP mocked.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
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

from _feat163_harness import (  # noqa: E402
    FakeDB, FakeRedis, make_participant, patch_main, seed_battle, utc_now,
)

BATTLE_ID = 4242


@pytest.fixture
def rds():
    return FakeRedis()


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def spies(monkeypatch, db, rds):
    return patch_main(monkeypatch, main, db, rds, rewards=None)


def _mark_npc(db, character_id):
    db.characters[character_id]["is_npc"] = True
    db.characters[character_id]["user_id"] = None


async def _finalize(db, state, winner_team):
    put = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
    with patch.object(main.httpx, "AsyncClient") as client_cls:
        client = client_cls.return_value.__aenter__.return_value
        client.put = put
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        await main._finalize_battle(db_session=db, battle_id=BATTLE_ID, battle_state=state,
                                    winner_team=winner_team, turn_events=[], turn_number=5)
    return [c for c in put.await_args_list if "/characters/internal/npc-status/" in c.args[0]]


def _party_kills_npc(db, rds):
    """Players 31 (alive) and 12 (fallen) on team 0, with NPC ally 50; NPC 77 on team 1 dies."""
    parts = {
        1: make_participant(31, team=0, hp=40),
        2: make_participant(12, team=0, hp=0),          # fallen winner still counts
        3: make_participant(50, team=0, hp=10),          # NPC ally (character-service filters it)
        4: make_participant(77, team=1, hp=0),
    }
    state = seed_battle(db, rds, BATTLE_ID, parts, next_actor=1,
                        deadline_at=utc_now() + timedelta(hours=1), battle_type="pvp_attack")
    _mark_npc(db, 50)
    _mark_npc(db, 77)
    return state


@pytest.mark.asyncio
async def test_npc_death_payload_carries_battle_and_sorted_winning_team(db, rds, spies):
    state = _party_kills_npc(db, rds)
    calls = await _finalize(db, state, winner_team=0)
    assert len(calls) == 1
    call = calls[0]
    assert call.args[0].endswith("/characters/internal/npc-status/77")
    assert call.kwargs["json"] == {"status": "dead", "battle_id": BATTLE_ID, "killer_character_ids": [12, 31, 50]}
    assert "X-Internal-Token" in call.kwargs["headers"]


@pytest.mark.asyncio
async def test_killer_ids_are_unique_and_exclude_the_losing_team(db, rds, spies):
    parts = {
        1: make_participant(31, team=0, hp=40),
        2: make_participant(31, team=0, hp=20),          # same character twice in the state
        3: make_participant(5, team=0, hp=20),
        4: make_participant(77, team=1, hp=0),
        5: make_participant(78, team=1, hp=0),
        6: make_participant(90, team=1, hp=30),          # surviving loser: not a killer, not dead
    }
    state = seed_battle(db, rds, BATTLE_ID, parts, next_actor=1,
                        deadline_at=utc_now() + timedelta(hours=1), battle_type="pvp_attack")
    for npc in (77, 78, 90):
        _mark_npc(db, npc)
    calls = await _finalize(db, state, winner_team=0)
    assert sorted(c.args[0].rsplit("/", 1)[1] for c in calls) == ["77", "78"]
    for c in calls:
        assert c.kwargs["json"]["killer_character_ids"] == [5, 31]
        assert c.kwargs["json"]["battle_id"] == BATTLE_ID


@pytest.mark.asyncio
async def test_dead_player_loser_is_not_reported_as_npc(db, rds, spies):
    parts = {1: make_participant(77, team=0, hp=50), 2: make_participant(31, team=1, hp=0)}
    state = seed_battle(db, rds, BATTLE_ID, parts, next_actor=1,
                        deadline_at=utc_now() + timedelta(hours=1), battle_type="pvp_attack")
    _mark_npc(db, 77)                                    # the NPC won; the player lost
    assert await _finalize(db, state, winner_team=0) == []


@pytest.mark.asyncio
async def test_no_winner_reports_nothing(db, rds, spies):
    state = _party_kills_npc(db, rds)
    assert await _finalize(db, state, winner_team=None) == []


@pytest.mark.asyncio
async def test_character_service_error_does_not_break_finalize(db, rds, spies):
    state = _party_kills_npc(db, rds)
    put = AsyncMock(return_value=MagicMock(status_code=500, text="boom"))
    with patch.object(main.httpx, "AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value.put = put
        await main._finalize_battle(db_session=db, battle_id=BATTLE_ID, battle_state=state,
                                    winner_team=0, turn_events=[], turn_number=5)
    assert put.await_count == 1
    assert db.battles[BATTLE_ID]["status"] == "finished"
    assert len(db.history) == 4                          # battle history still written after the NPC block
