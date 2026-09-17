"""
FEAT-165 — admin refining config: GET/PUT /inventory/admin/items/{id}/conversions,
the `resource_subcategory` filter of GET /items, and the cleanup of stale
config when an item's subcategory changes through PUT /items/{id}.

State is always read back from `item_conversions` / `items` (silent-failure guard).
"""

import pytest

import models
from auth_http import get_current_user_via_http, UserRead
from main import app
from tests.feat165_helpers import (
    PROF_ID, seed_professions, make_item, add_conversion, conversion_rows,
)

ORE, HERB, TROPHY, REAGENT_SRC = 100, 101, 102, 103
INGOT, INGOT2, DUST, MATERIAL, ESSENCE = 200, 201, 202, 203, 204
WEAPON = 300

ADMIN = UserRead(id=1, username="admin", role="admin",
                 permissions=["items:read", "items:update", "items:create"])
READER = UserRead(id=2, username="reader", role="editor", permissions=["items:read"])
NOBODY = UserRead(id=3, username="user", role="user", permissions=[])


def _as(user):
    app.dependency_overrides[get_current_user_via_http] = lambda: user


@pytest.fixture()
def env(client, db_session):
    seed_professions(db_session)
    make_item(db_session, ORE, "Медная руда", subcategory="ore")
    make_item(db_session, HERB, "Мята", subcategory="herb")
    make_item(db_session, TROPHY, "Шкура волка", subcategory="trophy")
    make_item(db_session, REAGENT_SRC, "Экстракт мяты", subcategory="reagent")
    make_item(db_session, INGOT, "Медный слиток", subcategory="ingot")
    make_item(db_session, INGOT2, "Бронзовый слиток", subcategory="ingot")
    make_item(db_session, DUST, "Магическая пыль", subcategory="magic_dust")
    make_item(db_session, MATERIAL, "Кожа", subcategory="material")
    make_item(db_session, ESSENCE, "Эссенция жизни", subcategory="essence")
    make_item(db_session, WEAPON, "Меч", item_type="weapon", max_stack=1)
    _as(ADMIN)
    yield {"client": client, "db": db_session}
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _entry(slug, result_item_id, source_quantity=1, result_quantity=1, profession_id=None):
    return {
        "profession_id": profession_id if profession_id is not None else PROF_ID[slug],
        "source_quantity": source_quantity,
        "result_item_id": result_item_id,
        "result_quantity": result_quantity,
    }


def _put(client, item_id, entries):
    return client.put(f"/inventory/admin/items/{item_id}/conversions", json={"conversions": entries})


def _get(client, item_id):
    return client.get(f"/inventory/admin/items/{item_id}/conversions")


# ===========================================================================
# Happy path — replace the whole set
# ===========================================================================

