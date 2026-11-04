"""FEAT-197 (task 10): region reputation in locations-service — quests, houses, admin validation.

* quest list: gated quests stay in the list with ``locked_reason`` (NPC gate first, then the quest's own),
  the region is the quest giver's; active / completed quests are never "locked";
* quest accept: 403 «Нужна репутация: X» for the quest gate and the NPC gate, nothing created;
* quest completion: after the COMMIT, ``POST /characters/internal/reputation/apply`` with the key
  ``quest_reward:cq:{id}``, the quest giver's region (player's region as the fallback), ``delta`` only when
  the quest overrides it, 0 = no call; one retry on network errors / 5xx only, a failure never fails the
  completion (mocked HTTP);
* houses: plot gate on purchase and on the resale (buy of a listed house), region of the plot;
* admin validation of tier codes (quests, plots) incl. SQL-injection-like strings (422), reward bounds;
* migration 054: revision chain, idempotent upgrade, exact downgrade.
"""

import contextlib
import importlib.util
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import econ_core  # noqa: E402
import econ_contract_cases as cc  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import reputation_core as rc  # noqa: E402
import reputation_sqlite  # noqa: E402
import schemas  # noqa: E402
from auth_http import UserRead, get_admin_user  # noqa: E402

from test_econ_locations_flows import _back_existing_gold, _one, _user  # noqa: E402
from test_houses import api, _plot, _gold, OWNER, STRANGER, ADMIN, TOWN, REGION  # noqa: E402,F401

APPLY_PATH = "/characters/internal/reputation/apply"
Q_CHAR, Q_USER, Q_NPC = 100, 5, 9
Q_OPEN, Q_GATED = 42, 43
REGION_A, REGION_B = 10, 20          # player stands in 1000 (region 10), the quest giver in 1001 (region 20)


