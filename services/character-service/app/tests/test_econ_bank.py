"""FEAT-184 B3: basic tests of the pure bank maths (``econ_bank``, contract 3.6).

No database. Q1 extends this file with the full matrix; here: rounding/carry, rates, reserve/lendable, cap, fee,
loan accrual across due_at and the debt cap, prorata, collection order, factor bounds, maturity convert vs merge,
disabled bank, and a 120-pass (30 days) loop over a capital-like bank with players and residents.
"""

import dataclasses
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

import econ_bank as eb
import econ_core as core
from econ_sim import DEFAULT_PARAMS, SimParams

T0 = datetime(2026, 11, 1, 0, 0, 0)
H6 = timedelta(hours=6)
P = DEFAULT_PARAMS


def _dep(dep_id, char_id, kind="demand", amount=1000, *, base=None, accrued_at=T0, rate=None, term=None,
         matures_at=None, accrued=0):
    return eb.DepositState(
        id=dep_id, character_id=char_id, kind=kind, amount=amount, accrued_at=accrued_at,
        interest_base=amount if base is None else base, interest_accrued=accrued, rate_day=rate, term_days=term,
        matures_at=matures_at,
    )


def _loan(loan_id=1, char_id=1, principal=1000, debt=None, *, issued=T0, term=7, rate=Decimal("0.005"),
          penalty=Decimal("0.01")):
    return eb.LoanState(
        id=loan_id, character_id=char_id, principal=principal, debt=principal if debt is None else debt,
        rate_day=rate, penalty_rate_day=penalty, due_at=issued + timedelta(days=term), accrued_at=issued,
    )


def _sum_legs(legs):
    return core.net_deltas(legs)


# --------------------------------------------------------------------------------------------- helpers

def test_accrue_floor_and_carry():
    coins, carry = eb.accrue(1000, Decimal("0.001"), 21600, Decimal(0))      # 1000 * 0.001 / 4 = 0.25
    assert (coins, carry) == (0, Decimal("0.250000"))
    total = 0
    for _ in range(4):
        coins, carry = eb.accrue(1000, Decimal("0.001"), 21600, carry)
        total += coins
    assert total == 1 and carry == Decimal("0.250000")                     # exact over time
    assert eb.accrue(0, Decimal("0.5"), 86400, Decimal("0.3")) == (0, Decimal("0.300000"))
    assert eb.accrue(1000, Decimal("0.5"), -5, Decimal(0)) == (0, Decimal(0))


def test_rates_reserve_cap_fee():
    assert eb.demand_rate(P, Decimal("0.5")) == Decimal("0.0005")
    assert eb.term_rate(P, 14, Decimal(1)) == Decimal("0.0025")
    with pytest.raises(ValueError):
        eb.term_rate(P, 10, Decimal(1))
    assert eb.reserve(101, 0.2) == 21                                      # ceil(20.2)
    assert eb.lendable(100, 101, P) == 79 and eb.lendable(10, 101, P) == 0
    assert eb.loan_cap(1, P) == 750 and eb.loan_cap(30, P) == 8000 and eb.loan_cap(0, P) == 750
    assert eb.transfer_fee(10, P) == 1 and eb.transfer_fee(101, P) == 3      # ceil(2.02)
    assert eb.debt_cap(1000, P) == 2000


def test_prorata():
    assert eb.prorata([5, 10], 100) == ([5, 10], 0)
    assert eb.prorata([5, 10], 0) == ([0, 0], 15)
    pays, skipped = eb.prorata([10, 20, 30], 30)
    assert pays == [5, 10, 15] and skipped == 30
    pays, skipped = eb.prorata([1, 1, 1], 2)
    assert sum(pays) <= 2 and skipped == 3 - sum(pays)


def test_plan_collection_order_and_limits():
    deps = [(5, "term", 100, 7), (3, "demand", 50, 0), (4, "demand", 20, 0)]
    plan = eb.plan_collection(160, deps, wallet=1000)
    assert [(t.deposit_id, t.from_interest, t.from_amount) for t in plan.takes] == [(3, 0, 50), (4, 0, 20), (5, 7, 83)]
    assert plan.wallet == 0 and plan.total == 160
    plan = eb.plan_collection(1000, deps, wallet=30)
    assert plan.wallet == 30 and plan.total == 50 + 20 + 107 + 30
    assert eb.plan_collection(0, deps, wallet=5).total == 0


def test_accrue_loan_across_due_and_cap():
    loan = _loan(principal=1000)
    acc = eb.accrue_loan(loan, T0 + timedelta(days=1), P)
    assert (acc.interest, acc.penalty, acc.debt, acc.status) == (5, 0, 1005, "active")
    # 1 day after due: 7 days at 0.5 % then 1 day at 1.5 % (1/3 interest, 2/3 penalty) on the running debt
    acc = eb.accrue_loan(loan, T0 + timedelta(days=8), P)
    assert acc.status == "overdue"
    assert acc.interest + acc.penalty == acc.debt - 1000
    assert acc.penalty == pytest.approx((1035) * 0.01, abs=1)
    # cap: debt never above 2 x principal
    acc = eb.accrue_loan(loan, T0 + timedelta(days=400), P)
    assert acc.debt == 2000 and acc.carry == 0
    assert eb.accrue_loan(dataclasses.replace(loan, status="closed"), T0 + timedelta(days=3), P).debt == 1000
    assert eb.is_overdue(loan, T0 + timedelta(days=7)) and not eb.is_overdue(loan, T0 + timedelta(days=6))


def test_rate_factor_next_bounds():
    assert eb.rate_factor_next(Decimal("0.5"), 0, 0, P) == Decimal("0.6250")          # target 1, smoothing 0.25
    assert eb.rate_factor_next(Decimal("0.2"), 0, 100, P) == Decimal("0.2000")        # target clamps to min
    assert eb.rate_factor_next(Decimal("1"), 10 ** 9, 1, P) == Decimal("1.0000")
    odd = SimParams(bank_rate_factor_min=0.12345)
    assert eb.rate_factor_next(Decimal(0), 0, 100, odd) == Decimal("0.1235")


