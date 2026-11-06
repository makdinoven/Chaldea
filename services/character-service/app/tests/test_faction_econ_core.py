"""FEAT-206 QA: faction economy — pure rules (``faction_econ.py``, no DB). features/FEAT-206 §3.4.

Params whitelist / bounds / tolerant merge, wealth + words, regional caps and their split, the step planner (inflow
scaling, wages ratio, FIFO partial debts, restock budget / take cap / units, members dynamics with carry and bounds,
legs that only move money between accounts), donation points (daily cap, fractions carry) and the quartermaster price /
rank gate. A seeded random sweep checks the planner's money invariants on many inputs.
"""

import random
from decimal import Decimal

import pytest

import econ_core as core
import faction_econ as fe
from tests.faction_world import load_migration_046

S = fe.DEFAULT_ECON_SETTINGS
SEEDED = {code: fe.effective_params(params, None) for code, _n, _d, params, _o in load_migration_046().TEMPLATES}


def params(**kw):
    return fe.effective_params({k: (str(v) if isinstance(v, (float, Decimal)) else v) for k, v in kw.items()}, None)


def plan(members=100, *, p=None, s=S, purse_budget=10 ** 9, treasury_budget=10 ** 9, purse=10 ** 9,
         region_treasury=0, last_income=0, balance=0, debts=(), restock=(), market=None, carry=Decimal(0),
         lo=10, hi=5000, share=Decimal("0.5")):
    return fe.plan_faction_step(fe.FactionStateIn(7, 10, members, carry, lo, hi), p or params(), s,
                                fe.Budgets(purse_budget, treasury_budget), purse=purse,
                                region_treasury=region_treasury, last_income=last_income, balance=balance,
                                open_debts=list(debts), restock_rows=list(restock), market=market,
                                wholesale_share=share)


def net_faction(p_):
    into = sum(l.amount for l in p_.legs if l.dst.kind == core.KIND_FACTION_TREASURY)
    out = sum(l.amount for l in p_.legs if l.src.kind == core.KIND_FACTION_TREASURY)
    return into - out


# ============================================================================================ params


