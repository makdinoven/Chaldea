"""Add mob system tables: mob_templates, mob_template_skills, mob_loot_table,
location_mob_spawns, active_mobs.

Revision ID: 005_add_mob_tables
Revises: 004_add_claim_fields
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa

revision = '005_add_mob_tables'
down_revision = '004_add_claim_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'mob_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tier', sa.Enum('normal', 'elite', 'boss', name='mob_tier_enum'), nullable=False, server_default='normal'),
        sa.Column('level', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('avatar', sa.String(255), nullable=True),
        sa.Column('id_race', sa.Integer(), nullable=False),
        sa.Column('id_subrace', sa.Integer(), nullable=False),
        sa.Column('id_class', sa.Integer(), nullable=False),
        sa.Column('sex', sa.Enum('male', 'female', 'genderless', name='mob_sex_enum'), server_default='genderless'),
        sa.Column('base_attributes', sa.JSON(), nullable=True),
        sa.Column('xp_reward', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gold_reward', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('respawn_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('respawn_seconds', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_mob_templates_tier', 'mob_templates', ['tier'])
    op.create_index('idx_mob_templates_name', 'mob_templates', ['name'])

    op.create_table(
        'mob_template_skills',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('mob_template_id', sa.Integer(), nullable=False),
        sa.Column('skill_rank_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['mob_template_id'], ['mob_templates.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('mob_template_id', 'skill_rank_id', name='uq_mob_template_skill'),
    )

    op.create_table(
        'mob_loot_table',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('mob_template_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('drop_chance', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('min_quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['mob_template_id'], ['mob_templates.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_loot_template', 'mob_loot_table', ['mob_template_id'])

    op.create_table(
        'location_mob_spawns',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('mob_template_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.BigInteger(), nullable=False),
        sa.Column('spawn_chance', sa.Float(), nullable=False, server_default='5.0'),
        sa.Column('max_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['mob_template_id'], ['mob_templates.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('mob_template_id', 'location_id', name='uq_template_location'),
    )
    op.create_index('idx_spawn_location', 'location_mob_spawns', ['location_id'])

    op.create_table(
        'active_mobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('mob_template_id', sa.Integer(), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.Enum('alive', 'in_battle', 'dead', name='active_mob_status_enum'), nullable=False, server_default='alive'),
        sa.Column('battle_id', sa.Integer(), nullable=True),
        sa.Column('spawn_type', sa.Enum('random', 'manual', name='spawn_type_enum'), nullable=False, server_default='random'),
        sa.Column('spawned_at', sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column('killed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('respawn_at', sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['mob_template_id'], ['mob_templates.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_active_mobs_location', 'active_mobs', ['location_id', 'status'])
    op.create_index('idx_active_mobs_respawn', 'active_mobs', ['respawn_at', 'status'])


def downgrade() -> None:
    op.drop_table('active_mobs')
    op.drop_table('location_mob_spawns')
    op.drop_table('mob_loot_table')
    op.drop_table('mob_template_skills')
    op.drop_table('mob_templates')
