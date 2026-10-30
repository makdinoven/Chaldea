"""FEAT-184 B6: admin bank API + economy integration (contract 3.10) on SQLite.

Covers: RBAC (401 / 403 / read vs settings), banks list / detail / debtors, the «Банк есть» flag with the one-time
capital seed, capital in / out bounds, loan write-off, «Заполнить регионы» opening banks in capitals and ports,
``bank_enabled`` in the regions list, ``has_bank`` on the public card, the summary bank totals and the vault
sub-invariant, bank accounts forbidden for admin adjustment.

World:
    country 1; regions 10 «Столица» (capital, 5000), 20 «Гавань» (port, 3000), 30 «Нива» (agrarian, 4000),
    40 «Глушь» (no economy row); locations 100 @10, 200 @20
    players 1 «Альфа» (user 7) @100, 2 «Бета» (user 8) @200; bankers 50 @100, 51 @100 dead, 52 @200
"""

import importlib.util
import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core as core
import econ_ledger
import economy_api
import economy_bank_crud as bank_crud
import models
from auth_http import UserRead, get_current_user_via_http
from main import app

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "028_econ_living_regions.py")
_spec = importlib.util.spec_from_file_location("migration_028_for_bank_admin", MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

BASE = "/characters/admin/economy"
ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]
SOURCE = "character-service"
ALPHA, BETA = 1, 2
START_CAPITAL = 20_000          # SimParams default bank_start_capital
COMMENT = "Тестовый комментарий"

EXTRA_DDL = [
    """CREATE TABLE items (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, item_type VARCHAR(32) NOT NULL,
        item_rarity VARCHAR(32) NOT NULL DEFAULT 'common', resource_subcategory VARCHAR(32) NULL,
        is_food INTEGER NOT NULL DEFAULT 0, price INTEGER NOT NULL DEFAULT 0, image VARCHAR(255) NULL)""",
    """CREATE TABLE quest_objectives (id INTEGER PRIMARY KEY, quest_id INTEGER NOT NULL DEFAULT 1,
        objective_type VARCHAR(32) NOT NULL, target_id INTEGER NULL)""",
    """CREATE TABLE auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER NOT NULL DEFAULT 0,
        current_bidder_id INTEGER NULL, status VARCHAR(20) NOT NULL DEFAULT 'active')""",
    "CREATE TABLE auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER NOT NULL DEFAULT 0)",
]


# --------------------------------------------------------------------------------------------- fixtures

@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=eng)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    db = factory()
    for ddl in EXTRA_DDL:
        db.execute(text(ddl))
    for i, g in enumerate(mig.GROUPS, 1):
        db.add(models.EconGoodsGroup(code=g[0], name=g[1], sort_order=i, base_price=g[2], norm_per_1000=g[3],
                                     norm_days=g[4], prosperity_elasticity=g[5], price_elasticity=g[6],
                                     is_food=bool(g[7])))
    db.flush()
    for group_code, inputs in mig.INPUTS.items():
        for input_code, ratio in inputs:
            db.add(models.EconGroupInput(group_code=group_code, input_code=input_code, ratio=ratio))
    for i, t in enumerate(mig.TEMPLATES, 1):
        db.add(models.EconRegionTemplate(code=t[0], name=t[1], description=t[2], settlement_noun=t[3],
                                         noun_gender=t[4], default_population=t[5], tax_rate=t[6], sort_order=i))
    db.flush()
    for t in mig.TEMPLATES:
        for group_code, prod, cmult in mig.template_goods(t[0]):
            db.add(models.EconTemplateGood(template_code=t[0], group_code=group_code, production_per_1000=prod,
                                           consumption_mult=cmult))
    db.add(models.EconSimSettings(id=1, tick_enabled=True, params=dict(mig.DEFAULT_PARAMS)))
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд')"))
    db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Столица', 1), (20, 'Гавань', 1), "
                    "(30, 'Нива', 1), (40, 'Глушь', 1)"))
    db.execute(text("INSERT INTO Locations (id, name, region_id) VALUES (100, 'Площадь', 10), (200, 'Пристань', 20)"))
    people = [  # id, name, user, npc, role, status, location
        (ALPHA, "Альфа", 7, False, None, "alive", 100), (BETA, "Бета", 8, False, None, "alive", 200),
        (50, "Банкир", None, True, "banker", "alive", 100), (51, "Мёртвый банкир", None, True, "banker", "dead", 100),
        (52, "Банкир гавани", None, True, "banker", "alive", 200),
    ]
    with econ_ledger.allow_direct_balance_write(db):
        for cid, name, user, npc, role, status, loc in people:
            db.add(models.Character(id=cid, name=name, user_id=user, id_subrace=1, id_class=1, id_race=1,
                                    appearance="-", avatar="-", is_npc=npc, npc_role=role, npc_status=status,
                                    current_location_id=loc, level=2, currency_balance=0))
        db.flush()
    for region_id, template, population in ((10, "capital", 5000), (20, "port", 3000), (30, "agrarian", 4000)):
        db.add(models.EconRegion(region_id=region_id, template_code=template, population=population, tax_rate=0.1))
    db.flush()
    for region_id in (10, 20, 30):                         # treasuries with money for the seed
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                   apply_tax=False, region_id=region_id,
                                   legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.region(region_id),
                                                  50_000)])
    db.commit()
    db.close()

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    core.invalidate_settings_cache()
    eng.factory = factory
    yield eng
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)
    core.invalidate_settings_cache()
    eng.dispose()


