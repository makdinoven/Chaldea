"""Tests for earn_gold and spend_gold mission progress computation.

FEAT-181: progress is read from the world-economy ledger
(econ_postings + econ_accounts(kind='character')), genesis excluded.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from sqlalchemy import select

from models import BpMission, BpLevel, BpReward, BpUserProgress, BpUserReward
from conftest import TEST_USER, Character, EconAccount, EconOperation, EconPosting
import crud

pytestmark = pytest.mark.asyncio

WORLD_ACC = 1
REGION_ACC = 2


def _recent():
    return datetime.utcnow() - timedelta(days=1)


async def _setup_accounts(db, char_ids):
    """World + region treasuries and one character account per char id
    (account id = 100 + char id)."""
    db.add_all([
        EconAccount(id=WORLD_ACC, kind="world_treasury", ref_id=0),
        EconAccount(id=REGION_ACC, kind="region_treasury", ref_id=5),
    ])
    for cid in char_ids:
        db.add(Character(id=cid, user_id=TEST_USER.id, name=f"Hero{cid}", level=5, is_npc=False))
        db.add(EconAccount(id=100 + cid, kind="character", ref_id=cid))
    await db.flush()


_next_op = [1000]


async def _post(db, op_type, frm, to, amount, created_at=None):
    _next_op[0] += 1
    op_id = _next_op[0]
    when = created_at or _recent()
    db.add(EconOperation(id=op_id, op_type=op_type, created_at=when))
    db.add(EconPosting(
        operation_id=op_id, from_account_id=frm, to_account_id=to,
        amount=amount, created_at=when,
    ))
    await db.flush()


def _mission(season, mission_type, target=100):
    return BpMission(
        season_id=season.id, week_number=1, mission_type=mission_type,
        description="gold", target_count=target, xp_reward=50,
    )


# ---------------------------------------------------------------------------
# earn_gold mission progress
# ---------------------------------------------------------------------------

class TestEarnGoldProgress:
    async def test_earn_gold_sums_postings_to_the_character(self, db_session, active_season):
        await _setup_accounts(db_session, [100])
        for amount in [100, 250, 350]:
            await _post(db_session, "battle_reward", REGION_ACC, 200, amount)
        # Outgoing posting is spending, not earning
        await _post(db_session, "npc_shop_buy", 200, REGION_ACC, 200)
        await db_session.commit()

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "earn_gold"),
        )
        assert progress == 700

    async def test_earn_gold_excludes_genesis(self, db_session, active_season):
        """The ledger-opening snapshot is not 'earned' gold."""
        await _setup_accounts(db_session, [100])
        await _post(db_session, "genesis", WORLD_ACC, 200, 5000)
        await _post(db_session, "battle_pass_reward", WORLD_ACC, 200, 40)
        await db_session.commit()

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "earn_gold"),
        )
        assert progress == 40

    async def test_earn_gold_ignores_old_postings(self, db_session, active_season):
        await _setup_accounts(db_session, [100])
        await _post(
            db_session, "battle_reward", REGION_ACC, 200, 999,
            created_at=active_season.start_date - timedelta(days=5),
        )
        await _post(db_session, "battle_reward", REGION_ACC, 200, 200)
        await db_session.commit()

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "earn_gold"),
        )
        assert progress == 200

    async def test_earn_gold_no_postings(self, db_session, active_season):
        await _setup_accounts(db_session, [100])
        await db_session.commit()

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "earn_gold"),
        )
        assert progress == 0

    async def test_earn_gold_multi_character_and_trade_between_them(self, db_session, active_season):
        """Sums across all user characters; a trade from another player counts as earned."""
        await _setup_accounts(db_session, [100, 101])
        db_session.add(EconAccount(id=999, kind="character", ref_id=555))  # someone else
        await db_session.flush()
        await _post(db_session, "battle_reward", REGION_ACC, 200, 300)
        await _post(db_session, "trade", 999, 201, 200)
        # Gold paid to another player's character is not ours
        await _post(db_session, "battle_reward", REGION_ACC, 999, 7777)
        await db_session.commit()

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "earn_gold"),
        )
        assert progress == 500

    async def test_earn_gold_ignores_non_character_account_with_same_ref_id(
        self, db_session, active_season,
    ):
        """A region treasury whose ref_id equals a character id is not that character."""
        await _setup_accounts(db_session, [100])
        db_session.add(EconAccount(id=50, kind="region_treasury", ref_id=100))
        await db_session.flush()
        await _post(db_session, "npc_shop_buy", 200, 50, 80)
        await db_session.commit()

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "earn_gold"),
        )
        assert progress == 0


# ---------------------------------------------------------------------------
# spend_gold mission progress
# ---------------------------------------------------------------------------

class TestSpendGoldProgress:
    async def test_spend_gold_sums_postings_from_the_character(self, db_session, active_season):
        await _setup_accounts(db_session, [100])
        for amount in [100, 250, 50]:
            await _post(db_session, "npc_shop_buy", 200, REGION_ACC, amount)
        # Incoming posting is ignored
        await _post(db_session, "battle_reward", REGION_ACC, 200, 500)
        await db_session.commit()

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "spend_gold", 300),
        )
        assert progress == 400

    async def test_spend_gold_ignores_old_postings(self, db_session, active_season):
        await _setup_accounts(db_session, [100])
        await _post(
            db_session, "teleport", 200, REGION_ACC, 999,
            created_at=active_season.start_date - timedelta(days=1),
        )
        await _post(db_session, "teleport", 200, REGION_ACC, 30)
        await db_session.commit()

        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "spend_gold"),
        )
        assert progress == 30

    async def test_spend_gold_no_characters(self, db_session, active_season):
        progress = await crud.compute_mission_progress(
            db_session, TEST_USER.id, active_season, _mission(active_season, "spend_gold"),
        )
        assert progress == 0


# ---------------------------------------------------------------------------
# FEAT-181 Q4: ledger edge cases not covered above
# ---------------------------------------------------------------------------

async def _earned_and_spent(db, season):
    earned = await crud.compute_mission_progress(
        db, TEST_USER.id, season, _mission(season, "earn_gold"),
    )
    spent = await crud.compute_mission_progress(
        db, TEST_USER.id, season, _mission(season, "spend_gold"),
    )
    return earned, spent


class TestLedgerProgressEdgeCases:
    async def test_spend_gold_excludes_genesis(self, db_session, active_season):
        """A genesis leg out of a character is not spending."""
        await _setup_accounts(db_session, [100])
        await _post(db_session, "genesis", 200, WORLD_ACC, 3000)
        await _post(db_session, "npc_shop_buy", 200, REGION_ACC, 25)
        await db_session.commit()

        assert await _earned_and_spent(db_session, active_season) == (0, 25)

    async def test_refund_and_trade_counted_on_both_sides(self, db_session, active_season):
        """As before the ledger: an auction bid is spent, its refund is earned;
        a trade to another player is spent, a trade from them is earned."""
        await _setup_accounts(db_session, [100])
        escrow, other = 300, 999
        db_session.add_all([
            EconAccount(id=escrow, kind="auction_escrow", ref_id=0),
            EconAccount(id=other, kind="character", ref_id=555),
        ])
        await db_session.flush()
        await _post(db_session, "auction_bid", 200, escrow, 400)
        await _post(db_session, "auction_refund", escrow, 200, 400)
        await _post(db_session, "trade", 200, other, 150)
        await _post(db_session, "trade", other, 200, 60)
        await db_session.commit()

        assert await _earned_and_spent(db_session, active_season) == (460, 550)

    async def test_posting_exactly_at_season_start_counts(self, db_session, active_season):
        """The boundary is inclusive (created_at >= start_date)."""
        await _setup_accounts(db_session, [100])
        start = active_season.start_date
        just_before = start - timedelta(seconds=1)
        await _post(db_session, "battle_reward", REGION_ACC, 200, 11, created_at=start)
        await _post(db_session, "battle_reward", REGION_ACC, 200, 500, created_at=just_before)
        await _post(db_session, "teleport", 200, REGION_ACC, 7, created_at=start)
        await _post(db_session, "teleport", 200, REGION_ACC, 900, created_at=just_before)
        await db_session.commit()

        assert await _earned_and_spent(db_session, active_season) == (11, 7)

    async def test_transfer_between_own_characters_counts_both_ways(
        self, db_session, active_season,
    ):
        """Kept semantics: gold moved between two own characters is both
        spent (by one) and earned (by the other)."""
        await _setup_accounts(db_session, [100, 101])
        await _post(db_session, "trade", 200, 201, 90)
        await db_session.commit()

        assert await _earned_and_spent(db_session, active_season) == (90, 90)

    async def test_injection_like_op_type_is_plain_data(self, db_session, active_season):
        """Values are bound parameters: a quote-laden op_type is just data."""
        await _setup_accounts(db_session, [100])
        await _post(db_session, "x' OR '1'='1", REGION_ACC, 200, 13)
        await db_session.commit()

        assert await _earned_and_spent(db_session, active_season) == (13, 0)


# ---------------------------------------------------------------------------
# FEAT-184: bank operations do not count as earning or spending
# ---------------------------------------------------------------------------

BANK_ACC = 400
VAULT_ACC = 401


async def _setup_bank(db):
    db.add_all([
        EconAccount(id=BANK_ACC, kind="bank", ref_id=5),
        EconAccount(id=VAULT_ACC, kind="bank_deposits", ref_id=5),
    ])
    await db.flush()


class TestBankOpsExcluded:
    async def test_deposit_withdraw_cycle_does_not_change_progress(
        self, db_session, active_season,
    ):
        """Cycling gold through a deposit cannot farm earn/spend missions."""
        await _setup_accounts(db_session, [100])
        await _setup_bank(db_session)
        await _post(db_session, "battle_reward", REGION_ACC, 200, 40)
        await db_session.commit()
        before = await _earned_and_spent(db_session, active_season)

        for _ in range(3):
            await _post(db_session, "bank_deposit", 200, VAULT_ACC, 1000)
            await _post(db_session, "bank_withdraw", VAULT_ACC, 200, 1000)
        await db_session.commit()

        assert before == (40, 0)
        assert await _earned_and_spent(db_session, active_season) == before

    async def test_loan_issue_repay_collect_excluded(self, db_session, active_season):
        await _setup_accounts(db_session, [100])
        await _setup_bank(db_session)
        await _post(db_session, "loan_issue", BANK_ACC, 200, 500)
        await _post(db_session, "loan_repay", 200, BANK_ACC, 300)
        await _post(db_session, "loan_collect", 200, BANK_ACC, 200)
        await db_session.commit()

        assert await _earned_and_spent(db_session, active_season) == (0, 0)

    async def test_bank_transfer_with_commission_excluded(self, db_session, active_season):
        """A send-to-player from the wallet (main + commission legs) is not
        spending; the recipient's deposit is not a character account anyway."""
        await _setup_accounts(db_session, [100])
        await _setup_bank(db_session)
        await _post(db_session, "bank_transfer", 200, VAULT_ACC, 100)
        await _post(db_session, "bank_transfer", 200, REGION_ACC, 2)
        await db_session.commit()

        assert await _earned_and_spent(db_session, active_season) == (0, 0)

    async def test_non_bank_ops_still_counted_alongside_bank_ops(
        self, db_session, active_season,
    ):
        await _setup_accounts(db_session, [100])
        await _setup_bank(db_session)
        await _post(db_session, "bank_deposit", 200, VAULT_ACC, 700)
        await _post(db_session, "npc_shop_buy", 200, REGION_ACC, 25)
        await _post(db_session, "quest_reward", REGION_ACC, 200, 15)
        await _post(db_session, "genesis", WORLD_ACC, 200, 9000)
        await db_session.commit()

        assert await _earned_and_spent(db_session, active_season) == (15, 25)

    async def test_excluded_op_types_cover_all_bank_ops(self):
        """Mirrors econ_core.BANK_OP_TYPES (FEAT-184 3.4) plus genesis."""
        assert set(crud.LEDGER_EXCLUDED_OP_TYPES) == {
            "genesis",
            "bank_deposit", "bank_withdraw", "bank_transfer", "bank_tick",
            "bank_capital", "loan_issue", "loan_repay", "loan_collect",
        }


