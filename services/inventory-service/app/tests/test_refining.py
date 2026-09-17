"""
FEAT-165 — player refining: GET refining-rules, GET refine-info, POST refine.

Every write test reads `character_inventory` / `character_professions` /
`character_recipes` back from the DB instead of trusting the response
(the project's silent-failure pattern: a broken query or a missing result
item must not look like a success).
"""

from unittest.mock import patch

import pytest
from sqlalchemy import text

import crud
import models
from auth_http import get_current_user_via_http
from main import app
from tests.feat165_helpers import (
    OWNER, PROF_ID,
    ensure_characters, seed_professions, assign_profession, make_item,
    add_stack, add_conversion, make_recipe, owned_quantity, profession_state,
    learned_recipe_ids, put_in_battle, start_gathering,
)

ORE, INGOT, DUST, HERB = 100, 200, 201, 102
INGREDIENT, REAGENT = 103, 202
NEVER_DOUBLE = 0.999  # random.random() value that never passes a doubling roll


@pytest.fixture()
def env(client, db_session):
    ensure_characters(db_session)
    seed_professions(db_session)
    make_item(db_session, ORE, "Медная руда", subcategory="ore")
    make_item(db_session, HERB, "Мята", subcategory="herb")
    make_item(db_session, INGREDIENT, "Пшеница", subcategory="ingredient")
    make_item(db_session, INGOT, "Медный слиток", subcategory="ingot")
    make_item(db_session, DUST, "Магическая пыль", subcategory="magic_dust", rarity="rare")
    make_item(db_session, REAGENT, "Экстракт", subcategory="reagent")
    add_conversion(db_session, ORE, "blacksmith", INGOT, source_quantity=2, result_quantity=1)
    add_conversion(db_session, ORE, "jeweler", DUST, source_quantity=1, result_quantity=1)
    add_conversion(db_session, INGREDIENT, "cook", REAGENT, source_quantity=1, result_quantity=2)
    app.dependency_overrides[get_current_user_via_http] = lambda: OWNER
    yield {"client": client, "db": db_session}
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _refine(client, source_item_id, quantity, character_id=1):
    return client.post(
        f"/inventory/crafting/{character_id}/refine",
        json={"source_item_id": source_item_id, "quantity": quantity},
    )


def _no_double():
    return patch("crud.random.random", return_value=NEVER_DOUBLE)


# ===========================================================================
# Happy paths
# ===========================================================================

class TestRefineHappyPath:

    def test_two_to_one_odd_quantity_keeps_remainder(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 7)

        with _no_double():
            resp = _refine(c, ORE, 7)

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["batches"] == 3
        assert data["consumed_quantity"] == 6
        assert data["leftover_quantity"] == 1
        assert data["doubled_batches"] == 0
        assert data["result_quantity"] == 3
        assert data["result_item"]["id"] == INGOT
        assert data["xp_earned"] == 3 * crud.REFINE_XP_BY_RARITY["common"]
        # DB state
        assert owned_quantity(db, 1, ORE) == 1
        assert owned_quantity(db, 1, INGOT) == 3
        assert profession_state(db, 1) == (1, 15)

    def test_partial_quantity_leaves_the_rest_of_the_stack(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 10)

        with _no_double():
            resp = _refine(c, ORE, 5)

        assert resp.status_code == 200, resp.text
        assert resp.json()["leftover_quantity"] == 1
        assert owned_quantity(db, 1, ORE) == 6  # 10 - 4
        assert owned_quantity(db, 1, INGOT) == 2

    def test_one_to_two_cook(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "cook")
        add_stack(db, 1, INGREDIENT, 3)

        with _no_double():
            resp = _refine(c, INGREDIENT, 3)

        assert resp.status_code == 200, resp.text
        assert resp.json()["result_quantity"] == 6
        assert owned_quantity(db, 1, INGREDIENT) == 0
        assert owned_quantity(db, 1, REAGENT) == 6

    def test_same_ore_different_result_for_jeweler(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler")
        add_stack(db, 1, ORE, 2)

        with _no_double():
            resp = _refine(c, ORE, 2)

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["result_item"]["id"] == DUST
        assert data["xp_earned"] == 2 * crud.REFINE_XP_BY_RARITY["rare"]
        assert owned_quantity(db, 1, DUST) == 2
        assert owned_quantity(db, 1, INGOT) == 0

    def test_alchemist_refines_reagent_into_essence(self, env):
        """The refine path itself accepts the alchemist's reagent source (config
        inserted directly; the admin endpoint currently refuses it, see
        test_item_conversions_admin)."""
        db, c = env["db"], env["client"]
        make_item(db, 203, "Эссенция жизни", subcategory="essence", rarity="epic")
        add_conversion(db, REAGENT, "alchemist", 203, source_quantity=2, result_quantity=1)
        assign_profession(db, 1, "alchemist")
        add_stack(db, 1, REAGENT, 4)

        with _no_double():
            resp = _refine(c, REAGENT, 4)

        assert resp.status_code == 200, resp.text
        assert resp.json()["xp_earned"] == 2 * crud.REFINE_XP_BY_RARITY["epic"]
        assert owned_quantity(db, 1, REAGENT) == 0
        assert owned_quantity(db, 1, 203) == 2

    def test_consumes_across_several_stacks(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 3)
        add_stack(db, 1, ORE, 4)

        with _no_double():
            resp = _refine(c, ORE, 7)

        assert resp.status_code == 200, resp.text
        assert resp.json()["consumed_quantity"] == 6
        assert owned_quantity(db, 1, ORE) == 1
        # an emptied stack is deleted, not left at quantity 0
        db.expire_all()
        rows = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == ORE,
        ).all()
        assert [r.quantity for r in rows] == [1]

    def test_other_characters_stacks_are_not_touched(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 2)
        add_stack(db, 2, ORE, 50)

        with _no_double():
            assert _refine(c, ORE, 3).status_code == 400  # only 2 of its own
            assert _refine(c, ORE, 2).status_code == 200

        assert owned_quantity(db, 2, ORE) == 50
        assert owned_quantity(db, 2, INGOT) == 0

    def test_unidentified_stack_is_not_used(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4, is_identified=False)

        resp = _refine(c, ORE, 2)

        assert resp.status_code == 400
        assert owned_quantity(db, 1, ORE) == 4


