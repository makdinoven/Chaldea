"""
FEAT-211 #14 — inventory-service: stolen caravan bales.

* Migration 037 sits on 036, adds `items.is_stolen` / `items.bale_group` (plain
  columns, no ENUM) and seeds 12 bales — one per goods group — idempotently,
  skipping a name that already exists. Run for real through Alembic
  `Operations` on a throw-away SQLite connection (the downgrade's FK scan reads
  information_schema, so that one part is stubbed).
* `schemas.Item` exposes both flags read-only; `ItemCreate` cannot carry them,
  so a regular item edit keeps them.
* `deposit_to_auction_storage` refuses a stolen item with 400 and leaves the
  inventory untouched; an ordinary `misc` item is still accepted.
* Bales are `misc` → no goods group → off-market in `econ_core`, so a living
  merchant's default bid (and every outlet keyed on the effective group:
  guild orders, faction donations) refuses them — even when an admin override
  tries to put them on the market without a group.

State is always read back from the DB (silent-failure guard).
"""

import importlib.util
import os
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import text

import econ_core
import models
import schemas
import crud
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.test_auction import (
    _create_characters_table,
    _insert_character,
    _insert_npc_auctioneer,
)

_VERSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "alembic", "versions")
_MIGRATION_FILE = "037_stolen_bales.py"

EXPECTED_BALES = {
    "food": "Тюк зерна (краденое)",
    "ore_metal": "Слиток руды (краденое)",
    "wood": "Связка древесины (краденое)",
    "herbs": "Тюк трав (краденое)",
    "hides_textiles": "Тюк кож и тканей (краденое)",
    "magic": "Ящик магических материалов (краденое)",
    "weapons": "Ящик оружия (краденое)",
    "armor": "Тюк доспехов (краденое)",
    "jewelry": "Шкатулка украшений (краденое)",
    "potions": "Ящик зелий (краденое)",
    "tools": "Ящик инструментов (краденое)",
    "household": "Тюк утвари (краденое)",
}
BALE_DESCRIPTION = "Краденый товар. Его купит только скупщик."

BALE, PLAIN_MISC = 501, 502
CHAR, NPC = 1, 100

EDITOR = UserRead(id=1, username="editor", role="editor",
                  permissions=["items:read", "items:update"])


