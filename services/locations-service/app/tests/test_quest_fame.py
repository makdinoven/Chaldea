"""FEAT-199 (task 8): quest fame in locations-service — the «Мин. слава» gate and the fame reward.

* quest list: a quest with ``min_fame_tier`` stays listed with ``locked_reason`` «Нужна слава: X»; fame is
  global (the gate works even when the quest giver has no region); when both gates fail the reputation
  reason wins; an unknown code in the DB is no gate; an empty ``renown_tiers`` falls back to the seed ladder;
  no renown table is touched when no quest of the list is fame-gated;
* quest accept: 403 «Нужна слава: X», nothing created; tier met -> accepted;
* quest completion: after the COMMIT, ``POST /characters/internal/fame/apply`` with
  ``{character_id, source: "quest", idempotency_key: "fame:quest:cq:{id}", points, ref_id}`` — ``points``
  null = the character-service default, ``fame_reward`` 0 = no call; one retry on network errors / 5xx
  only, a failure never fails the completion (mocked HTTP);
* admin schema validation of ``min_fame_tier`` (fixed codes, injection strings) and ``fame_reward`` (0..1000);
* CRUD persistence, ``fame_read`` pure helpers, migration 056.
"""

import contextlib
import importlib.util
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import fame_read  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402

from test_econ_locations_flows import _one, _user  # noqa: E402
from test_reputation_gates import (  # noqa: E402,F401  (qdb / admin_client are fixtures)
    BAD_CODES, Q_CHAR, Q_GATED, Q_NPC, Q_OPEN, Q_USER, REGION_B, _active_quest, _by_id, _exec, _rep,
    admin_client, qdb,
)

FAME_PATH = "/characters/internal/fame/apply"
REP_PATH = "/characters/internal/reputation/apply"
Q_FAME = 44                                   # gated by fame «known» (200)
Q_BOTH = 45                                   # reputation «trusted» + fame «famous»


# ═══════════════════════════════════════════════════════════════════════════
# World: the quest world of test_reputation_gates + renown tables + fame-gated quests
# ═══════════════════════════════════════════════════════════════════════════

RENOWN_DDL = [
    "CREATE TABLE character_renown (character_id INTEGER PRIMARY KEY, fame INTEGER NOT NULL DEFAULT 0, "
    "infamy INTEGER NOT NULL DEFAULT 0, updated_at DATETIME)",
    "CREATE TABLE renown_tiers (scale VARCHAR(10) NOT NULL, code VARCHAR(20) NOT NULL, sort_order INTEGER NOT NULL, "
    "name VARCHAR(60) NOT NULL, min_value INTEGER NOT NULL, witness_pct DECIMAL(5,2) NOT NULL DEFAULT 0, "
    "PRIMARY KEY (scale, code))",
]

SEED_TIERS = [
    ("fame", "nameless", 1, "Безвестный", 0), ("fame", "familiar", 2, "Знакомое имя", 50),
    ("fame", "known", 3, "Известный", 200), ("fame", "famous", 4, "Знаменитый", 600),
    ("fame", "legend", 5, "Легенда", 1500),
    # the infamy ladder lives in the same table and must never leak into the fame gate
    ("infamy", "none", 1, "О вас не говорят", 0), ("infamy", "whispers", 2, "Шёпот в тавернах", 100),
    ("infamy", "rumored", 3, "О вас ходят слухи", 400), ("infamy", "notorious", 4, "Дурная слава", 1000),
    ("infamy", "dreaded", 5, "Имя, которое произносят шёпотом", 2500),
]


async def _seed_tiers(s, rows=SEED_TIERS):
    for scale, code, order, name, min_value in rows:
        await s.execute(text("INSERT INTO renown_tiers (scale, code, sort_order, name, min_value) "
                             "VALUES (:s, :c, :o, :n, :m)"), {"s": scale, "c": code, "o": order, "n": name,
                                                              "m": min_value})
    await s.commit()


