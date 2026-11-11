"""FEAT-211 task 15 — locations-service side of physical caravans and raids.

Covered (section 3.11 / 3.12 / 3.13 A13-A14 of the feature file):

1. **Post gate «caravan»** — constants (type, 500 chars per target, label);
   ``crud.validate_caravan_targets`` against a real SQLite ``econ_caravans`` stand-in
   (physical + in_transit + not arrived + standing in that location, else 400
   «Каравана нет в этой локации»; no query at all without a caravan gate);
   the three entry points call it with the right location: ``POST /posts/``,
   ``move_and_post`` (the destination) and the retro-gate edit request
   (``crud.edit_post`` on real SQLite — a refused request leaves no row);
   the moderation queue resolves a caravan target («Караван: <группа>», state).
2. **Ordinary merchants never buy stolen goods** — ``quote_bids`` drops stolen items
   for an explicit admin row and for the living merchant's group auto-bid, the sell
   route refuses (nothing moves); admin shop rows refuse a stolen item on create and
   update, delete still works.
3. **Fence A13/A14** — the price formula floor(price x region mult x pct / 100) for a
   legacy and a living region and a custom pct, accepted groups (list / [] / NULL /
   garbage JSON), price < 1 and bogus groups dropped; the sale is paid from the
   fence's own cash (op npc_shop_sell, metadata fence: true, no tax, nothing
   stocked, world sum 0); not enough cash = 409 before the inventory; a failed
   credit returns the item; inventory refusal / outage pays nothing; the
   npc_dialogue gate and the same-location rule; an outlaw may sell (real
   reputation reads) while an ordinary merchant still refuses him; wrong NPC role /
   dead / inactive / unknown = 404; somebody else's character = 403; SQL-ish
   inputs are 422 and never executed.

Only the network is mocked; money flows run on the real async ledger.
"""

import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import crud  # noqa: E402
import econ_core  # noqa: E402
import main  # noqa: E402
import reputation_sqlite  # noqa: E402
import schemas  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from models import (  # noqa: E402
    ActionGate, Location, Post, PostDeletionRequest, PostGateRequest, PostReport, PostVersion,
)

from test_econ_locations_flows import (  # noqa: E402,F401
    shop_db, _Shop, _sell, _make_living, _fund, _balance, _one, _world_sum, _http_factory, _user,
    PLAYER, OTHER, USER, OTHER_USER, NPC_REGION, ITEM, OTHER_FOOD,
)
from test_npc_shop_admin_market import world, api, _sql  # noqa: E402,F401
from test_post_gate_requests import _sqlite_translate  # noqa: E402

CARAVAN_NOT_HERE = "Каравана нет в этой локации"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Post gate «caravan»
# ═══════════════════════════════════════════════════════════════════════════

HERE, ELSEWHERE = 60, 61
AUTHOR_UID, CHAR_ID, POST_ID = 20, 600, 700
CARAVAN_OK, CARAVAN_OK_2, CARAVAN_AWAY = 1, 2, 3
CARAVAN_ABSTRACT, CARAVAN_DELIVERED, CARAVAN_ARRIVED, CARAVAN_NOWHERE = 4, 5, 6, 7
CARAVAN_UNKNOWN = 999

ECON_CARAVANS_DDL = (
    "CREATE TABLE econ_caravans (id INTEGER PRIMARY KEY, group_code VARCHAR(32) NOT NULL, "
    "status VARCHAR(16) NOT NULL, is_physical INTEGER NOT NULL DEFAULT 0, "
    "current_location_id INTEGER NULL, arrived_at DATETIME NULL)"
)
CARAVAN_ROWS = [
    # id, group, status, physical, location, arrived_at
    (CARAVAN_OK, "ore_metal", "in_transit", 1, HERE, None),
    (CARAVAN_OK_2, "food", "in_transit", 1, HERE, None),
    (CARAVAN_AWAY, "food", "in_transit", 1, ELSEWHERE, None),
    (CARAVAN_ABSTRACT, "food", "in_transit", 0, HERE, None),
    (CARAVAN_DELIVERED, "food", "delivered", 1, HERE, None),
    (CARAVAN_ARRIVED, "food", "in_transit", 1, HERE, "2026-11-11 10:00:00"),
    (CARAVAN_NOWHERE, "food", "in_transit", 1, None, None),
]


def _caravan_gate(*ids):
    return [{"action_type": "caravan", "targets": list(ids)}]


