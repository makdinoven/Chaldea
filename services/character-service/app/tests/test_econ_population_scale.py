"""FEAT-186 B1: lore population / ``population_scale`` in the simulation, the param bounds, migration 032.

Acceptance: a region with lore population N at the default scale 100 ticks exactly like the pre-FEAT-186 sim did
with population N / 100. Migration 032 only touches templates (prod regions already hold lore numbers).
"""

import importlib.util
import os
from dataclasses import asdict, replace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, text

import econ_sim as S
from schemas import ECON_MAX_POPULATION, ECON_SIM_PARAM_BOUNDS, EconRegionUpdateRequest, EconSimParamsIn

VERSIONS = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _load(filename, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(VERSIONS, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig028 = _load("028_econ_living_regions.py", "migration_028_for_scale")
mig032 = _load("032_econ_population_scale.py", "migration_032_for_scale")

GROUPS = {
    code: S.GroupDef(code=code, name=name, base_price=base, norm_per_1000=norm, norm_days=days,
                     prosperity_elasticity=pe, price_elasticity=pr, is_food=bool(food),
                     inputs=dict(mig028.INPUTS.get(code, [])))
    for code, name, base, norm, days, pe, pr, food in mig028.GROUPS
}
TEMPLATES = {t[0]: t for t in mig028.TEMPLATES}
OLD_WORLD = S.SimParams(population_scale=1)       # before FEAT-186: the stored number was the simulated one


# --------------------------------------------------------------------------------------------- helper

@pytest.mark.parametrize("population, scale, expected", [
    (4_000_000, 100, 40_000.0), (100_000, 100, 1000.0), (2_500_000, 100, 25_000.0), (50, 100, 0.5),
    (0, 100, 0.0), (-10, 100, 0.0), (None, 100, 0.0), (3000, 1, 3000.0), (12345, 0, 12345.0), (12345, -5, 12345.0),
])
def test_sim_population(population, scale, expected):
    assert S.sim_population(population, S.SimParams(population_scale=scale)) == expected


def test_default_scale_is_100_and_from_mapping_keeps_int():
    assert S.DEFAULT_PARAMS.population_scale == 100
    assert S.sim_population(4_000_000) == 40_000.0
    params = S.SimParams.from_mapping({"population_scale": "250"})
    assert params.population_scale == 250 and isinstance(params.population_scale, int)
    assert S.SimParams.from_mapping({"dt": 0.25}).population_scale == 100       # old stored JSON -> default


# --------------------------------------------------------------------------------------------- equivalence

def _run(region, goods, params, ticks, purse, treasury=0):
    results = []
    for _ in range(ticks):
        r = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=treasury, grant=0,
                              country_tax_rate=0.1, params=params)
        results.append(r)
        region, goods, purse, treasury = r.region, r.goods, r.purse_after, r.treasury_after
    return results


def _comparable(result):
    data = asdict(result)
    data["region"].pop("population")     # the only field that differs: the lore number itself
    return data


@pytest.mark.parametrize("code", list(TEMPLATES))
def test_lore_population_at_scale_100_ticks_like_old_sim(code):
    pop = TEMPLATES[code][5]
    tgoods = {g: (prod, cmult) for g, prod, cmult in mig028.template_goods(code)}
    goods = S.starting_goods(GROUPS, tgoods, pop)
    purse = S.starting_purse(GROUPS, goods, pop)
    old = _run(S.RegionState(population=pop, tax_rate=TEMPLATES[code][6]), goods, OLD_WORLD, 40, purse)
    lore = S.RegionState(population=pop * mig032.POPULATION_FACTOR, tax_rate=TEMPLATES[code][6])
    new = _run(lore, goods, S.DEFAULT_PARAMS, 40, purse)
    assert [_comparable(r) for r in new] == [_comparable(r) for r in old]       # exact, not approx
    assert new[-1].region.population == pop * 100


def test_starting_purse_and_norms_match_old_world():
    pop = TEMPLATES["capital"][5]
    lore = pop * 100
    tgoods = {g: (prod, cmult) for g, prod, cmult in mig028.template_goods("capital")}
    old_goods = S.starting_goods(GROUPS, tgoods, pop)
    new_goods = S.starting_goods(GROUPS, tgoods, S.sim_population(lore))
    assert {c: g.norm_stock for c, g in new_goods.items()} == {c: g.norm_stock for c, g in old_goods.items()}
    assert S.starting_purse(GROUPS, new_goods, S.sim_population(lore)) == S.starting_purse(GROUPS, old_goods, pop)


def test_country_grants_use_lore_proportions():
    old = S.country_grants(100_000, {1: 1000, 2: 3000, 3: 2500})
    assert S.country_grants(100_000, {1: 100_000, 2: 300_000, 3: 250_000}) == old


def test_scale_changes_the_economy_size():
    pop = TEMPLATES["port"][5]
    tgoods = {g: (prod, cmult) for g, prod, cmult in mig028.template_goods("port")}
    goods = S.starting_goods(GROUPS, tgoods, pop)
    region = S.RegionState(population=pop * 100, tax_rate=0.1)
    at_100 = S.simulate_region(region, goods, GROUPS, purse=10**9, treasury=0, params=S.SimParams())
    at_200 = S.simulate_region(region, goods, GROUPS, purse=10**9, treasury=0,
                               params=S.SimParams(population_scale=200))
    assert at_200.goods["food"].last_produced == pytest.approx(at_100.goods["food"].last_produced / 2)


def test_tiny_region_below_scale_is_finite():
    tgoods = {g: (prod, cmult) for g, prod, cmult in mig028.template_goods("rural")}
    goods = S.starting_goods(GROUPS, tgoods, S.sim_population(50))      # 0.5 simulated inhabitants
    r = S.simulate_region(S.RegionState(population=50, tax_rate=0.06), goods, GROUPS, purse=10, treasury=0)
    assert 0 < r.goods["food"].last_produced < 1
    assert 0 <= r.region.stability <= 100 and r.purse_after >= 0


# --------------------------------------------------------------------------------------------- texts

def test_default_noun_is_region():
    assert S.food_label("fed") == "Регион сыт"
    assert S.prosperity_label("modest") == "Скромный регион"
    region = S.RegionState(population=100_000, tax_rate=0.1)
    tgoods = {g: (prod, cmult) for g, prod, cmult in mig028.template_goods("rural")}
    goods = S.starting_goods(GROUPS, tgoods, 1000)
    card = S.region_card(region, goods, GROUPS, treasury=0)
    assert card["food"]["label"] == "Регион сыт"


# --------------------------------------------------------------------------------------------- schemas

def test_population_scale_bounds():
    assert ECON_SIM_PARAM_BOUNDS["population_scale"] == (1, 10_000)
    assert EconSimParamsIn(population_scale=1).population_scale == 1
    assert EconSimParamsIn(population_scale=10_000).population_scale == 10_000
    for bad in (0, 10_001, 1.5, "много", True):
        with pytest.raises(ValidationError):
            EconSimParamsIn(population_scale=bad)


def test_lore_population_bounds():
    for ok in (4_000_000, ECON_MAX_POPULATION):
        assert EconRegionUpdateRequest(population=ok, tax_rate=0.1).population == ok
    with pytest.raises(ValidationError):
        EconRegionUpdateRequest(population=ECON_MAX_POPULATION + 1, tax_rate=0.1)
    assert ECON_MAX_POPULATION < 2 ** 31                                       # econ_regions.population INT


# --------------------------------------------------------------------------------------------- migration 032

DDL = (
    "CREATE TABLE econ_region_templates (code VARCHAR(32) PRIMARY KEY, name VARCHAR(100), description VARCHAR(500), "
    "settlement_noun VARCHAR(50), noun_gender VARCHAR(1), default_population INTEGER)",
    "CREATE TABLE econ_regions (region_id INTEGER PRIMARY KEY, population INTEGER)",
    "CREATE TABLE econ_region_history (id INTEGER PRIMARY KEY, population INTEGER)",
)


@pytest.fixture
def mig_engine():
    engine = create_engine("sqlite://")

    with engine.begin() as conn:
        for ddl in DDL:
            conn.execute(text(ddl))
        for t in mig028.TEMPLATES:
            conn.execute(text("INSERT INTO econ_region_templates VALUES (:c, :n, :d, :s, :g, :p)"),
                         {"c": t[0], "n": t[1], "d": t[2], "s": t[3], "g": t[4], "p": t[5]})
        # an admin already edited the port template's name, noun and population: those fields are kept
        conn.execute(text("UPDATE econ_region_templates SET name = 'Гавань', settlement_noun = 'Гавань', "
                          "noun_gender = 'f', default_population = 150000 WHERE code = 'port'"))
        # regions / history already hold lore numbers (prod): the migration does not touch them
        conn.execute(text("INSERT INTO econ_regions VALUES (1, 4000000), (2, 0), (3, 120000)"))
        conn.execute(text("INSERT INTO econ_region_history VALUES (1, 4000000)"))
    yield engine
    engine.dispose()


def _migrate(engine, step):
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mig032, step)()


