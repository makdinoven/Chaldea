"""FEAT-175: activity lock (dungeon run / knocked out) in locations-service.

The lock lives in `characters.dungeon_session_id` / `characters.unconscious_until`
(owned by character-service). These tests run the REAL shared-DB query against
a mocked session, so they opt out of the conftest "unlocked" default.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import activity_lock
from auth_http import get_current_user_via_http, UserRead

pytestmark = pytest.mark.real_activity_lock

MOCK_USER = UserRead(id=10, username="testuser", role="user", permissions=[])


def _row(*values):
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    return row


def _result(row):
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def _db_factory(dungeon_session_id=None, unconscious_until=None, escort_caravan_id=None):
    async def mock_get_db():
        db = AsyncMock()

        async def execute(query, params=None):
            q = str(query)
            if "dungeon_session_id" in q and "characters" in q:
                if escort_caravan_id is not None:  # FEAT-212: the 7th column of the full SQL
                    return _result((dungeon_session_id, unconscious_until, None, None, None, None,
                                    escort_caravan_id))
                return _result(_row(dungeon_session_id, unconscious_until))
            if "user_id" in q and "characters" in q:
                return _result(_row(10))
            return _result(None)

        db.execute = AsyncMock(side_effect=execute)
        yield db

    return mock_get_db


# ---------------------------------------------------------------------------
# Pure lock semantics
# ---------------------------------------------------------------------------

class TestComputeLock:
    def test_free(self):
        assert activity_lock.compute_lock(None, None)["locked"] is False

    def test_dungeon(self):
        lock = activity_lock.compute_lock(42, None)
        assert lock == {"locked": True, "reason": "dungeon", "until": None, "dungeon_session_id": 42,
                        "law_encounter_id": None}
        assert activity_lock.lock_message(lock) == "Персонаж находится в подземелье"

    def test_unconscious_future(self):
        until = datetime.utcnow() + timedelta(minutes=30)
        lock = activity_lock.compute_lock(None, until)
        assert lock["reason"] == "unconscious"
        assert activity_lock.lock_message(lock).startswith("Персонаж без сознания — осталось ")

    def test_unconscious_past_is_free(self):
        lock = activity_lock.compute_lock(None, datetime.utcnow() - timedelta(seconds=1))
        assert lock["locked"] is False

    def test_unconscious_string_from_sqlite(self):
        until = (datetime.utcnow() + timedelta(hours=1)).isoformat(sep=" ")
        assert activity_lock.compute_lock(None, until)["reason"] == "unconscious"

    def test_message_shows_time_left(self):
        until = (datetime.utcnow() + timedelta(hours=1, minutes=5)).isoformat()
        lock = {"locked": True, "reason": "unconscious", "until": until}
        assert activity_lock.lock_message(lock) == "Персонаж без сознания — осталось 1 ч 5 мин"


@pytest.mark.asyncio
async def test_check_raises_409_for_dungeon():
    gen = _db_factory(dungeon_session_id=7)()
    db = await gen.__anext__()
    with pytest.raises(HTTPException) as exc:
        await activity_lock.check_not_activity_locked(db, 1)
    assert exc.value.status_code == 409
    assert exc.value.detail == "Персонаж находится в подземелье"


@pytest.mark.asyncio
async def test_check_passes_for_free_character():
    gen = _db_factory()()
    db = await gen.__anext__()
    await activity_lock.check_not_activity_locked(db, 1)


# ---------------------------------------------------------------------------
# Endpoints refuse a locked character before doing anything
# ---------------------------------------------------------------------------

ENDPOINTS = [
    ("/locations/posts/", {"character_id": 1, "location_id": 100, "content": "Привет"}),
    ("/locations/200/move_and_post", {"character_id": 1, "content": "Перехожу"}),
    ("/locations/200/quick_move", {"character_id": 1}),
    ("/locations/100/tag-player", {"target_user_id": 5, "sender_character_id": 1}),
    ("/locations/100/loot/drop", {"character_id": 1, "item_id": 3}),
    ("/locations/100/loot/9/pickup", {"character_id": 1}),
    ("/locations/npcs/3/shop/buy", {"character_id": 1, "shop_item_id": 4}),
    ("/locations/npcs/3/shop/sell", {"character_id": 1, "item_id": 4}),
    ("/locations/quests/5/accept", {"character_id": 1}),
    ("/locations/quests/5/complete", {"character_id": 1}),
]


@pytest.mark.parametrize("url,payload", ENDPOINTS)
@pytest.mark.parametrize(
    "lock_kwargs,expected",
    [
        ({"dungeon_session_id": 11}, "Персонаж находится в подземелье"),
        (
            {"unconscious_until": datetime.utcnow() + timedelta(hours=1)},
            "Персонаж без сознания — осталось",
        ),
        # FEAT-212: a caravan escort gets the neutral text (never mentions the caravan).
        ({"escort_caravan_id": 5}, "Персонаж: действие сейчас недоступно"),
    ],
    ids=["dungeon", "unconscious", "escort"],
)
def test_locked_character_is_refused(client, url, payload, lock_kwargs, expected):
    from database import get_db
    from main import app

    app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _db_factory(**lock_kwargs)
    try:
        response = client.post(url, json=payload)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409, response.text
    assert response.json()["detail"].startswith(expected)


@pytest.mark.asyncio
async def test_start_gathering_checks_lock_first():
    """crud.start_gathering refuses a locked character before touching the node."""
    import crud

    db = AsyncMock()

    async def execute(query, params=None):
        q = str(query)
        if "dungeon_session_id" in q:
            return _result(_row(3, None))
        return _result(None)

    db.execute = AsyncMock(side_effect=execute)
    with patch.object(crud, "_read_character_for_start", AsyncMock(return_value=(10, 100, "Имя"))), \
         patch.object(crud, "finalize_due_sessions", AsyncMock()), \
         patch.object(crud, "_load_gathering_node_for_update", AsyncMock()) as load_node:
        with pytest.raises(HTTPException) as exc:
            await crud.start_gathering(
                db, location_id=100, node_id=1, character_id=1,
                tool_inventory_item_id=None, current_user_id=10,
            )
    assert exc.value.status_code == 409
    load_node.assert_not_called()


# ---------------------------------------------------------------------------
# FEAT-212: caravan escort reason + deploy-skew fallback chain (identical to the BS copy)
# ---------------------------------------------------------------------------

_LEGACY_COLS = {"dungeon_session_id": None, "unconscious_until": None, "asleep_since": None,
                "reading_since": None}
_LAW_COLS = dict(_LEGACY_COLS, jailed_until=None, law_encounter_id=None)
_FULL_COLS = dict(_LAW_COLS, escort_caravan_id=None)


def _schema_db(schema):
    """AsyncSession over a `characters` table with only these lock columns; an unknown
    column raises the MySQL error, whose text also echoes the whole SQL."""
    calls = []

    async def execute(query, params=None):
        q = str(query)
        calls.append(q)
        cols = [c.strip() for c in q.split("SELECT", 1)[1].split("FROM", 1)[0].split(",")]
        for c in cols:
            if c not in schema:
                raise RuntimeError(f"(pymysql.err.OperationalError) (1054, \"Unknown column '{c}' "
                                   f"in 'field list'\") [SQL: {q}]")
        return _result(tuple(schema[c] for c in cols))

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute)
    return db, calls


class TestEscortLock:
    def test_neutral_message(self):
        lock = activity_lock.compute_lock(None, None, escort_caravan_id=9)
        assert lock["reason"] == "caravan_escort"
        for subject in ("Персонаж", "Ваш персонаж"):
            msg = activity_lock.lock_message(lock, subject=subject)
            assert msg == f"{subject}: действие сейчас недоступно"
            assert "карав" not in msg.lower()

    def test_priority_below_dungeon_above_asleep(self):
        assert activity_lock.compute_lock(3, None, escort_caravan_id=9)["reason"] == "dungeon"
        assert activity_lock.compute_lock(None, None, escort_caravan_id=9,
                                          asleep_since=datetime.utcnow())["reason"] == "caravan_escort"

    @pytest.mark.asyncio
    async def test_full_schema(self):
        db, calls = _schema_db(dict(_FULL_COLS, escort_caravan_id=9))
        assert (await activity_lock.get_activity_lock(db, 1))["reason"] == "caravan_escort"
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_without_escort_column_uses_the_law_sql(self):
        db, calls = _schema_db(dict(_LAW_COLS, law_encounter_id=4))
        assert (await activity_lock.get_activity_lock(db, 1))["reason"] == "law_encounter"
        assert len(calls) == 2 and "escort_caravan_id" not in calls[1] and "jailed_until" in calls[1]

    @pytest.mark.asyncio
    async def test_without_law_columns_uses_the_legacy_sql(self):
        db, calls = _schema_db(dict(_LEGACY_COLS, dungeon_session_id=2))
        assert (await activity_lock.get_activity_lock(db, 1))["reason"] == "dungeon"
        assert len(calls) == 2 and "jailed_until" not in calls[1]

    @pytest.mark.asyncio
    async def test_unrelated_missing_column_propagates(self):
        async def execute(query, params=None):
            raise RuntimeError(f"(1054, \"Unknown column 'reading_since' in 'field list'\") [SQL: {query}]")

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        with pytest.raises(RuntimeError):
            await activity_lock.get_activity_lock(db, 1)
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_check_raises_409_neutral(self):
        db, _ = _schema_db(dict(_FULL_COLS, escort_caravan_id=9))
        with pytest.raises(HTTPException) as exc:
            await activity_lock.check_not_activity_locked(db, 1)
        assert exc.value.status_code == 409
        assert exc.value.detail == "Персонаж: действие сейчас недоступно"


def test_copy_is_identical_to_battle_service():
    """FEAT-212: the LS copy must stay byte-identical to the BS copy (skipped when only this
    service is mounted, e.g. inside its container)."""
    import hashlib
    import os
    here = os.path.dirname(os.path.abspath(activity_lock.__file__))
    other = os.path.normpath(os.path.join(here, "..", "..", "battle-service", "app", "activity_lock.py"))
    if not os.path.exists(other):
        pytest.skip("battle-service sources are not available here")
    digest = [hashlib.md5(open(f, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
              for f in (activity_lock.__file__, other)]
    assert digest[0] == digest[1]