# --------------------------------------------------------------------------------------------- bank_step

def _step(**kw):
    base = dict(region_id=7, now=T0 + H6, enabled=True, simulated=False, factor=Decimal(1), bank_balance=10000,
                purse_balance=0, residents=eb.ResidentState(accrued_at=T0))
    base.update(kw)
    return eb.bank_step(eb.BankInput(**base))


def test_step_demand_interest_and_min_balance():
    deps = (_dep(1, 1, amount=10000), _dep(2, 2, amount=5000, base=0))          # #2 deposited mid-period
    out = _step(deposits=deps, now=T0 + timedelta(days=1))
    assert out.deposits[0].amount == 10010 and out.deposits[0].interest_base == 10010
    assert out.deposits[1].amount == 5000 and out.deposits[1].interest_base == 5000   # earns from next period
    assert out.vault_delta == 10 and out.bank_balance == 9990
    assert _sum_legs(out.legs)[core.AccountRef.bank_deposits(7)] == 10
    assert deps[0].amount == 10000                                              # inputs not mutated


def test_step_disabled_pays_nothing_and_residents_wind_down():
    out = _step(enabled=False, simulated=True, deposits=(_dep(1, 1, amount=10000),), purse_balance=100,
                residents=eb.ResidentState(deposits=400, loans=0, accrued_at=T0), now=T0 + timedelta(days=1))
    assert out.vault_delta == 0 and out.deposits[0].amount == 10000
    # 1 day = 4 periods: k = 1 - 0.75^4 = 0.68359375 -> 273.4 rounded away (full periods) = 274
    assert out.stats["resident_out"] == 274 and out.residents.deposits == 126
    res = eb.ResidentState(deposits=3, accrued_at=T0)
    out = _step(enabled=False, simulated=True, residents=res)                  # k = 0.25: away-from-zero rounding
    assert out.residents.deposits == 2


def test_step_short_bank_pays_pro_rata():
    deps = (_dep(1, 1, amount=100000), _dep(2, 2, amount=100000))
    out = _step(deposits=deps, bank_balance=50, now=T0 + timedelta(days=1))    # dues 100 + 100, 50 free
    assert out.vault_delta == 50 and out.stats["interest_skipped"] == 150 and out.bank_balance == 0
    assert all(d.interest_carry == 0 for d in out.deposits)


def test_step_maturity_convert_and_merge():
    mat = T0 + timedelta(days=7)
    deps = (
        _dep(1, 1, amount=100),
        _dep(2, 1, "term", 1000, rate=Decimal("0.002"), term=7, matures_at=mat, accrued=10),
        _dep(3, 2, "term", 2000, rate=Decimal("0.002"), term=7, matures_at=mat),
        _dep(4, 2, "term", 500, rate=Decimal("0.002"), term=7, matures_at=mat),
    )
    out = _step(deposits=deps, enabled=False, now=mat + H6)
    d1, d2, d3, d4 = out.deposits
    assert d2.status == "closed" and d2.amount == 0 and d1.amount == 1110       # merged into the demand row
    assert d3.kind == "demand" and d3.rate_day is None and d3.demand_owner_id == 2  # converted in place
    assert d4.status == "closed" and d3.amount == 2500                           # then merged into #3
    assert out.stats["matured"] == 3 and out.stats["merged"] == 2
    assert sum(d.total for d in out.deposits) == sum(d.total for d in deps)


def test_step_term_accrues_until_maturity_only():
    mat = T0 + timedelta(days=1)
    deps = (_dep(1, 1, "term", 10000, rate=Decimal("0.002"), term=7, matures_at=mat, accrued_at=T0),)
    out = _step(deposits=deps, now=T0 + timedelta(days=3))
    assert out.vault_delta == 20 and out.deposits[0].amount == 10020 and out.deposits[0].kind == "demand"


def test_step_deterministic():
    kw = dict(deposits=(_dep(1, 1, amount=7777),), loans=(_loan(),), simulated=True, purse_balance=50000,
              residents=eb.ResidentState(deposits=3000, loans=1000, accrued_at=T0))
    assert _step(**kw) == _step(**kw)


# --------------------------------------------------------------------------------------------- 30-day loop

def test_120_passes_capital_like_bank():
    params = DEFAULT_PARAMS
    now = T0
    bank, purse = 20000, 400000
    deposits = [
        _dep(1, 1, amount=3000),
        _dep(2, 1, "term", 5000, rate=eb.term_rate(params, 7, 1), term=7, matures_at=T0 + timedelta(days=7)),
        _dep(3, 2, "term", 8000, rate=eb.term_rate(params, 28, 1), term=28, matures_at=T0 + timedelta(days=28)),
        _dep(4, 3, amount=50000),
    ]
    loans = [_loan(1, 4, principal=6000, term=7), _loan(2, 5, principal=750, term=28)]
    residents = eb.ResidentState(accrued_at=T0)
    factor = Decimal(1)
    vault = sum(d.total for d in deposits)
    lo, hi = eb.rate_factor_bounds(params)
    for _ in range(120):
        now += H6
        open_deps = [d for d in deposits if d.status == "open"]
        closed = [d for d in deposits if d.status != "open"]
        free_before = eb.lendable(bank, residents.deposits, params)
        out = eb.bank_step(eb.BankInput(
            region_id=1, now=now, enabled=True, simulated=True, factor=factor, bank_balance=bank,
            purse_balance=purse, residents=residents, deposits=open_deps, loans=loans, params=params,
        ))
        deltas = core.net_deltas(out.legs)
        assert bank + deltas.get(core.AccountRef.bank(1), 0) == out.bank_balance >= 0
        assert purse + deltas.get(core.AccountRef.purse(1), 0) == out.purse_balance >= 0
        assert deltas.get(core.AccountRef.bank_deposits(1), 0) == out.vault_delta
        assert out.stats["interest_paid"] + out.stats["resident_interest_paid"] <= free_before
        if out.stats["resident_out"] == 0:
            assert out.bank_balance >= eb.reserve(out.residents.deposits, params.bank_reserve_ratio)
        assert lo <= out.factor <= hi
        assert all(l.debt <= 2 * l.principal for l in out.loans)
        bank, purse, residents, factor, loans = (out.bank_balance, out.purse_balance, out.residents, out.factor,
                                                 list(out.loans))
        deposits = closed + list(out.deposits)
        vault += out.vault_delta
        assert vault == sum(d.total for d in deposits if d.status == "open")
    assert residents.deposits > 0 and residents.loans > 0
    assert loans[0].status == "overdue" and loans[0].penalty_total > 0 and 6000 < loans[0].debt <= 12000
    assert loans[1].status == "overdue" and loans[1].debt > 750                   # due on day 28
    assert all(d.kind == "demand" for d in deposits if d.status == "open")       # both term deposits matured
    assert sum(1 for d in deposits if d.status == "open" and d.character_id == 1) == 1   # merged



