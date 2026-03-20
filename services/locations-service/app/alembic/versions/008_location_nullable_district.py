"""Make Location.district_id nullable and add Location.region_id

Revision ID: 008_location_nullable_district
Revises: 007_add_district_map_icon_url
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008_location_nullable_district'
down_revision = '007_add_district_map_icon_url'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = [col['name'] for col in inspector.get_columns('Locations')]

    # Make district_id nullable
    op.execute("ALTER TABLE Locations MODIFY COLUMN district_id BIGINT NULL")

    # Add region_id column if not present
    if 'region_id' not in existing_columns:
        op.execute("ALTER TABLE Locations ADD COLUMN region_id BIGINT NULL")
        op.execute("ALTER TABLE Locations ADD INDEX idx_location_region (region_id)")
        op.execute(
            "ALTER TABLE Locations ADD CONSTRAINT fk_location_region "
            "FOREIGN KEY (region_id) REFERENCES Regions(id) ON DELETE CASCADE"
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop FK and column
    fks = inspector.get_foreign_keys('Locations')
    for fk in fks:
        if 'region_id' in fk.get('constrained_columns', []):
            fk_name = fk.get('name')
            if fk_name:
                op.execute(f"ALTER TABLE Locations DROP FOREIGN KEY {fk_name}")

    existing_columns = [col['name'] for col in inspector.get_columns('Locations')]
    if 'region_id' in existing_columns:
        op.execute("ALTER TABLE Locations DROP COLUMN region_id")

    # Restore district_id NOT NULL
    op.execute("ALTER TABLE Locations MODIFY COLUMN district_id BIGINT NOT NULL")
