"""FEAT-181 B3 — sanity checks of the economy API (the full suite is Q1).

Runs against an isolated SQLite DB built from the shared ledger DDL (econ_contract_cases) plus the
few foreign tables the summary reads (characters.is_npc, auction tables).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core
import economy_api
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.econ_contract_cases import SEED_SQL, SQLITE_DDL

EXTRA_DDL = [
    "ALTER TABLE characters ADD COLUMN is_npc INTEGER NOT NULL DEFAULT 0",
    """CREATE TABLE auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER NOT NULL DEFAULT 0,
        current_bidder_id INTEGER NULL, status VARCHAR(20) NOT NULL DEFAULT 'active')""",
    "CREATE TABLE auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER NOT NULL DEFAULT 0)",
    # FEAT-184: the summary checks the vaults against the open deposit rows
    """CREATE TABLE bank_deposits (id INTEGER PRIMARY KEY, region_id INTEGER NOT NULL,
        status VARCHAR(8) NOT NULL DEFAULT 'open', amount INTEGER NOT NULL DEFAULT 0,
        interest_accrued INTEGER NOT NULL DEFAULT 0)""",
]

ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]


@pytest.fixture
def econ_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        for ddl in SQLITE_DDL + EXTRA_DDL:
            conn.execute(text(ddl))
        for sql, params in SEED_SQL:
            conn.execute(text(sql), params)
        # Seed balances the way genesis does: one emission op funding Alice with 100.
        for sql in [
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (1, 'emission', 0, 'Эмиссия', -100, 1)",
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (2, 'character', 1, 'Alice', 0, 0)",
            "INSERT INTO econ_operations (id, op_type, source_service, comment) "
            "VALUES (1, 'genesis', 'character-service', 'Начальная эмиссия')",
            "INSERT INTO econ_postings (operation_id, from_account_id, to_account_id, amount) VALUES (1, 1, 2, 100)",
            "UPDATE characters SET currency_balance = 100 WHERE id = 1",
        ]:
            conn.execute(text(sql))
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    econ_core.invalidate_settings_cache()
    yield engine
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)
    econ_core.invalidate_settings_cache()


def _as_user(permissions):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=7, username="tester", role="admin", permissions=permissions)


def test_public_currency(econ_db):
    resp = TestClient(app).get("/characters/economy/currency")
    assert resp.status_code == 200
    assert resp.json() == {"name": "Марки", "genitive": "марок", "one": "марка", "few": "марки",
                           "many": "марок", "short": "ṃ"}


def test_admin_requires_auth_and_permission(econ_db):
    client = TestClient(app)
    assert client.get("/characters/admin/economy/summary").status_code == 401
    _as_user(["economy:read"])
    assert client.get("/characters/admin/economy/summary").status_code == 200
    body = {"account_id": 1, "amount": 10, "comment": "тест"}
    assert client.post("/characters/admin/economy/emission", json=body).status_code == 403


def test_summary_emission_and_journal(econ_db):
    _as_user(ALL_PERMS)
    client = TestClient(app)
    summary = client.get("/characters/admin/economy/summary").json()
    assert summary["invariant"]["ok"] is True
    assert summary["totals"]["issued"] == 100 and summary["totals"]["players"] == 100
    region_acc = summary["countries"][0]["regions"][0]["account_id"]  # treasuries created on demand

    resp = client.post("/characters/admin/economy/emission",
                       json={"account_id": region_acc, "amount": 500, "comment": "  Стартовая казна "})
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance"] == 500

    summary = client.get("/characters/admin/economy/summary").json()
    assert summary["invariant"]["ok"] is True
    assert summary["totals"]["issued"] == 600 and summary["totals"]["region_treasuries"] == 500

    ops = client.get("/characters/admin/economy/operations", params={"op_type": "admin_emission"}).json()
    assert ops["total"] == 1
    op = ops["items"][0]
    assert op["comment"] == "Стартовая казна" and op["actor_user_id"] == 7
    assert op["postings"][0]["from"]["kind"] == "emission" and op["postings"][0]["amount"] == 500


def test_adjust_rules(econ_db):
    _as_user(ALL_PERMS)
    client = TestClient(app)
    accounts = client.get("/characters/admin/economy/accounts",
                          params={"kind": "character", "q": "Bob"}).json()
    assert accounts["total"] == 1
    bob = accounts["items"][0]["account_id"]  # Bob had no account yet: created for the page

    resp = client.post("/characters/admin/economy/adjust", json={"account_id": bob, "delta": -1, "comment": "баг"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Недостаточно средств на счёте"
    resp = client.post("/characters/admin/economy/adjust", json={"account_id": bob, "delta": 30, "comment": "баг"})
    assert resp.status_code == 200 and resp.json()["balance"] == 30
    resp = client.post("/characters/admin/economy/adjust", json={"account_id": 1, "delta": 5, "comment": "баг"})
    assert resp.status_code == 400  # emission account is not adjustable
    resp = client.post("/characters/admin/economy/emission", json={"account_id": bob, "amount": 5, "comment": "баг"})
    assert resp.status_code == 400  # emission only into treasuries
    assert client.get("/characters/admin/economy/summary").json()["invariant"]["ok"] is True


def test_settings_validation_and_cache(econ_db):
    _as_user(ALL_PERMS)
    client = TestClient(app)
    good = {"currency": {"name": "Крона", "genitive": "крон", "one": "крона", "few": "кроны",
                         "many": "крон", "short": "кр."}, "country_tax_rate": 0.2}
    bad = {**good, "currency": {**good["currency"], "name": "<script>"}}
    assert client.put("/characters/admin/economy/settings", json=bad).status_code == 422
    assert client.put("/characters/admin/economy/settings",
                      json={**good, "country_tax_rate": 0.6}).status_code == 422
    client.get("/characters/economy/currency")  # warm the cache
    resp = client.put("/characters/admin/economy/settings", json=good)
    assert resp.status_code == 200 and resp.json() == good
    assert client.get("/characters/economy/currency").json()["name"] == "Крона"
