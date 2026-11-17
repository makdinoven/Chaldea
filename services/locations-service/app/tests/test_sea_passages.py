"""FEAT-213 v2 (T6): the port <-> deck passage in locations-service (§3.6), on a real SQLite DB.

* ``sea_read.passage``: board needs an active ship docked at the current location and an active pass of the
  character covering the next trip (``trip_no + 1``); disembark is open to anyone (also on an inactive ship) but
  only to the docked port; a deck at sea has no way out (400); everything else is "not a passage";
* ``sea_read.passages_for``: «board» entries only for the entitled viewer on docked active ships, «disembark»
  for any viewer on a docked deck, public ``docked_ships``, ``ship_id`` of a deck;
* ``move_and_post``: board with / without a pass, inactive ship, at sea, a sea zone destination (400), the passage
  costs nothing (0 stamina is enough, no travel cooldown); ordinary neighbours unchanged;
* ``quick_move``: refuses every passage («только постом»), at sea and sea zones;
* ``client/details``: passage entries, ``docked_ships``, ``ship_id``, ``is_sea_zone`` and their visibility per
  viewer (own character / foreign character / anonymous);
* security: string ids, injection-like ship names returned verbatim.
"""
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import main  # noqa: E402
import sea_read  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from database import get_db  # noqa: E402
from sea_sqlite import (  # noqa: E402
    CHAR, DECK, DECK2, LAND, LAND2, NEXT_TRIP, OTHER_CHAR, PORT_A, PORT_B, SHIP, SHIP2, SHIP_NAME, SHIP2_NAME,
    TRIP_NO, Z1, Z2, build_world,
)

USER, OTHER_USER = 5, 6
PLAYER = UserRead(id=USER, username="p", role="user", permissions=[])
MOVE_TEXT = "Путник поднимается по сходням, придерживая шляпу от морского ветра. " * 5
NOT_ADJACENT = "Целевая локация не является соседней"


@pytest.fixture()
def world(tmp_path):
    w = build_world(tmp_path / "sea.db")
    w.sql("CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER)")
    w.sql(f"INSERT INTO characters (id, user_id) VALUES ({CHAR}, {USER}), ({OTHER_CHAR}, {OTHER_USER})")
    return w


@pytest.fixture(autouse=True)
def _clean_overrides():
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


def _passage(world, current, dest, cid=CHAR):
    return world.run(lambda s: sea_read.passage(s, cid, current, dest))


def _sea(world, location_id, viewer=CHAR):
    return world.run(lambda s: sea_read.passages_for(s, location_id, viewer))


# ===========================================================================
# 1. sea_read.passage
# ===========================================================================

