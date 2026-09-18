"""
FEAT-168 §3.1 / §3.3 / §3.12 — battle effect payload of an item.

Two child tables (`item_effects`, `item_damage_entries`) and three item columns
(`consumable_action`, `coating_turns`, `coating_bonus_damage`) ride inside the
existing admin item payload under `items:create` / `items:update`.

What is pinned here:
  * a nested create round-trips through the DB with the REAL column names — the
    readback is raw SQL, so a renamed column fails the test instead of silently
    producing an empty list (the project's silent-failure pattern);
  * PUT replace-all semantics: sending a list replaces the rows, omitting the
    key leaves them alone, sending [] wipes them;
  * an item with no rows answers `effects: []` / `damage_entries: []`;
  * DELETE /items/{id} takes the child rows with it (asserted by reading the
    tables back, not by trusting the 204);
  * every validation rule of §3.12 returns 422 with the Russian message.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

import models


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
        "name": "Зелье силы",
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


def _delete(client, item_id):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.delete(f"/inventory/items/{item_id}", headers=HEADERS)


def _get(client, item_id):
    return client.get(f"/inventory/items/{item_id}")


def _messages(resp):
    """All validation messages of a 422 response, joined."""
    detail = resp.json()["detail"]
    if isinstance(detail, str):
        return detail
    return " | ".join(str(err.get("msg", "")) for err in detail)


# Real column names — the whole point of reading back with raw SQL.
_EFFECT_COLUMNS = (
    "target_side", "effect_name", "description",
    "chance", "duration", "magnitude", "attribute_key",
)
_DAMAGE_COLUMNS = (
    "damage_type", "amount", "description", "weapon_slot", "target_side",
    "chance", "aoe_shape", "aoe_falloff", "aoe_max_targets",
)


def _read_effects(db, item_id):
    cols = ", ".join(_EFFECT_COLUMNS)
    rows = db.execute(
        text(f"SELECT {cols} FROM item_effects WHERE item_id = :iid ORDER BY id"),
        {"iid": item_id},
    ).fetchall()
    return [dict(zip(_EFFECT_COLUMNS, row)) for row in rows]


def _read_damage(db, item_id):
    cols = ", ".join(_DAMAGE_COLUMNS)
    rows = db.execute(
        text(f"SELECT {cols} FROM item_damage_entries WHERE item_id = :iid ORDER BY id"),
        {"iid": item_id},
    ).fetchall()
    return [dict(zip(_DAMAGE_COLUMNS, row)) for row in rows]


_EFFECT_A = {
    "target_side": "self", "effect_name": "StatModifier", "description": "Сила",
    "chance": 100, "duration": 3, "magnitude": 5.0, "attribute_key": "strength",
}
_EFFECT_B = {
    "target_side": "enemy", "effect_name": "Poison", "description": None,
    "chance": 75, "duration": 4, "magnitude": -7.5, "attribute_key": "periodic_damage",
}
_DAMAGE_A = {
    "damage_type": "fire", "amount": 42.5, "description": "Огненный свиток",
    "weapon_slot": "no_weapon", "target_side": "enemy", "chance": 90,
    "aoe_shape": "splash", "aoe_falloff": 25, "aoe_max_targets": 4,
}


# ===========================================================================
# 1. Nested CRUD round-trip
# ===========================================================================

class TestNestedEffectRoundTrip:

    def test_create_with_two_effects_and_one_damage_row(self, client, db_session):
        resp = _post(client, _body(
            effects=[_EFFECT_A, _EFFECT_B], damage_entries=[_DAMAGE_A],
        ))
        assert resp.status_code == 201, resp.text
        item_id = resp.json()["id"]

        # --- response shape
        data = resp.json()
        assert len(data["effects"]) == 2
        assert len(data["damage_entries"]) == 1
        assert {e["effect_name"] for e in data["effects"]} == {"StatModifier", "Poison"}

        # --- state read back from the DB with the real column names
        stored_effects = _read_effects(db_session, item_id)
        assert stored_effects == [_EFFECT_A, _EFFECT_B]
        assert _read_damage(db_session, item_id) == [_DAMAGE_A]

        # --- and the same rows come back out of GET
        got = _get(client, item_id)
        assert got.status_code == 200, got.text
        assert [e["attribute_key"] for e in got.json()["effects"]] == \
            ["strength", "periodic_damage"]
        assert got.json()["damage_entries"][0]["aoe_max_targets"] == 4

    def test_effect_row_ids_are_returned(self, client, db_session):
        item_id = _post(client, _body(effects=[_EFFECT_A])).json()["id"]
        row_id = _get(client, item_id).json()["effects"][0]["id"]
        stored = db_session.query(models.ItemEffect).filter_by(item_id=item_id).one()
        assert stored.id == row_id

    def test_item_without_rows_returns_empty_lists(self, client, db_session):
        item_id = _post(client, _body(name="Пустышка")).json()["id"]
        data = _get(client, item_id).json()
        assert data["effects"] == []
        assert data["damage_entries"] == []
        assert data["xp_buffs"] == []
        assert _read_effects(db_session, item_id) == []
        assert _read_damage(db_session, item_id) == []

    def test_coating_columns_round_trip(self, client, db_session):
        resp = _post(client, _body(
            name="Яд гадюки",
            consumable_action="weapon_coating",
            coating_turns=3,
            coating_bonus_damage=12.5,
            effects=[_EFFECT_B],
        ))
        assert resp.status_code == 201, resp.text
        item_id = resp.json()["id"]

        db_session.expire_all()
        stored = db_session.query(models.Items).get(item_id)
        assert stored.consumable_action == "weapon_coating"
        assert stored.coating_turns == 3
        assert stored.coating_bonus_damage == 12.5

    def test_instant_action_is_stored_as_null(self, client, db_session):
        item_id = _post(client, _body(name="Обычное зелье",
                                      consumable_action="instant")).json()["id"]
        db_session.expire_all()
        assert db_session.query(models.Items).get(item_id).consumable_action is None


class TestReplaceAllSemantics:

    def test_put_with_new_list_replaces(self, client, db_session):
        item_id = _post(client, _body(effects=[_EFFECT_A, _EFFECT_B])).json()["id"]
        resp = _put(client, item_id, _body(effects=[_EFFECT_B]))
        assert resp.status_code == 200, resp.text

        stored = _read_effects(db_session, item_id)
        assert stored == [_EFFECT_B]

    def test_put_omitting_the_key_leaves_rows_untouched(self, client, db_session):
        item_id = _post(client, _body(
            effects=[_EFFECT_A], damage_entries=[_DAMAGE_A],
        )).json()["id"]

        # a payload without `effects` / `damage_entries` at all
        resp = _put(client, item_id, _body(description="только описание"))
        assert resp.status_code == 200, resp.text

        assert _read_effects(db_session, item_id) == [_EFFECT_A]
        assert _read_damage(db_session, item_id) == [_DAMAGE_A]
        # and the untouched rows are still served
        assert len(_get(client, item_id).json()["effects"]) == 1

    def test_put_with_empty_list_clears_rows(self, client, db_session):
        item_id = _post(client, _body(
            effects=[_EFFECT_A], damage_entries=[_DAMAGE_A],
        )).json()["id"]

        resp = _put(client, item_id, _body(effects=[], damage_entries=[]))
        assert resp.status_code == 200, resp.text
        assert _read_effects(db_session, item_id) == []
        assert _read_damage(db_session, item_id) == []

    def test_replace_does_not_touch_another_item(self, client, db_session):
        keep_id = _post(client, _body(name="Чужое зелье",
                                      effects=[_EFFECT_A])).json()["id"]
        edit_id = _post(client, _body(name="Своё зелье",
                                      effects=[_EFFECT_B])).json()["id"]

        _put(client, edit_id, _body(name="Своё зелье", effects=[]))

        assert _read_effects(db_session, edit_id) == []
        assert _read_effects(db_session, keep_id) == [_EFFECT_A]


class TestCascadeDelete:

    def test_delete_item_removes_child_rows(self, client, db_session):
        item_id = _post(client, _body(
            effects=[_EFFECT_A, _EFFECT_B], damage_entries=[_DAMAGE_A],
        )).json()["id"]
        assert len(_read_effects(db_session, item_id)) == 2

        resp = _delete(client, item_id)
        assert resp.status_code == 204, resp.text

        db_session.expire_all()
        # read the tables back — a 204 alone proves nothing
        assert _read_effects(db_session, item_id) == []
        assert _read_damage(db_session, item_id) == []
        assert db_session.query(models.Items).get(item_id) is None

    def test_delete_keeps_other_items_rows(self, client, db_session):
        keep_id = _post(client, _body(name="Оставить",
                                      effects=[_EFFECT_A])).json()["id"]
        drop_id = _post(client, _body(name="Удалить",
                                      effects=[_EFFECT_B])).json()["id"]

        _delete(client, drop_id)

        db_session.expire_all()
        assert _read_effects(db_session, drop_id) == []
        assert _read_effects(db_session, keep_id) == [_EFFECT_A]


# ===========================================================================
# 2. Validation (§3.12) — 422 + Russian message
# ===========================================================================

class TestEffectValidation:

    @pytest.mark.parametrize("chance", [-1, 101])
    def test_chance_out_of_range(self, client, chance):
        resp = _post(client, _body(effects=[dict(_EFFECT_A, chance=chance)]))
        assert resp.status_code == 422
        assert "Шанс эффекта должен быть от 0 до 100" in _messages(resp)

    @pytest.mark.parametrize("duration", [-1, 101])
    def test_duration_out_of_range(self, client, duration):
        resp = _post(client, _body(effects=[dict(_EFFECT_A, duration=duration)]))
        assert resp.status_code == 422
        assert "Длительность эффекта должна быть от 0 до 100 ходов" in _messages(resp)

    @pytest.mark.parametrize("magnitude", [-10000.5, 10000.5])
    def test_magnitude_out_of_range(self, client, magnitude):
        resp = _post(client, _body(effects=[dict(_EFFECT_A, magnitude=magnitude)]))
        assert resp.status_code == 422
        assert "Сила эффекта должна быть от -10000 до 10000" in _messages(resp)

    def test_boundary_values_are_accepted(self, client, db_session):
        resp = _post(client, _body(effects=[
            dict(_EFFECT_A, chance=0, duration=0, magnitude=-10000.0),
            dict(_EFFECT_B, chance=100, duration=100, magnitude=10000.0),
        ]))
        assert resp.status_code == 201, resp.text
        stored = _read_effects(db_session, resp.json()["id"])
        assert [r["magnitude"] for r in stored] == [-10000.0, 10000.0]

    def test_unknown_target_side(self, client):
        resp = _post(client, _body(effects=[dict(_EFFECT_A, target_side="everyone")]))
        assert resp.status_code == 422
        assert "Недопустимая цель эффекта" in _messages(resp)

    @pytest.mark.parametrize("side", ["self", "enemy", "ally", "all_allies"])
    def test_whitelisted_target_sides(self, client, side):
        resp = _post(client, _body(name=f"Зелье {side}",
                                   effects=[dict(_EFFECT_A, target_side=side)]))
        assert resp.status_code == 201, resp.text

    def test_effect_name_is_required(self, client):
        resp = _post(client, _body(effects=[dict(_EFFECT_A, effect_name="   ")]))
        assert resp.status_code == 422
        assert "Название эффекта обязательно" in _messages(resp)

    def test_effect_name_rejects_injection_characters(self, client):
        resp = _post(client, _body(effects=[
            dict(_EFFECT_A, effect_name="'; DROP TABLE items; --"),
        ]))
        assert resp.status_code == 422
        assert "допустимы только латинские буквы" in _messages(resp)

    def test_attribute_key_rejects_injection_characters(self, client):
        resp = _post(client, _body(effects=[
            dict(_EFFECT_A, attribute_key='" OR 1=1 --'),
        ]))
        assert resp.status_code == 422
        assert "допустимы только латинские буквы" in _messages(resp)

    def test_effect_name_length_cap(self, client):
        resp = _post(client, _body(effects=[dict(_EFFECT_A, effect_name="A" * 51)]))
        assert resp.status_code == 422
        assert "не длиннее 50 символов" in _messages(resp)

    def test_more_than_20_effect_rows(self, client):
        resp = _post(client, _body(effects=[_EFFECT_A] * 21))
        assert resp.status_code == 422
        assert "Не больше 20 эффектов у предмета" in _messages(resp)

    def test_exactly_20_effect_rows_pass(self, client, db_session):
        resp = _post(client, _body(effects=[_EFFECT_A] * 20))
        assert resp.status_code == 201, resp.text
        assert len(_read_effects(db_session, resp.json()["id"])) == 20


class TestDamageValidation:

    def test_unknown_damage_type(self, client):
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, damage_type="holy")]))
        assert resp.status_code == 422
        assert "Недопустимый тип урона" in _messages(resp)

    @pytest.mark.parametrize("damage_type", ["physical", "fire", "magic", "damning"])
    def test_whitelisted_damage_types(self, client, damage_type):
        resp = _post(client, _body(name=f"Свиток {damage_type}",
                                   damage_entries=[dict(_DAMAGE_A, damage_type=damage_type)]))
        assert resp.status_code == 201, resp.text

    def test_unknown_weapon_slot(self, client):
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, weapon_slot="off_hand")]))
        assert resp.status_code == 422
        assert "Недопустимый слот оружия" in _messages(resp)

    @pytest.mark.parametrize("slot", ["main_weapon", "additional_weapons", "no_weapon"])
    def test_whitelisted_weapon_slots(self, client, slot):
        resp = _post(client, _body(name=f"Свиток {slot}",
                                   damage_entries=[dict(_DAMAGE_A, weapon_slot=slot)]))
        assert resp.status_code == 201, resp.text

    def test_unknown_target_side(self, client):
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, target_side="nobody")]))
        assert resp.status_code == 422
        assert "Недопустимая цель урона" in _messages(resp)

    def test_unknown_aoe_shape(self, client):
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, aoe_shape="star")]))
        assert resp.status_code == 422
        assert "Недопустимая форма области урона" in _messages(resp)

    @pytest.mark.parametrize("shape", ["single", "splash", "cleave", "all", "random_n"])
    def test_every_shape_the_engine_implements_is_accepted(self, client, shape):
        """Ревью #1 §1: белый список обязан совпадать с resolve_aoe_targets.

        Раньше здесь были line/cone/circle — движок про них не знает и молча
        бьёт по одной цели, а splash/cleave/random_n, которые он умеет, ловили
        422 и три кнопки из пяти в админке было нечем сохранить.
        """
        resp = _post(client, _body(
            name=f"Свиток {shape}",
            damage_entries=[dict(_DAMAGE_A, aoe_shape=shape)],
        ))
        assert resp.status_code == 201, resp.text
        assert resp.json()["damage_entries"][0]["aoe_shape"] == shape

    @pytest.mark.parametrize("shape", ["line", "cone", "circle"])
    def test_shapes_the_engine_does_not_implement_are_rejected(self, client, shape):
        """Сохранить форму, которую движок проигнорирует, нельзя."""
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, aoe_shape=shape)]))
        assert resp.status_code == 422
        assert "Недопустимая форма области урона" in _messages(resp)

    @pytest.mark.parametrize("amount", [-10000.5, 10000.5])
    def test_amount_out_of_range(self, client, amount):
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, amount=amount)]))
        assert resp.status_code == 422
        assert "Урон должен быть от -10000 до 10000" in _messages(resp)

    @pytest.mark.parametrize("chance", [-1, 101])
    def test_chance_out_of_range(self, client, chance):
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, chance=chance)]))
        assert resp.status_code == 422
        assert "Шанс урона должен быть от 0 до 100" in _messages(resp)

    @pytest.mark.parametrize("falloff", [-1, 101])
    def test_aoe_falloff_out_of_range(self, client, falloff):
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, aoe_falloff=falloff)]))
        assert resp.status_code == 422
        assert "Затухание области должно быть от 0 до 100" in _messages(resp)

    @pytest.mark.parametrize("targets", [0, 11])
    def test_aoe_max_targets_out_of_range(self, client, targets):
        resp = _post(client, _body(damage_entries=[dict(_DAMAGE_A, aoe_max_targets=targets)]))
        assert resp.status_code == 422
        assert "Число целей области должно быть от 1 до 10" in _messages(resp)

    def test_more_than_10_damage_rows(self, client):
        resp = _post(client, _body(damage_entries=[_DAMAGE_A] * 11))
        assert resp.status_code == 422
        assert "Не больше 10 строк урона у предмета" in _messages(resp)

    def test_exactly_10_damage_rows_pass(self, client, db_session):
        resp = _post(client, _body(damage_entries=[_DAMAGE_A] * 10))
        assert resp.status_code == 201, resp.text
        assert len(_read_damage(db_session, resp.json()["id"])) == 10


class TestCoatingValidation:

    def test_unknown_consumable_action(self, client):
        resp = _post(client, _body(consumable_action="explode"))
        assert resp.status_code == 422
        assert "Недопустимый тип применения расходника" in _messages(resp)

    @pytest.mark.parametrize("turns", [0, 51])
    def test_coating_turns_out_of_range(self, client, turns):
        resp = _post(client, _body(consumable_action="weapon_coating",
                                   coating_turns=turns, coating_bonus_damage=5))
        assert resp.status_code == 422
        assert "Длительность яда должна быть от 1 до 50 ходов" in _messages(resp)

    def test_coating_turns_required_for_coating(self, client):
        resp = _post(client, _body(consumable_action="weapon_coating",
                                   coating_bonus_damage=5))
        assert resp.status_code == 422
        assert "Длительность яда должна быть от 1 до 50 ходов" in _messages(resp)

    @pytest.mark.parametrize("bonus", [-0.5, 10000.5])
    def test_coating_bonus_damage_out_of_range(self, client, bonus):
        resp = _post(client, _body(consumable_action="weapon_coating",
                                   coating_turns=3, coating_bonus_damage=bonus))
        assert resp.status_code == 422
        assert "Прибавка урона от яда должна быть от 0 до 10000" in _messages(resp)

    def test_coating_bonus_required_for_coating(self, client):
        resp = _post(client, _body(consumable_action="weapon_coating", coating_turns=3))
        assert resp.status_code == 422
        assert "Прибавка урона от яда должна быть от 0 до 10000" in _messages(resp)

    def test_coating_boundaries_accepted(self, client, db_session):
        resp = _post(client, _body(consumable_action="weapon_coating",
                                   coating_turns=50, coating_bonus_damage=0))
        assert resp.status_code == 201, resp.text
        db_session.expire_all()
        stored = db_session.query(models.Items).get(resp.json()["id"])
        assert (stored.coating_turns, stored.coating_bonus_damage) == (50, 0)

    def test_coating_params_without_coating_action(self, client):
        resp = _post(client, _body(coating_turns=3, coating_bonus_damage=5))
        assert resp.status_code == 422
        assert "Параметры яда указываются только для предмета «яд на оружие»" in _messages(resp)

    def test_cleanse_action_needs_no_coating_params(self, client, db_session):
        resp = _post(client, _body(
            name="Противоядие", consumable_action="cleanse",
            effects=[dict(_EFFECT_A, effect_name="Cleanse", attribute_key="debuff",
                          magnitude=0.0, duration=0)],
        ))
        assert resp.status_code == 201, resp.text
        db_session.expire_all()
        assert db_session.query(models.Items).get(
            resp.json()["id"]).consumable_action == "cleanse"


class TestBattlePayloadItemTypeRules:

    @pytest.mark.parametrize("item_type", ["consumable", "scroll"])
    def test_allowed_item_types(self, client, item_type):
        resp = _post(client, _body(name=f"Штука {item_type}", item_type=item_type,
                                   effects=[_EFFECT_A]))
        assert resp.status_code == 201, resp.text

    @pytest.mark.parametrize("item_type", ["weapon", "misc", "resource", "body"])
    def test_other_item_types_rejected(self, client, item_type):
        resp = _post(client, _body(item_type=item_type, effects=[_EFFECT_A]))
        assert resp.status_code == 422
        assert "Боевые эффекты доступны только для расходников и свитков" in _messages(resp)

    def test_damage_rows_also_bound_to_item_type(self, client):
        resp = _post(client, _body(item_type="weapon", damage_entries=[_DAMAGE_A]))
        assert resp.status_code == 422
        assert "Боевые эффекты доступны только для расходников и свитков" in _messages(resp)

    def test_consumable_action_also_bound_to_item_type(self, client):
        resp = _post(client, _body(item_type="misc", consumable_action="cleanse"))
        assert resp.status_code == 422
        assert "Боевые эффекты доступны только для расходников и свитков" in _messages(resp)

    def test_food_cannot_carry_battle_effects(self, client):
        resp = _post(client, _body(is_food=True, effects=[_EFFECT_A]))
        assert resp.status_code == 422
        assert "Еда не может иметь боевых эффектов" in _messages(resp)

    def test_food_without_battle_payload_is_fine(self, client):
        resp = _post(client, _body(name="Хлеб", is_food=True))
        assert resp.status_code == 201, resp.text


# ===========================================================================
# 3. `use_item` in battle (ISSUES #3 fix) — DB state, not just the status code
# ===========================================================================

@pytest.fixture()
def authed_client(client, db_session):
    from auth_http import get_current_user_via_http, UserRead
    from main import app

    db_session.execute(text(
        "CREATE TABLE IF NOT EXISTS characters (id INTEGER PRIMARY KEY, user_id INTEGER)"
    ))
    db_session.execute(text("INSERT OR IGNORE INTO characters (id, user_id) VALUES (1, 1)"))
    db_session.commit()

    user = UserRead(id=1, username="tester", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


class TestUseItemInBattleKeepsInventory:
    """The guard must refuse in Russian AND leave the stack untouched."""

    def _seed(self, db_session):
        item = models.Items(
            id=770, name="Зелье в бою", item_level=1, item_type="consumable",
            item_rarity="common", max_stack_size=10, is_unique=False,
            health_recovery=50,
        )
        db_session.add(item)
        db_session.flush()
        db_session.add(models.CharacterInventory(character_id=1, item_id=770, quantity=5))
        db_session.execute(text(
            "INSERT OR IGNORE INTO battles (id, status) VALUES (1, 'in_progress')"))
        db_session.execute(text(
            "INSERT OR IGNORE INTO battle_participants (id, battle_id, character_id) "
            "VALUES (1, 1, 1)"))
        db_session.commit()

    def test_item_is_not_consumed_while_in_battle(self, authed_client, db_session):
        self._seed(db_session)

        resp = authed_client.post("/inventory/1/use_item",
                                  json={"item_id": 770, "quantity": 1})

        assert resp.status_code == 400
        assert "бо" in resp.json()["detail"].lower()

        db_session.expire_all()
        row = db_session.query(models.CharacterInventory).filter_by(
            character_id=1, item_id=770).one()
        assert row.quantity == 5, "стопка не должна расходоваться при отказе"
