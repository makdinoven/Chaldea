"""FEAT-213 v2 (T6): sea geography in locations-service — admin validations (§3.12) on a real SQLite DB.

* sea zone / port fields on location create + update (hidden country, not a port / starting / deck, land neighbours,
  unflagging a zone that still has links or serves a port, ``port_sea_zone_id`` rules, null = leave, 0 = clear);
* zone <-> land and deck links refused on every neighbour path: single add, bulk ``/neighbors/update``, path update,
  arrow neighbour; nothing is written on a refusal;
* ``sync_cross_region_neighbors`` skips zone <-> land and deck pairs, keeps land <-> land and zone <-> zone;
* a port on a ship's route can't be unflagged or deleted, a deck can't be deleted, a zone serving a port can;
* ``get_world_graph`` drops sea zones even in a visible country;
* L5 ``/admin/sea-ports`` + L8 ``/admin/sea-zones``: payloads and auth (401 / 403);
* ``sea_read`` without the character-service tables: "no ships", nothing raises;
* security: ids as strings, negative zone id, SQL-injection-like names stored verbatim.
"""
import os
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import main  # noqa: E402
import schemas  # noqa: E402
import sea_read  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from database import get_db  # noqa: E402
from sea_sqlite import (  # noqa: E402
    DECK, DECK2, HIDDEN_LAND, LAND, LAND2, PORT_A, PORT_B, PORT_C, R_COAST, R_INNER_SEA, R_SEA, R_SHIPS,
    SHIP_NAME, SHIP2_NAME, Z1, Z2, Z3, build_world,
)

ADMIN = UserRead(id=1, username="admin", role="admin",
                 permissions=["locations:read", "locations:create", "locations:update", "locations:delete"])
NOBODY = UserRead(id=2, username="player", role="user", permissions=[])


@pytest.fixture()
def world(tmp_path):
    return build_world(tmp_path / "sea.db")


@pytest.fixture()
def bare(tmp_path):
    """The same LS world without the character-service sea tables (deploy skew)."""
    return build_world(tmp_path / "bare.db", with_cs_tables=False)


@pytest.fixture(autouse=True)
def _clean_overrides():
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


def _client(world, user=ADMIN):
    main.app.dependency_overrides[get_db] = world.db_override()
    if user is not None:
        main.app.dependency_overrides[get_current_user_via_http] = lambda: user
    return TestClient(main.app)


def _raises_409(world, coro_fn, detail=None):
    with pytest.raises(HTTPException) as e:
        world.run(coro_fn)
    assert e.value.status_code == 409
    if detail is not None:
        assert e.value.detail == detail
    return e.value.detail


def _update(loc_id, **fields):
    return lambda s: crud.update_location(s, loc_id, schemas.LocationUpdate(**fields))


def _create(**fields):
    base = {"name": "Новая", "region_id": R_SEA}
    base.update(fields)
    return lambda s: crud.create_location(s, schemas.LocationCreate(**base))


# ===========================================================================
# 1. Sea zone flag on create / update
# ===========================================================================

