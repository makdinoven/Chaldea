"""
FEAT-210: admin mob templates — country/region filter via spawn locations, spawn_count and the «Готов» mark.

Covers:
- GET /characters/admin/mob-templates ?country_id / ?region_id over the Location -> District -> Region -> Country
  hierarchy through location_mob_spawns (district location, nested sub-district, own region_id, child inheriting via
  parent_id, child with its own region NOT inherited), disabled spawns count, mob without spawns excluded, mob with
  spawns in two regions in both, foreign / unknown ids -> empty, combination with q / tier / ready / pagination,
  invalid params -> 422
- spawn_count in the list (enabled + disabled rows, 0 without spawns)
- ?ready filter, admin_ready* in the list and the admin detail
- PUT /characters/admin/mob-templates/{id}/ready: set/unset, idempotent re-set keeps who/when, 404, 422, 401/403
- admin_ready* never appears in public mob responses (/mobs/by_location, /bestiary)
- shared geo helper reputation_crud.admin_geo_location_ids + NPC/mob geo parity after the refactor
- migration 049 module metadata
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
import reputation_crud


READY_FIELDS = ("admin_ready", "admin_ready_at", "admin_ready_by")
LIST_URL = "/characters/admin/mob-templates"

_ADMIN = UserRead(id=1, username="admin_anna", role="admin", permissions=["mobs:manage", "npcs:read"])
_OTHER_ADMIN = UserRead(id=3, username="admin_boris", role="admin", permissions=["mobs:manage"])
_NO_MOBS = UserRead(id=2, username="editor", role="editor", permissions=["npcs:read", "items:read"])

# Same world as test_admin_npc_region_ready.py:
# Country 1: Region 10 (district 100, nested sub-district 101 -> parent 100), Region 11 (district 110)
# Country 2: Region 20 (district 200)
#   1000 in district 100 -> r10 ; 1001 in sub-district 101 -> r10 ; 1002 own region 11 -> r11
#   1003 child of 1000 -> r10 (inherited) ; 1004 child of 1000 with own region 20 -> r20 (NOT inherited)
#   1005 grandchild of 1003 -> r10 ; 2000 in district 200 -> r20 ; 3000 unresolved
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

_ALL_LOCATIONS = (1000, 1001, 1002, 1003, 1004, 1005, 2000, 3000)


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
def create_mob(world):
    def _create(name, spawns=(), tier="normal", ready=False, disabled=()):
        tpl = models.MobTemplate(
            name=name, tier=tier, level=3, id_race=1, id_subrace=1, id_class=1,
            xp_reward=10, gold_reward=5, respawn_enabled=False, admin_ready=ready,
        )
        world.add(tpl)
        world.flush()
        for lid in spawns:
            world.add(models.LocationMobSpawn(mob_template_id=tpl.id, location_id=lid, is_enabled=True))
        for lid in disabled:
            world.add(models.LocationMobSpawn(mob_template_id=tpl.id, location_id=lid, is_enabled=False))
        world.commit()
        world.refresh(tpl)
        return tpl

    return _create


@pytest.fixture
def geo_mobs(create_mob):
    """One mob spawning in each location + a mob without spawns + a disabled-only mob + a two-region mob."""
    for lid in _ALL_LOCATIONS:
        create_mob(f"Моб-{lid}", spawns=(lid,))
    create_mob("Моб-без-спавнов")
    create_mob("Моб-выключен-1001", disabled=(1001,))
    create_mob("Моб-два-региона", spawns=(1002, 2000))


def _names(resp):
    assert resp.status_code == 200, resp.text
    return {i["name"] for i in resp.json()["items"]}


def _list(client, **params):
    return client.get(LIST_URL, params={"page_size": 100, **params})


# ============================================================
# 1. Geo filter via spawn locations
# ============================================================


class TestRegionFilter:
    def test_region_includes_district_nested_inherited_and_disabled(self, client, geo_mobs):
        names = _names(_list(client, region_id=10))
        assert names == {"Моб-1000", "Моб-1001", "Моб-1003", "Моб-1005", "Моб-выключен-1001"}

    def test_child_with_own_region_not_inherited(self, client, geo_mobs):
        assert _names(_list(client, region_id=20)) == {"Моб-1004", "Моб-2000", "Моб-два-региона"}

    def test_location_with_own_region_and_no_district(self, client, geo_mobs):
        assert _names(_list(client, region_id=11)) == {"Моб-1002", "Моб-два-региона"}

    def test_mob_without_spawns_and_unresolved_location_excluded(self, client, geo_mobs):
        for params in ({"region_id": 10}, {"region_id": 11}, {"region_id": 20}, {"country_id": 1},
                       {"country_id": 2}):
            names = _names(_list(client, **params))
            assert "Моб-без-спавнов" not in names
            assert "Моб-3000" not in names

    def test_unknown_region_empty(self, client, geo_mobs):
        resp = _list(client, region_id=999)
        assert resp.status_code == 200
        assert resp.json()["items"] == [] and resp.json()["total"] == 0


class TestCountryFilter:
    def test_country_is_union_of_its_regions(self, client, geo_mobs):
        names = _names(_list(client, country_id=1))
        assert names == {"Моб-1000", "Моб-1001", "Моб-1002", "Моб-1003", "Моб-1005", "Моб-выключен-1001",
                         "Моб-два-региона"}

    def test_other_country(self, client, geo_mobs):
        assert _names(_list(client, country_id=2)) == {"Моб-1004", "Моб-2000", "Моб-два-региона"}

    def test_two_region_mob_counted_once(self, client, geo_mobs):
        body = _list(client, country_id=1).json()
        assert body["total"] == 7
        assert [i["name"] for i in body["items"]].count("Моб-два-региона") == 1

    def test_country_and_own_region_intersection(self, client, geo_mobs):
        assert _names(_list(client, country_id=1, region_id=11)) == {"Моб-1002", "Моб-два-региона"}

    def test_region_of_foreign_country_returns_empty(self, client, geo_mobs):
        resp = _list(client, country_id=1, region_id=20)
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0, "page": 1, "page_size": 100}

    def test_unknown_country_empty(self, client, geo_mobs):
        assert _list(client, country_id=999).json()["total"] == 0

    def test_country_without_regions_empty(self, client, world, geo_mobs):
        world.execute(text("INSERT INTO Countries (id, name) VALUES (3, 'Пустая')"))
        world.commit()
        assert _list(client, country_id=3).json()["total"] == 0

    def test_no_geo_params_returns_all_templates(self, client, geo_mobs):
        # 8 one-location mobs + no spawns + disabled-only + two-region
        assert _list(client).json()["total"] == 11

    @pytest.mark.parametrize("params", [{"country_id": 0}, {"region_id": -1}, {"country_id": "abc"},
                                        {"region_id": "1.5"}, {"ready": "maybe"}])
    def test_invalid_params_422(self, client, geo_mobs, params):
        assert _list(client, **params).status_code == 422


class TestGeoCombinations:
    def test_with_search(self, client, geo_mobs):
        assert _names(_list(client, region_id=10, q="1003")) == {"Моб-1003"}

    def test_with_tier(self, client, create_mob, geo_mobs):
        create_mob("Босс-1005", spawns=(1005,), tier="boss")
        create_mob("Босс-2000", spawns=(2000,), tier="boss")
        create_mob("Элита-1000", spawns=(1000,), tier="elite")
        assert _names(_list(client, country_id=1, tier="boss")) == {"Босс-1005"}
        assert _names(_list(client, region_id=10, tier="elite")) == {"Элита-1000"}

    def test_with_ready(self, client, create_mob, geo_mobs):
        create_mob("Готовый-1000", spawns=(1000,), ready=True)
        create_mob("Готовый-2000", spawns=(2000,), ready=True)
        assert _names(_list(client, region_id=10, ready=1)) == {"Готовый-1000"}
        assert _names(_list(client, region_id=10, ready=0)) == {
            "Моб-1000", "Моб-1001", "Моб-1003", "Моб-1005", "Моб-выключен-1001"}

    def test_pagination_total(self, client, geo_mobs):
        first = client.get(LIST_URL, params={"country_id": 1, "page": 1, "page_size": 3}).json()
        third = client.get(LIST_URL, params={"country_id": 1, "page": 3, "page_size": 3}).json()
        assert first["total"] == 7 and len(first["items"]) == 3
        assert third["total"] == 7 and len(third["items"]) == 1
        ids = [i["id"] for i in first["items"]]
        assert ids == sorted(ids)
        assert first["page"] == 1 and first["page_size"] == 3

    def test_geo_parity_with_npc_list(self, client, create_mob, world):
        """The shared helper drives both lists: an NPC and a mob in the same location fall into the same scopes."""
        for lid in _ALL_LOCATIONS:
            create_mob(f"Моб-{lid}", spawns=(lid,))
            world.add(models.Character(
                name=f"Моб-{lid}", id_race=1, id_subrace=1, id_class=1, appearance="t", avatar="t.jpg",
                is_npc=True, npc_role="merchant", npc_status="alive", current_location_id=lid,
                level=1, stat_points=0, currency_balance=0,
            ))
        world.commit()
        for params in ({"region_id": 10}, {"region_id": 11}, {"region_id": 20}, {"country_id": 1},
                       {"country_id": 2}, {"country_id": 1, "region_id": 20}, {"region_id": 999}):
            npc = _names(client.get("/characters/admin/npcs", params={"page_size": 100, **params}))
            mob = _names(_list(client, **params))
            assert npc == mob, params


# ============================================================
# 2. Shared geo helper
# ============================================================


class TestGeoHelper:
    def test_none_without_params(self, world):
        assert reputation_crud.admin_geo_location_ids(world, None, None) is None

    def test_region_scope(self, world):
        ids = reputation_crud.admin_geo_location_ids(world, None, 10)
        assert set(ids) == {1000, 1001, 1003, 1005}

    def test_country_scope(self, world):
        assert set(reputation_crud.admin_geo_location_ids(world, 2, None)) == {1004, 2000}

    def test_foreign_and_unknown_empty(self, world):
        assert reputation_crud.admin_geo_location_ids(world, 1, 20) == []
        assert reputation_crud.admin_geo_location_ids(world, 999, None) == []
        assert reputation_crud.admin_geo_location_ids(world, 999, 10) == []


# ============================================================
# 3. spawn_count
# ============================================================


class TestSpawnCount:
    def test_counts_enabled_and_disabled_rows(self, client, create_mob):
        create_mob("Три", spawns=(1000, 1001), disabled=(2000,))
        create_mob("Один выкл", disabled=(1002,))
        create_mob("Ноль")
        counts = {i["name"]: i["spawn_count"] for i in _list(client).json()["items"]}
        assert counts == {"Три": 3, "Один выкл": 1, "Ноль": 0}

    def test_count_is_total_not_scope(self, client, create_mob):
        # the geo filter selects the mob but the count stays the number of all its spawn rows
        create_mob("Широкий", spawns=(1000, 1002, 2000))
        item = _list(client, region_id=11).json()["items"][0]
        assert item["name"] == "Широкий" and item["spawn_count"] == 3

    def test_count_on_later_page(self, client, create_mob):
        for n in range(4):
            create_mob(f"М{n}", spawns=tuple(_ALL_LOCATIONS[:n]))
        page2 = client.get(LIST_URL, params={"page": 2, "page_size": 2}).json()["items"]
        assert [(i["name"], i["spawn_count"]) for i in page2] == [("М2", 2), ("М3", 3)]

    def test_detail_spawn_locations_match_count(self, client, create_mob):
        tpl = create_mob("Детали", spawns=(1000,), disabled=(1001,))
        detail = client.get(f"{LIST_URL}/{tpl.id}").json()
        assert len(detail["spawn_locations"]) == 2
        assert _list(client).json()["items"][0]["spawn_count"] == 2


# ============================================================
# 4. Ready filter + fields
# ============================================================


class TestReadyFilterAndFields:
    def test_ready_filter(self, client, create_mob):
        create_mob("Готов", ready=True)
        create_mob("Не готов")
        assert _names(_list(client, ready="true")) == {"Готов"}
        assert _names(_list(client, ready="false")) == {"Не готов"}
        assert _names(_list(client)) == {"Готов", "Не готов"}

    def test_ready_combined_with_q_and_tier(self, client, create_mob):
        create_mob("Волк готовый", ready=True)
        create_mob("Волк", ready=False)
        create_mob("Волк-босс готовый", tier="boss", ready=True)
        assert _names(_list(client, q="Волк", ready=1, tier="normal")) == {"Волк готовый"}

    def test_list_items_expose_ready_fields(self, client, create_mob):
        create_mob("Моб")
        item = _list(client).json()["items"][0]
        for f in READY_FIELDS + ("spawn_count",):
            assert f in item
        assert item["admin_ready"] is False
        assert item["admin_ready_at"] is None and item["admin_ready_by"] is None

    def test_detail_exposes_ready_fields(self, client, create_mob):
        tpl = create_mob("Моб")
        assert client.get(f"{LIST_URL}/{tpl.id}").json()["admin_ready"] is False
        client.put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True})
        body = client.get(f"{LIST_URL}/{tpl.id}").json()
        assert body["admin_ready"] is True
        assert body["admin_ready_by"] == "admin_anna"
        assert body["admin_ready_at"] is not None


# ============================================================
# 5. PUT /admin/mob-templates/{id}/ready
# ============================================================


class TestReadyToggle:
    def test_set_records_who_and_when(self, client, create_mob, db_session):
        tpl = create_mob("Моб")
        before = datetime.utcnow().replace(microsecond=0)
        resp = client.put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == tpl.id and body["admin_ready"] is True
        assert body["admin_ready_by"] == "admin_anna"
        at = datetime.fromisoformat(body["admin_ready_at"])
        assert before <= at.replace(microsecond=0) <= datetime.utcnow()
        db_session.expire_all()
        row = db_session.get(models.MobTemplate, tpl.id)
        assert row.admin_ready is True and row.admin_ready_by == "admin_anna"
        assert _list(client).json()["items"][0]["admin_ready"] is True

    def test_unset_clears_who_and_when(self, client, create_mob):
        tpl = create_mob("Моб")
        client.put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True})
        resp = client.put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": False})
        assert resp.status_code == 200
        assert resp.json() == {"id": tpl.id, "admin_ready": False, "admin_ready_at": None, "admin_ready_by": None}
        again = client.put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": False})
        assert again.status_code == 200 and again.json()["admin_ready"] is False

    def test_reset_true_is_idempotent_and_keeps_original(self, make_client, create_mob):
        tpl = create_mob("Моб")
        first = make_client(_ADMIN).put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True}).json()
        second = make_client(_OTHER_ADMIN).put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True})
        assert second.status_code == 200
        assert second.json() == first
        assert second.json()["admin_ready_by"] == "admin_anna"

    def test_regular_update_keeps_mark(self, client, create_mob):
        tpl = create_mob("Моб")
        client.put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True})
        resp = client.put(f"{LIST_URL}/{tpl.id}", json={"name": "Моб переименован", "level": 5})
        assert resp.status_code == 200, resp.text
        body = client.get(f"{LIST_URL}/{tpl.id}").json()
        assert body["name"] == "Моб переименован"
        assert body["admin_ready"] is True and body["admin_ready_by"] == "admin_anna"

    def test_missing_404(self, client, world):
        resp = client.put(f"{LIST_URL}/987654/ready", json={"ready": True})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Шаблон моба не найден"

    @pytest.mark.parametrize("body", [{}, {"ready": "maybe"}, {"ready": True, "extra": 1}, None])
    def test_bad_body_422(self, client, create_mob, body):
        tpl = create_mob("Моб")
        if body is None:
            resp = client.put(f"{LIST_URL}/{tpl.id}/ready")
        else:
            resp = client.put(f"{LIST_URL}/{tpl.id}/ready", json=body)
        assert resp.status_code == 422

    def test_without_mobs_manage_403(self, make_client, create_mob):
        tpl = create_mob("Моб")
        c = make_client(_NO_MOBS)
        assert c.put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True}).status_code == 403
        assert c.get(LIST_URL, params={"region_id": 10}).status_code == 403
        assert c.get(f"{LIST_URL}/{tpl.id}").status_code == 403

    def test_unauthenticated_401(self, make_client, create_mob):
        tpl = create_mob("Моб")
        c = make_client(None)
        assert c.put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True}).status_code in (401, 403)
        assert c.get(LIST_URL, params={"country_id": 1}).status_code in (401, 403)

    def test_sql_injection_in_path_and_query_rejected(self, client, create_mob):
        create_mob("Моб")
        resp = client.put(f"{LIST_URL}/1;DROP TABLE mob_templates/ready", json={"ready": True})
        assert resp.status_code in (404, 422)
        assert _list(client, region_id="1 OR 1=1").status_code == 422
        assert _list(client, q="' OR 1=1 --").json()["total"] == 0
        assert _list(client).json()["total"] == 1


# ============================================================
# 6. Public responses never carry the mark
# ============================================================


class TestReadyNotPublic:
    def test_public_endpoints_hide_ready(self, make_client, create_mob, world):
        tpl = create_mob("Готовый моб", spawns=(1000,))
        mob_char = models.Character(
            name="Готовый моб", id_race=1, id_subrace=1, id_class=1, appearance="t", avatar="t.jpg",
            is_npc=True, npc_role="mob", npc_status="alive", current_location_id=1000,
            level=3, stat_points=0, currency_balance=0,
        )
        world.add(mob_char)
        world.flush()
        world.add(models.ActiveMob(mob_template_id=tpl.id, character_id=mob_char.id, location_id=1000,
                                   status="alive", spawn_type="random"))
        world.commit()
        assert make_client(_ADMIN).put(f"{LIST_URL}/{tpl.id}/ready", json={"ready": True}).status_code == 200
        public = make_client(None)

        by_loc = public.get("/characters/mobs/by_location", params={"location_id": 1000})
        assert by_loc.status_code == 200 and by_loc.json()
        bestiary = public.get("/characters/bestiary")
        assert bestiary.status_code == 200 and "Готовый моб" in bestiary.text

        for resp in (by_loc, bestiary):
            for f in READY_FIELDS:
                assert f not in resp.text
            assert "admin_anna" not in resp.text


# ============================================================
# 7. Migration 049
# ============================================================


def _load_migration(filename, modname):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "alembic", "versions", filename)
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_049_metadata():
    mod = _load_migration("049_mob_admin_ready.py", "mig_049_mob_admin_ready")
    assert mod.revision == "049_mob_admin_ready"
    assert mod.down_revision == "048_npc_admin_ready"
    assert len(mod.revision) <= 32
    assert {t for t, _c, _d in mod._COLUMNS} == {"mob_templates"}
    assert {c for _t, c, _d in mod._COLUMNS} == set(READY_FIELDS)
    assert callable(mod.upgrade) and callable(mod.downgrade)


def test_migration_049_is_single_head():
    versions = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic", "versions")
    downs = set()
    for fn in os.listdir(versions):
        if fn.endswith(".py") and not fn.startswith("__"):
            mod = _load_migration(fn, f"mig_scan_{fn[:-3]}")
            d = getattr(mod, "down_revision", None)
            for rev in (d if isinstance(d, (tuple, list)) else (d,)):
                if rev:
                    downs.add(rev)
    assert "048_npc_admin_ready" in downs
    # FEAT-211: 050_physical_caravans follows 049; FEAT-212: 051_caravan_escorts follows 050 and is the single head
    assert "049_mob_admin_ready" in downs
    assert "050_physical_caravans" in downs
    assert "051_caravan_escorts" not in downs
