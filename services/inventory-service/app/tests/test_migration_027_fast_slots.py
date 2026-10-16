"""
Migration 027 — fast slots become belt-only for every existing character.

Driven for real against a throwaway SQLite DB with a real Alembic `op`, like
the other migration tests: a character without a belt loses all slots (their
contents go back to the bag, stacking onto an unfilled stack), a character
with a +2 belt keeps exactly fast_slot_1 and fast_slot_2.
"""

import importlib.util
import os

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

_VERSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic", "versions"))

_DDL = [
    """CREATE TABLE items (
        id INTEGER PRIMARY KEY, name TEXT, max_stack_size INTEGER, fast_slot_bonus INTEGER
    )""",
    """CREATE TABLE equipment_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, slot_type TEXT,
        item_id INTEGER, is_enabled BOOLEAN
    )""",
    """CREATE TABLE character_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, item_id INTEGER, quantity INTEGER
    )""",
]

BELT, POTION, AMULET = 1, 2, 3
BARE, BELTED = 10, 20


def _load(filename):
    path = os.path.join(_VERSIONS_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    conn = engine.connect()
    for ddl in _DDL:
        conn.execute(text(ddl))
    conn.execute(text(
        "INSERT INTO items (id, name, max_stack_size, fast_slot_bonus) VALUES "
        f"({BELT}, 'Пояс', 1, 2), ({POTION}, 'Зелье', 10, 0), ({AMULET}, 'Амулет', 1, 0)"
    ))
    for character, belt in ((BARE, None), (BELTED, BELT)):
        conn.execute(text(
            "INSERT INTO equipment_slots (character_id, slot_type, item_id, is_enabled) VALUES (:c, 'belt', :b, 1)"
        ), {"c": character, "b": belt})
        for i in range(1, 11):
            # The old base: slots 1-4 open, two of them holding a potion.
            conn.execute(text(
                "INSERT INTO equipment_slots (character_id, slot_type, item_id, is_enabled) "
                "VALUES (:c, :t, :i, :e)"
            ), {"c": character, "t": f"fast_slot_{i}", "i": POTION if i in (1, 3) else None, "e": i <= 4})
    # The bare character already has a stack of 9 potions: one returned potion tops it up.
    conn.execute(text(f"INSERT INTO character_inventory (character_id, item_id, quantity) VALUES ({BARE}, {POTION}, 9)"))
    conn.commit()

    m027 = _load("027_fast_slots_belt_only.py")
    m027.op = Operations(MigrationContext.configure(conn))
    m027.upgrade()
    conn.commit()
    yield conn
    conn.close()
    engine.dispose()


def _open_slots(conn, character):
    rows = conn.execute(text(
        "SELECT slot_type FROM equipment_slots WHERE character_id = :c AND slot_type LIKE 'fast_slot_%' AND is_enabled = 1"
    ), {"c": character}).fetchall()
    return sorted(r[0] for r in rows)


def _bag(conn, character):
    return sorted(conn.execute(text(
        "SELECT item_id, quantity FROM character_inventory WHERE character_id = :c"
    ), {"c": character}).fetchall())


def test_no_belt_closes_every_slot(db):
    assert _open_slots(db, BARE) == []


def test_contents_return_to_the_bag_stacking(db):
    # 9 + 1 fills the stack to its max of 10, the second potion starts a new row.
    assert _bag(db, BARE) == [(POTION, 1), (POTION, 10)]
    left = db.execute(text(
        "SELECT COUNT(*) FROM equipment_slots WHERE character_id = :c AND slot_type LIKE 'fast_slot_%' AND item_id IS NOT NULL"
    ), {"c": BARE}).scalar()
    assert left == 0


def test_belt_keeps_its_slots(db):
    assert _open_slots(db, BELTED) == ["fast_slot_1", "fast_slot_2"]
    # fast_slot_1 keeps its potion; the one in fast_slot_3 went to the bag.
    kept = db.execute(text(
        "SELECT item_id FROM equipment_slots WHERE character_id = :c AND slot_type = 'fast_slot_1'"
    ), {"c": BELTED}).scalar()
    assert kept == POTION
    assert _bag(db, BELTED) == [(POTION, 1)]