class TestPassage:
    @pytest.mark.parametrize("kind", ["ticket", "sailor", "stowaway"])
    def test_board_with_any_pass_kind(self, world, kind):
        world.add_pass(kind=kind)
        p = _passage(world, PORT_A, DECK)
        assert (p.kind, p.ship_id, p.allowed, p.refusal) == ("board", SHIP, True, None)

    def test_board_without_pass(self, world):
        p = _passage(world, PORT_A, DECK)
        assert (p.kind, p.allowed, p.refusal, p.status_code) == ("board", False, sea_read.MSG_NO_RIGHT, 403)

    def test_multi_trip_ticket_covering_next_trip(self, world):
        world.add_pass(first=TRIP_NO - 1, last=NEXT_TRIP + 2)
        assert _passage(world, PORT_A, DECK).allowed is True

    @pytest.mark.parametrize("first,last", [(NEXT_TRIP + 1, NEXT_TRIP + 2), (TRIP_NO - 2, TRIP_NO)],
                             ids=["future_only", "already_used"])
    def test_pass_not_covering_next_trip(self, world, first, last):
        world.add_pass(first=first, last=last)
        assert _passage(world, PORT_A, DECK).allowed is False

    @pytest.mark.parametrize("status", ["burnt", "completed", "ashore", "caught", "refunded", "expired"])
    def test_inactive_pass_status(self, world, status):
        world.add_pass(status=status)
        assert _passage(world, PORT_A, DECK).refusal == sea_read.MSG_NO_RIGHT

    def test_pass_of_another_character(self, world):
        world.add_pass(cid=OTHER_CHAR)
        assert _passage(world, PORT_A, DECK).allowed is False
        assert _passage(world, PORT_A, DECK, cid=OTHER_CHAR).allowed is True

    def test_pass_on_another_ship(self, world):
        world.add_pass(ship=SHIP2)
        assert _passage(world, PORT_A, DECK).allowed is False

    def test_unknown_pass_kind(self, world):
        world.add_pass(kind="crew")
        assert _passage(world, PORT_A, DECK).allowed is False

    def test_inactive_ship_refuses_boarding_even_with_pass(self, world):
        world.add_pass()
        world.ship(is_active=0)
        p = _passage(world, PORT_A, DECK)
        assert (p.allowed, p.refusal, p.status_code) == (False, sea_read.MSG_SHIP_INACTIVE, 403)

    def test_board_from_another_port_is_not_a_passage(self, world):
        world.add_pass()
        assert _passage(world, PORT_B, DECK) is None
        assert _passage(world, LAND, DECK) is None

    def test_board_sailing_ship_is_not_a_passage(self, world):
        world.add_pass(ship=SHIP2, first=3, last=3)
        assert _passage(world, PORT_B, DECK2) is None

    def test_disembark_open_to_anyone(self, world):
        p = _passage(world, DECK, PORT_A, cid=OTHER_CHAR)
        assert (p.kind, p.ship_id, p.allowed) == ("disembark", SHIP, True)

    def test_disembark_from_inactive_ship(self, world):
        world.ship(is_active=0)
        assert _passage(world, DECK, PORT_A).allowed is True

    def test_disembark_only_to_docked_port(self, world):
        assert _passage(world, DECK, PORT_B) is None
        assert _passage(world, DECK, LAND) is None

    def test_deck_at_sea_has_no_exit(self, world):
        for dest in (PORT_B, PORT_A, LAND):
            p = _passage(world, DECK2, dest)
            assert (p.kind, p.ship_id, p.allowed, p.refusal, p.status_code) == \
                (None, SHIP2, False, sea_read.MSG_AT_SEA, 400)

    def test_docked_status_without_port_is_at_sea(self, world):
        world.ship(docked_port_id=None)
        assert _passage(world, DECK, PORT_A).refusal == sea_read.MSG_AT_SEA

    def test_land_to_land_is_not_a_passage(self, world):
        assert _passage(world, LAND, PORT_B) is None

    def test_energy_cost_constant_is_zero(self):
        assert sea_read.PASSAGE_ENERGY_COST == 0


# ===========================================================================
# 2. sea_read.passages_for
# ===========================================================================

