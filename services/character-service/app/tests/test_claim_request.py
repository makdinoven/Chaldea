"""
Tests for character claim functionality (FEAT-058).

Covers:
1. POST /characters/requests/claim — success and all error cases
2. GET /characters/my-character-count — returns correct count and limit
3. GET /characters/list — username enrichment via user-service
4. Claim approval flow — character gets user_id set on approve
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock, MagicMock
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_character_mock(
    character_id=10,
    user_id=None,
    is_npc=False,
    name="Артемис",
    id_subrace=1,
    id_race=1,
    id_class=1,
):
    """Create a mock Character ORM object."""
    char = MagicMock()
    char.id = character_id
    char.user_id = user_id
    char.is_npc = is_npc
    char.name = name
    char.id_subrace = id_subrace
    char.id_race = id_race
    char.id_class = id_class
    char.biography = "Биография"
    char.personality = "Характер"
    char.appearance = "Внешность"
    char.background = "Предыстория"
    char.sex = "male"
    char.age = 25
    char.weight = "80"
    char.height = "180"
    char.avatar = "https://example.com/avatar.webp"
    char.level = 5
    char.current_title_id = None
    char.stat_points = 0
    char.current_location_id = None
    char.npc_role = None
    return char


def _make_claim_request_mock(
    request_id=1,
    user_id=7,
    character_id=10,
    status="pending",
    request_type="claim",
    name="Артемис",
):
    """Create a mock CharacterRequest ORM object for a claim."""
    req = MagicMock()
    req.id = request_id
    req.user_id = user_id
    req.character_id = character_id
    req.status = status
    req.request_type = request_type
    req.name = name
    req.id_subrace = 1
    req.id_race = 1
    req.id_class = 1
    req.biography = "Биография"
    req.personality = "Характер"
    req.appearance = "Внешность"
    req.background = "Предыстория"
    req.sex = "male"
    req.age = 25
    req.weight = "80"
    req.height = "180"
    req.avatar = "https://example.com/avatar.webp"
    req.created_at = "2026-03-22T12:00:00"
    return req


# ===========================================================================
# POST /characters/requests/claim
# ===========================================================================

class TestClaimRequestSuccess:
    """Successful claim request creation."""

    def test_claim_success(self, admin_mock_client, mock_db_session):
        """Create a claim for an unowned, non-NPC character — returns 200."""
        character = _make_character_mock(character_id=15, user_id=None, is_npc=False)

        # db.query(Character).filter(...).first() returns the character
        # db.query(CharacterRequest).filter(...).first() returns None (no dup)
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            character,  # Step 1: find character
            None,       # Step 5: no existing pending claim
        ]

        # Character count check (step 4) — user has 2 characters
        mock_db_session.execute.return_value.scalar.return_value = 2

        # db.refresh(obj) must populate fields that DB would normally set
        def fake_refresh(obj):
            if getattr(obj, 'id', None) is None:
                obj.id = 42
            if getattr(obj, 'status', None) is None:
                obj.status = 'pending'
        mock_db_session.refresh.side_effect = fake_refresh

        response = admin_mock_client.post(
            "/characters/requests/claim",
            json={"character_id": 15},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == 15
        assert data["user_id"] == 1  # admin user from conftest
        assert data["status"] == "pending"
        assert data["request_type"] == "claim"
        assert data["name"] == "Артемис"

    def test_claim_creates_request_in_db(self, admin_mock_client, mock_db_session):
        """Verify db.add() and db.commit() are called on success."""
        character = _make_character_mock(character_id=15)

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            character,
            None,
        ]
        mock_db_session.execute.return_value.scalar.return_value = 0

        # db.refresh(obj) must populate fields that DB would normally set
        def fake_refresh(obj):
            if getattr(obj, 'id', None) is None:
                obj.id = 42
            if getattr(obj, 'status', None) is None:
                obj.status = 'pending'
        mock_db_session.refresh.side_effect = fake_refresh

        response = admin_mock_client.post(
            "/characters/requests/claim",
            json={"character_id": 15},
        )

        assert response.status_code == 200
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()


class TestClaimRequestCharacterNotFound:
    """Character not found — returns 404."""

    def test_character_not_found(self, admin_mock_client, mock_db_session):
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = admin_mock_client.post(
            "/characters/requests/claim",
            json={"character_id": 9999},
        )

        assert response.status_code == 404
        assert "не найден" in response.json()["detail"].lower()


class TestClaimRequestCharacterHasOwner:
    """Character already has an owner — returns 400."""

    def test_character_has_owner(self, admin_mock_client, mock_db_session):
        character = _make_character_mock(character_id=15, user_id=42)
        mock_db_session.query.return_value.filter.return_value.first.return_value = character

        response = admin_mock_client.post(
            "/characters/requests/claim",
            json={"character_id": 15},
        )

        assert response.status_code == 400
        assert "принадлежит" in response.json()["detail"].lower()


class TestClaimRequestCharacterIsNpc:
    """Character is NPC — returns 400."""

    def test_character_is_npc(self, admin_mock_client, mock_db_session):
        character = _make_character_mock(character_id=15, is_npc=True)
        mock_db_session.query.return_value.filter.return_value.first.return_value = character

        response = admin_mock_client.post(
            "/characters/requests/claim",
            json={"character_id": 15},
        )

        assert response.status_code == 400
        assert "npc" in response.json()["detail"].lower()


class TestClaimRequestUserAtLimit:
    """User already has 5 characters — returns 400."""

    def test_user_at_character_limit(self, admin_mock_client, mock_db_session):
        character = _make_character_mock(character_id=15)
        mock_db_session.query.return_value.filter.return_value.first.return_value = character

        # User has 5 characters already
        mock_db_session.execute.return_value.scalar.return_value = 5

        response = admin_mock_client.post(
            "/characters/requests/claim",
            json={"character_id": 15},
        )

        assert response.status_code == 400
        assert "лимит" in response.json()["detail"].lower()


class TestClaimRequestDuplicatePending:
    """User already has a pending claim for the same character — returns 409."""

    def test_duplicate_pending_claim(self, admin_mock_client, mock_db_session):
        character = _make_character_mock(character_id=15)
        existing_claim = _make_claim_request_mock(user_id=1, character_id=15)

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            character,        # Step 1: find character
            existing_claim,   # Step 5: existing pending claim found
        ]
        mock_db_session.execute.return_value.scalar.return_value = 2

        response = admin_mock_client.post(
            "/characters/requests/claim",
            json={"character_id": 15},
        )

        assert response.status_code == 409
        assert "уже подали" in response.json()["detail"].lower()


class TestClaimRequestAuth:
    """Claim endpoint requires authentication."""

    def test_unauthenticated_returns_error(self, client):
        """Without auth, should get 401 or similar."""
        response = client.post(
            "/characters/requests/claim",
            json={"character_id": 15},
        )
        assert response.status_code in (401, 403, 422)


# ===========================================================================
# GET /characters/my-character-count
# ===========================================================================

class TestMyCharacterCount:
    """GET /characters/my-character-count returns correct count and limit."""

    def test_returns_count_and_limit(self, admin_mock_client, mock_db_session):
        mock_db_session.execute.return_value.scalar.return_value = 3

        response = admin_mock_client.get("/characters/my-character-count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert data["limit"] == 5

    def test_returns_zero_when_no_characters(self, admin_mock_client, mock_db_session):
        mock_db_session.execute.return_value.scalar.return_value = 0

        response = admin_mock_client.get("/characters/my-character-count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["limit"] == 5

    def test_unauthenticated_returns_error(self, client):
        """Character count endpoint requires auth."""
        response = client.get("/characters/my-character-count")
        assert response.status_code in (401, 403, 422)


# ===========================================================================
# GET /characters/list — username enrichment
# ===========================================================================

class TestListUsernameEnrichment:
    """GET /characters/list enriches response with username from user-service."""

    @patch("main.httpx.get")
    def test_character_with_owner_has_username(
        self, mock_httpx_get, admin_mock_client, mock_db_session
    ):
        """Characters with user_id should have username in response."""
        character = _make_character_mock(character_id=1, user_id=42)
        race = MagicMock()
        race.name = "Человек"
        cls = MagicMock()
        cls.name = "Воин"
        subrace = MagicMock()
        subrace.name = "Норд"

        # query.count() returns total
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [character]

        # For race/class/subrace lookups, return the mocks
        def query_side_effect(model):
            q = MagicMock()
            if model.__tablename__ == "characters":
                return mock_query
            elif model.__tablename__ == "races":
                q.filter.return_value.first.return_value = race
            elif model.__tablename__ == "classes":
                q.filter.return_value.first.return_value = cls
            elif model.__tablename__ == "subraces":
                q.filter.return_value.first.return_value = subrace
            return q

        mock_db_session.query.side_effect = query_side_effect

        # Mock httpx.get for user-service
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"username": "PlayerOne"}
        mock_httpx_get.return_value = mock_resp

        response = admin_mock_client.get("/characters/list")

        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["username"] == "PlayerOne"
        assert items[0]["user_id"] == 42

    @patch("main.httpx.get")
    def test_character_without_owner_has_null_username(
        self, mock_httpx_get, admin_mock_client, mock_db_session
    ):
        """Characters without user_id should have username=null."""
        character = _make_character_mock(character_id=2, user_id=None)
        race = MagicMock()
        race.name = "Эльф"
        cls = MagicMock()
        cls.name = "Маг"
        subrace = MagicMock()
        subrace.name = "Лесной"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [character]

        def query_side_effect(model):
            q = MagicMock()
            if model.__tablename__ == "characters":
                return mock_query
            elif model.__tablename__ == "races":
                q.filter.return_value.first.return_value = race
            elif model.__tablename__ == "classes":
                q.filter.return_value.first.return_value = cls
            elif model.__tablename__ == "subraces":
                q.filter.return_value.first.return_value = subrace
            return q

        mock_db_session.query.side_effect = query_side_effect

        response = admin_mock_client.get("/characters/list")

        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["username"] is None
        assert items[0]["user_id"] is None

        # httpx.get should NOT have been called (no user_ids to resolve)
        mock_httpx_get.assert_not_called()

    @patch("main.httpx.get")
    def test_username_fetch_failure_returns_null(
        self, mock_httpx_get, admin_mock_client, mock_db_session
    ):
        """When user-service is down, username should be null (graceful)."""
        character = _make_character_mock(character_id=3, user_id=99)
        race = MagicMock()
        race.name = "Дворф"
        cls = MagicMock()
        cls.name = "Воин"
        subrace = MagicMock()
        subrace.name = "Золотой"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [character]

        def query_side_effect(model):
            q = MagicMock()
            if model.__tablename__ == "characters":
                return mock_query
            elif model.__tablename__ == "races":
                q.filter.return_value.first.return_value = race
            elif model.__tablename__ == "classes":
                q.filter.return_value.first.return_value = cls
            elif model.__tablename__ == "subraces":
                q.filter.return_value.first.return_value = subrace
            return q

        mock_db_session.query.side_effect = query_side_effect

        # Simulate user-service failure
        mock_httpx_get.side_effect = Exception("Connection refused")

        response = admin_mock_client.get("/characters/list")

        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        # Username should be None because lookup failed gracefully
        assert items[0]["username"] is None


# ===========================================================================
# Claim Approval Flow
# ===========================================================================

class TestClaimApprovalFlow:
    """Approve a claim request — character gets user_id assigned."""

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.crud")
    def test_claim_approval_sets_user_id_on_character(
        self,
        mock_crud,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """Approving a claim sets user_id on the existing character."""
        claim_request = _make_claim_request_mock(
            request_id=5, user_id=7, character_id=10
        )
        character = _make_character_mock(character_id=10, user_id=None)

        # First query: find the request; second query: find the character
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            claim_request,  # Step 1: find request
            character,      # Claim branch: find character
        ]

        # Character count check — user has 2 characters
        mock_db_session.execute.return_value.scalar.return_value = 2

        mock_crud.update_character_request_status.return_value = claim_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/5/approve")

        assert response.status_code == 200
        # Character's user_id should have been set
        assert character.user_id == 7
        # db.commit() should have been called
        mock_db_session.commit.assert_called()

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.crud")
    def test_claim_approval_calls_assign_character_to_user(
        self,
        mock_crud,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """Claim approval calls assign_character_to_user with correct args."""
        claim_request = _make_claim_request_mock(
            request_id=5, user_id=7, character_id=10
        )
        character = _make_character_mock(character_id=10, user_id=None)

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            claim_request,
            character,
        ]
        mock_db_session.execute.return_value.scalar.return_value = 1

        mock_crud.update_character_request_status.return_value = claim_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/5/approve")

        assert response.status_code == 200
        mock_crud.assign_character_to_user.assert_called_once()
        call_args = mock_crud.assign_character_to_user.call_args
        assert call_args[0][0] == 7   # user_id
        assert call_args[0][1] == 10  # character_id

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.crud")
    def test_claim_approval_rollback_on_assign_failure(
        self,
        mock_crud,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """If assign_character_to_user fails, rollback should be called."""
        claim_request = _make_claim_request_mock(
            request_id=5, user_id=7, character_id=10
        )
        character = _make_character_mock(character_id=10, user_id=None)

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            claim_request,
            character,
        ]
        mock_db_session.execute.return_value.scalar.return_value = 1

        mock_crud.update_character_request_status.return_value = claim_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=False)

        response = admin_mock_client.post("/characters/requests/5/approve")

        assert response.status_code == 500
        mock_db_session.rollback.assert_called()
        mock_db_session.commit.assert_not_called()

    @patch("main.crud")
    def test_claim_approval_character_already_owned_returns_400(
        self,
        mock_crud,
        admin_mock_client,
        mock_db_session,
    ):
        """If the character was claimed by someone else between request and approval."""
        claim_request = _make_claim_request_mock(
            request_id=5, user_id=7, character_id=10
        )
        # Character now has an owner (race condition)
        character = _make_character_mock(character_id=10, user_id=99)

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            claim_request,
            character,
        ]
        mock_db_session.execute.return_value.scalar.return_value = 1

        response = admin_mock_client.post("/characters/requests/5/approve")

        assert response.status_code == 400
        assert "принадлежит" in response.json()["detail"].lower()

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.crud")
    def test_claim_approval_sends_notification(
        self,
        mock_crud,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """After successful claim approval, notification is sent."""
        claim_request = _make_claim_request_mock(
            request_id=5, user_id=7, character_id=10
        )
        character = _make_character_mock(character_id=10, user_id=None)

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            claim_request,
            character,
        ]
        mock_db_session.execute.return_value.scalar.return_value = 0

        mock_crud.update_character_request_status.return_value = claim_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/5/approve")

        assert response.status_code == 200
        mock_notif.assert_called_once_with(7, "Артемис")
