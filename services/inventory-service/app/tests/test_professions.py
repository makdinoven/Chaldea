"""
Task 8 — QA tests for FEAT-081: Profession system endpoints.

Tests covering profession listing, choosing, changing, character profession retrieval,
and all admin CRUD operations for professions, ranks, and set-rank.
"""

import pytest
from unittest.mock import patch
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead, require_permission
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_characters_table(db):
    """Create minimal characters table for ownership checks."""
    db.execute(text("DROP TABLE IF EXISTS battle_participants"))
    db.execute(text("DROP TABLE IF EXISTS battles"))
    db.execute(text("DROP TABLE IF EXISTS characters"))
    db.execute(text(
        """CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'TestChar',
            user_id INTEGER NOT NULL,
            current_location_id INTEGER DEFAULT 1,
            currency_balance INTEGER DEFAULT 0
        )"""
    ))
    db.execute(text(
        """CREATE TABLE battles (
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending'
        )"""
    ))
    db.execute(text(
        """CREATE TABLE battle_participants (
            id INTEGER PRIMARY KEY,
            battle_id INTEGER NOT NULL,
            character_id INTEGER NOT NULL
        )"""
    ))
    db.commit()


def _insert_character(db, char_id, user_id, name="TestChar"):
    db.execute(text(
        "INSERT OR IGNORE INTO characters (id, name, user_id) VALUES (:cid, :name, :uid)"
    ), {"cid": char_id, "name": name, "uid": user_id})
    db.commit()


def _create_profession(db, prof_id=1, name="Кузнец", slug="blacksmith", sort_order=1):
    prof = models.Profession(
        id=prof_id, name=name, slug=slug, description="Test profession",
        sort_order=sort_order, is_active=True,
    )
    db.add(prof)
    db.flush()
    return prof


def _create_rank(db, rank_id=None, profession_id=1, rank_number=1, name="Ученик", required_exp=0):
    rank = models.ProfessionRank(
        profession_id=profession_id,
        rank_number=rank_number,
        name=name,
        description="Rank desc",
        required_experience=required_exp,
    )
    if rank_id:
        rank.id = rank_id
    db.add(rank)
    db.flush()
    return rank


def _create_item(db, item_id, name, item_type="resource", max_stack=99):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type,
        item_rarity="common", max_stack_size=max_stack, is_unique=False,
    )
    db.add(item)
    db.flush()
    return item


def _create_recipe(db, recipe_id=None, name="Iron Sword", profession_id=1,
                   required_rank=1, result_item_id=50, auto_learn_rank=1):
    recipe = models.Recipe(
        name=name, profession_id=profession_id, required_rank=required_rank,
        result_item_id=result_item_id, result_quantity=1, rarity="common",
        auto_learn_rank=auto_learn_rank, is_active=True,
    )
    if recipe_id:
        recipe.id = recipe_id
    db.add(recipe)
    db.flush()
    return recipe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_user1 = UserRead(id=1, username="player1", role="user", permissions=[])
_admin_user = UserRead(
    id=99, username="admin", role="admin",
    permissions=[
        "professions:read", "professions:create",
        "professions:update", "professions:delete", "professions:manage",
    ],
)


@pytest.fixture()
def prof_env(client, db_session):
    """Base environment with characters table and auth override."""
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Hero")

    from main import app
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    yield {"client": client, "db": db_session, "app": app}

    app.dependency_overrides.pop(get_current_user_via_http, None)


@pytest.fixture()
def admin_env(client, db_session):
    """Environment with admin auth for profession admin endpoints."""
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Hero")

    from main import app
    app.dependency_overrides[get_current_user_via_http] = lambda: _admin_user
    # Override all require_permission dependencies for admin
    for perm in ["professions:read", "professions:create", "professions:update",
                 "professions:delete", "professions:manage"]:
        app.dependency_overrides[require_permission(perm)] = lambda: _admin_user

    yield {"client": client, "db": db_session, "app": app}

    app.dependency_overrides.clear()


# ===========================================================================
# 1. Profession listing — GET /inventory/professions
# ===========================================================================

