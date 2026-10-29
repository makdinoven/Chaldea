"""FEAT-181 Q1: behaviour of the sync posting helper `econ_ledger` beyond the shared contract.

* insufficient funds: nothing moves after the caller's rollback; the session stays usable
* duplicate idempotency key: raised before anything moves, the caller's own work survives
* lazy account creation (name snapshot, allow_negative), deactivation
* negative balances allowed for treasuries, never for characters / escrow / storage
* tax rate read from econ_settings, regions without a country are not taxed
* operation header fields (region resolved from location, metadata JSON)
* ORM copies of Character.currency_balance are refreshed after a posting
* the ORM balance guard: strict raise, new rows and no-op writes allowed, non-strict only warns
"""

import json
import logging

import pytest
from sqlalchemy import Column, Integer, create_engine, text
from sqlalchemy.orm import Session as SASession, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core
import econ_ledger
import models
from econ_core import AccountRef, Leg
from tests import econ_contract_cases as cc

SRC = "helper-test"
C1, C2, C3 = AccountRef.character(1), AccountRef.character(2), AccountRef.character(3)
R10, R20 = AccountRef.region(10), AccountRef.region(20)
K1, K2 = AccountRef.country(1), AccountRef.country(2)
WORLD, ESCROW, STORAGE = AccountRef.world(), AccountRef.escrow(), AccountRef.storage()
EMISSION = AccountRef.emission()


@pytest.fixture()
def Session():
    econ_core.invalidate_settings_cache()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = factory()
    for ddl in cc.SQLITE_DDL:
        s.execute(text(ddl))
    for sql, params in cc.SEED_SQL:
        s.execute(text(sql), params)
    s.commit()
    s.close()
    try:
        yield factory
    finally:
        econ_core.invalidate_settings_cache()
        engine.dispose()


def _fund(s, *pairs):
    econ_ledger.post_operation(s, op_type="admin_emission", legs=[Leg(EMISSION, r, a) for r, a in pairs],
                               source_service=SRC, comment="seed", apply_tax=False)


def _char(s, cid):
    return s.execute(text("SELECT currency_balance FROM characters WHERE id = :i"), {"i": cid}).scalar()


def _acc(s, ref):
    return s.execute(text("SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r"),
                     {"k": ref.kind, "r": ref.ref_id}).scalar()


def _count(s, table):
    return s.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def _world_sum(s):
    return s.execute(text(cc.WORLD_SUM_SQL)).scalar()


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def test_insufficient_funds_after_partial_apply_rolls_back_cleanly(Session):
    s = Session()
    _fund(s, (C1, 100))
    s.commit()

    # C1 (id 1) is debited first, then C2 (id 2, balance 0) fails.
    with pytest.raises(econ_core.InsufficientFunds) as exc:
        econ_ledger.post_operation(s, op_type="house_tax", legs=[Leg(C1, R10, 10), Leg(C2, R10, 10)],
                                   source_service=SRC)
    assert exc.value.account == C2 and exc.value.needed == 10
    s.rollback()

    assert _char(s, 1) == 100 and _char(s, 2) == 0
    assert _count(s, "econ_operations") == 1 and _count(s, "econ_postings") == 1

    # The session is still usable for the next operation.
    result = econ_ledger.post_operation(s, op_type="house_tax", legs=[Leg(C1, R10, 10)], source_service=SRC)
    s.commit()
    assert result.balances == {1: 90}
    assert _world_sum(s) == 0


def test_insufficient_funds_on_non_negative_account(Session):
    s = Session()
    for ref in (STORAGE, ESCROW):
        with pytest.raises(econ_core.InsufficientFunds) as exc:
            econ_ledger.post_operation(s, op_type="auction_claim", legs=[Leg(ref, C1, 1)], source_service=SRC)
        assert exc.value.account == ref
        s.rollback()
    assert _char(s, 1) == 0 and _count(s, "econ_operations") == 0