# =============================================================================================== Q1: full matrix

import copy
import random


def _legs_key_counts(legs):
    keys = [(l.src, l.dst, l.leg_type) for l in legs]
    return len(keys) == len(set(keys))


# --------------------------------------------------------------------------------------------- shared contract

def test_bank_contract_constants():
    assert core.KIND_BANK in core.ACCOUNT_KINDS and core.KIND_BANK_DEPOSITS in core.ACCOUNT_KINDS
    assert core.KIND_BANK not in core.NEGATIVE_ALLOWED_KINDS
    assert core.KIND_BANK_DEPOSITS not in core.NEGATIVE_ALLOWED_KINDS
    assert core.KIND_BANK_DEPOSITS in core.TAX_SOURCE_KINDS and core.KIND_BANK not in core.TAX_SOURCE_KINDS
    assert len(core.BANK_OP_TYPES) == 8 and core.BANK_OP_TYPES <= set(core.OP_TYPES)
    assert core.LEG_INTEREST in core.LEG_TYPES and core.LEG_INTEREST in core.CALLER_LEG_TYPES
    assert core.AccountRef.bank(3) != core.AccountRef.bank_deposits(3)


# --------------------------------------------------------------------------------------------- accrue / rates

@pytest.mark.parametrize("base,rate,seconds,carry,expected", [
    (10000, "0.001", 86400, "0", (10, Decimal("0"))),
    (999, "0.001", 86400, "0", (0, Decimal("0.999000"))),
    (999, "0.001", 86400, "0.001", (1, Decimal("0"))),
    (1, "0.001", 1, "0", (0, Decimal("0"))),                                 # 1.157e-8 floors to 6 dp
    (10 ** 9, "0.003", 21600, "0", (750000, Decimal("0"))),
    (1000, "0", 86400, "0.5", (0, Decimal("0.500000"))),                     # zero rate keeps the carry
    (1000, "0.001", 86400, "-3", (1, Decimal("0"))),                         # negative carry treated as 0
    (1000, "0.001", 0, "1.75", (1, Decimal("0.750000"))),                    # a whole carry is paid out
])
def test_accrue_matrix(base, rate, seconds, carry, expected):
    assert eb.accrue(base, Decimal(rate), seconds, Decimal(carry)) == expected


def test_accrue_carry_exact_over_a_year_of_ticks():
    total, carry = 0, Decimal(0)
    for _ in range(4 * 365):
        coins, carry = eb.accrue(1234, Decimal("0.0007"), 21600, carry)
        assert 0 <= carry < 1
        total += coins
    exact = Decimal(1234) * Decimal("0.0007") * 365
    assert total == int(exact) and float(total + carry) == pytest.approx(float(exact), abs=1e-5)


def test_rates_times_factor():
    f = Decimal("0.4")
    assert eb.demand_rate(P, f) == Decimal("0.0004")
    assert [eb.term_rate(P, t, f) for t in (7, 14, 28)] == [Decimal("0.0008"), Decimal("0.0010"), Decimal("0.0012")]
    assert eb.term_rate(P, 28, 1) == Decimal("0.003")
    for bad in (0, 1, 30, None):
        with pytest.raises(ValueError):
            eb.base_term_rate(P, bad)
    custom = SimParams(bank_demand_rate_day=0.01)
    assert eb.demand_rate(custom, Decimal("0.5")) == Decimal("0.005")


def test_reserve_and_lendable_edges():
    assert eb.reserve(0, 0.2) == 0 and eb.reserve(-50, 0.2) == 0
    assert eb.reserve(1, 0.2) == 1 and eb.reserve(5, 0.2) == 1 and eb.reserve(6, 0.2) == 2   # ceil
    assert eb.reserve(1000, 0) == 0 and eb.reserve(1000, 1) == 1000
    assert eb.lendable(0, 0, P) == 0 and eb.lendable(-10, 0, P) == 0
    assert eb.lendable(500, 0, P) == 500
    assert eb.lendable(1000, 1000, SimParams(bank_reserve_ratio=1)) == 0


