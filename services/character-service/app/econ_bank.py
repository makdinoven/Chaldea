"""Banks (FEAT-184, section 3.6) — pure maths, no DB.

The tick runner (``econ_tick.py`` + ``economy_bank_crud.py``) locks one bank, converts its rows into the dataclasses
below and calls :func:`bank_step` once per bank; the player API uses the small helpers (rates, caps, fees,
``accrue_loan`` to project a debt, ``plan_collection`` for overdue loans). Everything here is deterministic and
side-effect free; inputs are never mutated.

Money model (3.1): ``bank`` = the bank's own money (capital, residents' deposits, loan repayments); ``bank_deposits``
= the vault of player deposits, always equal to Σ (amount + interest_accrued) of the open player deposit rows.
Interest moves real money ``bank -> bank_deposits`` (players) / ``bank -> purse`` (residents), so a bank with no free
money pays nothing. A reserve ``ceil(resident_deposits x bank_reserve_ratio)`` stays in ``bank`` and is never lent
nor used for interest.

Rounding (3.6): what the bank **pays** (interest) -> ``ROUND_FLOOR``; what the player **pays** (commission) ->
``ROUND_CEILING``; reserve -> ``ROUND_CEILING``; interest owed **to** the bank -> ``ROUND_FLOOR`` with the fraction
kept in a carry. Carries are quantized to 6 dp (``ROUND_FLOOR``), factors to 4 dp (DECIMAL(5,4) in the DB).

Changed by B3 (documented in the feature file): the residents' moves toward their targets round **away from zero**
(``ROUND_UP``) instead of truncating — ``ceil(|gap| x k) <= |gap|`` for ``k <= 1`` so it never overshoots, while
truncation would leave a wind-down stuck at a few coins forever. With no elapsed time (``k = 0``) nothing moves, and
the deposit-rate factor is only updated when time has passed (a second manual run at the same instant is a no-op).

Changed by fix (B5 bug): the factor's smoothing and the residents' adjustment are **time-weighted** —
``w = 1 - (1 - share) ** periods`` with ``periods = seconds / TICK_SECONDS`` capped at ``MAX_CATCHUP_PERIODS``, so
two half-periods equal one full period and runs seconds apart barely move anything. The away-from-zero rounding is
kept for a full period (convergence) but faded for shorter ones: a step rounds up only when its fraction is at least
``1 - periods`` (see :func:`_round_step`), so a run a few seconds after the last one never forces a 1-coin / 0.0001
step. At exactly one period both formulas are identical to before.
"""

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Sequence, Tuple

import econ_core as core
from econ_sim import DEFAULT_PARAMS, SimParams

DAY = 86400
TICK_SECONDS = 21600                     # one 6 h tick: the residents' adjustment speed is defined per tick
MAX_CATCHUP_PERIODS = 4                  # after a long downtime smoothing/adjustment catch up at most one day (4 ticks)
BANK_TERMS = (7, 14, 28)

DEPOSIT_DEMAND = "demand"
DEPOSIT_TERM = "term"
DEPOSIT_OPEN = "open"
DEPOSIT_CLOSED = "closed"

LOAN_ACTIVE = "active"
LOAN_OVERDUE = "overdue"
LOAN_CLOSED = "closed"
LOAN_WRITTEN_OFF = "written_off"
LOAN_OPEN_STATUSES = (LOAN_ACTIVE, LOAN_OVERDUE)

STAT_KEYS = (
    "interest_paid", "interest_skipped", "resident_interest_paid", "loan_interest", "penalties",
    "resident_loan_interest", "resident_in", "resident_out", "resident_issued", "resident_repaid", "matured", "merged",
)

_ZERO = Decimal(0)
_ONE = Decimal(1)
_Q6 = Decimal("0.000001")
_Q4 = Decimal("0.0001")


# --------------------------------------------------------------------------------------------- rounding helpers