def _as_user(permissions, user_id=7):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username="tester", role="moderator", permissions=list(permissions))


@pytest.fixture
def api(engine):
    _as_user(ALL_PERMS)
    return TestClient(app)


def _q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _bal(engine, kind, ref_id):
    return int(_q(engine, "SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r", k=kind, r=ref_id)
               or 0)


def _ok_summary(api):
    resp = api.get(f"{BASE}/summary")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["invariant"]["ok"] is True, data["invariant"]
    return data


def _open_bank(api, region_id=10, **body):
    resp = api.put(f"{BASE}/banks/{region_id}", json={"is_enabled": True, **body})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _add_loan(engine, *, character_id=ALPHA, region_id=10, principal=1000, due_in_days=7, issued_days_ago=0):
    """A loan issued like the player flow (``B(X) -> C``), optionally already past due."""
    db = engine.factory()
    now = bank_crud.now_utc()
    issued = now - timedelta(days=issued_days_ago)
    loan = models.BankLoan(character_id=character_id, region_id=region_id, status="active", principal=principal,
                           debt=principal, rate_day=0.005, penalty_rate_day=0.01, term_days=7, issued_at=issued,
                           due_at=issued + timedelta(days=due_in_days), accrued_at=issued, interest_carry=0,
                           active_character_id=character_id)
    db.add(loan)
    db.flush()
    econ_ledger.post_operation(db, op_type=core.OP_LOAN_ISSUE, source_service=SOURCE, region_id=region_id,
                               legs=[core.Leg(core.AccountRef.bank(region_id), core.AccountRef.character(character_id),
                                              principal)])
    loan_id = int(loan.id)
    db.commit()
    db.close()
    return loan_id


def _add_deposit(engine, *, character_id=ALPHA, region_id=10, amount=500, kind="demand"):
    db = engine.factory()
    now = bank_crud.now_utc()
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                               legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.character(character_id),
                                              amount)])
    row = models.BankDeposit(character_id=character_id, region_id=region_id, kind=kind, status="open", amount=amount,
                             interest_base=0, interest_accrued=0, interest_total=0, interest_carry=0,
                             rate_day=0.002 if kind == "term" else None, term_days=7 if kind == "term" else None,
                             opened_at=now, matures_at=now + timedelta(days=7) if kind == "term" else None,
                             accrued_at=now, demand_owner_id=character_id if kind == "demand" else None)
    db.add(row)
    db.flush()
    econ_ledger.post_operation(db, op_type=core.OP_BANK_DEPOSIT, source_service=SOURCE, region_id=region_id,
                               legs=[core.Leg(core.AccountRef.character(character_id),
                                              core.AccountRef.bank_deposits(region_id), amount)])
    deposit_id = int(row.id)
    db.commit()
    db.close()
    return deposit_id


# --------------------------------------------------------------------------------------------- RBAC

