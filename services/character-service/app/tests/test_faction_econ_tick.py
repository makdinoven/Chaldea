"""FEAT-206 QA: the faction step of the 6 h economy tick. features/FEAT-206 §3.6.

``econ_tick._faction_econ_pass`` on the faction world (region 10 «Ост» simulated, HQ = location 100): one
``faction_tick`` op per faction per run with every leg (dues, profile, wages, restock paying the residents' purse, debt
payouts), resume via ``last_run_id`` / ``DuplicateOperation`` never double-posts, a failing faction is rolled back
alone, regional purse / treasury caps split between the factions of a region, the not-ticking cases are skipped
(no HQ, hidden, no template, disabled, HQ outside the simulation), members dynamics, history / ``last_*`` and the purge.
One integration test runs the real ``run_tick`` on the econ tick harness (faction pass between the mint and the banks,
error prefix in the run row).
"""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import econ_core as core
import econ_ledger
import econ_tick
import faction_econ_crud as fec
import faction_notify
import models
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GROUP_ARMS, ITEM_SCROLL, ITEM_SHIELD, ITEM_SWORD, R_OST, R_PASHNI, add_rank, as_user, balance,
    cash, debts, drain, econ_faction, econ_row, econ_world, exec_, fapi, fund, fw, join, make_faction, notice_texts, ops, q,
    qm_item, rep_world, rows, settings, simulate_region, treasury, world_sum,
)

PARAMS = SimpleNamespace(merchant_wholesale_share=0.5)
T = datetime(2026, 11, 6, 12, 0, 0)
PURSE, REGION = core.AccountRef.purse(R_OST), core.AccountRef.region(R_OST)


def run_pass(f, run_id=1, now=T):
    summary = econ_tick.RunSummary(run_id=run_id, trigger="manual", slot=None, status="running")
    econ_tick._faction_econ_pass(f, run_id, summary, PARAMS, now)
    return summary


def history(f, fid=None):
    keys = ("run_id", "faction_id", "balance_before", "balance_after", "dues", "profile", "wages_due", "wages_paid",
            "restock_spent", "restock_items", "debts_paid", "members_before", "members_after", "wealth")
    sql = f"SELECT {', '.join(keys)} FROM faction_econ_history"
    params = {}
    if fid is not None:
        sql += " WHERE faction_id = :fid"
        params["fid"] = fid
    return [dict(zip(keys, r)) for r in rows(f, sql + " ORDER BY id", **params)]


def stock(f, region_id=R_OST):
    return Decimal(str(q(f, "SELECT stock FROM econ_region_goods WHERE region_id = :r AND group_code = :g",
                         r=region_id, g=GROUP_ARMS)))


@pytest.fixture
def region(econ_world):
    simulate_region(econ_world)
    fund(econ_world, PURSE, 100_000)
    fund(econ_world, REGION, 50_000)
    return econ_world


def ticking(f, name="Орден Зари", *, template="order", members=100, money=10_000, hq=100, **kw):
    fid = make_faction(f, name, hq=hq)
    econ_faction(f, fid, template, members=members, **kw)
    if money:
        fund(f, core.AccountRef.faction(fid), money)
    return fid


# ============================================================================================ one step


