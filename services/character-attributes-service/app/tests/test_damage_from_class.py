"""
Tests for FEAT-113: NPC damage computed from class main stat.

Verifies that:
- compute_derived_stats sets damage based on class_id -> main attribute mapping
- Warrior (class_id=1) -> strength, Rogue (class_id=2) -> agility,
  Mage (class_id=3) -> intelligence
- None / unknown class_id -> damage = 0
- Integration: recalculate_attributes and create_character_attributes
  query characters.id_class and pass it to compute_derived_stats
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, event, Column, Integer, String
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
    id_class = Column(Integer, nullable=True)
    # Minimal columns; only id and id_class are needed by the queries.


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
# 1. Unit tests: compute_derived_stats damage from class_id
# ===========================================================================

class TestComputeDerivedStatsDamage:
    """Unit tests for the damage computation inside compute_derived_stats."""

    def test_warrior_damage_equals_strength(self, db_session):
        """class_id=1 (warrior): damage = strength."""
        attr = _make_attr(db_session, strength=50, agility=20, intelligence=30)
        crud.compute_derived_stats(attr, class_id=1)
        assert attr.damage == 50

    def test_rogue_damage_equals_agility(self, db_session):
        """class_id=2 (rogue): damage = agility."""
        attr = _make_attr(db_session, strength=20, agility=45, intelligence=30)
        crud.compute_derived_stats(attr, class_id=2)
        assert attr.damage == 45

    def test_mage_damage_equals_intelligence(self, db_session):
        """class_id=3 (mage): damage = intelligence."""
        attr = _make_attr(db_session, strength=20, agility=30, intelligence=60)
        crud.compute_derived_stats(attr, class_id=3)
        assert attr.damage == 60

    def test_none_class_id_damage_is_zero(self, db_session):
        """class_id=None: damage = 0."""
        attr = _make_attr(db_session, strength=50, agility=50, intelligence=50)
        crud.compute_derived_stats(attr, class_id=None)
        assert attr.damage == 0

    def test_unknown_class_id_damage_is_zero(self, db_session):
        """class_id=99 (not in mapping): damage = 0."""
        attr = _make_attr(db_session, strength=50, agility=50, intelligence=50)
        crud.compute_derived_stats(attr, class_id=99)
        assert attr.damage == 0

    def test_zero_stats_damage_zero_regardless_of_class(self, db_session):
        """All base stats 0: damage = 0 for any valid class."""
        for class_id in (1, 2, 3):
            attr = _make_attr(
                db_session,
                character_id=class_id + 100,  # unique per iteration
                strength=0, agility=0, intelligence=0,
            )
            crud.compute_derived_stats(attr, class_id=class_id)
            assert attr.damage == 0, f"Expected damage=0 for class_id={class_id} with zero stats"

    def test_high_stats_damage_matches_exact_value(self, db_session):
        """High stat values: damage equals the exact stat value."""
        attr = _make_attr(db_session, strength=9999)
        crud.compute_derived_stats(attr, class_id=1)
        assert attr.damage == 9999

        attr2 = _make_attr(db_session, character_id=2, agility=12345)
        crud.compute_derived_stats(attr2, class_id=2)
        assert attr2.damage == 12345

        attr3 = _make_attr(db_session, character_id=3, intelligence=7777)
        crud.compute_derived_stats(attr3, class_id=3)
        assert attr3.damage == 7777

    def test_default_call_without_class_id_damage_zero(self, db_session):
        """Calling compute_derived_stats without class_id kwarg gives damage=0."""
        attr = _make_attr(db_session, strength=50)
        crud.compute_derived_stats(attr)
        assert attr.damage == 0

    def test_class_main_attribute_mapping_matches_expected(self):
        """CLASS_MAIN_ATTRIBUTE has exactly the expected entries."""
        assert CLASS_MAIN_ATTRIBUTE == {
            1: "strength",
            2: "agility",
            3: "intelligence",
        }


# ===========================================================================
# 2. Integration tests: recalculate_attributes and create_character_attributes
# ===========================================================================

class TestRecalculateAttributesDamage:
    """Integration: recalculate_attributes queries characters.id_class."""

    def test_warrior_recalculate_damage_equals_strength(self, db_session):
        """recalculate_attributes for a warrior sets damage = strength."""
        _make_character(db_session, character_id=1, id_class=1)
        _make_attr(db_session, character_id=1, strength=42, agility=10, intelligence=10)

        result = crud.recalculate_attributes(db_session, character_id=1)
        assert result is not None
        assert result.damage == 42

    def test_mage_recalculate_damage_equals_intelligence(self, db_session):
        """recalculate_attributes for a mage sets damage = intelligence."""
        _make_character(db_session, character_id=1, id_class=3)
        _make_attr(db_session, character_id=1, strength=10, agility=10, intelligence=55)

        result = crud.recalculate_attributes(db_session, character_id=1)
        assert result is not None
        assert result.damage == 55

    def test_rogue_recalculate_damage_equals_agility(self, db_session):
        """recalculate_attributes for a rogue sets damage = agility."""
        _make_character(db_session, character_id=1, id_class=2)
        _make_attr(db_session, character_id=1, strength=10, agility=38, intelligence=10)

        result = crud.recalculate_attributes(db_session, character_id=1)
        assert result is not None
        assert result.damage == 38

    def test_no_character_row_damage_zero(self, db_session):
        """If characters row is missing, damage defaults to 0."""
        # No _make_character call -- orphaned attributes
        _make_attr(db_session, character_id=999, strength=50)

        result = crud.recalculate_attributes(db_session, character_id=999)
        assert result is not None
        assert result.damage == 0

    def test_damage_updates_when_stat_changes(self, db_session):
        """Damage changes when base stat changes and recalculate is called."""
        _make_character(db_session, character_id=1, id_class=1)
        _make_attr(db_session, character_id=1, strength=20)

        result = crud.recalculate_attributes(db_session, character_id=1)
        assert result.damage == 20

        # Simulate stat change
        result.strength = 80
        db_session.commit()

        result2 = crud.recalculate_attributes(db_session, character_id=1)
        assert result2.damage == 80


class TestCreateCharacterAttributesDamage:
    """Integration: create_character_attributes queries characters.id_class."""

    def test_mage_create_damage_equals_intelligence(self, db_session):
        """create_character_attributes for a mage sets damage = intelligence."""
        _make_character(db_session, character_id=10, id_class=3)

        attr_data = schemas.CharacterAttributesCreate(
            character_id=10,
            strength=5,
            agility=5,
            intelligence=40,
            endurance=10,
            health=10,
            mana=7,
            energy=5,
            stamina=10,
            charisma=1,
            luck=1,
        )
        result = crud.create_character_attributes(db_session, attr_data)
        assert result.damage == 40

    def test_warrior_create_damage_equals_strength(self, db_session):
        """create_character_attributes for a warrior sets damage = strength."""
        _make_character(db_session, character_id=11, id_class=1)

        attr_data = schemas.CharacterAttributesCreate(
            character_id=11,
            strength=33,
            agility=5,
            intelligence=5,
            endurance=10,
            health=10,
            mana=7,
            energy=5,
            stamina=10,
            charisma=1,
            luck=1,
        )
        result = crud.create_character_attributes(db_session, attr_data)
        assert result.damage == 33

    def test_no_character_row_create_damage_zero(self, db_session):
        """create_character_attributes with no characters row -> damage = 0."""
        attr_data = schemas.CharacterAttributesCreate(
            character_id=999,
            strength=50,
            agility=50,
            intelligence=50,
            endurance=10,
            health=10,
            mana=7,
            energy=5,
            stamina=10,
            charisma=1,
            luck=1,
        )
        result = crud.create_character_attributes(db_session, attr_data)
        assert result.damage == 0