ENDPOINTS = [
    ("get", f"{BASE}/banks", None, "economy:read"),
    ("get", f"{BASE}/banks/debtors", None, "economy:read"),
    ("get", f"{BASE}/banks/10", None, "economy:read"),
    ("put", f"{BASE}/banks/10", {"is_enabled": True}, "economy:settings"),
    ("post", f"{BASE}/banks/10/capital", {"direction": "in", "amount": 100, "comment": COMMENT}, "economy:settings"),
    ("post", f"{BASE}/banks/loans/1/write-off", {"comment": COMMENT}, "economy:settings"),
]
IDS = [f"{e[0]} {e[1][len(BASE):]}" for e in ENDPOINTS]


@pytest.mark.parametrize("method,url,body,perm", ENDPOINTS, ids=IDS)
def test_bank_admin_401_without_token(engine, method, url, body, perm):
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 401


@pytest.mark.parametrize("method,url,body,perm", ENDPOINTS, ids=IDS)
def test_bank_admin_403_without_permission(engine, method, url, body, perm):
    _as_user([p for p in ALL_PERMS if p != perm])
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 403
    assert _q(engine, "SELECT COUNT(*) FROM econ_banks") == 0


def test_moderator_with_read_reads_but_cannot_change(engine):
    _as_user(["economy:read"])
    client = TestClient(app)
    assert client.get(f"{BASE}/banks").status_code == 200
    assert client.get(f"{BASE}/banks/debtors").status_code == 200
    for method, url, body, perm in ENDPOINTS:
        if perm == "economy:settings":
            assert getattr(client, method)(url, json=body).status_code == 403


# --------------------------------------------------------------------------------------------- flag + seed

def test_flag_creates_bank_and_seeds_capital_once(api, engine):
    assert api.get(f"{BASE}/banks/10").status_code == 404          # no bank yet (region editor reads this)
    item = _open_bank(api, 10)
    assert item["enabled"] is True and item["own_funds"] == START_CAPITAL
    assert item["capital_seeded_at"] is not None
    assert item["region_name"] == "Столица" and item["country_name"] == "Мидденгерд" and item["simulated"] is True
    assert [b["npc_id"] for b in item["bankers"]] == [50]           # dead banker 51 not counted
    assert _bal(engine, "region_treasury", 10) == 50_000 - START_CAPITAL
    assert _q(engine, "SELECT accrued_at FROM econ_banks WHERE region_id = 10") is not None
    op = _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'bank_capital'")
    assert op == 1

    off = api.put(f"{BASE}/banks/10", json={"is_enabled": False}).json()
    assert off["enabled"] is False and off["own_funds"] == START_CAPITAL
    again = _open_bank(api, 10)                                    # re-toggle: no second seed
    assert again["own_funds"] == START_CAPITAL
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'bank_capital'") == 1
    _ok_summary(api)


def test_flag_without_seed_and_with_poor_treasury(api, engine):
    item = _open_bank(api, 10, seed_capital=False)
    assert item["own_funds"] == 0 and item["capital_seeded_at"] is None
    # Treasury 3000 < start capital: the seed takes what is there, and only once.
    db = engine.factory()
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_ADJUST, source_service=SOURCE, comment="тест",
                               apply_tax=False, legs=[core.Leg(core.AccountRef.region(20),
                                                               core.AccountRef.adjustment(), 47_000)])
    db.commit()
    db.close()
    item = _open_bank(api, 20)
    assert item["own_funds"] == 3000 and _bal(engine, "region_treasury", 20) == 0


def test_flag_off_creates_disabled_row_and_unknown_region_404(api, engine):
    resp = api.put(f"{BASE}/banks/10", json={"is_enabled": False})
    assert resp.status_code == 200 and resp.json()["enabled"] is False and resp.json()["own_funds"] == 0
    resp = api.put(f"{BASE}/banks/999", json={"is_enabled": True})
    assert resp.status_code == 404 and resp.json()["detail"] == "Регион не найден"
    assert api.put(f"{BASE}/banks/10", json={"is_enabled": "yes"}).status_code == 422


# --------------------------------------------------------------------------------------------- list / detail

ITEM_KEYS = {"region_id", "region_name", "country_name", "enabled", "simulated", "bankers", "own_funds", "vault",
             "deposits_sum", "vault_ok", "deposits_count", "term_count", "resident_deposits", "resident_loans",
             "reserve", "lendable", "loans_count", "loans_debt", "overdue_count", "rate_factor", "demand_rate_day",
             "term_rates", "capital_seeded_at", "last_tick_at", "last_stats"}


