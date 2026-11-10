"""Item admin «Готов» mark (FEAT-210): `items.admin_ready*`.

Admin-only mark (flag + when + who), same shape as the NPC mark of FEAT-209:
- admin_ready     TINYINT(1) NOT NULL DEFAULT 0
- admin_ready_at  DATETIME NULL (UTC naive)
- admin_ready_by  VARCHAR(255) NULL (username snapshot)

Plain columns only, no `item_type` ENUM change (no table lock). Idempotent.

Upgrade: add the columns. Downgrade: drop them (marks are lost).

Revision ID: 036_item_admin_ready
Revises: 035_item_stealth_modifier
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa

revision = '036_item_admin_ready'
down_revision = '035_item_stealth_modifier'
branch_labels = None
depends_on = None


def _has_column(table, column):
    inspector = sa.inspect(op.get_bind())
    return column in {c['name'] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column('items', 'admin_ready'):
        op.add_column(
            'items',
            sa.Column('admin_ready', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        )
    if not _has_column('items', 'admin_ready_at'):
        op.add_column('items', sa.Column('admin_ready_at', sa.DateTime(), nullable=True))
    if not _has_column('items', 'admin_ready_by'):
        op.add_column('items', sa.Column('admin_ready_by', sa.String(255), nullable=True))


def downgrade():
    for column in ('admin_ready_by', 'admin_ready_at', 'admin_ready'):
        if _has_column('items', column):
            op.drop_column('items', column)
