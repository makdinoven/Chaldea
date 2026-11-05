"""FEAT-201: the stealth stat drives witnesses, flee, escape and reveal.

* `shadow_settings` (singleton id=1):
  - new: `stealth_pct_per_point` (% of the chance removed per effective stealth point), `stealth_max_reduction_pct`
    (ceiling of that reduction) and the out-of-battle subclass stealth points `stealth_assassin_points` /
    `stealth_trickster_points` / `stealth_agent_points` (added to the raw stat BEFORE the FEAT-195 cap);
  - dropped: the FEAT-199 additive knobs `witness_stealth_per_point_pct`, `witness_agent_pct`,
    `witness_assassin_pct`, `witness_trickster_pct`, `witness_mask_pct` (the mask is anonymity only now);
  - location bases become 100 / 70 / 40 / 25 and `witness_max_pct` 100 (defaults AND the existing row).
* `law_crimes.stealth_reduction_pct` — the attacker's stealth reduction at crime time (reveal snapshot; NULL = 0).
* `law_settings.escape_per_point_pct` — escape now uses ONE stat (stealth) instead of two, so the shipped default
  0.150 is doubled to 0.300 (an admin-tuned value is left alone).

Every step is guarded (information_schema), so a re-run is a no-op. Downgrade restores the FEAT-199 columns with
their FEAT-199 defaults (custom values are lost — acceptable pre-beta), the old bases 70/45/25/15 and max 95.

Revision ID: 041_stealth
Revises: 040_shadow_renown
"""

import sqlalchemy as sa
from alembic import op


revision = "041_stealth"
down_revision = "040_shadow_renown"
branch_labels = None
depends_on = None


_NEW_SHADOW_COLUMNS = [
    ("stealth_pct_per_point", "DECIMAL(6,3) NOT NULL DEFAULT 0.500"),
    ("stealth_max_reduction_pct", "DECIMAL(5,2) NOT NULL DEFAULT 90.00"),
    ("stealth_assassin_points", "INT NOT NULL DEFAULT 30"),
    ("stealth_trickster_points", "INT NOT NULL DEFAULT 30"),
    ("stealth_agent_points", "INT NOT NULL DEFAULT 20"),
]

# the FEAT-199 definitions (040_shadow_renown), used by the downgrade
_OLD_SHADOW_COLUMNS = [
    ("witness_stealth_per_point_pct", "DECIMAL(6,3) NOT NULL DEFAULT 0.100"),
    ("witness_agent_pct", "DECIMAL(5,2) NOT NULL DEFAULT 10.00"),
    ("witness_assassin_pct", "DECIMAL(5,2) NOT NULL DEFAULT 15.00"),
    ("witness_trickster_pct", "DECIMAL(5,2) NOT NULL DEFAULT 15.00"),
    ("witness_mask_pct", "DECIMAL(5,2) NOT NULL DEFAULT 10.00"),
]

# column -> (FEAT-201 value, FEAT-199 value)
_BASES = [
    ("witness_base_safe_pct", "100.00", "70.00"),
    ("witness_base_farm_pct", "70.00", "45.00"),
    ("witness_base_dangerous_pct", "40.00", "25.00"),
    ("witness_base_dungeon_pct", "25.00", "15.00"),
    ("witness_max_pct", "100.00", "95.00"),
]

_ESCAPE_OLD = "0.150"
_ESCAPE_NEW = "0.300"


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def _has_table(conn, table: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"
    ), {"t": table}).scalar())


def _column_default(conn, table: str, column: str) -> str:
    value = conn.execute(sa.text(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar()
    return str(value) if value is not None else ""


def _set_bases(conn, index: int) -> None:
    """index 1 = FEAT-201 values, 2 = FEAT-199 values (column defaults + the singleton row)."""
    for spec in _BASES:
        column, value = spec[0], spec[index]
        op.execute(f"ALTER TABLE shadow_settings MODIFY {column} DECIMAL(5,2) NOT NULL DEFAULT {value}")
    assignments = ", ".join(f"{spec[0]} = {spec[index]}" for spec in _BASES)
    op.execute(f"UPDATE shadow_settings SET {assignments} WHERE id = 1")


def _set_escape(old: str, new: str) -> None:
    op.execute(f"ALTER TABLE law_settings MODIFY escape_per_point_pct DECIMAL(6,3) NOT NULL DEFAULT {new}")
    op.execute(f"UPDATE law_settings SET escape_per_point_pct = {new} WHERE id = 1 AND escape_per_point_pct = {old}")


def upgrade():
    conn = op.get_bind()
    if _has_table(conn, "shadow_settings"):
        for column, ddl in _NEW_SHADOW_COLUMNS:
            if not _has_column(conn, "shadow_settings", column):
                op.execute(f"ALTER TABLE shadow_settings ADD COLUMN {column} {ddl}")
        for column, _ddl in _OLD_SHADOW_COLUMNS:
            if _has_column(conn, "shadow_settings", column):
                op.execute(f"ALTER TABLE shadow_settings DROP COLUMN {column}")
        # idempotent: the bases move once (the column default is the marker), a re-run never overwrites admin edits
        if _column_default(conn, "shadow_settings", "witness_base_safe_pct") != "100.00":
            _set_bases(conn, 1)
    if _has_table(conn, "law_crimes") and not _has_column(conn, "law_crimes", "stealth_reduction_pct"):
        op.execute("ALTER TABLE law_crimes ADD COLUMN stealth_reduction_pct DECIMAL(5,2) NULL")
    if _has_table(conn, "law_settings"):
        if _column_default(conn, "law_settings", "escape_per_point_pct") != _ESCAPE_NEW:
            _set_escape(_ESCAPE_OLD, _ESCAPE_NEW)


def downgrade():
    conn = op.get_bind()
    if _has_table(conn, "law_settings"):
        _set_escape(_ESCAPE_NEW, _ESCAPE_OLD)
    if _has_column(conn, "law_crimes", "stealth_reduction_pct"):
        op.execute("ALTER TABLE law_crimes DROP COLUMN stealth_reduction_pct")
    if _has_table(conn, "shadow_settings"):
        _set_bases(conn, 2)
        for column, ddl in _OLD_SHADOW_COLUMNS:
            if not _has_column(conn, "shadow_settings", column):
                op.execute(f"ALTER TABLE shadow_settings ADD COLUMN {column} {ddl}")
        for column, _ddl in reversed(_NEW_SHADOW_COLUMNS):
            if _has_column(conn, "shadow_settings", column):
                op.execute(f"ALTER TABLE shadow_settings DROP COLUMN {column}")