class TestStep:

    def test_full_step_legs_numbers_and_invariant(self, region):
        fid = ticking(region)
        add_rank(region, fid, "Послушник", 1, reward_marks=30)
        join(region, ALPHA, fid)                                        # an open debt of 30 (not settled yet)
        qid = qm_item(region, fid, ITEM_SWORD, stock=0, target=5)
        summary = run_pass(region, run_id=1)
        assert (summary.factions_done, summary.factions_failed, summary.faction_ops_posted) == (1, 0, 1)
        (h,) = history(region, fid)
        assert h == {"run_id": 1, "faction_id": fid, "balance_before": 10_000, "balance_after": 9970, "dues": 100,
                     "profile": 250, "wages_due": 100, "wages_paid": 100, "restock_spent": 250, "restock_items": 5,
                     "debts_paid": 30, "members_before": 100, "members_after": 101, "wealth": 100}
        assert treasury(region, fid) == 9970
        assert balance(region, PURSE) == 100_000 - 100 + 100 + 250             # dues out, wages + restock back
        assert balance(region, REGION) == 50_000 - 250                        # «плата края за охрану»
        assert cash(region, ALPHA) == 30
        assert [(d["paid"], d["status"]) for d in debts(region, ALPHA)] == [(30, "paid")]
        assert int(q(region, "SELECT stock FROM faction_qm_items WHERE id = :i", i=qid)) == 5
        assert stock(region) == Decimal("995")
        (op,) = rows(region, "SELECT idempotency_key, region_id, metadata FROM econ_operations "
                             "WHERE op_type = 'faction_tick'")
        assert op[0] == f"faction_tick:1:f{fid}" and int(op[1]) == R_OST
        legs = rows(region, "SELECT fa.kind, ta.kind, p.amount FROM econ_postings p "
                            "JOIN econ_operations o ON o.id = p.operation_id "
                            "JOIN econ_accounts fa ON fa.id = p.from_account_id "
                            "JOIN econ_accounts ta ON ta.id = p.to_account_id WHERE o.op_type = 'faction_tick'")
        kinds = sorted((a, b, int(c)) for a, b, c in legs)
        assert kinds == sorted([("population_purse", "faction_treasury", 100), ("region_treasury", "faction_treasury",
                                                                                 250),
                                ("faction_treasury", "population_purse", 100),
                                ("faction_treasury", "population_purse", 250),
                                ("faction_treasury", "character", 30)])
        e = econ_row(region, fid)
        assert (e["members_count"], e["last_run_id"], e["last_dues"], e["last_profile"], e["last_wages_due"],
                e["last_wages_paid"], e["last_restock"], e["last_debts_paid"], e["last_members_delta"],
                e["last_wealth"]) == (101, 1, 100, 250, 100, 100, 250, 30, 1, 100)
        assert world_sum(region) == 0

    def test_resume_same_run_never_double_posts(self, region):
        fid = ticking(region)
        assert run_pass(region, run_id=1).factions_done == 1
        again = run_pass(region, run_id=1)
        assert (again.factions_done, again.faction_ops_posted, again.factions_failed) == (0, 0, 0)
        assert len(ops(region, core.OP_FACTION_TICK)) == 1 and len(history(region, fid)) == 1
        run_pass(region, run_id=2)
        assert [k for _t, k in ops(region, core.OP_FACTION_TICK)] == [f"faction_tick:1:f{fid}",
                                                                        f"faction_tick:2:f{fid}"]
        assert econ_row(region, fid)["last_run_id"] == 2 and world_sum(region) == 0

    def test_duplicate_operation_is_skipped_not_failed(self, region):
        fid = ticking(region)
        db = region()
        try:
            econ_ledger.post_operation(db, op_type=core.OP_FACTION_TICK,
                                       legs=[core.Leg(PURSE, core.AccountRef.faction(fid), 1)],
                                       source_service="test", idempotency_key=f"faction_tick:5:f{fid}",
                                       apply_tax=False)
            db.commit()
        finally:
            db.close()
        summary = run_pass(region, run_id=5)
        assert (summary.factions_done, summary.factions_failed) == (0, 0)
        assert history(region, fid) == [] and econ_row(region, fid)["last_run_id"] is None    # rolled back
        assert world_sum(region) == 0

    def test_failing_faction_is_rolled_back_alone(self, region, monkeypatch):
        f1 = ticking(region, "Первая")
        f2 = ticking(region, "Вторая")
        real = fec.faction_step

        def step(db, job, **kw):
            out = real(db, job, **kw)              # everything done in the session ... then the faction crashes
            if job.faction_id == f1:
                raise RuntimeError("boom")
            return out

        monkeypatch.setattr(fec, "faction_step", step)
        summary = run_pass(region, run_id=3)
        assert (summary.factions_done, summary.factions_failed, summary.faction_failed_ids) == (1, 1, [f1])
        assert history(region, f1) == [] and treasury(region, f1) == 10_000
        assert econ_row(region, f1)["members_count"] == 100 and econ_row(region, f1)["last_run_id"] is None
        assert len(history(region, f2)) == 1 and econ_row(region, f2)["last_run_id"] == 3
        monkeypatch.setattr(fec, "faction_step", real)
        assert run_pass(region, run_id=4).factions_done == 2                 # retried next tick
        assert world_sum(region) == 0

    def test_tick_debt_notices(self, region):
        fid = ticking(region, money=0)
        add_rank(region, fid, "Послушник", 1, reward_marks=500)
        join(region, ALPHA, fid)                                        # debt 500, never settled / notified
        run_pass(region, run_id=1)                                      # inflow 350 - wages 100 -> pays 250
        (d,) = debts(region, ALPHA)
        assert (d["paid"], d["status"], d["unpaid_notified"]) == (250, "open", 1)
        assert [t for t in notice_texts(region) if "долг" in t] == [
            "Казна фракции «Орден Зари» сейчас пуста: 250 марок за звание записаны в долг. "
            "Выплатим, когда казна пополнится"]
        run_pass(region, run_id=2)
        run_pass(region, run_id=3)
        assert [d["status"] for d in debts(region, ALPHA)] == ["paid"] and cash(region, ALPHA) == 500
        texts = [t for t in notice_texts(region) if "долг" in t]
        assert len(texts) == 2 and texts[1] == "Фракция «Орден Зари» выплатила долг: 500 марок"
        assert world_sum(region) == 0

    def test_nothing_to_post_still_records_the_step(self, region):
        exec_(region, "INSERT INTO faction_econ_templates (code, name, params, sort_order, updated_at) "
                      "VALUES ('idle', 'Покой', :p, 9, :t)", p='{"norm_per_member": 30}', t=T)
        fid = ticking(region, template="idle", money=0)
        summary = run_pass(region, run_id=1)
        assert (summary.factions_done, summary.faction_ops_posted) == (1, 0)
        assert ops(region, core.OP_FACTION_TICK) == []
        (h,) = history(region, fid)
        assert (h["members_after"], h["wealth"]) == (100, 0) and econ_row(region, fid)["last_run_id"] == 1

    def test_empty_treasury_members_leave(self, region):
        settings(region, econ_purse_share_pct=0, econ_treasury_share_pct=0)
        fid = ticking(region, money=0)
        run_pass(region, run_id=1)
        (h,) = history(region, fid)
        assert (h["dues"], h["profile"], h["wages_due"], h["wages_paid"], h["members_after"]) == (0, 0, 100, 0, 95)
        assert econ_row(region, fid)["last_members_delta"] == -5
        assert treasury(region, fid) == 0 and world_sum(region) == 0

    def test_many_runs_never_negative_and_world_closes(self, region):
        f1 = ticking(region, "Первая", template="dark_guild", members=300, money=0)
        f2 = ticking(region, "Вторая", template="merchants_guild", members=200, money=500)
        exec_(region, "UPDATE econ_regions SET last_income = 20000 WHERE region_id = :r", r=R_OST)
        qm_item(region, f2, ITEM_SHIELD, stock=0, target=40)
        for run in range(1, 13):
            run_pass(region, run_id=run)
            negatives = rows(region, "SELECT kind, ref_id, balance FROM econ_accounts "
                                     "WHERE allow_negative = 0 AND balance < 0")
            assert negatives == [] and world_sum(region) == 0
        assert len(history(region, f1)) == 12 and len(history(region, f2)) == 12
        for fid in (f1, f2):
            assert 10 <= econ_row(region, fid)["members_count"] <= 5000


