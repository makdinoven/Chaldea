"""Initial baseline — existing tables in skills-service

Revision ID: 001_initial
Revises:
Create Date: 2026-03-18

This is a baseline migration reflecting the current state of all existing
tables managed by skills-service. It should NOT be run against an existing
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

    # skills
    if 'skills' not in existing_tables:
        op.create_table(
            'skills',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(100), unique=True, nullable=False),
            sa.Column('skill_type', sa.String(50), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('class_limitations', sa.String(100), nullable=True),
            sa.Column('race_limitations', sa.String(100), nullable=True),
            sa.Column('subrace_limitations', sa.String(100), nullable=True),
            sa.Column('min_level', sa.Integer(), default=1),
            sa.Column('purchase_cost', sa.Integer(), default=0),
            sa.Column('skill_image', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_skills_id'), 'skills', ['id'], unique=False)

    # skill_ranks
    if 'skill_ranks' not in existing_tables:
        op.create_table(
            'skill_ranks',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('skill_id', sa.Integer(), nullable=False),
            sa.Column('rank_name', sa.String(100), nullable=True),
            sa.Column('rank_number', sa.Integer(), default=1),
            sa.Column('left_child_id', sa.Integer(), nullable=True),
            sa.Column('right_child_id', sa.Integer(), nullable=True),
            sa.Column('cost_energy', sa.Integer(), default=0),
            sa.Column('cost_mana', sa.Integer(), default=0),
            sa.Column('cooldown', sa.Integer(), default=0),
            sa.Column('level_requirement', sa.Integer(), default=1),
            sa.Column('upgrade_cost', sa.Integer(), default=0),
            sa.Column('class_limitations', sa.String(100), nullable=True),
            sa.Column('race_limitations', sa.String(100), nullable=True),
            sa.Column('subrace_limitations', sa.String(100), nullable=True),
            sa.Column('rank_description', sa.Text(), nullable=True),
            sa.Column('rank_image', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['skill_id'], ['skills.id']),
            sa.ForeignKeyConstraint(['left_child_id'], ['skill_ranks.id']),
            sa.ForeignKeyConstraint(['right_child_id'], ['skill_ranks.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_skill_ranks_id'), 'skill_ranks', ['id'], unique=False)

    # skill_rank_damage
    if 'skill_rank_damage' not in existing_tables:
        op.create_table(
            'skill_rank_damage',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('skill_rank_id', sa.Integer(), nullable=False),
            sa.Column('damage_type', sa.String(50), nullable=False),
            sa.Column('amount', sa.Float(), default=0.0),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('weapon_slot', sa.String(20), default='main_weapon'),
            sa.Column('target_side', sa.String(10), nullable=False, server_default='self'),
            sa.Column('chance', sa.Integer(), default=100),
            sa.ForeignKeyConstraint(['skill_rank_id'], ['skill_ranks.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_skill_rank_damage_id'), 'skill_rank_damage', ['id'], unique=False)

    # skill_rank_effects
    if 'skill_rank_effects' not in existing_tables:
        op.create_table(
            'skill_rank_effects',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('skill_rank_id', sa.Integer(), nullable=False),
            sa.Column('target_side', sa.String(10), default='self'),
            sa.Column('effect_name', sa.String(50), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('chance', sa.Integer(), default=100),
            sa.Column('duration', sa.Integer(), default=1),
            sa.Column('magnitude', sa.Float(), default=0.0),
            sa.Column('attribute_key', sa.String(50), nullable=True),
            sa.ForeignKeyConstraint(['skill_rank_id'], ['skill_ranks.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_skill_rank_effects_id'), 'skill_rank_effects', ['id'], unique=False)

    # character_skills
    if 'character_skills' not in existing_tables:
        op.create_table(
            'character_skills',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('skill_rank_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['skill_rank_id'], ['skill_ranks.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_character_skills_id'), 'character_skills', ['id'], unique=False)
        op.create_index(op.f('ix_character_skills_character_id'), 'character_skills', ['character_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_character_skills_character_id'), table_name='character_skills')
    op.drop_index(op.f('ix_character_skills_id'), table_name='character_skills')
    op.drop_table('character_skills')
    op.drop_index(op.f('ix_skill_rank_effects_id'), table_name='skill_rank_effects')
    op.drop_table('skill_rank_effects')
    op.drop_index(op.f('ix_skill_rank_damage_id'), table_name='skill_rank_damage')
    op.drop_table('skill_rank_damage')
    op.drop_index(op.f('ix_skill_ranks_id'), table_name='skill_ranks')
    op.drop_table('skill_ranks')
    op.drop_index(op.f('ix_skills_id'), table_name='skills')
    op.drop_table('skills')
