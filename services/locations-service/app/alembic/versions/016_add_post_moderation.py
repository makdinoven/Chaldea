"""Add post_deletion_requests and post_reports tables

Revision ID: 016_add_post_moderation
Revises: 015_add_location_favorites
Create Date: 2026-03-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '016_add_post_moderation'
down_revision = '015_add_location_favorites'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if 'post_deletion_requests' not in insp.get_table_names():
        op.create_table(
            'post_deletion_requests',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('post_id', sa.Integer(),
                      sa.ForeignKey('posts.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('reason', sa.String(500), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('reviewed_by_user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.Column('reviewed_at', sa.TIMESTAMP(), nullable=True),
        )

    if 'post_reports' not in insp.get_table_names():
        op.create_table(
            'post_reports',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('post_id', sa.Integer(),
                      sa.ForeignKey('posts.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('reason', sa.String(500), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('reviewed_by_user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.Column('reviewed_at', sa.TIMESTAMP(), nullable=True),
            sa.UniqueConstraint('post_id', 'user_id', name='uq_post_report_user'),
        )


def downgrade() -> None:
    op.drop_table('post_reports')
    op.drop_table('post_deletion_requests')