@pytest_asyncio.fixture()
async def post_db():
    """In-memory SQLite with the post tables, a `characters` stub and the character-service
    `econ_caravans` / `econ_goods_groups` tables locations-service reads by raw SQL."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _setup(dbapi_conn, _record):  # pragma: no cover - connection hook
        dbapi_conn.create_function("NOW", 0, lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def _translate(conn, cursor, statement, parameters, context, executemany):  # pragma: no cover - hook
        return _sqlite_translate(statement), parameters

    async with engine.begin() as conn:
        for ddl in (
            'CREATE TABLE "Regions" (id INTEGER PRIMARY KEY)',
            'CREATE TABLE "Districts" (id INTEGER PRIMARY KEY)',
            "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, current_location_id INTEGER)",
            ECON_CARAVANS_DDL,
            "CREATE TABLE econ_goods_groups (code VARCHAR(32) PRIMARY KEY, name VARCHAR(64) NOT NULL)",
        ):
            await conn.execute(text(ddl))
        for table in (Location.__table__, Post.__table__, ActionGate.__table__, PostDeletionRequest.__table__,
                      PostReport.__table__, PostGateRequest.__table__, PostVersion.__table__):
            await conn.run_sync(table.create)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        for loc_id, name in ((HERE, "Тракт"), (ELSEWHERE, "Перевал")):
            s.add(Location(id=loc_id, name=name, type="location", recommended_level=1,
                           quick_travel_marker=False, description="d", marker_type="safe",
                           sort_order=0, is_starting=False))
        await s.execute(text("INSERT INTO characters (id, user_id, current_location_id) VALUES (:c, :u, :l)"),
                        {"c": CHAR_ID, "u": AUTHOR_UID, "l": HERE})
        for row in CARAVAN_ROWS:
            await s.execute(text(
                "INSERT INTO econ_caravans (id, group_code, status, is_physical, current_location_id, arrived_at) "
                "VALUES (:i, :g, :s, :p, :l, :a)"),
                dict(zip(("i", "g", "s", "p", "l", "a"), row)))
        await s.execute(text("INSERT INTO econ_goods_groups (code, name) VALUES "
                             "('ore_metal', 'Руда и металл'), ('food', 'Еда')"))
        await s.commit()
        yield s
    await engine.dispose()


class TestCaravanGateConstants:

    def test_caravan_is_a_gated_post_type_priced_like_pvp(self):
        assert "caravan" in crud.GATED_POST_TYPES
        assert crud.GATE_SYMBOL_COST["caravan"] == 500 == crud.GATE_SYMBOL_COST["pvp"]
        assert crud.GATE_LABELS["caravan"] == "налёта на караван"

    def test_action_type_fits_the_varchar_20_column(self):
        assert len("caravan") <= 20

    @pytest.mark.parametrize("ids,required", [([1], 500), ([1, 2], 1000), ([1, 2, 3], 1500)])
    def test_required_symbols_are_500_per_caravan(self, ids, required):
        assert crud.required_symbols_for_gates(_caravan_gate(*ids)) == required

    def test_cost_adds_up_with_other_intents(self):
        gates = _caravan_gate(1) + [{"action_type": "combat", "targets": [5]}]
        assert crud.required_symbols_for_gates(gates) == 700

    def test_shape_accepts_a_caravan_gate_and_needs_a_target(self):
        crud.validate_gate_shape(_caravan_gate(1))
        with pytest.raises(HTTPException) as exc:
            crud.validate_gate_shape([{"action_type": "caravan", "targets": []}])
        assert exc.value.status_code == 400
        assert exc.value.detail == "Для налёта на караван выберите цель в посте"

    def test_intent_post_needs_500_chars_for_one_caravan(self):
        main._validate_intent_post(500, _caravan_gate(1))
        with pytest.raises(HTTPException) as exc:
            main._validate_intent_post(499, _caravan_gate(1))
        assert exc.value.status_code == 400 and "минимум 500" in exc.value.detail


class TestValidateCaravanTargets:

    async def test_a_caravan_standing_here_passes(self, post_db):
        await crud.validate_caravan_targets(post_db, _caravan_gate(CARAVAN_OK), HERE)

    async def test_two_caravans_here_and_repeated_ids_pass(self, post_db):
        gates = _caravan_gate(CARAVAN_OK, CARAVAN_OK_2, CARAVAN_OK)
        await crud.validate_caravan_targets(post_db, gates, HERE)

    @pytest.mark.parametrize("caravan_id", [
        CARAVAN_AWAY,        # on the road, but in another location
        CARAVAN_ABSTRACT,    # abstract caravan (not on the map)
        CARAVAN_DELIVERED,   # finished
        CARAVAN_ARRIVED,     # reached its destination, waiting for delivery
        CARAVAN_NOWHERE,     # no position
        CARAVAN_UNKNOWN,     # no such caravan
    ])
    async def test_anything_else_is_400(self, post_db, caravan_id):
        with pytest.raises(HTTPException) as exc:
            await crud.validate_caravan_targets(post_db, _caravan_gate(caravan_id), HERE)
        assert (exc.value.status_code, exc.value.detail) == (400, CARAVAN_NOT_HERE)

    async def test_one_bad_target_among_good_ones_fails_the_whole_post(self, post_db):
        with pytest.raises(HTTPException) as exc:
            await crud.validate_caravan_targets(post_db, _caravan_gate(CARAVAN_OK, CARAVAN_AWAY), HERE)
        assert exc.value.detail == CARAVAN_NOT_HERE

    async def test_the_caravan_counts_only_for_its_own_location(self, post_db):
        await crud.validate_caravan_targets(post_db, _caravan_gate(CARAVAN_AWAY), ELSEWHERE)
        with pytest.raises(HTTPException):
            await crud.validate_caravan_targets(post_db, _caravan_gate(CARAVAN_OK), ELSEWHERE)

    async def test_unknown_location_is_400(self, post_db):
        with pytest.raises(HTTPException) as exc:
            await crud.validate_caravan_targets(post_db, _caravan_gate(CARAVAN_OK), None)
        assert exc.value.detail == CARAVAN_NOT_HERE

    @pytest.mark.parametrize("gates", [
        [],
        None,
        [{"action_type": "combat", "targets": [CARAVAN_UNKNOWN]}],
        [{"action_type": "npc_dialogue", "targets": [5]}, {"action_type": "pvp", "targets": [6]}],
        [{"action_type": "caravan", "targets": [None]}],
    ])
    async def test_no_caravan_target_means_no_query(self, gates):
        session = MagicMock()
        session.execute = AsyncMock(side_effect=AssertionError("must not query"))
        await crud.validate_caravan_targets(session, gates, HERE)
        session.execute.assert_not_awaited()

    async def test_mob_targets_are_not_validated_against_caravans(self, post_db):
        gates = [{"action_type": "combat", "targets": [CARAVAN_UNKNOWN]}] + _caravan_gate(CARAVAN_OK)
        await crud.validate_caravan_targets(post_db, gates, HERE)

    async def test_string_ids_are_coerced_and_parameterised(self, post_db):
        await crud.validate_caravan_targets(post_db, _caravan_gate(str(CARAVAN_OK)), HERE)
        with pytest.raises(ValueError):
            await crud.validate_caravan_targets(post_db, _caravan_gate("1 OR 1=1"), HERE)
        assert await _one(post_db, "SELECT COUNT(*) FROM econ_caravans") == len(CARAVAN_ROWS)


# --------------------------------------------------------------------------- create / move-and-post routes

ADMIN = UserRead(id=1, username="a", role="admin", permissions=[])
POST_TEXT = "Караван скрипит колёсами по тракту, и охрана косится на обочину. "


def _route_patches(validator, *, create_post_exc=None):
    exc = create_post_exc or HTTPException(status_code=418, detail="past the caravan gate")
    return [
        patch("main.verify_character_ownership", new_callable=AsyncMock),
        patch("main.check_not_in_battle", new_callable=AsyncMock),
        patch("main.check_not_gathering", new_callable=AsyncMock),
        patch("crud.validate_caravan_targets", validator),
        patch("crud.create_post", new_callable=AsyncMock, side_effect=exc),
    ]


class _Patched:
    def __init__(self, patches):
        self.patches = patches

    def __enter__(self):
        return [p.start() for p in self.patches]

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


@pytest.fixture()
def admin_client(client):
    main.app.dependency_overrides[get_current_user_via_http] = lambda: ADMIN
    yield client
    main.app.dependency_overrides.pop(get_current_user_via_http, None)


class TestCreatePostRoute:

    def _post(self, client, content, gates, location_id=HERE):
        return client.post("/locations/posts/", json={
            "character_id": CHAR_ID, "location_id": location_id, "content": content, "gates": gates})

    def test_caravan_gate_is_validated_with_the_post_location(self, admin_client):
        validator = AsyncMock(return_value=None)
        with _Patched(_route_patches(validator)) as mocks:
            r = self._post(admin_client, POST_TEXT * 8, _caravan_gate(CARAVAN_OK))
        assert r.status_code == 418, r.text                   # reached crud.create_post
        validator.assert_awaited_once()
        _session, gates, location_id = validator.await_args.args
        assert gates == [{"action_type": "caravan", "targets": [CARAVAN_OK]}]
        assert location_id == HERE
        mocks[-1].assert_awaited_once()

    def test_caravan_not_here_stops_the_post(self, admin_client):
        validator = AsyncMock(side_effect=HTTPException(status_code=400, detail=CARAVAN_NOT_HERE))
        with _Patched(_route_patches(validator)) as mocks:
            r = self._post(admin_client, POST_TEXT * 8, _caravan_gate(CARAVAN_AWAY))
        assert (r.status_code, r.json()["detail"]) == (400, CARAVAN_NOT_HERE)
        mocks[-1].assert_not_awaited()                        # no post was created

    def test_too_short_for_a_caravan_gate_is_400_before_the_caravan_lookup(self, admin_client):
        validator = AsyncMock(return_value=None)
        with _Patched(_route_patches(validator)) as mocks:
            r = self._post(admin_client, "ж" * 499, _caravan_gate(CARAVAN_OK))
        assert r.status_code == 400 and "минимум 500" in r.json()["detail"]
        validator.assert_not_awaited()
        mocks[-1].assert_not_awaited()

    def test_two_caravans_need_1000_chars(self, admin_client):
        validator = AsyncMock(return_value=None)
        with _Patched(_route_patches(validator)):
            r = self._post(admin_client, "ж" * 999, _caravan_gate(CARAVAN_OK, CARAVAN_OK_2))
        assert r.status_code == 400 and "минимум 1000" in r.json()["detail"]

    def test_caravan_gate_without_target_is_400(self, admin_client):
        validator = AsyncMock(return_value=None)
        with _Patched(_route_patches(validator)):
            r = self._post(admin_client, POST_TEXT * 8, [{"action_type": "caravan", "targets": []}])
        assert (r.status_code, r.json()["detail"]) == (400, "Для налёта на караван выберите цель в посте")

    @pytest.mark.parametrize("target", ["1 OR 1=1", "1; DROP TABLE econ_caravans; --"])
    def test_sql_like_target_is_422(self, admin_client, target):
        validator = AsyncMock(return_value=None)
        with _Patched(_route_patches(validator)):
            r = self._post(admin_client, POST_TEXT * 8, [{"action_type": "caravan", "targets": [target]}])
        assert r.status_code == 422
        validator.assert_not_awaited()

    def test_without_a_token_is_401(self, client):
        r = client.post("/locations/posts/", json={
            "character_id": CHAR_ID, "location_id": HERE, "content": POST_TEXT * 8,
            "gates": _caravan_gate(CARAVAN_OK)})
        assert r.status_code == 401


def _move_http(current_location):
    async def get(url, *a, **kw):
        resp = MagicMock(status_code=200)
        if "/profile" in url:
            resp.json.return_value = {"current_location_id": current_location, "travel_cooldown_until": None}
        else:
            resp.json.return_value = {"current_stamina": 100}
        return resp

    http = AsyncMock()
    http.__aenter__.return_value = http
    http.__aexit__.return_value = False
    http.get = AsyncMock(side_effect=get)
    return http


class TestMoveAndPostRoute:

    def _move(self, client, validator, gates, content=None):
        with _Patched(_route_patches(validator) + [
                patch("httpx.AsyncClient", return_value=_move_http(HERE))]) as mocks:
            r = client.post(f"/locations/{HERE}/move_and_post", json={
                "character_id": CHAR_ID, "content": content or POST_TEXT * 8, "gates": gates})
        return r, mocks[4]

    def test_caravan_is_validated_against_the_destination(self, admin_client):
        validator = AsyncMock(return_value=None)
        r, create_post = self._move(admin_client, validator, _caravan_gate(CARAVAN_OK))
        assert r.status_code == 418, r.text
        assert validator.await_args.args[1:] == ([{"action_type": "caravan", "targets": [CARAVAN_OK]}], HERE)
        create_post.assert_awaited_once()

    def test_caravan_not_here_stops_the_move_and_the_post(self, admin_client):
        validator = AsyncMock(side_effect=HTTPException(status_code=400, detail=CARAVAN_NOT_HERE))
        r, create_post = self._move(admin_client, validator, _caravan_gate(CARAVAN_AWAY))
        assert (r.status_code, r.json()["detail"]) == (400, CARAVAN_NOT_HERE)
        create_post.assert_not_awaited()

    def test_short_text_is_refused_before_the_lookup(self, admin_client):
        validator = AsyncMock(return_value=None)
        r, create_post = self._move(admin_client, validator, _caravan_gate(CARAVAN_OK), content="ж" * 450)
        assert r.status_code == 400 and "минимум 500" in r.json()["detail"]
        validator.assert_not_awaited()
        create_post.assert_not_awaited()


# --------------------------------------------------------------------------- retro-gate edit request

async def _add_post(s, content):
    s.add(Post(id=POST_ID, character_id=CHAR_ID, location_id=HERE, content=content, post_type="regular",
               created_at=datetime.utcnow()))
    await s.commit()


async def _requests(s):
    return await _one(s, "SELECT COUNT(*) FROM post_gate_requests")


async def _edit(s, content, gates):
    return await crud.edit_post(s, post_id=POST_ID, content=content, user_id=AUTHOR_UID, is_admin=False,
                                gates=gates)


class TestEditRequest:

    async def test_request_for_a_caravan_here_is_created(self, post_db):
        await _add_post(post_db, "а" * 600)
        out = await _edit(post_db, "а" * 600, _caravan_gate(CARAVAN_OK))
        assert out["gate_request_status"] == "pending" and out["gate_request_id"] is not None
        gates = await _one(post_db, "SELECT gates FROM post_gate_requests WHERE id = :r", r=out["gate_request_id"])
        assert "caravan" in gates and str(CARAVAN_OK) in gates
        assert await _one(post_db, "SELECT COUNT(*) FROM action_gates") == 0     # a request, never a gate

    @pytest.mark.parametrize("caravan_id", [CARAVAN_AWAY, CARAVAN_DELIVERED, CARAVAN_ABSTRACT, CARAVAN_UNKNOWN])
    async def test_request_for_a_caravan_not_here_is_400_and_leaves_nothing(self, post_db, caravan_id):
        await _add_post(post_db, "а" * 600)
        with pytest.raises(HTTPException) as exc:
            await _edit(post_db, "б" * 600, _caravan_gate(caravan_id))
        assert (exc.value.status_code, exc.value.detail) == (400, CARAVAN_NOT_HERE)
        assert await _requests(post_db) == 0
        assert await _one(post_db, "SELECT content FROM posts WHERE id = :p", p=POST_ID) == "а" * 600

    async def test_the_budget_is_500_per_caravan(self, post_db):
        await _add_post(post_db, "а" * 400)
        with pytest.raises(HTTPException) as exc:
            await _edit(post_db, "а" * 400, _caravan_gate(CARAVAN_OK))
        assert exc.value.status_code == 400 and "минимум 500" in exc.value.detail
        assert await _requests(post_db) == 0

    async def test_character_who_walked_away_gets_403_first(self, post_db):
        await _add_post(post_db, "а" * 600)
        await post_db.execute(text("UPDATE characters SET current_location_id = :l WHERE id = :c"),
                              {"l": ELSEWHERE, "c": CHAR_ID})
        await post_db.commit()
        with pytest.raises(HTTPException) as exc:
            await _edit(post_db, "а" * 600, _caravan_gate(CARAVAN_OK))
        assert exc.value.status_code == 403
        assert await _requests(post_db) == 0

    async def test_a_text_only_edit_does_not_look_at_caravans(self, post_db):
        await _add_post(post_db, "а" * 600)
        await post_db.execute(text("DROP TABLE econ_caravans"))
        await post_db.commit()
        out = await _edit(post_db, "в" * 600, None)
        assert out["gate_request_id"] is None


class TestModerationQueue:

    def _item(self, *ids, location_id=HERE):
        return {"location_id": location_id, "gates": _caravan_gate(*ids)}

    async def test_caravan_target_is_resolved_with_its_group_and_state(self, post_db):
        (item,) = await crud._resolve_gate_targets(post_db, [self._item(CARAVAN_OK, CARAVAN_AWAY)])
        assert item["targets_resolved"]["caravan"] == [
            {"id": CARAVAN_OK, "name": "Караван: Руда и металл", "state": "караван в пути, в этой локации"},
            {"id": CARAVAN_AWAY, "name": "Караван: Еда", "state": "караван в пути, в другой локации"},
        ]

    @pytest.mark.parametrize("caravan_id", [CARAVAN_DELIVERED, CARAVAN_ARRIVED, CARAVAN_ABSTRACT])
    async def test_a_caravan_off_the_road_is_shown_as_such(self, post_db, caravan_id):
        (item,) = await crud._resolve_gate_targets(post_db, [self._item(caravan_id)])
        assert item["targets_resolved"]["caravan"][0]["state"] == "караван уже не в пути, в этой локации"

    async def test_unknown_group_falls_back_to_the_id(self, post_db):
        await post_db.execute(text("UPDATE econ_caravans SET group_code = 'junk' WHERE id = :i"), {"i": CARAVAN_OK})
        await post_db.commit()
        (item,) = await crud._resolve_gate_targets(post_db, [self._item(CARAVAN_OK)])
        assert item["targets_resolved"]["caravan"][0]["name"] == f"Караван #{CARAVAN_OK}"

    async def test_unknown_caravan_and_unknown_location(self, post_db):
        (a, b) = await crud._resolve_gate_targets(post_db, [self._item(CARAVAN_UNKNOWN),
                                                             self._item(CARAVAN_NOWHERE)])
        assert a["targets_resolved"]["caravan"] == [{"id": CARAVAN_UNKNOWN, "name": None, "state": "цель не найдена"}]
        assert b["targets_resolved"]["caravan"][0]["state"] == "караван в пути, локация неизвестна"

    async def test_missing_table_degrades_instead_of_500(self, post_db):
        await post_db.execute(text("DROP TABLE econ_caravans"))
        await post_db.commit()
        (item,) = await crud._resolve_gate_targets(post_db, [self._item(CARAVAN_OK)])
        assert item["targets_resolved"]["caravan"] == [{"id": CARAVAN_OK, "name": None, "state": "цель не найдена"}]

    async def test_the_pending_queue_carries_the_caravan_target(self, post_db):
        await _add_post(post_db, "а" * 600)
        await _edit(post_db, "а" * 600, _caravan_gate(CARAVAN_OK))
        with patch.object(crud, "_enrich_moderation_items", AsyncMock(side_effect=lambda items: items)):
            (item,) = await crud.get_pending_gate_requests(post_db)
        assert item["gates"] == _caravan_gate(CARAVAN_OK)
        assert item["targets_resolved"]["caravan"][0]["name"] == "Караван: Руда и металл"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Ordinary merchants never buy stolen goods
# ═══════════════════════════════════════════════════════════════════════════

async def _steal(s, *item_ids):
    for item_id in item_ids:
        await s.execute(text("UPDATE items SET is_stolen = 1 WHERE id = :i"), {"i": item_id})
    await s.commit()


async def _bag(s, item_id, quantity, cid=PLAYER):
    await s.execute(text("INSERT INTO character_inventory (character_id, item_id, quantity) VALUES (:c, :i, :q)"),
                    {"c": cid, "i": item_id, "q": quantity})
    await s.commit()


class TestMerchantsRefuseStolen:

    async def test_stolen_item_ids_helper(self, shop_db):
        await _steal(shop_db, ITEM)
        assert await crud.stolen_item_ids(shop_db, [ITEM, OTHER_FOOD, 12345]) == {ITEM}
        assert await crud.stolen_item_ids(shop_db, []) == set()

    async def test_explicit_admin_row_is_not_quoted_for_a_stolen_item(self, shop_db):
        market = await crud.merchant_market(shop_db, NPC_REGION)
        assert ITEM in await crud.quote_bids(shop_db, market, [ITEM])
        await _steal(shop_db, ITEM)
        assert await crud.quote_bids(shop_db, market, [ITEM]) == {}

    async def test_living_merchant_group_auto_bid_skips_stolen(self, shop_db):
        await _make_living(shop_db)
        market = await crud.merchant_market(shop_db, NPC_REGION)
        assert set(await crud.quote_bids(shop_db, market, [ITEM, OTHER_FOOD])) == {ITEM, OTHER_FOOD}
        await _steal(shop_db, OTHER_FOOD)
        assert set(await crud.quote_bids(shop_db, market, [ITEM, OTHER_FOOD])) == {ITEM}

    async def test_sell_offers_hide_stolen_items(self, shop_db):
        await _make_living(shop_db)
        await _bag(shop_db, ITEM, 2)
        await _bag(shop_db, OTHER_FOOD, 5)
        await _steal(shop_db, OTHER_FOOD)
        offers = await crud.get_sell_offers(shop_db, NPC_REGION, PLAYER, 999)
        assert [o["item_id"] for o in offers] == [ITEM]

    async def test_legacy_merchant_refuses_to_buy_a_stolen_row_item(self, shop_db):
        await _steal(shop_db, ITEM)
        with _Shop(sell_price=40) as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION)
        assert (exc.value.status_code, exc.value.detail) == (400, "Этот NPC не покупает данный предмет")
        shop.client.delete.assert_not_awaited()
        assert await _balance(shop_db, PLAYER) == 1000
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_operations") == 0

    async def test_living_merchant_refuses_a_stolen_group_item(self, shop_db):
        await _make_living(shop_db)
        await _fund(shop_db, NPC_REGION, 1000)
        await _steal(shop_db, OTHER_FOOD)
        ops_before = await _one(shop_db, "SELECT COUNT(*) FROM econ_operations")
        with _Shop() as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(shop_db, NPC_REGION, item_id=OTHER_FOOD, mirror=False)
        assert exc.value.status_code == 400
        shop.client.delete.assert_not_awaited()
        assert await _one(shop_db, "SELECT COUNT(*) FROM econ_operations") == ops_before
        assert await _world_sum(shop_db) == 0


SHOP_STOLEN = "Краденое нельзя продавать в магазине"


class TestAdminShopRowsRefuseStolen:

    def test_create_row_for_a_stolen_item_is_400(self, api, world):
        _sql(world, "UPDATE items SET is_stolen = 1 WHERE id = 3")
        r = api.post("/locations/admin/npc-shop/31/items", json={"item_id": 3, "buy_price": 200, "sell_price": 80})
        assert (r.status_code, r.json()["detail"]) == (400, SHOP_STOLEN)
        assert _sql(world, "SELECT COUNT(*) FROM npc_shop_items WHERE npc_id = 31 AND item_id = 3")[0][0] == 0

    def test_create_row_for_a_clean_item_still_works(self, api):
        r = api.post("/locations/admin/npc-shop/31/items", json={"item_id": 3, "buy_price": 200, "sell_price": 80})
        assert r.status_code == 200, r.text

    def test_update_of_a_stolen_row_is_400_and_unchanged(self, api, world):
        before = _sql(world, "SELECT buy_price, stock FROM npc_shop_items WHERE id = 1")[0]
        item_id = _sql(world, "SELECT item_id FROM npc_shop_items WHERE id = 1")[0][0]
        _sql(world, "UPDATE items SET is_stolen = 1 WHERE id = :i", i=item_id)
        r = api.put("/locations/admin/npc-shop/items/1", json={"buy_price": 999, "stock": 50})
        assert (r.status_code, r.json()["detail"]) == (400, SHOP_STOLEN)
        assert _sql(world, "SELECT buy_price, stock FROM npc_shop_items WHERE id = 1")[0] == before

    def test_a_stolen_row_can_still_be_deleted(self, api, world):
        item_id = _sql(world, "SELECT item_id FROM npc_shop_items WHERE id = 1")[0][0]
        _sql(world, "UPDATE items SET is_stolen = 1 WHERE id = :i", i=item_id)
        r = api.delete("/locations/admin/npc-shop/items/1")
        assert r.status_code == 200, r.text
        assert _sql(world, "SELECT COUNT(*) FROM npc_shop_items WHERE id = 1")[0][0] == 0

    def test_update_of_a_missing_row_is_still_404(self, api):
        assert api.put("/locations/admin/npc-shop/items/999", json={"stock": 1}).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 3. Fence («Скупщик») A13 / A14
# ═══════════════════════════════════════════════════════════════════════════

FENCE, FENCE_FAR, FENCE_DEAD, FENCE_HOMELESS, FENCE_PLAYER = 60, 61, 62, 63, 64
ORE_BALE, FOOD_BALE, CHEAP_BALE, NO_GROUP_BALE, BOGUS_BALE = 70, 71, 72, 73, 74
FENCE_NOT_FOUND = "Скупщик не найден"
FENCE_NOT_BUYING = "Скупщик это не берёт"
FENCE_NO_CASH = "У скупщика сейчас нет денег"


@pytest_asyncio.fixture()
async def fence_db(shop_db):
    """shop_db + characters.npc_role, items.bale_group, econ_fences and stolen bales.

    FENCE stands at 1000 (region 10, the player's location), FENCE_FAR at 1001, FENCE_DEAD is dead,
    FENCE_HOMELESS has no location, FENCE_PLAYER is a player character with role 'fence';
    NPC_REGION is an ordinary merchant. The player's bag holds every bale and the clean ITEM."""
    s = shop_db
    await s.execute(text("ALTER TABLE characters ADD COLUMN npc_role VARCHAR(20) NULL"))
    await s.execute(text("ALTER TABLE items ADD COLUMN bale_group VARCHAR(32) NULL"))
    await s.execute(text(
        "CREATE TABLE econ_fences (npc_id INTEGER PRIMARY KEY, is_active INTEGER NOT NULL DEFAULT 1, "
        "price_pct INTEGER NOT NULL DEFAULT 40, accepted_groups TEXT NULL, "
        "cash_target INTEGER NOT NULL DEFAULT 2000, updated_at DATETIME NULL, updated_by INTEGER NULL)"))
    await s.execute(text("INSERT INTO econ_goods_groups (code, name, base_price) VALUES "
                         "('ore_metal', 'Руда и металл', 10), ('herbs', 'Травы', 5)"))
    for item_id, name, price, group in (
            (ORE_BALE, "Слиток руды (краденое)", 101, "ore_metal"),
            (FOOD_BALE, "Тюк зерна (краденое)", 50, "food"),
            (CHEAP_BALE, "Тюк трав (краденое)", 1, "herbs"),         # floor(1 x 0.4) = 0 -> not bought
            (NO_GROUP_BALE, "Безымянное краденое", 80, None),
            (BOGUS_BALE, "Странное краденое", 80, "junk")):
        await s.execute(text(
            "INSERT INTO items (id, name, image, item_type, item_rarity, resource_subcategory, is_food, price, "
            "is_stolen, bale_group) VALUES (:i, :n, 'bale.png', 'misc', 'common', NULL, 0, :p, 1, :g)"),
            {"i": item_id, "n": name, "p": price, "g": group})
    await s.execute(text("UPDATE characters SET npc_role = 'merchant' WHERE id = :n"), {"n": NPC_REGION})
    for cid, loc, status, npc in ((FENCE, 1000, "alive", 1), (FENCE_FAR, 1001, "alive", 1),
                                  (FENCE_DEAD, 1000, "dead", 1), (FENCE_HOMELESS, None, "alive", 1),
                                  (FENCE_PLAYER, 1000, "alive", 0)):
        await s.execute(text("INSERT INTO characters (id, current_location_id, is_npc, npc_status, npc_role) "
                             "VALUES (:c, :l, :n, :s, 'fence')"), {"c": cid, "l": loc, "n": npc, "s": status})
    for item_id, qty in ((ORE_BALE, 5), (FOOD_BALE, 3), (CHEAP_BALE, 2), (NO_GROUP_BALE, 1), (BOGUS_BALE, 1),
                         (ITEM, 2)):
        await s.execute(text("INSERT INTO character_inventory (character_id, item_id, quantity) "
                             "VALUES (:c, :i, :q)"), {"c": PLAYER, "i": item_id, "q": qty})
    await s.commit()
    return s


async def _fence_settings(s, *, npc=FENCE, is_active=1, price_pct=40, accepted=None):
    await s.execute(text("INSERT INTO econ_fences (npc_id, is_active, price_pct, accepted_groups) "
                         "VALUES (:n, :a, :p, :g)"), {"n": npc, "a": is_active, "p": price_pct, "g": accepted})
    await s.commit()


async def _region_mult(s, group, mult):
    await s.execute(text("INSERT INTO econ_region_goods (region_id, group_code, price_mult) VALUES (10, :g, :m)"),
                    {"g": group, "m": mult})
    await s.commit()


class _Fence:
    """Network + gate patches for the fence routes. `gate` = result of crud.check_action_gate."""

    def __init__(self, *, gate=True, delete_exc=None, **http):
        self.factory, self.client = _http_factory(**http)
        if delete_exc is not None:
            self.client.delete = AsyncMock(side_effect=delete_exc)
        self.gate = AsyncMock(return_value=gate)
        self.stats = AsyncMock(return_value=None)
        self._p = [
            patch.object(main.httpx, "AsyncClient", self.factory),
            patch.object(crud, "check_action_gate", self.gate),
            patch.object(main, "_track_cumulative_stats", self.stats),
        ]

    def __enter__(self):
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._p):
            p.stop()


