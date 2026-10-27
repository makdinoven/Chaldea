"""FEAT-179: episodes — player-run stories with their own locations, members and mini-roles.

Routes run through TestClient against a file-backed SQLite: the schema is laid
out with a plain sync engine, each request opens its own aiosqlite session.
"""

import os
import sys
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import episodes  # noqa: E402
import models  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from database import get_db  # noqa: E402
from main import app  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


@compiles(MEDIUMTEXT, "sqlite")
def _mediumtext(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "TEXT"


OWNER, MASTER, PLAYER, STRANGER, ADMIN, MODER = 1, 2, 3, 4, 5, 6
USERS = {OWNER: "Owner", MASTER: "Master", PLAYER: "Player", STRANGER: "Stranger", ADMIN: "Admin", MODER: "Moder"}
ROLES = {ADMIN: "admin", MODER: "moderator"}
IMG = "https://s3.example/bucket/episode_images/a.webp"

TABLES = [models.Episode, models.EpisodeMember, models.EpisodeRole, models.EpisodeLocation,
          models.EpisodePost, models.EpisodePostLike, models.EpisodeJoinRequest]


@pytest.fixture()
def api(tmp_path, monkeypatch):
    path = tmp_path / "episodes.db"
    sync = create_engine(f"sqlite:///{path}")
    with sync.begin() as conn:
        for m in TABLES:
            m.__table__.create(conn)
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, avatar TEXT)"))
        for uid, name in USERS.items():
            conn.execute(text("INSERT INTO users VALUES (:i, :n, NULL)"), {"i": uid, "n": name})
    sync.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with Session() as s:
            yield s

    who = {"id": None}

    def _user():
        uid = who["id"]
        return UserRead(id=uid, username=USERS[uid], role=ROLES.get(uid, "user"), permissions=[])

    def _viewer():
        return _user() if who["id"] else None

    notes = []
    monkeypatch.setattr(episodes, "publish_notification_sync", lambda uid, msg: notes.append((uid, msg)))
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user_via_http] = _user
    app.dependency_overrides[episodes.get_viewer] = _viewer

    class Api:
        notifications = notes

        def __init__(self, client):
            self.c = client

        def as_(self, uid):
            who["id"] = uid
            return self

        def __getattr__(self, method):
            return lambda url, json=None: getattr(self.c, method)(
                "/locations/episodes" + url, **({"json": json} if json is not None else {}))

    with TestClient(app) as client:
        yield Api(client)
    app.dependency_overrides.clear()


def _story(api, private=False):
    """An episode by OWNER with a location, MASTER as a master and PLAYER holding a role."""
    eid = api.as_(OWNER).post("", {"category": "separate", "title": "Сказка", "description": "Про лес",
                                   "image_url": IMG, "is_private": private}).json()["id"]
    lid = api.post(f"/{eid}/locations", {"name": "Опушка", "description": "Тихо"}).json()["id"]
    for uid in (MASTER, PLAYER):
        assert api.post(f"/{eid}/members", {"user_id": uid}).status_code == 200
    assert api.put(f"/{eid}/members/{MASTER}", {"role": "master"}).status_code == 200
    rid = api.post(f"/{eid}/roles", {"user_id": PLAYER, "name": "Волк"}).json()["id"]
    return eid, lid, rid


# --- creation ---------------------------------------------------------------

def test_owner_is_a_member_and_the_limit_holds(api):
    for i in range(episodes.OWNED_EPISODES_LIMIT):
        r = api.as_(OWNER).post("", {"category": "world", "title": f"E{i}", "description": "d"})
        assert r.status_code == 200
    r = api.post("", {"category": "world", "title": "lots", "description": "d"})
    assert r.status_code == 409
    detail = api.get(f"/{1}").json()
    assert detail["my_role"] == "owner" and detail["is_owner"] and detail["can_manage"]


def test_bad_category_and_foreign_pictures_are_refused(api):
    assert api.as_(OWNER).post("", {"category": "x", "title": "a", "description": "b"}).status_code == 422
    r = api.post("", {"category": "world", "title": "a", "description": "b", "image_url": "https://evil.com/x.png"})
    assert r.status_code == 422


def test_category_filter(api):
    api.as_(OWNER).post("", {"category": "world", "title": "W", "description": "d"})
    api.post("", {"category": "separate", "title": "S", "description": "d"})
    assert [e["title"] for e in api.get("?category=world").json()] == ["W"]


# --- privacy ----------------------------------------------------------------