class TestReplaceSet:

    def test_put_creates_both_professions_and_get_returns_them(self, env):
        db, c = env["db"], env["client"]

        resp = _put(c, ORE, [
            _entry("blacksmith", INGOT, source_quantity=2, result_quantity=1),
            _entry("jeweler", DUST),
        ])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_item_id"] == ORE
        by_prof = {e["profession_id"]: e for e in body["conversions"]}
        assert by_prof[PROF_ID["blacksmith"]]["profession_name"] == "Кузнец"
        assert by_prof[PROF_ID["blacksmith"]]["result_item"] == {
            "id": INGOT, "name": "Медный слиток", "image": None, "item_rarity": "common",
        }
        assert by_prof[PROF_ID["blacksmith"]]["source_quantity"] == 2
        assert conversion_rows(db, ORE) == [
            (ORE, PROF_ID["blacksmith"], 2, INGOT, 1),
            (ORE, PROF_ID["jeweler"], 1, DUST, 1),
        ]
        assert _get(c, ORE).json() == body

    def test_put_replaces_previous_set(self, env):
        db, c = env["db"], env["client"]
        add_conversion(db, ORE, "blacksmith", INGOT, source_quantity=2)
        add_conversion(db, ORE, "jeweler", DUST)

        resp = _put(c, ORE, [_entry("blacksmith", INGOT2, source_quantity=3, result_quantity=2)])

        assert resp.status_code == 200, resp.text
        assert conversion_rows(db, ORE) == [(ORE, PROF_ID["blacksmith"], 3, INGOT2, 2)]

    def test_empty_list_removes_everything(self, env):
        db, c = env["db"], env["client"]
        add_conversion(db, ORE, "blacksmith", INGOT)

        resp = _put(c, ORE, [])

        assert resp.status_code == 200, resp.text
        assert resp.json()["conversions"] == []
        assert conversion_rows(db, ORE) == []

    def test_other_items_config_is_untouched(self, env):
        db, c = env["db"], env["client"]
        add_conversion(db, TROPHY, "scholar", MATERIAL)

        assert _put(c, ORE, [_entry("blacksmith", INGOT)]).status_code == 200

        assert conversion_rows(db, TROPHY) == [(TROPHY, PROF_ID["scholar"], 1, MATERIAL, 1)]

    def test_scholar_trophy_to_material(self, env):
        db, c = env["db"], env["client"]
        assert _put(c, TROPHY, [_entry("scholar", MATERIAL)]).status_code == 200
        assert conversion_rows(db, TROPHY) == [(TROPHY, PROF_ID["scholar"], 1, MATERIAL, 1)]

    def test_get_empty_and_404(self, env):
        c = env["client"]
        resp = _get(c, ORE)
        assert resp.status_code == 200
        assert resp.json() == {"source_item_id": ORE, "conversions": []}
        assert _get(c, 999999).status_code == 404

    def test_alchemist_can_configure_reagent_to_essence(self, env):
        """Business rule (brief): the alchemist refines alchemical reagents into
        essences, the cook's reagents being the input. The admin must be able to
        configure it. BUG: replace_item_conversions only accepts RAW_SUBCATEGORIES
        as a source, and 'reagent' is a product subcategory."""
        db, c = env["db"], env["client"]

        resp = _put(c, REAGENT_SRC, [_entry("alchemist", ESSENCE, source_quantity=2)])

        assert resp.status_code == 200, resp.text
        assert conversion_rows(db, REAGENT_SRC) == [(REAGENT_SRC, PROF_ID["alchemist"], 2, ESSENCE, 1)]


# ===========================================================================
# Validation — nothing is written
# ===========================================================================

