"""Add index on posts.character_id for efficient batch queries

Revision ID: 022_add_index_posts_character_id
Revises: 021_add_path_data_to_neighbors
Create Date: 2026-03-27

"""
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '022_add_index_posts_character_id'
down_revision = '021_add_path_data_to_neighbors'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    indexes = insp.get_indexes('posts')
    existing_index_names = {idx['name'] for idx in indexes}

    if 'idx_posts_character_id' not in existing_index_names:
        op.create_index('idx_posts_character_id', 'posts', ['character_id'])


def downgrade() -> None:
    op.drop_index('idx_posts_character_id', table_name='posts')