async def _offers(s, npc=FENCE, *, character_id=PLAYER, uid=USER):
    rows = await main.get_fence_offers(npc_id=npc, character_id=character_id, session=s, current_user=_user(uid))
    return [schemas.FenceOfferRead(**r) for r in rows]


async def _fence_sell(s, npc=FENCE, *, item_id=ORE_BALE, quantity=1, character_id=PLAYER, uid=USER):
    request = MagicMock()
    request.headers = {"authorization": "Bearer t"}
    body = schemas.ShopSellRequest(character_id=character_id, item_id=item_id, quantity=quantity)
    return await main.sell_to_fence(npc_id=npc, body=body, request=request, session=s, current_user=_user(uid))


async def _bag_ops(s):
    return await _one(s, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'npc_shop_sell'")


class TestFenceUnitPrice:

    @pytest.mark.parametrize("price,mult,pct,expected", [
        (101, 1, 40, 40),            # floor(40.4)
        (101, "2", 40, 80),          # floor(80.8)
        (50, "1.5", 40, 30),
        (100, "0.333", 40, 13),      # floor(13.32)
        (101, 1, 100, 101),
        (101, 1, 1, 1),              # floor(1.01)
        (99, 1, 1, 0),               # < 1 -> does not buy
        (1, 1, 40, 0),
        (0, 1, 40, 0),
        (None, 1, 40, 0),
        (-5, 1, 40, 0),
        (100, 1, 0, 0),
    ])
    def test_formula(self, price, mult, pct, expected):
        assert crud.fence_unit_price(price, mult, pct) == expected

    @pytest.mark.parametrize("raw,expected", [
        (None, None),
        ("[]", None),
        ([], None),
        ('["food", "ore_metal"]', frozenset({"food", "ore_metal"})),
        (b'["food"]', frozenset({"food"})),
        (["herbs", "", None], frozenset({"herbs"})),
        ("not json", None),
        ('{"food": 1}', None),
        ("42", None),
    ])
    def test_accepted_groups_parsing(self, raw, expected):
        assert crud._fence_groups(raw) == expected


class TestFenceOffers:

    async def test_defaults_without_a_settings_row(self, fence_db):
        with _Fence():
            offers = await _offers(fence_db)
        assert [(o.item_id, o.group_code, o.group_name, o.unit_price, o.max_quantity) for o in offers] == [
            (ORE_BALE, "ore_metal", "Руда и металл", 40, 5),
            (FOOD_BALE, "food", "Еда", 20, 3),
        ]
        assert offers[0].item_name == "Слиток руды (краденое)" and offers[0].item_image == "bale.png"

    async def test_living_region_multiplies_by_the_region_price(self, fence_db):
        await _make_living(fence_db, food_mult="1.5")
        await _region_mult(fence_db, "ore_metal", "2")
        with _Fence():
            offers = await _offers(fence_db)
        assert {o.item_id: o.unit_price for o in offers} == {ORE_BALE: 80, FOOD_BALE: 30}

    async def test_custom_percent(self, fence_db):
        await _fence_settings(fence_db, price_pct=75)
        with _Fence():
            offers = await _offers(fence_db)
        assert {o.item_id: o.unit_price for o in offers} == {ORE_BALE: 75, FOOD_BALE: 37}

    @pytest.mark.parametrize("accepted,expected", [
        ('["food"]', {FOOD_BALE}),
        ('["ore_metal", "herbs"]', {ORE_BALE}),               # herbs bale costs < 1 -> still absent
        ('[]', {ORE_BALE, FOOD_BALE}),
        (None, {ORE_BALE, FOOD_BALE}),
        ("garbage", {ORE_BALE, FOOD_BALE}),
        ('["weapons"]', set()),
        ('["ore_metal\'; DROP TABLE items; --"]', set()),
    ])
    async def test_accepted_groups(self, fence_db, accepted, expected):
        await _fence_settings(fence_db, accepted=accepted)
        with _Fence():
            offers = await _offers(fence_db)
        assert {o.item_id for o in offers} == expected
        assert await _one(fence_db, "SELECT COUNT(*) FROM items WHERE is_stolen = 1") == 5

    async def test_clean_items_are_never_offered_and_bale_count_is_capped(self, fence_db):
        await fence_db.execute(text("INSERT INTO character_inventory (character_id, item_id, quantity) "
                                    "VALUES (:c, :i, 1500)"), {"c": PLAYER, "i": ORE_BALE})
        await fence_db.commit()
        with _Fence():
            offers = await _offers(fence_db)
        assert ITEM not in {o.item_id for o in offers}
        assert {o.item_id: o.max_quantity for o in offers}[ORE_BALE] == schemas.SHOP_MAX_QUANTITY

    async def test_empty_bag_gives_an_empty_list(self, fence_db):
        await fence_db.execute(text("DELETE FROM character_inventory"))
        await fence_db.commit()
        with _Fence():
            assert await _offers(fence_db) == []

    async def test_fence_cash_is_not_disclosed(self, fence_db):
        with _Fence():
            rows = await main.get_fence_offers(npc_id=FENCE, character_id=PLAYER, session=fence_db,
                                               current_user=_user())
        assert set(rows[0]) == {"item_id", "item_name", "item_image", "group_code", "group_name",
                                "unit_price", "max_quantity"}


class TestFenceAccess:
    """Shared A13/A14 checks (`_require_fence_access`)."""

    @pytest.mark.parametrize("npc", [NPC_REGION, FENCE_DEAD, FENCE_HOMELESS, FENCE_PLAYER, PLAYER, 424242])
    async def test_not_a_live_fence_is_404_on_both_routes(self, fence_db, npc):
        with _Fence() as f:
            with pytest.raises(HTTPException) as exc:
                await _offers(fence_db, npc)
            assert (exc.value.status_code, exc.value.detail) == (404, FENCE_NOT_FOUND)
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db, npc)
            assert (exc.value.status_code, exc.value.detail) == (404, FENCE_NOT_FOUND)
        f.client.delete.assert_not_awaited()

    async def test_inactive_fence_is_404(self, fence_db):
        await _fence_settings(fence_db, is_active=0)
        with _Fence():
            with pytest.raises(HTTPException) as exc:
                await _offers(fence_db)
        assert (exc.value.status_code, exc.value.detail) == (404, FENCE_NOT_FOUND)

    async def test_someone_elses_character_is_403(self, fence_db):
        with _Fence() as f:
            with pytest.raises(HTTPException) as exc:
                await _offers(fence_db, character_id=OTHER, uid=USER)
            assert exc.value.status_code == 403
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db, character_id=OTHER, uid=USER)
            assert exc.value.status_code == 403
        f.client.delete.assert_not_awaited()
        assert await _balance(fence_db, OTHER) == 1000

    async def test_unknown_character_is_404(self, fence_db):
        with _Fence():
            with pytest.raises(HTTPException) as exc:
                await _offers(fence_db, character_id=777777)
        assert exc.value.status_code == 404

    async def test_no_dialogue_post_is_403_and_the_gate_names_the_fence(self, fence_db):
        await _fund(fence_db, FENCE, 1000)
        with _Fence(gate=False) as f:
            with pytest.raises(HTTPException) as exc:
                await _offers(fence_db)
            assert exc.value.status_code == 403 and "Диалог с НПС" in exc.value.detail
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db)
            assert exc.value.status_code == 403
        assert f.gate.await_args.args[1:] == (PLAYER, 1000, "npc_dialogue", FENCE)
        f.client.delete.assert_not_awaited()
        assert await _balance(fence_db, PLAYER) == 1000

    async def test_fence_in_another_location_is_400(self, fence_db):
        await _fund(fence_db, FENCE_FAR, 1000)
        with _Fence() as f:
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db, FENCE_FAR)
        assert (exc.value.status_code, exc.value.detail) == (400, "Персонаж не находится в локации этого NPC")
        f.client.delete.assert_not_awaited()

    async def test_activity_locked_character_is_refused(self, fence_db):
        locked = AsyncMock(side_effect=HTTPException(status_code=409, detail="Персонаж в подземелье"))
        with _Fence() as f, patch.object(main, "check_not_activity_locked", locked):
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db)
        assert exc.value.status_code == 409
        f.client.delete.assert_not_awaited()


