"""Add is_npc, npc_role columns to characters; make request_id nullable.

Revision ID: 003_add_npc_fields
Revises: 002_add_race_subrace_columns
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa

revision = '003_add_npc_fields'
down_revision = '002_add_race_subrace_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c['name'] for c in inspector.get_columns('characters')]

    if 'is_npc' not in existing_columns:
        op.add_column('characters', sa.Column('is_npc', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        op.create_index('ix_characters_is_npc', 'characters', ['is_npc'])

    if 'npc_role' not in existing_columns:
        op.add_column('characters', sa.Column('npc_role', sa.String(50), nullable=True))

    # Make request_id nullable (NPCs don't have character requests)
    op.alter_column('characters', 'request_id',
                    existing_type=sa.Integer(),
                    nullable=True)


def downgrade() -> None:
    op.drop_index('ix_characters_is_npc', table_name='characters')
    op.drop_column('characters', 'is_npc')
    op.drop_column('characters', 'npc_role')
    op.alter_column('characters', 'request_id',
                    existing_type=sa.Integer(),
                    nullable=False)
