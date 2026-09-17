"""
FEAT-165 — ORM enums must match migration 022 exactly.

Tests build the schema with SQLite `create_all` from the ORM, so a drift
between models.py and the Alembic migration would go unnoticed by every other
test and only explode on MySQL (silent-failure guard).

The conftest replaces ENUM columns of `items` with String for SQLite; the real
values are captured before that patch (`original_enum_values` fixture).
"""

import importlib.util
import os

import pytest

import crud
import models
import schemas

_VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _load_migration(filename):
    path = os.path.join(_VERSIONS_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def m022():
    return _load_migration("022_profession_rework.py")


class TestMigrationChain:

    def test_revision_ids(self, m022):
        assert m022.revision == "022_profession_rework"
        assert m022.down_revision == "021_add_item_is_food"
        # alembic_version_inventory.version_num is VARCHAR(32)
        assert len(m022.revision) <= 32


class TestOrmEnumsMatchMigration:

    def test_item_type_matches_and_has_no_blueprint(self, m022, original_enum_values):
        orm_values = original_enum_values["items.item_type"]
        assert list(orm_values) == list(m022.ITEM_TYPES_NEW)
        assert "blueprint" not in orm_values
        assert "blueprint" in m022.ITEM_TYPES_OLD  # downgrade restores it

    def test_item_type_matches_pydantic_enum(self, original_enum_values):
        assert set(original_enum_values["items.item_type"]) == {t.value for t in schemas.ItemType}

    def test_resource_subcategory_matches(self, m022, original_enum_values):
        orm_values = original_enum_values["items.resource_subcategory"]
        assert list(orm_values) == list(m022.RESOURCE_SUBCATEGORIES)
        assert set(orm_values) == {s.value for s in schemas.ResourceSubcategory}
        # crud groups cover exactly the enum
        assert set(orm_values) == set(
            crud.RAW_SUBCATEGORIES + crud.PRODUCT_SUBCATEGORIES + crud.TOOL_SUBCATEGORIES
        )

    def test_whetstone_group_matches(self, m022, original_enum_values):
        orm_values = original_enum_values["items.whetstone_group"]
        assert list(orm_values) == list(m022.WHETSTONE_GROUPS)
        assert set(orm_values) == {g.value for g in schemas.WhetstoneGroup}
        assert set(orm_values) == set(crud.SHARPEN_GROUP_TYPES.keys())

    def test_gathering_skill_category_matches(self, m022, original_enum_values):
        orm_values = original_enum_values["gathering_skills.category"]
        assert list(orm_values) == list(m022.GATHERING_CATEGORIES_NEW)
        assert "ingredient" in orm_values
        assert m022.GATHERING_CATEGORIES_OLD == ["ore", "herb", "wood"]

    def test_foraging_seed_constants(self, m022):
        assert m022.FORAGING_SLUG == "foraging"
        assert m022.FORAGING_CATEGORY == "ingredient"
        assert m022.FORAGING_SLUG in schemas.GATHERING_SKILL_SLUGS
        assert len(m022.DEFAULT_GATHERING_RANKS) == 5

    def test_removed_columns_are_gone_from_orm(self):
        item_cols = set(models.Items.__table__.columns.keys())
        assert "essence_result_item_id" not in item_cols
        assert {"resource_subcategory", "whetstone_group", "blueprint_recipe_id"} <= item_cols
        assert "is_blueprint_recipe" not in models.Recipe.__table__.columns.keys()

    def test_item_conversions_table_shape(self):
        table = models.ItemConversion.__table__
        assert table.name == "item_conversions"
        assert set(table.columns.keys()) == {
            "id", "source_item_id", "profession_id", "source_quantity",
            "result_item_id", "result_quantity", "created_at", "updated_at",
        }
        uniques = {
            c.name for c in table.constraints if type(c).__name__ == "UniqueConstraint"
        }
        assert "uq_item_conversion" in uniques

    def test_refining_rules_use_known_subcategories(self):
        for slug, (source, result) in crud.REFINING_RULES.items():
            assert source in crud.RAW_SUBCATEGORIES + ("reagent",), slug
            assert result in crud.PRODUCT_SUBCATEGORIES, slug
        assert "enchanter" not in crud.REFINING_RULES
