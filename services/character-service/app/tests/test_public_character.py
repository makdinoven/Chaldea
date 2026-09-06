"""
FEAT-154 (task #25) — tests for the public character passport and the list keys.

Covers:
(a) GET /characters/{id}/public — 200, 404, NPCs (N13), username resolution,
    graceful degradation when user-service is unreachable
(b) GET /characters/list — the additive FEAT-154 keys, and the proof that no
    pre-existing key disappeared
(c) security: the endpoint is public but read-only; injection through the path
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

import database
from database import Base
import models
from main import app, get_db


# Every key GET /characters/list returned BEFORE FEAT-154. None may disappear.
LEGACY_LIST_KEYS = {
    "id", "name", "avatar", "level", "id_class", "id_race", "id_subrace",
    "biography", "personality", "appearance", "background", "sex", "age",
    "is_npc", "user_id", "username", "class_name", "race_name", "subrace_name",
}

# Keys FEAT-154 adds so the compact passport card renders with zero extra requests.
NEW_LIST_KEYS = {
    "origin_id", "registered_at", "skitaltsy_since_year", "skitaltsy_since_segment",
    "height", "weight", "current_location_id", "subrace_image",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# The preset the passport prints (FEAT-154 rule 27 / N26).
PASSPORT_STAT_KEYS = {
    "strength", "agility", "intelligence", "endurance", "health",
    "mana", "energy", "stamina", "charisma", "luck",
}

SAMPLE_ATTRIBUTES = {
    "id": 1, "character_id": 1,
    "strength": 12, "agility": 14, "intelligence": 20, "endurance": 8,
    "health": 10, "mana": 12, "energy": 6, "stamina": 9,
    "charisma": 5, "luck": 4,
    # Everything the attributes service also returns and the passport ignores.
    "max_health": 350, "current_health": 350, "dodge": 5.0, "damage": 0,
}


def _http_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


@pytest.fixture(autouse=True)
def stub_outbound():
    """
    Keep the passport off the network.

    ``get_character_public`` now makes TWO outbound GETs: the username from
    user-service and the stat preset from character-attributes-service (N26).
    They are routed by URL so a test can break one without breaking the other.
    """
    with patch("main.httpx.get") as mock_get:
        def route(url, *args, **kwargs):
            if "/attributes/" in url:
                return _http_response(SAMPLE_ATTRIBUTES)
            return _http_response({"username": "player"})

        mock_get.side_effect = route
        yield mock_get


def _user_service_calls(mock_get):
    """Only the calls aimed at user-service."""
    return [c for c in mock_get.call_args_list if "/users/" in c.args[0]]


def _attributes_calls(mock_get):
    """Only the calls aimed at character-attributes-service."""
    return [c for c in mock_get.call_args_list if "/attributes/" in c.args[0]]


@pytest.fixture
def stub_user_service(stub_outbound):
    """Backwards-compatible alias for tests that talk about user-service."""
    return stub_outbound


@pytest.fixture
def db_session(seed_fk_data):
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
    """Public endpoints — no auth override on purpose."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_character(db, **overrides):
    fields = dict(
        name="Аэлис",
        id_race=2,
        id_subrace=4,
        id_class=1,
        biography="Био",
        personality="Характер",
        appearance="Высокая эльфийка",
        background="Предыстория",
        sex="female",
        age=120,
        weight="52",
        height="168",
        avatar="https://example.com/a.webp",
        user_id=42,
        level=3,
        origin_id=7,
        skitaltsy_since_year=1783,
        skitaltsy_since_segment=2,
        current_location_id=1183,
        granted_kit={
            "class_id": 1, "origin_id": 7, "resolved_from": "exact",
            "items": [{"item_id": 5, "quantity": 1}], "skills": [{"skill_id": 4}],
            "currency_amount": 100, "granted_at": "2026-09-06T11:00:00",
        },
    )
    fields.update(overrides)
    char = models.Character(**fields)
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


# ===========================================================================
# (a) GET /characters/{id}/public
# ===========================================================================

