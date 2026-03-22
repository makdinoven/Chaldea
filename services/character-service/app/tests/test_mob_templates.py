"""
Tests for mob template admin CRUD endpoints in character-service.

Covers:
- Template CRUD (list, create, get detail, update, delete)
- Skills update (replace skills list)
- Loot update (replace loot entries with validation)
- Spawn config update (replace spawn rules with validation)
- Auth enforcement (mobs:manage permission required)
- Negative scenarios and edge cases
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from auth_http import (
    get_admin_user,
    get_current_user_via_http,
    require_permission,
    OAUTH2_SCHEME,
    UserRead,
)
from main import app, get_db
import models
import database


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_TEMPLATE_DATA = {
    "name": "Гоблин-воин",
    "description": "Зелёный гоблин",
    "tier": "normal",
    "level": 5,
    "id_race": 1,
    "id_subrace": 1,
    "id_class": 1,
    "sex": "male",
    "xp_reward": 100,
    "gold_reward": 50,
    "respawn_enabled": True,
    "respawn_seconds": 300,
}

_MOB_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=["mobs:manage"],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(test_engine):
    """Real SQLite session for integration tests."""
    models.Base.metadata.create_all(bind=test_engine)
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def mob_client(db_session):
    """TestClient with real DB and mocked admin auth (mobs:manage permission)."""

    def override_get_db():
        yield db_session

    def override_admin():
        return _MOB_ADMIN_USER

    def override_token():
        return "fake-admin-token"

    # Override require_permission to always return _MOB_ADMIN_USER
    def _require_perm_override(permission: str):
        def checker():
            return _MOB_ADMIN_USER
        return checker

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def _create_template(db_session):
    """Helper to insert a MobTemplate directly into the DB."""

    def _create(**overrides):
        data = {
            "name": "Тестовый моб",
            "tier": "normal",
            "level": 1,
            "id_race": 1,
            "id_subrace": 1,
            "id_class": 1,
            "sex": "genderless",
            "xp_reward": 0,
            "gold_reward": 0,
            "respawn_enabled": False,
        }
        data.update(overrides)
        template = models.MobTemplate(**data)
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)
        return template

    return _create


# ============================================================
# 1. Template CRUD — List
# ============================================================


class TestListMobTemplates:
    """GET /characters/admin/mob-templates"""

    def test_list_empty(self, mob_client):
        resp = mob_client.get("/characters/admin/mob-templates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["page"] == 1

    def test_list_returns_templates(self, mob_client, _create_template):
        _create_template(name="Волк")
        _create_template(name="Дракон", tier="boss", level=50)
        resp = mob_client.get("/characters/admin/mob-templates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_list_pagination(self, mob_client, _create_template):
        for i in range(5):
            _create_template(name=f"Моб-{i}")
        resp = mob_client.get("/characters/admin/mob-templates?page=1&page_size=2")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_list_search_by_name(self, mob_client, _create_template):
        _create_template(name="Огненный дракон")
        _create_template(name="Ледяной волк")
        resp = mob_client.get("/characters/admin/mob-templates?q=дракон")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Огненный дракон"

    def test_list_filter_by_tier(self, mob_client, _create_template):
        _create_template(name="Обычный враг", tier="normal")
        _create_template(name="Элитный враг", tier="elite")
        _create_template(name="Босс", tier="boss")
        resp = mob_client.get("/characters/admin/mob-templates?tier=elite")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Элитный враг"

    def test_list_search_and_filter_combined(self, mob_client, _create_template):
        _create_template(name="Тёмный рыцарь", tier="elite")
        _create_template(name="Тёмный гоблин", tier="normal")
        resp = mob_client.get("/characters/admin/mob-templates?q=Тёмный&tier=elite")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Тёмный рыцарь"


# ============================================================
# 2. Template CRUD — Create
# ============================================================


class TestCreateMobTemplate:
    """POST /characters/admin/mob-templates"""

    def test_create_success(self, mob_client):
        resp = mob_client.post("/characters/admin/mob-templates", json=_VALID_TEMPLATE_DATA)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == _VALID_TEMPLATE_DATA["name"]
        assert body["tier"] == "normal"
        assert body["level"] == 5
        assert body["xp_reward"] == 100
        assert body["gold_reward"] == 50
        assert "id" in body

    def test_create_minimal_data(self, mob_client):
        data = {
            "name": "Минимальный моб",
            "id_race": 1,
            "id_subrace": 1,
            "id_class": 1,
        }
        resp = mob_client.post("/characters/admin/mob-templates", json=data)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Минимальный моб"
        assert body["tier"] == "normal"
        assert body["level"] == 1
        assert body["xp_reward"] == 0
        assert body["gold_reward"] == 0

    def test_create_invalid_tier(self, mob_client):
        data = {**_VALID_TEMPLATE_DATA, "tier": "legendary"}
        resp = mob_client.post("/characters/admin/mob-templates", json=data)
        assert resp.status_code == 422

    def test_create_negative_level(self, mob_client):
        data = {**_VALID_TEMPLATE_DATA, "level": -1}
        resp = mob_client.post("/characters/admin/mob-templates", json=data)
        assert resp.status_code == 422

    def test_create_negative_xp_reward(self, mob_client):
        data = {**_VALID_TEMPLATE_DATA, "xp_reward": -10}
        resp = mob_client.post("/characters/admin/mob-templates", json=data)
        assert resp.status_code == 422

    def test_create_negative_gold_reward(self, mob_client):
        data = {**_VALID_TEMPLATE_DATA, "gold_reward": -5}
        resp = mob_client.post("/characters/admin/mob-templates", json=data)
        assert resp.status_code == 422

    def test_create_missing_required_fields(self, mob_client):
        resp = mob_client.post("/characters/admin/mob-templates", json={})
        assert resp.status_code == 422

    def test_create_sql_injection_in_name(self, mob_client):
        data = {**_VALID_TEMPLATE_DATA, "name": "'; DROP TABLE mob_templates; --"}
        resp = mob_client.post("/characters/admin/mob-templates", json=data)
        assert resp.status_code in (201, 400)  # Must not crash with 500


# ============================================================
# 3. Template CRUD — Get Detail
# ============================================================


class TestGetMobTemplateDetail:
    """GET /characters/admin/mob-templates/{id}"""

    def test_get_detail_success(self, mob_client, _create_template):
        template = _create_template(name="Детальный моб", tier="elite", level=10)
        resp = mob_client.get(f"/characters/admin/mob-templates/{template.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == template.id
        assert body["name"] == "Детальный моб"
        assert body["tier"] == "elite"
        assert body["level"] == 10
        assert "skills" in body
        assert "spawn_locations" in body

    def test_get_detail_not_found(self, mob_client):
        resp = mob_client.get("/characters/admin/mob-templates/99999")
        assert resp.status_code == 404

    def test_get_detail_with_skills(self, mob_client, _create_template, db_session):
        template = _create_template(name="Моб с навыками")
        db_session.add(models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=10))
        db_session.add(models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=20))
        db_session.commit()
        resp = mob_client.get(f"/characters/admin/mob-templates/{template.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["skills"]) == 2
        skill_ids = [s["skill_rank_id"] for s in body["skills"]]
        assert 10 in skill_ids
        assert 20 in skill_ids

    def test_get_detail_with_loot(self, mob_client, _create_template, db_session):
        template = _create_template(name="Моб с лутом")
        db_session.add(models.MobLootTable(
            mob_template_id=template.id,
            item_id=5,
            drop_chance=50.0,
            min_quantity=1,
            max_quantity=3,
        ))
        db_session.commit()
        resp = mob_client.get(f"/characters/admin/mob-templates/{template.id}")
        assert resp.status_code == 200
        body = resp.json()
        # Schema field was renamed from "loot_table" to "loot_entries" to match ORM relationship.
        assert "loot_entries" in body
        assert len(body["loot_entries"]) == 1

    def test_get_detail_with_spawns(self, mob_client, _create_template, db_session):
        template = _create_template(name="Моб со спавнами")
        db_session.add(models.LocationMobSpawn(
            mob_template_id=template.id,
            location_id=100,
            spawn_chance=10.0,
            max_active=2,
            is_enabled=True,
        ))
        db_session.commit()
        resp = mob_client.get(f"/characters/admin/mob-templates/{template.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["spawn_locations"]) == 1
        assert body["spawn_locations"][0]["location_id"] == 100


# ============================================================
# 4. Template CRUD — Update
# ============================================================


class TestUpdateMobTemplate:
    """PUT /characters/admin/mob-templates/{id}"""

    def test_update_success(self, mob_client, _create_template):
        template = _create_template(name="Старое имя", level=1)
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}",
            json={"name": "Новое имя", "level": 10},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Новое имя"
        assert body["level"] == 10

    def test_update_not_found(self, mob_client):
        resp = mob_client.put(
            "/characters/admin/mob-templates/99999",
            json={"name": "Не существует"},
        )
        assert resp.status_code == 404

    def test_update_no_data(self, mob_client, _create_template):
        template = _create_template(name="Без изменений")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}",
            json={},
        )
        assert resp.status_code == 400

    def test_update_partial_fields(self, mob_client, _create_template):
        template = _create_template(name="Частичное обновление", level=1, xp_reward=10)
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}",
            json={"xp_reward": 200},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["xp_reward"] == 200
        assert body["name"] == "Частичное обновление"  # unchanged

    def test_update_invalid_tier(self, mob_client, _create_template):
        template = _create_template(name="Невалидный тир")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}",
            json={"tier": "mythic"},
        )
        assert resp.status_code == 422

    def test_update_negative_rewards(self, mob_client, _create_template):
        template = _create_template(name="Негативная награда")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}",
            json={"gold_reward": -100},
        )
        assert resp.status_code == 422


# ============================================================
# 5. Template CRUD — Delete
# ============================================================


class TestDeleteMobTemplate:
    """DELETE /characters/admin/mob-templates/{id}"""

    def test_delete_success(self, mob_client, _create_template):
        template = _create_template(name="Удаляемый моб")
        resp = mob_client.delete(f"/characters/admin/mob-templates/{template.id}")
        assert resp.status_code == 200
        # Verify it's gone
        resp2 = mob_client.get(f"/characters/admin/mob-templates/{template.id}")
        assert resp2.status_code == 404

    def test_delete_not_found(self, mob_client):
        resp = mob_client.delete("/characters/admin/mob-templates/99999")
        assert resp.status_code == 404

    def test_delete_cascades_skills(self, mob_client, _create_template, db_session):
        template = _create_template(name="Каскадное удаление")
        db_session.add(models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=1))
        db_session.commit()
        resp = mob_client.delete(f"/characters/admin/mob-templates/{template.id}")
        assert resp.status_code == 200
        # Verify skills are also deleted
        remaining = db_session.query(models.MobTemplateSkill).filter_by(
            mob_template_id=template.id
        ).count()
        assert remaining == 0


# ============================================================
# 6. Skills Update
# ============================================================


class TestUpdateMobSkills:
    """PUT /characters/admin/mob-templates/{id}/skills"""

    def test_replace_skills_success(self, mob_client, _create_template):
        template = _create_template(name="Навыковый моб")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/skills",
            json={"skill_rank_ids": [1, 2, 3]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["skill_rank_ids"] == [1, 2, 3]

    def test_replace_skills_replaces_old(self, mob_client, _create_template, db_session):
        template = _create_template(name="Замена навыков")
        db_session.add(models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=100))
        db_session.commit()

        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/skills",
            json={"skill_rank_ids": [200, 300]},
        )
        assert resp.status_code == 200

        skills = db_session.query(models.MobTemplateSkill).filter_by(
            mob_template_id=template.id
        ).all()
        rank_ids = [s.skill_rank_id for s in skills]
        assert 100 not in rank_ids
        assert 200 in rank_ids
        assert 300 in rank_ids

    def test_replace_skills_empty_list(self, mob_client, _create_template, db_session):
        template = _create_template(name="Очистка навыков")
        db_session.add(models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=1))
        db_session.commit()

        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/skills",
            json={"skill_rank_ids": []},
        )
        assert resp.status_code == 200

        count = db_session.query(models.MobTemplateSkill).filter_by(
            mob_template_id=template.id
        ).count()
        assert count == 0

    def test_replace_skills_template_not_found(self, mob_client):
        resp = mob_client.put(
            "/characters/admin/mob-templates/99999/skills",
            json={"skill_rank_ids": [1]},
        )
        assert resp.status_code == 404


# ============================================================
# 7. Loot Update
# ============================================================


class TestUpdateMobLoot:
    """PUT /characters/admin/mob-templates/{id}/loot"""

    def test_replace_loot_success(self, mob_client, _create_template):
        template = _create_template(name="Лутовый моб")
        loot_data = {
            "entries": [
                {"item_id": 1, "drop_chance": 50.0, "min_quantity": 1, "max_quantity": 3},
                {"item_id": 2, "drop_chance": 10.0, "min_quantity": 1, "max_quantity": 1},
            ]
        }
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json=loot_data,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entries"]) == 2

    def test_replace_loot_replaces_old(self, mob_client, _create_template, db_session):
        template = _create_template(name="Замена лута")
        db_session.add(models.MobLootTable(
            mob_template_id=template.id, item_id=99, drop_chance=100.0,
        ))
        db_session.commit()

        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json={"entries": [{"item_id": 5, "drop_chance": 25.0, "min_quantity": 1, "max_quantity": 2}]},
        )
        assert resp.status_code == 200

        entries = db_session.query(models.MobLootTable).filter_by(
            mob_template_id=template.id
        ).all()
        assert len(entries) == 1
        assert entries[0].item_id == 5

    def test_loot_drop_chance_too_high(self, mob_client, _create_template):
        template = _create_template(name="Невалидный шанс")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json={"entries": [{"item_id": 1, "drop_chance": 150.0, "min_quantity": 1, "max_quantity": 1}]},
        )
        assert resp.status_code == 422

    def test_loot_drop_chance_negative(self, mob_client, _create_template):
        template = _create_template(name="Отрицательный шанс")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json={"entries": [{"item_id": 1, "drop_chance": -5.0, "min_quantity": 1, "max_quantity": 1}]},
        )
        assert resp.status_code == 422

    def test_loot_quantity_zero(self, mob_client, _create_template):
        template = _create_template(name="Нулевое количество")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json={"entries": [{"item_id": 1, "drop_chance": 10.0, "min_quantity": 0, "max_quantity": 1}]},
        )
        assert resp.status_code == 422

    def test_loot_max_quantity_zero(self, mob_client, _create_template):
        template = _create_template(name="Нулевой макс")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json={"entries": [{"item_id": 1, "drop_chance": 10.0, "min_quantity": 1, "max_quantity": 0}]},
        )
        assert resp.status_code == 422

    def test_loot_boundary_drop_chance_zero(self, mob_client, _create_template):
        template = _create_template(name="Граничный ноль")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json={"entries": [{"item_id": 1, "drop_chance": 0.0, "min_quantity": 1, "max_quantity": 1}]},
        )
        assert resp.status_code == 200

    def test_loot_boundary_drop_chance_100(self, mob_client, _create_template):
        template = _create_template(name="Граничные 100")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json={"entries": [{"item_id": 1, "drop_chance": 100.0, "min_quantity": 1, "max_quantity": 1}]},
        )
        assert resp.status_code == 200

    def test_loot_empty_entries(self, mob_client, _create_template):
        template = _create_template(name="Пустой лут")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/loot",
            json={"entries": []},
        )
        assert resp.status_code == 200

    def test_loot_template_not_found(self, mob_client):
        resp = mob_client.put(
            "/characters/admin/mob-templates/99999/loot",
            json={"entries": [{"item_id": 1, "drop_chance": 10.0, "min_quantity": 1, "max_quantity": 1}]},
        )
        assert resp.status_code == 404


# ============================================================
# 8. Spawn Config Update
# ============================================================


class TestUpdateMobSpawns:
    """PUT /characters/admin/mob-templates/{id}/spawns"""

    def test_replace_spawns_success(self, mob_client, _create_template):
        template = _create_template(name="Спавновый моб")
        spawn_data = {
            "spawns": [
                {"location_id": 1, "spawn_chance": 10.0, "max_active": 2, "is_enabled": True},
                {"location_id": 2, "spawn_chance": 5.0, "max_active": 1, "is_enabled": False},
            ]
        }
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/spawns",
            json=spawn_data,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["spawns"]) == 2

    def test_replace_spawns_replaces_old(self, mob_client, _create_template, db_session):
        template = _create_template(name="Замена спавнов")
        db_session.add(models.LocationMobSpawn(
            mob_template_id=template.id, location_id=999, spawn_chance=50.0,
        ))
        db_session.commit()

        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/spawns",
            json={"spawns": [{"location_id": 1, "spawn_chance": 5.0, "max_active": 1, "is_enabled": True}]},
        )
        assert resp.status_code == 200

        spawns = db_session.query(models.LocationMobSpawn).filter_by(
            mob_template_id=template.id
        ).all()
        assert len(spawns) == 1
        assert spawns[0].location_id == 1

    def test_spawn_chance_too_high(self, mob_client, _create_template):
        template = _create_template(name="Невалидный спавн-шанс")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/spawns",
            json={"spawns": [{"location_id": 1, "spawn_chance": 200.0, "max_active": 1, "is_enabled": True}]},
        )
        assert resp.status_code == 422

    def test_spawn_chance_negative(self, mob_client, _create_template):
        template = _create_template(name="Отрицательный спавн")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/spawns",
            json={"spawns": [{"location_id": 1, "spawn_chance": -1.0, "max_active": 1, "is_enabled": True}]},
        )
        assert resp.status_code == 422

    def test_spawn_max_active_zero(self, mob_client, _create_template):
        template = _create_template(name="Нулевой max_active")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/spawns",
            json={"spawns": [{"location_id": 1, "spawn_chance": 5.0, "max_active": 0, "is_enabled": True}]},
        )
        assert resp.status_code == 422

    def test_spawn_empty_list(self, mob_client, _create_template):
        template = _create_template(name="Пустые спавны")
        resp = mob_client.put(
            f"/characters/admin/mob-templates/{template.id}/spawns",
            json={"spawns": []},
        )
        assert resp.status_code == 200

    def test_spawn_template_not_found(self, mob_client):
        resp = mob_client.put(
            "/characters/admin/mob-templates/99999/spawns",
            json={"spawns": [{"location_id": 1, "spawn_chance": 5.0, "max_active": 1, "is_enabled": True}]},
        )
        assert resp.status_code == 404


# ============================================================
# 9. Auth Enforcement — mobs:manage permission required
# ============================================================


class TestMobTemplateAuth:
    """Verify that admin endpoints require mobs:manage permission."""

    def test_list_no_token_returns_401(self, client):
        resp = client.get("/characters/admin/mob-templates")
        assert resp.status_code == 401

    def test_create_no_token_returns_401(self, client):
        resp = client.post("/characters/admin/mob-templates", json=_VALID_TEMPLATE_DATA)
        assert resp.status_code == 401

    def test_get_detail_no_token_returns_401(self, client):
        resp = client.get("/characters/admin/mob-templates/1")
        assert resp.status_code == 401

    def test_update_no_token_returns_401(self, client):
        resp = client.put("/characters/admin/mob-templates/1", json={"name": "Test"})
        assert resp.status_code == 401

    def test_delete_no_token_returns_401(self, client):
        resp = client.delete("/characters/admin/mob-templates/1")
        assert resp.status_code == 401

    def test_skills_no_token_returns_401(self, client):
        resp = client.put(
            "/characters/admin/mob-templates/1/skills",
            json={"skill_rank_ids": [1]},
        )
        assert resp.status_code == 401

    def test_loot_no_token_returns_401(self, client):
        resp = client.put(
            "/characters/admin/mob-templates/1/loot",
            json={"entries": []},
        )
        assert resp.status_code == 401

    def test_spawns_no_token_returns_401(self, client):
        resp = client.put(
            "/characters/admin/mob-templates/1/spawns",
            json={"spawns": []},
        )
        assert resp.status_code == 401

    @patch("auth_http.requests.get")
    def test_user_without_mobs_manage_returns_403(self, mock_get, client):
        """User with valid token but no mobs:manage permission gets 403."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "id": 2,
                "username": "editor",
                "role": "editor",
                "permissions": ["characters:read"],
            },
        )
        resp = client.get(
            "/characters/admin/mob-templates",
            headers={"Authorization": "Bearer editor-token"},
        )
        assert resp.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get, client):
        mock_get.return_value = MagicMock(status_code=401)
        resp = client.get(
            "/characters/admin/mob-templates",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401


# ============================================================
# 10. SQL Injection — safety checks
# ============================================================


class TestMobTemplateSQLInjection:
    """Verify ORM-based queries handle malicious input safely."""

    def test_search_with_sql_injection(self, mob_client):
        resp = mob_client.get(
            "/characters/admin/mob-templates",
            params={"q": "'; DROP TABLE mob_templates; --"},
        )
        assert resp.status_code in (200, 400)

    def test_tier_filter_injection(self, mob_client):
        resp = mob_client.get(
            "/characters/admin/mob-templates",
            params={"tier": "normal' OR '1'='1"},
        )
        assert resp.status_code in (200, 400)
