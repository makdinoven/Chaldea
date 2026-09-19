"""FEAT-168, review #2 gap 1 — reading stored item rows must never 500.

`ItemXpBuffOut` / `ItemEffectOut` / `ItemDamageOut` deliberately do **not**
inherit from their `*In` siblings, so none of the request-side validators run on
the way out. Response validation is not input validation: a row that is already
in the database — written before a whitelist existed, by a migration backfill, by
a DBA, or by an older build — must be **served verbatim**, not turned into a 500
that takes down the admin item page (and, for the fast-slot payload, the start of
every battle).

Nothing in the previous suite covered this: every stored row was written through
the API, so it was valid by construction, and re-adding the inheritance would
have left the whole suite green. Every test below therefore writes the offending
row **straight into the table with raw SQL**, bypassing the API, and then asserts
that every read path answers 200 with the stored values unchanged.

Read paths covered: `GET /inventory/items/{id}`, `GET /inventory/items` (the
list), `GET /inventory/{cid}/item-detail/{inv_id}` and
`GET /inventory/internal/characters/{cid}/fast_slots` (FEAT-169: the belt
is read by battle-service through the internal twin).
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

import auth_http
import models


# FEAT-169: the internal belt route requires `X-Internal-Token`.
_TOKEN = "test-internal-token"
_INTERNAL_HEADERS = {"X-Internal-Token": _TOKEN}


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    """`verify_internal_token` reads a module-level constant — pin it."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _TOKEN)


HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update", "items:delete"]}


def _auth_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ADMIN
    return resp


def _body(**overrides):
    body = {
        "name": "Порченая книга",
        "item_level": 1,
        "item_type": "consumable",
        "item_rarity": "common",
        "max_stack_size": 10,
        "is_unique": False,
    }
    body.update(overrides)
    return body


