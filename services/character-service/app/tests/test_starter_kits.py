"""
Tests for starter kits feature (FEAT-008).

Covers:
(a) Starter kit CRUD: get_all_starter_kits, upsert_starter_kit (create + update)
(b) Starter kit API endpoints: GET /characters/starter-kits, PUT /characters/starter-kits/{class_id}
(c) Approval flow with starter kit from DB (mock cross-service HTTP calls)
(d) Double-approve guard returns 400
(e) Notification producer: send_character_approved_notification
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.orm import sessionmaker

# database.engine and database.SessionLocal have been patched in conftest.py
# to point at an in-memory SQLite engine before main.py was imported.
import database
from database import Base
from main import app, get_db
from fastapi.testclient import TestClient
import models
import schemas


# ---------------------------------------------------------------------------
# Fixtures — real SQLite DB session (not mocked)
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create fresh tables for every test, yield a session, then tear down."""
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client(db_session):
    """FastAPI TestClient wired to the real SQLite test session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers: seed test data
# ---------------------------------------------------------------------------

def _seed_class(db, class_id=1, name="Воин"):
    cls = models.Class(id_class=class_id, name=name)
    db.add(cls)
    db.commit()
    db.refresh(cls)
    return cls


def _seed_race_and_subrace(db, race_id=1, subrace_id=1):
    race = models.Race(id_race=race_id, name=f"Race{race_id}")
    db.add(race)
    db.commit()
    subrace = models.Subrace(id_subrace=subrace_id, id_race=race_id, name=f"Subrace{subrace_id}")
    db.add(subrace)
    db.commit()
    return race, subrace


def _seed_character_request(db, user_id=42, class_id=1, race_id=1, subrace_id=1, status="pending"):
    req = models.CharacterRequest(
        user_id=user_id,
        name="TestHero",
        id_subrace=subrace_id,
        id_race=race_id,
        id_class=class_id,
        biography="Test bio",
        personality="Test personality",
        appearance="Tall and strong",
        sex="male",
        background="Noble",
        age=25,
        weight="80",
        height="185",
        avatar="https://example.com/avatar.webp",
        status=status,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _seed_starter_kit(db, class_id=1, items=None, skills=None, currency=100):
    kit = models.StarterKit(
        class_id=class_id,
        items=items or [{"item_id": 4, "quantity": 1}],
        skills=skills or [{"skill_id": 1}],
        currency_amount=currency,
    )
    db.add(kit)
    db.commit()
    db.refresh(kit)
    return kit


# ===========================================================================
# (a) Starter Kit CRUD tests
# ===========================================================================


class TestGetAllStarterKits:
    """Test crud.get_all_starter_kits returns all kits."""

    def test_get_all_starter_kits_empty(self, db_session):
        import crud
        result = crud.get_all_starter_kits(db_session)
        assert result == []

    def test_get_all_starter_kits_returns_all(self, db_session):
        import crud
        _seed_class(db_session, 1, "Воин")
        _seed_class(db_session, 2, "Плут")
        _seed_starter_kit(db_session, class_id=1, currency=100)
        _seed_starter_kit(db_session, class_id=2, currency=150)

        result = crud.get_all_starter_kits(db_session)
        assert len(result) == 2
        class_ids = {kit.class_id for kit in result}
        assert class_ids == {1, 2}


class TestUpsertStarterKit:
    """Test crud.upsert_starter_kit creates and updates."""

    def test_upsert_starter_kit_create(self, db_session):
        import crud
        _seed_class(db_session, 1, "Воин")
        data = schemas.StarterKitUpdate(
            items=[schemas.StarterKitItem(item_id=4, quantity=1)],
            skills=[schemas.StarterKitSkill(skill_id=1)],
            currency_amount=200,
        )
        kit = crud.upsert_starter_kit(db_session, class_id=1, data=data)

        assert kit.id is not None
        assert kit.class_id == 1
        assert kit.currency_amount == 200
        assert len(kit.items) == 1
        assert kit.items[0]["item_id"] == 4
        assert len(kit.skills) == 1
        assert kit.skills[0]["skill_id"] == 1

    def test_upsert_starter_kit_update(self, db_session):
        import crud
        _seed_class(db_session, 1, "Воин")
        _seed_starter_kit(db_session, class_id=1, items=[{"item_id": 4, "quantity": 1}], currency=100)

        updated_data = schemas.StarterKitUpdate(
            items=[schemas.StarterKitItem(item_id=5, quantity=3), schemas.StarterKitItem(item_id=6, quantity=2)],
            skills=[schemas.StarterKitSkill(skill_id=10), schemas.StarterKitSkill(skill_id=11)],
            currency_amount=500,
        )
        kit = crud.upsert_starter_kit(db_session, class_id=1, data=updated_data)

        assert kit.currency_amount == 500
        assert len(kit.items) == 2
        assert kit.items[0]["item_id"] == 5
        assert len(kit.skills) == 2


# ===========================================================================
# (b) Starter Kit API endpoint tests
# ===========================================================================


class TestGetStarterKitsEndpoint:
    """GET /characters/starter-kits"""

    def test_get_starter_kits_empty(self, db_session, client):
        response = client.get("/characters/starter-kits")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_starter_kits_returns_list(self, db_session, client):
        _seed_class(db_session, 1, "Воин")
        _seed_starter_kit(db_session, class_id=1, items=[{"item_id": 4, "quantity": 1}], skills=[{"skill_id": 1}], currency=100)

        response = client.get("/characters/starter-kits")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["class_id"] == 1
        assert data[0]["currency_amount"] == 100
        assert data[0]["items"] == [{"item_id": 4, "quantity": 1}]
        assert data[0]["skills"] == [{"skill_id": 1}]


class TestPutStarterKitEndpoint:
    """PUT /characters/starter-kits/{class_id}"""

    def test_put_starter_kit_valid(self, db_session, client):
        _seed_class(db_session, 1, "Воин")

        payload = {
            "items": [{"item_id": 4, "quantity": 1}, {"item_id": 1, "quantity": 5}],
            "skills": [{"skill_id": 1}, {"skill_id": 2}],
            "currency_amount": 100,
        }
        response = client.put("/characters/starter-kits/1", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["class_id"] == 1
        assert data["currency_amount"] == 100
        assert len(data["items"]) == 2
        assert len(data["skills"]) == 2

    def test_put_starter_kit_invalid_class(self, db_session, client):
        """PUT with non-existent class_id returns 404."""
        payload = {
            "items": [],
            "skills": [],
            "currency_amount": 0,
        }
        response = client.put("/characters/starter-kits/9999", json=payload)
        assert response.status_code == 404

    def test_put_starter_kit_upsert_updates_existing(self, db_session, client):
        """Second PUT to same class_id updates rather than duplicates."""
        _seed_class(db_session, 2, "Плут")

        payload1 = {"items": [{"item_id": 6, "quantity": 1}], "skills": [], "currency_amount": 50}
        resp1 = client.put("/characters/starter-kits/2", json=payload1)
        assert resp1.status_code == 200

        payload2 = {"items": [{"item_id": 7, "quantity": 2}], "skills": [{"skill_id": 3}], "currency_amount": 200}
        resp2 = client.put("/characters/starter-kits/2", json=payload2)
        assert resp2.status_code == 200

        data = resp2.json()
        assert data["currency_amount"] == 200
        assert len(data["items"]) == 1
        assert data["items"][0]["item_id"] == 7

        # Verify only one row exists
        kits = client.get("/characters/starter-kits").json()
        assert len(kits) == 1


# ===========================================================================
# (c) Approval flow tests
# ===========================================================================


class TestApproveWithStarterKit:
    """Approval reads starter kit from DB, sends correct data to services."""

    @patch("main.send_character_approved_notification")
    @patch("crud.assign_character_to_user", new_callable=AsyncMock)
    @patch("crud.send_attributes_request", new_callable=AsyncMock)
    @patch("crud.send_skills_presets_request", new_callable=AsyncMock)
    @patch("crud.send_inventory_request", new_callable=AsyncMock)
    def test_approve_with_starter_kit(
        self,
        mock_inventory,
        mock_skills,
        mock_attributes,
        mock_assign,
        mock_notification,
        db_session,
        client,
    ):
        # Setup
        _seed_class(db_session, 1, "Воин")
        _seed_race_and_subrace(db_session, race_id=1, subrace_id=1)
        req = _seed_character_request(db_session, user_id=42, class_id=1)
        _seed_starter_kit(
            db_session,
            class_id=1,
            items=[{"item_id": 4, "quantity": 1}, {"item_id": 1, "quantity": 5}],
            skills=[{"skill_id": 1}, {"skill_id": 2}],
            currency=100,
        )

        # Mock responses
        mock_inventory.return_value = {"status": "ok"}
        mock_skills.return_value = {"status": "ok"}
        mock_attributes.return_value = {"id": 999}
        mock_assign.return_value = True

        response = client.post(f"/characters/requests/{req.id}/approve")
        assert response.status_code == 200

        # Verify inventory was called with starter kit items
        mock_inventory.assert_called_once()
        inv_args = mock_inventory.call_args
        items_sent = inv_args[0][1]  # second positional arg is items list
        assert len(items_sent) == 2
        assert items_sent[0]["item_id"] == 4
        assert items_sent[1]["item_id"] == 1
        assert items_sent[1]["quantity"] == 5

        # Verify skills were called with starter kit skills + subrace skill (7)
        mock_skills.assert_called_once()
        skills_call = mock_skills.call_args
        # send_skills_presets_request(character_id=..., skill_ids=...)
        skill_ids = skills_call.kwargs.get("skill_ids") or skills_call[1].get("skill_ids")
        if skill_ids is None:
            # positional args: (character_id, skill_ids)
            skill_ids = skills_call[0][1]
        assert 1 in skill_ids
        assert 2 in skill_ids
        assert 7 in skill_ids  # SUBRACE_SKILL_ID

        # Verify character got currency_balance
        character = db_session.query(models.Character).first()
        assert character is not None
        assert character.currency_balance == 100

        # Verify notification was called
        mock_notification.assert_called_once_with(42, "TestHero")

    @patch("main.send_character_approved_notification")
    @patch("crud.assign_character_to_user", new_callable=AsyncMock)
    @patch("crud.send_attributes_request", new_callable=AsyncMock)
    @patch("crud.send_skills_presets_request", new_callable=AsyncMock)
    @patch("crud.send_inventory_request", new_callable=AsyncMock)
    def test_approve_without_starter_kit(
        self,
        mock_inventory,
        mock_skills,
        mock_attributes,
        mock_assign,
        mock_notification,
        db_session,
        client,
    ):
        """Approval works even if no starter kit is configured (empty items/skills)."""
        _seed_class(db_session, 1, "Воин")
        _seed_race_and_subrace(db_session, race_id=1, subrace_id=1)
        req = _seed_character_request(db_session, user_id=42, class_id=1)
        # No starter kit seeded

        mock_attributes.return_value = {"id": 888}
        mock_assign.return_value = True
        mock_skills.return_value = {"status": "ok"}

        response = client.post(f"/characters/requests/{req.id}/approve")
        assert response.status_code == 200

        # Inventory should NOT be called (no items)
        mock_inventory.assert_not_called()

        # Skills should still be called with the universal subrace skill
        mock_skills.assert_called_once()
        skills_call = mock_skills.call_args
        skill_ids = skills_call.kwargs.get("skill_ids") or skills_call[1].get("skill_ids")
        if skill_ids is None:
            skill_ids = skills_call[0][1]
        assert skill_ids == [7]  # only SUBRACE_SKILL_ID

        # Character currency_balance should be 0
        character = db_session.query(models.Character).first()
        assert character is not None
        assert character.currency_balance == 0


# ===========================================================================
# (d) Double-approve guard
# ===========================================================================


class TestDoubleApproveGuard:
    """Approving an already-approved request returns HTTP 400."""

    def test_double_approve_returns_400(self, db_session, client):
        _seed_class(db_session, 1, "Воин")
        _seed_race_and_subrace(db_session, race_id=1, subrace_id=1)
        req = _seed_character_request(db_session, user_id=42, class_id=1, status="approved")

        response = client.post(f"/characters/requests/{req.id}/approve")
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "обработана" in detail or "уже" in detail

    def test_approve_nonexistent_request_returns_404(self, db_session, client):
        response = client.post("/characters/requests/99999/approve")
        assert response.status_code == 404


# ===========================================================================
# (e) Notification producer tests
# ===========================================================================


class TestSendNotificationSuccess:
    """Mock pika, verify correct message published."""

    @patch("producer.BlockingConnection")
    def test_send_notification_success(self, mock_conn_class):
        from producer import send_character_approved_notification

        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_conn_class.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel

        send_character_approved_notification(user_id=42, character_name="Артас")

        # Verify queue declared
        mock_channel.queue_declare.assert_called_once_with(
            queue="general_notifications", durable=True
        )

        # Verify message published with correct routing key and body
        mock_channel.basic_publish.assert_called_once()
        call_kwargs = mock_channel.basic_publish.call_args[1]
        assert call_kwargs["routing_key"] == "general_notifications"

        parsed = json.loads(call_kwargs["body"])
        assert parsed["target_type"] == "user"
        assert parsed["target_value"] == 42
        assert "Артас" in parsed["message"]

        # Verify connection closed
        mock_connection.close.assert_called_once()


class TestSendNotificationFailure:
    """Mock pika to raise exception, verify function doesn't throw."""

    @patch("producer.BlockingConnection")
    def test_send_notification_failure_non_blocking(self, mock_conn_class):
        from producer import send_character_approved_notification

        mock_conn_class.side_effect = Exception("Connection refused")

        # Should NOT raise — function handles exception internally
        send_character_approved_notification(user_id=42, character_name="Артас")
        # If we get here, the function did not throw