@pytest.fixture()
async def fdb(qdb):
    for ddl in RENOWN_DDL:
        await qdb.execute(text(ddl))
    await qdb.commit()
    await _seed_tiers(qdb)
    for qid, title, rep_gate, fame_gate in ((Q_FAME, "Поручение для знаменитых", None, "known"),
                                            (Q_BOTH, "Дело чести", "trusted", "famous")):
        qdb.add(models.Quest(id=qid, npc_id=Q_NPC, title=title, description="", quest_type="standard",
                             min_level=1, reward_currency=0, reward_exp=0, reward_items=None, is_active=True,
                             min_reputation_tier=rep_gate, min_fame_tier=fame_gate))
        qdb.add(models.QuestObjective(quest_id=qid, description="Поговорить", objective_type="talk_npc",
                                      target_id=Q_NPC, target_count=1, sort_order=0))
    await qdb.commit()
    return qdb


async def _fame(s, value, cid=Q_CHAR):
    await s.execute(text("DELETE FROM character_renown WHERE character_id = :c"), {"c": cid})
    await s.execute(text("INSERT INTO character_renown (character_id, fame, infamy, updated_at) "
                         "VALUES (:c, :f, 0, :u)"), {"c": cid, "f": value, "u": datetime.utcnow()})
    await s.commit()


async def _count_cq(s):
    return await _one(s, "SELECT COUNT(*) FROM character_quests WHERE character_id = :c", c=Q_CHAR)


# ═══════════════════════════════════════════════════════════════════════════
# Quest list
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.real_reputation
class TestFameList:

    async def test_fame_gated_quest_is_listed_with_the_reason(self, fdb):
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert set(rows) == {Q_OPEN, Q_GATED, Q_FAME, Q_BOTH}
        assert rows[Q_FAME]["locked_reason"] == "Нужна слава: Известный"
        assert rows[Q_FAME]["min_fame_tier"] == "known"
        assert rows[Q_FAME]["player_status"] == "available"
        assert rows[Q_OPEN]["locked_reason"] is None
        assert rows[Q_OPEN]["min_fame_tier"] is None

    @pytest.mark.parametrize("value,locked", [(0, True), (199, True), (200, False), (5000, False)])
    async def test_threshold(self, fdb, value, locked):
        await _fame(fdb, value)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert (rows[Q_FAME]["locked_reason"] is not None) is locked

    async def test_infamy_does_not_count_as_fame(self, fdb):
        await _exec(fdb, "INSERT INTO character_renown (character_id, fame, infamy, updated_at) "
                         "VALUES (:c, 0, 9999, :u)", c=Q_CHAR, u=datetime.utcnow())
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_FAME]["locked_reason"] == "Нужна слава: Известный"

    async def test_other_characters_fame_does_not_count(self, fdb):
        await _fame(fdb, 5000, cid=Q_CHAR + 1)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_FAME]["locked_reason"] == "Нужна слава: Известный"

    async def test_fame_gate_works_without_a_region(self, fdb):
        """Fame is global: a quest giver outside any region opens the reputation gate, not the fame one."""
        await _exec(fdb, "UPDATE characters SET current_location_id = 1003 WHERE id = :n", n=Q_NPC)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_GATED]["locked_reason"] is None                       # reputation: no region = open
        assert rows[Q_FAME]["locked_reason"] == "Нужна слава: Известный"
        assert rows[Q_BOTH]["locked_reason"] == "Нужна слава: Знаменитый"

    async def test_both_gates_fail_reputation_reason_wins(self, fdb):
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_BOTH]["locked_reason"] == "Нужна репутация: Свой человек"

    async def test_reputation_met_fame_reason_shows(self, fdb):
        await _rep(fdb, 300)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_BOTH]["locked_reason"] == "Нужна слава: Знаменитый"
        await _fame(fdb, 600)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_BOTH]["locked_reason"] is None

    async def test_npc_reputation_gate_comes_before_fame(self, fdb):
        await _fame(fdb, 5000)
        await _exec(fdb, "UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :n", n=Q_NPC)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_FAME]["locked_reason"] == "Нужна репутация: Знакомое лицо"

    async def test_unknown_code_in_the_db_is_no_gate(self, fdb):
        await _exec(fdb, "UPDATE quests SET min_fame_tier = 'bogus' WHERE id = :q", q=Q_FAME)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_FAME]["locked_reason"] is None

    async def test_empty_tiers_fall_back_to_the_seed_ladder(self, fdb):
        await _exec(fdb, "DELETE FROM renown_tiers")
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_FAME]["locked_reason"] == "Нужна слава: Известный"
        await _fame(fdb, 200)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_FAME]["locked_reason"] is None

    async def test_edited_ladder_name_and_threshold_are_used(self, fdb):
        await _exec(fdb, "UPDATE renown_tiers SET name = 'Узнаваемый', min_value = 300 "
                         "WHERE scale = 'fame' AND code = 'known'")
        await _fame(fdb, 250)
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert rows[Q_FAME]["locked_reason"] == "Нужна слава: Узнаваемый"

    async def test_active_and_completed_quests_are_never_locked(self, fdb):
        await _active_quest(fdb, Q_FAME, status="active")
        rows = _by_id(await crud.get_available_quests_for_npc(fdb, Q_NPC, Q_CHAR))
        assert (rows[Q_FAME]["player_status"], rows[Q_FAME]["locked_reason"]) == ("active", None)

    async def test_no_fame_read_when_no_quest_is_gated(self, qdb):
        """The base world has no renown tables at all: a list without fame gates must not touch them."""
        with patch.object(fame_read, "load_fame_tiers", AsyncMock()) as tiers, \
                patch.object(fame_read, "fame_value", AsyncMock()) as value:
            rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert set(rows) == {Q_OPEN, Q_GATED}
        tiers.assert_not_awaited()
        value.assert_not_awaited()
        # and for real: no table -> would raise if it were read
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert rows[Q_OPEN]["locked_reason"] is None

    def test_list_schema_declares_the_field(self):
        assert schemas.QuestAvailableRead.__fields__["min_fame_tier"].default is None


