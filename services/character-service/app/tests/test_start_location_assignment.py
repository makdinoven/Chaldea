"""
FEAT-154 (task #26) — the start-location fallback chain on approval (§3.6).

Every step of the chain is graceful (D8): locations-service is a soft dependency
and its outage must never fail an approval — the character simply ends up with
``current_location_id = NULL`` plus a Russian warning, which is exactly the
pre-feature status quo.

Also covered here: ``registered_at`` population, the passport fields copied from
the request, and the ``subraces.image`` avatar fallback (D5).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

import database
from database import Base
import models
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import (
    app,
    get_db,
    START_LOCATION_FALLBACK_WARNING,
    START_LOCATION_UNASSIGNED_WARNING,
)


CHOSEN_LOCATION_ID = 1183
DEFAULT_LOCATION_ID = 700

_ADMIN_USER = UserRead(id=1, username="admin", role="admin", permissions=[
    "characters:create", "characters:read", "characters:update",
    "characters:delete", "characters:approve",
])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def locations(seed_fk_data):
    """Stub main.locations_client — see the same fixture in test_approval_flow.py.

    Without it every approval waits out the 5 s HTTP timeout before falling
    through to step 3 of the chain.
    """
    with patch("main.locations_client") as mock_client:
        mock_client.probe_starting_point = AsyncMock(return_value=True)
        mock_client.get_default_starting_point_id = AsyncMock(return_value=DEFAULT_LOCATION_ID)
        yield mock_client


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
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = lambda: _ADMIN_USER
    app.dependency_overrides[get_current_user_via_http] = lambda: _ADMIN_USER
    app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-admin-token"
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def cross_service():
    """Mock every outbound call the approval flow makes, all successful."""
    with patch("crud.send_inventory_request", new_callable=AsyncMock) as inv, \
         patch("crud.send_skills_presets_request", new_callable=AsyncMock) as skills, \
         patch("crud.send_attributes_request", new_callable=AsyncMock) as attrs, \
         patch("crud.assign_character_to_user", new_callable=AsyncMock) as assign, \
         patch("main.send_character_approved_notification", new_callable=AsyncMock), \
         patch("main.publish_character_inventory", new_callable=AsyncMock), \
         patch("main.publish_character_skills", new_callable=AsyncMock), \
         patch("main.publish_character_attributes", new_callable=AsyncMock):
        inv.return_value = {"status": "ok"}
        skills.return_value = {"status": "ok"}
        attrs.return_value = {"id": 999}
        assign.return_value = True
        yield {"inventory": inv, "skills": skills, "attributes": attrs, "assign": assign}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_request(db, **overrides):
    fields = dict(
        user_id=42,
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
        status="pending",
        request_type="creation",
    )
    fields.update(overrides)
    req = models.CharacterRequest(**fields)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# ===========================================================================
# §3.6 — the fallback chain
# ===========================================================================

class TestStartLocationChain:
    def test_step1_valid_choice_is_used(self, db_session, client, locations, cross_service):
        req = _seed_request(db_session, start_location_id=CHOSEN_LOCATION_ID)
        locations.probe_starting_point.return_value = True

        response = client.post(f"/characters/requests/{req.id}/approve")
        assert response.status_code == 200
        body = response.json()
        assert body["current_location_id"] == CHOSEN_LOCATION_ID
        assert body["location_warning"] is None

        locations.probe_starting_point.assert_awaited_once_with(CHOSEN_LOCATION_ID)
        # No default lookup is needed when the player's own choice checks out.
        locations.get_default_starting_point_id.assert_not_awaited()

        character = db_session.query(models.Character).one()
        assert character.current_location_id == CHOSEN_LOCATION_ID

    def test_step2_invalid_choice_falls_back_to_the_default_point(
        self, db_session, client, locations, cross_service
    ):
        req = _seed_request(db_session, start_location_id=CHOSEN_LOCATION_ID)
        locations.probe_starting_point.return_value = False

        body = client.post(f"/characters/requests/{req.id}/approve").json()
        assert body["current_location_id"] == DEFAULT_LOCATION_ID
        assert body["location_warning"] == START_LOCATION_FALLBACK_WARNING

        character = db_session.query(models.Character).one()
        assert character.current_location_id == DEFAULT_LOCATION_ID

    def test_step2_no_choice_at_all_falls_back_to_the_default_point(
        self, db_session, client, locations, cross_service
    ):
        """No choice was ever made, so assigning the default is normal, not degradation.

        The moderator must not be told a point is «недоступна» when none was picked (N14).
        """
        req = _seed_request(db_session, start_location_id=None)

        body = client.post(f"/characters/requests/{req.id}/approve").json()
        assert body["current_location_id"] == DEFAULT_LOCATION_ID
        assert body["location_warning"] is None
        # Nothing to probe — the chain goes straight to the curated list.
        locations.probe_starting_point.assert_not_awaited()

    def test_step3_nothing_available_leaves_null_with_a_warning(
        self, db_session, client, locations, cross_service
    ):
        """No admin has flagged a starting point yet — status quo, not an error."""
        req = _seed_request(db_session, start_location_id=None)
        locations.get_default_starting_point_id.return_value = None

        response = client.post(f"/characters/requests/{req.id}/approve")
        assert response.status_code == 200
        body = response.json()
        assert body["current_location_id"] is None
        assert body["location_warning"] == START_LOCATION_UNASSIGNED_WARNING

        character = db_session.query(models.Character).one()
        assert character.current_location_id is None

    def test_step3_locations_service_down_still_approves(
        self, db_session, client, locations, cross_service
    ):
        """D8: the call is graceful — an outage must not fail the approval."""
        req = _seed_request(db_session, start_location_id=CHOSEN_LOCATION_ID)
        locations.probe_starting_point.side_effect = httpx.ConnectError("connection refused")

        response = client.post(f"/characters/requests/{req.id}/approve")
        assert response.status_code == 200
        body = response.json()
        assert body["current_location_id"] is None
        assert body["location_warning"] == START_LOCATION_UNASSIGNED_WARNING

        # The character exists, was committed, and is attached to its owner.
        character = db_session.query(models.Character).one()
        assert character.current_location_id is None
        assert character.user_id == 42
        db_session.refresh(req)
        assert req.status == "approved"

    def test_default_lookup_failure_is_also_graceful(
        self, db_session, client, locations, cross_service
    ):
        req = _seed_request(db_session, start_location_id=None)
        locations.get_default_starting_point_id.side_effect = httpx.ReadTimeout("timeout")

        response = client.post(f"/characters/requests/{req.id}/approve")
        assert response.status_code == 200
        assert response.json()["current_location_id"] is None
        assert response.json()["location_warning"] == START_LOCATION_UNASSIGNED_WARNING

    def test_unknown_probe_answer_falls_back_rather_than_trusting_it(
        self, db_session, client, locations, cross_service
    ):
        """probe returns None (service could not answer) -> do not use the id."""
        req = _seed_request(db_session, start_location_id=CHOSEN_LOCATION_ID)
        locations.probe_starting_point.return_value = None

        body = client.post(f"/characters/requests/{req.id}/approve").json()
        assert body["current_location_id"] == DEFAULT_LOCATION_ID
        assert body["location_warning"] == START_LOCATION_FALLBACK_WARNING

    def test_response_always_carries_both_location_keys(
        self, db_session, client, locations, cross_service
    ):
        req = _seed_request(db_session, start_location_id=CHOSEN_LOCATION_ID)
        body = client.post(f"/characters/requests/{req.id}/approve").json()
        assert {"message", "current_location_id", "location_warning"} <= set(body.keys())


# ===========================================================================
# Passport fields written at approval time
# ===========================================================================

class TestApprovalPassportFields:
    def test_registered_at_is_stamped(self, db_session, client, locations, cross_service):
        """Rule 22 — the system registration date, distinct from the in-game tenure."""
        req = _seed_request(db_session)

        assert client.post(f"/characters/requests/{req.id}/approve").status_code == 200
        character = db_session.query(models.Character).one()
        assert character.registered_at is not None

    def test_origin_and_tenure_are_copied_from_the_request(
        self, db_session, client, locations, cross_service
    ):
        req = _seed_request(
            db_session, origin_id=7, skitaltsy_since_year=1783, skitaltsy_since_segment=2
        )

        assert client.post(f"/characters/requests/{req.id}/approve").status_code == 200
        character = db_session.query(models.Character).one()
        assert character.origin_id == 7
        assert character.skitaltsy_since_year == 1783
        assert character.skitaltsy_since_segment == 2

    def test_missing_passport_fields_stay_null(self, db_session, client, locations, cross_service):
        req = _seed_request(db_session, origin_id=None, skitaltsy_since_year=None)

        assert client.post(f"/characters/requests/{req.id}/approve").status_code == 200
        character = db_session.query(models.Character).one()
        assert character.origin_id is None
        assert character.skitaltsy_since_year is None


class TestAvatarFallback:
    def test_request_avatar_wins(self, db_session, client, locations, cross_service):
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.image = "https://example.com/subrace.webp"
        db_session.commit()
        req = _seed_request(db_session, avatar="https://example.com/mine.webp")

        assert client.post(f"/characters/requests/{req.id}/approve").status_code == 200
        assert db_session.query(models.Character).one().avatar == "https://example.com/mine.webp"

    def test_subrace_image_is_used_when_no_avatar_was_uploaded(
        self, db_session, client, locations, cross_service
    ):
        """D5 — characters.avatar is NOT NULL, the request avatar is optional."""
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.image = "https://example.com/subrace.webp"
        db_session.commit()
        req = _seed_request(db_session, avatar=None)

        assert client.post(f"/characters/requests/{req.id}/approve").status_code == 200
        assert db_session.query(models.Character).one().avatar == "https://example.com/subrace.webp"

    def test_empty_string_when_neither_is_available(
        self, db_session, client, locations, cross_service
    ):
        req = _seed_request(db_session, avatar=None)

        assert client.post(f"/characters/requests/{req.id}/approve").status_code == 200
        assert db_session.query(models.Character).one().avatar == ""