class TestParams:

    def test_seeded_templates_match_the_architecture_table(self):
        assert set(SEEDED) == {"order", "merchants_guild", "dark_guild", "temple", "academy"}
        o = SEEDED["order"]
        assert (o.start_members, o.norm_per_member, o.start_treasury_per_member) == (300, 30, 30)
        assert (o.dues_per_member, o.wage_per_member, o.profile_kind, o.profile_rate, o.qm_budget_share) == \
            (Decimal(1), Decimal(1), fe.PROFILE_TREASURY_SHARE, Decimal("0.005"), Decimal("0.1"))
        m = SEEDED["merchants_guild"]
        assert (m.start_members, m.dues_per_member, m.profile_kind, m.profile_rate) == \
            (200, Decimal("1.5"), fe.PROFILE_INCOME_SHARE, Decimal("0.01"))
        assert SEEDED["dark_guild"].profile_per_member == Decimal(1)
        t = SEEDED["temple"]
        assert (t.wage_per_member, t.profile_kind, t.profile_per_member) == \
            (Decimal("0.75"), fe.PROFILE_MEMBERS_PURSE, Decimal("0.75"))
        assert SEEDED["academy"].profile_per_member == Decimal("0.5")
        # every stored template passes the strict validator unchanged
        for _code, _n, _d, raw, _o in load_migration_046().TEMPLATES:
            assert fe.effective_params(fe.validate_params(raw, partial=False), None) == \
                fe.effective_params(raw, None)

    def test_each_template_inflow_covers_wages_at_baseline(self):
        """§3.4: at baseline each template's purse inflow >= wages (the treasury fills toward its norm)."""
        for code, p_ in SEEDED.items():
            w = fe.wants(100, p_, region_treasury=100_000, last_income=100_000)
            wages = int(100 * p_.wage_per_member)
            assert w.purse + w.profile_treasury >= wages, code

    @pytest.mark.parametrize("key,value", [
        ("bogus", 1), ("norm_per_member", 0), ("norm_per_member", 100001), ("norm_per_member", "1.5"),
        ("start_members", -1), ("dues_per_member", "1000.01"), ("profile_rate", "0.21"), ("profile_kind", "x"),
        ("profile_kind", 1), ("qm_budget_share", "1.1"), ("wage_per_member", True), ("dues_per_member", "NaN"),
        ("dues_per_member", "Infinity"), ("dues_per_member", None), ("dues_per_member", [1]),
        ("dues_per_member", "'; DROP TABLE factions; --"),
    ])
    def test_invalid_values_are_rejected_in_russian(self, key, value):
        with pytest.raises(fe.ParamError) as err:
            fe.validate_params({key: value}, partial=True)
        msg = str(err.value)
        assert msg and any("а" <= ch <= "я" for ch in msg.lower())

    def test_unknown_key_message(self):
        with pytest.raises(fe.ParamError, match="Неизвестный параметр шаблона: bogus"):
            fe.validate_params({"bogus": 1}, partial=True)

    def test_bounds_are_inclusive_and_values_normalised(self):
        out = fe.validate_params({"norm_per_member": "100000", "start_members": 0, "dues_per_member": 1000,
                                  "profile_rate": "0.2", "qm_budget_share": "0.1234567891"}, partial=True)
        assert out == {"start_members": 0, "norm_per_member": 100000, "dues_per_member": "1000",
                       "profile_rate": "0.2", "qm_budget_share": "0.123456"}         # 6 decimals, rounded down

    def test_full_template_gets_code_defaults(self):
        out = fe.validate_params({"dues_per_member": "2"}, partial=False)
        assert set(out) == set(fe.PARAM_KEYS)
        assert out["dues_per_member"] == "2" and out["norm_per_member"] == fe.DEFAULT_PARAMS.norm_per_member

    def test_effective_is_defaults_then_template_then_overrides(self):
        p_ = fe.effective_params({"dues_per_member": "1", "wage_per_member": "2"}, {"wage_per_member": "3"})
        assert (p_.dues_per_member, p_.wage_per_member, p_.norm_per_member) == (Decimal(1), Decimal(3), 30)

    def test_broken_stored_json_is_tolerated(self):
        p_ = fe.effective_params({"dues_per_member": "abc", "norm_per_member": 40, "zzz": 1}, ["not", "a", "dict"])
        assert p_.dues_per_member == fe.DEFAULT_PARAMS.dues_per_member and p_.norm_per_member == 40
        assert fe.effective_params(None, None) == fe.DEFAULT_PARAMS

    def test_settings_from_row_defaults_and_floors(self):
        assert fe.econ_settings_from_row(None) == S
        assert S == fe.EconSettings(10, 50, True, 2, 1, 5, 1, 5)

        class Row:
            donation_marks_per_point = 0
            donation_points_daily_cap = -5
            econ_enabled = 0
            econ_purse_share_pct = None

        s = fe.econ_settings_from_row(Row())
        assert (s.donation_marks_per_point, s.donation_points_daily_cap, s.econ_enabled, s.econ_purse_share_pct) == \
            (1, 0, False, 2)


# ============================================================================================ wealth


class TestWealth:

    @pytest.mark.parametrize("bal,norm,value", [
        (3000, 3000, 50), (6000, 3000, 100), (9000, 3000, 100), (0, 3000, 0), (-50, 3000, 0), (1, 100, 1),
        (2999, 3000, 50), (1499, 3000, 25), (30, 0, 100),
    ])
    def test_wealth_formula(self, bal, norm, value):
        assert fe.wealth(bal, norm) == value

    @pytest.mark.parametrize("value,state,label", [
        (100, "thriving", "Процветает"), (75, "thriving", "Процветает"), (74, "stable", "Держится"),
        (40, "stable", "Держится"), (39, "struggling", "В затруднении"), (15, "struggling", "В затруднении"),
        (14, "destitute", "Бедствует"), (0, "destitute", "Бедствует"),
    ])
    def test_words(self, value, state, label):
        assert fe.wealth_word(value) == {"state": state, "label": label}

    def test_no_template_no_wealth(self):
        assert fe.wealth_word(None) is None

    def test_norm_is_at_least_one(self):
        assert fe.norm(0, params(norm_per_member=30)) == 1
        assert fe.norm(100, params(norm_per_member=30)) == 3000


# ============================================================================================ caps


