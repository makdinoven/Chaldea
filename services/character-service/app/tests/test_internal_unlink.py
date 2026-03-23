"""
Tests for POST /characters/internal/unlink endpoint in character-service.

Covers:
- Unlink works (character user_id set to None)
- Character not found -> 404
- Already unlinked character -> 200 (idempotent)
"""

import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

import models
import database
from main import app, get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_tables(test_engine):
    """Create all tables before each test, drop after."""
    models.Base.metadata.create_all(bind=test_engine)
    yield
    models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session(test_session_factory):
    """Provide a clean DB session for each test."""
    session = test_session_factory()
    try:
        yield session
    finally:
        session.close()


def _seed_reference_data(session):
    """Insert minimal FK reference data required by characters table."""
    for rid, name in [(1, "Человек")]:
        if not session.query(models.Race).filter_by(id_race=rid).first():
            session.add(models.Race(id_race=rid, name=name))
    session.flush()
    for sid, rid, name in [(1, 1, "Норд")]:
        if not session.query(models.Subrace).filter_by(id_subrace=sid).first():
            session.add(models.Subrace(id_subrace=sid, id_race=rid, name=name))
    session.flush()
    for cid, name in [(1, "Воин")]:
        if not session.query(models.Class).filter_by(id_class=cid).first():
            session.add(models.Class(id_class=cid, name=name))
    session.commit()


def _create_character(session, char_id=1, user_id=10, name="TestChar"):
    """Create a test character with minimal required fields."""
    _seed_reference_data(session)
    char = models.Character(
        id=char_id,
        name=name,
        id_subrace=1,
        id_class=1,
        id_race=1,
        user_id=user_id,
        appearance="Test appearance",
        avatar="test.png",
    )
    session.add(char)
    session.commit()
    session.refresh(char)
    return char


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with real SQLite DB session."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Tests: POST /characters/internal/unlink
# ═══════════════════════════════════════════════════════════════════════════


class TestInternalUnlink:
    """Tests for the internal unlink endpoint."""

    def test_unlink_character_success(self, client, db_session):
        """Unlink sets character.user_id to None and returns 200."""
        char = _create_character(db_session, char_id=1, user_id=10)
        assert char.user_id == 10

        response = client.post(
            "/characters/internal/unlink",
            json={"character_id": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["detail"] == "Character unlinked from user"
        assert data["character_id"] == 1
        assert data["previous_user_id"] == 10

        # Verify in DB
        db_session.expire_all()
        updated_char = db_session.query(models.Character).filter_by(id=1).first()
        assert updated_char.user_id is None

    def test_character_not_found_returns_404(self, client):
        """Non-existent character -> 404."""
        response = client.post(
            "/characters/internal/unlink",
            json={"character_id": 9999},
        )

        assert response.status_code == 404
        assert "не найден" in response.json()["detail"]

    def test_already_unlinked_returns_200_idempotent(self, client, db_session):
        """Already unlinked character -> 200 with idempotent message."""
        char = _create_character(db_session, char_id=2, user_id=None)
        assert char.user_id is None

        response = client.post(
            "/characters/internal/unlink",
            json={"character_id": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["detail"] == "Character already unlinked"
        assert data["character_id"] == 2