def _load_037():
    path = os.path.join(_VERSIONS_DIR, _MIGRATION_FILE)
    spec = importlib.util.spec_from_file_location("mig_037_stolen_bales", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(db, item_id):
    db.expire_all()
    return db.query(models.Items).filter(models.Items.id == item_id).one()


# ===========================================================================
# Migration 037 — static shape
# ===========================================================================

class TestMigration037Shape:

    def test_revision_chain(self):
        m = _load_037()
        assert m.revision == "037_stolen_bales"
        assert m.down_revision == "036_item_admin_ready"
        assert len(m.revision) <= 32
        assert os.path.exists(os.path.join(_VERSIONS_DIR, "036_item_admin_ready.py"))

    def test_037_is_the_only_head(self):
        revisions, parents = set(), []
        for name in os.listdir(_VERSIONS_DIR):
            if not name.endswith(".py"):
                continue
            spec = importlib.util.spec_from_file_location(f"rev_{name[:-3]}",
                                                          os.path.join(_VERSIONS_DIR, name))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            revisions.add(module.revision)
            if module.down_revision:
                parents.append(module.down_revision)
        assert revisions - set(parents) == {"037_stolen_bales"}

    def test_twelve_bales_one_per_goods_group(self):
        m = _load_037()
        assert len(m.BALES) == 12
        assert dict(m.BALES) == EXPECTED_BALES
        assert sorted(code for code, _ in m.BALES) == sorted(econ_core.GOODS_GROUPS)
        assert len({name for _, name in m.BALES}) == 12
        assert all(len(code) <= 32 for code, _ in m.BALES)  # bale_group VARCHAR(32)

    def test_no_enum_or_item_type_alter(self):
        with open(os.path.join(_VERSIONS_DIR, _MIGRATION_FILE), encoding="utf-8") as f:
            src = f.read()
        code = src.split('"""', 2)[2]
        assert "Enum" not in code and "alter_column" not in code


# ===========================================================================
# Migration 037 — executed on a real (SQLite) connection
# ===========================================================================

_ITEMS_DDL = """CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL UNIQUE,
    image VARCHAR(255),
    item_level INTEGER NOT NULL DEFAULT 0,
    item_type VARCHAR(50) NOT NULL,
    item_rarity VARCHAR(50) NOT NULL DEFAULT 'common',
    price INTEGER,
    max_stack_size INTEGER NOT NULL DEFAULT 1,
    is_unique BOOLEAN NOT NULL DEFAULT 0,
    description TEXT,
    fast_slot_bonus INTEGER NOT NULL DEFAULT 0
)"""


@pytest.fixture()
def mig_conn():
    """Private SQLite connection with a pre-037 `items` table and one ordinary item."""
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        conn.execute(text(_ITEMS_DDL))
        conn.execute(text("INSERT INTO items (id, name, item_type, price) "
                          "VALUES (1, 'Медная руда', 'resource', 10)"))
        yield conn
    engine.dispose()


def _run(module, conn, step):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        getattr(module, step)()


def _columns(conn):
    return {c["name"]: c for c in sa.inspect(conn).get_columns("items")}


def _bales(conn):
    return conn.execute(text(
        "SELECT name, item_type, item_rarity, price, max_stack_size, is_unique, description, "
        "is_stolen, bale_group, item_level, fast_slot_bonus, image "
        "FROM items WHERE is_stolen = 1 ORDER BY id"
    )).fetchall()


class TestMigration037Run:

    def test_upgrade_adds_columns_and_seeds_12_bales(self, mig_conn):
        _run(_load_037(), mig_conn, "upgrade")
        cols = _columns(mig_conn)
        assert cols["is_stolen"]["nullable"] is False
        assert str(cols["is_stolen"]["default"]).strip("'\"") == "0"
        assert cols["bale_group"]["nullable"] is True

        rows = _bales(mig_conn)
        assert len(rows) == 12
        assert {r.bale_group: r.name for r in rows} == EXPECTED_BALES
        for r in rows:
            assert (r.item_type, r.item_rarity, r.price, r.max_stack_size) == ("misc", "common", 50, 999)
            assert not r.is_unique
            assert r.description == BALE_DESCRIPTION
            assert (r.item_level, r.fast_slot_bonus, r.image) == (0, 0, None)

    def test_existing_items_default_to_not_stolen(self, mig_conn):
        _run(_load_037(), mig_conn, "upgrade")
        row = mig_conn.execute(text("SELECT is_stolen, bale_group FROM items WHERE id = 1")).one()
        assert (row.is_stolen, row.bale_group) == (0, None)

    def test_upgrade_is_idempotent(self, mig_conn):
        m = _load_037()
        _run(m, mig_conn, "upgrade")
        _run(m, mig_conn, "upgrade")
        assert len(_bales(mig_conn)) == 12
        assert mig_conn.execute(text("SELECT COUNT(*) FROM items")).scalar() == 13

    def test_upgrade_skips_a_name_that_already_exists(self, mig_conn):
        mig_conn.execute(text("INSERT INTO items (id, name, item_type, price) "
                              "VALUES (2, 'Тюк зерна (краденое)', 'misc', 777)"))
        _run(_load_037(), mig_conn, "upgrade")
        assert len(_bales(mig_conn)) == 11
        kept = mig_conn.execute(text(
            "SELECT price, is_stolen FROM items WHERE name = 'Тюк зерна (краденое)'")).fetchall()
        assert [(r.price, r.is_stolen) for r in kept] == [(777, 0)]

    def test_downgrade_removes_bales_and_columns(self, mig_conn):
        m = _load_037()
        _run(m, mig_conn, "upgrade")
        ids = [r[0] for r in mig_conn.execute(text("SELECT id FROM items WHERE is_stolen = 1"))]
        cleared = []
        # information_schema is MySQL-only — record what would be cleared instead.
        with patch.object(m, "_clear_references", side_effect=lambda b, i: cleared.append(sorted(i))):
            _run(m, mig_conn, "downgrade")
        assert cleared == [sorted(ids)]
        cols = _columns(mig_conn)
        assert "is_stolen" not in cols and "bale_group" not in cols
        names = [r[0] for r in mig_conn.execute(text("SELECT name FROM items"))]
        assert names == ["Медная руда"]

    def test_downgrade_keeps_a_same_named_ordinary_item(self, mig_conn):
        """Only rows flagged is_stolen are deleted, never a pre-existing namesake."""
        mig_conn.execute(text("INSERT INTO items (id, name, item_type) "
                              "VALUES (2, 'Тюк трав (краденое)', 'misc')"))
        m = _load_037()
        _run(m, mig_conn, "upgrade")
        with patch.object(m, "_clear_references"):
            _run(m, mig_conn, "downgrade")
        names = sorted(r[0] for r in mig_conn.execute(text("SELECT name FROM items")))
        assert names == sorted(["Медная руда", "Тюк трав (краденое)"])

    def test_downgrade_then_upgrade_again(self, mig_conn):
        m = _load_037()
        _run(m, mig_conn, "upgrade")
        with patch.object(m, "_clear_references"):
            _run(m, mig_conn, "downgrade")
        _run(m, mig_conn, "upgrade")
        assert len(_bales(mig_conn)) == 12

    def test_downgrade_without_columns_is_noop(self, mig_conn):
        m = _load_037()
        with patch.object(m, "_clear_references") as clear:
            _run(m, mig_conn, "downgrade")
        clear.assert_not_called()
        assert mig_conn.execute(text("SELECT COUNT(*) FROM items")).scalar() == 1


# ===========================================================================
# Model + schemas
# ===========================================================================

@pytest.fixture()
def bale_items(db_session):
    db_session.add(models.Items(
        id=BALE, name="Слиток руды (краденое)", item_type="misc", item_rarity="common",
        item_level=0, max_stack_size=999, is_unique=False, price=50,
        description=BALE_DESCRIPTION, is_stolen=True, bale_group="ore_metal",
    ))
    db_session.add(models.Items(
        id=PLAIN_MISC, name="Старая монета", item_type="misc", item_rarity="common",
        item_level=0, max_stack_size=99, is_unique=False, price=5,
    ))
    db_session.commit()
    yield db_session
    app.dependency_overrides.pop(get_current_user_via_http, None)


class TestSchemaFields:

    def test_model_defaults(self, bale_items):
        plain = _row(bale_items, PLAIN_MISC)
        assert (plain.is_stolen, plain.bale_group) == (False, None)
        bale = _row(bale_items, BALE)
        assert (bale.is_stolen, bale.bale_group) == (True, "ore_metal")

    def test_item_schema_exposes_flags(self, bale_items):
        body = schemas.Item.from_orm(_row(bale_items, BALE)).dict()
        assert body["is_stolen"] is True
        assert body["bale_group"] == "ore_metal"
        plain = schemas.Item.from_orm(_row(bale_items, PLAIN_MISC)).dict()
        assert (plain["is_stolen"], plain["bale_group"]) == (False, None)

    def test_item_create_cannot_carry_flags(self):
        assert "is_stolen" not in schemas.ItemCreate.__fields__
        assert "bale_group" not in schemas.ItemCreate.__fields__

    def test_public_items_list_carries_flags(self, bale_items, client):
        r = client.get("/inventory/items")
        assert r.status_code == 200, r.text
        by_id = {row["id"]: row for row in r.json()}
        assert by_id[BALE]["is_stolen"] is True
        assert by_id[BALE]["bale_group"] == "ore_metal"
        assert by_id[PLAIN_MISC]["is_stolen"] is False
        assert by_id[PLAIN_MISC]["bale_group"] is None


class TestItemEditKeepsFlags:

    def _put(self, client, **extra):
        body = {"name": "Слиток руды (краденое)", "item_type": "misc", "item_rarity": "common",
                "item_level": 0, "max_stack_size": 999, "is_unique": False, "price": 80, **extra}
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock), \
             patch("main._reconcile_perks_async", new_callable=AsyncMock):
            return client.put(f"/inventory/items/{BALE}", json=body)

    def test_edit_keeps_flags(self, bale_items, client):
        app.dependency_overrides[get_current_user_via_http] = lambda: EDITOR
        r = self._put(client)
        assert r.status_code == 200, r.text
        assert r.json()["is_stolen"] is True
        assert r.json()["bale_group"] == "ore_metal"
        row = _row(bale_items, BALE)
        assert row.price == 80
        assert (row.is_stolen, row.bale_group) == (True, "ore_metal")

    def test_edit_payload_cannot_clear_or_set_flags(self, bale_items, client):
        app.dependency_overrides[get_current_user_via_http] = lambda: EDITOR
        r = self._put(client, is_stolen=False, bale_group="food")
        assert r.status_code in (200, 422), r.text
        row = _row(bale_items, BALE)
        assert (row.is_stolen, row.bale_group) == (True, "ore_metal")

    def test_edit_cannot_make_an_ordinary_item_stolen(self, bale_items, client):
        app.dependency_overrides[get_current_user_via_http] = lambda: EDITOR
        body = {"name": "Старая монета", "item_type": "misc", "item_rarity": "common",
                "item_level": 0, "max_stack_size": 99, "is_unique": False,
                "is_stolen": True, "bale_group": "jewelry"}
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock), \
             patch("main._reconcile_perks_async", new_callable=AsyncMock):
            r = client.put(f"/inventory/items/{PLAIN_MISC}", json=body)
        assert r.status_code in (200, 422), r.text
        row = _row(bale_items, PLAIN_MISC)
        assert (row.is_stolen, row.bale_group) == (False, None)