def test_loan_cap_and_fee_params():
    assert eb.loan_cap(None, P) == 750 and eb.loan_cap(-3, P) == 750 and eb.loan_cap(2, P) == 1000
    assert eb.loan_cap(5, SimParams(bank_loan_cap_base=0, bank_loan_cap_per_level=100)) == 500
    assert eb.transfer_fee(0, P) == 1 and eb.transfer_fee(50, P) == 1 and eb.transfer_fee(51, P) == 2
    assert eb.transfer_fee(100, P) == 2 and eb.transfer_fee(10 ** 6, P) == 20000
    no_min = SimParams(bank_transfer_fee_min=0)
    assert eb.transfer_fee(1, no_min) == 1 and eb.transfer_fee(0, no_min) == 0
    assert eb.transfer_fee(10 ** 6, SimParams(bank_transfer_fee_rate=0, bank_transfer_fee_min=5)) == 5
    assert eb.debt_cap(333, SimParams(bank_debt_cap_mult=1.5)) == 499           # floor(499.5)


# --------------------------------------------------------------------------------------------- loans

def test_accrue_loan_only_penalty_segment_after_due():
    loan = _loan(principal=1000)
    late = dataclasses.replace(loan, accrued_at=loan.due_at)
    acc = eb.accrue_loan(late, loan.due_at + timedelta(days=1), P)            # 1000 x 1.5 % = 15: 5 + 10
    assert (acc.interest, acc.penalty, acc.debt, acc.status) == (5, 10, 1015, "overdue")
    exact = eb.accrue_loan(loan, loan.due_at, P)                                # exactly at due: overdue, no penalty
    assert exact.status == "overdue" and exact.penalty == 0 and exact.interest == 35


def test_accrue_loan_split_compounds_on_running_debt():
    loan = _loan(principal=10000)
    acc = eb.accrue_loan(loan, loan.due_at + timedelta(days=2), P)
    # 7 d x 0.5 % on 10000 = 350; then 2 d x 1.5 % on 10350 = 310.5 -> 310; penalty floor(310 x 2/3) = 206
    assert (acc.interest, acc.penalty, acc.debt) == (350 + 104, 206, 10660)
    assert acc.carry == Decimal("0.5")


def test_accrue_loan_cap_cuts_penalty_first():
    loan = dataclasses.replace(_loan(principal=1000, debt=1980), accrued_at=T0 + timedelta(days=7))
    acc = eb.accrue_loan(loan, T0 + timedelta(days=8), P)                    # part 29 = 10 + 19, cap leaves 20
    assert (acc.interest, acc.penalty, acc.debt, acc.carry) == (10, 10, 2000, 0)
    loan = dataclasses.replace(loan, debt=1990)                                # part 29, excess 19 = the penalty
    acc = eb.accrue_loan(loan, T0 + timedelta(days=8), P)
    assert (acc.interest, acc.penalty, acc.debt) == (10, 0, 2000)
    at_cap = dataclasses.replace(loan, debt=2000, interest_carry=Decimal("0.7"))
    acc = eb.accrue_loan(at_cap, T0 + timedelta(days=30), P)
    assert (acc.interest, acc.penalty, acc.debt, acc.carry) == (0, 0, 2000, 0)
    flat = eb.accrue_loan(_loan(principal=1000), T0 + timedelta(days=30), SimParams(bank_debt_cap_mult=1))
    assert flat.debt == 1000 and flat.interest == flat.penalty == 0


def test_accrue_loan_inactive_and_zero_penalty_rate():
    loan = _loan(principal=1000)
    for status in ("closed", "written_off"):
        acc = eb.accrue_loan(dataclasses.replace(loan, status=status), T0 + timedelta(days=20), P)
        assert (acc.interest, acc.penalty, acc.debt, acc.status) == (0, 0, 1000, status)
    paid = dataclasses.replace(loan, debt=0)
    assert eb.accrue_loan(paid, T0 + timedelta(days=20), P).debt == 0
    assert not eb.is_overdue(paid, T0 + timedelta(days=20))
    assert not eb.is_overdue(dataclasses.replace(loan, status="closed"), T0 + timedelta(days=20))
    nopen = dataclasses.replace(loan, penalty_rate_day=Decimal(0))
    acc = eb.accrue_loan(nopen, T0 + timedelta(days=8), P)
    assert acc.penalty == 0 and acc.status == "overdue" and acc.interest == 35 + 5   # 1035 x 0.5 % = 5.175


def test_accrue_loan_stepwise_keeps_carry_and_is_monotonic():
    loan = _loan(principal=750, term=7)
    now = T0
    for _ in range(4 * 20):
        now += H6
        acc = eb.accrue_loan(loan, now, P)
        new = eb.apply_loan_accrual(loan, acc, now)
        assert new.debt >= loan.debt and new.accrued_at == now and 0 <= new.interest_carry < 1
        assert new.interest_total + new.penalty_total == new.debt - 750
        loan = new
    assert loan.status == "overdue" and loan.penalty_total > 0 and loan.debt <= 1500
    closed = dataclasses.replace(loan, status="closed")
    assert eb.apply_loan_accrual(closed, eb.accrue_loan(closed, now, P), now + H6) is closed


# --------------------------------------------------------------------------------------------- prorata / collection

def test_prorata_edges():
    assert eb.prorata([], 100) == ([], 0)
    assert eb.prorata([0, 0], 0) == ([0, 0], 0)
    assert eb.prorata([5, -3], -10) == ([0, 0], 5)
    rng = random.Random(184)
    for _ in range(300):
        dues = [rng.randint(0, 500) for _ in range(rng.randint(1, 8))]
        avail = rng.randint(0, sum(dues) + 50)
        pays, skipped = eb.prorata(dues, avail)
        assert all(0 <= p <= d for p, d in zip(pays, dues))
        assert sum(pays) <= avail and skipped == sum(dues) - sum(pays)
        if avail >= sum(dues):
            assert pays == dues


