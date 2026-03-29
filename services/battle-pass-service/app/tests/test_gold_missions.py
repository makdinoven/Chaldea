"""Tests for earn_gold and spend_gold mission progress computation."""

import pytest
from datetime import datetime, timedelta

from models import BpMission, BpUserProgress
from conftest import TEST_USER, Character, GoldTransaction
import crud

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# earn_gold mission progress
# ---------------------------------------------------------------------------

class TestEarnGoldProgress:
    async def test_earn_gold_sums_positive_amounts(self, db_session, active_season):
        """earn_gold counts SUM of positive amounts from gold_transactions."""
        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero", level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.flush()

        # Add positive gold transactions since season start
        for amount in [100, 250, 350]:
            tx = GoldTransaction(
                character_id=100,
                amount=amount,
                balance_after=1000,
                transaction_type="battle_reward",
                created_at=datetime.utcnow() - timedelta(days=1),
            )
            db_session.add(tx)

        # Add a negative transaction (should be ignored)
        tx_neg = GoldTransaction(
            character_id=100,
            amount=-200,
            balance_after=800,
            transaction_type="npc_shop_buy",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(tx_neg)

        await db_session.commit()

        mission = BpMission(
            season_id=active_season.id,
            week_number=1,
            mission_type="earn_gold",
            description="Earn 500 gold",
            target_count=500,
            xp_reward=50,
        )

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, mission,
        )
        assert progress == 700  # 100 + 250 + 350

    async def test_earn_gold_ignores_old_transactions(self, db_session, active_season):
        """Transactions before season_start should not count."""
        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero", level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.flush()

        # Transaction before season start
        old_tx = GoldTransaction(
            character_id=100,
            amount=999,
            balance_after=999,
            transaction_type="battle_reward",
            created_at=active_season.start_date - timedelta(days=5),
        )
        db_session.add(old_tx)

        # Transaction during season
        new_tx = GoldTransaction(
            character_id=100,
            amount=200,
            balance_after=1199,
            transaction_type="battle_reward",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(new_tx)
        await db_session.commit()

        mission = BpMission(
            season_id=active_season.id,
            week_number=1,
            mission_type="earn_gold",
            description="Earn gold",
            target_count=100,
            xp_reward=50,
        )

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, mission,
        )
        assert progress == 200  # Only the new transaction

    async def test_earn_gold_no_transactions(self, db_session, active_season):
        """Zero progress when no transactions exist."""
        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero", level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.commit()

        mission = BpMission(
            season_id=active_season.id,
            week_number=1,
            mission_type="earn_gold",
            description="Earn gold",
            target_count=100,
            xp_reward=50,
        )

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, mission,
        )
        assert progress == 0

    async def test_earn_gold_multi_character(self, db_session, active_season):
        """earn_gold sums across all user characters."""
        char1 = Character(
            id=100, user_id=TEST_USER.id, name="Hero1", level=5, is_npc=False,
        )
        char2 = Character(
            id=101, user_id=TEST_USER.id, name="Hero2", level=3, is_npc=False,
        )
        db_session.add_all([char1, char2])
        await db_session.flush()

        tx1 = GoldTransaction(
            character_id=100, amount=300, balance_after=300,
            transaction_type="battle_reward",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
        tx2 = GoldTransaction(
            character_id=101, amount=200, balance_after=200,
            transaction_type="quest_reward",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add_all([tx1, tx2])
        await db_session.commit()

        mission = BpMission(
            season_id=active_season.id,
            week_number=1,
            mission_type="earn_gold",
            description="Earn gold",
            target_count=400,
            xp_reward=50,
        )

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, mission,
        )
        assert progress == 500  # 300 + 200


# ---------------------------------------------------------------------------
# spend_gold mission progress
# ---------------------------------------------------------------------------

class TestSpendGoldProgress:
    async def test_spend_gold_sums_negative_amounts(self, db_session, active_season):
        """spend_gold counts SUM of ABS(negative amounts) from gold_transactions."""
        char = Character(
            id=100, user_id=TEST_USER.id, name="Hero", level=5, is_npc=False,
        )
        db_session.add(char)
        await db_session.flush()

        for amount in [-100, -250, -50]:
            tx = GoldTransaction(
                character_id=100,
                amount=amount,
                balance_after=500,
                transaction_type="npc_shop_buy",
                created_at=datetime.utcnow() - timedelta(days=1),
            )
            db_session.add(tx)

        # Positive transaction (should be ignored)
        tx_pos = GoldTransaction(
            character_id=100,
            amount=500,
            balance_after=1000,
            transaction_type="battle_reward",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(tx_pos)
        await db_session.commit()

        mission = BpMission(
            season_id=active_season.id,
            week_number=1,
            mission_type="spend_gold",
            description="Spend 300 gold",
            target_count=300,
            xp_reward=40,
        )

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, mission,
        )
        assert progress == 400  # 100 + 250 + 50

    async def test_spend_gold_no_characters(self, db_session, active_season):
        """Zero progress when user has no characters."""
        mission = BpMission(
            season_id=active_season.id,
            week_number=1,
            mission_type="spend_gold",
            description="Spend gold",
            target_count=100,
            xp_reward=40,
        )

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, mission,
        )
        assert progress == 0