# ═══════════════════════════════════════════════════════════════════════════
# Quest accept
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.real_reputation
class TestFameAccept:

    async def test_fame_gate_is_403_and_creates_nothing(self, fdb):
        with pytest.raises(HTTPException) as exc:
            await crud.accept_quest(fdb, Q_FAME, Q_CHAR)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна слава: Известный")
        assert await _count_cq(fdb) == 0

    async def test_tier_met_accepts(self, fdb):
        await _fame(fdb, 200)
        cq = await crud.accept_quest(fdb, Q_FAME, Q_CHAR)
        assert cq.status == "active" and await _count_cq(fdb) == 1

    async def test_both_gates_reputation_reason_wins(self, fdb):
        with pytest.raises(HTTPException) as exc:
            await crud.accept_quest(fdb, Q_BOTH, Q_CHAR)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна репутация: Свой человек")

    async def test_reputation_met_then_fame_403(self, fdb):
        await _rep(fdb, 300)
        with pytest.raises(HTTPException) as exc:
            await crud.accept_quest(fdb, Q_BOTH, Q_CHAR)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна слава: Знаменитый")
        await _fame(fdb, 600)
        assert (await crud.accept_quest(fdb, Q_BOTH, Q_CHAR)).status == "active"

    async def test_fame_gate_without_a_region_still_403(self, fdb):
        await _exec(fdb, "UPDATE characters SET current_location_id = 1003 WHERE id = :n", n=Q_NPC)
        with pytest.raises(HTTPException) as exc:
            await crud.accept_quest(fdb, Q_FAME, Q_CHAR)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна слава: Известный")
        assert await _count_cq(fdb) == 0

    async def test_unknown_code_accepts(self, fdb):
        await _exec(fdb, "UPDATE quests SET min_fame_tier = 'bogus' WHERE id = :q", q=Q_FAME)
        assert (await crud.accept_quest(fdb, Q_FAME, Q_CHAR)).status == "active"

    async def test_ungated_quest_reads_no_fame(self, qdb):
        """Base world without renown tables: accepting an ungated quest works."""
        assert (await crud.accept_quest(qdb, Q_OPEN, Q_CHAR)).status == "active"

    async def test_route_maps_the_gate_to_403(self, fdb):
        with patch.object(main, "check_not_activity_locked", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await main.accept_quest(quest_id=Q_FAME, body=schemas.QuestAcceptRequest(character_id=Q_CHAR),
                                        session=fdb, current_user=_user(Q_USER))
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна слава: Известный")
        assert await _count_cq(fdb) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Quest completion -> internal fame call
# ═══════════════════════════════════════════════════════════════════════════

class _Http:
    """httpx.AsyncClient stand-in. `answers` = what successive FAME calls return (int status or exception).
    Records every call (path order) and the character quest's committed status seen at each fame call."""

    def __init__(self, qdb, answers=(200,)):
        self.answers = list(answers)
        self.fame_calls = []
        self.order = []
        self.status_at_call = []
        self.qdb = qdb
        client = AsyncMock()
        client.post = AsyncMock(side_effect=self._post)
        self.factory = MagicMock()
        self.factory.return_value.__aenter__ = AsyncMock(return_value=client)
        self.factory.return_value.__aexit__ = AsyncMock(return_value=False)

    async def _post(self, url, json=None, headers=None, **kw):
        self.order.append(url)
        if not url.endswith(FAME_PATH):
            return MagicMock(status_code=200)
        self.fame_calls.append({"url": url, "json": json, "headers": headers})
        async with AsyncSession(bind=self.qdb.bind) as other:
            self.status_at_call.append(await _one(other, "SELECT status FROM character_quests WHERE id = :i",
                                                  i=json["ref_id"]))
        answer = self.answers.pop(0) if self.answers else 200
        if isinstance(answer, Exception):
            raise answer
        return MagicMock(status_code=answer)


@contextlib.contextmanager
def _patched(http):
    with patch.object(main.httpx, "AsyncClient", http.factory), patch.object(crud.httpx, "AsyncClient", http.factory), \
            patch.object(main, "check_not_activity_locked", AsyncMock(return_value=None)), \
            patch.object(main, "_track_cumulative_stats", AsyncMock(return_value=None)), \
            patch.object(main, "_auto_progress_quest", AsyncMock(return_value=None)), \
            patch.object(crud, "get_character_xp_multiplier", AsyncMock(return_value=None)):
        yield


async def _complete(s, http, quest_id=Q_OPEN):
    with _patched(http):
        return await main.complete_quest(quest_id=quest_id, body=schemas.QuestCompleteRequest(character_id=Q_CHAR),
                                         request=MagicMock(), session=s, current_user=_user(Q_USER))


class TestFameCompletion:

    async def test_default_call_after_the_commit_with_null_points(self, qdb):
        cq = await _active_quest(qdb)
        http = _Http(qdb)
        out = await _complete(qdb, http)
        assert out["success"] is True
        assert len(http.fame_calls) == 1
        call = http.fame_calls[0]
        assert call["url"].endswith(FAME_PATH)
        assert call["json"] == {"character_id": Q_CHAR, "source": "quest",
                                "idempotency_key": f"fame:quest:cq:{cq}", "points": None, "ref_id": cq}
        assert "X-Internal-Token" in call["headers"]
        assert http.status_at_call == ["completed"]                    # committed before the HTTP call

    @pytest.mark.parametrize("reward", [1, 25, 1000])
    async def test_quest_override_is_sent_as_points(self, qdb, reward):
        await _exec(qdb, "UPDATE quests SET fame_reward = :r WHERE id = :q", r=reward, q=Q_OPEN)
        await _active_quest(qdb)
        http = _Http(qdb)
        await _complete(qdb, http)
        assert http.fame_calls[0]["json"]["points"] == reward

    async def test_zero_reward_makes_no_call(self, qdb):
        await _exec(qdb, "UPDATE quests SET fame_reward = 0 WHERE id = :q", q=Q_OPEN)
        await _active_quest(qdb)
        http = _Http(qdb)
        out = await _complete(qdb, http)
        assert out["success"] is True and http.fame_calls == []

    async def test_fame_does_not_depend_on_a_region(self, qdb):
        """No region anywhere -> no reputation call, but the fame call still goes out."""
        await _exec(qdb, "UPDATE characters SET current_location_id = 1003 WHERE id IN (:n, :c)", n=Q_NPC, c=Q_CHAR)
        await _active_quest(qdb)
        http = _Http(qdb)
        await _complete(qdb, http)
        assert len(http.fame_calls) == 1
        assert not any(u.endswith(REP_PATH) for u in http.order)

    @pytest.mark.real_reputation
    async def test_reputation_and_fame_are_separate_calls(self, qdb):
        cq = await _active_quest(qdb)
        http = _Http(qdb)
        await _complete(qdb, http)
        paths = [u for u in http.order if u.endswith((REP_PATH, FAME_PATH))]
        assert [p.endswith(REP_PATH) for p in paths] == [True, False]  # reputation first, then fame
        assert http.fame_calls[0]["json"]["idempotency_key"] == f"fame:quest:cq:{cq}"

    @pytest.mark.parametrize("answers,calls", [
        ((503, 200), 2),
        ((httpx.ConnectError("down"), 200), 2),
        ((httpx.ReadTimeout("slow"), 200), 2),
        ((500, 500), 2),                                               # one retry only
        ((httpx.ConnectError("down"), httpx.ConnectError("down")), 2),
        ((404,), 1),                                                   # 4xx is not retried
        ((422,), 1),
        ((403,), 1),
    ])
    async def test_retry_policy_and_completion_never_fails(self, qdb, answers, calls):
        cq = await _active_quest(qdb)
        http = _Http(qdb, answers)
        out = await _complete(qdb, http)
        assert out["success"] is True and out["new_balance"] == 310
        assert len(http.fame_calls) == calls
        assert {c["json"]["idempotency_key"] for c in http.fame_calls} == {f"fame:quest:cq:{cq}"}   # same key
        assert await _one(qdb, "SELECT status FROM character_quests WHERE id = :i", i=cq) == "completed"

    @pytest.mark.parametrize("error", [RuntimeError("boom"), ValueError("bad json"), KeyError("x")])
    async def test_unexpected_error_never_fails_the_completion(self, qdb, error):
        """FEAT-200 (fix 9): any exception after the commit is logged, not retried, and never a 500."""
        cq = await _active_quest(qdb)
        http = _Http(qdb, (error,))
        with patch.object(main, "logger") as log:
            out = await _complete(qdb, http)
        assert out["success"] is True and out["new_balance"] == 310
        assert len(http.fame_calls) == 1                                         # no retry
        assert await _one(qdb, "SELECT status FROM character_quests WHERE id = :i", i=cq) == "completed"
        log.exception.assert_called_once()

    @pytest.mark.real_reputation
    async def test_reputation_error_does_not_stop_the_fame_call(self, qdb):
        """Both post-commit calls are independent: an unexpected reputation failure still lets fame go out."""
        await _active_quest(qdb)
        http = _Http(qdb)
        real_post = http._post

        async def post(url, json=None, headers=None, **kw):
            if url.endswith(REP_PATH):
                http.order.append(url)
                raise RuntimeError("boom")
            return await real_post(url, json=json, headers=headers, **kw)

        http.factory.return_value.__aenter__.return_value.post.side_effect = post
        out = await _complete(qdb, http)
        assert out["success"] is True and len(http.fame_calls) == 1

    async def test_helper_returns_false_on_an_unexpected_error(self, qdb):
        http = _Http(qdb, (RuntimeError("boom"),))
        with _patched(http), patch.object(main, "logger") as log:
            assert await main._apply_quest_fame(Q_CHAR, 7, None) is False
        assert "unexpectedly" in log.exception.call_args.args[0]

    async def test_helper_returns_whether_it_was_applied(self, qdb):
        http = _Http(qdb, (503, 503))
        with _patched(http):
            assert await main._apply_quest_fame(Q_CHAR, 7, None) is False
        assert len(http.fame_calls) == 2
        http = _Http(qdb, (200,))
        with _patched(http):
            assert await main._apply_quest_fame(Q_CHAR, 7, 15) is True
        assert http.fame_calls[0]["json"] == {"character_id": Q_CHAR, "source": "quest",
                                              "idempotency_key": "fame:quest:cq:7", "points": 15, "ref_id": 7}

    def test_attempts_constant(self):
        assert main.QUEST_FAME_ATTEMPTS == 2 and main.QUEST_FAME_SOURCE == "quest"


# ═══════════════════════════════════════════════════════════════════════════
# Admin schema validation
# ═══════════════════════════════════════════════════════════════════════════

class TestFameSchemas:

    @pytest.mark.parametrize("code", fame_read.FAME_TIER_CODES)
    @pytest.mark.parametrize("model", [schemas.QuestCreate, schemas.QuestUpdate])
    def test_every_fixed_code_is_accepted(self, model, code):
        assert model(npc_id=1, title="t", min_fame_tier=code).min_fame_tier == code

    def test_fixed_codes(self):
        assert fame_read.FAME_TIER_CODES == ("nameless", "familiar", "known", "famous", "legend")

    @pytest.mark.parametrize("raw,clean", [(None, None), ("", None), ("   ", None), (" legend ", "legend")])
    def test_blank_means_no_gate_and_spaces_are_trimmed(self, raw, clean):
        assert schemas.QuestUpdate(min_fame_tier=raw).min_fame_tier == clean

    @pytest.mark.parametrize("code", BAD_CODES + ["trusted", "Known", "dreaded", "none"])
    @pytest.mark.parametrize("model", [schemas.QuestCreate, schemas.QuestUpdate])
    def test_unknown_codes_are_rejected(self, model, code):
        """Reputation / infamy codes and injection strings are not fame codes."""
        with pytest.raises(ValidationError) as exc:
            model(npc_id=1, title="t", min_fame_tier=code)
        assert "Неизвестная ступень славы" in str(exc.value)

    @pytest.mark.parametrize("value,ok", [(0, True), (1, True), (1000, True), (None, True),
                                          (-1, False), (1001, False), (10 ** 9, False)])
    @pytest.mark.parametrize("model", [schemas.QuestCreate, schemas.QuestUpdate])
    def test_reward_bounds(self, model, value, ok):
        if ok:
            assert model(npc_id=1, title="t", fame_reward=value).fame_reward == value
        else:
            with pytest.raises(ValidationError):
                model(npc_id=1, title="t", fame_reward=value)

    @pytest.mark.parametrize("value", ["abc", "1; DROP TABLE quests", "5 OR 1=1"])
    def test_reward_must_be_an_int(self, value):
        with pytest.raises(ValidationError):
            schemas.QuestCreate(npc_id=1, title="t", fame_reward=value)

    def test_update_keeps_unsent_fields_unset_and_sends_explicit_null(self):
        assert not {"min_fame_tier", "fame_reward"} & set(schemas.QuestUpdate(title="x").dict(exclude_unset=True))
        data = schemas.QuestUpdate(min_fame_tier=None, fame_reward=None).dict(exclude_unset=True)
        assert data == {"min_fame_tier": None, "fame_reward": None}

    def test_read_schema_carries_the_fields(self):
        quest = models.Quest(id=1, npc_id=1, title="t", description="", quest_type="standard", min_level=1,
                             reward_currency=0, reward_exp=0, is_active=True, objectives=[],
                             min_fame_tier="famous", fame_reward=0)
        data = schemas.QuestRead.from_orm(quest).dict()
        assert (data["min_fame_tier"], data["fame_reward"]) == ("famous", 0)


class TestFameAdminHttp:

    @pytest.mark.parametrize("code", ["boss", "known' OR '1'='1", "legend; DROP TABLE quests;--",
                                      "<script>alert(1)</script>"])
    def test_create_with_an_unknown_tier_is_422_and_touches_nothing(self, admin_client, code):
        with patch.object(crud, "create_quest", AsyncMock()) as create:
            r = admin_client.post("/locations/admin/quests", json={"npc_id": 1, "title": "t", "min_fame_tier": code})
        assert r.status_code == 422
        assert "Неизвестная ступень славы" in r.text
        create.assert_not_awaited()

    @pytest.mark.parametrize("value", [-1, 1001, "x"])
    def test_out_of_range_reward_is_422(self, admin_client, value):
        with patch.object(crud, "create_quest", AsyncMock()) as create, \
                patch.object(crud, "update_quest", AsyncMock()) as update:
            r1 = admin_client.post("/locations/admin/quests", json={"npc_id": 1, "title": "t", "fame_reward": value})
            r2 = admin_client.put("/locations/admin/quests/1", json={"fame_reward": value})
        assert (r1.status_code, r2.status_code) == (422, 422)
        create.assert_not_awaited()
        update.assert_not_awaited()

    def test_update_passes_the_explicit_clear_to_crud(self, admin_client):
        quest = models.Quest(id=1, npc_id=1, title="t", description="", quest_type="standard", min_level=1,
                             reward_currency=0, reward_exp=0, is_active=True, objectives=[])
        with patch.object(crud, "update_quest", AsyncMock(return_value=quest)) as update:
            r = admin_client.put("/locations/admin/quests/1", json={"min_fame_tier": "", "fame_reward": None})
        assert r.status_code == 200, r.text
        assert update.await_args.args[2] == {"min_fame_tier": None, "fame_reward": None}
        assert r.json()["min_fame_tier"] is None and r.json()["fame_reward"] is None

    def test_create_passes_the_fields_to_crud(self, admin_client):
        quest = models.Quest(id=1, npc_id=1, title="t", description="", quest_type="standard", min_level=1,
                             reward_currency=0, reward_exp=0, is_active=True, objectives=[],
                             min_fame_tier="known", fame_reward=12)
        with patch.object(crud, "create_quest", AsyncMock(return_value=quest)) as create:
            r = admin_client.post("/locations/admin/quests",
                                  json={"npc_id": 1, "title": "t", "min_fame_tier": " known ", "fame_reward": 12})
        assert r.status_code == 200, r.text
        sent = create.await_args.args[1]
        assert (sent["min_fame_tier"], sent["fame_reward"]) == ("known", 12)
        assert (r.json()["min_fame_tier"], r.json()["fame_reward"]) == ("known", 12)


@pytest.mark.real_reputation
class TestFameCrudPersistence:

    async def test_create_and_update_store_the_fields(self, qdb):
        quest = await crud.create_quest(qdb, {"npc_id": Q_NPC, "title": "Новое", "description": "",
                                              "quest_type": "standard", "min_level": 1, "objectives": [],
                                              "min_fame_tier": "familiar", "fame_reward": 0})
        await qdb.commit()
        assert (quest.min_fame_tier, quest.fame_reward) == ("familiar", 0)

        async def _row():
            return tuple((await qdb.execute(text("SELECT min_fame_tier, fame_reward FROM quests WHERE id = :i"),
                                            {"i": quest.id})).first())

        await crud.update_quest(qdb, quest.id, {"title": "Новое 2"})
        await qdb.commit()
        assert await _row() == ("familiar", 0)                          # untouched when not sent
        await crud.update_quest(qdb, quest.id, {"min_fame_tier": "legend", "fame_reward": 40})
        await qdb.commit()
        assert await _row() == ("legend", 40)
        await crud.update_quest(qdb, quest.id, {"min_fame_tier": None, "fame_reward": None})
        await qdb.commit()
        assert await _row() == (None, None)

    async def test_create_without_fields_defaults_to_null(self, qdb):
        quest = await crud.create_quest(qdb, {"npc_id": Q_NPC, "title": "Простое", "description": "",
                                              "quest_type": "standard", "min_level": 1, "objectives": []})
        await qdb.commit()
        assert (quest.min_fame_tier, quest.fame_reward) == (None, None)


# ═══════════════════════════════════════════════════════════════════════════
# fame_read pure helpers
# ═══════════════════════════════════════════════════════════════════════════

class TestFameReadHelpers:

    def test_seed_ladder_matches_the_character_service_seed(self):
        assert [(t.code, t.name, t.min_value) for t in fame_read.DEFAULT_FAME_TIERS] == [
            (code, name, mv) for scale, code, _o, name, mv in SEED_TIERS if scale == "fame"]

    def test_tiers_from_rows(self):
        assert fame_read.tiers_from_rows([]) == fame_read.DEFAULT_FAME_TIERS
        assert fame_read.tiers_from_rows(None) == fame_read.DEFAULT_FAME_TIERS
        tiers = fame_read.tiers_from_rows([("known", "B", 200, 3), ("nameless", "A", 0, 1)])
        assert [t.code for t in tiers] == ["nameless", "known"]

    @pytest.mark.parametrize("value,code", [(0, "nameless"), (49, "nameless"), (50, "familiar"), (599, "known"),
                                            (1500, "legend"), (-5, "nameless")])
    def test_tier_for(self, value, code):
        assert fame_read.tier_for(value, fame_read.DEFAULT_FAME_TIERS).code == code

    def test_reason(self):
        gates = fame_read.FameGates(100, fame_read.DEFAULT_FAME_TIERS)
        assert gates.reason(None) is None and gates.reason("") is None
        assert gates.reason("familiar") is None
        assert gates.reason("known") == "Нужна слава: Известный"
        assert gates.reason("bogus") is None

    async def test_quest_fame_gates_reads_nothing_without_codes(self):
        session = MagicMock()
        session.execute = AsyncMock()
        assert await fame_read.quest_fame_gates(session, 1, [None, None, ""]) is fame_read.OPEN_FAME_GATES
        assert await fame_read.quest_fame_gates(session, 1, []) is fame_read.OPEN_FAME_GATES
        session.execute.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# Migration 056
# ═══════════════════════════════════════════════════════════════════════════

def _load_056():
    path = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "056_quest_fame.py")
    spec = importlib.util.spec_from_file_location("mig056", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_056_chain():
    mod = _load_056()
    assert mod.revision == "056_quest_fame" and len(mod.revision) <= 32
    assert mod.down_revision == "055_region_jail_location"


def test_migration_056_upgrade_downgrade_upgrade(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    mod = _load_056()
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    cols = lambda conn: {c["name"]: c for c in inspect(conn).get_columns("quests")}  # noqa: E731
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE quests (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO quests (id, title) VALUES (1, 'Старый')"))
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        c = cols(conn)
        assert set(c) == {"id", "title", "min_fame_tier", "fame_reward"}
        assert c["min_fame_tier"]["nullable"] and c["fame_reward"]["nullable"]
        assert tuple(conn.execute(text("SELECT min_fame_tier, fame_reward FROM quests")).first()) == (None, None)
        with Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()
        assert set(cols(conn)) == {"id", "title"}
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        assert set(cols(conn)) == {"id", "title", "min_fame_tier", "fame_reward"}
    engine.dispose()


def test_models_carry_the_columns():
    c = models.Quest.__table__.c
    assert {"min_fame_tier", "fame_reward"} <= set(c.keys())
    assert c.min_fame_tier.type.length == 20 and c.min_fame_tier.nullable and c.fame_reward.nullable
