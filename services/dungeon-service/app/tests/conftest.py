# conftest.py - Fixtures for dungeon-service tests.
# Uses async SQLite in-memory DB (aiosqlite), patches config before imports.

import sys
import os
import atexit

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
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from sqlalchemy import event, String, Integer  # noqa: E402
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

# Dispose the original MySQL engine immediately to prevent hang on exit
# (aiomysql pool cleanup blocks when no MySQL server is reachable)
database.engine.sync_engine.dispose()

database.engine = _test_engine
database.async_session = _TestAsyncSession


# Force-kill the process after pytest finishes to prevent async cleanup hang.
# Without this, leftover asyncio resources (aioredis, aiomysql pools from
# module-level imports) block Python's interpreter shutdown indefinitely.
atexit.register(lambda: os._exit(0))

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
        # SQLite needs INTEGER (not BIGINT) for autoincrement PKs
        if col.primary_key and type(col.type).__name__ == "BigInteger":
            col.type = Integer()

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


# Data factory helpers — imported from helpers.py to avoid `from conftest import` anti-pattern
from helpers import _dungeon_payload, _room_payload, _corridor_payload  # noqa: F401


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


# ---------------------------------------------------------------------------
# Mock-based fixtures for unit tests (test_gameplay.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Async mock for SQLAlchemy AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def sample_dungeon():
    """Mock Dungeon ORM object with sensible defaults."""
    d = MagicMock(spec=models.Dungeon)
    d.id = 1
    d.location_id = 100
    d.is_active = True
    d.cooldown_hours = 24
    d.stability_type = "static"
    d.name = "Test Dungeon"
    d.description = "A test dungeon"
    d.danger_level = "safe"
    d.recommended_level = 1
    d.recommended_party_size = 1
    d.mob_multiplier = 1.0
    d.loot_multiplier = 1.0
    d.stamina_multiplier = 1.0
    d.difficulty_modifier = 1.0
    d.disable_rest_rooms = False
    d.disable_merchants = False
    d.mana_core_chance = 0.0
    d.mana_core_item_id = None
    d.image_url = None
    return d


@pytest.fixture
def sample_session():
    """Mock DungeonSession ORM object — active session with two members."""
    m1 = MagicMock(spec=models.DungeonSessionMember)
    m1.id = 1
    m1.session_id = 100
    m1.character_id = 200
    m1.user_id = 1
    m1.status = "alive"

    m2 = MagicMock(spec=models.DungeonSessionMember)
    m2.id = 2
    m2.session_id = 100
    m2.character_id = 201
    m2.user_id = 2
    m2.status = "alive"

    s = MagicMock(spec=models.DungeonSession)
    s.id = 100
    s.dungeon_id = 1
    s.leader_character_id = 200
    s.status = "active"
    s.current_room_id = 10
    s.members = [m1, m2]
    s.started_at = None
    s.finished_at = None
    s.cooldown_until = None
    return s


@pytest.fixture
def sample_corridor():
    """Mock DungeonCorridor ORM object — from room 10 to room 11."""
    c = MagicMock(spec=models.DungeonCorridor)
    c.id = 50
    c.dungeon_id = 1
    c.from_room_id = 10
    c.to_room_id = 11
    c.stamina_cost = 5
    c.is_bidirectional = True
    c.random_battle_chance = 0.0
    c.random_battle_mob_ids = None
    c.trap_chance = 0.0
    c.trap_config = None
    c.description = None
    c.source_handle = None
    c.target_handle = None
    return c


@pytest.fixture
def sample_room():
    """Mock DungeonRoom ORM object — fork room (current room)."""
    r = MagicMock(spec=models.DungeonRoom)
    r.id = 10
    r.dungeon_id = 1
    r.room_type = "fork"
    r.name = "Первая комната"
    r.description = "Начальная комната"
    r.image_url = None
    r.is_entrance = True
    r.is_boss_room = False
    r.is_mana_core_room = False
    r.sort_order = 0
    r.room_config = None
    r.position_x = 0.0
    r.position_y = 0.0
    return r


@pytest.fixture
def sample_room_state():
    """Mock DungeonRoomState ORM object — not cleared, no loot collected."""
    rs = MagicMock(spec=models.DungeonRoomState)
    rs.id = 1
    rs.session_id = 100
    rs.room_id = 10
    rs.is_cleared = False
    rs.loot_collected = False
    rs.event_choice_index = None
    rs.extra_data = {}
    return rs


@pytest.fixture
def sample_redis_state():
    """Dict representing a Redis session state — active session, two alive members."""
    return {
        "session_id": 100,
        "dungeon_id": 1,
        "current_room_id": 10,
        "status": "active",
        "leader_character_id": 200,
        "members": {
            "200": {"user_id": 1, "status": "alive"},
            "201": {"user_id": 2, "status": "alive"},
        },
        "active_battle_id": None,
        "dead_count": 0,
        "phase": "exploring",
    }
