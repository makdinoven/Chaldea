"""Episodes (FEAT-179): player-run stories outside the main world.

Seven new tables, nothing existing is touched. Downgrade drops them child-first;
their FK-backing indexes go with the tables.

Revision ID: 045_episodes
Revises: 044_game_rule_section
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = '045_episodes'
down_revision = '044_game_rule_section'
branch_labels = None
depends_on = None


def _id():
    return sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True)


def _created():
    return sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False)


def _episode_fk():
    return sa.Column('episode_id', sa.BigInteger(),
                     sa.ForeignKey('episodes.id', ondelete='CASCADE'), nullable=False)


def upgrade() -> None:
    op.create_table(
        'episodes', _id(),
        sa.Column('owner_user_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.Enum('world', 'separate', name='episode_category'), nullable=False),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('image_url', sa.String(512), nullable=True),
        sa.Column('is_private', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='0'),
        _created(),
        sa.Index('ix_episodes_owner', 'owner_user_id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'episode_members', _id(), _episode_fk(),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.Enum('owner', 'master', 'player', name='episode_member_role'),
                  nullable=False, server_default='player'),
        sa.Column('joined_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('episode_id', 'user_id', name='uq_episode_member'),
        sa.Index('ix_episode_members_user', 'user_id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'episode_roles', _id(), _episode_fk(),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default='0'),
        _created(),
        sa.Index('ix_episode_roles_episode', 'episode_id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'episode_locations', _id(), _episode_fk(),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('image_url', sa.String(512), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        _created(),
        sa.Index('ix_episode_locations_episode', 'episode_id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'episode_posts', _id(),
        sa.Column('location_id', sa.BigInteger(),
                  sa.ForeignKey('episode_locations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role_id', sa.BigInteger(),
                  sa.ForeignKey('episode_roles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('content', MEDIUMTEXT(), nullable=False),
        _created(),
        sa.Column('edited_at', sa.TIMESTAMP(), nullable=True),
        sa.Index('ix_episode_posts_location', 'location_id', 'id'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'episode_post_likes', _id(),
        sa.Column('post_id', sa.BigInteger(),
                  sa.ForeignKey('episode_posts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_episode_post_like'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'episode_join_requests', _id(), _episode_fk(),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.String(500), nullable=True),
        _created(),
        sa.UniqueConstraint('episode_id', 'user_id', name='uq_episode_join_request'),
        mysql_engine='InnoDB',
    )


def downgrade() -> None:
    for table in ('episode_join_requests', 'episode_post_likes', 'episode_posts',
                  'episode_locations', 'episode_roles', 'episode_members', 'episodes'):
        op.drop_table(table)
