"""FEAT-198 QA (task 10): law in locations-service.

Covers:
  * the activity-lock copy: reason priority (jail > law_encounter > unconscious > dungeon >
    asleep > reading), relative «— осталось …» messages, the unknown-column fallback;
  * the shared upper part of the 4 activity_lock copies is identical (runs when the whole
    repository is checked out, e.g. in CI; skipped inside a single-service container);
  * the jail posting exception: a jailed character may post in the location they are in,
    any other location -> 409, the guard-encounter lock -> 409 (POST /posts/ and move_and_post);
  * update_location: 409 pass-through with its detail, `source`, `law_encounter` in the
    move / quick-move responses;
  * region jail_location_id validation (this region ok, another region / unknown -> 400);
  * dialogue choose with character_id: ownership + lock.

The lock tests run the real shared-DB query against a mocked session.
"""

import itertools
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import activity_lock
import crud
import main
import schemas
from auth_http import get_current_user_via_http, UserRead
from database import get_db

pytestmark = pytest.mark.real_activity_lock

USER = UserRead(id=10, username="prisoner", role="user", permissions=[])
CID = 1
JAIL = 100
OTHER = 200
SOON = datetime.utcnow() + timedelta(hours=5)
PAST = datetime.utcnow() - timedelta(minutes=1)
ENCOUNTER = {"id": 12, "region_id": 3, "status": "pending", "options": ["fine", "fight"]}


def _res(row=None, first=None):
    r = MagicMock()
    r.fetchone.return_value = row
    r.first.return_value = row
    r.fetchall.return_value = [row] if row is not None else []
    r.scalars.return_value.first.return_value = first
    r.scalars.return_value.all.return_value = []
    r.scalar.return_value = 0
    return r


def _session(jailed=None, encounter=None, dungeon=None, unconscious=None, location=JAIL, neighbor=None):
    """AsyncSession mock: the lock row, the character's location, everything else empty."""
    session = AsyncMock()

    async def execute(query, params=None):
        q = str(query)
        if "jailed_until, law_encounter_id FROM characters" in q:
            return _res((dungeon, unconscious, None, None, jailed, encounter))
        if "SELECT current_location_id FROM characters" in q:
            return _res((location,))
        if '"LocationNeighbors"' in q or "LocationNeighbors" in q:
            return _res(first=neighbor)
        return _res()

    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


def _client(session, user=USER):
    async def override():
        yield session

    main.app.dependency_overrides[get_db] = override
    main.app.dependency_overrides[get_current_user_via_http] = lambda: user
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean():
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


# ===========================================================================
# 1. activity_lock copy
# ===========================================================================

REASONS = ["jail", "law_encounter", "unconscious", "dungeon", "asleep", "reading"]


@pytest.mark.parametrize(
    "present",
    [set(c) for n in range(len(REASONS) + 1) for c in itertools.combinations(REASONS, n)],
    ids=lambda s: "+".join(sorted(s)) or "free",
)
def test_reason_priority_matrix(present):
    later = datetime.utcnow() + timedelta(hours=3)
    lock = activity_lock.compute_lock(
        7 if "dungeon" in present else None,
        later if "unconscious" in present else None,
        asleep_since=datetime.utcnow() if "asleep" in present else None,
        reading_since=datetime.utcnow() if "reading" in present else None,
        jailed_until=later if "jail" in present else None,
        law_encounter_id=5 if "law_encounter" in present else None,
    )
    expected = next((r for r in REASONS if r in present), None)
    assert lock["reason"] == expected
    assert lock["locked"] is (expected is not None)
    assert lock["law_encounter_id"] == (5 if expected == "law_encounter" else None)
    assert set(lock) == {"locked", "reason", "until", "dungeon_session_id", "law_encounter_id"}


def test_expired_jail_is_free():
    assert activity_lock.compute_lock(None, None, jailed_until=PAST)["locked"] is False