class TestDoublingRoll:

    def test_roll_per_batch_rank1(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith", rank=1)
        add_stack(db, 1, ORE, 6)

        # rank 1 = 5 %: 0.01 and 0.04 pass, 0.05 does not
        with patch("crud.random.random", side_effect=[0.01, 0.05, 0.04]):
            resp = _refine(c, ORE, 6)

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["batches"] == 3
        assert data["doubled_batches"] == 2
        assert data["result_quantity"] == 5
        assert owned_quantity(db, 1, INGOT) == 5
        # XP is per batch, doubling does not add XP
        assert data["xp_earned"] == 15

    def test_roll_rank3_uses_20_percent(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "cook", rank=3, experience=100)
        add_stack(db, 1, INGREDIENT, 2)

        with patch("crud.random.random", side_effect=[0.19, 0.20]):
            resp = _refine(c, INGREDIENT, 2)

        assert resp.status_code == 200, resp.text
        assert resp.json()["doubled_batches"] == 1
        # 2 per batch, (2 batches + 1 doubled) * 2
        assert owned_quantity(db, 1, REAGENT) == 6

    @pytest.mark.parametrize("rank,expected", [(1, 0.05), (2, 0.10), (3, 0.20), (4, 0.20), (0, 0.0)])
    def test_chance_table(self, rank, expected):
        assert crud.refine_double_chance(rank) == expected

    @pytest.mark.parametrize("rarity,xp", [("common", 5), ("rare", 12), ("epic", 25), ("legendary", 50)])
    def test_xp_table(self, rarity, xp):
        assert crud.refine_xp_per_batch(rarity) == xp


class TestRefineXpAndRankUp:

    def test_rank_up_and_auto_learn_through_helper(self, env):
        db, c = env["db"], env["client"]
        make_item(db, 300, "Медный кинжал", item_type="weapon", max_stack=1)
        make_recipe(db, 50, "jeweler", 300, auto_learn_rank=2, required_rank=2, name="Кольцо подмастерья")
        make_recipe(db, 51, "jeweler", 300, auto_learn_rank=3, required_rank=3, name="Кольцо мастера")
        assign_profession(db, 1, "jeweler", rank=1, experience=0)
        add_stack(db, 1, ORE, 2)

        with _no_double():
            resp = _refine(c, ORE, 2)  # 2 rare batches = 24 XP >= 20

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["xp_earned"] == 24
        assert data["new_total_xp"] == 24
        assert data["rank_up"] is True
        assert data["new_rank_name"] == "Подмастерье"
        assert data["auto_learned_recipes"] == [{"id": 50, "name": "Кольцо подмастерья"}]
        assert profession_state(db, 1) == (2, 24)
        assert learned_recipe_ids(db, 1) == [50]

    def test_xp_buff_multiplies_refine_xp(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 2)

        with _no_double(), patch("crud.get_xp_multiplier", return_value=2.0):
            resp = _refine(c, ORE, 2)

        assert resp.status_code == 200, resp.text
        assert resp.json()["xp_earned"] == 10
        assert profession_state(db, 1) == (1, 10)


# ===========================================================================
# Errors — nothing may be consumed
# ===========================================================================

class TestRefineErrorsConsumeNothing:

    def _assert_untouched(self, db, ore=4):
        assert owned_quantity(db, 1, ORE) == ore
        assert owned_quantity(db, 1, INGOT) == 0
        assert owned_quantity(db, 1, DUST) == 0

    def test_wrong_subcategory(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)
        add_stack(db, 1, HERB, 4)
        # even a (legacy) conversion row does not make herbs refinable by a blacksmith
        add_conversion(db, HERB, "blacksmith", INGOT)

        resp = _refine(c, HERB, 4)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Этот предмет нельзя переработать"
        assert owned_quantity(db, 1, HERB) == 4
        self._assert_untouched(db)

    def test_missing_config_for_profession(self, env):
        db, c = env["db"], env["client"]
        make_item(db, 104, "Железная руда", subcategory="ore")
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)
        add_stack(db, 1, 104, 4)

        resp = _refine(c, 104, 4)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Для этого сырья не настроен результат переработки"
        assert owned_quantity(db, 1, 104) == 4
        self._assert_untouched(db)

    def test_missing_result_item(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)
        # Point the config at an item id that does not exist (FK checks off,
        # the way a broken prod row would look).
        db.commit()
        db.execute(text("PRAGMA foreign_keys=OFF"))
        db.execute(
            text("UPDATE item_conversions SET result_item_id = 9999 "
                 "WHERE source_item_id = :s AND profession_id = :p"),
            {"s": ORE, "p": PROF_ID["blacksmith"]},
        )
        db.commit()
        db.execute(text("PRAGMA foreign_keys=ON"))

        resp = _refine(c, ORE, 4)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Результат переработки не найден"
        self._assert_untouched(db)

    def test_unknown_source_item_404(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)

        resp = _refine(c, 424242, 2)

        assert resp.status_code == 404
        self._assert_untouched(db)

    def test_not_enough_raw(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)

        resp = _refine(c, ORE, 5)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Недостаточно сырья"
        self._assert_untouched(db)

    def test_less_than_one_batch(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)

        resp = _refine(c, ORE, 1)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Нужно минимум 2 шт. для переработки"
        self._assert_untouched(db)

    def test_no_profession(self, env):
        db, c = env["db"], env["client"]
        add_stack(db, 1, ORE, 4)

        resp = _refine(c, ORE, 2)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "У персонажа нет профессии"
        self._assert_untouched(db)

    def test_enchanter_has_no_refining(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "enchanter")
        add_stack(db, 1, ORE, 4)

        resp = _refine(c, ORE, 2)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Ваша профессия не перерабатывает сырьё"
        self._assert_untouched(db)

    def test_blocked_in_battle(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)
        put_in_battle(db, 1)

        resp = _refine(c, ORE, 2)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Нельзя перерабатывать во время боя"
        self._assert_untouched(db)

    def test_blocked_while_gathering(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)
        start_gathering(db, 1)

        resp = _refine(c, ORE, 2)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Нельзя перерабатывать во время добычи"
        self._assert_untouched(db)

    def test_unexpected_error_rolls_back(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)

        with _no_double(), patch("crud.award_profession_xp", side_effect=RuntimeError("boom")):
            resp = _refine(c, ORE, 4)

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Ошибка при переработке"
        assert "boom" not in resp.text
        self._assert_untouched(db)
        assert profession_state(db, 1) == (1, 0)


