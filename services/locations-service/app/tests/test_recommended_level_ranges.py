"""
Recommended level range for map cards (countries / regions / areas).

- auto range = min..max recommended_level of locations inside, whether a location
  hangs off the region directly or through a district
- manual bounds on Country/Region override the computed ones, per bound
- the zones route attaches target_level; the admin route returns auto + manual
- CountryUpdate/RegionUpdate validate the bounds
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
import schemas  # noqa: E402
from models import Area, Country, District, Location, Region  # noqa: E402


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _location(loc_id, level, region_id=None, district_id=None):
    return Location(
        id=loc_id, name=f"L{loc_id}", type="location", recommended_level=level,
        quick_travel_marker=False, description="d", marker_type="safe", sort_order=0,
        region_id=region_id, district_id=district_id,
    )


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        for model in (Area, Country, Region, District, Location):
            await conn.run_sync(model.__table__.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            Area(id=1, name="World", description="d"),
            Country(id=10, name="North", description="d", area_id=1),
            Country(id=20, name="South", description="d", area_id=1,
                    recommended_level_min=40, recommended_level_max=None),
            Country(id=30, name="Empty", description="d", area_id=1),
            Region(id=100, name="Hills", country_id=10, description="d"),
            Region(id=101, name="Coast", country_id=10, description="d",
                   recommended_level_min=None, recommended_level_max=99),
            Region(id=200, name="Desert", country_id=20, description="d"),
            Region(id=300, name="Unset", country_id=30, description="d"),
        ])
        await s.flush()
        s.add_all([
            District(id=1000, name="Village", region_id=100, description="d"),
        ])
        await s.flush()
        s.add_all([
            _location(1, 10, region_id=100),          # directly in region
            _location(2, 25, district_id=1000),      # through a district of region 100
            _location(3, 5, region_id=101),
            _location(4, 60, region_id=200),
            _location(5, 1, region_id=100),           # level 1 = not set, ignored
            _location(6, 1, region_id=300),
        ])
        await s.commit()
        yield s
    await engine.dispose()


class TestAutoRanges:

    @pytest.mark.asyncio
    async def test_region_counts_direct_and_district_locations(self, session):
        ranges = await crud.auto_level_ranges(session, "region", [100, 101, 200])
        assert ranges == {100: (10, 25), 101: (5, 5), 200: (60, 60)}

    @pytest.mark.asyncio
    async def test_country_and_area_roll_up(self, session):
        assert await crud.auto_level_ranges(session, "country", [10, 20, 30]) == {10: (5, 25), 20: (60, 60)}
        assert await crud.auto_level_ranges(session, "area", [1]) == {1: (5, 60)}

    @pytest.mark.asyncio
    async def test_level_one_locations_are_ignored(self, session):
        # Region 100 also holds a level-1 location; region 300 has only one
        ranges = await crud.auto_level_ranges(session, "region", [100, 300])
        assert ranges == {100: (10, 25)}
        assert (await crud.auto_level_ranges(session, "country", [30])) == {}

    @pytest.mark.asyncio
    async def test_unknown_type_and_empty_ids(self, session):
        assert await crud.auto_level_ranges(session, "district", [1]) == {}
        assert await crud.auto_level_ranges(session, "region", []) == {}


class TestEffectiveRanges:

    @pytest.mark.asyncio
    async def test_manual_bound_wins_per_bound(self, session):
        levels = await crud.level_ranges_for_targets(
            session, {("country", 10), ("country", 20), ("country", 30), ("region", 101), ("area", 1)},
        )
        assert levels[("country", 10)] == {"min": 5, "max": 25, "is_manual": False}
        assert levels[("country", 20)] == {"min": 40, "max": 60, "is_manual": True}
        assert levels[("country", 30)] is None
        assert levels[("region", 101)] == {"min": 5, "max": 99, "is_manual": True}
        assert levels[("area", 1)] == {"min": 5, "max": 60, "is_manual": False}


class TestSchemas:

    def test_min_above_max_rejected(self):
        with pytest.raises(ValidationError) as exc:
            schemas.CountryUpdate(recommended_level_min=30, recommended_level_max=10)
        assert "Минимальный" in str(exc.value)

    @pytest.mark.parametrize("value", [0, 1, 1000, -5])
    def test_out_of_range_rejected(self, value):
        with pytest.raises(ValidationError):
            schemas.RegionUpdate(recommended_level_min=value)

    def test_clearing_to_automatic_allowed(self):
        data = schemas.RegionUpdate(recommended_level_min=None, recommended_level_max=None).dict(exclude_unset=True)
        assert data == {"recommended_level_min": None, "recommended_level_max": None}


# ---------------------------------------------------------------------------
# Routes (DB mocked, crud patched)
# ---------------------------------------------------------------------------

def _zone(zone_id, target_type, target_id):
    zone = MagicMock()
    zone.id = zone_id
    zone.parent_type = "country"
    zone.parent_id = 6
    zone.target_type = target_type
    zone.target_id = target_id
    zone.zone_data = [{"x": 1, "y": 1}, {"x": 5, "y": 1}, {"x": 5, "y": 5}]
    zone.label = "Zone"
    zone.stroke_color = None
    zone.precise_path = None
    zone.land_settings = None
    return zone


class TestRoutes:

    @patch("crud.level_ranges_for_targets", new_callable=AsyncMock)
    @patch("crud.get_clickable_zones_by_parent", new_callable=AsyncMock)
    def test_zones_carry_target_level(self, get_zones, get_levels, client):
        get_zones.return_value = [_zone(1, "region", 100), _zone(2, "region", 999)]
        get_levels.return_value = {("region", 100): {"min": 10, "max": 30, "is_manual": False}}

        data = client.get("/locations/clickable-zones/country/6").json()
        assert data[0]["target_level"] == {"min": 10, "max": 30, "is_manual": False}
        assert data[1]["target_level"] is None

    @patch("crud.auto_level_ranges", new_callable=AsyncMock, return_value={10: (5, 25)})
    @patch("crud.manual_level_ranges", new_callable=AsyncMock, return_value={10: (None, 40)})
    def test_admin_level_info(self, _manual, _auto, client):
        resp = client.get("/locations/recommended-level/country/10")
        assert resp.status_code == 200
        assert resp.json() == {"auto_min": 5, "auto_max": 25, "manual_min": None, "manual_max": 40}

    @patch("crud.manual_level_ranges", new_callable=AsyncMock, return_value={})
    def test_admin_level_info_unknown_is_404(self, _manual, client):
        assert client.get("/locations/recommended-level/region/12345").status_code == 404

    def test_admin_level_info_bad_type(self, client):
        assert client.get("/locations/recommended-level/district/1").status_code == 400
