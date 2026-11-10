"""
FEAT-209: admin NPC list — country/region filter and the «Готов» (ready) mark.

Covers:
- GET /characters/admin/npcs ?country_id / ?region_id over the Location -> District -> Region -> Country
  hierarchy (district location, nested sub-district, own region_id, child inheriting via parent_id, child with
  its own region NOT inherited), NPC without location excluded, foreign / unknown ids, combination with
  q / npc_role / npc_status / ready / pagination, invalid ids -> 422
- ?ready filter, npc_ready* fields in the admin list and admin detail
- PUT /characters/admin/npcs/{id}/ready: set/unset, idempotent re-set keeps who/when, 404, 422, 401/403
- npc_ready* never appears in public NPC / character responses
- migration 048 module metadata
"""

import importlib.util
import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db
import database
import models


READY_FIELDS = ("npc_ready", "npc_ready_at", "npc_ready_by")

_ADMIN = UserRead(id=1, username="admin_anna", role="admin",
                  permissions=["npcs:read", "npcs:create", "npcs:update", "npcs:delete"])
_OTHER_ADMIN = UserRead(id=3, username="admin_boris", role="admin",
                        permissions=["npcs:read", "npcs:update"])
_READ_ONLY = UserRead(id=2, username="editor", role="editor", permissions=["npcs:read"])