# ===========================================================================
# Security / validation
# ===========================================================================

class TestRefineSecurity:

    def test_unauthenticated_401(self, client):
        resp = client.post("/inventory/crafting/1/refine", json={"source_item_id": ORE, "quantity": 2})
        assert resp.status_code == 401

    def test_refine_info_unauthenticated_401(self, client):
        assert client.get("/inventory/crafting/1/refine-info").status_code == 401

    def test_refining_rules_unauthenticated_401(self, client):
        assert client.get("/inventory/crafting/refining-rules").status_code == 401

    def test_foreign_character_403_and_nothing_consumed(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 2, "blacksmith")
        add_stack(db, 2, ORE, 4)

        resp = _refine(c, ORE, 2, character_id=2)

        assert resp.status_code == 403
        assert owned_quantity(db, 2, ORE) == 4
        assert owned_quantity(db, 2, INGOT) == 0

    def test_foreign_refine_info_403(self, env):
        assert env["client"].get("/inventory/crafting/2/refine-info").status_code == 403

    def test_unknown_character_404(self, env):
        assert _refine(env["client"], ORE, 2, character_id=31337).status_code == 404

    @pytest.mark.parametrize("quantity", [0, -1, crud.REFINE_MAX_QUANTITY + 1, 10 ** 12, "abc",
                                          "1; DROP TABLE character_inventory; --", None])
    def test_invalid_quantity_422(self, env, quantity):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)

        resp = _refine(c, ORE, quantity)

        assert resp.status_code == 422
        assert owned_quantity(db, 1, ORE) == 4

    @pytest.mark.parametrize("source", [0, -5, "' OR 1=1 --", None])
    def test_invalid_source_id_422(self, env, source):
        resp = env["client"].post(
            "/inventory/crafting/1/refine", json={"source_item_id": source, "quantity": 2},
        )
        assert resp.status_code == 422

    def test_max_quantity_is_accepted_by_validation(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "blacksmith")
        add_stack(db, 1, ORE, 4)
        resp = _refine(c, ORE, crud.REFINE_MAX_QUANTITY)
        assert resp.status_code == 400  # passes validation, fails on stock
        assert resp.json()["detail"] == "Недостаточно сырья"


