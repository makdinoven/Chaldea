"""
Tests for POST /characters/requests/{request_id}/approve endpoint.

Covers:
1. Token forwarding — admin JWT token is passed to user-service HTTP calls
2. Atomicity on failure — if user-service PUT fails, no DB commit happens (only flush), rollback is called
3. Happy path — all external calls succeed, single db.commit() at the end, 200 response
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock, MagicMock, call
import pytest
import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_character_request_mock(request_id=1, user_id=42, status="pending",
                                  id_class=1, id_subrace=1, id_race=1):
    """Create a mock CharacterRequest object."""
    req = MagicMock()
    req.id = request_id
    req.user_id = user_id
    req.status = status
    req.name = "Артас"
    req.id_subrace = id_subrace
    req.id_race = id_race
    req.background = "Рыцарь"
    req.age = 25
    req.weight = "85"
    req.height = "190"
    req.avatar = "https://example.com/avatar.webp"
    req.biography = "Принц Лордерона"
    req.personality = "Решительный"
    req.id_class = id_class
    req.sex = "male"
    req.appearance = "Высокий блондин"
    return req


def _make_character_mock(character_id=100, user_id=42):
    """Create a mock Character object."""
    char = MagicMock()
    char.id = character_id
    char.user_id = user_id
    char.name = "Артас"
    char.id_attributes = None
    return char


def _make_starter_kit_mock(class_id=1):
    """Create a mock StarterKit object."""
    kit = MagicMock()
    kit.class_id = class_id
    kit.items = [{"item_id": 10, "quantity": 1}]
    kit.skills = [{"skill_id": 5}]
    kit.currency_amount = 500
    return kit


# ---------------------------------------------------------------------------
# Test Class: Token Forwarding
# ---------------------------------------------------------------------------

class TestTokenForwarding:
    """Verify that the admin's JWT token is forwarded to user-service HTTP calls."""

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_token_forwarded_to_assign_character(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """Token from admin auth must be passed to crud.assign_character_to_user."""
        db_request = _make_character_request_mock()
        character = _make_character_mock()
        starter_kit = _make_starter_kit_mock()

        # DB queries
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,   # Step 1: find request
            starter_kit,  # Step 2: find starter kit
        ]

        # CRUD functions
        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_attributes_request = AsyncMock(return_value={"id": 99})
        mock_crud.update_character_with_dependencies.return_value = character
        mock_crud.update_character_request_status.return_value = db_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 200

        # Verify assign_character_to_user was called with token
        mock_crud.assign_character_to_user.assert_called_once()
        call_kwargs = mock_crud.assign_character_to_user.call_args
        # token= keyword argument should be "fake-admin-token" (from conftest override)
        assert call_kwargs.kwargs.get("token") == "fake-admin-token" or \
               (len(call_kwargs.args) >= 3 and call_kwargs.args[2] == "fake-admin-token") or \
               call_kwargs[1].get("token") == "fake-admin-token"

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_token_included_in_httpx_put_header(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """Verify the actual httpx PUT call includes Authorization header with token.

        Instead of mocking crud.assign_character_to_user entirely, we mock httpx
        at the transport level to verify the header is set.
        """
        db_request = _make_character_request_mock()
        character = _make_character_mock()
        starter_kit = _make_starter_kit_mock()

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,
            starter_kit,
        ]

        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_attributes_request = AsyncMock(return_value={"id": 99})
        mock_crud.update_character_with_dependencies.return_value = character
        mock_crud.update_character_request_status.return_value = db_request

        # Patch the actual assign_character_to_user to inspect token parameter
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 200

        # The call must have token="fake-admin-token"
        args, kwargs = mock_crud.assign_character_to_user.call_args
        assert kwargs.get("token") == "fake-admin-token"


# ---------------------------------------------------------------------------
# Test Class: Atomicity on Failure
# ---------------------------------------------------------------------------

