"""Add archive tables for lore wiki (categories, articles, join table)

Revision ID: 020_add_archive_tables
Revises: 019_add_quest_tables
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '020_add_archive_tables'
down_revision = '019_add_quest_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = insp.get_table_names()

    if 'archive_categories' not in existing_tables:
        op.create_table(
            'archive_categories',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('slug', sa.String(255), nullable=False, unique=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_archive_categories_sort_order', 'archive_categories', ['sort_order'])

    if 'archive_articles' not in existing_tables:
        op.create_table(
            'archive_articles',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('slug', sa.String(255), nullable=False, unique=True),
            sa.Column('content', sa.Text().with_variant(sa.Text(length=16_777_215), 'mysql'), nullable=True),
            sa.Column('summary', sa.String(500), nullable=True),
            sa.Column('cover_image_url', sa.String(512), nullable=True),
            sa.Column('is_featured', sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column('featured_sort_order', sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column('created_by_user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_archive_articles_featured', 'archive_articles', ['is_featured', 'featured_sort_order'])
        op.create_index('ix_archive_articles_slug', 'archive_articles', ['slug'])
        op.execute("ALTER TABLE archive_articles ADD FULLTEXT INDEX ft_archive_articles_title (title)")

    if 'archive_article_categories' not in existing_tables:
        op.create_table(
            'archive_article_categories',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('article_id', sa.BigInteger(), sa.ForeignKey('archive_articles.id', ondelete='CASCADE'), nullable=False),
            sa.Column('category_id', sa.BigInteger(), sa.ForeignKey('archive_categories.id', ondelete='CASCADE'), nullable=False),
            sa.UniqueConstraint('article_id', 'category_id', name='uq_article_category'),
        )


def downgrade() -> None:
    op.drop_table('archive_article_categories')
    op.drop_table('archive_articles')
    op.drop_table('archive_categories')
