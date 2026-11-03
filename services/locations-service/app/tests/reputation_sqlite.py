"""FEAT-197: SQLite stand-ins of the character-service reputation tables locations-service reads.

Empty settings / tiers tables make reputation_core fall back to its defaults, and no character_reputation row
means value 0 (Скиталец, no price effect) — so a fixture that only creates these tables keeps its old
behaviour. ``characters.reputation_min_tier`` is the NPC gate column (added with ALTER when missing).
"""

from sqlalchemy import text

REPUTATION_SQLITE_DDL = (
    "CREATE TABLE IF NOT EXISTS character_reputation (id INTEGER PRIMARY KEY, character_id INTEGER NOT NULL, "
    "region_id INTEGER NOT NULL, value INTEGER NOT NULL DEFAULT 0, decay_at DATETIME NULL, "
    "updated_at DATETIME NULL, UNIQUE (character_id, region_id))",
    "CREATE TABLE IF NOT EXISTS reputation_settings (id INTEGER PRIMARY KEY, min_value INTEGER NOT NULL, "
    "max_value INTEGER NOT NULL, echo_pct NUMERIC NOT NULL, decay_per_day NUMERIC NOT NULL, "
    "decay_last_run_at DATETIME NULL, updated_at DATETIME NULL)",
    "CREATE TABLE IF NOT EXISTS reputation_tiers (code VARCHAR(20) PRIMARY KEY, sort_order INTEGER NOT NULL, "
    "name VARCHAR(60) NOT NULL, min_value INTEGER NULL, price_pct NUMERIC NOT NULL DEFAULT 0, "
    "sell_pct NUMERIC NOT NULL DEFAULT 0, trade_refused INTEGER NOT NULL DEFAULT 0)",
)
NPC_GATE_COLUMN_DDL = "ALTER TABLE characters ADD COLUMN reputation_min_tier VARCHAR(20) NULL"


def _has_gate_column(rows) -> bool:
    return any(r[1] == "reputation_min_tier" for r in rows)


def create_sync(conn) -> None:
    """For a sync connection / session whose schema already has a `characters` table (or not)."""
    for ddl in REPUTATION_SQLITE_DDL:
        conn.execute(text(ddl))
    rows = conn.execute(text("PRAGMA table_info(characters)")).fetchall()
    if rows and not _has_gate_column(rows):
        conn.execute(text(NPC_GATE_COLUMN_DDL))


async def create_async(conn) -> None:
    """Async twin of :func:`create_sync` (AsyncConnection or AsyncSession)."""
    for ddl in REPUTATION_SQLITE_DDL:
        await conn.execute(text(ddl))
    rows = (await conn.execute(text("PRAGMA table_info(characters)"))).fetchall()
    if rows and not _has_gate_column(rows):
        await conn.execute(text(NPC_GATE_COLUMN_DDL))
