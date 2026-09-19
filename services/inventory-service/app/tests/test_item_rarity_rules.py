"""
FEAT-164 — item validators: food flag and the equipment-only rarity cap.

- is_food only on consumables, never together with a buff; persisted & returned
- mythical / divine / demonic are rejected for EVERY non-equipment type and
  accepted for EVERY equipment type (create and update)
- the cap is a set-membership rule (no ordering): common..legendary are
  accepted everywhere
"""

from unittest.mock import MagicMock, patch

import pytest

import auth_http
import models

# FEAT-171 I3: `GET /inventory/items/{id}` is now the thin public card; the fat
# item template moved to the internal twin, which requires `X-Internal-Token`.
_INTERNAL_TOKEN = "test-internal-token"
_INTERNAL_HEADERS = {"X-Internal-Token": _INTERNAL_TOKEN}


@pytest.fixture(autouse=True)
def _pin_internal_token(monkeypatch):
    """`verify_internal_token` reads a module-level constant — pin it."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _INTERNAL_TOKEN)

import schemas

HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update"]}
USER = {"id": 2, "username": "player", "role": "user", "permissions": []}

EQUIPMENT_TYPES = ["head", "body", "cloak", "belt", "ring", "necklace", "bracelet", "weapon"]
NON_EQUIPMENT_TYPES = [
    "consumable", "resource", "scroll", "misc", "recipe",
    "gem", "rune", "gathering_tool",
]
EQUIPMENT_ONLY = ["mythical", "divine", "demonic"]
COMMON_RARITIES = ["common", "rare", "epic", "legendary"]
RARITY_ERROR = "Мифическая, божественная и демоническая редкость доступны только для снаряжения"

# Type-specific fields other validators require
_TYPE_EXTRAS = {
    "weapon": {"weapon_subclass": "sword"},
    "gathering_tool": {"tool_category": "pickaxe", "max_durability": 10},
}


def _auth(user):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = user
    return resp


def _body(**overrides):
    body = {
        "name": "Предмет",
        "item_level": 1,
        "item_type": "misc",
        "item_rarity": "common",
        "max_stack_size": 1,
        "is_unique": False,
    }
    body.update(_TYPE_EXTRAS.get(overrides.get("item_type"), {}))
    body.update(overrides)
    return body


def _post(client, body, user=ADMIN, headers=HEADERS):
    with patch("auth_http.requests.get", return_value=_auth(user)):
        return client.post("/inventory/items", json=body, headers=headers)


def _put(client, item_id, body, user=ADMIN):
    with patch("auth_http.requests.get", return_value=_auth(user)):
        return client.put(f"/inventory/items/{item_id}", json=body, headers=HEADERS)


def _detail_text(resp):
    detail = resp.json().get("detail")
    return detail if isinstance(detail, str) else str(detail)


def _seed_item(db, **kw):
    values = dict(id=900, name="Старый предмет", item_level=1, item_type="misc",
                  item_rarity="common", max_stack_size=1, is_unique=False)
    values.update(kw)
    item = models.Items(**values)
    db.add(item)
    db.commit()
    return item


# ===========================================================================
# Constants
# ===========================================================================

class TestConstants:
    def test_sets(self):
        assert schemas.EQUIPMENT_ITEM_TYPES == frozenset(EQUIPMENT_TYPES)
        assert schemas.EQUIPMENT_ONLY_RARITIES == frozenset(EQUIPMENT_ONLY)

    def test_every_item_type_is_classified(self):
        all_types = {t.value for t in schemas.ItemType}
        assert all_types == set(EQUIPMENT_TYPES) | set(NON_EQUIPMENT_TYPES)

    @pytest.mark.parametrize("rarity", EQUIPMENT_ONLY)
    def test_unknown_future_type_is_capped(self, rarity):
        assert schemas.is_rarity_allowed_for_type("totem", rarity) is False
        assert schemas.is_rarity_allowed_for_type("totem", "legendary") is True


# ===========================================================================
# Rarity cap on create / update
# ===========================================================================

class TestRarityCap:

    @pytest.mark.parametrize("item_type", NON_EQUIPMENT_TYPES)
    @pytest.mark.parametrize("rarity", EQUIPMENT_ONLY)
    def test_non_equipment_rejected(self, client, db_session, item_type, rarity):
        resp = _post(client, _body(item_type=item_type, item_rarity=rarity))
        assert resp.status_code in (400, 422), resp.text
        assert RARITY_ERROR in _detail_text(resp)
        assert db_session.query(models.Items).count() == 0

    @pytest.mark.parametrize("item_type", EQUIPMENT_TYPES)
    @pytest.mark.parametrize("rarity", EQUIPMENT_ONLY)
    def test_equipment_accepted(self, client, db_session, item_type, rarity):
        resp = _post(client, _body(item_type=item_type, item_rarity=rarity))
        assert resp.status_code == 201, resp.text
        assert resp.json()["item_rarity"] == rarity

    @pytest.mark.parametrize("item_type", NON_EQUIPMENT_TYPES)
    @pytest.mark.parametrize("rarity", COMMON_RARITIES)
    def test_non_equipment_up_to_legendary_accepted(self, client, db_session, item_type, rarity):
        resp = _post(client, _body(item_type=item_type, item_rarity=rarity))
        assert resp.status_code == 201, resp.text

    @pytest.mark.parametrize("rarity", EQUIPMENT_ONLY)
    def test_update_to_equipment_only_rarity_rejected(self, client, db_session, rarity):
        item = _seed_item(db_session, item_type="resource")
        resp = _put(client, item.id, _body(name=item.name, item_type="resource", item_rarity=rarity))
        assert resp.status_code in (400, 422)
        assert RARITY_ERROR in _detail_text(resp)
        db_session.expire_all()
        assert db_session.query(models.Items).get(item.id).item_rarity == "common"

    def test_update_equipment_type_change_to_non_equipment_rejected(self, client, db_session):
        item = _seed_item(db_session, item_type="ring", item_rarity="mythical")
        resp = _put(client, item.id, _body(name=item.name, item_type="misc", item_rarity="mythical"))
        assert resp.status_code in (400, 422)
        db_session.expire_all()
        assert db_session.query(models.Items).get(item.id).item_type == "ring"

    def test_legacy_mythical_resource_can_be_saved_after_lowering(self, client, db_session):
        item = _seed_item(db_session, item_type="resource", item_rarity="mythical",
                          name="Трансмутированный ресурс (мифический)")
        resp = _put(client, item.id, _body(name=item.name, item_type="resource", item_rarity="legendary"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["item_rarity"] == "legendary"


# ===========================================================================
# Food flag
# ===========================================================================

class TestFoodFlag:

    def test_food_consumable_persisted_and_returned(self, client, db_session):
        resp = _post(client, _body(
            item_type="consumable", item_rarity="rare", is_food=True, max_stack_size=20,
            health_recovery=15, strength_modifier=2, res_fire_modifier=1.5,
        ))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["is_food"] is True
        row = db_session.query(models.Items).get(data["id"])
        assert row.is_food is True
        assert row.strength_modifier == 2

    def test_is_food_defaults_false(self, client, db_session):
        resp = _post(client, _body(item_type="consumable"))
        assert resp.status_code == 201
        assert resp.json()["is_food"] is False

    @pytest.mark.parametrize("item_type", [t for t in EQUIPMENT_TYPES + NON_EQUIPMENT_TYPES if t != "consumable"])
    def test_food_must_be_consumable(self, client, db_session, item_type):
        resp = _post(client, _body(item_type=item_type, is_food=True))
        assert resp.status_code in (400, 422)
        assert "Едой может быть только расходуемый предмет" in _detail_text(resp)

    def test_food_cannot_be_buff_item(self, client, db_session):
        resp = _post(client, _body(
            item_type="consumable", is_food=True,
            buff_type="xp_bonus", buff_value=0.5, buff_duration_minutes=60,
        ))
        assert resp.status_code in (400, 422)
        assert "Еда не может быть баффовым предметом" in _detail_text(resp)

    @pytest.mark.parametrize("rarity", EQUIPMENT_ONLY)
    def test_food_above_legendary_rejected(self, client, db_session, rarity):
        resp = _post(client, _body(item_type="consumable", is_food=True, item_rarity=rarity))
        assert resp.status_code in (400, 422)
        assert RARITY_ERROR in _detail_text(resp)

    def test_update_toggles_food(self, client, db_session):
        item = _seed_item(db_session, item_type="consumable")
        resp = _put(client, item.id, _body(name=item.name, item_type="consumable", is_food=True))
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_food"] is True
        resp = _put(client, item.id, _body(name=item.name, item_type="consumable", is_food=False))
        assert resp.json()["is_food"] is False

    def test_item_list_exposes_is_food(self, client, db_session):
        _seed_item(db_session, item_type="consumable", is_food=True)
        resp = client.get("/inventory/internal/items/900", headers=_INTERNAL_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["is_food"] is True


# ===========================================================================
# Security
# ===========================================================================

class TestItemSecurity:

    def test_create_without_token_rejected(self, client, db_session):
        resp = client.post("/inventory/items", json=_body(item_type="consumable", is_food=True))
        assert resp.status_code == 401

    def test_create_as_regular_user_forbidden(self, client, db_session):
        resp = _post(client, _body(item_type="consumable", is_food=True), user=USER)
        assert resp.status_code == 403
        assert db_session.query(models.Items).count() == 0

    def test_is_food_type_confusion_rejected(self, client, db_session):
        resp = _post(client, _body(item_type="consumable", is_food="yes please"))
        assert resp.status_code == 422
