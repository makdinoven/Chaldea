"""Initial baseline — existing tables in battle-service

Revision ID: 001_initial
Revises:
Create Date: 2026-03-22

This is a baseline migration reflecting the current state of all existing
tables managed by battle-service. It should NOT be run against an existing
database — use `alembic stamp head` to mark it as applied.

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # battles
    if 'battles' not in existing_tables:
        op.create_table(
            'battles',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('status', sa.Enum('pending', 'in_progress', 'finished', 'forfeit',
                                        name='battlestatus'), nullable=False,
                       server_default='in_progress'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_battles_id'), 'battles', ['id'], unique=False)

    # battle_participants
    if 'battle_participants' not in existing_tables:
        op.create_table(
            'battle_participants',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('battle_id', sa.Integer(), nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('team', sa.Integer(), nullable=False, server_default='0'),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['battle_id'], ['battles.id']),
        )
        op.create_index(op.f('ix_battle_participants_battle_id'),
                        'battle_participants', ['battle_id'], unique=False)
        op.create_index(op.f('ix_battle_participants_character_id'),
                        'battle_participants', ['character_id'], unique=False)

    # battle_turns
    if 'battle_turns' not in existing_tables:
        op.create_table(
            'battle_turns',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('battle_id', sa.Integer(), nullable=False),
            sa.Column('actor_participant_id', sa.Integer(), nullable=False),
            sa.Column('turn_number', sa.Integer(), nullable=False),
            sa.Column('attack_rank_id', sa.Integer(), nullable=True),
            sa.Column('defense_rank_id', sa.Integer(), nullable=True),
            sa.Column('support_rank_id', sa.Integer(), nullable=True),
            sa.Column('item_id', sa.Integer(), nullable=True),
            sa.Column('submitted_at', sa.DateTime(), nullable=False),
            sa.Column('deadline_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['battle_id'], ['battles.id']),
            sa.ForeignKeyConstraint(['actor_participant_id'], ['battle_participants.id']),
        )
        op.create_index(op.f('ix_battle_turns_battle_id'),
                        'battle_turns', ['battle_id'], unique=False)
        op.create_index(op.f('ix_battle_turns_actor_participant_id'),
                        'battle_turns', ['actor_participant_id'], unique=False)


def downgrade() -> None:
    op.drop_table('battle_turns')
    op.drop_table('battle_participants')
    op.drop_table('battles')
