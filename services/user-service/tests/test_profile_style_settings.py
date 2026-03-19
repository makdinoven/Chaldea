"""
FEAT-044 Task #11 — Tests for profile style settings (post_color, profile_style_settings, last_active_at).

Covers:
1. PUT /users/me/settings — post_color validation and persistence
2. PUT /users/me/settings — profile_style_settings JSON validation (types, ranges, size, unknown keys)
3. GET /users/{id}/profile — new fields in response
4. GET /users/{id}/friends — last_active_at in friend response
5. GET /users/{id}/characters — race/class fields passed through
"""

from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta

import pytest
import json

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
# 1. PUT /users/me/settings — post_color tests
# ===========================================================================

class TestPostColor:

    def test_valid_hex_color_saves(self, client, db_session):
        """Valid hex color for post_color should save correctly."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put("/users/me/settings", json={"post_color": "#1a1a2e"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["post_color"] == "#1a1a2e"

    def test_valid_short_hex_color_saves(self, client, db_session):
        """3-char hex color for post_color should save correctly."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put("/users/me/settings", json={"post_color": "#fff"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["post_color"] == "#fff"

    def test_invalid_hex_color_rejected(self, client, db_session):
        """Invalid hex string for post_color should return 422."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put("/users/me/settings", json={"post_color": "not-a-color"}, headers=headers)
        assert resp.status_code == 422

    def test_hex_without_hash_rejected(self, client, db_session):
        """Hex color without '#' prefix should be rejected."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put("/users/me/settings", json={"post_color": "ff0000"}, headers=headers)
        assert resp.status_code == 422

    def test_null_resets_field(self, client, db_session):
        """Setting post_color to null should reset the field."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        # First set a color
        client.put("/users/me/settings", json={"post_color": "#aabbcc"}, headers=headers)

        # Then reset to null
        resp = client.put("/users/me/settings", json={"post_color": None}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["post_color"] is None

    def test_sql_injection_in_post_color(self, client, db_session):
        """SQL injection attempt in post_color should be rejected, not crash."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"post_color": "'; DROP TABLE users; --"},
            headers=headers,
        )
        assert resp.status_code == 422


# ===========================================================================
# 2. PUT /users/me/settings — profile_style_settings tests
# ===========================================================================