class TestFenceSell:

    async def test_sale_is_paid_from_the_fence_cash_and_the_bales_are_destroyed(self, fence_db):
        await _fund(fence_db, FENCE, 1000)
        with _Fence() as f:
            out = await _fence_sell(fence_db, quantity=3)
        assert out == {"success": True, "message": "Продажа совершена", "new_balance": 1120,
                       "item_name": "Слиток руды (краденое)", "quantity": 3, "total_price": 120}
        assert (await _balance(fence_db, PLAYER), await _balance(fence_db, FENCE)) == (1120, 880)
        f.client.delete.assert_awaited_once()
        url = f.client.delete.await_args.args[0]
        assert url.endswith(f"/inventory/{PLAYER}/items/{ORE_BALE}?quantity=3")
        assert f.client.delete.await_args.kwargs["headers"] == {"Authorization": "Bearer t"}
        f.client.post.assert_not_awaited()                                  # nothing given back
        meta = await _one(fence_db, "SELECT metadata FROM econ_operations WHERE op_type = 'npc_shop_sell'")
        assert '"fence": true' in meta and '"group_code": "ore_metal"' in meta and '"price_pct": 40' in meta
        assert await _one(fence_db, "SELECT COUNT(*) FROM econ_postings WHERE leg_type IN ('tax', 'trade_tax')") == 0
        assert await _one(fence_db, "SELECT COUNT(*) FROM npc_shop_items WHERE npc_id = :n", n=FENCE) == 0
        f.stats.assert_awaited_once_with(PLAYER, {"items_sold": 3, "total_gold_earned": 120})
        assert await _world_sum(fence_db) == 0

    async def test_living_region_price_is_paid(self, fence_db):
        await _make_living(fence_db)
        await _region_mult(fence_db, "ore_metal", "2")
        await _fund(fence_db, FENCE, 500)
        with _Fence():
            out = await _fence_sell(fence_db, quantity=2)
        assert out["total_price"] == 160
        assert await _balance(fence_db, FENCE) == 340
        assert await _world_sum(fence_db) == 0

    async def test_exact_cash_is_enough(self, fence_db):
        await _fund(fence_db, FENCE, 40)
        with _Fence():
            out = await _fence_sell(fence_db)
        assert out["total_price"] == 40 and await _balance(fence_db, FENCE) == 0

    async def test_not_enough_cash_is_409_before_the_inventory(self, fence_db):
        await _fund(fence_db, FENCE, 119)
        with _Fence() as f:
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db, quantity=3)
        assert (exc.value.status_code, exc.value.detail) == (409, FENCE_NO_CASH)
        f.client.delete.assert_not_awaited()
        assert (await _balance(fence_db, PLAYER), await _balance(fence_db, FENCE)) == (1000, 119)
        assert await _bag_ops(fence_db) == 0

    async def test_broke_fence_is_409(self, fence_db):
        with _Fence() as f:
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db)
        assert exc.value.detail == FENCE_NO_CASH
        f.client.delete.assert_not_awaited()

    @pytest.mark.parametrize("item_id", [ITEM, CHEAP_BALE, NO_GROUP_BALE, BOGUS_BALE, 31337])
    async def test_what_the_fence_does_not_buy_is_400(self, fence_db, item_id):
        await _fund(fence_db, FENCE, 1000)
        with _Fence() as f:
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db, item_id=item_id)
        assert (exc.value.status_code, exc.value.detail) == (400, FENCE_NOT_BUYING)
        f.client.delete.assert_not_awaited()
        assert await _balance(fence_db, FENCE) == 1000

    async def test_group_outside_the_accepted_list_is_400(self, fence_db):
        await _fence_settings(fence_db, accepted='["food"]')
        await _fund(fence_db, FENCE, 1000)
        with _Fence() as f:
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db, item_id=ORE_BALE)
            assert exc.value.detail == FENCE_NOT_BUYING
            out = await _fence_sell(fence_db, item_id=FOOD_BALE, quantity=2)
        assert out["total_price"] == 40
        assert f.client.delete.await_count == 1

    async def test_credit_failure_for_lack_of_cash_returns_the_item(self, fence_db):
        await _fund(fence_db, FENCE, 1000)

        async def _drained(*a, **kw):
            raise econ_core.InsufficientFunds(econ_core.AccountRef.character(FENCE), 80)

        with _Fence() as f, patch.object(crud, "pay_player_from_merchant", _drained):
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db, quantity=2)
        assert (exc.value.status_code, exc.value.detail) == (409, FENCE_NO_CASH)
        f.client.delete.assert_awaited_once()
        f.client.post.assert_awaited_once()
        assert f.client.post.await_args.args[0].endswith(f"/inventory/internal/characters/{PLAYER}/items")
        assert f.client.post.await_args.kwargs["json"] == {"item_id": ORE_BALE, "quantity": 2}
        assert (await _balance(fence_db, PLAYER), await _balance(fence_db, FENCE)) == (1000, 1000)
        assert await _world_sum(fence_db) == 0

    async def test_unexpected_credit_failure_is_500_and_returns_the_item(self, fence_db):
        await _fund(fence_db, FENCE, 1000)
        with _Fence() as f, patch.object(crud, "pay_player_from_merchant",
                                         AsyncMock(side_effect=RuntimeError("db gone"))):
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db)
        assert exc.value.status_code == 500
        assert "db gone" not in str(exc.value.detail)
        f.client.post.assert_awaited_once()
        assert await _balance(fence_db, PLAYER) == 1000

    async def test_failed_return_still_answers_the_error(self, fence_db):
        await _fund(fence_db, FENCE, 1000)
        with _Fence(post_status=500) as f, patch.object(crud, "pay_player_from_merchant",
                                                        AsyncMock(side_effect=RuntimeError("x"))):
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db)
        assert exc.value.status_code == 500
        f.client.post.assert_awaited_once()

    async def test_inventory_refusal_pays_nothing(self, fence_db):
        await _fund(fence_db, FENCE, 1000)
        with _Fence(delete_status=404) as f:
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db)
        assert (exc.value.status_code, exc.value.detail) == (404, "Предмета нет")
        f.client.post.assert_not_awaited()
        assert (await _balance(fence_db, PLAYER), await _balance(fence_db, FENCE)) == (1000, 1000)
        assert await _bag_ops(fence_db) == 0

    async def test_inventory_unreachable_is_503_and_pays_nothing(self, fence_db):
        await _fund(fence_db, FENCE, 1000)
        with _Fence(delete_exc=httpx.ConnectError("down")):
            with pytest.raises(HTTPException) as exc:
                await _fence_sell(fence_db)
        assert (exc.value.status_code, exc.value.detail) == (503, "Сервис инвентаря недоступен")
        assert await _balance(fence_db, FENCE) == 1000
        assert await _bag_ops(fence_db) == 0

    @pytest.mark.parametrize("quantity", [0, -1, 1000])
    def test_quantity_bounds_are_enforced_by_the_schema(self, quantity):
        with pytest.raises(Exception):
            schemas.ShopSellRequest(character_id=PLAYER, item_id=ORE_BALE, quantity=quantity)


