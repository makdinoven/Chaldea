"""Add stroke_color to ClickableZones, emblem_url to Countries, expand target_type ENUM

Revision ID: 005_clickable_zone_enhancements
Revises: 004_game_time_config
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_clickable_zone_enhancements'
down_revision = '004_game_time_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add stroke_color to ClickableZones
    existing_columns = [col['name'] for col in inspector.get_columns('ClickableZones')]
    if 'stroke_color' not in existing_columns:
        op.execute("ALTER TABLE ClickableZones ADD COLUMN stroke_color VARCHAR(20) NULL")

    # 2. Add emblem_url to Countries
    country_columns = [col['name'] for col in inspector.get_columns('Countries')]
    if 'emblem_url' not in country_columns:
        op.execute("ALTER TABLE Countries ADD COLUMN emblem_url VARCHAR(255) NULL")

    # 3. Expand target_type ENUM to include 'area'
    op.execute(
        "ALTER TABLE ClickableZones MODIFY COLUMN target_type ENUM('country', 'region', 'area') NOT NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ClickableZones DROP COLUMN stroke_color")
    op.execute("ALTER TABLE Countries DROP COLUMN emblem_url")
    op.execute(
        "ALTER TABLE ClickableZones MODIFY COLUMN target_type ENUM('country', 'region') NOT NULL"
    )