class TestListProfessions:

    def test_returns_seeded_professions(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        p1 = _create_profession(db, 1, "Кузнец", "blacksmith", 1)
        _create_rank(db, profession_id=p1.id, rank_number=1, name="Ученик")
        _create_rank(db, profession_id=p1.id, rank_number=2, name="Подмастерье")
        p2 = _create_profession(db, 2, "Алхимик", "alchemist", 2)
        _create_rank(db, profession_id=p2.id, rank_number=1, name="Новичок")
        db.commit()

        resp = c.get("/inventory/professions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {p["name"] for p in data}
        assert "Кузнец" in names
        assert "Алхимик" in names
        # Check ranks are included
        blacksmith = next(p for p in data if p["slug"] == "blacksmith")
        assert len(blacksmith["ranks"]) == 2

    def test_inactive_professions_hidden(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith", 1)
        inactive = _create_profession(db, 2, "Тест", "test", 2)
        inactive.is_active = False
        db.commit()

        resp = c.get("/inventory/professions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Кузнец"


# ===========================================================================
# 2. Choose profession — POST /inventory/professions/{char_id}/choose
# ===========================================================================

class TestChooseProfession:

    def test_choose_happy_path(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        result_item = _create_item(db, 50, "Железный меч", "main_weapon")
        recipe = _create_recipe(db, name="Ковка меча", profession_id=prof.id,
                                result_item_id=result_item.id, auto_learn_rank=1)
        db.commit()

        resp = c.post(f"/inventory/professions/1/choose", json={"profession_id": prof.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_id"] == 1
        assert data["profession_id"] == prof.id
        assert data["current_rank"] == 1
        assert data["experience"] == 0
        assert len(data["auto_learned_recipes"]) == 1
        assert data["auto_learned_recipes"][0]["name"] == "Ковка меча"

    def test_choose_auto_learns_rank1_recipes(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        item1 = _create_item(db, 50, "Item A", "resource")
        item2 = _create_item(db, 51, "Item B", "resource")
        _create_recipe(db, name="Recipe A", profession_id=prof.id,
                       result_item_id=item1.id, auto_learn_rank=1)
        _create_recipe(db, name="Recipe B", profession_id=prof.id,
                       result_item_id=item2.id, auto_learn_rank=1)
        _create_recipe(db, name="Recipe C", profession_id=prof.id,
                       result_item_id=item1.id, auto_learn_rank=2)
        db.commit()

        resp = c.post("/inventory/professions/1/choose", json={"profession_id": prof.id})
        assert resp.status_code == 200
        data = resp.json()
        # Only rank-1 recipes should be auto-learned
        assert len(data["auto_learned_recipes"]) == 2

    def test_choose_profession_invalid_id(self, prof_env):
        c = prof_env["client"]
        resp = c.post("/inventory/professions/1/choose", json={"profession_id": 9999})
        assert resp.status_code == 404

    def test_choose_inactive_profession(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof = _create_profession(db)
        prof.is_active = False
        db.commit()

        resp = c.post("/inventory/professions/1/choose", json={"profession_id": prof.id})
        assert resp.status_code == 400


# ===========================================================================
# 3. Choose profession duplicate — returns 400 if already has profession
# ===========================================================================

class TestChooseProfessionDuplicate:

    def test_duplicate_returns_400(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        db.commit()

        # First choice succeeds
        resp = c.post("/inventory/professions/1/choose", json={"profession_id": prof.id})
        assert resp.status_code == 200

        # Second choice fails
        resp = c.post("/inventory/professions/1/choose", json={"profession_id": prof.id})
        assert resp.status_code == 400
        assert "уже есть профессия" in resp.json()["detail"]


# ===========================================================================
# 4. Get character profession — GET /inventory/professions/{char_id}/my
# ===========================================================================

class TestGetMyProfession:

    def test_get_my_profession_happy(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        db.commit()

        # Choose profession first
        c.post("/inventory/professions/1/choose", json={"profession_id": prof.id})

        resp = c.get("/inventory/professions/1/my")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_id"] == 1
        assert data["profession"]["name"] == "Кузнец"
        assert data["profession"]["slug"] == "blacksmith"
        assert data["current_rank"] == 1
        assert data["rank_name"] == "Ученик"
        assert data["experience"] == 0
        assert "chosen_at" in data


# ===========================================================================
# 5. Get character profession 404 — returns 404 if no profession
# ===========================================================================

class TestGetMyProfession404:

    def test_no_profession_returns_404(self, prof_env):
        c = prof_env["client"]
        resp = c.get("/inventory/professions/1/my")
        assert resp.status_code == 404
        assert "нет профессии" in resp.json()["detail"]


# ===========================================================================
# 6. Change profession — POST /inventory/professions/{char_id}/change
# ===========================================================================

class TestChangeProfession:

    def test_change_resets_rank_and_xp(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof1 = _create_profession(db, 1, "Кузнец", "blacksmith", 1)
        _create_rank(db, profession_id=prof1.id, rank_number=1, name="Ученик")
        prof2 = _create_profession(db, 2, "Алхимик", "alchemist", 2)
        _create_rank(db, profession_id=prof2.id, rank_number=1, name="Новичок")
        db.commit()

        # Choose first profession
        c.post("/inventory/professions/1/choose", json={"profession_id": prof1.id})

        # Change to second profession
        resp = c.post("/inventory/professions/1/change", json={"profession_id": prof2.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_profession"] == "Кузнец"
        assert data["new_profession"] == "Алхимик"
        assert data["current_rank"] == 1
        assert data["experience"] == 0
        assert "рецепты сохранены" in data["message"]

    def test_change_preserves_recipes(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof1 = _create_profession(db, 1, "Кузнец", "blacksmith", 1)
        _create_rank(db, profession_id=prof1.id, rank_number=1, name="Ученик")
        result_item = _create_item(db, 50, "Железный меч", "main_weapon")
        _create_recipe(db, name="Ковка меча", profession_id=prof1.id,
                       result_item_id=result_item.id, auto_learn_rank=1)

        prof2 = _create_profession(db, 2, "Алхимик", "alchemist", 2)
        _create_rank(db, profession_id=prof2.id, rank_number=1, name="Новичок")
        db.commit()

        # Choose first profession (auto-learns recipe)
        resp = c.post("/inventory/professions/1/choose", json={"profession_id": prof1.id})
        assert len(resp.json()["auto_learned_recipes"]) == 1

        # Change profession
        c.post("/inventory/professions/1/change", json={"profession_id": prof2.id})

        # Verify recipes still exist in DB
        learned = db.query(models.CharacterRecipe).filter(
            models.CharacterRecipe.character_id == 1
        ).all()
        assert len(learned) == 1

    def test_change_no_profession_returns_404(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        _create_profession(db, 2, "Алхимик", "alchemist", 2)
        db.commit()

        resp = c.post("/inventory/professions/1/change", json={"profession_id": 2})
        assert resp.status_code == 404

    def test_change_to_invalid_profession_returns_404(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        db.commit()
        c.post("/inventory/professions/1/choose", json={"profession_id": prof.id})

        resp = c.post("/inventory/professions/1/change", json={"profession_id": 9999})
        assert resp.status_code == 404


# ===========================================================================
# 7. Change to same profession — returns 400
# ===========================================================================

class TestChangeSameProfession:

    def test_same_profession_returns_400(self, prof_env):
        db = prof_env["db"]
        c = prof_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        db.commit()

        c.post("/inventory/professions/1/choose", json={"profession_id": prof.id})
        resp = c.post("/inventory/professions/1/change", json={"profession_id": prof.id})
        assert resp.status_code == 400
        assert "уже имеет эту профессию" in resp.json()["detail"]


# ===========================================================================
# 8. Admin CRUD professions
# ===========================================================================

class TestAdminProfessions:

    def test_create_profession(self, admin_env):
        c = admin_env["client"]
        resp = c.post("/inventory/admin/professions", json={
            "name": "Кузнец",
            "slug": "blacksmith",
            "description": "Крафт снаряжения",
            "sort_order": 1,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Кузнец"
        assert data["slug"] == "blacksmith"

    def test_create_duplicate_profession_400(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith")
        db.commit()

        resp = c.post("/inventory/admin/professions", json={
            "name": "Кузнец",
            "slug": "blacksmith2",
            "sort_order": 2,
        })
        assert resp.status_code == 400

    def test_list_professions_admin_includes_inactive(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith")
        inactive = _create_profession(db, 2, "Тест", "test", 2)
        inactive.is_active = False
        db.commit()

        resp = c.get("/inventory/admin/professions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_update_profession(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith")
        db.commit()

        resp = c.put("/inventory/admin/professions/1", json={
            "description": "Updated description",
        })
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_update_nonexistent_profession_404(self, admin_env):
        c = admin_env["client"]
        resp = c.put("/inventory/admin/professions/9999", json={"description": "X"})
        assert resp.status_code == 404

    def test_delete_profession(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith")
        db.commit()

        resp = c.delete("/inventory/admin/professions/1")
        assert resp.status_code == 200
        assert "удалена" in resp.json()["detail"]

        # Verify it's gone
        assert db.query(models.Profession).filter(models.Profession.id == 1).first() is None

    def test_delete_nonexistent_profession_404(self, admin_env):
        c = admin_env["client"]
        resp = c.delete("/inventory/admin/professions/9999")
        assert resp.status_code == 404


# ===========================================================================
# 9. Admin CRUD ranks
# ===========================================================================

class TestAdminRanks:

    def test_create_rank(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith")
        db.commit()

        resp = c.post("/inventory/admin/professions/1/ranks", json={
            "rank_number": 1,
            "name": "Ученик",
            "description": "Начинающий кузнец",
            "required_experience": 0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["rank_number"] == 1
        assert data["name"] == "Ученик"
        assert data["profession_id"] == 1

    def test_create_duplicate_rank_400(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith")
        _create_rank(db, profession_id=1, rank_number=1, name="Ученик")
        db.commit()

        resp = c.post("/inventory/admin/professions/1/ranks", json={
            "rank_number": 1,
            "name": "Another Rank 1",
        })
        assert resp.status_code == 400

    def test_create_rank_nonexistent_profession_404(self, admin_env):
        c = admin_env["client"]
        resp = c.post("/inventory/admin/professions/9999/ranks", json={
            "rank_number": 1,
            "name": "Test",
        })
        assert resp.status_code == 404

    def test_update_rank(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith")
        rank = _create_rank(db, profession_id=1, rank_number=1, name="Ученик")
        db.commit()

        resp = c.put(f"/inventory/admin/professions/ranks/{rank.id}", json={
            "name": "Мастер-ученик",
            "required_experience": 100,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Мастер-ученик"
        assert data["required_experience"] == 100

    def test_update_nonexistent_rank_404(self, admin_env):
        c = admin_env["client"]
        resp = c.put("/inventory/admin/professions/ranks/9999", json={"name": "X"})
        assert resp.status_code == 404

    def test_delete_rank(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _create_profession(db, 1, "Кузнец", "blacksmith")
        rank = _create_rank(db, profession_id=1, rank_number=1, name="Ученик")
        db.commit()

        resp = c.delete(f"/inventory/admin/professions/ranks/{rank.id}")
        assert resp.status_code == 200
        assert "удалён" in resp.json()["detail"]

    def test_delete_nonexistent_rank_404(self, admin_env):
        c = admin_env["client"]
        resp = c.delete("/inventory/admin/professions/ranks/9999")
        assert resp.status_code == 404


# ===========================================================================
# 10. Admin set rank — POST /admin/professions/{char_id}/set-rank
# ===========================================================================

class TestAdminSetRank:

    def test_set_rank_happy(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        _insert_character(db, 1, user_id=1, name="Hero")
        prof = _create_profession(db, 1, "Кузнец", "blacksmith")
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        rank2 = _create_rank(db, profession_id=prof.id, rank_number=2, name="Подмастерье")

        # Assign profession to character
        cp = models.CharacterProfession(
            character_id=1, profession_id=prof.id, current_rank=1, experience=0,
        )
        db.add(cp)
        db.commit()

        resp = c.post("/inventory/admin/professions/1/set-rank", json={"rank_number": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_rank"] == 2
        assert data["rank_name"] == "Подмастерье"

    def test_set_rank_no_profession_404(self, admin_env):
        c = admin_env["client"]
        resp = c.post("/inventory/admin/professions/1/set-rank", json={"rank_number": 2})
        assert resp.status_code == 404

    def test_set_rank_invalid_rank_400(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        prof = _create_profession(db, 1, "Кузнец", "blacksmith")
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        cp = models.CharacterProfession(
            character_id=1, profession_id=prof.id, current_rank=1, experience=0,
        )
        db.add(cp)
        db.commit()

        resp = c.post("/inventory/admin/professions/1/set-rank", json={"rank_number": 99})
        assert resp.status_code == 400
        assert "не существует" in resp.json()["detail"]


# ===========================================================================
# Security tests
# ===========================================================================

class TestProfessionSecurity:

    def test_list_professions_no_auth_401(self, client):
        """No token should return 401."""
        resp = client.get("/inventory/professions")
        assert resp.status_code == 401

    def test_choose_profession_wrong_character_403(self, prof_env):
        """Attempting to choose profession for another user's character."""
        db = prof_env["db"]
        c = prof_env["client"]

        _insert_character(db, 2, user_id=999, name="OtherPlayer")
        prof = _create_profession(db)
        db.commit()

        resp = c.post("/inventory/professions/2/choose", json={"profession_id": prof.id})
        assert resp.status_code == 403

    def test_sql_injection_in_profession_name(self, admin_env):
        """SQL injection attempt in profession name should not crash."""
        c = admin_env["client"]
        resp = c.post("/inventory/admin/professions", json={
            "name": "'; DROP TABLE professions; --",
            "slug": "injection-test",
            "sort_order": 1,
        })
        assert resp.status_code in (201, 400)
