"""
FEAT-154 (task #25) — tests for the public character passport and the list keys.

Covers:
(a) GET /characters/{id}/public — 200, 404, NPCs (N13), username resolution,
    graceful degradation when user-service is unreachable
(b) GET /characters/list — the additive FEAT-154 keys, and the proof that no
    pre-existing key disappeared
(c) security: the endpoint is public but read-only; injection through the path
(d) FEAT-155: the passport prints the FROZEN starting attributes and the
    endpoint never reads the character's current stats
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

# The ten keys the passport prints (rule 27).
PASSPORT_STAT_KEYS = {
    "strength", "agility", "intelligence", "endurance", "health",
    "mana", "energy", "stamina", "charisma", "luck",
}

# A subrace preset: exactly 100 points, as every preset must be (rule 5).
STARTING_PRESET = {
    "strength": 12, "agility": 14, "intelligence": 20, "endurance": 8,
    "health": 10, "mana": 12, "energy": 6, "stamina": 9,
    "charisma": 5, "luck": 4,
}

# What the character has grown into. FEAT-155: this must NEVER reach the
# passport — it is the exact leak the feature closes. If a test ever sees these
# numbers in a response, the live lookup is back.
CURRENT_ATTRIBUTES = {
    "id": 1, "character_id": 1,
    "strength": 30, "agility": 25, "intelligence": 20, "endurance": 8,
    "health": 10, "mana": 12, "energy": 6, "stamina": 9,
    "charisma": 5, "luck": 4,
    "max_health": 350, "current_health": 350, "dodge": 5.0, "damage": 0,
}

# Kept for the older tests that only care about "some outbound call happened".
SAMPLE_ATTRIBUTES = CURRENT_ATTRIBUTES


def _http_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


@pytest.fixture(autouse=True)
def stub_outbound():
    """
    Keep the passport off the network.

    ``get_character_public`` makes exactly ONE outbound GET — the username from
    user-service. FEAT-155 removed the second one: the passport no longer asks
    character-attributes-service for anything, because it prints the frozen
    starting attributes, not the character's current build.

    The stub still answers an attributes URL with a *loud, wrong* payload
    (``CURRENT_ATTRIBUTES``). That is deliberate: if the live lookup ever comes
    back, those numbers will show up in a response and the assertions below
    will fail rather than quietly pass.
    """
    with patch("main.httpx.get") as mock_get:
        def route(url, *args, **kwargs):
            if "/attributes/" in url:
                return _http_response(CURRENT_ATTRIBUTES)
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

def _numbers_in(payload):
    """Every number anywhere in a JSON payload — used to prove a value is absent."""
    found = []
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            found.append(node)
    return found


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
        starting_attributes=dict(STARTING_PRESET),
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
            return _http_response(CURRENT_ATTRIBUTES)

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
    """
    FEAT-155 / rule 27 — «Оценка при вступлении» is a RECORD.

    Two things are pinned here, and together they are the whole feature: the
    passport prints what the character *started* with, and the endpoint cannot
    leak what they have *become*.
    """

    def test_the_frozen_snapshot_is_what_is_returned(self, db_session, client, stub_user_service):
        char = _seed_character(db_session)

        data = client.get(f"/characters/{char.id}/public").json()

        assert data["starting_attributes"] == STARTING_PRESET
        assert data["starting_attributes_is_snapshot"] is True
        assert set(data["starting_attributes"].keys()) == PASSPORT_STAT_KEYS

    def test_the_snapshot_sums_to_the_preset_total(self, db_session, client, stub_user_service):
        """The caption «N из 100 очков подрасы» must not be able to lie again."""
        char = _seed_character(db_session)

        data = client.get(f"/characters/{char.id}/public").json()
        assert sum(data["starting_attributes"].values()) == 100

    def test_the_attributes_service_is_never_called(self, db_session, client, stub_user_service):
        """
        The leak is closed at the source: with no live lookup left, there is
        nothing current for the endpoint to hand out.
        """
        char = _seed_character(db_session)
        client.get(f"/characters/{char.id}/public")

        assert _attributes_calls(stub_user_service) == []

    def test_current_stats_are_not_exposed_anywhere_in_the_response(
        self, db_session, client, stub_user_service
    ):
        """
        A grown character (strength 30) must still read as the recruit they
        were (strength 12). Asserted over the WHOLE body, not one key, so a
        re-introduction under a different name is caught too.
        """
        char = _seed_character(db_session)

        body = client.get(f"/characters/{char.id}/public").json()

        assert "stats" not in body
        assert body["starting_attributes"]["strength"] == 12
        assert CURRENT_ATTRIBUTES["strength"] not in _numbers_in(body)
        assert CURRENT_ATTRIBUTES["agility"] not in _numbers_in(body)

    def test_level_is_still_reported(self, db_session, client, stub_user_service):
        """The УР stays public — only the point distribution was the spoiler."""
        char = _seed_character(db_session, level=17)

        assert client.get(f"/characters/{char.id}/public").json()["level"] == 17

    def test_a_later_stat_gain_does_not_rewrite_the_record(
        self, db_session, client, stub_user_service
    ):
        """
        Retroactivity, mirrored from the granted_kit freeze (rule 12d): the
        character levels up and spends points, and the passport is unchanged.
        """
        char = _seed_character(db_session)
        before = client.get(f"/characters/{char.id}/public").json()["starting_attributes"]

        char.level = 9
        char.stat_points = 40
        db_session.commit()

        after = client.get(f"/characters/{char.id}/public").json()["starting_attributes"]
        assert after == before == STARTING_PRESET


class TestPassportStatsWithoutSnapshot:
    """
    FEAT-155, the pre-feature case — the analogue of D18.

    A character created before the column existed has no record. Rather than
    fabricating one, or falling back to the live build (which is the bug), the
    passport reconstructs the subrace preset and flags it as a reconstruction,
    so the reader is not sold a certainty.
    """

    def _preset_the_subrace(self, db_session, preset=None):
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.stat_preset = dict(preset if preset is not None else STARTING_PRESET)
        db_session.commit()

    def test_falls_back_to_the_subrace_preset(self, db_session, client, stub_user_service):
        self._preset_the_subrace(db_session)
        char = _seed_character(db_session, starting_attributes=None)

        data = client.get(f"/characters/{char.id}/public").json()

        assert data["starting_attributes"] == STARTING_PRESET
        assert data["starting_attributes_is_snapshot"] is False

    def test_the_fallback_does_not_call_the_attributes_service(
        self, db_session, client, stub_user_service
    ):
        """The pre-feature path is exactly where the old code leaked. It must not."""
        self._preset_the_subrace(db_session)
        char = _seed_character(db_session, starting_attributes=None)

        body = client.get(f"/characters/{char.id}/public").json()

        assert _attributes_calls(stub_user_service) == []
        assert body["starting_attributes"]["strength"] == 12
        assert CURRENT_ATTRIBUTES["strength"] not in _numbers_in(body)

    def test_no_snapshot_and_no_preset_means_no_block(self, db_session, client, stub_user_service):
        """Nothing knowable -> None, and the frontend omits the block entirely."""
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.stat_preset = None
        db_session.commit()
        char = _seed_character(db_session, starting_attributes=None)

        data = client.get(f"/characters/{char.id}/public").json()
        assert data["starting_attributes"] is None
        assert data["starting_attributes_is_snapshot"] is False

    def test_a_corrupt_snapshot_degrades_instead_of_crashing(
        self, db_session, client, stub_user_service
    ):
        """A JSON blob of the wrong shape must not 500 a public page."""
        self._preset_the_subrace(db_session)
        char = _seed_character(db_session, starting_attributes=["not", "a", "dict"])

        response = client.get(f"/characters/{char.id}/public")
        assert response.status_code == 200
        # An unusable snapshot is treated as absent, so the reconstruction wins.
        assert response.json()["starting_attributes"] == STARTING_PRESET
        assert response.json()["starting_attributes_is_snapshot"] is False

    def test_non_numeric_keys_are_dropped_from_the_snapshot(
        self, db_session, client, stub_user_service
    ):
        char = _seed_character(
            db_session,
            starting_attributes={"strength": 12, "agility": "много", "luck": None},
        )

        data = client.get(f"/characters/{char.id}/public").json()
        assert data["starting_attributes"] == {"strength": 12}
        assert data["starting_attributes_is_snapshot"] is True


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
