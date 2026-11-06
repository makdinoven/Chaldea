"""FEAT-207 (task 11): closed faction territories in locations-service.

Sync tests (asyncio.run wrapper, no pytest-asyncio needed):

* ``faction_read.access_marks`` / ``location_access`` on a real aiosqlite file DB: public labels (secret faction never
  named), viewer-aware marks (member / rank / left member / secret member), hidden + deleted factions open, missing
  tables -> no marks;
* ``faction_read.access_decision`` parity table with character-service ``faction_core.access_decision`` (same texts);
* ``faction_read.owned_character``: own character only, foreign / missing / broken session -> None;
* routes: ``move_and_post`` and ``quick_move`` refuse with 403 BEFORE ``crud.create_post``; a 409 of character-service
  is still passed through; ``client/details`` passes the viewer only when the user owns ``character_id``;
* ``get_client_location_details`` neighbour fields and ``_update_character_location`` 409 pass-through.
"""

import asyncio
import inspect
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
import faction_read  # noqa: E402
import main  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from database import get_db  # noqa: E402

CHAR, OTHER_CHAR, USER, OTHER_USER = 100, 101, 5, 6
F_ORDER, F_SHADOW, F_HIDDEN, F_DELETED = 1, 2, 3, 99
R_NOVICE, R_KNIGHT = 11, 12
L_ORDER, L_ORDER_RANK, L_SHADOW, L_HIDDEN, L_DELETED, L_FREE = 201, 202, 203, 204, 205, 206

DDL = [
    "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER)",
    "CREATE TABLE factions (id INTEGER PRIMARY KEY, name VARCHAR(100), is_secret INTEGER NOT NULL DEFAULT 0, "
    "is_active INTEGER NOT NULL DEFAULT 1)",
    "CREATE TABLE faction_ranks (id INTEGER PRIMARY KEY, faction_id INTEGER, name VARCHAR(100), sort_order INTEGER)",
    "CREATE TABLE faction_members (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, faction_id INTEGER, "
    "status VARCHAR(10), rank_id INTEGER NULL)",
    "CREATE TABLE faction_access_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, kind VARCHAR(10), target_id INTEGER, "
    "faction_id INTEGER, min_rank_id INTEGER NULL)",
]
SEED = [
    f"INSERT INTO characters (id, user_id) VALUES ({CHAR}, {USER}), ({OTHER_CHAR}, {OTHER_USER})",
    "INSERT INTO factions (id, name, is_secret, is_active) VALUES "
    "(1, 'Орден Зари', 0, 1), (2, 'Тени', 1, 1), (3, 'Забытые', 0, 0)",
    "INSERT INTO faction_ranks (id, faction_id, name, sort_order) VALUES (11, 1, 'Послушник', 1), (12, 1, 'Рыцарь', 2)",
    "INSERT INTO faction_access_rules (kind, target_id, faction_id, min_rank_id) VALUES "
    f"('location', {L_ORDER}, 1, NULL), ('location', {L_ORDER_RANK}, 1, 12), ('location', {L_SHADOW}, 2, NULL), "
    f"('location', {L_HIDDEN}, 3, NULL), ('location', {L_DELETED}, 99, NULL), ('dungeon', {L_FREE}, 1, NULL)",
]

ALL = [L_ORDER, L_ORDER_RANK, L_SHADOW, L_HIDDEN, L_DELETED, L_FREE]


class World:
    def __init__(self, path):
        self.path = path

    def sql(self, query, **params):
        eng = create_engine(f"sqlite:///{self.path}")
        with eng.begin() as conn:
            conn.execute(text(query), params)
        eng.dispose()

    def run(self, fn):
        async def go():
            engine = create_async_engine(f"sqlite+aiosqlite:///{self.path}", poolclass=NullPool)
            Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with Session() as s:
                    return await fn(s)
            finally:
                await engine.dispose()
        return asyncio.run(go())

    def join(self, faction_id, rank_id=None, status="active", cid=CHAR):
        self.sql("INSERT INTO faction_members (character_id, faction_id, status, rank_id) VALUES (:c, :f, :s, :r)",
                 c=cid, f=faction_id, s=status, r=rank_id)

    def marks(self, character_id=None, ids=ALL):
        return self.run(lambda s: faction_read.access_marks(s, faction_read.ACCESS_LOCATION, ids, character_id))


