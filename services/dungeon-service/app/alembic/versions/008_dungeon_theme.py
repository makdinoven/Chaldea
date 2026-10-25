"""Dungeon look presets for the 3D miniature

* `dungeons.theme` (VARCHAR(32) NOT NULL DEFAULT 'stone') — walls, floor and light.
* `dungeons.floor_themes` (JSON NULL) — {"2": "volcano"}: a floor's own look.

Revision ID: 008
Revises: 007
Create Date: 2026-10-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("dungeons")]
    if "theme" not in cols:
        op.add_column("dungeons", sa.Column("theme", sa.String(32), nullable=False, server_default="stone"))
    if "floor_themes" not in cols:
        op.add_column("dungeons", sa.Column("floor_themes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("dungeons", "floor_themes")
    op.drop_column("dungeons", "theme")
