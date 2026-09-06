"""
FEAT-154 task #3 — GET /locations/game-time now carries a `computed` block.

The change is purely additive: the three original keys must stay, and the new
block must be the same shape the admin endpoint already returns, so that
character-service can read `computed.year` without re-implementing the calendar.

Hard constraint of §3.5: no four-digit in-game year is hardcoded anywhere —
these tests assert on the *derivation*, never on a literal year.
"""

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import schemas  # noqa: E402
from crud import DAYS_PER_YEAR, compute_game_time  # noqa: E402


EPOCH = datetime(2026, 3, 19, 0, 0, 0)


def _make_config(offset_days=0):
    cfg = MagicMock()
    cfg.id = 1
    cfg.epoch = EPOCH
    cfg.offset_days = offset_days
    cfg.updated_at = datetime(2026, 3, 19, 12, 0, 0)
    return cfg


class TestPublicGameTimeComputed:

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    def test_original_keys_are_preserved(self, mock_config, client):
        """Existing consumers (frontend gameTime.ts) must keep working."""
        mock_config.return_value = _make_config(offset_days=5)
        body = client.get("/locations/game-time").json()
        assert {"epoch", "offset_days", "server_time"} <= set(body)
        assert body["offset_days"] == 5

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    def test_computed_block_is_present_and_complete(self, mock_config, client):
        mock_config.return_value = _make_config(offset_days=0)
        body = client.get("/locations/game-time").json()
        assert "computed" in body
        assert set(body["computed"]) == {
            "year", "segment_name", "segment_type", "week", "is_transition",
        }

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    def test_computed_matches_compute_game_time(self, mock_config, client):
        """No second calendar implementation — the block comes from crud."""
        offset = DAYS_PER_YEAR * 3 + 49  # year 4, first day of summer
        mock_config.return_value = _make_config(offset_days=offset)

        computed = client.get("/locations/game-time").json()["computed"]
        expected = compute_game_time(EPOCH, offset, datetime.utcnow())

        assert computed["year"] == expected["year"]
        assert computed["segment_name"] == expected["segment_name"]
        assert computed["segment_type"] == expected["segment_type"]
        assert computed["is_transition"] == expected["is_transition"]

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    def test_year_advances_with_the_clock(self, mock_config, client):
        """Moving the clock must move the year with zero code changes."""
        mock_config.return_value = _make_config(offset_days=0)
        first = client.get("/locations/game-time").json()["computed"]["year"]

        mock_config.return_value = _make_config(offset_days=DAYS_PER_YEAR * 5)
        later = client.get("/locations/game-time").json()["computed"]["year"]

        assert later == first + 5

    @patch("crud.get_game_time_config", new_callable=AsyncMock, return_value=None)
    def test_computed_present_even_without_a_config_row(self, mock_config, client):
        body = client.get("/locations/game-time").json()
        assert body["offset_days"] == 0
        assert body["computed"]["year"] >= 1

    @patch("crud.get_game_time_config", new_callable=AsyncMock)
    def test_still_public(self, mock_config, client):
        mock_config.return_value = _make_config()
        assert client.get("/locations/game-time").status_code == 200

    def test_schema_declares_computed_as_required(self):
        field = schemas.GameTimePublicResponse.__fields__["computed"]
        assert field.required is True
        assert field.type_ is schemas.ComputedGameTime
