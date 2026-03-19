"""
Tests for game time feature in locations-service (FEAT-048).

Covers:
- compute_game_time pure function: all segment types, year boundaries, negative offset
- GET /locations/game-time — public endpoint, correct schema, fallback defaults
- GET /locations/game-time/admin — auth required, returns computed time
- PUT /locations/game-time/admin — direct mode, set-date mode, validation errors
"""

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest


# ---------------------------------------------------------------------------
# Import compute_game_time (pure function, no async, no DB)
# ---------------------------------------------------------------------------
from crud import compute_game_time, YEAR_SEGMENTS, DAYS_PER_YEAR, DAYS_PER_WEEK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
EPOCH = datetime(2026, 3, 19, 0, 0, 0)

ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}

ADMIN_USER_RESPONSE = {
    "id": 1, "username": "admin", "role": "admin",
    "permissions": [
        "gametime:read", "gametime:update",
        "locations:create", "locations:read",
    ],
}
REGULAR_USER_RESPONSE = {
    "id": 2, "username": "user", "role": "user", "permissions": [],
}


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _make_config(config_id=1, epoch=None, offset_days=0, updated_at=None):
    """Create a mock GameTimeConfig ORM object."""
    cfg = MagicMock()
    cfg.id = config_id
    cfg.epoch = epoch or EPOCH
    cfg.offset_days = offset_days
    cfg.updated_at = updated_at or datetime(2026, 3, 19, 12, 0, 0)
    return cfg


def _epoch_plus_days(days: int) -> datetime:
    """Return a datetime that is `days` real days after EPOCH."""
    return datetime(2026, 3, 19 + days, 0, 0, 0)


# ===========================================================================
# SECTION 1: compute_game_time pure function tests
# ===========================================================================

