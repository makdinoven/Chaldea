"""Fourth gathering node category: ingredient (FEAT-165).

Ingredient nodes are gathered without a tool (skill slug `foraging` in
inventory-service). Appending an ENUM value is safe on MySQL.

Downgrade is fail-fast: if any `ingredient` node exists, the admin must delete
or recategorise it first — shrinking the ENUM would otherwise corrupt the rows.

Revision ID: 043_gathering_ingredient
Revises: 042_recommended_level_ranges
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa

# Revision id kept <= 32 chars (alembic_version_locations.version_num).
revision = '043_gathering_ingredient'
down_revision = '042_recommended_level_ranges'
branch_labels = None
depends_on = None

CATEGORIES_OLD = ('ore', 'herb', 'wood')
CATEGORIES_NEW = ('ore', 'herb', 'wood', 'ingredient')


def _enum(values) -> str:
    return "ENUM(" + ",".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE gathering_nodes MODIFY COLUMN category "
        f"{_enum(CATEGORIES_NEW)} NOT NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id FROM gathering_nodes WHERE category = 'ingredient' "
            "ORDER BY id"
        )
    ).fetchall()
    if rows:
        ids = ", ".join(str(r[0]) for r in rows)
        raise RuntimeError(
            f"Migration 043 downgrade: {len(rows)} gathering node(s) with "
            f"category 'ingredient' still exist (ids {ids}). Delete or "
            f"recategorise them first."
        )
    op.execute(
        f"ALTER TABLE gathering_nodes MODIFY COLUMN category "
        f"{_enum(CATEGORIES_OLD)} NOT NULL"
    )
