"""Add battle_participants.joined_at (FEAT-164)

Start of a participant's "busy" interval for passive regen (late joiners get
their own time). Historical rows stay NULL — character-attributes-service
falls back to battles.created_at.

Revision ID: 007_participant_joined_at
Revises: 006_dropout_admin_freeze
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_participant_joined_at'
down_revision = '006_dropout_admin_freeze'
branch_labels = None
depends_on = None


def _participant_columns() -> list:
    inspector = sa.inspect(op.get_bind())
    return [c['name'] for c in inspector.get_columns('battle_participants')]


def upgrade() -> None:
    if 'joined_at' not in _participant_columns():
        op.add_column(
            'battle_participants',
            sa.Column('joined_at', sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    if 'joined_at' in _participant_columns():
        op.drop_column('battle_participants', 'joined_at')