# ============================================================================================ caps


class TestRegionalCaps:

    def test_purse_cap_split_between_factions_of_a_region(self, region):
        # purse 100 000 x 2 % = 2000 for ALL factions; each wants 2000 dues -> 1000 each
        f1 = ticking(region, "Первая", members=2000, money=0)
        f2 = ticking(region, "Вторая", members=2000, money=0)
        jobs = {j.faction_id: j for j in fec.plan_pass(region())}
        assert jobs[f1].budgets.purse == jobs[f2].budgets.purse == 1000
        run_pass(region, run_id=1)
        assert [h["dues"] for h in history(region)] == [1000, 1000]

    def test_treasury_cap_split(self, region):
        over = {"profile_rate": "0.02"}                                # wants 1000 each, cap 50 000 x 1 % = 500
        f1 = ticking(region, "Первая", overrides=over, money=0)
        f2 = ticking(region, "Вторая", overrides=over, money=0)
        run_pass(region, run_id=1)
        assert {h["faction_id"]: h["profile"] for h in history(region)} == {f1: 250, f2: 250}
        assert balance(region, REGION) == 50_000 - 500

    def test_empty_region_treasury_gives_nothing(self, region):
        drain(region, REGION, 50_000)
        fid = ticking(region, money=0)
        run_pass(region, run_id=1)
        assert history(region, fid)[0]["profile"] == 0 and balance(region, REGION) == 0
        assert world_sum(region) == 0

    def test_settings_switch_purse_share(self, region):
        settings(region, econ_purse_share_pct=20)
        fid = ticking(region, members=5000, money=0, members_max=100_000)
        run_pass(region, run_id=1)
        assert history(region, fid)[0]["dues"] == 5000                  # 20 % of 100 000 = 20 000 >= wants


