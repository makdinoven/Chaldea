"""
FEAT-165 D7 — base recipes (`auto_learn_rank`) reach characters that already
have the rank (lazy sync on GET recipes / GET my profession), plus the
rank-up and admin set-rank paths. `character_recipes` is read back from the DB.
"""

from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

import crud
from auth_http import get_current_user_via_http, UserRead
from main import app
from tests.feat165_helpers import (
    OWNER, ensure_characters, seed_professions, assign_profession, make_item,
    make_recipe, learned_recipe_ids, profession_state,
)

RESULT = 300


@pytest.fixture()
def env(client, db_session):
    ensure_characters(db_session)
    seed_professions(db_session)
    make_item(db_session, RESULT, "Изделие", item_type="ring", max_stack=1)
    app.dependency_overrides[get_current_user_via_http] = lambda: OWNER
    yield {"client": client, "db": db_session}
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _recipe_ids(resp):
    assert resp.status_code == 200, resp.text
    return sorted(r["id"] for r in resp.json())


class TestLazySyncOnRecipes:

    def test_recipe_created_after_reaching_rank_appears(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=1)
        # admin creates the base recipe later
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=1)

        assert _recipe_ids(c.get("/inventory/crafting/1/recipes")) == [10]
        assert learned_recipe_ids(db, 1) == [10]
        assert c.get("/inventory/crafting/1/recipes").json()[0]["source"] == "learned"

    def test_higher_rank_recipe_not_learned(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=1)
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=2, required_rank=2)

        assert _recipe_ids(c.get("/inventory/crafting/1/recipes")) == []
        assert learned_recipe_ids(db, 1) == []

    def test_lower_ranks_are_included(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=3, experience=100)
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=1)
        make_recipe(db, 11, "jeweler", RESULT, auto_learn_rank=2)
        make_recipe(db, 12, "jeweler", RESULT, auto_learn_rank=3)

        assert _recipe_ids(c.get("/inventory/crafting/1/recipes")) == [10, 11, 12]

    def test_inactive_recipe_never_learned(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=3, experience=100)
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=1, is_active=False)

        assert _recipe_ids(c.get("/inventory/crafting/1/recipes")) == []
        assert learned_recipe_ids(db, 1) == []

    def test_item_learned_recipe_not_granted(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=3, experience=100)
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=None)

        assert _recipe_ids(c.get("/inventory/crafting/1/recipes")) == []
        assert learned_recipe_ids(db, 1) == []

    def test_other_professions_recipe_not_granted(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=1)
        make_recipe(db, 10, "blacksmith", RESULT, auto_learn_rank=1)

        c.get("/inventory/crafting/1/recipes")
        assert learned_recipe_ids(db, 1) == []

    def test_idempotent_on_repeated_get(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=1)
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=1)

        for _ in range(3):
            assert _recipe_ids(c.get("/inventory/crafting/1/recipes")) == [10]
        assert learned_recipe_ids(db, 1) == [10]

    def test_no_profession_learns_nothing(self, env):
        db, c = env["db"], env["client"]
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=1)
        assert _recipe_ids(c.get("/inventory/crafting/1/recipes")) == []
        assert learned_recipe_ids(db, 1) == []

    def test_concurrent_insert_race_does_not_500(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=1)

        with patch("crud.sync_auto_learned_recipes",
                   side_effect=IntegrityError("INSERT", {}, Exception("dup"))):
            resp = c.get("/inventory/crafting/1/recipes")

        assert resp.status_code == 200

    def test_foreign_character_403_learns_nothing(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 2, "jeweler", rank=1)
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=1)

        assert c.get("/inventory/crafting/2/recipes").status_code == 403
        assert learned_recipe_ids(db, 2) == []

    def test_unauthenticated_401(self, client):
        assert client.get("/inventory/crafting/1/recipes").status_code == 401


