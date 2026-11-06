"""FEAT-207 QA (task #10): item donations and the tick sale of the faction item stock — features/FEAT-207 §3.3, §3.8.

Donations: the options list (plain stacks only, quest / off-market / enhanced / damaged excluded, not-ticking reason),
owner / member checks, per-item 400 reasons, all-or-nothing over several lines, 409 not ticking / duplicate request,
422 validation (incl. injection-shaped request ids), the daily cap SHARED with the marks donation (both orders), the
hostile penalty, no ledger operation and the world invariant. Tick: the sale stays within ``econ_item_sale_share_pct``
of the HQ purse, stock -n / region goods +units / history / ``last_item_sales`` / op metadata, a resumed run never
sells twice, share 0 and unsellable rows sell nothing, the admin economy view; pure planner regressions.

The single happy path (donate 4 swords + one tick) is in ``test_faction_stage3_sanity.py``.
"""

import subprocess
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import econ_core as core
import econ_tick
import faction_core as fc
import faction_econ as fe
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GROUP_ARMS, ITEM_DONATION_DDL, ITEM_SCROLL, ITEM_SHIELD, ITEM_SWORD, R_OST, USER_ALPHA, add_rank,
    as_admin, as_user, bag, econ_faction, econ_world, exec_, fapi, fund, fw, give_item, hostile, item_stock, join,
    load_migration_046, log_types, make_faction, member, ops, q, rep_world, rows, settings, simulate_region,
    treasury, world_sum,
)

PURSE = core.AccountRef.purse(R_OST)
PARAMS = SimpleNamespace(merchant_wholesale_share=0.5)
SWORD_VALUE, SHIELD_VALUE = 50, 25                   # wholesale = price x mult 1 x share 0.5


@pytest.fixture
def donor(econ_world):
    """Region 10 simulated (purse 100 000), «Орден» ticking with HQ @100, Альфа a member, logged in as his user."""
    f = econ_world
    for ddl in ITEM_DONATION_DDL:
        exec_(f, ddl)
    simulate_region(f)
    fund(f, PURSE, 100_000)
    fid = make_faction(f, "Орден", hq=100)
    econ_faction(f, fid, "order", members=100)
    add_rank(f, fid, "Послушник", 1)
    join(f, ALPHA, fid)
    as_user(USER_ALPHA)
    f.fid = fid
    return f


def url(fid, cid=ALPHA):
    return f"/characters/{cid}/factions/{fid}/donate-items"


def donate(fapi, fid, items, request_id="req-00000001", cid=ALPHA):
    return fapi.post(url(fid, cid), json={"items": [{"item_id": i, "quantity": n} for i, n in items],
                                          "request_id": request_id})


def quest_item(f, item_id):
    exec_(f, "INSERT INTO quest_objectives (objective_type, target_id) VALUES ('collect', :i)", i=item_id)


# ============================================================================================ options


def test_options_list_only_eligible_plain_stacks(fapi, donor):
    fid = donor.fid
    give_item(donor, ALPHA, ITEM_SWORD, 5)
    give_item(donor, ALPHA, ITEM_SWORD, 1, enhancement_points_spent=3)          # enhanced: not plain
    give_item(donor, ALPHA, ITEM_SHIELD, 3)
    give_item(donor, ALPHA, ITEM_SHIELD, 1, current_durability=10)              # damaged / durable: not plain
    give_item(donor, ALPHA, ITEM_SHIELD, 1, socketed_gems="[1]")
    give_item(donor, ALPHA, ITEM_SCROLL, 2)                                      # off-market
    give_item(donor, BETA, ITEM_SWORD, 9)                                        # someone else's bag
    out = fapi.get(url(fid)).json()
    assert out["enabled"] is True and out["reason"] is None
    assert (out["marks_per_point"], out["daily_cap"], out["points_today"]) == (10, 50, 0)
    assert [(i["item_id"], i["name"], i["quantity"], i["unit_value"]) for i in out["items"]] == [
        (ITEM_SWORD, "Меч Зари", 5, SWORD_VALUE), (ITEM_SHIELD, "Щит Зари", 3, SHIELD_VALUE)]
    quest_item(donor, ITEM_SHIELD)
    assert [i["item_id"] for i in fapi.get(url(fid)).json()["items"]] == [ITEM_SWORD]


