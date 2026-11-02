"""
FEAT-196 — character-service side of the per-level resource growth.

character-service only *notifies* character-attributes-service that a level /
class may have changed (`POST /attributes/internal/{id}/sync-level`); the
attributes service re-reads `characters` itself. At creation the row is only
flushed, so `level` and `id_class` travel in the `POST /attributes/` body.

Covers:
  * crud.notify_level_changed: URL, X-Internal-Token, timeout, no body,
    True on 200, False + WARNING on non-200 / timeout / connect error / any
    exception — never raises;
  * crud.check_and_update_level: one notify per call that levels up (also a
    multi-level jump), only AFTER the commit, none without a level-up or for a
    missing character, an unreachable attributes service never breaks it;
  * PUT /characters/admin/{id}: notify on level up and down, none for an
    unchanged level / stat_points-only edit, still 200 when attributes is down;
  * PUT /characters/admin/npcs/{id}: notify on level or class change (once
    for both), none otherwise;
  * create bodies carry level + id_class: player approval (level 1 + request
    class; `starting_attributes` snapshot unchanged), admin NPC create, mob
    spawn (template level/class, NOT scaled by the dungeon multiplier).

The autouse `stub_notify_level_changed` fixture (conftest.py) replaces the
helper for every test in the suite; REAL_NOTIFY below is the real function,
captured at import time (before any fixture runs).
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import String

import auth_http
import crud
import database
import models
from auth_http import (
    OAUTH2_SCHEME,
    UserRead,
    get_admin_user,
    get_current_user_via_http,
    get_optional_user,
)
from config import settings
from database import Base
from main import app, get_db

# Patch Enum columns to String for SQLite compatibility (same as sibling tests).
for _model in (models.Character, models.CharacterRequest):
    for _col in _model.__table__.columns:
        if type(_col.type).__name__ == "Enum":
            _col.type = String(50)

REAL_NOTIFY = crud.notify_level_changed
TOKEN = "feat196-internal-token"

_ADMIN = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve",
        "npcs:read", "npcs:create", "npcs:update", "npcs:delete",
        "mobs:manage",
    ],
)

SUBRACE_PRESET = {
    "strength": 12, "agility": 14, "intelligence": 20, "endurance": 8,
    "health": 10, "mana": 12, "energy": 6, "stamina": 9,
    "charisma": 5, "luck": 4,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _pin_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


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
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = lambda: _ADMIN
    app.dependency_overrides[get_current_user_via_http] = lambda: _ADMIN
    app.dependency_overrides[get_optional_user] = lambda: _ADMIN
    app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def attributes_async_ok():
    """main.py's AsyncClient calls after an admin level change (XP sync,
    title-book lookup): answer 200 with plenty of XP, nothing else to do."""
    with patch("httpx.AsyncClient") as cls:
        inst = AsyncMock()
        ok = MagicMock(status_code=200, text="OK")
        ok.json.return_value = {"passive_experience": 10 ** 9}
        inst.get = AsyncMock(return_value=ok)
        inst.put = AsyncMock(return_value=ok)
        inst.post = AsyncMock(return_value=ok)
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        cls.return_value = inst
        yield inst


def _character(db, level=1, id_class=1, is_npc=False, **extra):
    values = dict(
        name="Тест", id_race=1, id_subrace=1, id_class=id_class, level=level,
        stat_points=0, appearance="", avatar="", currency_balance=0,
        is_npc=is_npc, user_id=None if is_npc else 10,
    )
    if is_npc:
        values.update(npc_role="merchant", npc_status="alive")
    values.update(extra)
    ch = models.Character(**values)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _thresholds(db, *pairs):
    for lv, xp in pairs:
        db.add(models.LevelThreshold(level_number=lv, required_experience=xp))
    db.commit()


def _resp(status):
    r = MagicMock()
    r.status_code = status
    return r


# ===========================================================================
# 1. notify_level_changed (real helper)
# ===========================================================================

class TestNotifyHelper:

    def test_posts_to_sync_level_with_internal_token(self):
        with patch("crud.httpx.post", return_value=_resp(200)) as post:
            assert REAL_NOTIFY(42) is True
        post.assert_called_once()
        url = post.call_args.args[0] if post.call_args.args else post.call_args.kwargs["url"]
        assert url == f"{settings.ATTRIBUTES_SERVICE_URL}internal/42/sync-level"
        assert url.endswith("/attributes/internal/42/sync-level")
        assert "//internal" not in url
        assert post.call_args.kwargs["headers"] == {"X-Internal-Token": TOKEN}
        assert post.call_args.kwargs["timeout"] == crud.LEVEL_SYNC_TIMEOUT_SECONDS == 5.0
        assert "json" not in post.call_args.kwargs and "data" not in post.call_args.kwargs

    @pytest.mark.parametrize("status", [401, 404, 500, 502])
    def test_non_200_returns_false_and_warns(self, status, caplog):
        with caplog.at_level(logging.WARNING), \
                patch("crud.httpx.post", return_value=_resp(status)):
            assert REAL_NOTIFY(7) is False
        assert any("sync-level" in r.getMessage() and str(status) in r.getMessage()
                   for r in caplog.records if r.levelno == logging.WARNING)

    @pytest.mark.parametrize("exc", [
        httpx.ReadTimeout("slow"),
        httpx.ConnectTimeout("slow"),
        httpx.ConnectError("refused"),
        RuntimeError("boom"),
    ])
    def test_errors_never_raise(self, exc, caplog):
        with caplog.at_level(logging.WARNING), \
                patch("crud.httpx.post", side_effect=exc):
            assert REAL_NOTIFY(7) is False
        assert any("sync-level" in r.getMessage() for r in caplog.records
                   if r.levelno == logging.WARNING)

    def test_on_event_loop_post_is_offloaded_to_a_thread(self):
        """Review #1: from the event-loop thread (async full_profile/titles
        handlers) the blocking post must not run on the loop — attributes may
        call back full_profile during the sync (expired satiety)."""
        import asyncio
        import threading

        loop_thread = {}
        post_thread = {}
        done = threading.Event()

        def fake_post(*args, **kwargs):
            post_thread["t"] = threading.current_thread()
            done.set()
            return _resp(200)

        async def call_from_loop():
            loop_thread["t"] = threading.current_thread()
            return REAL_NOTIFY(42)

        with patch("crud.httpx.post", side_effect=fake_post) as post:
            assert asyncio.run(call_from_loop()) is True
            assert done.wait(5)
        post.assert_called_once()
        assert post_thread["t"] is not loop_thread["t"]
        assert post_thread["t"].daemon

    def test_off_loop_post_stays_synchronous(self):
        import threading
        seen = {}

        def fake_post(*args, **kwargs):
            seen["t"] = threading.current_thread()
            return _resp(200)

        with patch("crud.httpx.post", side_effect=fake_post):
            assert REAL_NOTIFY(42) is True
        assert seen["t"] is threading.current_thread()


# ===========================================================================
# 2. check_and_update_level
# ===========================================================================

class TestCheckAndUpdateLevel:

    def test_level_up_notifies_once_after_commit(self, db_session, stub_notify_level_changed):
        _thresholds(db_session, (2, 100), (3, 250))
        ch = _character(db_session, level=1)
        order = []
        real_commit = db_session.commit

        def spy_commit():
            order.append("commit")
            return real_commit()

        stub_notify_level_changed.side_effect = lambda cid: order.append(("notify", cid))
        with patch.object(db_session, "commit", side_effect=spy_commit):
            crud.check_and_update_level(db_session, ch.id, 120)
        assert order == ["commit", ("notify", ch.id)]
        db_session.expire_all()
        assert db_session.get(models.Character, ch.id).level == 2

    def test_multi_level_jump_notifies_once(self, db_session, stub_notify_level_changed):
        _thresholds(db_session, (2, 100), (3, 250), (4, 450))
        ch = _character(db_session, level=1)
        crud.check_and_update_level(db_session, ch.id, 500)
        db_session.refresh(ch)
        assert ch.level == 4 and ch.stat_points == 30
        stub_notify_level_changed.assert_called_once_with(ch.id)

    def test_no_level_up_no_notify(self, db_session, stub_notify_level_changed):
        _thresholds(db_session, (2, 100))
        ch = _character(db_session, level=1)
        crud.check_and_update_level(db_session, ch.id, 99)
        db_session.refresh(ch)
        assert ch.level == 1
        stub_notify_level_changed.assert_not_called()

    def test_no_threshold_no_notify(self, db_session, stub_notify_level_changed):
        ch = _character(db_session, level=5)
        crud.check_and_update_level(db_session, ch.id, 10 ** 9)
        stub_notify_level_changed.assert_not_called()

    def test_missing_character_no_notify(self, db_session, stub_notify_level_changed):
        assert crud.check_and_update_level(db_session, 987654, 10 ** 9) is None
        stub_notify_level_changed.assert_not_called()

    def test_each_level_up_call_notifies(self, db_session, stub_notify_level_changed):
        _thresholds(db_session, (2, 100), (3, 250))
        ch = _character(db_session, level=1)
        crud.check_and_update_level(db_session, ch.id, 100)
        crud.check_and_update_level(db_session, ch.id, 100)  # no-op
        crud.check_and_update_level(db_session, ch.id, 260)
        assert stub_notify_level_changed.call_count == 2

    @pytest.mark.parametrize("failure", [
        {"side_effect": httpx.ReadTimeout("slow")},
        {"side_effect": httpx.ConnectError("down")},
        {"return_value": _resp(503)},
    ])
    def test_attributes_down_level_up_still_committed(self, db_session, monkeypatch, failure):
        monkeypatch.setattr(crud, "notify_level_changed", REAL_NOTIFY)
        _thresholds(db_session, (2, 100))
        ch = _character(db_session, level=1)
        with patch("crud.httpx.post", **failure) as post:
            result = crud.check_and_update_level(db_session, ch.id, 150)
        post.assert_called_once()
        assert result.level == 2
        db_session.expire_all()
        stored = db_session.get(models.Character, ch.id)
        assert stored.level == 2 and stored.stat_points == 10


# ===========================================================================
# 3. Admin character update
# ===========================================================================

class TestAdminCharacterUpdate:

    def test_level_up_notifies(self, client, db_session, attributes_async_ok,
                               stub_notify_level_changed):
        ch = _character(db_session, level=3)
        seen = []
        stub_notify_level_changed.side_effect = lambda cid: seen.append(
            (cid, db_session.get(models.Character, cid).level))
        resp = client.put(f"/characters/admin/{ch.id}", json={"level": 7})
        assert resp.status_code == 200, resp.text
        assert seen == [(ch.id, 7)]

    def test_level_down_notifies(self, client, db_session, attributes_async_ok,
                                 stub_notify_level_changed):
        ch = _character(db_session, level=9)
        resp = client.put(f"/characters/admin/{ch.id}", json={"level": 2})
        assert resp.status_code == 200, resp.text
        stub_notify_level_changed.assert_called_once_with(ch.id)
        db_session.expire_all()
        assert db_session.get(models.Character, ch.id).level == 2

    def test_same_level_no_notify(self, client, db_session, attributes_async_ok,
                                  stub_notify_level_changed):
        ch = _character(db_session, level=4)
        resp = client.put(f"/characters/admin/{ch.id}", json={"level": 4, "stat_points": 0})
        assert resp.status_code == 200, resp.text
        stub_notify_level_changed.assert_not_called()

    def test_stat_points_only_no_notify(self, client, db_session, attributes_async_ok,
                                        stub_notify_level_changed):
        ch = _character(db_session, level=4)
        resp = client.put(f"/characters/admin/{ch.id}", json={"stat_points": 25})
        assert resp.status_code == 200, resp.text
        stub_notify_level_changed.assert_not_called()

    def test_invalid_level_no_notify(self, client, db_session, stub_notify_level_changed):
        ch = _character(db_session, level=4)
        assert client.put(f"/characters/admin/{ch.id}", json={"level": 0}).status_code == 400
        stub_notify_level_changed.assert_not_called()

    def test_attributes_down_still_200(self, client, db_session, attributes_async_ok, monkeypatch):
        monkeypatch.setattr(crud, "notify_level_changed", REAL_NOTIFY)
        ch = _character(db_session, level=3)
        with patch("crud.httpx.post", side_effect=httpx.ConnectError("down")) as post:
            resp = client.put(f"/characters/admin/{ch.id}", json={"level": 5})
        assert resp.status_code == 200, resp.text
        assert post.call_count == 1
        assert post.call_args.args[0].endswith(f"/internal/{ch.id}/sync-level")
        db_session.expire_all()
        assert db_session.get(models.Character, ch.id).level == 5


# ===========================================================================
# 4. Admin NPC update / create
# ===========================================================================

class TestAdminNpc:

    def test_level_change_notifies(self, client, db_session, stub_notify_level_changed):
        npc = _character(db_session, level=2, is_npc=True)
        resp = client.put(f"/characters/admin/npcs/{npc.id}", json={"level": 15})
        assert resp.status_code == 200, resp.text
        stub_notify_level_changed.assert_called_once_with(npc.id)

    def test_class_change_notifies(self, client, db_session, stub_notify_level_changed):
        npc = _character(db_session, level=2, id_class=1, is_npc=True)
        seen = []
        stub_notify_level_changed.side_effect = lambda cid: seen.append(
            db_session.get(models.Character, cid).id_class)
        resp = client.put(f"/characters/admin/npcs/{npc.id}", json={"id_class": 3})
        assert resp.status_code == 200, resp.text
        assert seen == [3]

    def test_level_and_class_notify_once(self, client, db_session, stub_notify_level_changed):
        npc = _character(db_session, level=2, id_class=1, is_npc=True)
        resp = client.put(f"/characters/admin/npcs/{npc.id}", json={"level": 1, "id_class": 2})
        assert resp.status_code == 200, resp.text
        stub_notify_level_changed.assert_called_once_with(npc.id)

    @pytest.mark.parametrize("body", [
        {"name": "Новое имя"},
        {"level": 2},
        {"id_class": 1},
        {"level": 2, "id_class": 1, "biography": "Другая"},
    ])
    def test_no_level_class_change_no_notify(self, client, db_session,
                                             stub_notify_level_changed, body):
        npc = _character(db_session, level=2, id_class=1, is_npc=True)
        resp = client.put(f"/characters/admin/npcs/{npc.id}", json=body)
        assert resp.status_code == 200, resp.text
        stub_notify_level_changed.assert_not_called()

    def test_attributes_down_npc_update_still_200(self, client, db_session, monkeypatch):
        monkeypatch.setattr(crud, "notify_level_changed", REAL_NOTIFY)
        npc = _character(db_session, level=2, is_npc=True)
        with patch("crud.httpx.post", side_effect=httpx.ReadTimeout("slow")):
            resp = client.put(f"/characters/admin/npcs/{npc.id}", json={"level": 6})
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.get(models.Character, npc.id).level == 6

    def test_create_body_has_level_and_class(self, client, db_session, stub_notify_level_changed):
        with patch("crud.generate_attributes_for_subrace", return_value=dict(SUBRACE_PRESET)), \
                patch("crud.send_attributes_request", new_callable=AsyncMock,
                      return_value={"id": 555}) as send:
            resp = client.post("/characters/admin/npcs", json={
                "name": "Страж", "id_class": 3, "id_race": 1, "id_subrace": 1, "level": 12,
            })
        assert resp.status_code == 200, resp.text
        send.assert_awaited_once()
        cid, body = send.await_args.args
        assert cid == resp.json()["id"]
        assert body["level"] == 12 and body["id_class"] == 3
        for k, v in SUBRACE_PRESET.items():
            assert body[k] == v
        # creation itself carries level/class; no separate sync needed
        stub_notify_level_changed.assert_not_called()


# ===========================================================================
# 5. Mob spawn
# ===========================================================================

def _template(db, level=7, id_class=2, base=None):
    t = models.MobTemplate(
        name="Волк", tier="normal", level=level, id_race=1, id_subrace=1,
        id_class=id_class, sex="genderless",
        base_attributes=base if base is not None else {"strength": 15, "health": 20, "mana": 4},
        xp_reward=10, gold_reward=1, respawn_enabled=False, respawn_seconds=None,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


class TestMobSpawn:

    def test_body_has_template_level_and_class(self, db_session):
        t = _template(db_session, level=7, id_class=2)
        with patch("crud._sync_send_attributes_request", return_value={"id": 1}) as send:
            _, character = crud.spawn_mob_from_template(db_session, t.id, location_id=1)
        cid, body = send.call_args.args
        assert cid == character.id
        assert body["level"] == 7 and body["id_class"] == 2
        assert character.level == 7 and character.id_class == 2
        assert body["strength"] == 15 and body["health"] == 20

    @pytest.mark.parametrize("multiplier", [0.5, 2.0, 3.0])
    def test_dungeon_multiplier_does_not_scale_level(self, db_session, multiplier):
        t = _template(db_session, level=7, id_class=1)
        with patch("crud._sync_send_attributes_request", return_value={"id": 1}) as send:
            crud.spawn_mob_from_template(db_session, t.id, location_id=1,
                                         stat_multiplier=multiplier)
        body = send.call_args.args[1]
        assert body["level"] == 7 and body["id_class"] == 1
        assert body["strength"] == int(round(15 * multiplier))
        assert body["health"] == int(round(20 * multiplier))

    def test_template_base_attributes_not_mutated(self, db_session):
        base = {"strength": 15, "health": 20}
        t = _template(db_session, base=dict(base))
        with patch("crud._sync_send_attributes_request", return_value={"id": 1}):
            crud.spawn_mob_from_template(db_session, t.id, location_id=1)
        db_session.expire_all()
        assert db_session.get(models.MobTemplate, t.id).base_attributes == base


# ===========================================================================
# 6. Player approval
# ===========================================================================

@pytest.fixture
def approval_env():
    with patch("main.locations_client") as locations, \
            patch("main.httpx.get") as user_service, \
            patch("main.send_character_approved_notification", new_callable=AsyncMock), \
            patch("main.publish_character_inventory", new_callable=AsyncMock), \
            patch("main.publish_character_skills", new_callable=AsyncMock), \
            patch("main.publish_character_attributes", new_callable=AsyncMock), \
            patch("crud.send_inventory_request", new_callable=AsyncMock, return_value={"status": "ok"}), \
            patch("crud.send_skills_presets_request", new_callable=AsyncMock, return_value={"status": "ok"}), \
            patch("crud.assign_character_to_user", new_callable=AsyncMock, return_value=True), \
            patch("crud.send_attributes_request", new_callable=AsyncMock,
                  return_value={"id": 999}) as attrs:
        locations.probe_starting_point = AsyncMock(return_value=True)
        locations.get_default_starting_point_id = AsyncMock(return_value=700)
        ok = MagicMock(status_code=200)
        ok.json.return_value = {"username": "player"}
        user_service.return_value = ok
        yield attrs


class TestApproval:

    @pytest.mark.parametrize("class_id", [1, 2, 3])
    def test_body_has_level_1_and_class_snapshot_clean(self, client, db_session,
                                                       approval_env, class_id):
        subrace = db_session.query(models.Subrace).filter_by(id_subrace=4).one()
        subrace.stat_preset = dict(SUBRACE_PRESET)
        db_session.commit()
        req = models.CharacterRequest(
            user_id=42, name=f"Аэлис{class_id}", id_race=2, id_subrace=4, id_class=class_id,
            biography="Био", personality="Характер", appearance="Высокая",
            sex="female", age=120, avatar="https://example.com/a.webp",
            status="pending", request_type="creation",
        )
        db_session.add(req)
        db_session.commit()

        resp = client.post(f"/characters/requests/{req.id}/approve")
        assert resp.status_code == 200, resp.text

        approval_env.assert_awaited_once()
        cid, body = approval_env.await_args.args
        character = db_session.query(models.Character).one()
        assert cid == character.id
        assert body["level"] == 1 == character.level
        assert body["id_class"] == class_id == character.id_class
        # the snapshot is the stats only — no level/class leaked into it
        assert character.starting_attributes == SUBRACE_PRESET
        assert "level" not in character.starting_attributes
        assert "id_class" not in character.starting_attributes
        assert {k: v for k, v in body.items() if k not in ("level", "id_class")} == SUBRACE_PRESET
