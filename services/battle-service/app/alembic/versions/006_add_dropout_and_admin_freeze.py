"""Add battle_participants.dropped_out_at, battles.pause_reason / paused_by_admin

FEAT-163: turn-timeout dropouts and the admin battle freeze. One revision for
the whole feature so it takes a single deploy window.

Revision ID: 006_dropout_admin_freeze
Revises: 005_battle_parties
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_dropout_admin_freeze'
down_revision = '005_battle_parties'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    battles_columns = [c['name'] for c in inspector.get_columns('battles')]
    if 'pause_reason' not in battles_columns:
        op.add_column(
            'battles',
            sa.Column('pause_reason', sa.String(length=255), nullable=True),
        )
    if 'paused_by_admin' not in battles_columns:
        op.add_column(
            'battles',
            sa.Column(
                'paused_by_admin',
                sa.Boolean(),
                nullable=False,
                server_default='0',
            ),
        )

    participant_columns = [
        c['name'] for c in inspector.get_columns('battle_participants')
    ]
    if 'dropped_out_at' not in participant_columns:
        op.add_column(
            'battle_participants',
            sa.Column('dropped_out_at', sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    participant_columns = [
        c['name'] for c in inspector.get_columns('battle_participants')
    ]
    if 'dropped_out_at' in participant_columns:
        op.drop_column('battle_participants', 'dropped_out_at')

    battles_columns = [c['name'] for c in inspector.get_columns('battles')]
    if 'paused_by_admin' in battles_columns:
        op.drop_column('battles', 'paused_by_admin')
    if 'pause_reason' in battles_columns:
        op.drop_column('battles', 'pause_reason')
