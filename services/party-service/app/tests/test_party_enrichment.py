"""party-service FEAT-151 tests — MemberOut enrichment (level, class, HP/MP).

Unlike test_party.py (which stubs out the character lookups), this module
creates the shared `characters` / `classes` / `character_attributes` tables in
the SQLite test DB with raw DDL and runs crud's REAL raw-SQL helpers, so the
LEFT JOIN on `classes` and the batched `IN (...)` reads are actually exercised.
Auth is overridden to a fixed user id; the party tables come from models.Base.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
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

_SHARED_DDL = [
    "CREATE TABLE classes ("
    "  id_class INTEGER PRIMARY KEY, name VARCHAR(50) NOT NULL)",
    "CREATE TABLE characters ("
    "  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,"
    "  current_location_id INTEGER, name VARCHAR(50), avatar VARCHAR(255),"
    "  level INTEGER, id_class INTEGER, is_npc INTEGER DEFAULT 0)",
    "CREATE TABLE character_attributes ("
    "  character_id INTEGER PRIMARY KEY,"
    "  current_health INTEGER, max_health INTEGER,"
    "  current_mana INTEGER, max_mana INTEGER)",
]
_SHARED_DROP = [
    "DROP TABLE IF EXISTS character_attributes",
    "DROP TABLE IF EXISTS characters",
    "DROP TABLE IF EXISTS classes",
]


@pytest.fixture(autouse=True)
def _setup():
    models.Base.metadata.create_all(bind=_engine)
    with _engine.begin() as conn:
        for ddl in _SHARED_DDL:
            conn.execute(text(ddl))
    yield
    main.app.dependency_overrides.clear()
    with _engine.begin() as conn:
        for ddl in _SHARED_DROP:
            conn.execute(text(ddl))
    models.Base.metadata.drop_all(bind=_engine)


# ---------------------------------------------------------------------------
# Seed helpers (raw inserts into the shared tables)
# ---------------------------------------------------------------------------
def _add_class(class_id, name):
    with _engine.begin() as conn:
        conn.execute(
            text("INSERT INTO classes (id_class, name) VALUES (:i, :n)"),
            {"i": class_id, "n": name},
        )


def _add_char(char_id, user_id, loc=1, name="Char", level=1, id_class=None):
    with _engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO characters"
                " (id, user_id, current_location_id, name, avatar, level, id_class, is_npc)"
                " VALUES (:i, :u, :loc, :n, NULL, :lvl, :cls, 0)"
            ),
            {"i": char_id, "u": user_id, "loc": loc, "n": name,
             "lvl": level, "cls": id_class},
        )


def _add_attrs(char_id, ch=100, mh=100, cm=50, mm=50):
    with _engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO character_attributes"
                " (character_id, current_health, max_health, current_mana, max_mana)"
                " VALUES (:i, :ch, :mh, :cm, :mm)"
            ),
            {"i": char_id, "ch": ch, "mh": mh, "cm": cm, "mm": mm},
        )


def _make_party(leader_id, member_ids=(), invited_ids=()):
    """Insert a party + members straight into the DB."""
    db = _TestSession()
    party = models.Party(name="Отряд", leader_character_id=leader_id)
    db.add(party)
    db.flush()
    db.add(models.PartyMember(
        party_id=party.id, character_id=leader_id, user_id=leader_id * 10,
        is_leader=True, status=models.MemberStatus.accepted,
    ))
    for mid in member_ids:
        db.add(models.PartyMember(
            party_id=party.id, character_id=mid, user_id=mid * 10,
            is_leader=False, status=models.MemberStatus.accepted,
        ))
    for mid in invited_ids:
        db.add(models.PartyMember(
            party_id=party.id, character_id=mid, user_id=mid * 10,
            is_leader=False, status=models.MemberStatus.invited,
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


def _members_by_id(party_json):
    return {m["character_id"]: m for m in party_json["members"]}


# ---------------------------------------------------------------------------
# Unit tests — real raw-SQL helpers
# ---------------------------------------------------------------------------
def test_get_characters_map_includes_level_and_class():
    _add_class(1, "Воин")
    _add_class(2, "Маг")
    _add_char(1, 10, name="Артур", level=7, id_class=1)
    _add_char(2, 20, name="Мира", level=4, id_class=2)
    db = _TestSession()
    m = crud.get_characters_map(db, [1, 2])
    db.close()
    assert m[1]["level"] == 7 and m[1]["class_name"] == "Воин"
    assert m[2]["level"] == 4 and m[2]["class_name"] == "Маг"
    assert m[1]["name"] == "Артур" and m[1]["user_id"] == 10


def test_get_character_info_unknown_class_is_null():
    _add_char(1, 10, level=3, id_class=None)          # class never chosen
    _add_char(2, 20, level=5, id_class=999)           # dangling class id
    db = _TestSession()
    assert crud.get_character_info(db, 1)["class_name"] is None
    assert crud.get_character_info(db, 2)["class_name"] is None
    db.close()


def test_get_attributes_map_batched_and_missing_rows():
    _add_attrs(1, ch=260, mh=300, cm=40, mm=90)
    # char 2 has NO attributes row
    db = _TestSession()
    m = crud.get_attributes_map(db, [1, 2])
    db.close()
    assert m[1] == {
        "current_health": 260, "max_health": 300,
        "current_mana": 40, "max_mana": 90,
    }
    assert 2 not in m


def test_get_attributes_map_empty_ids():
    db = _TestSession()
    assert crud.get_attributes_map(db, []) == {}
    db.close()


# ---------------------------------------------------------------------------
# Endpoint tests — GET /party/mine and friends (real SQL end-to-end)
# ---------------------------------------------------------------------------
def test_mine_members_fully_enriched():
    _add_class(1, "Воин")
    _add_class(2, "Маг")
    _add_char(1, 10, name="Артур", level=7, id_class=1)
    _add_char(2, 20, name="Мира", level=4, id_class=2)
    _add_attrs(1, ch=260, mh=300, cm=40, mm=90)
    _add_attrs(2, ch=110, mh=140, cm=95, mm=120)
    _make_party(1, member_ids=[], invited_ids=[2])

    r = _client(10).get("/party/mine", params={"character_id": 1})
    assert r.status_code == 200, r.text
    members = _members_by_id(r.json())
    leader = members[1]
    assert leader["level"] == 7
    assert leader["class_name"] == "Воин"
    assert leader["current_health"] == 260 and leader["max_health"] == 300
    assert leader["current_mana"] == 40 and leader["max_mana"] == 90
    # invited (not yet accepted) member is enriched too — §3.1.1 example
    invited = members[2]
    assert invited["status"] == "invited"
    assert invited["level"] == 4 and invited["class_name"] == "Маг"
    assert invited["current_health"] == 110 and invited["max_mana"] == 120


def test_mine_missing_attributes_row_gives_nulls_no_500():
    _add_class(1, "Воин")
    _add_char(1, 10, name="Артур", level=7, id_class=1)
    _add_char(2, 20, name="Мира", level=4, id_class=1)
    _add_attrs(1)
    # char 2 has NO character_attributes row (created only on approval)
    _make_party(1, member_ids=[2])

    r = _client(10).get("/party/mine", params={"character_id": 1})
    assert r.status_code == 200, r.text
    m2 = _members_by_id(r.json())[2]
    assert m2["current_health"] is None
    assert m2["max_health"] is None
    assert m2["current_mana"] is None
    assert m2["max_mana"] is None
    # non-attribute enrichment still present
    assert m2["level"] == 4 and m2["class_name"] == "Воин"


def test_mine_unknown_class_gives_null_class_name():
    _add_char(1, 10, name="Артур", level=7, id_class=None)
    _add_attrs(1)
    _make_party(1)

    r = _client(10).get("/party/mine", params={"character_id": 1})
    assert r.status_code == 200, r.text
    m1 = _members_by_id(r.json())[1]
    assert m1["class_name"] is None
    assert m1["level"] == 7  # level independent of class


def test_create_party_response_enriched():
    _add_class(1, "Разбойник")
    _add_char(1, 10, name="Тень", level=9, id_class=1)
    _add_attrs(1, ch=180, mh=200, cm=30, mm=60)

    r = _client(10).post("/party/", json={"leader_character_id": 1, "name": "Отряд"})
    assert r.status_code == 201, r.text
    m1 = _members_by_id(r.json())[1]
    assert m1["level"] == 9 and m1["class_name"] == "Разбойник"
    assert m1["current_health"] == 180 and m1["max_health"] == 200
    assert m1["current_mana"] == 30 and m1["max_mana"] == 60


def test_mine_batched_queries_once_per_request(monkeypatch):
    """build_party_out must stay O(1): one characters read + one attributes
    read for the whole roster, never per member."""
    _add_class(1, "Воин")
    for cid in (1, 2, 3, 4):
        _add_char(cid, cid * 10, name=f"C{cid}", level=cid, id_class=1)
        _add_attrs(cid)
    _make_party(1, member_ids=[2, 3, 4])

    calls = {"chars": 0, "attrs": 0}
    real_chars, real_attrs = crud.get_characters_map, crud.get_attributes_map

    def counting_chars(db, ids):
        calls["chars"] += 1
        return real_chars(db, ids)

    def counting_attrs(db, ids):
        calls["attrs"] += 1
        return real_attrs(db, ids)

    monkeypatch.setattr(crud, "get_characters_map", counting_chars)
    monkeypatch.setattr(crud, "get_attributes_map", counting_attrs)

    r = _client(10).get("/party/mine", params={"character_id": 1})
    assert r.status_code == 200, r.text
    assert len(r.json()["members"]) == 4
    assert calls == {"chars": 1, "attrs": 1}


def test_invites_list_shape_unchanged():
    """FEAT-151 must not touch the incoming-invites payload."""
    _add_class(1, "Воин")
    _add_char(1, 10, name="Лидер", level=7, id_class=1)
    _add_char(2, 20, name="Гость", level=4, id_class=1)
    _add_attrs(1)
    _add_attrs(2)
    _make_party(1, invited_ids=[2])

    r = _client(20).get("/party/invites/incoming", params={"character_id": 2})
    assert r.status_code == 200, r.text
    invites = r.json()
    assert len(invites) == 1
    assert set(invites[0].keys()) == {
        "party_id", "party_name", "party_avatar",
        "leader_character_id", "leader_name",
    }
    assert invites[0]["leader_name"] == "Лидер"
