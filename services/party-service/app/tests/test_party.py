"""party-service FEAT-144 Ф1 tests — create / invite / accept / guards / disband.

The `characters` table lives in another service's schema, so crud's character
lookups are monkeypatched to a small in-memory registry; the party tables run on
an in-memory SQLite DB. Auth is overridden to a fixed user id.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import crud
import main
from auth_http import UserRead, get_current_user_via_http
from database import get_db

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

# character_id -> {id, user_id, current_location_id, name, avatar}
CHARS: dict = {}


def _reg(char_id, user_id, loc=1, name="Char"):
    CHARS[char_id] = {
        "id": char_id, "user_id": user_id,
        "current_location_id": loc, "name": name, "avatar": None,
    }


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    models.Base.metadata.create_all(bind=_engine)
    monkeypatch.setattr(crud, "get_character_info", lambda db, cid: CHARS.get(cid))
    monkeypatch.setattr(
        crud, "get_characters_map",
        lambda db, ids: {cid: CHARS[cid] for cid in ids if cid in CHARS},
    )
    CHARS.clear()
    yield
    main.app.dependency_overrides.clear()
    models.Base.metadata.drop_all(bind=_engine)


def _client(user_id):
    def override_db():
        db = _TestSession()
        try:
            yield db
        finally:
            db.close()
    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[get_current_user_via_http] = \
        lambda: UserRead(id=user_id, username="t")
    return TestClient(main.app)


def test_create_party():
    _reg(1, user_id=10, loc=1)
    r = _client(10).post("/party/", json={"leader_character_id": 1, "name": "Отряд"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Отряд"
    assert data["leader_character_id"] == 1
    assert len(data["members"]) == 1 and data["members"][0]["is_leader"]


def test_create_requires_ownership():
    _reg(1, user_id=99, loc=1)  # owned by someone else
    r = _client(10).post("/party/", json={"leader_character_id": 1, "name": "X"})
    assert r.status_code == 403


def test_one_party_per_character():
    _reg(1, user_id=10, loc=1)
    c = _client(10)
    assert c.post("/party/", json={"leader_character_id": 1, "name": "A"}).status_code == 201
    assert c.post("/party/", json={"leader_character_id": 1, "name": "B"}).status_code == 409


def test_invite_and_accept_flow():
    _reg(1, user_id=10, loc=1)
    _reg(2, user_id=20, loc=1)
    lead = _client(10)
    pid = lead.post("/party/", json={"leader_character_id": 1, "name": "Отряд"}).json()["id"]

    inv = lead.post(f"/party/{pid}/invite", json={"character_id": 2})
    assert inv.status_code == 200, inv.text
    statuses = {m["character_id"]: m["status"] for m in inv.json()["members"]}
    assert statuses[2] == "invited"

    resp = _client(20).post(f"/party/{pid}/respond", json={"character_id": 2, "accept": True})
    assert resp.status_code == 200, resp.text
    assert {m["character_id"]: m["status"] for m in resp.json()["members"]}[2] == "accepted"

    mine = _client(20).get("/party/mine", params={"character_id": 2})
    assert mine.status_code == 200 and mine.json()["id"] == pid


def test_invite_only_same_location():
    _reg(1, user_id=10, loc=1)
    _reg(2, user_id=20, loc=2)  # elsewhere
    lead = _client(10)
    pid = lead.post("/party/", json={"leader_character_id": 1, "name": "Отряд"}).json()["id"]
    r = lead.post(f"/party/{pid}/invite", json={"character_id": 2})
    assert r.status_code == 400


def test_party_max_size():
    for cid in (1, 2, 3, 4, 5):
        _reg(cid, user_id=cid * 10, loc=1)
    lead = _client(10)
    pid = lead.post("/party/", json={"leader_character_id": 1, "name": "Отряд"}).json()["id"]
    # leader + 3 invites = 4 committed (full)
    for cid in (2, 3, 4):
        assert lead.post(f"/party/{pid}/invite", json={"character_id": cid}).status_code == 200
    assert lead.post(f"/party/{pid}/invite", json={"character_id": 5}).status_code == 400


def test_only_leader_invites():
    _reg(1, user_id=10, loc=1)
    _reg(2, user_id=20, loc=1)
    pid = _client(10).post("/party/", json={"leader_character_id": 1, "name": "Отряд"}).json()["id"]
    # user 20 (not the leader/owner) tries to invite via this party
    r = _client(20).post(f"/party/{pid}/invite", json={"character_id": 2})
    assert r.status_code == 403


def test_disband():
    _reg(1, user_id=10, loc=1)
    lead = _client(10)
    pid = lead.post("/party/", json={"leader_character_id": 1, "name": "Отряд"}).json()["id"]
    assert lead.delete(f"/party/{pid}").status_code == 200
    assert _client(10).get("/party/mine", params={"character_id": 1}).json() is None


def test_leader_leave_transfers_leadership():
    _reg(1, user_id=10, loc=1)
    _reg(2, user_id=20, loc=1)
    lead = _client(10)
    pid = lead.post("/party/", json={"leader_character_id": 1, "name": "Отряд"}).json()["id"]
    lead.post(f"/party/{pid}/invite", json={"character_id": 2})
    _client(20).post(f"/party/{pid}/respond", json={"character_id": 2, "accept": True})

    # Re-create the leader's client so the auth override points back to user 10
    # (dependency_overrides is shared on the app across TestClients).
    out = _client(10).post(f"/party/{pid}/leave", json={"character_id": 1})
    assert out.status_code == 200 and out.json()["new_leader"] == 2
    mine = _client(20).get("/party/mine", params={"character_id": 2}).json()
    assert mine["leader_character_id"] == 2
