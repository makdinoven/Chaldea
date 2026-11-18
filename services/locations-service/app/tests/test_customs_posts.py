"""FEAT-216 (T12): customs posts («Таможня») in locations-service — ``Locations.is_customs`` on a real SQLite DB.

* the flag round-trips through admin create / update (crud + routes) and every read payload that carries
  ``is_port``: location details, region details, client details, world map graph;
* null on create = "not a post", explicit null on update = leave as is (crud and route);
* validation (400, ``crud.CUSTOMS_NOT_AT_SEA``): flagging a sea zone or a ship's deck, creating a customs sea zone,
  turning a customs post into a sea zone; nothing is written on a refusal; unflagging is always allowed;
* migration ``061_customs_posts``: revision id <= 32 chars, revises ``060_sea_zones``, single head of the chain.
"""
import os
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import main  # noqa: E402
import schemas  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from database import get_db  # noqa: E402
from sea_sqlite import (  # noqa: E402
    DECK, HIDDEN_LAND, LAND, LAND2, PORT_A, R_COAST, R_SEA, Z1, build_world,
)

ADMIN = UserRead(id=1, username="admin", role="admin",
                 permissions=["locations:read", "locations:create", "locations:update", "locations:delete"])

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"
CUSTOMS_REVISION = "061_customs_posts"
PREV_REVISION = "060_sea_zones"
MAX_REVISION_LEN = 32  # MySQL alembic_version.version_num is VARCHAR(32)


@pytest.fixture()
def world(tmp_path):
    return build_world(tmp_path / "customs.db")


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


def _customs(world, loc_id):
    rows = world.sql("SELECT is_customs FROM Locations WHERE id = :i", i=loc_id)
    return bool(rows[0][0])


def _flag(world, loc_id, value=True):
    world.sql("UPDATE Locations SET is_customs = :v WHERE id = :i", v=1 if value else 0, i=loc_id)


def _update(loc_id, **fields):
    return lambda s: crud.update_location(s, loc_id, schemas.LocationUpdate(**fields))


def _create(**fields):
    base = {"name": "Застава", "region_id": R_COAST}
    base.update(fields)
    return lambda s: crud.create_location(s, schemas.LocationCreate(**base))


def _raises_400(world, coro_fn):
    with pytest.raises(HTTPException) as e:
        world.run(coro_fn)
    assert e.value.status_code == 400
    assert e.value.detail == crud.CUSTOMS_NOT_AT_SEA


# ===========================================================================
# 1. Create / update (crud)
# ===========================================================================

class TestCreateUpdate:
    def test_column_defaults_to_false(self, world):
        assert all(not bool(r[0]) for r in world.sql("SELECT is_customs FROM Locations"))

    def test_create_with_flag(self, world):
        loc = world.run(_create(is_customs=True))
        assert _customs(world, loc.id) is True

    def test_create_without_flag_is_not_a_post(self, world):
        loc = world.run(_create())
        assert _customs(world, loc.id) is False

    def test_create_with_null_is_not_a_post(self, world):
        loc = world.run(_create(is_customs=None))
        assert _customs(world, loc.id) is False

    def test_update_sets_and_clears(self, world):
        world.run(_update(LAND, is_customs=True))
        assert _customs(world, LAND) is True
        world.run(_update(LAND, is_customs=False))
        assert _customs(world, LAND) is False

    def test_explicit_null_keeps_value(self, world):
        _flag(world, LAND)
        world.run(_update(LAND, is_customs=None, name="Застава у тракта"))
        assert _customs(world, LAND) is True
        assert world.loc(LAND)["name"] == "Застава у тракта"

    def test_unrelated_update_keeps_value(self, world):
        _flag(world, LAND)
        world.run(_update(LAND, description="Новое описание"))
        assert _customs(world, LAND) is True

    def test_port_can_be_customs(self, world):
        world.run(_update(PORT_A, is_customs=True))
        assert _customs(world, PORT_A) is True
        assert world.loc(PORT_A)["is_port"] is True

    def test_plain_location_of_hidden_country_can_be_customs(self, world):
        world.run(_update(HIDDEN_LAND, is_customs=True))
        assert _customs(world, HIDDEN_LAND) is True