class TestCaps:

    def test_regional_caps(self):
        assert fe.regional_caps(10_000, 50_000, S) == (200, 500)
        assert fe.regional_caps(10_000, -50_000, S) == (200, 0)
        assert fe.regional_caps(-1, 0, S) == (0, 0)
        assert fe.regional_caps(99, 99, S) == (1, 0)

    def test_split_below_cap_gives_wants(self):
        assert fe.split_cap(1000, {1: 50, 2: 150}) == {1: 50, 2: 150}

    def test_split_above_cap_is_proportional_and_floored(self):
        assert fe.split_cap(100, {1: 50, 2: 150}) == {1: 25, 2: 75}
        assert fe.split_cap(2, {1: 1, 2: 1, 3: 1}) == {1: 0, 2: 0, 3: 0}
        assert fe.split_cap(0, {1: 10}) == {1: 0}
        assert fe.split_cap(10, {}) == {}

    def test_split_never_exceeds_cap_or_wants(self):
        rnd = random.Random(206)
        for _ in range(500):
            wants = {i: rnd.randint(0, 5000) for i in range(1, rnd.randint(2, 6))}
            cap = rnd.randint(0, 20000)
            out = fe.split_cap(cap, wants)
            assert sum(out.values()) <= cap or sum(out.values()) == sum(wants.values()) <= cap
            assert all(0 <= out[k] <= wants[k] for k in wants)

    def test_wants_by_profile_kind(self):
        assert fe.wants(100, SEEDED["order"], region_treasury=50_000, last_income=0) == fe.Wants(100, 0, 250)
        assert fe.wants(100, SEEDED["order"], region_treasury=-5, last_income=0) == fe.Wants(100, 0, 0)
        assert fe.wants(100, SEEDED["merchants_guild"], region_treasury=0, last_income=12_345) == fe.Wants(150, 123, 0)
        assert fe.wants(100, SEEDED["dark_guild"], region_treasury=0, last_income=0) == fe.Wants(50, 100, 0)
        assert fe.wants(33, SEEDED["temple"], region_treasury=0, last_income=0) == fe.Wants(16, 24, 0)   # floors
        assert fe.wants(100, params(profile_kind="none"), region_treasury=10 ** 6, last_income=10 ** 6).purse == 0


# ============================================================================================ planner


class TestStepInflows:

    def test_uncapped_takes_the_wants(self):
        p_ = plan(100, p=SEEDED["dark_guild"])
        assert (p_.dues, p_.profile_purse, p_.profile_treasury) == (50, 100, 0)

    def test_purse_budget_scales_dues_and_profile_together(self):
        p_ = plan(100, p=SEEDED["dark_guild"], purse_budget=60)
        assert (p_.dues, p_.profile_purse) == (20, 40)                   # 50:100 scaled to 60

    def test_purse_balance_also_caps(self):
        p_ = plan(100, p=SEEDED["dark_guild"], purse=30)
        assert (p_.dues, p_.profile_purse) == (10, 20)
        assert plan(100, p=SEEDED["dark_guild"], purse=0).dues == 0

    def test_treasury_profile_capped_by_budget_and_region(self):
        assert plan(100, p=SEEDED["order"], region_treasury=50_000, treasury_budget=70).profile_treasury == 70
        assert plan(100, p=SEEDED["order"], region_treasury=50_000).profile_treasury == 250
        assert plan(100, p=SEEDED["order"], region_treasury=-1).profile_treasury == 0

    def test_legs_route_purse_and_region(self):
        p_ = plan(100, p=SEEDED["order"], region_treasury=50_000, balance=1000)
        legs = {(l.src.kind, l.dst.kind): l.amount for l in p_.legs}
        assert legs[(core.KIND_POPULATION_PURSE, core.KIND_FACTION_TREASURY)] == 100
        assert legs[(core.KIND_REGION_TREASURY, core.KIND_FACTION_TREASURY)] == 250
        assert legs[(core.KIND_FACTION_TREASURY, core.KIND_POPULATION_PURSE)] == 100          # wages
        assert all(l.src.ref_id in (7, 10) and l.dst.ref_id in (7, 10) for l in p_.legs)


