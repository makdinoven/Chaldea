"""Tests for cosmetic reward types (frame, chat_background) in battle-pass-service.

Covers:
- RewardIn schema validation for cosmetic types
- RewardIn schema still accepts old types without cosmetic_slug
- Admin bulk upsert with cosmetic rewards
- deliver_reward calls user-service unlock endpoint (mocked httpx)
- cosmetic_slug field included in season/levels API response
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from pydantic import ValidationError

from schemas import RewardIn
from models import BpSeason, BpLevel, BpReward, BpUserProgress, BpUserReward
from conftest import TEST_USER, ADMIN_USER, Character, CharacterAttribute

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# RewardIn schema — cosmetic types accepted
# ---------------------------------------------------------------------------

class TestRewardInCosmeticAccepted:
    def test_frame_with_cosmetic_slug(self):
        reward = RewardIn(
            reward_type="frame",
            reward_value=1,
            cosmetic_slug="golden_glow",
        )
        assert reward.reward_type == "frame"
        assert reward.cosmetic_slug == "golden_glow"

    def test_chat_background_with_cosmetic_slug(self):
        reward = RewardIn(
            reward_type="chat_background",
            reward_value=1,
            cosmetic_slug="dark_blue_gradient",
        )
        assert reward.reward_type == "chat_background"
        assert reward.cosmetic_slug == "dark_blue_gradient"


# ---------------------------------------------------------------------------
# RewardIn schema — cosmetic types rejected without cosmetic_slug
# ---------------------------------------------------------------------------

class TestRewardInCosmeticRejected:
    def test_frame_without_cosmetic_slug_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            RewardIn(
                reward_type="frame",
                reward_value=1,
            )
        errors = exc_info.value.errors()
        assert any("cosmetic_slug" in str(e) for e in errors)

    def test_chat_background_without_cosmetic_slug_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            RewardIn(
                reward_type="chat_background",
                reward_value=1,
            )
        errors = exc_info.value.errors()
        assert any("cosmetic_slug" in str(e) for e in errors)

    def test_frame_with_empty_cosmetic_slug_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            RewardIn(
                reward_type="frame",
                reward_value=1,
                cosmetic_slug="",
            )
        errors = exc_info.value.errors()
        assert any("cosmetic_slug" in str(e) for e in errors)

    def test_chat_background_with_none_cosmetic_slug_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            RewardIn(
                reward_type="chat_background",
                reward_value=1,
                cosmetic_slug=None,
            )
        errors = exc_info.value.errors()
        assert any("cosmetic_slug" in str(e) for e in errors)


# ---------------------------------------------------------------------------
# RewardIn schema — old types still work without cosmetic_slug
# ---------------------------------------------------------------------------

class TestRewardInOldTypes:
    def test_gold_without_cosmetic_slug(self):
        reward = RewardIn(reward_type="gold", reward_value=500)
        assert reward.reward_type == "gold"
        assert reward.cosmetic_slug is None

    def test_xp_without_cosmetic_slug(self):
        reward = RewardIn(reward_type="xp", reward_value=200)
        assert reward.reward_type == "xp"
        assert reward.cosmetic_slug is None

    def test_item_without_cosmetic_slug(self):
        reward = RewardIn(reward_type="item", reward_value=1, item_id=42)
        assert reward.reward_type == "item"
        assert reward.cosmetic_slug is None

    def test_diamonds_without_cosmetic_slug(self):
        reward = RewardIn(reward_type="diamonds", reward_value=50)
        assert reward.reward_type == "diamonds"
        assert reward.cosmetic_slug is None

    def test_invalid_reward_type_raises(self):
        with pytest.raises(ValidationError):
            RewardIn(reward_type="unknown_type", reward_value=1)


# ---------------------------------------------------------------------------
# Admin bulk upsert with cosmetic rewards
# ---------------------------------------------------------------------------

class TestAdminBulkUpsertCosmetics:
    async def test_upsert_levels_with_frame_reward(
        self, admin_client, db_session, active_season,
    ):
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
                            {
                                "reward_type": "frame",
                                "reward_value": 1,
                                "cosmetic_slug": "golden_glow",
                            },
                        ],
                    },
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        rewards = data[0]["rewards"]
        # Should have 2 rewards: free gold + premium frame
        assert len(rewards) == 2
        frame_rewards = [r for r in rewards if r["reward_type"] == "frame"]
        assert len(frame_rewards) == 1
        assert frame_rewards[0]["cosmetic_slug"] == "golden_glow"

    async def test_upsert_levels_with_background_reward(
        self, admin_client, db_session, active_season,
    ):
        resp = await admin_client.put(
            f"/battle-pass/admin/seasons/{active_season.id}/levels",
            json={
                "levels": [
                    {
                        "level_number": 1,
                        "required_xp": 100,
                        "free_rewards": [],
                        "premium_rewards": [
                            {
                                "reward_type": "chat_background",
                                "reward_value": 1,
                                "cosmetic_slug": "fire_gradient",
                            },
                        ],
                    },
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        rewards = data[0]["rewards"]
        bg_rewards = [r for r in rewards if r["reward_type"] == "chat_background"]
        assert len(bg_rewards) == 1
        assert bg_rewards[0]["cosmetic_slug"] == "fire_gradient"

    async def test_upsert_mixed_cosmetic_and_regular_rewards(
        self, admin_client, db_session, active_season,
    ):
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
                            {
                                "reward_type": "frame",
                                "reward_value": 1,
                                "cosmetic_slug": "silver_shimmer",
                            },
                        ],
                    },
                    {
                        "level_number": 2,
                        "required_xp": 200,
                        "free_rewards": [
                            {"reward_type": "xp", "reward_value": 100},
                        ],
                        "premium_rewards": [
                            {
                                "reward_type": "chat_background",
                                "reward_value": 1,
                                "cosmetic_slug": "ocean_depth",
                            },
                        ],
                    },
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Level 1 premium = frame
        lvl1_rewards = data[0]["rewards"]
        frame_r = [r for r in lvl1_rewards if r["reward_type"] == "frame"]
        assert len(frame_r) == 1
        assert frame_r[0]["cosmetic_slug"] == "silver_shimmer"
        # Level 2 premium = chat_background
        lvl2_rewards = data[1]["rewards"]
        bg_r = [r for r in lvl2_rewards if r["reward_type"] == "chat_background"]
        assert len(bg_r) == 1
        assert bg_r[0]["cosmetic_slug"] == "ocean_depth"


# ---------------------------------------------------------------------------
# deliver_reward — cosmetic types call user-service unlock endpoint
# ---------------------------------------------------------------------------

class TestDeliverCosmeticReward:
    @patch("crud._deliver_cosmetic", new_callable=AsyncMock)
    async def test_claim_frame_reward_calls_deliver_cosmetic(
        self, mock_deliver, client, db_session, active_season,
    ):
        """Claiming a frame reward calls _deliver_cosmetic with type='frame'."""
        # Setup: level with frame reward
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        await db_session.flush()

        reward = BpReward(
            level_id=level.id,
            track="free",
            reward_type="frame",
            reward_value=1,
            cosmetic_slug="golden_glow",
        )
        db_session.add(reward)

        progress = BpUserProgress(
            user_id=TEST_USER.id,
            season_id=active_season.id,
            current_level=1,
            current_xp=0,
            is_premium=False,
        )
        db_session.add(progress)

        char = Character(
            id=100, user_id=TEST_USER.id, name="Test Hero",
            level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.commit()

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Test Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["reward_type"] == "frame"
        mock_deliver.assert_called_once_with(TEST_USER.id, "frame", "golden_glow")

    @patch("crud._deliver_cosmetic", new_callable=AsyncMock)
    async def test_claim_chat_background_reward_calls_deliver_cosmetic(
        self, mock_deliver, client, db_session, active_season,
    ):
        """Claiming a chat_background reward calls _deliver_cosmetic with type='background'."""
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        await db_session.flush()

        reward = BpReward(
            level_id=level.id,
            track="free",
            reward_type="chat_background",
            reward_value=1,
            cosmetic_slug="fire_gradient",
        )
        db_session.add(reward)

        progress = BpUserProgress(
            user_id=TEST_USER.id,
            season_id=active_season.id,
            current_level=1,
            current_xp=0,
            is_premium=False,
        )
        db_session.add(progress)

        char = Character(
            id=100, user_id=TEST_USER.id, name="Test Hero",
            level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.commit()

        with patch("crud.get_active_character", new_callable=AsyncMock) as mock_char:
            mock_char.return_value = {"id": 100, "name": "Test Hero"}
            resp = await client.post(
                "/battle-pass/me/rewards/claim",
                json={"level_number": 1, "track": "free"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["reward_type"] == "chat_background"
        mock_deliver.assert_called_once_with(TEST_USER.id, "background", "fire_gradient")

    @patch("crud.httpx.AsyncClient")
    async def test_deliver_cosmetic_sends_correct_payload(self, mock_client_cls):
        """_deliver_cosmetic POSTs to user-service with correct JSON body."""
        import crud

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        await crud._deliver_cosmetic(user_id=1, cosmetic_type="frame", cosmetic_slug="golden_glow")

        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        url = call_args[0][0]
        json_body = call_args[1]["json"]

        assert "/users/internal/1/cosmetics/unlock" in url
        assert json_body["cosmetic_type"] == "frame"
        assert json_body["cosmetic_slug"] == "golden_glow"
        assert json_body["source"] == "battlepass"

    @patch("crud.httpx.AsyncClient")
    async def test_deliver_cosmetic_background_payload(self, mock_client_cls):
        """_deliver_cosmetic for background sends cosmetic_type='background'."""
        import crud

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        await crud._deliver_cosmetic(user_id=5, cosmetic_type="background", cosmetic_slug="ocean_depth")

        call_args = mock_client_instance.post.call_args
        json_body = call_args[1]["json"]
        assert json_body["cosmetic_type"] == "background"
        assert json_body["cosmetic_slug"] == "ocean_depth"


# ---------------------------------------------------------------------------
# cosmetic_slug in season/levels API response
# ---------------------------------------------------------------------------

class TestCosmeticSlugInResponse:
    async def test_cosmetic_slug_in_current_season_response(
        self, client, db_session, active_season,
    ):
        """GET /battle-pass/seasons/current includes cosmetic_slug in rewards."""
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        await db_session.flush()

        # Free reward: gold (no cosmetic_slug)
        gold_reward = BpReward(
            level_id=level.id, track="free",
            reward_type="gold", reward_value=500,
        )
        db_session.add(gold_reward)

        # Premium reward: frame (with cosmetic_slug)
        frame_reward = BpReward(
            level_id=level.id, track="premium",
            reward_type="frame", reward_value=1,
            cosmetic_slug="rainbow_border",
        )
        db_session.add(frame_reward)
        await db_session.commit()

        resp = await client.get("/battle-pass/seasons/current")
        assert resp.status_code == 200
        data = resp.json()
        levels = data["levels"]
        assert len(levels) >= 1

        lvl = levels[0]
        # Check free rewards — gold has no cosmetic_slug
        free_rewards = lvl["free_rewards"]
        assert len(free_rewards) >= 1
        gold_r = [r for r in free_rewards if r["reward_type"] == "gold"][0]
        assert gold_r["cosmetic_slug"] is None

        # Check premium rewards — frame has cosmetic_slug
        premium_rewards = lvl["premium_rewards"]
        assert len(premium_rewards) >= 1
        frame_r = [r for r in premium_rewards if r["reward_type"] == "frame"][0]
        assert frame_r["cosmetic_slug"] == "rainbow_border"

    async def test_cosmetic_slug_in_admin_levels_response(
        self, admin_client, db_session, active_season,
    ):
        """GET /battle-pass/admin/seasons/{id}/levels includes cosmetic_slug."""
        level = BpLevel(
            season_id=active_season.id, level_number=1, required_xp=100,
        )
        db_session.add(level)
        await db_session.flush()

        reward = BpReward(
            level_id=level.id, track="premium",
            reward_type="chat_background", reward_value=1,
            cosmetic_slug="mystic_purple",
        )
        db_session.add(reward)
        await db_session.commit()

        resp = await admin_client.get(
            f"/battle-pass/admin/seasons/{active_season.id}/levels"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        rewards = data[0]["rewards"]
        bg_r = [r for r in rewards if r["reward_type"] == "chat_background"]
        assert len(bg_r) == 1
        assert bg_r[0]["cosmetic_slug"] == "mystic_purple"