def test_private_episode_is_shut_to_outsiders_and_moderators(api):
    eid, lid, _ = _story(api, private=True)
    for uid in (STRANGER, MODER):
        assert api.as_(uid).get(f"/{eid}").status_code == 403
        assert api.get(f"/{eid}/locations/{lid}/posts").status_code == 403
        assert api.get("").json() == []
    assert api.as_(None).get(f"/{eid}").status_code == 403
    assert api.as_(ADMIN).get(f"/{eid}").status_code == 200
    assert api.as_(PLAYER).get(f"/{eid}").status_code == 200
    assert [e["id"] for e in api.get("").json()] == [eid]


def test_public_episode_is_read_by_anyone_but_written_by_members(api):
    eid, lid, rid = _story(api)
    assert api.as_(None).get(f"/{eid}/locations/{lid}").status_code == 200
    assert api.as_(STRANGER).post(f"/{eid}/locations/{lid}/posts", {"role_id": rid, "content": "<p>Я</p>"}).status_code == 403


def test_hidden_episode_seen_by_members_and_staff_only(api):
    eid, _, _ = _story(api)
    assert api.as_(PLAYER).post(f"/{eid}/hide", {"hidden": True}).status_code == 403
    assert api.as_(MODER).post(f"/{eid}/hide", {"hidden": True}).status_code == 200
    assert api.as_(STRANGER).get(f"/{eid}").status_code == 404
    assert api.as_(MODER).get(f"/{eid}").status_code == 200
    assert api.as_(PLAYER).get(f"/{eid}").status_code == 200


# --- managing ---------------------------------------------------------------

def test_players_cannot_manage_masters_can(api):
    eid, lid, _ = _story(api)
    assert api.as_(PLAYER).post(f"/{eid}/locations", {"name": "X"}).status_code == 403
    assert api.as_(MASTER).post(f"/{eid}/locations", {"name": "X"}).status_code == 200
    assert api.as_(MASTER).put(f"/{eid}/locations/{lid}", {"name": "Чаща", "description": "", "image_url": IMG}).status_code == 200
    # Only the owner names masters and deletes the episode.
    assert api.as_(MASTER).put(f"/{eid}/members/{PLAYER}", {"role": "master"}).status_code == 403
    assert api.as_(MASTER).delete(f"/{eid}").status_code == 403
    assert api.as_(OWNER).delete(f"/{eid}").status_code == 200


def test_member_removal_rules(api):
    eid, _, rid = _story(api)
    assert api.as_(MASTER).delete(f"/{eid}/members/{OWNER}").status_code == 400
    assert api.as_(PLAYER).delete(f"/{eid}/members/{MASTER}").status_code == 403
    # Removed: their roles go to the archive and stop writing.
    assert api.as_(MASTER).delete(f"/{eid}/members/{PLAYER}").status_code == 200
    detail = api.get(f"/{eid}").json()
    assert PLAYER not in [m["user_id"] for m in detail["members"]]


def test_a_member_may_leave(api):
    eid, _, _ = _story(api)
    assert api.as_(PLAYER).delete(f"/{eid}/members/{PLAYER}").status_code == 200
    assert api.get(f"/{eid}").json()["my_role"] is None


def test_roles_only_for_members(api):
    eid, _, _ = _story(api)
    assert api.as_(OWNER).post(f"/{eid}/roles", {"user_id": STRANGER}).status_code == 400


def test_holder_dresses_their_role_others_cannot(api):
    eid, _, rid = _story(api)
    body = {"name": "Серый волк", "avatar_url": IMG, "description": "Голодный"}
    assert api.as_(PLAYER).put(f"/{eid}/roles/{rid}", body).status_code == 200
    assert api.as_(STRANGER).put(f"/{eid}/roles/{rid}", body).status_code == 403
    player = next(m for m in api.as_(OWNER).get(f"/{eid}").json()["members"] if m["user_id"] == PLAYER)
    assert player["roles"][0]["name"] == "Серый волк"


def test_role_with_posts_is_archived_not_deleted(api):
    eid, lid, rid = _story(api)
    api.as_(PLAYER).post(f"/{eid}/locations/{lid}/posts", {"role_id": rid, "content": "<p>Ау</p>"})
    r = api.as_(OWNER).delete(f"/{eid}/roles/{rid}")
    assert r.json()["archived"] is True
    posts = api.get(f"/{eid}/locations/{lid}/posts").json()["posts"]
    assert posts[0]["role"]["name"] == "Волк"
    assert api.as_(PLAYER).post(f"/{eid}/locations/{lid}/posts", {"role_id": rid, "content": "<p>Ещё</p>"}).status_code == 403