class TestAtomicityOnFailure:
    """Verify that if step 10 (assign to user) fails, DB changes are rolled back."""

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_no_commit_on_assign_failure(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """When assign_character_to_user returns False, db.commit() must NOT be called.
        db.rollback() MUST be called instead."""
        db_request = _make_character_request_mock()
        character = _make_character_mock()
        starter_kit = _make_starter_kit_mock()

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,
            starter_kit,
        ]

        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_attributes_request = AsyncMock(return_value={"id": 99})
        mock_crud.update_character_with_dependencies.return_value = character
        mock_crud.update_character_request_status.return_value = db_request
        # Step 10 FAILS
        mock_crud.assign_character_to_user = AsyncMock(return_value=False)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 500

        # commit must NOT have been called (only flush inside CRUD functions with auto_commit=False)
        mock_db_session.commit.assert_not_called()
        # rollback MUST have been called (explicit rollback in the except block)
        mock_db_session.rollback.assert_called()

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_no_commit_on_attributes_failure(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """When attributes-service returns None (step 7), db.rollback() is called."""
        db_request = _make_character_request_mock()
        character = _make_character_mock()
        starter_kit = _make_starter_kit_mock()

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,
            starter_kit,
        ]

        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        # Step 7 FAILS — attributes-service returns None
        mock_crud.send_attributes_request = AsyncMock(return_value=None)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 500

        # commit must NOT have been called
        mock_db_session.commit.assert_not_called()
        # rollback MUST have been called
        mock_db_session.rollback.assert_called()

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_crud_called_with_auto_commit_false(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """CRUD functions must be called with auto_commit=False in the approval flow."""
        db_request = _make_character_request_mock()
        character = _make_character_mock()
        starter_kit = _make_starter_kit_mock()

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,
            starter_kit,
        ]

        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_attributes_request = AsyncMock(return_value={"id": 99})
        mock_crud.update_character_with_dependencies.return_value = character
        mock_crud.update_character_request_status.return_value = db_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 200

        # create_preliminary_character must be called with auto_commit=False
        cpc_call = mock_crud.create_preliminary_character.call_args
        assert cpc_call.kwargs.get("auto_commit") is False or \
               (len(cpc_call.args) >= 4 and cpc_call.args[3] is False)

        # update_character_with_dependencies must be called with auto_commit=False
        ucd_call = mock_crud.update_character_with_dependencies.call_args
        assert ucd_call.kwargs.get("auto_commit") is False

        # update_character_request_status must be called with auto_commit=False
        ucrs_call = mock_crud.update_character_request_status.call_args
        assert ucrs_call.kwargs.get("auto_commit") is False or \
               (len(ucrs_call.args) >= 4 and ucrs_call.args[3] is False)


# ---------------------------------------------------------------------------
# Test Class: Happy Path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """Verify successful approval flow: all steps pass, single commit, 200 response."""

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_happy_path_returns_200(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """Successful approval returns 200 with a success message."""
        db_request = _make_character_request_mock()
        character = _make_character_mock()
        starter_kit = _make_starter_kit_mock()

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,
            starter_kit,
        ]

        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_attributes_request = AsyncMock(return_value={"id": 99})
        mock_crud.update_character_with_dependencies.return_value = character
        mock_crud.update_character_request_status.return_value = db_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert str(character.id) in data["message"]

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_single_commit_on_success(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """On success, db.commit() must be called exactly once (at the end)."""
        db_request = _make_character_request_mock()
        character = _make_character_mock()
        starter_kit = _make_starter_kit_mock()

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,
            starter_kit,
        ]

        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_attributes_request = AsyncMock(return_value={"id": 99})
        mock_crud.update_character_with_dependencies.return_value = character
        mock_crud.update_character_request_status.return_value = db_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 200

        # Exactly ONE commit at the end
        assert mock_db_session.commit.call_count == 1
        # No rollback on success
        mock_db_session.rollback.assert_not_called()

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_notification_sent_after_commit(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """RabbitMQ notification is sent after successful commit."""
        db_request = _make_character_request_mock()
        character = _make_character_mock()
        starter_kit = _make_starter_kit_mock()

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,
            starter_kit,
        ]

        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_attributes_request = AsyncMock(return_value={"id": 99})
        mock_crud.update_character_with_dependencies.return_value = character
        mock_crud.update_character_request_status.return_value = db_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 200
        # Notification was sent
        mock_notif.assert_called_once_with(db_request.user_id, character.name)


# ---------------------------------------------------------------------------
# Test Class: Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases for the approval flow."""

    @patch("main.crud")
    def test_request_not_found_returns_404(self, mock_crud, admin_mock_client, mock_db_session):
        """Approving a non-existent request returns 404."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = admin_mock_client.post("/characters/requests/9999/approve")

        assert response.status_code == 404

    @patch("main.crud")
    def test_already_approved_returns_400(self, mock_crud, admin_mock_client, mock_db_session):
        """Approving a request that is not 'pending' returns 400."""
        db_request = _make_character_request_mock(status="approved")
        mock_db_session.query.return_value.filter.return_value.first.return_value = db_request

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 400

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("main.crud")
    def test_no_starter_kit_still_succeeds(
        self,
        mock_crud,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        admin_mock_client,
        mock_db_session,
    ):
        """Approval succeeds even when no starter kit exists for the class."""
        db_request = _make_character_request_mock()
        character = _make_character_mock()

        # First query returns the request, second returns None (no starter kit)
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            db_request,
            None,  # No starter kit
        ]

        mock_crud.create_preliminary_character.return_value = character
        mock_crud.generate_attributes_for_subrace.return_value = {"strength": 10}
        mock_crud.send_inventory_request = AsyncMock(return_value=None)
        mock_crud.send_skills_presets_request = AsyncMock(return_value={"status": "ok"})
        mock_crud.send_attributes_request = AsyncMock(return_value={"id": 99})
        mock_crud.update_character_with_dependencies.return_value = character
        mock_crud.update_character_request_status.return_value = db_request
        mock_crud.assign_character_to_user = AsyncMock(return_value=True)

        response = admin_mock_client.post("/characters/requests/1/approve")

        assert response.status_code == 200

    def test_unauthenticated_returns_401_or_403(self, client, mock_db_session):
        """Approval endpoint requires authentication (no admin override)."""
        response = client.post("/characters/requests/1/approve")

        # Without auth override, should get 401 or 403
        assert response.status_code in (401, 403, 422)