class TestPassagesFor:
    def test_port_entitled_viewer_sees_board(self, world):
        world.add_pass()
        sea = _sea(world, PORT_A)
        assert sea.ship_id is None and sea.disembark == []
        assert sea.docked_ships == [{"id": SHIP, "name": SHIP_NAME}]
        assert sea.board == [{
            "id": DECK, "name": f"Корабль «{SHIP_NAME}»", "image_url": f"img/{DECK}.png", "recommended_level": 3,
            "energy_cost": 0, "passage": "board", "ship_id": SHIP, "access_label": None, "access_allowed": True,
        }]

    @pytest.mark.parametrize("viewer", [OTHER_CHAR, None], ids=["other_character", "anonymous"])
    def test_port_others_see_only_docked_ships(self, world, viewer):
        world.add_pass()
        sea = _sea(world, PORT_A, viewer=viewer)
        assert sea.board == [] and sea.docked_ships == [{"id": SHIP, "name": SHIP_NAME}]

    def test_inactive_ship_no_board_entry(self, world):
        world.add_pass()
        world.ship(is_active=0)
        sea = _sea(world, PORT_A)
        assert sea.board == [] and sea.docked_ships == [{"id": SHIP, "name": SHIP_NAME}]

    def test_two_ships_at_one_pier(self, world):
        world.ship(SHIP2, status="docked", docked_port_id=PORT_A, trip_no=7)
        world.add_pass(ship=SHIP2, first=8, last=8)
        sea = _sea(world, PORT_A)
        assert sea.docked_ships == [{"id": SHIP, "name": SHIP_NAME}, {"id": SHIP2, "name": SHIP2_NAME}]
        assert [b["ship_id"] for b in sea.board] == [SHIP2]

    def test_docked_deck_disembark_for_anyone(self, world):
        for viewer in (CHAR, OTHER_CHAR, None):
            sea = _sea(world, DECK, viewer=viewer)
            assert sea.ship_id == SHIP and sea.board == [] and sea.docked_ships == []
            assert sea.disembark == [{
                "id": PORT_A, "name": "Гавань Рассвета", "image_url": f"img/{PORT_A}.png", "recommended_level": 3,
                "energy_cost": 0, "passage": "disembark", "ship_id": SHIP,
            }]

    def test_sailing_deck_has_no_exit(self, world):
        sea = _sea(world, DECK2)
        assert sea.ship_id == SHIP2 and sea.disembark == [] and sea.board == []

    def test_ship_left_the_port(self, world):
        world.add_pass()
        world.ship(status="sailing", docked_port_id=None)
        sea = _sea(world, PORT_A)
        assert sea.board == [] and sea.docked_ships == []

    def test_land_location_has_nothing(self, world):
        sea = _sea(world, LAND)
        assert (sea.ship_id, sea.board, sea.disembark, sea.docked_ships) == (None, [], [], [])


# ===========================================================================
# 3. move_and_post / quick_move
# ===========================================================================

def _http(current, stamina):
    calls = []

    async def get(url, *a, **kw):
        resp = MagicMock(status_code=200)
        if "/profile" in url:
            resp.json.return_value = {"current_location_id": current, "travel_cooldown_until": None,
                                      "character_name": "Путник"}
        else:
            resp.json.return_value = {"current_stamina": stamina}
        return resp

    async def post(url, *a, **kw):
        calls.append((url, kw.get("json")))
        return MagicMock(status_code=200)

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get)
    client.post = AsyncMock(side_effect=post)
    return client, calls


def _drive(world, path, payload, current, stamina=100):
    main.app.dependency_overrides[get_db] = world.db_override()
    main.app.dependency_overrides[get_current_user_via_http] = lambda: PLAYER
    update = AsyncMock(return_value=main.NO_LAW_ARRIVAL)
    create_post = AsyncMock(return_value=SimpleNamespace(id=555, character_id=CHAR, location_id=0, content="x",
                                                         created_at=datetime(2026, 11, 17, 12, 0)))
    http, calls = _http(current, stamina)
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
            patch("main.check_not_locked_for_post", new_callable=AsyncMock, return_value=main.POST_FREE), \
            patch("main.check_not_locked_for_move", new_callable=AsyncMock), \
            patch("main.check_not_in_battle", new_callable=AsyncMock), \
            patch("main.check_not_gathering", new_callable=AsyncMock), \
            patch("main.faction_read.location_access", AsyncMock(return_value=None)), \
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
            patch("httpx.AsyncClient", return_value=http):
        r = TestClient(main.app).post(path, json=payload)
    return r, create_post, update, calls


def _move(world, dest, current, stamina=100, cid=CHAR):
    return _drive(world, f"/locations/{dest}/move_and_post", {"character_id": cid, "content": MOVE_TEXT},
                  current, stamina)


def _quick(world, dest, current, stamina=100):
    return _drive(world, f"/locations/{dest}/quick_move", {"character_id": CHAR}, current, stamina)


def _posted(calls, fragment):
    return [body for url, body in calls if fragment in url]