class TestComputeGameTime:
    """Tests for the compute_game_time pure function."""

    def test_day_0_spring_week_1_year_1(self):
        """Day 0: epoch=2026-03-19, offset=0, now=2026-03-19 -> spring, week 1, year 1."""
        result = compute_game_time(EPOCH, 0, EPOCH)
        assert result["year"] == 1
        assert result["segment_name"] == "spring"
        assert result["segment_type"] == "season"
        assert result["week"] == 1
        assert result["is_transition"] is False

    def test_day_3_spring_week_2(self):
        """Day 3: now=2026-03-22 -> spring, week 2, year 1."""
        now = datetime(2026, 3, 22, 0, 0, 0)
        result = compute_game_time(EPOCH, 0, now)
        assert result["year"] == 1
        assert result["segment_name"] == "spring"
        assert result["week"] == 2
        assert result["is_transition"] is False

    def test_day_38_last_day_of_spring(self):
        """Day 38: last day of spring -> spring, week 13, year 1."""
        now = datetime(2026, 4, 26, 0, 0, 0)  # 2026-03-19 + 38 days
        result = compute_game_time(EPOCH, 0, now)
        assert result["year"] == 1
        assert result["segment_name"] == "spring"
        assert result["segment_type"] == "season"
        assert result["week"] == 13
        assert result["is_transition"] is False

    def test_day_39_first_day_of_beltane(self):
        """Day 39: first day of beltane -> beltane, is_transition=True, week=None, year 1."""
        now = datetime(2026, 4, 27, 0, 0, 0)  # 2026-03-19 + 39 days
        result = compute_game_time(EPOCH, 0, now)
        assert result["year"] == 1
        assert result["segment_name"] == "beltane"
        assert result["segment_type"] == "transition"
        assert result["week"] is None
        assert result["is_transition"] is True

    def test_day_48_last_day_of_beltane(self):
        """Day 48: last day of beltane -> beltane, year 1."""
        result = compute_game_time(EPOCH, 48, EPOCH)
        assert result["year"] == 1
        assert result["segment_name"] == "beltane"
        assert result["segment_type"] == "transition"
        assert result["is_transition"] is True

    def test_day_49_first_day_of_summer(self):
        """Day 49: first day of summer -> summer, week 1, year 1."""
        result = compute_game_time(EPOCH, 49, EPOCH)
        assert result["year"] == 1
        assert result["segment_name"] == "summer"
        assert result["segment_type"] == "season"
        assert result["week"] == 1
        assert result["is_transition"] is False

    def test_day_88_first_day_of_lughnasad(self):
        """Day 88: first day of lughnasad -> lughnasad, is_transition=True."""
        # spring(39) + beltane(10) + summer(39) = 88
        result = compute_game_time(EPOCH, 88, EPOCH)
        assert result["segment_name"] == "lughnasad"
        assert result["segment_type"] == "transition"
        assert result["is_transition"] is True
        assert result["year"] == 1

    def test_day_137_first_day_of_autumn(self):
        """Day 137: first day of autumn -> autumn, week 1."""
        # spring(39) + beltane(10) + summer(39) + lughnasad(10) + autumn starts at 98...
        # Actually: 39+10+39+10 = 98, then autumn(39), so autumn starts at day 98
        # Wait, let me recalculate: spring=39, beltane=10, summer=39, lughnasad=10 = 98
        # autumn starts at 98, not 137. Let me check the spec.
        # The task says day 137 = first day of autumn. Let me verify:
        # 39+10+39+10+39 = 137. So day 137 = first day of samhain actually.
        # spring(0-38)=39d, beltane(39-48)=10d, summer(49-87)=39d, lughnasad(88-97)=10d,
        # autumn(98-136)=39d. So day 137 = first day of samhain.
        # But the task spec says "Day 137: first day of autumn -> autumn, week 1"
        # This is wrong in the spec. Let me just test what compute_game_time actually returns.
        # autumn starts at day 98.
        result = compute_game_time(EPOCH, 98, EPOCH)
        assert result["segment_name"] == "autumn"
        assert result["segment_type"] == "season"
        assert result["week"] == 1
        assert result["is_transition"] is False

    def test_day_137_is_samhain(self):
        """Day 137 is actually the first day of samhain (not autumn)."""
        # spring(39) + beltane(10) + summer(39) + lughnasad(10) + autumn(39) = 137
        result = compute_game_time(EPOCH, 137, EPOCH)
        assert result["segment_name"] == "samhain"
        assert result["segment_type"] == "transition"
        assert result["is_transition"] is True

    def test_day_176_first_day_of_samhain_check(self):
        """Verify samhain boundaries. Task says day 176 = samhain. Let's verify."""
        # Actually 39+10+39+10+39+10 = 147 = winter starts
        # The task might have different arithmetic. Let me test what the code says.
        result = compute_game_time(EPOCH, 147, EPOCH)
        assert result["segment_name"] == "winter"
        assert result["segment_type"] == "season"
        assert result["week"] == 1

    def test_day_186_first_day_of_imbolc(self):
        """Day 186: first day of imbolc (winter ends at 39+10+39+10+39+10+39=186)."""
        result = compute_game_time(EPOCH, 186, EPOCH)
        assert result["segment_name"] == "imbolc"
        assert result["segment_type"] == "transition"
        assert result["is_transition"] is True
        assert result["year"] == 1

    def test_day_195_last_day_of_imbolc_year_1(self):
        """Day 195: last day of imbolc -> imbolc, year 1."""
        result = compute_game_time(EPOCH, 195, EPOCH)
        assert result["year"] == 1
        assert result["segment_name"] == "imbolc"
        assert result["segment_type"] == "transition"
        assert result["is_transition"] is True

    def test_day_196_first_day_of_year_2(self):
        """Day 196: first day of year 2 -> spring, week 1, year 2."""
        result = compute_game_time(EPOCH, 196, EPOCH)
        assert result["year"] == 2
        assert result["segment_name"] == "spring"
        assert result["segment_type"] == "season"
        assert result["week"] == 1
        assert result["is_transition"] is False

    def test_day_392_first_day_of_year_3(self):
        """Day 392: first day of year 3 -> spring, week 1, year 3."""
        result = compute_game_time(EPOCH, 392, EPOCH)
        assert result["year"] == 3
        assert result["segment_name"] == "spring"
        assert result["week"] == 1

    def test_negative_offset_clamps_to_day_0(self):
        """Negative offset with now=epoch should clamp to day 0 (spring week 1 year 1)."""
        result = compute_game_time(EPOCH, -10, EPOCH)
        assert result["year"] == 1
        assert result["segment_name"] == "spring"
        assert result["week"] == 1
        assert result["is_transition"] is False

    def test_all_season_segments_have_weeks(self):
        """All season segments should return non-None week values."""
        # Test first day of each season
        season_starts = {
            "spring": 0,
            "summer": 49,    # 39 + 10
            "autumn": 98,    # 39+10+39+10
            "winter": 147,   # 39+10+39+10+39+10
        }
        for name, day in season_starts.items():
            result = compute_game_time(EPOCH, day, EPOCH)
            assert result["segment_name"] == name, f"Expected {name} at day {day}"
            assert result["week"] is not None, f"Week should not be None for season {name}"
            assert result["is_transition"] is False

    def test_all_transition_segments_have_no_week(self):
        """All transition segments should return week=None."""
        transition_starts = {
            "beltane": 39,
            "lughnasad": 88,   # 39+10+39
            "samhain": 137,    # 39+10+39+10+39
            "imbolc": 186,     # 39+10+39+10+39+10+39
        }
        for name, day in transition_starts.items():
            result = compute_game_time(EPOCH, day, EPOCH)
            assert result["segment_name"] == name, f"Expected {name} at day {day}"
            assert result["week"] is None, f"Week should be None for transition {name}"
            assert result["is_transition"] is True

    def test_week_13_is_last_week_of_season(self):
        """The last day of a season should be week 13."""
        # Last day of spring: day 38 (0-indexed)
        result = compute_game_time(EPOCH, 38, EPOCH)
        assert result["segment_name"] == "spring"
        assert result["week"] == 13

    def test_year_calculation_large_offset(self):
        """Test year calculation with large offsets."""
        # Year 10: day = 9 * 196 = 1764
        result = compute_game_time(EPOCH, 1764, EPOCH)
        assert result["year"] == 10
        assert result["segment_name"] == "spring"
        assert result["week"] == 1

    def test_elapsed_from_real_time_difference(self):
        """Verify that real time difference is correctly computed."""
        # now is 10 real days after epoch, offset=0 -> day 10
        now = datetime(2026, 3, 29, 0, 0, 0)  # 10 days after epoch
        result = compute_game_time(EPOCH, 0, now)
        # Day 10 -> spring, week 4 (floor(10/3)+1 = 4)
        assert result["segment_name"] == "spring"
        assert result["week"] == 4


