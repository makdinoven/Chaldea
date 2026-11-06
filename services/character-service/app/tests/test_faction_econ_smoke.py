"""FEAT-206 backend smoke checks (developer-written; the full QA suite is task #9).

Covers one happy path per flow on the shared faction world, each ending with the world money invariant:
rank marks -> debt queue -> payout; donation (points, daily cap, idempotency); the 6 h faction step (dues / wages /
restock / debts, resume never double-posts); quartermaster probe / secrecy / buy + delivery; admin fill re-click.
"""

from datetime import datetime
from decimal import Decimal

import pytest

import econ_core as core
import econ_ledger
import faction_econ as fe
import faction_econ_crud as fec
import faction_qm_crud as fqm
import faction_rewards
import locations_client
import models
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, USER_ALPHA, add_rank, as_admin, as_user, exec_, fapi, fw, join, make_faction, q, rep_world, rows,
)

QM_NPC = 53            # «Безымянный» NPC @100 (region 10)
ITEM = 501             # «Меч Зари»
P = "/characters"


def world_sum(f) -> int:
    return int(q(f, "SELECT (SELECT COALESCE(SUM(currency_balance), 0) FROM characters) + "
                    "(SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character')"))


def fund(f, ref, amount):
    db = f()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, legs=[core.Leg(core.AccountRef.emission(), ref,
                                                                                      amount)],
                                   source_service="test", comment="seed", apply_tax=False)
        db.commit()
    finally:
        db.close()


def balance(f, ref):
    if ref.is_character:
        return int(q(f, "SELECT currency_balance FROM characters WHERE id = :c", c=ref.ref_id) or 0)
    return int(q(f, "SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r", k=ref.kind,
                 r=ref.ref_id) or 0)


def seed_template(f):
    exec_(f, "INSERT INTO faction_econ_templates (code, name, params, sort_order, updated_at) "
             "VALUES ('order', 'Орден', :p, 1, :now)",
          p='{"start_members": 300, "norm_per_member": 30, "start_treasury_per_member": 30, "dues_per_member": "1.0",'
            ' "wage_per_member": "1.0", "profile_kind": "treasury_share", "profile_rate": "0.005", '
            '"qm_budget_share": "0.10"}', now=datetime.utcnow())


def test_pure_plan_moves_money_only_between_accounts():
    params = fe.effective_params({"dues_per_member": "1", "wage_per_member": "2", "norm_per_member": 30}, None)
    plan = fe.plan_faction_step(fe.FactionStateIn(1, 10, 100), params, fe.DEFAULT_ECON_SETTINGS,
                                fe.Budgets(50, 0), purse=1000, region_treasury=0, last_income=0, balance=120,
                                open_debts=[fe.DebtIn(1, 5, 30)])
    # dues capped at the budget 50; wages due 200, paid 170; nothing left for the debt
    assert (plan.dues, plan.wages_due, plan.wages_paid, plan.debts) == (50, 200, 170, {})
    net = sum(leg.amount for leg in plan.legs if leg.dst.kind == core.KIND_FACTION_TREASURY) - \
        sum(leg.amount for leg in plan.legs if leg.src.kind == core.KIND_FACTION_TREASURY)
    assert plan.balance_after == 120 + net == 0
    assert plan.members_after == 100 and plan.carry_after == Decimal("-0.75")   # -100 x 5 % x 0.15


def test_rank_marks_debt_then_payout(fw):
    fid = make_faction(fw)
    add_rank(fw, fid, "Послушник", 1, reward_marks=100)
    join(fw, ALPHA, fid)
    faction_rewards.deliver_pending(ALPHA, fw)
    debt = rows(fw, "SELECT amount, paid, status, unpaid_notified FROM faction_debts WHERE character_id = :c", c=ALPHA)
    assert debt == [(100, 0, "open", 1)]                    # empty treasury: owed + notified once
    fund(fw, core.AccountRef.faction(fid), 60)
    assert fec.settle_after_commit([fid], fw) == 1
    assert rows(fw, "SELECT paid, status FROM faction_debts") == [(60, "open")]
    fund(fw, core.AccountRef.faction(fid), 100)
    fec.sweep_debts(fw, datetime.utcnow())
    assert rows(fw, "SELECT paid, status FROM faction_debts") == [(100, "paid")]
    assert balance(fw, core.AccountRef.character(ALPHA)) == 100
    assert balance(fw, core.AccountRef.faction(fid)) == 60
    assert world_sum(fw) == 0


