"""Add items.is_food (FEAT-164) and report items/recipes above the rarity cap

- items.is_food BOOLEAN NOT NULL DEFAULT 0 — food gives "Сытость" when eaten.
- Rarity cap (FEAT-164): mythical/divine/demonic exist only on equipment and
  never come from crafting. This migration does NOT modify existing rows; it
  only logs non-equipment items and recipes that violate the cap so the deploy
  log documents them (prod: the mythical transmutation resource). The admin
  validator forces a valid rarity on the next edit.

Revision ID: 021_add_item_is_food
Revises: 020_add_equipment_rules
Create Date: 2026-09-17

"""
import logging

from alembic import op
import sqlalchemy as sa

revision = '021_add_item_is_food'
down_revision = '020_add_equipment_rules'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_EQUIPMENT_TYPES = ('head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet', 'weapon')
_EQUIPMENT_ONLY_RARITIES = ('mythical', 'divine', 'demonic')


def _columns(table: str) -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _report_rarity_cap_violations() -> None:
    bind = op.get_bind()
    items = bind.execute(
        sa.text(
            "SELECT id, name, item_type, item_rarity FROM items "
            "WHERE item_rarity IN :rarities AND item_type NOT IN :types"
        ).bindparams(
            sa.bindparam('rarities', expanding=True),
            sa.bindparam('types', expanding=True),
        ),
        {'rarities': list(_EQUIPMENT_ONLY_RARITIES), 'types': list(_EQUIPMENT_TYPES)},
    ).fetchall()
    for row in items:
        logger.warning(
            "FEAT-164 rarity cap: non-equipment item id=%s name=%r type=%s rarity=%s left unchanged",
            row[0], row[1], row[2], row[3],
        )

    recipes = bind.execute(
        sa.text(
            "SELECT r.id, r.name, r.rarity, i.item_type, i.item_rarity "
            "FROM recipes r LEFT JOIN items i ON i.id = r.result_item_id "
            "WHERE (r.rarity IN :rarities OR i.item_rarity IN :rarities) "
            "AND (i.item_type IS NULL OR i.item_type NOT IN :types)"
        ).bindparams(
            sa.bindparam('rarities', expanding=True),
            sa.bindparam('types', expanding=True),
        ),
        {'rarities': list(_EQUIPMENT_ONLY_RARITIES), 'types': list(_EQUIPMENT_TYPES)},
    ).fetchall()
    for row in recipes:
        logger.warning(
            "FEAT-164 rarity cap: recipe id=%s name=%r rarity=%s (result type=%s rarity=%s) left unchanged",
            row[0], row[1], row[2], row[3], row[4],
        )
    logger.info(
        "FEAT-164 rarity cap report: %d item(s), %d recipe(s) above the cap",
        len(items), len(recipes),
    )


def upgrade() -> None:
    if 'is_food' not in _columns('items'):
        op.add_column(
            'items',
            sa.Column('is_food', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        )
    _report_rarity_cap_violations()


def downgrade() -> None:
    if 'is_food' in _columns('items'):
        op.drop_column('items', 'is_food')