def test_duplicate_key_raises_before_anything_moves_and_keeps_callers_work(Session):
    s = Session()
    _fund(s, (C1, 100))
    econ_ledger.post_operation(s, op_type="dungeon_expense", legs=[Leg(C1, WORLD, 20)], source_service=SRC,
                               idempotency_key="dungeon_expense:s:1")
    s.commit()

    s.execute(text("UPDATE characters SET name = 'Alice II' WHERE id = 1"))  # the caller's business row
    with pytest.raises(econ_core.DuplicateOperation) as exc:
        econ_ledger.post_operation(s, op_type="dungeon_expense", legs=[Leg(C1, WORLD, 20)],
                                   source_service=SRC, idempotency_key="dungeon_expense:s:1")
    assert exc.value.operation_id == 2
    s.commit()

    assert s.execute(text("SELECT name FROM characters WHERE id = 1")).scalar() == "Alice II"
    assert _char(s, 1) == 80 and _acc(s, WORLD) == 20
    assert _count(s, "econ_operations") == 2


def test_validation_error_touches_nothing(Session):
    s = Session()
    with pytest.raises(econ_core.EconomyError):
        econ_ledger.post_operation(s, op_type="quest_reward", legs=[Leg(EMISSION, C1, 5)], source_service=SRC)
    assert _count(s, "econ_operations") == 0 and _count(s, "econ_accounts") == 0


def test_all_zero_legs_return_empty_result(Session):
    s = Session()
    result = econ_ledger.post_operation(s, op_type="battle_reward", legs=[Leg(WORLD, C1, 0)],
                                        source_service=SRC, idempotency_key="k:0")
    assert result == econ_core.PostingResult(None, {})
    assert _count(s, "econ_operations") == 0


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def test_accounts_created_lazily_with_name_snapshot_and_flags(Session):
    s = Session()
    assert _count(s, "econ_accounts") == 0
    econ_ledger.post_operation(s, op_type="quest_reward", legs=[Leg(R20, C2, 50)], source_service=SRC)
    s.commit()
    rows = {(r[0], r[1]): (r[2], r[3], r[4], r[5]) for r in s.execute(text(
        "SELECT kind, ref_id, name, balance, allow_negative, is_active FROM econ_accounts")).fetchall()}
    assert rows == {
        ("region_treasury", 20): ("Region B1", -50, 1, 1),
        ("character", 2): ("Bob", 0, 0, 1),          # character balance lives in characters
    }
    assert _char(s, 2) == 50


def test_singleton_names_and_get_or_create_is_stable(Session):
    s = Session()
    first = econ_ledger.get_or_create_account(s, WORLD)
    assert econ_ledger.get_or_create_account(s, WORLD) == first
    assert s.execute(text("SELECT name, allow_negative FROM econ_accounts WHERE id = :i"),
                     {"i": first}).first() == ("Казна Скитальцев", 1)
    escrow = econ_ledger.get_or_create_account(s, ESCROW)
    assert s.execute(text("SELECT name, allow_negative FROM econ_accounts WHERE id = :i"),
                     {"i": escrow}).first() == ("Ставки аукциона", 0)
    with pytest.raises(econ_core.EconomyError):
        econ_ledger.get_or_create_account(s, AccountRef("unknown_kind", 1))


def test_account_for_missing_region_row_has_no_name(Session):
    s = Session()
    acc = econ_ledger.get_or_create_account(s, AccountRef.region(999))
    assert s.execute(text("SELECT name FROM econ_accounts WHERE id = :i"), {"i": acc}).scalar() is None


def test_deactivate_account_keeps_row_and_journal(Session):
    s = Session()
    _fund(s, (C1, 10))
    econ_ledger.deactivate_account(s, C1)
    s.commit()
    assert s.execute(text("SELECT is_active FROM econ_accounts WHERE kind = 'character' AND ref_id = 1")).scalar() == 0
    assert _count(s, "econ_postings") == 1


def test_negative_balances_allowed_for_treasuries_only(Session):
    s = Session()
    econ_ledger.post_operation(s, op_type="quest_reward", legs=[Leg(R10, C1, 30)], source_service=SRC)
    econ_ledger.post_operation(s, op_type="battle_pass_reward", legs=[Leg(WORLD, C1, 20)], source_service=SRC)
    econ_ledger.post_operation(s, op_type="treasury_closed", legs=[Leg(K2, WORLD, 5)], source_service=SRC)
    s.commit()
    assert _acc(s, R10) == -30 and _acc(s, WORLD) == -15 and _acc(s, K2) == -5
    assert _char(s, 1) == 50
    with pytest.raises(econ_core.InsufficientFunds):
        econ_ledger.post_operation(s, op_type="trade", legs=[Leg(C2, C1, 1)], source_service=SRC)
    s.rollback()
    assert _char(s, 2) == 0 and _world_sum(s) == 0


