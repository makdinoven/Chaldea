"""FEAT-184 B4: player bank API (contract 3.9) on SQLite — happy paths and the main refusals.

QA (Q2) extends this file. The FEAT-145 gate is mocked (``locations_client.check_npc_gate``).

World:
    country 1; region 10 «Ост» <- location 100; region 20 «Пашни» <- 200; location 300 has no region
    players: 1 «Альфа» (user 7) @100 wallet 5000, 2 «Бета» (user 8) @200 wallet 1000, 3 «Близнец» ×2 (users 9, 10)
    bankers: 50 @100, 51 @200, 52 @100 dead, 53 @300 (no region), 54 @100 merchant (not a banker)
    banks: 10 enabled with 20 000 own money, 20 enabled (empty), 30 «Глушь» (no location) disabled
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core as core
import econ_ledger
import economy_api
import economy_bank_crud as bank_crud
import locations_client
import models
from auth_http import UserRead, get_current_user_via_http
from main import app

SOURCE = "character-service"
BANK = "/characters/economy/bank"
ALPHA, BETA = 1, 2
BANKER, BANKER_20, BANKER_DEAD, BANKER_NOWHERE, MERCHANT = 50, 51, 52, 53, 54
BANK_CAPITAL = 20_000


def _url(action=None, npc=BANKER):
    return f"{BANK}/npc/{npc}" + (f"/{action}" if action else "")


@pytest.fixture
def engine(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=eng)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    db = factory()
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд')"))
    db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Ост', 1), (20, 'Пашни', 1), "
                    "(30, 'Глушь', 1)"))
    db.execute(text("INSERT INTO Locations (id, name, region_id) VALUES (100, 'Рынок', 10), (200, 'Село', 20), "
                    "(300, 'Пустошь', NULL)"))
    people = [  # id, name, user, npc, role, status, location
        (ALPHA, "Альфа", 7, False, None, "alive", 100), (BETA, "Бета", 8, False, None, "alive", 200),
        (3, "Близнец", 9, False, None, "alive", 100), (4, "Близнец", 10, False, None, "alive", 100),
        (BANKER, "Банкир", None, True, "banker", "alive", 100), (BANKER_20, "Банкир 2", None, True, "banker",
                                                                  "alive", 200),
        (BANKER_DEAD, "Мёртвый", None, True, "banker", "dead", 100),
        (BANKER_NOWHERE, "Странник", None, True, "banker", "alive", 300),
        (MERCHANT, "Торговец", None, True, "merchant", "alive", 100),
    ]
    with econ_ledger.allow_direct_balance_write(db):
        for cid, name, user, npc, role, status, loc in people:
            db.add(models.Character(id=cid, name=name, user_id=user, id_subrace=1, id_class=1, id_race=1,
                                    appearance="-", avatar="-", is_npc=npc, npc_role=role, npc_status=status,
                                    current_location_id=loc, level=2, currency_balance=0))
        db.flush()
    for region_id, enabled in ((10, True), (20, True), (30, False)):
        db.add(models.EconBank(region_id=region_id, is_enabled=enabled))
    db.flush()
    for cid, amount in ((ALPHA, 5000), (BETA, 1000)):
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                   legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.character(cid),
                                                  amount)])
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                               legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.region(10), BANK_CAPITAL)])
    econ_ledger.post_operation(db, op_type=core.OP_BANK_CAPITAL, source_service=SOURCE, apply_tax=False,
                               legs=[core.Leg(core.AccountRef.region(10), core.AccountRef.bank(10), BANK_CAPITAL)])
    db.commit()
    db.close()

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    gate = AsyncMock(return_value=True)
    monkeypatch.setattr(locations_client, "check_npc_gate", gate)
    core.invalidate_settings_cache()
    eng.factory = factory
    eng.gate = gate
    yield eng
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)
    core.invalidate_settings_cache()
    eng.dispose()


def _as_user(user_id=7, permissions=()):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username="tester", role="user", permissions=list(permissions))


@pytest.fixture
def client(engine):
    _as_user(7)
    return TestClient(app)


def _q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _wallet(engine, cid=ALPHA):
    return int(_q(engine, "SELECT currency_balance FROM characters WHERE id = :i", i=cid))


def _acc(engine, kind, ref):
    return int(_q(engine, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind = :k AND ref_id = :r",
                  k=kind, r=ref) or 0)


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


def _post(client, action, body, npc=BANKER):
    return client.post(_url(action, npc), json={"character_id": ALPHA, **body})


# --------------------------------------------------------------------------------------------- view / lists

def test_view_shows_rates_wallet_and_loan_limit(client, engine):
    resp = client.get(_url(), params={"character_id": ALPHA})
    assert resp.status_code == 200, resp.text
    view = resp.json()
    assert view["npc_name"] == "Банкир" and view["region_id"] == 10 and view["region_name"] == "Ост"
    assert view["bank_enabled"] is True and view["wallet"] == 5000
    assert view["rates"]["min_amount"] == 10
    assert [r["term_days"] for r in view["rates"]["term_rates"]] == [7, 14, 28]
    assert view["loan_cap"] == 500 + 250 * 2
    assert view["max_loan_now"] == 1000 and view["loan_refusal"] is None
    assert [r["region_id"] for r in view["bank_regions"]] == [10, 20]
    engine.gate.assert_not_called()                     # GET needs no gate


def test_regions_list_is_public(engine):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    resp = TestClient(app).get(f"{BANK}/regions")
    assert resp.status_code == 200
    assert resp.json() == [{"region_id": 10, "name": "Ост", "country_name": "Мидденгерд"},
                           {"region_id": 20, "name": "Пашни", "country_name": "Мидденгерд"}]


# --------------------------------------------------------------------------------------------- deposits

def test_demand_deposit_topup_and_withdraw(client, engine):
    resp = _post(client, "deposit", {"kind": "demand", "amount": 1000, "request_id": "req-0001"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["wallet"] == 4000 and data["operation_id"]
    dep = data["view"]["deposits"][0]
    assert dep["kind"] == "demand" and dep["amount"] == 1000 and dep["here"] is True
    assert _q(engine, "SELECT interest_base FROM bank_deposits WHERE id = :i", i=dep["id"]) == 0
    engine.gate.assert_awaited_with(ALPHA, 100, BANKER)

    resp = _post(client, "deposit", {"kind": "demand", "amount": 500})
    assert resp.status_code == 200, resp.text
    assert [d["amount"] for d in resp.json()["view"]["deposits"]] == [1500]      # same row topped up

    resp = _post(client, "withdraw", {"deposit_id": dep["id"], "amount": 600})
    assert resp.status_code == 200, resp.text
    assert resp.json()["view"]["deposits"][0]["amount"] == 900
    resp = _post(client, "withdraw", {"deposit_id": dep["id"], "amount": 900})
    assert resp.status_code == 200, resp.text
    assert resp.json()["view"]["deposits"] == [] and resp.json()["wallet"] == 5000
    assert _q(engine, "SELECT status FROM bank_deposits WHERE id = :i", i=dep["id"]) == "closed"
    _assert_invariant(engine)


def test_withdraw_refusals(client, engine):
    dep_id = _post(client, "deposit", {"kind": "demand", "amount": 100}).json()["view"]["deposits"][0]["id"]
    assert _post(client, "withdraw", {"deposit_id": dep_id}).json()["detail"] == "Укажите сумму"
    assert _post(client, "withdraw", {"deposit_id": dep_id, "amount": 5}).json()["detail"] == "Минимальная сумма — 10"
    assert _post(client, "withdraw", {"deposit_id": dep_id, "amount": 101}).status_code == 400
    assert _post(client, "withdraw", {"deposit_id": 999, "amount": 10}).status_code == 404
    # at the banker of another region
    with engine.factory() as db:
        db.execute(text("UPDATE characters SET current_location_id = 200 WHERE id = :i"), {"i": ALPHA})
        db.commit()
    resp = _post(client, "withdraw", {"deposit_id": dep_id, "amount": 10}, npc=BANKER_20)
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("Этот вклад лежит в банке региона «Ост»")
    _assert_invariant(engine)


def _credit_term_interest(engine, dep_id, interest):
    """Simulate a bank pass: interest B(10) -> V(10) on a term deposit."""
    with engine.factory() as db:
        econ_ledger.post_operation(db, op_type=core.OP_BANK_TICK, source_service=SOURCE, apply_tax=False,
                                   legs=[core.Leg(core.AccountRef.bank(10), core.AccountRef.bank_deposits(10),
                                                  interest, core.LEG_INTEREST)])
        db.execute(text("UPDATE bank_deposits SET interest_accrued = :a, interest_total = :a WHERE id = :i"),
                   {"a": interest, "i": dep_id})
        db.commit()


def test_term_deposit_early_close_burns_interest(client, engine):
    resp = _post(client, "deposit", {"kind": "term", "term_days": 14, "amount": 1000})
    assert resp.status_code == 200, resp.text
    dep = resp.json()["view"]["deposits"][0]
    assert dep["kind"] == "term" and dep["term_days"] == 14 and dep["matured"] is False
    assert dep["rate_day"] == pytest.approx(0.0025)
    _credit_term_interest(engine, dep["id"], 30)
    bank_before = _acc(engine, "bank", 10)

    resp = _post(client, "withdraw", {"deposit_id": dep["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Срочный вклад закрыт досрочно: проценты (30 марок) сгорели"
    assert resp.json()["wallet"] == 5000
    assert _acc(engine, "bank", 10) == bank_before + 30
    legs = _q(engine, "SELECT COUNT(*) FROM econ_postings WHERE operation_id = :o AND leg_type = 'interest'",
              o=resp.json()["operation_id"])
    assert legs == 1
    _assert_invariant(engine)


def test_matured_term_deposit_pays_interest(client, engine):
    dep_id = _post(client, "deposit", {"kind": "term", "term_days": 7, "amount": 1000}).json()["view"]["deposits"][0]["id"]
    _credit_term_interest(engine, dep_id, 14)
    with engine.factory() as db:
        db.execute(text("UPDATE bank_deposits SET matures_at = :t WHERE id = :i"),
                   {"t": datetime.utcnow() - timedelta(minutes=1), "i": dep_id})
        db.commit()
    resp = _post(client, "withdraw", {"deposit_id": dep_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["wallet"] == 5014
    _assert_invariant(engine)


def test_deposit_refusals(client, engine):
    assert _post(client, "deposit", {"kind": "demand", "amount": 5}).json()["detail"] == "Минимальная сумма — 10"
    assert _post(client, "deposit", {"kind": "demand", "amount": 9000}).json()["detail"] == "Недостаточно марок"
    assert _post(client, "deposit", {"kind": "term", "term_days": 10, "amount": 100}).status_code == 422
    assert _post(client, "deposit", {"kind": "demand", "term_days": 7, "amount": 100}).status_code == 422
    assert _post(client, "deposit", {"kind": "demand", "amount": 10.5}).status_code == 422
    assert _post(client, "deposit", {"kind": "demand", "amount": -5}).status_code == 422
    with engine.factory() as db:
        db.execute(text("UPDATE econ_banks SET is_enabled = 0 WHERE region_id = 10"))
        db.commit()
    resp = _post(client, "deposit", {"kind": "demand", "amount": 100})
    assert resp.status_code == 409 and resp.json()["detail"] == "В этом регионе банк не принимает вклады"
    assert _wallet(engine) == 5000


def test_duplicate_request_id_is_409(client, engine):
    body = {"kind": "demand", "amount": 100, "request_id": "dup-request-1"}
    assert _post(client, "deposit", body).status_code == 200
    resp = _post(client, "deposit", body)
    assert resp.status_code == 409 and resp.json()["detail"] == "Операция уже выполнена"
    assert _wallet(engine) == 4900
    assert _post(client, "deposit", {**body, "request_id": "bad id!"}).status_code == 422


# --------------------------------------------------------------------------------------------- transfers

def test_transfer_to_another_bank_with_commission_and_tax(client, engine):
    dep_id = _post(client, "deposit", {"kind": "demand", "amount": 1000}).json()["view"]["deposits"][0]["id"]
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 500})
    assert resp.status_code == 200, resp.text
    deposits = {d["region_id"]: d for d in resp.json()["view"]["deposits"]}
    assert deposits[10]["amount"] == 490 and deposits[20]["amount"] == 500           # fee max(1, ceil(2 %)) = 10
    assert deposits[20]["here"] is False
    assert _acc(engine, "region_treasury", 10) == 9 and _acc(engine, "country_treasury", 1) == 1   # 10 % tax
    assert _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 10, "amount": 50}).json()["detail"] \
        == "Вклад уже в этом банке"
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 30, "amount": 50})
    assert resp.status_code == 409 and resp.json()["detail"] == "Банк региона «Глушь» не принимает вклады"
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 485})
    assert resp.status_code == 400 and "комиссии" in resp.json()["detail"]
    _assert_invariant(engine)


def test_term_deposit_cannot_be_transferred(client, engine):
    dep_id = _post(client, "deposit", {"kind": "term", "term_days": 7, "amount": 100}).json()["view"]["deposits"][0]["id"]
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 50})
    assert resp.status_code == 400 and resp.json()["detail"].startswith("Срочный вклад нельзя перевести")


def test_send_to_player_from_wallet_and_deposit(client, engine):
    resp = _post(client, "send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 20, "amount": 200})
    assert resp.status_code == 200, resp.text
    assert resp.json()["wallet"] == 5000 - 200 - 4                  # fee ceil(2 %) = 4
    assert all(d["region_id"] != 20 for d in resp.json()["view"]["deposits"])        # recipient's rows not shown
    assert _q(engine, "SELECT amount FROM bank_deposits WHERE character_id = :c AND region_id = 20", c=BETA) == 200

    dep_id = _post(client, "deposit", {"kind": "demand", "amount": 1000}).json()["view"]["deposits"][0]["id"]
    resp = _post(client, "send", {"source": "deposit", "deposit_id": dep_id, "recipient_name": " Бета ",
                                  "to_region_id": 10, "amount": 100})
    assert resp.status_code == 200, resp.text
    assert resp.json()["view"]["deposits"][0]["amount"] == 1000 - 100 - 2
    assert _q(engine, "SELECT amount FROM bank_deposits WHERE character_id = :c AND region_id = 10", c=BETA) == 100
    _assert_invariant(engine)


def test_send_refusals(client, engine):
    base = {"source": "wallet", "to_region_id": 20, "amount": 100}
    assert _post(client, "send", {**base, "recipient_name": "Никто"}).status_code == 404
    assert _post(client, "send", {**base, "recipient_name": "Близнец"}).json()["detail"] \
        == "Найдено несколько персонажей с таким именем"
    assert _post(client, "send", {**base, "recipient_name": "Альфа"}).json()["detail"] == "Нельзя перевести самому себе"
    assert _post(client, "send", {**base, "recipient_name": "Банкир"}).status_code == 404       # NPCs are not players
    assert _post(client, "send", {**base, "recipient_name": "Бета", "source": "deposit"}).status_code == 422
    assert _post(client, "send", {**base, "recipient_name": "Бета", "amount": 4995}).status_code == 400
    assert _wallet(engine) == 5000


# --------------------------------------------------------------------------------------------- loans

def test_loan_issue_repay_partial_and_full(client, engine):
    resp = _post(client, "loan", {"amount": 800, "term_days": 7})
    assert resp.status_code == 200, resp.text
    view = resp.json()["view"]
    assert resp.json()["wallet"] == 5800 and view["loan"]["debt"] == 800 and view["loan"]["overdue"] is False
    assert view["max_loan_now"] == 0 and view["loan_refusal"] == "У вас уже есть займ — сначала погасите его"
    assert _acc(engine, "bank", 10) == BANK_CAPITAL - 800
    assert _post(client, "loan", {"amount": 100, "term_days": 7}).json()["detail"] \
        == "У вас уже есть займ — сначала погасите его"

    resp = _post(client, "repay", {"amount": 300})
    assert resp.status_code == 200, resp.text
    assert resp.json()["view"]["loan"]["debt"] == 500
    resp = _post(client, "repay", {"amount": 5000})                 # more than the rest: pays the rest only
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Займ погашен" and resp.json()["view"]["loan"] is None
    assert resp.json()["wallet"] == 5000
    assert _acc(engine, "bank", 10) == BANK_CAPITAL
    assert _post(client, "repay", {"amount": 10}).status_code == 404
    _assert_invariant(engine)


def test_loan_refusals(client, engine):
    assert _post(client, "loan", {"amount": 1001, "term_days": 7}).json()["detail"].startswith("Ваш лимит займа")
    assert _post(client, "loan", {"amount": 100, "term_days": 5}).status_code == 422
    with engine.factory() as db:
        db.execute(text("UPDATE econ_accounts SET balance = balance - 19500 WHERE kind = 'bank' AND ref_id = 10"))
        db.execute(text("UPDATE econ_accounts SET balance = balance + 19500 WHERE kind = 'region_treasury' "
                        "AND ref_id = 10"))
        db.commit()
    resp = _post(client, "loan", {"amount": 600, "term_days": 7})
    assert resp.status_code == 409 and resp.json()["detail"] == "Банк сейчас может выдать не больше 500 марок"
    resp = client.post(_url("loan", BANKER_20), json={"character_id": BETA, "amount": 100, "term_days": 7})
    assert resp.status_code == 403                                    # not Beta's user


def test_overdue_loan_marks_debtor(client, engine):
    assert _post(client, "loan", {"amount": 500, "term_days": 7}).status_code == 200
    with engine.factory() as db:
        db.execute(text("UPDATE bank_loans SET due_at = :t, accrued_at = :t"),
                   {"t": datetime.utcnow() - timedelta(days=1)})
        db.commit()
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["debtor"] is True and view["loan"]["overdue"] is True and view["loan"]["debt"] > 500
    assert view["loan_refusal"] == "Вы в списке должников — новые займы не выдаются"


# --------------------------------------------------------------------------------------------- banker checks

def test_banker_check_order_and_gate(client, engine):
    body = {"kind": "demand", "amount": 100}
    assert _post(client, "deposit", body, npc=MERCHANT).json()["detail"] == "Банкир не найден"
    assert _post(client, "deposit", body, npc=999).status_code == 404
    resp = _post(client, "deposit", body, npc=BANKER_DEAD)
    assert resp.status_code == 409 and resp.json()["detail"] == "Банкир больше не принимает посетителей"
    resp = _post(client, "deposit", body, npc=BANKER_20)
    assert resp.status_code == 400 and resp.json()["detail"] == "Подойдите к банкиру — он в другой локации"

    engine.gate.return_value = False
    resp = _post(client, "deposit", body)
    assert resp.status_code == 403 and resp.json()["detail"] == "Нужен пост-намерение «Диалог с НПС» с этим персонажем"
    engine.gate.side_effect = locations_client.GateUnavailable()
    resp = _post(client, "deposit", body)
    assert resp.status_code == 503
    assert _wallet(engine) == 5000

    with engine.factory() as db:
        db.execute(text("UPDATE characters SET dungeon_session_id = 5 WHERE id = :i"), {"i": ALPHA})
        db.commit()
    engine.gate.reset_mock()
    resp = _post(client, "deposit", body)
    assert resp.status_code == 409 and resp.json()["detail"] == "Персонаж находится в подземелье"
    engine.gate.assert_not_called()                     # the lock is checked before the gate
    assert client.get(_url(), params={"character_id": ALPHA}).status_code == 200   # GET ignores the lock


def test_banker_without_region(client, engine):
    with engine.factory() as db:
        db.execute(text("UPDATE characters SET current_location_id = 300 WHERE id = :i"), {"i": ALPHA})
        db.commit()
    resp = client.get(_url(npc=BANKER_NOWHERE), params={"character_id": ALPHA})
    assert resp.status_code == 409 and resp.json()["detail"] == "Этот банкир не служит ни одному банку"


def test_ownership(client, engine):
    _as_user(8)
    resp = _post(client, "deposit", {"kind": "demand", "amount": 100})
    assert resp.status_code == 403 and resp.json()["detail"] == "Вы можете управлять только своими персонажами"
    assert client.get(_url(), params={"character_id": 999}).status_code == 404


# --------------------------------------------------------------------------------------------- summary

def test_summary_owner_and_admin(client, engine):
    _post(client, "deposit", {"kind": "demand", "amount": 300})
    _post(client, "deposit", {"kind": "term", "term_days": 28, "amount": 200})
    resp = client.get(f"{BANK}/summary", params={"character_id": ALPHA})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_deposits"] == 500 and len(data["deposits"]) == 2
    assert all(d["here"] is False for d in data["deposits"]) and data["loan"] is None and data["debtor"] is False

    _as_user(8)
    assert client.get(f"{BANK}/summary", params={"character_id": ALPHA}).status_code == 403
    _as_user(8, permissions=["economy:read"])
    assert client.get(f"{BANK}/summary", params={"character_id": ALPHA}).json()["total_deposits"] == 500


# =====================================================================================================================
# Q2 (QA): security, banker checks in order, gate client, disabled bank, reserve rule, commission math, loans,
# idempotency per flow. Every money scenario ends with `_assert_invariant` (world sum 0, vault == open deposits).
# =====================================================================================================================

import asyncio  # noqa: E402

import httpx  # noqa: E402

_REAL_CHECK_NPC_GATE = locations_client.check_npc_gate     # captured before the fixture mocks it
FIXTURE_OPS = 4                                            # operations posted by the `engine` fixture


def _sql(engine, sql, **params):
    with engine.factory() as db:
        db.execute(text(sql), params)
        db.commit()


def _move_alpha(engine, location_id):
    _sql(engine, "UPDATE characters SET current_location_id = :l WHERE id = :i", l=location_id, i=ALPHA)


def _ledger_move(engine, src, dst, amount):
    """Move money between accounts through the ledger (keeps the world sum at 0)."""
    with engine.factory() as db:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_ADJUST, source_service=SOURCE, apply_tax=False,
                                   comment="тест", legs=[core.Leg(src, dst, amount)])
        db.commit()


def _drain_bank(engine, region_id=10, leave=0):
    have = _acc(engine, "bank", region_id)
    if have > leave:
        _ledger_move(engine, core.AccountRef.bank(region_id), core.AccountRef.region(region_id), have - leave)


def _deposit(client, amount, kind="demand", term_days=None, npc=BANKER, character_id=ALPHA):
    body = {"character_id": character_id, "kind": kind, "amount": amount}
    if term_days:
        body["term_days"] = term_days
    resp = client.post(_url("deposit", npc), json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    data["new_id"] = max(d["id"] for d in data["view"]["deposits"])     # the row just opened / topped up
    return data


def _demand_id(engine, cid=ALPHA, region_id=10):
    return _q(engine, "SELECT id FROM bank_deposits WHERE character_id = :c AND region_id = :r AND kind = 'demand' "
                      "AND status = 'open'", c=cid, r=region_id)


def _ops(engine):
    return int(_q(engine, "SELECT COUNT(*) FROM econ_operations"))


def _ago(**delta):
    """A past moment a few seconds further back, so `now_utc()` (microseconds cut) never lands short of it."""
    return datetime.utcnow() - timedelta(seconds=5, **delta)


# --------------------------------------------------------------------------------------------- auth / ownership

def test_no_token_is_401_everywhere(engine):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    anon = TestClient(app)
    assert anon.get(_url(), params={"character_id": ALPHA}).status_code == 401
    assert anon.get(f"{BANK}/summary", params={"character_id": ALPHA}).status_code == 401
    for action, body in _EVERY_POST:
        resp = anon.post(_url(action), json={"character_id": ALPHA, **body})
        assert resp.status_code == 401, action
    engine.gate.assert_not_called()
    assert _wallet(engine) == 5000 and _ops(engine) == FIXTURE_OPS


def test_ownership_is_checked_before_the_banker(client, engine):
    _as_user(8)                                   # Beta's user, Alpha's character, a merchant as "banker"
    resp = _post(client, "deposit", {"kind": "demand", "amount": 100}, npc=MERCHANT)
    assert resp.status_code == 403 and resp.json()["detail"] == "Вы можете управлять только своими персонажами"
    resp = client.get(_url(npc=999), params={"character_id": 999})
    assert resp.status_code == 404 and resp.json()["detail"] == "Персонаж не найден"
    resp = client.post(_url("deposit"), json={"character_id": 999, "kind": "demand", "amount": 100})
    assert resp.status_code == 404 and resp.json()["detail"] == "Персонаж не найден"
    engine.gate.assert_not_called()


def test_other_players_character_cannot_use_any_flow(client, engine):
    dep_id = _deposit(client, 500)["new_id"]
    _as_user(8)
    for action, body in (("withdraw", {"deposit_id": dep_id, "amount": 100}),
                         ("transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 100}),
                         ("send", {"source": "deposit", "deposit_id": dep_id, "recipient_name": "Бета",
                                   "to_region_id": 20, "amount": 100}),
                         ("loan", {"amount": 100, "term_days": 7}), ("repay", {"amount": 100})):
        assert _post(client, action, body).status_code == 403, action
    assert client.get(_url(), params={"character_id": ALPHA}).status_code == 403
    # Beta (own character, at her banker) cannot touch Alpha's deposit id
    for action, body in (("withdraw", {"deposit_id": dep_id, "amount": 100}),
                         ("transfer", {"deposit_id": dep_id, "to_region_id": 10, "amount": 100}),
                         ("send", {"source": "deposit", "deposit_id": dep_id, "recipient_name": "Альфа",
                                   "to_region_id": 10, "amount": 100})):
        resp = client.post(_url(action, BANKER_20), json={"character_id": BETA, **body})
        assert resp.status_code == 404 and resp.json()["detail"] == "Вклад не найден", action
    assert _q(engine, "SELECT amount FROM bank_deposits WHERE id = :i", i=dep_id) == 500
    assert _wallet(engine, BETA) == 1000
    _assert_invariant(engine)


def test_npc_character_cannot_bank(client, engine):
    _sql(engine, "UPDATE characters SET user_id = 7 WHERE id = :i", i=MERCHANT)
    resp = client.post(_url("deposit"), json={"character_id": MERCHANT, "kind": "demand", "amount": 100})
    assert resp.status_code == 403 and resp.json()["detail"] == "Банком пользуются только персонажи игроков"
    assert client.get(f"{BANK}/summary", params={"character_id": MERCHANT}).status_code == 403


# --------------------------------------------------------------------------------------------- banker check order

def test_dead_banker_is_checked_before_location(client, engine):
    _move_alpha(engine, 200)                        # the dead banker stands at 100
    resp = _post(client, "deposit", {"kind": "demand", "amount": 100}, npc=BANKER_DEAD)
    assert resp.status_code == 409 and resp.json()["detail"] == "Банкир больше не принимает посетителей"
    assert client.get(_url(npc=BANKER_DEAD), params={"character_id": ALPHA}).status_code == 409
    resp = client.get(_url(), params={"character_id": ALPHA})                      # GET checks the location too
    assert resp.status_code == 400 and resp.json()["detail"] == "Подойдите к банкиру — он в другой локации"


def test_activity_lock_is_checked_before_location_and_gate(client, engine):
    _sql(engine, "UPDATE characters SET dungeon_session_id = 5 WHERE id = :i", i=ALPHA)
    resp = _post(client, "deposit", {"kind": "demand", "amount": 100}, npc=BANKER_20)   # other location too
    assert resp.status_code == 409 and resp.json()["detail"] == "Персонаж находится в подземелье"
    engine.gate.assert_not_called()


def test_wrong_location_never_asks_the_gate(client, engine):
    assert _post(client, "deposit", {"kind": "demand", "amount": 100}, npc=BANKER_20).status_code == 400
    engine.gate.assert_not_called()


def test_gate_is_checked_before_the_region(client, engine):
    _move_alpha(engine, 300)
    engine.gate.return_value = False
    assert _post(client, "deposit", {"kind": "demand", "amount": 100}, npc=BANKER_NOWHERE).status_code == 403
    engine.gate.return_value = True
    resp = _post(client, "deposit", {"kind": "demand", "amount": 100}, npc=BANKER_NOWHERE)
    assert resp.status_code == 409 and resp.json()["detail"] == "Этот банкир не служит ни одному банку"
    engine.gate.assert_awaited_with(ALPHA, 300, BANKER_NOWHERE)


_EVERY_POST = [
    ("deposit", {"kind": "demand", "amount": 100}),
    ("withdraw", {"deposit_id": 1, "amount": 100}),
    ("transfer", {"deposit_id": 1, "to_region_id": 20, "amount": 100}),
    ("send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 20, "amount": 100}),
    ("loan", {"amount": 100, "term_days": 7}),
    ("repay", {"amount": 100}),
]


@pytest.mark.parametrize("action,body", _EVERY_POST, ids=[a for a, _ in _EVERY_POST])
def test_every_post_is_gated(client, engine, action, body):
    engine.gate.return_value = False
    resp = _post(client, action, body)
    assert resp.status_code == 403 and resp.json()["detail"] == "Нужен пост-намерение «Диалог с НПС» с этим персонажем"
    engine.gate.return_value = True
    engine.gate.side_effect = locations_client.GateUnavailable()
    resp = _post(client, action, body)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Не удалось проверить обращение к банкиру, попробуйте позже"
    assert engine.gate.await_count == 2
    assert _wallet(engine) == 5000 and _ops(engine) == FIXTURE_OPS
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- gate client itself

class _FakeResponse:
    def __init__(self, status_code, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


def _fake_httpx(monkeypatch, outcome, calls):
    class _Client:
        def __init__(self, *args, **kwargs):
            calls.append(("init", kwargs))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None, headers=None):
            calls.append(("get", url, params, headers))
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(locations_client.httpx, "AsyncClient", _Client)


@pytest.mark.parametrize("payload,expected", [({"open": True}, True), ({"open": False}, False)])
def test_gate_client_answers(monkeypatch, payload, expected):
    calls = []
    _fake_httpx(monkeypatch, _FakeResponse(200, payload), calls)
    assert asyncio.run(_REAL_CHECK_NPC_GATE(ALPHA, 100, BANKER)) is expected
    assert calls[0][1].get("timeout")                                               # a bounded call
    _, url, params, headers = calls[-1]
    assert url.endswith("/locations/internal/action-gate")
    assert params == {"character_id": ALPHA, "location_id": 100, "action_type": "npc_dialogue",
                      "target_ref": BANKER}
    assert "X-Internal-Token" in (headers or {})


@pytest.mark.parametrize("outcome", [
    httpx.ConnectError("down"), httpx.ReadTimeout("slow"), _FakeResponse(500, {"open": True}),
    _FakeResponse(404, {"open": True}), _FakeResponse(200, bad_json=True), _FakeResponse(200, {}),
    _FakeResponse(200, {"open": "yes"}), _FakeResponse(200, {"open": 1}), _FakeResponse(200, None),
], ids=["connect", "timeout", "500", "404", "bad-json", "no-open", "open-str", "open-int", "null"])
def test_gate_client_fails_closed(monkeypatch, outcome):
    _fake_httpx(monkeypatch, outcome, [])
    with pytest.raises(locations_client.GateUnavailable):
        asyncio.run(_REAL_CHECK_NPC_GATE(ALPHA, 100, BANKER))


# --------------------------------------------------------------------------------------------- input validation

_BAD_BODIES = [
    ("deposit", {"kind": "demand", "amount": 0}),
    ("deposit", {"kind": "demand", "amount": -100}),
    ("deposit", {"kind": "demand", "amount": 1_000_000_001}),
    ("deposit", {"kind": "demand", "amount": 10 ** 30}),
    ("deposit", {"kind": "demand", "amount": 100.0}),
    ("deposit", {"kind": "demand", "amount": "100"}),
    ("deposit", {"kind": "demand", "amount": True}),
    ("deposit", {"kind": "demand", "amount": None}),
    ("deposit", {"kind": "demand"}),
    ("deposit", {"kind": "savings", "amount": 100}),
    ("deposit", {"kind": "term", "amount": 100}),
    ("deposit", {"kind": "term", "term_days": "7", "amount": 100}),
    ("deposit", {"kind": "term", "term_days": 7.0, "amount": 100}),
    ("deposit", {"kind": "term", "term_days": True, "amount": 100}),
    ("deposit", {"kind": "term", "term_days": 0, "amount": 100}),
    ("deposit", {"kind": "demand", "amount": 100, "character_id": "1"}),
    ("deposit", {"kind": "demand", "amount": 100, "character_id": "1 OR 1=1"}),
    ("deposit", {"kind": "demand", "amount": 100, "character_id": True}),
    ("deposit", {"kind": "demand", "amount": 100, "character_id": 0}),
    ("deposit", {"kind": "demand", "amount": 100, "request_id": "short"}),
    ("deposit", {"kind": "demand", "amount": 100, "request_id": "x' OR '1'='1"}),
    ("deposit", {"kind": "demand", "amount": 100, "request_id": "a" * 65}),
    ("withdraw", {"deposit_id": "1", "amount": 100}),
    ("withdraw", {"deposit_id": 1.5, "amount": 100}),
    ("withdraw", {"deposit_id": 0, "amount": 100}),
    ("withdraw", {"deposit_id": 1, "amount": -1}),
    ("transfer", {"deposit_id": 1, "to_region_id": "20; DROP TABLE econ_banks", "amount": 100}),
    ("transfer", {"deposit_id": 1, "to_region_id": 0, "amount": 100}),
    ("transfer", {"deposit_id": 1, "to_region_id": 20, "amount": 0}),
    ("send", {"source": "wallet", "recipient_name": "", "to_region_id": 20, "amount": 100}),
    ("send", {"source": "wallet", "recipient_name": "   ", "to_region_id": 20, "amount": 100}),
    ("send", {"source": "wallet", "recipient_name": "Б" * 256, "to_region_id": 20, "amount": 100}),
    ("send", {"source": "wallet", "deposit_id": 1, "recipient_name": "Бета", "to_region_id": 20, "amount": 100}),
    ("send", {"source": "bank", "recipient_name": "Бета", "to_region_id": 20, "amount": 100}),
    ("send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 20, "amount": 1.5}),
    ("loan", {"amount": 100, "term_days": 30}),
    ("loan", {"amount": 100, "term_days": "14"}),
    ("loan", {"amount": 100, "term_days": False}),
    ("loan", {"amount": 100}),
    ("loan", {"amount": -100, "term_days": 7}),
    ("repay", {"amount": 0}),
    ("repay", {"amount": "all"}),
    ("repay", {"amount": 10 ** 12}),
]


@pytest.mark.parametrize("action,body", _BAD_BODIES)
def test_bad_input_is_422_and_moves_nothing(client, engine, action, body):
    resp = client.post(_url(action), json={"character_id": ALPHA, **body})
    assert resp.status_code == 422, resp.text
    engine.gate.assert_not_called()
    assert _wallet(engine) == 5000 and _ops(engine) == FIXTURE_OPS


def test_bad_path_and_query_are_422(client, engine):
    assert client.get(f"{BANK}/npc/abc", params={"character_id": ALPHA}).status_code == 422
    assert client.get(_url(), params={"character_id": "1 OR 1=1"}).status_code == 422
    assert client.get(_url(), params={"character_id": 0}).status_code == 422
    assert client.get(f"{BANK}/summary", params={"character_id": "1; DROP TABLE bank_deposits"}).status_code == 422
    assert client.get(f"{BANK}/summary").status_code == 422
    resp = client.post(f"{BANK}/npc/50%20OR%201=1/deposit", json={"character_id": ALPHA, "kind": "demand",
                                                                  "amount": 100})
    assert resp.status_code == 422
    resp = client.post(_url("deposit"), data="not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 422
    engine.gate.assert_not_called()


@pytest.mark.parametrize("name", ["'; DROP TABLE characters; --", "\" OR 1=1 --", "Бета' OR '1'='1",
                                  "<script>alert(1)</script>", "%", "_____"])
def test_sql_like_recipient_names_are_not_found(client, engine, name):
    resp = _post(client, "send", {"source": "wallet", "recipient_name": name, "to_region_id": 20, "amount": 100})
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == f"Персонаж «{name}» не найден"
    assert _q(engine, "SELECT COUNT(*) FROM characters") == 9
    assert _wallet(engine) == 5000


def test_huge_but_valid_amounts_are_refused_cleanly(client, engine):
    top = 1_000_000_000
    assert _post(client, "deposit", {"kind": "demand", "amount": top}).json()["detail"] == "Недостаточно марок"
    assert _post(client, "loan", {"amount": top, "term_days": 28}).json()["detail"].startswith("Ваш лимит займа")
    resp = _post(client, "send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 20, "amount": top})
    assert resp.status_code == 400 and "с учётом комиссии" in resp.json()["detail"]
    dep_id = _deposit(client, 100)["new_id"]
    assert _post(client, "withdraw", {"deposit_id": dep_id, "amount": top}).status_code == 400
    assert _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": top}).status_code == 400
    assert _wallet(engine) == 4900
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- idempotency

def test_request_id_repeat_is_409_for_every_flow(client, engine):
    def twice(action, body):
        first = _post(client, action, body)
        assert first.status_code == 200, (action, first.text)
        ops = _ops(engine)
        again = _post(client, action, body)
        assert again.status_code == 409 and again.json()["detail"] == "Операция уже выполнена", action
        assert _ops(engine) == ops, action
        return first.json()

    dep_id = twice("deposit", {"kind": "demand", "amount": 1000,
                               "request_id": "rid-deposit-1"})["view"]["deposits"][0]["id"]
    twice("deposit", {"kind": "term", "term_days": 7, "amount": 100, "request_id": "rid-term-0001"})
    twice("withdraw", {"deposit_id": dep_id, "amount": 100, "request_id": "rid-withdraw-1"})
    twice("transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 100, "request_id": "rid-transfer-1"})
    twice("send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 20, "amount": 100,
                   "request_id": "rid-send-0001"})
    twice("loan", {"amount": 500, "term_days": 7, "request_id": "rid-loan-0001"})
    twice("repay", {"amount": 100, "request_id": "rid-repay-0001"})

    assert _q(engine, "SELECT amount FROM bank_deposits WHERE id = :i", i=dep_id) == 1000 - 100 - 100 - 2
    assert _q(engine, "SELECT COUNT(*) FROM bank_deposits WHERE kind = 'term'") == 1
    assert _q(engine, "SELECT debt FROM bank_loans") == 400
    assert _wallet(engine) == 5000 - 1000 - 100 + 100 - 102 + 500 - 100
    _assert_invariant(engine)


def test_request_id_is_scoped_per_flow_and_character(client, engine):
    rid = "shared-request-id"
    assert _post(client, "deposit", {"kind": "demand", "amount": 100, "request_id": rid}).status_code == 200
    assert _post(client, "loan", {"amount": 100, "term_days": 7, "request_id": rid}).status_code == 200
    _as_user(8)
    resp = client.post(_url("deposit", BANKER_20), json={"character_id": BETA, "kind": "demand", "amount": 100,
                                                         "request_id": rid})
    assert resp.status_code == 200, resp.text
    _assert_invariant(engine)


def test_refused_request_id_can_be_retried(client, engine):
    body = {"kind": "demand", "amount": 9000, "request_id": "retry-after-400"}
    assert _post(client, "deposit", body).status_code == 400            # nothing posted -> the key stays free
    assert _post(client, "deposit", {**body, "amount": 900}).status_code == 200
    assert _wallet(engine) == 4100
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- deposits / withdrawals

def test_term_deposits_limit_is_ten(client, engine):
    for _ in range(10):
        _deposit(client, 10, kind="term", term_days=28)
    resp = _post(client, "deposit", {"kind": "term", "term_days": 7, "amount": 10})
    assert resp.status_code == 409 and resp.json()["detail"] == "Не больше 10 срочных вкладов"
    assert _post(client, "deposit", {"kind": "demand", "amount": 10}).status_code == 200   # demand is not limited
    assert _wallet(engine) == 5000 - 110
    _assert_invariant(engine)


def test_term_rates_follow_factor_and_are_fixed_at_opening(client, engine):
    _sql(engine, "UPDATE econ_banks SET deposit_rate_factor = 0.5 WHERE region_id = 10")
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["rates"]["demand_rate_day"] == pytest.approx(0.0005)
    assert [r["rate_day"] for r in view["rates"]["term_rates"]] == pytest.approx([0.001, 0.00125, 0.0015])
    dep = _deposit(client, 100, kind="term", term_days=28)["view"]["deposits"][0]
    assert dep["rate_day"] == pytest.approx(0.0015)
    opened = datetime.fromisoformat(dep["opened_at"])
    assert datetime.fromisoformat(dep["matures_at"]) - opened == timedelta(days=28)
    _sql(engine, "UPDATE econ_banks SET deposit_rate_factor = 1 WHERE region_id = 10")
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["deposits"][0]["rate_day"] == pytest.approx(0.0015)


def test_demand_withdraw_whole_rest_below_minimum(client, engine):
    dep_id = _deposit(client, 15)["new_id"]
    assert _post(client, "withdraw", {"deposit_id": dep_id, "amount": 10}).status_code == 200
    assert _post(client, "withdraw", {"deposit_id": dep_id, "amount": 4}).json()["detail"] == "Минимальная сумма — 10"
    resp = _post(client, "withdraw", {"deposit_id": dep_id, "amount": 5})                 # the whole rest
    assert resp.status_code == 200 and resp.json()["message"].startswith("Вклад закрыт")
    assert _post(client, "withdraw", {"deposit_id": dep_id, "amount": 5}).status_code == 404   # closed now
    assert _wallet(engine) == 5000
    _assert_invariant(engine)


def test_withdraw_lowers_interest_base_topup_keeps_it(client, engine):
    dep_id = _deposit(client, 1000)["new_id"]
    _sql(engine, "UPDATE bank_deposits SET interest_base = 1000 WHERE id = :i", i=dep_id)
    _post(client, "withdraw", {"deposit_id": dep_id, "amount": 300})
    assert _q(engine, "SELECT interest_base FROM bank_deposits WHERE id = :i", i=dep_id) == 700
    _deposit(client, 500)
    assert _q(engine, "SELECT interest_base FROM bank_deposits WHERE id = :i", i=dep_id) == 700


def test_term_deposit_of_another_bank_cannot_be_withdrawn_here(client, engine):
    dep_id = _deposit(client, 100, kind="term", term_days=7)["new_id"]
    _move_alpha(engine, 200)
    resp = _post(client, "withdraw", {"deposit_id": dep_id}, npc=BANKER_20)
    assert resp.status_code == 400 and "«Ост»" in resp.json()["detail"]
    view = client.get(_url(npc=BANKER_20), params={"character_id": ALPHA}).json()
    assert [(d["id"], d["here"]) for d in view["deposits"]] == [(dep_id, False)]          # all own deposits shown


def test_early_close_without_interest_and_matured_flag(client, engine):
    dep = _deposit(client, 100, kind="term", term_days=7)["view"]["deposits"][0]
    resp = _post(client, "withdraw", {"deposit_id": dep["id"], "amount": 5})               # amount ignored for term
    assert resp.status_code == 200
    assert resp.json()["message"] == "Срочный вклад закрыт досрочно: возвращено 100 марок"
    dep_id = _deposit(client, 100, kind="term", term_days=14)["new_id"]
    _sql(engine, "UPDATE bank_deposits SET matures_at = :t WHERE id = :i", t=_ago(hours=1), i=dep_id)
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["deposits"][0]["matured"] is True
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- disabled / missing bank

def test_disabled_bank_keeps_withdrawals_transfers_and_repayments(client, engine):
    dep_id = _deposit(client, 1000)["new_id"]
    term_id = _deposit(client, 200, kind="term", term_days=7)["new_id"]
    assert _post(client, "loan", {"amount": 500, "term_days": 7}).status_code == 200
    _sql(engine, "UPDATE econ_banks SET is_enabled = 0 WHERE region_id = 10")

    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["bank_enabled"] is False and view["max_loan_now"] == 0
    assert view["loan_refusal"] == "Банк этого региона сейчас не выдаёт займы"
    assert [r["region_id"] for r in view["bank_regions"]] == [20]
    demand = next(d for d in view["deposits"] if d["kind"] == "demand")
    assert demand["rate_day"] == 0                                                   # disabled bank pays nothing

    assert _post(client, "withdraw", {"deposit_id": dep_id, "amount": 100}).status_code == 200
    assert _post(client, "withdraw", {"deposit_id": term_id}).status_code == 200
    assert _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 100}).status_code == 200
    assert _post(client, "repay", {"amount": 500}).json()["message"] == "Займ погашен"
    resp = _post(client, "loan", {"amount": 100, "term_days": 7})
    assert resp.status_code == 409 and resp.json()["detail"] == "Банк этого региона сейчас не выдаёт займы"
    resp = _post(client, "send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 10, "amount": 100})
    assert resp.status_code == 409 and resp.json()["detail"] == "Банк региона «Ост» не принимает вклады"
    _assert_invariant(engine)


def test_region_without_bank_row(client, engine):
    _sql(engine, "DELETE FROM econ_banks WHERE region_id = 20")
    dep_id = _deposit(client, 500)["new_id"]
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 100})
    assert resp.status_code == 409 and resp.json()["detail"] == "Банк региона «Пашни» не принимает вклады"
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 999, "amount": 100})
    assert resp.status_code == 409 and resp.json()["detail"] == "Банк региона «удалённый регион» не принимает вклады"
    _move_alpha(engine, 200)
    view = client.get(_url(npc=BANKER_20), params={"character_id": ALPHA}).json()
    assert view["bank_enabled"] is False and view["region_name"] == "Пашни"
    assert view["loan_refusal"] == "Банк этого региона сейчас не выдаёт займы"
    assert _post(client, "deposit", {"kind": "demand", "amount": 100}, npc=BANKER_20).status_code == 409
    assert _post(client, "loan", {"amount": 100, "term_days": 7}, npc=BANKER_20).status_code == 409
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- reserve rule

def test_player_withdrawals_work_with_an_empty_bank(client, engine):
    dep_id = _deposit(client, 1000)["new_id"]
    term_id = _deposit(client, 500, kind="term", term_days=7)["new_id"]
    _drain_bank(engine)
    assert _acc(engine, "bank", 10) == 0 and _acc(engine, "bank_deposits", 10) == 1500

    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["max_loan_now"] == 0 and view["loan_refusal"] == "У банка сейчас нет денег на займы"
    resp = _post(client, "loan", {"amount": 100, "term_days": 7})
    assert resp.status_code == 409 and resp.json()["detail"] == "У банка сейчас нет денег на займы"

    assert _post(client, "withdraw", {"deposit_id": dep_id, "amount": 1000}).status_code == 200
    assert _post(client, "withdraw", {"deposit_id": term_id}).status_code == 200
    assert _wallet(engine) == 5000 and _acc(engine, "bank_deposits", 10) == 0
    _assert_invariant(engine)


def test_residents_reserve_is_never_lent(client, engine):
    _sql(engine, "UPDATE econ_banks SET resident_deposits = 10000 WHERE region_id = 10")    # reserve ceil(20 %)
    _drain_bank(engine, leave=2600)
    assert client.get(_url(), params={"character_id": ALPHA}).json()["max_loan_now"] == 600
    resp = _post(client, "loan", {"amount": 700, "term_days": 7})
    assert resp.status_code == 409 and resp.json()["detail"] == "Банк сейчас может выдать не больше 600 марок"
    assert _post(client, "loan", {"amount": 600, "term_days": 7}).status_code == 200
    assert _acc(engine, "bank", 10) == 2000
    _assert_invariant(engine)


def test_player_deposits_are_not_lendable(client, engine):
    _drain_bank(engine)
    _deposit(client, 3000)                                  # the vault holds 3000, the bank 0
    resp = _post(client, "loan", {"amount": 100, "term_days": 7})
    assert resp.status_code == 409 and resp.json()["detail"] == "У банка сейчас нет денег на займы"
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- commission math

@pytest.mark.parametrize("amount,fee", [(10, 1), (49, 1), (50, 1), (51, 2), (100, 2), (999, 20), (1000, 20),
                                        (1001, 21), (2500, 50)])
def test_transfer_commission(client, engine, amount, fee):
    dep_id = _deposit(client, 3000)["new_id"]
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": amount})
    assert resp.status_code == 200, resp.text
    assert f"комиссия {fee} " in resp.json()["message"]
    assert _q(engine, "SELECT amount FROM bank_deposits WHERE id = :i", i=dep_id) == 3000 - amount - fee
    assert _q(engine, "SELECT amount FROM bank_deposits WHERE region_id = 20 AND character_id = :c", c=ALPHA) == amount
    treasury, country = _acc(engine, "region_treasury", 10), _acc(engine, "country_treasury", 1)
    assert treasury + country == fee and country == fee // 10                 # 10 % of the commission (floor)
    assert _acc(engine, "bank_deposits", 10) == 3000 - amount - fee and _acc(engine, "bank_deposits", 20) == amount
    _assert_invariant(engine)


def test_transfer_exactly_all_with_fee_closes_the_source(client, engine):
    dep_id = _deposit(client, 102)["new_id"]
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 100})
    assert resp.status_code == 200, resp.text
    assert _q(engine, "SELECT status FROM bank_deposits WHERE id = :i", i=dep_id) == "closed"
    assert [d["region_id"] for d in resp.json()["view"]["deposits"]] == [20]
    _assert_invariant(engine)


def test_transfer_from_another_bank_pays_commission_to_the_bankers_region(client, engine):
    _move_alpha(engine, 200)
    dep_id = _deposit(client, 1000, npc=BANKER_20)["new_id"]
    _move_alpha(engine, 100)
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 10, "amount": 500})
    assert resp.status_code == 200, resp.text
    assert _acc(engine, "region_treasury", 20) == 0
    assert _acc(engine, "region_treasury", 10) + _acc(engine, "country_treasury", 1) == 10
    assert _acc(engine, "bank_deposits", 10) == 500 and _acc(engine, "bank_deposits", 20) == 490
    # a second transfer tops up the existing destination row (one demand deposit per bank)
    assert _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 10, "amount": 100}).status_code == 200
    assert _q(engine, "SELECT COUNT(*) FROM bank_deposits WHERE region_id = 10 AND status = 'open'") == 1
    _assert_invariant(engine)


def test_transfer_refusals_for_missing_closed_and_small(client, engine):
    assert _post(client, "transfer", {"deposit_id": 999, "to_region_id": 20, "amount": 100}).status_code == 404
    dep_id = _deposit(client, 100)["new_id"]
    _post(client, "withdraw", {"deposit_id": dep_id, "amount": 100})
    resp = _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 10})
    assert resp.status_code == 404 and resp.json()["detail"] == "Вклад не найден"
    dep_id = _deposit(client, 100)["new_id"]
    assert _post(client, "transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 5}).json()["detail"] \
        == "Минимальная сумма — 10"
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- send to a player

def test_send_from_wallet_commission_and_tax(client, engine):
    resp = _post(client, "send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 20, "amount": 1000})
    assert resp.status_code == 200, resp.text
    assert resp.json()["wallet"] == 5000 - 1020
    assert "Бета получит 1000 марок" in resp.json()["message"]
    assert _acc(engine, "region_treasury", 10) == 18 and _acc(engine, "country_treasury", 1) == 2
    assert _q(engine, "SELECT interest_base FROM bank_deposits WHERE character_id = :c", c=BETA) == 0
    _assert_invariant(engine)


def test_send_within_one_bank_moves_only_the_commission(client, engine):
    dep_id = _deposit(client, 1000)["new_id"]
    resp = _post(client, "send", {"source": "deposit", "deposit_id": dep_id, "recipient_name": "Бета",
                                  "to_region_id": 10, "amount": 500})
    assert resp.status_code == 200, resp.text
    assert _acc(engine, "bank_deposits", 10) == 1000 - 10                 # only the fee left the vault
    assert _q(engine, "SELECT amount FROM bank_deposits WHERE character_id = :c", c=BETA) == 500
    assert _q(engine, "SELECT COUNT(*) FROM econ_postings WHERE operation_id = :o AND leg_type = 'main'",
              o=resp.json()["operation_id"]) == 0
    _assert_invariant(engine)


def test_send_tops_up_the_recipients_row_without_touching_its_base(client, engine):
    _as_user(8)
    _deposit(client, 500, npc=BANKER_20, character_id=BETA)
    _sql(engine, "UPDATE bank_deposits SET interest_base = 400 WHERE character_id = :c", c=BETA)
    _as_user(7)
    resp = _post(client, "send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 20, "amount": 300})
    assert resp.status_code == 200, resp.text
    assert _q(engine, "SELECT COUNT(*) FROM bank_deposits WHERE character_id = :c", c=BETA) == 1
    assert _q(engine, "SELECT amount FROM bank_deposits WHERE character_id = :c", c=BETA) == 800
    assert _q(engine, "SELECT interest_base FROM bank_deposits WHERE character_id = :c", c=BETA) == 400
    _assert_invariant(engine)


def test_send_refusals_more(client, engine):
    term_id = _deposit(client, 100, kind="term", term_days=7)["new_id"]
    base = {"recipient_name": "Бета", "to_region_id": 20, "amount": 50}
    resp = _post(client, "send", {**base, "source": "deposit", "deposit_id": term_id})
    assert resp.status_code == 400 and resp.json()["detail"].startswith("Срочный вклад нельзя перевести")
    assert _post(client, "send", {**base, "source": "deposit", "deposit_id": 999}).status_code == 404
    resp = _post(client, "send", {**base, "source": "wallet", "to_region_id": 30})
    assert resp.status_code == 409 and resp.json()["detail"] == "Банк региона «Глушь» не принимает вклады"
    dep_id = _deposit(client, 100)["new_id"]
    resp = _post(client, "send", {**base, "source": "deposit", "deposit_id": dep_id, "amount": 99})
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("На вкладе недостаточно средств с учётом комиссии 2 ")
    resp = _post(client, "send", {**base, "source": "wallet", "amount": 4901})       # wallet is 4800 now
    assert resp.status_code == 400 and resp.json()["detail"].startswith("Недостаточно марок: нужно 5000 ")
    assert _wallet(engine) == 4800 and _wallet(engine, BETA) == 1000
    assert _q(engine, "SELECT COUNT(*) FROM bank_deposits WHERE character_id = :c", c=BETA) == 0
    _assert_invariant(engine)


def test_send_from_a_deposit_in_another_bank(client, engine):
    _move_alpha(engine, 200)
    dep_id = _deposit(client, 1000, npc=BANKER_20)["new_id"]
    _move_alpha(engine, 100)
    resp = _post(client, "send", {"source": "deposit", "deposit_id": dep_id, "recipient_name": "Бета",
                                  "to_region_id": 10, "amount": 200})
    assert resp.status_code == 200, resp.text
    assert _acc(engine, "bank_deposits", 20) == 1000 - 204 and _acc(engine, "bank_deposits", 10) == 200
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- loans

def test_loan_cap_follows_level(client, engine):
    _sql(engine, "UPDATE characters SET level = 30 WHERE id = :i", i=ALPHA)
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["loan_cap"] == 8000 and view["max_loan_now"] == 8000
    assert _post(client, "loan", {"amount": 8001, "term_days": 28}).json()["detail"].startswith("Ваш лимит займа — 8")
    assert _post(client, "loan", {"amount": 5, "term_days": 28}).json()["detail"] == "Минимальная сумма — 10"
    resp = _post(client, "loan", {"amount": 8000, "term_days": 28})
    assert resp.status_code == 200, resp.text
    loan = resp.json()["view"]["loan"]
    assert loan["term_days"] == 28 and loan["rate_day"] == pytest.approx(0.005)
    assert loan["penalty_rate_day"] == pytest.approx(0.01)
    assert datetime.fromisoformat(loan["due_at"]) - datetime.fromisoformat(loan["issued_at"]) == timedelta(days=28)
    _assert_invariant(engine)


def test_one_loan_across_banks_and_repay_at_any_banker(client, engine):
    assert _post(client, "loan", {"amount": 500, "term_days": 14}).status_code == 200
    _move_alpha(engine, 200)
    resp = _post(client, "loan", {"amount": 100, "term_days": 7}, npc=BANKER_20)
    assert resp.status_code == 409 and resp.json()["detail"] == "У вас уже есть займ — сначала погасите его"
    resp = _post(client, "repay", {"amount": 500}, npc=BANKER_20)                       # money goes to B(10)
    assert resp.status_code == 200 and resp.json()["message"] == "Займ погашен"
    assert _acc(engine, "bank", 10) == BANK_CAPITAL and _acc(engine, "bank", 20) == 0
    assert _q(engine, "SELECT COUNT(*) FROM bank_loans WHERE active_character_id IS NOT NULL") == 0
    _move_alpha(engine, 100)
    assert _post(client, "loan", {"amount": 100, "term_days": 7}).status_code == 200      # a new loan is fine again
    assert _q(engine, "SELECT COUNT(*) FROM bank_loans") == 2
    _assert_invariant(engine)


def test_loan_interest_is_counted_to_now(client, engine):
    assert _post(client, "loan", {"amount": 1000, "term_days": 7}).status_code == 200
    t = _ago(days=2)
    _sql(engine, "UPDATE bank_loans SET issued_at = :t, accrued_at = :t", t=t)
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["loan"]["debt"] == 1010 and view["loan"]["overdue"] is False        # 1000 x 0.5 % x 2 days
    assert _q(engine, "SELECT debt FROM bank_loans") == 1000                         # GET stores nothing
    resp = _post(client, "repay", {"amount": 10})
    assert resp.status_code == 200 and resp.json()["view"]["loan"]["debt"] == 1000
    assert _q(engine, "SELECT interest_total FROM bank_loans") == 10
    assert _post(client, "repay", {"amount": 1000}).json()["message"] == "Займ погашен"
    assert _acc(engine, "bank", 10) == BANK_CAPITAL + 10 and _wallet(engine) == 5000 - 10
    _assert_invariant(engine)


def test_overdue_debtor_flow(client, engine):
    assert _post(client, "loan", {"amount": 1000, "term_days": 7}).status_code == 200
    t = _ago(days=1)
    _sql(engine, "UPDATE bank_loans SET due_at = :t, accrued_at = :t", t=t)
    resp = _post(client, "loan", {"amount": 100, "term_days": 7})
    assert resp.status_code == 409 and resp.json()["detail"] == "Вы в списке должников — новые займы не выдаются"
    summary = client.get(f"{BANK}/summary", params={"character_id": ALPHA}).json()
    assert summary["debtor"] is True and summary["loan"]["overdue"] is True
    assert summary["loan"]["debt"] == 1015 and summary["loan"]["penalty_total"] == 10   # (0.5 % + 1 %) x 1 day
    resp = _post(client, "repay", {"amount": 500})
    assert resp.status_code == 200 and resp.json()["view"]["debtor"] is True          # partial: still a debtor
    assert _q(engine, "SELECT status FROM bank_loans") == "overdue"
    resp = _post(client, "repay", {"amount": 515})
    assert resp.json()["message"] == "Займ погашен" and resp.json()["view"]["debtor"] is False
    assert _acc(engine, "bank", 10) == BANK_CAPITAL + 15
    _assert_invariant(engine)


def test_overdue_debt_stops_at_the_cap(client, engine):
    assert _post(client, "loan", {"amount": 1000, "term_days": 7}).status_code == 200
    t = _ago(days=400)
    _sql(engine, "UPDATE bank_loans SET issued_at = :t, due_at = :t, accrued_at = :t", t=t)
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["loan"]["debt"] == 2000 and view["debtor"] is True
    assert view["loan_refusal"] == "Вы в списке должников — новые займы не выдаются"


def test_repay_refusals_and_whole_rest(client, engine):
    assert _post(client, "loan", {"amount": 800, "term_days": 7}).status_code == 200
    _ledger_move(engine, core.AccountRef.character(ALPHA), core.AccountRef.region(10), 5800 - 100)
    assert _post(client, "repay", {"amount": 500}).json()["detail"] == "Недостаточно марок"
    assert _post(client, "repay", {"amount": 5}).json()["detail"] == "Минимальная сумма — 10"
    assert _post(client, "repay", {"amount": 95}).status_code == 200
    _ledger_move(engine, core.AccountRef.region(10), core.AccountRef.character(ALPHA), 2000)
    assert _post(client, "repay", {"amount": 700}).status_code == 200
    resp = _post(client, "repay", {"amount": 5})                                    # the whole rest (5) is allowed
    assert resp.status_code == 200 and resp.json()["message"] == "Займ погашен"
    assert _q(engine, "SELECT paid_total FROM bank_loans") == 800
    _assert_invariant(engine)


def test_loan_view_states(client, engine):
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["loan"] is None and view["debtor"] is False
    _drain_bank(engine, leave=300)
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["max_loan_now"] == 300 and view["loan_refusal"] is None             # min(cap, lendable)
    _drain_bank(engine, leave=9)
    view = client.get(_url(), params={"character_id": ALPHA}).json()
    assert view["max_loan_now"] == 0 and view["loan_refusal"] == "У банка сейчас нет денег на займы"


# --------------------------------------------------------------------------------------------- summary

def test_summary_spans_banks_and_admin_needs_read(client, engine):
    _deposit(client, 300)
    assert _post(client, "loan", {"amount": 400, "term_days": 7}).status_code == 200
    _move_alpha(engine, 200)
    _deposit(client, 200, kind="term", term_days=7, npc=BANKER_20)
    assert _post(client, "send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 20, "amount": 100},
                 npc=BANKER_20).status_code == 200
    data = client.get(f"{BANK}/summary", params={"character_id": ALPHA}).json()
    assert data["total_deposits"] == 500
    assert sorted((d["region_id"], d["kind"]) for d in data["deposits"]) == [(10, "demand"), (20, "term")]
    assert data["loan"]["region_id"] == 10 and data["loan"]["region_name"] == "Ост"
    _as_user(99, permissions=["economy:read"])
    assert client.get(f"{BANK}/summary", params={"character_id": 999}).status_code == 404
    assert client.get(f"{BANK}/summary", params={"character_id": BETA}).json()["total_deposits"] == 100
    _as_user(99, permissions=["economy:settings"])                                  # not the read permission
    assert client.get(f"{BANK}/summary", params={"character_id": BETA}).status_code == 403
    _assert_invariant(engine)


# --------------------------------------------------------------------------------------------- invariant / full flow

def test_full_flow_keeps_world_sum_and_vault(client, engine):
    for action, body in (("deposit", {"kind": "demand", "amount": 2000}),
                         ("deposit", {"kind": "term", "term_days": 28, "amount": 700}),
                         ("loan", {"amount": 900, "term_days": 14}),
                         ("send", {"source": "wallet", "recipient_name": "Бета", "to_region_id": 10, "amount": 333})):
        assert _post(client, action, body).status_code == 200, action
        _assert_invariant(engine)
    dep_id = _demand_id(engine)
    term_id = _q(engine, "SELECT id FROM bank_deposits WHERE kind = 'term'")
    _credit_term_interest(engine, term_id, 40)
    _assert_invariant(engine)
    for action, body in (("transfer", {"deposit_id": dep_id, "to_region_id": 20, "amount": 777}),
                         ("send", {"source": "deposit", "deposit_id": dep_id, "recipient_name": "Бета",
                                   "to_region_id": 20, "amount": 111}),
                         ("withdraw", {"deposit_id": term_id}),
                         ("withdraw", {"deposit_id": dep_id, "amount": 50}),
                         ("repay", {"amount": 450}), ("repay", {"amount": 450})):
        resp = _post(client, action, body)
        assert resp.status_code == 200, (action, resp.text)
        _assert_invariant(engine)
    assert _acc(engine, "bank", 10) == BANK_CAPITAL          # 40 paid as interest, then burnt back on early close
    assert _q(engine, "SELECT amount FROM bank_deposits WHERE id = :i", i=dep_id) == 2000 - 793 - 114 - 50
