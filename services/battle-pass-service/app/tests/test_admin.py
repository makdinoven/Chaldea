"""Tests for admin endpoints: seasons CRUD, levels/rewards upsert, missions upsert."""

import pytest
from datetime import datetime, timedelta

from models import BpSeason, BpLevel, BpReward, BpMission, BpUserProgress
from conftest import ADMIN_USER, UNAUTHORIZED_USER

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Admin: Seasons CRUD
# ---------------------------------------------------------------------------

class TestAdminSeasons:
    async def test_create_season(self, admin_client, db_session):
        now = datetime.utcnow()
        resp = await admin_client.post(
            "/battle-pass/admin/seasons",
            json={
                "name": "Spring Season",
                "segment_name": "spring",
                "year": 1,
                "start_date": (now + timedelta(days=10)).isoformat(),
                "end_date": (now + timedelta(days=49)).isoformat(),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Spring Season"
        assert data["segment_name"] == "spring"
        assert data["is_active"] is False
        # grace_end_date should be end_date + 7 days
        end_dt = datetime.fromisoformat(data["end_date"])
        grace_dt = datetime.fromisoformat(data["grace_end_date"])
        assert (grace_dt - end_dt).days == 7

    async def test_list_seasons(self, admin_client, db_session, active_season):
        resp = await admin_client.get("/battle-pass/admin/seasons")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    async def test_update_season(self, admin_client, db_session, active_season):
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{active_season.id}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"

    async def test_update_season_not_found(self, admin_client):
        resp = await admin_client.put(
            "/battle-pass/admin/seasons/99999",
            json={"name": "Nope"},
        )
        assert resp.status_code == 404

    async def test_delete_season_success(self, admin_client, db_session, active_season):
        resp = await admin_client.delete(
            f"/battle-pass/admin/seasons/{active_season.id}"
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    async def test_delete_season_not_found(self, admin_client):
        resp = await admin_client.delete("/battle-pass/admin/seasons/99999")
        assert resp.status_code == 404

    async def test_delete_blocked_with_user_progress(
        self, admin_client, db_session, active_season,
    ):
        """Cannot delete season that has user progress."""
        progress = BpUserProgress(
            user_id=1, season_id=active_season.id,
            current_level=0, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        await db_session.commit()

        resp = await admin_client.delete(
            f"/battle-pass/admin/seasons/{active_season.id}"
        )
        assert resp.status_code == 400
        assert "прогресс" in resp.json()["detail"].lower()

    async def test_date_overlap_validation(
        self, admin_client, db_session, active_season,
    ):
        """Creating season with overlapping dates -> 400."""
        # active_season occupies start-10d to start+36d
        now = datetime.utcnow()
        resp = await admin_client.post(
            "/battle-pass/admin/seasons",
            json={
                "name": "Overlap Season",
                "segment_name": "winter",
                "year": 1,
                "start_date": (now - timedelta(days=5)).isoformat(),
                "end_date": (now + timedelta(days=34)).isoformat(),
            },
        )
        assert resp.status_code == 400
        assert "пересекаются" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Admin: Levels & Rewards bulk upsert
# ---------------------------------------------------------------------------

class TestAdminLevels:
    async def test_bulk_upsert_levels(self, admin_client, db_session, active_season):
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{active_season.id}/levels",
            json={
                "levels": [
                    {
                        "level_number": 1,
                        "required_xp": 100,
                        "free_rewards": [
                            {"reward_type": "gold", "reward_value": 500},
                        ],
                        "premium_rewards": [
                            {"reward_type": "diamonds", "reward_value": 50},
                        ],
                    },
                    {
                        "level_number": 2,
                        "required_xp": 200,
                        "free_rewards": [
                            {"reward_type": "xp", "reward_value": 100},
                        ],
                        "premium_rewards": [],
                    },
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["level_number"] == 1
        assert data[0]["required_xp"] == 100
        assert len(data[0]["rewards"]) == 2  # free + premium

    async def test_get_levels(self, admin_client, db_session, season_with_levels):
        resp = await admin_client.get(
            f"/battle-pass/admin/seasons/{season_with_levels.id}/levels"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    async def test_upsert_replaces_existing(
        self, admin_client, db_session, season_with_levels,
    ):
        """Bulk upsert deletes old levels and inserts new ones."""
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{season_with_levels.id}/levels",
            json={
                "levels": [
                    {
                        "level_number": 1,
                        "required_xp": 999,
                        "free_rewards": [],
                        "premium_rewards": [],
                    },
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["required_xp"] == 999


# ---------------------------------------------------------------------------
# Admin: Missions bulk upsert
# ---------------------------------------------------------------------------

class TestAdminMissions:
    async def test_bulk_upsert_missions(self, admin_client, db_session, active_season):
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{active_season.id}/missions",
            json={
                "missions": [
                    {
                        "week_number": 1,
                        "mission_type": "kill_mobs",
                        "description": "Kill 10 mobs",
                        "target_count": 10,
                        "xp_reward": 50,
                    },
                    {
                        "week_number": 1,
                        "mission_type": "write_posts",
                        "description": "Write 3 posts",
                        "target_count": 3,
                        "xp_reward": 30,
                    },
                    {
                        "week_number": 2,
                        "mission_type": "earn_gold",
                        "description": "Earn 1000 gold",
                        "target_count": 1000,
                        "xp_reward": 60,
                    },
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    async def test_get_missions_grouped(
        self, admin_client, db_session, season_with_missions,
    ):
        resp = await admin_client.get(
            f"/battle-pass/admin/seasons/{season_with_missions.id}/missions"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "weeks" in data
        # season_with_missions has missions in weeks 1 and 2
        assert "1" in data["weeks"]
        assert "2" in data["weeks"]

    async def test_upsert_replaces_missions(
        self, admin_client, db_session, season_with_missions,
    ):
        """Bulk upsert deletes old missions and inserts new ones."""
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{season_with_missions.id}/missions",
            json={
                "missions": [
                    {
                        "week_number": 1,
                        "mission_type": "level_up",
                        "description": "Level up once",
                        "target_count": 1,
                        "xp_reward": 100,
                    },
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["mission_type"] == "level_up"


# ---------------------------------------------------------------------------
# Permission checks (403 for unauthorized)
# ---------------------------------------------------------------------------

class TestAdminPermissions:
    async def test_list_seasons_403_no_permission(self, unauthorized_client):
        resp = await unauthorized_client.get("/battle-pass/admin/seasons")
        assert resp.status_code == 403

    async def test_create_season_403_no_permission(self, unauthorized_client):
        now = datetime.utcnow()
        resp = await unauthorized_client.post(
            "/battle-pass/admin/seasons",
            json={
                "name": "Test",
                "segment_name": "spring",
                "year": 1,
                "start_date": (now + timedelta(days=10)).isoformat(),
                "end_date": (now + timedelta(days=49)).isoformat(),
            },
        )
        assert resp.status_code == 403

    async def test_update_season_403_no_permission(self, unauthorized_client):
        resp = await unauthorized_client.put(
            "/battle-pass/admin/seasons/1",
            json={"name": "X"},
        )
        assert resp.status_code == 403

    async def test_delete_season_403_no_permission(self, unauthorized_client):
        resp = await unauthorized_client.delete("/battle-pass/admin/seasons/1")
        assert resp.status_code == 403

    async def test_get_levels_403_no_permission(self, unauthorized_client):
        resp = await unauthorized_client.get(
            "/battle-pass/admin/seasons/1/levels"
        )
        assert resp.status_code == 403

    async def test_upsert_levels_403_no_permission(self, unauthorized_client):
        resp = await unauthorized_client.put(
            "/battle-pass/admin/seasons/1/levels",
            json={"levels": []},
        )
        assert resp.status_code == 403

    async def test_get_missions_403_no_permission(self, unauthorized_client):
        resp = await unauthorized_client.get(
            "/battle-pass/admin/seasons/1/missions"
        )
        assert resp.status_code == 403

    async def test_upsert_missions_403_no_permission(self, unauthorized_client):
        resp = await unauthorized_client.put(
            "/battle-pass/admin/seasons/1/missions",
            json={"missions": []},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestAdminValidation:
    async def test_create_season_end_before_start(self, admin_client):
        now = datetime.utcnow()
        resp = await admin_client.post(
            "/battle-pass/admin/seasons",
            json={
                "name": "Bad",
                "segment_name": "spring",
                "year": 1,
                "start_date": (now + timedelta(days=50)).isoformat(),
                "end_date": (now + timedelta(days=10)).isoformat(),
            },
        )
        assert resp.status_code == 422  # Pydantic validation error

    async def test_level_number_out_of_range(self, admin_client, active_season):
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{active_season.id}/levels",
            json={
                "levels": [
                    {
                        "level_number": 0,
                        "required_xp": 100,
                        "free_rewards": [],
                        "premium_rewards": [],
                    },
                ],
            },
        )
        assert resp.status_code == 422

    async def test_invalid_reward_type(self, admin_client, active_season):
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{active_season.id}/levels",
            json={
                "levels": [
                    {
                        "level_number": 1,
                        "required_xp": 100,
                        "free_rewards": [
                            {"reward_type": "invalid", "reward_value": 100},
                        ],
                        "premium_rewards": [],
                    },
                ],
            },
        )
        assert resp.status_code == 422

    async def test_invalid_mission_type(self, admin_client, active_season):
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{active_season.id}/missions",
            json={
                "missions": [
                    {
                        "week_number": 1,
                        "mission_type": "nonexistent_type",
                        "description": "Bad",
                        "target_count": 1,
                        "xp_reward": 10,
                    },
                ],
            },
        )
        assert resp.status_code == 422

    async def test_negative_xp_reward(self, admin_client, active_season):
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{active_season.id}/missions",
            json={
                "missions": [
                    {
                        "week_number": 1,
                        "mission_type": "kill_mobs",
                        "description": "Kill",
                        "target_count": 1,
                        "xp_reward": -10,
                    },
                ],
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Security: SQL injection attempts in admin endpoints
# ---------------------------------------------------------------------------

class TestAdminSecurity:
    async def test_sql_injection_in_season_name(self, admin_client):
        now = datetime.utcnow()
        resp = await admin_client.post(
            "/battle-pass/admin/seasons",
            json={
                "name": "'; DROP TABLE bp_seasons; --",
                "segment_name": "spring",
                "year": 1,
                "start_date": (now + timedelta(days=100)).isoformat(),
                "end_date": (now + timedelta(days=139)).isoformat(),
            },
        )
        # Should succeed (ORM escapes input) — or fail gracefully
        assert resp.status_code in (201, 400, 422)
