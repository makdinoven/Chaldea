"""Add travel_cooldown_until column to characters

Revision ID: 017_add_travel_cooldown_until
Revises: 016_repoint_mob_template_skills
"""
from alembic import op
import sqlalchemy as sa


revision = "017_add_travel_cooldown_until"
down_revision = "016_repoint_mob_template_skills"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "characters", "travel_cooldown_until"):
        op.add_column(
            "characters",
            sa.Column("travel_cooldown_until", sa.TIMESTAMP(), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "characters", "travel_cooldown_until"):
        op.drop_column("characters", "travel_cooldown_until")