class TestPublicPassport:
    def test_returns_the_full_passport(self, db_session, client):
        char = _seed_character(db_session)

        response = client.get(f"/characters/{char.id}/public")
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == char.id
        assert data["name"] == "Аэлис"
        assert data["level"] == 3
        assert data["race_name"] == "Эльф"
        assert data["subrace_name"] == "Лесной"
        assert data["class_name"] == "Воин"
        assert data["origin_id"] == 7
        assert data["skitaltsy_since_year"] == 1783
        assert data["skitaltsy_since_segment"] == 2
        assert data["current_location_id"] == 1183
        assert data["is_npc"] is False

    def test_subrace_look_and_feel_is_included(self, db_session, client):
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.image = "https://example.com/subrace.webp"
        subrace.distinctive_features = "Заострённые уши, серебристая кожа."
        db_session.commit()

        char = _seed_character(db_session)
        data = client.get(f"/characters/{char.id}/public").json()

        assert data["subrace_image"] == "https://example.com/subrace.webp"
        assert data["subrace_distinctive_features"] == "Заострённые уши, серебристая кожа."

    def test_username_comes_from_user_service(self, db_session, client, stub_user_service):
        char = _seed_character(db_session, user_id=42)
        data = client.get(f"/characters/{char.id}/public").json()

        assert data["user_id"] == 42
        assert data["username"] == "player"

    def test_user_service_failure_does_not_break_the_passport(self, db_session, client, stub_user_service):
        """The name lives in another service; its outage must not 500 the passport."""
        def only_user_service_fails(url, *args, **kwargs):
            if "/users/" in url:
                raise Exception("connection refused")
            return _http_response(SAMPLE_ATTRIBUTES)

        stub_user_service.side_effect = only_user_service_fails
        char = _seed_character(db_session, user_id=42)

        response = client.get(f"/characters/{char.id}/public")
        assert response.status_code == 200
        assert response.json()["username"] is None

    def test_ownerless_character_skips_user_service(self, db_session, client, stub_user_service):
        char = _seed_character(db_session, user_id=None)
        data = client.get(f"/characters/{char.id}/public").json()

        assert data["user_id"] is None
        assert data["username"] is None
        assert _user_service_calls(stub_user_service) == []


    def test_npc_is_served_too(self, db_session, client):
        """N13: no NPC filtering was specified — the flag is reported instead."""
        npc = _seed_character(db_session, name="Координатор", is_npc=True, user_id=None)

        response = client.get(f"/characters/{npc.id}/public")
        assert response.status_code == 200
        assert response.json()["is_npc"] is True

    def test_unknown_id_returns_404(self, db_session, client):
        response = client.get("/characters/999999/public")
        assert response.status_code == 404
        assert response.json()["detail"] == "Персонаж не найден"

    def test_endpoint_is_public(self, db_session, client):
        """No Authorization header — the characters page reads it anonymously."""
        char = _seed_character(db_session)
        assert client.get(f"/characters/{char.id}/public").status_code == 200

    def test_non_numeric_id_returns_422_not_500(self, db_session, client):
        assert client.get("/characters/abc/public").status_code == 422

    def test_sql_injection_in_path_is_rejected_by_the_type(self, db_session, client):
        response = client.get("/characters/1 OR 1=1; DROP TABLE characters/public")
        assert response.status_code in (404, 422)
        # The table survived.
        assert db_session.query(models.Character).count() == 0

    def test_free_text_is_returned_verbatim_not_executed(self, db_session, client):
        """Passport prose is stored and returned as text (R9 rendering invariant)."""
        payload = "<script>alert(1)</script>'; DROP TABLE characters; --"
        char = _seed_character(db_session, biography=payload)

        data = client.get(f"/characters/{char.id}/public").json()
        assert data["biography"] == payload
        assert db_session.query(models.Character).count() == 1


