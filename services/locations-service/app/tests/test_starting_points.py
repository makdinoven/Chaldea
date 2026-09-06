"""
Tests for the curated starting points of FEAT-154 (task #2).

Endpoints under test:
- ``GET /locations/starting-points``      — public, curated list only
- ``GET /locations/starting-points/{id}`` — public validation probe

Strategy (mirrors ``test_locations_lookup_search.py``):
- ``crud.get_starting_points`` / ``crud.get_starting_point`` are exercised
  directly against an in-memory aiosqlite database, because the filtering
  (``is_starting = 1``) and the hierarchy joins are the whole point of the
  feature.
- The routes themselves are covered through the shared ``client`` fixture with
  crud mocked, so the 404 contract and the "no auth required" property are
  pinned independently of the DB.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
from models import Country, District, Location, Region  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — in-memory async SQLite with the world hierarchy seeded
# ---------------------------------------------------------------------------

@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _location(**kwargs):
    """Location with every NOT NULL column filled in."""
    defaults = dict(
        type="location",
        recommended_level=1,
        quick_travel_marker=False,
        description="desc",
        marker_type="safe",
        sort_order=0,
        is_starting=False,
    )
    defaults.update(kwargs)
    return Location(**defaults)


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    # Create only the four tables the joins touch. Order matters only for
    # readability — SQLite does not resolve FK targets at CREATE time.
    async with engine.begin() as conn:
        await conn.run_sync(Country.__table__.create)
        await conn.run_sync(Region.__table__.create)
        await conn.run_sync(District.__table__.create)
        await conn.run_sync(Location.__table__.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        s.add(Country(id=1, name="Middengerd", description="d"))
        s.add(Region(id=1, name="Citadel", country_id=1, description="d"))
        s.add(District(id=1, name="Lower Tier", region_id=1, description="d"))
        s.add_all([
            # Curated starting point hanging off a district.
            _location(
                id=10, name="Citadel Pier", district_id=1,
                image_url="https://s3/pier.webp",
                starting_blurb="Recruits come ashore here.",
                sort_order=10, is_starting=True,
            ),
            # Curated starting point hanging straight off a region.
            _location(
                id=11, name="Wayfarers Camp", region_id=1,
                sort_order=5, is_starting=True,
            ),
            # Ordinary catalogue location — must never be published.
            _location(id=12, name="Dark Forest", district_id=1, sort_order=1),
            # Orphaned starting point — no district, no region.
            _location(id=13, name="Nowhere Dock", sort_order=99, is_starting=True),
        ])
        await s.commit()
        yield s

    await engine.dispose()


# ===========================================================================
# 1. crud.get_starting_points — the curated list
# ===========================================================================

class TestGetStartingPoints:

    @pytest.mark.asyncio
    async def test_returns_only_flagged_locations(self, session):
        """Rule 19: the 2260-location catalogue is never published."""
        rows = await crud.get_starting_points(session)
        assert {r["id"] for r in rows} == {10, 11, 13}

    @pytest.mark.asyncio
    async def test_ordered_by_sort_order(self, session):
        rows = await crud.get_starting_points(session)
        assert [r["id"] for r in rows] == [11, 10, 13]

    @pytest.mark.asyncio
    async def test_breadcrumbs_resolved_through_district(self, session):
        rows = {r["id"]: r for r in await crud.get_starting_points(session)}
        pier = rows[10]
        assert pier["district_name"] == "Lower Tier"
        assert pier["region_name"] == "Citadel"
        assert pier["country_name"] == "Middengerd"
        assert pier["starting_blurb"] == "Recruits come ashore here."
        assert pier["image_url"] == "https://s3/pier.webp"

    @pytest.mark.asyncio
    async def test_breadcrumbs_resolved_for_region_bound_location(self, session):
        """A location hanging off a region still gets region/country names."""
        rows = {r["id"]: r for r in await crud.get_starting_points(session)}
        camp = rows[11]
        assert camp["district_name"] is None
        assert camp["region_name"] == "Citadel"
        assert camp["country_name"] == "Middengerd"

    @pytest.mark.asyncio
    async def test_orphaned_starting_point_still_listed(self, session):
        """Every join is an OUTER join — a point with no parents still shows."""
        rows = {r["id"]: r for r in await crud.get_starting_points(session)}
        assert 13 in rows
        assert rows[13]["region_name"] is None
        assert rows[13]["country_name"] is None

    @pytest.mark.asyncio
    async def test_payload_keys_match_the_contract(self, session):
        rows = await crud.get_starting_points(session)
        assert set(rows[0].keys()) == {
            "id", "name", "image_url", "starting_blurb",
            "district_name", "region_name", "country_name", "sort_order",
            # FEAT-155 — additive: false unless ?origin_id is supplied
            "is_recommended",
        }


# ===========================================================================
# 2. crud.get_starting_point — the validation probe
# ===========================================================================

class TestGetStartingPoint:

    @pytest.mark.asyncio
    async def test_flagged_location_is_found(self, session):
        row = await crud.get_starting_point(session, 10)
        assert row is not None
        assert row["name"] == "Citadel Pier"

    @pytest.mark.asyncio
    async def test_unflagged_location_returns_none(self, session):
        """An existing but non-curated location is indistinguishable from absent."""
        assert await crud.get_starting_point(session, 12) is None

    @pytest.mark.asyncio
    async def test_missing_location_returns_none(self, session):
        assert await crud.get_starting_point(session, 999999) is None


# ===========================================================================
# 3. Routes
# ===========================================================================

_POINT = {
    "id": 10,
    "name": "Citadel Pier",
    "image_url": "https://s3/pier.webp",
    "starting_blurb": "Recruits come ashore here.",
    "district_name": "Lower Tier",
    "region_name": "Citadel",
    "country_name": "Middengerd",
    "sort_order": 10,
}


class TestStartingPointRoutes:

    @patch("crud.get_starting_points", new_callable=AsyncMock, return_value=[_POINT])
    def test_list_returns_200_without_auth(self, mock_crud, client):
        resp = client.get("/locations/starting-points")
        assert resp.status_code == 200
        # FEAT-155 — the response model now carries an additive is_recommended
        assert resp.json() == [{**_POINT, "is_recommended": False}]

    @patch("crud.get_starting_points", new_callable=AsyncMock, return_value=[])
    def test_list_can_be_empty(self, mock_crud, client):
        resp = client.get("/locations/starting-points")
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("crud.get_starting_point", new_callable=AsyncMock, return_value=_POINT)
    def test_detail_returns_200_without_auth(self, mock_crud, client):
        resp = client.get("/locations/starting-points/10")
        assert resp.status_code == 200
        assert resp.json()["id"] == 10
        mock_crud.assert_awaited_once()

    @patch("crud.get_starting_point", new_callable=AsyncMock, return_value=None)
    def test_detail_returns_404_when_not_curated(self, mock_crud, client):
        resp = client.get("/locations/starting-points/12")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Выбранная точка не входит в список стартовых."

    @patch("crud.get_starting_point", new_callable=AsyncMock, return_value=None)
    def test_detail_returns_404_for_missing_location(self, mock_crud, client):
        resp = client.get("/locations/starting-points/999999")
        assert resp.status_code == 404

    def test_detail_rejects_non_numeric_id(self, client):
        """The literal /starting-points route must not swallow garbage ids."""
        resp = client.get("/locations/starting-points/not-a-number")
        assert resp.status_code == 422