def test_list_detail_and_totals(api, engine):
    assert api.get(f"{BASE}/banks").json() == {"items": [], "totals": {
        "banks": 0, "enabled": 0, "own_funds": 0, "player_deposits": 0, "resident_deposits": 0,
        "player_loans_debt": 0, "resident_loans": 0, "debtors": 0}}
    _open_bank(api, 10)
    api.put(f"{BASE}/banks/30", json={"is_enabled": False})
    _add_deposit(engine, amount=700)
    _add_deposit(engine, amount=300, kind="term")
    _add_loan(engine, character_id=BETA, principal=1000)

    data = api.get(f"{BASE}/banks").json()
    items = {i["region_id"]: i for i in data["items"]}
    assert set(items) == {10, 30}
    for item in items.values():
        assert set(item) == ITEM_KEYS
    capital = items[10]
    assert capital["vault"] == capital["deposits_sum"] == 1000 and capital["vault_ok"] is True
    assert capital["deposits_count"] == 2 and capital["term_count"] == 1
    assert capital["own_funds"] == START_CAPITAL - 1000 and capital["lendable"] == START_CAPITAL - 1000
    assert capital["loans_count"] == 1 and capital["loans_debt"] >= 1000 and capital["overdue_count"] == 0
    assert [t["term_days"] for t in capital["term_rates"]] == [7, 14, 28]
    assert capital["rate_factor"] == 1.0 and capital["demand_rate_day"] == pytest.approx(0.001)
    assert capital["last_stats"] == {}
    assert data["totals"]["banks"] == 2 and data["totals"]["enabled"] == 1
    assert data["totals"]["player_deposits"] == 1000 and data["totals"]["own_funds"] == START_CAPITAL - 1000

    detail = api.get(f"{BASE}/banks/10").json()
    assert detail["item"]["region_id"] == 10
    assert {d["character_name"] for d in detail["deposits"]} == {"Альфа"}
    assert all(d["status"] == "open" and d["character_id"] == ALPHA for d in detail["deposits"])
    assert detail["deposits"][0]["id"] > detail["deposits"][1]["id"]            # newest first
    assert [(l["character_id"], l["character_name"], l["principal"]) for l in detail["loans"]] == [(BETA, "Бета",
                                                                                                    1000)]
    assert api.get(f"{BASE}/banks/40").status_code == 404
    _ok_summary(api)


def test_vault_drift_is_flagged(api, engine):
    _open_bank(api, 10)
    deposit_id = _add_deposit(engine, amount=500)
    with engine.begin() as conn:                                                  # rows drift from the vault
        conn.execute(text("UPDATE bank_deposits SET amount = 400 WHERE id = :i"), {"i": deposit_id})
    item = api.get(f"{BASE}/banks").json()["items"][0]
    assert item["vault_ok"] is False and item["vault"] == 500 and item["deposits_sum"] == 400
    summary = api.get(f"{BASE}/summary").json()
    assert summary["invariant"]["ok"] is False
    assert summary["invariant"]["bank_deposits_expected"] == 400
    assert summary["invariant"]["bank_deposits_actual"] == 500


# --------------------------------------------------------------------------------------------- debtors / write-off

def test_debtors_and_write_off(api, engine):
    _open_bank(api, 10)
    current = _add_loan(engine, character_id=ALPHA, principal=500)
    overdue = _add_loan(engine, character_id=BETA, principal=1000, due_in_days=7, issued_days_ago=10)

    debtors = api.get(f"{BASE}/banks/debtors").json()
    assert [d["loan_id"] for d in debtors] == [overdue]
    debtor = debtors[0]
    assert debtor["character_name"] == "Бета" and debtor["region_name"] == "Столица"
    assert debtor["overdue_days"] == 3 and debtor["penalty_total"] > 0 and debtor["debt"] > 1000
    assert api.get(f"{BASE}/banks").json()["totals"]["debtors"] == 1

    resp = api.post(f"{BASE}/banks/loans/{overdue}/write-off", json={"comment": COMMENT})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["status"] == "written_off" and out["debt"] == 0 and out["overdue"] is False
    row = dict(engine.connect().execute(text(
        "SELECT written_off, debt, active_character_id, closed_by_user_id, note FROM bank_loans WHERE id = :i"),
        {"i": overdue}).mappings().first())
    assert row["written_off"] == debtor["debt"] and row["debt"] == 0 and row["active_character_id"] is None
    assert row["closed_by_user_id"] == 7 and row["note"] == COMMENT
    assert api.get(f"{BASE}/banks/debtors").json() == []
    resp = api.post(f"{BASE}/banks/loans/{overdue}/write-off", json={"comment": COMMENT})
    assert resp.status_code == 409 and resp.json()["detail"] == "Займ уже закрыт"
    assert api.post(f"{BASE}/banks/loans/9999/write-off", json={"comment": COMMENT}).status_code == 404
    assert api.post(f"{BASE}/banks/loans/{current}/write-off", json={"comment": "x"}).status_code == 422
    # No money moved by the write-off.
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type NOT IN "
                      "('admin_emission', 'bank_capital', 'loan_issue')") == 0
    _ok_summary(api)