# ═══════════════════════════════════════════════════════════════════════════
# Quest world
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
async def qdb(tmp_path):
    econ_core.invalidate_settings_cache()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rq.db'}", poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "connect")
    def _now(dbapi_conn, _record):  # pragma: no cover - DDL hook
        dbapi_conn.create_function("NOW", 0, lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

    async with engine.begin() as conn:
        for m in (models.Quest, models.QuestObjective, models.CharacterQuest, models.CharacterQuestProgress):
            await conn.run_sync(m.__table__.create)
        await conn.execute(text(
            "CREATE TABLE characters (id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', user_id INTEGER, "
            "currency_balance BIGINT NOT NULL DEFAULT 0, current_location_id INTEGER, level INTEGER DEFAULT 5, "
            "is_npc INTEGER NOT NULL DEFAULT 0)"))
        await conn.execute(text("CREATE TABLE character_attributes (character_id INTEGER PRIMARY KEY, "
                                "passive_experience INTEGER NOT NULL DEFAULT 0, "
                                "active_experience INTEGER NOT NULL DEFAULT 0)"))
        for ddl in cc.SQLITE_DDL:
            await conn.execute(text(ddl))
        for sql, params in cc.SEED_SQL:
            if "INTO characters" not in sql:
                await conn.execute(text(sql), params)
        await conn.execute(text("INSERT INTO characters (id, user_id, currency_balance, current_location_id) "
                                "VALUES (:c, :u, 250, 1000)"), {"c": Q_CHAR, "u": Q_USER})
        await conn.execute(text("INSERT INTO characters (id, current_location_id, is_npc) VALUES (:n, 1001, 1)"),
                           {"n": Q_NPC})
        await conn.execute(text("INSERT INTO character_attributes VALUES (:c, 1000, 0)"), {"c": Q_CHAR})
        await reputation_sqlite.create_async(conn)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        await _back_existing_gold(s)
        for qid, title, gate in ((Q_OPEN, "Гонец", None), (Q_GATED, "Тайное поручение", "trusted")):
            s.add(models.Quest(id=qid, npc_id=Q_NPC, title=title, description="", quest_type="standard",
                               min_level=1, reward_currency=60, reward_exp=10, reward_items=None, is_active=True,
                               min_reputation_tier=gate))
            s.add(models.QuestObjective(quest_id=qid, description="Поговорить", objective_type="talk_npc",
                                        target_id=Q_NPC, target_count=1, sort_order=0))
        await s.commit()
        yield s
    await engine.dispose()
    econ_core.invalidate_settings_cache()


async def _rep(s, value, *, region=REGION_B, cid=Q_CHAR):
    await s.execute(text("INSERT INTO character_reputation (character_id, region_id, value, updated_at) "
                         "VALUES (:c, :r, :v, :u)"), {"c": cid, "r": region, "v": value, "u": datetime.utcnow()})
    await s.commit()


async def _exec(s, sql, **p):
    await s.execute(text(sql), p)
    await s.commit()


async def _active_quest(s, quest_id=Q_OPEN, status="active"):
    """A character quest with its single objective done (ready to complete); returns its id."""
    await _exec(s, "INSERT INTO character_quests (character_id, quest_id, status) VALUES (:c, :q, :st)",
                c=Q_CHAR, q=quest_id, st=status)
    cq_id = await _one(s, "SELECT id FROM character_quests WHERE character_id = :c AND quest_id = :q",
                       c=Q_CHAR, q=quest_id)
    obj = await _one(s, "SELECT id FROM quest_objectives WHERE quest_id = :q", q=quest_id)
    await _exec(s, "INSERT INTO character_quest_progress (character_quest_id, objective_id, current_count, "
                   "is_completed) VALUES (:cq, :o, 1, 1)", cq=cq_id, o=obj)
    return cq_id


def _by_id(rows):
    return {r["id"]: r for r in rows}


# ═══════════════════════════════════════════════════════════════════════════
# Quest list
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.real_reputation
class TestQuestList:

    async def test_gated_quest_stays_listed_with_the_reason(self, qdb):
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert set(rows) == {Q_OPEN, Q_GATED}
        assert rows[Q_OPEN]["locked_reason"] is None
        assert rows[Q_GATED]["locked_reason"] == "Нужна репутация: Свой человек"
        assert rows[Q_GATED]["min_reputation_tier"] == "trusted"
        assert rows[Q_GATED]["player_status"] == "available"

    async def test_reaching_the_tier_unlocks(self, qdb):
        await _rep(qdb, 300)
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert rows[Q_GATED]["locked_reason"] is None

    async def test_region_is_the_quest_givers_not_the_players(self, qdb):
        await _rep(qdb, 900, region=REGION_A)
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert rows[Q_GATED]["locked_reason"] == "Нужна репутация: Свой человек"

    async def test_npc_gate_locks_every_quest_and_comes_first(self, qdb):
        await _exec(qdb, "UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :n", n=Q_NPC)
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert {q: r["locked_reason"] for q, r in rows.items()} == {
            Q_OPEN: "Нужна репутация: Знакомое лицо", Q_GATED: "Нужна репутация: Знакомое лицо"}
        await _rep(qdb, 100)                                    # NPC gate met, the quest's own still not
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert (rows[Q_OPEN]["locked_reason"], rows[Q_GATED]["locked_reason"]) == (
            None, "Нужна репутация: Свой человек")

    async def test_active_and_completed_quests_are_never_locked(self, qdb):
        await _active_quest(qdb, Q_GATED, status="active")
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert (rows[Q_GATED]["player_status"], rows[Q_GATED]["locked_reason"]) == ("active", None)

    async def test_quest_giver_without_a_region_has_no_gates(self, qdb):
        await _exec(qdb, "UPDATE characters SET current_location_id = 1003 WHERE id = :n", n=Q_NPC)
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert rows[Q_GATED]["locked_reason"] is None

    async def test_regionless_npc_gate_is_open(self, qdb):
        # the NPC-level gate does follow "no region = no gate" (only the quest's own gate is affected by the bug)
        await _exec(qdb, "UPDATE characters SET current_location_id = 1003, reputation_min_tier = 'legend' "
                         "WHERE id = :n", n=Q_NPC)
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert rows[Q_OPEN]["locked_reason"] is None

    async def test_unknown_quest_code_in_the_db_is_no_gate(self, qdb):
        await _exec(qdb, "UPDATE quests SET min_reputation_tier = 'bogus' WHERE id = :q", q=Q_GATED)
        rows = _by_id(await crud.get_available_quests_for_npc(qdb, Q_NPC, Q_CHAR))
        assert rows[Q_GATED]["locked_reason"] is None

    def test_list_schema_declares_the_new_fields(self):
        fields = schemas.QuestAvailableRead.__fields__
        assert fields["locked_reason"].default is None and fields["min_reputation_tier"].default is None


# ═══════════════════════════════════════════════════════════════════════════
# Quest accept
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.real_reputation
class TestQuestAccept:

    async def _count(self, s):
        return await _one(s, "SELECT COUNT(*) FROM character_quests WHERE character_id = :c", c=Q_CHAR)

    async def test_quest_gate_is_403_and_creates_nothing(self, qdb):
        with pytest.raises(HTTPException) as exc:
            await crud.accept_quest(qdb, Q_GATED, Q_CHAR)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна репутация: Свой человек")
        assert await self._count(qdb) == 0

    async def test_tier_met_accepts(self, qdb):
        await _rep(qdb, 300)
        cq = await crud.accept_quest(qdb, Q_GATED, Q_CHAR)
        assert cq.status == "active" and await self._count(qdb) == 1

    async def test_npc_gate_is_403_even_for_an_ungated_quest(self, qdb):
        await _exec(qdb, "UPDATE characters SET reputation_min_tier = 'defender' WHERE id = :n", n=Q_NPC)
        await _rep(qdb, 300)
        with pytest.raises(HTTPException) as exc:
            await crud.accept_quest(qdb, Q_OPEN, Q_CHAR)
        assert (exc.value.status_code, exc.value.detail) == (403, "Нужна репутация: Заступник")
        assert await self._count(qdb) == 0

    async def test_low_reputation_does_not_block_an_ungated_quest(self, qdb):
        await _rep(qdb, -700)                                   # outlaw: quests are not trade
        cq = await crud.accept_quest(qdb, Q_OPEN, Q_CHAR)
        assert cq.status == "active"

    async def test_regionless_quest_giver_accepts_a_gated_quest(self, qdb):
        await _exec(qdb, "UPDATE characters SET current_location_id = 1003 WHERE id = :n", n=Q_NPC)
        cq = await crud.accept_quest(qdb, Q_GATED, Q_CHAR)
        assert cq.status == "active"

    async def test_route_maps_the_gate_to_403(self, qdb):
        with patch.object(main, "check_not_activity_locked", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await main.accept_quest(quest_id=Q_GATED, body=schemas.QuestAcceptRequest(character_id=Q_CHAR),
                                        session=qdb, current_user=_user(Q_USER))
        assert exc.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Quest completion -> internal reputation call
# ═══════════════════════════════════════════════════════════════════════════

class _Rep:
    """httpx.AsyncClient stand-in; `answers` = what successive reputation calls return (int status or
    an exception). Records each call and the character quest's status seen at call time."""

    def __init__(self, qdb, answers=(200,)):
        self.answers = list(answers)
        self.calls = []
        self.status_at_call = []
        self.qdb = qdb
        client = AsyncMock()
        client.post = AsyncMock(side_effect=self._post)
        self.factory = MagicMock()
        self.factory.return_value.__aenter__ = AsyncMock(return_value=client)
        self.factory.return_value.__aexit__ = AsyncMock(return_value=False)

    async def _post(self, url, json=None, headers=None, **kw):
        if not url.endswith(APPLY_PATH):
            return MagicMock(status_code=200)
        self.calls.append({"url": url, "json": json, "headers": headers})
        # a separate connection sees only committed data
        async with AsyncSession(bind=self.qdb.bind) as other:
            self.status_at_call.append(await _one(other, "SELECT status FROM character_quests WHERE id = :i",
                                                  i=json and int(json["idempotency_key"].rsplit(":", 1)[1])))
        answer = self.answers.pop(0) if self.answers else 200
        if isinstance(answer, Exception):
            raise answer
        return MagicMock(status_code=answer)


@contextlib.contextmanager
def _patched(rep):
    with patch.object(main.httpx, "AsyncClient", rep.factory), patch.object(crud.httpx, "AsyncClient", rep.factory), \
            patch.object(main, "check_not_activity_locked", AsyncMock(return_value=None)), \
            patch.object(main, "_track_cumulative_stats", AsyncMock(return_value=None)), \
            patch.object(main, "_auto_progress_quest", AsyncMock(return_value=None)), \
            patch.object(crud, "get_character_xp_multiplier", AsyncMock(return_value=None)):
        yield


async def _complete(s, rep, quest_id=Q_OPEN):
    with _patched(rep):
        return await main.complete_quest(quest_id=quest_id, body=schemas.QuestCompleteRequest(character_id=Q_CHAR),
                                         request=MagicMock(), session=s, current_user=_user(Q_USER))


@pytest.mark.real_reputation
class TestQuestCompletion:

    async def test_default_reward_call_after_the_commit(self, qdb):
        cq = await _active_quest(qdb)
        rep = _Rep(qdb)
        out = await _complete(qdb, rep)
        assert out["success"] is True
        assert len(rep.calls) == 1
        call = rep.calls[0]
        assert call["url"].endswith(APPLY_PATH)
        assert call["json"] == {"character_id": Q_CHAR, "region_id": REGION_B, "action": rc.ACTION_QUEST,
                                "idempotency_key": f"quest_reward:cq:{cq}"}   # no delta = the action default
        assert "X-Internal-Token" in call["headers"]
        assert rep.status_at_call == ["completed"]                       # committed before the HTTP call

    @pytest.mark.parametrize("reward", [25, -40, 1000])
    async def test_quest_override_is_sent_as_delta(self, qdb, reward):
        await _exec(qdb, "UPDATE quests SET reputation_reward = :r WHERE id = :q", r=reward, q=Q_OPEN)
        await _active_quest(qdb)
        rep = _Rep(qdb)
        await _complete(qdb, rep)
        assert rep.calls[0]["json"]["delta"] == reward

    async def test_zero_reward_makes_no_call(self, qdb):
        await _exec(qdb, "UPDATE quests SET reputation_reward = 0 WHERE id = :q", q=Q_OPEN)
        await _active_quest(qdb)
        rep = _Rep(qdb)
        out = await _complete(qdb, rep)
        assert out["success"] is True and rep.calls == []

    async def test_quest_giver_without_a_place_uses_the_players_region(self, qdb):
        await _exec(qdb, "UPDATE characters SET current_location_id = NULL WHERE id = :n", n=Q_NPC)
        await _active_quest(qdb)
        rep = _Rep(qdb)
        await _complete(qdb, rep)
        assert rep.calls[0]["json"]["region_id"] == REGION_A

    async def test_no_region_anywhere_makes_no_call(self, qdb):
        await _exec(qdb, "UPDATE characters SET current_location_id = NULL WHERE id = :n", n=Q_NPC)
        await _exec(qdb, "UPDATE characters SET current_location_id = 1003 WHERE id = :c", c=Q_CHAR)
        await _active_quest(qdb)
        rep = _Rep(qdb)
        out = await _complete(qdb, rep)
        assert out["success"] is True and rep.calls == []

    @pytest.mark.parametrize("answers,calls", [
        ((503, 200), 2),
        ((httpx.ConnectError("down"), 200), 2),
        ((httpx.ReadTimeout("slow"), 200), 2),
        ((500, 500), 2),                                         # one retry only
        ((httpx.ConnectError("down"), httpx.ConnectError("down")), 2),
        ((404,), 1),                                             # 4xx is not retried
        ((422,), 1),
    ])
    async def test_retry_policy_and_completion_never_fails(self, qdb, answers, calls):
        cq = await _active_quest(qdb)
        rep = _Rep(qdb, answers)
        out = await _complete(qdb, rep)
        assert out["success"] is True and out["new_balance"] == 310
        assert len(rep.calls) == calls
        assert {c["json"]["idempotency_key"] for c in rep.calls} == {f"quest_reward:cq:{cq}"}   # same key
        assert await _one(qdb, "SELECT status FROM character_quests WHERE id = :i", i=cq) == "completed"

    @pytest.mark.parametrize("error", [RuntimeError("boom"), ValueError("bad json"), KeyError("x")])
    async def test_unexpected_error_never_fails_the_completion(self, qdb, error):
        """FEAT-200 (fix 9): any exception after the commit is logged, not retried, and never a 500."""
        cq = await _active_quest(qdb)
        rep = _Rep(qdb, (error,))
        with patch.object(main, "logger") as log:
            out = await _complete(qdb, rep)
        assert out["success"] is True and out["new_balance"] == 310
        assert len(rep.calls) == 1                                               # no retry
        assert await _one(qdb, "SELECT status FROM character_quests WHERE id = :i", i=cq) == "completed"
        log.exception.assert_called_once()

    async def test_helper_returns_false_on_an_unexpected_error(self, qdb):
        rep = _Rep(qdb, (RuntimeError("boom"),))
        with _patched(rep), patch.object(main, "logger") as log:
            assert await main._apply_quest_reputation(Q_CHAR, REGION_B, 7, None) is False
        assert "unexpectedly" in log.exception.call_args.args[0]

    async def test_helper_returns_whether_it_was_applied(self, qdb):
        rep = _Rep(qdb, (503, 503))
        with _patched(rep):
            assert await main._apply_quest_reputation(Q_CHAR, REGION_B, 7, None) is False
        rep = _Rep(qdb, (200,))
        with _patched(rep):
            assert await main._apply_quest_reputation(Q_CHAR, REGION_B, 7, -5) is True
        assert rep.calls[0]["json"]["delta"] == -5


class TestQuestCompletionNeutral:
    """Without @real_reputation the conftest default (no region) applies: no reputation call at all."""

    async def test_default_fixture_makes_no_call(self, qdb):
        await _active_quest(qdb)
        rep = _Rep(qdb)
        out = await _complete(qdb, rep)
        assert out["success"] is True and rep.calls == []


# ═══════════════════════════════════════════════════════════════════════════
# Houses: plot gate on purchase and on resale
# ═══════════════════════════════════════════════════════════════════════════

def _rep_tables(api):
    for ddl in reputation_sqlite.REPUTATION_SQLITE_DDL:
        api.sql(ddl)


def _house_rep(api, cid, value, region=REGION):
    api.sql("INSERT INTO character_reputation (character_id, region_id, value, updated_at) VALUES (:c, :r, :v, :u)",
            c=cid, r=region, v=value, u=datetime.utcnow())


@pytest.mark.real_reputation
class TestHouseGates:

    def test_purchase_needs_the_plot_tier(self, api):
        _rep_tables(api)
        pid = _plot(api, min_reputation_tier="trusted")
        assert api.get(f"/plots/{pid}").json()["min_reputation_tier"] == "trusted"
        r = api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10})
        assert (r.status_code, r.json()["detail"]) == (403, "Нужна репутация: Свой человек")
        assert _gold(api, 10) == 1000
        _house_rep(api, 10, 300)
        assert api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).status_code == 200
        assert _gold(api, 10) == 700

    def test_reputation_elsewhere_does_not_count(self, api):
        _rep_tables(api)
        pid = _plot(api, min_reputation_tier="familiar")
        _house_rep(api, 10, 900, region=REGION + 1)
        assert api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).status_code == 403

    def test_ungated_plot_ignores_bad_standing(self, api):
        _rep_tables(api)
        pid = _plot(api)
        _house_rep(api, 10, -1000)
        assert api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).status_code == 200

    def test_resale_needs_the_plot_tier(self, api):
        _rep_tables(api)
        pid = _plot(api, min_reputation_tier="trusted")
        _house_rep(api, 10, 300)
        hid = api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).json()["house_id"]
        assert api.put(f"/{hid}/sale", {"character_id": 10, "price": 400}).status_code == 200
        seller, buyer = _gold(api, 10), _gold(api, 30)
        r = api.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30})
        assert (r.status_code, r.json()["detail"]) == (403, "Нужна репутация: Свой человек")
        assert (_gold(api, 10), _gold(api, 30)) == (seller, buyer)
        assert api.get(f"/{hid}").json()["owner"]["id"] == 10
        _house_rep(api, 30, 300)
        assert api.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30}).status_code == 200
        assert (_gold(api, 10), _gold(api, 30)) == (seller + 400, buyer - 400)

    def test_admin_clears_and_sets_the_plot_gate(self, api):
        _rep_tables(api)
        pid = _plot(api, min_reputation_tier="legend")
        body = api.as_(ADMIN).get(f"/plots/{pid}").json()
        assert body["min_reputation_tier"] == "legend"
        upd = {"location_id": TOWN, "name": "Дом", "price": 300, "grid_w": 2, "grid_h": 2,
               "layers": [{"layer": "floor1"}],
               "cells": [{"layer": "floor1", "x": x, "y": y} for y in range(2) for x in range(2)],
               "rooms": [{"room_type": "hall", "name": "Гостиная", "x": 0, "y": 0}],
               "min_reputation_tier": ""}
        r = api.as_(ADMIN).put(f"/admin/plots/{pid}", upd)
        assert r.status_code == 200, r.text
        assert api.get(f"/plots/{pid}").json()["min_reputation_tier"] is None
        assert api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).status_code == 200

    @pytest.mark.parametrize("bad", ["Trusted", "boss", "trusted' OR '1'='1", "legend; DROP TABLE house_plots;--", 7])
    def test_admin_plot_with_an_unknown_tier_is_422(self, api, bad):
        body = {"location_id": TOWN, "name": "Дом", "price": 1, "grid_w": 1, "grid_h": 1,
                "layers": [{"layer": "floor1"}], "cells": [{"layer": "floor1", "x": 0, "y": 0}],
                "rooms": [{"room_type": "hall", "name": "a", "x": 0, "y": 0}], "min_reputation_tier": bad}
        r = api.as_(ADMIN).post("/admin/plots", body)
        assert r.status_code == 422
        assert api.sql("SELECT COUNT(*) FROM house_plots")[0][0] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Admin schema validation (quests)
