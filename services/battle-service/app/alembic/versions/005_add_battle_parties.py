"""Add battle_parties and battle_party_members (pre-battle party lobby)

Revision ID: 005_battle_parties
Revises: 004_location_paused_join
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_battle_parties'
down_revision = '004_location_paused_join'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'battle_parties' not in existing_tables:
        op.create_table(
            'battle_parties',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('leader_character_id', sa.Integer(), nullable=False),
            sa.Column('location_id', sa.Integer(), nullable=False),
            sa.Column(
                'battle_type',
                sa.Enum('pve', 'pvp_training', 'pvp_death', 'pvp_attack',
                        name='battletype'),
                nullable=False,
                server_default='pvp_training',
            ),
            sa.Column(
                'status',
                sa.Enum('forming', 'started', 'cancelled', 'expired',
                        name='battlepartystatus'),
                nullable=False,
                server_default='forming',
            ),
            sa.Column('battle_id', sa.Integer(), nullable=True),
            sa.Column(
                'created_at', sa.DateTime(), nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('idx_party_leader', 'battle_parties', ['leader_character_id'])
        op.create_index('idx_party_location', 'battle_parties', ['location_id'])

    if 'battle_party_members' not in existing_tables:
        op.create_table(
            'battle_party_members',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('party_id', sa.Integer(), nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('team', sa.Integer(), nullable=False, server_default='0'),
            sa.Column(
                'status',
                sa.Enum('invited', 'accepted', 'declined',
                        name='partymemberstatus'),
                nullable=False,
                server_default='invited',
            ),
            sa.Column('is_leader', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column(
                'created_at', sa.DateTime(), nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.Column('responded_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(
                ['party_id'], ['battle_parties.id'], name='fk_party_member_party',
                ondelete='CASCADE',
            ),
            sa.UniqueConstraint('party_id', 'character_id', name='uq_party_member'),
        )
        op.create_index('idx_party_member_party', 'battle_party_members', ['party_id'])
        op.create_index('idx_party_member_character', 'battle_party_members', ['character_id'])
        op.create_index('idx_party_member_user', 'battle_party_members', ['user_id'])


def downgrade() -> None:
    op.drop_table('battle_party_members')
    op.drop_table('battle_parties')
    sa.Enum(name='partymemberstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='battlepartystatus').drop(op.get_bind(), checkfirst=True)