def test_plan_collection_edges():
    plan = eb.plan_collection(100, [], wallet=40)
    assert plan.takes == () and plan.wallet == 40 and plan.total == 40
    plan = eb.plan_collection(30, [(1, "term", 100, 50)], wallet=1000)          # interest first, partial
    assert [(t.from_interest, t.from_amount) for t in plan.takes] == [(30, 0)] and plan.wallet == 0
    plan = eb.plan_collection(60, [(2, "demand", 0, 0), (1, "term", 100, 50)], wallet=0)  # empty row skipped
    assert [(t.deposit_id, t.total) for t in plan.takes] == [(1, 60)]
    plan = eb.plan_collection(-5, [(1, "demand", 10, 0)], wallet=10)
    assert plan.total == 0 and plan.takes == () and plan.wallet == 0
    plan = eb.plan_collection(50, [(1, "demand", -10, 0)], wallet=-3)
    assert plan.total == 0
    rng = random.Random(7)
    for _ in range(200):
        deps = [(i, rng.choice(["demand", "term"]), rng.randint(0, 300), rng.randint(0, 30)) for i in range(5)]
        wallet, debt = rng.randint(0, 300), rng.randint(0, 2500)
        plan = eb.plan_collection(debt, deps, wallet)
        by_id = {d[0]: d for d in deps}
        assert plan.total == sum(t.total for t in plan.takes) + plan.wallet <= debt
        assert plan.total == min(debt, sum(d[2] + d[3] for d in deps) + wallet)
        for t in plan.takes:
            assert t.from_interest <= by_id[t.deposit_id][3] and t.from_amount <= by_id[t.deposit_id][2]
        assert 0 <= plan.wallet <= wallet


# --------------------------------------------------------------------------------------------- factor

def test_rate_factor_next_target_and_smoothing():
    # income exactly covers cost x cover -> target 1
    assert eb.rate_factor_next(Decimal(1), Decimal("125"), Decimal("100"), P) == Decimal("1.0000")
    # half the cover -> target 0.5; 1 + (0.5 - 1) x 0.25
    assert eb.rate_factor_next(Decimal(1), Decimal("62.5"), Decimal("100"), P) == Decimal("0.8750")
    assert eb.rate_factor_next(Decimal("0.7"), 0, 100, SimParams(bank_rate_smoothing=0)) == Decimal("0.7000")
    assert eb.rate_factor_next(Decimal("0.7"), 0, 100, SimParams(bank_rate_smoothing=1)) == Decimal("0.2000")
    assert eb.rate_factor_next(Decimal(5), 0, 0, P) == Decimal("1.0000")              # out of range input
    assert eb.rate_factor_next(Decimal("0.5"), 0, -10, P) == Decimal("0.6250")          # negative cost = none
    assert eb.rate_factor_bounds(SimParams(bank_rate_factor_min=0)) == (Decimal("0.0000"), Decimal(1))
    f = Decimal(1)
    for _ in range(100):                                                               # converges to the minimum
        f = eb.rate_factor_next(f, 0, 100, P)
        assert Decimal("0.2") <= f <= 1 and f == f.quantize(Decimal("0.0001"))
    assert f == Decimal("0.2000")
    for _ in range(100):                                                               # and recovers fully to 1
        f = eb.rate_factor_next(f, 10 ** 6, 100, P)
    assert f == Decimal("1.0000")
    assert eb.rate_factor_next(Decimal("0.9999"), 0, 0, P) == Decimal("1.0000")        # no stall one step short
    # an off-grid target is reached, not overshot: target 0.33333..., from 0.3334 the step is -0.0001 -> 0.3333
    assert eb.rate_factor_next(Decimal("0.3334"), Decimal(1), Decimal("2.4"), P) == Decimal("0.3333")


# --------------------------------------------------------------------------------------------- bank_step

def test_step_term_rate_fixed_demand_rate_follows_factor():
    deps = (_dep(1, 1, amount=100000), _dep(2, 2, "term", 100000, rate=Decimal("0.002"), term=7,
                                            matures_at=T0 + timedelta(days=7)))
    out = _step(deposits=deps, factor=Decimal("0.5"), now=T0 + timedelta(days=1))
    assert out.deposits[0].amount == 100050                                     # 0.1 % x 0.5
    assert out.deposits[1].interest_accrued == 200 and out.deposits[1].amount == 100000   # fixed 0.2 %
    assert out.deposits[1].interest_base == 100000 and out.deposits[1].kind == "term"
    assert out.vault_delta == 250 and out.stats["interest_paid"] == 250
    assert out.deposits[0].interest_total == 50 and out.deposits[1].interest_total == 200
    assert all(d.accrued_at == T0 + timedelta(days=1) for d in out.deposits)


def test_step_merge_into_later_demand_row_and_its_base():
    mat = T0 + timedelta(days=7)
    deps = (_dep(1, 1, "term", 1000, rate=Decimal("0.002"), term=7, matures_at=mat, accrued=14,
                 accrued_at=mat - H6),
            _dep(5, 1, amount=300, accrued_at=mat - H6))
    out = _step(deposits=deps, now=mat, bank_balance=0)                        # empty bank: no new interest
    d1, d5 = out.deposits
    assert d1.status == "closed" and d1.amount == 0 and d1.interest_accrued == 0 and d1.closed_at == mat
    assert d1.demand_owner_id is None
    assert d5.amount == 1314 and d5.interest_base == 1314 and d5.demand_owner_id == 1
    assert out.stats["merged"] == 1 and out.vault_delta == 0


def test_step_short_bank_keeps_carry_of_rows_with_no_due():
    deps = (_dep(1, 1, amount=100000), dataclasses.replace(_dep(2, 2, amount=500), interest_carry=Decimal("0.3")))
    out = _step(deposits=deps, bank_balance=10, now=T0 + H6)                   # dues 25 + 0 (0.125 + 0.3); 10 free
    assert out.vault_delta == 10 and out.stats["interest_skipped"] == 15
    assert out.deposits[0].interest_carry == 0                                  # shortened: carry forfeited
    assert out.deposits[1].interest_carry == Decimal("0.425000")              # due 0 -> not shortened


