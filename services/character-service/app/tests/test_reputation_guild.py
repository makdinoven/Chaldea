"""FEAT-197 QA (task 9): merchant guild — hand-in reputation (step 10b) and the gates (§3.14 A4).

Reuses the guild world of ``test_econ_guild_api`` (region 10 «Регион 10» and 20 in country 1; guild NPC 60 @100).
"""

from unittest.mock import MagicMock

import pytest

import reputation_notify
from tests.test_econ_guild_api import (  # noqa: F401  (fixtures)
    ALPHA, G_NPC, WOOD, _exec, _q, _rows, client, factory, give, post, view, world,
)


@pytest.fixture(autouse=True)
def no_rabbit(monkeypatch):
    sent = MagicMock(name="reputation_notify._send")
    monkeypatch.setattr(reputation_notify, "_send", sent)
    return sent


def rep(f, region_id=10, cid=ALPHA):
    v = _q(f, "SELECT value FROM character_reputation WHERE character_id = :c AND region_id = :r", c=cid, r=region_id)
    return None if v is None else int(v)


def set_rep(f, val, region_id=10):
    _exec(f, "INSERT INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
             "VALUES (:c, :r, :v, NULL, CURRENT_TIMESTAMP)", c=ALPHA, r=region_id, v=val)


def test_hand_in_gives_reputation_keyed_like_the_ledger(client, world):
    give(world, ALPHA, WOOD, 10)
    resp = post(client, quantity=2, request_id="req-rep-0001")
    assert resp.status_code == 200, resp.text
    assert "reputation_tier_changes" not in resp.json()                 # popped by the router
    assert rep(world) == 2
    assert _rows(world, "SELECT action, event_key, applied_delta, is_echo FROM reputation_log") == [
        ("guild_delivery", "guild:1:req-rep-0001", 2, 0)]               # echo of 2 × 20 % = 0
    # a retry with the same request id is not a second delivery
    post(client, quantity=2, request_id="req-rep-0001")
    assert rep(world) == 2


def test_hand_in_reputation_daily_cap(client, world):
    give(world, ALPHA, WOOD, 40)
    for i in range(12):
        assert post(client, quantity=1, request_id=f"req-cap-{i:04d}").status_code == 200
    assert rep(world) == 20                                             # +2 each, cap 20 per region per day
    assert _q(world, "SELECT COUNT(*) FROM reputation_log") == 10


def test_hand_in_publishes_tier_change_after_commit(client, world, no_rabbit):
    set_rep(world, 99)
    give(world, ALPHA, WOOD, 5)
    assert post(client, quantity=1).status_code == 200
    payloads = [p for c in no_rabbit.call_args_list for p in c.args[0]]
    assert [p["message"] for p in payloads] == ["Жители края «Регион 10» теперь считают вас: Знакомое лицо"]


def test_outlaw_is_refused_by_the_guild(client, world):
    set_rep(world, -600)
    give(world, ALPHA, WOOD, 5)
    resp = post(client, quantity=1)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Гильдия не работает с теми, кто вне закона (репутация: Вне закона)"
    v = view(client).json()
    assert v["reputation_lock"] == resp.json()["detail"]
    assert v["working"] is False and v["closed_reason"] == resp.json()["detail"] and not v.get("orders")
    assert _q(world, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'guild_order'") == 0


def test_outcast_still_trades_with_the_guild(client, world):
    set_rep(world, -599)
    give(world, ALPHA, WOOD, 5)
    assert post(client, quantity=1).status_code == 200
    assert view(client).json()["reputation_lock"] is None


def test_npc_gate_on_the_guild_master(client, world):
    _exec(world, "UPDATE characters SET reputation_min_tier = 'trusted' WHERE id = :i", i=G_NPC)
    give(world, ALPHA, WOOD, 5)
    resp = post(client, quantity=1)
    assert resp.status_code == 403 and resp.json()["detail"] == "Нужна репутация: Свой человек"
    assert view(client).json()["reputation_lock"] == "Нужна репутация: Свой человек"
    set_rep(world, 300)
    assert post(client, quantity=1).status_code == 200


def test_other_region_reputation_does_not_open_the_gate(client, world):
    _exec(world, "UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :i", i=G_NPC)
    set_rep(world, 900, region_id=20)
    give(world, ALPHA, WOOD, 5)
    assert post(client, quantity=1).status_code == 403
