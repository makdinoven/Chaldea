"""
Tests for the home-page mini-stats leaderboards (GET /characters/home-leaderboards).

Covers:
1. symbols_daily — sums character_logs.metadata.char_count for rp_post in the last
   24h, orders desc, ignores posts older than the window.
2. pvp — orders by character_cumulative_stats.pvp_wins desc, omits zero rows.
3. pve — orders by character_cumulative_stats.pve_points desc (level-weighted).
4. NPCs are excluded from every board.
5. limit caps each board.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta

import database
from database import Base
from main import app, get_db
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text
import models


@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    # character_cumulative_stats is owned by character-attributes-service and is
    # not in this service's models — create a minimal version for the test.
    session.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS character_cumulative_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER,
            pvp_wins INTEGER DEFAULT 0,
            pve_points INTEGER DEFAULT 0
        )
    """))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        session_engine = database.engine
        with session_engine.begin() as conn:
            conn.execute(sa_text("DROP TABLE IF EXISTS character_cumulative_stats"))
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _make_char(session, cid, name, is_npc=False):
    session.add(models.Character(
        id=cid, name=name, id_subrace=1, id_class=1, id_race=1,
        appearance="—", avatar=f"avatar_{cid}.png", level=1, is_npc=is_npc,
    ))


def _add_post(session, cid, char_count, hours_ago):
    session.add(models.CharacterLog(
        character_id=cid,
        event_type="rp_post",
        description="post",
        metadata_={"char_count": char_count},
        created_at=datetime.utcnow() - timedelta(hours=hours_ago),
    ))


def _set_stats(session, cid, pvp_wins=0, pve_points=0):
    session.execute(
        sa_text("INSERT INTO character_cumulative_stats (character_id, pvp_wins, pve_points) "
                "VALUES (:cid, :w, :p)"),
        {"cid": cid, "w": pvp_wins, "p": pve_points},
    )


def _seed(session):
    _make_char(session, 1, "Алиса")
    _make_char(session, 2, "Борис")
    _make_char(session, 3, "Вика")
    _make_char(session, 99, "МобНПС", is_npc=True)

    # Symbols in the last 24h: Борис 1500, Алиса 500. Вика's post is 30h old.
    _add_post(session, 1, 500, hours_ago=2)
    _add_post(session, 2, 1000, hours_ago=3)
    _add_post(session, 2, 500, hours_ago=1)
    _add_post(session, 3, 9999, hours_ago=30)   # outside window → excluded
    _add_post(session, 99, 8000, hours_ago=1)   # NPC → excluded

    # PvP wins: Алиса 10, Борис 5. PvE points: Борис 250, Алиса 100.
    _set_stats(session, 1, pvp_wins=10, pve_points=100)
    _set_stats(session, 2, pvp_wins=5, pve_points=250)
    _set_stats(session, 3, pvp_wins=0, pve_points=0)      # zero → omitted
    _set_stats(session, 99, pvp_wins=99, pve_points=99)   # NPC → excluded
    session.commit()


def test_leaderboards_ordering_and_windowing(client, db_session):
    _seed(db_session)
    resp = client.get("/characters/home-leaderboards")
    assert resp.status_code == 200
    data = resp.json()

    # Symbols: Борис (1500) before Алиса (500); Вика (old) & NPC absent.
    symbols = data["symbols_daily"]
    assert [(e["name"], e["value"]) for e in symbols] == [("Борис", 1500), ("Алиса", 500)]

    # PvP: Алиса (10) before Борис (5); zero row & NPC absent.
    assert [(e["name"], e["value"]) for e in data["pvp"]] == [("Алиса", 10), ("Борис", 5)]

    # PvE: Борис (250) before Алиса (100).
    assert [(e["name"], e["value"]) for e in data["pve"]] == [("Борис", 250), ("Алиса", 100)]

    # Avatars are carried through.
    assert symbols[0]["avatar"] == "avatar_2.png"


def test_leaderboards_limit(client, db_session):
    _seed(db_session)
    resp = client.get("/characters/home-leaderboards", params={"limit": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["pvp"]) == 1
    assert data["pvp"][0]["name"] == "Алиса"


def test_leaderboards_empty(client, db_session):
    # No characters / no data → empty boards, still 200.
    resp = client.get("/characters/home-leaderboards")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"symbols_daily": [], "pvp": [], "pve": []}
