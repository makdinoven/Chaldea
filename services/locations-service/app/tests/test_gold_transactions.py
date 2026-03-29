"""
Task #13 — QA: gold_transactions tests (locations-service).

Tests that gold modifications in NPC shops and quests create gold_transaction records:
1. Shop buy creates a negative gold_transaction (type "charisma_shop_buy")
2. Shop sell creates a positive gold_transaction (type "charisma_shop_sell")
3. Quest reward gold creates a transaction (type "quest_reward")
4. _log_gold_transaction helper — correct fields, exception safety
5. deduct_currency and add_currency log transactions
"""

import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
import pytest_asyncio

import crud


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(*values):
    """Create a mock row that supports index access."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _result_with_row(row_data):
    result = MagicMock()
    result.fetchone.return_value = row_data
    return result


# ---------------------------------------------------------------------------
# Tests: _log_gold_transaction helper
# ---------------------------------------------------------------------------


class TestLogGoldTransactionHelper:
    """Tests for the async _log_gold_transaction helper."""

    @pytest.mark.asyncio
    async def test_correct_fields_in_insert(self):
        """_log_gold_transaction executes INSERT with correct parameters."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        await crud._log_gold_transaction(
            session,
            character_id=1,
            amount=-100,
            balance_after=400,
            transaction_type="charisma_shop_buy",
            source="NPC shop",
            metadata={"npc_id": 5, "item_id": 10},
        )

        # Verify execute was called with INSERT INTO gold_transactions
        session.execute.assert_called_once()
        call_args = session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "gold_transactions" in sql_text.lower()

        params = call_args[0][1]
        assert params["character_id"] == 1
        assert params["amount"] == -100
        assert params["balance_after"] == 400
        assert params["transaction_type"] == "charisma_shop_buy"
        assert params["source"] == "NPC shop"
        meta = json.loads(params["metadata"])
        assert meta["npc_id"] == 5

        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_metadata_stored_as_none(self):
        """When metadata is None, it is stored as None (not JSON 'null')."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        await crud._log_gold_transaction(
            session,
            character_id=1,
            amount=50,
            balance_after=550,
            transaction_type="test",
            source=None,
            metadata=None,
        )

        params = session.execute.call_args[0][1]
        assert params["source"] is None
        assert params["metadata"] is None

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self):
        """_log_gold_transaction catches exceptions — does not re-raise."""
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=Exception("DB error"))

        # Should NOT raise
        await crud._log_gold_transaction(
            session,
            character_id=1,
            amount=50,
            balance_after=550,
            transaction_type="test",
        )


# ---------------------------------------------------------------------------
# Tests: deduct_currency logs charisma_shop_buy
# ---------------------------------------------------------------------------


class TestDeductCurrencyGoldTransaction:
    """Tests that deduct_currency calls _log_gold_transaction."""

    @pytest.mark.asyncio
    async def test_deduct_currency_logs_negative_transaction(self):
        """deduct_currency creates a negative gold_transaction."""
        session = AsyncMock()

        # Mock UPDATE rowcount > 0 (success)
        update_result = MagicMock()
        update_result.rowcount = 1

        # Mock SELECT for new balance
        balance_result = MagicMock()
        balance_result.fetchone.return_value = _row(900)

        session.execute = AsyncMock(side_effect=[update_result, balance_result])
        session.commit = AsyncMock()

        with patch.object(crud, "_log_gold_transaction", new_callable=AsyncMock) as mock_log:
            new_balance = await crud.deduct_currency(
                session, character_id=1, amount=100,
                transaction_type="charisma_shop_buy",
                source="NPC shop buy (npc_id=5)",
                metadata={"npc_id": 5},
            )

        assert new_balance == 900
        mock_log.assert_called_once_with(
            session,
            character_id=1,
            amount=-100,
            balance_after=900,
            transaction_type="charisma_shop_buy",
            source="NPC shop buy (npc_id=5)",
            metadata={"npc_id": 5},
        )

    @pytest.mark.asyncio
    async def test_deduct_currency_insufficient_gold_no_transaction(self):
        """deduct_currency returns None and does not log when gold is insufficient."""
        session = AsyncMock()

        update_result = MagicMock()
        update_result.rowcount = 0  # Insufficient gold

        session.execute = AsyncMock(return_value=update_result)
        session.commit = AsyncMock()

        with patch.object(crud, "_log_gold_transaction", new_callable=AsyncMock) as mock_log:
            result = await crud.deduct_currency(
                session, character_id=1, amount=9999,
                transaction_type="charisma_shop_buy",
            )

        assert result is None
        mock_log.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: add_currency logs charisma_shop_sell / quest_reward
# ---------------------------------------------------------------------------


class TestAddCurrencyGoldTransaction:
    """Tests that add_currency calls _log_gold_transaction."""

    @pytest.mark.asyncio
    async def test_add_currency_logs_positive_transaction(self):
        """add_currency creates a positive gold_transaction."""
        session = AsyncMock()

        # Mock UPDATE (always succeeds for add)
        update_result = MagicMock()

        # Mock SELECT for new balance
        balance_result = MagicMock()
        balance_result.fetchone.return_value = _row(1500)

        session.execute = AsyncMock(side_effect=[update_result, balance_result])
        session.commit = AsyncMock()

        with patch.object(crud, "_log_gold_transaction", new_callable=AsyncMock) as mock_log:
            new_balance = await crud.add_currency(
                session, character_id=1, amount=500,
                transaction_type="charisma_shop_sell",
                source="NPC shop sell (npc_id=5)",
                metadata={"npc_id": 5, "item_id": 10},
            )

        assert new_balance == 1500
        mock_log.assert_called_once_with(
            session,
            character_id=1,
            amount=500,
            balance_after=1500,
            transaction_type="charisma_shop_sell",
            source="NPC shop sell (npc_id=5)",
            metadata={"npc_id": 5, "item_id": 10},
        )

    @pytest.mark.asyncio
    async def test_quest_reward_logs_transaction(self):
        """add_currency with type quest_reward logs correctly."""
        session = AsyncMock()

        update_result = MagicMock()
        balance_result = MagicMock()
        balance_result.fetchone.return_value = _row(2000)

        session.execute = AsyncMock(side_effect=[update_result, balance_result])
        session.commit = AsyncMock()

        with patch.object(crud, "_log_gold_transaction", new_callable=AsyncMock) as mock_log:
            new_balance = await crud.add_currency(
                session, character_id=3, amount=200,
                transaction_type="quest_reward",
                source="Quest completion (quest_id=7)",
                metadata={"quest_id": 7},
            )

        assert new_balance == 2000
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["transaction_type"] == "quest_reward"
        assert call_kwargs[1]["amount"] == 200
        assert call_kwargs[1]["character_id"] == 3

    @pytest.mark.asyncio
    async def test_add_currency_no_log_when_balance_none(self):
        """add_currency does not log when character not found (balance is None)."""
        session = AsyncMock()

        update_result = MagicMock()
        balance_result = MagicMock()
        balance_result.fetchone.return_value = None  # Character not found

        session.execute = AsyncMock(side_effect=[update_result, balance_result])
        session.commit = AsyncMock()

        with patch.object(crud, "_log_gold_transaction", new_callable=AsyncMock) as mock_log:
            new_balance = await crud.add_currency(
                session, character_id=999, amount=100,
                transaction_type="charisma_shop_sell",
            )

        assert new_balance is None
        mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_shop_buy_refund_logs_transaction(self):
        """Refund after failed inventory add creates a positive transaction."""
        session = AsyncMock()

        update_result = MagicMock()
        balance_result = MagicMock()
        balance_result.fetchone.return_value = _row(1000)

        session.execute = AsyncMock(side_effect=[update_result, balance_result])
        session.commit = AsyncMock()

        with patch.object(crud, "_log_gold_transaction", new_callable=AsyncMock) as mock_log:
            new_balance = await crud.add_currency(
                session, character_id=1, amount=500,
                transaction_type="shop_buy_refund",
                source="Refund: inventory add failed",
                metadata={"npc_id": 5},
            )

        assert new_balance == 1000
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["transaction_type"] == "shop_buy_refund"
        assert mock_log.call_args[1]["amount"] == 500
