"""
`item_effects.secondary_magnitude` — generic second value of an effect row
(Burn: `magnitude` = damage per turn, `secondary_magnitude` = dodge reduction
in percentage points).

Pinned here:
  * the value round-trips create -> DB (raw SQL, real column name) -> GET;
  * it is optional: omitted / null stays NULL and is served as null;
  * PUT replace-all keeps / changes it;
  * it reaches the internal fast-slot payload battle-service reads;
  * the range validator returns 422 with a Russian message.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

import auth_http
import models

_TOKEN = "test-internal-token"
_INTERNAL_HEADERS = {"X-Internal-Token": _TOKEN}

HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update", "items:delete"]}


@pytest.fixture(autouse=True)
def _pin_internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _TOKEN)


def _auth_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ADMIN
    return resp


def _body(**overrides):
    body = {
        "name": "Горючая смесь",
        "item_level": 1,
        "item_type": "consumable",
        "item_rarity": "common",
        "max_stack_size": 10,
        "is_unique": False,
    }
    body.update(overrides)
    return body


def _post(client, body):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.post("/inventory/items", json=body, headers=HEADERS)


def _put(client, item_id, body):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.put(f"/inventory/items/{item_id}", json=body, headers=HEADERS)


def _get(client, item_id):
    return client.get(f"/inventory/internal/items/{item_id}", headers=_INTERNAL_HEADERS)


def _stored_secondary(db, item_id):
    rows = db.execute(
        text("SELECT secondary_magnitude FROM item_effects WHERE item_id = :iid ORDER BY id"),
        {"iid": item_id},
    ).fetchall()
    return [r[0] for r in rows]


_BURN = {
    "target_side": "enemy", "effect_name": "Burn", "description": None,
    "chance": 100, "duration": 3, "magnitude": 4.0, "secondary_magnitude": 15.0,
    "attribute_key": None,
}
_PLAIN = {
    "target_side": "self", "effect_name": "StatModifier", "description": None,
    "chance": 100, "duration": 2, "magnitude": 5.0, "attribute_key": "strength",
}


class TestSecondaryMagnitudeRoundTrip:

    def test_create_stores_and_returns_value(self, client, db_session):
        resp = _post(client, _body(effects=[_BURN, _PLAIN]))
        assert resp.status_code == 201, resp.text
        item_id = resp.json()["id"]

        assert [e["secondary_magnitude"] for e in resp.json()["effects"]] == [15.0, None]
        assert _stored_secondary(db_session, item_id) == [15.0, None]

        got = _get(client, item_id)
        assert got.status_code == 200, got.text
        assert [e["secondary_magnitude"] for e in got.json()["effects"]] == [15.0, None]

    def test_explicit_null_is_stored_as_null(self, client, db_session):
        item_id = _post(client, _body(
            effects=[dict(_BURN, secondary_magnitude=None)],
        )).json()["id"]
        assert _stored_secondary(db_session, item_id) == [None]

    def test_put_replaces_value(self, client, db_session):
        item_id = _post(client, _body(effects=[_BURN])).json()["id"]
        resp = _put(client, item_id, _body(effects=[dict(_BURN, secondary_magnitude=25.5)]))
        assert resp.status_code == 200, resp.text
        assert _stored_secondary(db_session, item_id) == [25.5]

    @pytest.mark.parametrize("value", [-10000.5, 10000.5])
    def test_out_of_range_rejected(self, client, value):
        resp = _post(client, _body(effects=[dict(_BURN, secondary_magnitude=value)]))
        assert resp.status_code == 422
        assert "Второе значение эффекта" in resp.text


class TestSecondaryMagnitudeInFastSlots:

    def test_value_reaches_fast_slot_payload(self, client, db_session):
        item_id = _post(client, _body(effects=[_BURN])).json()["id"]
        db_session.add(models.CharacterInventory(character_id=1, item_id=item_id, quantity=2))
        db_session.add(models.EquipmentSlot(
            character_id=1, slot_type="fast_slot_1", item_id=item_id, is_enabled=True))
        db_session.commit()

        resp = client.get("/inventory/internal/characters/1/fast_slots",
                          headers=_INTERNAL_HEADERS)
        assert resp.status_code == 200, resp.text
        row = resp.json()[0]["effects"][0]
        assert row["effect_name"] == "Burn"
        assert row["magnitude"] == 4.0
        assert row["secondary_magnitude"] == 15.0