def test_step_reserve_never_used_for_interest_or_lending():
    res = eb.ResidentState(deposits=10000, loans=0, accrued_at=T0)             # reserve 2000
    deps = (_dep(1, 1, amount=10 ** 7),)                                         # due 2500 a quarter day
    out = _step(deposits=deps, residents=res, bank_balance=2100, simulated=True, purse_balance=40000)  # at target
    # 100 free; dues 2500 (player) + 2 (residents) -> pro rata floor(2500 x 100 / 2502) = 99, floor(200 / 2502) = 0
    assert out.stats["interest_paid"] == 99 and out.stats["resident_interest_paid"] == 0
    assert out.stats["resident_issued"] == 1 and out.bank_balance == 2000          # only the floored-off coin is lent
    assert out.bank_balance >= eb.reserve(out.residents.deposits, P.bank_reserve_ratio)


def test_step_resident_loan_interest_short_purse_forgiven():
    res = eb.ResidentState(deposits=0, loans=100000, loan_carry=Decimal("0.9"), accrued_at=T0)
    out = _step(residents=res, simulated=True, purse_balance=50, bank_balance=0)   # due 125 a quarter day
    assert out.stats["resident_loan_interest"] == 50 and out.residents.loan_carry == 0
    assert out.purse_balance >= 0 and out.bank_balance >= 0
    full = _step(residents=res, simulated=True, purse_balance=10 ** 6, bank_balance=0)
    assert full.stats["resident_loan_interest"] == 125 and full.residents.loan_carry == Decimal("0.900000")


def test_step_resident_targets_and_k():
    res = eb.ResidentState(accrued_at=T0)
    out = _step(residents=res, simulated=True, purse_balance=100000, bank_balance=50000)  # 6 h: k = 0.25
    # deposits: target 20000, move 5000; loans: target floor(95000 x 0.1) = 9500, move 2375
    assert out.stats["resident_in"] == 5000 and out.residents.deposits == 5000
    assert out.stats["resident_issued"] == 2375 and out.residents.loans == 2375
    assert out.purse_balance == 100000 - 5000 + 2375 and out.bank_balance == 50000 + 5000 - 2375
    main = [l for l in out.legs if l.leg_type == core.LEG_MAIN]
    assert len(main) == 1 and main[0].src == core.AccountRef.purse(7) and main[0].amount == 2625   # netted
    first = _step(residents=eb.ResidentState(), simulated=True, purse_balance=100000, bank_balance=50000)
    assert first.stats["resident_in"] == 5000                                   # accrued_at None = one tick
    long = _step(residents=res, simulated=True, purse_balance=100000, bank_balance=50000,
                 now=T0 + timedelta(days=3))                                    # capped at 4 periods
    assert long.residents.deposits == 13672                                     # 20000 x (1 - 0.75^4), rounded up


def test_step_resident_issue_limited_by_lendable_and_payout_by_bank():
    res = eb.ResidentState(deposits=1000, accrued_at=T0)
    out = _step(residents=res, simulated=True, purse_balance=10 ** 6, bank_balance=300)
    assert out.stats["resident_issued"] <= eb.lendable(300 + out.stats["resident_in"], out.residents.deposits, P)
    out = _step(enabled=False, simulated=True, residents=res, bank_balance=120, now=T0 + timedelta(days=1))
    assert out.stats["resident_out"] == 120 and out.residents.deposits == 880 and out.bank_balance == 0


def test_step_not_simulated_residents_wind_down_and_get_no_interest():
    res = eb.ResidentState(deposits=4000, loans=2000, accrued_at=T0)
    out = _step(residents=res, simulated=False, purse_balance=10 ** 6, bank_balance=10 ** 6)
    assert out.stats["resident_interest_paid"] == 0
    assert out.stats["resident_out"] == 1000 and out.stats["resident_repaid"] == 500
    assert out.stats["resident_loan_interest"] == 2                              # loans still cost (2.5)
    assert out.residents.deposits == 3000 and out.residents.loans == 1500


def test_step_same_instant_is_a_no_op():
    res = eb.ResidentState(deposits=3000, loans=1000, dep_carry=Decimal("0.4"), accrued_at=T0 + H6)
    deps = (_dep(1, 1, amount=5000, accrued_at=T0 + H6),)
    loans = (dataclasses.replace(_loan(), accrued_at=T0 + H6),)
    out = _step(residents=res, deposits=deps, loans=loans, simulated=True, purse_balance=10 ** 5,
                factor=Decimal("0.6"))
    assert out.factor == Decimal("0.6") and out.legs == () and out.vault_delta == 0
    assert all(v == 0 for v in out.stats.values())
    assert out.residents.deposits == 3000 and out.residents.loans == 1000
    assert out.residents.dep_carry == Decimal("0.4")
    assert out.loans[0].debt == 1000


def test_step_disabled_bank_factor_frozen_loans_still_accrue_terms_still_mature():
    mat = T0 + timedelta(days=1)
    deps = (_dep(1, 1, "term", 1000, rate=Decimal("0.002"), term=7, matures_at=mat, accrued=3),)
    out = _step(enabled=False, deposits=deps, loans=(_loan(),), factor=Decimal("0.5"), now=mat + H6)
    assert out.factor == Decimal("0.5") and out.vault_delta == 0
    assert out.deposits[0].kind == "demand" and out.deposits[0].amount == 1003
    assert out.loans[0].debt > 1000 and out.stats["loan_interest"] > 0
    assert out.legs == ()                                                        # receivables only, no money


def test_step_loan_income_keeps_factor_up():
    deps = (_dep(1, 1, amount=100000),)
    loans = (_loan(principal=100000, term=28),)
    rich = _step(deposits=deps, loans=loans, factor=Decimal(1), now=T0 + timedelta(days=1))
    assert rich.factor == Decimal(1)                                             # 500 income vs 100 cost
    poor = _step(deposits=deps, factor=Decimal(1), now=T0 + timedelta(days=1))
    assert poor.factor == Decimal("0.4531")             # no income -> toward min: 1 - 0.8 x (1 - 0.75^4) over 1 day


