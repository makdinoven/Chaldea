"""Add is_hidden to Countries

Revision ID: 028_country_is_hidden
Revises: 027_floating_structures
Create Date: 2026-04-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '028_country_is_hidden'
down_revision = '027_floating_structures'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c['name'] for c in insp.get_columns('Countries')}
    if 'is_hidden' in cols:
        return

    op.add_column(
        'Countries',
        sa.Column(
            'is_hidden',
            sa.Boolean(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('Countries', 'is_hidden')
