"""FEAT-181 Q1: economy API of character-service (section 3.6) — full suite.

Complements tests/test_economy_api_sanity.py (B3). Runs against an isolated SQLite DB built from
the shared ledger DDL plus the foreign tables the summary reads (characters.is_npc, auction tables).
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
from tests.econ_contract_cases import SEED_SQL, SQLITE_DDL, WORLD_SUM_SQL

EXTRA_DDL = [
    "ALTER TABLE characters ADD COLUMN is_npc INTEGER NOT NULL DEFAULT 0",
    """CREATE TABLE auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER NOT NULL DEFAULT 0,
        current_bidder_id INTEGER NULL, status VARCHAR(20) NOT NULL DEFAULT 'active')""",
    "CREATE TABLE auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER NOT NULL DEFAULT 0)",
]

ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]
CURRENCY = {"name": "Марки", "genitive": "марок", "one": "марка", "few": "марки", "many": "марок",
            "short": "мар."}
GOOD_SETTINGS = {"currency": {"name": "Крона", "genitive": "крон", "one": "крона", "few": "кроны",
                              "many": "крон", "short": "кр."}, "country_tax_rate": 0.2}

# Account ids fixed by the seed below.
EMISSION_ID, ALICE_ACC, ADJUSTMENT_ID, WORLD_ID, ESCROW_ID, STORAGE_ID = 1, 2, 3, 4, 5, 6


@pytest.fixture
def econ_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        for ddl in SQLITE_DDL + EXTRA_DDL:
            conn.execute(text(ddl))
        for sql, params in SEED_SQL:
            conn.execute(text(sql), params)
        conn.execute(text("UPDATE characters SET is_npc = 1 WHERE id = 4"))  # Dave is an NPC
        for sql in [
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (1, 'emission', 0, 'Эмиссия', -150, 1)",
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (2, 'character', 1, 'Alice', 0, 0)",
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (3, 'adjustment', 0, 'Корректировки', 0, 1)",
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (4, 'world_treasury', 0, 'Казна Скитальцев', 0, 1)",
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (5, 'auction_escrow', 0, 'Ставки аукциона', 0, 0)",
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (6, 'auction_storage', 0, 'Хранилище аукциона', 0, 0)",
            "INSERT INTO econ_accounts (id, kind, ref_id, name, balance, allow_negative) "
            "VALUES (7, 'character', 4, 'Dave', 0, 0)",
            "INSERT INTO econ_operations (id, op_type, source_service, comment, created_at) "
            "VALUES (1, 'genesis', 'character-service', 'Начальная эмиссия', '2026-10-01 10:00:00')",
            "INSERT INTO econ_postings (operation_id, from_account_id, to_account_id, amount) VALUES (1, 1, 2, 100)",
            "INSERT INTO econ_postings (operation_id, from_account_id, to_account_id, amount) VALUES (1, 1, 7, 50)",
            "UPDATE characters SET currency_balance = 100 WHERE id = 1",
            "UPDATE characters SET currency_balance = 50 WHERE id = 4",
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


def _as_user(permissions, user_id=7):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username="tester", role="moderator", permissions=permissions)


@pytest.fixture
def client(econ_db):
    _as_user(ALL_PERMS)
    return TestClient(app)


def _q(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _account_id(engine, kind, ref_id=0):
    return _q(engine, "SELECT id FROM econ_accounts WHERE kind = :k AND ref_id = :r", k=kind, r=ref_id)


def _summary(client):
    resp = client.get("/characters/admin/economy/summary")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _assert_world_closes(engine, client):
    assert _q(engine, WORLD_SUM_SQL) == 0
    assert _summary(client)["invariant"]["ok"] is True


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------

ENDPOINTS = [
    ("get", "/characters/admin/economy/summary", None, "economy:read"),
    ("get", "/characters/admin/economy/accounts", None, "economy:read"),
    ("get", "/characters/admin/economy/operations", None, "economy:read"),
    ("get", "/characters/admin/economy/settings", None, "economy:read"),
    ("post", "/characters/admin/economy/emission", {"account_id": WORLD_ID, "amount": 10, "comment": "тест"},
     "economy:emit"),
    ("post", "/characters/admin/economy/adjust", {"account_id": ALICE_ACC, "delta": 10, "comment": "тест"},
     "economy:adjust"),
    ("put", "/characters/admin/economy/settings", GOOD_SETTINGS, "economy:settings"),
]


@pytest.mark.parametrize("method,url,body,perm", ENDPOINTS, ids=[f"{e[0]} {e[1]}" for e in ENDPOINTS])
def test_admin_endpoints_401_without_token(econ_db, method, url, body, perm):
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 401


@pytest.mark.parametrize("method,url,body,perm", ENDPOINTS, ids=[f"{e[0]} {e[1]}" for e in ENDPOINTS])
def test_admin_endpoints_403_without_their_permission(econ_db, method, url, body, perm):
    _as_user([p for p in ALL_PERMS if p != perm] + ["characters:update", "npcs:update"])
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Недостаточно прав"
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_operations") == 1     # nothing posted


@pytest.mark.parametrize("method,url,body,perm", ENDPOINTS, ids=[f"{e[0]} {e[1]}" for e in ENDPOINTS])
def test_admin_endpoints_allowed_with_only_their_permission(econ_db, method, url, body, perm):
    _as_user([perm])
    resp = getattr(TestClient(app), method)(url, **({"json": body} if body else {}))
    assert resp.status_code == 200, resp.text


def test_moderator_read_only(econ_db):
    """Moderator gets economy:read only: can look, cannot emit / adjust / change settings."""
    _as_user(["economy:read"])
    client = TestClient(app)
    assert client.get("/characters/admin/economy/summary").status_code == 200
    for method, url, body, _perm in ENDPOINTS[4:]:
        assert getattr(client, method)(url, json=body).status_code == 403


def test_public_currency_needs_no_auth(econ_db):
    resp = TestClient(app).get("/characters/economy/currency")
    assert resp.status_code == 200 and resp.json() == CURRENCY


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summary_shape(client):
    s = _summary(client)
    assert set(s) == {"currency", "totals", "invariant", "countries", "system_accounts", "settings"}
    assert s["currency"] == CURRENCY
    assert s["totals"] == {"issued": 150, "held": 150, "players": 100, "npcs": 50, "escrow": 0,
                           "auction_storage": 0, "region_treasuries": 0, "country_treasuries": 0,
                           "world_treasury": 0, "population_purses": 0}
    assert s["invariant"] == {"ok": True, "ledger_sum": 0, "escrow_expected": 0, "escrow_actual": 0,
                              "storage_expected": 0, "storage_actual": 0, "drifting_characters": []}
    assert s["settings"] == {"country_tax_rate": 0.1}
    # Treasuries of every existing country / region are created for the page.
    assert [(c["country_id"], c["name"], [r["region_id"] for r in c["regions"]]) for c in s["countries"]] == [
        (1, "Country A", [10]), (2, "Country B", [20])]
    for country in s["countries"]:
        assert set(country) == {"account_id", "country_id", "name", "balance", "is_active", "regions"}
        assert country["is_active"] is True and country["balance"] == 0
        for region in country["regions"]:
            assert set(region) == {"account_id", "region_id", "name", "balance", "is_active",
                                   "purse_account_id", "purse_balance"}
            assert region["purse_account_id"] is None and region["purse_balance"] is None
    kinds = [a["kind"] for a in s["system_accounts"]]
    assert kinds == ["emission", "adjustment", "world_treasury", "auction_escrow", "auction_storage"]
    assert set(s["system_accounts"][0]) == {"account_id", "kind", "name", "balance"}
    assert s["system_accounts"][0]["balance"] == -150


def test_summary_detects_drift(client, econ_db):
    """A balance written around the ledger shows up as drift and breaks the invariant."""
    with econ_db.begin() as conn:
        conn.execute(text("UPDATE characters SET currency_balance = 130 WHERE id = 1"))
    s = _summary(client)
    inv = s["invariant"]
    assert inv["ok"] is False
    assert inv["ledger_sum"] == 30
    assert inv["drifting_characters"] == [{"character_id": 1, "name": "Alice", "balance": 130, "ledger": 100}]


def test_summary_drift_of_character_without_account(client, econ_db):
    with econ_db.begin() as conn:
        conn.execute(text("UPDATE characters SET currency_balance = 5 WHERE id = 3"))
    inv = _summary(client)["invariant"]
    assert inv["ok"] is False
    assert [d["character_id"] for d in inv["drifting_characters"]] == [3]
    assert inv["drifting_characters"][0]["ledger"] == 0


def test_summary_drift_list_is_capped(client, econ_db):
    with econ_db.begin() as conn:
        for cid in range(100, 160):
            conn.execute(text("INSERT INTO characters (id, name, currency_balance) VALUES (:i, :n, 1)"),
                         {"i": cid, "n": f"c{cid}"})
    inv = _summary(client)["invariant"]
    assert len(inv["drifting_characters"]) == 50 and inv["ledger_sum"] == 60


def test_summary_detects_escrow_and_storage_mismatch(client, econ_db):
    with econ_db.begin() as conn:
        conn.execute(text("INSERT INTO auction_listings (current_bid, current_bidder_id, status) "
                          "VALUES (40, 1, 'active')"))
        conn.execute(text("INSERT INTO auction_listings (current_bid, current_bidder_id, status) "
                          "VALUES (99, NULL, 'active')"))   # no bidder: not in escrow
        conn.execute(text("INSERT INTO auction_listings (current_bid, current_bidder_id, status) "
                          "VALUES (77, 2, 'sold')"))         # not active: not in escrow
        conn.execute(text("INSERT INTO auction_storage (gold_amount) VALUES (12)"))
    inv = _summary(client)["invariant"]
    assert inv["ok"] is False
    assert (inv["escrow_expected"], inv["escrow_actual"]) == (40, 0)
    assert (inv["storage_expected"], inv["storage_actual"]) == (12, 0)
    assert inv["ledger_sum"] == 0 and inv["drifting_characters"] == []


def test_summary_tree_keeps_deleted_and_orphan_treasuries(client, econ_db):
    """A deleted country keeps its snapshot name; a region whose country is unknown is grouped apart."""
    _summary(client)  # create treasury accounts with name snapshots
    with econ_db.begin() as conn:
        conn.execute(text("DELETE FROM Regions WHERE id = 20"))
        conn.execute(text("DELETE FROM Countries WHERE id = 2"))
        conn.execute(text("UPDATE econ_accounts SET is_active = 0 WHERE kind IN ('region_treasury', "
                          "'country_treasury') AND ref_id IN (2, 20)"))
    s = _summary(client)
    names = {c["name"]: c for c in s["countries"]}
    assert names["Country B"]["is_active"] is False            # snapshot name
    assert names["Country B"]["regions"] == []
    orphan = names["Без страны"]
    assert orphan["account_id"] is None and orphan["country_id"] is None
    assert [(r["region_id"], r["name"], r["is_active"]) for r in orphan["regions"]] == [(20, "Region B1", False)]


# ---------------------------------------------------------------------------
# Emission / adjust
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,ref_id", [("region_treasury", 10), ("country_treasury", 2), ("world_treasury", 0)])
def test_emission_into_each_treasury_kind(client, econ_db, kind, ref_id):
    _summary(client)
    acc = _account_id(econ_db, kind, ref_id)
    resp = client.post("/characters/admin/economy/emission",
                       json={"account_id": acc, "amount": 1000, "comment": "Стартовая казна"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"operation_id", "account_id", "balance"}
    assert body["account_id"] == acc and body["balance"] == 1000
    assert _q(econ_db, "SELECT leg_type FROM econ_postings WHERE operation_id = :o", o=body["operation_id"]) == "main"
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 0   # admin ops untaxed
    region = _q(econ_db, "SELECT region_id FROM econ_operations WHERE id = :o", o=body["operation_id"])
    assert region == (ref_id if kind == "region_treasury" else None)
    s = _summary(client)
    assert s["totals"]["issued"] == 1150 and s["invariant"]["ok"] is True


@pytest.mark.parametrize("account_id", [ALICE_ACC, ESCROW_ID, STORAGE_ID, EMISSION_ID, ADJUSTMENT_ID])
def test_emission_only_into_treasuries(client, econ_db, account_id):
    resp = client.post("/characters/admin/economy/emission",
                       json={"account_id": account_id, "amount": 5, "comment": "тест"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == ("Эмиссия возможна только в казну региона, страны, Казну Скитальцев "
                                     "или кошелёк жителей региона")
    _assert_world_closes(econ_db, client)


def test_emission_unknown_account_404(client):
    resp = client.post("/characters/admin/economy/emission", json={"account_id": 9999, "amount": 5, "comment": "тест"})
    assert resp.status_code == 404 and resp.json()["detail"] == "Счёт не найден"


def test_closed_account_rejects_emission_and_adjust(client, econ_db):
    with econ_db.begin() as conn:
        conn.execute(text("UPDATE econ_accounts SET is_active = 0 WHERE id IN (:w, :a)"), {"w": WORLD_ID, "a": ALICE_ACC})
    r1 = client.post("/characters/admin/economy/emission", json={"account_id": WORLD_ID, "amount": 5, "comment": "тест"})
    r2 = client.post("/characters/admin/economy/adjust", json={"account_id": ALICE_ACC, "delta": 5, "comment": "тест"})
    assert r1.status_code == 400 and r1.json()["detail"] == "Счёт закрыт"
    assert r2.status_code == 400 and r2.json()["detail"] == "Счёт закрыт"
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_operations") == 1


def test_adjust_character_of_deleted_row_rejected(client, econ_db):
    with econ_db.begin() as conn:
        conn.execute(text("DELETE FROM characters WHERE id = 1"))
    resp = client.post("/characters/admin/economy/adjust", json={"account_id": ALICE_ACC, "delta": 5, "comment": "тест"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Персонаж этого счёта удалён"


def test_adjust_character_up_and_down(client, econ_db):
    resp = client.post("/characters/admin/economy/adjust",
                       json={"account_id": ALICE_ACC, "delta": -100, "comment": "Возврат за баг"})
    assert resp.status_code == 200 and resp.json()["balance"] == 0
    resp = client.post("/characters/admin/economy/adjust",
                       json={"account_id": ALICE_ACC, "delta": -1, "comment": "Возврат за баг"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Недостаточно средств на счёте"
    resp = client.post("/characters/admin/economy/adjust",
                       json={"account_id": ALICE_ACC, "delta": 25, "comment": "Компенсация"})
    assert resp.status_code == 200 and resp.json()["balance"] == 25
    s = _summary(client)
    adj = next(a for a in s["system_accounts"] if a["kind"] == "adjustment")
    assert adj["balance"] == 75                       # 100 removed, 25 created
    assert s["totals"]["issued"] == 75 and s["invariant"]["ok"] is True
    ops = client.get("/characters/admin/economy/operations", params={"op_type": "admin_adjust"}).json()
    assert ops["total"] == 2 and all(op["actor_user_id"] == 7 for op in ops["items"])


def test_adjust_treasury_may_go_negative(client, econ_db):
    resp = client.post("/characters/admin/economy/adjust",
                       json={"account_id": WORLD_ID, "delta": -300, "comment": "Долг казны"})
    assert resp.status_code == 200 and resp.json()["balance"] == -300
    _assert_world_closes(econ_db, client)


@pytest.mark.parametrize("account_id", [EMISSION_ID, ADJUSTMENT_ID, ESCROW_ID, STORAGE_ID])
def test_adjust_forbidden_accounts(client, account_id):
    resp = client.post("/characters/admin/economy/adjust", json={"account_id": account_id, "delta": 5, "comment": "тест"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Этот счёт нельзя корректировать"


@pytest.mark.parametrize("body", [
    {"account_id": WORLD_ID, "amount": 0, "comment": "тест"},
    {"account_id": WORLD_ID, "amount": -5, "comment": "тест"},
    {"account_id": WORLD_ID, "amount": 10 ** 12 + 1, "comment": "тест"},
    {"account_id": WORLD_ID, "amount": "100", "comment": "тест"},
    {"account_id": WORLD_ID, "amount": 1.5, "comment": "тест"},
    {"account_id": "4", "amount": 5, "comment": "тест"},
    {"account_id": WORLD_ID, "amount": 5, "comment": "ab"},
    {"account_id": WORLD_ID, "amount": 5, "comment": "   ab   "},
    {"account_id": WORLD_ID, "amount": 5, "comment": "x" * 501},
    {"account_id": WORLD_ID, "amount": 5},
    {"account_id": WORLD_ID, "amount": 5, "comment": None},
])
def test_emission_validation(client, econ_db, body):
    assert client.post("/characters/admin/economy/emission", json=body).status_code == 422
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_operations") == 1


def test_emission_upper_bound_accepted(client, econ_db):
    resp = client.post("/characters/admin/economy/emission",
                       json={"account_id": WORLD_ID, "amount": 10 ** 12, "comment": "x" * 500})
    assert resp.status_code == 200 and resp.json()["balance"] == 10 ** 12


@pytest.mark.parametrize("body", [
    {"account_id": ALICE_ACC, "delta": 0, "comment": "тест"},
    {"account_id": ALICE_ACC, "delta": 10 ** 12 + 1, "comment": "тест"},
    {"account_id": ALICE_ACC, "delta": -(10 ** 12 + 1), "comment": "тест"},
    {"account_id": ALICE_ACC, "delta": "5", "comment": "тест"},
    {"account_id": ALICE_ACC, "delta": 5, "comment": ""},
    {"account_id": ALICE_ACC, "delta": 5},
])
def test_adjust_validation(client, econ_db, body):
    assert client.post("/characters/admin/economy/adjust", json=body).status_code == 422
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_operations") == 1


def test_emission_comment_with_markup_is_stored_verbatim_not_executed(client, econ_db):
    """Comments are free text (JSON-escaped by the API, rendered as text by the UI)."""
    resp = client.post("/characters/admin/economy/emission",
                       json={"account_id": WORLD_ID, "amount": 5, "comment": "<b>x</b>'; DROP TABLE econ_postings; --"})
    assert resp.status_code == 200
    assert _q(econ_db, "SELECT comment FROM econ_operations WHERE op_type = 'admin_emission'") == \
        "<b>x</b>'; DROP TABLE econ_postings; --"
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_postings") == 3


# ---------------------------------------------------------------------------
# Accounts listing
# ---------------------------------------------------------------------------

def test_accounts_shape_order_and_lazy_character_accounts(client, econ_db):
    resp = client.get("/characters/admin/economy/accounts")
    assert resp.status_code == 200
    page = resp.json()
    assert set(page) == {"items", "total", "page", "page_size"}
    assert page["page"] == 1 and page["page_size"] == 50
    # 5 singletons + 4 characters (treasuries are not created by this listing)
    assert page["total"] == 9
    for item in page["items"]:
        assert set(item) == {"account_id", "kind", "ref_id", "name", "balance", "is_active"}
    kinds = [i["kind"] for i in page["items"]]
    assert kinds[-4:] == ["character"] * 4          # characters listed after system accounts
    chars = {i["ref_id"]: i for i in page["items"] if i["kind"] == "character"}
    assert chars[1]["balance"] == 100 and chars[4]["balance"] == 50
    # Bob and Carol had no account: created so the admin can address them.
    assert _account_id(econ_db, "character", 2) == chars[2]["account_id"]
    assert _account_id(econ_db, "character", 3) == chars[3]["account_id"]


def test_accounts_filters_and_paging(client):
    page = client.get("/characters/admin/economy/accounts", params={"kind": "character", "page_size": 2}).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    page2 = client.get("/characters/admin/economy/accounts",
                       params={"kind": "character", "page_size": 2, "page": 2}).json()
    assert {i["ref_id"] for i in page["items"]}.isdisjoint({i["ref_id"] for i in page2["items"]})
    found = client.get("/characters/admin/economy/accounts", params={"q": "  ali  "}).json()
    assert [i["name"] for i in found["items"]] == ["Alice"]
    _summary(client)  # creates treasuries
    regions = client.get("/characters/admin/economy/accounts", params={"q": "Region"}).json()
    assert {i["kind"] for i in regions["items"]} == {"region_treasury"} and regions["total"] == 2


@pytest.mark.parametrize("q", [
    "' OR 1=1 --", "'; DROP TABLE characters; --", '" OR ""="', "%", "_", "!", "Al%", "\\",
])
def test_accounts_search_is_parameterised(client, econ_db, q):
    resp = client.get("/characters/admin/economy/accounts", params={"q": q})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0                 # LIKE wildcards are escaped, nothing matches
    assert _q(econ_db, "SELECT COUNT(*) FROM characters") == 4


@pytest.mark.parametrize("params,status", [
    ({"kind": "bank"}, 400),
    ({"kind": "character'--"}, 400),
    ({"q": "x" * 101}, 400),
    ({"page": 0}, 422),
    ({"page_size": 101}, 422),
    ({"page_size": 0}, 422),
])
def test_accounts_validation(client, params, status):
    assert client.get("/characters/admin/economy/accounts", params=params).status_code == status


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

def test_operations_shape_and_filters(client, econ_db):
    _summary(client)
    region_acc = _account_id(econ_db, "region_treasury", 10)
    client.post("/characters/admin/economy/emission", json={"account_id": region_acc, "amount": 70, "comment": "казна"})
    client.post("/characters/admin/economy/adjust", json={"account_id": ALICE_ACC, "delta": 5, "comment": "бонус"})

    page = client.get("/characters/admin/economy/operations").json()
    assert set(page) == {"items", "total", "page", "page_size"}
    assert page["total"] == 3
    assert [op["op_type"] for op in page["items"]] == ["admin_adjust", "admin_emission", "genesis"]  # id DESC
    op = page["items"][1]
    assert set(op) == {"id", "op_type", "created_at", "source_service", "location_id", "region_id",
                       "actor_user_id", "comment", "metadata", "postings"}
    assert op["region_id"] == 10 and op["source_service"] == "character-service"
    assert op["postings"] == [{
        "from": {"account_id": EMISSION_ID, "kind": "emission", "ref_id": 0, "name": "Эмиссия"},
        "to": {"account_id": region_acc, "kind": "region_treasury", "ref_id": 10, "name": "Region A1"},
        "amount": 70, "leg_type": "main"}]
    genesis = page["items"][2]
    assert [p["to"]["name"] for p in genesis["postings"]] == ["Alice", "Dave"]

    def total(**params):
        r = client.get("/characters/admin/economy/operations", params=params)
        assert r.status_code == 200, r.text
        return r.json()["total"]

    assert total(account_id=ALICE_ACC) == 2
    assert total(character_id=1) == 2
    assert total(character_id=2) == 0                # no account yet -> empty, not an error
    assert total(account_id=ALICE_ACC, character_id=4) == 1    # both filters: genesis only
    assert total(region_id=10) == 1
    assert total(op_type="genesis") == 1
    assert total(date_from="2026-10-01", date_to="2026-10-01") == 1   # inclusive day
    assert total(date_to="2026-09-30") == 0
    assert total(page_size=1, page=3) == 3


@pytest.mark.parametrize("params,status", [
    ({"op_type": "steal"}, 400),
    ({"op_type": "genesis' OR '1'='1"}, 400),
    ({"date_from": "2026-10-05", "date_to": "2026-10-01"}, 400),
    ({"date_from": "yesterday"}, 422),
    ({"account_id": 0}, 422),
    ({"page_size": 101}, 422),
])
def test_operations_validation(client, params, status):
    assert client.get("/characters/admin/economy/operations", params=params).status_code == status


# ---------------------------------------------------------------------------
# FEAT-182: population purse + exclude_op_type
# ---------------------------------------------------------------------------

def _create_purse(engine, region_id):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO econ_accounts (kind, ref_id, name, balance, allow_negative) "
            "VALUES ('population_purse', :r, 'snapshot', 0, 0)"), {"r": region_id})
    return _account_id(engine, "population_purse", region_id)


def test_emission_into_population_purse(client, econ_db):
    _summary(client)
    purse = _create_purse(econ_db, 10)
    resp = client.post("/characters/admin/economy/emission",
                       json={"account_id": purse, "amount": 700, "comment": "Кошелёк жителей"})
    assert resp.status_code == 200, resp.text
    op_id = resp.json()["operation_id"]
    assert resp.json()["balance"] == 700
    assert _q(econ_db, "SELECT region_id FROM econ_operations WHERE id = :o", o=op_id) == 10
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 0

    s = _summary(client)
    assert s["invariant"]["ok"] is True
    assert s["totals"]["population_purses"] == 700 and s["totals"]["held"] == 850
    region = next(r for c in s["countries"] for r in c["regions"] if r["region_id"] == 10)
    assert region["purse_account_id"] == purse and region["purse_balance"] == 700
    assert "population_purse" not in [a["kind"] for a in s["system_accounts"]]

    accounts = client.get("/characters/admin/economy/accounts", params={"kind": "population_purse"}).json()
    assert [(a["account_id"], a["name"], a["balance"]) for a in accounts["items"]] == [(purse, "Region A1", 700)]

    ops = client.get("/characters/admin/economy/operations", params={"account_id": purse}).json()
    assert ops["items"][0]["postings"][0]["to"] == {"account_id": purse, "kind": "population_purse",
                                                    "ref_id": 10, "name": "Region A1"}


def test_operations_exclude_op_type(client, econ_db):
    _summary(client)
    acc = _account_id(econ_db, "world_treasury")
    client.post("/characters/admin/economy/emission", json={"account_id": acc, "amount": 5, "comment": "Тест журнала"})
    all_ops = client.get("/characters/admin/economy/operations").json()
    assert sorted(o["op_type"] for o in all_ops["items"]) == ["admin_emission", "genesis"]
    rest = client.get("/characters/admin/economy/operations", params={"exclude_op_type": "admin_emission"}).json()
    assert [o["op_type"] for o in rest["items"]] == ["genesis"] and rest["total"] == 1
    assert client.get("/characters/admin/economy/operations",
                      params={"exclude_op_type": "nope"}).status_code == 400


def test_adjust_population_purse_up_down_and_never_negative(client, econ_db):
    """FEAT-182 3.2: admin adjust is allowed on a purse, but a purse never goes below zero."""
    _summary(client)
    purse = _create_purse(econ_db, 20)
    resp = client.post("/characters/admin/economy/adjust",
                       json={"account_id": purse, "delta": 120, "comment": "Пополнение кошелька"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance"] == 120
    op_id = resp.json()["operation_id"]
    assert _q(econ_db, "SELECT region_id FROM econ_operations WHERE id = :o", o=op_id) == 20
    resp = client.post("/characters/admin/economy/adjust",
                       json={"account_id": purse, "delta": -121, "comment": "Слишком много"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Недостаточно средств на счёте"
    resp = client.post("/characters/admin/economy/adjust",
                       json={"account_id": purse, "delta": -120, "comment": "Обнуление"})
    assert resp.status_code == 200 and resp.json()["balance"] == 0
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 0
    s = _summary(client)
    assert s["totals"]["population_purses"] == 0 and s["invariant"]["ok"] is True
    _assert_world_closes(econ_db, client)


def test_closed_population_purse_rejects_emission_and_adjust(client, econ_db):
    _summary(client)
    purse = _create_purse(econ_db, 10)
    with econ_db.begin() as conn:
        conn.execute(text("UPDATE econ_accounts SET is_active = 0 WHERE id = :i"), {"i": purse})
    for url, body in (("/characters/admin/economy/emission", {"account_id": purse, "amount": 5, "comment": "тест"}),
                      ("/characters/admin/economy/adjust", {"account_id": purse, "delta": 5, "comment": "тест"})):
        assert client.post(url, json=body).status_code == 400
    assert _q(econ_db, "SELECT balance FROM econ_accounts WHERE id = :i", i=purse) == 0


def test_exclude_region_tick_hides_simulation_steps(client, econ_db):
    """The journal hides region_tick operations with exclude_op_type and can combine it with other filters."""
    import econ_ledger
    from sqlalchemy.orm import sessionmaker as _sm

    _summary(client)
    purse = _create_purse(econ_db, 10)
    client.post("/characters/admin/economy/emission", json={"account_id": purse, "amount": 500, "comment": "Жители"})
    s = _sm(bind=econ_db)()
    try:
        for slot in (1, 2):
            econ_ledger.post_operation(
                s, op_type="region_tick",
                legs=[econ_core.Leg(econ_core.AccountRef.purse(10), econ_core.AccountRef.region(10), 100)],
                source_service="character-service", region_id=10, idempotency_key=f"region_tick:{slot}:r:10")
            s.commit()
    finally:
        s.close()

    def ops(**params):
        r = client.get("/characters/admin/economy/operations", params=params)
        assert r.status_code == 200, r.text
        return r.json()

    assert ops()["total"] == 4
    assert ops(op_type="region_tick")["total"] == 2
    hidden = ops(exclude_op_type="region_tick")
    assert hidden["total"] == 2 and {o["op_type"] for o in hidden["items"]} == {"admin_emission", "genesis"}
    assert ops(account_id=purse, exclude_op_type="region_tick")["total"] == 1
    assert ops(region_id=10, exclude_op_type="region_tick")["total"] == 1
    assert ops(op_type="region_tick", exclude_op_type="region_tick")["total"] == 0
    assert ops(exclude_op_type="")["total"] == 4        # empty == no filter
    tick = ops(op_type="region_tick")["items"][0]
    assert [p["leg_type"] for p in tick["postings"]] == ["main", "tax"]
    assert tick["postings"][0]["from"]["kind"] == "population_purse"
    _assert_world_closes(econ_db, client)


@pytest.mark.parametrize("value", [
    "region_tick' OR '1'='1", "region_tick; DROP TABLE econ_operations; --", "REGION_TICK", " region_tick",
    "%", "x" * 300,
])
def test_exclude_op_type_rejects_unknown_and_injection(client, econ_db, value):
    resp = client.get("/characters/admin/economy/operations", params={"exclude_op_type": value})
    assert resp.status_code == 400 and resp.json()["detail"] == "Неизвестный тип операции"
    assert _q(econ_db, "SELECT COUNT(*) FROM econ_operations") == 1


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_get_shape(client):
    resp = client.get("/characters/admin/economy/settings")
    assert resp.status_code == 200
    assert resp.json() == {"currency": CURRENCY, "country_tax_rate": 0.1}


def test_settings_put_strips_and_changes_public_currency_and_tax(client, econ_db):
    client.get("/characters/economy/currency")      # warm the cache
    body = {"currency": {k: f"  {v} " for k, v in GOOD_SETTINGS["currency"].items()}, "country_tax_rate": 0.25}
    resp = client.put("/characters/admin/economy/settings", json=body)
    assert resp.status_code == 200
    assert resp.json() == {"currency": GOOD_SETTINGS["currency"], "country_tax_rate": 0.25}
    assert client.get("/characters/economy/currency").json()["name"] == "Крона"
    assert _q(econ_db, "SELECT updated_by_user_id FROM econ_settings WHERE id = 1") == 7
    assert _summary(client)["settings"] == {"country_tax_rate": 0.25}


@pytest.mark.parametrize("field", ["name", "genitive", "one", "few", "many", "short"])
@pytest.mark.parametrize("value", ["<script>alert(1)</script>", "<b>", "кр>", "", "   ", "a\tb", "a\nb"])
def test_settings_rejects_markup_and_empty_forms(client, econ_db, field, value):
    body = {**GOOD_SETTINGS, "currency": {**GOOD_SETTINGS["currency"], field: value}}
    assert client.put("/characters/admin/economy/settings", json=body).status_code == 422
    assert _q(econ_db, "SELECT currency_name FROM econ_settings WHERE id = 1") == "Марки"


@pytest.mark.parametrize("field,limit", [("name", 50), ("genitive", 50), ("short", 20)])
def test_settings_form_length_limits(client, field, limit):
    ok = {**GOOD_SETTINGS, "currency": {**GOOD_SETTINGS["currency"], field: "я" * limit}}
    too_long = {**GOOD_SETTINGS, "currency": {**GOOD_SETTINGS["currency"], field: "я" * (limit + 1)}}
    assert client.put("/characters/admin/economy/settings", json=too_long).status_code == 422
    assert client.put("/characters/admin/economy/settings", json=ok).status_code == 200


@pytest.mark.parametrize("rate,status", [
    (0, 200), (0.5, 200), (-0.01, 422), (0.51, 422), (True, 422), ("0.1", 422), (None, 422),
])
def test_settings_tax_rate_bounds(client, rate, status):
    assert client.put("/characters/admin/economy/settings",
                      json={**GOOD_SETTINGS, "country_tax_rate": rate}).status_code == status


def test_settings_missing_form_rejected(client):
    currency = dict(GOOD_SETTINGS["currency"])
    currency.pop("few")
    assert client.put("/characters/admin/economy/settings",
                      json={"currency": currency, "country_tax_rate": 0.1}).status_code == 422
