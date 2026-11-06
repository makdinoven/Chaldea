"""FEAT-207 backend sanity tests (the developer's quick checks; QA tasks #9-#11 add the full suites).

Territory (move gate, internal check / labels, admin rule), rank passives, kill points (battle-result), membership
crime in an outlawed region, item donations + the tick sale (world invariant).
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

import econ_core as core
import econ_tick
import faction_core as fc
import faction_items
import law_core as lc
import law_crud
import models
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GUARD, INTERNAL, ITEM_SWORD, MERCHANT, R_OST, USER_ALPHA, add_rank, as_admin, as_user, econ_faction,
    econ_world, exec_, fapi, fund, fw, join, log_types, make_faction, member, notice_texts, q, rep_world, rows,
    simulate_region, treasury, world_sum,
)

I = "/characters/internal"
A = "/characters/admin/factions"


def rule(f, fid, target, kind="location", rank=None):
    exec_(f, "INSERT INTO faction_access_rules (kind, target_id, faction_id, min_rank_id, created_at, updated_at) "
             "VALUES (:k, :t, :fid, :r, :n, :n)", k=kind, t=target, fid=fid, r=rank, n=datetime.utcnow())


def move(fapi, cid, loc):
    return fapi.put(f"{I}/{cid}/update_location", json={"new_location_id": loc}, headers=INTERNAL)


# ============================================================================================ pure


def test_access_decision_table():
    pub = fc.AccessFaction(1, "Орден", False, True)
    sec = fc.AccessFaction(2, "Тень", True, True)
    rank = fc.AccessRank(5, "Рыцарь", 3)
    assert fc.access_decision(None, None, viewer_known=True).allowed is True
    assert fc.access_decision(fc.AccessFaction(1, "Орден", False, False), None, viewer_known=True).rule is False
    assert fc.access_decision(pub, None, viewer_known=False).label == "Закрыто: Орден"
    assert fc.access_decision(sec, None, viewer_known=False).label == "Закрыто"
    d = fc.access_decision(sec, None, viewer_known=True)
    assert (d.allowed, d.refusal) == (False, "Сюда вас не пускают") and "Тень" not in d.label
    d = fc.access_decision(pub, rank, viewer_known=True, is_member=True, member_rank_order=2)
    assert d.allowed is False and d.refusal == "Нужно звание «Рыцарь» во фракции «Орден»"
    assert fc.access_decision(pub, rank, viewer_known=True, is_member=True, member_rank_order=3).allowed is True


def test_passives_and_kill_gain():
    ladder = [fc.PassiveRank(1, 1, "A", "a", None, {"strength": 2}), fc.PassiveRank(2, 2, "B", None, None, {}),
              fc.PassiveRank(3, 3, "C", "c", None, {"strength": 1, "dodge": 5})]
    assert [p.id for p in fc.active_passives(ladder, 3)] == [1, 3]
    assert fc.sum_modifiers([p.modifiers for p in fc.active_passives(ladder, 3)]) == {"strength": 3, "dodge": 5}
    assert fc.kill_gain([30, 30], 50, 10) == (40, 50)
    with pytest.raises(fc.PassiveError):
        fc.validate_passive("x", None, {"health": 5})


# ============================================================================================ territory


def test_move_gate_member_rank_npc_and_hidden(fapi, fw):
    fid = make_faction(fw, "Орден")
    r1 = add_rank(fw, fid, "Послушник", 1)
    r2 = add_rank(fw, fid, "Рыцарь", 2, min_points=100)
    rule(fw, fid, 110)
    r = move(fapi, ALPHA, 110)
    assert r.status_code == 409 and r.json()["detail"] == "Вход только для членов фракции «Орден»"
    join(fw, ALPHA, fid)
    assert move(fapi, ALPHA, 110).status_code == 200
    move(fapi, ALPHA, 100)
    exec_(fw, "UPDATE faction_access_rules SET min_rank_id = :r", r=r2)
    assert move(fapi, ALPHA, 110).json()["detail"] == "Нужно звание «Рыцарь» во фракции «Орден»"
    assert move(fapi, MERCHANT, 110).status_code == 200                       # NPCs are never gated
    exec_(fw, "UPDATE factions SET is_active = 0")
    assert move(fapi, BETA, 110).status_code == 200                           # hidden faction = open
    assert r1


def test_secret_faction_never_named(fapi, fw):
    fid = make_faction(fw, "Тайный круг", secret=True)
    add_rank(fw, fid, "Посвящённый", 1)
    rule(fw, fid, 110)
    assert move(fapi, BETA, 110).json()["detail"] == "Сюда вас не пускают"
    rule(fw, fid, 77, kind="dungeon")
    out = fapi.post(f"{I}/factions/access/check", headers=INTERNAL,
                    json={"kind": "dungeon", "target_id": 77, "character_ids": [ALPHA, BETA]}).json()
    assert out["allowed"] is False and "Тайный" not in out["detail"] and out["failed_character_ids"] == [ALPHA, BETA]
    labels = fapi.post(f"{I}/factions/access/labels", headers=INTERNAL,
                       json={"kind": "location", "target_ids": [110, 100], "character_id": ALPHA,
                             "user_id": 999}).json()
    assert labels == {"items": [{"target_id": 110, "access_label": "Закрыто", "access_allowed": None}]}


def test_party_check_names_failing_members(fapi, fw):
    fid = make_faction(fw, "Орден")
    add_rank(fw, fid, "Послушник", 1)
    join(fw, ALPHA, fid)
    rule(fw, fid, 77, kind="dungeon")
    out = fapi.post(f"{I}/factions/access/check", headers=INTERNAL,
                    json={"kind": "dungeon", "target_id": 77, "character_ids": [ALPHA, BETA]}).json()
    assert out["detail"] == "Подземелье только для членов фракции «Орден» — не проходят: Бета"
    own = fapi.post(f"{I}/factions/access/labels", headers=INTERNAL,
                    json={"kind": "dungeon", "target_ids": [77], "character_id": ALPHA, "user_id": USER_ALPHA}).json()
    assert own["items"][0]["access_allowed"] is True


def test_admin_rule_and_rank_delete_guard(fapi, fw):
    as_admin()
    fid = make_faction(fw, "Орден")
    rid = add_rank(fw, fid, "Рыцарь", 1)
    r = fapi.put(f"{A}/access/location/110", json={"faction_id": fid, "min_rank_id": rid})
    assert r.status_code == 200 and r.json()["rule"]["min_rank_name"] == "Рыцарь"
    assert fapi.put(f"{A}/access/location/999999", json={"faction_id": fid}).status_code == 404
    assert fapi.get(f"{A}/{fid}/territory").json()[0]["target_name"] == "Нива"
    assert fapi.delete(f"{A}/ranks/{rid}").status_code == 409
    assert fapi.delete(f"{A}/access/location/110").json() == {"ok": True}
    assert fapi.get(f"{A}/access/location/110").json() == {"rule": None}


# ============================================================================================ passives / kills


def test_passive_modifiers_cumulative(fapi, fw):
    fid = make_faction(fw, "Орден")
    add_rank(fw, fid, "Послушник", 1, passive_name="Закалка", passive_modifiers={"strength": 2})
    add_rank(fw, fid, "Рыцарь", 2)
    join(fw, ALPHA, fid)
    assert fapi.get(f"{I}/factions/{ALPHA}/passive-modifiers", headers=INTERNAL).json() == {
        "modifiers": {"strength": 2}}
    assert fapi.get(f"{I}/factions/{BETA}/passive-modifiers", headers=INTERNAL).json() == {"modifiers": {}}


def test_kill_points_npc_enemy_idempotent_and_cap(fapi, fw):
    fid = make_faction(fw, "Орден")
    add_rank(fw, fid, "Послушник", 1)
    join(fw, ALPHA, fid)
    exec_(fw, "INSERT INTO faction_enemies (faction_id, kind, ref_id, points) VALUES (:fid, 'npc', :n, 30)",
          fid=fid, n=MERCHANT)
    body = {"battle_id": 900, "battle_type": "pve", "winner_team": 0,
            "participants": [{"character_id": ALPHA, "team": 0, "alive": False},
                             {"character_id": MERCHANT, "team": 1, "alive": False}]}
    out = fapi.post(f"{I}/factions/battle-result", headers=INTERNAL, json=body).json()
    assert out["applied"] == [{"character_id": ALPHA, "faction_id": fid, "points_delta": 30}]   # fallen winner counts
    again = fapi.post(f"{I}/factions/battle-result", headers=INTERNAL, json=body).json()
    assert again["duplicate"] is True and member(fw, ALPHA, fid)["points"] == 30
    body["battle_id"] = 901
    assert fapi.post(f"{I}/factions/battle-result", headers=INTERNAL, json=body).json()["applied"][0][
        "points_delta"] == 20                                                   # daily cap 50
    assert log_types(fw, ALPHA, fid).count(fc.EV_KILL) == 2


def test_pvp_training_and_secret_victims_do_not_count(fapi, fw):
    a = make_faction(fw, "Орден")
    b = make_faction(fw, "Тень", secret=True)
    for fid in (a, b):
        add_rank(fw, fid, "Ранг", 1)
    exec_(fw, "INSERT INTO faction_hostilities (faction_a_id, faction_b_id, irreconcilable, created_at) "
              "VALUES (:a, :b, 0, :n)", a=min(a, b), b=max(a, b), n=datetime.utcnow())
    join(fw, ALPHA, a)
    join(fw, BETA, b)
    exec_(fw, "INSERT INTO faction_enemies (faction_id, kind, ref_id, points) VALUES (:fid, 'hostile', 0, 10)", fid=a)
    body = {"battle_id": 910, "battle_type": "pvp_death", "winner_team": 0,
            "participants": [{"character_id": ALPHA, "team": 0}, {"character_id": BETA, "team": 1}]}
    assert fapi.post(f"{I}/factions/battle-result", headers=INTERNAL, json=body).json()["applied"] == []
    exec_(fw, "UPDATE factions SET is_secret = 0 WHERE id = :b", b=b)
    body["battle_type"] = "pvp_training"
    assert fapi.post(f"{I}/factions/battle-result", headers=INTERNAL, json=body).json()["applied"] == []
    body.update(battle_type="pvp_attack", battle_id=911)
    assert fapi.post(f"{I}/factions/battle-result", headers=INTERNAL, json=body).json()["applied"][0][
        "points_delta"] == 10
    body["battle_id"] = 912                                                     # same victim within 24 h
    assert fapi.post(f"{I}/factions/battle-result", headers=INTERNAL, json=body).json()["applied"] == []


# ============================================================================================ membership crime


def test_open_outlawed_member_is_stopped_once_per_cooldown(fw):
    fid = make_faction(fw, "Орден")
    add_rank(fw, fid, "Послушник", 1)
    join(fw, ALPHA, fid)
    exec_(fw, "INSERT INTO faction_outlaw_regions (faction_id, region_id, level_code) VALUES (:fid, :r, 'criminal')",
          fid=fid, r=R_OST)
    db = fw()
    try:
        ch = db.get(models.Character, ALPHA)
        result = law_crud.check_entry(db, ch, 100, lc.SOURCE_MOVE)
        db.commit()
        assert result.encounter is not None and result.encounter.level_code == "criminal"
        crimes = rows(fw, "SELECT crime_type, region_id FROM law_crimes WHERE character_id = :c", c=ALPHA)
        assert crimes == [("faction_membership", R_OST)]
        assert law_crud._outlaw_membership(db, ALPHA, R_OST, datetime.utcnow()) is None     # cooldown
    finally:
        db.close()


# ============================================================================================ item donations


INVENTORY_DDL = ("CREATE TABLE IF NOT EXISTS character_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "character_id INTEGER NOT NULL, item_id INTEGER NOT NULL, quantity INTEGER DEFAULT 1, "
                 "enhancement_points_spent INTEGER DEFAULT 0, socketed_gems TEXT NULL, current_durability INTEGER NULL)")
QUEST_DDL = ("CREATE TABLE IF NOT EXISTS quest_objectives (id INTEGER PRIMARY KEY, quest_id INTEGER NOT NULL DEFAULT 1, "
             "objective_type VARCHAR(32) NOT NULL, target_id INTEGER NULL)")


def test_item_donation_and_tick_sale(fapi, econ_world):
    f = econ_world
    exec_(f, INVENTORY_DDL)
    exec_(f, QUEST_DDL)
    simulate_region(f)
    fund(f, core.AccountRef.purse(R_OST), 100_000)
    fid = make_faction(f, "Орден", hq=100)
    econ_faction(f, fid, "order", members=100)
    add_rank(f, fid, "Послушник", 1)
    join(f, ALPHA, fid)
    exec_(f, "INSERT INTO character_inventory (character_id, item_id, quantity) VALUES (:c, :i, 5)",
          c=ALPHA, i=ITEM_SWORD)
    as_user(USER_ALPHA)
    opts = fapi.get(f"/characters/{ALPHA}/factions/{fid}/donate-items").json()
    assert opts["enabled"] is True and opts["items"][0]["unit_value"] == 50       # 100 x 1 x 0.5
    body = {"items": [{"item_id": ITEM_SWORD, "quantity": 4}], "request_id": "abcdefgh-1"}
    r = fapi.post(f"/characters/{ALPHA}/factions/{fid}/donate-items", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["value_total"] == 200 and r.json()["points_delta"] == 20
    assert fapi.post(f"/characters/{ALPHA}/factions/{fid}/donate-items", json=body).status_code == 409
    assert q(f, "SELECT quantity FROM character_inventory WHERE character_id = :c", c=ALPHA) == 1
    assert q(f, "SELECT quantity FROM faction_item_stock WHERE faction_id = :fid", fid=fid) == 4
    before = world_sum(f)
    summary = econ_tick.RunSummary(run_id=1, trigger="manual", slot=None, status="running")
    econ_tick._faction_econ_pass(f, 1, summary, SimpleNamespace(merchant_wholesale_share=0.5), datetime.utcnow())
    assert summary.factions_failed == 0
    sold = 4 - int(q(f, "SELECT quantity FROM faction_item_stock WHERE faction_id = :fid", fid=fid))
    assert sold > 0 and q(f, "SELECT last_item_sales FROM faction_economy WHERE faction_id = :fid", fid=fid) == sold * 50
    assert world_sum(f) == before == 0
    assert faction_items.stock_value is not None
