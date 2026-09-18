"""
FEAT-168 §3.9-bis D — XP books at the locations-service award sites.

Two character-XP write points live here:

  * ``crud.award_post_xp_and_log`` — roleplay-post XP, source
    ``character_xp_post_bonus``. The party +10 % bonus must keep being computed
    from the **base** XP so the book does not compound into it.
  * ``crud.add_experience`` — quest XP, source ``character_xp_quest_bonus``,
    and ``POST /locations/quests/{id}/complete`` must report the **awarded**
    amount, not the raw ``quest.reward_exp``.

Both fail open to ×1.0 when inventory-service is unreachable — a lost bonus is
acceptable, lost XP is not.

All cross-service HTTP is mocked.
"""

import logging
from unittest.mock import patch, MagicMock, AsyncMock

import httpx
import pytest

import crud
from auth_http import get_current_user_via_http, UserRead

POST_SOURCE = "character_xp_post_bonus"
QUEST_SOURCE = "character_xp_quest_bonus"

MOCK_USER = UserRead(
    id=1, username="tester", role="user", permissions=[], current_character_id=1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _multiplier_response(value):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"character_id": 1, "multiplier": value}
    return resp


def _ok_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {}
    return resp


def _make_async_client(get_response=None, put_response=None, post_response=None):
    """An ``httpx.AsyncClient`` stand-in usable as an async context manager."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=get_response or _ok_response())
    client.put = AsyncMock(return_value=put_response or _ok_response())
    client.post = AsyncMock(return_value=post_response or _ok_response())
    return client


def _buff_types_sent(mock_client):
    return [c.kwargs["params"]["buff_type"] for c in mock_client.get.call_args_list]


def _party_call(mock_client):
    for call in mock_client.post.call_args_list:
        url = call.args[0] if call.args else call.kwargs.get("url", "")
        if "xp-bonus" in url:
            return call
    return None


def _attrs_settings(mock_settings):
    mock_settings.ATTRIBUTES_SERVICE_URL = "http://attrs:8002"
    mock_settings.CHARACTER_SERVICE_URL = "http://chars:8005"
    mock_settings.PARTY_SERVICE_URL = "http://party:8014"
    mock_settings.INVENTORY_SERVICE_URL = "http://inv:8004"
    return mock_settings


class _FakeQuest:
    def __init__(self, reward_exp=100, reward_currency=0, reward_items=None):
        self.id = 7
        self.reward_exp = reward_exp
        self.reward_currency = reward_currency
        self.reward_items = reward_items or []


# ═══════════════════════════════════════════════════════════════════════════
# A) get_character_xp_multiplier / apply_character_xp_buff
# ═══════════════════════════════════════════════════════════════════════════

class TestGetCharacterXpMultiplier:
    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_returns_multiplier(self, mock_settings):
        _attrs_settings(mock_settings)
        client = _make_async_client(get_response=_multiplier_response(1.25))
        with patch("crud.httpx.AsyncClient", return_value=client):
            assert await crud.get_character_xp_multiplier(3, QUEST_SOURCE) == 1.25

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_sends_the_requested_buff_type_and_token(self, mock_settings):
        """Anti-silent-failure: the source must travel as ``buff_type``."""
        _attrs_settings(mock_settings)
        for source in (POST_SOURCE, QUEST_SOURCE):
            client = _make_async_client(get_response=_multiplier_response(1.0))
            with patch("crud.httpx.AsyncClient", return_value=client):
                await crud.get_character_xp_multiplier(3, source)
            assert client.get.call_args.kwargs["params"] == {"buff_type": source}
            assert client.get.call_args.kwargs["headers"] == crud._internal_token_headers()
            url = client.get.call_args.args[0]
            assert url.endswith("/inventory/internal/characters/3/xp-multiplier")

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_unknown_source_does_not_call_inventory(self, mock_settings):
        _attrs_settings(mock_settings)
        client = _make_async_client()
        with patch("crud.httpx.AsyncClient", return_value=client):
            # battle XP is not awarded here — this service must refuse it
            assert await crud.get_character_xp_multiplier(3, "character_xp_battle_bonus") == 1.0
        client.get.assert_not_called()

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_multiplier_below_one_is_clamped(self, mock_settings):
        _attrs_settings(mock_settings)
        client = _make_async_client(get_response=_multiplier_response(0.25))
        with patch("crud.httpx.AsyncClient", return_value=client):
            assert await crud.get_character_xp_multiplier(3, POST_SOURCE) == 1.0

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_fails_open_on_connection_error(self, mock_settings, caplog):
        _attrs_settings(mock_settings)
        with patch("crud.httpx.AsyncClient", side_effect=httpx.ConnectError("down")):
            with caplog.at_level(logging.WARNING):
                assert await crud.get_character_xp_multiplier(3, POST_SOURCE) == 1.0
        assert any("множитель опыта" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_fails_open_on_timeout(self, mock_settings):
        _attrs_settings(mock_settings)
        client = _make_async_client()
        client.get = AsyncMock(side_effect=httpx.TimeoutException("slow"))
        with patch("crud.httpx.AsyncClient", return_value=client):
            assert await crud.get_character_xp_multiplier(3, QUEST_SOURCE) == 1.0

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_fails_open_on_http_error_status(self, mock_settings):
        _attrs_settings(mock_settings)
        bad = MagicMock()
        bad.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(),
        )
        client = _make_async_client(get_response=bad)
        with patch("crud.httpx.AsyncClient", return_value=client):
            assert await crud.get_character_xp_multiplier(3, QUEST_SOURCE) == 1.0

    @pytest.mark.asyncio
    async def test_known_sources_are_post_and_quest_only(self):
        assert crud.CHARACTER_XP_SOURCES == frozenset({POST_SOURCE, QUEST_SOURCE})
        assert crud.XP_SOURCE_POST == POST_SOURCE
        assert crud.XP_SOURCE_QUEST == QUEST_SOURCE

    @pytest.mark.asyncio
    async def test_truncates_instead_of_rounding(self):
        with patch("crud.get_character_xp_multiplier",
                   new_callable=AsyncMock, return_value=1.25):
            assert await crud.apply_character_xp_buff(1, 101, QUEST_SOURCE) == 126

    @pytest.mark.asyncio
    async def test_zero_xp_skips_the_lookup(self):
        mock_mult = AsyncMock(return_value=2.0)
        with patch("crud.get_character_xp_multiplier", mock_mult):
            assert await crud.apply_character_xp_buff(1, 0, QUEST_SOURCE) == 0
        mock_mult.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# B) award_post_xp_and_log — roleplay posts
# ═══════════════════════════════════════════════════════════════════════════

class TestAwardPostXpBook:
    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_asks_for_the_post_source(self, mock_settings):
        """Anti-silent-failure guard for the post award site."""
        _attrs_settings(mock_settings)
        client = _make_async_client(get_response=_multiplier_response(1.0))
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud.award_post_xp_and_log(1, 10, 100, "Таверна", 350, 4)
        assert _buff_types_sent(client) == [POST_SOURCE]

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_boosted_xp_is_sent_to_attributes(self, mock_settings):
        _attrs_settings(mock_settings)
        client = _make_async_client(get_response=_multiplier_response(1.5))
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud.award_post_xp_and_log(1, 10, 100, "Таверна", 350, 4)

        client.put.assert_called_once_with(
            "http://attrs:8002/attributes/1/passive_experience",
            json={"amount": 6},  # int(4 * 1.5)
            headers=crud._internal_token_headers(),
        )

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_party_bonus_still_uses_the_base_xp(self, mock_settings):
        """The +10 % squad bonus must not compound with the book."""
        _attrs_settings(mock_settings)
        client = _make_async_client(get_response=_multiplier_response(2.0))
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud.award_post_xp_and_log(1, 10, 100, "Таверна", 500, 5)

        party = _party_call(client)
        assert party is not None
        assert party.kwargs["json"]["base_xp"] == 5          # base, not 10
        assert party.kwargs["json"]["source"] == "post"
        # while the direct award did get the book
        assert client.put.call_args.kwargs["json"] == {"amount": 10}

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_log_entry_reports_the_awarded_xp(self, mock_settings):
        _attrs_settings(mock_settings)
        client = _make_async_client(get_response=_multiplier_response(1.5))
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud.award_post_xp_and_log(1, 10, 100, "Таверна", 350, 4)

        log_call = next(
            c for c in client.post.call_args_list
            if "logs" in (c.args[0] if c.args else "")
        )
        assert log_call.kwargs["json"]["description"] == "Написал пост в Таверна, получил 6 XP"
        assert log_call.kwargs["json"]["metadata"]["xp_earned"] == 6

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_truncation_at_the_post_award_site(self, mock_settings):
        _attrs_settings(mock_settings)
        client = _make_async_client(get_response=_multiplier_response(1.35))
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud.award_post_xp_and_log(1, 10, 100, "Таверна", 700, 7)
        # 7 * 1.35 = 9.45 → 9
        assert client.put.call_args.kwargs["json"] == {"amount": 9}

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_fail_open_awards_base_post_xp(self, mock_settings):
        """inventory-service down ⇒ base XP still reaches the player."""
        _attrs_settings(mock_settings)
        client = _make_async_client()
        client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud.award_post_xp_and_log(1, 10, 100, "Таверна", 350, 4)

        client.put.assert_called_once_with(
            "http://attrs:8002/attributes/1/passive_experience",
            json={"amount": 4},
            headers=crud._internal_token_headers(),
        )

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_zero_xp_post_never_asks_inventory(self, mock_settings):
        _attrs_settings(mock_settings)
        client = _make_async_client()
        with patch("crud.httpx.AsyncClient", return_value=client):
            await crud.award_post_xp_and_log(1, 10, 100, "Таверна", 200, 0)

        client.get.assert_not_called()
        client.put.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# C) add_experience — quest XP
# ═══════════════════════════════════════════════════════════════════════════

class TestAddExperienceQuestBook:
    """`add_experience` never looks the multiplier up itself (review #2).

    It runs inside the caller's transaction, so the value must arrive as a
    parameter — a network call there would hold the transaction open, and
    freeing the connection with a rollback would expire the caller's ORM
    objects (that is the bug this contract exists to prevent).
    """

    @pytest.mark.asyncio
    async def test_does_not_call_inventory_itself(self):
        session = AsyncMock()
        mock_mult = AsyncMock(return_value=2.0)
        with patch("crud.get_character_xp_multiplier", mock_mult):
            await crud.add_experience(session, 3, 100, xp_multiplier=1.5)
        mock_mult.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_writes_the_multiplied_amount(self):
        session = AsyncMock()
        awarded = await crud.add_experience(session, 3, 100, xp_multiplier=1.5)

        assert awarded == 150
        params = session.execute.call_args.args[1]
        assert params == {"cid": 3, "amount": 150}
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_truncation_at_the_quest_award_site(self):
        session = AsyncMock()
        awarded = await crud.add_experience(session, 3, 7, xp_multiplier=1.35)
        assert awarded == 9  # int(9.45)

    @pytest.mark.asyncio
    async def test_no_multiplier_writes_the_base_amount(self):
        """`None` = «книги нет»: начисляем базовый опыт, ничего не теряем."""
        session = AsyncMock()
        awarded = await crud.add_experience(session, 3, 80)

        assert awarded == 80
        assert session.execute.call_args.args[1] == {"cid": 3, "amount": 80}

    @pytest.mark.asyncio
    async def test_never_rolls_the_session_back(self):
        """Регрессия review #2: откат протухал объекты вызывающего."""
        session = AsyncMock()
        await crud.add_experience(session, 3, 10, xp_multiplier=1.5)
        session.rollback.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# D) POST /locations/quests/{id}/complete — reports the awarded XP
# ═══════════════════════════════════════════════════════════════════════════

class TestQuestCompleteEndpoint:
    def _complete(self, client, quest_id=7):
        from main import app
        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        try:
            return client.post(
                f"/locations/quests/{quest_id}/complete",
                json={"character_id": 1},
                headers={"Authorization": "Bearer test-token"},
            )
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)

    @patch("main._auto_progress_quest", new_callable=AsyncMock)
    @patch("main._track_cumulative_stats", new_callable=AsyncMock)
    @patch("main.crud.complete_quest_record", new_callable=AsyncMock)
    @patch("main.crud.add_experience", new_callable=AsyncMock)
    @patch("main.crud.get_quest_by_id", new_callable=AsyncMock)
    @patch("main.crud.check_quest_completable", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_returns_the_boosted_reward_exp(
        self, mock_own, mock_check, mock_quest, mock_add_exp,
        mock_complete, mock_track, mock_auto, client,
    ):
        mock_check.return_value = {"all_completed": True, "character_quest_id": 55}
        mock_quest.return_value = _FakeQuest(reward_exp=100)
        mock_add_exp.return_value = 135  # what the book actually granted

        resp = self._complete(client)

        assert resp.status_code == 200
        assert resp.json()["reward_exp"] == 135
        mock_add_exp.assert_awaited_once()
        assert mock_add_exp.await_args.args[1:] == (1, 100)

    @patch("main._auto_progress_quest", new_callable=AsyncMock)
    @patch("main._track_cumulative_stats", new_callable=AsyncMock)
    @patch("main.crud.complete_quest_record", new_callable=AsyncMock)
    @patch("main.crud.add_experience", new_callable=AsyncMock)
    @patch("main.crud.get_quest_by_id", new_callable=AsyncMock)
    @patch("main.crud.check_quest_completable", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_reports_base_exp_when_no_book_is_active(
        self, mock_own, mock_check, mock_quest, mock_add_exp,
        mock_complete, mock_track, mock_auto, client,
    ):
        mock_check.return_value = {"all_completed": True, "character_quest_id": 55}
        mock_quest.return_value = _FakeQuest(reward_exp=100)
        mock_add_exp.return_value = 100

        resp = self._complete(client)

        assert resp.status_code == 200
        assert resp.json()["reward_exp"] == 100

    @patch("main.crud.get_character_xp_multiplier", new_callable=AsyncMock)
    @patch("main._auto_progress_quest", new_callable=AsyncMock)
    @patch("main._track_cumulative_stats", new_callable=AsyncMock)
    @patch("main.crud.complete_quest_record", new_callable=AsyncMock)
    @patch("main.crud.add_experience", new_callable=AsyncMock)
    @patch("main.crud.get_quest_by_id", new_callable=AsyncMock)
    @patch("main.crud.check_quest_completable", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_zero_reward_exp_skips_the_lookup_entirely(
        self, mock_own, mock_check, mock_quest, mock_add_exp,
        mock_complete, mock_track, mock_auto, mock_mult, client,
    ):
        """review #3: a quest without XP must not ask inventory-service anything."""
        mock_check.return_value = {"all_completed": True, "character_quest_id": 55}
        mock_quest.return_value = _FakeQuest(reward_exp=0)

        resp = self._complete(client)

        assert resp.status_code == 200
        mock_mult.assert_not_awaited()
        mock_add_exp.assert_not_awaited()

    @patch("main._auto_progress_quest", new_callable=AsyncMock)
    @patch("main._track_cumulative_stats", new_callable=AsyncMock)
    @patch("main.crud.complete_quest_record", new_callable=AsyncMock)
    @patch("main.crud.add_experience", new_callable=AsyncMock)
    @patch("main.crud.get_quest_by_id", new_callable=AsyncMock)
    @patch("main.crud.check_quest_completable", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_zero_reward_exp_skips_the_award(
        self, mock_own, mock_check, mock_quest, mock_add_exp,
        mock_complete, mock_track, mock_auto, client,
    ):
        mock_check.return_value = {"all_completed": True, "character_quest_id": 55}
        mock_quest.return_value = _FakeQuest(reward_exp=0)

        resp = self._complete(client)

        assert resp.status_code == 200
        assert resp.json()["reward_exp"] == 0
        mock_add_exp.assert_not_awaited()

    @patch("main.crud.check_quest_completable", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_incomplete_quest_awards_nothing(self, mock_own, mock_check, client):
        mock_check.return_value = {"all_completed": False, "character_quest_id": 55}

        with patch("main.crud.add_experience", new_callable=AsyncMock) as mock_add_exp:
            resp = self._complete(client)

        assert resp.status_code == 400
        mock_add_exp.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# E) Review #2 regression — a real AsyncSession, the exact case that 500'd
# ═══════════════════════════════════════════════════════════════════════════
#
# The first attempt at «don't hold a transaction across HTTP» freed the
# connection with `session.rollback()`. A rollback expires every loaded ORM
# object, so `complete_quest` blew up with MissingGreenlet on its next read of
# `quest.reward_items` / `quest.reward_currency` — *after* the XP had been
# committed, leaving the quest active and re-completable for XP indefinitely.
#
# The trigger was `reward_exp > 0` **and** `reward_currency == 0`: a gold-bearing
# quest commits inside `add_currency` first, which hid the bug in manual testing.
# These tests run against a real in-memory aiosqlite session, so a rollback
# inside `add_experience` fails them again.

import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from models import Quest as _Quest  # noqa: E402


@pytest_asyncio.fixture()
async def real_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(_Quest.__table__.create)
        await conn.exec_driver_sql(
            "CREATE TABLE character_attributes ("
            " character_id INTEGER PRIMARY KEY, passive_experience INTEGER DEFAULT 0)"
        )
        await conn.exec_driver_sql(
            "INSERT INTO character_attributes (character_id, passive_experience) VALUES (3, 10)"
        )

    # `expire_on_commit=False` mirrors `database.async_session` exactly. It is
    # what makes a commit inside the award harmless — while a ROLLBACK expires
    # loaded objects regardless of this flag, which is precisely why freeing the
    # connection that way broke the caller.
    Session = sessionmaker(engine, class_=_AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


class TestAddExperienceKeepsCallerObjectsUsable:
    @pytest.mark.asyncio
    async def test_quest_with_exp_and_zero_currency_survives(self, real_session):
        """reward_exp > 0, reward_currency == 0 — the combination that 500'd."""
        real_session.add(_Quest(
            id=7, npc_id=1, title="Награда только опытом",
            reward_currency=0, reward_exp=100, reward_items=[{"item_id": 5}],
        ))
        await real_session.commit()

        quest = await real_session.get(_Quest, 7)

        awarded = await crud.add_experience(real_session, 3, quest.reward_exp, xp_multiplier=1.5)
        assert awarded == 150

        # The caller keeps reading its own ORM object after the award — this is
        # the exact line that raised MissingGreenlet in review #2.
        assert quest.reward_items == [{"item_id": 5}]
        assert quest.reward_currency == 0
        assert quest.title == "Награда только опытом"

    @pytest.mark.asyncio
    async def test_xp_is_actually_committed(self, real_session):
        await crud.add_experience(real_session, 3, 20, xp_multiplier=2.0)
        row = await real_session.execute(
            text("SELECT passive_experience FROM character_attributes WHERE character_id = 3")
        )
        assert row.scalar() == 50  # 10 + int(20 * 2.0)


# ═══════════════════════════════════════════════════════════════════════════
# F) A failed lookup must be VISIBLE (review #5, finding 36)
# ═══════════════════════════════════════════════════════════════════════════

class TestFailedLookupIsVisible:
    """Fail-open must not mean fail-silent — same contract as character-service."""

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_failure_is_logged_at_error_level(self, mock_settings, caplog):
        mock_settings.INVENTORY_SERVICE_URL = "http://inventory-service:8004"
        with patch("crud.httpx.AsyncClient", side_effect=httpx.ConnectError("down")):
            with caplog.at_level(logging.ERROR):
                result = await crud.lookup_character_xp_multiplier(3, QUEST_SOURCE)

        assert result.multiplier == 1.0        # fail-open, XP never lost
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, "провал запроса должен быть виден уровнем error"
        message = errors[0].getMessage()
        assert "3" in message and QUEST_SOURCE in message and "мс" in message

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_failure_is_flagged(self, mock_settings):
        mock_settings.INVENTORY_SERVICE_URL = "http://inventory-service:8004"
        with patch("crud.httpx.AsyncClient", side_effect=httpx.TimeoutException("slow")):
            result = await crud.lookup_character_xp_multiplier(3, QUEST_SOURCE)

        assert (result.multiplier, result.ok, result.reason) == (1.0, False, "request_failed")
        assert result.elapsed_ms >= 0

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_no_book_is_a_success(self, mock_settings):
        mock_settings.INVENTORY_SERVICE_URL = "http://inventory-service:8004"
        client = _make_async_client(get_response=_multiplier_response(1.0))
        with patch("crud.httpx.AsyncClient", return_value=client):
            result = await crud.lookup_character_xp_multiplier(3, QUEST_SOURCE)

        assert (result.multiplier, result.ok, result.reason) == (1.0, True, None)

    @pytest.mark.asyncio
    async def test_unknown_source_is_flagged(self):
        result = await crud.lookup_character_xp_multiplier(3, "character_xp_pvp_bonus")
        assert (result.multiplier, result.ok, result.reason) == (1.0, False, "unknown_source")