def test_lock_characters_skips_missing_and_dedups(Session):
    s = Session()
    _fund(s, (C3, 7))
    assert econ_ledger.lock_characters(s, [3, 3, 999, 1]) == {1: 0, 3: 7}
    assert econ_ledger.lock_characters(s, []) == {}


# ---------------------------------------------------------------------------
# Tax / header
# ---------------------------------------------------------------------------

def test_tax_rate_comes_from_settings(Session):
    s = Session()
    _fund(s, (C1, 1000))
    s.execute(text("UPDATE econ_settings SET country_tax_rate = 0.25"))
    s.commit()
    econ_core.invalidate_settings_cache()
    econ_ledger.post_operation(s, op_type="npc_shop_buy", legs=[Leg(C1, R10, 99)], source_service=SRC)
    s.commit()
    # floor(99 * 0.25) = 24
    assert _acc(s, R10) == 75 and _acc(s, K1) == 24 and _world_sum(s) == 0


def test_settings_are_cached_until_invalidated(Session):
    s = Session()
    econ_core.invalidate_settings_cache()
    assert econ_ledger.get_economy_settings(s).country_tax_rate == econ_core.DEFAULT_COUNTRY_TAX_RATE
    s.execute(text("UPDATE econ_settings SET country_tax_rate = 0.3, currency_genitive = 'серебра'"))
    s.commit()
    assert econ_ledger.get_currency_forms(s).genitive == "марок"         # still cached
    econ_ledger.invalidate_settings_cache()
    assert econ_ledger.get_currency_forms(s).genitive == "серебра"
    assert float(econ_ledger.get_economy_settings(s).country_tax_rate) == 0.3


def test_missing_settings_table_falls_back_to_defaults():
    econ_core.invalidate_settings_cache()
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    s = sessionmaker(bind=engine)()
    try:
        assert econ_ledger.get_economy_settings(s) == econ_core.DEFAULT_SETTINGS
    finally:
        s.close()
        econ_core.invalidate_settings_cache()


def test_region_without_country_row_is_not_taxed(Session):
    s = Session()
    _fund(s, (C1, 100))
    econ_ledger.post_operation(s, op_type="teleport", legs=[Leg(C1, AccountRef.region(77), 50)],
                               source_service=SRC)
    s.commit()
    assert _count(s, "econ_postings WHERE leg_type = 'tax'") == 0
    assert _acc(s, AccountRef.region(77)) == 50


def test_operation_header_region_from_location_and_metadata(Session):
    s = Session()
    _fund(s, (C1, 100))
    res = econ_ledger.post_operation(s, op_type="teleport", legs=[Leg(C1, R10, 10)], source_service=SRC,
                                     location_id=1004, actor_user_id=5, metadata={"npc": "Мастер"},
                                     idempotency_key="teleport:1")
    s.commit()
    row = s.execute(text("SELECT op_type, location_id, region_id, actor_user_id, source_service, metadata, "
                         "idempotency_key FROM econ_operations WHERE id = :i"), {"i": res.operation_id}).first()
    assert row[:5] == ("teleport", 1004, 10, 5, SRC)
    assert json.loads(row[5]) == {"npc": "Мастер"} and "Мастер" in row[5]   # ensure_ascii=False
    assert row[6] == "teleport:1"

    # An explicit region_id wins over the location.
    res = econ_ledger.post_operation(s, op_type="teleport", legs=[Leg(C1, R20, 1)], source_service=SRC,
                                     location_id=1004, region_id=20)
    assert s.execute(text("SELECT region_id FROM econ_operations WHERE id = :i"),
                     {"i": res.operation_id}).scalar() == 20


def test_netting_touches_neither_side_of_an_even_swap(Session):
    """Both characters have 0: an even swap nets to 0 per account, so no debit can fail."""
    s = Session()
    res = econ_ledger.post_operation(s, op_type="trade", legs=[Leg(C1, C2, 50), Leg(C2, C1, 50)],
                                     source_service=SRC)
    s.commit()
    assert res.balances == {1: 0, 2: 0}
    assert _count(s, "econ_postings") == 2


def test_unknown_character_debit_is_rejected(Session):
    s = Session()
    with pytest.raises(econ_core.EconomyError):
        econ_ledger.post_operation(s, op_type="teleport", legs=[Leg(AccountRef.character(999), R10, 5)],
                                   source_service=SRC)
    s.rollback()