# ===========================================================================
# refine-info
# ===========================================================================

class TestRefineInfo:

    def test_lists_owned_configured_sources(self, env):
        db, c = env["db"], env["client"]
        make_item(db, 105, "Оловянная руда", subcategory="ore")  # no config
        make_item(db, 106, "Серебряная руда", subcategory="ore")  # config, not owned
        add_conversion(db, 106, "blacksmith", INGOT)
        assign_profession(db, 1, "blacksmith", rank=2, experience=20)
        add_stack(db, 1, ORE, 3)
        add_stack(db, 1, ORE, 2)
        add_stack(db, 1, 105, 5)
        add_stack(db, 1, INGREDIENT, 5)  # cook's config only

        resp = c.get("/inventory/crafting/1/refine-info")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["can_refine"] is True
        assert data["profession_slug"] == "blacksmith"
        assert data["source_subcategory"] == "ore"
        assert data["result_subcategory"] == "ingot"
        assert data["double_chance_pct"] == 10
        assert len(data["sources"]) == 1
        src = data["sources"][0]
        assert src["source_item_id"] == ORE
        assert src["owned_quantity"] == 5
        assert src["source_quantity"] == 2
        assert src["max_batches"] == 2
        assert src["result_item"]["id"] == INGOT
        assert src["result_quantity"] == 1
        assert src["xp_per_batch"] == 5

    def test_empty_sources_when_nothing_owned(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=3, experience=100)
        data = c.get("/inventory/crafting/1/refine-info").json()
        assert data["can_refine"] is True
        assert data["double_chance_pct"] == 20
        assert data["sources"] == []

    def test_no_profession(self, env):
        data = env["client"].get("/inventory/crafting/1/refine-info").json()
        assert data["can_refine"] is False
        assert data["profession_slug"] is None
        assert data["sources"] == []

    def test_enchanter_cannot_refine(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "enchanter")
        add_stack(db, 1, ORE, 5)
        data = c.get("/inventory/crafting/1/refine-info").json()
        assert data["can_refine"] is False
        assert data["profession_slug"] == "enchanter"
        assert data["sources"] == []


# ===========================================================================
# refining-rules
# ===========================================================================

class TestRefiningRules:

    def test_rules_for_all_refining_professions(self, env):
        resp = env["client"].get("/inventory/crafting/refining-rules")
        assert resp.status_code == 200, resp.text
        rules = {r["profession_slug"]: r for r in resp.json()}
        assert set(rules) == {"blacksmith", "alchemist", "cook", "jeweler", "scholar"}
        assert rules["blacksmith"]["source_subcategory"] == "ore"
        assert rules["blacksmith"]["result_subcategory"] == "ingot"
        assert rules["jeweler"]["result_subcategory"] == "magic_dust"
        assert rules["alchemist"]["source_subcategory"] == "reagent"
        assert rules["alchemist"]["result_subcategory"] == "essence"
        assert rules["cook"]["source_subcategory"] == "ingredient"
        assert rules["cook"]["result_subcategory"] == "reagent"
        assert rules["scholar"]["source_subcategory"] == "trophy"
        assert rules["scholar"]["result_subcategory"] == "material"
        assert rules["scholar"]["profession_name"] == "Мистик"
        assert rules["blacksmith"]["profession_id"] == PROF_ID["blacksmith"]

    def test_inactive_profession_is_skipped(self, client, db_session):
        ensure_characters(db_session)
        seed_professions(db_session, inactive=("cook",))
        app.dependency_overrides[get_current_user_via_http] = lambda: OWNER
        try:
            slugs = {r["profession_slug"] for r in client.get("/inventory/crafting/refining-rules").json()}
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)
        assert "cook" not in slugs
        assert "blacksmith" in slugs