def test_lock_for_character_reads_the_law_attributes():
    c = SimpleNamespace(dungeon_session_id=None, unconscious_until=None, asleep_since=None,
                        reading_since=None, jailed_until=None, law_encounter_id=9)
    assert activity_lock.lock_for_character(c)["reason"] == "law_encounter"
    # an object without the new attributes (old mirror) stays free
    assert activity_lock.lock_for_character(SimpleNamespace())["locked"] is False


def test_relative_messages():
    jail = activity_lock.compute_lock(None, None, jailed_until=datetime.utcnow() + timedelta(hours=3, minutes=10, seconds=20))
    assert activity_lock.lock_message(jail) == "Персонаж в тюрьме — осталось 3 ч 11 мин"
    enc = activity_lock.compute_lock(None, None, law_encounter_id=1)
    assert activity_lock.lock_message(enc) == "Персонаж остановлен стражей — сначала нужно решить, как поступить"
    assert "МСК" not in activity_lock.lock_message(jail)


@pytest.mark.parametrize("delta,expected", [
    (timedelta(seconds=1), "1 мин"),
    (timedelta(minutes=60), "1 ч"),
    (timedelta(hours=1, minutes=1), "1 ч 1 мин"),
    (timedelta(days=2, hours=5), "2 д 5 ч"),
    (timedelta(days=7), "7 д"),
])
def test_format_remaining(delta, expected):
    now = datetime(2026, 11, 4, 12, 0, 0)
    assert activity_lock.format_remaining(now + delta, now) == expected


class TestSharedDbRead:
    @pytest.mark.asyncio
    async def test_unknown_column_falls_back(self):
        calls = []

        async def execute(query, params=None):
            calls.append(str(query))
            if "law_encounter_id" in str(query):
                raise RuntimeError("(1054, \"Unknown column 'law_encounter_id' in 'field list'\")")
            return _res((None, SOON, None, None))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute)
        lock = await activity_lock.get_activity_lock(db, CID)
        assert lock["reason"] == "unconscious"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_unrelated_error_propagates(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
        with pytest.raises(RuntimeError):
            await activity_lock.get_activity_lock(db, CID)

    @pytest.mark.asyncio
    async def test_check_raises_for_jail(self):
        with pytest.raises(HTTPException) as exc:
            await activity_lock.check_not_activity_locked(_session(jailed=SOON), CID)
        assert exc.value.status_code == 409
        assert exc.value.detail.startswith("Персонаж в тюрьме — осталось")


# --- the 4 copies share their upper part byte for byte ----------------------

_SERVICES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_CANONICAL = os.path.join(_SERVICES_DIR, "character-service", "app", "activity_lock.py")
_COPIES = [os.path.join(_SERVICES_DIR, s, "app", "activity_lock.py")
           for s in ("locations-service", "battle-service", "inventory-service")]
_SHARED_DB_MARKER = "\n# ---------------------------------------------------------------------------\n# Shared-DB read"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.mark.skipif(not os.path.exists(_CANONICAL), reason="needs the whole repository (CI checkout)")
@pytest.mark.parametrize("copy_path", _COPIES, ids=lambda p: p.split(os.sep)[-3])
def test_activity_lock_copies_share_the_canonical_upper_part(copy_path):
    canonical = _read(_CANONICAL).rstrip()
    copy = _read(copy_path)
    assert _SHARED_DB_MARKER in copy
    assert copy.split(_SHARED_DB_MARKER)[0].rstrip() == canonical


# ===========================================================================
# 2. The jail posting exception
# ===========================================================================

class TestCheckNotLockedForPost:
    @pytest.mark.asyncio
    async def test_jailed_in_current_location_is_allowed(self):
        assert await main.check_not_locked_for_post(_session(jailed=SOON, location=JAIL), CID, JAIL) is True

    @pytest.mark.asyncio
    async def test_jailed_elsewhere_is_refused(self):
        with pytest.raises(HTTPException) as exc:
            await main.check_not_locked_for_post(_session(jailed=SOON, location=JAIL), CID, OTHER)
        assert exc.value.status_code == 409
        assert exc.value.detail.startswith("Персонаж в тюрьме — осталось")

    @pytest.mark.asyncio
    async def test_jailed_without_location_is_refused(self):
        with pytest.raises(HTTPException) as exc:
            await main.check_not_locked_for_post(_session(jailed=SOON, location=None), CID, JAIL)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lock", [{"encounter": 4}, {"dungeon": 2}, {"unconscious": SOON}],
                             ids=["encounter", "dungeon", "unconscious"])
    async def test_other_locks_are_refused_even_in_place(self, lock):
        with pytest.raises(HTTPException) as exc:
            await main.check_not_locked_for_post(_session(location=JAIL, **lock), CID, JAIL)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_free_character_passes(self):
        assert await main.check_not_locked_for_post(_session(location=JAIL), CID, OTHER) is False

    @pytest.mark.asyncio
    async def test_expired_jail_passes(self):
        assert await main.check_not_locked_for_post(_session(jailed=PAST, location=JAIL), CID, OTHER) is False