class TestSeaZoneFlag:
    def test_zone_created_in_hidden_country(self, world):
        loc = world.run(_create(name="Пролив Бурь", is_sea_zone=True))
        assert world.loc(loc.id)["is_sea_zone"] is True

    def test_zone_in_visible_country_refused(self, world):
        _raises_409(world, _create(region_id=R_COAST, is_sea_zone=True), crud.SEA_ZONE_NOT_HIDDEN)
        assert world.sql("SELECT COUNT(*) FROM Locations WHERE name = 'Новая'")[0][0] == 0

    def test_zone_cannot_be_port(self, world):
        _raises_409(world, _create(is_sea_zone=True, is_port=True), crud.SEA_ZONE_NOT_PORT)

    def test_zone_cannot_be_starting(self, world):
        _raises_409(world, _create(is_sea_zone=True, is_starting=True), crud.SEA_ZONE_NOT_STARTING)

    def test_flag_hidden_plain_location_as_zone(self, world):
        world.run(_update(HIDDEN_LAND, is_sea_zone=True))
        assert world.loc(HIDDEN_LAND)["is_sea_zone"] is True

    def test_deck_cannot_become_zone(self, world):
        _raises_409(world, _update(DECK, is_sea_zone=True), crud.SEA_ZONE_NOT_DECK.format(name=SHIP_NAME))
        assert world.loc(DECK)["is_sea_zone"] is False

    def test_location_with_land_neighbour_cannot_become_zone(self, world):
        world.link(HIDDEN_LAND, LAND)
        _raises_409(world, _update(HIDDEN_LAND, is_sea_zone=True), crud.SEA_ZONE_LINKS_ONLY_ZONES)
        assert world.loc(HIDDEN_LAND)["is_sea_zone"] is False

    def test_location_with_only_zone_neighbours_becomes_zone(self, world):
        world.link(HIDDEN_LAND, Z1)
        world.run(_update(HIDDEN_LAND, is_sea_zone=True))
        assert world.loc(HIDDEN_LAND)["is_sea_zone"] is True

    def test_existing_zone_in_visible_country_refused_on_move(self, world):
        """Moving a zone to a visible country's region is refused (the hidden-country rule holds on update)."""
        world.sql(f"DELETE FROM LocationNeighbors WHERE location_id = {Z3} OR neighbor_id = {Z3}")
        _raises_409(world, _update(Z3, region_id=R_COAST), crud.SEA_ZONE_NOT_HIDDEN)

    def test_unflag_zone_with_links_refused(self, world):
        _raises_409(world, _update(Z2, is_sea_zone=False), crud.SEA_ZONE_HAS_LINKS)
        assert world.loc(Z2)["is_sea_zone"] is True

    def test_unflag_zone_used_by_port_refused(self, world):
        world.sql(f"DELETE FROM LocationNeighbors WHERE location_id = {Z1} OR neighbor_id = {Z1}")
        detail = _raises_409(world, _update(Z1, is_sea_zone=False))
        assert detail == crud.SEA_ZONE_USED_BY_PORT.format(name="Гавань Рассвета")

    def test_unflag_free_zone(self, world):
        world.run(_update(Z3, is_sea_zone=False))
        assert world.loc(Z3)["is_sea_zone"] is False

    def test_null_flags_leave_as_is(self, world):
        world.run(_update(PORT_A, is_port=None, is_sea_zone=None, port_sea_zone_id=None, name="Гавань"))
        assert world.loc(PORT_A) == {"is_port": True, "is_sea_zone": False, "port_sea_zone_id": Z1, "name": "Гавань"}


# ===========================================================================
# 2. Port fields
# ===========================================================================

class TestPortFields:
    def test_port_created_with_zone(self, world):
        loc = world.run(_create(region_id=R_COAST, is_port=True, port_sea_zone_id=Z2))
        assert world.loc(loc.id)["port_sea_zone_id"] == Z2

    def test_port_zone_must_be_zone(self, world):
        _raises_409(world, _update(PORT_C, port_sea_zone_id=LAND), crud.SEA_PORT_ZONE_NOT_ZONE)
        assert world.loc(PORT_C)["port_sea_zone_id"] is None

    def test_port_zone_unknown_id_refused(self, world):
        _raises_409(world, _update(PORT_C, port_sea_zone_id=99999), crud.SEA_PORT_ZONE_NOT_ZONE)

    def test_zone_only_on_ports(self, world):
        _raises_409(world, _update(LAND, port_sea_zone_id=Z1), crud.SEA_PORT_ZONE_PORTS_ONLY)
        _raises_409(world, _create(region_id=R_COAST, port_sea_zone_id=Z1), crud.SEA_PORT_ZONE_PORTS_ONLY)

    def test_set_and_clear_with_zero(self, world):
        world.run(_update(PORT_C, port_sea_zone_id=Z3))
        assert world.loc(PORT_C)["port_sea_zone_id"] == Z3
        world.run(_update(PORT_C, port_sea_zone_id=0))
        assert world.loc(PORT_C)["port_sea_zone_id"] is None
        assert world.loc(PORT_C)["is_port"] is True

    def test_unflag_free_port_clears_zone(self, world):
        world.run(_update(PORT_C, port_sea_zone_id=Z3))
        world.run(_update(PORT_C, is_port=False))
        assert world.loc(PORT_C) == {"is_port": False, "is_sea_zone": False, "port_sea_zone_id": None,
                                     "name": "Рыбацкая пристань"}

    def test_unflag_port_on_route_refused(self, world):
        _raises_409(world, _update(PORT_B, is_port=False), crud.SEA_PORT_ON_ROUTE.format(name=SHIP_NAME))
        assert world.loc(PORT_B)["is_port"] is True and world.loc(PORT_B)["port_sea_zone_id"] == Z2

    def test_route_check_tolerates_missing_cs_tables(self, bare):
        bare.run(_update(PORT_B, is_port=False))
        assert bare.loc(PORT_B)["is_port"] is False


