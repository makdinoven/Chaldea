"""character_titles.character_id -> ON DELETE CASCADE.

Why
---
`character_titles.character_id` is half of that table's composite primary key
and its FK to `characters` was the only one into that table still declared
NO ACTION. Two consequences, both observed live:

* SQLAlchemy's default relationship behaviour on `db.delete(character)` tried
  to blank out the child's FK — a primary-key column — and raised
  `AssertionError`, so any character that owned a title could not be deleted.
* Any deletion that bypasses the ORM (raw SQL, a manual cleanup) would hit a
  foreign-key error instead of removing the link rows.

The ORM side is fixed by `cascade="all, delete-orphan"` on
`Character.titles`; this migration fixes the database side so both paths agree.

Pure constraint-metadata change: no rows are read or rewritten. Reversible —
`downgrade` restores the RESTRICT/NO ACTION rule.

Revision ID: 022_char_titles_cascade
Revises: 021_starting_attributes
"""

from alembic import op
import sqlalchemy as sa


# 22 characters — inside the 32-char limit of alembic_version_character.
revision = "022_char_titles_cascade"
down_revision = "021_starting_attributes"
branch_labels = None
depends_on = None

TABLE = "character_titles"
COLUMN = "character_id"


def _fk_name(inspector) -> str | None:
    """Name of the FK on character_titles.character_id, whatever MySQL called it."""
    for fk in inspector.get_foreign_keys(TABLE):
        if fk.get("referred_table") == "characters" and fk.get("constrained_columns") == [COLUMN]:
            return fk.get("name")
    return None


def _recreate(ondelete: str | None) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    name = _fk_name(inspector)
    if name:
        op.drop_constraint(name, TABLE, type_="foreignkey")
    op.create_foreign_key(
        "fk_character_titles_character",
        TABLE,
        "characters",
        [COLUMN],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    _recreate("CASCADE")


def downgrade() -> None:
    _recreate(None)
