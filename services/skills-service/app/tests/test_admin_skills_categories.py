"""
Tests for the category filters on GET /skills/admin/skills/.

The admin skill list is split into categories that do not overlap:

- `mob=true` / `mob=false` splits mob skills from the players' skills outright
- `class_id` means "this class, and no subclass of it"
- `subclass_key` means that subclass, which is NOT part of its parent class

The last point is the one worth pinning down: a Paladin skill must not turn up
under Warrior, or the whole split stops meaning anything.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from auth_http import get_current_user_via_http, UserRead


_async_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
)

_AsyncTestSessionLocal = async_sessionmaker(
    _async_test_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


import database  # noqa: E402

_original_get_db = database.get_db


async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session


import models  # noqa: E402
from main import app  # noqa: E402

app.router.on_startup.clear()


_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=["skills:read", "skills:create", "skills:update", "skills:delete"],
)


def _override_admin_user():
    return _ADMIN_USER


@pytest_asyncio.fixture()
async def setup_db():
    database.engine = _async_test_engine
    database.async_session = _AsyncTestSessionLocal
    database.get_db = _override_get_db
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def admin_client(setup_db):
    app.dependency_overrides[_original_get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = _override_admin_user
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _seed():
    """One skill per category, plus the awkward cases worth guarding."""
    async with _AsyncTestSessionLocal() as session:
        session.add_all(
            [
                # Plain class skills
                models.Skill(id=1, name="Удар", skill_type="Attack", class_limitations="1"),
                models.Skill(id=2, name="Выпад", skill_type="Attack", class_limitations="2"),
                # Belongs to two classes at once
                models.Skill(id=3, name="Рывок", skill_type="Attack", class_limitations="1,3"),
                # Subclass skills: scoped to the subclass, not to the class
                models.Skill(
                    id=4, name="Кара", skill_type="Attack",
                    class_limitations="1", subclass_limitations="warrior_paladin",
                ),
                models.Skill(
                    id=5, name="Клятва", skill_type="Support",
                    class_limitations="1", subclass_limitations="warrior_paladin,warrior_saber",
                ),
                # Mob skill: no class scoping at all
                models.Skill(id=6, name="Укус", skill_type="Attack", is_mob_skill=True),
                # Universal player skill: no category
                models.Skill(id=7, name="Отдых", skill_type="Support"),
                # Guards against "1" matching "10" in a comma list
                models.Skill(id=8, name="Чужой", skill_type="Attack", class_limitations="10,11"),
                # Latin-named, for the search test: SQLite's lower() leaves
                # Cyrillic alone, so a case-insensitive search over Russian
                # names only works on MySQL, and testing it here would be
                # testing the test database rather than the filter.
                models.Skill(
                    id=9, name="Smite", skill_type="Attack",
                    class_limitations="1", subclass_limitations="warrior_paladin",
                ),
                # Racial skills: the same narrowing as class -> subclass
                models.Skill(id=10, name="Кровь", skill_type="Support", race_limitations="3"),
                models.Skill(
                    id=11, name="Чешуя", skill_type="Defense",
                    race_limitations="3", subrace_limitations="7",
                ),
                # Scoped on both axes: class and race are independent, so it
                # belongs to both categories at once.
                models.Skill(
                    id=12, name="Ярость", skill_type="Attack",
                    class_limitations="1", race_limitations="3",
                ),
            ]
        )
        await session.commit()


async def _ids(client, **params):
    resp = await client.get("/skills/admin/skills/", params=params)
    assert resp.status_code == 200, resp.text
    return {s["id"] for s in resp.json()}


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_filters_returns_everything(admin_client):
    await _seed()
    assert await _ids(admin_client) == {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}


@pytest.mark.asyncio
async def test_new_columns_default_to_no_category(admin_client):
    await _seed()
    resp = await admin_client.get("/skills/admin/skills/")
    plain = next(s for s in resp.json() if s["id"] == 7)
    assert plain["is_mob_skill"] is False
    assert plain["subclass_limitations"] is None


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_class_filter_excludes_subclass_skills(admin_client):
    """The point of the split: a Paladin skill is not a Warrior skill."""
    await _seed()
    assert await _ids(admin_client, class_id=1) == {1, 3, 12}


@pytest.mark.asyncio
async def test_class_filter_matches_one_entry_of_a_list(admin_client):
    await _seed()
    assert await _ids(admin_client, class_id=3) == {3}


@pytest.mark.asyncio
async def test_class_filter_does_not_match_a_longer_id(admin_client):
    """"1" must not match the "10,11" list."""
    await _seed()
    assert 8 not in await _ids(admin_client, class_id=1)
    assert await _ids(admin_client, class_id=10) == {8}


# ---------------------------------------------------------------------------
# Subclass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subclass_filter(admin_client):
    await _seed()
    assert await _ids(admin_client, subclass_key="warrior_paladin") == {4, 5, 9}
    assert await _ids(admin_client, subclass_key="warrior_saber") == {5}


@pytest.mark.asyncio
async def test_unknown_subclass_returns_nothing(admin_client):
    await _seed()
    assert await _ids(admin_client, subclass_key="mage_necromancer") == set()


# ---------------------------------------------------------------------------
# Mobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mob_filter_splits_both_ways(admin_client):
    await _seed()
    assert await _ids(admin_client, mob=True) == {6}
    assert await _ids(admin_client, mob=False) == {1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12}


@pytest.mark.asyncio
async def test_mob_skills_stay_out_of_class_and_subclass_lists(admin_client):
    await _seed()
    for class_id in (1, 2, 3):
        assert 6 not in await _ids(admin_client, class_id=class_id)
    assert 6 not in await _ids(admin_client, subclass_key="warrior_paladin")


# ---------------------------------------------------------------------------
# Combined with the existing search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_narrows_within_a_category(admin_client):
    await _seed()
    assert await _ids(admin_client, subclass_key="warrior_paladin", q="smi") == {9}


@pytest.mark.asyncio
async def test_search_cannot_reach_outside_its_category(admin_client):
    """A hit that matches the name but sits in another category stays hidden."""
    await _seed()
    assert await _ids(admin_client, q="smi") == {9}
    assert await _ids(admin_client, class_id=1, q="smi") == set()
    assert await _ids(admin_client, mob=True, q="smi") == set()


# ---------------------------------------------------------------------------
# Race
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_race_filter_excludes_subrace_skills(admin_client):
    """Same narrowing as class -> subclass: a subrace skill is not a race skill."""
    await _seed()
    assert await _ids(admin_client, race_id=3) == {10, 12}


@pytest.mark.asyncio
async def test_subrace_filter(admin_client):
    await _seed()
    assert await _ids(admin_client, subrace_id=7) == {11}


@pytest.mark.asyncio
async def test_class_and_race_are_independent_axes(admin_client):
    """A skill scoped to both is listed under both — it is both."""
    await _seed()
    assert 12 in await _ids(admin_client, class_id=1)
    assert 12 in await _ids(admin_client, race_id=3)


# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_general_means_no_scoping_at_all(admin_client):
    """Only the skill with no class, no subclass, no race and no mob flag."""
    await _seed()
    assert await _ids(admin_client, general="true") == {7}


@pytest.mark.asyncio
async def test_general_excludes_mob_skills(admin_client):
    """A mob skill has no class scoping either, but it is not "general"."""
    await _seed()
    assert 6 not in await _ids(admin_client, general="true")
