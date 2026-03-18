"""Initial baseline for character-service tables

Revision ID: 001_initial_baseline
Revises:
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'races' not in existing_tables:
        op.create_table(
            'races',
            sa.Column('id_race', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(50), nullable=False, unique=True),
            sa.Column('description', sa.Text(), nullable=True),
        )

    if 'subraces' not in existing_tables:
        op.create_table(
            'subraces',
            sa.Column('id_subrace', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('id_race', sa.Integer(), sa.ForeignKey('races.id_race'), nullable=False),
            sa.Column('name', sa.String(50), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
        )

    if 'classes' not in existing_tables:
        op.create_table(
            'classes',
            sa.Column('id_class', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(50), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
        )

    if 'titles' not in existing_tables:
        op.create_table(
            'titles',
            sa.Column('id_title', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(50), nullable=False, unique=True),
            sa.Column('description', sa.Text(), nullable=True),
        )

    if 'character_requests' not in existing_tables:
        op.create_table(
            'character_requests',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(20), index=True),
            sa.Column('id_subrace', sa.Integer(), sa.ForeignKey('subraces.id_subrace')),
            sa.Column('biography', sa.Text()),
            sa.Column('personality', sa.Text()),
            sa.Column('id_class', sa.Integer(), sa.ForeignKey('classes.id_class')),
            sa.Column('status', sa.Enum('pending', 'approved', 'rejected'), server_default='pending'),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now()),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('appearance', sa.Text(), nullable=False),
            sa.Column('sex', sa.Enum('male', 'female', 'genderless'), server_default='genderless'),
            sa.Column('background', sa.Text(), nullable=True),
            sa.Column('age', sa.Integer(), nullable=True),
            sa.Column('weight', sa.String(10), nullable=True),
            sa.Column('height', sa.String(10), nullable=True),
            sa.Column('id_race', sa.Integer(), sa.ForeignKey('races.id_race'), nullable=False),
            sa.Column('avatar', sa.String(255), nullable=True),
        )

    if 'characters' not in existing_tables:
        op.create_table(
            'characters',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('id_subrace', sa.Integer(), nullable=False),
            sa.Column('biography', sa.Text(), nullable=True),
            sa.Column('personality', sa.Text(), nullable=True),
            sa.Column('id_class', sa.Integer(), nullable=False),
            sa.Column('id_attributes', sa.Integer(), nullable=True),
            sa.Column('currency_balance', sa.Integer(), server_default='0'),
            sa.Column('request_id', sa.Integer(), sa.ForeignKey('character_requests.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('appearance', sa.Text(), nullable=False),
            sa.Column('sex', sa.Enum('male', 'female', 'genderless'), server_default='genderless'),
            sa.Column('background', sa.Text(), nullable=True),
            sa.Column('age', sa.Integer(), nullable=True),
            sa.Column('weight', sa.String(10), nullable=True),
            sa.Column('height', sa.String(10), nullable=True),
            sa.Column('id_race', sa.Integer(), nullable=False),
            sa.Column('avatar', sa.String(255), nullable=False),
            sa.Column('current_title_id', sa.Integer(), sa.ForeignKey('titles.id_title'), nullable=True),
            sa.Column('level', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('stat_points', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('current_location_id', sa.BigInteger(), nullable=True),
        )

    if 'character_titles' not in existing_tables:
        op.create_table(
            'character_titles',
            sa.Column('character_id', sa.Integer(), sa.ForeignKey('characters.id'), primary_key=True),
            sa.Column('title_id', sa.Integer(), sa.ForeignKey('titles.id_title'), primary_key=True),
            sa.Column('assigned_at', sa.TIMESTAMP(), server_default=sa.func.now()),
        )

    if 'level_thresholds' not in existing_tables:
        op.create_table(
            'level_thresholds',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('level_number', sa.Integer(), unique=True, nullable=False),
            sa.Column('required_experience', sa.Integer(), nullable=False),
        )

    if 'starter_kits' not in existing_tables:
        op.create_table(
            'starter_kits',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('class_id', sa.Integer(), sa.ForeignKey('classes.id_class'), unique=True, nullable=False),
            sa.Column('items', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('skills', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('currency_amount', sa.Integer(), nullable=False, server_default='0'),
        )


def downgrade() -> None:
    op.drop_table('starter_kits')
    op.drop_table('level_thresholds')
    op.drop_table('character_titles')
    op.drop_table('characters')
    op.drop_table('character_requests')
    op.drop_table('titles')
    op.drop_table('classes')
    op.drop_table('subraces')
    op.drop_table('races')