class TestWagesAndMembers:

    def test_half_wages_paid_members_leave_with_carry(self):
        p_ = plan(100, p=params(wage_per_member=1), balance=50)
        assert (p_.wages_due, p_.wages_paid, p_.balance_after) == (100, 50, 0)
        assert (p_.members_after, p_.carry_after) == (98, Decimal("-0.5"))      # -100 x 5 % x 0.5 = -2.5

    def test_no_wages_paid_full_leave_rate(self):
        p_ = plan(1000, p=params(wage_per_member=1))
        assert p_.members_after == 950                                            # -5 %

    def test_carry_accumulates_across_ticks(self):
        first = plan(12, p=params(wage_per_member=1))
        assert (first.members_after, first.carry_after) == (12, Decimal("-0.6"))
        second = plan(12, p=params(wage_per_member=1), carry=first.carry_after)
        assert (second.members_after, second.carry_after) == (11, Decimal("-0.2"))

    def test_lower_bound_clamps_and_keeps_only_the_fraction(self):
        p_ = plan(10, p=params(wage_per_member=1), carry=Decimal("-0.9"))
        assert (p_.members_after, p_.carry_after) == (10, Decimal("-0.4"))

    def test_upper_bound(self):
        p_ = plan(5000, p=params(wage_per_member=0, norm_per_member=1), balance=10 ** 6)
        assert p_.members_after == 5000
        p_ = plan(100, p=params(norm_per_member=1), balance=10 ** 6, hi=100)
        assert p_.members_after == 100

    def test_rich_treasury_grows_one_percent(self):
        p_ = plan(100, p=params(wage_per_member=1, norm_per_member=30), balance=6100)   # after wages 6000 = 2x norm
        assert (p_.wealth_after, p_.members_after) == (100, 101)

    def test_growth_scales_with_wealth_above_neutral(self):
        p_ = plan(100, p=params(norm_per_member=30), balance=4500)            # wealth 75
        assert (p_.wealth_after, p_.carry_after, p_.members_after) == (75, Decimal("0.5"), 100)

    def test_paid_but_poor_no_change(self):
        p_ = plan(100, p=params(wage_per_member=1, norm_per_member=30), balance=1100)   # wealth 17 after wages
        assert p_.wages_paid == 100 and p_.members_after == 100 and p_.carry_after == 0

    def test_no_wages_due_counts_as_paid(self):
        assert plan(100, p=params(norm_per_member=30), balance=0).members_after == 100

    def test_settings_rates_apply(self):
        s = fe.EconSettings(members_leave_pct=50, members_grow_pct=10)
        assert plan(100, p=params(wage_per_member=1), s=s).members_after == 50
        assert plan(100, p=params(norm_per_member=1), s=s, balance=10 ** 6).members_after == 110

    def test_wealth_measured_against_the_norm_before_the_change(self):
        p_ = plan(200, p=params(wage_per_member=1, norm_per_member=10), balance=2200)  # 2000 left, norm 2000
        assert p_.wealth_after == 50


class TestDebts:

    def test_fifo_by_id_with_partial(self):
        debts = [fe.DebtIn(3, 1, 30), fe.DebtIn(1, 2, 50), fe.DebtIn(2, 1, 40)]
        by_debt, by_char, left = fe.plan_debts(100, debts)
        assert by_debt == {1: 50, 2: 40, 3: 10} and by_char == {2: 50, 1: 50} and left == 0

    def test_nothing_available(self):
        assert fe.plan_debts(0, [fe.DebtIn(1, 1, 5)]) == ({}, {}, 0)
        assert fe.plan_debts(-5, [fe.DebtIn(1, 1, 5)]) == ({}, {}, 0)

    def test_surplus_is_left(self):
        assert fe.plan_debts(100, [fe.DebtIn(1, 1, 5), fe.DebtIn(2, 1, 0)]) == ({1: 5}, {1: 5}, 95)

    def test_wages_before_debts(self):
        p_ = plan(100, p=params(wage_per_member=1), balance=130, debts=[fe.DebtIn(1, 1, 50)])
        assert (p_.wages_paid, p_.debts, p_.payouts) == (100, {1: 30}, {1: 30})
        legs = [(l.dst.kind, l.dst.ref_id, l.amount) for l in p_.legs if l.dst.is_character]
        assert legs == [(core.KIND_CHARACTER, 1, 30)]

    def test_debts_before_restock(self):
        market = {"arms": fe.MarketGroupIn(1000.0, Decimal(1), 100)}
        p_ = plan(10, p=params(norm_per_member=1, qm_budget_share=1), balance=1000,
                  debts=[fe.DebtIn(1, 1, 1000)], restock=[fe.RestockRowIn(1, "arms", 0, 50, 100)], market=market)
        assert p_.debts == {1: 1000} and p_.restock == {} and p_.balance_after == 0