# ===========================================================================
# 3. Neighbour links (G4): single, bulk, path, arrows
# ===========================================================================

class TestNeighbourLinks:
    def test_zone_to_land_refused(self, world):
        _raises_409(world, lambda s: crud.add_neighbor(s, Z1, LAND, 1), crud.SEA_ZONE_LINKS_ONLY_ZONES)
        _raises_409(world, lambda s: crud.add_neighbor(s, LAND, Z1, 1), crud.SEA_ZONE_LINKS_ONLY_ZONES)
        assert (Z1, LAND) not in world.links(Z1)

    def test_zone_to_zone_allowed(self, world):
        world.run(lambda s: crud.add_neighbor(s, Z2, Z3, 1))
        assert (Z2, Z3) in world.links(Z3) and (Z3, Z2) in world.links(Z3)

    def test_deck_either_side_refused(self, world):
        _raises_409(world, lambda s: crud.add_neighbor(s, DECK, LAND, 1), crud.SEA_DECK_NO_LINKS)
        _raises_409(world, lambda s: crud.add_neighbor(s, PORT_A, DECK2, 1), crud.SEA_DECK_NO_LINKS)
        assert world.links(DECK) == [] and world.links(DECK2) == []

    def test_bulk_update_with_one_zone_refused_whole(self, world):
        before = world.links(LAND)
        neighbors = [schemas.LocationNeighborCreate(neighbor_id=LAND2, energy_cost=9),
                     schemas.LocationNeighborCreate(neighbor_id=Z1, energy_cost=1)]
        _raises_409(world, lambda s: crud.update_location_neighbors(s, LAND, neighbors),
                    crud.SEA_ZONE_LINKS_ONLY_ZONES)
        assert world.links(LAND) == before
        assert world.sql(f"SELECT energy_cost FROM LocationNeighbors WHERE location_id={LAND} "
                         f"AND neighbor_id={LAND2}")[0][0] == 2

    def test_bulk_update_on_deck_refused(self, world):
        neighbors = [schemas.LocationNeighborCreate(neighbor_id=PORT_A, energy_cost=0)]
        _raises_409(world, lambda s: crud.update_location_neighbors(s, DECK, neighbors), crud.SEA_DECK_NO_LINKS)
        assert world.links(DECK) == []

    def test_bulk_update_zone_list_of_zones_ok(self, world):
        neighbors = [schemas.LocationNeighborCreate(neighbor_id=Z2, energy_cost=1),
                     schemas.LocationNeighborCreate(neighbor_id=Z3, energy_cost=1)]
        world.run(lambda s: crud.update_location_neighbors(s, Z1, neighbors))
        assert {b for a, b in world.links(Z1) if a == Z1} == {Z2, Z3}

    def test_bulk_update_empty_list_on_deck_is_harmless(self, world):
        assert world.run(lambda s: crud.update_location_neighbors(s, DECK, [])) == []

    def test_path_update_refused_for_mixed_pair(self, world):
        # a mixed row slipped in before FEAT-213 (raw insert): its path can't be edited either
        world.link(Z1, LAND)
        _raises_409(world, lambda s: crud.update_neighbor_path(s, Z1, LAND, [{"x": 1, "y": 2}]),
                    crud.SEA_ZONE_LINKS_ONLY_ZONES)

    def test_path_update_land_pair_ok(self, world):
        out = world.run(lambda s: crud.update_neighbor_path(s, LAND, LAND2, [{"x": 1, "y": 2}]))
        assert out is not None

    def test_arrow_neighbor_with_deck_refused(self, world):
        arrow = world.run(lambda s: crud.create_transition_arrow(
            s, schemas.TransitionArrowCreate(region_id=R_SHIPS, target_region_id=R_COAST, x=1, y=1)))
        arrow_id = arrow["arrow"]["id"]
        _raises_409(world, lambda s: crud.create_arrow_neighbor(
            s, arrow_id, schemas.ArrowNeighborCreate(location_id=DECK, energy_cost=1)), crud.SEA_DECK_NO_LINKS)
        assert world.sql("SELECT COUNT(*) FROM arrow_neighbors")[0][0] == 0


