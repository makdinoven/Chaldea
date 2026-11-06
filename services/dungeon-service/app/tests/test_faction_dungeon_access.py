"""FEAT-207 (task 11): faction dungeons in dungeon-service.

* ``start_run``: the whole assembled group goes to character-service in one check; a refusal is a 403 with the
  detail built by character-service (solo / party with names / secret generic) and leaves nothing behind (no session,
  no locks); the other-check skip rules are unchanged (skipped members are not sent to the faction check);
* ``http_clients.check_faction_access``: payload, fails CLOSED (503) on network / HTTP errors;
* ``http_clients.faction_access_labels``: soft-fail -> {} ;
* ``GET /dungeons/at-location/{id}``: ``access_label`` / ``access_allowed`` from the labels call (viewer + user id
  forwarded), null when open / on failure.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

import gameplay
import http_clients
import session_state
from auth_http import UserRead, get_current_user_via_http
from main import app
from models import DungeonSession
from dungeon_harness import fake_redis, world, build_dungeon, enter_solo  # noqa: F401

PLAYER = UserRead(id=1, username="p", role="user", permissions=[])

SOLO_PUBLIC = "Подземелье только для членов фракции «Орден Зари»"
PARTY_PUBLIC = "Подземелье только для членов фракции «Орден Зари» — не проходят: Герой11, Герой12"
PARTY_SECRET = "Подземелье закрыто — войти могут не все участники отряда"


def _refuse(detail, failed):
    return {"rule": True, "allowed": False, "failed_character_ids": list(failed), "detail": detail}


async def _session_count(db):
    return (await db.execute(select(func.count()).select_from(DungeonSession))).scalar()


async def _assert_nothing_left(db, world, ids):
    assert await _session_count(db) == 0
    for cid in ids:
        assert world.lock_of(cid)["locked"] is False
        assert await session_state.get_character_active_session(cid) is None


# ===========================================================================
# 1. start_run
# ===========================================================================

async def test_open_dungeon_checks_and_enters(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    state = await enter_solo(db_session, d)
    assert state.status == "active"
    assert world.faction_checks == [(d.id, [10])]


async def test_solo_refusal_is_403_and_leaves_nothing(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.faction_access = _refuse(SOLO_PUBLIC, [10])
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 403 and exc.value.detail == SOLO_PUBLIC
    await _assert_nothing_left(db_session, world, [10])


async def test_refusal_without_detail_has_generic_text(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.faction_access = _refuse(None, [10])
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 403 and exc.value.detail == "Подземелье закрыто"


async def test_member_passes(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.faction_access = {"rule": True, "allowed": True, "failed_character_ids": [], "detail": None}
    state = await enter_solo(db_session, d)
    assert state.status == "active"


async def test_whole_party_is_sent_and_refused_as_a_whole(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11, 12]}
    world.faction_access = _refuse(PARTY_PUBLIC, [11, 12])
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    assert exc.value.status_code == 403 and exc.value.detail == PARTY_PUBLIC
    assert world.faction_checks == [(d.id, [10, 11, 12])]
    await _assert_nothing_left(db_session, world, [10, 11, 12])


async def test_secret_faction_party_refusal_is_generic(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    world.faction_access = _refuse(PARTY_SECRET, [11])
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    assert exc.value.status_code == 403 and exc.value.detail == PARTY_SECRET
    await _assert_nothing_left(db_session, world, [10, 11])


async def test_skipped_members_are_not_sent_to_the_faction_check(db_session, world):
    """Other checks keep their skip rules: an unconscious / far-away squadmate stays outside, the rest is checked."""
    d, _, _ = await build_dungeon(db_session)
    world.add_character(13, user_id=4, location=5)
    world.locks[12] = {"unconscious": datetime.utcnow() + timedelta(hours=1)}
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11, 12, 13]}
    state = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    assert world.faction_checks == [(d.id, [10, 11])]
    assert sorted(m.character_id for m in state.members) == [10, 11]
    assert {s.character_id for s in state.skipped_members} == {12, 13}


async def test_check_unavailable_is_503_and_leaves_nothing(db_session, world, monkeypatch):
    d, _, _ = await build_dungeon(db_session)

    async def down(dungeon_id, ids):
        raise HTTPException(status_code=503, detail=http_clients.FACTION_CHECK_UNAVAILABLE)

    monkeypatch.setattr(http_clients, "check_faction_access", down)
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 503
    assert exc.value.detail == "Не удалось проверить доступ к подземелью — попробуйте позже"
    await _assert_nothing_left(db_session, world, [10])


# ===========================================================================
# 2. http_clients
# ===========================================================================

def _http_client(post):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.post = post
    return client


def _resp(status, body=None):
    request = httpx.Request("POST", "http://character-service/x")
    return httpx.Response(status, json=body if body is not None else {}, request=request)


class TestCheckFactionAccess:
    async def test_payload_and_result(self):
        body = _refuse(SOLO_PUBLIC, [7])
        post = AsyncMock(return_value=_resp(200, body))
        with patch.object(http_clients, "_client", return_value=_http_client(post)):
            out = await http_clients.check_faction_access(3, [7, "8"])
        assert out == body
        url = post.await_args.args[0]
        assert url.endswith("/characters/internal/factions/access/check")
        assert post.await_args.kwargs["json"] == {"kind": "dungeon", "target_id": 3, "character_ids": [7, 8]}
        assert "X-Internal-Token" in post.await_args.kwargs["headers"]

    @pytest.mark.parametrize("post", [
        AsyncMock(side_effect=httpx.ConnectError("refused")),
        AsyncMock(side_effect=httpx.ReadTimeout("slow")),
        AsyncMock(return_value=_resp(500, {"detail": "boom"})),
        AsyncMock(return_value=_resp(404, {"detail": "Not Found"})),
    ], ids=["connect", "timeout", "5xx", "4xx"])
    async def test_fails_closed_with_503(self, post):
        with patch.object(http_clients, "_client", return_value=_http_client(post)):
            with pytest.raises(HTTPException) as exc:
                await http_clients.check_faction_access(3, [7])
        assert exc.value.status_code == 503
        assert exc.value.detail == http_clients.FACTION_CHECK_UNAVAILABLE


class TestFactionAccessLabels:
    async def test_items_by_dungeon_id(self):
        items = [{"target_id": 4, "access_label": "Закрыто: Орден Зари", "access_allowed": False}]
        post = AsyncMock(return_value=_resp(200, {"items": items}))
        with patch.object(http_clients, "_client", return_value=_http_client(post)):
            out = await http_clients.faction_access_labels([4, 5], 10, 1)
        assert out == {4: items[0]}
        assert post.await_args.kwargs["json"] == {"kind": "dungeon", "target_ids": [4, 5],
                                                  "character_id": 10, "user_id": 1}

    async def test_no_dungeons_no_call(self):
        post = AsyncMock()
        with patch.object(http_clients, "_client", return_value=_http_client(post)):
            assert await http_clients.faction_access_labels([], 10, 1) == {}
        post.assert_not_called()

    @pytest.mark.parametrize("post", [
        AsyncMock(side_effect=httpx.ConnectError("refused")),
        AsyncMock(return_value=_resp(500, {"detail": "boom"})),
        AsyncMock(return_value=_resp(200, {"items": [{"no_target": 1}]})),
    ], ids=["connect", "5xx", "malformed"])
    async def test_soft_fail(self, post):
        with patch.object(http_clients, "_client", return_value=_http_client(post)):
            assert await http_clients.faction_access_labels([4], 10, 1) == {}


# ===========================================================================
# 3. GET /dungeons/at-location
# ===========================================================================

async def test_at_location_marks(no_auth_client, db_session, world, monkeypatch):
    closed, _, _ = await build_dungeon(db_session)
    opened, _, _ = await build_dungeon(db_session)
    seen = []

    async def labels(dungeon_ids, character_id, user_id):
        seen.append((sorted(dungeon_ids), character_id, user_id))
        return {closed.id: {"target_id": closed.id, "access_label": "Закрыто: Орден Зари", "access_allowed": False}}

    monkeypatch.setattr(http_clients, "faction_access_labels", labels)
    app.dependency_overrides[get_current_user_via_http] = lambda: PLAYER
    r = await no_auth_client.get(f"/dungeons/at-location/{closed.location_id}?character_id=10")
    assert r.status_code == 200, r.text
    by_id = {d["id"]: d for d in r.json()}
    assert (by_id[closed.id]["access_label"], by_id[closed.id]["access_allowed"]) == ("Закрыто: Орден Зари", False)
    assert (by_id[opened.id]["access_label"], by_id[opened.id]["access_allowed"]) == (None, None)
    assert seen == [(sorted([closed.id, opened.id]), 10, PLAYER.id)]


async def test_at_location_without_character_and_on_failure(no_auth_client, db_session, world, monkeypatch):
    d, _, _ = await build_dungeon(db_session)
    seen = []

    async def labels(dungeon_ids, character_id, user_id):
        seen.append(character_id)
        return {}

    monkeypatch.setattr(http_clients, "faction_access_labels", labels)
    app.dependency_overrides[get_current_user_via_http] = lambda: PLAYER
    r = await no_auth_client.get(f"/dungeons/at-location/{d.location_id}")
    assert r.status_code == 200
    assert seen == [None]
    assert r.json()[0]["access_label"] is None and r.json()[0]["access_allowed"] is None


async def test_at_location_rejects_bad_character_id(no_auth_client, db_session, world):
    d, _, _ = await build_dungeon(db_session)
    app.dependency_overrides[get_current_user_via_http] = lambda: PLAYER
    r = await no_auth_client.get(f"/dungeons/at-location/{d.location_id}?character_id=0")
    assert r.status_code == 422