# --- posts ------------------------------------------------------------------

def test_posting_from_own_role_only(api):
    eid, lid, rid = _story(api)
    mine = api.as_(MASTER).post(f"/{eid}/roles", {"user_id": MASTER, "name": "Лес"}).json()["id"]
    assert api.as_(MASTER).post(f"/{eid}/locations/{lid}/posts", {"role_id": rid, "content": "<p>x</p>"}).status_code == 403
    r = api.as_(MASTER).post(f"/{eid}/locations/{lid}/posts", {"role_id": mine, "content": "<p>Шумит</p>"})
    assert r.status_code == 200 and r.json()["role"]["name"] == "Лес" and r.json()["length"] == 5


def test_empty_post_refused(api):
    eid, lid, rid = _story(api)
    r = api.as_(PLAYER).post(f"/{eid}/locations/{lid}/posts", {"role_id": rid, "content": "<p>&nbsp; </p>"})
    assert r.status_code == 400


def test_edit_delete_and_like(api):
    eid, lid, rid = _story(api)
    pid = api.as_(PLAYER).post(f"/{eid}/locations/{lid}/posts", {"role_id": rid, "content": "<p>Раз</p>"}).json()["id"]
    assert api.as_(MASTER).put(f"/{eid}/posts/{pid}", {"content": "<p>Чужое</p>"}).status_code == 403
    r = api.as_(PLAYER).put(f"/{eid}/posts/{pid}", {"content": "<p>Два</p>"})
    assert r.status_code == 200 and r.json()["edited_at"]
    api.as_(STRANGER).post(f"/{eid}/posts/{pid}/like")
    api.post(f"/{eid}/posts/{pid}/like")
    post = api.get(f"/{eid}/locations/{lid}/posts").json()["posts"][0]
    assert post["likes_count"] == 1 and post["liked"]
    assert api.as_(STRANGER).delete(f"/{eid}/posts/{pid}").status_code == 403
    assert api.as_(MASTER).delete(f"/{eid}/posts/{pid}").status_code == 200
    assert api.get(f"/{eid}/locations/{lid}/posts").json()["posts"] == []


def test_posts_page_newest_first(api, monkeypatch):
    monkeypatch.setattr(episodes, "POSTS_PAGE", 2)
    eid, lid, rid = _story(api)
    ids = [api.as_(PLAYER).post(f"/{eid}/locations/{lid}/posts", {"role_id": rid, "content": f"<p>{i}</p>"}).json()["id"]
           for i in range(3)]
    first = api.get(f"/{eid}/locations/{lid}/posts").json()
    assert [p["id"] for p in first["posts"]] == ids[:0:-1] and first["has_more"]
    rest = api.get(f"/{eid}/locations/{lid}/posts?before_id={ids[1]}").json()
    assert [p["id"] for p in rest["posts"]] == [ids[0]] and not rest["has_more"]


def test_location_of_another_episode_is_not_found(api):
    eid, lid, _ = _story(api)
    other = api.as_(OWNER).post("", {"category": "world", "title": "B", "description": "d"}).json()["id"]
    assert api.get(f"/{other}/locations/{lid}").status_code == 404


# --- join requests ----------------------------------------------------------

def test_join_request_flow(api):
    eid, _, _ = _story(api)
    assert api.as_(STRANGER).post(f"/{eid}/requests", {"message": "Возьмите"}).status_code == 200
    assert api.post(f"/{eid}/requests", {}).status_code == 409
    assert api.get(f"/{eid}").json()["my_request"] is True
    reqs = api.as_(MASTER).get(f"/{eid}/requests").json()
    assert reqs[0]["username"] == "Stranger" and api.get(f"/{eid}").json()["requests_count"] == 1
    assert api.post(f"/{eid}/requests/{reqs[0]['id']}/accept").status_code == 200
    assert api.as_(STRANGER).get(f"/{eid}").json()["my_role"] == "player"
    assert (STRANGER, "Вас приняли в эпизод «Сказка»") in api.notifications


def test_no_requests_to_a_private_episode(api):
    eid, _, _ = _story(api, private=True)
    assert api.as_(STRANGER).post(f"/{eid}/requests", {}).status_code == 403


def test_user_search_is_for_managers(api):
    eid, _, _ = _story(api)
    assert api.as_(PLAYER).get(f"/{eid}/user-search?q=Str").status_code == 403
    assert [u["username"] for u in api.as_(OWNER).get(f"/{eid}/user-search?q=Str").json()] == ["Stranger"]
