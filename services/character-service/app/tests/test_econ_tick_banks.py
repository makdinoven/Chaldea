"""FEAT-184 B5: bank tick passes (orphan purge, bank pass, collection pass) and the character deletion hook on SQLite.

World:
    country 1; region 10 «Ост» <- location 100; region 20 «Пашни» <- 200; region 30 «Глушь» (no location, deleted in
    the orphan tests); players 1 «Альфа» @100, 2 «Бета» @200; banks 10 / 20 / 30 enabled with own money.
Regions are not simulated (no ``econ_regions`` rows) unless a test adds one, so the region loop of ``run_tick`` is
empty and the residents stay at 0 there.
"""

import dataclasses
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import crud
import econ_bank
import econ_core as core
import econ_ledger
import econ_sim
import econ_tick
import economy_bank_crud as bank_crud
import economy_sim_crud
import models

SOURCE = "character-service"
ALPHA, BETA = 1, 2
T0 = datetime(2026, 10, 28, 0, 5)
CAPITAL = {10: 50_000, 20: 20_000, 30: 700}
PARAMS = econ_sim.DEFAULT_PARAMS


# --------------------------------------------------------------------------------------------- fixtures

def _emit(db, dst, amount):
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                               legs=[core.Leg(core.AccountRef.emission(), dst, amount)])


def _build(engine, wallets=(200_000, 1_000)):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд')"))
    db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Ост', 1), (20, 'Пашни', 1), "
                    "(30, 'Глушь', 1)"))
    db.execute(text("INSERT INTO Locations (id, name, region_id) VALUES (100, 'Рынок', 10), (200, 'Село', 20)"))
    with econ_ledger.allow_direct_balance_write(db):
        for cid, name, user, loc in ((ALPHA, "Альфа", 7, 100), (BETA, "Бета", 8, 200)):
            db.add(models.Character(id=cid, name=name, user_id=user, id_subrace=1, id_class=1, id_race=1,
                                    appearance="-", avatar="-", is_npc=False, current_location_id=loc, level=2,
                                    currency_balance=0))
        db.flush()
    for region_id in (10, 20, 30):
        db.add(models.EconBank(region_id=region_id, is_enabled=True))
    db.flush()
    for cid, amount in zip((ALPHA, BETA), wallets):
        if amount:
            _emit(db, core.AccountRef.character(cid), amount)
    for region_id, amount in CAPITAL.items():
        _emit(db, core.AccountRef.region(region_id), amount)
        econ_ledger.post_operation(db, op_type=core.OP_BANK_CAPITAL, source_service=SOURCE, apply_tax=False,
                                   legs=[core.Leg(core.AccountRef.region(region_id), core.AccountRef.bank(region_id),
                                                  amount)])
    db.commit()
    db.close()
    return factory


def _new_engine(wallets=(200_000, 1_000)):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=eng)
    core.invalidate_settings_cache()
    eng.factory = _build(eng, wallets)
    return eng


@pytest.fixture
def engine():
    eng = _new_engine()
    yield eng
    core.invalidate_settings_cache()
    eng.dispose()


@pytest.fixture
def poor_engine():
    """Альфа has 1 500 in the wallet."""
    eng = _new_engine((1_500, 1_000))
    yield eng
    core.invalidate_settings_cache()
    eng.dispose()


def _q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _sql(engine, sql, **params):
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def _acc(engine, kind, ref):
    return int(_q(engine, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind = :k AND ref_id = :r",
                  k=kind, r=ref) or 0)


def _wallet(engine, cid):
    return int(_q(engine, "SELECT currency_balance FROM characters WHERE id = :i", i=cid))