# World layout (ids):
# Country 1: Region 10 (district 100, nested sub-district 101 -> parent 100), Region 11 (district 110)
# Country 2: Region 20 (district 200)
# Locations:
#   1000 in district 100                       -> region 10
#   1001 in nested sub-district 101            -> region 10
#   1002 own region_id=11, no district         -> region 11
#   1003 child of 1000 (no own region)         -> region 10 (inherited)
#   1004 child of 1000, own region_id=20       -> region 20 (NOT inherited)
#   1005 grandchild of 1003 (no own region)    -> region 10 (inherited two levels)
#   2000 in district 200                       -> region 20
#   3000 no district, no region, no parent     -> unresolved
_WORLD_SQL = [
    "INSERT INTO Countries (id, name) VALUES (1, 'Страна-1'), (2, 'Страна-2')",
    "INSERT INTO Regions (id, name, country_id) VALUES (10, 'Регион-10', 1), (11, 'Регион-11', 1), "
    "(20, 'Регион-20', 2)",
    "INSERT INTO Districts (id, name, region_id, parent_district_id) VALUES "
    "(100, 'Район-100', 10, NULL), (101, 'Подрайон-101', 10, 100), (110, 'Район-110', 11, NULL), "
    "(200, 'Район-200', 20, NULL)",
    "INSERT INTO Locations (id, name, district_id, region_id, parent_id) VALUES "
    "(1000, 'Лок-1000', 100, NULL, NULL), (1001, 'Лок-1001', 101, NULL, NULL), "
    "(1002, 'Лок-1002', NULL, 11, NULL), (1003, 'Лок-1003', NULL, NULL, 1000), "
    "(1004, 'Лок-1004', NULL, 20, 1000), (1005, 'Лок-1005', NULL, NULL, 1003), "
    "(2000, 'Лок-2000', 200, NULL, NULL), (3000, 'Лок-3000', NULL, NULL, NULL)",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(test_engine):
    models.Base.metadata.create_all(bind=test_engine)
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


def _install(db_session, user):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        app.dependency_overrides[get_admin_user] = lambda: user
        app.dependency_overrides[get_current_user_via_http] = lambda: user
        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(db_session):
    yield _install(db_session, _ADMIN)
    app.dependency_overrides.clear()


@pytest.fixture
def make_client(db_session):
    def _make(user):
        app.dependency_overrides.clear()
        return _install(db_session, user)

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture
def world(db_session, seed_fk_data):
    seed_fk_data(db_session)
    for sql in _WORLD_SQL:
        db_session.execute(text(sql))
    db_session.commit()
    return db_session


@pytest.fixture
def create_npc(world):
    def _create(name, location_id=None, npc_role="merchant", npc_status="alive", is_npc=True, ready=False):
        npc = models.Character(
            name=name, id_race=1, id_subrace=1, id_class=1, appearance="test", avatar="test.jpg",
            is_npc=is_npc, npc_role=npc_role, npc_status=npc_status, current_location_id=location_id,
            level=1, stat_points=0, currency_balance=0, npc_ready=ready,
        )
        world.add(npc)
        world.commit()
        world.refresh(npc)
        return npc

    return _create


@pytest.fixture
def geo_npcs(create_npc):
    """One NPC per location of the world + one without location + a mob in region 10."""
    for lid in (1000, 1001, 1002, 1003, 1004, 1005, 2000, 3000):
        create_npc(f"НПС-{lid}", location_id=lid)
    create_npc("НПС-без-локации", location_id=None)
    create_npc("Моб-1000", location_id=1000, npc_role="mob")


def _names(resp):
    assert resp.status_code == 200, resp.text
    return {i["name"] for i in resp.json()["items"]}


def _list(client, **params):
    return client.get("/characters/admin/npcs", params={"page_size": 100, **params})


# ============================================================
# 1. Geo filter
# ============================================================


class TestRegionFilter:
    def test_region_includes_district_nested_and_inherited_children(self, client, geo_npcs):
        names = _names(_list(client, region_id=10))
        assert names == {"НПС-1000", "НПС-1001", "НПС-1003", "НПС-1005"}

    def test_child_with_own_region_not_inherited(self, client, geo_npcs):
        names = _names(_list(client, region_id=20))
        assert names == {"НПС-1004", "НПС-2000"}

    def test_location_with_own_region_and_no_district(self, client, geo_npcs):
        assert _names(_list(client, region_id=11)) == {"НПС-1002"}

    def test_mob_and_no_location_excluded(self, client, geo_npcs):
        names = _names(_list(client, region_id=10))
        assert "Моб-1000" not in names
        assert "НПС-без-локации" not in names

    def test_unknown_region_empty(self, client, geo_npcs):
        resp = _list(client, region_id=999)
        assert resp.status_code == 200
        assert resp.json()["items"] == [] and resp.json()["total"] == 0


class TestCountryFilter:
    def test_country_is_union_of_its_regions(self, client, geo_npcs):
        names = _names(_list(client, country_id=1))
        assert names == {"НПС-1000", "НПС-1001", "НПС-1002", "НПС-1003", "НПС-1005"}

    def test_other_country(self, client, geo_npcs):
        assert _names(_list(client, country_id=2)) == {"НПС-1004", "НПС-2000"}

    def test_country_and_own_region_intersection(self, client, geo_npcs):
        assert _names(_list(client, country_id=1, region_id=11)) == {"НПС-1002"}

    def test_region_of_foreign_country_returns_empty(self, client, geo_npcs):
        resp = _list(client, country_id=1, region_id=20)
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0, "page": 1, "page_size": 100}

    def test_unknown_country_empty(self, client, geo_npcs):
        resp = _list(client, country_id=999)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_country_without_regions_empty(self, client, world, geo_npcs):
        world.execute(text("INSERT INTO Countries (id, name) VALUES (3, 'Пустая')"))
        world.commit()
        assert _list(client, country_id=3).json()["total"] == 0

    def test_no_geo_params_returns_all_npcs(self, client, geo_npcs):
        # 8 located NPCs + one without location; the mob is excluded
        assert _list(client).json()["total"] == 9

    @pytest.mark.parametrize("params", [{"country_id": 0}, {"region_id": -1}, {"country_id": "abc"},
                                        {"region_id": "1.5"}, {"ready": "maybe"}])
    def test_invalid_params_422(self, client, geo_npcs, params):
        assert _list(client, **params).status_code == 422