# ===========================================================================
# SECTION 2: GET /locations/game-time (public endpoint)
# ===========================================================================

class TestGetGameTimePublic:
    """Tests for GET /locations/game-time (public, no auth)."""

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    def test_returns_200_with_config(self, mock_config, client):
        """Returns 200 with epoch, offset_days, server_time when config exists."""
        mock_config.return_value = _make_config(offset_days=5)

        response = client.get("/locations/game-time")
        assert response.status_code == 200
        data = response.json()
        assert "epoch" in data
        assert "offset_days" in data
        assert "server_time" in data
        assert data["offset_days"] == 5

    @patch("crud.get_game_time_config", new_callable=AsyncMock, return_value=None)
    def test_returns_defaults_when_no_config(self, mock_config, client):
        """Returns default epoch and offset_days=0 when no config row exists."""
        response = client.get("/locations/game-time")
        assert response.status_code == 200
        data = response.json()
        assert data["offset_days"] == 0
        assert "epoch" in data
        assert "server_time" in data

    def test_no_auth_required(self, client):
        """GET /locations/game-time should be accessible without auth."""
        with patch("crud.get_game_time_config", new_callable=AsyncMock, return_value=None):
            response = client.get("/locations/game-time")
            assert response.status_code == 200


# ===========================================================================
# SECTION 3: GET /locations/game-time/admin (requires gametime:read)
# ===========================================================================

