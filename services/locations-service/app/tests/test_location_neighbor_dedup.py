"""Duplicated transitions between locations (prod bug 2026-11-15).

The admin location editor received arrow transitions (is_auto_arrow=1) among the
location's neighbours and saved them back through /neighbors/update, which
re-created them as manual rows. A pair then had two or three rows in one
direction with different stamina costs, and the manual copy outlived the arrow
path when the admin deleted it.

Covered here on a real (SQLite) database:
* update_location_neighbors never copies an arrow pair and keeps one row per neighbour;
* drawing an arrow path over an existing manual link replaces it instead of adding a second row;
* deleting the arrow path leaves no transition behind;
* location details mark arrow transitions so the editor can show them read-only;
* the unique key refuses a second row of the same direction.
"""
import os
import sys

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


REGION_A, REGION_B = 10, 20
LOC_A1, LOC_A2, LOC_B1 = 1, 3, 2


@pytest_asyncio.fixture()
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'nb.db'}", poolclass=NullPool)
    async with engine.begin() as conn:
        for m in (models.Country, models.Region, models.District, models.Location,
                  models.LocationNeighbor, models.RegionTransitionArrow, models.ArrowNeighbor):
            await conn.run_sync(m.__table__.create)
        await conn.execute(text("INSERT INTO Countries (id, name, description) VALUES (1, 'C', '')"))
        await conn.execute(text("INSERT INTO Regions (id, name, country_id, description) VALUES "
                                "(10, 'A', 1, ''), (20, 'B', 1, '')"))
        loc = ("INSERT INTO Locations (id, name, district_id, region_id, type, recommended_level, "
               "quick_travel_marker, description, marker_type, sort_order, no_quick_move, is_starting) "
               "VALUES (:i, 'L', NULL, :r, 'location', 1, 0, '', 'safe', 0, 0, 0)")
        for i, r in ((LOC_A1, REGION_A), (LOC_A2, REGION_A), (LOC_B1, REGION_B)):
            await conn.execute(text(loc), {"i": i, "r": r})
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _rows(session, a, b):
    result = await session.execute(
        select(models.LocationNeighbor.energy_cost, models.LocationNeighbor.is_auto_arrow).where(
            models.LocationNeighbor.location_id == a, models.LocationNeighbor.neighbor_id == b
        )
    )
    return [(cost, bool(auto)) for cost, auto in result.all()]


async def _arrow_pair(session):
    created = await crud.create_transition_arrow(
        session, schemas.TransitionArrowCreate(region_id=REGION_A, target_region_id=REGION_B, x=50, y=50)
    )
    return created["arrow"]["id"], created["paired_arrow"]["id"]


async def _link_through_arrows(session, cost_a=5, cost_b=6):
    arrow, paired = await _arrow_pair(session)
    await crud.create_arrow_neighbor(session, arrow, schemas.ArrowNeighborCreate(location_id=LOC_A1, energy_cost=cost_a))
    await crud.create_arrow_neighbor(session, paired, schemas.ArrowNeighborCreate(location_id=LOC_B1, energy_cost=cost_b))
    return arrow, paired


@pytest.mark.asyncio
async def test_editor_save_does_not_copy_arrow_transition(db):
    await _link_through_arrows(db)
    assert await _rows(db, LOC_A1, LOC_B1) == [(11, True)]

    # The old editor sent the arrow pair back with an edited cost, plus a repeated id.
    neighbors = [
        schemas.LocationNeighborCreate(neighbor_id=LOC_B1, energy_cost=8),
        schemas.LocationNeighborCreate(neighbor_id=LOC_A2, energy_cost=4),
        schemas.LocationNeighborCreate(neighbor_id=LOC_A2, energy_cost=5),
    ]
    saved = await crud.update_location_neighbors(db, LOC_A1, neighbors)

    assert saved == [{"neighbor_id": LOC_A2, "energy_cost": 5}]
    assert await _rows(db, LOC_A1, LOC_B1) == [(11, True)]
    assert await _rows(db, LOC_B1, LOC_A1) == [(11, True)]
    assert await _rows(db, LOC_A1, LOC_A2) == [(5, False)]
    assert await _rows(db, LOC_A2, LOC_A1) == [(5, False)]


@pytest.mark.asyncio
async def test_arrow_path_replaces_existing_manual_link(db):
    await crud.add_neighbor(db, LOC_A1, LOC_B1, 3)
    assert await _rows(db, LOC_A1, LOC_B1) == [(3, False)]

    await _link_through_arrows(db)

    assert await _rows(db, LOC_A1, LOC_B1) == [(11, True)]
    assert await _rows(db, LOC_B1, LOC_A1) == [(11, True)]


