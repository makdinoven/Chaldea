"""
`damage` is a pure bonus field — the class's main attribute is NOT seeded here.

FEAT-113 made `compute_derived_stats` set `damage` to the value of the class's
main attribute. But the damage formula adds that attribute itself:
`base = base_stat + damage + weapon` in
`battle-service/app/battle_engine.py::compute_damage_with_rolls`, and the same
shape on the profile in `.../StatsTab/damage.ts`. A warrior's point of strength
therefore bought two points of damage — for every class, once a recalculation
had run.

Design decision (2026-09-20): one strength = one damage. The attribute is
counted once, by the formula, and `compute_derived_stats` leaves `damage` at 0
so the column carries only what equipment, sharpening and perks put there.

These tests pin that down from both directions: the unit call and the two
integration paths that used to pass `class_id` in for this purpose.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, event, Boolean, Column, Integer, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Patch database BEFORE importing app modules
_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402
database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import models  # noqa: E402
import crud  # noqa: E402
import schemas  # noqa: E402
from constants import CLASS_MAIN_ATTRIBUTE  # noqa: E402


# ---------------------------------------------------------------------------
# We need a `characters` table for integration tests. The character-attributes
# service does not own it, but queries it via raw SQL for id_class.
# Create a minimal SQLAlchemy model so create_all builds the table.
# ---------------------------------------------------------------------------

class _Character(database.Base):
    __tablename__ = "characters"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    name = Column(String(100), nullable=True)
    id_class = Column(Integer, nullable=True)
    # FEAT-164: settle_regen reads characters.is_npc (real column, character-service).
    is_npc = Column(Boolean, nullable=False, default=False, server_default="0")
    # Minimal columns needed by queries across test files (id_class for
    # damage-from-class tests, user_id + name for ownership checks in auth tests).


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_attr(db, character_id=1, **overrides):
    """Create a CharacterAttributes row with sensible defaults."""
    defaults = dict(
        character_id=character_id,
        current_health=100,
        max_health=100,
        current_mana=75,
        max_mana=75,
        current_energy=50,
        max_energy=50,
        current_stamina=100,
        max_stamina=100,
        strength=10,
        agility=10,
        intelligence=10,
        endurance=10,
        health=10,
        mana=7,
        energy=5,
        stamina=10,
        charisma=1,
        luck=1,
        damage=0,
    )
    defaults.update(overrides)
    attr = models.CharacterAttributes(**defaults)
    db.add(attr)
    db.commit()
    db.refresh(attr)
    return attr


def _make_character(db, character_id=1, id_class=1):
    """Insert a minimal character row for integration tests."""
    char = _Character(id=character_id, id_class=id_class)
    db.add(char)
    db.commit()
    return char


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    database.Base.metadata.create_all(bind=_test_engine)
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        database.Base.metadata.drop_all(bind=_test_engine)


# ===========================================================================
# 1. Unit: compute_derived_stats never seeds damage
# ===========================================================================

class TestComputeDerivedStatsLeavesDamageAlone:
    """`damage` must come out 0 whatever the class and whatever the stats."""

    @pytest.mark.parametrize("class_id", [1, 2, 3, 99, None])
    def test_damage_is_zero_for_every_class(self, db_session, class_id):
        attr = _make_attr(
            db_session,
            character_id=(class_id or 0) + 1,
            strength=50, agility=45, intelligence=60,
        )
        crud.compute_derived_stats(attr, class_id=class_id)
        assert attr.damage == 0

    def test_damage_is_zero_without_the_class_id_kwarg(self, db_session):
        attr = _make_attr(db_session, strength=50)
        crud.compute_derived_stats(attr)
        assert attr.damage == 0

    def test_an_existing_bonus_is_cleared_not_doubled(self, db_session):
        """Recalculation rebuilds derived stats from base — equipment bonuses
        are re-applied afterwards by apply_modifiers, never accumulated here."""
        attr = _make_attr(db_session, strength=50)
        attr.damage = 17          # as if equipment had added it
        crud.compute_derived_stats(attr, class_id=1)
        assert attr.damage == 0

    def test_the_other_derived_stats_still_follow_the_attributes(self, db_session):
        """Guard against 'fixing' damage by gutting compute_derived_stats."""
        attr = _make_attr(db_session, strength=50, agility=20, intelligence=30)
        crud.compute_derived_stats(attr, class_id=1)
        assert attr.res_physical == pytest.approx(5.0)    # strength * 0.1
        assert attr.res_magic == pytest.approx(3.0)       # intelligence * 0.1

    def test_class_main_attribute_mapping_matches_expected(self):
        """The mapping still exists — the damage formula reads it."""
        assert CLASS_MAIN_ATTRIBUTE == {
            1: "strength",
            2: "agility",
            3: "intelligence",
        }


# ===========================================================================
# 2. Integration: the two paths that used to seed damage from the class
# ===========================================================================

class TestRecalculateAttributesLeavesDamageAlone:
    """`recalculate_attributes` reads characters.id_class — and must not use it
    to seed damage."""

    @pytest.mark.parametrize("id_class, stats", [
        (1, {"strength": 42}),
        (2, {"agility": 55}),
        (3, {"intelligence": 38}),
    ])
    def test_damage_is_zero_after_recalculation(self, db_session, id_class, stats):
        _make_character(db_session, character_id=1, id_class=id_class)
        _make_attr(db_session, character_id=1, **stats)
        result = crud.recalculate_attributes(db_session, 1)
        assert result is not None
        assert result.damage == 0

    def test_no_character_row_damage_zero(self, db_session):
        _make_attr(db_session, character_id=7, strength=50)
        result = crud.recalculate_attributes(db_session, 7)
        assert result is not None
        assert result.damage == 0

    def test_raising_the_main_stat_does_not_raise_damage(self, db_session):
        _make_character(db_session, character_id=1, id_class=1)
        attr = _make_attr(db_session, character_id=1, strength=20)
        crud.recalculate_attributes(db_session, 1)

        attr.strength = 80
        db_session.commit()
        result = crud.recalculate_attributes(db_session, 1)
        assert result.strength == 80
        assert result.damage == 0


class TestCreateCharacterAttributesLeavesDamageAlone:
    """Creation queries the class too — same rule applies."""

    @pytest.mark.parametrize("id_class, stats", [
        (1, {"strength": 40}),
        (3, {"intelligence": 33}),
    ])
    def test_damage_is_zero_on_create(self, db_session, id_class, stats):
        _make_character(db_session, character_id=5, id_class=id_class)
        payload = schemas.CharacterAttributesCreate(character_id=5, **stats)
        result = crud.create_character_attributes(db_session, payload)
        assert result.damage == 0

    def test_no_character_row_create_damage_zero(self, db_session):
        payload = schemas.CharacterAttributesCreate(character_id=9, strength=40)
        result = crud.create_character_attributes(db_session, payload)
        assert result.damage == 0