class _PastTheLock(Exception):
    pass


def _create_post(session, location_id):
    """POST /locations/posts/ with every check after the lock stubbed; `crud.create_post`
    raises a sentinel 418 so reaching it proves the lock let the post through."""
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
            patch("main.check_not_in_battle", new_callable=AsyncMock), \
            patch("main.check_not_gathering", new_callable=AsyncMock), \
            patch("crud.create_post", new_callable=AsyncMock,
                  side_effect=HTTPException(status_code=418, detail="past the lock")):
        return _client(session).post("/locations/posts/", json={
            "character_id": CID, "location_id": location_id, "content": "Узник пишет на стене камеры. " * 15,
        })


class TestCreatePostInJail:
    def test_post_in_the_jail_is_allowed(self):
        r = _create_post(_session(jailed=SOON, location=JAIL), JAIL)
        assert r.status_code == 418, r.text

    def test_post_in_another_location_is_refused(self):
        r = _create_post(_session(jailed=SOON, location=JAIL), OTHER)
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Персонаж в тюрьме — осталось")

    def test_encounter_lock_refuses_the_post(self):
        r = _create_post(_session(encounter=7, location=JAIL), JAIL)
        assert r.status_code == 409
        assert r.json()["detail"] == "Персонаж остановлен стражей — сначала нужно решить, как поступить"


# --- move_and_post / quick_move flows -----------------------------------------

def _http(current_location=JAIL, stamina=50):
    async def get(url, *a, **kw):
        resp = MagicMock(status_code=200)
        if "/profile" in url:
            resp.json.return_value = {"current_location_id": current_location, "travel_cooldown_until": None,
                                      "character_name": "Узник"}
        else:
            resp.json.return_value = {"current_stamina": stamina}
        return resp

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get)
    client.post = AsyncMock(return_value=MagicMock(status_code=200))
    client.put = AsyncMock(side_effect=AssertionError("update_location must go through the helper"))
    return client


def _fake_post(location_id):
    return SimpleNamespace(id=555, character_id=CID, location_id=location_id, content="x",
                           created_at=datetime(2026, 11, 4, 12, 0))


def _drive(path, payload, session, dest, update_result=None, update_exc=None):
    """Run a move endpoint with the outside world mocked. Returns (response, update_mock, http)."""
    http = _http()
    update = AsyncMock(return_value=update_result, side_effect=update_exc)
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
            patch("main.check_not_in_battle", new_callable=AsyncMock), \
            patch("main.check_not_gathering", new_callable=AsyncMock), \
            patch("main._update_character_location", update), \
            patch("main._try_spawn_mob", new_callable=AsyncMock), \
            patch("main._track_cumulative_stats", new_callable=AsyncMock), \
            patch("main._auto_progress_quest", new_callable=AsyncMock), \
            patch("main._count_unique_locations", new_callable=AsyncMock, return_value=0), \
            patch("crud.create_post", new_callable=AsyncMock, return_value=_fake_post(dest)), \
            patch("crud.archive_draft_on_post", new_callable=AsyncMock), \
            patch("crud.award_post_xp_and_log", new_callable=AsyncMock), \
            patch("crud.expire_action_gates", new_callable=AsyncMock), \
            patch("crud.expire_gate_requests", new_callable=AsyncMock), \
            patch("httpx.AsyncClient", return_value=http):
        r = _client(session).post(path, json=payload)
    return r, update, http