@pytest.fixture()
def fw(tmp_path):
    path = tmp_path / "fa.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        for q in DDL + SEED:
            conn.execute(text(q))
    eng.dispose()
    return World(path)


@pytest.fixture()
def empty_db(tmp_path):
    path = tmp_path / "empty.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text(DDL[0]))
        conn.execute(text(SEED[0]))
    eng.dispose()
    return World(path)


# ===========================================================================
# 1. access_marks / location_access
# ===========================================================================

class TestPublicMarks:
    def test_public_labels_without_viewer(self, fw):
        m = fw.marks()
        assert set(m) == {L_ORDER, L_ORDER_RANK, L_SHADOW}  # hidden / deleted faction / other kind: open
        assert m[L_ORDER].label == "Закрыто: Орден Зари" and m[L_ORDER].allowed is None
        assert m[L_ORDER_RANK].label == "Закрыто: Орден Зари" and m[L_ORDER_RANK].allowed is None
        assert m[L_SHADOW].label == "Закрыто" and m[L_SHADOW].allowed is None

    def test_secret_faction_never_named_to_non_member(self, fw):
        for m in (fw.marks(), fw.marks(CHAR)):
            assert "Тени" not in (m[L_SHADOW].label or "")
            assert "Тени" not in (m[L_SHADOW].refusal or "")

    def test_no_targets_reads_nothing(self, fw):
        assert fw.marks(CHAR, ids=[]) == {}

    def test_target_without_rule_has_no_mark(self, fw):
        assert fw.marks(CHAR, ids=[L_FREE, 999]) == {}


class TestViewerMarks:
    def test_non_member(self, fw):
        m = fw.marks(CHAR)
        assert (m[L_ORDER].allowed, m[L_ORDER].label, m[L_ORDER].refusal) == (
            False, "Закрыто: Орден Зари", "Вход только для членов фракции «Орден Зари»")
        assert (m[L_SHADOW].allowed, m[L_SHADOW].label, m[L_SHADOW].refusal) == (
            False, "Закрыто", "Сюда вас не пускают")

    def test_member_without_needed_rank(self, fw):
        fw.join(F_ORDER, R_NOVICE)
        m = fw.marks(CHAR)
        assert m[L_ORDER].allowed is True and m[L_ORDER].label == "Территория фракции «Орден Зари»"
        assert m[L_ORDER_RANK].allowed is False
        assert m[L_ORDER_RANK].label == "Закрыто: нужно звание «Рыцарь» во фракции «Орден Зари»"
        assert m[L_ORDER_RANK].refusal == "Нужно звание «Рыцарь» во фракции «Орден Зари»"

    def test_member_without_any_rank_is_refused_on_rank_gate(self, fw):
        fw.join(F_ORDER, None)
        m = fw.marks(CHAR)
        assert m[L_ORDER].allowed is True
        assert m[L_ORDER_RANK].allowed is False

    def test_member_with_needed_rank(self, fw):
        fw.join(F_ORDER, R_KNIGHT)
        m = fw.marks(CHAR)
        assert m[L_ORDER_RANK].allowed is True and m[L_ORDER_RANK].refusal is None

    def test_left_member_is_a_stranger(self, fw):
        fw.join(F_ORDER, R_KNIGHT, status="left")
        assert fw.marks(CHAR)[L_ORDER].allowed is False

    def test_secret_member_sees_the_name(self, fw):
        fw.join(F_SHADOW)
        m = fw.marks(CHAR)
        assert m[L_SHADOW].allowed is True and m[L_SHADOW].label == "Территория фракции «Тени»"

    def test_membership_of_another_character_does_not_count(self, fw):
        fw.join(F_ORDER, R_KNIGHT, cid=OTHER_CHAR)
        assert fw.marks(CHAR)[L_ORDER].allowed is False


class TestLocationAccess:
    def test_refusal_text_for_stranger(self, fw):
        assert fw.run(lambda s: faction_read.location_access(s, CHAR, L_ORDER)) == \
            "Вход только для членов фракции «Орден Зари»"
        assert fw.run(lambda s: faction_read.location_access(s, CHAR, L_SHADOW)) == "Сюда вас не пускают"

    def test_member_and_open_locations_pass(self, fw):
        fw.join(F_ORDER, R_NOVICE)
        for loc in (L_ORDER, L_HIDDEN, L_DELETED, L_FREE, 999):
            assert fw.run(lambda s, loc=loc: faction_read.location_access(s, CHAR, loc)) is None

    def test_missing_tables_mean_no_marks_and_no_refusal(self, empty_db):
        assert empty_db.marks(CHAR) == {}
        assert empty_db.marks() == {}
        assert empty_db.run(lambda s: faction_read.location_access(s, CHAR, L_ORDER)) is None

    def test_broken_session_never_raises(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("boom"))
        assert asyncio.run(faction_read.access_marks(session, "location", [1], CHAR)) == {}
        assert asyncio.run(faction_read.location_access(session, CHAR, 1)) is None