def _dec(value) -> Decimal:
    """Decimal via str (0.1 -> Decimal('0.1')); None -> 0."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return _ZERO
    return Decimal(str(value))


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def q6(value: Decimal) -> Decimal:
    return _dec(value).quantize(_Q6, rounding=ROUND_FLOOR)


def q4(value: Decimal) -> Decimal:
    return _dec(value).quantize(_Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _p(params: SimParams, name: str) -> Decimal:
    return _dec(getattr(params, name))


def _periods(seconds) -> Decimal:
    """Elapsed time in nominal 6 h periods, clamped to ``[0, MAX_CATCHUP_PERIODS]``."""
    periods = Decimal(max(0, int(seconds))) / Decimal(TICK_SECONDS)
    return min(periods, Decimal(MAX_CATCHUP_PERIODS))


def time_weight(share, seconds) -> Decimal:
    """Share of a gap closed in ``seconds`` when ``share`` is closed per nominal period: ``1 - (1 - share) ** periods``.

    Exactly ``share`` for one period, 0 for no time; two half-periods compose to one period."""
    share = _clamp(_dec(share), _ZERO, _ONE)
    periods = _periods(seconds)
    if periods <= 0 or share <= 0:
        return _ZERO
    if periods == _ONE or share >= _ONE:
        return share
    return _clamp(_ONE - (_ONE - share) ** periods, _ZERO, _ONE)


def _round_step(value: Decimal, seconds) -> int:
    """Round a step (in whole units) toward zero, but **away** from zero when its fraction is at least
    ``1 - periods``: a full period always rounds away (no stalling short of the target), a near-zero elapsed run
    effectively truncates (no forced 1-unit step)."""
    value = _dec(value)
    sign = -1 if value < 0 else 1
    mag = abs(value)
    whole = _floor(mag)
    frac = mag - whole
    if frac > 0 and frac >= _ONE - min(_ONE, _periods(seconds)):
        whole += 1
    return sign * whole


def seconds_between(start: Optional[datetime], end: datetime) -> int:
    """Whole seconds in ``[start, end)``; 0 when ``start`` is missing or not before ``end``."""
    if start is None or end <= start:
        return 0
    return int((end - start).total_seconds())


# --------------------------------------------------------------------------------------------- small helpers

def accrue(base: int, rate_day, seconds: int, carry) -> Tuple[int, Decimal]:
    """Interest on ``base`` at ``rate_day`` for ``seconds`` plus the previous carry: ``(whole coins, new carry)``.

    ``exact = base x rate_day x seconds / DAY + carry``; coins = ``floor(exact)``; carry = ``q6(exact - coins)``.
    Non-positive base / rate / seconds add nothing (the carry is kept)."""
    carry = _dec(carry)
    if carry < 0:
        carry = _ZERO
    rate = _dec(rate_day)
    seconds = max(0, int(seconds))
    base = max(0, int(base))
    exact = carry
    if base > 0 and rate > 0 and seconds > 0:
        exact = Decimal(base) * rate * Decimal(seconds) / Decimal(DAY) + carry
    coins = _floor(exact)
    return coins, q6(exact - coins)


def exact_interest(base: int, rate_day, seconds: int) -> Decimal:
    """``base x rate_day x seconds / DAY`` without rounding (the deposit cost of the rate factor)."""
    if base <= 0 or seconds <= 0:
        return _ZERO
    return Decimal(int(base)) * _dec(rate_day) * Decimal(int(seconds)) / Decimal(DAY)


def demand_rate(params: SimParams, factor) -> Decimal:
    """Current demand-deposit rate per day = base x the bank's factor."""
    return _p(params, "bank_demand_rate_day") * _dec(factor)


def base_term_rate(params: SimParams, term_days: int) -> Decimal:
    if term_days not in BANK_TERMS:
        raise ValueError(f"term_days must be one of {BANK_TERMS}, got {term_days!r}")
    return _p(params, f"bank_term_rate_day_{int(term_days)}")


def term_rate(params: SimParams, term_days: int, factor) -> Decimal:
    """Rate per day of a new term deposit (fixed at opening) = base term rate x the bank's factor."""
    return base_term_rate(params, term_days) * _dec(factor)


def reserve(resident_deposits: int, ratio) -> int:
    """Part of the bank's own money kept for the residents' deposits (never lent, never used for interest)."""
    return max(0, _ceil(Decimal(max(0, int(resident_deposits))) * _dec(ratio)))


def lendable(bank_balance: int, resident_deposits: int, params: SimParams = DEFAULT_PARAMS) -> int:
    """Free money of the bank: its balance above the reserve."""
    return max(0, int(bank_balance) - reserve(resident_deposits, params.bank_reserve_ratio))