# ===========================================================================
# 4. Arrow sync skips mixed pairs
# ===========================================================================

def _arrow(world, region, target):
    created = world.run(lambda s: crud.create_transition_arrow(
        s, schemas.TransitionArrowCreate(region_id=region, target_region_id=target, x=5, y=5)))
    return created["arrow"]["id"], created["paired_arrow"]["id"]


def _attach(world, arrow_id, loc_id, cost=1):
    world.run(lambda s: crud.create_arrow_neighbor(s, arrow_id, schemas.ArrowNeighborCreate(
        location_id=loc_id, energy_cost=cost)))


class TestArrowSync:
    def test_zone_vs_land_pair_skipped_land_pair_kept(self, world):
        a, b = _arrow(world, R_SEA, R_COAST)
        _attach(world, a, Z1)
        _attach(world, b, LAND2)
        assert (Z1, LAND2) not in world.links(Z1)
        # a land location on the sea side of the arrow still links to the land side
        world.sql(f"UPDATE Locations SET region_id = {R_SEA} WHERE id = {HIDDEN_LAND}")
        _attach(world, a, HIDDEN_LAND)
        links = world.links(LAND2)
        assert (HIDDEN_LAND, LAND2) in links and (LAND2, HIDDEN_LAND) in links
        assert (Z1, LAND2) not in links and (LAND2, Z1) not in links

    def test_zone_to_zone_between_seas(self, world):
        a, b = _arrow(world, R_SEA, R_INNER_SEA)
        _attach(world, a, Z2, cost=1)
        _attach(world, b, Z3, cost=2)
        rows = world.sql(f"SELECT energy_cost, is_auto_arrow FROM LocationNeighbors "
                         f"WHERE location_id = {Z2} AND neighbor_id = {Z3}")
        assert rows == [(3, 1)]

    def test_deck_pair_skipped(self, world):
        a, b = _arrow(world, R_SHIPS, R_COAST)
        # a deck arrow neighbour can only exist through a raw write (create_arrow_neighbor refuses it)
        world.sql(f"INSERT INTO arrow_neighbors (location_id, arrow_id, energy_cost) VALUES ({DECK}, {a}, 0)")
        world.sql(f"INSERT INTO arrow_neighbors (location_id, arrow_id, energy_cost) VALUES ({HIDDEN_LAND}, {a}, 0)")
        _attach(world, b, LAND)

        async def sync(s):
            await crud.sync_cross_region_neighbors(s, a)
            await s.commit()
        world.run(sync)
        assert world.links(DECK) == []
        assert (HIDDEN_LAND, LAND) in world.links(LAND)

    def test_sync_without_cs_tables_still_links(self, bare):
        a, b = _arrow(bare, R_SEA, R_COAST)
        bare.sql(f"UPDATE Locations SET region_id = {R_SEA} WHERE id = {HIDDEN_LAND}")
        _attach(bare, a, HIDDEN_LAND)
        _attach(bare, b, LAND2)
        assert (HIDDEN_LAND, LAND2) in bare.links(LAND2)