# ===========================================================================
# 2. Parity with character-service faction_core.access_decision (same texts as task 9's table)
# ===========================================================================

KNIGHT = faction_read.RankInfo(R_KNIGHT, F_ORDER, "Рыцарь", 2)

PARITY = [
    # (name, secret, rank, viewer_known, is_member, held_order) -> (label, allowed, refusal)
    (("Орден", False, None, False, False, None), ("Закрыто: Орден", None, None)),
    (("Тени", True, None, False, False, None), ("Закрыто", None, None)),
    (("Орден", False, None, True, False, None), ("Закрыто: Орден", False, "Вход только для членов фракции «Орден»")),
    (("Тени", True, None, True, False, None), ("Закрыто", False, "Сюда вас не пускают")),
    (("Орден", False, None, True, True, None), ("Территория фракции «Орден»", True, None)),
    (("Тени", True, None, True, True, 1), ("Территория фракции «Тени»", True, None)),
    (("Орден", False, KNIGHT, True, True, 2), ("Территория фракции «Орден»", True, None)),
    (("Орден", False, KNIGHT, True, True, 3), ("Территория фракции «Орден»", True, None)),
    (("Орден", False, KNIGHT, True, True, 1),
     ("Закрыто: нужно звание «Рыцарь» во фракции «Орден»", False, "Нужно звание «Рыцарь» во фракции «Орден»")),
    (("Орден", False, KNIGHT, True, True, None),
     ("Закрыто: нужно звание «Рыцарь» во фракции «Орден»", False, "Нужно звание «Рыцарь» во фракции «Орден»")),
]


@pytest.mark.parametrize("args,expected", PARITY)
def test_access_decision_parity(args, expected):
    name, secret, rank, known, member, held = args
    mark = faction_read.access_decision(name, secret, rank, viewer_known=known, is_member=member, held_order=held)
    assert (mark.label, mark.allowed, mark.refusal) == expected


# ===========================================================================
# 3. owned_character
# ===========================================================================

class TestOwnedCharacter:
    def test_own_character(self, fw):
        assert fw.run(lambda s: faction_read.owned_character(s, CHAR, USER)) == CHAR

    def test_foreign_character(self, fw):
        assert fw.run(lambda s: faction_read.owned_character(s, OTHER_CHAR, USER)) is None

    def test_missing_character_or_ids(self, fw):
        assert fw.run(lambda s: faction_read.owned_character(s, 9999, USER)) is None
        assert fw.run(lambda s: faction_read.owned_character(s, None, USER)) is None
        assert fw.run(lambda s: faction_read.owned_character(s, CHAR, None)) is None

    def test_broken_session_gives_public(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("boom"))
        assert asyncio.run(faction_read.owned_character(session, CHAR, USER)) is None


# ===========================================================================
# 4. Routes: move pre-check before the post, 409 pass-through, client details viewer
# ===========================================================================

CUR, DEST = 1, L_ORDER
PLAYER = UserRead(id=USER, username="p", role="user", permissions=[])
MOVE_TEXT = "Путник идёт к воротам ордена и стучит в тяжёлую дверь. " * 6
REFUSAL = "Вход только для членов фракции «Орден Зари»"


def _res(first=None):
    r = MagicMock()
    r.scalars.return_value.first.return_value = first
    r.scalars.return_value.all.return_value = []
    r.fetchall.return_value = []
    r.first.return_value = None
    return r


def _session(neighbor=SimpleNamespace(energy_cost=0), dest=None):
    session = AsyncMock()

    async def execute(query, params=None):
        q = str(query)
        if "LocationNeighbors" in q:
            return _res(neighbor)
        if '"Locations"' in q:
            return _res(dest)
        return _res()

    session.execute = AsyncMock(side_effect=execute)
    return session


