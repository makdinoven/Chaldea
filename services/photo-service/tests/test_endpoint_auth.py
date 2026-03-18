"""
Tests for JWT authentication and ownership checks on photo-service endpoints.

Covers:
- DELETE /photo/delete_user_avatar_photo

Each endpoint is tested for:
1. 401 without token
2. 403 with wrong user_id (ownership violation)
3. Success with correct auth
"""

from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


AUTH_HEADERS = {"Authorization": "Bearer valid-token"}
USER_1 = {"id": 1, "username": "testuser", "role": "user"}
USER_999 = {"id": 999, "username": "otheruser", "role": "user"}


# ===========================================================================
# DELETE /photo/delete_user_avatar_photo
# ===========================================================================

class TestDeleteUserAvatarAuth:
    """Auth tests for DELETE /photo/delete_user_avatar_photo."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.delete("/photo/delete_user_avatar_photo", params={"user_id": 1})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        """User-service returns 401 for bad token -> 401."""
        mock_auth.return_value = _mock_response(401)

        response = client.delete(
            "/photo/delete_user_avatar_photo",
            params={"user_id": 1},
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_user_returns_403(self, mock_auth, client):
        """Authenticated as user 999, trying to delete avatar for user 1 -> 403."""
        mock_auth.return_value = _mock_response(200, USER_999)

        response = client.delete(
            "/photo/delete_user_avatar_photo",
            params={"user_id": 1},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 403
        assert "свой" in response.json()["detail"].lower() or "аватар" in response.json()["detail"].lower()

    @patch("main.delete_s3_file")
    @patch("main.get_user_avatar", return_value="https://s3.example.com/avatar.webp")
    @patch("main.update_user_avatar")
    @patch("auth_http.requests.get")
    def test_correct_user_returns_200(self, mock_auth, mock_update, mock_get_avatar, mock_delete_s3, client):
        """Authenticated as user 1, deleting own avatar -> 200."""
        mock_auth.return_value = _mock_response(200, USER_1)

        response = client.delete(
            "/photo/delete_user_avatar_photo",
            params={"user_id": 1},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Фото успешно удалено"