@pytest.mark.real_reputation
class TestFenceServesOutlaws:
    """Real reputation reads: an outlaw of region 10 is refused by the ordinary merchant there but
    the fence buys from him (no outlaw refusal, no reputation cut)."""

    async def _outlaw(self, s):
        await reputation_sqlite.create_async(s)
        await s.execute(text("INSERT INTO character_reputation (character_id, region_id, value, decay_at, "
                             "updated_at) VALUES (:c, 10, -600, NULL, :u)"), {"c": PLAYER, "u": datetime.utcnow()})
        await s.commit()

    async def test_outlaw_sells_to_the_fence_at_the_full_price(self, fence_db):
        await self._outlaw(fence_db)
        await _fund(fence_db, FENCE, 1000)
        with _Fence():
            offers = await _offers(fence_db)
            out = await _fence_sell(fence_db, quantity=2)
        assert {o.item_id: o.unit_price for o in offers} == {ORE_BALE: 40, FOOD_BALE: 20}
        assert out["total_price"] == 80
        assert await _balance(fence_db, PLAYER) == 1080
        assert await _world_sum(fence_db) == 0

    async def test_the_same_outlaw_is_refused_by_the_ordinary_merchant(self, fence_db):
        await self._outlaw(fence_db)
        with _Shop(sell_price=40) as shop:
            with pytest.raises(HTTPException) as exc:
                await _sell(fence_db, NPC_REGION)
        assert exc.value.status_code == 409
        shop.client.delete.assert_not_awaited()

    async def test_npc_tier_gate_still_applies_to_the_fence(self, fence_db):
        await self._outlaw(fence_db)
        await fence_db.execute(text("UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :n"),
                               {"n": FENCE})
        await fence_db.commit()
        with _Fence() as f:
            with pytest.raises(HTTPException) as exc:
                await _offers(fence_db)
        assert exc.value.status_code == 403 and "репутация" in exc.value.detail.lower()
        f.client.delete.assert_not_awaited()