def _http(current=CUR):
    async def get(url, *a, **kw):
        resp = MagicMock(status_code=200)
        if "/profile" in url:
            resp.json.return_value = {"current_location_id": current, "travel_cooldown_until": None,
                                      "character_name": "Путник"}
        else:
            resp.json.return_value = {"current_stamina": 100}
        return resp

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get)
    client.post = AsyncMock(return_value=MagicMock(status_code=200))
    return client


@pytest.fixture(autouse=True)
def _clean_overrides():
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


def _drive(path, payload, session, refusal=None, current=CUR, update_exc=None):
    async def override():
        yield session

    main.app.dependency_overrides[get_db] = override
    main.app.dependency_overrides[get_current_user_via_http] = lambda: PLAYER
    access = AsyncMock(return_value=refusal)
    update = AsyncMock(return_value=main.NO_LAW_ARRIVAL, side_effect=update_exc)
    create_post = AsyncMock(return_value=SimpleNamespace(id=555, character_id=CHAR, location_id=DEST, content="x",
                                                         created_at=datetime(2026, 11, 6, 12, 0)))
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
            patch("main.check_not_locked_for_post", new_callable=AsyncMock, return_value=main.POST_FREE), \
            patch("main.check_not_locked_for_move", new_callable=AsyncMock), \
            patch("main.check_not_in_battle", new_callable=AsyncMock), \
            patch("main.check_not_gathering", new_callable=AsyncMock), \
            patch("main.faction_read.location_access", access), \
            patch("main._update_character_location", update), \
            patch("main._try_spawn_mob", new_callable=AsyncMock), \
            patch("main._track_cumulative_stats", new_callable=AsyncMock), \
            patch("main._auto_progress_quest", new_callable=AsyncMock), \
            patch("main._count_unique_locations", new_callable=AsyncMock, return_value=0), \
            patch("crud.get_favorite_user_ids", new_callable=AsyncMock, return_value=[]), \
            patch("crud.create_post", create_post), \
            patch("crud.archive_draft_on_post", new_callable=AsyncMock), \
            patch("crud.award_post_xp_and_log", new_callable=AsyncMock), \
            patch("crud.expire_action_gates", new_callable=AsyncMock), \
            patch("crud.expire_gate_requests", new_callable=AsyncMock), \
            patch("httpx.AsyncClient", return_value=_http(current)):
        r = TestClient(main.app).post(path, json=payload)
    return r, access, create_post, update


MOVE = (f"/locations/{DEST}/move_and_post", {"character_id": CHAR, "content": MOVE_TEXT})
QUICK = (f"/locations/{DEST}/quick_move", {"character_id": CHAR})
DEST_LOC = SimpleNamespace(id=DEST, name="Цитадель ордена", no_quick_move=False)


class TestMovePreCheck:
    @pytest.mark.parametrize("route", [MOVE, QUICK], ids=["move_and_post", "quick_move"])
    def test_refused_move_is_403_and_creates_no_post(self, route):
        r, access, create_post, update = _drive(*route, _session(dest=DEST_LOC), refusal=REFUSAL)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == REFUSAL
        assert access.await_args.args[1:] == (CHAR, DEST)
        create_post.assert_not_called()
        update.assert_not_called()

    @pytest.mark.parametrize("route", [MOVE, QUICK], ids=["move_and_post", "quick_move"])
    def test_allowed_move_goes_on(self, route):
        r, access, create_post, update = _drive(*route, _session(dest=DEST_LOC), refusal=None)
        assert r.status_code == 200, r.text
        create_post.assert_awaited_once()
        update.assert_awaited_once()

    @pytest.mark.parametrize("route", [MOVE, QUICK], ids=["move_and_post", "quick_move"])
    def test_character_service_409_still_passed_through(self, route):
        exc = HTTPException(status_code=409, detail=REFUSAL)
        r, _, create_post, _ = _drive(*route, _session(dest=DEST_LOC), refusal=None, update_exc=exc)
        assert r.status_code == 409 and r.json()["detail"] == REFUSAL

    def test_post_in_place_skips_the_pre_check(self):
        r, access, create_post, _ = _drive(*MOVE, _session(), refusal=REFUSAL, current=DEST)
        assert r.status_code == 200, r.text
        access.assert_not_called()
        create_post.assert_awaited_once()

    def test_not_adjacent_is_checked_before_faction(self):
        r, access, create_post, _ = _drive(*MOVE, _session(neighbor=None), refusal=REFUSAL)
        assert r.status_code == 400
        access.assert_not_called()
        create_post.assert_not_called()


