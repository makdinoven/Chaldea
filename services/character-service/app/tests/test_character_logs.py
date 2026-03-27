"""
Tests for character logs and post history endpoints (FEAT-095, Tasks #2-3).

Covers:
(A) Create log entry — POST with valid data returns 201 with correct fields
(B) Create log with null metadata — POST without metadata works fine
(C) Get logs — returns paginated list ordered by created_at DESC
(D) Get logs with event_type filter — returns only matching type
(E) Get logs with limit/offset — pagination works correctly
(F) Get logs for non-existent character — returns empty list (not 404)
(G) Post history endpoint — char_count strips HTML, xp_earned computed correctly
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import Column, Integer, BigInteger, String, Text, TIMESTAMP, func

# database.engine and database.SessionLocal have been patched in conftest.py
import database
from database import Base
from main import app, get_db
from fastapi.testclient import TestClient
import models


# ---------------------------------------------------------------------------
# Extra tables needed for post-history tests (posts + Locations)
# These tables belong to locations-service but character-service queries them
# via raw SQL on the shared DB. We create minimal versions in the test DB.
# ---------------------------------------------------------------------------

class _PostTable(Base):
    __tablename__ = "posts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    location_id = Column(BigInteger, nullable=False)
    content = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class _LocationTable(Base):
    __tablename__ = "Locations"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(seed_fk_data):
    """Create fresh tables for every test, yield a session, then tear down."""
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client(db_session):
    """FastAPI TestClient wired to the real SQLite test session (no auth needed — endpoints are public/internal)."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_character(db_session, char_id=1, name="TestChar"):
    """Insert a minimal character for FK-like references."""
    char = models.Character(
        id=char_id,
        name=name,
        id_subrace=1,
        id_class=1,
        id_race=1,
        appearance="Test appearance",
        avatar="test.png",
        user_id=1,
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


# ---------------------------------------------------------------------------
# (A) Create log entry — POST with valid data returns 201
# ---------------------------------------------------------------------------

def test_create_log_entry(client, db_session):
    _create_character(db_session, char_id=1)

    response = client.post("/characters/1/logs", json={
        "event_type": "rp_post",
        "description": "Wrote a post in Tavern",
        "metadata": {"xp_earned": 3, "location": "Tavern"},
    })

    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["character_id"] == 1
    assert data["event_type"] == "rp_post"
    assert data["description"] == "Wrote a post in Tavern"
    assert data["metadata"] == {"xp_earned": 3, "location": "Tavern"}
    assert "created_at" in data


# ---------------------------------------------------------------------------
# (B) Create log with null metadata — works fine
# ---------------------------------------------------------------------------

def test_create_log_null_metadata(client, db_session):
    _create_character(db_session, char_id=1)

    response = client.post("/characters/1/logs", json={
        "event_type": "level_up",
        "description": "Reached level 5",
    })

    assert response.status_code == 201
    data = response.json()
    assert data["metadata"] is None
    assert data["event_type"] == "level_up"
    assert data["description"] == "Reached level 5"


# ---------------------------------------------------------------------------
# (A/B extra) Create log for non-existent character — returns 404
# ---------------------------------------------------------------------------

def test_create_log_nonexistent_character(client):
    response = client.post("/characters/99999/logs", json={
        "event_type": "rp_post",
        "description": "Should fail",
    })
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# (C) Get logs — returns paginated list ordered by created_at DESC
# ---------------------------------------------------------------------------

def test_get_logs_ordered_desc(client, db_session):
    char = _create_character(db_session, char_id=1)

    # Use explicit created_at values to ensure deterministic ordering
    # (SQLite CURRENT_TIMESTAMP has second resolution, so time.sleep is unreliable)
    from datetime import datetime, timedelta
    base_time = datetime(2026, 1, 1, 12, 0, 0)
    for i in range(3):
        db_session.add(models.CharacterLog(
            character_id=1,
            event_type="rp_post",
            description=f"Log entry {i}",
            created_at=base_time + timedelta(minutes=i),
        ))
    db_session.commit()

    response = client.get("/characters/1/logs")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["logs"]) == 3
    # Most recent first
    descriptions = [log["description"] for log in data["logs"]]
    assert descriptions == ["Log entry 2", "Log entry 1", "Log entry 0"]


# ---------------------------------------------------------------------------
# (D) Get logs with event_type filter — returns only matching type
# ---------------------------------------------------------------------------

def test_get_logs_filter_event_type(client, db_session):
    _create_character(db_session, char_id=1)

    db_session.add(models.CharacterLog(character_id=1, event_type="rp_post", description="Post 1"))
    db_session.add(models.CharacterLog(character_id=1, event_type="battle", description="Battle 1"))
    db_session.add(models.CharacterLog(character_id=1, event_type="rp_post", description="Post 2"))
    db_session.commit()

    response = client.get("/characters/1/logs?event_type=rp_post")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(log["event_type"] == "rp_post" for log in data["logs"])

    response2 = client.get("/characters/1/logs?event_type=battle")
    data2 = response2.json()
    assert data2["total"] == 1
    assert data2["logs"][0]["event_type"] == "battle"