class TestMoveAndPost:
    def test_board_with_pass_and_zero_stamina(self, world):
        world.add_pass()
        r, create_post, update, calls = _move(world, DECK, PORT_A, stamina=0)
        assert r.status_code == 200, r.text
        create_post.assert_awaited_once()
        assert update.await_args.args[:2] == (CHAR, DECK)
        assert _posted(calls, "set_travel_cooldown") == []
        assert _posted(calls, "consume_stamina") == [{"amount": 0}]

    def test_board_without_pass_403_no_post(self, world):
        r, create_post, update, _ = _move(world, DECK, PORT_A)
        assert r.status_code == 403 and r.json()["detail"] == sea_read.MSG_NO_RIGHT
        create_post.assert_not_called()
        update.assert_not_called()

    def test_board_with_foreign_pass_403(self, world):
        world.add_pass(cid=OTHER_CHAR)
        r, create_post, _, _ = _move(world, DECK, PORT_A)
        assert r.status_code == 403
        create_post.assert_not_called()

    def test_board_inactive_ship_403(self, world):
        world.add_pass()
        world.ship(is_active=0)
        r, create_post, _, _ = _move(world, DECK, PORT_A)
        assert r.status_code == 403 and r.json()["detail"] == sea_read.MSG_SHIP_INACTIVE
        create_post.assert_not_called()

    def test_board_from_wrong_port_400(self, world):
        world.add_pass()
        r, create_post, _, _ = _move(world, DECK, PORT_B)
        assert r.status_code == 400 and r.json()["detail"] == NOT_ADJACENT
        create_post.assert_not_called()

    def test_disembark_free_with_zero_stamina(self, world):
        r, create_post, update, calls = _move(world, PORT_A, DECK, stamina=0)
        assert r.status_code == 200, r.text
        assert update.await_args.args[:2] == (CHAR, PORT_A)
        assert _posted(calls, "set_travel_cooldown") == []

    def test_disembark_inactive_ship_allowed(self, world):
        world.ship(is_active=0)
        r, _, _, _ = _move(world, PORT_A, DECK)
        assert r.status_code == 200, r.text

    def test_at_sea_400(self, world):
        r, create_post, update, _ = _move(world, PORT_B, DECK2)
        assert r.status_code == 400 and r.json()["detail"] == sea_read.MSG_AT_SEA
        create_post.assert_not_called()
        update.assert_not_called()

    def test_post_in_place_on_deck_at_sea(self, world):
        r, create_post, _, _ = _move(world, DECK2, DECK2)
        assert r.status_code == 200, r.text
        create_post.assert_awaited_once()

    @pytest.mark.parametrize("current", [PORT_A, Z2, None], ids=["from_port", "from_zone", "no_location"])
    def test_zone_destination_400(self, world, current):
        r, create_post, update, _ = _move(world, Z1, current)
        assert r.status_code == 400 and r.json()["detail"] == sea_read.MSG_OPEN_SEA
        create_post.assert_not_called()
        update.assert_not_called()

    def test_zone_destination_400_even_with_a_raw_neighbour_row(self, world):
        world.link(PORT_A, Z1)
        r, _, _, _ = _move(world, Z1, PORT_A)
        assert r.status_code == 400 and r.json()["detail"] == sea_read.MSG_OPEN_SEA

    def test_ordinary_neighbour_still_costs_stamina(self, world):
        r, _, _, calls = _move(world, PORT_A, LAND, stamina=10)
        assert r.status_code == 200, r.text
        assert _posted(calls, "set_travel_cooldown") == [{"minutes": 3}]
        assert _posted(calls, "consume_stamina") == [{"amount": 3}]
        r, _, _, _ = _move(world, PORT_A, LAND, stamina=0)
        assert r.status_code == 400 and r.json()["detail"] == "Недостаточно выносливости для перехода"

    def test_not_adjacent_land(self, world):
        r, _, _, _ = _move(world, PORT_B, LAND2)
        assert r.status_code == 400 and r.json()["detail"] == NOT_ADJACENT

    def test_missing_cs_tables_board_is_not_adjacent(self, tmp_path):
        bare = build_world(tmp_path / "bare.db", with_cs_tables=False)
        r, create_post, _, _ = _move(bare, DECK, PORT_A)
        assert r.status_code == 400 and r.json()["detail"] == NOT_ADJACENT
        create_post.assert_not_called()