def test_options_access_and_not_ticking(fapi, donor):
    fid = donor.fid
    give_item(donor, ALPHA, ITEM_SWORD, 5)
    assert fapi.get(url(fid, BETA)).status_code == 403                            # not his character
    assert fapi.get(url(99999)).status_code == 404
    other = make_faction(donor, "Гильдия", hq=100)
    assert fapi.get(url(other)).json()["detail"] == "Вы не состоите в этой фракции"
    exec_(donor, "UPDATE faction_economy SET econ_enabled = 0 WHERE faction_id = :fid", fid=fid)
    out = fapi.get(url(fid)).json()
    assert (out["enabled"], out["reason"], out["items"]) == (False, "Экономика этой фракции выключена", [])
    m = fapi.get(f"/characters/{ALPHA}/factions").json()["memberships"][0]
    assert (m["donation"]["items_enabled"], m["donation"]["items_disabled_reason"]) == (
        False, "Экономика этой фракции выключена")


# ============================================================================================ donate: refusals


def test_per_item_reasons_and_nothing_taken(fapi, donor):
    fid = donor.fid
    give_item(donor, ALPHA, ITEM_SWORD, 1, enhancement_points_spent=3)
    give_item(donor, ALPHA, ITEM_SHIELD, 3)
    give_item(donor, ALPHA, ITEM_SCROLL, 2)
    quest_item(donor, ITEM_SHIELD)
    cases = [
        ([(ITEM_SHIELD, 1)], 400, "Предмет «Щит Зари» нельзя пожертвовать: квестовый предмет"),
        ([(ITEM_SCROLL, 1)], 400, "Предмет «Свиток Зари» нельзя пожертвовать: не продаётся на рынке края штаба"),
        ([(ITEM_SWORD, 1)], 400, "Недостаточно предметов «Меч Зари»"),               # only an enhanced one
        ([(4242, 1)], 400, "Предмет «#4242» нельзя пожертвовать: предмет не найден"),
    ]
    for n, (items, status, detail) in enumerate(cases):
        r = donate(fapi, fid, items, f"req-reason-{n}")
        assert (r.status_code, r.json()["detail"]) == (status, detail)
    assert (bag(donor, ALPHA, ITEM_SWORD), bag(donor, ALPHA, ITEM_SHIELD), bag(donor, ALPHA, ITEM_SCROLL)) == (1, 3, 2)
    assert item_stock(donor, fid, ITEM_SWORD) == 0 and log_types(donor, ALPHA, fid).count(fc.EV_DONATION) == 0


def test_several_lines_are_all_or_nothing(fapi, donor):
    fid = donor.fid
    give_item(donor, ALPHA, ITEM_SWORD, 5)
    give_item(donor, ALPHA, ITEM_SHIELD, 3)
    r = donate(fapi, fid, [(ITEM_SWORD, 2), (ITEM_SHIELD, 9)])
    assert (r.status_code, r.json()["detail"]) == (400, "Недостаточно предметов «Щит Зари»")
    assert (bag(donor, ALPHA, ITEM_SWORD), item_stock(donor, fid, ITEM_SWORD), member(donor, ALPHA, fid)["points"]) \
        == (5, 0, 0)
    r = donate(fapi, fid, [(ITEM_SHIELD, 3), (ITEM_SWORD, 2)], "req-00000002")
    assert r.json() == {"points_delta": 17, "points_after": 17, "points_today": 17, "daily_cap": 50,
                        "value_total": 175, "items_given": 5, "rank_ups": 0}
    assert (bag(donor, ALPHA, ITEM_SWORD), bag(donor, ALPHA, ITEM_SHIELD)) == (3, 0)
    assert (item_stock(donor, fid, ITEM_SWORD), item_stock(donor, fid, ITEM_SHIELD)) == (2, 3)