# ═══════════════════════════════════════════════════════════════════════════

BAD_CODES = ["Trusted", "TRUSTED", "boss", "trusted' OR '1'='1", "legend; DROP TABLE quests;--",
             "' UNION SELECT password FROM users--", "<script>alert(1)</script>", "x" * 500, 5]


class TestQuestSchemas:

    @pytest.mark.parametrize("code", rc.TIER_CODES)
    def test_every_fixed_code_is_accepted(self, code):
        assert schemas.QuestCreate(npc_id=1, title="t", min_reputation_tier=code).min_reputation_tier == code

    @pytest.mark.parametrize("raw,clean", [(None, None), ("", None), ("   ", None), (" legend ", "legend")])
    def test_blank_means_no_gate_and_spaces_are_trimmed(self, raw, clean):
        assert schemas.QuestUpdate(min_reputation_tier=raw).min_reputation_tier == clean

    @pytest.mark.parametrize("code", BAD_CODES)
    @pytest.mark.parametrize("model", [schemas.QuestCreate, schemas.QuestUpdate])
    def test_unknown_codes_are_rejected(self, model, code):
        with pytest.raises(ValidationError) as exc:
            model(npc_id=1, title="t", min_reputation_tier=code)
        assert "Неизвестная ступень репутации" in str(exc.value)

    @pytest.mark.parametrize("value,ok", [(-1000, True), (1000, True), (0, True), (-1001, False), (1001, False)])
    def test_reward_bounds(self, value, ok):
        if ok:
            assert schemas.QuestCreate(npc_id=1, title="t", reputation_reward=value).reputation_reward == value
        else:
            with pytest.raises(ValidationError):
                schemas.QuestCreate(npc_id=1, title="t", reputation_reward=value)

    def test_update_keeps_unsent_fields_unset_and_sends_explicit_null(self):
        assert "min_reputation_tier" not in schemas.QuestUpdate(title="x").dict(exclude_unset=True)
        data = schemas.QuestUpdate(min_reputation_tier=None, reputation_reward=None).dict(exclude_unset=True)
        assert data == {"min_reputation_tier": None, "reputation_reward": None}