# --------------------------------------------------------------------------------------------- capital

def test_capital_in_and_out_bounds(api, engine):
    _open_bank(api, 10)                                     # bank 20 000, treasury 30 000
    body = {"direction": "in", "amount": 30_001, "comment": COMMENT}
    resp = api.post(f"{BASE}/banks/10/capital", json=body)
    assert resp.status_code == 400 and resp.json()["detail"].startswith("В казне региона только")

    resp = api.post(f"{BASE}/banks/10/capital", json={**body, "amount": 5000})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["bank_balance"] == 25_000 and data["treasury_balance"] == 25_000 and data["operation_id"]

    with engine.begin() as conn:                            # residents' reserve: 20 % of 10 000
        conn.execute(text("UPDATE econ_banks SET resident_deposits = 10000 WHERE region_id = 10"))
    resp = api.post(f"{BASE}/banks/10/capital", json={"direction": "out", "amount": 23_001, "comment": COMMENT})
    assert resp.status_code == 400 and resp.json()["detail"].startswith("Банк может вернуть не больше")
    resp = api.post(f"{BASE}/banks/10/capital", json={"direction": "out", "amount": 23_000, "comment": COMMENT})
    assert resp.status_code == 200 and resp.json()["bank_balance"] == 2000
    # The capital moves are not taxed (no country leg).
    assert _q(engine, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 0

    assert api.post(f"{BASE}/banks/30/capital", json=body).status_code == 404       # no bank row
    for bad in ({**body, "amount": 0}, {**body, "direction": "up"}, {**body, "comment": ""},
                {**body, "amount": 1.5}):
        assert api.post(f"{BASE}/banks/10/capital", json=bad).status_code == 422
    _ok_summary(api)


def test_bank_accounts_cannot_be_adjusted(api, engine):
    _open_bank(api, 10)
    account_id = _q(engine, "SELECT id FROM econ_accounts WHERE kind = 'bank' AND ref_id = 10")
    resp = api.post(f"{BASE}/adjust", json={"account_id": account_id, "delta": -100, "comment": COMMENT})
    assert resp.status_code == 400 and resp.json()["detail"] == "Этот счёт нельзя корректировать"


# --------------------------------------------------------------------------------------------- economy integration

FILL = {"comment": "Заполнение для теста"}


def test_fill_opens_banks_in_capitals_and_ports_once(api, engine):
    resp = api.post(f"{BASE}/regions/fill", json=FILL)
    assert resp.status_code == 200, resp.text
    assert resp.json()["banks_opened"] == [10, 20]
    for region_id in (10, 20):
        assert _bal(engine, "bank", region_id) == START_CAPITAL
    assert _q(engine, "SELECT COUNT(*) FROM econ_banks WHERE region_id = 30") == 0          # agrarian: no bank
    second = api.post(f"{BASE}/regions/fill", json=FILL).json()
    assert second["banks_opened"] == []
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'bank_capital'") == 2

    regions = {r["region_id"]: r for r in api.get(f"{BASE}/regions").json()["items"]}
    assert regions[10]["bank_enabled"] is True and regions[30]["bank_enabled"] is False
    assert api.get(f"{BASE}/regions/20").json()["bank_enabled"] is True
    _ok_summary(api)


def test_fill_without_open_banks(api, engine):
    resp = api.post(f"{BASE}/regions/fill", json={**FILL, "open_banks": False})
    assert resp.status_code == 200 and resp.json()["banks_opened"] == []
    assert _q(engine, "SELECT COUNT(*) FROM econ_banks") == 0


def test_region_card_has_bank_in_both_shapes(api, engine):
    _open_bank(api, 10)
    _open_bank(api, 40)                                     # «Глушь»: not simulated -> hidden card
    app.dependency_overrides.pop(get_current_user_via_http, None)
    client = TestClient(app)
    hidden = client.get("/characters/economy/regions/40/card").json()
    assert hidden == {"region_id": 40, "participating": False, "has_bank": True, "events": []}
    assert client.get("/characters/economy/regions/30/card").json()["has_bank"] is False
    assert client.get("/characters/economy/regions/0/card").json()["has_bank"] is False


def test_summary_bank_totals(api, engine):
    _open_bank(api, 10)
    _add_deposit(engine, amount=800)
    totals = _ok_summary(api)["totals"]
    assert totals["banks"] == START_CAPITAL and totals["bank_deposits"] == 800
    accounts = {a["kind"] for a in api.get(f"{BASE}/summary").json()["system_accounts"]}
    assert not accounts & {"bank", "bank_deposits"}         # regional accounts are not «system» ones


# --------------------------------------------------------------------------------------------- Q3: RBAC by role

def test_admin_role_passes_and_plain_user_without_permissions_is_refused(engine):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=1, username="admin", role="admin", permissions=list(ALL_PERMS))
    client = TestClient(app)
    assert client.put(f"{BASE}/banks/10", json={"is_enabled": True}).status_code == 200
    assert client.post(f"{BASE}/banks/10/capital",
                       json={"direction": "out", "amount": 100, "comment": COMMENT}).status_code == 200

    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=9, username="player", role="user", permissions=[])
    for method, url, body, _perm in ENDPOINTS:
        assert getattr(client, method)(url, **({"json": body} if body else {})).status_code == 403, url
    # a role alone is not enough: an admin-role token without economy:* permissions is refused too
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=1, username="admin", role="admin", permissions=[])
    assert client.get(f"{BASE}/banks").status_code == 403
    assert client.put(f"{BASE}/banks/10", json={"is_enabled": False}).status_code == 403
    assert _q(engine, "SELECT is_enabled FROM econ_banks WHERE region_id = 10") in (1, True)


