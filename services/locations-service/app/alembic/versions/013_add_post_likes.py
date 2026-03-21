"""Add post_likes table

Revision ID: 013_add_post_likes
Revises: 012_district_map_image
Create Date: 2026-03-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '013_add_post_likes'
down_revision = '012_district_map_image'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if 'post_likes' not in insp.get_table_names():
        op.create_table(
            'post_likes',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('post_id', sa.Integer(), sa.ForeignKey('posts.id', ondelete='CASCADE'), nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('post_id', 'character_id', name='uq_post_character'),
        )
        op.create_index('ix_post_likes_id', 'post_likes', ['id'])


def downgrade() -> None:
    op.drop_index('ix_post_likes_id', table_name='post_likes')
    op.drop_table('post_likes')
