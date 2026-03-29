"""Tests for POST /battle-pass/me/rewards/claim — all reward types and error cases."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from models import (
    BpSeason, BpLevel, BpReward, BpUserProgress, BpUserReward,
)
from conftest import TEST_USER, NO_CHAR_USER, Character, CharacterAttribute

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _setup_claimable(db_session, season, reward_type="gold", reward_value=500,
                           item_id=None, track="free", user_level=1):
    """Create a level+reward and user progress at specified level."""
    level = BpLevel(
        season_id=season.id,
        level_number=1,
        required_xp=100,
    )
    db_session.add(level)
    await db_session.flush()

    reward = BpReward(
        level_id=level.id,
        track=track,
        reward_type=reward_type,
        reward_value=reward_value,
        item_id=item_id,
    )
    db_session.add(reward)

    progress = BpUserProgress(
        user_id=TEST_USER.id,
        season_id=season.id,
        current_level=user_level,
        current_xp=0,
        is_premium=(track == "premium"),
    )
    db_session.add(progress)

    # Character for TEST_USER
    char = Character(
        id=100, user_id=TEST_USER.id, name="Test Hero",
        level=5, is_npc=False,
    )
    db_session.add(char)

    await db_session.commit()
    return level, reward


# ---------------------------------------------------------------------------
# Successful claims for all reward types
# ---------------------------------------------------------------------------

class TestClaimRewardTypes:
    @patch("crud._deliver_gold_xp", new_callable=AsyncMock)
    async def test_claim_gold_reward(
        self, mock_deliver, client, db_session, active_season,
    ):
        await _setup_claimable(db_session, active_season, "gold", 500)

        # Mock get_active_character
        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Test Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["reward_type"] == "gold"
        assert data["reward_value"] == 500
        assert data["delivered_to_character_id"] == 100
        mock_deliver.assert_called_once_with(100, xp=0, gold=500)

    @patch("crud._deliver_gold_xp", new_callable=AsyncMock)
    async def test_claim_xp_reward(
        self, mock_deliver, client, db_session, active_season,
    ):
        await _setup_claimable(db_session, active_season, "xp", 200)

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Test Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reward_type"] == "xp"
        mock_deliver.assert_called_once_with(100, xp=200, gold=0)

    @patch("crud._deliver_item", new_callable=AsyncMock)
    async def test_claim_item_reward(
        self, mock_deliver, client, db_session, active_season,
    ):
        await _setup_claimable(
            db_session, active_season, "item", 1, item_id=42,
        )

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Test Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reward_type"] == "item"
        mock_deliver.assert_called_once_with(100, 42, 1)

    @patch("crud._deliver_diamonds", new_callable=AsyncMock)
    async def test_claim_diamonds_reward(
        self, mock_deliver, client, db_session, active_season,
    ):
        await _setup_claimable(
            db_session, active_season, "diamonds", 50, track="premium",
        )

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Test Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "premium"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reward_type"] == "diamonds"
        mock_deliver.assert_called_once_with(TEST_USER.id, 50)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestClaimRewardErrors:
    async def test_no_active_character_400(
        self, no_char_client, db_session, active_season,
    ):
        """User without current_character_id gets 400."""
        # Setup season with level
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        await db_session.flush()
        reward = BpReward(
            level_id=level.id, track="free", reward_type="gold", reward_value=100,
        )
        db_session.add(reward)
        progress = BpUserProgress(
            user_id=NO_CHAR_USER.id, season_id=active_season.id,
            current_level=1, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        await db_session.commit()

        resp = await no_char_client.post(
            "/battle-pass/me/rewards/claim",
            json={"level_number": 1, "track": "free"},
        )
        assert resp.status_code == 400
        assert "персонажа" in resp.json()["detail"].lower()

    async def test_level_not_reached_400(
        self, client, db_session, active_season,
    ):
        """User at level 0 trying to claim level 1 reward."""
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        await db_session.flush()
        reward = BpReward(
            level_id=level.id, track="free", reward_type="gold", reward_value=100,
        )
        db_session.add(reward)
        # User at level 0
        progress = BpUserProgress(
            user_id=TEST_USER.id, season_id=active_season.id,
            current_level=0, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero",
            level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.commit()

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )
        assert resp.status_code == 400
        assert "не достигнут" in resp.json()["detail"].lower()

    @patch("crud._deliver_gold_xp", new_callable=AsyncMock)
    async def test_already_claimed_409(
        self, mock_deliver, client, db_session, active_season,
    ):
        """Claiming the same reward twice -> 409."""
        level, reward = await _setup_claimable(
            db_session, active_season, "gold", 500,
        )

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Hero"}
            resp1 = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )
            assert resp1.status_code == 200

            resp2 = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )
        assert resp2.status_code == 409
        assert "уже получена" in resp2.json()["detail"].lower()

    async def test_premium_locked_400(
        self, client, db_session, active_season,
    ):
        """Non-premium user trying to claim premium reward -> 400."""
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        await db_session.flush()
        reward = BpReward(
            level_id=level.id, track="premium", reward_type="diamonds",
            reward_value=50,
        )
        db_session.add(reward)
        # Non-premium progress at level 1
        progress = BpUserProgress(
            user_id=TEST_USER.id, season_id=active_season.id,
            current_level=1, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero",
            level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.commit()

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "premium"},
            )
        assert resp.status_code == 400
        assert "премиум" in resp.json()["detail"].lower()

    async def test_grace_period_expired_400(
        self, client, db_session, ended_season,
    ):
        """Season fully ended (past grace) -> 404 (no current season)."""
        resp = await client.post(
            "/battle-pass/me/rewards/claim",
            json={"level_number": 1, "track": "free"},
        )
        assert resp.status_code == 404

    async def test_no_season_404(self, client):
        resp = await client.post(
            "/battle-pass/me/rewards/claim",
            json={"level_number": 1, "track": "free"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reward delivery verification
# ---------------------------------------------------------------------------

class TestRewardDelivery:
    @patch("crud._deliver_gold_xp", new_callable=AsyncMock)
    async def test_gold_delivery_call(
        self, mock_deliver, client, db_session, active_season,
    ):
        """Verify gold reward calls _deliver_gold_xp with correct params."""
        await _setup_claimable(db_session, active_season, "gold", 1000)

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )
        assert resp.status_code == 200
        mock_deliver.assert_called_once_with(100, xp=0, gold=1000)

    @patch("crud._deliver_diamonds", new_callable=AsyncMock)
    async def test_diamonds_delivery_call(
        self, mock_deliver, client, db_session, active_season,
    ):
        """Verify diamonds reward calls _deliver_diamonds with user_id."""
        await _setup_claimable(
            db_session, active_season, "diamonds", 100, track="premium",
        )

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "premium"},
            )
        assert resp.status_code == 200
        mock_deliver.assert_called_once_with(TEST_USER.id, 100)


# ---------------------------------------------------------------------------
# Grace period claiming
# ---------------------------------------------------------------------------

class TestGracePeriodClaiming:
    @patch("crud._deliver_gold_xp", new_callable=AsyncMock)
    async def test_can_claim_during_grace(
        self, mock_deliver, db_session, client, grace_season,
    ):
        """Rewards can still be claimed during grace period."""
        level = BpLevel(
            season_id=grace_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        await db_session.flush()
        reward = BpReward(
            level_id=level.id, track="free", reward_type="gold", reward_value=100,
        )
        db_session.add(reward)
        progress = BpUserProgress(
            user_id=TEST_USER.id, season_id=grace_season.id,
            current_level=1, current_xp=0, is_premium=False,
        )
        db_session.add(progress)
        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero",
            level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.commit()

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


# ---------------------------------------------------------------------------
# Premium activation stub
# ---------------------------------------------------------------------------

class TestPremiumActivation:
    async def test_premium_stub_501(self, client):
        resp = await client.post("/battle-pass/me/premium/activate")
        assert resp.status_code == 501