MOVE_TEXT = "Персонаж осматривается по сторонам и идёт дальше. " * 8


class TestMoveAndPost:
    def test_jailed_post_in_place_skips_update_location(self):
        r, update, _ = _drive(f"/locations/{JAIL}/move_and_post", {"character_id": CID, "content": MOVE_TEXT},
                              _session(jailed=SOON, location=JAIL), JAIL)
        assert r.status_code == 200, r.text
        update.assert_not_called()
        assert r.json()["law_encounter"] is None

    def test_jailed_move_elsewhere_is_refused_before_anything(self):
        r, update, http = _drive(f"/locations/{OTHER}/move_and_post", {"character_id": CID, "content": MOVE_TEXT},
                                 _session(jailed=SOON, location=JAIL), OTHER)
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Персонаж в тюрьме — осталось")
        update.assert_not_called()
        http.get.assert_not_called()

    def test_encounter_lock_refuses_move(self):
        r, update, _ = _drive(f"/locations/{OTHER}/move_and_post", {"character_id": CID, "content": MOVE_TEXT},
                              _session(encounter=12, location=JAIL), OTHER)
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Персонаж остановлен стражей")
        update.assert_not_called()

    def test_move_returns_the_law_encounter(self):
        neighbor = SimpleNamespace(energy_cost=0)
        r, update, _ = _drive(f"/locations/{OTHER}/move_and_post", {"character_id": CID, "content": MOVE_TEXT},
                              _session(location=JAIL, neighbor=neighbor), OTHER, update_result=ENCOUNTER)
        assert r.status_code == 200, r.text
        assert update.await_args.args == (CID, OTHER, "move")
        body = r.json()
        assert body["law_encounter"] == ENCOUNTER
        assert body["id"] == 555 and body["location_id"] == OTHER

    def test_move_without_encounter_returns_null(self):
        neighbor = SimpleNamespace(energy_cost=0)
        r, _, _ = _drive(f"/locations/{OTHER}/move_and_post", {"character_id": CID, "content": MOVE_TEXT},
                         _session(location=JAIL, neighbor=neighbor), OTHER, update_result=None)
        assert r.status_code == 200, r.text
        assert r.json()["law_encounter"] is None

    def test_409_from_update_location_reaches_the_player(self):
        neighbor = SimpleNamespace(energy_cost=0)
        exc = HTTPException(status_code=409, detail="Персонаж остановлен стражей — сначала нужно решить, как поступить")
        r, _, _ = _drive(f"/locations/{OTHER}/move_and_post", {"character_id": CID, "content": MOVE_TEXT},
                         _session(location=JAIL, neighbor=neighbor), OTHER, update_exc=exc)
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Персонаж остановлен стражей")


class TestQuickMove:
    def test_quick_move_returns_the_law_encounter(self):
        neighbor = SimpleNamespace(energy_cost=0)
        dest = SimpleNamespace(id=OTHER, name="Застава", no_quick_move=False)
        session = _session(location=JAIL, neighbor=neighbor)
        base_execute = session.execute.side_effect

        async def execute(query, params=None):
            if '"Locations"' in str(query) and "LocationNeighbors" not in str(query):
                return _res(first=dest)
            return await base_execute(query, params)

        session.execute = AsyncMock(side_effect=execute)
        with patch("crud.get_favorite_user_ids", new_callable=AsyncMock, return_value=[]):
            r, update, _ = _drive(f"/locations/{OTHER}/quick_move", {"character_id": CID}, session, OTHER,
                                  update_result=ENCOUNTER)
        assert r.status_code == 200, r.text
        assert update.await_args.args == (CID, OTHER, "quick_move")
        assert r.json()["law_encounter"] == ENCOUNTER

    def test_jailed_quick_move_is_refused(self):
        r, update, _ = _drive(f"/locations/{OTHER}/quick_move", {"character_id": CID},
                              _session(jailed=SOON, location=JAIL), OTHER)
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Персонаж в тюрьме")
        update.assert_not_called()