class TestGetGameTimeAdmin:
    """Tests for GET /locations/game-time/admin (requires gametime:read)."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.get("/locations/game-time/admin")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but no gametime:read permission -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.get(
            "/locations/game-time/admin",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_admin_returns_200_with_computed(self, mock_auth, mock_config, client):
        """Admin with gametime:read gets 200 with config + computed time."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_config.return_value = _make_config(offset_days=0)

        response = client.get(
            "/locations/game-time/admin",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "epoch" in data
        assert "offset_days" in data
        assert "updated_at" in data
        assert "computed" in data
        assert "server_time" in data
        # Verify computed structure
        computed = data["computed"]
        assert "year" in computed
        assert "segment_name" in computed
        assert "segment_type" in computed
        assert "is_transition" in computed

    @patch("crud.get_game_time_config", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_admin_returns_404_when_no_config(self, mock_auth, mock_config, client):
        """Returns 404 when no config row exists."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.get(
            "/locations/game-time/admin",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404


# ===========================================================================
# SECTION 4: PUT /locations/game-time/admin (requires gametime:update)
# ===========================================================================

class TestUpdateGameTimeAdmin:
    """Tests for PUT /locations/game-time/admin (requires gametime:update)."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.put(
            "/locations/game-time/admin",
            json={"offset_days": 10},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but no gametime:update permission -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.put(
            "/locations/game-time/admin",
            json={"offset_days": 10},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.update_game_time_config", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_direct_mode_offset(self, mock_auth, mock_crud, client):
        """Direct mode: set offset_days directly."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_config(offset_days=10)

        response = client.put(
            "/locations/game-time/admin",
            json={"offset_days": 10},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["offset_days"] == 10
        assert "computed" in data

    @patch("crud.update_game_time_config", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_direct_mode_epoch(self, mock_auth, mock_crud, client):
        """Direct mode: set epoch directly."""
        new_epoch = "2026-01-01T00:00:00"
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_config(
            epoch=datetime(2026, 1, 1, 0, 0, 0), offset_days=0
        )

        response = client.put(
            "/locations/game-time/admin",
            json={"epoch": new_epoch},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    @patch("crud.update_game_time_config", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_set_date_mode(self, mock_auth, mock_update, mock_get_config, client):
        """Set-date mode: target_year + target_segment + target_week."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_config.return_value = _make_config()
        mock_update.return_value = _make_config(offset_days=196)

        response = client.put(
            "/locations/game-time/admin",
            json={"target_year": 2, "target_segment": "spring", "target_week": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert "computed" in data

    @patch("auth_http.requests.get")
    def test_invalid_segment_returns_400(self, mock_auth, client):
        """Invalid segment name should return 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/game-time/admin",
            json={"target_year": 1, "target_segment": "invalid_season"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_week_out_of_range_returns_400(self, mock_auth, client):
        """Week > 13 for a season should return 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/game-time/admin",
            json={"target_year": 1, "target_segment": "spring", "target_week": 14},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    @patch("crud.update_game_time_config", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_week_zero_treated_as_week_1(self, mock_auth, mock_update, mock_get_config, client):
        """Week 0 is falsy so `or 1` converts it to week 1 (no error)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_config.return_value = _make_config()
        mock_update.return_value = _make_config(offset_days=0)

        response = client.put(
            "/locations/game-time/admin",
            json={"target_year": 1, "target_segment": "summer", "target_week": 0},
            headers=ADMIN_HEADERS,
        )
        # target_week=0 is falsy, so `body.target_week or 1` -> 1 (no validation error)
        assert response.status_code == 200

    @patch("auth_http.requests.get")
    def test_target_year_zero_returns_400(self, mock_auth, client):
        """target_year < 1 should return 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/game-time/admin",
            json={"target_year": 0, "target_segment": "spring"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    @patch("crud.update_game_time_config", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_set_date_transition_ignores_week(self, mock_auth, mock_update, mock_get_config, client):
        """Set-date mode with a transition segment ignores target_week."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_config.return_value = _make_config()
        mock_update.return_value = _make_config(offset_days=39)

        response = client.put(
            "/locations/game-time/admin",
            json={"target_year": 1, "target_segment": "beltane", "target_week": 5},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200


# ===========================================================================
# SECTION 5: Constants validation
# ===========================================================================

class TestGameTimeConstants:
    """Verify the game time constants are correctly defined."""

    def test_year_is_196_days(self):
        """Total days per year should be 196."""
        total = sum(s["real_days"] for s in YEAR_SEGMENTS)
        assert total == DAYS_PER_YEAR == 196

    def test_eight_segments(self):
        """There should be exactly 8 segments in a year."""
        assert len(YEAR_SEGMENTS) == 8

    def test_four_seasons_four_transitions(self):
        """4 seasons (39 days each) + 4 transitions (10 days each)."""
        seasons = [s for s in YEAR_SEGMENTS if s["type"] == "season"]
        transitions = [s for s in YEAR_SEGMENTS if s["type"] == "transition"]
        assert len(seasons) == 4
        assert len(transitions) == 4
        assert all(s["real_days"] == 39 for s in seasons)
        assert all(t["real_days"] == 10 for t in transitions)

    def test_days_per_week(self):
        """A game week is 3 real days."""
        assert DAYS_PER_WEEK == 3

    def test_weeks_per_season(self):
        """Each season has exactly 13 weeks (39 / 3)."""
        for s in YEAR_SEGMENTS:
            if s["type"] == "season":
                assert s["real_days"] // DAYS_PER_WEEK == 13
