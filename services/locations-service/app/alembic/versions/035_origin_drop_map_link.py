"""Drop origin_countries.country_id and .is_playable (FEAT-155, rules 10-12).

Both columns expressed almost the same idea — "this origin is a country on the
game map" — and could contradict each other (a checked ``is_playable`` with no
``country_id``, or the reverse).  The user removed the notion "on the map /
off the map" from the player-facing wizard entirely; the tie between an origin
and the world is now expressed only through ``origin_starting_points``, which
an administrator curates by hand.

Safe to drop: the origins registry is empty in production (``GET
/locations/origins`` returns ``[]``), so no data is lost.

``country_id`` carries a foreign key to ``Countries``.  033 declared it with an
explicit name, but a hand-made or re-created table could carry whatever MySQL
assigned, so the name is looked up in ``information_schema`` rather than
guessed — the same lesson as FEAT-154's migration 020 (note N9).

``downgrade()`` restores both columns, the FK and the default values.  It is
lossy only in the sense that the old values cannot be recovered — every row
comes back with ``country_id = NULL`` and ``is_playable = 0``.

Revision ID: 035_origin_drop_map_link
Revises: 034_origin_start_pts
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa


revision = "035_origin_drop_map_link"
down_revision = "034_origin_start_pts"
branch_labels = None
depends_on = None


TABLE = "origin_countries"
FK_NAME = "fk_origin_countries_country"


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _fk_names_on_column(bind, inspector, table: str, column: str):
    """Names of every FK on `table` whose only column is `column`.

    On MySQL the authoritative source is information_schema — the constraint
    name may have been assigned by the server (``origin_countries_ibfk_1``)
    rather than by the migration that created it.  On other backends (SQLite
    in the test suite) the generic inspector is good enough.
    """
    if bind.dialect.name == "mysql":
        rows = bind.execute(
            sa.text(
                """
                SELECT CONSTRAINT_NAME
                  FROM information_schema.KEY_COLUMN_USAGE
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = :table
                   AND REFERENCED_TABLE_NAME IS NOT NULL
                 GROUP BY CONSTRAINT_NAME
                HAVING COUNT(*) = 1 AND MAX(COLUMN_NAME) = :column
                """
            ),
            {"table": table, "column": column},
        ).fetchall()
        return [row[0] for row in rows]

    return [
        fk["name"]
        for fk in inspector.get_foreign_keys(table)
        if fk.get("name") and list(fk.get("constrained_columns") or []) == [column]
    ]


def _index_names_on_column(bind, table: str, column: str):
    """Names of every non-PRIMARY index on `table` covering exactly `column`."""
    rows = bind.execute(
        sa.text(
            """
            SELECT INDEX_NAME
              FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE()
               AND TABLE_NAME = :table
               AND INDEX_NAME <> 'PRIMARY'
             GROUP BY INDEX_NAME
            HAVING COUNT(*) = 1 AND MAX(COLUMN_NAME) = :column
            """
        ),
        {"table": table, "column": column},
    ).fetchall()
    return [row[0] for row in rows]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        return

    if _has_column(inspector, TABLE, "country_id"):
        # The FK must go first: MySQL refuses to drop a column an FK depends on.
        for name in _fk_names_on_column(bind, inspector, TABLE, "country_id"):
            op.drop_constraint(name, TABLE, type_="foreignkey")

        # MySQL creates a helper index for the FK; it usually disappears with
        # the column, but drop it explicitly when it survived the FK removal.
        if bind.dialect.name == "mysql":
            for name in _index_names_on_column(bind, TABLE, "country_id"):
                op.drop_index(name, table_name=TABLE)

        op.drop_column(TABLE, "country_id")

    inspector = sa.inspect(bind)
    if _has_column(inspector, TABLE, "is_playable"):
        op.drop_column(TABLE, "is_playable")


def downgrade() -> None:
    """Restores the columns and the FK; the old values are NOT recoverable."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        return

    if not _has_column(inspector, TABLE, "country_id"):
        op.add_column(TABLE, sa.Column("country_id", sa.BigInteger(), nullable=True))
        inspector = sa.inspect(bind)
        if not _fk_names_on_column(bind, inspector, TABLE, "country_id"):
            op.create_foreign_key(
                FK_NAME, TABLE, "Countries", ["country_id"], ["id"],
                ondelete="SET NULL",
            )

    inspector = sa.inspect(bind)
    if not _has_column(inspector, TABLE, "is_playable"):
        op.add_column(
            TABLE,
            sa.Column(
                "is_playable", sa.Boolean(), nullable=False, server_default="0"
            ),
        )