# ===========================================================================
# 2. Validation: never at sea
# ===========================================================================

class TestNotAtSea:
    def test_sea_zone_refused(self, world):
        _raises_400(world, _update(Z1, is_customs=True))
        assert _customs(world, Z1) is False

    def test_deck_refused(self, world):
        _raises_400(world, _update(DECK, is_customs=True))
        assert _customs(world, DECK) is False

    def test_create_customs_sea_zone_refused(self, world):
        _raises_400(world, _create(name="Пролив", region_id=R_SEA, is_sea_zone=True, is_customs=True))
        assert world.sql("SELECT COUNT(*) FROM Locations WHERE name = 'Пролив'")[0][0] == 0

    def test_customs_post_cannot_become_sea_zone(self, world):
        _flag(world, HIDDEN_LAND)
        _raises_400(world, _update(HIDDEN_LAND, is_sea_zone=True))
        assert world.loc(HIDDEN_LAND)["is_sea_zone"] is False
        assert _customs(world, HIDDEN_LAND) is True

    def test_unflag_and_zone_in_one_request_allowed(self, world):
        _flag(world, HIDDEN_LAND)
        world.run(_update(HIDDEN_LAND, is_customs=False, is_sea_zone=True))
        assert _customs(world, HIDDEN_LAND) is False
        assert world.loc(HIDDEN_LAND)["is_sea_zone"] is True

    def test_unflag_on_deck_allowed(self, world):
        """A raw-written flag on a deck (defence) can always be cleared."""
        _flag(world, DECK)
        world.run(_update(DECK, is_customs=False))
        assert _customs(world, DECK) is False

    def test_null_on_zone_is_harmless(self, world):
        world.run(_update(Z1, is_customs=None, name="Пролив Ветров"))
        assert _customs(world, Z1) is False


# ===========================================================================
# 3. Admin routes
# ===========================================================================