@pytest.mark.asyncio
async def test_deleting_arrow_path_leaves_no_transition(db):
    arrow, _ = await _link_through_arrows(db)
    await crud.update_location_neighbors(
        db, LOC_A1, [schemas.LocationNeighborCreate(neighbor_id=LOC_B1, energy_cost=8)]
    )

    await crud.delete_arrow_neighbor(db, LOC_A1, arrow)

    assert await _rows(db, LOC_A1, LOC_B1) == []
    assert await _rows(db, LOC_B1, LOC_A1) == []


@pytest.mark.asyncio
async def test_location_details_mark_arrow_transitions(db):
    await _link_through_arrows(db)
    await crud.add_neighbor(db, LOC_A1, LOC_A2, 2)

    details = await crud.get_location_details(db, LOC_A1)

    by_id = {n["neighbor_id"]: n for n in details["neighbors"]}
    assert by_id[LOC_B1] == {"neighbor_id": LOC_B1, "energy_cost": 11, "is_auto_arrow": True}
    assert by_id[LOC_A2] == {"neighbor_id": LOC_A2, "energy_cost": 2, "is_auto_arrow": False}


@pytest.mark.asyncio
async def test_unique_key_refuses_second_row_of_same_direction(db):
    await crud.add_neighbor(db, LOC_A1, LOC_A2, 2)
    db.add(models.LocationNeighbor(location_id=LOC_A1, neighbor_id=LOC_A2, energy_cost=7, is_auto_arrow=True))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


@pytest.mark.asyncio
async def test_unique_key_refuses_second_path_to_same_arrow(db):
    arrow, _ = await _arrow_pair(db)
    db.add(models.ArrowNeighbor(location_id=LOC_A1, arrow_id=arrow, energy_cost=1))
    db.add(models.ArrowNeighbor(location_id=LOC_A1, arrow_id=arrow, energy_cost=2))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ---------------------------------------------------------------------------
# Saving the location form must not straighten drawn roads (prod bug 2026-11-15)
# ---------------------------------------------------------------------------

ROAD = [{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 5.0}]


async def _paths(session, a, b):
    result = await session.execute(
        select(models.LocationNeighbor.path_data).where(
            models.LocationNeighbor.location_id == a, models.LocationNeighbor.neighbor_id == b
        )
    )
    return [row[0] for row in result.all()]


@pytest.mark.asyncio
async def test_editor_save_keeps_drawn_road_and_updates_cost(db):
    await crud.add_neighbor(db, LOC_A1, LOC_A2, 2, path_data=ROAD)

    # The location form sends neighbours without path_data.
    await crud.update_location_neighbors(
        db, LOC_A1, [schemas.LocationNeighborCreate(neighbor_id=LOC_A2, energy_cost=4)]
    )

    assert await _paths(db, LOC_A1, LOC_A2) == [ROAD]
    assert await _paths(db, LOC_A2, LOC_A1) == [ROAD]
    assert await _rows(db, LOC_A1, LOC_A2) == [(4, False)]
    assert await _rows(db, LOC_A2, LOC_A1) == [(4, False)]


@pytest.mark.asyncio
async def test_editor_save_from_the_other_side_keeps_road(db):
    await crud.add_neighbor(db, LOC_A1, LOC_A2, 2, path_data=ROAD)

    await crud.update_location_neighbors(
        db, LOC_A2, [schemas.LocationNeighborCreate(neighbor_id=LOC_A1, energy_cost=2)]
    )

    assert await _paths(db, LOC_A1, LOC_A2) == [ROAD]
    assert await _paths(db, LOC_A2, LOC_A1) == [ROAD]


@pytest.mark.asyncio
async def test_editor_save_drops_only_unlisted_links(db):
    await crud.add_neighbor(db, LOC_A1, LOC_A2, 2, path_data=ROAD)
    await crud.add_neighbor(db, LOC_A1, LOC_B1, 3)

    await crud.update_location_neighbors(
        db, LOC_A1, [schemas.LocationNeighborCreate(neighbor_id=LOC_A2, energy_cost=2)]
    )

    assert await _paths(db, LOC_A1, LOC_A2) == [ROAD]
    assert await _rows(db, LOC_A1, LOC_B1) == []
    assert await _rows(db, LOC_B1, LOC_A1) == []


@pytest.mark.asyncio
async def test_missing_direction_is_restored_with_the_road(db):
    db.add(models.LocationNeighbor(location_id=LOC_A2, neighbor_id=LOC_A1, energy_cost=2, path_data=ROAD))
    await db.commit()

    await crud.update_location_neighbors(
        db, LOC_A1, [schemas.LocationNeighborCreate(neighbor_id=LOC_A2, energy_cost=2)]
    )

    assert await _paths(db, LOC_A1, LOC_A2) == [ROAD]
    assert await _paths(db, LOC_A2, LOC_A1) == [ROAD]
