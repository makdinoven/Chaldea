"""
FEAT-168 §3.9-bis D — the battle pass names its own XP source.

``_deliver_gold_xp`` posts to character-service ``/characters/{cid}/add_rewards``.
Without an explicit ``xp_source`` character-service would fall back to the
*battle* book, so a battle-pass reward would be accelerated by the wrong item.
These tests fail the moment that field stops being sent or changes value.

The outgoing HTTP call is mocked — no character-service is involved.
"""

from unittest.mock import patch, MagicMock, AsyncMock

import httpx
import pytest

import crud

PASS_SOURCE = "character_xp_pass_bonus"


def _make_async_client(response=None):
    resp = response or MagicMock(status_code=200, raise_for_status=MagicMock())
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=resp)
    return client


class TestDeliverGoldXpSource:
    @pytest.mark.asyncio
    async def test_sends_the_battle_pass_xp_source(self):
        """Anti-silent-failure guard: the body must carry the pass source."""
        client = _make_async_client()
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud._deliver_gold_xp(42, xp=100, gold=0)

        body = client.post.call_args.kwargs["json"]
        assert body["xp_source"] == PASS_SOURCE
        assert body["xp"] == 100
        assert body["gold"] == 0

    @pytest.mark.asyncio
    async def test_constant_matches_the_contract(self):
        assert crud.BATTLE_PASS_XP_SOURCE == PASS_SOURCE

    @pytest.mark.asyncio
    async def test_posts_to_the_add_rewards_endpoint(self):
        client = _make_async_client()
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud._deliver_gold_xp(42, xp=10, gold=5)

        url = client.post.call_args.args[0]
        assert url.endswith("/characters/42/add_rewards")

    @pytest.mark.asyncio
    async def test_gold_only_reward_also_names_the_source(self):
        """A gold-only reward still goes through the same body shape."""
        client = _make_async_client()
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud._deliver_gold_xp(42, xp=0, gold=500)

        assert client.post.call_args.kwargs["json"] == {
            "xp": 0, "gold": 500, "xp_source": PASS_SOURCE,
        }

    @pytest.mark.asyncio
    async def test_never_sends_the_battle_source(self):
        """Regression: the battle book must not accelerate pass rewards."""
        client = _make_async_client()
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud._deliver_gold_xp(42, xp=100, gold=0)

        assert client.post.call_args.kwargs["json"]["xp_source"] != "character_xp_battle_bonus"

    @pytest.mark.asyncio
    async def test_http_failure_is_raised_to_the_caller(self):
        """Delivery errors must surface — a silently swallowed reward is a bug."""
        client = _make_async_client()
        client.post = AsyncMock(side_effect=httpx.ConnectError("character-service down"))
        with patch("crud.httpx.AsyncClient", return_value=client):
            with pytest.raises(Exception):
                await crud._deliver_gold_xp(42, xp=100, gold=0)


class TestClaimRewardUsesTheSource:
    @pytest.mark.asyncio
    async def test_xp_reward_delivery_carries_the_source(self):
        """End-to-end through the delivery helper for an XP-type reward."""
        client = _make_async_client()
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud._deliver_gold_xp(7, xp=250)

        body = client.post.call_args.kwargs["json"]
        assert body == {"xp": 250, "gold": 0, "xp_source": PASS_SOURCE}