# ===========================================================================
# Auction refuses stolen items
# ===========================================================================

@pytest.fixture()
def auction_env(bale_items):
    db = bale_items
    _create_characters_table(db)
    _insert_character(db, CHAR, user_id=1, name="Налётчик", location=1)
    _insert_character(db, 2, user_id=2, name="Чужой", location=1)
    _insert_npc_auctioneer(db, NPC, location=1)
    bale_inv = models.CharacterInventory(character_id=CHAR, item_id=BALE, quantity=7)
    plain_inv = models.CharacterInventory(character_id=CHAR, item_id=PLAIN_MISC, quantity=3)
    db.add_all([bale_inv, plain_inv])
    db.commit()
    return {"db": db, "bale_inv": bale_inv.id, "plain_inv": plain_inv.id}


def _inv_qty(db, inv_id):
    db.expire_all()
    row = db.query(models.CharacterInventory).filter(models.CharacterInventory.id == inv_id).first()
    return row.quantity if row else 0


def _storage_count(db):
    db.expire_all()
    return db.query(models.AuctionStorage).count()


class TestAuctionRefusesStolen:

    def test_crud_refuses_bale_with_400(self, auction_env):
        db = auction_env["db"]
        req = schemas.AuctionDepositRequest(character_id=CHAR,
                                            inventory_item_id=auction_env["bale_inv"], quantity=1)
        with pytest.raises(HTTPException) as exc:
            crud.deposit_to_auction_storage(db, data=req, user_id=1)
        assert exc.value.status_code == 400
        assert exc.value.detail == "Краденое нельзя выставить на аукцион"
        assert _inv_qty(db, auction_env["bale_inv"]) == 7
        assert _storage_count(db) == 0

    def test_refusal_wins_over_quantity_check(self, auction_env):
        """Even an over-quantity request names the real reason — the item is stolen."""
        db = auction_env["db"]
        req = schemas.AuctionDepositRequest(character_id=CHAR,
                                            inventory_item_id=auction_env["bale_inv"], quantity=500)
        with pytest.raises(HTTPException) as exc:
            crud.deposit_to_auction_storage(db, data=req, user_id=1)
        assert exc.value.detail == "Краденое нельзя выставить на аукцион"

    def test_ordinary_misc_item_is_still_accepted(self, auction_env):
        db = auction_env["db"]
        req = schemas.AuctionDepositRequest(character_id=CHAR,
                                            inventory_item_id=auction_env["plain_inv"], quantity=2)
        result = crud.deposit_to_auction_storage(db, data=req, user_id=1)
        assert result["quantity"] == 2
        assert _inv_qty(db, auction_env["plain_inv"]) == 1
        db.expire_all()
        storage = db.query(models.AuctionStorage).one()
        assert (storage.item_id, storage.quantity, storage.character_id) == (PLAIN_MISC, 2, CHAR)

    def test_endpoint_refuses_bale_with_russian_400(self, auction_env, client):
        app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
            id=1, username="raider", role="user", permissions=[])
        r = client.post("/inventory/auction/storage/deposit",
                        json={"character_id": CHAR, "inventory_item_id": auction_env["bale_inv"],
                              "quantity": 3})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Краденое нельзя выставить на аукцион"
        assert _inv_qty(auction_env["db"], auction_env["bale_inv"]) == 7
        assert _storage_count(auction_env["db"]) == 0

    def test_endpoint_accepts_ordinary_item(self, auction_env, client):
        app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
            id=1, username="raider", role="user", permissions=[])
        r = client.post("/inventory/auction/storage/deposit",
                        json={"character_id": CHAR, "inventory_item_id": auction_env["plain_inv"],
                              "quantity": 1})
        assert r.status_code == 201, r.text
        assert _inv_qty(auction_env["db"], auction_env["plain_inv"]) == 2

    def test_ownership_checked_before_stolen_flag(self, auction_env):
        """Someone else's character → 403, the stolen flag does not leak the item type."""
        db = auction_env["db"]
        req = schemas.AuctionDepositRequest(character_id=CHAR,
                                            inventory_item_id=auction_env["bale_inv"], quantity=1)
        with pytest.raises(HTTPException) as exc:
            crud.deposit_to_auction_storage(db, data=req, user_id=2)
        assert exc.value.status_code == 403
        assert _inv_qty(db, auction_env["bale_inv"]) == 7