class TestAdminRoutes:
    def test_create_route_returns_flag(self, world):
        r = _client(world).post("/locations/", json={"name": "Застава", "region_id": R_COAST, "is_customs": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_customs"] is True
        assert _customs(world, body["id"]) is True

    def test_create_route_default_false(self, world):
        r = _client(world).post("/locations/", json={"name": "Застава", "region_id": R_COAST})
        assert r.status_code == 200, r.text
        assert r.json()["is_customs"] is False

    def test_update_route_returns_flag(self, world):
        c = _client(world)
        r = c.put(f"/locations/{LAND}/update", json={"is_customs": True})
        assert r.status_code == 200, r.text
        assert r.json()["is_customs"] is True
        r = c.put(f"/locations/{LAND}/update", json={"is_customs": None, "name": "Застава"})
        assert r.status_code == 200, r.text
        assert r.json()["is_customs"] is True

    def test_update_route_zone_400(self, world):
        r = _client(world).put(f"/locations/{Z1}/update", json={"is_customs": True})
        assert r.status_code == 400
        assert r.json()["detail"] == crud.CUSTOMS_NOT_AT_SEA

    def test_update_route_deck_400(self, world):
        r = _client(world).put(f"/locations/{DECK}/update", json={"is_customs": True})
        assert r.status_code == 400
        assert r.json()["detail"] == crud.CUSTOMS_NOT_AT_SEA
        assert _customs(world, DECK) is False

    def test_create_route_zone_400(self, world):
        r = _client(world).post("/locations/", json={"name": "Пролив", "region_id": R_SEA,
                                                     "is_sea_zone": True, "is_customs": True})
        assert r.status_code == 400
        assert r.json()["detail"] == crud.CUSTOMS_NOT_AT_SEA

    def test_flag_needs_update_permission(self, world):
        nobody = UserRead(id=2, username="player", role="user", permissions=[])
        r = _client(world, nobody).put(f"/locations/{LAND}/update", json={"is_customs": True})
        assert r.status_code == 403
        assert _customs(world, LAND) is False

    def test_string_flag_422(self, world):
        r = _client(world).put(f"/locations/{LAND}/update", json={"is_customs": "таможня"})
        assert r.status_code == 422
        assert _customs(world, LAND) is False


# ===========================================================================
# 4. Read payloads
# ===========================================================================

def _no_side_reads():
    """Patch the client-details helpers that hit other services / tables absent from the sea world."""
    names = {
        "get_players_in_location": [], "get_npcs_in_location": [], "get_posts_by_location": [],
        "get_likes_for_posts": {}, "gates_for_posts": {}, "pending_gates_for_posts": {},
        "get_location_loot": [], "is_favorited": False, "lazy_restore_depleted_nodes": None,
        "fetch_gathering_nodes_with_active_sessions": [],
    }
    patches = [patch.object(crud, n, AsyncMock(return_value=v)) for n, v in names.items()]
    patches.append(patch.object(crud.faction_read, "access_marks", AsyncMock(return_value={})))
    return patches


class TestReadPayloads:
    def test_location_details(self, world):
        _flag(world, LAND)
        c = _client(world)
        assert c.get(f"/locations/{LAND}/details").json()["is_customs"] is True
        assert c.get(f"/locations/{LAND2}/details").json()["is_customs"] is False

    def test_region_details(self, world):
        """The sea world has no districts: the region's entrance location carries the location dict."""
        _flag(world, LAND)
        world.sql(f"UPDATE Regions SET entrance_location_id = {LAND} WHERE id = {R_COAST}")
        world.sql(f"UPDATE Regions SET entrance_location_id = {LAND2} WHERE id = {R_SEA}")
        world.sql(f"UPDATE Locations SET region_id = {R_SEA} WHERE id = {LAND2}")
        data = world.run(lambda s: crud.get_region_full_details(s, R_COAST))
        assert data["entrance_location"]["id"] == LAND and data["entrance_location"]["is_customs"] is True
        data = world.run(lambda s: crud.get_region_full_details(s, R_SEA))
        assert data["entrance_location"]["id"] == LAND2 and data["entrance_location"]["is_customs"] is False

    def test_client_details(self, world):
        _flag(world, LAND)
        patches = _no_side_reads()
        for p in patches:
            p.start()
        try:
            data = world.run(lambda s: crud.get_client_location_details(s, LAND))
            other = world.run(lambda s: crud.get_client_location_details(s, LAND2))
        finally:
            for p in patches:
                p.stop()
        assert data["is_customs"] is True and other["is_customs"] is False
        # the payload passes the response model with the flag intact
        assert schemas.LocationClientDetails(**data).is_customs is True

    def test_world_graph(self, world):
        _flag(world, LAND)
        graph = world.run(crud.get_world_graph)
        nodes = {n["id"]: n for n in graph["locations"]}
        assert nodes[LAND]["is_customs"] is True
        assert nodes[LAND2]["is_customs"] is False
        assert nodes[PORT_A]["is_customs"] is False


# ===========================================================================
# 5. Migration 061
# ===========================================================================

def _revisions():
    out = {}
    for f in VERSIONS_DIR.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", src, re.M)
        down = re.search(r"^down_revision\s*=\s*(.+)$", src, re.M)
        if rev:
            out[rev.group(1)] = (f.name, re.findall(r"['\"]([^'\"]+)['\"]", down.group(1)) if down else [])
    return out


class TestMigration:
    def test_revision_id_and_parent(self):
        revs = _revisions()
        assert CUSTOMS_REVISION in revs
        assert len(CUSTOMS_REVISION) <= MAX_REVISION_LEN
        assert revs[CUSTOMS_REVISION][1] == [PREV_REVISION]

    def test_all_revision_ids_fit_alembic_version(self):
        assert all(len(r) <= MAX_REVISION_LEN for r in _revisions())

    def test_only_061_revises_060(self):
        children = [r for r, (_, downs) in _revisions().items() if PREV_REVISION in downs]
        assert children == [CUSTOMS_REVISION]

    def test_single_head(self):
        revs = _revisions()
        parents = {d for _, downs in revs.values() for d in downs}
        heads = [r for r in revs if r not in parents]
        assert heads == [CUSTOMS_REVISION]

    def test_upgrade_and_downgrade_touch_column_and_index(self):
        src = (VERSIONS_DIR / f"{CUSTOMS_REVISION}.py").read_text(encoding="utf-8")
        assert "ix_locations_is_customs" in src and "is_customs" in src
        assert "def downgrade" in src and "drop_column" in src and "drop_index" in src