def _templates(engine):
    with engine.connect() as conn:
        return {r[0]: tuple(r[1:]) for r in conn.execute(text(
            "SELECT code, name, description, settlement_noun, noun_gender, default_population "
            "FROM econ_region_templates")).fetchall()}


def _pops(engine):
    with engine.connect() as conn:
        return ([r[0] for r in conn.execute(text("SELECT population FROM econ_regions ORDER BY region_id"))],
                [r[0] for r in conn.execute(text("SELECT population FROM econ_region_history"))])


def test_migration_032_revision_chain():
    assert mig032.revision == "032_econ_population_scale" and len(mig032.revision) <= 32
    assert mig032.down_revision == "031_econ_banks"
    assert set(mig032.TEMPLATE_TEXTS) == set(TEMPLATES)
    for code, (old, _new) in mig032.TEMPLATE_TEXTS.items():
        assert old == TEMPLATES[code][1:5]                                       # 032 "old" == 028 seed
    assert mig032.DEFAULT_POPULATIONS == {code: t[5] for code, t in TEMPLATES.items()}


def test_migration_032_upgrade_and_downgrade(mig_engine):
    before = _templates(mig_engine)
    _migrate(mig_engine, "upgrade")
    after = _templates(mig_engine)
    assert _pops(mig_engine) == ([4_000_000, 0, 120_000], [4_000_000])           # untouched
    assert after["capital"] == ("Столичный регион", mig032.TEMPLATE_TEXTS["capital"][1][1], "Регион", "m", 2_500_000)
    assert after["fortress"][:1] + after["fortress"][2:] == ("Пограничный регион", "Регион", "m", 300_000)
    assert after["port"][0] == "Гавань" and after["port"][2:5] == ("Гавань", "f", 150000)   # admin edits kept ...
    assert after["port"][1] == mig032.TEMPLATE_TEXTS["port"][1][1]                    # ... untouched field rewritten
    for code, row in after.items():
        if code != "port":
            assert row[2:4] == ("Регион", "m") and row[0].endswith("регион")
        assert "город" not in (row[1] or "").lower()
    _migrate(mig_engine, "downgrade")
    assert _templates(mig_engine) == before
    assert _pops(mig_engine) == ([4_000_000, 0, 120_000], [4_000_000])