class TestRestock:
    MARKET = {"arms": fe.MarketGroupIn(1000.0, Decimal(1), 100)}

    def _plan(self, rows, *, balance=10_000, members=100, market=None, share=Decimal("0.10"), s=S, mult=None):
        return plan(members, p=params(norm_per_member=30, qm_budget_share=share), balance=balance,
                    restock=rows, market=market or self.MARKET, s=s)

    def test_budget_is_share_of_excess_over_half_norm(self):
        # available 10 000, half norm 1500 -> excess 8500 x 0.10 = 850 -> 17 swords at wholesale 50
        p_ = self._plan([fe.RestockRowIn(1, "arms", 0, 100, 100)], s=fe.EconSettings(qm_take_share_pct=50))
        assert p_.restock == {1: 17} and p_.restock_spent == 850 and p_.balance_after == 10_000 - 850
        assert p_.stock_delta == {"arms": -17.0}

    def test_take_cap_of_region_stock(self):
        p_ = self._plan([fe.RestockRowIn(1, "arms", 0, 100, 100)])            # 5 % of 1000 units = 50 -> budget 17
        assert p_.restock == {1: 17}
        small = {"arms": fe.MarketGroupIn(100.0, Decimal(1), 100)}
        p_ = self._plan([fe.RestockRowIn(1, "arms", 0, 100, 100)], market=small)   # 5 units
        assert p_.restock == {1: 5} and p_.restock_spent == 250

    def test_take_cap_shared_by_rows_of_a_group_and_units_by_value(self):
        small = {"arms": fe.MarketGroupIn(100.0, Decimal(1), 100)}            # 5 units for the whole group
        rows = [fe.RestockRowIn(1, "arms", 0, 3, 100), fe.RestockRowIn(2, "arms", 0, 10, 50)]
        p_ = self._plan(rows, market=small)
        # sword: 3 x 1 unit; shield (price 50 = 0.5 unit, wholesale 25): the remaining 2 units -> 4
        assert p_.restock == {1: 3, 2: 4} and p_.restock_spent == 3 * 50 + 4 * 25
        assert p_.stock_delta == {"arms": -5.0}

    def test_price_mult_and_need(self):
        market = {"arms": fe.MarketGroupIn(1000.0, Decimal("1.5"), 100)}
        p_ = self._plan([fe.RestockRowIn(1, "arms", 8, 10, 100)], market=market)
        assert p_.restock == {1: 2} and p_.restock_spent == 2 * 75

    def test_skipped_rows(self):
        rows = [fe.RestockRowIn(1, "food", 0, 10, 100), fe.RestockRowIn(2, "arms", 10, 10, 100),
                fe.RestockRowIn(3, "arms", 0, 10, 0)]
        zero_base = {"arms": fe.MarketGroupIn(1000.0, Decimal(1), 0)}
        assert self._plan(rows).restock == {3: 10}                  # price 0 -> group base 100
        assert self._plan(rows, market=zero_base).restock == {}     # unknown group base -> cannot trade

    def test_poor_faction_buys_nothing(self):
        p_ = self._plan([fe.RestockRowIn(1, "arms", 0, 10, 100)], balance=1500)
        assert p_.restock == {} and p_.restock_spent == 0

    def test_restock_leg_pays_the_purse(self):
        p_ = self._plan([fe.RestockRowIn(1, "arms", 0, 2, 100)])
        restock_legs = [l for l in p_.legs if l.src.kind == core.KIND_FACTION_TREASURY
                        and l.dst.kind == core.KIND_POPULATION_PURSE]
        assert sum(l.amount for l in restock_legs) == p_.restock_spent == 100