# ---------------------------------------------------------------------------
# FEAT-181 Q4: claim -> add_rewards HTTP payload (httpx mocked)
# ---------------------------------------------------------------------------

def _mock_http_client(post_side_effect=None):
    resp = MagicMock(status_code=200, raise_for_status=MagicMock())
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=resp, side_effect=post_side_effect)
    return client


async def _claimable_gold(db, season, track="free", value=500):
    level = BpLevel(season_id=season.id, level_number=1, required_xp=100)
    db.add(level)
    await db.flush()
    db.add(BpReward(level_id=level.id, track=track, reward_type="gold", reward_value=value))
    progress = BpUserProgress(
        user_id=TEST_USER.id, season_id=season.id, current_level=1,
        current_xp=0, is_premium=(track == "premium"),
    )
    db.add(progress)
    await db.commit()
    return level, progress


class TestClaimSendsLedgerFields:
    async def test_gold_claim_payload_end_to_end(self, db_session, active_season):
        level, progress = await _claimable_gold(db_session, active_season, value=500)
        http = _mock_http_client()
        with patch("crud.httpx.AsyncClient", return_value=http):
            result = await crud.claim_reward(
                db_session, TEST_USER.id, active_season, progress, 1, "free", 100, "Hero",
            )

        assert result["ok"] is True
        http.post.assert_called_once()
        assert http.post.call_args.args[0].endswith("/characters/100/add_rewards")
        assert http.post.call_args.kwargs["json"] == {
            "xp": 0,
            "gold": 500,
            "xp_source": "character_xp_pass_bonus",
            "gold_op_type": "battle_pass_reward",
            "payer": "world",
            "idempotency_key": f"battle_pass_reward:u:{TEST_USER.id}:l:{level.id}:free",
        }

    async def test_premium_track_key_differs_from_free(self, db_session, active_season):
        level, progress = await _claimable_gold(db_session, active_season, track="premium")
        http = _mock_http_client()
        with patch("crud.httpx.AsyncClient", return_value=http):
            await crud.claim_reward(
                db_session, TEST_USER.id, active_season, progress, 1, "premium", 100, "Hero",
            )
        key = http.post.call_args.kwargs["json"]["idempotency_key"]
        assert key == f"battle_pass_reward:u:{TEST_USER.id}:l:{level.id}:premium"
        assert key != crud.reward_idempotency_key(TEST_USER.id, level.id, "free")

    async def test_failed_delivery_retry_reuses_the_same_key(self, db_session, active_season):
        """If character-service fails, the claim is not recorded; the retry
        sends the same key, so a payment that did land is not paid twice."""
        level, progress = await _claimable_gold(db_session, active_season)
        level_id = level.id

        failing =_mock_http_client(post_side_effect=httpx.ReadTimeout("timeout"))
        with patch("crud.httpx.AsyncClient", return_value=failing):
            with pytest.raises(Exception):
                await crud.claim_reward(
                    db_session, TEST_USER.id, active_season, progress, 1, "free", 100, "Hero",
                )
        await db_session.rollback()
        rows = (await db_session.execute(select(BpUserReward))).scalars().all()
        assert rows == []
        await db_session.refresh(progress)
        await db_session.refresh(active_season)

        ok =_mock_http_client()
        with patch("crud.httpx.AsyncClient", return_value=ok):
            result = await crud.claim_reward(
                db_session, TEST_USER.id, active_season, progress, 1, "free", 100, "Hero",
            )
        assert result["ok"] is True
        first_key = failing.post.call_args.kwargs["json"]["idempotency_key"]
        second_key = ok.post.call_args.kwargs["json"]["idempotency_key"]
        assert first_key == second_key == crud.reward_idempotency_key(
            TEST_USER.id, level_id, "free",
        )