# ===========================================================================
# econ_core: a misc bale is off-market → merchants / guild / faction refuse it
# ===========================================================================

def _market_row(item_id, item_type="misc", subcat=None, is_food=0, rarity="common", price=50,
                override_group=None, override_off=None):
    """sql_item_market column order: id, type, subcategory, is_food, rarity, price, name, image, o.group, o.off."""
    return (item_id, item_type, subcat, is_food, rarity, price, "item", None, override_group, override_off)


MULTS = {g: "1.5" for g in econ_core.GOODS_GROUPS}
BASES = {g: 40 for g in econ_core.GOODS_GROUPS}
ALL_GROUPS = list(econ_core.GOODS_GROUPS)


class TestBalesOffMarket:

    def test_misc_has_no_group_and_is_off_market(self):
        assert econ_core.auto_item_group("misc", None, 0, "common") == (None, False)
        assert econ_core.effective_item_group("misc", None, 0, "common") == (None, True)

    def test_off_market_even_if_override_says_on_market(self):
        """Without a group an item is always off-market, whatever off_market override says."""
        assert econ_core.effective_item_group("misc", None, 0, "common", None, 0) == (None, True)

    def test_bale_market_row_resolves_off_market(self):
        m = econ_core.item_market_from_row(_market_row(BALE))
        assert (m.item_id, m.group, m.off_market, m.price) == (BALE, None, True, 50)

    def test_living_merchant_default_bid_is_zero(self):
        bale = econ_core.item_market_from_row(_market_row(BALE))
        assert econ_core.shop_row_bid(True, bale, None, ALL_GROUPS, MULTS, BASES, "0.5") == 0

    def test_legacy_merchant_default_bid_is_zero(self):
        bale = econ_core.item_market_from_row(_market_row(BALE))
        assert econ_core.shop_row_bid(False, bale, None, ALL_GROUPS, MULTS, BASES, "0.5") == 0

    def test_control_on_market_item_of_same_group_is_bought(self):
        """Same price, a real ore resource — the living merchant does bid on it."""
        ore = econ_core.item_market_from_row(_market_row(1, "resource", "ore"))
        assert (ore.group, ore.off_market) == ("ore_metal", False)
        assert econ_core.shop_row_bid(True, ore, None, ALL_GROUPS, MULTS, BASES, "0.5") > 0

    def test_bale_never_widens_merchant_buy_groups(self):
        """An admin shop row with a bale adds no goods group to what the merchant buys."""
        bale = econ_core.item_market_from_row(_market_row(BALE))
        row = (1, NPC, BALE, 100, 50, 10, 10, econ_core.SHOP_ORIGIN_ADMIN, 1)
        assert econ_core.merchant_buys_groups([row], {BALE: bale}) == []

    def test_shop_row_prices_not_market(self):
        bale = econ_core.item_market_from_row(_market_row(BALE))
        prices = econ_core.shop_row_prices(True, bale, 100, 50, MULTS)
        assert prices["market"] is False
        assert prices["off_market"] is True
        assert prices["group"] is None
        assert prices["mult"] == 1