class TestGeoCombinations:
    def test_with_search(self, client, geo_npcs):
        assert _names(_list(client, region_id=10, q="1003")) == {"НПС-1003"}

    def test_with_role(self, client, create_npc, geo_npcs):
        create_npc("Стражник-1001", location_id=1001, npc_role="guard")
        create_npc("Стражник-2000", location_id=2000, npc_role="guard")
        assert _names(_list(client, country_id=1, npc_role="guard")) == {"Стражник-1001"}

    def test_with_status(self, client, create_npc, geo_npcs):
        create_npc("Мёртвый-1005", location_id=1005, npc_status="dead")
        assert _names(_list(client, region_id=10, npc_status="dead")) == {"Мёртвый-1005"}

    def test_with_location_id(self, client, geo_npcs):
        assert _names(_list(client, region_id=10, location_id=1003)) == {"НПС-1003"}
        assert _names(_list(client, region_id=10, location_id=2000)) == set()

    def test_with_ready(self, client, create_npc, geo_npcs):
        create_npc("Готовый-1000", location_id=1000, ready=True)
        create_npc("Готовый-2000", location_id=2000, ready=True)
        assert _names(_list(client, region_id=10, ready=1)) == {"Готовый-1000"}
        not_ready = _names(_list(client, region_id=10, ready=0))
        assert not_ready == {"НПС-1000", "НПС-1001", "НПС-1003", "НПС-1005"}

    def test_pagination_total(self, client, geo_npcs):
        first = client.get("/characters/admin/npcs", params={"country_id": 1, "page": 1, "page_size": 2}).json()
        third = client.get("/characters/admin/npcs", params={"country_id": 1, "page": 3, "page_size": 2}).json()
        assert first["total"] == 5 and len(first["items"]) == 2
        assert third["total"] == 5 and len(third["items"]) == 1
        ids = [i["id"] for i in first["items"]]
        assert ids == sorted(ids)

    def test_items_carry_location_name(self, client, geo_npcs):
        items = _list(client, region_id=11).json()["items"]
        assert items[0]["location_name"] == "Лок-1002"


# ============================================================
# 2. Ready filter + fields
# ============================================================


class TestReadyFilterAndFields:
    def test_ready_filter(self, client, create_npc):
        create_npc("Готов", ready=True)
        create_npc("Не готов")
        create_npc("Готовый моб", npc_role="mob", ready=True)
        assert _names(_list(client, ready="true")) == {"Готов"}
        assert _names(_list(client, ready="false")) == {"Не готов"}
        assert _names(_list(client)) == {"Готов", "Не готов"}

    def test_list_items_expose_ready_fields(self, client, create_npc):
        create_npc("НПС")
        item = _list(client).json()["items"][0]
        for f in READY_FIELDS:
            assert f in item
        assert item["npc_ready"] is False
        assert item["npc_ready_at"] is None and item["npc_ready_by"] is None

    def test_detail_exposes_ready_fields(self, client, create_npc):
        npc = create_npc("НПС")
        client.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True})
        body = client.get(f"/characters/admin/npcs/{npc.id}").json()
        assert body["npc_ready"] is True
        assert body["npc_ready_by"] == "admin_anna"
        assert body["npc_ready_at"] is not None


# ============================================================
# 3. PUT /admin/npcs/{id}/ready
# ============================================================


