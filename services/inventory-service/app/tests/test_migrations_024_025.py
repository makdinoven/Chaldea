"""
FEAT-168 — the two Alembic revisions of this feature are driven for real.

`024_item_battle_effects` creates `item_effects` / `item_damage_entries` and the
three `items` columns; `025_item_xp_buffs` creates `item_xp_buffs` and backfills
one row per item that already carried the legacy buff triple.

The revisions run exactly as Alembic runs them: a real `alembic.operations
.Operations` bound to a throwaway SQLite database (so `op.create_table`,
`op.add_column`, `op.drop_column` and `op.execute` are the genuine article, not
a stub). Every assertion reads the schema/rows back out of that database.

Sequence exercised: upgrade → downgrade → upgrade, plus the backfill contents.
SQLite is not MySQL — this pins the operations, the column names and the
backfill SQL, not MySQL-specific DDL behaviour (the Backend Dev's log records a
manual upgrade/downgrade/upgrade run on dev MySQL).
"""

import importlib.util
import os
import re

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

import models
import schemas


_VERSIONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)

# The pre-024 shape of `items`, reduced to what these revisions touch.
_ITEMS_DDL = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    buff_type VARCHAR(50),
    buff_value FLOAT,
    buff_duration_minutes INTEGER
)
"""


def _load(filename):
    path = os.path.join(_VERSIONS_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def migration_db():
    """A throwaway DB with the pre-FEAT-168 `items` table and a real `op`."""
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    conn = engine.connect()
    conn.execute(text(_ITEMS_DDL))
    conn.commit()

    op = Operations(MigrationContext.configure(conn))
    m024 = _load("024_item_battle_effects.py")
    m025 = _load("025_item_xp_buffs.py")
    m024.op = op
    m025.op = op

    yield {"conn": conn, "op": op, "m024": m024, "m025": m025}

    conn.close()
    engine.dispose()


def _tables(conn):
    return set(inspect(conn).get_table_names())


def _columns(conn, table):
    return {c["name"] for c in inspect(conn).get_columns(table)}


def _add_item(conn, name, buff_type=None, buff_value=None, minutes=None):
    conn.execute(
        text("INSERT INTO items (name, buff_type, buff_value, buff_duration_minutes) "
             "VALUES (:n, :bt, :bv, :bd)"),
        {"n": name, "bt": buff_type, "bv": buff_value, "bd": minutes},
    )
    conn.commit()
    return conn.execute(text("SELECT id FROM items WHERE name = :n"),
                        {"n": name}).scalar()


# ===========================================================================
# 1. Revision chain
# ===========================================================================

class TestRevisionChain:

    def test_revision_ids_and_order(self, migration_db):
        m024, m025 = migration_db["m024"], migration_db["m025"]
        assert m024.revision == "024_item_battle_effects"
        assert m024.down_revision == "023_weapon_damage_backfill"
        assert m025.revision == "025_item_xp_buffs"
        assert m025.down_revision == "024_item_battle_effects"
        # alembic_version_inventory.version_num is VARCHAR(32)
        assert len(m024.revision) <= 32
        assert len(m025.revision) <= 32

    def test_no_branch_and_025_is_head(self):
        """Ровно один потомок у каждой ревизии, 025 — голова."""
        revisions, downs = set(), {}
        for fname in os.listdir(_VERSIONS_DIR):
            if not re.match(r"^\d{3}_.*\.py$", fname):
                continue
            source = open(os.path.join(_VERSIONS_DIR, fname), encoding="utf-8").read()
            rev = re.search(r"^revision = ['\"](.+)['\"]", source, re.M).group(1)
            down = re.search(r"^down_revision = (.+)$", source, re.M).group(1).strip()
            revisions.add(rev)
            downs[rev] = None if down == "None" else down.strip("'\"")

        parents = [d for d in downs.values() if d]
        assert len(parents) == len(set(parents)), "ветвление в дереве миграций"
        heads = revisions - set(parents)
        assert heads == {"025_item_xp_buffs"}


# ===========================================================================
# 2. 024 — battle effect tables
# ===========================================================================

class TestMigration024:

    def test_upgrade_creates_tables_and_columns(self, migration_db):
        conn, m024 = migration_db["conn"], migration_db["m024"]
        m024.upgrade()
        conn.commit()

        assert {"item_effects", "item_damage_entries"} <= _tables(conn)
        assert _columns(conn, "item_effects") == {
            "id", "item_id", "target_side", "effect_name", "description",
            "chance", "duration", "magnitude", "attribute_key",
        }
        assert _columns(conn, "item_damage_entries") == {
            "id", "item_id", "damage_type", "amount", "description",
            "weapon_slot", "target_side", "chance",
            "aoe_shape", "aoe_falloff", "aoe_max_targets",
        }
        assert {"consumable_action", "coating_turns", "coating_bonus_damage"} \
            <= _columns(conn, "items")

    def test_columns_match_the_orm_models(self, migration_db):
        """Дрейф между models.py и миграцией ловится здесь, а не на проде."""
        conn, m024 = migration_db["conn"], migration_db["m024"]
        m024.upgrade()
        conn.commit()

        assert _columns(conn, "item_effects") == \
            {c.name for c in models.ItemEffect.__table__.columns}
        assert _columns(conn, "item_damage_entries") == \
            {c.name for c in models.ItemDamageEntry.__table__.columns}
        for column in ("consumable_action", "coating_turns", "coating_bonus_damage"):
            assert column in models.Items.__table__.columns

    def test_server_defaults_apply_on_a_bare_insert(self, migration_db):
        conn, m024 = migration_db["conn"], migration_db["m024"]
        m024.upgrade()
        item_id = _add_item(conn, "Зелье")

        conn.execute(text("INSERT INTO item_effects (item_id, effect_name) "
                          "VALUES (:iid, 'StatModifier')"), {"iid": item_id})
        conn.execute(text("INSERT INTO item_damage_entries (item_id, damage_type) "
                          "VALUES (:iid, 'fire')"), {"iid": item_id})
        conn.commit()

        effect = conn.execute(text(
            "SELECT target_side, chance, duration, magnitude FROM item_effects"
        )).fetchone()
        assert tuple(effect) == ("self", 100, 1, 0)

        damage = conn.execute(text(
            "SELECT weapon_slot, target_side, chance, aoe_shape, aoe_falloff, "
            "aoe_max_targets FROM item_damage_entries"
        )).fetchone()
        assert tuple(damage) == ("no_weapon", "enemy", 100, "single", 50, 3)

    def test_upgrade_downgrade_upgrade(self, migration_db):
        conn, m024 = migration_db["conn"], migration_db["m024"]

        m024.upgrade()
        conn.commit()
        m024.downgrade()
        conn.commit()

        assert "item_effects" not in _tables(conn)
        assert "item_damage_entries" not in _tables(conn)
        assert "consumable_action" not in _columns(conn, "items")
        assert "coating_turns" not in _columns(conn, "items")
        assert "coating_bonus_damage" not in _columns(conn, "items")

        m024.upgrade()
        conn.commit()
        assert {"item_effects", "item_damage_entries"} <= _tables(conn)
        assert "coating_turns" in _columns(conn, "items")

    def test_downgrade_keeps_the_items_rows(self, migration_db):
        conn, m024 = migration_db["conn"], migration_db["m024"]
        m024.upgrade()
        _add_item(conn, "Зелье силы")
        m024.downgrade()
        conn.commit()

        assert conn.execute(text("SELECT name FROM items")).scalar() == "Зелье силы"


# ===========================================================================
# 3. 025 — XP buff table + backfill
# ===========================================================================

class TestMigration025:

    def test_upgrade_creates_the_table(self, migration_db):
        conn, m024, m025 = migration_db["conn"], migration_db["m024"], migration_db["m025"]
        m024.upgrade()
        m025.upgrade()
        conn.commit()

        assert "item_xp_buffs" in _tables(conn)
        assert _columns(conn, "item_xp_buffs") == \
            {"id", "item_id", "buff_type", "value", "duration_minutes"}
        assert _columns(conn, "item_xp_buffs") == \
            {c.name for c in models.ItemXpBuff.__table__.columns}

    def test_backfill_writes_exactly_one_row_per_legacy_item(self, migration_db):
        conn, m024, m025 = migration_db["conn"], migration_db["m024"], migration_db["m025"]
        m024.upgrade()

        book_id = _add_item(conn, "Книга профессии", "xp_bonus", 0.25, 60)
        other_id = _add_item(conn, "Книга сбора", "gathering_xp_bonus", 0.5, 120)
        # items that must NOT be backfilled
        _add_item(conn, "Зелье")
        _add_item(conn, "Полукнига без значения", "xp_bonus", None, 60)
        _add_item(conn, "Полукнига без длительности", "xp_bonus", 0.1, None)

        m025.upgrade()
        conn.commit()

        rows = conn.execute(text(
            "SELECT item_id, buff_type, value, duration_minutes "
            "FROM item_xp_buffs ORDER BY item_id"
        )).fetchall()
        assert [tuple(r) for r in rows] == [
            (book_id, "xp_bonus", 0.25, 60),
            (other_id, "gathering_xp_bonus", 0.5, 120),
        ]

    def test_backfill_skips_rows_the_new_schema_would_reject(self, migration_db):
        """Ревью #1 §2: `items.buff_type` был свободной строкой.

        Перенести такую строку как есть — значит положить за
        `GET /inventory/items/{id}` данные, которые схема ответа не переварит.
        Непригодные строки пропускаются, устаревшие колонки не трогаются.
        """
        conn, m024, m025 = migration_db["conn"], migration_db["m024"], migration_db["m025"]
        m024.upgrade()

        good_id = _add_item(conn, "Книга профессии", "xp_bonus", 0.25, 60)
        # каждая из этих строк валила бы ответ, если перенести её дословно
        _add_item(conn, "Мусорный тип", "legacy_nonsense", 0.25, 60)
        _add_item(conn, "Пустой тип", "", 0.25, 60)
        _add_item(conn, "Нулевая прибавка", "xp_bonus", 0.0, 60)
        _add_item(conn, "Отрицательная прибавка", "xp_bonus", -0.5, 60)
        _add_item(conn, "Слишком большая прибавка", "xp_bonus", 99.0, 60)

        m025.upgrade()
        conn.commit()

        rows = conn.execute(text(
            "SELECT item_id, buff_type, value, duration_minutes FROM item_xp_buffs"
        )).fetchall()
        assert [tuple(r) for r in rows] == [(good_id, "xp_bonus", 0.25, 60)]

        # ничего не разрушено — старые колонки пропущенных предметов на месте
        assert conn.execute(text(
            "SELECT buff_type FROM items WHERE name = 'Мусорный тип'"
        )).scalar() == "legacy_nonsense"

    def test_backfill_clamps_an_out_of_range_duration(self, migration_db):
        """Слишком длинная книга — осмысленная книга, режется только длительность."""
        conn, m024, m025 = migration_db["conn"], migration_db["m024"], migration_db["m025"]
        m024.upgrade()

        long_id = _add_item(conn, "Вечная книга", "xp_bonus", 0.25, 99999)
        zero_id = _add_item(conn, "Мгновенная книга", "gathering_xp_bonus", 0.5, 0)

        m025.upgrade()
        conn.commit()

        rows = dict(conn.execute(text(
            "SELECT item_id, duration_minutes FROM item_xp_buffs"
        )).fetchall())
        assert rows[long_id] == 7 * 24 * 60
        assert rows[zero_id] == 1

    def test_inlined_whitelist_mirrors_the_schemas_module(self, migration_db):
        """Константы в миграции скопированы намеренно — но расходиться не должны."""
        m025 = migration_db["m025"]
        assert m025.ALLOWED_BUFF_TYPES == schemas.ALLOWED_BUFF_TYPES
        assert m025.MAX_XP_BUFF_VALUE == schemas.MAX_XP_BUFF_VALUE
        assert m025.MAX_XP_BUFF_DURATION_MINUTES == schemas.MAX_XP_BUFF_DURATION_MINUTES

    def test_backfill_leaves_the_legacy_columns_filled(self, migration_db):
        conn, m024, m025 = migration_db["conn"], migration_db["m024"], migration_db["m025"]
        m024.upgrade()
        _add_item(conn, "Книга профессии", "xp_bonus", 0.25, 60)
        m025.upgrade()
        conn.commit()

        legacy = conn.execute(text(
            "SELECT buff_type, buff_value, buff_duration_minutes FROM items"
        )).fetchone()
        assert tuple(legacy) == ("xp_bonus", 0.25, 60)

    def test_upgrade_downgrade_upgrade_and_backfill_is_idempotent(self, migration_db):
        conn, m024, m025 = migration_db["conn"], migration_db["m024"], migration_db["m025"]
        m024.upgrade()
        book_id = _add_item(conn, "Книга профессии", "xp_bonus", 0.25, 60)

        m025.upgrade()
        conn.commit()
        m025.downgrade()
        conn.commit()
        assert "item_xp_buffs" not in _tables(conn)
        # откат ничего не теряет — старые колонки на месте
        assert conn.execute(text("SELECT buff_type FROM items")).scalar() == "xp_bonus"

        m025.upgrade()
        conn.commit()
        rows = conn.execute(text(
            "SELECT item_id, buff_type, value, duration_minutes FROM item_xp_buffs"
        )).fetchall()
        assert [tuple(r) for r in rows] == [(book_id, "xp_bonus", 0.25, 60)]

    def test_full_chain_down_and_up(self, migration_db):
        """024+025 вверх, затем вниз в обратном порядке и снова вверх."""
        conn, m024, m025 = migration_db["conn"], migration_db["m024"], migration_db["m025"]
        m024.upgrade()
        m025.upgrade()
        conn.commit()

        m025.downgrade()
        m024.downgrade()
        conn.commit()
        assert not ({"item_effects", "item_damage_entries", "item_xp_buffs"}
                    & _tables(conn))

        m024.upgrade()
        m025.upgrade()
        conn.commit()
        assert {"item_effects", "item_damage_entries", "item_xp_buffs"} <= _tables(conn)

    def test_unique_constraint_on_item_and_type(self, migration_db):
        conn, m024, m025 = migration_db["conn"], migration_db["m024"], migration_db["m025"]
        m024.upgrade()
        m025.upgrade()
        item_id = _add_item(conn, "Книга")
        conn.execute(text("INSERT INTO item_xp_buffs (item_id, buff_type, value, "
                          "duration_minutes) VALUES (:i, 'xp_bonus', 0.1, 60)"),
                     {"i": item_id})
        conn.commit()

        with pytest.raises(Exception):
            conn.execute(text("INSERT INTO item_xp_buffs (item_id, buff_type, value, "
                              "duration_minutes) VALUES (:i, 'xp_bonus', 0.2, 60)"),
                         {"i": item_id})
            conn.commit()