def _assert_invariant(engine):
    accounts = int(_q(engine, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character'"))
    characters = int(_q(engine, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters"))
    assert accounts + characters == 0
    assert _q(engine, "SELECT COUNT(*) FROM characters WHERE currency_balance < 0") == 0
    for region_id in (10, 20, 30):
        rows = int(_q(engine, "SELECT COALESCE(SUM(amount + interest_accrued), 0) FROM bank_deposits "
                              "WHERE region_id = :r AND status = 'open'", r=region_id))
        assert _acc(engine, "bank_deposits", region_id) == rows, region_id
        assert _acc(engine, "bank", region_id) >= 0


def _deposit(engine, cid, region_id, amount, *, kind="demand", base=None, accrued_at=None, rate=None,
             term=None, matures_at=None, interest_accrued=0):
    """An open deposit row + its money ``C -> V`` (interest_accrued is emitted into the vault for the test)."""
    db = engine.factory()
    try:
        row = models.BankDeposit(
            character_id=cid, region_id=region_id, kind=kind, status="open", amount=amount,
            interest_base=amount if base is None else base, interest_accrued=interest_accrued, interest_total=0,
            interest_carry=0, rate_day=rate, term_days=term, opened_at=T0 - timedelta(days=30),
            matures_at=matures_at, accrued_at=accrued_at or (T0 - timedelta(hours=6)),
            demand_owner_id=cid if kind == "demand" else None)
        db.add(row)
        db.flush()
        econ_ledger.post_operation(db, op_type=core.OP_BANK_DEPOSIT, source_service=SOURCE,
                                   legs=[core.Leg(core.AccountRef.character(cid),
                                                  core.AccountRef.bank_deposits(region_id), amount)])
        if interest_accrued:
            econ_ledger.post_operation(db, op_type=core.OP_BANK_TICK, source_service=SOURCE, apply_tax=False,
                                       legs=[core.Leg(core.AccountRef.bank(region_id),
                                                      core.AccountRef.bank_deposits(region_id), interest_accrued,
                                                      core.LEG_INTEREST)])
        db.commit()
        return int(row.id)
    finally:
        db.close()


def _loan(engine, cid, region_id, principal, *, due_at, accrued_at=None, issue=True):
    """An open loan row; ``issue`` moves the principal ``B -> C`` like a real issue."""
    db = engine.factory()
    try:
        row = models.BankLoan(
            character_id=cid, region_id=region_id, status="active", principal=principal, debt=principal,
            rate_day=Decimal("0.005"), penalty_rate_day=Decimal("0.01"), term_days=7,
            issued_at=due_at - timedelta(days=7), due_at=due_at, accrued_at=accrued_at or due_at,
            active_character_id=cid)
        db.add(row)
        db.flush()
        if issue:
            econ_ledger.post_operation(db, op_type=core.OP_LOAN_ISSUE, source_service=SOURCE,
                                       legs=[core.Leg(core.AccountRef.bank(region_id),
                                                      core.AccountRef.character(cid), principal)])
        db.commit()
        return int(row.id)
    finally:
        db.close()


def _run(engine, now):
    return econ_tick.run_tick(engine.factory, trigger=econ_tick.TRIGGER_MANUAL, now=now)


def _ops(engine, op_type):
    return int(_q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = :t", t=op_type))


def _legs(engine, op_id):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT s.kind, s.ref_id, d.kind, d.ref_id, p.amount, p.leg_type FROM econ_postings p "
            "JOIN econ_accounts s ON s.id = p.from_account_id JOIN econ_accounts d ON d.id = p.to_account_id "
            "WHERE p.operation_id = :o ORDER BY p.id"), {"o": op_id}).fetchall()
    return [tuple(r) for r in rows]


def _dep(engine, dep_id, col):
    return _q(engine, f"SELECT {col} FROM bank_deposits WHERE id = :i", i=dep_id)


def _loan_col(engine, loan_id, col):
    return _q(engine, f"SELECT {col} FROM bank_loans WHERE id = :i", i=loan_id)


# --------------------------------------------------------------------------------------------- bank pass

def test_bank_pass_pays_interest_once_per_bank_and_rerun_is_noop(engine):
    dep = _deposit(engine, ALPHA, 10, 100_000)
    bank_before = _acc(engine, "bank", 10)
    summary = _run(engine, T0)

    assert summary.status == econ_tick.STATUS_DONE
    assert summary.banks_processed == 3 and summary.bank_failures == 0
    assert summary.bank_ops_posted == 1                   # only bank 10 had something to post
    assert summary.bank_interest_paid == 25               # 100 000 × 0.001 × 6 h
    assert _dep(engine, dep, "amount") == 100_025 and _dep(engine, dep, "interest_base") == 100_025
    assert _acc(engine, "bank", 10) == bank_before - 25
    op_id = _q(engine, "SELECT id FROM econ_operations WHERE idempotency_key = :k",
               k=f"bank_tick:{summary.run_id}:b:10")
    assert _legs(engine, op_id) == [("bank", 10, "bank_deposits", 10, 25, "interest")]
    assert _q(engine, "SELECT last_run_id FROM econ_banks WHERE region_id = 10") == summary.run_id
    _assert_invariant(engine)

    # the same run again (resumed run): every bank is skipped by its last_run_id guard
    db = engine.factory()
    try:
        result = bank_crud.tick_bank(db, 10, run_id=summary.run_id, params=PARAMS, clock=lambda: T0)
        db.commit()
    finally:
        db.close()
    assert result.status == bank_crud.TICK_STATUS_ALREADY
    assert _ops(engine, core.OP_BANK_TICK) == 1

    # a second run at the same instant: no time passed, nothing paid, nothing posted
    again = _run(engine, T0)
    assert again.bank_ops_posted == 0 and again.bank_interest_paid == 0
    assert _dep(engine, dep, "amount") == 100_025
    _assert_invariant(engine)


def test_second_run_pays_only_the_elapsed_minutes(engine):
    dep = _deposit(engine, ALPHA, 10, 100_000)
    _run(engine, T0)
    factor = Decimal(str(_q(engine, "SELECT deposit_rate_factor FROM econ_banks WHERE region_id = 10")))
    carry = Decimal(str(_dep(engine, dep, "interest_carry")))
    expected, _ = econ_bank.accrue(100_025, econ_bank.demand_rate(PARAMS, factor), 3600, carry)

    summary = _run(engine, T0 + timedelta(hours=1))
    assert summary.bank_interest_paid == expected
    assert 0 < expected < 25
    assert _dep(engine, dep, "amount") == 100_025 + expected
    _assert_invariant(engine)


def test_matured_term_deposits_convert_or_merge(engine):
    demand = _deposit(engine, ALPHA, 10, 1_000, base=0)
    merged = _deposit(engine, ALPHA, 10, 2_000, kind="term", rate=Decimal("0.002"), term=7,
                      matures_at=T0 - timedelta(hours=1), accrued_at=T0 - timedelta(hours=7), interest_accrued=10)
    converted = _deposit(engine, BETA, 20, 500, kind="term", rate=Decimal("0.002"), term=7,
                         matures_at=T0 - timedelta(hours=1), accrued_at=T0 - timedelta(hours=1))
    _run(engine, T0)

    # 2 000 × 0.002 × 6 h = 1 for the last period up to matures_at, + 10 accrued earlier
    assert _dep(engine, merged, "status") == "closed" and _dep(engine, merged, "amount") == 0
    assert _dep(engine, demand, "amount") == 1_000 + 2_000 + 10 + 1
    assert _dep(engine, converted, "kind") == "demand" and _dep(engine, converted, "status") == "open"
    assert _dep(engine, converted, "demand_owner_id") == BETA and _dep(engine, converted, "rate_day") is None
    assert _dep(engine, converted, "amount") == 500
    _assert_invariant(engine)


def test_residents_move_money_in_a_simulated_region(engine):
    db = engine.factory()
    try:
        db.add(models.EconRegionTemplate(code="capital", name="Столица", description="-", settlement_noun="город",
                                         noun_gender="m", default_population=1000, tax_rate=Decimal("0.1"),
                                         sort_order=1))
        db.flush()
        db.add(models.EconRegion(region_id=10, template_code="capital", population=1000, tax_rate=Decimal("0.1")))
        _emit(db, core.AccountRef.purse(10), 100_000)
        db.commit()
        result = bank_crud.tick_bank(db, 10, run_id=999, params=PARAMS, clock=lambda: T0)
        db.commit()
    finally:
        db.close()
    assert result.status == bank_crud.TICK_STATUS_DONE and result.posted
    deposits = _q(engine, "SELECT resident_deposits FROM econ_banks WHERE region_id = 10")
    loans = _q(engine, "SELECT resident_loans FROM econ_banks WHERE region_id = 10")
    assert deposits > 0 and loans > 0
    assert result.stats["resident_in"] == deposits and result.stats["resident_issued"] == loans
    assert _acc(engine, "population_purse", 10) == 100_000 - deposits + loans
    assert _q(engine, "SELECT last_stats FROM econ_banks WHERE region_id = 10") is not None
    _assert_invariant(engine)


def test_failing_bank_is_isolated_and_reported(engine, monkeypatch):
    dep10 = _deposit(engine, ALPHA, 10, 100_000)
    dep20 = _deposit(engine, BETA, 20, 1_000)
    original = econ_bank.bank_step

    def broken(inp):
        if inp.region_id == 10:
            raise RuntimeError("boom")
        return original(inp)

    monkeypatch.setattr(econ_bank, "bank_step", broken)
    summary = _run(engine, T0)
    assert summary.bank_failures == 1 and summary.bank_failed_region_ids == [10]
    assert summary.banks_processed == 2
    assert _dep(engine, dep10, "amount") == 100_000                       # rolled back
    assert _q(engine, "SELECT last_run_id FROM econ_banks WHERE region_id = 10") is None
    assert _dep(engine, dep20, "amount") == 1_000                         # 1 000 × 0.001 / 4 = 0.25 -> carry
    assert _q(engine, "SELECT last_run_id FROM econ_banks WHERE region_id = 20") == summary.run_id

    db = engine.factory()
    try:
        run = db.get(models.EconTickRun, summary.run_id)
        assert econ_tick.BANK_ERROR_PREFIX + "10" in run.error
        listed = economy_sim_crud._run_dict(run, db)
    finally:
        db.close()
    assert listed["bank_failures"] == 1 and listed["bank_ops_posted"] == 0 and listed["loans_collected"] == 0

    monkeypatch.setattr(econ_bank, "bank_step", original)                 # retried next run, nothing lost
    later = _run(engine, T0 + timedelta(hours=6))
    assert later.bank_failures == 0
    assert _dep(engine, dep10, "amount") > 100_000
    _assert_invariant(engine)


def test_runs_list_counts_bank_and_collection_ops(engine):
    _deposit(engine, ALPHA, 10, 100_000)
    _loan(engine, BETA, 20, 500, due_at=T0 - timedelta(days=1))
    summary = _run(engine, T0)
    db = engine.factory()
    try:
        listed = economy_sim_crud._run_dict(db.get(models.EconTickRun, summary.run_id), db)
    finally:
        db.close()
    assert listed["bank_ops_posted"] == summary.bank_ops_posted == 1
    assert listed["loans_collected"] == summary.loans_collected == 1
    assert listed["bank_failures"] == 0


def test_missing_bank_tables_do_not_stop_the_run():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=eng)
    for model in (models.BankLoan, models.BankDeposit, models.EconBank):
        model.__table__.drop(eng)
    core.invalidate_settings_cache()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    try:
        summary = econ_tick.run_tick(factory, trigger=econ_tick.TRIGGER_MANUAL, now=T0)
        assert summary.status == econ_tick.STATUS_DONE
        assert summary.banks_processed == 0 and summary.bank_failures == 0 and summary.banks_closed == 0
    finally:
        core.invalidate_settings_cache()
        eng.dispose()


# --------------------------------------------------------------------------------------------- collection pass

def test_collection_takes_other_bank_deposit_then_wallet_never_negative(poor_engine):
    engine = poor_engine
    dep = _deposit(engine, ALPHA, 10, 500, base=0)
    loan = _loan(engine, ALPHA, 20, 3_000, due_at=T0 - timedelta(days=1), issue=False)   # money spent long ago
    assert _wallet(engine, ALPHA) == 1_000

    summary = _run(engine, T0)
    assert summary.loans_collected == 1 and summary.collected_amount == 1_500 and summary.loans_overdue == 1
    assert _wallet(engine, ALPHA) == 0
    assert _dep(engine, dep, "status") == "closed" and _dep(engine, dep, "amount") == 0
    assert _loan_col(engine, loan, "status") == "overdue"
    assert _loan_col(engine, loan, "collected_total") == 1_500
    accrued = _loan_col(engine, loan, "interest_total") + _loan_col(engine, loan, "penalty_total")
    assert accrued > 0                                                  # a day of interest + penalty
    assert _loan_col(engine, loan, "debt") == 3_000 + accrued - 1_500
    op_id = _q(engine, "SELECT id FROM econ_operations WHERE idempotency_key = :k",
               k=f"loan_collect:{summary.run_id}:l:{loan}")
    assert _legs(engine, op_id) == [("bank_deposits", 10, "bank", 20, 500, "main"),
                                    ("character", ALPHA, "bank", 20, 1_000, "main")]
    _assert_invariant(engine)

    # rerun of the same run: the ledger key guards it
    db = engine.factory()
    try:
        result = bank_crud.collect_loan(db, loan, run_id=summary.run_id, params=PARAMS, clock=lambda: T0)
        db.commit()
    finally:
        db.close()
    assert result.status == bank_crud.TICK_STATUS_ALREADY
    assert _ops(engine, core.OP_LOAN_COLLECT) == 1


def test_collection_closes_the_loan_when_enough(engine):
    term = _deposit(engine, ALPHA, 10, 400, kind="term", rate=Decimal("0.002"), term=7,
                    matures_at=T0 + timedelta(days=3), interest_accrued=7)
    loan = _loan(engine, ALPHA, 20, 1_000, due_at=T0 - timedelta(hours=6))
    wallet_before = _wallet(engine, ALPHA)
    summary = _run(engine, T0)

    debt_total = 1_000 + _loan_col(engine, loan, "interest_total") + _loan_col(engine, loan, "penalty_total")
    assert _loan_col(engine, loan, "status") == "closed" and _loan_col(engine, loan, "debt") == 0
    assert _loan_col(engine, loan, "active_character_id") is None
    assert summary.loans_overdue == 0 and summary.collected_amount == debt_total
    # term deposit: interest first, then the amount; the rest from the wallet
    assert _dep(engine, term, "status") == "closed"
    assert _wallet(engine, ALPHA) == wallet_before - (debt_total - 407)
    _assert_invariant(engine)


def test_loan_not_yet_due_is_not_collected(engine):
    _deposit(engine, ALPHA, 10, 5_000, base=0)
    loan = _loan(engine, ALPHA, 20, 1_000, due_at=T0 + timedelta(days=1), accrued_at=T0 - timedelta(days=1))
    summary = _run(engine, T0)
    assert summary.loans_collected == 0 and _ops(engine, core.OP_LOAN_COLLECT) == 0
    assert _loan_col(engine, loan, "status") == "active"
    assert _loan_col(engine, loan, "debt") == 1_005                     # a day at 0.5 % accrued by the bank pass


# --------------------------------------------------------------------------------------------- orphan purge

def test_orphan_bank_is_closed_once(engine):
    dep = _deposit(engine, ALPHA, 30, 300, base=0)
    loan = _loan(engine, BETA, 30, 200, due_at=T0 + timedelta(days=3), accrued_at=T0 - timedelta(hours=1))
    world_before = _acc(engine, "world_treasury", 0)
    _sql(engine, "DELETE FROM Regions WHERE id = 30")

    summary = _run(engine, T0)
    assert summary.banks_closed == 1
    assert _acc(engine, "bank", 30) == 0
    assert _acc(engine, "world_treasury", 0) == world_before + CAPITAL[30] - 200
    assert _q(engine, "SELECT is_enabled FROM econ_banks WHERE region_id = 30") in (0, False)
    assert _loan_col(engine, loan, "status") == "written_off" and _loan_col(engine, loan, "written_off") == 200
    assert _loan_col(engine, loan, "active_character_id") is None
    assert _dep(engine, dep, "status") == "open" and _acc(engine, "bank_deposits", 30) == 300   # vault stays
    assert _ops(engine, core.OP_TREASURY_CLOSED) == 1

    again = _run(engine, T0 + timedelta(hours=6))
    assert again.banks_closed == 0 and _ops(engine, core.OP_TREASURY_CLOSED) == 1
    assert _dep(engine, dep, "amount") == 300                          # a closed bank pays no interest
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- deletion hook

def test_character_deletion_pays_out_deposits_and_writes_off_the_loan(engine):
    demand = _deposit(engine, ALPHA, 10, 1_000)
    term = _deposit(engine, ALPHA, 30, 500, kind="term", rate=Decimal("0.002"), term=7,
                    matures_at=T0 + timedelta(days=3), interest_accrued=20)
    loan = _loan(engine, ALPHA, 20, 800, due_at=T0 + timedelta(days=3))
    _sql(engine, "DELETE FROM Regions WHERE id = 30")
    wallet = _wallet(engine, ALPHA)
    world_before = _acc(engine, "world_treasury", 0)
    region_before = _acc(engine, "region_treasury", 10)

    db = engine.factory()
    try:
        alpha = db.get(models.Character, ALPHA)
        assert crud.post_character_deletion(db, alpha) == wallet
        db.commit()
    finally:
        db.close()

    op_id = _q(engine, "SELECT id FROM econ_operations WHERE idempotency_key = :k", k=f"character_deleted:c:{ALPHA}")
    legs = _legs(engine, op_id)
    assert ("character", ALPHA, "region_treasury", 10, wallet, "main") in legs
    assert ("bank_deposits", 10, "region_treasury", 10, 1_000, "main") in legs
    assert ("bank_deposits", 30, "world_treasury", 0, 520, "main") in legs
    taxed = sum(r[4] for r in legs if r[5] == "tax")
    assert _acc(engine, "region_treasury", 10) == region_before + wallet + 1_000 - taxed
    assert _acc(engine, "world_treasury", 0) == world_before + 520
    assert _acc(engine, "bank_deposits", 10) == 0 and _acc(engine, "bank_deposits", 30) == 0
    for dep in (demand, term):
        assert _dep(engine, dep, "status") == "closed" and _dep(engine, dep, "amount") == 0
    assert _dep(engine, demand, "demand_owner_id") is None
    assert _loan_col(engine, loan, "status") == "written_off" and _loan_col(engine, loan, "written_off") == 800
    assert _loan_col(engine, loan, "active_character_id") is None
    assert _wallet(engine, ALPHA) == 0
    _assert_invariant(engine)


def test_character_deletion_without_bank_rows_is_unchanged(engine):
    wallet = _wallet(engine, BETA)
    db = engine.factory()
    try:
        assert crud.post_character_deletion(db, db.get(models.Character, BETA)) == wallet
        db.commit()
    finally:
        db.close()
    op_id = _q(engine, "SELECT id FROM econ_operations WHERE idempotency_key = :k", k=f"character_deleted:c:{BETA}")
    assert [r for r in _legs(engine, op_id) if r[5] == "main"] == [("character", BETA, "region_treasury", 20,
                                                                      wallet, "main")]


# --------------------------------------------------------------------------------------------- matured withdraw

def test_matured_term_interest_for_the_last_period(engine):
    dep = _deposit(engine, ALPHA, 10, 100_000, kind="term", rate=Decimal("0.002"), term=7,
                   matures_at=T0 - timedelta(hours=1), accrued_at=T0 - timedelta(hours=7))
    db = engine.factory()
    try:
        row = db.get(models.BankDeposit, dep)
        bank = db.get(models.EconBank, 10)
        assert bank_crud.matured_term_interest(db, row, bank, PARAMS, T0) == 50       # 100 000 × 0.002 × 6 h
        assert bank_crud.matured_term_interest(db, row, bank, PARAMS, T0 - timedelta(hours=2)) == 0  # not matured
        bank.is_enabled = False
        assert bank_crud.matured_term_interest(db, row, bank, PARAMS, T0) == 0        # closed bank pays nothing
        db.rollback()
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- Q3: time weighting

def _factor(engine, region_id=10):
    return Decimal(str(_q(engine, "SELECT deposit_rate_factor FROM econ_banks WHERE region_id = :r", r=region_id)))


def test_back_to_back_manual_runs_do_not_move_the_factor(engine):
    # Deposits but no loans: income 0 -> the factor heads for factor_min (0.2), 0.25 of the gap per 6 h.
    _deposit(engine, ALPHA, 10, 100_000)
    _run(engine, T0)
    assert _factor(engine) == Decimal("0.8")
    for seconds in (10, 20, 30):                                     # «Пересчитать сейчас» clicked again and again
        _run(engine, T0 + timedelta(seconds=seconds))
        assert _factor(engine) == Decimal("0.8"), seconds
    _assert_invariant(engine)


def test_two_half_periods_move_the_factor_like_one_period():
    whole, halves = _new_engine(), _new_engine()
    try:
        for eng in (whole, halves):
            _deposit(eng, ALPHA, 10, 100_000)
            _run(eng, T0)
        _run(whole, T0 + timedelta(hours=6))
        _run(halves, T0 + timedelta(hours=3))
        mid = _factor(halves)
        assert Decimal("0.65") < mid < Decimal("0.8")                # a half period moves part of the way
        _run(halves, T0 + timedelta(hours=6))
        assert _factor(whole) == Decimal("0.65")                     # 0.8 + (0.2 - 0.8) x 0.25
        assert abs(_factor(halves) - _factor(whole)) <= Decimal("0.0002")
        for eng in (whole, halves):
            _assert_invariant(eng)
    finally:
        whole.dispose()
        halves.dispose()


def test_long_downtime_catches_up_the_factor_at_most_one_day_but_pays_all_interest():
    day, ten_days = _new_engine(), _new_engine()
    try:
        deps = {}
        for eng in (day, ten_days):
            deps[id(eng)] = _deposit(eng, ALPHA, 10, 100_000)
            _run(eng, T0)
        first_day = _run(day, T0 + timedelta(days=1))
        first_ten = _run(ten_days, T0 + timedelta(days=10))            # the tick was off / missed 39 slots
        # smoothing is capped at 4 periods: 0.8 + (0.2 - 0.8) x (1 - 0.75^4)
        assert _factor(day) == _factor(ten_days)
        assert _factor(day) == Decimal("0.3898")                   # step 0.41015625 rounded away
        # the interest itself is time-based: nothing is lost over the downtime
        assert first_ten.bank_interest_paid > 9 * first_day.bank_interest_paid
        assert _dep(ten_days, deps[id(ten_days)], "amount") == 100_025 + first_ten.bank_interest_paid
        for eng, summary in ((day, first_day), (ten_days, first_ten)):
            assert summary.bank_ops_posted == 1
            # one bank_tick per bank per run
            assert _q(eng, "SELECT COUNT(*) FROM econ_operations WHERE idempotency_key LIKE :k",
                      k=f"bank_tick:{summary.run_id}:b:%") == 1
            _assert_invariant(eng)
    finally:
        day.dispose()
        ten_days.dispose()


def _simulated_region_10(engine, purse=100_000):
    db = engine.factory()
    try:
        db.add(models.EconRegionTemplate(code="capital", name="Столица", description="-", settlement_noun="город",
                                         noun_gender="m", default_population=1000, tax_rate=Decimal("0.1"),
                                         sort_order=1))
        db.flush()
        db.add(models.EconRegion(region_id=10, template_code="capital", population=1000, tax_rate=Decimal("0.1")))
        _emit(db, core.AccountRef.purse(10), purse)
        db.commit()
    finally:
        db.close()


def _tick_bank(engine, run_id, now, params):
    db = engine.factory()
    try:
        result = bank_crud.tick_bank(db, 10, run_id=run_id, params=params, clock=lambda: now)
        db.commit()
        return result
    finally:
        db.close()


def test_long_downtime_catches_up_the_residents_at_most_one_day():
    # Rates 0 so only the residents move the purse — the gaps are then identical across the engines.
    params = dataclasses.replace(PARAMS, bank_loan_rate_day=0.0, bank_demand_rate_day=0.0)
    gaps = (timedelta(hours=6), timedelta(days=1), timedelta(days=10))
    engines = [_new_engine() for _ in gaps]
    try:
        stats = []
        for gap, eng in zip(gaps, engines):
            _simulated_region_10(eng)
            _tick_bank(eng, 1, T0, params)
            stats.append(_tick_bank(eng, 2, T0 + gap, params).stats)
            _assert_invariant(eng)
        one_period, one_day, ten_days = stats
        assert one_day["resident_in"] == ten_days["resident_in"] > one_period["resident_in"] > 0
        assert one_day["resident_issued"] == ten_days["resident_issued"] > one_period["resident_issued"] > 0
        balances = [(_q(e, "SELECT resident_deposits FROM econ_banks WHERE region_id = 10"),
                     _q(e, "SELECT resident_loans FROM econ_banks WHERE region_id = 10")) for e in engines]
        assert balances[1] == balances[2]
    finally:
        for eng in engines:
            eng.dispose()


# --------------------------------------------------------------------------------------------- Q3: collection

def test_collection_spans_several_banks_including_a_disabled_one(poor_engine):
    engine = poor_engine                                                # Альфа: 1 500 in the wallet
    d10 = _deposit(engine, ALPHA, 10, 300, base=0)
    d20 = _deposit(engine, ALPHA, 20, 100, base=0)                      # a deposit in the lender bank itself
    t30 = _deposit(engine, ALPHA, 30, 200, kind="term", rate=Decimal("0.002"), term=14,
                   matures_at=T0 + timedelta(days=5), interest_accrued=15)
    _sql(engine, "UPDATE econ_banks SET is_enabled = 0 WHERE region_id = 30")   # flag off: still collected
    loan = _loan(engine, ALPHA, 20, 5_000, due_at=T0 - timedelta(days=2), issue=False)
    assert _wallet(engine, ALPHA) == 900
    lender_before = _acc(engine, "bank", 20)

    summary = _run(engine, T0)
    assert summary.collected_amount == 300 + 100 + 215 + 900 and summary.loans_overdue == 1
    assert _wallet(engine, ALPHA) == 0
    for dep in (d10, d20, t30):
        assert _dep(engine, dep, "status") == "closed" and _dep(engine, dep, "amount") == 0
    assert _dep(engine, t30, "interest_accrued") == 0
    op_id = _q(engine, "SELECT id FROM econ_operations WHERE idempotency_key = :k",
               k=f"loan_collect:{summary.run_id}:l:{loan}")
    assert _legs(engine, op_id) == [("bank_deposits", 10, "bank", 20, 300, "main"),
                                    ("bank_deposits", 20, "bank", 20, 100, "main"),
                                    ("bank_deposits", 30, "bank", 20, 215, "main"),
                                    ("character", ALPHA, "bank", 20, 900, "main")]
    assert _acc(engine, "bank", 20) == lender_before + 1_515
    assert _loan_col(engine, loan, "status") == "overdue" and _loan_col(engine, loan, "debt") > 5_000 - 1_515
    _assert_invariant(engine)

    # next run: nothing left anywhere -> only the accrual, no second operation, the wallet never goes negative
    later = _run(engine, T0 + timedelta(hours=6))
    assert later.loans_collected == 0 and later.collected_amount == 0 and later.loans_overdue == 1
    assert _ops(engine, core.OP_LOAN_COLLECT) == 1
    assert _wallet(engine, ALPHA) == 0
    _assert_invariant(engine)


def test_collection_with_an_empty_wallet_only_marks_the_loan_overdue():
    engine = _new_engine((200_000, 0))                                  # Бета has nothing
    try:
        loan = _loan(engine, BETA, 20, 400, due_at=T0 - timedelta(days=1), accrued_at=T0 - timedelta(days=2),
                     issue=False)
        summary = _run(engine, T0)
        assert summary.loans_collected == 0 and summary.loans_overdue == 1
        assert _ops(engine, core.OP_LOAN_COLLECT) == 0
        assert _loan_col(engine, loan, "status") == "overdue" and _loan_col(engine, loan, "debt") > 400
        assert _loan_col(engine, loan, "active_character_id") == BETA
        assert _wallet(engine, BETA) == 0
        _assert_invariant(engine)
    finally:
        engine.dispose()


def test_written_off_loan_is_never_collected(engine):
    loan = _loan(engine, ALPHA, 20, 1_000, due_at=T0 - timedelta(days=1))
    db = engine.factory()
    try:
        row = db.get(models.BankLoan, loan)
        assert bank_crud.write_off_loan_row(row, T0, "тест", user_id=7) == 1_000
        db.commit()
    finally:
        db.close()
    wallet = _wallet(engine, ALPHA)
    summary = _run(engine, T0)
    assert summary.loans_collected == 0 and summary.loans_overdue == 0
    assert _wallet(engine, ALPHA) == wallet and _loan_col(engine, loan, "debt") == 0
    assert _loan_col(engine, loan, "status") == "written_off"
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- Q3: deletion + orphans

def test_deletion_with_empty_wallet_pays_out_three_banks_then_the_orphan_is_purged(engine):
    # Бета puts the whole wallet into three banks; region 30 is deleted before the character.
    d10 = _deposit(engine, BETA, 10, 400)
    d20 = _deposit(engine, BETA, 20, 300, kind="term", rate=Decimal("0.002"), term=7,
                   matures_at=T0 + timedelta(days=3), interest_accrued=12)
    d30 = _deposit(engine, BETA, 30, 300)
    loan = _loan(engine, BETA, 30, 200, due_at=T0 - timedelta(days=1), issue=False)   # overdue at the deleted bank
    assert _wallet(engine, BETA) == 0
    _sql(engine, "DELETE FROM Regions WHERE id = 30")
    world_before = _acc(engine, "world_treasury", 0)
    t10, t20 = _acc(engine, "region_treasury", 10), _acc(engine, "region_treasury", 20)

    db = engine.factory()
    try:
        assert crud.post_character_deletion(db, db.get(models.Character, BETA)) == 0
        db.commit()
    finally:
        db.close()
    op_id = _q(engine, "SELECT id FROM econ_operations WHERE idempotency_key = :k", k=f"character_deleted:c:{BETA}")
    legs = _legs(engine, op_id)
    assert [r for r in legs if r[5] == "main"] == [("bank_deposits", 10, "region_treasury", 10, 400, "main"),
                                                   ("bank_deposits", 20, "region_treasury", 20, 312, "main"),
                                                   ("bank_deposits", 30, "world_treasury", 0, 300, "main")]
    taxes = {r[1]: r[4] for r in legs if r[5] == "tax"}                 # vault money is taxed like wallet money
    assert set(taxes) == {10, 20} and all(t > 0 for t in taxes.values())
    assert _acc(engine, "region_treasury", 10) == t10 + 400 - taxes[10]
    assert _acc(engine, "region_treasury", 20) == t20 + 312 - taxes[20]
    assert _acc(engine, "world_treasury", 0) == world_before + 300
    for dep in (d10, d20, d30):
        assert _dep(engine, dep, "status") == "closed" and _dep(engine, dep, "amount") == 0
    assert _loan_col(engine, loan, "status") == "written_off" and _loan_col(engine, loan, "written_off") >= 200
    assert _loan_col(engine, loan, "active_character_id") is None
    _assert_invariant(engine)

    # the next tick purges the orphan bank: its own money -> world, nothing else to write off
    world_mid = _acc(engine, "world_treasury", 0)
    summary = _run(engine, T0)
    assert summary.banks_closed == 1 and summary.loans_collected == 0
    assert _acc(engine, "world_treasury", 0) == world_mid + CAPITAL[30]
    assert _acc(engine, "bank", 30) == 0 and _acc(engine, "bank_deposits", 30) == 0
    _assert_invariant(engine)


def test_orphan_row_with_nothing_in_it_is_left_alone(engine):
    db = engine.factory()
    try:
        db.add(models.EconBank(region_id=40, is_enabled=False))         # region 40 never existed / long gone
        db.commit()
    finally:
        db.close()
    summary = _run(engine, T0)
    assert summary.banks_closed == 0 and summary.bank_failures == 0
    assert summary.banks_processed == 3                                 # 40 has nothing to tick
    assert _ops(engine, core.OP_TREASURY_CLOSED) == 0
    _assert_invariant(engine)