class TestValidation:

    @pytest.fixture()
    def existing(self, env):
        add_conversion(env["db"], ORE, "jeweler", DUST)
        return [(ORE, PROF_ID["jeweler"], 1, DUST, 1)]

    def _assert_400(self, resp, detail=None):
        assert resp.status_code == 400, resp.text
        if detail is not None:
            assert resp.json()["detail"] == detail

    def test_duplicate_profession(self, env, existing):
        resp = _put(env["client"], ORE, [_entry("blacksmith", INGOT), _entry("blacksmith", INGOT2)])
        self._assert_400(resp, "Профессия указана несколько раз")
        assert conversion_rows(env["db"], ORE) == existing

    def test_wrong_result_subcategory(self, env, existing):
        resp = _put(env["client"], ORE, [_entry("blacksmith", DUST)])
        self._assert_400(resp, "Результат для профессии Кузнец должен иметь подкатегорию «Слитки»")
        assert conversion_rows(env["db"], ORE) == existing

    def test_result_not_a_resource(self, env, existing):
        self._assert_400(_put(env["client"], ORE, [_entry("blacksmith", WEAPON)]))
        assert conversion_rows(env["db"], ORE) == existing

    def test_result_equals_source(self, env, existing):
        resp = _put(env["client"], ORE, [_entry("blacksmith", ORE)])
        self._assert_400(resp, "Сырьё не может перерабатываться само в себя")
        assert conversion_rows(env["db"], ORE) == existing

    def test_profession_does_not_accept_subcategory(self, env, existing):
        resp = _put(env["client"], ORE, [_entry("cook", INGOT)])
        self._assert_400(resp, "Повар не перерабатывает эту подкатегорию")
        assert conversion_rows(env["db"], ORE) == existing

    def test_profession_without_rule(self, env, existing):
        resp = _put(env["client"], ORE, [_entry("enchanter", INGOT)])
        self._assert_400(resp, "Профессия Зачарователь не перерабатывает сырьё")
        assert conversion_rows(env["db"], ORE) == existing

    def test_herb_is_not_refined_by_anyone(self, env):
        for slug in ("blacksmith", "jeweler", "cook", "scholar"):
            self._assert_400(_put(env["client"], HERB, [_entry(slug, INGOT)]))
        assert conversion_rows(env["db"]) == []

    def test_source_is_a_product(self, env):
        self._assert_400(_put(env["client"], INGOT, [_entry("blacksmith", INGOT2)]))
        assert conversion_rows(env["db"], INGOT) == []

    def test_source_is_not_a_resource(self, env):
        self._assert_400(_put(env["client"], WEAPON, [_entry("blacksmith", INGOT)]))
        assert conversion_rows(env["db"], WEAPON) == []

    def test_unknown_source_404(self, env):
        assert _put(env["client"], 999999, [_entry("blacksmith", INGOT)]).status_code == 404

    def test_unknown_profession_404(self, env, existing):
        resp = _put(env["client"], ORE, [_entry("blacksmith", INGOT, profession_id=4242)])
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Профессия не найдена"
        assert conversion_rows(env["db"], ORE) == existing

    def test_unknown_result_404(self, env, existing):
        resp = _put(env["client"], ORE, [_entry("blacksmith", 777777)])
        assert resp.status_code == 404
        assert conversion_rows(env["db"], ORE) == existing

    def test_more_than_five_entries(self, env, existing):
        entries = [_entry("blacksmith", INGOT, profession_id=i) for i in range(1, 7)]
        resp = _put(env["client"], ORE, entries)
        self._assert_400(resp, "Можно указать не больше 5 настроек переработки")
        assert conversion_rows(env["db"], ORE) == existing

    def test_one_bad_entry_rejects_the_whole_set(self, env, existing):
        resp = _put(env["client"], ORE, [_entry("blacksmith", INGOT), _entry("jeweler", INGOT)])
        self._assert_400(resp)
        assert conversion_rows(env["db"], ORE) == existing

    @pytest.mark.parametrize("field,value", [
        ("source_quantity", 0), ("source_quantity", 101), ("source_quantity", -1),
        ("result_quantity", 0), ("result_quantity", 101),
        ("source_quantity", "1 OR 1=1"), ("result_quantity", "'; DROP TABLE item_conversions; --"),
        ("profession_id", 0), ("profession_id", -3), ("profession_id", "blacksmith"),
        ("result_item_id", 0), ("result_item_id", None),
    ])
    def test_field_validation_422(self, env, existing, field, value):
        entry = _entry("blacksmith", INGOT)
        entry[field] = value
        assert _put(env["client"], ORE, [entry]).status_code == 422
        assert conversion_rows(env["db"], ORE) == existing

    def test_bounds_are_inclusive(self, env):
        resp = _put(env["client"], ORE, [_entry("blacksmith", INGOT, source_quantity=100, result_quantity=1),
                                         _entry("jeweler", DUST, source_quantity=1, result_quantity=100)])
        assert resp.status_code == 200, resp.text
        assert conversion_rows(env["db"], ORE) == [
            (ORE, PROF_ID["blacksmith"], 100, INGOT, 1),
            (ORE, PROF_ID["jeweler"], 1, DUST, 100),
        ]

    def test_malformed_body_422(self, env):
        c = env["client"]
        assert c.put(f"/inventory/admin/items/{ORE}/conversions", json={"conversions": "x"}).status_code == 422
        assert c.put(f"/inventory/admin/items/{ORE}/conversions", json=[1, 2]).status_code == 422
        assert c.put("/inventory/admin/items/abc/conversions", json={"conversions": []}).status_code == 422


# ===========================================================================
# RBAC
# ===========================================================================

class TestPermissions:

    def test_unauthenticated_401(self, client):
        assert client.get(f"/inventory/admin/items/{ORE}/conversions").status_code == 401
        assert client.put(f"/inventory/admin/items/{ORE}/conversions", json={"conversions": []}).status_code == 401

    def test_get_requires_items_read(self, env):
        _as(NOBODY)
        assert _get(env["client"], ORE).status_code == 403
        _as(READER)
        assert _get(env["client"], ORE).status_code == 200

    def test_put_requires_items_update(self, env):
        db = env["db"]
        add_conversion(db, ORE, "jeweler", DUST)
        for user in (NOBODY, READER):
            _as(user)
            assert _put(env["client"], ORE, []).status_code == 403
        assert conversion_rows(db, ORE) == [(ORE, PROF_ID["jeweler"], 1, DUST, 1)]

    def test_moderator_role_without_permission_is_rejected(self, env):
        _as(UserRead(id=4, username="mod", role="moderator", permissions=["items:read"]))
        assert _put(env["client"], ORE, []).status_code == 403