class TestReadyToggle:
    def test_set_records_who_and_when(self, client, create_npc, db_session):
        npc = create_npc("НПС")
        before = datetime.utcnow().replace(microsecond=0)
        resp = client.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == npc.id and body["npc_ready"] is True
        assert body["npc_ready_by"] == "admin_anna"
        at = datetime.fromisoformat(body["npc_ready_at"])
        assert before <= at.replace(microsecond=0) <= datetime.utcnow()
        db_session.expire_all()
        row = db_session.get(models.Character, npc.id)
        assert row.npc_ready is True and row.npc_ready_by == "admin_anna"
        assert _list(client).json()["items"][0]["npc_ready"] is True

    def test_unset_clears_who_and_when(self, client, create_npc):
        npc = create_npc("НПС")
        client.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True})
        resp = client.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": False})
        assert resp.status_code == 200
        assert resp.json() == {"id": npc.id, "npc_ready": False, "npc_ready_at": None, "npc_ready_by": None}
        # unset again is a no-op
        again = client.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": False})
        assert again.status_code == 200 and again.json()["npc_ready"] is False

    def test_reset_true_is_idempotent_and_keeps_original(self, make_client, create_npc):
        npc = create_npc("НПС")
        first = make_client(_ADMIN).put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True}).json()
        second = make_client(_OTHER_ADMIN).put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True})
        assert second.status_code == 200
        assert second.json() == first
        assert second.json()["npc_ready_by"] == "admin_anna"

    def test_works_for_dead_and_null_role_npc(self, client, create_npc):
        dead = create_npc("Мёртвый", npc_status="dead")
        plain = create_npc("Без роли", npc_role=None)
        for npc in (dead, plain):
            resp = client.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True})
            assert resp.status_code == 200 and resp.json()["npc_ready"] is True

    def test_mob_404(self, client, create_npc):
        mob = create_npc("Моб", npc_role="mob")
        resp = client.put(f"/characters/admin/npcs/{mob.id}/ready", json={"ready": True})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "NPC не найден"

    def test_player_character_404(self, client, create_npc):
        player = create_npc("Игрок", is_npc=False, npc_role=None)
        assert client.put(f"/characters/admin/npcs/{player.id}/ready", json={"ready": True}).status_code == 404

    def test_missing_404(self, client, world):
        assert client.put("/characters/admin/npcs/987654/ready", json={"ready": True}).status_code == 404

    @pytest.mark.parametrize("body", [{}, {"ready": "maybe"}, {"ready": True, "extra": 1}, None])
    def test_bad_body_422(self, client, create_npc, body):
        npc = create_npc("НПС")
        if body is None:
            resp = client.put(f"/characters/admin/npcs/{npc.id}/ready")
        else:
            resp = client.put(f"/characters/admin/npcs/{npc.id}/ready", json=body)
        assert resp.status_code == 422

    def test_read_only_user_403_but_can_list(self, make_client, create_npc):
        npc = create_npc("НПС")
        c = make_client(_READ_ONLY)
        assert c.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True}).status_code == 403
        assert c.get("/characters/admin/npcs", params={"ready": 0}).status_code == 200

    def test_no_permissions_403(self, make_client, create_npc):
        npc = create_npc("НПС")
        c = make_client(UserRead(id=9, username="player", role="user", permissions=[]))
        assert c.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True}).status_code == 403
        assert c.get("/characters/admin/npcs", params={"region_id": 10}).status_code == 403

    def test_unauthenticated_401(self, make_client, create_npc):
        npc = create_npc("НПС")
        c = make_client(None)
        assert c.put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True}).status_code in (401, 403)
        assert c.get("/characters/admin/npcs", params={"country_id": 1}).status_code in (401, 403)

    def test_sql_injection_in_path_rejected(self, client, world):
        resp = client.put("/characters/admin/npcs/1;DROP TABLE characters/ready", json={"ready": True})
        assert resp.status_code in (404, 422)


# ============================================================
# 4. Public responses never carry the mark
# ============================================================


class TestReadyNotPublic:
    def test_public_endpoints_hide_ready(self, make_client, create_npc):
        npc = create_npc("Готовый НПС", location_id=1000)
        make_client(_ADMIN).put(f"/characters/admin/npcs/{npc.id}/ready", json={"ready": True})
        public = make_client(None)

        by_loc = public.get("/characters/npcs/by_location", params={"location_id": 1000})
        assert by_loc.status_code == 200 and by_loc.json()
        listing = public.get("/characters/list", params={"include_npcs": True})
        assert listing.status_code == 200
        short = public.get(f"/characters/{npc.id}/short_info")
        assert short.status_code == 200

        for resp in (by_loc, listing, short):
            for f in READY_FIELDS:
                assert f not in resp.text
            assert "admin_anna" not in resp.text


# ============================================================
# 5. Migration 048
# ============================================================


def test_migration_048_metadata():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "alembic", "versions", "048_npc_admin_ready.py")
    spec = importlib.util.spec_from_file_location("mig_048_npc_admin_ready", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "048_npc_admin_ready"
    assert mod.down_revision == "047_faction_territory"
    assert len(mod.revision) <= 32
    assert {c for _t, c, _d in mod._COLUMNS} == set(READY_FIELDS)
    assert callable(mod.upgrade) and callable(mod.downgrade)