# --- _update_character_location: the HTTP contract with character-service -----

def _put_client(status, body=None, json_error=False):
    resp = MagicMock(status_code=status)
    if json_error:
        resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = body if body is not None else {}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.put = AsyncMock(return_value=resp)
    return client


class TestUpdateCharacterLocation:
    @pytest.mark.asyncio
    async def test_sends_source_and_internal_token(self):
        client = _put_client(200, {"ok": True, "law_encounter": None})
        with patch("httpx.AsyncClient", return_value=client):
            assert await main._update_character_location(CID, OTHER, "quick_move") is None
        call = client.put.await_args
        assert call.args[0].endswith(f"/characters/internal/{CID}/update_location")
        assert call.kwargs["json"] == {"new_location_id": OTHER, "source": "quick_move"}
        assert "X-Internal-Token" in call.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_returns_the_encounter(self):
        with patch("httpx.AsyncClient", return_value=_put_client(200, {"law_encounter": ENCOUNTER})):
            assert await main._update_character_location(CID, OTHER, "move") == ENCOUNTER

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [{"law_encounter": "x"}, [], {"law_encounter": None}])
    async def test_non_dict_encounter_is_ignored(self, body):
        with patch("httpx.AsyncClient", return_value=_put_client(200, body)):
            assert await main._update_character_location(CID, OTHER, "move") is None

    @pytest.mark.asyncio
    async def test_409_detail_is_passed_through(self):
        with patch("httpx.AsyncClient", return_value=_put_client(409, {"detail": "Персонаж в тюрьме — осталось 2 ч"})):
            with pytest.raises(HTTPException) as exc:
                await main._update_character_location(CID, OTHER, "move")
        assert exc.value.status_code == 409
        assert exc.value.detail == "Персонаж в тюрьме — осталось 2 ч"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kw", [{"json_error": True}, {"body": {"detail": {"x": 1}}}, {"body": {}}],
                             ids=["not-json", "dict-detail", "no-detail"])
    async def test_409_without_text_detail_gets_the_generic_russian_message(self, kw):
        with patch("httpx.AsyncClient", return_value=_put_client(409, **kw)):
            with pytest.raises(HTTPException) as exc:
                await main._update_character_location(CID, OTHER, "move")
        assert exc.value.status_code == 409
        assert exc.value.detail == main.LOCATION_UPDATE_REFUSED

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 404, 500, 502])
    async def test_other_failures_stay_500(self, status):
        with patch("httpx.AsyncClient", return_value=_put_client(status, {"detail": "boom"})):
            with pytest.raises(HTTPException) as exc:
                await main._update_character_location(CID, OTHER, "move")
        assert exc.value.status_code == 500
        assert exc.value.detail == "Не удалось обновить локацию персонажа"


def test_post_response_shapes():
    post = _fake_post(OTHER)
    assert main._post_response(post, None) is post
    data = main._post_response(post, ENCOUNTER)
    assert data["law_encounter"] == ENCOUNTER and data["id"] == 555


# ===========================================================================
# 3. Region jail location
# ===========================================================================

def _region_session(region):
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = region
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    return session


