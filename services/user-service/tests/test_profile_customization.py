"""
FEAT-030 Task #7 — Tests for profile customization endpoints.

Covers:
1. PUT /users/me/settings — update profile settings (colors, frame, status)
2. PUT /users/me/username — change username with validation
3. GET /users/{user_id}/characters — list user characters (mocked)
4. GET /users/{user_id}/profile — verify new customization fields in response
"""

from unittest.mock import patch, AsyncMock

import pytest

from crud import create_user
from schemas import UserCreate
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, username="player1", email="player1@test.com", password="Pass1234"):
    """Create a user via CRUD and return the ORM object."""
    return create_user(db, UserCreate(email=email, username=username, password=password))


def _auth_header(user):
    """Build an Authorization header with a valid JWT for the given user."""
    from auth import create_access_token
    token = create_access_token(data={"sub": user.email}, role=user.role)
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# 1. PUT /users/me/settings
# ===========================================================================

class TestUpdateProfileSettings:

    def test_update_profile_settings_success(self, client, db_session):
        """Update all customization fields and verify the response."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        # Seed a default frame so validation passes
        db_session.add(models.CosmeticFrame(
            name="Золотое свечение", slug="gold", type="css",
            css_class="frame-gold", rarity="common", is_default=True,
        ))
        db_session.commit()

        payload = {
            "profile_bg_color": "#1a1a2e",
            "nickname_color": "#fff",
            "avatar_frame": "gold",
            "avatar_effect_color": "#ff0000",
            "status_text": "Hello World!",
        }
        resp = client.put("/users/me/settings", json=payload, headers=headers)
        assert resp.status_code == 200

        data = resp.json()
        assert data["profile_bg_color"] == "#1a1a2e"
        assert data["nickname_color"] == "#fff"
        assert data["avatar_frame"] == "gold"
        assert data["avatar_effect_color"] == "#ff0000"
        assert data["status_text"] == "Hello World!"

    def test_update_settings_partial(self, client, db_session):
        """Updating only some fields should work (exclude_unset behavior)."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put("/users/me/settings", json={"nickname_color": "#abc"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["nickname_color"] == "#abc"

    def test_update_settings_invalid_hex_color(self, client, db_session):
        """Invalid hex color format should return 422."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_bg_color": "not-a-color"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_update_settings_invalid_hex_color_missing_hash(self, client, db_session):
        """Hex color without '#' prefix should be rejected."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"nickname_color": "ff0000"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_update_settings_invalid_frame(self, client, db_session):
        """Unknown frame name should return 422."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"avatar_frame": "diamond"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_update_settings_status_too_long(self, client, db_session):
        """Status text longer than 100 chars should return 422."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        long_status = "A" * 101
        resp = client.put(
            "/users/me/settings",
            json={"status_text": long_status},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_update_settings_status_exactly_100(self, client, db_session):
        """Status text of exactly 100 chars should be accepted."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        status_100 = "A" * 100
        resp = client.put(
            "/users/me/settings",
            json={"status_text": status_100},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status_text"] == status_100

    def test_update_settings_unauthenticated(self, client, db_session):
        """No token should return 401."""
        resp = client.put("/users/me/settings", json={"nickname_color": "#fff"})
        assert resp.status_code == 401

    def test_update_settings_xss_in_status(self, client, db_session):
        """XSS attempt in status_text should be sanitized (bleach strips tags)."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"status_text": '<script>alert("xss")</script>Hello'},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "<script>" not in data["status_text"]
        assert "Hello" in data["status_text"]


# ===========================================================================
# 2. PUT /users/me/username
# ===========================================================================

class TestUpdateUsername:

    def test_update_username_success(self, client, db_session):
        """Change username to a new unique name."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/username",
            json={"username": "new_name"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "new_name"
        assert data["id"] == user.id
        assert "message" in data

    def test_update_username_cyrillic(self, client, db_session):
        """Cyrillic usernames should be accepted."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/username",
            json={"username": "Игрок"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "Игрок"

    def test_update_username_duplicate(self, client, db_session):
        """Trying to take an existing username should return 400."""
        _make_user(db_session, "existing_user", "existing@test.com")
        user2 = _make_user(db_session, "user2", "user2@test.com")
        headers = _auth_header(user2)

        resp = client.put(
            "/users/me/username",
            json={"username": "existing_user"},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_update_username_empty(self, client, db_session):
        """Empty username should return 400."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/username",
            json={"username": ""},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_update_username_whitespace_only(self, client, db_session):
        """Whitespace-only username should return 400 (stripped to empty)."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/username",
            json={"username": "   "},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_update_username_too_long(self, client, db_session):
        """Username longer than 32 chars should return 400."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        long_name = "a" * 33
        resp = client.put(
            "/users/me/username",
            json={"username": long_name},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_update_username_invalid_chars(self, client, db_session):
        """Special chars like @#$ should be rejected with 400."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        for bad_name in ["user@name", "user#1", "user$money", "hello world"]:
            resp = client.put(
                "/users/me/username",
                json={"username": bad_name},
                headers=headers,
            )
            assert resp.status_code == 400, f"Expected 400 for '{bad_name}', got {resp.status_code}"

    def test_update_username_unauthenticated(self, client, db_session):
        """No token should return 401."""
        resp = client.put("/users/me/username", json={"username": "newname"})
        assert resp.status_code == 401

    def test_update_username_same_name(self, client, db_session):
        """Updating to the same current name should succeed (no conflict)."""
        user = _make_user(db_session, "samename", "same@test.com")
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/username",
            json={"username": "samename"},
            headers=headers,
        )
        assert resp.status_code == 200

    def test_update_username_sql_injection(self, client, db_session):
        """SQL injection attempts should not crash the service."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        # The username regex should reject this, returning 400
        resp = client.put(
            "/users/me/username",
            json={"username": "'; DROP TABLE users; --"},
            headers=headers,
        )
        assert resp.status_code == 400


# ===========================================================================
# 3. GET /users/{user_id}/characters
# ===========================================================================

class TestGetUserCharacters:

    @patch("main._fetch_character_short", new_callable=AsyncMock)
    def test_get_user_characters_success(self, mock_fetch, client, db_session):
        """Mock character-service response and verify character list."""
        user = _make_user(db_session)

        # Create user-character relation
        rel = models.UserCharacter(user_id=user.id, character_id=10)
        db_session.add(rel)
        db_session.commit()

        mock_fetch.return_value = {
            "id": 10,
            "name": "TestChar",
            "avatar": "/avatars/char.png",
            "level": 5,
            "current_location": None,
        }

        resp = client.get(f"/users/{user.id}/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["characters"]) == 1
        char = data["characters"][0]
        assert char["id"] == 10
        assert char["name"] == "TestChar"
        assert char["level"] == 5
        assert char["rp_posts_count"] == 0
        assert char["last_rp_post_date"] is None

    def test_get_user_characters_empty(self, client, db_session):
        """User with no characters should return empty list."""
        user = _make_user(db_session)

        resp = client.get(f"/users/{user.id}/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert data["characters"] == []

    def test_get_user_characters_nonexistent_user(self, client, db_session):
        """Non-existent user should return 404."""
        resp = client.get("/users/99999/characters")
        assert resp.status_code == 404

    @patch("main._fetch_character_short", new_callable=AsyncMock)
    def test_get_user_characters_multiple(self, mock_fetch, client, db_session):
        """Multiple characters should all be returned."""
        user = _make_user(db_session)

        for cid in [10, 20, 30]:
            rel = models.UserCharacter(user_id=user.id, character_id=cid)
            db_session.add(rel)
        db_session.commit()

        async def side_effect(char_id):
            return {
                "id": char_id,
                "name": f"Char{char_id}",
                "avatar": f"/avatars/{char_id}.png",
                "level": char_id // 10,
                "current_location": None,
            }

        mock_fetch.side_effect = side_effect

        resp = client.get(f"/users/{user.id}/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["characters"]) == 3

    @patch("main._fetch_character_short", new_callable=AsyncMock)
    def test_get_user_characters_service_failure(self, mock_fetch, client, db_session):
        """If character-service returns None, that character is skipped."""
        user = _make_user(db_session)

        rel = models.UserCharacter(user_id=user.id, character_id=10)
        db_session.add(rel)
        db_session.commit()

        mock_fetch.return_value = None  # Simulates service failure

        resp = client.get(f"/users/{user.id}/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert data["characters"] == []


# ===========================================================================
# 4. GET /users/{user_id}/profile — customization fields
# ===========================================================================

class TestProfileIncludesCustomizationFields:

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_profile_includes_customization_fields(self, mock_fetch, client, db_session):
        """Verify new customization fields are present in profile response."""
        user = _make_user(db_session)

        # Set some customization values
        db_user = db_session.query(models.User).filter(models.User.id == user.id).first()
        db_user.profile_bg_color = "#1a1a2e"
        db_user.nickname_color = "#ffffff"
        db_user.avatar_frame = "gold"
        db_user.avatar_effect_color = "#ff0000"
        db_user.status_text = "Test status"
        db_user.profile_bg_image = "https://s3.example.com/bg.webp"
        db_session.commit()

        resp = client.get(f"/users/{user.id}/profile")
        assert resp.status_code == 200
        data = resp.json()

        assert data["profile_bg_color"] == "#1a1a2e"
        assert data["profile_bg_image"] == "https://s3.example.com/bg.webp"
        assert data["nickname_color"] == "#ffffff"
        assert data["avatar_frame"] == "gold"
        assert data["avatar_effect_color"] == "#ff0000"
        assert data["status_text"] == "Test status"

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_profile_customization_defaults_null(self, mock_fetch, client, db_session):
        """New user should have null customization fields."""
        user = _make_user(db_session)

        resp = client.get(f"/users/{user.id}/profile")
        assert resp.status_code == 200
        data = resp.json()

        assert data["profile_bg_color"] is None
        assert data["profile_bg_image"] is None
        assert data["nickname_color"] is None
        assert data["avatar_frame"] is None
        assert data["avatar_effect_color"] is None
        assert data["status_text"] is None

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_profile_nonexistent_user(self, mock_fetch, client, db_session):
        """Non-existent user profile should return 404."""
        resp = client.get("/users/99999/profile")
        assert resp.status_code == 404