def test_donation_points_cap_and_idempotency(fapi, fw):
    fid = make_faction(fw)
    add_rank(fw, fid, "Послушник", 1)
    join(fw, ALPHA, fid)
    fund(fw, core.AccountRef.character(ALPHA), 1000)
    as_user(USER_ALPHA)
    r = fapi.post(f"{P}/{ALPHA}/factions/{fid}/donate", json={"amount": 25, "request_id": "req-00001"})
    assert r.status_code == 200, r.text
    assert r.json()["points_delta"] == 2 and r.json()["marks_today"] == 25 and r.json()["new_balance"] == 975
    again = fapi.post(f"{P}/{ALPHA}/factions/{fid}/donate", json={"amount": 25, "request_id": "req-00001"})
    assert again.status_code == 409 and again.json()["detail"] == "Это пожертвование уже выполнено"
    r = fapi.post(f"{P}/{ALPHA}/factions/{fid}/donate", json={"amount": 900, "request_id": "req-00002"})
    assert r.json()["points_delta"] == 48 and r.json()["points_today"] == 50     # cap 50
    poor = fapi.post(f"{P}/{ALPHA}/factions/{fid}/donate", json={"amount": 500, "request_id": "req-00003"})
    assert poor.status_code == 400
    view = fapi.get(f"{P}/{ALPHA}/factions").json()["memberships"][0]
    assert view["donation"]["points_today"] == 50 and view["debt"] == 0 and view["wealth"] is None
    assert balance(fw, core.AccountRef.faction(fid)) == 925
    assert world_sum(fw) == 0


def _region_ready(f, region_id=10):
    exec_(f, "INSERT INTO econ_regions (region_id, template_code, population, last_income) VALUES (:r, 'x', 1000, 0)",
          r=region_id)
    exec_(f, "INSERT INTO econ_goods_groups (code, name, base_price, norm_per_1000, norm_days) "
             "VALUES ('arms', 'Оружие', 100, 1, 1)")
    exec_(f, "INSERT INTO econ_region_goods (region_id, group_code, stock, price_mult) VALUES (:r, 'arms', 1000, 1)",
          r=region_id)