class TestLazySyncOnMyProfession:

    def test_get_my_profession_syncs(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "scholar", rank=2, experience=30)
        make_recipe(db, 10, "scholar", RESULT, auto_learn_rank=2)

        resp = c.get("/inventory/professions/1/my")

        assert resp.status_code == 200, resp.text
        assert resp.json()["profession"]["name"] == "Мистик"
        assert resp.json()["rank_name"] == "Подмастерье"
        assert learned_recipe_ids(db, 1) == [10]


class TestRankUpAndAdmin:

    def test_award_helper_learns_after_rank_up(self, env):
        db = env["db"]
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=2, name="Базовое кольцо")
        make_recipe(db, 11, "jeweler", RESULT, auto_learn_rank=3)
        assign_profession(db, 1, "jeweler", rank=1)
        cp = crud.get_character_profession(db, 1)

        result = crud.award_profession_xp(db, cp, 20)
        db.commit()

        assert result["rank_up"] is True
        assert result["new_rank_name"] == "Подмастерье"
        assert result["auto_learned_recipes"] == [{"id": 10, "name": "Базовое кольцо"}]
        assert profession_state(db, 1) == (2, 20)
        assert learned_recipe_ids(db, 1) == [10]

    def test_award_helper_multi_rank_jump(self, env):
        db = env["db"]
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=2)
        make_recipe(db, 11, "jeweler", RESULT, auto_learn_rank=3)
        assign_profession(db, 1, "jeweler", rank=1)
        cp = crud.get_character_profession(db, 1)

        result = crud.award_profession_xp(db, cp, 500)
        db.commit()

        assert result["new_rank_name"] == "Мастер"
        assert profession_state(db, 1) == (3, 500)
        assert learned_recipe_ids(db, 1) == [10, 11]

    def test_award_helper_no_rank_up(self, env):
        db = env["db"]
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=2)
        assign_profession(db, 1, "jeweler", rank=1)
        cp = crud.get_character_profession(db, 1)

        result = crud.award_profession_xp(db, cp, 19)
        db.commit()

        assert result == {
            "xp_earned": 19, "new_total_xp": 19, "rank_up": False,
            "new_rank_name": None, "auto_learned_recipes": [],
        }
        assert learned_recipe_ids(db, 1) == []

    def test_admin_set_rank_learns_up_to_rank(self, client, env):
        db = env["db"]
        make_recipe(db, 10, "jeweler", RESULT, auto_learn_rank=1)
        make_recipe(db, 11, "jeweler", RESULT, auto_learn_rank=2)
        make_recipe(db, 12, "jeweler", RESULT, auto_learn_rank=3)
        assign_profession(db, 1, "jeweler", rank=1)
        app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
            id=5, username="admin", role="admin", permissions=["professions:manage"])

        resp = client.post("/inventory/admin/professions/1/set-rank", json={"rank_number": 2})

        assert resp.status_code == 200, resp.text
        assert profession_state(db, 1)[0] == 2
        assert learned_recipe_ids(db, 1) == [10, 11]

    def test_admin_set_rank_requires_permission(self, env):
        assign_profession(env["db"], 1, "jeweler", rank=1)
        resp = env["client"].post("/inventory/admin/professions/1/set-rank", json={"rank_number": 3})
        assert resp.status_code == 403
        assert profession_state(env["db"], 1)[0] == 1

    def test_choose_profession_learns_rank1_recipes(self, env):
        db, c = env["db"], env["client"]
        make_recipe(db, 10, "cook", RESULT, auto_learn_rank=1)
        make_recipe(db, 11, "cook", RESULT, auto_learn_rank=2)

        resp = c.post("/inventory/professions/1/choose", json={"profession_id": 3})

        assert resp.status_code == 200, resp.text
        assert learned_recipe_ids(db, 1) == [10]


class TestFreeLearningClosed:

    def test_learn_recipe_endpoint_removed(self, env):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, "jeweler", rank=1)
        make_recipe(db, 10, "jeweler", RESULT)

        resp = c.post("/inventory/crafting/1/learn-recipe", json={"recipe_id": 10})

        assert resp.status_code in (404, 405)
        assert learned_recipe_ids(db, 1) == []
