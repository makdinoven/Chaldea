"""
FEAT-167 — the one-off backfill migration `023_weapon_damage_backfill`.

Until this feature every equipped weapon's effective damage was folded into
`character_attributes.damage`. The new model accounts it per hand, so the stored
value is wrong the moment the new code starts and equip/unequip deltas would
never cancel it again. The revision subtracts it once.

What is pinned here:
  * upgrade removes exactly the weapon damage and nothing else (armour, perks
    and buffs stay in the attribute);
  * the migration's INLINED arithmetic agrees with `crud.compute_item_damage`
    on every fixture — plain, sharpened, gemmed, sharpened+gemmed, broken,
    off-hand and empty slots (the revision deliberately does not import app
    code, so the two copies can only be kept honest by a test);
  * downgrade puts the same amount back (round-trip);
  * the `GREATEST(0, …)` clamp: a character whose stored damage is smaller than
    the weapon's damage lands on 0, never on a negative value;
  * a character with equipment but no `character_attributes` row is skipped, not
    crashed on.

The revision is driven exactly as Alembic drives it (`upgrade()` / `downgrade()`
with `op.get_bind()` pointing at the test connection), and every assertion reads
`character_attributes.damage` back out of the database.
"""

import importlib.util
import json
import os
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import crud
import models


# ---------------------------------------------------------------------------
# Load the revision module by path (it is not importable as a package)
# ---------------------------------------------------------------------------

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REVISION_PATH = os.path.join(
    _APP_DIR, "alembic", "versions", "023_weapon_damage_backfill.py"
)


