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
# recorded (character_id, amount) passive-XP awards during xp-bonus tests
AWARDS: list = []


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
    monkeypatch.setattr(main, "_award_passive_xp", lambda cid, amt: AWARDS.append((cid, amt)))
    CHARS.clear()
    AWARDS.clear()
    yield
    main.app.dependency_overrides.clear()
    models.Base.metadata.drop_all(bind=_engine)


def _make_party(leader_id, accepted_member_ids):
    """Insert a party + accepted members straight into the DB for XP tests."""
    db = _TestSession()
    party = models.Party(name="Отряд", leader_character_id=leader_id)
    db.add(party)
    db.flush()
    db.add(models.PartyMember(
        party_id=party.id, character_id=leader_id, user_id=leader_id * 10,
        is_leader=True, status=models.MemberStatus.accepted,
    ))
    for mid in accepted_member_ids:
        db.add(models.PartyMember(
            party_id=party.id, character_id=mid, user_id=mid * 10,
            is_leader=False, status=models.MemberStatus.accepted,
        ))
    db.commit()
    pid = party.id
    db.close()
    return pid


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


# ---------------------------------------------------------------------------
# XP bonus (FEAT-144 Ф2)
# ---------------------------------------------------------------------------

def _xp(character_id, base_xp, source, location_id, participants):
    return _client(character_id).post("/party/internal/xp-bonus", json={
        "character_id": character_id, "base_xp": base_xp, "source": source,
        "location_id": location_id, "participant_character_ids": participants,
    })


def test_xp_bonus_combat_self_and_trickle():
    _reg(1, 10, loc=1); _reg(2, 20, loc=1); _reg(3, 30, loc=2)  # char3 elsewhere
    _make_party(1, [2, 3])
    d = _xp(1, 100, "combat", 1, [1]).json()
    assert d["applied"] and d["self_bonus"] == 10
    # actor self-bonus + trickle to green squadmate 2; red squadmate 3 gets nothing
    assert set(AWARDS) == {(1, 10), (2, 10)}


def test_xp_bonus_post_no_trickle():
    _reg(1, 10, loc=1); _reg(2, 20, loc=1)
    _make_party(1, [2])
    assert _xp(1, 100, "post", 1, [1]).json()["applied"]
    assert AWARDS == [(1, 10)]  # only the poster's self-bonus, no trickle


def test_xp_bonus_alone_no_bonus():
    _reg(1, 10, loc=1); _reg(2, 20, loc=2)  # squadmate not co-located
    _make_party(1, [2])
    assert _xp(1, 100, "combat", 1, [1]).json()["applied"] is False
    assert AWARDS == []


def test_xp_bonus_group_excludes_participants():
    _reg(1, 10, loc=1); _reg(2, 20, loc=1)
    _make_party(1, [2])
    assert _xp(1, 100, "combat", 1, [1, 2]).json()["applied"]
    assert AWARDS == [(1, 10)]  # char2 earned base in the group fight → no trickle


def test_xp_bonus_no_party():
    _reg(1, 10, loc=1)
    assert _xp(1, 100, "combat", 1, [1]).json()["applied"] is False
    assert AWARDS == []