@pytest.mark.parametrize("field, reason", [
    ("econ", "Экономика этой фракции выключена"), ("hidden", "Фракция скрыта"),
    ("settings", "Экономика фракций выключена в настройках"), ("region", "Край штаба не участвует в экономике"),
])
def test_not_ticking_faction_refuses_items(fapi, donor, field, reason):
    fid = donor.fid
    give_item(donor, ALPHA, ITEM_SWORD, 5)
    if field == "econ":
        exec_(donor, "UPDATE faction_economy SET econ_enabled = 0")
    elif field == "hidden":
        exec_(donor, "UPDATE factions SET is_active = 0")
    elif field == "settings":
        settings(donor, econ_enabled=False)
    else:
        exec_(donor, "DELETE FROM econ_regions")
    r = donate(fapi, fid, [(ITEM_SWORD, 1)])
    assert (r.status_code, r.json()["detail"]) == (409, f"Фракция сейчас не принимает предметы: {reason}")
    assert bag(donor, ALPHA, ITEM_SWORD) == 5


@pytest.mark.parametrize("body", [
    {"items": [{"item_id": ITEM_SWORD, "quantity": 1}] * 2, "request_id": "req-00000001"},
    {"items": [{"item_id": ITEM_SWORD, "quantity": 0}], "request_id": "req-00000001"},
    {"items": [{"item_id": ITEM_SWORD, "quantity": 10000}], "request_id": "req-00000001"},
    {"items": [{"item_id": ITEM_SWORD, "quantity": "1"}], "request_id": "req-00000001"},
    {"items": [{"item_id": ITEM_SWORD, "quantity": 1.5}], "request_id": "req-00000001"},
    {"items": [{"item_id": 0, "quantity": 1}], "request_id": "req-00000001"},
    {"items": [], "request_id": "req-00000001"},
    {"items": [{"item_id": i, "quantity": 1} for i in range(1, 22)], "request_id": "req-00000001"},
    {"items": [{"item_id": ITEM_SWORD, "quantity": 1}], "request_id": "short"},
    {"items": [{"item_id": ITEM_SWORD, "quantity": 1}], "request_id": "x' OR '1'='1"},
    {"items": [{"item_id": ITEM_SWORD, "quantity": 1}], "request_id": "<script>alert(1)</script>"},
    {"items": [{"item_id": ITEM_SWORD, "quantity": 1}]},
])
def test_validation(fapi, donor, body):
    give_item(donor, ALPHA, ITEM_SWORD, 5)
    assert fapi.post(url(donor.fid), json=body).status_code == 422
    assert bag(donor, ALPHA, ITEM_SWORD) == 5


def test_same_request_id_is_409_even_with_another_body(fapi, donor):
    fid = donor.fid
    give_item(donor, ALPHA, ITEM_SWORD, 5)
    assert donate(fapi, fid, [(ITEM_SWORD, 1)], "req-same-0001").status_code == 200
    r = donate(fapi, fid, [(ITEM_SWORD, 3)], "req-same-0001")
    assert (r.status_code, r.json()["detail"]) == (409, "Это пожертвование уже выполнено")
    assert bag(donor, ALPHA, ITEM_SWORD) == 4 and item_stock(donor, fid, ITEM_SWORD) == 1


# ============================================================================================ points / money


def test_daily_cap_is_shared_with_the_marks_donation(fapi, donor):
    fid = donor.fid
    give_item(donor, ALPHA, ITEM_SWORD, 10)
    fund(donor, core.AccountRef.character(ALPHA), 1000)
    r = fapi.post(f"/characters/{ALPHA}/factions/{fid}/donate", json={"amount": 450, "request_id": "marks-0001"})
    assert r.status_code == 200, r.text
    assert member(donor, ALPHA, fid)["points"] == 45
    out = donate(fapi, fid, [(ITEM_SWORD, 4)]).json()                         # 200 marks worth -> only 5 left
    assert (out["points_delta"], out["points_today"], out["value_total"]) == (5, 50, 200)
    out = donate(fapi, fid, [(ITEM_SWORD, 2)], "req-00000002").json()         # cap reached: items still taken
    assert out["points_delta"] == 0 and bag(donor, ALPHA, ITEM_SWORD) == 4
    assert log_types(donor, ALPHA, fid).count(fc.EV_DONATION) == 3
    fapi.post(f"/characters/{ALPHA}/factions/{fid}/donate", json={"amount": 100, "request_id": "marks-0002"})
    assert member(donor, ALPHA, fid)["points"] == 50
    assert q(donor, "SELECT marks FROM faction_donation_days WHERE character_id = :c", c=ALPHA) == 450 + 200 + 100 + 100
    assert world_sum(donor) == 0