class TestUpdateLocation409:
    def test_faction_refusal_detail_reaches_the_player(self):
        resp = MagicMock(status_code=409)
        resp.json.return_value = {"detail": "Сюда вас не пускают"}
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.put = AsyncMock(return_value=resp)
        with patch("httpx.AsyncClient", return_value=client):
            with pytest.raises(HTTPException) as e:
                asyncio.run(main._update_character_location(CHAR, DEST, "move"))
        assert e.value.status_code == 409 and e.value.detail == "Сюда вас не пускают"


class TestClientDetailsViewer:
    def _get(self, url, owner_row, user=PLAYER):
        session = AsyncMock()
        res = MagicMock()
        res.fetchall.return_value = [owner_row] if owner_row is not None else []
        session.execute = AsyncMock(return_value=res)

        async def override():
            yield session

        main.app.dependency_overrides[get_db] = override
        main.app.dependency_overrides[main.get_optional_user] = lambda: user
        details = AsyncMock(return_value=None)
        with patch("crud.finalize_due_sessions", new_callable=AsyncMock), \
                patch("crud.get_client_location_details", details):
            r = TestClient(main.app).get(url)
        return r, details

    def test_own_character_is_the_viewer(self):
        r, details = self._get(f"/locations/{CUR}/client/details?character_id={CHAR}", (USER,))
        assert r.status_code == 404  # details mocked to None; only the call matters
        assert details.await_args.kwargs == {"user_id": USER, "viewer_character_id": CHAR}

    def test_foreign_character_gets_public_marks(self):
        _, details = self._get(f"/locations/{CUR}/client/details?character_id={OTHER_CHAR}", (OTHER_USER,))
        assert details.await_args.kwargs["viewer_character_id"] is None

    def test_anonymous_gets_public_marks(self):
        _, details = self._get(f"/locations/{CUR}/client/details?character_id={CHAR}", (USER,), user=None)
        assert details.await_args.kwargs == {"user_id": None, "viewer_character_id": None}


class TestNeighbourFields:
    def test_neighbours_get_access_fields(self):
        loc = SimpleNamespace(id=CUR, district_id=None, region_id=None)
        n1, n2 = SimpleNamespace(neighbor_id=L_ORDER, energy_cost=1), SimpleNamespace(neighbor_id=L_FREE, energy_cost=2)
        locs = {L_ORDER: SimpleNamespace(id=L_ORDER, name="A", recommended_level=1, image_url=None),
                L_FREE: SimpleNamespace(id=L_FREE, name="B", recommended_level=1, image_url=None)}
        calls = {"n": 0}

        async def execute(query, params=None):
            calls["n"] += 1
            q = str(query)
            r = MagicMock()
            if "LocationNeighbors" in q:
                r.scalars.return_value.all.return_value = [n1, n2]
            elif calls["n"] == 1:
                r.scalars.return_value.first.return_value = loc
            else:
                lid = L_ORDER if calls["n"] == 3 else L_FREE
                r.scalars.return_value.first.return_value = locs[lid]
            return r

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=execute)
        marks = AsyncMock(return_value={L_ORDER: faction_read.AccessMark("Закрыто: Орден Зари", False, REFUSAL)})
        captured = {}

        async def stop(*a, **kw):  # stop right after the neighbours are built; grab them from the caller frame
            captured["neighbors"] = inspect.currentframe().f_back.f_locals["detailed_neighbors"]
            raise RuntimeError("stop")

        with patch("crud.faction_read.access_marks", marks), patch("crud.get_players_in_location", stop):
            with pytest.raises(RuntimeError):
                asyncio.run(crud.get_client_location_details(session, CUR, user_id=USER,
                                                              viewer_character_id=CHAR))
        args = marks.await_args.args
        assert args[1] == faction_read.ACCESS_LOCATION and sorted(args[2]) == [L_ORDER, L_FREE] and args[3] == CHAR
        by_id = {d["id"]: d for d in captured["neighbors"]}
        assert (by_id[L_ORDER]["access_label"], by_id[L_ORDER]["access_allowed"]) == ("Закрыто: Орден Зари", False)
        assert (by_id[L_FREE]["access_label"], by_id[L_FREE]["access_allowed"]) == (None, None)