def test_step_inputs_not_mutated():
    deps = [_dep(1, 1, amount=5000), _dep(2, 1, "term", 1000, rate=Decimal("0.002"), term=7,
                                          matures_at=T0 + H6)]
    loans = [_loan()]
    res = eb.ResidentState(deposits=2000, loans=500, accrued_at=T0)
    snap = copy.deepcopy((deps, loans, res))
    _step(deposits=deps, loans=loans, residents=res, simulated=True, purse_balance=10 ** 5)
    assert (deps, loans, res) == snap


def _random_world(rng, now):
    params = SimParams(bank_reserve_ratio=rng.choice([0, 0.2, 0.5, 1]),
                       bank_resident_adjust=rng.choice([0, 0.25, 1]),
                       bank_rate_factor_min=rng.choice([0, 0.2, 0.5]))
    deps, next_id = [], 1
    for char in range(1, rng.randint(2, 6)):
        if rng.random() < 0.7:
            amt = rng.randint(0, 50000)
            deps.append(_dep(next_id, char, amount=amt, base=rng.randint(0, amt),
                             accrued_at=now - timedelta(seconds=rng.randint(0, 3 * 86400))))
            next_id += 1
        for _ in range(rng.randint(0, 2)):
            term = rng.choice(eb.BANK_TERMS)
            opened = now - timedelta(days=rng.randint(0, 35))
            deps.append(_dep(next_id, char, "term", rng.randint(1, 50000), rate=eb.term_rate(params, term, 1),
                             term=term, matures_at=opened + timedelta(days=term), accrued=rng.randint(0, 500),
                             accrued_at=now - timedelta(seconds=rng.randint(0, 2 * 86400))))
            next_id += 1
    loans = []
    for i in range(rng.randint(0, 3)):
        principal = rng.randint(10, 8000)
        loans.append(dataclasses.replace(
            _loan(i + 1, 10 + i, principal=principal, issued=now - timedelta(days=rng.randint(0, 40)),
                  term=rng.choice(eb.BANK_TERMS)),
            debt=rng.randint(0, 2 * principal), accrued_at=now - timedelta(seconds=rng.randint(0, 86400))))
    res = eb.ResidentState(deposits=rng.randint(0, 100000), loans=rng.randint(0, 50000),
                           dep_carry=Decimal(rng.randint(0, 999999)) / 10 ** 6,
                           loan_carry=Decimal(rng.randint(0, 999999)) / 10 ** 6,
                           accrued_at=rng.choice([None, now, now - H6, now - timedelta(days=2)]))
    return eb.BankInput(
        region_id=rng.randint(1, 50), now=now, enabled=rng.random() < 0.8, simulated=rng.random() < 0.7,
        factor=Decimal(rng.randint(0, 12000)) / 10000, bank_balance=rng.randint(0, 200000),
        purse_balance=rng.randint(0, 500000), residents=res, deposits=tuple(deps), loans=tuple(loans),
        params=params,
    )


def test_step_random_worlds_guarantees():
    rng = random.Random(20261029)
    now = datetime(2026, 12, 1, 12, 0, 0)
    for _ in range(400):
        inp = _random_world(rng, now)
        snap = copy.deepcopy(inp)
        out = eb.bank_step(inp)
        assert inp == snap and eb.bank_step(inp) == out                     # not mutated, deterministic
        region = inp.region_id
        bank, vault, purse = (core.AccountRef.bank(region), core.AccountRef.bank_deposits(region),
                              core.AccountRef.purse(region))
        deltas = core.net_deltas(out.legs)
        assert set(deltas) <= {bank, vault, purse} and sum(deltas.values()) == 0
        assert _legs_key_counts(out.legs) and all(l.amount > 0 for l in out.legs)
        assert inp.bank_balance + deltas.get(bank, 0) == out.bank_balance >= 0
        assert inp.purse_balance + deltas.get(purse, 0) == out.purse_balance >= 0
        # sum of player pays = vault delta = the growth of the deposit rows
        assert deltas.get(vault, 0) == out.vault_delta == out.stats["interest_paid"]
        assert sum(d.total for d in out.deposits) - sum(d.total for d in inp.deposits) == out.vault_delta
        assert [d.id for d in out.deposits] == [d.id for d in inp.deposits]
        free = eb.lendable(inp.bank_balance, inp.residents.deposits, inp.params)
        assert out.stats["interest_paid"] + out.stats["resident_interest_paid"] <= free
        if not inp.enabled:
            assert out.vault_delta == 0 and out.stats["resident_interest_paid"] == 0
            assert out.factor == eb._clamp(inp.factor, *eb.rate_factor_bounds(inp.params))
            assert out.stats["resident_in"] == out.stats["resident_issued"] == 0
        lo, hi = eb.rate_factor_bounds(inp.params)
        assert lo <= out.factor <= hi
        # reserve: untouched unless the residents themselves withdrew
        if out.stats["resident_out"] == 0 and inp.bank_balance >= eb.reserve(inp.residents.deposits,
                                                                               inp.params.bank_reserve_ratio):
            assert out.bank_balance >= eb.reserve(out.residents.deposits, inp.params.bank_reserve_ratio)
        assert out.residents.deposits >= 0 and out.residents.loans >= 0
        assert 0 <= out.residents.dep_carry < 1 and 0 <= out.residents.loan_carry < 1
        for before, after in zip(inp.loans, out.loans):
            assert before.debt <= after.debt <= max(before.debt, eb.debt_cap(before.principal, inp.params))
            assert after.accrued_at == now
        open_rows = [d for d in out.deposits if d.status == "open"]
        demand_owners = [d.character_id for d in open_rows if d.kind == "demand"]
        assert len(demand_owners) == len(set(demand_owners))                 # UNIQUE demand_owner_id holds
        assert all(d.matures_at is None or d.kind == "demand" or d.matures_at > now for d in open_rows)
        assert all(d.amount >= 0 and d.interest_accrued >= 0 and 0 <= d.interest_carry < 1 for d in out.deposits)
        for d in open_rows:
            assert d.accrued_at == now and d.interest_base == d.amount


