"""Tests for GET /battle-pass/me/progress, XP awarding, and level-up logic."""

import pytest
from datetime import datetime, timedelta

from models import BpLevel, BpUserProgress, BpUserSnapshot
from conftest import TEST_USER, Character, CharacterAttribute
import crud

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# GET /battle-pass/me/progress
# ---------------------------------------------------------------------------

class TestGetMyProgress:
    async def test_lazy_enrollment_creates_progress(
        self, client, db_session, active_season, test_character,
    ):
        """First access auto-creates progress and snapshots."""
        resp = await client.get("/battle-pass/me/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["season_id"] == active_season.id
        assert data["current_level"] == 0
        assert data["current_xp"] == 0
        assert data["is_premium"] is False

        # Verify snapshots were created
        from sqlalchemy import select
        result = await db_session.execute(
            select(BpUserSnapshot).where(
                BpUserSnapshot.user_id == TEST_USER.id,
                BpUserSnapshot.season_id == active_season.id,
            )
        )
        snapshots = result.scalars().all()
        assert len(snapshots) == 2  # pve_kills + level
        types = {s.snapshot_type for s in snapshots}
        assert "pve_kills" in types
        assert "level" in types

    async def test_existing_progress_returned(
        self, client, db_session, active_season, test_character,
    ):
        """Second access returns existing progress without re-creating."""
        # Create progress manually
        progress = BpUserProgress(
            user_id=TEST_USER.id,
            season_id=active_season.id,
            current_level=5,
            current_xp=42,
            is_premium=True,
        )
        db_session.add(progress)
        await db_session.commit()

        resp = await client.get("/battle-pass/me/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_level"] == 5
        assert data["current_xp"] == 42
        assert data["is_premium"] is True

    async def test_xp_to_next_level_present(
        self, client, db_session, season_with_levels, test_character,
    ):
        """Progress includes xp_to_next_level."""
        resp = await client.get("/battle-pass/me/progress")
        assert resp.status_code == 200
        data = resp.json()
        # At level 0, next is level 1 with required_xp = 100
        assert data["xp_to_next_level"] == 100

    async def test_xp_to_next_level_at_max(
        self, client, db_session, season_with_levels, test_character,
    ):
        """At max level, xp_to_next_level is None."""
        progress = BpUserProgress(
            user_id=TEST_USER.id,
            season_id=season_with_levels.id,
            current_level=3,  # Max in our fixture (3 levels)
            current_xp=0,
            is_premium=False,
        )
        db_session.add(progress)
        await db_session.commit()

        resp = await client.get("/battle-pass/me/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_to_next_level"] is None

    async def test_no_season_404(self, client):
        resp = await client.get("/battle-pass/me/progress")
        assert resp.status_code == 404

    async def test_claimed_rewards_in_response(
        self, client, db_session, season_with_levels, test_character,
    ):
        """Claimed rewards are included in progress response."""
        from models import BpUserReward, BpLevel
        from sqlalchemy import select

        progress = BpUserProgress(
            user_id=TEST_USER.id,
            season_id=season_with_levels.id,
            current_level=1,
            current_xp=0,
            is_premium=False,
        )
        db_session.add(progress)
        await db_session.flush()

        # Get level 1
        result = await db_session.execute(
            select(BpLevel).where(
                BpLevel.season_id == season_with_levels.id,
                BpLevel.level_number == 1,
            )
        )
        level = result.scalars().first()

        claim = BpUserReward(
            user_id=TEST_USER.id,
            season_id=season_with_levels.id,
            level_id=level.id,
            track="free",
            delivered_to_character_id=100,
        )
        db_session.add(claim)
        await db_session.commit()

        resp = await client.get("/battle-pass/me/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["claimed_rewards"]) == 1
        assert data["claimed_rewards"][0]["level_number"] == 1
        assert data["claimed_rewards"][0]["track"] == "free"


# ---------------------------------------------------------------------------
# XP awarding and level-up (unit-level via crud)
# ---------------------------------------------------------------------------

class TestAwardBpXp:
    async def test_basic_xp_award(self, db_session, active_season):
        """Award XP without enough for level-up."""
        # Create levels
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)

        progress = BpUserProgress(
            user_id=TEST_USER.id, season_id=active_season.id,
            current_level=0, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        await db_session.commit()

        result = await crud.award_bp_xp(db_session, TEST_USER.id, active_season.id, 50)
        assert result["new_total_xp"] == 50
        assert result["new_level"] == 0
        assert result["leveled_up"] is False

    async def test_level_up(self, db_session, active_season):
        """Award enough XP to level up once."""
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        progress = BpUserProgress(
            user_id=TEST_USER.id, season_id=active_season.id,
            current_level=0, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        await db_session.commit()

        result = await crud.award_bp_xp(db_session, TEST_USER.id, active_season.id, 100)
        assert result["new_level"] == 1
        assert result["new_total_xp"] == 0  # XP consumed by level-up
        assert result["leveled_up"] is True

    async def test_multi_level_up(self, db_session, active_season):
        """Award enough XP to skip multiple levels."""
        for i in range(1, 4):
            level = BpLevel(
                season_id=active_season.id, level_number=i, required_xp=100,
            )
            db_session.add(level)
        progress = BpUserProgress(
            user_id=TEST_USER.id, season_id=active_season.id,
            current_level=0, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        await db_session.commit()

        # Award 250 XP: level 1 costs 100, level 2 costs 100, level 3 costs 100
        # So 250 XP -> level 2 with 50 remaining
        result = await crud.award_bp_xp(db_session, TEST_USER.id, active_season.id, 250)
        assert result["new_level"] == 2
        assert result["new_total_xp"] == 50
        assert result["leveled_up"] is True

    async def test_xp_overflow_at_max_level(self, db_session, active_season):
        """XP that exceeds all levels stays as remainder."""
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=50,
        )
        db_session.add(level)
        progress = BpUserProgress(
            user_id=TEST_USER.id, season_id=active_season.id,
            current_level=0, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        await db_session.commit()

        result = await crud.award_bp_xp(db_session, TEST_USER.id, active_season.id, 200)
        assert result["new_level"] == 1
        assert result["new_total_xp"] == 150  # 200 - 50 = 150 remaining

    async def test_no_progress_returns_zero(self, db_session, active_season):
        """If no user progress exists, returns default values."""
        result = await crud.award_bp_xp(db_session, 999, active_season.id, 100)
        assert result["new_total_xp"] == 0
        assert result["new_level"] == 0
        assert result["leveled_up"] is False


# ---------------------------------------------------------------------------
# Snapshot creation
# ---------------------------------------------------------------------------

class TestSnapshots:
    async def test_snapshots_created_for_all_characters(
        self, db_session, active_season,
    ):
        """Snapshots are taken per character at enrollment."""
        # Two characters for user
        char1 = Character(
            id=100, user_id=TEST_USER.id, name="Hero1", level=5, is_npc=False,
        )
        char2 = Character(
            id=101, user_id=TEST_USER.id, name="Hero2", level=3, is_npc=False,
        )
        db_session.add_all([char1, char2])

        attrs1 = CharacterAttribute(character_id=100, pve_kills=10)
        attrs2 = CharacterAttribute(character_id=101, pve_kills=20)
        db_session.add_all([attrs1, attrs2])
        await db_session.commit()

        progress = await crud.get_or_create_user_progress(
            db_session, TEST_USER.id, active_season,
        )
        assert progress.current_level == 0

        from sqlalchemy import select
        result = await db_session.execute(
            select(BpUserSnapshot).where(
                BpUserSnapshot.user_id == TEST_USER.id,
            )
        )
        snapshots = result.scalars().all()
        # 2 characters x 2 types (pve_kills, level) = 4
        assert len(snapshots) == 4

    async def test_npc_characters_excluded(self, db_session, active_season):
        """NPC characters should not get snapshots."""
        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero", level=5, is_npc=False,
        )
        npc = Character(
            id=101, user_id=TEST_USER.id, name="NPC", level=1, is_npc=True,
        )
        db_session.add_all([char, npc])

        attrs = CharacterAttribute(character_id=100, pve_kills=10)
        db_session.add(attrs)
        await db_session.commit()

        await crud.get_or_create_user_progress(
            db_session, TEST_USER.id, active_season,
        )

        from sqlalchemy import select
        result = await db_session.execute(
            select(BpUserSnapshot).where(
                BpUserSnapshot.user_id == TEST_USER.id,
            )
        )
        snapshots = result.scalars().all()
        char_ids = {s.character_id for s in snapshots}
        assert 101 not in char_ids  # NPC excluded