def _load_revision():
    spec = importlib.util.spec_from_file_location(
        "feat167_weapon_damage_backfill", _REVISION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def revision(db_session):
    """The revision module with `op.get_bind()` bound to the test connection —
    the same contract Alembic gives it."""
    module = _load_revision()
    module.op = SimpleNamespace(get_bind=lambda: db_session.connection())
    return module


# ---------------------------------------------------------------------------
# `character_attributes` lives in character-attributes-service; inventory's
# Base does not know it, so the test creates it with the real column names.
# ---------------------------------------------------------------------------

_CHAR_ATTRS_DDL = """
CREATE TABLE IF NOT EXISTS character_attributes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    damage INTEGER NOT NULL DEFAULT 0
)
"""


@pytest.fixture()
def attrs_table(db_session):
    db_session.execute(text("DROP TABLE IF EXISTS character_attributes"))
    db_session.execute(text(_CHAR_ATTRS_DDL))
    db_session.commit()
    yield
    db_session.execute(text("DROP TABLE IF EXISTS character_attributes"))
    db_session.commit()


def _set_damage(db, character_id, damage):
    db.execute(
        text("INSERT INTO character_attributes (character_id, damage) "
             "VALUES (:cid, :dmg)"),
        {"cid": character_id, "dmg": damage},
    )
    db.commit()


def _get_damage(db, character_id):
    db.expire_all()
    row = db.execute(
        text("SELECT damage FROM character_attributes WHERE character_id = :cid"),
        {"cid": character_id},
    ).fetchone()
    return None if row is None else row[0]


def _make_item(db, name, item_type="weapon", damage_modifier=0,
               max_durability=0, **extra):
    item = models.Items(
        name=name, item_type=item_type, item_rarity="common", item_level=1,
        damage_modifier=damage_modifier, max_durability=max_durability, **extra,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _equip(db, character_id, slot_type, item, enhancement_bonuses=None,
           socketed_gems=None, current_durability=None):
    slot = models.EquipmentSlot(
        character_id=character_id,
        slot_type=slot_type,
        item_id=item.id if item else None,
        is_enabled=True,
        enhancement_points_spent=sum((enhancement_bonuses or {}).values()),
        enhancement_bonuses=json.dumps(enhancement_bonuses) if enhancement_bonuses else None,
        socketed_gems=json.dumps(socketed_gems) if socketed_gems else None,
        current_durability=current_durability,
    )
    db.add(slot)
    db.commit()
    return slot


# ══════════════════════════════════════════════════════════════════════════════
# 1. Upgrade / downgrade round-trip
# ══════════════════════════════════════════════════════════════════════════════


class TestUpgradeAndDowngrade:

    def test_upgrade_removes_exactly_the_main_weapon_damage(
        self, revision, db_session, attrs_table
    ):
        sword = _make_item(db_session, "Меч миграции", damage_modifier=10)
        _equip(db_session, 1, "main_weapon", sword)
        _set_damage(db_session, 1, 25)  # 15 base + the sword's 10 (the old model)

        revision.upgrade()
        db_session.commit()

        assert _get_damage(db_session, 1) == 15

    def test_downgrade_restores_the_original_value(
        self, revision, db_session, attrs_table
    ):
        sword = _make_item(db_session, "Меч туда-обратно", damage_modifier=10)
        _equip(db_session, 2, "main_weapon", sword)
        _set_damage(db_session, 2, 25)

        revision.upgrade()
        db_session.commit()
        assert _get_damage(db_session, 2) == 15

        revision.downgrade()
        db_session.commit()
        assert _get_damage(db_session, 2) == 25

    def test_both_hands_are_subtracted(self, revision, db_session, attrs_table):
        sword = _make_item(db_session, "Меч двуручный", damage_modifier=10)
        dagger = _make_item(db_session, "Кинжал вторичный", damage_modifier=4)
        _equip(db_session, 3, "main_weapon", sword)
        _equip(db_session, 3, "additional_weapons", dagger)
        _set_damage(db_session, 3, 39)  # 25 base + 10 + 4

        revision.upgrade()
        db_session.commit()

        assert _get_damage(db_session, 3) == 25

    def test_sharpening_and_gems_are_included(self, revision, db_session, attrs_table):
        staff = _make_item(db_session, "Посох миграции", damage_modifier=500)
        gem = _make_item(db_session, "Камень миграции", item_type="gem",
                         damage_modifier=12)
        _equip(db_session, 4, "main_weapon", staff,
               enhancement_bonuses={"damage_modifier": 5},
               socketed_gems=[gem.id, None])
        _set_damage(db_session, 4, 537)  # 20 base + 500 + 5 + 12

        revision.upgrade()
        db_session.commit()

        assert _get_damage(db_session, 4) == 20

    def test_broken_weapon_is_not_subtracted(self, revision, db_session, attrs_table):
        """A broken weapon never contributed to the attribute, so the migration
        must leave it alone — otherwise the player silently loses damage."""
        axe = _make_item(db_session, "Топор сломанный", damage_modifier=8,
                         max_durability=40)
        _equip(db_session, 5, "additional_weapons", axe, current_durability=0)
        _set_damage(db_session, 5, 30)

        revision.upgrade()
        db_session.commit()

        assert _get_damage(db_session, 5) == 30

    def test_armour_damage_is_left_in_the_attribute(
        self, revision, db_session, attrs_table
    ):
        """Only weapon slots are touched: armour and jewellery damage stays in
        `character_attributes.damage` by design."""
        plate = _make_item(db_session, "Кираса миграции", item_type="body",
                           damage_modifier=6)
        sword = _make_item(db_session, "Меч рядом с кирасой", damage_modifier=10)
        _equip(db_session, 6, "body", plate)
        _equip(db_session, 6, "main_weapon", sword)
        _set_damage(db_session, 6, 31)  # 15 base + 6 armour + 10 weapon

        revision.upgrade()
        db_session.commit()

        assert _get_damage(db_session, 6) == 21  # armour's 6 survives

    def test_character_without_weapons_is_untouched(
        self, revision, db_session, attrs_table
    ):
        _set_damage(db_session, 7, 42)
        revision.upgrade()
        db_session.commit()
        assert _get_damage(db_session, 7) == 42

    def test_empty_weapon_slot_is_untouched(self, revision, db_session, attrs_table):
        _equip(db_session, 8, "main_weapon", None)
        _set_damage(db_session, 8, 42)
        revision.upgrade()
        db_session.commit()
        assert _get_damage(db_session, 8) == 42

    def test_zero_damage_weapon_changes_nothing(
        self, revision, db_session, attrs_table
    ):
        club = _make_item(db_session, "Дубина без урона", damage_modifier=0)
        _equip(db_session, 9, "main_weapon", club)
        _set_damage(db_session, 9, 17)
        revision.upgrade()
        db_session.commit()
        assert _get_damage(db_session, 9) == 17

    def test_multiple_characters_are_each_handled_separately(
        self, revision, db_session, attrs_table
    ):
        sword = _make_item(db_session, "Меч общий", damage_modifier=10)
        dagger = _make_item(db_session, "Кинжал общий", damage_modifier=3)
        _equip(db_session, 10, "main_weapon", sword)
        _equip(db_session, 11, "main_weapon", dagger)
        _set_damage(db_session, 10, 100)
        _set_damage(db_session, 11, 100)
        _set_damage(db_session, 12, 100)  # no equipment at all

        revision.upgrade()
        db_session.commit()

        assert _get_damage(db_session, 10) == 90
        assert _get_damage(db_session, 11) == 97
        assert _get_damage(db_session, 12) == 100


# ══════════════════════════════════════════════════════════════════════════════
# 2. Clamp and anomalies
# ══════════════════════════════════════════════════════════════════════════════


class TestClampAndAnomalies:

    def test_negative_result_is_clamped_to_zero(
        self, revision, db_session, attrs_table
    ):
        sword = _make_item(db_session, "Меч аномальный", damage_modifier=50)
        _equip(db_session, 20, "main_weapon", sword)
        _set_damage(db_session, 20, 10)  # less than the weapon's damage

        revision.upgrade()
        db_session.commit()

        assert _get_damage(db_session, 20) == 0

    def test_anomaly_is_logged_not_silent(
        self, revision, db_session, attrs_table, caplog
    ):
        sword = _make_item(db_session, "Меч аномальный 2", damage_modifier=50)
        _equip(db_session, 21, "main_weapon", sword)
        _set_damage(db_session, 21, 10)

        with caplog.at_level("WARNING", logger="alembic.runtime.migration"):
            revision.upgrade()
            db_session.commit()

        assert any("21" in record.getMessage() for record in caplog.records), \
            "the clamped anomaly must be reported, never applied silently"

    def test_missing_attributes_row_is_skipped_with_a_warning(
        self, revision, db_session, attrs_table, caplog
    ):
        sword = _make_item(db_session, "Меч без атрибутов", damage_modifier=10)
        _equip(db_session, 22, "main_weapon", sword)

        with caplog.at_level("WARNING", logger="alembic.runtime.migration"):
            revision.upgrade()
            db_session.commit()

        assert _get_damage(db_session, 22) is None
        assert caplog.records, "a character without attributes must be reported"

    def test_malformed_enhancement_json_does_not_break_the_migration(
        self, revision, db_session, attrs_table
    ):
        sword = _make_item(db_session, "Меч с битым JSON", damage_modifier=10)
        slot = _equip(db_session, 23, "main_weapon", sword)
        slot.enhancement_bonuses = "{not json"
        db_session.commit()
        _set_damage(db_session, 23, 25)

        revision.upgrade()
        db_session.commit()

        # the sharpening is unknown -> only the template value is removed
        assert _get_damage(db_session, 23) == 15


# ══════════════════════════════════════════════════════════════════════════════
# 3. The migration and `crud.compute_item_damage` must agree
# ══════════════════════════════════════════════════════════════════════════════


_CASES = [
    # (name, damage_modifier, max_durability, bonuses, gem_damage, durability)
    ("plain", 10, 0, None, None, None),
    ("sharpened", 10, 0, {"damage_modifier": 5}, None, None),
    ("gemmed", 10, 0, None, 4, None),
    ("sharpened_and_gemmed", 500, 0, {"damage_modifier": 5}, 12, None),
    ("other_stat_sharpened", 10, 0, {"strength_modifier": 5}, None, None),
    ("damaged_not_broken", 25, 60, None, None, 1),
    ("broken", 25, 60, None, None, 0),
    ("zero_damage", 0, 0, {"damage_modifier": 2}, None, None),
]


class TestMigrationMatchesComputeItemDamage:

    @pytest.mark.parametrize(
        "name, dmg, max_dur, bonuses, gem_damage, durability", _CASES,
        ids=[case[0] for case in _CASES],
    )
    def test_per_slot_agreement(self, revision, db_session, attrs_table,
                                name, dmg, max_dur, bonuses, gem_damage, durability):
        """One character per case: what the migration subtracts must equal what
        `compute_item_damage` (and therefore `effective_damage`) reports."""
        weapon = _make_item(db_session, f"Оружие {name}", damage_modifier=dmg,
                            max_durability=max_dur)
        gem_items = []
        gem_ids = None
        if gem_damage:
            gem = _make_item(db_session, f"Камень {name}", item_type="gem",
                             damage_modifier=gem_damage)
            gem_items = [gem]
            gem_ids = [gem.id]

        character_id = 30
        _equip(db_session, character_id, "main_weapon", weapon,
               enhancement_bonuses=bonuses, socketed_gems=gem_ids,
               current_durability=durability)

        expected = crud.compute_item_damage(
            weapon, enhancement_bonuses=bonuses, gem_items=gem_items,
            current_durability=durability, max_durability=max_dur,
        )

        per_character = revision._damage_per_character(db_session.connection())
        assert per_character.get(character_id, 0) == expected, (
            f"case {name}: migration removes {per_character.get(character_id, 0)}, "
            f"compute_item_damage says {expected}"
        )

        start = 1000
        _set_damage(db_session, character_id, start)
        revision.upgrade()
        db_session.commit()
        assert _get_damage(db_session, character_id) == start - expected

    def test_agreement_on_a_mixed_character(self, revision, db_session, attrs_table):
        """Both hands at once, one of them sharpened and gemmed."""
        sword = _make_item(db_session, "Меч смешанный", damage_modifier=18)
        dagger = _make_item(db_session, "Кинжал смешанный", damage_modifier=7)
        gem = _make_item(db_session, "Камень смешанный", item_type="gem",
                         damage_modifier=2)
        _equip(db_session, 40, "main_weapon", sword,
               enhancement_bonuses={"damage_modifier": 3}, socketed_gems=[gem.id])
        _equip(db_session, 40, "additional_weapons", dagger)

        expected = (
            crud.compute_item_damage(
                sword, enhancement_bonuses={"damage_modifier": 3}, gem_items=[gem]
            )
            + crud.compute_item_damage(dagger)
        )
        per_character = revision._damage_per_character(db_session.connection())
        assert per_character[40] == expected == 30  # (18+3+2) + 7


# ══════════════════════════════════════════════════════════════════════════════
# 4. Cross-service / bookkeeping guards
# ══════════════════════════════════════════════════════════════════════════════


class TestRevisionMetadata:

    def test_revision_is_wired_into_the_chain(self, revision):
        assert revision.revision == "023_weapon_damage_backfill"
        assert revision.down_revision == "022_profession_rework"

    def test_revision_does_not_import_app_code(self):
        """The arithmetic is inlined on purpose: a migration must not depend on
        `crud`, which can change after the revision has run in production."""
        with open(_REVISION_PATH, encoding="utf-8") as fh:
            source = fh.read()
        assert not re.search(r"^\s*(from|import)\s+crud", source, re.MULTILINE)
        # the helper may be *mentioned* in the docstring, but never called
        assert "crud.compute_item_damage(" not in source
        assert not re.search(r"^\s*[^#\s].*compute_item_damage\(", source, re.MULTILINE)

    def test_migration_targets_the_real_char_attrs_columns(self):
        """The revision writes a table owned by character-attributes-service.
        Pin the column names against that service's model so a rename there
        cannot leave this migration silently updating nothing."""
        char_attrs_models = os.path.abspath(os.path.join(
            _APP_DIR, "..", "..", "character-attributes-service", "app", "models.py"
        ))
        if not os.path.exists(char_attrs_models):
            pytest.skip("character-attributes-service source not available")
        with open(char_attrs_models, encoding="utf-8") as fh:
            source = fh.read()
        assert "__tablename__ = 'character_attributes'" in source \
            or '__tablename__ = "character_attributes"' in source
        assert re.search(r"^\s*character_id\s*=\s*Column", source, re.MULTILINE)
        assert re.search(r"^\s*damage\s*=\s*Column", source, re.MULTILINE)