@dataclass(frozen=True)
class ResidentRescale:
    """FEAT-186 «Привести к масштабу»: residents' bank positions brought to the scaled purse target."""

    deposits_target: int
    loans_target: int
    deposits_out: int        # bank -> purse (residents take back the part of their deposits above the target)
    loans_repaid: int        # purse -> bank (residents repay the part of their loans above the target)
    deposits_after: int
    loans_after: int

    @property
    def net_to_purse(self) -> int:
        return self.deposits_out - self.loans_repaid


def resident_rescale(*, purse: int, bank_balance: int, deposits: int, loans: int, purse_target: int,
                     enabled: bool, params: SimParams = DEFAULT_PARAMS) -> ResidentRescale:
    """Targets = the steady state of the residents' step for a purse at ``purse_target`` (enabled bank):
    deposits ``D* = floor(P* x s / (1 - s))`` (so ``floor((P* + D*) x s) ≈ D*``), loans ``L* = floor(P* x loan_share)``;
    a disabled bank -> 0 / 0 (the tick winds them down anyway). The excess deposits and the excess loans are first set
    off against each other (no cash needed: the residents repay with their own deposits); what is left is paid in
    cash — extra deposits from the bank's whole balance (the reserve exists for exactly this; the bank never goes
    negative — what it cannot pay stays owed and the tick returns it later), extra loans from the purse (never below
    0). Already at/below the targets -> nothing moves (idempotent).
    """
    purse, bank_balance = max(0, int(purse)), max(0, int(bank_balance))
    deposits, loans, target = max(0, int(deposits)), max(0, int(loans)), max(0, int(purse_target))
    if enabled:
        share = min(_p(params, "bank_resident_deposit_share"), Decimal("0.99"))
        d_target = _floor(Decimal(target) * share / (Decimal(1) - share))
        l_target = _floor(Decimal(target) * _p(params, "bank_resident_loan_share"))
    else:
        d_target = l_target = 0
    want_out, want_repay = max(0, deposits - d_target), max(0, loans - l_target)
    offset = min(want_out, want_repay)
    out = offset + min(want_out - offset, bank_balance)
    repaid = offset + min(want_repay - offset, purse)
    return ResidentRescale(deposits_target=d_target, loans_target=l_target, deposits_out=out, loans_repaid=repaid,
                           deposits_after=deposits - out, loans_after=loans - repaid)


def loan_cap(level: Optional[int], params: SimParams = DEFAULT_PARAMS) -> int:
    """Largest loan a character of ``level`` may take (level < 1 counts as 1)."""
    lvl = max(1, int(level or 0))
    return int(params.bank_loan_cap_base) + int(params.bank_loan_cap_per_level) * lvl


def transfer_fee(amount: int, params: SimParams = DEFAULT_PARAMS) -> int:
    """Commission of a transfer: ``max(fee_min, ceil(amount x fee_rate))``."""
    share = Decimal(max(0, int(amount))) * _p(params, "bank_transfer_fee_rate")
    return max(int(params.bank_transfer_fee_min), _ceil(share))


def debt_cap(principal: int, params: SimParams = DEFAULT_PARAMS) -> int:
    """Interest and penalties stop once the debt reaches ``principal x bank_debt_cap_mult``."""
    return _floor(Decimal(int(principal)) * _p(params, "bank_debt_cap_mult"))


# --------------------------------------------------------------------------------------------- state

@dataclass(frozen=True)
class DepositState:
    """One open ``bank_deposits`` row (the runner passes only open rows of one bank, ascending id)."""

    id: int
    character_id: int
    kind: str                                   # demand | term
    amount: int
    accrued_at: datetime
    interest_base: int = 0                      # smallest amount since accrued_at (Q3)
    interest_accrued: int = 0                   # term only
    interest_total: int = 0
    interest_carry: Decimal = _ZERO
    rate_day: Optional[Decimal] = None          # term: fixed; demand: None (current rate)
    term_days: Optional[int] = None
    matures_at: Optional[datetime] = None
    status: str = DEPOSIT_OPEN
    closed_at: Optional[datetime] = None

    @property
    def demand_owner_id(self) -> Optional[int]:
        """Value of the ``demand_owner_id`` column (UNIQUE per bank): set only for an open demand deposit."""
        return self.character_id if self.kind == DEPOSIT_DEMAND and self.status == DEPOSIT_OPEN else None

    @property
    def total(self) -> int:
        """What the row holds in the vault."""
        return int(self.amount) + int(self.interest_accrued)


