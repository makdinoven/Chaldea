"""FEAT-155 — freeze the starting characteristics on the character row.

  characters + starting_attributes JSON NULL

Why
---
The passport block «Оценка при вступлении» used to be filled by a live call to
character-attributes-service, so it printed the character's *current* build:
the caption lied ("125 из 100 очков подрасы"), and any visitor of
`/characters/list` could read a stranger's actual point distribution.

The passport is a record of what a Скиталец arrived with, exactly like the
issued kit (`characters.granted_kit`, rule 12d / D17). So the starting
attributes are frozen the same way: approval resolves the subrace preset once
and writes that one result both to character-attributes-service and to this
column.

Nullable and **not backfilled**, mirroring D18 and `granted_kit`: a NULL means
"created before this feature", and the passport then reconstructs the value
from the subrace's `stat_preset` and says so. Backfilling from today's live
attributes is precisely the bug this migration exists to remove.

Additive and reversible: `upgrade` only adds a nullable column (risk R3 — the
tests construct `models.Character` directly, so a NOT NULL without a
server_default would break them), `downgrade` drops it. The downgrade is lossy
only in that the frozen records are lost; nothing else depends on the column.

Revision ID: 021_starting_attributes
Revises: 020_starter_kit_origin
"""

from alembic import op
import sqlalchemy as sa


# 23 characters — well inside the 32-char limit of alembic_version_character.
revision = "021_starting_attributes"
down_revision = "020_starter_kit_origin"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "characters" not in inspector.get_table_names():
        return
    if not _has_column(inspector, "characters", "starting_attributes"):
        op.add_column(
            "characters",
            sa.Column("starting_attributes", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    """Drops the column. Every frozen starting-attributes record is lost."""
    inspector = sa.inspect(op.get_bind())
    if "characters" not in inspector.get_table_names():
        return
    if _has_column(inspector, "characters", "starting_attributes"):
        op.drop_column("characters", "starting_attributes")