# --------------------------------------------------------------------------------------------- residents' bank rescale

import econ_bank as B  # noqa: E402


def test_resident_rescale_steady_targets_and_payout():
    p = S.DEFAULT_PARAMS        # deposit share 0.2 -> D* = P* x 0.25; loan share 0.1 -> L* = P* x 0.1
    r = B.resident_rescale(purse=1_000_000, bank_balance=10**9, deposits=500_000, loans=200_000, purse_target=10_000,
                           enabled=True, params=p)
    assert (r.deposits_target, r.loans_target) == (2500, 1000)
    assert r.deposits_out == 497_500 and r.deposits_after == 2500
    assert r.loans_repaid == 199_000 and r.loans_after == 1000
    assert r.net_to_purse == 497_500 - 199_000


def test_resident_rescale_is_idempotent_at_or_below_target():
    r = B.resident_rescale(purse=10_000, bank_balance=50_000, deposits=2500, loans=1000, purse_target=10_000,
                           enabled=True)
    assert (r.deposits_out, r.loans_repaid, r.net_to_purse) == (0, 0, 0)
    r = B.resident_rescale(purse=10_000, bank_balance=50_000, deposits=10, loans=0, purse_target=10_000, enabled=True)
    assert (r.deposits_out, r.loans_repaid) == (0, 0)                     # below target: never pushes money in


def test_resident_rescale_bank_short_of_money_pays_what_it_has():
    r = B.resident_rescale(purse=0, bank_balance=1000, deposits=500_000, loans=0, purse_target=10_000, enabled=True)
    assert r.deposits_out == 1000 and r.deposits_after == 499_000          # the rest stays owed, bank at 0
    r = B.resident_rescale(purse=0, bank_balance=-50, deposits=500_000, loans=0, purse_target=10_000, enabled=True)
    assert r.deposits_out == 0


def test_resident_rescale_sets_deposits_off_against_loans():
    # excess deposits 10 150 vs excess loans 49 900: 10 150 set off without cash, the rest repaid from the purse (100)
    r = B.resident_rescale(purse=100, bank_balance=0, deposits=10_400, loans=50_000, purse_target=1000, enabled=True)
    assert r.deposits_out == 10_150 and r.deposits_after == 250
    assert r.loans_repaid == 10_250 and r.loans_after == 39_750
    assert r.net_to_purse == -100                                            # the purse never goes below 0
    # the other way round: the bank pays only the cash part beyond the set-off, bounded by its balance
    r = B.resident_rescale(purse=0, bank_balance=300, deposits=50_250, loans=10_100, purse_target=1000, enabled=True)
    assert r.loans_repaid == 10_000 and r.deposits_out == 10_300 and r.net_to_purse == 300


def test_resident_rescale_disabled_bank_winds_down():
    r = B.resident_rescale(purse=0, bank_balance=10**6, deposits=3000, loans=2000, purse_target=10_000,
                           enabled=False)
    assert (r.deposits_target, r.loans_target, r.deposits_after, r.loans_after) == (0, 0, 0, 0)
    assert r.net_to_purse == 1000
