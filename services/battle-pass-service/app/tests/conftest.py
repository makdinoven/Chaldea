"""
Fixtures for battle-pass-service tests.

Uses async SQLite in-memory database (aiosqlite) for testing.
Mocks external HTTP calls and auth dependencies.
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

# Add the app directory to sys.path so bare imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set DB env vars BEFORE importing config/database
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from auth_http import get_current_user_via_http, require_permission, UserRead
from models import (
    BpSeason, BpLevel, BpReward, BpMission,
    BpUserProgress, BpUserReward, BpUserMissionProgress,
    BpLocationVisit, BpUserSnapshot,
)

# We need to create shared tables that crud.py reads via raw SQL
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float
from sqlalchemy.sql import func


# Mirror tables for shared DB reads in tests
class Character(Base):
    __tablename__ = "characters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=True)
    level = Column(Integer, nullable=False, default=1)
    is_npc = Column(Boolean, nullable=False, default=False)
    currency_balance = Column(Integer, nullable=False, default=0)


class CharacterAttribute(Base):
    __tablename__ = "character_attributes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    pve_kills = Column(Integer, nullable=False, default=0)


class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class GoldTransaction(Base):
    __tablename__ = "gold_transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False, default=0)
    transaction_type = Column(String(50), nullable=False)
    source = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# Async SQLite engine and session
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def async_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(async_engine):
    async_session_factory = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with async_session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Test user fixtures
# ---------------------------------------------------------------------------

TEST_USER = UserRead(
    id=1,
    username="testuser",
    role="user",
    permissions=[],
    current_character_id=100,
)

ADMIN_USER = UserRead(
    id=99,
    username="admin",
    role="admin",
    permissions=[
        "battlepass:read", "battlepass:create",
        "battlepass:update", "battlepass:delete",
    ],
    current_character_id=200,
)

NO_CHAR_USER = UserRead(
    id=2,
    username="nocharuser",
    role="user",
    permissions=[],
    current_character_id=None,
)

UNAUTHORIZED_USER = UserRead(
    id=3,
    username="unauthorized",
    role="user",
    permissions=[],
    current_character_id=100,
)


# ---------------------------------------------------------------------------
# FastAPI test client with dependency overrides
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def client(db_session):
    """AsyncClient with overridden DB and auth dependencies."""
    from httpx import AsyncClient, ASGITransport
    from main import app

    async def override_get_db():
        yield db_session

    async def override_auth():
        return TEST_USER

    async def override_admin_auth():
        return ADMIN_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth

    # Override all permission checkers
    for route in app.routes:
        pass

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def admin_client(db_session):
    """AsyncClient with admin auth."""
    from httpx import AsyncClient, ASGITransport
    from main import app

    async def override_get_db():
        yield db_session

    async def override_admin_auth():
        return ADMIN_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_admin_auth

    # Override require_permission to return admin user
    original_require = require_permission

    def mock_require_permission(perm: str):
        async def checker():
            return ADMIN_USER
        return checker

    import main as main_module
    _orig_rp = main_module.require_permission

    # We patch at the module level
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def unauthorized_client(db_session):
    """AsyncClient with user that has no permissions (for 403 tests)."""
    from httpx import AsyncClient, ASGITransport
    from main import app

    async def override_get_db():
        yield db_session

    async def override_auth():
        return UNAUTHORIZED_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def no_char_client(db_session):
    """AsyncClient with user that has no active character."""
    from httpx import AsyncClient, ASGITransport
    from main import app

    async def override_get_db():
        yield db_session

    async def override_auth():
        return NO_CHAR_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def active_season(db_session) -> BpSeason:
    """Create an active season (now is between start and end)."""
    now = datetime.utcnow()
    season = BpSeason(
        name="Test Season",
        segment_name="spring",
        year=1,
        start_date=now - timedelta(days=10),
        end_date=now + timedelta(days=29),
        grace_end_date=now + timedelta(days=36),
        is_active=True,
    )
    db_session.add(season)
    await db_session.commit()
    await db_session.refresh(season)
    return season


@pytest_asyncio.fixture()
async def grace_season(db_session) -> BpSeason:
    """Create a season in grace period (end_date passed, grace_end not)."""
    now = datetime.utcnow()
    season = BpSeason(
        name="Grace Season",
        segment_name="summer",
        year=1,
        start_date=now - timedelta(days=45),
        end_date=now - timedelta(days=6),
        grace_end_date=now + timedelta(days=1),
        is_active=True,
    )
    db_session.add(season)
    await db_session.commit()
    await db_session.refresh(season)
    return season


@pytest_asyncio.fixture()
async def ended_season(db_session) -> BpSeason:
    """Create an ended season (grace_end passed)."""
    now = datetime.utcnow()
    season = BpSeason(
        name="Ended Season",
        segment_name="autumn",
        year=1,
        start_date=now - timedelta(days=60),
        end_date=now - timedelta(days=21),
        grace_end_date=now - timedelta(days=14),
        is_active=False,
    )
    db_session.add(season)
    await db_session.commit()
    await db_session.refresh(season)
    return season


@pytest_asyncio.fixture()
async def season_with_levels(db_session, active_season) -> BpSeason:
    """Active season with 3 levels and rewards."""
    for i in range(1, 4):
        level = BpLevel(
            season_id=active_season.id,
            level_number=i,
            required_xp=100 * i,
        )
        db_session.add(level)
        await db_session.flush()

        # Free reward
        free_reward = BpReward(
            level_id=level.id,
            track="free",
            reward_type="gold",
            reward_value=500 * i,
        )
        db_session.add(free_reward)

        # Premium reward
        premium_reward = BpReward(
            level_id=level.id,
            track="premium",
            reward_type="diamonds",
            reward_value=50 * i,
        )
        db_session.add(premium_reward)

    await db_session.commit()
    return active_season


@pytest_asyncio.fixture()
async def season_with_missions(db_session, active_season) -> BpSeason:
    """Active season with missions for weeks 1 and 2."""
    missions_data = [
        ("kill_mobs", 1, 10, 50, "Kill 10 mobs"),
        ("write_posts", 1, 5, 30, "Write 5 posts"),
        ("quest_complete", 1, 3, 40, "Complete 3 quests"),
        ("earn_gold", 2, 1000, 60, "Earn 1000 gold"),
        ("spend_gold", 2, 500, 40, "Spend 500 gold"),
        ("visit_locations", 2, 5, 30, "Visit 5 locations"),
    ]
    for mtype, week, target, xp, desc in missions_data:
        mission = BpMission(
            season_id=active_season.id,
            week_number=week,
            mission_type=mtype,
            description=desc,
            target_count=target,
            xp_reward=xp,
        )
        db_session.add(mission)
    await db_session.commit()
    return active_season


@pytest_asyncio.fixture()
async def test_character(db_session) -> Character:
    """Create a test character owned by TEST_USER."""
    char = Character(
        id=100,
        user_id=TEST_USER.id,
        name="Test Hero",
        level=5,
        is_npc=False,
    )
    db_session.add(char)
    # Also create character_attributes
    attrs = CharacterAttribute(
        character_id=100,
        pve_kills=20,
    )
    db_session.add(attrs)
    await db_session.commit()
    return char


@pytest_asyncio.fixture()
async def test_character_admin(db_session) -> Character:
    """Create a test character for admin user."""
    char = Character(
        id=200,
        user_id=ADMIN_USER.id,
        name="Admin Hero",
        level=10,
        is_npc=False,
    )
    db_session.add(char)
    await db_session.commit()
    return char