# ===========================================================================
# 5. Delete refusals
# ===========================================================================

class TestDeleteRefusals:
    def test_deck_delete_refused(self, world):
        _raises_409(world, lambda s: crud.check_location_deletable(s, DECK),
                    crud.SEA_DECK_DELETE.format(name=SHIP_NAME))
        _raises_409(world, lambda s: crud.check_location_deletable(s, DECK2),
                    crud.SEA_DECK_DELETE.format(name=SHIP2_NAME))

    def test_port_on_route_delete_refused(self, world):
        _raises_409(world, lambda s: crud.check_location_deletable(s, PORT_A),
                    crud.SEA_PORT_ON_ROUTE.format(name=SHIP_NAME))

    @pytest.mark.parametrize("loc_id", [PORT_C, LAND, Z1], ids=["port_off_route", "land", "zone_used_by_port"])
    def test_other_locations_deletable(self, world, loc_id):
        assert world.run(lambda s: crud.check_location_deletable(s, loc_id)) is None

    def test_missing_cs_tables_mean_deletable(self, bare):
        assert bare.run(lambda s: crud.check_location_deletable(s, DECK)) is None

    def test_delete_route_returns_409_and_keeps_rows(self, world):
        r = _client(world).delete(f"/locations/{DECK}/delete")
        assert r.status_code == 409 and r.json()["detail"] == crud.SEA_DECK_DELETE.format(name=SHIP_NAME)
        r = _client(world).delete(f"/locations/{PORT_B}/delete")
        assert r.status_code == 409 and SHIP_NAME in r.json()["detail"]
        assert world.loc(DECK) is not None and world.loc(PORT_B) is not None


# ===========================================================================
# 6. Admin routes surface the 409s
# ===========================================================================