# ============================================================================================ restock


class TestRestock:

    def test_only_active_on_market_rows_of_the_hq_market(self, region):
        fid = ticking(region)
        sword = qm_item(region, fid, ITEM_SWORD, stock=0, target=3)
        scroll = qm_item(region, fid, ITEM_SCROLL, stock=0, target=3)          # off-market (direct insert)
        shield = qm_item(region, fid, ITEM_SHIELD, stock=0, target=3, active=False)
        run_pass(region, run_id=1)
        got = dict(rows(region, "SELECT id, stock FROM faction_qm_items"))
        assert (got[sword], got[scroll], got[shield]) == (3, 0, 0)
        # money of the restock went to the residents' purse, goods out of the region stock
        assert history(region, fid)[0]["restock_spent"] == 150 and stock(region) == Decimal("997")

    def test_group_missing_in_the_hq_region(self, region):
        fid = ticking(region)
        exec_(region, "DELETE FROM econ_region_goods")
        qid = qm_item(region, fid, ITEM_SWORD, stock=0, target=3)
        run_pass(region, run_id=1)
        assert int(q(region, "SELECT stock FROM faction_qm_items WHERE id = :i", i=qid)) == 0
        assert history(region, fid)[0]["restock_spent"] == 0

    def test_take_share_setting(self, region):
        settings(region, qm_take_share_pct=0)
        fid = ticking(region)
        qm_item(region, fid, ITEM_SWORD, stock=0, target=3)
        run_pass(region, run_id=1)
        assert history(region, fid)[0]["restock_items"] == 0

    def test_region_stock_never_negative(self, region):
        exec_(region, "UPDATE econ_region_goods SET stock = 30")
        fid = ticking(region, money=100_000)
        qm_item(region, fid, ITEM_SWORD, stock=0, target=1000)
        for run in range(1, 30):
            run_pass(region, run_id=run)
        assert stock(region) >= 0 and world_sum(region) == 0


# ============================================================================================ not ticking