async def _mock_db():
    """Request DB for routes that must never reach it (validation fails first) or whose crud is mocked."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    yield db


@pytest.fixture()
def admin_client():
    _fake_get_db = _mock_db
    from database import get_db
    main.app.dependency_overrides[get_db] = _fake_get_db
    main.app.dependency_overrides[get_admin_user] = lambda: UserRead(id=1, username="a", role="admin",
                                                                     permissions=[])
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


class TestQuestAdminHttp:

    @pytest.mark.parametrize("code", ["boss", "trusted' OR '1'='1", "legend; DROP TABLE quests;--"])
    def test_create_with_an_unknown_tier_is_422_and_touches_nothing(self, admin_client, code):
        with patch.object(crud, "create_quest", AsyncMock()) as create:
            r = admin_client.post("/locations/admin/quests",
                                  json={"npc_id": 1, "title": "t", "min_reputation_tier": code})
        assert r.status_code == 422
        create.assert_not_awaited()

    def test_update_with_an_out_of_range_reward_is_422(self, admin_client):
        with patch.object(crud, "update_quest", AsyncMock()) as update:
            r = admin_client.put("/locations/admin/quests/1", json={"reputation_reward": 5000})
        assert r.status_code == 422
        update.assert_not_awaited()

    def test_update_passes_the_explicit_clear_to_crud(self, admin_client):
        quest = models.Quest(id=1, npc_id=1, title="t", description="", quest_type="standard", min_level=1,
                             reward_currency=0, reward_exp=0, is_active=True, objectives=[])
        with patch.object(crud, "update_quest", AsyncMock(return_value=quest)) as update:
            r = admin_client.put("/locations/admin/quests/1",
                                 json={"min_reputation_tier": "", "reputation_reward": None})
        assert r.status_code == 200, r.text
        assert update.await_args.args[2] == {"min_reputation_tier": None, "reputation_reward": None}

    def test_non_admin_cannot_create(self):
        _fake_get_db = _mock_db
        from database import get_db
        main.app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(main.app) as c:
                r = c.post("/locations/admin/quests", json={"npc_id": 1, "title": "t"})
        finally:
            main.app.dependency_overrides.clear()
        assert r.status_code in (401, 403)

    @pytest.mark.parametrize("value", ["1 OR 1=1", "1;DROP TABLE characters", "abc"])
    def test_shop_character_id_must_be_an_int(self, client, value):
        assert client.get(f"/locations/npcs/5/shop?character_id={value}").status_code == 422
        assert client.get(f"/locations/npcs/5/quests?character_id={value}").status_code == 422


@pytest.mark.real_reputation
class TestQuestCrudPersistence:

    async def test_create_and_update_store_the_fields(self, qdb):
        quest = await crud.create_quest(qdb, {"npc_id": Q_NPC, "title": "Новое", "description": "",
                                              "quest_type": "standard", "min_level": 1, "objectives": [],
                                              "reputation_reward": -20, "min_reputation_tier": "watched"})
        await qdb.commit()
        assert (quest.reputation_reward, quest.min_reputation_tier) == (-20, "watched")
        await crud.update_quest(qdb, quest.id, {"title": "Новое 2"})
        await qdb.commit()
        row = (await qdb.execute(text("SELECT reputation_reward, min_reputation_tier FROM quests WHERE id = :i"),
                                 {"i": quest.id})).first()
        assert tuple(row) == (-20, "watched")                        # untouched when not sent
        await crud.update_quest(qdb, quest.id, {"reputation_reward": None, "min_reputation_tier": None})
        await qdb.commit()
        row = (await qdb.execute(text("SELECT reputation_reward, min_reputation_tier FROM quests WHERE id = :i"),
                                 {"i": quest.id})).first()
        assert tuple(row) == (None, None)


# ═══════════════════════════════════════════════════════════════════════════
# Migration 054
# ═══════════════════════════════════════════════════════════════════════════

def _load_054():
    path = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "054_reputation_gates.py")
    spec = importlib.util.spec_from_file_location("mig054", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_054_chain():
    mod = _load_054()
    assert mod.revision == "054_reputation_gates" and len(mod.revision) <= 32
    assert mod.down_revision == "053_npc_shop_market"


def test_migration_054_upgrade_is_idempotent_and_downgrade_exact(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    mod = _load_054()
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE quests (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("CREATE TABLE house_plots (id INTEGER PRIMARY KEY, name TEXT)"))
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
            mod.upgrade()                                            # re-run: no duplicate column error
        cols = lambda t: {c["name"] for c in inspect(conn).get_columns(t)}  # noqa: E731
        assert cols("quests") == {"id", "title", "reputation_reward", "min_reputation_tier"}
        assert cols("house_plots") == {"id", "name", "min_reputation_tier"}
        with Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()
            mod.downgrade()
        assert cols("quests") == {"id", "title"} and cols("house_plots") == {"id", "name"}
    engine.dispose()


def test_models_carry_the_columns():
    assert {"reputation_reward", "min_reputation_tier"} <= set(models.Quest.__table__.c.keys())
    assert "min_reputation_tier" in models.HousePlot.__table__.c.keys()
    assert models.Quest.__table__.c.min_reputation_tier.type.length == 20