class TestPassportStats:
    """N26 / rule 27 — the passport carries the stat preset, gracefully."""

    def test_stats_come_from_the_attributes_service(self, db_session, client, stub_user_service):
        char = _seed_character(db_session)

        data = client.get(f"/characters/{char.id}/public").json()

        assert data["stats"] == {
            "strength": 12, "agility": 14, "intelligence": 20, "endurance": 8,
            "health": 10, "mana": 12, "energy": 6, "stamina": 9,
            "charisma": 5, "luck": 4,
        }
        assert set(data["stats"].keys()) == PASSPORT_STAT_KEYS

    def test_the_attributes_service_is_asked_for_this_character(self, db_session, client, stub_user_service):
        char = _seed_character(db_session)
        client.get(f"/characters/{char.id}/public")

        calls = _attributes_calls(stub_user_service)
        assert len(calls) == 1
        assert calls[0].args[0].endswith(f"/{char.id}")

    def test_service_outage_returns_the_passport_without_stats(self, db_session, client, stub_user_service):
        """A neighbour going down must never 500 the passport."""
        def attributes_are_down(url, *args, **kwargs):
            if "/attributes/" in url:
                raise Exception("connection refused")
            return _http_response({"username": "player"})

        stub_user_service.side_effect = attributes_are_down
        char = _seed_character(db_session)

        response = client.get(f"/characters/{char.id}/public")
        assert response.status_code == 200
        body = response.json()
        assert body["stats"] is None
        # The rest of the passport is intact.
        assert body["name"] == "Аэлис"
        assert body["granted_kit"] is not None

    def test_missing_attributes_row_is_reported_as_no_stats(self, db_session, client, stub_user_service):
        """404 from the attributes service — a character without an attributes row."""
        def not_found(url, *args, **kwargs):
            if "/attributes/" in url:
                return _http_response({"detail": "Attributes not found"}, status_code=404)
            return _http_response({"username": "player"})

        stub_user_service.side_effect = not_found
        char = _seed_character(db_session)

        response = client.get(f"/characters/{char.id}/public")
        assert response.status_code == 200
        assert response.json()["stats"] is None

    def test_unexpected_payload_does_not_crash_the_passport(self, db_session, client, stub_user_service):
        """A garbage body degrades to «no stats», it does not raise."""
        def garbage(url, *args, **kwargs):
            if "/attributes/" in url:
                return _http_response(["not", "a", "dict"])
            return _http_response({"username": "player"})

        stub_user_service.side_effect = garbage
        char = _seed_character(db_session)

        response = client.get(f"/characters/{char.id}/public")
        assert response.status_code == 200
        assert response.json()["stats"] is None


# ===========================================================================
# (b) GET /characters/list — additive keys only
# ===========================================================================

class TestCharacterListKeys:
    def test_no_legacy_key_disappeared(self, db_session, client):
        _seed_character(db_session)

        item = client.get("/characters/list").json()["items"][0]
        missing = LEGACY_LIST_KEYS - set(item.keys())
        assert missing == set(), f"пропали существующие ключи: {missing}"

    def test_new_passport_keys_are_present(self, db_session, client):
        _seed_character(db_session)

        item = client.get("/characters/list").json()["items"][0]
        missing = NEW_LIST_KEYS - set(item.keys())
        assert missing == set(), f"не добавлены ключи FEAT-154: {missing}"

    def test_new_keys_carry_the_real_values(self, db_session, client):
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.image = "https://example.com/subrace.webp"
        db_session.commit()
        _seed_character(db_session)

        item = client.get("/characters/list").json()["items"][0]
        assert item["origin_id"] == 7
        assert item["skitaltsy_since_year"] == 1783
        assert item["skitaltsy_since_segment"] == 2
        assert item["height"] == "168"
        assert item["weight"] == "52"
        assert item["current_location_id"] == 1183
        assert item["subrace_image"] == "https://example.com/subrace.webp"

    def test_registered_at_is_serialised(self, db_session, client):
        from datetime import datetime

        _seed_character(db_session, registered_at=datetime(2026, 9, 6, 11, 0, 0))
        item = client.get("/characters/list").json()["items"][0]
        assert item["registered_at"] is not None
        assert "2026-09-06" in str(item["registered_at"])

    def test_pre_feature_character_reports_nulls_not_errors(self, db_session, client):
        """A character created before FEAT-154 has NULLs in every new column."""
        _seed_character(
            db_session, origin_id=None, skitaltsy_since_year=None,
            skitaltsy_since_segment=None, current_location_id=None, granted_kit=None,
        )
        item = client.get("/characters/list").json()["items"][0]
        assert item["origin_id"] is None
        assert item["registered_at"] is None
        assert item["skitaltsy_since_year"] is None
        assert item["current_location_id"] is None

    def test_envelope_shape_is_unchanged(self, db_session, client):
        _seed_character(db_session)
        body = client.get("/characters/list").json()
        assert set(body.keys()) == {"items", "total", "page", "page_size"}
        assert body["total"] == 1

    def test_npcs_are_still_hidden_by_default(self, db_session, client):
        _seed_character(db_session, name="Игрок")
        _seed_character(db_session, name="НПС", is_npc=True, user_id=None)

        default_names = [i["name"] for i in client.get("/characters/list").json()["items"]]
        assert default_names == ["Игрок"]

        with_npcs = [i["name"] for i in client.get("/characters/list?include_npcs=true").json()["items"]]
        assert set(with_npcs) == {"Игрок", "НПС"}

    def test_search_with_sql_injection_does_not_crash(self, db_session, client):
        _seed_character(db_session)
        response = client.get("/characters/list", params={"q": "'; DROP TABLE characters; --"})
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert db_session.query(models.Character).count() == 1