# ---------------------------------------------------------------------------
# ORM integration (character-service models on the shared test engine)
# ---------------------------------------------------------------------------

@pytest.fixture()
def orm_session(test_engine, test_session_factory, seed_fk_data):
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    seed_fk_data(session)
    econ_core.invalidate_settings_cache()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)
        econ_core.invalidate_settings_cache()


def _new_character(session, cid=1, balance=0):
    ch = models.Character(id=cid, name=f"Герой {cid}", id_subrace=1, id_class=1, id_race=1, level=1,
                          stat_points=0, currency_balance=balance, appearance="a", avatar="/a.jpg")
    session.add(ch)
    session.commit()
    return ch


def test_orm_balance_refreshed_after_posting(orm_session):
    ch = _new_character(orm_session)
    assert ch.currency_balance == 0          # loaded into the identity map
    econ_ledger.post_operation(orm_session, op_type="battle_pass_reward", legs=[Leg(WORLD, C1, 40)],
                               source_service=SRC)
    assert ch.currency_balance == 40         # expired by the helper, reloaded on access
    orm_session.commit()
    # And the reload did not count as an ORM write for the guard.
    ch.level = 2
    orm_session.commit()
    assert ch.currency_balance == 40


def test_posting_flushes_pending_character_insert(orm_session):
    """A just-added character (pending insert) is flushed before the raw balance UPDATE."""
    ch = models.Character(id=7, name="Новичок", id_subrace=1, id_class=1, id_race=1, level=1, stat_points=0,
                          currency_balance=0, appearance="a", avatar="/a.jpg")
    orm_session.add(ch)
    res = econ_ledger.post_operation(orm_session, op_type="starter_kit",
                                     legs=[Leg(WORLD, AccountRef.character(7), 15)], source_service=SRC)
    orm_session.commit()
    assert res.balances == {7: 15} and ch.currency_balance == 15


def test_guard_strict_raises_on_orm_write(orm_session):
    ch = _new_character(orm_session, balance=0)
    ch.currency_balance = 500
    with pytest.raises(econ_core.EconomyError, match="currency_balance"):
        orm_session.flush()
    orm_session.rollback()
    assert orm_session.execute(text("SELECT currency_balance FROM characters WHERE id = 1")).scalar() == 0


def test_guard_allows_new_rows_and_same_value(orm_session):
    ch = _new_character(orm_session, balance=0)   # insert: not checked
    assert ch.currency_balance == 0               # load the committed value
    ch.currency_balance = 0                       # same value: no real change
    ch.level = 3
    orm_session.commit()
    assert ch.level == 3


def test_guard_bypass_is_scoped(orm_session):
    ch = _new_character(orm_session, balance=0)
    with econ_ledger.allow_direct_balance_write(orm_session):
        ch.currency_balance = 5
        orm_session.commit()
    assert econ_ledger.ALLOW_DIRECT_BALANCE_KEY not in orm_session.info
    ch.currency_balance = 6
    with pytest.raises(econ_core.EconomyError):
        orm_session.commit()
    orm_session.rollback()


def test_models_install_the_guard_strict():
    assert models.BALANCE_GUARD_STRICT is True


def test_non_strict_guard_only_warns(caplog):
    """install_balance_guard(strict=False) logs instead of raising (own model + session class)."""
    Base = declarative_base()

    class Purse(Base):
        __tablename__ = "purses"
        id = Column(Integer, primary_key=True)
        coins = Column(Integer, nullable=False, default=0)

    class PurseSession(SASession):
        pass

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    econ_ledger.install_balance_guard(Purse, "coins", strict=False, session_cls=PurseSession)
    econ_ledger.install_balance_guard(Purse, "coins", strict=False, session_cls=PurseSession)  # idempotent
    s = sessionmaker(bind=engine, class_=PurseSession)()
    try:
        s.add(Purse(id=1, coins=1))
        s.commit()
        purse = s.get(Purse, 1)
        purse.coins = 9
        with caplog.at_level(logging.WARNING, logger="econ_ledger"):
            s.commit()
        assert sum("direct write of Purse.coins" in r.getMessage() for r in caplog.records) == 1
        assert s.execute(text("SELECT coins FROM purses")).scalar() == 9
    finally:
        s.close()
