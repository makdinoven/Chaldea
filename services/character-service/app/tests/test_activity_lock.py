"""FEAT-175: activity lock (dungeon run / knock-out) owned by character-service,
dungeon mobs never reaching the surface, dungeon mob_multiplier scaling."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
from unittest.mock import patch

import httpx

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import auth_http
import activity_lock
import crud
import database
import models
from database import Base
from main import app, get_db

TOKEN = "test-internal-token"
H = {"X-Internal-Token": TOKEN}


@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client(db_session, monkeypatch):
    def override_get_db():
        yield db_session

    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _char(db, name="Арья", user_id=1, location=100, npc=False):
    c = models.Character(
        name=name, id_race=1, id_subrace=1, id_class=1, sex="genderless", level=1,
        avatar="a.png", appearance="", is_npc=npc, npc_role="mob" if npc else None,
        user_id=user_id, request_id=None, currency_balance=0, stat_points=0,
        current_location_id=location,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ---------------------------------------------------------------- pure helpers

def test_compute_lock_priorities():
    soon = datetime.utcnow() + timedelta(minutes=5)
    assert activity_lock.compute_lock(None, None)["locked"] is False
    assert activity_lock.compute_lock(7, None)["reason"] == "dungeon"
    assert activity_lock.compute_lock(7, soon)["reason"] == "unconscious"
    assert activity_lock.compute_lock(None, datetime.utcnow() - timedelta(seconds=1))["locked"] is False


def test_messages():
    assert activity_lock.lock_message({"locked": True, "reason": "dungeon"}) == "Персонаж находится в подземелье"
    msg = activity_lock.lock_message({"locked": True, "reason": "unconscious", "until": "2026-10-22T20:30:00"})
    assert msg == "Персонаж без сознания до 23:30 МСК"
    assert activity_lock.lock_message({"locked": False}) is None


# ---------------------------------------------------------------- internal endpoints

def test_get_activity_lock_endpoint(client, db_session):
    c = _char(db_session)
    assert client.get(f"/characters/internal/{c.id}/activity-lock").status_code == 401
    r = client.get(f"/characters/internal/{c.id}/activity-lock", headers=H)
    assert r.status_code == 200
    assert r.json() == {"locked": False, "reason": None, "until": None, "dungeon_session_id": None}
    assert client.get("/characters/internal/999999/activity-lock", headers=H).status_code == 404


def test_set_lock_all_or_nothing(client, db_session):
    a, b = _char(db_session, "А"), _char(db_session, "Б", user_id=2)
    b.unconscious_until = datetime.utcnow() + timedelta(hours=1)
    db_session.commit()
    r = client.post("/characters/internal/activity-lock/dungeon",
                    json={"character_ids": [a.id, b.id], "session_id": 5}, headers=H)
    assert r.status_code == 409
    assert r.json()["detail"]["character_id"] == b.id
    assert r.json()["detail"]["message"].startswith("Б без сознания до")
    db_session.expire_all()
    assert db_session.get(models.Character, a.id).dungeon_session_id is None, "nothing written"

    b.unconscious_until = None
    db_session.commit()
    r = client.post("/characters/internal/activity-lock/dungeon",
                    json={"character_ids": [a.id, b.id], "session_id": 5}, headers=H)
    assert r.status_code == 200
    # idempotent for the same session, refused for another one
    assert client.post("/characters/internal/activity-lock/dungeon",
                       json={"character_ids": [a.id], "session_id": 5}, headers=H).status_code == 200
    r = client.post("/characters/internal/activity-lock/dungeon",
                    json={"character_ids": [a.id], "session_id": 6}, headers=H)
    assert r.status_code == 409
    assert r.json()["detail"]["message"] == "А находится в подземелье"


def test_clear_only_matching_session(client, db_session):
    a = _char(db_session)
    a.dungeon_session_id = 5
    db_session.commit()
    r = client.post("/characters/internal/activity-lock/dungeon/clear",
                    json={"character_ids": [a.id], "session_id": 4}, headers=H)
    assert r.json()["cleared"] == []
    r = client.post("/characters/internal/activity-lock/dungeon/clear",
                    json={"character_ids": [a.id], "session_id": 5}, headers=H)
    assert r.json()["cleared"] == [a.id]
    db_session.expire_all()
    assert db_session.get(models.Character, a.id).dungeon_session_id is None


def test_knockout_one_hour_and_return_to_location(client, db_session):
    a = _char(db_session, location=55)
    a.dungeon_session_id = 9
    db_session.commit()
    r = client.post("/characters/internal/activity-lock/knockout",
                    json={"character_ids": [a.id], "seconds": 3600, "session_id": 9,
                          "return_location_id": 100}, headers=H)
    assert r.status_code == 200
    assert r.json()["characters"] == [{"character_id": a.id, "moved": True}]
    db_session.expire_all()
    c = db_session.get(models.Character, a.id)
    assert c.dungeon_session_id is None
    assert c.current_location_id == 100
    left = c.unconscious_until - datetime.utcnow()
    assert timedelta(minutes=59) < left <= timedelta(hours=1)
    lock = client.get(f"/characters/internal/{a.id}/activity-lock", headers=H).json()
    assert lock["reason"] == "unconscious" and lock["until"]
    bad = client.post("/characters/internal/activity-lock/knockout",
                      json={"character_ids": [a.id], "seconds": 0}, headers=H)
    assert bad.status_code == 422


def test_profile_and_short_info_expose_lock(client, db_session):
    a = _char(db_session)
    a.dungeon_session_id = 3
    db_session.commit()
    with patch("main.httpx.AsyncClient") as ac:
        ac.return_value.__aenter__.return_value.get.side_effect = httpx.RequestError("no user-service")
        r = client.get(f"/characters/{a.id}/profile")
    assert r.status_code == 200, r.text
    assert r.json()["activity_lock"] == {"locked": True, "reason": "dungeon", "until": None,
                                        "dungeon_session_id": 3}
    r = client.get(f"/characters/internal/{a.id}/short_info", headers=H)
    assert r.json()["activity_lock"]["reason"] == "dungeon"


# ---------------------------------------------------------------- Teleport Master

def test_teleport_master_refuses_locked_character(db_session):
    a = _char(db_session)
    a.unconscious_until = datetime.utcnow() + timedelta(minutes=30)
    db_session.commit()
    from sqlalchemy import text
    db_session.execute(text("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, current_character INTEGER)"))
    db_session.execute(text("INSERT INTO users (id, current_character) VALUES (1, :c)"), {"c": a.id})
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        crud.execute_teleport(db_session, user_id=1, source_npc_id=12345, link_id=1)
    assert exc.value.status_code == 409
    assert "без сознания" in exc.value.detail
    db_session.execute(text("DROP TABLE users"))
    db_session.commit()


# ---------------------------------------------------------------- dungeon mobs

def _template(db):
    t = models.MobTemplate(name="Крыса", tier="normal", level=2, id_race=1, id_subrace=1, id_class=1,
                           sex="genderless", base_attributes={"strength": 10, "health": 40, "luck": 0},
                           xp_reward=5, gold_reward=1, respawn_enabled=True, respawn_seconds=60)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_dungeon_mobs_are_invisible_and_never_respawn(db_session):
    t = _template(db_session)
    m = _char(db_session, "Крыса", user_id=None, npc=True, location=10)
    am = models.ActiveMob(mob_template_id=t.id, character_id=m.id, location_id=10,
                          status="alive", spawn_type="dungeon")
    db_session.add(am)
    db_session.commit()
    assert crud.get_mobs_at_location(db_session, 10) == []

    crud.update_active_mob_status(db_session, m.id, "dead")
    db_session.refresh(am)
    assert am.respawn_at is None, "dungeon mobs never get a respawn timer"

    # a legacy leaked row with a past respawn_at stays dead and hidden
    am.respawn_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()
    assert crud.get_mobs_at_location(db_session, 10) == []
    db_session.refresh(am)
    assert am.status == "dead"


def test_despawn_endpoint_only_touches_dungeon_mobs(client, db_session):
    t = _template(db_session)
    m1 = _char(db_session, "Д", user_id=None, npc=True)
    m2 = _char(db_session, "П", user_id=None, npc=True)
    db_session.add_all([
        models.ActiveMob(mob_template_id=t.id, character_id=m1.id, location_id=1, status="dead", spawn_type="dungeon"),
        models.ActiveMob(mob_template_id=t.id, character_id=m2.id, location_id=1, status="alive", spawn_type="random"),
    ])
    db_session.commit()
    r = client.post("/characters/internal/despawn-dungeon-mobs", json={"character_ids": [m1.id, m2.id]}, headers=H)
    assert r.json() == {"removed": 1}
    left = db_session.query(models.ActiveMob).all()
    assert [x.character_id for x in left] == [m2.id]


def test_mob_multiplier_scales_spawned_stats(db_session):
    t = _template(db_session)
    sent = {}

    def fake_send(cid, attrs):
        sent.update(attrs)
        return {"id": 1}
    with patch.object(crud, "_sync_send_attributes_request", side_effect=fake_send):
        am, ch = crud.spawn_mob_from_template(db_session, t.id, 10, "dungeon", stat_multiplier=1.5)
    assert sent["strength"] == 15 and sent["health"] == 60 and sent["luck"] == 0
    assert am.spawn_type == "dungeon"


def test_scale_never_zeroes_positive_stats():
    assert crud._scale_mob_attributes({"a": 1, "b": 0, "c": "x"}, 0.1) == {"a": 1, "b": 0, "c": "x"}


def test_spawn_request_validates_multiplier():
    import schemas
    with pytest.raises(Exception):
        schemas.SpawnDungeonMobsRequest(mob_template_ids=[1], location_id=1, stat_multiplier=0)
    assert schemas.SpawnDungeonMobsRequest(mob_template_ids=[1], location_id=1).stat_multiplier == 1.0
