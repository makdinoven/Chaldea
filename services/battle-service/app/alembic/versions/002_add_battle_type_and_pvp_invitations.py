"""Add battle_type column to battles and create pvp_invitations table

Revision ID: 002_add_pvp
Revises: 001_initial
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_add_pvp'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # --- A. Add battle_type column to battles ---
    if 'battles' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('battles')]
        if 'battle_type' not in columns:
            op.add_column(
                'battles',
                sa.Column(
                    'battle_type',
                    sa.Enum('pve', 'pvp_training', 'pvp_death', 'pvp_attack',
                            name='battletype'),
                    nullable=False,
                    server_default='pve',
                ),
            )

    # --- B. Create pvp_invitations table ---
    if 'pvp_invitations' not in existing_tables:
        op.create_table(
            'pvp_invitations',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('initiator_character_id', sa.Integer(), nullable=False),
            sa.Column('target_character_id', sa.Integer(), nullable=False),
            sa.Column('location_id', sa.Integer(), nullable=False),
            sa.Column(
                'battle_type',
                sa.Enum('pvp_training', 'pvp_death',
                        name='pvp_invitation_battle_type'),
                nullable=False,
            ),
            sa.Column(
                'status',
                sa.Enum('pending', 'accepted', 'declined', 'expired', 'cancelled',
                        name='pvpinvitationstatus'),
                nullable=False,
                server_default='pending',
            ),
            sa.Column('created_at', sa.DateTime(), nullable=False,
                       server_default=sa.func.now()),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            'idx_target_status', 'pvp_invitations',
            ['target_character_id', 'status'], unique=False,
        )
        op.create_index(
            'idx_initiator_status', 'pvp_invitations',
            ['initiator_character_id', 'status'], unique=False,
        )


def downgrade() -> None:
    op.drop_table('pvp_invitations')
    op.drop_column('battles', 'battle_type')