def test_item_donation_moves_no_money_and_applies_the_hostile_penalty(fapi, donor):
    fid = donor.fid
    rival = make_faction(donor, "Тень")
    add_rank(donor, rival, "Тень", 1)
    join(donor, ALPHA, rival)
    exec_(donor, "UPDATE faction_members SET points = 100 WHERE faction_id = :fid", fid=rival)
    hostile(donor, fid, rival)
    give_item(donor, ALPHA, ITEM_SWORD, 5)
    ops_before, treasury_before = len(ops(donor)), treasury(donor, fid)
    out = donate(fapi, fid, [(ITEM_SWORD, 4)]).json()
    assert out["points_delta"] == 20 and member(donor, ALPHA, rival)["points"] == 90       # -50 % of 20
    assert fc.EV_HOSTILE in log_types(donor, ALPHA, rival)
    assert len(ops(donor)) == ops_before and treasury(donor, fid) == treasury_before
    assert world_sum(donor) == 0
    assert rows(donor, "SELECT reason FROM faction_log WHERE event_type = :t AND faction_id = :fid",
                t=fc.EV_DONATION, fid=fid) == [("items:4:200",)]


# ============================================================================================ tick sale


def run_pass(f, run_id=1):
    summary = econ_tick.RunSummary(run_id=run_id, trigger="manual", slot=None, status="running")
    econ_tick._faction_econ_pass(f, run_id, summary, PARAMS, datetime.utcnow())
    assert summary.factions_failed == 0
    return summary


def stock_on_market(f):
    return Decimal(str(q(f, "SELECT stock FROM econ_region_goods WHERE region_id = :r AND group_code = :g",
                         r=R_OST, g=GROUP_ARMS)))


@pytest.fixture
def stocked(donor):
    exec_(donor, "INSERT INTO faction_item_stock (faction_id, item_id, quantity, updated_at) VALUES (:fid, :i, 100, :n)",
          fid=donor.fid, i=ITEM_SWORD, n=datetime.utcnow())
    return donor


def test_tick_sale_within_the_purse_share_and_resume(stocked):
    f, fid = stocked, stocked.fid
    market_before = stock_on_market(f)
    run_pass(f, 1)
    # budget = 2 % of the 100 000 purse = 2000 -> 40 swords at 50
    assert item_stock(f, fid, ITEM_SWORD) == 60
    assert q(f, "SELECT last_item_sales FROM faction_economy WHERE faction_id = :fid", fid=fid) == 2000
    assert rows(f, "SELECT item_sales, items_sold FROM faction_econ_history WHERE faction_id = :fid",
                fid=fid) == [(2000, 40)]
    assert stock_on_market(f) - market_before == 40                                     # 1 unit per sword
    meta = q(f, "SELECT metadata FROM econ_operations WHERE op_type = :t", t=core.OP_FACTION_TICK)
    assert '"item_sales"' in str(meta) and f'"{ITEM_SWORD}": 40' in str(meta).replace("'", '"')
    assert world_sum(f) == 0
    run_pass(f, 1)                                                                     # resumed run
    assert item_stock(f, fid, ITEM_SWORD) == 60 and len(ops(f, core.OP_FACTION_TICK)) == 1
    run_pass(f, 2)
    assert 0 < 60 - item_stock(f, fid, ITEM_SWORD) <= 40 and world_sum(f) == 0


def test_tick_share_zero_and_unsellable_rows_sell_nothing(stocked):
    f, fid = stocked, stocked.fid
    settings(f, econ_item_sale_share_pct=0)
    run_pass(f, 1)
    assert item_stock(f, fid, ITEM_SWORD) == 100
    assert q(f, "SELECT last_item_sales FROM faction_economy WHERE faction_id = :fid", fid=fid) == 0
    settings(f, econ_item_sale_share_pct=2)
    quest_item(f, ITEM_SWORD)                                                          # became a quest item
    run_pass(f, 2)
    assert item_stock(f, fid, ITEM_SWORD) == 100 and world_sum(f) == 0