# ---------------------------------------------------------------------------
# (E) Get logs with limit/offset — pagination works correctly
# ---------------------------------------------------------------------------

def test_get_logs_pagination(client, db_session):
    _create_character(db_session, char_id=1)

    for i in range(5):
        db_session.add(models.CharacterLog(
            character_id=1,
            event_type="rp_post",
            description=f"Log {i}",
        ))
    db_session.commit()

    # First page: limit=2, offset=0
    response = client.get("/characters/1/logs?limit=2&offset=0")
    data = response.json()
    assert data["total"] == 5
    assert len(data["logs"]) == 2

    # Second page: limit=2, offset=2
    response2 = client.get("/characters/1/logs?limit=2&offset=2")
    data2 = response2.json()
    assert data2["total"] == 5
    assert len(data2["logs"]) == 2

    # No overlap between pages
    ids_page1 = {log["id"] for log in data["logs"]}
    ids_page2 = {log["id"] for log in data2["logs"]}
    assert ids_page1.isdisjoint(ids_page2)

    # Last page: limit=2, offset=4
    response3 = client.get("/characters/1/logs?limit=2&offset=4")
    data3 = response3.json()
    assert len(data3["logs"]) == 1  # Only 1 remaining


# ---------------------------------------------------------------------------
# (F) Get logs for non-existent character — returns empty list (not 404)
# ---------------------------------------------------------------------------

def test_get_logs_nonexistent_character(client):
    response = client.get("/characters/99999/logs")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["logs"] == []


# ---------------------------------------------------------------------------
# (G) Post history endpoint — char_count strips HTML, xp_earned computed
# ---------------------------------------------------------------------------

def _seed_location(db_session, loc_id=1, name="Таверна"):
    loc = _LocationTable(id=loc_id, name=name)
    db_session.add(loc)
    db_session.commit()
    return loc


def _seed_post(db_session, post_id, character_id, location_id, content):
    post = _PostTable(id=post_id, character_id=character_id, location_id=location_id, content=content)
    db_session.add(post)
    db_session.commit()
    return post


def test_post_history_basic(client, db_session):
    """Post history returns posts with location names, char_count and xp_earned."""
    _create_character(db_session, char_id=1)
    _seed_location(db_session, loc_id=10, name="Таверна")

    # Plain text, 340 chars => xp_earned = floor(340/100 + 0.5) = floor(3.9) = 3
    content_340 = "A" * 340
    _seed_post(db_session, post_id=1, character_id=1, location_id=10, content=content_340)

    response = client.get("/characters/1/post-history")
    assert response.status_code == 200
    data = response.json()
    assert len(data["posts"]) == 1

    post = data["posts"][0]
    assert post["character_id"] == 1
    assert post["location_id"] == 10
    assert post["location_name"] == "Таверна"
    assert post["char_count"] == 340
    assert post["xp_earned"] == 3


def test_post_history_xp_350(client, db_session):
    """350 chars => xp_earned = floor(350/100 + 0.5) = floor(4.0) = 4."""
    _create_character(db_session, char_id=1)
    _seed_location(db_session, loc_id=10, name="Площадь")

    content_350 = "B" * 350
    _seed_post(db_session, post_id=1, character_id=1, location_id=10, content=content_350)

    response = client.get("/characters/1/post-history")
    data = response.json()
    assert data["posts"][0]["char_count"] == 350
    assert data["posts"][0]["xp_earned"] == 4


def test_post_history_xp_zero_below_300(client, db_session):
    """299 chars => xp_earned = 0 (below 300 threshold)."""
    _create_character(db_session, char_id=1)
    _seed_location(db_session, loc_id=10, name="Лес")

    content_299 = "C" * 299
    _seed_post(db_session, post_id=1, character_id=1, location_id=10, content=content_299)

    response = client.get("/characters/1/post-history")
    data = response.json()
    assert data["posts"][0]["char_count"] == 299
    assert data["posts"][0]["xp_earned"] == 0


def test_post_history_html_stripping(client, db_session):
    """char_count should not include HTML tags."""
    _create_character(db_session, char_id=1)
    _seed_location(db_session, loc_id=10, name="Порт")

    # 310 visible chars wrapped in heavy HTML markup
    visible_text = "X" * 310
    html_content = f"<p><b>{visible_text}</b></p>"
    _seed_post(db_session, post_id=1, character_id=1, location_id=10, content=html_content)

    response = client.get("/characters/1/post-history")
    data = response.json()
    assert data["posts"][0]["char_count"] == 310
    # 310 chars: floor(310/100 + 0.5) = floor(3.6) = 3
    assert data["posts"][0]["xp_earned"] == 3


def test_post_history_empty(client, db_session):
    """Post history for character with no posts returns empty list."""
    _create_character(db_session, char_id=1)

    response = client.get("/characters/1/post-history")
    assert response.status_code == 200
    data = response.json()
    assert data["posts"] == []
