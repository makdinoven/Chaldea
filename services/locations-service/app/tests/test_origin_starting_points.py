"""
Tests for the recommended starting points of an origin (FEAT-155).

Endpoints under test:
- ``GET    /locations/starting-points?origin_id=``                        — public
- ``GET    /locations/admin/origins/{id}/starting-points``                — ``origins:read``
- ``PUT    /locations/admin/origins/{id}/starting-points``                — ``origins:update``
- ``POST   /locations/admin/origins/{id}/starting-points/{location_id}``  — ``origins:update``
- ``DELETE /locations/admin/origins/{id}/starting-points/{location_id}``  — ``origins:update``
- ``GET    /locations/admin/location-search``                             — ``origins:update``

Strategy (mirrors ``test_starting_points.py`` / ``test_origins.py``):
- The crud layer runs against in-memory aiosqlite with ``PRAGMA foreign_keys=ON``,
  because the three things the feature actually rests on — the rule-7 promotion,
  the ON DELETE CASCADE that implements rule 9, and the "recommended first"
  ordering — can only be proven against real tables with real constraints.
- The routes run through the shared ``client`` fixture with crud mocked and
  ``auth_http.requests.get`` patched, so the RBAC split (``origins:read`` vs
  ``origins:update``) and the error contracts are pinned independently of the DB.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import BigInteger, event, select, func as sa_func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
from models import (  # noqa: E402
    Area, Country, District, Location, OriginCountry, OriginStartingPoint,
    Region,
)


# SQLite only auto-assigns a primary key for the exact type "INTEGER"; a BIGINT
# PK stays NULL and the INSERT fails. Same test-harness hook as test_origins.py.
@compiles(BigInteger, "sqlite")
def _bigint_as_sqlite_integer(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


# ---------------------------------------------------------------------------
# Fixtures — in-memory async SQLite with FK enforcement switched on
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

    # SQLite ignores foreign keys unless the pragma is set per connection — and
    # ON DELETE CASCADE is exactly what rule 9 rests on, so it must be on.
    @event.listens_for(engine.sync_engine, "connect")
    def _fk_pragma(dbapi_conn, record):  # pragma: no cover - connection hook
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        # Areas too: with the pragma on, Countries.area_id is checked at INSERT.
        await conn.run_sync(Area.__table__.create)
        await conn.run_sync(Country.__table__.create)
        await conn.run_sync(Region.__table__.create)
        await conn.run_sync(District.__table__.create)
        await conn.run_sync(Location.__table__.create)
        await conn.run_sync(OriginCountry.__table__.create)
        await conn.run_sync(OriginStartingPoint.__table__.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        # Flushed level by level: Regions/Districts point at Locations
        # (entrance_location_id) and Locations point back, so the unit of work
        # cannot order a single flush safely once FKs are enforced.
        s.add(Country(id=1, name="Middengerd", description="d"))
        await s.flush()
        s.add(Region(id=1, name="Citadel", country_id=1, description="d"))
        await s.flush()
        s.add(District(id=1, name="Lower Tier", region_id=1, description="d"))
        await s.flush()
        s.add_all([
            _location(
                id=10, name="Citadel Pier", district_id=1,
                image_url="https://s3/pier.webp",
                starting_blurb="Recruits come ashore here.",
                sort_order=10, is_starting=True,
            ),
            _location(
                id=11, name="Wayfarers Camp", region_id=1,
                sort_order=5, is_starting=True,
            ),
            # Not a starting point — the promotion target of rule 7.
            _location(id=12, name="Dark Forest", district_id=1, sort_order=1),
            # Orphaned starting point — no district, no region.
            _location(id=13, name="Nowhere Dock", sort_order=99, is_starting=True),
            # Digits in the name, for the "numeric query" search case.
            _location(id=14, name="Post 12", district_id=1, sort_order=7),
        ])
        s.add_all([
            OriginCountry(id=1, name="Belyi Klin",
                          is_active=True, sort_order=10),
            OriginCountry(id=2, name="Aldergard",
                          is_active=True, sort_order=20),
        ])
        await s.flush()
        # Curated order is deliberately the opposite of Location.sort_order,
        # so "curated first" cannot be mistaken for "sort_order happened to win".
        s.add_all([
            OriginStartingPoint(origin_id=1, location_id=13, sort_order=0),
            OriginStartingPoint(origin_id=1, location_id=11, sort_order=1),
        ])
        await s.commit()
        yield s

    await engine.dispose()


async def _link_ids(session, origin_id):
    result = await session.execute(
        select(OriginStartingPoint.location_id)
        .where(OriginStartingPoint.origin_id == origin_id)
        .order_by(OriginStartingPoint.sort_order.asc())
    )
    return list(result.scalars().all())


async def _is_starting(session, location_id):
    result = await session.execute(
        select(Location.is_starting).where(Location.id == location_id)
    )
    return bool(result.scalar_one())


# ===========================================================================
# 1. GET /locations/starting-points — backward compatibility and annotation
# ===========================================================================

class TestStartingPointsWithOrigin:

    @pytest.mark.asyncio
    async def test_without_origin_behaviour_is_unchanged(self, session):
        """FEAT-154 contract: same rows, same order, nothing recommended."""
        rows = await crud.get_starting_points(session)
        assert [r["id"] for r in rows] == [11, 10, 13]
        assert all(r["is_recommended"] is False for r in rows)

    @pytest.mark.asyncio
    async def test_without_origin_keys_are_unchanged(self, session):
        rows = await crud.get_starting_points(session)
        assert set(rows[0].keys()) == {
            "id", "name", "image_url", "starting_blurb", "district_name",
            "region_name", "country_name", "sort_order", "is_recommended",
        }

    @pytest.mark.asyncio
    async def test_origin_id_does_not_filter_the_list(self, session):
        """Rule 2 — a recommendation is a hint, never a restriction."""
        plain = {r["id"] for r in await crud.get_starting_points(session)}
        annotated = {
            r["id"] for r in await crud.get_starting_points(session, origin_id=1)
        }
        assert annotated == plain == {10, 11, 13}

    @pytest.mark.asyncio
    async def test_recommended_come_first_in_curated_order(self, session):
        """Curated order (13, 11) wins over Location.sort_order (11, 10, 13)."""
        rows = await crud.get_starting_points(session, origin_id=1)
        assert [r["id"] for r in rows] == [13, 11, 10]

    @pytest.mark.asyncio
    async def test_the_rest_keep_their_previous_order(self, session):
        """Non-recommended points stay in the FEAT-154 order among themselves."""
        await crud.set_origin_starting_points(session, 1, [13])
        rows = await crud.get_starting_points(session, origin_id=1)
        assert [r["id"] for r in rows] == [13, 11, 10]  # 11 (sort 5) before 10 (sort 10)

    @pytest.mark.asyncio
    async def test_only_the_recommended_are_flagged(self, session):
        rows = {r["id"]: r for r in await crud.get_starting_points(session, origin_id=1)}
        assert rows[13]["is_recommended"] is True
        assert rows[11]["is_recommended"] is True
        assert rows[10]["is_recommended"] is False

    @pytest.mark.asyncio
    async def test_origin_without_recommendations_behaves_like_no_origin(self, session):
        """Rule 4 — no marks, no empty states, just the old list."""
        plain = await crud.get_starting_points(session)
        rows = await crud.get_starting_points(session, origin_id=2)
        assert [r["id"] for r in rows] == [r["id"] for r in plain]
        assert all(r["is_recommended"] is False for r in rows)

    @pytest.mark.asyncio
    async def test_unknown_origin_id_is_not_an_error(self, session):
        """The public step must never 500 because an origin vanished."""
        rows = await crud.get_starting_points(session, origin_id=999999)
        assert [r["id"] for r in rows] == [11, 10, 13]
        assert all(r["is_recommended"] is False for r in rows)

    @pytest.mark.asyncio
    async def test_annotated_rows_keep_their_breadcrumbs(self, session):
        rows = {r["id"]: r for r in await crud.get_starting_points(session, origin_id=1)}
        assert rows[10]["district_name"] == "Lower Tier"
        assert rows[10]["region_name"] == "Citadel"
        assert rows[10]["country_name"] == "Middengerd"


# ===========================================================================
# 2. crud — reading one origin's recommended set
# ===========================================================================

class TestGetOriginStartingPoints:

    @pytest.mark.asyncio
    async def test_returns_the_curated_set_in_curated_order(self, session):
        rows = await crud.get_origin_starting_points(session, 1)
        assert [r["id"] for r in rows] == [13, 11]

    @pytest.mark.asyncio
    async def test_every_row_is_flagged_recommended(self, session):
        rows = await crud.get_origin_starting_points(session, 1)
        assert all(r["is_recommended"] is True for r in rows)

    @pytest.mark.asyncio
    async def test_origin_without_links_returns_empty(self, session):
        assert await crud.get_origin_starting_points(session, 2) == []

    @pytest.mark.asyncio
    async def test_unknown_origin_is_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.get_origin_starting_points(session, 999999)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Происхождение не найдено."


# ===========================================================================
# 3. PUT — replacing the whole set (rule 7 promotion, atomicity)
# ===========================================================================

class TestSetOriginStartingPoints:

    @pytest.mark.asyncio
    async def test_array_order_becomes_the_curated_order(self, session):
        rows = await crud.set_origin_starting_points(session, 1, [10, 13, 11])
        assert [r["id"] for r in rows] == [10, 13, 11]
        assert await _link_ids(session, 1) == [10, 13, 11]

    @pytest.mark.asyncio
    async def test_replaces_rather_than_appends(self, session):
        await crud.set_origin_starting_points(session, 1, [10])
        assert await _link_ids(session, 1) == [10]

    @pytest.mark.asyncio
    async def test_duplicates_collapse_keeping_first_position(self, session):
        rows = await crud.set_origin_starting_points(session, 1, [11, 10, 11, 10])
        assert [r["id"] for r in rows] == [11, 10]

    @pytest.mark.asyncio
    async def test_empty_list_clears_the_set(self, session):
        assert await crud.set_origin_starting_points(session, 1, []) == []
        assert await _link_ids(session, 1) == []

    @pytest.mark.asyncio
    async def test_promotes_a_location_that_was_not_a_starting_point(self, session):
        """Rule 7 — recommending 12 makes it a starting point in the same write."""
        assert await _is_starting(session, 12) is False

        rows = await crud.set_origin_starting_points(session, 1, [12])

        assert [r["id"] for r in rows] == [12]
        assert await _is_starting(session, 12) is True
        # And it now shows up in the public curated list too.
        public = await crud.get_starting_points(session)
        assert 12 in {r["id"] for r in public}

    @pytest.mark.asyncio
    async def test_promotion_survives_a_fresh_read(self, session):
        """The flag is committed, not merely set on the in-memory object."""
        await crud.set_origin_starting_points(session, 1, [12])
        session.expire_all()
        assert await _is_starting(session, 12) is True

    @pytest.mark.asyncio
    async def test_does_not_touch_another_origins_set(self, session):
        await crud.set_origin_starting_points(session, 2, [10])
        assert await _link_ids(session, 1) == [13, 11]
        assert await _link_ids(session, 2) == [10]

    @pytest.mark.asyncio
    async def test_unknown_origin_raises_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.set_origin_starting_points(session, 999999, [10])
        assert exc.value.status_code == 404
        assert exc.value.detail == "Происхождение не найдено."

    @pytest.mark.asyncio
    async def test_unknown_location_raises_404_and_writes_nothing(self, session):
        """Atomicity: one bad id and the whole request is a no-op."""
        with pytest.raises(HTTPException) as exc:
            await crud.set_origin_starting_points(session, 1, [12, 999999])
        assert exc.value.status_code == 404
        assert exc.value.detail == "Локация не найдена: 999999."

        # The request would end here; get_db closes the session, rolling back.
        await session.rollback()

        assert await _link_ids(session, 1) == [13, 11], "the old set must survive"
        assert await _is_starting(session, 12) is False, "no half-promotion"


# ===========================================================================
# 4. POST — appending one point, idempotently
# ===========================================================================

class TestAddOriginStartingPoint:

    @pytest.mark.asyncio
    async def test_appends_to_the_end_of_the_curated_order(self, session):
        rows = await crud.add_origin_starting_point(session, 1, 10)
        assert [r["id"] for r in rows] == [13, 11, 10]

    @pytest.mark.asyncio
    async def test_repeat_is_idempotent_not_an_error(self, session):
        first = await crud.add_origin_starting_point(session, 1, 10)
        second = await crud.add_origin_starting_point(session, 1, 10)
        assert [r["id"] for r in second] == [r["id"] for r in first]
        assert await _link_ids(session, 1) == [13, 11, 10]

    @pytest.mark.asyncio
    async def test_promotes_a_location_that_was_not_a_starting_point(self, session):
        """Rule 7 again — the POST path must promote just like the PUT path."""
        assert await _is_starting(session, 12) is False
        rows = await crud.add_origin_starting_point(session, 1, 12)
        assert 12 in {r["id"] for r in rows}
        assert await _is_starting(session, 12) is True

    @pytest.mark.asyncio
    async def test_add_to_an_empty_set(self, session):
        rows = await crud.add_origin_starting_point(session, 2, 10)
        assert [r["id"] for r in rows] == [10]

    @pytest.mark.asyncio
    async def test_unknown_origin_raises_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.add_origin_starting_point(session, 999999, 10)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_location_raises_404_and_writes_nothing(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.add_origin_starting_point(session, 1, 999999)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Локация не найдена: 999999."
        await session.rollback()
        assert await _link_ids(session, 1) == [13, 11]


# ===========================================================================
# 5. DELETE — removing one point, keeping the flag (rule 8)
# ===========================================================================

class TestRemoveOriginStartingPoint:

    @pytest.mark.asyncio
    async def test_removes_only_that_link(self, session):
        rows = await crud.remove_origin_starting_point(session, 1, 13)
        assert [r["id"] for r in rows] == [11]
        assert await _link_ids(session, 1) == [11]

    @pytest.mark.asyncio
    async def test_does_not_clear_is_starting(self, session):
        """Rule 8 — the point may well be a starting point on its own account."""
        await crud.remove_origin_starting_point(session, 1, 13)
        session.expire_all()
        assert await _is_starting(session, 13) is True
        public = await crud.get_starting_points(session)
        assert 13 in {r["id"] for r in public}

    @pytest.mark.asyncio
    async def test_removing_a_link_that_is_not_there_raises_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.remove_origin_starting_point(session, 1, 10)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Эта локация не входит в набор рекомендованных."

    @pytest.mark.asyncio
    async def test_second_delete_raises_404(self, session):
        await crud.remove_origin_starting_point(session, 1, 13)
        with pytest.raises(HTTPException) as exc:
            await crud.remove_origin_starting_point(session, 1, 13)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_origin_raises_404(self, session):
        with pytest.raises(HTTPException) as exc:
            await crud.remove_origin_starting_point(session, 999999, 13)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Происхождение не найдено."

    @pytest.mark.asyncio
    async def test_does_not_touch_another_origins_link_to_the_same_location(
        self, session
    ):
        await crud.add_origin_starting_point(session, 2, 13)
        await crud.remove_origin_starting_point(session, 1, 13)
        assert await _link_ids(session, 2) == [13]


# ===========================================================================
# 6. ON DELETE CASCADE — rule 9
# ===========================================================================

class TestCascade:

    @pytest.mark.asyncio
    async def test_deleting_a_location_takes_its_links_with_it(self, session):
        location = await session.get(Location, 13)
        await session.delete(location)
        await session.commit()

        assert await _link_ids(session, 1) == [11]
        # And the read path never sees a ghost.
        rows = await crud.get_origin_starting_points(session, 1)
        assert [r["id"] for r in rows] == [11]

    @pytest.mark.asyncio
    async def test_deleting_a_location_leaves_other_links_alone(self, session):
        await crud.add_origin_starting_point(session, 2, 11)
        location = await session.get(Location, 13)
        await session.delete(location)
        await session.commit()
        assert await _link_ids(session, 2) == [11]

    @pytest.mark.asyncio
    async def test_deleting_an_origin_takes_its_links_with_it(self, session):
        total_before = (await session.execute(
            select(sa_func.count()).select_from(OriginStartingPoint)
        )).scalar_one()
        assert total_before == 2

        origin = await session.get(OriginCountry, 1)
        await session.delete(origin)
        await session.commit()

        total_after = (await session.execute(
            select(sa_func.count()).select_from(OriginStartingPoint)
        )).scalar_one()
        assert total_after == 0

    @pytest.mark.asyncio
    async def test_cascade_does_not_delete_the_location_itself(self, session):
        """The link table is the dependent side — locations outlive the links."""
        origin = await session.get(OriginCountry, 1)
        await session.delete(origin)
        await session.commit()

        assert await session.get(Location, 13) is not None
        assert await _is_starting(session, 13) is True


# ===========================================================================
# 7. crud.search_locations_with_breadcrumbs — rule 6
# ===========================================================================

class TestLocationSearch:

    @pytest.mark.asyncio
    async def test_substring_match_is_case_insensitive(self, session):
        rows = await crud.search_locations_with_breadcrumbs(session, "CITADEL")
        assert [r["id"] for r in rows] == [10]

    @pytest.mark.asyncio
    async def test_partial_substring_matches_in_the_middle(self, session):
        rows = await crud.search_locations_with_breadcrumbs(session, "are")
        assert [r["id"] for r in rows] == [11]  # Wayfarers Camp

    @pytest.mark.asyncio
    async def test_search_is_not_limited_to_starting_points(self, session):
        """Rule 7 exists precisely because a non-starting location is pickable."""
        rows = await crud.search_locations_with_breadcrumbs(session, "Dark")
        assert [r["id"] for r in rows] == [12]
        assert rows[0]["is_starting"] is False

    @pytest.mark.asyncio
    async def test_numeric_query_matches_by_id_and_by_name(self, session):
        rows = await crud.search_locations_with_breadcrumbs(session, "12")
        # id 12 ("Dark Forest") and name "Post 12"
        assert {r["id"] for r in rows} == {12, 14}

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, session):
        assert await crud.search_locations_with_breadcrumbs(session, "zzzz") == []

    @pytest.mark.asyncio
    async def test_blank_query_returns_empty_without_touching_the_db(self, session):
        assert await crud.search_locations_with_breadcrumbs(session, "   ") == []
        assert await crud.search_locations_with_breadcrumbs(session, "") == []

    @pytest.mark.asyncio
    async def test_query_is_trimmed(self, session):
        rows = await crud.search_locations_with_breadcrumbs(session, "  Pier  ")
        assert [r["id"] for r in rows] == [10]

    @pytest.mark.asyncio
    async def test_limit_is_respected(self, session):
        rows = await crud.search_locations_with_breadcrumbs(session, "a", limit=1)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_limit_is_clamped_to_fifty(self, session):
        rows = await crud.search_locations_with_breadcrumbs(session, "a", limit=10_000)
        assert len(rows) <= 50

    @pytest.mark.asyncio
    async def test_payload_carries_breadcrumbs(self, session):
        rows = await crud.search_locations_with_breadcrumbs(session, "Pier")
        assert set(rows[0].keys()) == {
            "id", "name", "image_url", "district_name", "region_name",
            "country_name", "is_starting",
        }
        assert rows[0]["district_name"] == "Lower Tier"
        assert rows[0]["region_name"] == "Citadel"
        assert rows[0]["country_name"] == "Middengerd"
        assert rows[0]["is_starting"] is True

    @pytest.mark.asyncio
    async def test_orphaned_location_is_still_findable(self, session):
        """Every join is OUTER — a location with no parents must not disappear."""
        rows = await crud.search_locations_with_breadcrumbs(session, "Nowhere")
        assert [r["id"] for r in rows] == [13]
        assert rows[0]["country_name"] is None

    @pytest.mark.asyncio
    async def test_sql_injection_in_q_is_treated_as_a_literal(self, session):
        payload = "'; DROP TABLE Locations; --"
        assert await crud.search_locations_with_breadcrumbs(session, payload) == []
        total = (await session.execute(
            select(sa_func.count()).select_from(Location)
        )).scalar_one()
        assert total == 5, "the table must survive"

    @pytest.mark.asyncio
    async def test_like_wildcards_are_treated_as_literal_characters(self, session):
        """``%`` and ``_`` are typed text, not a pattern the admin is writing.

        None of the five fixture locations carries either character, so a bare
        wildcard query must come back empty instead of listing the whole table.
        """
        assert await crud.search_locations_with_breadcrumbs(
            session, "%", limit=50) == []
        assert await crud.search_locations_with_breadcrumbs(
            session, "_", limit=50) == []
        # "_" as a single-character wildcard would match "Post 12" here.
        assert await crud.search_locations_with_breadcrumbs(
            session, "Post_12", limit=50) == []

    @pytest.mark.asyncio
    async def test_a_name_containing_a_wildcard_is_findable_by_it(self, session):
        """The flip side: escaping must not make such a location unreachable."""
        session.add_all([
            _location(id=20, name="Rate_Limit Post", district_id=1),
            _location(id=21, name="Tavern 50% Off", district_id=1),
            # The escape character itself must survive a round trip.
            _location(id=22, name="Bang! Range", district_id=1),
        ])
        await session.commit()

        assert [r["id"] for r in await crud.search_locations_with_breadcrumbs(
            session, "Rate_Limit")] == [20]
        assert [r["id"] for r in await crud.search_locations_with_breadcrumbs(
            session, "50%")] == [21]
        assert [r["id"] for r in await crud.search_locations_with_breadcrumbs(
            session, "Bang!")] == [22]


# ===========================================================================
# 8. Routes — RBAC
# ===========================================================================

ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}

ORIGINS_ADMIN_USER = {
    "id": 1, "username": "admin", "role": "admin",
    "permissions": [
        "origins:read", "origins:create", "origins:update", "origins:delete",
    ],
}
READ_ONLY_USER = {
    "id": 4, "username": "editor", "role": "editor",
    "permissions": ["origins:read"],
}
OTHER_MODULE_USER = {
    "id": 2, "username": "moderator", "role": "moderator",
    "permissions": ["locations:create", "locations:update", "locations:delete"],
}
PLAIN_USER = {"id": 3, "username": "player", "role": "user", "permissions": []}

SET_BODY = {"location_ids": [13, 11]}


def _auth(json_data, status_code=200):
    from unittest.mock import MagicMock
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


_ROW = {
    "id": 13, "name": "Nowhere Dock", "image_url": None, "starting_blurb": None,
    "district_name": None, "region_name": None, "country_name": None,
    "sort_order": 99, "is_recommended": True,
}


class TestOriginStartingPointRoutesAuth:

    def test_every_route_requires_a_token(self, client):
        assert client.get(
            "/locations/admin/origins/1/starting-points").status_code == 401
        assert client.put(
            "/locations/admin/origins/1/starting-points",
            json=SET_BODY).status_code == 401
        assert client.post(
            "/locations/admin/origins/1/starting-points/13").status_code == 401
        assert client.delete(
            "/locations/admin/origins/1/starting-points/13").status_code == 401
        assert client.get(
            "/locations/admin/location-search?q=pier").status_code == 401

    @patch("auth_http.requests.get")
    def test_plain_user_gets_403_everywhere(self, mock_auth, client):
        mock_auth.return_value = _auth(PLAIN_USER)
        assert client.get(
            "/locations/admin/origins/1/starting-points",
            headers=ADMIN_HEADERS).status_code == 403
        assert client.put(
            "/locations/admin/origins/1/starting-points", json=SET_BODY,
            headers=ADMIN_HEADERS).status_code == 403
        assert client.post(
            "/locations/admin/origins/1/starting-points/13",
            headers=ADMIN_HEADERS).status_code == 403
        assert client.delete(
            "/locations/admin/origins/1/starting-points/13",
            headers=ADMIN_HEADERS).status_code == 403
        assert client.get(
            "/locations/admin/location-search?q=pier",
            headers=ADMIN_HEADERS).status_code == 403

    @patch("crud.get_origin_starting_points", new_callable=AsyncMock, return_value=[])
    @patch("auth_http.requests.get")
    def test_read_permission_allows_the_get_but_not_the_writes(
        self, mock_auth, mock_crud, client
    ):
        mock_auth.return_value = _auth(READ_ONLY_USER)
        assert client.get(
            "/locations/admin/origins/1/starting-points",
            headers=ADMIN_HEADERS).status_code == 200
        assert client.put(
            "/locations/admin/origins/1/starting-points", json=SET_BODY,
            headers=ADMIN_HEADERS).status_code == 403
        assert client.post(
            "/locations/admin/origins/1/starting-points/13",
            headers=ADMIN_HEADERS).status_code == 403
        assert client.delete(
            "/locations/admin/origins/1/starting-points/13",
            headers=ADMIN_HEADERS).status_code == 403
        # The search screen is part of the editing flow — origins:update.
        assert client.get(
            "/locations/admin/location-search?q=pier",
            headers=ADMIN_HEADERS).status_code == 403

    @patch("auth_http.requests.get")
    def test_locations_permissions_do_not_grant_origins_access(self, mock_auth, client):
        mock_auth.return_value = _auth(OTHER_MODULE_USER)
        resp = client.put(
            "/locations/admin/origins/1/starting-points", json=SET_BODY,
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Недостаточно прав"

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        mock_auth.return_value = _auth(None, status_code=401)
        resp = client.get(
            "/locations/admin/origins/1/starting-points", headers=ADMIN_HEADERS
        )
        assert resp.status_code == 401


# ===========================================================================
# 9. Routes — contracts
# ===========================================================================

class TestOriginStartingPointRoutes:

    @patch("crud.get_origin_starting_points", new_callable=AsyncMock,
           return_value=[_ROW])
    @patch("auth_http.requests.get")
    def test_admin_list_returns_the_recommended_set(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.get(
            "/locations/admin/origins/1/starting-points", headers=ADMIN_HEADERS
        )
        assert resp.status_code == 200
        assert resp.json() == [_ROW]

    @patch("crud.set_origin_starting_points", new_callable=AsyncMock,
           return_value=[_ROW])
    @patch("auth_http.requests.get")
    def test_put_passes_the_array_through_in_order(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.put(
            "/locations/admin/origins/1/starting-points",
            json={"location_ids": [13, 11, 10]}, headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert mock_crud.await_args.args[1:] == (1, [13, 11, 10])

    @patch("crud.set_origin_starting_points", new_callable=AsyncMock,
           return_value=[])
    @patch("auth_http.requests.get")
    def test_put_accepts_an_empty_array(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.put(
            "/locations/admin/origins/1/starting-points",
            json={"location_ids": []}, headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("auth_http.requests.get")
    def test_put_rejects_more_than_200_ids(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.put(
            "/locations/admin/origins/1/starting-points",
            json={"location_ids": list(range(1, 202))}, headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422

    @patch("auth_http.requests.get")
    def test_put_rejects_non_positive_ids(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        for bad in (0, -5):
            resp = client.put(
                "/locations/admin/origins/1/starting-points",
                json={"location_ids": [bad]}, headers=ADMIN_HEADERS,
            )
            assert resp.status_code == 422

    @patch("auth_http.requests.get")
    def test_put_rejects_a_non_list_body(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.put(
            "/locations/admin/origins/1/starting-points",
            json={"location_ids": "13"}, headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 422

    @patch("crud.set_origin_starting_points", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_put_propagates_the_missing_location_404(
        self, mock_auth, mock_crud, client
    ):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.side_effect = HTTPException(
            status_code=404, detail="Локация не найдена: 999999."
        )
        resp = client.put(
            "/locations/admin/origins/1/starting-points",
            json={"location_ids": [999999]}, headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Локация не найдена: 999999."

    @patch("crud.add_origin_starting_point", new_callable=AsyncMock,
           return_value=[_ROW])
    @patch("auth_http.requests.get")
    def test_post_returns_200_not_201(self, mock_auth, mock_crud, client):
        """Idempotent append — the response is the resulting set, not a creation."""
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.post(
            "/locations/admin/origins/1/starting-points/13", headers=ADMIN_HEADERS
        )
        assert resp.status_code == 200
        assert resp.json() == [_ROW]

    @patch("crud.remove_origin_starting_point", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_propagates_the_russian_404(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        mock_crud.side_effect = HTTPException(
            status_code=404, detail="Эта локация не входит в набор рекомендованных."
        )
        resp = client.delete(
            "/locations/admin/origins/1/starting-points/13", headers=ADMIN_HEADERS
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Эта локация не входит в набор рекомендованных."

    @patch("auth_http.requests.get")
    def test_non_numeric_ids_are_rejected(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        assert client.get(
            "/locations/admin/origins/abc/starting-points",
            headers=ADMIN_HEADERS).status_code == 422
        assert client.delete(
            "/locations/admin/origins/1/starting-points/abc",
            headers=ADMIN_HEADERS).status_code == 422


# ===========================================================================
# 10. Routes — public list and search wiring
# ===========================================================================

class TestPublicListRoute:

    @patch("crud.get_starting_points", new_callable=AsyncMock, return_value=[])
    def test_origin_id_is_forwarded_to_crud(self, mock_crud, client):
        client.get("/locations/starting-points?origin_id=7")
        assert mock_crud.await_args.kwargs.get("origin_id") == 7

    @patch("crud.get_starting_points", new_callable=AsyncMock, return_value=[])
    def test_origin_id_defaults_to_none(self, mock_crud, client):
        client.get("/locations/starting-points")
        assert mock_crud.await_args.kwargs.get("origin_id") is None

    @patch("crud.get_starting_points", new_callable=AsyncMock, return_value=[])
    def test_the_public_route_stays_open(self, mock_crud, client):
        assert client.get(
            "/locations/starting-points?origin_id=7").status_code == 200

    def test_non_numeric_origin_id_is_rejected(self, client):
        resp = client.get("/locations/starting-points?origin_id=abc")
        assert resp.status_code == 422


_SEARCH_ROW = {
    "id": 658, "name": "Abbey", "image_url": None, "district_name": "Vinifera",
    "region_name": "Hopfenau", "country_name": "Oros", "is_starting": False,
}


class TestLocationSearchRoute:

    @patch("crud.search_locations_with_breadcrumbs", new_callable=AsyncMock,
           return_value=[_SEARCH_ROW])
    @patch("auth_http.requests.get")
    def test_returns_matches_with_breadcrumbs(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.get(
            "/locations/admin/location-search?q=abb", headers=ADMIN_HEADERS
        )
        assert resp.status_code == 200
        assert resp.json() == [_SEARCH_ROW]

    @patch("crud.search_locations_with_breadcrumbs", new_callable=AsyncMock,
           return_value=[])
    @patch("auth_http.requests.get")
    def test_default_limit_is_twenty(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        client.get("/locations/admin/location-search?q=abb", headers=ADMIN_HEADERS)
        assert mock_crud.await_args.kwargs.get("limit") == 20

    @patch("auth_http.requests.get")
    def test_missing_query_returns_422(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        assert client.get(
            "/locations/admin/location-search", headers=ADMIN_HEADERS
        ).status_code == 422

    @patch("auth_http.requests.get")
    def test_empty_query_returns_422(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        assert client.get(
            "/locations/admin/location-search?q=", headers=ADMIN_HEADERS
        ).status_code == 422

    @patch("auth_http.requests.get")
    def test_limit_out_of_bounds_returns_422(self, mock_auth, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        assert client.get(
            "/locations/admin/location-search?q=a&limit=0", headers=ADMIN_HEADERS
        ).status_code == 422
        assert client.get(
            "/locations/admin/location-search?q=a&limit=51", headers=ADMIN_HEADERS
        ).status_code == 422

    @patch("crud.search_locations_with_breadcrumbs", new_callable=AsyncMock,
           return_value=[])
    @patch("auth_http.requests.get")
    def test_limit_bounds_are_accepted(self, mock_auth, mock_crud, client):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        for limit in (1, 50):
            resp = client.get(
                f"/locations/admin/location-search?q=a&limit={limit}",
                headers=ADMIN_HEADERS,
            )
            assert resp.status_code == 200

    @patch("crud.search_locations_with_breadcrumbs", new_callable=AsyncMock,
           return_value=[])
    @patch("auth_http.requests.get")
    def test_injection_string_does_not_crash_the_route(
        self, mock_auth, mock_crud, client
    ):
        mock_auth.return_value = _auth(ORIGINS_ADMIN_USER)
        resp = client.get(
            "/locations/admin/location-search",
            params={"q": "'; DROP TABLE Locations; --"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code in (200, 400)
