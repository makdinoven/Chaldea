"""Add area_id to floating_structures

Revision ID: 029_floating_structure_area_id
Revises: 028_country_is_hidden
Create Date: 2026-04-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '029_floating_structure_area_id'
down_revision = '028_country_is_hidden'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c['name'] for c in insp.get_columns('floating_structures')}
    if 'area_id' in cols:
        return

    op.add_column(
        'floating_structures',
        sa.Column('area_id', sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        'fk_floating_structures_area_id',
        'floating_structures',
        'Areas',
        ['area_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_floating_structures_area_id', 'floating_structures', type_='foreignkey')
    op.drop_column('floating_structures', 'area_id')
