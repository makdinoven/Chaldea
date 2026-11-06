"""FEAT-207 (task 11): factions in battle-service.

* ``faction_passives.apply``: every key added; a primary also moves its derived stats by the CAPPED worth of the change
  (``buffs._DERIVED_PER_POINT`` + ``stat_caps.effective_delta``), nothing else touched;
* ``faction_passives.fetch_faction_passives``: URL + internal token, filters junk values, soft-fail -> {};
* ``build_participant_info``: the passive is folded into the snapshot attributes of a player, an NPC is never looked
  up, a failed lookup leaves the snapshot intact;
* kill-points callback: payload (fallen winners ``alive: false``, ``mob_template_id`` only for losers, enum battle
  type), fire-and-forget task, retries (5xx / network), 4xx final, never raises; inside ``_finalize_battle`` it is
  sent only with a winner and a broken payload never breaks the ending.

Preamble follows test_law_guard_battle.py / test_subclass_passives.py (FEAT-163 harness, private real modules).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database  # noqa: E402

database.engine = MagicMock()

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())
for _mod in ("mongo_client", "mongo_helpers", "tasks", "inventory_client",
             "character_client", "skills_client", "rabbitmq_publisher"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
_tasks = sys.modules["tasks"]
if isinstance(_tasks, MagicMock):
    _tasks.save_log = MagicMock()
    _tasks.save_log.delay = MagicMock()

import main  # noqa: E402
from _feat163_harness import (  # noqa: E402
    FakeDB, FakeRedis, FakeResult, make_participant, patch_main, seed_battle, utc_now,
)

main.app.router.on_startup.clear()


def _load_private(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Real modules under private names: other test files park MagicMocks in sys.modules["buffs"].
stat_caps = _load_private("_feat207_stat_caps", "stat_caps.py")
with patch.dict(sys.modules, {"stat_caps": stat_caps}):
    buffs = _load_private("_feat207_buffs", "buffs.py")
with patch.dict(sys.modules, {"stat_caps": stat_caps, "buffs": buffs}):
    fp = _load_private("_feat207_faction_passives", "faction_passives.py")

PHYSICAL = ("res_physical", "res_catting", "res_crushing", "res_piercing")
MAGICAL = ("res_magic", "res_fire", "res_ice", "res_watering",
           "res_electricity", "res_wind", "res_sainting", "res_damning")


# ===========================================================================
# 1. apply
# ===========================================================================

class TestApply:
    def test_derived_table_is_the_real_one(self):
        assert isinstance(fp._DERIVED_PER_POINT, dict)
        assert set(fp._DERIVED_PER_POINT) == {"strength", "agility", "intelligence", "endurance", "luck"}

    def test_plain_keys_are_added(self):
        attrs = {"damage": 10, "res_fire": 5.0, "critical_damage": 125}
        fp.apply(attrs, {"damage": 3, "res_fire": 2, "vul_ice": 4, "critical_damage": 10})
        assert attrs == {"damage": 13, "res_fire": 7.0, "vul_ice": 4, "critical_damage": 135}

    def test_strength_below_cap_moves_physical_resists(self):
        attrs = {"strength": 50, **{k: 1.0 for k in PHYSICAL}, "res_fire": 0.0}
        fp.apply(attrs, {"strength": 10})
        assert attrs["strength"] == 60
        for k in PHYSICAL:
            assert attrs[k] == pytest.approx(2.0)          # 10 points * 0.1
        assert attrs["res_fire"] == 0.0                    # magical untouched

    def test_strength_across_the_soft_cap_is_capped(self):
        attrs = {"strength": 190}
        fp.apply(attrs, {"strength": 20})
        # eff(210) - eff(190) = (150 + 10*0.25) - (100 + 90*0.5) = 152.5 - 145 = 7.5
        assert attrs["strength"] == 210
        for k in PHYSICAL:
            assert attrs[k] == pytest.approx(0.75)

    def test_intelligence_moves_magical_resists(self):
        attrs = {"intelligence": 0}
        fp.apply(attrs, {"intelligence": 5})
        for k in MAGICAL:
            assert attrs[k] == pytest.approx(0.5)

    def test_luck_and_agility_stack_on_dodge(self):
        attrs = {"agility": 10, "luck": 10, "dodge": 5.0, "critical_hit_chance": 20.0, "res_effects": 1.0}
        fp.apply(attrs, {"agility": 10, "luck": 10})
        assert attrs["dodge"] == pytest.approx(5.0 + 1.0 + 1.0)
        assert attrs["critical_hit_chance"] == pytest.approx(21.0)
        assert attrs["res_effects"] == pytest.approx(2.0)

    def test_endurance_moves_effect_resist(self):
        attrs = {"endurance": None}
        fp.apply(attrs, {"endurance": 10})
        assert attrs["endurance"] == 10 and attrs["res_effects"] == pytest.approx(2.0)

    def test_no_resource_keys_are_touched(self):
        attrs = {"strength": 10, "max_health": 100, "current_health": 80}
        fp.apply(attrs, {"strength": 5})
        assert (attrs["max_health"], attrs["current_health"]) == (100, 80)

    @pytest.mark.parametrize("mods", [{}, None])
    def test_empty_modifiers_change_nothing(self, mods):
        attrs = {"strength": 10}
        assert fp.apply(attrs, mods) == {"strength": 10}

    def test_non_dict_attributes_returned_as_is(self):
        assert fp.apply(None, {"strength": 1}) is None


# ===========================================================================
# 2. fetch_faction_passives
# ===========================================================================

def _cm(client):
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = False
    return cm


def _get_client(resp=None, exc=None):
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp, side_effect=exc)
    return client


class TestFetch:
    @pytest.mark.asyncio
    async def test_url_token_and_filtering(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "tok207")
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"modifiers": {"strength": 5, "dodge": 1.5, "zero": 0, "flag": True, "txt": "x"}}
        client = _get_client(resp)
        with patch.object(fp.httpx, "AsyncClient", return_value=_cm(client)):
            out = await fp.fetch_faction_passives(42)
        assert out == {"strength": 5, "dodge": 1.5}
        assert client.get.await_args.args[0].endswith("/characters/internal/factions/42/passive-modifiers")
        assert client.get.await_args.kwargs["headers"] == {"X-Internal-Token": "tok207"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resp,exc", [
        (MagicMock(status_code=500), None),
        (MagicMock(status_code=404), None),
        (None, httpx.ConnectError("down")),
        (None, httpx.ReadTimeout("slow")),
    ], ids=["5xx", "4xx", "connect", "timeout"])
    async def test_soft_fail(self, resp, exc):
        with patch.object(fp.httpx, "AsyncClient", return_value=_cm(_get_client(resp, exc))):
            assert await fp.fetch_faction_passives(42) == {}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [{"modifiers": None}, {"modifiers": ["strength"]}, {}, ["x"]])
    async def test_malformed_body(self, body):
        resp = MagicMock(status_code=200)
        resp.json.return_value = body
        with patch.object(fp.httpx, "AsyncClient", return_value=_cm(_get_client(resp))):
            assert await fp.fetch_faction_passives(42) == {}

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError("not json")
        with patch.object(fp.httpx, "AsyncClient", return_value=_cm(_get_client(resp))):
            assert await fp.fetch_faction_passives(42) == {}


# ===========================================================================
# 3. build_participant_info
# ===========================================================================

BASE_ATTRS = {"current_health": 100, "max_health": 100, "strength": 50, "dodge": 3.0,
              **{k: 0.0 for k in PHYSICAL}}


async def _build(is_npc, fetch, monkeypatch, char_id=77):
    monkeypatch.setattr(fp, "fetch_faction_passives", fetch)
    monkeypatch.setattr(main, "faction_passives", fp)
    for name, value in (
            ("fetch_full_attributes", AsyncMock(return_value=dict(BASE_ATTRS))),
            ("character_skills", AsyncMock(return_value=[])),
            ("get_fast_slots", AsyncMock(return_value=[])),
            ("get_character_profile", AsyncMock(return_value={"character_name": "Ашари", "character_photo": ""})),
            ("get_equipment_durability", AsyncMock(return_value={})),
            ("get_character_subclass", AsyncMock(return_value={"is_npc": is_npc, "subclass_key": None,
                                                               "passive": None})),
    ):
        monkeypatch.setattr(main, name, value)
    return await main.build_participant_info(char_id, 5)


class TestBuildParticipantInfo:
    @pytest.mark.asyncio
    async def test_player_snapshot_carries_the_passive(self, monkeypatch):
        fetch = AsyncMock(return_value={"strength": 10, "damage": 4})
        info = await _build(False, fetch, monkeypatch)
        fetch.assert_awaited_once_with(77)
        a = info["attributes"]
        assert a["strength"] == 60 and a["damage"] == 4
        for k in PHYSICAL:
            assert a[k] == pytest.approx(1.0)
        assert a["dodge"] == 3.0 and a["max_health"] == 100
        assert info["is_npc"] is False and info["name"] == "Ашари"

    @pytest.mark.asyncio
    async def test_npc_is_never_looked_up(self, monkeypatch):
        fetch = AsyncMock(return_value={"strength": 10})
        info = await _build(True, fetch, monkeypatch)
        fetch.assert_not_called()
        assert info["attributes"] == BASE_ATTRS

    @pytest.mark.asyncio
    async def test_failed_lookup_leaves_the_snapshot_intact(self, monkeypatch):
        """The real fetch with character-service down: the battle starts without passives."""
        real_fetch = fp.fetch_faction_passives
        client = _get_client(exc=httpx.ConnectError("character-service down"))

        async def fetch(cid):
            with patch.object(fp.httpx, "AsyncClient", return_value=_cm(client)):
                return await real_fetch(cid)

        info = await _build(False, fetch, monkeypatch)
        assert info["attributes"] == BASE_ATTRS
        assert client.get.await_count == 1


# ===========================================================================
# 4. kill-points callback
# ===========================================================================

def _res(rows):
    r = MagicMock()
    r.fetchone.return_value = rows[0] if rows else None
    r.fetchall.return_value = list(rows)
    return r


def _payload_db(battle_type="pve", mobs=()):
    db = AsyncMock()
    seen = []

    async def execute(query, params=None):
        q = str(query)
        seen.append((q, params))
        if "SELECT battle_type FROM battles" in q:
            return _res([(battle_type,)])
        if "FROM active_mobs" in q:
            return _res(list(mobs))
        return _res([])

    db.execute = AsyncMock(side_effect=execute)
    db.seen = seen
    return db


STATE = {"participants": {
    "1": {"character_id": 10, "team": 1, "hp": 40},
    "2": {"character_id": 11, "team": 1, "hp": 0},       # fallen winner
    "3": {"character_id": 900, "team": 2, "hp": 0},      # mob
    "4": {"character_id": 901, "team": 2, "hp": -5},     # NPC (no active_mobs row)
}}


class TestPayload:
    @pytest.mark.asyncio
    async def test_payload_shape(self):
        db = _payload_db("pve", mobs=[(900, 7)])
        payload = await main._faction_battle_payload(db, 55, STATE, 1)
        assert payload["battle_id"] == 55 and payload["battle_type"] == "pve" and payload["winner_team"] == 1
        by_id = {p["character_id"]: p for p in payload["participants"]}
        assert by_id[10] == {"character_id": 10, "team": 1, "alive": True, "mob_template_id": None}
        assert by_id[11] == {"character_id": 11, "team": 1, "alive": False, "mob_template_id": None}
        assert by_id[900] == {"character_id": 900, "team": 2, "alive": False, "mob_template_id": 7}
        assert by_id[901]["mob_template_id"] is None and by_id[901]["alive"] is False
        mob_query = next(p for q, p in db.seen if "active_mobs" in q)
        assert sorted(mob_query.values()) == [900, 901]          # only losers are resolved

    @pytest.mark.asyncio
    async def test_enum_battle_type_and_missing_row(self):
        db = _payload_db(SimpleNamespace(value="pvp_death"))
        assert (await main._faction_battle_payload(db, 1, STATE, 2))["battle_type"] == "pvp_death"
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_res([]))
        assert (await main._faction_battle_payload(db, 1, STATE, 2))["battle_type"] == "pve"

    @pytest.mark.asyncio
    async def test_no_losers_no_mob_query(self):
        db = _payload_db()
        state = {"participants": {"1": {"character_id": 10, "team": 1, "hp": 5}}}
        await main._faction_battle_payload(db, 1, state, 1)
        assert not any("active_mobs" in q for q, _ in db.seen)

    @pytest.mark.asyncio
    async def test_participants_capped_at_50(self):
        state = {"participants": {str(i): {"character_id": i, "team": 1, "hp": 1} for i in range(1, 61)}}
        payload = await main._faction_battle_payload(_payload_db(), 1, state, 1)
        assert len(payload["participants"]) == 50


class TestNotify:
    @pytest.mark.asyncio
    async def test_posts_in_background(self):
        with patch("main._post_faction_callback", new_callable=AsyncMock) as post:
            await main._notify_faction_battle_end(_payload_db(mobs=[(900, 7)]), 55, STATE, 1)
            await asyncio.sleep(0)
        post.assert_awaited_once()
        assert post.call_args.args[0]["battle_id"] == 55

    @pytest.mark.asyncio
    async def test_payload_error_never_raises(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db gone"))
        with patch("main._post_faction_callback", new_callable=AsyncMock) as post:
            await main._notify_faction_battle_end(db, 55, STATE, 1)
            await asyncio.sleep(0)
        post.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_wait_for_the_callback(self):
        gate = asyncio.Event()

        async def slow(payload):
            await gate.wait()

        with patch("main._post_faction_callback", side_effect=slow):
            await asyncio.wait_for(main._notify_faction_battle_end(_payload_db(), 55, STATE, 1), timeout=1)
        gate.set()
        await asyncio.sleep(0)


class TestPostFactionCallback:
    @pytest.mark.asyncio
    async def test_url_token_and_stop_on_2xx(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text=""))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_faction_callback({"battle_id": 1})
        assert client.post.await_count == 1
        call = client.post.await_args
        assert call.args[0].endswith("/characters/internal/factions/battle-result")
        assert call.kwargs["json"] == {"battle_id": 1}
        assert "X-Internal-Token" in call.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_retries_on_5xx_then_stops(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[MagicMock(status_code=502, text=""),
                                             MagicMock(status_code=200, text="")])
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_faction_callback({"battle_id": 1})
        assert client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_4xx_is_final(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=422, text="bad"))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_faction_callback({"battle_id": 1})
        assert client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_gives_up_after_three_network_errors_without_raising(self, monkeypatch):
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
        client = AsyncMock()
        client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        with patch("main.httpx.AsyncClient", return_value=_cm(client)):
            await main._post_faction_callback({"battle_id": 1})
        assert client.post.await_count == 3


# --- the callback inside the real ending (FEAT-163 harness) -----------------

BATTLE_ID = 7070
PLAYER, MOB = 1, 905


class _MobDB(FakeDB):
    def _dispatch(self, q, p):
        if q.startswith("select character_id, mob_template_id from active_mobs"):
            return FakeResult([(MOB, 33)] if MOB in p.values() else [])
        return super()._dispatch(q, p)


def _fight(db, rds, player_hp=40, mob_hp=0):
    parts = {1: make_participant(PLAYER, team=1, hp=player_hp), 2: make_participant(MOB, team=2, hp=mob_hp)}
    return seed_battle(db, rds, BATTLE_ID, parts, next_actor=1, deadline_at=utc_now() + timedelta(hours=1))


async def _finalize(monkeypatch, winner_team, broken_payload=False):
    db, rds = _MobDB(), FakeRedis()
    spies = patch_main(monkeypatch, main, db, rds, rewards=None)
    state = _fight(db, rds)
    post_cb = AsyncMock()
    monkeypatch.setattr(main, "_post_faction_callback", post_cb)
    monkeypatch.setattr(main, "_post_law_callback", AsyncMock())
    if broken_payload:
        monkeypatch.setattr(main, "_faction_battle_payload", AsyncMock(side_effect=RuntimeError("boom")))
    with patch.object(main.httpx, "AsyncClient") as client_cls:
        client = client_cls.return_value.__aenter__.return_value
        client.put = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        client.get = AsyncMock(return_value=MagicMock(status_code=200, text="ok", json=MagicMock(return_value={})))
        await main._finalize_battle(db_session=db, battle_id=BATTLE_ID, battle_state=state,
                                    winner_team=winner_team, turn_events=[], turn_number=5)
        await asyncio.sleep(0)
    return post_cb, spies, db


class TestCallbackInEnding:
    @pytest.mark.asyncio
    async def test_sent_with_the_winner(self, monkeypatch):
        post_cb, spies, db = await _finalize(monkeypatch, 1)
        post_cb.assert_awaited_once()
        payload = post_cb.call_args.args[0]
        assert payload["battle_id"] == BATTLE_ID and payload["winner_team"] == 1
        assert payload["battle_type"] == "pve"
        by_id = {p["character_id"]: p for p in payload["participants"]}
        assert by_id[MOB]["mob_template_id"] == 33 and by_id[MOB]["alive"] is False
        assert by_id[PLAYER]["alive"] is True and by_id[PLAYER]["mob_template_id"] is None

    @pytest.mark.asyncio
    async def test_broken_payload_does_not_break_the_ending(self, monkeypatch):
        healthy_cb, healthy_spies, healthy_db = await _finalize(monkeypatch, 1)
        healthy_cb.assert_awaited_once()
        post_cb, spies, db = await _finalize(monkeypatch, 1, broken_payload=True)
        post_cb.assert_not_called()
        # everything after the hook (history rows, log, notifications) ran exactly like in a healthy ending
        assert len(db.history) == len(healthy_db.history) > 0
        assert spies.save_log.delay.call_count == healthy_spies.save_log.delay.call_count
