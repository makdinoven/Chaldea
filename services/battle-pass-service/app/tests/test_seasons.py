"""Tests for GET /battle-pass/seasons/current and season status computation."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import crud
from models import BpSeason, BpLevel, BpReward


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Unit tests for season status helpers
# ---------------------------------------------------------------------------

class TestComputeSeasonStatus:
    def test_active_season(self, active_season):
        status = crud.compute_season_status(active_season)
        assert status == "active"

    def test_grace_season(self, grace_season):
        status = crud.compute_season_status(grace_season)
        assert status == "grace"

    def test_ended_season(self, ended_season):
        status = crud.compute_season_status(ended_season)
        assert status == "ended"


class TestComputeCurrentWeek:
    def test_first_week(self):
        now = datetime.utcnow()
        season = BpSeason(
            start_date=now - timedelta(days=3),
            end_date=now + timedelta(days=36),
            grace_end_date=now + timedelta(days=43),
        )
        week = crud.compute_current_week(season)
        assert week == 1

    def test_second_week(self):
        now = datetime.utcnow()
        season = BpSeason(
            start_date=now - timedelta(days=8),
            end_date=now + timedelta(days=31),
            grace_end_date=now + timedelta(days=38),
        )
        week = crud.compute_current_week(season)
        assert week == 2

    def test_before_start(self):
        now = datetime.utcnow()
        season = BpSeason(
            start_date=now + timedelta(days=5),
            end_date=now + timedelta(days=44),
            grace_end_date=now + timedelta(days=51),
        )
        week = crud.compute_current_week(season)
        assert week == 1  # Returns 1 when before start


class TestComputeTotalWeeks:
    def test_39_day_season(self):
        now = datetime.utcnow()
        season = BpSeason(
            start_date=now,
            end_date=now + timedelta(days=39),
            grace_end_date=now + timedelta(days=46),
        )
        total = crud.compute_total_weeks(season)
        assert total == 6  # ceil(39/7) = 6


class TestComputeDaysRemaining:
    def test_active_season_days(self, active_season):
        days = crud.compute_days_remaining(active_season)
        assert days >= 28  # We set end_date to now + 29 days

    def test_grace_season_days(self, grace_season):
        days = crud.compute_days_remaining(grace_season)
        assert days >= 0
        assert days <= 1

    def test_ended_season_days(self, ended_season):
        days = crud.compute_days_remaining(ended_season)
        assert days == 0


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class TestGetCurrentSeason:
    async def test_active_season_returned(self, client, season_with_levels):
        resp = await client.get("/battle-pass/seasons/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Season"
        assert data["status"] == "active"
        assert data["days_remaining"] >= 0
        assert data["current_week"] >= 1
        assert len(data["levels"]) == 3
        # Verify levels have rewards split by track
        lvl1 = data["levels"][0]
        assert lvl1["level_number"] == 1
        assert len(lvl1["free_rewards"]) == 1
        assert len(lvl1["premium_rewards"]) == 1
        assert lvl1["free_rewards"][0]["reward_type"] == "gold"
        assert lvl1["premium_rewards"][0]["reward_type"] == "diamonds"

    async def test_grace_season_returned(self, db_session, client, grace_season):
        # Add a level so get_season_with_levels works
        level = BpLevel(
            season_id=grace_season.id,
            level_number=1,
            required_xp=100,
        )
        db_session.add(level)
        await db_session.commit()

        resp = await client.get("/battle-pass/seasons/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "grace"

    async def test_no_season_404(self, client):
        resp = await client.get("/battle-pass/seasons/current")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Нет активного сезона"

    async def test_ended_season_not_returned(self, client, ended_season):
        resp = await client.get("/battle-pass/seasons/current")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Security: SQL injection in path params (season endpoint is param-free,
# but test overall app resilience)
# ---------------------------------------------------------------------------

class TestSeasonSecurity:
    async def test_no_crash_on_invalid_paths(self, client):
        resp = await client.get("/battle-pass/seasons/'; DROP TABLE bp_seasons; --")
        assert resp.status_code in (404, 405, 422)
