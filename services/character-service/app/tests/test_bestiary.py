"""
Tests for bestiary (kill tracker + bestiary endpoint) in character-service.

Covers:
- record_mob_kill CRUD: successful recording, duplicate (idempotent), invalid mob
- get_bestiary CRUD: visibility rules for normal/elite/boss × killed/not-killed
- POST /internal/record-mob-kill endpoint: 200 + 404 responses
- GET /bestiary endpoint: with and without character_id param
"""

import pytest
from fastapi.testclient import TestClient

import models
import database
import crud
from main import app, get_db


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
def bestiary_client(db_session):
    """TestClient with real SQLite DB. No auth override needed (endpoints are public/internal)."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def _create_mob_template(db_session):
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


@pytest.fixture
def _create_active_mob(db_session):
    """Helper to insert an ActiveMob referencing a MobTemplate."""

    def _create(mob_template_id, character_id, **overrides):
        data = {
            "mob_template_id": mob_template_id,
            "character_id": character_id,
            "location_id": 1,
            "status": "alive",
            "spawn_type": "random",
        }
        data.update(overrides)
        mob = models.ActiveMob(**data)
        db_session.add(mob)
        db_session.commit()
        db_session.refresh(mob)
        return mob

    return _create


@pytest.fixture
def _create_mob_kill(db_session):
    """Helper to insert a MobKill record."""

    def _create(character_id, mob_template_id):
        kill = models.MobKill(
            character_id=character_id,
            mob_template_id=mob_template_id,
        )
        db_session.add(kill)
        db_session.commit()
        db_session.refresh(kill)
        return kill

    return _create


# ============================================================
# 1. CRUD: record_mob_kill
# ============================================================


class TestRecordMobKillCRUD:
    """Direct tests for crud.record_mob_kill()."""

    def test_successful_kill_recording(
        self, db_session, _create_mob_template, _create_active_mob
    ):
        """First kill creates a MobKill record, returns ok=True, already_recorded=False."""
        template = _create_mob_template(name="Волк", tier="normal")
        active = _create_active_mob(mob_template_id=template.id, character_id=500)

        result = crud.record_mob_kill(db_session, character_id=1, mob_character_id=500)

        assert result is not None
        assert result["ok"] is True
        assert result["already_recorded"] is False
        assert result["mob_template_id"] == template.id

        # Verify the DB record exists
        kill = (
            db_session.query(models.MobKill)
            .filter_by(character_id=1, mob_template_id=template.id)
            .first()
        )
        assert kill is not None

    def test_duplicate_kill_recording_is_idempotent(
        self, db_session, _create_mob_template, _create_active_mob
    ):
        """Second kill for same (character, template) returns already_recorded=True."""
        template = _create_mob_template(name="Гоблин", tier="normal")
        active = _create_active_mob(mob_template_id=template.id, character_id=600)

        # First call
        result1 = crud.record_mob_kill(db_session, character_id=2, mob_character_id=600)
        assert result1["ok"] is True
        assert result1["already_recorded"] is False

        # Second call — same character, same mob template
        result2 = crud.record_mob_kill(db_session, character_id=2, mob_character_id=600)
        assert result2["ok"] is True
        assert result2["already_recorded"] is True
        assert result2["mob_template_id"] == template.id

    def test_invalid_mob_character_id_returns_none(self, db_session):
        """No ActiveMob found for the given mob_character_id — returns None."""
        result = crud.record_mob_kill(db_session, character_id=1, mob_character_id=99999)
        assert result is None


# ============================================================
# 2. CRUD: get_bestiary — visibility rules
# ============================================================


class TestGetBestiaryCRUD:
    """Direct tests for crud.get_bestiary() visibility rules."""

    def test_returns_all_templates_with_killed_false_when_no_character_id(
        self, db_session, _create_mob_template
    ):
        """Without character_id, all entries have killed=False."""
        _create_mob_template(name="Моб-1", tier="normal")
        _create_mob_template(name="Моб-2", tier="elite")
        _create_mob_template(name="Моб-3", tier="boss")

        result = crud.get_bestiary(db_session, character_id=None)

        assert result["total"] == 3
        assert result["killed_count"] == 0
        for entry in result["entries"]:
            assert entry["killed"] is False

    def test_normal_mob_not_killed_shows_description_and_stats(
        self, db_session, _create_mob_template
    ):
        """Normal tier, NOT killed: description + base_attributes visible; skills/loot/spawns are None."""
        _create_mob_template(
            name="Обычный моб",
            tier="normal",
            description="Описание обычного моба",
            base_attributes={"strength": 10, "agility": 5},
        )

        result = crud.get_bestiary(db_session, character_id=1)
        entry = result["entries"][0]

        assert entry["killed"] is False
        assert entry["name"] == "Обычный моб"
        assert entry["description"] == "Описание обычного моба"
        assert entry["base_attributes"] == {"strength": 10, "agility": 5}
        assert entry["skills"] is None
        assert entry["loot_entries"] is None
        assert entry["spawn_locations"] is None

    def test_normal_mob_killed_shows_everything(
        self, db_session, _create_mob_template, _create_mob_kill
    ):
        """Normal tier, KILLED: all fields visible (description, stats, skills, loot, spawns)."""
        template = _create_mob_template(
            name="Убитый обычный моб",
            tier="normal",
            description="Описание",
            base_attributes={"strength": 15},
        )
        # Add skill, loot, spawn data
        db_session.add(models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=42))
        db_session.add(
            models.MobLootTable(
                mob_template_id=template.id,
                item_id=7,
                drop_chance=50.0,
                min_quantity=1,
                max_quantity=2,
            )
        )
        db_session.add(
            models.LocationMobSpawn(
                mob_template_id=template.id,
                location_id=10,
                spawn_chance=25.0,
                max_active=3,
                is_enabled=True,
            )
        )
        db_session.commit()

        # Record kill for character_id=1
        _create_mob_kill(character_id=1, mob_template_id=template.id)

        result = crud.get_bestiary(db_session, character_id=1)
        entry = result["entries"][0]

        assert entry["killed"] is True
        assert entry["description"] == "Описание"
        assert entry["base_attributes"] == {"strength": 15}
        assert len(entry["skills"]) == 1
        assert entry["skills"][0]["skill_rank_id"] == 42
        assert len(entry["loot_entries"]) == 1
        assert entry["loot_entries"][0]["item_id"] == 7
        assert len(entry["spawn_locations"]) == 1
        assert entry["spawn_locations"][0]["location_id"] == 10

    def test_elite_mob_not_killed_hides_everything(
        self, db_session, _create_mob_template
    ):
        """Elite tier, NOT killed: only id/name/tier/level/avatar visible; rest is None."""
        _create_mob_template(
            name="Элитный моб",
            tier="elite",
            description="Секретное описание",
            base_attributes={"strength": 50},
        )

        result = crud.get_bestiary(db_session, character_id=1)
        entry = result["entries"][0]

        assert entry["killed"] is False
        assert entry["name"] == "Элитный моб"
        assert entry["tier"] == "elite"
        assert entry["description"] is None
        assert entry["base_attributes"] is None
        assert entry["skills"] is None
        assert entry["loot_entries"] is None
        assert entry["spawn_locations"] is None

    def test_boss_mob_not_killed_hides_everything(
        self, db_session, _create_mob_template
    ):
        """Boss tier, NOT killed: same visibility as elite — everything hidden."""
        _create_mob_template(
            name="Босс",
            tier="boss",
            description="Описание босса",
            base_attributes={"strength": 100},
        )

        result = crud.get_bestiary(db_session, character_id=1)
        entry = result["entries"][0]

        assert entry["killed"] is False
        assert entry["name"] == "Босс"
        assert entry["tier"] == "boss"
        assert entry["description"] is None
        assert entry["base_attributes"] is None
        assert entry["skills"] is None
        assert entry["loot_entries"] is None
        assert entry["spawn_locations"] is None

    def test_elite_mob_killed_shows_everything(
        self, db_session, _create_mob_template, _create_mob_kill
    ):
        """Elite tier, KILLED: all fields visible."""
        template = _create_mob_template(
            name="Убитый элитный моб",
            tier="elite",
            description="Раскрытое описание элиты",
            base_attributes={"strength": 50, "agility": 30},
        )
        db_session.add(models.MobTemplateSkill(mob_template_id=template.id, skill_rank_id=99))
        db_session.commit()

        _create_mob_kill(character_id=1, mob_template_id=template.id)

        result = crud.get_bestiary(db_session, character_id=1)
        entry = result["entries"][0]

        assert entry["killed"] is True
        assert entry["description"] == "Раскрытое описание элиты"
        assert entry["base_attributes"] == {"strength": 50, "agility": 30}
        assert len(entry["skills"]) == 1
        assert entry["skills"][0]["skill_rank_id"] == 99

    def test_killed_count_reflects_kills(
        self, db_session, _create_mob_template, _create_mob_kill
    ):
        """killed_count in response reflects how many templates the character has killed."""
        t1 = _create_mob_template(name="Моб-A", tier="normal")
        t2 = _create_mob_template(name="Моб-B", tier="elite")
        _create_mob_template(name="Моб-C", tier="boss")

        _create_mob_kill(character_id=5, mob_template_id=t1.id)
        _create_mob_kill(character_id=5, mob_template_id=t2.id)

        result = crud.get_bestiary(db_session, character_id=5)

        assert result["total"] == 3
        assert result["killed_count"] == 2


# ============================================================
# 3. Endpoint: POST /internal/record-mob-kill
# ============================================================


class TestRecordMobKillEndpoint:
    """Integration tests for POST /characters/internal/record-mob-kill."""

    def test_record_kill_returns_200(
        self, bestiary_client, db_session, _create_mob_template, _create_active_mob
    ):
        template = _create_mob_template(name="Тролль", tier="normal")
        _create_active_mob(mob_template_id=template.id, character_id=700)

        resp = bestiary_client.post(
            "/characters/internal/record-mob-kill",
            json={"character_id": 10, "mob_character_id": 700},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["mob_template_id"] == template.id
        assert body["already_recorded"] is False

    def test_record_kill_returns_404_for_invalid_mob(self, bestiary_client):
        resp = bestiary_client.post(
            "/characters/internal/record-mob-kill",
            json={"character_id": 10, "mob_character_id": 99999},
        )

        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    def test_record_kill_duplicate_returns_already_recorded(
        self, bestiary_client, db_session, _create_mob_template, _create_active_mob
    ):
        """Duplicate POST returns 200 with already_recorded=True."""
        template = _create_mob_template(name="Скелет", tier="normal")
        _create_active_mob(mob_template_id=template.id, character_id=800)

        # First call
        resp1 = bestiary_client.post(
            "/characters/internal/record-mob-kill",
            json={"character_id": 20, "mob_character_id": 800},
        )
        assert resp1.status_code == 200
        assert resp1.json()["already_recorded"] is False

        # Second call — idempotent
        resp2 = bestiary_client.post(
            "/characters/internal/record-mob-kill",
            json={"character_id": 20, "mob_character_id": 800},
        )
        assert resp2.status_code == 200
        assert resp2.json()["already_recorded"] is True

    def test_record_kill_missing_fields_returns_422(self, bestiary_client):
        """Missing required fields in request body returns 422."""
        resp = bestiary_client.post(
            "/characters/internal/record-mob-kill",
            json={"character_id": 10},
        )
        assert resp.status_code == 422


# ============================================================
# 4. Endpoint: GET /bestiary
# ============================================================


class TestBestiaryEndpoint:
    """Integration tests for GET /characters/bestiary."""

    def test_bestiary_returns_entries(
        self, bestiary_client, _create_mob_template
    ):
        _create_mob_template(name="Огр", tier="normal")
        _create_mob_template(name="Дракон", tier="boss", level=50)

        resp = bestiary_client.get("/characters/bestiary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["entries"]) == 2
        assert body["killed_count"] == 0

    def test_bestiary_with_character_id_shows_killed_status(
        self, bestiary_client, db_session, _create_mob_template, _create_mob_kill
    ):
        t1 = _create_mob_template(name="Убитый моб", tier="normal")
        _create_mob_template(name="Живой моб", tier="normal")
        _create_mob_kill(character_id=42, mob_template_id=t1.id)

        resp = bestiary_client.get("/characters/bestiary?character_id=42")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["killed_count"] == 1

        entries_by_name = {e["name"]: e for e in body["entries"]}
        assert entries_by_name["Убитый моб"]["killed"] is True
        assert entries_by_name["Живой моб"]["killed"] is False

    def test_bestiary_empty_db_returns_empty_list(self, bestiary_client):
        resp = bestiary_client.get("/characters/bestiary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["entries"] == []
        assert body["killed_count"] == 0

    def test_bestiary_visibility_rules_in_response(
        self, bestiary_client, db_session, _create_mob_template, _create_mob_kill
    ):
        """Verify visibility rules are applied through the endpoint response."""
        t_normal = _create_mob_template(
            name="Обычный враг",
            tier="normal",
            description="Видимое описание",
            base_attributes={"strength": 10},
        )
        t_boss = _create_mob_template(
            name="Скрытый босс",
            tier="boss",
            description="Скрытое описание",
            base_attributes={"strength": 999},
        )

        resp = bestiary_client.get("/characters/bestiary?character_id=99")

        assert resp.status_code == 200
        body = resp.json()
        entries_by_name = {e["name"]: e for e in body["entries"]}

        # Normal, not killed: description visible, skills hidden
        normal_entry = entries_by_name["Обычный враг"]
        assert normal_entry["description"] == "Видимое описание"
        assert normal_entry["base_attributes"] == {"strength": 10}
        assert normal_entry["skills"] is None

        # Boss, not killed: everything hidden
        boss_entry = entries_by_name["Скрытый босс"]
        assert boss_entry["description"] is None
        assert boss_entry["base_attributes"] is None
        assert boss_entry["skills"] is None
