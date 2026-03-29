"""Initial schema — battle pass tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # bp_seasons
    if 'bp_seasons' not in existing_tables:
        op.create_table(
            'bp_seasons',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('segment_name', sa.String(50), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('start_date', sa.DateTime(), nullable=False),
            sa.Column('end_date', sa.DateTime(), nullable=False),
            sa.Column('grace_end_date', sa.DateTime(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('segment_name', 'year', name='uq_segment_year'),
        )

    # bp_levels
    if 'bp_levels' not in existing_tables:
        op.create_table(
            'bp_levels',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('level_number', sa.Integer(), nullable=False),
            sa.Column('required_xp', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['season_id'], ['bp_seasons.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('season_id', 'level_number', name='uq_season_level'),
        )

    # bp_rewards
    if 'bp_rewards' not in existing_tables:
        op.create_table(
            'bp_rewards',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('level_id', sa.Integer(), nullable=False),
            sa.Column('track', sa.String(10), nullable=False),
            sa.Column('reward_type', sa.String(20), nullable=False),
            sa.Column('reward_value', sa.Integer(), nullable=False),
            sa.Column('item_id', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['level_id'], ['bp_levels.id'], ondelete='CASCADE'),
        )

    # bp_missions
    if 'bp_missions' not in existing_tables:
        op.create_table(
            'bp_missions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('week_number', sa.Integer(), nullable=False),
            sa.Column('mission_type', sa.String(50), nullable=False),
            sa.Column('description', sa.String(500), nullable=False),
            sa.Column('target_count', sa.Integer(), nullable=False),
            sa.Column('xp_reward', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['season_id'], ['bp_seasons.id'], ondelete='CASCADE'),
        )
        op.create_index('idx_season_week', 'bp_missions', ['season_id', 'week_number'])

    # bp_user_progress
    if 'bp_user_progress' not in existing_tables:
        op.create_table(
            'bp_user_progress',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('current_level', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('current_xp', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('is_premium', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['season_id'], ['bp_seasons.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('user_id', 'season_id', name='uq_user_season'),
        )
        op.create_index('idx_user_id', 'bp_user_progress', ['user_id'])

    # bp_user_rewards
    if 'bp_user_rewards' not in existing_tables:
        op.create_table(
            'bp_user_rewards',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('level_id', sa.Integer(), nullable=False),
            sa.Column('track', sa.String(10), nullable=False),
            sa.Column('claimed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('delivered_to_character_id', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['season_id'], ['bp_seasons.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['level_id'], ['bp_levels.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('user_id', 'level_id', 'track', name='uq_user_level_track'),
        )
        op.create_index('idx_user_season_rewards', 'bp_user_rewards', ['user_id', 'season_id'])

    # bp_user_mission_progress
    if 'bp_user_mission_progress' not in existing_tables:
        op.create_table(
            'bp_user_mission_progress',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('mission_id', sa.Integer(), nullable=False),
            sa.Column('current_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['mission_id'], ['bp_missions.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('user_id', 'mission_id', name='uq_user_mission'),
        )
        op.create_index('idx_user_mission_user_id', 'bp_user_mission_progress', ['user_id'])

    # bp_location_visits
    if 'bp_location_visits' not in existing_tables:
        op.create_table(
            'bp_location_visits',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('location_id', sa.Integer(), nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('visited_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['season_id'], ['bp_seasons.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('user_id', 'season_id', 'location_id', name='uq_user_season_location'),
        )
        op.create_index('idx_user_season_visits', 'bp_location_visits', ['user_id', 'season_id'])

    # bp_user_snapshots
    if 'bp_user_snapshots' not in existing_tables:
        op.create_table(
            'bp_user_snapshots',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('snapshot_type', sa.String(50), nullable=False),
            sa.Column('value_at_enrollment', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['season_id'], ['bp_seasons.id'], ondelete='CASCADE'),
            sa.UniqueConstraint(
                'user_id', 'season_id', 'character_id', 'snapshot_type',
                name='uq_user_season_char_type',
            ),
        )


def downgrade() -> None:
    op.drop_table('bp_user_snapshots')
    op.drop_table('bp_location_visits')
    op.drop_table('bp_user_mission_progress')
    op.drop_table('bp_user_rewards')
    op.drop_table('bp_user_progress')
    op.drop_table('bp_missions')
    op.drop_table('bp_rewards')
    op.drop_table('bp_levels')
    op.drop_table('bp_seasons')