class TestRegionJailLocation:
    @pytest.mark.asyncio
    async def test_location_of_this_region_is_saved(self):
        region = SimpleNamespace(id=3, jail_location_id=None)
        session = _region_session(region)
        with patch("econ_ledger.resolve_location", new_callable=AsyncMock, return_value=(3, 1)) as resolve:
            out = await crud.update_region(session, 3, schemas.RegionUpdate(jail_location_id=90))
        assert out.jail_location_id == 90
        resolve.assert_awaited_once()
        assert resolve.await_args.args[1] == 90
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("resolved", [(4, 1), (None, None)], ids=["other-region", "unknown-location"])
    async def test_location_outside_the_region_is_400(self, resolved):
        region = SimpleNamespace(id=3, jail_location_id=None)
        session = _region_session(region)
        with patch("econ_ledger.resolve_location", new_callable=AsyncMock, return_value=resolved):
            with pytest.raises(HTTPException) as exc:
                await crud.update_region(session, 3, schemas.RegionUpdate(jail_location_id=91))
        assert exc.value.status_code == 400
        assert exc.value.detail == "Локация тюрьмы должна находиться в этом крае"
        assert region.jail_location_id is None
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_null_clears_the_jail_without_validation(self):
        region = SimpleNamespace(id=3, jail_location_id=90)
        session = _region_session(region)
        with patch("econ_ledger.resolve_location", new_callable=AsyncMock) as resolve:
            await crud.update_region(session, 3, schemas.RegionUpdate(jail_location_id=None))
        resolve.assert_not_awaited()
        assert region.jail_location_id is None

    @pytest.mark.asyncio
    async def test_other_fields_do_not_touch_the_jail(self):
        region = SimpleNamespace(id=3, jail_location_id=90, name="Старое")
        session = _region_session(region)
        with patch("econ_ledger.resolve_location", new_callable=AsyncMock) as resolve:
            await crud.update_region(session, 3, schemas.RegionUpdate(name="Новое"))
        resolve.assert_not_awaited()
        assert region.jail_location_id == 90

    def test_schemas_carry_the_field(self):
        for cls in (schemas.RegionBase, schemas.RegionUpdate, schemas.RegionUpdateResponse, schemas.RegionRead):
            assert "jail_location_id" in cls.__fields__, cls.__name__
            assert cls.__fields__["jail_location_id"].required is False

    def test_model_column_is_nullable_fk_set_null(self):
        import models
        col = models.Region.__table__.c.jail_location_id
        assert col.nullable is True
        fk = next(iter(col.foreign_keys))
        assert fk.column.table.name == "Locations"
        assert fk.ondelete == "SET NULL"


# ===========================================================================
# 4. Dialogue choose: optional character_id -> ownership + lock
# ===========================================================================

def _choose(session, body, ownership=None):
    with patch("main.verify_character_ownership", new_callable=AsyncMock, side_effect=ownership) as own, \
            patch("crud.get_dialogue_node", new_callable=AsyncMock, return_value=None) as node:
        r = _client(session).post("/locations/npcs/3/dialogue/5/choose", json=body)
    return r, own, node


class TestDialogueChoose:
    def test_without_character_id_no_checks(self):
        r, own, node = _choose(_session(jailed=SOON), {"option_id": 1})
        assert r.status_code == 404                      # reached the node lookup
        own.assert_not_called()
        node.assert_awaited_once()

    def test_owned_free_character_proceeds(self):
        r, own, node = _choose(_session(), {"option_id": 1, "character_id": CID})
        assert r.status_code == 404
        assert own.await_args.args[1:] == (CID, USER.id)
        node.assert_awaited_once()

    def test_foreign_character_is_refused(self):
        r, own, node = _choose(_session(), {"option_id": 1, "character_id": CID},
                               ownership=HTTPException(status_code=403, detail="Чужой персонаж"))
        assert r.status_code == 403
        node.assert_not_called()

    @pytest.mark.parametrize("lock,prefix", [
        ({"jailed": SOON}, "Персонаж в тюрьме"),
        ({"encounter": 4}, "Персонаж остановлен стражей"),
        ({"dungeon": 9}, "Персонаж находится в подземелье"),
    ], ids=["jail", "encounter", "dungeon"])
    def test_locked_character_gets_409(self, lock, prefix):
        r, _, node = _choose(_session(**lock), {"option_id": 1, "character_id": CID})
        assert r.status_code == 409
        assert r.json()["detail"].startswith(prefix)
        node.assert_not_called()
