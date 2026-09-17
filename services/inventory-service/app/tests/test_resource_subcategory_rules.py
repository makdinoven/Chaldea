"""
FEAT-165 — ItemCreate validators for resource subcategories, sharpening stones,
repair kits and sockets (POST/PUT /inventory/items). Rejected payloads must not
create or change rows.
"""

from unittest.mock import patch, MagicMock

import pytest

import models

HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update"]}


def _auth(payload=ADMIN):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def _body(**overrides):
    body = {
        "name": "Ресурс",
        "item_level": 1,
        "item_type": "resource",
        "item_rarity": "common",
        "max_stack_size": 99,
        "is_unique": False,
    }
    body.update(overrides)
    return body


def _post(client, body, auth=ADMIN):
    with patch("auth_http.requests.get", return_value=_auth(auth)):
        return client.post("/inventory/items", json=body, headers=HEADERS)


def _put(client, item_id, body):
    with patch("auth_http.requests.get", return_value=_auth()):
        return client.put(f"/inventory/items/{item_id}", json=body, headers=HEADERS)


def _items(db):
    db.expire_all()
    return db.query(models.Items).all()


def _stored(db, item_id):
    db.expire_all()
    return db.query(models.Items).filter(models.Items.id == item_id).first()


VALID = [
    _body(resource_subcategory="ore"),
    _body(resource_subcategory="ingredient"),
    _body(resource_subcategory="trophy"),
    _body(resource_subcategory="material"),
    _body(resource_subcategory=None),
    _body(resource_subcategory="whetstone", whetstone_level=1, whetstone_group="weapon_armor"),
    _body(resource_subcategory="whetstone", whetstone_level=3, whetstone_group="cloak_belt"),
    _body(resource_subcategory="repair_kit", repair_power=25),
    _body(item_type="ring", item_rarity="common", max_stack_size=1, socket_count=2),
    _body(item_type="cloak", max_stack_size=1, socket_count=1),
    _body(item_type="weapon", max_stack_size=1, socket_count=1),
]

INVALID = [
    # subcategory only for resources
    (_body(item_type="consumable", resource_subcategory="ore"), "Подкатегорию можно указать только для ресурса"),
    (_body(item_type="weapon", max_stack_size=1, resource_subcategory="whetstone",
           whetstone_level=1, whetstone_group="weapon_armor"), None),
    # stones need level + group
    (_body(resource_subcategory="whetstone"), "Для камня заточки укажите уровень и группу"),
    (_body(resource_subcategory="whetstone", whetstone_level=2), "Для камня заточки укажите уровень и группу"),
    (_body(resource_subcategory="whetstone", whetstone_group="jewelry"), "Для камня заточки укажите уровень и группу"),
    (_body(resource_subcategory="whetstone", whetstone_level=4, whetstone_group="jewelry"), None),
    (_body(resource_subcategory="whetstone", whetstone_level=-1, whetstone_group="jewelry"), None),
    (_body(resource_subcategory="whetstone", whetstone_level=1, whetstone_group="gloves"), None),
    # level/group without the stone subcategory
    (_body(whetstone_level=1, whetstone_group="jewelry"),
     "Уровень и группу камня заточки можно указать только для камня заточки"),
    (_body(resource_subcategory="ore", whetstone_level=1), None),
    (_body(resource_subcategory="ore", whetstone_group="jewelry"), None),
    # repair kits
    (_body(resource_subcategory="repair_kit"), "Для ремкомплекта укажите силу ремонта больше 0"),
    (_body(resource_subcategory="repair_kit", repair_power=-5), None),
    (_body(resource_subcategory="ore", repair_power=10), "Сила ремонта указывается только для ремкомплекта"),
    # sockets
    (_body(item_type="belt", max_stack_size=1, socket_count=1),
     "Слоты доступны только для оружия, брони, шлема, плаща и украшений"),
    (_body(item_type="consumable", socket_count=1), None),
    (_body(socket_count=2), None),
    # removed / unknown values
    (_body(item_type="blueprint"), None),
    (_body(resource_subcategory="crystal"), None),
    (_body(resource_subcategory="ore'; DROP TABLE items; --"), None),
]


class TestCreateValidators:

    @pytest.mark.parametrize("body", VALID)
    def test_valid_payloads_created(self, client, db_session, body):
        resp = _post(client, body)
        assert resp.status_code == 201, resp.text
        stored = _stored(db_session, resp.json()["id"])
        assert stored.resource_subcategory == body.get("resource_subcategory")
        assert stored.whetstone_group == body.get("whetstone_group")
        assert stored.whetstone_level == body.get("whetstone_level")

    @pytest.mark.parametrize("body,detail", INVALID)
    def test_invalid_payloads_422(self, client, db_session, body, detail):
        resp = _post(client, body)
        assert resp.status_code == 422, resp.text
        if detail is not None:
            assert detail in resp.text
        assert _items(db_session) == []

    def test_legacy_essence_field_is_ignored(self, client, db_session):
        """essence_result_item_id no longer exists; an old client sending it still works."""
        resp = _post(client, _body(essence_result_item_id=5, resource_subcategory="herb"))
        assert resp.status_code == 201, resp.text
        assert "essence_result_item_id" not in resp.json()

    def test_response_exposes_new_fields(self, client, db_session):
        data = _post(client, _body(resource_subcategory="whetstone", whetstone_level=2,
                                   whetstone_group="jewelry")).json()
        assert data["resource_subcategory"] == "whetstone"
        assert data["whetstone_group"] == "jewelry"

    def test_create_requires_permission(self, client, db_session):
        resp = _post(client, _body(resource_subcategory="ore"),
                     auth={"id": 2, "username": "u", "role": "user", "permissions": []})
        assert resp.status_code == 403
        assert _items(db_session) == []


class TestUpdateValidators:

    def test_update_changes_subcategory_and_clears_stone_fields(self, client, db_session):
        created = _post(client, _body(name="Камень", resource_subcategory="whetstone",
                                      whetstone_level=1, whetstone_group="weapon_armor")).json()

        resp = _put(client, created["id"], _body(name="Камень", resource_subcategory="ore",
                                                 whetstone_level=None, whetstone_group=None))

        assert resp.status_code == 200, resp.text
        stored = _stored(db_session, created["id"])
        assert stored.resource_subcategory == "ore"
        assert stored.whetstone_level is None
        assert stored.whetstone_group is None

    def test_invalid_update_leaves_row_unchanged(self, client, db_session):
        created = _post(client, _body(name="Руда", resource_subcategory="ore")).json()

        resp = _put(client, created["id"], _body(name="Руда", item_type="consumable",
                                                 resource_subcategory="ore"))

        assert resp.status_code == 422
        stored = _stored(db_session, created["id"])
        assert stored.item_type == "resource"
        assert stored.resource_subcategory == "ore"
