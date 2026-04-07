"""Add floating_structures table

Revision ID: 027_floating_structures
Revises: 026_arrow_rotation
Create Date: 2026-04-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '027_floating_structures'
down_revision = '026_arrow_rotation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if 'floating_structures' in insp.get_table_names():
        return

    op.create_table(
        'floating_structures',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon_url', sa.String(length=500), nullable=True),
        sa.Column('route_json', sa.JSON(), nullable=False),
        sa.Column('speed', sa.Float(), nullable=False, server_default='0'),
        sa.Column(
            'started_at',
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.Column('internal_district_id', sa.BigInteger(), nullable=True),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.Column(
            'updated_at',
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
        ),
        sa.ForeignKeyConstraint(
            ['internal_district_id'],
            ['Districts.id'],
            name='fk_floating_internal_district',
            ondelete='SET NULL',
        ),
    )


def downgrade() -> None:
    op.drop_table('floating_structures')
