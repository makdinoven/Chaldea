"""post_drafts — server-side RP post drafts (FEAT-156).

One live draft per (character, location) plus an archive of the character's ten
most recent texts, drafted or already sent.

Two deliberate choices are encoded here:

* ``content`` is ``MEDIUMTEXT``, not ``TEXT``.  ``TEXT`` holds 64 **KB**;
  Cyrillic in ``utf8mb4`` costs 2 bytes per character and TipTap adds HTML
  markup on top, so a long RP post can realistically reach that ceiling — and a
  silently truncated draft would reproduce the exact data loss this feature
  exists to prevent.

* ``active`` is a nullable ``TINYINT``, not a boolean.  MySQL has no partial
  unique indexes but treats ``NULL``s as distinct inside a unique key, so
  ``UNIQUE (character_id, location_id, active)`` enforces *at most one live
  draft per pair* while leaving the number of archived rows unbounded.  That is
  the race guard for the "typing on two devices" case; the application writes
  literally ``1`` or ``NULL`` and never ``0``.

``location_id`` carries ``ON DELETE CASCADE`` so a deleted location cannot leave
a dangling draft behind.  There is no foreign key on ``character_id``: this
service holds no foreign keys into tables owned by other services, and cleanup
on character deletion is an explicit admin call (see section 3.12 of the
feature file).

``downgrade()`` drops the indexes and the table.  It touches nothing outside the
new table, so it is lossless for pre-existing data — rolling back only discards
drafts written after the deploy.

Revision ID: 036_add_post_drafts
Revises: 035_origin_drop_map_link
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "036_add_post_drafts"
down_revision = "035_origin_drop_map_link"
branch_labels = None
depends_on = None


TABLE = "post_drafts"
UNIQUE_INDEX = "uq_post_drafts_active"
LOOKUP_INDEX = "idx_post_drafts_char_updated"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE in inspector.get_table_names():
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.BigInteger(), nullable=False),
        sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
        # 1 = live draft of (character, location); NULL = archived row
        sa.Column("active", mysql.TINYINT(), nullable=True),
        # NOT NULL => this text became a real post
        sa.Column("sent_at", sa.TIMESTAMP(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["Locations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
    )
    op.create_index(
        UNIQUE_INDEX, TABLE, ["character_id", "location_id", "active"], unique=True
    )
    op.create_index(LOOKUP_INDEX, TABLE, ["character_id", "updated_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        return

    existing = {ix["name"] for ix in inspector.get_indexes(TABLE)}
    if LOOKUP_INDEX in existing:
        op.drop_index(LOOKUP_INDEX, table_name=TABLE)
    if UNIQUE_INDEX in existing:
        op.drop_index(UNIQUE_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
