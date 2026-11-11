"""Stolen caravan bales (FEAT-211): `items.is_stolen`, `items.bale_group` + 12 bales.

- is_stolen   TINYINT(1) NOT NULL DEFAULT 0 — item-level «краденое» mark; the
  auction refuses such items, ordinary merchants never buy them, only a fence.
- bale_group  VARCHAR(32) NULL — goods group code the bale stands for (VARCHAR,
  not ENUM: no `items` table lock on a new group).

Seeds one stolen bale per goods group (`misc`, common, stack 999, price 50 —
admins tune prices later). A name that already exists is skipped.

Plain columns only, no `item_type` ENUM change. Idempotent.

Downgrade: removes the 12 bales (rows referencing them in tables whose FK is
not ON DELETE CASCADE / SET NULL are deleted or nulled first — pre-beta data
loss accepted), then drops both columns.

Revision ID: 037_stolen_bales
Revises: 036_item_admin_ready
Create Date: 2026-11-11

"""
from alembic import op
import sqlalchemy as sa

revision = '037_stolen_bales'
down_revision = '036_item_admin_ready'
branch_labels = None
depends_on = None

BALE_DESCRIPTION = 'Краденый товар. Его купит только скупщик.'
BALE_PRICE = 50
BALE_STACK = 999

# (goods group code, bale name)
BALES = (
    ('food', 'Тюк зерна (краденое)'),
    ('ore_metal', 'Слиток руды (краденое)'),
    ('wood', 'Связка древесины (краденое)'),
    ('herbs', 'Тюк трав (краденое)'),
    ('hides_textiles', 'Тюк кож и тканей (краденое)'),
    ('magic', 'Ящик магических материалов (краденое)'),
    ('weapons', 'Ящик оружия (краденое)'),
    ('armor', 'Тюк доспехов (краденое)'),
    ('jewelry', 'Шкатулка украшений (краденое)'),
    ('potions', 'Ящик зелий (краденое)'),
    ('tools', 'Ящик инструментов (краденое)'),
    ('household', 'Тюк утвари (краденое)'),
)


def _has_column(table, column):
    inspector = sa.inspect(op.get_bind())
    return column in {c['name'] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column('items', 'is_stolen'):
        op.add_column(
            'items',
            sa.Column('is_stolen', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        )
    if not _has_column('items', 'bale_group'):
        op.add_column('items', sa.Column('bale_group', sa.String(32), nullable=True))

    bind = op.get_bind()
    for group_code, name in BALES:
        exists = bind.execute(
            sa.text("SELECT id FROM items WHERE name = :name"), {"name": name}
        ).fetchone()
        if exists:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO items (name, image, item_level, item_type, item_rarity, price, "
                "max_stack_size, is_unique, description, fast_slot_bonus, is_stolen, bale_group) "
                "VALUES (:name, NULL, 0, 'misc', 'common', :price, :stack, 0, :descr, 0, 1, :grp)"
            ),
            {
                "name": name,
                "price": BALE_PRICE,
                "stack": BALE_STACK,
                "descr": BALE_DESCRIPTION,
                "grp": group_code,
            },
        )


def _clear_references(bind, item_ids):
    """Delete / null rows that point at the bales through a non-cascading FK."""
    refs = bind.execute(sa.text(
        "SELECT k.TABLE_NAME, k.COLUMN_NAME, r.DELETE_RULE, c.IS_NULLABLE "
        "FROM information_schema.KEY_COLUMN_USAGE k "
        "JOIN information_schema.REFERENTIAL_CONSTRAINTS r "
        "  ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME "
        "JOIN information_schema.COLUMNS c "
        "  ON c.TABLE_SCHEMA = k.TABLE_SCHEMA AND c.TABLE_NAME = k.TABLE_NAME "
        "  AND c.COLUMN_NAME = k.COLUMN_NAME "
        "WHERE k.TABLE_SCHEMA = DATABASE() AND k.REFERENCED_TABLE_NAME = 'items' "
        "  AND k.REFERENCED_COLUMN_NAME = 'id'"
    )).fetchall()
    params = {f"i{n}": item_id for n, item_id in enumerate(item_ids)}
    in_list = ", ".join(f":{key}" for key in params)
    for table, column, delete_rule, is_nullable in refs:
        if delete_rule in ('CASCADE', 'SET NULL'):
            continue
        if is_nullable == 'YES':
            bind.execute(
                sa.text(f"UPDATE `{table}` SET `{column}` = NULL WHERE `{column}` IN ({in_list})"),
                params,
            )
        else:
            bind.execute(
                sa.text(f"DELETE FROM `{table}` WHERE `{column}` IN ({in_list})"), params
            )


def downgrade():
    bind = op.get_bind()
    if _has_column('items', 'is_stolen'):
        names = [name for _, name in BALES]
        params = {f"n{n}": name for n, name in enumerate(names)}
        in_list = ", ".join(f":{key}" for key in params)
        rows = bind.execute(
            sa.text(f"SELECT id FROM items WHERE is_stolen = 1 AND name IN ({in_list})"),
            params,
        ).fetchall()
        item_ids = [row[0] for row in rows]
        if item_ids:
            _clear_references(bind, item_ids)
            id_params = {f"i{n}": item_id for n, item_id in enumerate(item_ids)}
            id_list = ", ".join(f":{key}" for key in id_params)
            bind.execute(sa.text(f"DELETE FROM items WHERE id IN ({id_list})"), id_params)
    for column in ('bale_group', 'is_stolen'):
        if _has_column('items', column):
            op.drop_column('items', column)
