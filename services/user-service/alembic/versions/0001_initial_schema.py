"""Initial schema for user-service tables.

Revision ID: 0001
Revises:
Create Date: 2026-03-18

This migration captures the existing DB schema state for user-service.
All tables already exist in production, so upgrade() is intentionally empty
(stamp this revision to mark it as applied). downgrade() drops all tables
for completeness.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All tables already exist in production DB (created by Base.metadata.create_all).
    # This migration is a baseline snapshot. Uses inspector checks to be idempotent.
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('email', sa.String(255), nullable=False),
            sa.Column('username', sa.String(255), nullable=False),
            sa.Column('hashed_password', sa.String(255), nullable=False),
            sa.Column('registered_at', sa.DateTime(), nullable=True),
            sa.Column('role', sa.String(100), nullable=True),
            sa.Column('avatar', sa.String(255), nullable=True),
            sa.Column('balance', sa.Integer(), nullable=True),
            sa.Column('current_character', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('email'),
            sa.UniqueConstraint('username'),
        )
        op.create_index('ix_users_id', 'users', ['id'], unique=False)
        op.create_index('ix_users_email', 'users', ['email'], unique=True)
        op.create_index('ix_users_username', 'users', ['username'], unique=True)

    if 'users_character' not in existing_tables:
        op.create_table(
            'users_character',
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('user_id', 'character_id'),
        )

    if 'users_avatar_character_preview' not in existing_tables:
        op.create_table(
            'users_avatar_character_preview',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('avatar', sa.String(255), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if 'users_avatar_preview' not in existing_tables:
        op.create_table(
            'users_avatar_preview',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('avatar', sa.String(255), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if 'user_posts' not in existing_tables:
        op.create_table(
            'user_posts',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('author_id', sa.Integer(), nullable=False),
            sa.Column('wall_owner_id', sa.Integer(), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['author_id'], ['users.id']),
            sa.ForeignKeyConstraint(['wall_owner_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_user_posts_id', 'user_posts', ['id'], unique=False)

    if 'friendships' not in existing_tables:
        op.create_table(
            'friendships',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('friend_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(20), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['friend_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_friendships_id', 'friendships', ['id'], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    existing_tables = inspector.get_table_names()

    for table in ['friendships', 'user_posts', 'users_avatar_preview',
                  'users_avatar_character_preview', 'users_character', 'users']:
        if table in existing_tables:
            op.drop_table(table)