# ===========================================================================
# Item list filter + stale config cleanup via PUT /items/{id}
# ===========================================================================

def _item_body(item, **overrides):
    body = {
        "name": item.name,
        "item_level": 1,
        "item_type": "resource",
        "item_rarity": "common",
        "max_stack_size": 99,
        "is_unique": False,
        "resource_subcategory": item.resource_subcategory,
    }
    body.update(overrides)
    return body


def _db_item(db, item_id):
    db.expire_all()
    return db.query(models.Items).filter(models.Items.id == item_id).first()


class TestItemSubcategoryWrites:

    def test_filter_by_subcategory(self, env):
        resp = env["client"].get("/inventory/items?resource_subcategory=ingot&page_size=100")
        assert resp.status_code == 200
        assert sorted(i["id"] for i in resp.json()) == [INGOT, INGOT2]
        assert all(i["resource_subcategory"] == "ingot" for i in resp.json())

    def test_filter_rejects_unknown_subcategory(self, env):
        c = env["client"]
        assert c.get("/inventory/items?resource_subcategory=crystal").status_code == 422
        assert c.get("/inventory/items?resource_subcategory=ore'%20OR%20'1'='1").status_code == 422

    def test_create_stores_subcategory_and_stone_group(self, env):
        db, c = env["db"], env["client"]
        resp = c.post("/inventory/items", json={
            "name": "Резец", "item_level": 1, "item_type": "resource",
            "item_rarity": "rare", "max_stack_size": 20, "is_unique": False,
            "resource_subcategory": "whetstone", "whetstone_level": 2,
            "whetstone_group": "jewelry",
        })
        assert resp.status_code == 201, resp.text
        stored = _db_item(db, resp.json()["id"])
        assert stored.resource_subcategory == "whetstone"
        assert stored.whetstone_group == "jewelry"
        assert stored.whetstone_level == 2

    def test_subcategory_change_deletes_source_config(self, env):
        db, c = env["db"], env["client"]
        add_conversion(db, ORE, "blacksmith", INGOT)
        add_conversion(db, ORE, "jeweler", DUST)

        resp = c.put(f"/inventory/items/{ORE}", json=_item_body(_db_item(db, ORE), resource_subcategory="trophy"))

        assert resp.status_code == 200, resp.text
        assert _db_item(db, ORE).resource_subcategory == "trophy"
        assert conversion_rows(db, ORE) == []

    def test_result_subcategory_change_deletes_config(self, env):
        db, c = env["db"], env["client"]
        add_conversion(db, ORE, "blacksmith", INGOT)
        add_conversion(db, ORE, "jeweler", DUST)

        resp = c.put(f"/inventory/items/{INGOT}", json=_item_body(_db_item(db, INGOT), resource_subcategory="material"))

        assert resp.status_code == 200, resp.text
        assert conversion_rows(db, ORE) == [(ORE, PROF_ID["jeweler"], 1, DUST, 1)]

    def test_unrelated_update_keeps_config(self, env):
        db, c = env["db"], env["client"]
        add_conversion(db, ORE, "blacksmith", INGOT)

        resp = c.put(f"/inventory/items/{ORE}", json=_item_body(_db_item(db, ORE), description="Новое описание"))
        assert resp.status_code == 200, resp.text
        resp = c.put(f"/inventory/items/{INGOT}", json=_item_body(_db_item(db, INGOT), name="Слиток меди"))
        assert resp.status_code == 200, resp.text

        assert conversion_rows(db, ORE) == [(ORE, PROF_ID["blacksmith"], 1, INGOT, 1)]

    def test_deleting_source_item_cascades(self, env):
        db = env["db"]
        add_conversion(db, ORE, "blacksmith", INGOT)
        db.delete(_db_item(db, ORE))
        db.commit()
        assert conversion_rows(db) == []