# --------------------------------------------------------------------------- HTTP layer: auth + SQL-ish input

@pytest.fixture()
def player_client(client):
    main.app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=USER, username="p", role="user", permissions=[])
    yield client
    main.app.dependency_overrides.pop(get_current_user_via_http, None)


class TestFenceHttp:

    def test_offers_without_a_token_is_401(self, client):
        assert client.get(f"/locations/npcs/{FENCE}/fence/offers?character_id={PLAYER}").status_code == 401

    def test_sell_without_a_token_is_401(self, client):
        r = client.post(f"/locations/npcs/{FENCE}/fence/sell",
                        json={"character_id": PLAYER, "item_id": ORE_BALE, "quantity": 1})
        assert r.status_code == 401

    @pytest.mark.parametrize("query", ["character_id=1%20OR%201%3D1", "character_id=1%3B%20DROP%20TABLE%20items",
                                       "character_id=0", "character_id=-1", ""])
    def test_bad_character_id_on_offers_is_422(self, player_client, query):
        assert player_client.get(f"/locations/npcs/{FENCE}/fence/offers?{query}").status_code == 422

    @pytest.mark.parametrize("path_npc", ["1%20OR%201%3D1", "abc"])
    def test_sql_like_npc_id_is_422(self, player_client, path_npc):
        assert player_client.get(f"/locations/npcs/{path_npc}/fence/offers?character_id=1").status_code == 422

    @pytest.mark.parametrize("body", [
        {"character_id": PLAYER, "item_id": "70; DROP TABLE items; --", "quantity": 1},
        {"character_id": "1 OR 1=1", "item_id": ORE_BALE, "quantity": 1},
        {"character_id": PLAYER, "item_id": ORE_BALE, "quantity": "1; --"},
        {"character_id": PLAYER, "item_id": ORE_BALE, "quantity": 0},
        {"character_id": PLAYER, "item_id": ORE_BALE, "quantity": 1000},
        {"character_id": PLAYER, "item_id": 0, "quantity": 1},
        {"character_id": PLAYER},
    ])
    def test_bad_sell_body_is_422(self, player_client, body):
        assert player_client.post(f"/locations/npcs/{FENCE}/fence/sell", json=body).status_code == 422
