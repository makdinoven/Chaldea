"""
FEAT-164 test harness: shared-DB tables read by ``regen.py``.

These tables are owned by OTHER services, so they are not part of
``models.Base`` here. The DDL below mirrors the owners' real column names —
keep it in sync with:

  * characters               -> character-service/app/models.py (is_npc)
  * battles                  -> battle-service/app/models.py (status, created_at)
  * battle_participants      -> battle-service/app/models.py (joined_at, dropped_out_at)
  * dungeon_sessions         -> dungeon-service/app/models.py (status, started_at, finished_at)
  * dungeon_session_members  -> dungeon-service/app/models.py (session_id, character_id)
  * gathering_sessions       -> locations-service/app/models.py
                                (started_at, complete_at, status, finished_at)

``test_regen.py::TestSharedSchemaMatchesOwners`` greps the owner model files
for these column names so a rename on the owner side fails the suite instead
of silently turning the busy queries into "no busy time" (the recurring
silent-failure pattern: typo'd column + swallowed error + wrong fixture).
"""
from datetime import datetime
from typing import Optional

import os

import pytest
from sqlalchemy import text


def skip_or_fail_missing(path: str, what: str) -> None:
    """Cross-repo guard files missing: FAIL in CI (full checkout expected), skip locally."""
    msg = (
        f"{what} not found at {path} — this guard needs the whole repository "
        f"(run from a full checkout, e.g. mount the repo root into the container)"
    )
    if os.environ.get("CI"):
        pytest.fail(f"CI is set but {msg}")
    pytest.skip(msg)

SHARED_TABLES_DDL = (
    """
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NULL,
        name VARCHAR(255),
        id_class INTEGER NULL,
        is_npc BOOLEAN NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS battles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        battle_type VARCHAR(20) NOT NULL DEFAULT 'pve',
        created_at DATETIME,
        updated_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS battle_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        battle_id INTEGER NOT NULL REFERENCES battles(id),
        character_id INTEGER NOT NULL,
        team INTEGER NOT NULL DEFAULT 0,
        dropped_out_at DATETIME NULL,
        joined_at DATETIME NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dungeon_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dungeon_id INTEGER NOT NULL DEFAULT 1,
        leader_character_id INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(20) NOT NULL DEFAULT 'forming',
        current_room_id INTEGER NULL,
        started_at TIMESTAMP NULL,
        finished_at TIMESTAMP NULL,
        cooldown_until TIMESTAMP NULL,
        created_at TIMESTAMP NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dungeon_session_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL REFERENCES dungeon_sessions(id),
        character_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(20) NOT NULL DEFAULT 'alive',
        joined_at TIMESTAMP NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gathering_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id INTEGER NOT NULL DEFAULT 1,
        character_id INTEGER NOT NULL,
        tool_inventory_item_id INTEGER NULL,
        started_at TIMESTAMP NOT NULL,
        complete_at TIMESTAMP NOT NULL,
        effective_speed_bonus_pct FLOAT NOT NULL DEFAULT 0,
        effective_double_chance_pct FLOAT NOT NULL DEFAULT 0,
        effective_stamina_bonus_pct FLOAT NOT NULL DEFAULT 0,
        stamina_paid INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(30) NOT NULL DEFAULT 'active',
        finished_at TIMESTAMP NULL,
        result_quantity INTEGER NULL,
        xp_awarded INTEGER NULL
    )
    """,
)

SHARED_TABLE_NAMES = (
    "gathering_sessions",
    "dungeon_session_members",
    "dungeon_sessions",
    "battle_participants",
    "battles",
    "characters",
)


def _ts(value: Optional[datetime]) -> Optional[str]:
    """Store timestamps like MySQL/pymysql would hand them back (naive UTC)."""
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else None


def create_shared_tables(engine) -> None:
    with engine.begin() as conn:
        for ddl in SHARED_TABLES_DDL:
            conn.execute(text(ddl))


def drop_shared_tables(engine) -> None:
    with engine.begin() as conn:
        for name in SHARED_TABLE_NAMES:
            conn.execute(text(f"DROP TABLE IF EXISTS {name}"))


def add_character(
    db, character_id: int, is_npc: bool = False, user_id: Optional[int] = None
) -> None:
    """Insert a row into the shared ``characters`` table.

    ``user_id`` defaults to NULL, which FEAT-171's ``visibility.can_view_private``
    reads as "NPC/mob — no private layer", i.e. publicly readable. Pass an owner
    id to exercise the player path.
    """
    db.execute(
        text(
            "INSERT INTO characters (id, name, is_npc, user_id) "
            "VALUES (:id, :n, :npc, :uid)"
        ),
        {
            "id": character_id,
            "n": f"char{character_id}",
            "npc": 1 if is_npc else 0,
            "uid": user_id,
        },
    )
    db.commit()


def add_battle(
    db,
    character_id: int,
    status: str = "in_progress",
    created_at: Optional[datetime] = None,
    joined_at: Optional[datetime] = None,
    dropped_out_at: Optional[datetime] = None,
) -> int:
    res = db.execute(
        text("INSERT INTO battles (status, created_at, updated_at) VALUES (:s, :c, :c)"),
        {"s": status, "c": _ts(created_at)},
    )
    battle_id = res.lastrowid
    db.execute(
        text(
            "INSERT INTO battle_participants (battle_id, character_id, team, joined_at, dropped_out_at) "
            "VALUES (:b, :cid, 0, :j, :d)"
        ),
        {"b": battle_id, "cid": character_id, "j": _ts(joined_at), "d": _ts(dropped_out_at)},
    )
    db.commit()
    return battle_id


def add_dungeon(
    db,
    character_id: int,
    status: str = "active",
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> int:
    res = db.execute(
        text(
            "INSERT INTO dungeon_sessions (status, started_at, finished_at, leader_character_id) "
            "VALUES (:s, :st, :f, :cid)"
        ),
        {"s": status, "st": _ts(started_at), "f": _ts(finished_at), "cid": character_id},
    )
    session_id = res.lastrowid
    db.execute(
        text(
            "INSERT INTO dungeon_session_members (session_id, character_id, user_id) "
            "VALUES (:sid, :cid, 1)"
        ),
        {"sid": session_id, "cid": character_id},
    )
    db.commit()
    return session_id


def add_gathering(
    db,
    character_id: int,
    started_at: datetime,
    complete_at: datetime,
    status: str = "active",
    finished_at: Optional[datetime] = None,
) -> int:
    res = db.execute(
        text(
            "INSERT INTO gathering_sessions (character_id, started_at, complete_at, status, finished_at) "
            "VALUES (:cid, :st, :c, :s, :f)"
        ),
        {
            "cid": character_id,
            "st": _ts(started_at),
            "c": _ts(complete_at),
            "s": status,
            "f": _ts(finished_at),
        },
    )
    db.commit()
    return res.lastrowid
