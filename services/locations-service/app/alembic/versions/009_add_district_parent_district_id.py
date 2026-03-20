"""Add parent_district_id to Districts for nested zones

Revision ID: 009_district_parent_id
Revises: 008_location_nullable_district
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '009_district_parent_id'
down_revision = '008_location_nullable_district'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns('Districts')]
    if 'parent_district_id' not in columns:
        op.add_column('Districts', sa.Column('parent_district_id', sa.BigInteger(), nullable=True))
    fks = [fk['name'] for fk in insp.get_foreign_keys('Districts')]
    if 'fk_districts_parent_district_id' not in fks:
        op.create_foreign_key(
            'fk_districts_parent_district_id',
            'Districts',
            'Districts',
            ['parent_district_id'],
            ['id'],
            ondelete='CASCADE',
        )


def downgrade() -> None:
    op.drop_constraint('fk_districts_parent_district_id', 'Districts', type_='foreignkey')
    op.drop_column('Districts', 'parent_district_id')
