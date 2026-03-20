"""
Tests for photo-service SQLAlchemy mirror models (FEAT-034).

Verifies that each model has the expected table name and columns,
matching the actual DB schema that photo-service reads/writes.
"""

from sqlalchemy import Integer, String, Text
from models import (
    User, Character, Country, Region, District,
    Location, Skill, SkillRank, Item, GameRule,
)


def _column_names(model_cls):
    """Return set of column names for a model class."""
    return {c.name for c in model_cls.__table__.columns}


def _column_type(model_cls, col_name):
    """Return the SQLAlchemy type class for a column."""
    return type(model_cls.__table__.c[col_name].type)


# ===========================================================================
# 1. Table names
# ===========================================================================

class TestTableNames:
    """Verify __tablename__ matches actual MySQL table names."""

    def test_user_table(self):
        assert User.__tablename__ == "users"

    def test_character_table(self):
        assert Character.__tablename__ == "characters"

    def test_country_table(self):
        assert Country.__tablename__ == "Countries"

    def test_region_table(self):
        assert Region.__tablename__ == "Regions"

    def test_district_table(self):
        assert District.__tablename__ == "Districts"

    def test_location_table(self):
        assert Location.__tablename__ == "Locations"

    def test_skill_table(self):
        assert Skill.__tablename__ == "skills"

    def test_skill_rank_table(self):
        assert SkillRank.__tablename__ == "skill_ranks"

    def test_item_table(self):
        assert Item.__tablename__ == "items"

    def test_game_rule_table(self):
        assert GameRule.__tablename__ == "game_rules"


# ===========================================================================
# 2. Column existence — verify all columns photo-service uses are defined
# ===========================================================================

class TestColumnPresence:
    """Each model must have exactly the columns that crud.py reads/writes."""

    def test_user_columns(self):
        cols = _column_names(User)
        assert {"id", "avatar", "profile_bg_image"} == cols

    def test_character_columns(self):
        cols = _column_names(Character)
        assert {"id", "user_id", "avatar"} == cols

    def test_country_columns(self):
        cols = _column_names(Country)
        assert {"id", "map_image_url", "emblem_url"} == cols

    def test_region_columns(self):
        cols = _column_names(Region)
        assert {"id", "map_image_url", "image_url"} == cols

    def test_district_columns(self):
        cols = _column_names(District)
        assert {"id", "image_url", "map_icon_url"} == cols

    def test_location_columns(self):
        cols = _column_names(Location)
        assert {"id", "image_url", "map_icon_url"} == cols

    def test_skill_columns(self):
        cols = _column_names(Skill)
        assert {"id", "skill_image"} == cols

    def test_skill_rank_columns(self):
        cols = _column_names(SkillRank)
        assert {"id", "rank_image"} == cols

    def test_item_columns(self):
        cols = _column_names(Item)
        assert {"id", "image"} == cols

    def test_game_rule_columns(self):
        cols = _column_names(GameRule)
        assert {"id", "image_url"} == cols


# ===========================================================================
# 3. Primary keys
# ===========================================================================

class TestPrimaryKeys:
    """Every model must have 'id' as the primary key."""

    def test_all_models_have_id_pk(self):
        for model in (User, Character, Country, Region, District,
                      Location, Skill, SkillRank, Item, GameRule):
            pk_cols = [c.name for c in model.__table__.primary_key.columns]
            assert pk_cols == ["id"], f"{model.__name__} PK is {pk_cols}, expected ['id']"


# ===========================================================================
# 4. Column types — verify key type choices
# ===========================================================================

class TestColumnTypes:
    """Verify important column type choices match expectations."""

    def test_user_avatar_is_string(self):
        assert _column_type(User, "avatar") == String

    def test_character_user_id_is_integer(self):
        assert _column_type(Character, "user_id") == Integer

    def test_country_map_image_url_is_text(self):
        assert _column_type(Country, "map_image_url") == Text

    def test_item_image_is_string(self):
        assert _column_type(Item, "image") == String

    def test_game_rule_image_url_is_text(self):
        assert _column_type(GameRule, "image_url") == Text