def test_tick_purse_share_split_between_factions_of_a_region(stocked):
    f, fid = stocked, stocked.fid
    other = make_faction(f, "Гильдия", hq=100)
    econ_faction(f, other, "order", members=100)
    exec_(f, "INSERT INTO faction_item_stock (faction_id, item_id, quantity, updated_at) VALUES (:fid, :i, 100, :n)",
          fid=other, i=ITEM_SWORD, n=datetime.utcnow())
    run_pass(f, 1)
    sold = 200 - item_stock(f, fid, ITEM_SWORD) - item_stock(f, other, ITEM_SWORD)
    assert sold * SWORD_VALUE <= 2000 and sold == 40                                  # 1000 each
    assert item_stock(f, fid, ITEM_SWORD) == item_stock(f, other, ITEM_SWORD) == 80
    assert world_sum(f) == 0


def test_admin_economy_view_shows_the_stock_and_last_sales(fapi, stocked):
    f, fid = stocked, stocked.fid
    run_pass(f, 1)
    as_admin()
    out = fapi.get(f"/characters/admin/factions/{fid}/economy").json()
    assert out["item_stock"] == [{"item_id": ITEM_SWORD, "name": "Меч Зари", "quantity": 60,
                                  "unit_value": SWORD_VALUE}]
    assert out["last"]["item_sales"] == 2000
    history = fapi.get(f"/characters/admin/factions/{fid}/economy/history").json()
    items = history if isinstance(history, list) else history.get("items", [])
    assert items[0]["item_sales"] == 2000 and items[0]["items_sold"] == 40


# ============================================================================================ pure planner


ORDER = fe.effective_params(next(p for code, _n, _d, p, _o in load_migration_046().TEMPLATES if code == "order"), None)
MARKET = {GROUP_ARMS: fe.MarketGroupIn(stock=1000.0, price_mult=Decimal(1), group_base=100)}


def plan(sales=0, rows_=(), purse=10 ** 6, balance=5000):
    return fe.plan_faction_step(fe.FactionStateIn(7, 10, 100, Decimal(0), 10, 5000), ORDER, fe.DEFAULT_ECON_SETTINGS,
                                fe.Budgets(10 ** 6, 10 ** 6, sales), purse=purse, region_treasury=10 ** 6,
                                last_income=1000, balance=balance, market=MARKET, sale_rows=list(rows_))


def test_planner_without_stock_is_the_stage_2_result():
    base = plan()
    assert plan(sales=10 ** 6) == base and plan(rows_=[]) == base
    assert base.item_sales == 0 and base.sale == {} and base.items_sold == 0


def test_planner_sale_caps_and_one_purse_leg():
    rows_ = [fe.SaleRowIn(ITEM_SWORD, GROUP_ARMS, 100, 100), fe.SaleRowIn(ITEM_SHIELD, GROUP_ARMS, 10, 50),
             fe.SaleRowIn(999, "unknown", 10, 100)]
    p = plan(sales=1000, rows_=rows_)
    assert p.sale == {ITEM_SWORD: 20} and p.item_sales == 1000 and p.items_sold == 20       # budget eaten by swords
    assert p.stock_delta[GROUP_ARMS] == pytest.approx(20.0)
    p = plan(sales=1080, rows_=rows_)
    assert p.sale == {ITEM_SWORD: 21, ITEM_SHIELD: 1} and p.item_sales == 1075        # 30 left: one shield at 25
    assert p.stock_delta[GROUP_ARMS] == pytest.approx(21.5)                           # a shield = 0.5 unit
    base = plan()
    poor = plan(sales=10 ** 6, rows_=rows_[:1], purse=base.dues + base.profile_purse + 120)
    assert poor.sale == {ITEM_SWORD: 2}                                                # purse left 120 -> 2
    sale_legs = [leg for leg in plan(sales=1000, rows_=rows_).legs
                 if leg.src == PURSE and leg.dst == core.AccountRef.faction(7) and leg.amount == 1000]
    assert len(sale_legs) == 1                                                         # its own purse -> faction leg


def test_econ_core_copies_unchanged():
    root = Path(__file__).resolve()
    script = next((p / "scripts" / "check_econ_copies.sh" for p in root.parents
                   if (p / "scripts" / "check_econ_copies.sh").exists()), None)
    if script is None:
        pytest.skip("repo scripts/ not mounted in this container (checked on the host)")
    out = subprocess.run(["sh", str(script)], cwd=script.parent.parent, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stdout + out.stderr