class TestPlannerInvariants:

    def test_inputs_are_not_mutated(self):
        debts = [fe.DebtIn(1, 1, 50)]
        rows = [fe.RestockRowIn(1, "arms", 0, 5, 100)]
        market = {"arms": fe.MarketGroupIn(1000.0, Decimal(1), 100)}
        plan(100, p=params(norm_per_member=1, qm_budget_share=1), balance=10_000, debts=debts, restock=rows,
             market=market)
        assert debts == [fe.DebtIn(1, 1, 50)] and rows == [fe.RestockRowIn(1, "arms", 0, 5, 100)]
        assert market["arms"].stock == 1000.0

    def test_nothing_to_do_no_legs(self):
        p_ = plan(0, p=params(), balance=0)
        assert p_.legs == [] and p_.members_after == 10     # clamped up to members_min

    def test_random_sweep_money_invariants(self):
        rnd = random.Random(20261106)
        kinds = list(fe.PROFILE_KINDS)
        for _ in range(1500):
            p_ = params(norm_per_member=rnd.randint(1, 60), dues_per_member=Decimal(rnd.randint(0, 300)) / 100,
                        wage_per_member=Decimal(rnd.randint(0, 300)) / 100, profile_kind=rnd.choice(kinds),
                        profile_per_member=Decimal(rnd.randint(0, 200)) / 100,
                        profile_rate=Decimal(rnd.randint(0, 200)) / 1000,
                        qm_budget_share=Decimal(rnd.randint(0, 100)) / 100)
            members = rnd.randint(0, 3000)
            lo = rnd.randint(0, 50)
            hi = rnd.randint(lo, 5000)
            debts = [fe.DebtIn(i, rnd.randint(1, 4), rnd.randint(0, 3000)) for i in range(rnd.randint(0, 4))]
            stock = float(rnd.randint(0, 2000))
            market = {"arms": fe.MarketGroupIn(stock, Decimal(rnd.randint(50, 200)) / 100, 100)}
            rows = [fe.RestockRowIn(i, "arms", rnd.randint(0, 20), rnd.randint(0, 40), rnd.choice([0, 50, 100, 300]))
                    for i in range(rnd.randint(0, 3))]
            purse, treasury, bal = rnd.randint(-100, 50_000), rnd.randint(-5000, 90_000), rnd.randint(0, 200_000)
            out = plan(members, p=p_, purse=purse, region_treasury=treasury, balance=bal,
                       purse_budget=rnd.randint(0, 3000), treasury_budget=rnd.randint(0, 3000),
                       last_income=rnd.randint(-10, 90_000), debts=debts, restock=rows, market=market,
                       carry=Decimal(rnd.randint(-9999, 9999)) / 10000, lo=lo, hi=hi)
            assert out.balance_after >= 0
            assert out.balance_after == bal + net_faction(out)
            assert out.dues + out.profile_purse <= max(0, purse)
            assert out.profile_treasury <= max(0, treasury)
            assert 0 <= out.wages_paid <= out.wages_due
            remaining = {d.debt_id: d.remaining for d in debts}
            assert all(0 < v <= remaining[k] for k, v in out.debts.items())
            assert sum(out.payouts.values()) == out.debts_paid
            assert lo <= out.members_after <= hi or (members == 0 and out.members_after == lo)
            assert -1 < out.carry_after < 1
            assert all(leg.amount > 0 for leg in out.legs)
            assert -out.stock_delta.get("arms", 0.0) <= stock * S.qm_take_share_pct / 100 + 1e-6
            for row in rows:
                assert row.stock + out.restock.get(row.qm_item_id, 0) <= max(row.target, row.stock)


# ============================================================================================ donations / qm price


class TestDonationPoints:

    @pytest.mark.parametrize("before,marks,per,cap,pts,expected", [
        (0, 25, 10, 50, 0, (2, 2)),
        (25, 900, 10, 50, 2, (48, 50)),           # capped at 50
        (925, 500, 10, 50, 50, (0, 50)),          # above the cap: nothing
        (5, 5, 10, 50, 0, (1, 1)),                # fractions carry within the day
        (0, 9, 10, 50, 0, (0, 0)),
        (0, 1000, 10, 0, 0, (0, 0)),              # cap 0 = donations give no points
        (0, 7, 1, 50, 0, (7, 7)),
        (0, 1_000_000, 10000, 100000, 0, (100, 100)),
    ])
    def test_points(self, before, marks, per, cap, pts, expected):
        assert fe.donation_points(before, marks, per, cap, pts) == expected


class TestQmPrice:

    def test_discount(self):
        assert fe.qm_unit_price(100, 15) == 85
        assert fe.qm_unit_price(99, 10) == 89
        assert fe.qm_total(99, 10, 3) == 267
        assert fe.qm_unit_price(100, 0) == fe.qm_unit_price(100, None) == 100

    def test_never_below_one_and_discount_clamped(self):
        assert fe.qm_unit_price(1, 50) == 1
        assert fe.qm_unit_price(100, 80) == 50
        assert fe.qm_unit_price(100, -5) == 100

    def test_rank_gate(self):
        assert fe.rank_allows(None, None) is True
        assert fe.rank_allows(3, None) is True
        assert fe.rank_allows(None, 1) is False
        assert fe.rank_allows(2, 1) is True and fe.rank_allows(2, 2) is True
        assert fe.rank_allows(1, 2) is False