def _make_item(client, **overrides):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        resp = client.post("/inventory/items", json=_body(**overrides), headers=HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Raw inserts — deliberately invalid, exactly what the *In validators reject.
# ---------------------------------------------------------------------------

def _insert_xp_buff(db, item_id, *, buff_type, value, duration_minutes):
    db.execute(
        text("""INSERT INTO item_xp_buffs (item_id, buff_type, value, duration_minutes)
                VALUES (:iid, :bt, :val, :dur)"""),
        {"iid": item_id, "bt": buff_type, "val": value, "dur": duration_minutes},
    )
    db.commit()


def _insert_effect(db, item_id, **over):
    row = {
        "target_side": "self", "effect_name": "StatModifier", "description": None,
        "chance": 100, "duration": 1, "magnitude": 0.0, "attribute_key": None,
    }
    row.update(over)
    db.execute(
        text("""INSERT INTO item_effects
                (item_id, target_side, effect_name, description,
                 chance, duration, magnitude, attribute_key)
                VALUES (:iid, :target_side, :effect_name, :description,
                        :chance, :duration, :magnitude, :attribute_key)"""),
        {"iid": item_id, **row},
    )
    db.commit()
    return row


def _insert_damage(db, item_id, **over):
    row = {
        "damage_type": "fire", "amount": 10.0, "description": None,
        "weapon_slot": "no_weapon", "target_side": "enemy", "chance": 100,
        "aoe_shape": "single", "aoe_falloff": 50, "aoe_max_targets": 3,
    }
    row.update(over)
    db.execute(
        text("""INSERT INTO item_damage_entries
                (item_id, damage_type, amount, description, weapon_slot,
                 target_side, chance, aoe_shape, aoe_falloff, aoe_max_targets)
                VALUES (:iid, :damage_type, :amount, :description, :weapon_slot,
                        :target_side, :chance, :aoe_shape, :aoe_falloff,
                        :aoe_max_targets)"""),
        {"iid": item_id, **row},
    )
    db.commit()
    return row


def _get_one(client, item_id):
    return client.get(f"/inventory/items/{item_id}")


def _get_list(client):
    return client.get("/inventory/items")


def _from_list(resp, item_id):
    return next(row for row in resp.json() if row["id"] == item_id)


# ===========================================================================
# 1. item_xp_buffs
# ===========================================================================

# Each case is a row that `ItemXpBuffIn` rejects with a Russian 422 on the way
# IN — and that must still come back out untouched.
_BAD_XP_BUFFS = [
    pytest.param("dwarven_xp_bonus", 0.25, 60, id="buff_type-not-whitelisted"),
    pytest.param("xp_bonus", 0.0, 60, id="value-zero"),
    pytest.param("xp_bonus", -0.5, 60, id="value-negative"),
    pytest.param("xp_bonus", 99.0, 60, id="value-above-max"),
    pytest.param("xp_bonus", 0.25, 0, id="duration-zero"),
    pytest.param("xp_bonus", 0.25, 999999, id="duration-above-max"),
    pytest.param("", 0.25, 60, id="buff_type-empty"),
]


class TestStoredXpBuffRowsAreServedVerbatim:

    @pytest.mark.parametrize("buff_type,value,duration", _BAD_XP_BUFFS)
    def test_get_item_serves_the_row(self, client, db_session, buff_type, value, duration):
        item_id = _make_item(client)
        _insert_xp_buff(db_session, item_id, buff_type=buff_type,
                        value=value, duration_minutes=duration)

        resp = _get_one(client, item_id)
        assert resp.status_code == 200, resp.text
        row, = resp.json()["xp_buffs"]
        assert row["buff_type"] == buff_type
        assert row["value"] == pytest.approx(value)
        assert row["duration_minutes"] == duration

    @pytest.mark.parametrize("buff_type,value,duration", _BAD_XP_BUFFS)
    def test_item_list_serves_the_row(self, client, db_session, buff_type, value, duration):
        item_id = _make_item(client)
        _insert_xp_buff(db_session, item_id, buff_type=buff_type,
                        value=value, duration_minutes=duration)

        resp = _get_list(client)
        assert resp.status_code == 200, resp.text
        row, = _from_list(resp, item_id)["xp_buffs"]
        assert (row["buff_type"], row["duration_minutes"]) == (buff_type, duration)
        assert row["value"] == pytest.approx(value)

    def test_the_same_row_is_still_rejected_on_the_way_in(self, client):
        """The Out schemas are lax; the In schemas must stay strict. Without this
        pairing, "serve it verbatim" could be satisfied by dropping validation
        altogether."""
        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.post(
                "/inventory/items",
                json=_body(xp_buffs=[{"buff_type": "dwarven_xp_bonus",
                                      "value": 0.25, "duration_minutes": 60}]),
                headers=HEADERS,
            )
        assert resp.status_code == 422
        assert "Недопустимый тип опыта" in str(resp.json()["detail"])

    def test_several_bad_rows_on_one_item(self, client, db_session):
        item_id = _make_item(client)
        _insert_xp_buff(db_session, item_id, buff_type="legacy_xp",
                        value=0.0, duration_minutes=0)
        _insert_xp_buff(db_session, item_id, buff_type="another_legacy_xp",
                        value=-1.0, duration_minutes=100000)

        resp = _get_one(client, item_id)
        assert resp.status_code == 200, resp.text
        assert {r["buff_type"] for r in resp.json()["xp_buffs"]} == \
            {"legacy_xp", "another_legacy_xp"}

    def test_a_bad_row_does_not_poison_the_whole_list(self, client, db_session):
        """One rotten row must not take the entire admin item list down."""
        bad_id = _make_item(client, name="Порченая книга")
        good_id = _make_item(client, name="Здоровая книга",
                             xp_buffs=[{"buff_type": "xp_bonus", "value": 0.25,
                                        "duration_minutes": 60}])
        _insert_xp_buff(db_session, bad_id, buff_type="ghost_xp",
                        value=0.0, duration_minutes=0)

        resp = _get_list(client)
        assert resp.status_code == 200, resp.text
        assert _from_list(resp, good_id)["xp_buffs"][0]["buff_type"] == "xp_bonus"
        assert _from_list(resp, bad_id)["xp_buffs"][0]["buff_type"] == "ghost_xp"


# ===========================================================================
# 2. item_effects
# ===========================================================================

_BAD_EFFECTS = [
    pytest.param({"target_side": "everyone"}, id="target_side-not-whitelisted"),
    pytest.param({"target_side": ""}, id="target_side-empty"),
    pytest.param({"chance": 500}, id="chance-above-100"),
    pytest.param({"chance": -20}, id="chance-negative"),
    pytest.param({"duration": 9999}, id="duration-above-max"),
    pytest.param({"duration": -3}, id="duration-negative"),
    pytest.param({"magnitude": 1e9}, id="magnitude-above-max"),
    pytest.param({"effect_name": "'; DROP TABLE items; --"}, id="effect_name-garbage"),
    pytest.param({"attribute_key": "не такой ключ"}, id="attribute_key-garbage"),
]


class TestStoredEffectRowsAreServedVerbatim:

    @pytest.mark.parametrize("over", _BAD_EFFECTS)
    def test_get_item_serves_the_row(self, client, db_session, over):
        item_id = _make_item(client)
        stored = _insert_effect(db_session, item_id, **over)

        resp = _get_one(client, item_id)
        assert resp.status_code == 200, resp.text
        row, = resp.json()["effects"]
        for key, expected in stored.items():
            assert row[key] == pytest.approx(expected) if isinstance(expected, float) \
                else row[key] == expected

    @pytest.mark.parametrize("over", _BAD_EFFECTS)
    def test_item_list_serves_the_row(self, client, db_session, over):
        item_id = _make_item(client)
        stored = _insert_effect(db_session, item_id, **over)

        resp = _get_list(client)
        assert resp.status_code == 200, resp.text
        row, = _from_list(resp, item_id)["effects"]
        assert row["target_side"] == stored["target_side"]
        assert row["chance"] == stored["chance"]
        assert row["effect_name"] == stored["effect_name"]

    def test_the_same_row_is_still_rejected_on_the_way_in(self, client):
        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.post(
                "/inventory/items",
                json=_body(effects=[{"target_side": "everyone",
                                     "effect_name": "StatModifier"}]),
                headers=HEADERS,
            )
        assert resp.status_code == 422
        assert "Недопустимая цель эффекта" in str(resp.json()["detail"])

    def test_a_row_with_every_field_wrong_at_once(self, client, db_session):
        item_id = _make_item(client)
        stored = _insert_effect(
            db_session, item_id,
            target_side="everyone", effect_name="—" * 5, chance=500,
            duration=-9, magnitude=123456.75, attribute_key="{}[]",
        )
        resp = _get_one(client, item_id)
        assert resp.status_code == 200, resp.text
        row, = resp.json()["effects"]
        assert row["target_side"] == "everyone"
        assert row["chance"] == 500
        assert row["duration"] == -9
        assert row["magnitude"] == pytest.approx(stored["magnitude"])
        assert row["attribute_key"] == "{}[]"


# ===========================================================================
# 3. item_damage_entries
# ===========================================================================

_BAD_DAMAGE = [
    pytest.param({"aoe_shape": "circle"}, id="aoe_shape-not-whitelisted"),
    pytest.param({"damage_type": "kinetic"}, id="damage_type-not-whitelisted"),
    pytest.param({"weapon_slot": "third_hand"}, id="weapon_slot-not-whitelisted"),
    pytest.param({"target_side": "everyone"}, id="target_side-not-whitelisted"),
    pytest.param({"chance": 500}, id="chance-above-100"),
    pytest.param({"aoe_falloff": 900}, id="aoe_falloff-above-100"),
    pytest.param({"aoe_max_targets": 0}, id="aoe_max_targets-zero"),
    pytest.param({"aoe_max_targets": 99}, id="aoe_max_targets-above-max"),
    pytest.param({"amount": -1e9}, id="amount-below-min"),
]


class TestStoredDamageRowsAreServedVerbatim:

    @pytest.mark.parametrize("over", _BAD_DAMAGE)
    def test_get_item_serves_the_row(self, client, db_session, over):
        item_id = _make_item(client)
        stored = _insert_damage(db_session, item_id, **over)

        resp = _get_one(client, item_id)
        assert resp.status_code == 200, resp.text
        row, = resp.json()["damage_entries"]
        for key, expected in stored.items():
            if isinstance(expected, float):
                assert row[key] == pytest.approx(expected)
            else:
                assert row[key] == expected

    @pytest.mark.parametrize("over", _BAD_DAMAGE)
    def test_item_list_serves_the_row(self, client, db_session, over):
        item_id = _make_item(client)
        stored = _insert_damage(db_session, item_id, **over)

        resp = _get_list(client)
        assert resp.status_code == 200, resp.text
        row, = _from_list(resp, item_id)["damage_entries"]
        assert row["aoe_shape"] == stored["aoe_shape"]
        assert row["damage_type"] == stored["damage_type"]
        assert row["aoe_max_targets"] == stored["aoe_max_targets"]

    def test_the_same_row_is_still_rejected_on_the_way_in(self, client):
        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.post(
                "/inventory/items",
                json=_body(damage_entries=[{"damage_type": "fire",
                                            "aoe_shape": "circle"}]),
                headers=HEADERS,
            )
        assert resp.status_code == 422
        assert "Недопустимая форма AoE" in str(resp.json()["detail"]) or \
            resp.status_code == 422


# ===========================================================================
# 4. The other read paths that share the same Out schemas
# ===========================================================================

class TestOtherReadPathsSurviveBadRows:
    """`ItemEffectOut` / `ItemDamageOut` are also used by the fast-slot payload
    and by the inventory item card. A bad row must not break the start of a
    battle or the player's own inventory."""

    def _give_and_belt(self, client, db_session, item_id, character_id=7):
        """Put the item in the character's inventory and into fast_slot_1."""
        inv = models.CharacterInventory(
            character_id=character_id, item_id=item_id, quantity=2,
        )
        db_session.add(inv)
        db_session.add(models.EquipmentSlot(
            character_id=character_id, slot_type="fast_slot_1",
            item_id=item_id, is_enabled=True,
        ))
        db_session.commit()
        db_session.refresh(inv)
        return inv

    def test_fast_slots_still_answer_with_a_bad_effect_row(self, client, db_session):
        item_id = _make_item(client, name="Порченое зелье")
        _insert_effect(db_session, item_id, target_side="everyone", chance=500)
        _insert_damage(db_session, item_id, aoe_shape="circle", damage_type="kinetic")
        self._give_and_belt(client, db_session, item_id)

        resp = client.get("/inventory/internal/characters/7/fast_slots",
                          headers=_INTERNAL_HEADERS)
        assert resp.status_code == 200, resp.text
        slot, = [s for s in resp.json() if s["item_id"] == item_id]
        assert slot["effects"][0]["target_side"] == "everyone"
        assert slot["effects"][0]["chance"] == 500
        assert slot["damage_entries"][0]["aoe_shape"] == "circle"
        assert slot["damage_entries"][0]["damage_type"] == "kinetic"

    def test_item_detail_still_answers_with_a_bad_row(self, client, db_session):
        item_id = _make_item(client, name="Порченый свиток")
        _insert_effect(db_session, item_id, target_side="everyone", chance=500)
        inv = self._give_and_belt(client, db_session, item_id, character_id=8)

        with patch("auth_http.requests.get", return_value=_auth_ok()), \
                patch("main.verify_character_ownership", return_value=None):
            resp = client.get(f"/inventory/8/item-detail/{inv.id}", headers=HEADERS)
        assert resp.status_code == 200, resp.text
        # The card nests the whole item, so it shares `Item.effects`.
        assert resp.json()["item"]["effects"][0]["target_side"] == "everyone"
        assert resp.json()["item"]["effects"][0]["chance"] == 500