def test_tick_step_posts_once_and_restocks(fw):
    for ddl in ("ALTER TABLE items ADD COLUMN resource_subcategory VARCHAR(30)",
                "ALTER TABLE items ADD COLUMN is_food INTEGER DEFAULT 0",
                "ALTER TABLE items ADD COLUMN item_rarity VARCHAR(20)",
                "ALTER TABLE items ADD COLUMN price INTEGER DEFAULT 0",
                "ALTER TABLE items ADD COLUMN image VARCHAR(255)"):
        exec_(fw, ddl)
    exec_(fw, "UPDATE items SET price = 100, item_rarity = 'common' WHERE id = :i", i=ITEM)
    seed_template(fw)
    _region_ready(fw)
    exec_(fw, "INSERT INTO econ_item_groups (item_id, group_code, off_market, updated_at) "
              "VALUES (:i, 'arms', 0, :now)", i=ITEM, now=datetime.utcnow())
    fid = make_faction(fw, hq=100)
    exec_(fw, "INSERT INTO faction_economy (faction_id, template_code, members_count, updated_at) "
              "VALUES (:fid, 'order', 100, :now)", fid=fid, now=datetime.utcnow())
    exec_(fw, "INSERT INTO faction_qm_items (faction_id, item_id, price, stock, restock_target, is_active, sort_order, "
              "updated_at) VALUES (:fid, :i, 80, 0, 5, 1, 0, :now)", fid=fid, i=ITEM, now=datetime.utcnow())
    fund(fw, core.AccountRef.purse(10), 100000)
    fund(fw, core.AccountRef.region(10), 50000)
    fund(fw, core.AccountRef.faction(fid), 10000)
    db = fw()
    try:
        jobs = fec.plan_pass(db)
    finally:
        db.close()
    assert [j.faction_id for j in jobs] == [fid] and jobs[0].budgets.purse == 100

    import econ_tick
    for attempt in range(2):
        db = fw()
        try:
            out = fec.faction_step(db, jobs[0], run_id=7, now=datetime.utcnow(), wholesale_share=0.5,
                                   load_item_markets=econ_tick.load_item_markets)
            db.commit()
        finally:
            db.close()
        assert out.status == ("done" if attempt == 0 else "already")
    assert int(q(fw, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'faction_tick'")) == 1
    assert int(q(fw, "SELECT stock FROM faction_qm_items")) == 5
    assert Decimal(str(q(fw, "SELECT stock FROM econ_region_goods"))) == Decimal("995")
    hist = rows(fw, "SELECT dues, profile, wages_paid, restock_spent, members_after FROM faction_econ_history")
    # 5 swords x wholesale 50; wealth 100 (balance 10000 vs norm 3000) -> +1 % members
    assert hist == [(100, 250, 100, 250, 101)]
    assert world_sum(fw) == 0


def test_quartermaster_secrecy_and_buy(fapi, fw, monkeypatch):
    for ddl in ("ALTER TABLE items ADD COLUMN resource_subcategory VARCHAR(30)",
                "ALTER TABLE items ADD COLUMN is_food INTEGER DEFAULT 0",
                "ALTER TABLE items ADD COLUMN item_rarity VARCHAR(20)",
                "ALTER TABLE items ADD COLUMN price INTEGER DEFAULT 0",
                "ALTER TABLE items ADD COLUMN image VARCHAR(255)"):
        exec_(fw, ddl)

    async def gate(*_args):
        return True

    monkeypatch.setattr(locations_client, "check_npc_gate", gate)
    secret = make_faction(fw, "Тень", secret=True)
    add_rank(fw, secret, "Тень I", 1)
    exec_(fw, "UPDATE characters SET npc_role = 'quartermaster' WHERE id = :n", n=QM_NPC)
    exec_(fw, "INSERT INTO faction_quartermasters (npc_id, faction_id, created_at) VALUES (:n, :fid, :now)",
          n=QM_NPC, fid=secret, now=datetime.utcnow())
    exec_(fw, "INSERT INTO faction_qm_items (faction_id, item_id, price, stock, restock_target, is_active, sort_order, "
              "updated_at) VALUES (:fid, :i, 50, 3, 0, 1, 0, :now)", fid=secret, i=ITEM, now=datetime.utcnow())
    as_user(USER_ALPHA)
    assert fapi.get(f"{P}/factions/quartermaster/npc/{QM_NPC}/probe?character_id={ALPHA}").json() == \
        {"state": "silent"}
    r = fapi.get(f"{P}/factions/quartermaster/npc/{QM_NPC}?character_id={ALPHA}")
    assert r.status_code == 403 and r.json()["detail"] == "Этот человек с вами не разговаривает"

    join(fw, ALPHA, secret)
    fund(fw, core.AccountRef.character(ALPHA), 200)
    view = fapi.get(f"{P}/factions/quartermaster/npc/{QM_NPC}?character_id={ALPHA}").json()
    assert view["member"] is True and view["items"][0]["locked_reason"] is None
    body = {"character_id": ALPHA, "qm_item_id": view["items"][0]["qm_item_id"], "quantity": 2,
            "request_id": "buy-00001"}
    r = fapi.post(f"{P}/factions/quartermaster/npc/{QM_NPC}/buy", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["delivered"] is True and r.json()["price_total"] == 100 and r.json()["new_balance"] == 100
    assert fapi.post(f"{P}/factions/quartermaster/npc/{QM_NPC}/buy", json=body).status_code == 409
    assert int(q(fw, "SELECT stock FROM faction_qm_items")) == 1
    assert rows(fw, "SELECT status FROM faction_qm_purchases") == [("done",)]
    assert balance(fw, core.AccountRef.faction(secret)) == 100
    assert world_sum(fw) == 0


def test_admin_fill_reclick_emits_zero(fapi, fw):
    seed_template(fw)
    fid = make_faction(fw)
    exec_(fw, "INSERT INTO faction_economy (faction_id, template_code, updated_at) VALUES (:fid, 'order', :now)",
          fid=fid, now=datetime.utcnow())
    as_user(1, "admin", ["factions:read", "factions:economy", "economy:emit"])
    first = fapi.post(f"{P}/admin/factions/{fid}/economy/fill", json={"comment": "старт", "set_members": True})
    assert first.status_code == 200, first.text
    assert first.json() == {"members_count": 300, "emitted": 9000, "balance": 9000}
    again = fapi.post(f"{P}/admin/factions/{fid}/economy/fill", json={"comment": "старт", "set_members": True})
    assert again.json()["emitted"] == 0
    as_user(2, "moderator", ["factions:read", "factions:economy"])
    assert fapi.post(f"{P}/admin/factions/{fid}/economy/fill",
                     json={"comment": "старт", "set_members": True}).status_code == 403
    econ = fapi.get(f"{P}/admin/factions/{fid}/economy").json()
    assert econ["wealth"] == 50 and econ["wealth_label"] == "Держится" and econ["ticking"] is False
    assert world_sum(fw) == 0