class TestNotTicking:

    def test_skip_cases_and_admin_reasons(self, region, fapi):
        good = ticking(region, "Тикает")
        no_hq = ticking(region, "Без штаба", hq=None)
        hidden = ticking(region, "Скрытая")
        exec_(region, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=hidden)
        no_tpl = ticking(region, "Без шаблона", template=None)
        disabled = ticking(region, "Выключена", enabled=False)
        unsimulated = ticking(region, "Пашни", hq=110)                      # region 11 has no econ_regions row
        nowhere = ticking(region, "Пустошь", hq=300)                         # location without a region
        assert [j.faction_id for j in fec.plan_pass(region())] == [good]
        run_pass(region, run_id=1)
        assert {h["faction_id"] for h in history(region)} == {good}
        for fid in (no_hq, hidden, no_tpl, disabled, unsimulated, nowhere):
            assert treasury(region, fid) == 10_000 and econ_row(region, fid)["members_count"] == 100
        as_user(1, "admin", ["factions:read"])
        reasons = {fid: fapi.get(f"/characters/admin/factions/{fid}/economy").json()["not_ticking_reason"]
                   for fid in (good, no_hq, hidden, no_tpl, disabled, unsimulated, nowhere)}
        assert reasons == {good: None, no_hq: "Не задан штаб", hidden: "Фракция скрыта",
                           no_tpl: "Не выбран шаблон", disabled: "Экономика этой фракции выключена",
                           unsimulated: "Край штаба не участвует в экономике",
                           nowhere: "Штаб не относится ни к одному краю"}
        hq = fapi.get(f"/characters/admin/factions/{good}/economy").json()["hq"]
        assert hq == {"location_id": 100, "location_name": "Рынок", "region_id": R_OST, "region_name": "Ост",
                      "simulated": True}
        assert world_sum(region) == 0

    def test_global_switch_off(self, region):
        fid = ticking(region)
        settings(region, econ_enabled=False)
        assert fec.plan_pass(region()) == []
        assert run_pass(region).factions_done == 0 and history(region, fid) == []

    def test_region_with_no_population(self, region):
        fid = ticking(region)
        exec_(region, "UPDATE econ_regions SET population = 0")
        assert run_pass(region).factions_done == 0 and history(region, fid) == []

    def test_hidden_between_plan_and_step(self, region, monkeypatch):
        fid = ticking(region)
        real = fec.plan_pass

        def plan_then_hide(db):
            jobs = real(db)
            exec_(region, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=fid)
            return jobs

        monkeypatch.setattr(fec, "plan_pass", plan_then_hide)
        summary = run_pass(region)
        assert summary.factions_done == 0 and history(region, fid) == []


# ============================================================================================ history purge


def test_purge_old_deletes_old_faction_history(region):
    fid = ticking(region)
    run_pass(region, run_id=1, now=T - timedelta(days=400))
    run_pass(region, run_id=2, now=T)
    db = region()
    try:
        econ_tick.purge_old(db, SimpleNamespace(history_retention_days=30), T)
        db.commit()
    finally:
        db.close()
    assert [h["run_id"] for h in history(region, fid)] == [2]


# ============================================================================================ run_tick integration

from tests.test_econ_tick import T0, _add_region, _assert_ledger_closes, factory  # noqa: E402,F401


def _tick_world(f):
    import tests.faction_world as w
    _add_region(f, 1)
    db = f()
    try:
        db.execute(text("INSERT INTO Locations (id, name, region_id) VALUES (900, 'Штаб', 1)"))
        db.commit()
    finally:
        db.close()
    w.seed_templates(f)
    fid = make_faction(f, "Орден Зари", hq=900)
    econ_faction(f, fid, "order", members=100)
    return fid


def test_run_tick_runs_the_faction_pass(factory, monkeypatch):
    monkeypatch.setattr(faction_notify, "_send", lambda payloads: None)
    fid = _tick_world(factory)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.status == "done"
    assert (summary.factions_done, summary.faction_ops_posted, summary.factions_failed) == (1, 1, 0)
    rows_ = [tuple(r) for r in factory().execute(text(
        "SELECT run_id, dues FROM faction_econ_history WHERE faction_id = :f"), {"f": fid}).fetchall()]
    assert rows_ == [(summary.run_id, 100)]
    _assert_ledger_closes(factory)


def test_run_tick_reports_a_failing_faction(factory, monkeypatch):
    monkeypatch.setattr(faction_notify, "_send", lambda payloads: None)
    fid = _tick_world(factory)

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(fec, "faction_step", boom)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.factions_failed == 1 and summary.faction_failed_ids == [fid]
    error = factory().execute(text("SELECT error FROM econ_tick_runs WHERE id = :i"), {"i": summary.run_id}).scalar()
    assert error and econ_tick.FACTION_ERROR_PREFIX + str(fid) in error
    _assert_ledger_closes(factory)
