"""Add npc_status column to characters table.

NPC characters (is_npc=True, npc_role != 'mob') can now be marked as
'alive' or 'dead'. Default is 'alive' for backward compatibility.

Revision ID: 008_add_npc_status
Revises: 007_seed_mob_template_skills
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = '008_add_npc_status'
down_revision = '007_seed_mob_template_skills'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'characters',
        sa.Column(
            'npc_status',
            sa.Enum('alive', 'dead', name='npc_status_enum'),
            nullable=False,
            server_default='alive',
        ),
    )


def downgrade() -> None:
    op.drop_column('characters', 'npc_status')