@dataclass(frozen=True)
class LoanState:
    """One ``bank_loans`` row."""

    id: int
    character_id: int
    principal: int
    debt: int
    rate_day: Decimal
    penalty_rate_day: Decimal
    due_at: datetime
    accrued_at: datetime
    status: str = LOAN_ACTIVE
    interest_total: int = 0
    penalty_total: int = 0
    interest_carry: Decimal = _ZERO


@dataclass(frozen=True)
class LoanAccrual:
    interest: int           # added at the base rate
    penalty: int            # added at the penalty rate (after due_at)
    debt: int
    carry: Decimal
    status: str


def is_overdue(loan: LoanState, now: datetime) -> bool:
    return loan.status in LOAN_OPEN_STATUSES and int(loan.debt) > 0 and now >= loan.due_at


def accrue_loan(loan: LoanState, now: datetime, params: SimParams = DEFAULT_PARAMS) -> LoanAccrual:
    """Interest (and penalties after ``due_at``) on the running debt for ``[accrued_at, now)``.

    The period is split at ``due_at``: before it the loan's ``rate_day``; after it ``rate_day + penalty_rate_day``
    (the penalty share of that segment is reported separately). The second segment compounds on the debt after the
    first. The debt never grows above :func:`debt_cap` (the excess is dropped — first from the penalty — and the
    carry reset). Closed / written-off loans and loans with no debt accrue nothing."""
    status = loan.status
    debt = int(loan.debt)
    carry = _dec(loan.interest_carry)
    if status not in LOAN_OPEN_STATUSES or debt <= 0:
        return LoanAccrual(0, 0, max(0, debt), carry, status)
    if now >= loan.due_at:
        status = LOAN_OVERDUE
    cap = debt_cap(loan.principal, params)
    if debt >= cap:
        return LoanAccrual(0, 0, debt, _ZERO, status)

    rate = _dec(loan.rate_day)
    penalty_rate = _dec(loan.penalty_rate_day)
    before_end = min(now, loan.due_at)
    s1 = seconds_between(loan.accrued_at, before_end)
    s2 = seconds_between(max(loan.accrued_at, loan.due_at), now)

    interest, carry = accrue(debt, rate, s1, carry)
    penalty = 0
    if s2 > 0:
        total_rate = rate + penalty_rate
        part, carry = accrue(debt + interest, total_rate, s2, carry)
        pen = _floor(Decimal(part) * penalty_rate / total_rate) if total_rate > 0 else 0
        penalty += pen
        interest += part - pen
    new_debt = debt + interest + penalty
    if new_debt > cap:
        excess = new_debt - cap
        cut = min(excess, penalty)
        penalty -= cut
        interest -= excess - cut
        new_debt = cap
        carry = _ZERO
    return LoanAccrual(interest, penalty, new_debt, carry, status)


def apply_loan_accrual(loan: LoanState, acc: LoanAccrual, now: datetime) -> LoanState:
    """The loan row after :func:`accrue_loan` (clock moved to ``now``)."""
    if loan.status not in LOAN_OPEN_STATUSES:
        return loan
    return dataclasses.replace(
        loan, debt=acc.debt, status=acc.status, interest_carry=acc.carry, accrued_at=now,
        interest_total=int(loan.interest_total) + acc.interest, penalty_total=int(loan.penalty_total) + acc.penalty,
    )