# --------------------------------------------------------------------------------------------- Q3: seed once

def test_seed_happens_once_across_flag_toggles_and_fills(api, engine):
    def seeds():
        return _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'bank_capital'")

    item = _open_bank(api, 10, seed_capital=False)                  # switched on without capital
    assert item["own_funds"] == 0 and item["capital_seeded_at"] is None and seeds() == 0
    api.put(f"{BASE}/banks/10", json={"is_enabled": False})
    item = _open_bank(api, 10)                                      # first switch-on with the seed
    assert item["own_funds"] == START_CAPITAL and seeds() == 1
    for _ in range(2):
        api.put(f"{BASE}/banks/10", json={"is_enabled": False})
        assert _open_bank(api, 10)["own_funds"] == START_CAPITAL
    assert seeds() == 1

    first = api.post(f"{BASE}/regions/fill", json=FILL).json()      # 10 already open: only the port opens + seeds
    assert first["banks_opened"] == [20] and seeds() == 2
    api.put(f"{BASE}/banks/10", json={"is_enabled": False})
    again = api.post(f"{BASE}/regions/fill", json=FILL).json()      # re-opens 10, never seeds it twice
    assert again["banks_opened"] == [10] and seeds() == 2
    assert _bal(engine, "bank", 10) == START_CAPITAL and _bal(engine, "bank", 20) == START_CAPITAL
    _ok_summary(api)


def test_seed_from_an_empty_treasury_counts_as_seeded(api, engine):
    db = engine.factory()
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_ADJUST, source_service=SOURCE, comment="тест",
                               apply_tax=False, legs=[core.Leg(core.AccountRef.region(10),
                                                               core.AccountRef.adjustment(), 50_000)])
    db.commit()
    db.close()
    item = _open_bank(api, 10)
    assert item["own_funds"] == 0 and item["capital_seeded_at"] is not None
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'bank_capital'") == 0

    db = engine.factory()                                           # the treasury fills up later
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                               apply_tax=False, legs=[core.Leg(core.AccountRef.emission(),
                                                               core.AccountRef.region(10), 40_000)])
    db.commit()
    db.close()
    api.put(f"{BASE}/banks/10", json={"is_enabled": False})
    assert _open_bank(api, 10)["own_funds"] == 0                    # re-toggling never seeds
    assert _bal(engine, "region_treasury", 10) == 40_000
    _ok_summary(api)