class TestQuickMove:
    @pytest.mark.parametrize("dest,current", [(DECK, PORT_A), (PORT_A, DECK)], ids=["board", "disembark"])
    def test_passage_only_by_post(self, world, dest, current):
        world.add_pass()
        r, create_post, update, _ = _quick(world, dest, current)
        assert r.status_code == 400 and r.json()["detail"] == sea_read.MSG_POST_ONLY
        create_post.assert_not_called()
        update.assert_not_called()

    def test_board_without_pass_also_post_only(self, world):
        r, _, _, _ = _quick(world, DECK, PORT_A)
        assert r.status_code == 400 and r.json()["detail"] == sea_read.MSG_POST_ONLY

    def test_at_sea(self, world):
        r, create_post, _, _ = _quick(world, PORT_B, DECK2)
        assert r.status_code == 400 and r.json()["detail"] == sea_read.MSG_AT_SEA
        create_post.assert_not_called()

    def test_zone_destination(self, world):
        # Z1 <-> Z2 is a real neighbour row in the seed — the zone rule wins over adjacency
        r, create_post, _, _ = _quick(world, Z1, Z2)
        assert r.status_code == 400 and r.json()["detail"] == sea_read.MSG_OPEN_SEA
        create_post.assert_not_called()

    def test_ordinary_quick_move_unchanged(self, world):
        r, create_post, update, calls = _quick(world, PORT_A, LAND)
        assert r.status_code == 200, r.text
        assert update.await_args.args[:2] == (CHAR, PORT_A)


# ===========================================================================
# 4. client/details
# ===========================================================================

_EXTERNALS = {
    "crud.finalize_due_sessions": None,
    "crud.get_players_in_location": [],
    "crud.get_npcs_in_location": [],
    "crud.get_posts_by_location": [],
    "crud.get_likes_for_posts": {},
    "crud.gates_for_posts": {},
    "crud.pending_gates_for_posts": {},
    "crud.get_location_loot": [],
    "crud.is_favorited": False,
    "crud.lazy_restore_depleted_nodes": None,
    "crud.fetch_gathering_nodes_with_active_sessions": [],
}


def _details(world, location_id, character_id=None, user=PLAYER):
    main.app.dependency_overrides[get_db] = world.db_override()
    main.app.dependency_overrides[main.get_optional_user] = lambda: user
    patches = [patch(name, new_callable=AsyncMock, return_value=value) for name, value in _EXTERNALS.items()]
    for p in patches:
        p.start()
    try:
        url = f"/locations/{location_id}/client/details"
        if character_id is not None:
            url += f"?character_id={character_id}"
        r = TestClient(main.app).get(url)
    finally:
        for p in patches:
            p.stop()
    assert r.status_code == 200, r.text
    return r.json()


def _by_id(data):
    return {n["id"]: n for n in data["neighbors"]}