# --------------------------------------------------------------------------------------------- time weighting (B5 fix)

def test_time_weight_composes_and_is_bounded():
    s = Decimal("0.25")
    assert eb.time_weight(s, 0) == 0 and eb.time_weight(s, -100) == 0
    assert eb.time_weight(s, eb.TICK_SECONDS) == s                                     # nominal period: exact
    half = eb.time_weight(s, eb.TICK_SECONDS // 2)
    assert abs((1 - (1 - half) ** 2) - s) < Decimal("1e-20")                          # two halves = one period
    assert eb.time_weight(s, 5) < Decimal("0.0001")
    cap = eb.time_weight(s, eb.TICK_SECONDS * eb.MAX_CATCHUP_PERIODS)
    assert cap == Decimal(1) - Decimal("0.75") ** 4
    assert eb.time_weight(s, 365 * eb.DAY) == cap                                     # long downtime is bounded
    assert eb.time_weight(1, 5) == 1 and eb.time_weight(0, eb.DAY) == 0


def test_rate_factor_next_time_weighted():
    nominal = eb.rate_factor_next(Decimal(1), 0, 100, P)
    assert nominal == eb.rate_factor_next(Decimal(1), 0, 100, P, eb.TICK_SECONDS) == Decimal("0.8000")
    assert eb.rate_factor_next(Decimal(1), 0, 100, P, 0) == Decimal("1.0000")        # no time -> unchanged
    assert eb.rate_factor_next(Decimal(1), 0, 100, P, 3) == Decimal("1.0000")        # seconds -> no forced 0.0001
    assert eb.rate_factor_next(Decimal("0.5"), 0, 0, P, 3) == Decimal("0.5000")
    f = Decimal(1)
    for _ in range(2):
        f = eb.rate_factor_next(f, 0, 100, P, eb.TICK_SECONDS // 2)
    assert abs(f - nominal) <= Decimal("0.0002")                                     # two halves ~ one period
    day = eb.rate_factor_next(Decimal(1), 0, 100, P, eb.DAY)
    month = eb.rate_factor_next(Decimal(1), 0, 100, P, 30 * eb.DAY)
    assert day == month == Decimal("0.4531")                                           # bounded catch-up
    assert eb.rate_factor_next(Decimal("0.2001"), 0, 100, P, eb.TICK_SECONDS - 7) == Decimal("0.2000")  # jitter


def test_step_back_to_back_runs_move_nothing():
    """B5 bug: two manual runs seconds apart dropped the factor 1.0 -> 0.8 and stepped residents by 1 coin."""
    # deposits at target (20 % of 15000), loans 200 short of target (10 % of 12000): a full period would move both
    res = eb.ResidentState(deposits=3000, loans=1000, accrued_at=T0 + H6)
    deps = (_dep(1, 1, amount=5000, accrued_at=T0 + H6),)
    for secs in (0, 1, 5, 30):
        out = _step(residents=res, deposits=deps, simulated=True, purse_balance=12000, factor=Decimal(1),
                    now=T0 + H6 + timedelta(seconds=secs))
        # no income at all -> target 0.2; before the fix any run dropped the factor to 0.8000
        assert out.factor >= Decimal("0.999") and (secs > 5 or out.factor == Decimal(1)), (secs, out.factor)
        assert out.residents.deposits == 3000 and out.residents.loans == 1000, secs
        assert out.stats["resident_in"] == out.stats["resident_out"] == 0
        assert out.stats["resident_issued"] == out.stats["resident_repaid"] == 0
        net = _sum_legs(out.legs)
        assert sum(net.values()) == 0                                                  # conservation
    # a huge gap still moves proportionally to the elapsed time (not a forced step): 17600 x w(5 s) ~ 1.17
    big = _step(residents=res, simulated=True, purse_balance=10 ** 5, now=T0 + H6 + timedelta(seconds=5))
    assert big.stats["resident_in"] <= 2
    nominal = _step(residents=res, simulated=True, purse_balance=12000, now=T0 + H6 * 2)
    assert nominal.stats["resident_issued"] == 50                                       # 200 x 0.25, unchanged


def test_step_two_half_periods_close_to_one_period():
    res = eb.ResidentState(accrued_at=T0)
    kw = dict(simulated=True, purse_balance=100000, bank_balance=50000)
    full = _step(residents=res, now=T0 + H6, **kw)
    a = _step(residents=res, now=T0 + H6 / 2, **kw)
    b = _step(residents=a.residents, now=T0 + H6, simulated=True, purse_balance=a.purse_balance,
              bank_balance=a.bank_balance)
    # within 2 % (the targets are coupled: loans issued in the first half raise the purse and the deposit target)
    assert abs(b.residents.deposits - full.residents.deposits) <= 0.02 * full.residents.deposits
    assert abs(b.residents.loans - full.residents.loans) <= 0.02 * full.residents.loans
    assert a.purse_balance + a.bank_balance == b.purse_balance + b.bank_balance == 150000   # nothing created


def test_step_full_period_still_converges_to_target():
    res = eb.ResidentState(deposits=3, accrued_at=T0)
    out = _step(enabled=False, simulated=True, residents=res)
    for i in range(1, 6):
        out = _step(enabled=False, simulated=True, residents=out.residents, purse_balance=out.purse_balance,
                    bank_balance=out.bank_balance, now=T0 + H6 * (i + 1))
    assert out.residents.deposits == 0
