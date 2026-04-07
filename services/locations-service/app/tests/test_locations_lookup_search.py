"""
Tests for the optional `q` filter on GET /locations/locations/lookup (FEAT-121).

Strategy:
- Tests `crud.get_locations_lookup` directly against an in-memory aiosqlite
  database. The route is a thin wrapper that just forwards `q` to crud, so
  exercising crud gives us full coverage of the filter logic without needing
  to spin up MySQL.
- One additional test verifies that the function only ever queries the
  `Locations` table — `ClickableZones` rows must not leak into the response.
"""

import os
import sys
import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Make sure DB env vars are set before importing app modules (config requires them)
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

# Ensure the app/ directory is on sys.path (mirrors conftest.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
from models import Location, ClickableZone  # noqa: E402


# ---------- async sqlite fixture ----------

@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    # Create only the tables we need (avoid pulling the whole metadata, which
    # has cross-table FKs that complicate sqlite setup).
    async with engine.begin() as conn:
        await conn.run_sync(Location.__table__.create)
        await conn.run_sync(ClickableZone.__table__.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        # Seed locations
        # NOTE: Use ASCII names so the test is portable across DB collations.
        # SQLite's LOWER() is ASCII-only by default; production MySQL uses
        # utf8mb4_unicode_ci which folds Cyrillic correctly. The crud filter
        # logic (LOWER(name) LIKE %LOWER(q)%) is identical in both cases.
        s.add_all([
            Location(
                id=1, name="Old Town", type="location",
                recommended_level=1, quick_travel_marker=False,
                description="desc", marker_type="safe", sort_order=0,
            ),
            Location(
                id=2, name="Dark Forest", type="location",
                recommended_level=5, quick_travel_marker=False,
                description="desc", marker_type="safe", sort_order=0,
            ),
            Location(
                id=42, name="Dragon Dungeon", type="location",
                recommended_level=10, quick_travel_marker=False,
                description="desc", marker_type="dungeon", sort_order=0,
            ),
            Location(
                id=100, name="MOUNTAIN Pass", type="location",
                recommended_level=7, quick_travel_marker=False,
                description="desc", marker_type="safe", sort_order=0,
            ),
        ])
        # Seed a clickable zone — must NEVER appear in lookup output.
        # ClickableZone has no `name` column; we use `label` to detect leakage.
        s.add(ClickableZone(
            id=999, label="Zone-That-Must-Not-Leak",
            parent_id=1, parent_type="area",
            target_id=2, target_type="region",
            zone_data=[],
        ))
        await s.commit()
        yield s

    await engine.dispose()


# ---------- helpers ----------

def _names(rows):
    return {r["name"] for r in rows}


def _ids(rows):
    return {r["id"] for r in rows}


# ---------- tests ----------

@pytest.mark.asyncio
async def test_lookup_q_omitted_returns_all(session):
    rows = await crud.get_locations_lookup(session, q=None)
    assert _ids(rows) == {1, 2, 42, 100}


@pytest.mark.asyncio
async def test_lookup_q_empty_string_returns_all(session):
    rows = await crud.get_locations_lookup(session, q="")
    assert _ids(rows) == {1, 2, 42, 100}


@pytest.mark.asyncio
async def test_lookup_q_whitespace_only_returns_all(session):
    rows = await crud.get_locations_lookup(session, q="   ")
    assert _ids(rows) == {1, 2, 42, 100}


@pytest.mark.asyncio
async def test_lookup_q_name_substring_case_insensitive(session):
    # lowercase query against mixed-case "Dark Forest"
    rows = await crud.get_locations_lookup(session, q="forest")
    assert _ids(rows) == {2}
    # uppercase query against mixed-case "Dark Forest"
    rows = await crud.get_locations_lookup(session, q="FOREST")
    assert _ids(rows) == {2}
    # Lowercase query against ALL-CAPS "MOUNTAIN Pass"
    rows = await crud.get_locations_lookup(session, q="mountain")
    assert _ids(rows) == {100}
    # Substring (not full word) match
    rows = await crud.get_locations_lookup(session, q="dung")
    assert _ids(rows) == {42}


@pytest.mark.asyncio
async def test_lookup_q_numeric_matches_id(session):
    rows = await crud.get_locations_lookup(session, q="42")
    assert 42 in _ids(rows)
    # Only the row with id=42 should match (no other location name contains "42")
    assert _ids(rows) == {42}


@pytest.mark.asyncio
async def test_lookup_q_no_match_returns_empty(session):
    rows = await crud.get_locations_lookup(session, q="no_such_location_xyz")
    assert rows == []


@pytest.mark.asyncio
async def test_lookup_does_not_include_clickable_zones(session):
    """ClickableZones live in a separate table and must never leak into the
    lookup response, regardless of the query."""
    for q in (None, "", "Zone", "zone-that-must-not-leak", "999"):
        rows = await crud.get_locations_lookup(session, q=q)
        assert all("Zone-That-Must-Not-Leak" not in r["name"] for r in rows), \
            f"ClickableZone leaked into lookup for q={q!r}"
        # The zone has id=999, which must not appear either
        assert 999 not in _ids(rows), f"ClickableZone id leaked for q={q!r}"
