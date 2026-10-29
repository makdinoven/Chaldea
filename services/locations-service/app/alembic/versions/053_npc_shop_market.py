"""NPC merchants (FEAT-183): npc_shop_items becomes a merchant's stock.

* Dedupe (npc_id, item_id): per pair the kept row is the ACTIVE one with the lowest id
  (if none is active, the lowest id). The player buy flow addresses rows by id and the
  sell flow only ever looked at active rows, so an active row is the one players used.
  Pre-beta: the dropped duplicates are not restored on downgrade; the count is logged.
* Sanitize old unvalidated admin input: buy_price < 1 -> 1, sell_price < 0 -> 0, stock < 0 -> 0.
* New columns: restock_target («норма склада», filled with COALESCE(stock, 10)),
  origin (admin | player), updated_at.
* UNIQUE (npc_id, item_id).

Downgrade drops the unique key and the three columns.

Revision ID: 053_npc_shop_market
Revises: 052_house_rooms_6b
Create Date: 2026-10-29

"""
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '053_npc_shop_market'
down_revision = '052_house_rooms_6b'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = 'npc_shop_items'
UNIQUE_NAME = 'uq_npc_shop_items_npc_item'
DEFAULT_RESTOCK_TARGET = 10   # econ_core.DEFAULT_RESTOCK_TARGET (migrations do not import app code)

# A row is dropped when the same (npc, item) has a "better" row: active beats inactive, then lower id.
DEDUPE_SQL = f"""
DELETE s FROM {TABLE} s
JOIN {TABLE} k
  ON k.npc_id = s.npc_id AND k.item_id = s.item_id AND k.id <> s.id
 AND (k.is_active > s.is_active OR (k.is_active = s.is_active AND k.id < s.id))
"""


def _columns(bind) -> set:
    return {c['name'] for c in inspect(bind).get_columns(TABLE)}


def _unique_names(bind) -> set:
    insp = inspect(bind)
    names = {u['name'] for u in insp.get_unique_constraints(TABLE)}
    names |= {i['name'] for i in insp.get_indexes(TABLE) if i.get('unique')}
    return names


def upgrade() -> None:
    bind = op.get_bind()

    # 1. One row per (npc, item).
    deleted = bind.execute(sa.text(DEDUPE_SQL)).rowcount
    if deleted:
        logger.warning("053_npc_shop_market: removed %s duplicate npc_shop_items rows", deleted)

    # 2. Old unvalidated input.
    bind.execute(sa.text(f"UPDATE {TABLE} SET buy_price = 1 WHERE buy_price < 1"))
    bind.execute(sa.text(f"UPDATE {TABLE} SET sell_price = 0 WHERE sell_price < 0"))
    bind.execute(sa.text(f"UPDATE {TABLE} SET stock = 0 WHERE stock < 0"))

    # 3. New columns.
    columns = _columns(bind)
    if 'restock_target' not in columns:
        op.add_column(TABLE, sa.Column('restock_target', sa.Integer(), nullable=False, server_default=sa.text("0")))
        bind.execute(sa.text(f"UPDATE {TABLE} SET restock_target = COALESCE(stock, {DEFAULT_RESTOCK_TARGET})"))
    if 'origin' not in columns:
        op.add_column(TABLE, sa.Column('origin', sa.String(16), nullable=False, server_default='admin'))
    if 'updated_at' not in columns:
        op.execute(f"ALTER TABLE {TABLE} ADD COLUMN updated_at TIMESTAMP NULL "
                   "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")

    # 4. Unique key.
    if UNIQUE_NAME not in _unique_names(bind):
        op.create_unique_constraint(UNIQUE_NAME, TABLE, ['npc_id', 'item_id'])


def downgrade() -> None:
    bind = op.get_bind()
    # No foreign key uses this index, so dropping it is safe on MySQL.
    if UNIQUE_NAME in _unique_names(bind):
        op.drop_constraint(UNIQUE_NAME, TABLE, type_='unique')
    columns = _columns(bind)
    for name in ('updated_at', 'origin', 'restock_target'):
        if name in columns:
            op.drop_column(TABLE, name)