class TestAdminRoutes:
    def test_create_zone_route(self, world):
        r = _client(world).post("/locations/", json={"name": "Пролив", "region_id": R_SEA, "is_sea_zone": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_sea_zone"] is True and body["is_port"] is False and body["port_sea_zone_id"] is None

    def test_create_zone_in_visible_country_route_409(self, world):
        r = _client(world).post("/locations/", json={"name": "Пролив", "region_id": R_COAST, "is_sea_zone": True})
        assert r.status_code == 409 and r.json()["detail"] == crud.SEA_ZONE_NOT_HIDDEN

    def test_update_route_409_and_payload(self, world):
        c = _client(world)
        r = c.put(f"/locations/{PORT_B}/update", json={"is_port": False})
        assert r.status_code == 409 and r.json()["detail"] == crud.SEA_PORT_ON_ROUTE.format(name=SHIP_NAME)
        r = c.put(f"/locations/{PORT_C}/update", json={"port_sea_zone_id": Z3})
        assert r.status_code == 200, r.text
        assert r.json()["port_sea_zone_id"] == Z3 and r.json()["is_port"] is True

    def test_neighbor_route_409(self, world):
        r = _client(world).post(f"/locations/{Z1}/neighbors/", json={"neighbor_id": LAND, "energy_cost": 1})
        assert r.status_code == 409 and r.json()["detail"] == crud.SEA_ZONE_LINKS_ONLY_ZONES

    def test_bulk_neighbors_route_409(self, world):
        r = _client(world).post(f"/locations/{DECK}/neighbors/update",
                                json={"neighbors": [{"neighbor_id": PORT_A, "energy_cost": 0}]})
        assert r.status_code == 409 and r.json()["detail"] == crud.SEA_DECK_NO_LINKS

    def test_path_route_409(self, world):
        world.link(Z1, LAND)
        r = _client(world).put(f"/locations/neighbors/{Z1}/{LAND}/path", json={"path_data": [{"x": 1, "y": 1}]})
        assert r.status_code == 409

    def test_arrow_neighbor_route_409(self, world):
        a, _ = _arrow(world, R_SHIPS, R_COAST)
        r = _client(world).post(f"/locations/arrows/{a}/neighbors/", json={"location_id": DECK, "energy_cost": 0})
        assert r.status_code == 409 and r.json()["detail"] == crud.SEA_DECK_NO_LINKS


# ===========================================================================
# 7. World graph
# ===========================================================================

class TestWorldGraph:
    def test_zone_dropped_even_in_visible_country(self, world):
        # defence: a zone that slipped into a visible country (raw write) is still not on the map
        world.sql(f"UPDATE Locations SET region_id = {R_COAST} WHERE id = {Z1}")
        world.link(LAND2, Z1)
        graph = world.run(crud.get_world_graph)
        ids = {n["id"] for n in graph["locations"]}
        assert Z1 not in ids and Z2 not in ids
        assert {PORT_A, LAND, LAND2}.issubset(ids)
        assert all(Z1 not in (e["a"], e["b"]) for e in graph["edges"])
        assert all(n["is_sea_zone"] is False for n in graph["locations"])
        port = next(n for n in graph["locations"] if n["id"] == PORT_A)
        assert port["is_port"] is True and port["port_sea_zone_id"] == Z1

    def test_hidden_country_locations_absent(self, world):
        ids = {n["id"] for n in world.run(crud.get_world_graph)["locations"]}
        assert not ids & {DECK, DECK2, HIDDEN_LAND, Z3}


# ===========================================================================
# 8. L5 / L8
# ===========================================================================

class TestSeaListings:
    def test_l5_ports(self, world):
        r = _client(world).get("/locations/admin/sea-ports")
        assert r.status_code == 200, r.text
        rows = {p["id"]: p for p in r.json()}
        assert set(rows) == {PORT_A, PORT_B, PORT_C}
        assert rows[PORT_A]["port_sea_zone_id"] == Z1 and rows[PORT_A]["port_sea_zone_name"] == "Пролив Ветров"
        assert rows[PORT_A]["region_name"] == "Побережье" and rows[PORT_A]["country_name"] == "Земля"
        assert rows[PORT_C]["port_sea_zone_id"] is None and rows[PORT_C]["port_sea_zone_name"] is None
        assert set(rows[PORT_A]) == set(schemas.SeaPortRead.__fields__)

    def test_l8_zones(self, world):
        world.link(Z2, Z3)
        r = _client(world).get("/locations/admin/sea-zones")
        assert r.status_code == 200, r.text
        rows = {z["id"]: z for z in r.json()}
        assert set(rows) == {Z1, Z2, Z3}
        assert rows[Z1]["neighbor_ids"] == [Z2]
        assert rows[Z2]["neighbor_ids"] == [Z1, Z3]
        assert rows[Z3]["region_name"] == "Внутреннее море" and rows[Z3]["country_name"] == "Моря"
        assert rows[Z1]["region_id"] == R_SEA

    def test_l8_neighbour_ids_only_zones(self, world):
        world.link(Z1, LAND)  # raw mixed row (pre-FEAT-213 data) is not a zone neighbour
        rows = {z["id"]: z for z in world.run(crud.list_sea_zones)}
        assert rows[Z1]["neighbor_ids"] == [Z2]

    def test_l8_empty(self, world):
        world.sql("UPDATE Locations SET is_sea_zone = 0")
        assert world.run(crud.list_sea_zones) == []

    @pytest.mark.parametrize("path", ["/locations/admin/sea-ports", "/locations/admin/sea-zones"])
    def test_anonymous_401(self, world, path):
        r = _client(world, user=None).get(path)
        assert r.status_code == 401

    @pytest.mark.parametrize("path", ["/locations/admin/sea-ports", "/locations/admin/sea-zones"])
    def test_without_permission_403(self, world, path):
        r = _client(world, user=NOBODY).get(path)
        assert r.status_code == 403

    @pytest.mark.parametrize("path", ["/locations/admin/sea-ports", "/locations/admin/sea-zones"])
    def test_read_permission_is_enough(self, world, path):
        reader = UserRead(id=3, username="ed", role="editor", permissions=["locations:read"])
        assert _client(world, user=reader).get(path).status_code == 200

    @pytest.mark.parametrize("path", ["/locations/admin/sea-ports", "/locations/admin/sea-zones"])
    def test_invalid_token_401(self, world, path):
        main.app.dependency_overrides[get_db] = world.db_override()
        with patch("auth_http.requests.get") as g:
            g.return_value.status_code = 401
            r = TestClient(main.app).get(path, headers={"Authorization": "Bearer bad"})
        assert r.status_code == 401


# ===========================================================================
# 9. sea_read tolerance
# ===========================================================================

class TestSeaReadTolerance:
    def test_missing_tables_mean_no_ships(self, bare):
        async def go(s):
            return (await sea_read.ships_by_decks(s, [DECK, DECK2]),
                    await sea_read.ship_by_deck(s, DECK),
                    await sea_read.ships_docked_at(s, PORT_A),
                    await sea_read.ships_stopping_at(s, [PORT_A]),
                    await sea_read.passage(s, 100, PORT_A, DECK),
                    await sea_read.passages_for(s, PORT_A, 100))
        by_deck, one, docked, stopping, passage, sea = bare.run(go)
        assert by_deck == {} and one is None and docked == [] and stopping == [] and passage is None
        assert sea.ship_id is None and sea.board == [] and sea.disembark == [] and sea.docked_ships == []

    def test_session_still_usable_after_failed_read(self, bare):
        async def go(s):
            await sea_read.ships_by_decks(s, [DECK])
            return (await s.execute(text("SELECT COUNT(*) FROM Locations"))).scalar()
        assert bare.run(go) == 11

    def test_empty_ids_read_nothing(self, world):
        async def go(s):
            return (await sea_read.ships_by_decks(s, []), await sea_read.ships_stopping_at(s, [None]))
        assert world.run(go) == ({}, [])

    def test_warning_logged(self, bare, caplog):
        with caplog.at_level("WARNING", logger="sea_read"):
            bare.run(lambda s: sea_read.ships_by_decks(s, [DECK]))
        assert any("treated as no ships" in r.getMessage() for r in caplog.records)


# ===========================================================================
# 10. Security
# ===========================================================================

class TestSecurity:
    INJECTION = "'; DROP TABLE Locations; --"

    def test_injection_like_zone_name_stored_verbatim(self, world):
        loc = world.run(_create(name=self.INJECTION, is_sea_zone=True))
        assert world.loc(loc.id)["name"] == self.INJECTION
        assert world.sql("SELECT COUNT(*) FROM Locations")[0][0] == 12
        names = {z["name"] for z in world.run(crud.list_sea_zones)}
        assert self.INJECTION in names

    def test_injection_like_ship_name_in_refusal(self, world):
        world.sql("UPDATE sea_ships SET name = :n WHERE id = 1", n=self.INJECTION)
        _raises_409(world, lambda s: crud.check_location_deletable(s, DECK),
                    crud.SEA_DECK_DELETE.format(name=self.INJECTION))
        assert world.sql("SELECT COUNT(*) FROM Locations")[0][0] == 11

    def test_string_ids_422(self, world):
        c = _client(world)
        assert c.put(f"/locations/{PORT_C}/update", json={"port_sea_zone_id": "abc"}).status_code == 422
        assert c.post("/locations/abc/neighbors/", json={"neighbor_id": Z1}).status_code == 422
        assert c.post(f"/locations/{Z1}/neighbors/", json={"neighbor_id": "1 OR 1=1"}).status_code == 422
        assert c.delete("/locations/1;DROP/delete").status_code in (404, 422)

    def test_negative_zone_id_422(self, world):
        r = _client(world).put(f"/locations/{PORT_C}/update", json={"port_sea_zone_id": -5})
        assert r.status_code == 422
        assert world.loc(PORT_C)["port_sea_zone_id"] is None

    def test_zone_flag_needs_update_permission(self, world):
        reader = UserRead(id=3, username="ed", role="editor", permissions=["locations:read"])
        r = _client(world, user=reader).put(f"/locations/{HIDDEN_LAND}/update", json={"is_sea_zone": True})
        assert r.status_code == 403
        assert world.loc(HIDDEN_LAND)["is_sea_zone"] is False