class TestClientDetails:
    def test_port_own_entitled_character_sees_board(self, world):
        world.add_pass()
        data = _details(world, PORT_A, character_id=CHAR)
        assert data["is_port"] is True and data["is_sea_zone"] is False and data["port_sea_zone_id"] == Z1
        assert data["ship_id"] is None
        assert data["docked_ships"] == [{"id": SHIP, "name": SHIP_NAME}]
        nb = _by_id(data)
        assert set(nb) == {LAND, DECK}
        assert (nb[LAND]["passage"], nb[LAND]["ship_id"], nb[LAND]["energy_cost"]) == (None, None, 3)
        assert nb[DECK]["passage"] == "board" and nb[DECK]["ship_id"] == SHIP
        assert nb[DECK]["name"] == f"Корабль «{SHIP_NAME}»" and nb[DECK]["energy_cost"] == 0
        assert nb[DECK]["access_allowed"] is True and nb[DECK]["access_label"] is None

    def test_port_foreign_character_does_not_see_board(self, world):
        world.add_pass()  # the pass is CHAR's, but the viewer is OTHER_USER asking with CHAR's id
        data = _details(world, PORT_A, character_id=CHAR,
                        user=UserRead(id=OTHER_USER, username="o", role="user", permissions=[]))
        assert set(_by_id(data)) == {LAND}
        assert data["docked_ships"] == [{"id": SHIP, "name": SHIP_NAME}]

    def test_port_anonymous_does_not_see_board(self, world):
        world.add_pass()
        data = _details(world, PORT_A, character_id=CHAR, user=None)
        assert set(_by_id(data)) == {LAND}
        assert data["docked_ships"] == [{"id": SHIP, "name": SHIP_NAME}]

    def test_port_without_pass_no_board(self, world):
        data = _details(world, PORT_A, character_id=CHAR)
        assert set(_by_id(data)) == {LAND}

    def test_docked_deck_disembark_for_everyone(self, world):
        for user, cid in ((PLAYER, CHAR), (None, None)):
            data = _details(world, DECK, character_id=cid, user=user)
            assert data["ship_id"] == SHIP and data["docked_ships"] == []
            nb = _by_id(data)
            assert set(nb) == {PORT_A}
            assert (nb[PORT_A]["passage"], nb[PORT_A]["ship_id"], nb[PORT_A]["energy_cost"]) == \
                ("disembark", SHIP, 0)
            assert nb[PORT_A]["name"] == "Гавань Рассвета"

    def test_sailing_deck(self, world):
        data = _details(world, DECK2, character_id=CHAR)
        assert data["ship_id"] == SHIP2 and data["neighbors"] == [] and data["docked_ships"] == []

    def test_sea_zone_flag(self, world):
        data = _details(world, Z1)
        assert data["is_sea_zone"] is True and data["ship_id"] is None
        assert {n["id"] for n in data["neighbors"]} == {Z2}

    def test_land_location_defaults(self, world):
        data = _details(world, LAND2)
        assert (data["is_port"], data["is_sea_zone"], data["ship_id"], data["docked_ships"]) == \
            (False, False, None, [])
        assert all(n["passage"] is None and n["ship_id"] is None for n in data["neighbors"])

    def test_missing_cs_tables(self, tmp_path):
        bare = build_world(tmp_path / "bare.db", with_cs_tables=False)
        data = _details(bare, PORT_A)
        assert data["docked_ships"] == [] and data["ship_id"] is None
        assert set(_by_id(data)) == {LAND}


# ===========================================================================
# 5. Security
# ===========================================================================

class TestSecurity:
    INJECTION = "'; DROP TABLE sea_ships; --"

    def test_string_ids_422(self, world):
        main.app.dependency_overrides[get_db] = world.db_override()
        main.app.dependency_overrides[get_current_user_via_http] = lambda: PLAYER
        c = TestClient(main.app)
        assert c.post("/locations/abc/move_and_post",
                      json={"character_id": CHAR, "content": MOVE_TEXT}).status_code == 422
        assert c.post(f"/locations/{DECK}/move_and_post",
                      json={"character_id": "1 OR 1=1", "content": MOVE_TEXT}).status_code == 422
        assert c.post(f"/locations/{DECK}/quick_move", json={"character_id": "abc"}).status_code == 422
        assert c.get(f"/locations/{PORT_A}/client/details?character_id=1;DROP").status_code == 422

    def test_injection_like_ship_name_verbatim(self, world):
        world.ship(name=self.INJECTION)
        world.add_pass()
        data = _details(world, PORT_A, character_id=CHAR)
        assert data["docked_ships"] == [{"id": SHIP, "name": self.INJECTION}]
        assert _by_id(data)[DECK]["name"] == f"Корабль «{self.INJECTION}»"
        assert world.sql("SELECT COUNT(*) FROM sea_ships")[0][0] == 2

    def test_move_requires_auth(self, world):
        main.app.dependency_overrides[get_db] = world.db_override()
        r = TestClient(main.app).post(f"/locations/{DECK}/move_and_post",
                                      json={"character_id": CHAR, "content": MOVE_TEXT})
        assert r.status_code == 401
