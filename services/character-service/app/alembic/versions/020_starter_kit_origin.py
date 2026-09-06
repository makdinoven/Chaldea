"""Starter kits keyed by (class x origin), granted kit frozen (FEAT-154, rules 12a-12d).

Alter:
  characters   + granted_kit JSON NULL
                 The frozen record of what a character was actually issued at
                 approval (rule 12d, D17).  Nullable and deliberately NOT
                 backfilled (D18): NULL means "created before this feature",
                 and the passport falls back to a live resolve for those rows.
  starter_kits + origin_id INT NOT NULL DEFAULT 0
                 0 means "class default" (D16).  A sentinel rather than NULL,
                 because MySQL treats NULLs as distinct inside a UNIQUE index,
                 so a nullable column would accept two competing defaults for
                 the same class and make resolution non-deterministic.
                 origin_countries.id (locations-service) is AUTO_INCREMENT and
                 never yields 0, so the sentinel cannot collide with a real id.

Index changes on starter_kits:
  - the single-column UNIQUE on class_id is dropped.  001_initial_baseline.py
    declared it inline (`unique=True`), so its name was assigned by MySQL and
    must be looked up in information_schema.STATISTICS, never guessed.
  - a UNIQUE on the pair (class_id, origin_id) is created: one default per
    class, one override per (class, origin) pair.

No data is rewritten.  Existing rows acquire origin_id = 0 from the column
default and thereby become their class's default kit.

No FK on origin_id: origin_countries is owned by locations-service.

Revision ID: 020_starter_kit_origin
Revises: 019_char_registration
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa


revision = "020_starter_kit_origin"
down_revision = "019_char_registration"
branch_labels = None
depends_on = None


UNIQUE_PAIR_NAME = "uq_starter_kits_class_origin"


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _single_column_unique_names(bind, inspector, table: str, column: str):
    """Names of every UNIQUE index on `table` that covers exactly `column`.

    001_initial_baseline.py declared the uniqueness inline, so the name is
    whatever MySQL picked.  On MySQL we read it out of information_schema;
    on any other backend (SQLite in the test suite) we fall back to the
    generic inspector.
    """
    if bind.dialect.name == "mysql":
        rows = bind.execute(
            sa.text(
                """
                SELECT INDEX_NAME
                  FROM information_schema.STATISTICS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = :table
                   AND NON_UNIQUE = 0
                   AND INDEX_NAME <> 'PRIMARY'
                 GROUP BY INDEX_NAME
                HAVING COUNT(*) = 1 AND MAX(COLUMN_NAME) = :column
                """
            ),
            {"table": table, "column": column},
        ).fetchall()
        return [row[0] for row in rows]

    names = []
    for index in inspector.get_indexes(table):
        if index.get("unique") and list(index.get("column_names") or []) == [column]:
            if index.get("name"):
                names.append(index["name"])
    for constraint in inspector.get_unique_constraints(table):
        if list(constraint.get("column_names") or []) == [column] and constraint.get("name"):
            names.append(constraint["name"])
    return names


def _has_index(bind, inspector, table: str, name: str) -> bool:
    if bind.dialect.name == "mysql":
        found = bind.execute(
            sa.text(
                """
                SELECT 1
                  FROM information_schema.STATISTICS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = :table
                   AND INDEX_NAME = :name
                 LIMIT 1
                """
            ),
            {"table": table, "name": name},
        ).fetchone()
        return found is not None

    existing = {i.get("name") for i in inspector.get_indexes(table)}
    existing |= {c.get("name") for c in inspector.get_unique_constraints(table)}
    return name in existing


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 0. Frozen record of the kit a character was actually issued (rule 12d, D17).
    #    Nullable, not backfilled (D18).
    if "characters" in tables and not _has_column(inspector, "characters", "granted_kit"):
        op.add_column("characters", sa.Column("granted_kit", sa.JSON(), nullable=True))

    if "starter_kits" not in tables:
        return

    # 1. Every existing row becomes its class's default, with no data rewrite.
    if not _has_column(inspector, "starter_kits", "origin_id"):
        op.add_column(
            "starter_kits",
            sa.Column("origin_id", sa.Integer(), nullable=False, server_default="0"),
        )
        inspector = sa.inspect(bind)

    # 2. One default per class, one override per (class, origin) pair.
    #    Created BEFORE the old index is dropped: the FK class_id -> classes.id_class
    #    needs an index on class_id at all times, and MySQL refuses to drop the last
    #    one ("Cannot drop index 'class_id': needed in a foreign key constraint").
    #    The pair index has class_id as its leftmost column, so it takes over that job.
    if not _has_index(bind, inspector, "starter_kits", UNIQUE_PAIR_NAME):
        op.create_unique_constraint(
            UNIQUE_PAIR_NAME, "starter_kits", ["class_id", "origin_id"]
        )
        inspector = sa.inspect(bind)

    # 3. Drop the MySQL-named single-column UNIQUE on class_id.  No-op if absent.
    for name in _single_column_unique_names(bind, inspector, "starter_kits", "class_id"):
        if name == UNIQUE_PAIR_NAME:
            continue
        op.drop_constraint(name, "starter_kits", type_="unique")


def downgrade() -> None:
    """⚠️ LOSSY — this direction destroys data and cannot be undone.

    It deletes every (class x origin) override from starter_kits (only the
    class defaults survive, because the restored single-column UNIQUE on
    class_id admits one row per class), and it drops characters.granted_kit,
    losing every frozen record of what characters were issued at recruitment.

    The forward direction is fully backward compatible; the reverse is not.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "starter_kits" in tables:
        if _has_column(inspector, "starter_kits", "origin_id"):
            # LOSSY: every origin override is discarded.
            op.execute(sa.text("DELETE FROM starter_kits WHERE origin_id <> 0"))

        # Restore the single-column uniqueness BEFORE dropping the pair index, for
        # the same FK reason as in upgrade(): class_id must stay indexed throughout.
        inspector = sa.inspect(bind)
        if not _single_column_unique_names(bind, inspector, "starter_kits", "class_id"):
            op.create_unique_constraint(
                "uq_starter_kits_class_id", "starter_kits", ["class_id"]
            )

        inspector = sa.inspect(bind)
        if _has_index(bind, inspector, "starter_kits", UNIQUE_PAIR_NAME):
            op.drop_constraint(UNIQUE_PAIR_NAME, "starter_kits", type_="unique")

        inspector = sa.inspect(bind)
        if _has_column(inspector, "starter_kits", "origin_id"):
            op.drop_column("starter_kits", "origin_id")

    # LOSSY: every frozen passport record is lost.
    inspector = sa.inspect(bind)
    if "characters" in tables and _has_column(inspector, "characters", "granted_kit"):
        op.drop_column("characters", "granted_kit")