def prorata(dues: Sequence[int], available: int) -> Tuple[List[int], int]:
    """Pay ``dues`` from ``available``: in full when it suffices, else ``floor(due x available / total)`` each.
    Returns ``(pays, skipped)`` with ``skipped = Σ dues − Σ pays``."""
    dues = [max(0, int(d)) for d in dues]
    total = sum(dues)
    available = max(0, int(available))
    if total <= available:
        return list(dues), 0
    if available <= 0:
        return [0] * len(dues), total
    pays = [d * available // total for d in dues]
    return pays, total - sum(pays)


@dataclass(frozen=True)
class DepositTake:
    deposit_id: int
    from_interest: int      # taken from interest_accrued
    from_amount: int        # taken from amount

    @property
    def total(self) -> int:
        return self.from_interest + self.from_amount


@dataclass(frozen=True)
class CollectionPlan:
    takes: Tuple[DepositTake, ...]
    wallet: int
    total: int


def plan_collection(debt: int, deposits: Sequence[Tuple[int, str, int, int]], wallet: int) -> CollectionPlan:
    """What the bank takes for an overdue ``debt``: demand deposits (ascending id), then term deposits (ascending id,
    ``interest_accrued`` first, then ``amount``), then the wallet. Every take is at most what is there and the total
    at most the debt — no balance goes negative. ``deposits`` = ``(id, kind, amount, interest_accrued)``."""
    left = max(0, int(debt))
    ordered = sorted(deposits, key=lambda d: (0 if d[1] == DEPOSIT_DEMAND else 1, int(d[0])))
    takes: List[DepositTake] = []
    for dep_id, _kind, amount, accrued in ordered:
        if left <= 0:
            break
        from_interest = min(left, max(0, int(accrued)))
        left -= from_interest
        from_amount = min(left, max(0, int(amount)))
        left -= from_amount
        if from_interest or from_amount:
            takes.append(DepositTake(int(dep_id), from_interest, from_amount))
    from_wallet = min(left, max(0, int(wallet)))
    left -= from_wallet
    return CollectionPlan(tuple(takes), from_wallet, max(0, int(debt)) - left)


def rate_factor_bounds(params: SimParams = DEFAULT_PARAMS) -> Tuple[Decimal, Decimal]:
    """[factor_min, 1] with factor_min rounded up to 4 dp (storable in DECIMAL(5,4))."""
    lo = _clamp(_p(params, "bank_rate_factor_min"), _ZERO, _ONE).quantize(_Q4, rounding=ROUND_CEILING)
    return lo, _ONE


def rate_factor_next(factor, income, cost_base, params: SimParams = DEFAULT_PARAMS,
                     seconds: int = TICK_SECONDS) -> Decimal:
    """Deposit-rate factor after a pass of ``seconds``: moves ``time_weight(bank_rate_smoothing, seconds)`` of the way
    toward ``income / (cost_base x cover)`` (1 when nothing is owed), within ``[factor_min, 1]``."""
    lo, hi = rate_factor_bounds(params)
    cost = _dec(cost_base)
    if cost <= 0:
        target = hi
    else:
        target = _clamp(_dec(income) / (cost * _p(params, "bank_rate_cover")), lo, hi)
    current = _clamp(_dec(factor), lo, hi)
    gap = target - current
    # The step rounds away from zero (like the residents' moves) so the factor really reaches its target instead of
    # stalling a few 0.0001 short (HALF_UP of a smoothed step < 0.00005 is 0); never past the target. Time-weighted:
    # a run seconds after the previous one moves (almost) nothing.
    weight = time_weight(_p(params, "bank_rate_smoothing"), seconds)
    step = _round_step(gap * weight / _Q4, seconds) * _Q4
    nxt = current + step
    if (gap >= 0 and nxt > target) or (gap < 0 and nxt < target):
        nxt = target
    return _clamp(q4(nxt), lo, hi)


# --------------------------------------------------------------------------------------------- the bank step

@dataclass(frozen=True)
class ResidentState:
    """Residents' aggregate position in the bank (``econ_banks`` columns)."""

    deposits: int = 0                   # the bank owes the residents
    loans: int = 0                      # the residents owe the bank
    dep_carry: Decimal = _ZERO
    loan_carry: Decimal = _ZERO
    accrued_at: Optional[datetime] = None


@dataclass(frozen=True)
class BankInput:
    region_id: int
    now: datetime
    enabled: bool                       # «Банк есть»
    simulated: bool                     # the region is in the economy simulation (residents exist)
    factor: Decimal                     # econ_banks.deposit_rate_factor
    bank_balance: int                   # ledger account bank(X)
    purse_balance: int                  # ledger account population_purse(X)
    residents: ResidentState = ResidentState()
    deposits: Sequence[DepositState] = ()   # open deposits of this bank, ascending id
    loans: Sequence[LoanState] = ()         # active/overdue loans of this bank, ascending id
    params: SimParams = DEFAULT_PARAMS


@dataclass(frozen=True)
class BankOutput:
    deposits: Tuple[DepositState, ...]  # every input deposit, updated (merged rows: status closed, amount 0)
    loans: Tuple[LoanState, ...]
    residents: ResidentState
    factor: Decimal
    bank_balance: int
    purse_balance: int
    vault_delta: int                    # = Σ interest paid to players (bank -> vault)
    legs: Tuple[core.Leg, ...]
    stats: Dict[str, int] = field(default_factory=dict)


def bank_legs(region_id: int, *, player_interest: int, resident_interest: int, resident_loan_interest: int,
              main_in: int, main_out: int) -> List[core.Leg]:
    """Legs of one ``bank_tick`` operation (at most one per (src, dst, leg_type), zero legs omitted):
    ``bank -> vault`` interest, ``bank -> purse`` interest, ``purse -> bank`` interest, and the residents' ``main``
    flows netted into one ``purse -> bank`` or ``bank -> purse`` leg."""
    bank = core.AccountRef.bank(region_id)
    vault = core.AccountRef.bank_deposits(region_id)
    purse = core.AccountRef.purse(region_id)
    legs: List[core.Leg] = []
    net = int(main_in) - int(main_out)
    for src, dst, amount, leg_type in (
        (bank, vault, player_interest, core.LEG_INTEREST),
        (bank, purse, resident_interest, core.LEG_INTEREST),
        (purse, bank, resident_loan_interest, core.LEG_INTEREST),
        (purse, bank, net, core.LEG_MAIN),
        (bank, purse, -net, core.LEG_MAIN),
    ):
        if amount > 0:
            legs.append(core.Leg(src, dst, int(amount), leg_type))
    return legs


def bank_step(inp: BankInput) -> BankOutput:
    """The whole bank pass of one bank (3.6 steps 1–8)."""
    params = inp.params
    now = inp.now
    stats = {k: 0 for k in STAT_KEYS}
    bank = max(0, int(inp.bank_balance))
    purse = max(0, int(inp.purse_balance))
    res = inp.residents
    res_deposits = max(0, int(res.deposits))
    res_loans = max(0, int(res.loans))
    lo, hi = rate_factor_bounds(params)
    factor = _clamp(_dec(inp.factor), lo, hi)
    residents_active = bool(inp.enabled and inp.simulated)
    seconds_bank = TICK_SECONDS if res.accrued_at is None else seconds_between(res.accrued_at, now)

    # 1. Loans (always): receivables grow; nothing moves.
    loans: List[LoanState] = []
    income = 0
    for loan in inp.loans:
        acc = accrue_loan(loan, now, params)
        loans.append(apply_loan_accrual(loan, acc, now))
        stats["loan_interest"] += acc.interest
        stats["penalties"] += acc.penalty
        income += acc.interest + acc.penalty

    # 2. Deposit dues (enabled only) + the cost base of the factor (demand/residents at factor 1, term fixed).
    deps = list(inp.deposits)
    dues: List[int] = []
    carries: List[Decimal] = []
    cost_base = _ZERO
    rate_now = demand_rate(params, factor)
    rate_one = demand_rate(params, _ONE)
    for d in deps:
        if not inp.enabled:
            dues.append(0)
            carries.append(_ZERO)
            continue
        if d.kind == DEPOSIT_TERM:
            end = min(now, d.matures_at) if d.matures_at is not None else now
            rate = _dec(d.rate_day)
            base_rate = rate
        else:
            end = now
            rate = rate_now
            base_rate = rate_one
        seconds = seconds_between(d.accrued_at, end)
        due, carry = accrue(d.interest_base, rate, seconds, d.interest_carry)
        dues.append(due)
        carries.append(carry)
        cost_base += exact_interest(int(d.interest_base), base_rate, seconds)
    if residents_active:
        due_res, res_dep_carry = accrue(res_deposits, rate_now, seconds_bank, res.dep_carry)
        cost_base += exact_interest(res_deposits, rate_one, seconds_bank)
    else:
        due_res, res_dep_carry = 0, _ZERO

    # 3. Pay from the free money only (the reserve is never touched); short -> pro rata, the rest forfeited.
    pays, skipped = prorata(dues + [due_res], lendable(bank, res_deposits, params))
    stats["interest_skipped"] = skipped
    player_paid = 0
    updated: List[DepositState] = []
    for d, due, pay, carry in zip(deps, dues, pays, carries):
        if pay < due:
            carry = _ZERO
        player_paid += pay
        if d.kind == DEPOSIT_TERM:
            d = dataclasses.replace(d, interest_accrued=int(d.interest_accrued) + pay)
        else:
            d = dataclasses.replace(d, amount=int(d.amount) + pay)
        updated.append(dataclasses.replace(d, interest_total=int(d.interest_total) + pay, interest_carry=carry))
    res_paid = pays[-1]
    if res_paid < due_res:
        res_dep_carry = _ZERO
    bank -= player_paid + res_paid
    purse += res_paid
    stats["interest_paid"] = player_paid
    stats["resident_interest_paid"] = res_paid

    # 4. Maturity: term rows with matures_at <= now -> demand (converted in place or merged into the open demand row).
    demand_idx: Dict[int, int] = {d.character_id: i for i, d in enumerate(updated)
                                  if d.kind == DEPOSIT_DEMAND and d.status == DEPOSIT_OPEN}
    for i, d in enumerate(updated):
        if d.kind != DEPOSIT_TERM or d.matures_at is None or d.matures_at > now:
            continue
        stats["matured"] += 1
        amount = int(d.amount) + int(d.interest_accrued)
        target = demand_idx.get(d.character_id)
        if target is not None:
            t = updated[target]
            updated[target] = dataclasses.replace(t, amount=int(t.amount) + amount)
            updated[i] = dataclasses.replace(d, amount=0, interest_accrued=0, interest_base=0, interest_carry=_ZERO,
                                             status=DEPOSIT_CLOSED, closed_at=now)
            stats["merged"] += 1
        else:
            updated[i] = dataclasses.replace(d, kind=DEPOSIT_DEMAND, amount=amount, interest_accrued=0, rate_day=None)
            demand_idx[d.character_id] = i

    # 5. Clocks: next period earns on the amount at its start (Q3 smallest-balance rule).
    updated = [
        dataclasses.replace(d, accrued_at=now, interest_base=int(d.amount)) if d.status == DEPOSIT_OPEN
        else dataclasses.replace(d, accrued_at=now)
        for d in updated
    ]

    # 6. Residents (targets 0 when the bank is disabled or the region is not simulated -> wind down).
    k = time_weight(_p(params, "bank_resident_adjust"), seconds_bank)
    # a) interest on the residents' loans: paid from the purse as far as it goes, the rest forgiven.
    due_l, res_loan_carry = accrue(res_loans, _p(params, "bank_loan_rate_day"), seconds_bank, res.loan_carry)
    res_loan_paid = min(due_l, purse)
    if res_loan_paid < due_l:
        res_loan_carry = _ZERO
    purse -= res_loan_paid
    bank += res_loan_paid
    income += res_loan_paid
    stats["resident_loan_interest"] = res_loan_paid
    # b) deposits toward a share of the residents' savings.
    target_d = 0
    if residents_active:
        target_d = _floor(Decimal(purse + res_deposits) * _p(params, "bank_resident_deposit_share"))
    dd = _round_step(Decimal(target_d - res_deposits) * k, seconds_bank)
    if dd > 0:
        moved = min(dd, purse)
        purse -= moved
        bank += moved
        res_deposits += moved
        stats["resident_in"] = moved
    elif dd < 0:
        moved = min(-dd, bank)
        bank -= moved
        purse += moved
        res_deposits -= moved
        stats["resident_out"] = moved
    # c) loans toward a share of the purse; issued from the free money only.
    target_l = _floor(Decimal(purse) * _p(params, "bank_resident_loan_share")) if residents_active else 0
    dl = _round_step(Decimal(target_l - res_loans) * k, seconds_bank)
    if dl > 0:
        moved = min(dl, lendable(bank, res_deposits, params))
        bank -= moved
        purse += moved
        res_loans += moved
        stats["resident_issued"] = moved
    elif dl < 0:
        moved = min(-dl, purse)
        purse -= moved
        bank += moved
        res_loans -= moved
        stats["resident_repaid"] = moved

    # 7. Deposit-rate factor (enabled only, and only when time has passed).
    if inp.enabled and seconds_bank > 0:
        factor = rate_factor_next(factor, income, cost_base, params, seconds_bank)

    # 8. Legs.
    legs = bank_legs(
        inp.region_id, player_interest=player_paid, resident_interest=res_paid, resident_loan_interest=res_loan_paid,
        main_in=stats["resident_in"] + stats["resident_repaid"],
        main_out=stats["resident_out"] + stats["resident_issued"],
    )
    residents = ResidentState(deposits=res_deposits, loans=res_loans, dep_carry=q6(res_dep_carry),
                              loan_carry=q6(res_loan_carry), accrued_at=now)
    return BankOutput(
        deposits=tuple(updated), loans=tuple(loans), residents=residents, factor=factor, bank_balance=bank,
        purse_balance=purse, vault_delta=player_paid, legs=tuple(legs), stats=stats,
    )
