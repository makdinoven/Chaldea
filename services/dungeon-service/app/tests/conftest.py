# conftest.py - Fixtures for dungeon-service tests.
# Uses async SQLite in-memory DB (aiosqlite), patches config before imports.

import sys
import os

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set DB env vars BEFORE importing config/database
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from typing import AsyncGenerator  # noqa: E402

from sqlalchemy import event, String  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402

# Async SQLite in-memory engine (aiosqlite)
_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

_TestAsyncSession = sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@event.listens_for(_test_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Patch database module BEFORE importing models/main
import database  # noqa: E402

database.engine = _test_engine
database.async_session = _TestAsyncSession

# Import models and patch Enum columns to String for SQLite compat
import models  # noqa: E402

for _model_cls in (
    models.Dungeon,
    models.DungeonRoom,
    models.DungeonCorridor,
    models.DungeonSession,
    models.DungeonSessionMember,
    models.DungeonSessionInventory,
    models.DungeonRoomVisit,
    models.DungeonRoomState,
):
    for col in _model_cls.__table__.columns:
        if type(col.type).__name__ == "Enum":
            col.type = String(100)

from auth_http import get_admin_user, get_current_user_via_http, UserRead  # noqa: E402
from main import app  # noqa: E402
from database import get_db, Base  # noqa: E402

# Shared admin user constant
_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=[
        "dungeons:create", "dungeons:edit",
        "dungeons:delete", "dungeons:view",
    ],
)

_REGULAR_USER = UserRead(
    id=2,
    username="regular",
    role="user",
    permissions=[],
)


# Fixtures

@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a clean async DB session; tables created/dropped per test."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with _TestAsyncSession() as session:
        yield session

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def admin_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with overridden get_db AND admin auth."""

    async def override_get_db():
        yield db_session

    def override_admin():
        return _ADMIN_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def no_auth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with DB override but NO auth override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# Data factory helpers

def _dungeon_payload(**overrides) -> dict:
    """Return a valid DungeonCreate payload."""
    base = {
        "name": "Test Dungeon",
        "description": "A dark test dungeon",
        "lore_text": "Ancient halls of testing",
        "stability_type": "static",
        "danger_level": "safe",
        "location_id": 1,
        "recommended_level": 5,
        "recommended_party_size": 2,
        "cooldown_hours": 24,
        "mob_multiplier": 1.0,
        "loot_multiplier": 1.0,
        "stamina_multiplier": 1.0,
        "difficulty_modifier": 1.0,
        "disable_rest_rooms": False,
        "disable_merchants": False,
        "mana_core_chance": 0.1,
        "mana_core_item_id": None,
        "image_url": None,
    }
    base.update(overrides)
    return base


def _room_payload(room_type="battle", **overrides) -> dict:
    """Return a valid DungeonRoomCreate payload."""
    base = {
        "room_type": room_type,
        "name": "Room (" + room_type + ")",
        "description": "A " + room_type + " room",
        "sort_order": 0,
        "is_entrance": False,
        "is_boss_room": False,
        "is_mana_core_room": False,
        "room_config": None,
    }
    base.update(overrides)
    return base


def _corridor_payload(from_room_id, to_room_id, **overrides) -> dict:
    """Return a valid DungeonCorridorCreate payload."""
    base = {
        "from_room_id": from_room_id,
        "to_room_id": to_room_id,
        "stamina_cost": 5,
        "is_bidirectional": True,
        "random_battle_chance": 0.0,
        "random_battle_mob_ids": None,
        "trap_chance": 0.0,
        "trap_config": None,
        "description": None,
    }
    base.update(overrides)
    return base


@pytest_asyncio.fixture()
async def created_dungeon(admin_client):
    """Create a dungeon and return the response JSON."""
    resp = await admin_client.post(
        "/dungeons/admin/dungeons",
        json=_dungeon_payload(),
    )
    assert resp.status_code == 201
    return resp.json()


@pytest_asyncio.fixture()
async def dungeon_with_rooms(admin_client, created_dungeon):
    """Create a dungeon with entrance, battle, and boss rooms + corridors."""
    dungeon_id = created_dungeon["id"]

    entrance_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("fork", name="Entrance", is_entrance=True),
    )
    assert entrance_resp.status_code == 201
    entrance = entrance_resp.json()

    battle_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("battle", name="Battle Room"),
    )
    assert battle_resp.status_code == 201
    battle_room = battle_resp.json()

    boss_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("boss", name="Boss Room", is_boss_room=True),
    )
    assert boss_resp.status_code == 201
    boss_room = boss_resp.json()

    c1_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/corridors" % dungeon_id,
        json=_corridor_payload(entrance["id"], battle_room["id"]),
    )
    assert c1_resp.status_code == 201
    corridor1 = c1_resp.json()

    c2_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/corridors" % dungeon_id,
        json=_corridor_payload(battle_room["id"], boss_room["id"]),
    )
    assert c2_resp.status_code == 201
    corridor2 = c2_resp.json()

    return {
        "dungeon": created_dungeon,
        "entrance": entrance,
        "battle_room": battle_room,
        "boss_room": boss_room,
        "corridor1": corridor1,
        "corridor2": corridor2,
    }
