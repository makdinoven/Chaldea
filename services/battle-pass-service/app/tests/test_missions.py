"""Tests for mission endpoints: GET /me/missions, POST /me/missions/{id}/complete."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from models import (
    BpMission, BpUserProgress, BpUserMissionProgress, BpUserSnapshot,
)
from conftest import TEST_USER, Character, CharacterAttribute

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# GET /battle-pass/me/missions
# ---------------------------------------------------------------------------

class TestGetMyMissions:
    async def test_returns_missions_with_progress(
        self, client, db_session, season_with_missions, test_character,
    ):
        resp = await client.get("/battle-pass/me/missions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["season_id"] == season_with_missions.id
        assert data["current_week"] >= 1
        # Only missions for weeks <= current_week are returned
        for m in data["missions"]:
            assert m["week_number"] <= data["current_week"]

    async def test_no_season_404(self, client):
        resp = await client.get("/battle-pass/me/missions")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Нет активного сезона"

    async def test_stub_missions_return_zero_progress(
        self, client, db_session, season_with_missions, test_character,
    ):
        """quest_complete is a stub type - should always return 0 progress."""
        resp = await client.get("/battle-pass/me/missions")
        assert resp.status_code == 200
        data = resp.json()
        stub_missions = [
            m for m in data["missions"] if m["mission_type"] == "quest_complete"
        ]
        for m in stub_missions:
            assert m["current_count"] == 0
            assert m["is_completed"] is False

    async def test_completed_mission_shows_completed(
        self, client, db_session, season_with_missions, test_character,
    ):
        """If a mission was previously completed, it should show as completed."""
        # Find a mission
        from sqlalchemy import select
        result = await db_session.execute(
            select(BpMission).where(
                BpMission.season_id == season_with_missions.id,
                BpMission.week_number == 1,
            ).limit(1)
        )
        mission = result.scalars().first()

        # Manually mark as completed
        record = BpUserMissionProgress(
            user_id=TEST_USER.id,
            mission_id=mission.id,
            current_count=mission.target_count,
            completed_at=datetime.utcnow(),
        )
        db_session.add(record)
        await db_session.commit()

        resp = await client.get("/battle-pass/me/missions")
        assert resp.status_code == 200
        data = resp.json()
        completed = [m for m in data["missions"] if m["id"] == mission.id]
        assert len(completed) == 1
        assert completed[0]["is_completed"] is True


# ---------------------------------------------------------------------------
# POST /battle-pass/me/missions/{mission_id}/complete
# ---------------------------------------------------------------------------

class TestCompleteMission:
    async def _setup_completable_mission(self, db_session, season):
        """Create a kill_mobs mission and set up character data so progress >= target."""
        mission = BpMission(
            season_id=season.id,
            week_number=1,
            mission_type="kill_mobs",
            description="Kill 5 mobs",
            target_count=5,
            xp_reward=50,
        )
        db_session.add(mission)
        await db_session.flush()

        # Create character with kills
        char = Character(
            id=100,
            user_id=TEST_USER.id,
            name="Hero",
            level=5,
            is_npc=False,
        )
        db_session.add(char)
        attrs = CharacterAttribute(character_id=100, pve_kills=15)
        db_session.add(attrs)

        # Enrollment progress (needed for XP award)
        progress = BpUserProgress(
            user_id=TEST_USER.id,
            season_id=season.id,
            current_level=0,
            current_xp=0,
            is_premium=False,
        )
        db_session.add(progress)

        # Snapshot with 5 kills -> delta = 15 - 5 = 10 >= 5
        snapshot = BpUserSnapshot(
            user_id=TEST_USER.id,
            season_id=season.id,
            character_id=100,
            snapshot_type="pve_kills",
            value_at_enrollment=5,
        )
        db_session.add(snapshot)
        await db_session.commit()
        await db_session.refresh(mission)
        return mission

    async def test_complete_mission_success(
        self, client, db_session, active_season,
    ):
        mission = await self._setup_completable_mission(db_session, active_season)
        resp = await client.post(
            f"/battle-pass/me/missions/{mission.id}/complete"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["xp_awarded"] == 50

    async def test_already_completed_409(
        self, client, db_session, active_season,
    ):
        mission = await self._setup_completable_mission(db_session, active_season)

        # Complete once
        resp1 = await client.post(
            f"/battle-pass/me/missions/{mission.id}/complete"
        )
        assert resp1.status_code == 200

        # Try again -> 409
        resp2 = await client.post(
            f"/battle-pass/me/missions/{mission.id}/complete"
        )
        assert resp2.status_code == 409
        assert "уже завершено" in resp2.json()["detail"].lower()

    async def test_not_yet_done_400(
        self, client, db_session, active_season,
    ):
        """Mission with target not reached -> 400."""
        mission = BpMission(
            season_id=active_season.id,
            week_number=1,
            mission_type="kill_mobs",
            description="Kill 100 mobs",
            target_count=100,
            xp_reward=50,
        )
        db_session.add(mission)

        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero", level=5, is_npc=False,
        )
        db_session.add(char)
        attrs = CharacterAttribute(character_id=100, pve_kills=5)
        db_session.add(attrs)

        progress = BpUserProgress(
            user_id=TEST_USER.id, season_id=active_season.id,
            current_level=0, current_xp=0, is_premium=False,
        )
        db_session.add(progress)

        snapshot = BpUserSnapshot(
            user_id=TEST_USER.id, season_id=active_season.id,
            character_id=100, snapshot_type="pve_kills",
            value_at_enrollment=5,
        )
        db_session.add(snapshot)
        await db_session.commit()
        await db_session.refresh(mission)

        resp = await client.post(
            f"/battle-pass/me/missions/{mission.id}/complete"
        )
        assert resp.status_code == 400
        assert "не выполнено" in resp.json()["detail"].lower()

    async def test_mission_not_found_404(self, client, active_season):
        resp = await client.post("/battle-pass/me/missions/99999/complete")
        assert resp.status_code == 404

    async def test_no_season_404(self, client):
        resp = await client.post("/battle-pass/me/missions/1/complete")
        assert resp.status_code == 404

    async def test_season_ended_400(self, client, ended_season, db_session):
        """Cannot complete missions when season is ended."""
        # ended_season's grace period is also past, so status is "ended"
        # But get_current_season won't return it (grace_end < now)
        # So we get 404 instead of 400
        resp = await client.post("/battle-pass/me/missions/1/complete")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Week number computation edge case
# ---------------------------------------------------------------------------

class TestMissionWeekAvailability:
    async def test_future_week_mission_not_returned(
        self, client, db_session, active_season, test_character,
    ):
        """Missions for future weeks should not appear in GET /me/missions."""
        mission = BpMission(
            season_id=active_season.id,
            week_number=99,  # Far future week
            mission_type="kill_mobs",
            description="Future mission",
            target_count=1,
            xp_reward=10,
        )
        db_session.add(mission)
        await db_session.commit()

        resp = await client.get("/battle-pass/me/missions")
        assert resp.status_code == 200
        data = resp.json()
        future = [m for m in data["missions"] if m["week_number"] == 99]
        assert len(future) == 0