class TestProfileStyleSettings:

    def test_valid_json_all_fields(self, client, db_session):
        """Valid JSON with all known fields should save correctly."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        settings = {
            "post_color_opacity": 0.8,
            "post_color_blur": 5.0,
            "post_color_glow": 3.0,
            "post_color_saturation": 1.5,
            "bg_color_opacity": 0.6,
            "bg_color_blur": 10.0,
            "bg_color_glow": 2.0,
            "bg_color_saturation": 1.0,
            "avatar_effect_opacity": 1.0,
            "avatar_effect_blur": 0.0,
            "avatar_effect_glow": 5.0,
            "avatar_effect_saturation": 0.5,
            "nickname_brightness": 1.2,
            "nickname_contrast": 1.5,
            "nickname_gradient_angle": 90,
            "nickname_shimmer": True,
            "text_shadow_enabled": True,
            "text_backdrop_enabled": False,
            "nickname_color_2": "#ff00ff",
        }

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": settings},
            headers=headers,
        )
        assert resp.status_code == 200

        data = resp.json()["profile_style_settings"]
        assert data is not None
        assert data["post_color_opacity"] == 0.8
        assert data["nickname_shimmer"] is True
        assert data["nickname_color_2"] == "#ff00ff"
        assert data["nickname_gradient_angle"] == 90

    def test_float_clamped_above_max(self, client, db_session):
        """Float values above max should be clamped to max."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {
                "post_color_opacity": 5.0,   # max is 1.0
                "post_color_blur": 100.0,     # max is 20.0
            }},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["profile_style_settings"]
        assert data["post_color_opacity"] == 1.0
        assert data["post_color_blur"] == 20.0

    def test_float_clamped_below_min(self, client, db_session):
        """Float values below min should be clamped to min."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {
                "post_color_opacity": -1.0,   # min is 0.0
                "nickname_brightness": 0.1,   # min is 0.5
            }},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["profile_style_settings"]
        assert data["post_color_opacity"] == 0.0
        assert data["nickname_brightness"] == 0.5

    def test_int_field_clamped(self, client, db_session):
        """Integer field nickname_gradient_angle should be clamped to 0-360."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"nickname_gradient_angle": 999}},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["profile_style_settings"]["nickname_gradient_angle"] == 360

        resp2 = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"nickname_gradient_angle": -50}},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["profile_style_settings"]["nickname_gradient_angle"] == 0

    def test_invalid_type_string_for_float(self, client, db_session):
        """String value where float expected should return 422."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"post_color_opacity": "high"}},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_invalid_type_string_for_bool(self, client, db_session):
        """String value where bool expected should return 422."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"nickname_shimmer": "yes"}},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_invalid_type_int_for_bool(self, client, db_session):
        """Integer value where bool expected should return 422 (JSON true != 1)."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"text_shadow_enabled": 1}},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_oversized_json_rejected(self, client, db_session):
        """JSON exceeding 2048 chars when serialized should be rejected."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        # We can't create oversized JSON with known keys (they're dropped),
        # so we fill all float fields to create large but valid content.
        # The validation drops unknown keys first, so we use known keys with
        # long hex values to test. Actually the hex field value is max 7 chars.
        # Let's just test with many valid fields — each field contributes
        # a small amount. With all known fields, JSON is well under 2048.
        # The real protection is against future abuse. We can test the
        # behavior by patching the constant.
        from main import PROFILE_STYLE_SETTINGS_MAX_SIZE
        import main

        original = main.PROFILE_STYLE_SETTINGS_MAX_SIZE
        try:
            # Temporarily set very small max size
            main.PROFILE_STYLE_SETTINGS_MAX_SIZE = 10

            resp = client.put(
                "/users/me/settings",
                json={"profile_style_settings": {
                    "post_color_opacity": 0.5,
                    "bg_color_opacity": 0.5,
                }},
                headers=headers,
            )
            assert resp.status_code == 422
        finally:
            main.PROFILE_STYLE_SETTINGS_MAX_SIZE = original

    def test_unknown_keys_dropped(self, client, db_session):
        """Unknown keys in profile_style_settings should be silently dropped."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {
                "post_color_opacity": 0.5,
                "totally_unknown_key": "should be dropped",
                "another_unknown": 42,
            }},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["profile_style_settings"]
        assert data["post_color_opacity"] == 0.5
        assert "totally_unknown_key" not in data
        assert "another_unknown" not in data

    def test_nickname_color_2_valid_hex(self, client, db_session):
        """nickname_color_2 with valid hex should be accepted."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"nickname_color_2": "#abc"}},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["profile_style_settings"]["nickname_color_2"] == "#abc"

    def test_nickname_color_2_invalid_hex(self, client, db_session):
        """nickname_color_2 with invalid hex should return 422."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"nickname_color_2": "not-hex"}},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_boolean_fields_accept_true_false(self, client, db_session):
        """Boolean fields should accept true and false."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {
                "nickname_shimmer": False,
                "text_shadow_enabled": True,
                "text_backdrop_enabled": False,
            }},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["profile_style_settings"]
        assert data["nickname_shimmer"] is False
        assert data["text_shadow_enabled"] is True
        assert data["text_backdrop_enabled"] is False

    def test_partial_update_only_some_keys(self, client, db_session):
        """Providing only some keys should work (others not included)."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"post_color_opacity": 0.7}},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["profile_style_settings"]
        assert data["post_color_opacity"] == 0.7
        # Other keys should not be present (only provided keys are saved)
        assert "bg_color_opacity" not in data

    def test_empty_dict_saves(self, client, db_session):
        """Empty dict should save as empty JSON object."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {}},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["profile_style_settings"]
        assert data == {}

    def test_null_resets_settings(self, client, db_session):
        """Setting profile_style_settings to null should reset it."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        # First set some settings
        client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"post_color_opacity": 0.5}},
            headers=headers,
        )

        # Then reset to null
        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": None},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["profile_style_settings"] is None

    def test_float_accepts_integer_values(self, client, db_session):
        """Integer values should be accepted for float fields (JSON has no float type distinction)."""
        user = _make_user(db_session)
        headers = _auth_header(user)

        resp = client.put(
            "/users/me/settings",
            json={"profile_style_settings": {"post_color_opacity": 1}},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["profile_style_settings"]["post_color_opacity"] == 1.0


# ===========================================================================
# 3. GET /users/{id}/profile — new fields in response
# ===========================================================================

class TestProfileResponseNewFields:

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_profile_includes_post_color(self, mock_fetch, client, db_session):
        """Profile response should include post_color."""
        user = _make_user(db_session)

        db_user = db_session.query(models.User).filter(models.User.id == user.id).first()
        db_user.post_color = "#112233"
        db_session.commit()

        resp = client.get(f"/users/{user.id}/profile")
        assert resp.status_code == 200
        assert resp.json()["post_color"] == "#112233"

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_profile_includes_style_settings_as_dict(self, mock_fetch, client, db_session):
        """profile_style_settings should be returned as dict, not string."""
        user = _make_user(db_session)

        db_user = db_session.query(models.User).filter(models.User.id == user.id).first()
        db_user.profile_style_settings = json.dumps({"post_color_opacity": 0.5, "nickname_shimmer": True})
        db_session.commit()

        resp = client.get(f"/users/{user.id}/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["profile_style_settings"], dict)
        assert data["profile_style_settings"]["post_color_opacity"] == 0.5
        assert data["profile_style_settings"]["nickname_shimmer"] is True

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_profile_includes_last_active_at(self, mock_fetch, client, db_session):
        """Profile response should include last_active_at."""
        user = _make_user(db_session)

        now = datetime.utcnow()
        db_user = db_session.query(models.User).filter(models.User.id == user.id).first()
        db_user.last_active_at = now
        db_session.commit()

        resp = client.get(f"/users/{user.id}/profile")
        assert resp.status_code == 200
        assert resp.json()["last_active_at"] is not None

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_profile_null_defaults(self, mock_fetch, client, db_session):
        """New user should have null for post_color, profile_style_settings, last_active_at."""
        user = _make_user(db_session)

        resp = client.get(f"/users/{user.id}/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["post_color"] is None
        assert data["profile_style_settings"] is None
        assert data["last_active_at"] is None

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_profile_malformed_json_returns_null(self, mock_fetch, client, db_session):
        """If profile_style_settings contains malformed JSON, it should return null."""
        user = _make_user(db_session)

        db_user = db_session.query(models.User).filter(models.User.id == user.id).first()
        db_user.profile_style_settings = "not valid json{{"
        db_session.commit()

        resp = client.get(f"/users/{user.id}/profile")
        assert resp.status_code == 200
        assert resp.json()["profile_style_settings"] is None


# ===========================================================================
# 4. GET /users/{id}/friends — last_active_at in response
# ===========================================================================

class TestFriendsLastActiveAt:

    def test_friend_has_last_active_at(self, client, db_session):
        """Each friend in the friends list should have last_active_at field."""
        user1 = _make_user(db_session, "user1", "user1@test.com")
        user2 = _make_user(db_session, "user2", "user2@test.com")

        # Set last_active_at on user2
        db_user2 = db_session.query(models.User).filter(models.User.id == user2.id).first()
        db_user2.last_active_at = datetime.utcnow()
        db_session.commit()

        # Create accepted friendship
        friendship = models.Friendship(
            user_id=user1.id,
            friend_id=user2.id,
            status="accepted",
        )
        db_session.add(friendship)
        db_session.commit()

        resp = client.get(f"/users/{user1.id}/friends")
        assert resp.status_code == 200
        friends = resp.json()
        assert len(friends) == 1
        assert "last_active_at" in friends[0]
        assert friends[0]["last_active_at"] is not None

    def test_friend_null_last_active_at(self, client, db_session):
        """Friend who never logged in should have null last_active_at."""
        user1 = _make_user(db_session, "user1", "user1@test.com")
        user2 = _make_user(db_session, "user2", "user2@test.com")

        friendship = models.Friendship(
            user_id=user1.id,
            friend_id=user2.id,
            status="accepted",
        )
        db_session.add(friendship)
        db_session.commit()

        resp = client.get(f"/users/{user1.id}/friends")
        assert resp.status_code == 200
        friends = resp.json()
        assert len(friends) == 1
        assert friends[0]["last_active_at"] is None


# ===========================================================================
# 5. GET /users/{id}/characters — race/class fields
# ===========================================================================

class TestCharactersRaceClassFields:

    @patch("main._fetch_character_short", new_callable=AsyncMock)
    def test_characters_include_race_class_fields(self, mock_fetch, client, db_session):
        """Characters response should include race/class fields from character-service."""
        user = _make_user(db_session)

        rel = models.UserCharacter(user_id=user.id, character_id=10)
        db_session.add(rel)
        db_session.commit()

        mock_fetch.return_value = {
            "id": 10,
            "name": "TestChar",
            "avatar": "/avatars/char.png",
            "level": 5,
            "current_location": None,
            "id_race": 2,
            "id_class": 1,
            "id_subrace": 4,
            "race_name": "Эльф",
            "class_name": "Воин",
            "subrace_name": "Высший эльф",
        }

        resp = client.get(f"/users/{user.id}/characters")
        assert resp.status_code == 200
        chars = resp.json()["characters"]
        assert len(chars) == 1

        char = chars[0]
        assert char["id_race"] == 2
        assert char["id_class"] == 1
        assert char["id_subrace"] == 4
        assert char["race_name"] == "Эльф"
        assert char["class_name"] == "Воин"
        assert char["subrace_name"] == "Высший эльф"

    @patch("main._fetch_character_short", new_callable=AsyncMock)
    def test_characters_null_race_class_fields(self, mock_fetch, client, db_session):
        """Characters without race/class data should have null for those fields."""
        user = _make_user(db_session)

        rel = models.UserCharacter(user_id=user.id, character_id=10)
        db_session.add(rel)
        db_session.commit()

        mock_fetch.return_value = {
            "id": 10,
            "name": "TestChar",
            "avatar": "/avatars/char.png",
            "level": 5,
            "current_location": None,
            # No race/class fields (old character-service response)
        }

        resp = client.get(f"/users/{user.id}/characters")
        assert resp.status_code == 200
        chars = resp.json()["characters"]
        assert len(chars) == 1

        char = chars[0]
        assert char["id_race"] is None
        assert char["id_class"] is None
        assert char["id_subrace"] is None
        assert char["race_name"] is None
        assert char["class_name"] is None
        assert char["subrace_name"] is None