# --------------------------------------------------------------------------------------------- Q3: capital bounds

def test_capital_out_never_exceeds_lendable_nor_touches_player_deposits(api, engine):
    _open_bank(api, 10)                                             # bank 20 000
    _add_deposit(engine, amount=5_000)                              # player money sits in the vault, not the bank
    _add_loan(engine, character_id=BETA, principal=3_000)           # bank 17 000 left
    with engine.begin() as conn:                                    # residents: reserve ceil(1 001 × 0.2) = 201
        conn.execute(text("UPDATE econ_banks SET resident_deposits = 1001 WHERE region_id = 10"))
    item = api.get(f"{BASE}/banks/10").json()["item"]
    assert item["own_funds"] == 17_000 and item["reserve"] == 201 and item["lendable"] == 16_799

    resp = api.post(f"{BASE}/banks/10/capital", json={"direction": "out", "amount": 16_800, "comment": COMMENT})
    assert resp.status_code == 400 and resp.json()["detail"].startswith("Банк может вернуть не больше")
    resp = api.post(f"{BASE}/banks/10/capital", json={"direction": "out", "amount": 16_799, "comment": COMMENT})
    assert resp.status_code == 200, resp.text
    assert resp.json()["bank_balance"] == 201                       # only the reserve stays
    assert _bal(engine, "bank_deposits", 10) == 5_000               # the vault is untouched
    resp = api.post(f"{BASE}/banks/10/capital", json={"direction": "out", "amount": 1, "comment": COMMENT})
    assert resp.status_code == 400                                  # nothing lendable left
    # in: exactly the treasury is fine, one coin more is not
    treasury = _bal(engine, "region_treasury", 10)
    resp = api.post(f"{BASE}/banks/10/capital", json={"direction": "in", "amount": treasury + 1, "comment": COMMENT})
    assert resp.status_code == 400
    resp = api.post(f"{BASE}/banks/10/capital", json={"direction": "in", "amount": treasury, "comment": COMMENT})
    assert resp.status_code == 200 and resp.json()["treasury_balance"] == 0
    summary = _ok_summary(api)
    assert summary["invariant"]["bank_deposits_expected"] == summary["invariant"]["bank_deposits_actual"] == 5_000


# --------------------------------------------------------------------------------------------- Q3: write-off

def test_write_off_of_a_current_loan_moves_no_money(api, engine):
    _open_bank(api, 10)
    loan = _add_loan(engine, character_id=ALPHA, principal=700)
    wallet = int(_q(engine, "SELECT currency_balance FROM characters WHERE id = :i", i=ALPHA))
    bank = _bal(engine, "bank", 10)
    resp = api.post(f"{BASE}/banks/loans/{loan}/write-off", json={"comment": COMMENT})
    assert resp.status_code == 200 and resp.json()["status"] == "written_off"
    assert _q(engine, "SELECT written_off FROM bank_loans WHERE id = :i", i=loan) == 700
    assert int(_q(engine, "SELECT currency_balance FROM characters WHERE id = :i", i=ALPHA)) == wallet
    assert _bal(engine, "bank", 10) == bank
    item = api.get(f"{BASE}/banks/10").json()
    assert item["loans"] == [] and item["item"]["loans_count"] == 0
    _ok_summary(api)


# --------------------------------------------------------------------------------------------- Q3: fill

