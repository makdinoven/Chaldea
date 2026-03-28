"""Add cover_text_color column to archive_articles

Revision ID: 025_cover_text_color
Revises: 024_add_is_auto_arrow
Create Date: 2026-03-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '025_cover_text_color'
down_revision = '024_add_is_auto_arrow'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns('archive_articles')]

    if 'cover_text_color' not in columns:
        op.add_column(
            'archive_articles',
            sa.Column('cover_text_color', sa.String(20), nullable=True, server_default="'#FFFFFF'"),
        )


def downgrade() -> None:
    op.drop_column('archive_articles', 'cover_text_color')
