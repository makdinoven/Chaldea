"""Migration 011 — enemy-targeted buffs move onto the caster (effect audit, 2026-10-16).

Runs the migration's own WHERE clause against a throwaway SQLite table, so the
test checks exactly what goes to MySQL: which rows move and which stay.
"""
import importlib.util
import os
import sqlite3

import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions",
                     "011_enemy_buffs_to_self.py")
_spec = importlib.util.spec_from_file_location("migration_011", _PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


ROWS = [
    # (effect_name, attribute_key, target_side, magnitude, should_move)
    ("StatModifier", "crit_chance", "enemy", 15, True),
    ("StatModifier", "crit_damage", "enemy", 25, True),
    ("StatModifier", "dodge_chance", "all_enemies", 10, True),
    ("Buff: magic", None, "enemy", 5, True),
    ("Resist: damning", None, "enemy", 5, True),
    ("MagicImpact", "intelligence", "enemy", 20, True),
    # Debuffs on an enemy stay where they are.
    ("StatModifier", "dodge_chance", "enemy", -10, False),
    ("Resist: all", None, "enemy", -5, False),
    ("MagicImpact", "strength", "enemy", -5, False),
    # On an enemy a positive resource row is already damage — untouched.
    ("StatModifier", "hp", "enemy", 20, False),
    ("StatModifier", "energy", "enemy", 10, False),
    # Effects whose direction lives in the name — untouched.
    ("Bleeding", None, "enemy", 10, False),
    ("Electrify", None, "enemy", 10, False),
    ("Stun", None, "enemy", 1, False),
    # Already on the caster — untouched.
    ("StatModifier", "crit_chance", "self", 15, False),
]


@pytest.fixture
def table():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE skill_base_effects (id INTEGER PRIMARY KEY, effect_name TEXT, "
               "attribute_key TEXT, target_side TEXT, magnitude REAL)")
    db.executemany(
        "INSERT INTO skill_base_effects (effect_name, attribute_key, target_side, magnitude) "
        "VALUES (?, ?, ?, ?)",
        [r[:4] for r in ROWS],
    )
    yield db
    db.close()


def test_only_buffs_aimed_at_enemies_move_to_self(table):
    before = dict(table.execute("SELECT id, target_side FROM skill_base_effects"))
    table.execute(f"UPDATE skill_base_effects SET target_side = 'self' "
                  f"WHERE {migration.BUFFING_ENEMY_EFFECT}")
    after = dict(table.execute("SELECT id, target_side FROM skill_base_effects"))
    for row_id, (name, attr, side, mag, should_move) in enumerate(ROWS, start=1):
        expected = "self" if should_move else side
        assert after[row_id] == expected, (name, attr, side, mag, before[row_id])


def test_migration_touches_base_and_perk_effects():
    assert set(migration.TABLES) == {"skill_base_effects", "skill_perk_effects"}


def test_revision_id_fits_mysql_version_column():
    assert len(migration.revision) <= 32
    assert migration.down_revision == "010_effect_secondary_mag"