def test_fill_opens_banks_only_where_residents_will_live(api, engine):
    with engine.begin() as conn:                                    # the port has no residents yet
        conn.execute(text("UPDATE econ_regions SET population = 0 WHERE region_id = 20"))
    resp = api.post(f"{BASE}/regions/fill", json={**FILL, "population_from_template": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["banks_opened"] == [10]
    assert _q(engine, "SELECT COUNT(*) FROM econ_banks WHERE region_id IN (20, 30)") == 0
    # the same port filled with the template population gets its bank
    resp = api.post(f"{BASE}/regions/fill", json={**FILL, "region_ids": [20], "population_from_template": True})
    assert resp.status_code == 200 and resp.json()["banks_opened"] == [20]
    resp = api.post(f"{BASE}/regions/fill", json={**FILL, "region_ids": [30]})       # agrarian: never
    assert resp.status_code == 200 and resp.json()["banks_opened"] == []
    _ok_summary(api)


# --------------------------------------------------------------------------------------------- Q3: run + runs list

RUN_BANK_KEYS = {"banks_processed", "bank_ops_posted", "bank_failures", "bank_failed_region_ids",
                 "bank_interest_paid", "loans_overdue", "loans_collected", "collected_amount", "banks_closed"}


def test_manual_run_reports_bank_counters_and_the_runs_list(api, engine):
    assert api.post(f"{BASE}/regions/fill", json=FILL).json()["banks_opened"] == [10, 20]
    _add_deposit(engine, amount=1_000)
    overdue = _add_loan(engine, character_id=BETA, region_id=20, principal=500, issued_days_ago=10)
    six_hours_ago = bank_crud.now_utc() - timedelta(hours=6)       # a period passed since the deposit / opening
    with engine.begin() as conn:
        conn.execute(text("UPDATE bank_deposits SET accrued_at = :t, interest_base = amount"), {"t": six_hours_ago})
        conn.execute(text("UPDATE econ_banks SET accrued_at = :t"), {"t": six_hours_ago})

    resp = api.post(f"{BASE}/sim/run")
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert RUN_BANK_KEYS <= set(run)
    assert run["banks_processed"] == 2 and run["bank_failures"] == 0 and run["bank_failed_region_ids"] == []
    assert run["loans_collected"] == 1 and run["collected_amount"] == 500 and run["banks_closed"] == 0
    assert run["loans_overdue"] == 1                                # Бета had only the 500 of the loan
    assert _q(engine, "SELECT status FROM bank_loans WHERE id = :i", i=overdue) == "overdue"
    assert int(_q(engine, "SELECT currency_balance FROM characters WHERE id = :i", i=BETA)) == 0

    listed = api.get(f"{BASE}/sim").json()["runs"][0]
    assert listed["id"] == run["id"]
    assert listed["bank_ops_posted"] == run["bank_ops_posted"] >= 1
    assert listed["bank_failures"] == 0 and listed["loans_collected"] == 1
    summary = _ok_summary(api)
    assert summary["invariant"]["bank_deposits_expected"] == summary["invariant"]["bank_deposits_actual"] >= 1_000

    # a second run straight after: no time passed for the banks, nothing collected twice
    again = api.post(f"{BASE}/sim/run").json()
    assert again["loans_collected"] == 0 and again["bank_failures"] == 0
    assert _q(engine, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'loan_collect'") == 1
    _ok_summary(api)


def test_banks_live_in_regions_with_lore_populations(api, engine):
    """FEAT-186: lore populations (4 000 000 / 1 500 000 / 120 000) at scale 100 — fill opens the banks, residents
    deposit and borrow at simulated size, bank passes run without failures and the invariant holds."""
    with engine.begin() as conn:
        for region_id, population in ((10, 4_000_000), (20, 1_500_000), (30, 120_000)):
            conn.execute(text("UPDATE econ_regions SET population = :p WHERE region_id = :r"),
                         {"p": population, "r": region_id})
    assert api.post(f"{BASE}/regions/fill", json=FILL).json()["banks_opened"] == [10, 20]
    _add_deposit(engine, amount=1_000)
    for _ in range(2):
        with engine.begin() as conn:
            conn.execute(text("UPDATE econ_banks SET accrued_at = :t"),
                         {"t": bank_crud.now_utc() - timedelta(hours=6)})
        run = api.post(f"{BASE}/sim/run").json()
        assert run["status"] == "done" and run["banks_processed"] == 2 and run["bank_failures"] == 0, run
        _ok_summary(api)
    purse = _bal(engine, "population_purse", 10)
    deposits = int(_q(engine, "SELECT resident_deposits FROM econ_banks WHERE region_id = 10"))
    assert purse > 0 and 0 < deposits < purse                     # residents keep a share of savings in the bank
    assert _bal(engine, "bank", 10) >= 0 and _bal(engine, "bank", 20) >= 0
    summary = _ok_summary(api)
    assert summary["invariant"]["bank_deposits_expected"] == summary["invariant"]["bank_deposits_actual"]
