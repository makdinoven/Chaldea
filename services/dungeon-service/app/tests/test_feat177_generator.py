# test_feat177_generator.py - FEAT-177: the dungeon generator (drafts for admins).
import json
from collections import defaultdict
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import text

import generator
from generator import Catalog, GenParams, generate
from schemas import validate_lock_config, validate_passage_config, validate_room_config
from helpers import _dungeon_payload

# ---------------------------------------------------------------------------
#  A catalog like the game's: mobs of every tier over the levels, and items.
# ---------------------------------------------------------------------------

MOBS = (
    [{"id": i, "tier": "normal", "level": i} for i in range(1, 41)]
    + [{"id": 100 + i, "tier": "elite", "level": 5 + i} for i in range(0, 36, 3)]
    + [{"id": 200 + i, "tier": "boss", "level": 10 + i} for i in range(0, 31, 5)]
)
ITEMS = (
    [{"id": 1000 + i, "item_type": "consumable", "item_rarity": "common", "item_level": 0, "price": 10,
      "max_stack_size": 10} for i in range(6)]
    + [{"id": 1100 + i, "item_type": "resource", "item_rarity": "rare", "item_level": 15, "price": 30,
        "max_stack_size": 20} for i in range(4)]
    + [{"id": 1200 + i, "item_type": "weapon", "item_rarity": "rare", "item_level": 20 + i, "price": 200,
        "max_stack_size": 1} for i in range(4)]
)
CATALOG = Catalog(mobs=MOBS, items=ITEMS)

PARAM_SETS = [
    dict(floors=1, rooms_per_floor=4, level=1, party_size=1, difficulty="easy"),
    dict(floors=1, rooms_per_floor=8, level=10, party_size=2),
    dict(floors=2, rooms_per_floor=10, level=25, party_size=3, difficulty="hard"),
    dict(floors=3, rooms_per_floor=14, level=30, party_size=4),
    dict(floors=5, rooms_per_floor=20, level=50, party_size=4, difficulty="hard"),
    dict(floors=2, rooms_per_floor=6, level=5, party_size=2, locks=False, secrets=False),
]
SEEDS = range(40)


def _plans():
    for params in PARAM_SETS:
        for seed in SEEDS:
            yield params, generate(GenParams(seed=seed, **params), CATALOG)


def _boss_reachable_with_keys_only(plan) -> bool:
    """From the entrance, without picking a lock and without any class challenge
    (gates, seals, secrets, hidden drops): collect keys, open their doors, reach the boss."""
    rooms = plan.rooms
    entrance = next(r.idx for r in rooms if r.role == "entrance")
    boss = next(r.idx for r in rooms if r.room_type == "boss")
    keys, seen = set(), {entrance}
    changed = True
    while changed:
        changed = False
        for r in list(seen):
            k = rooms[r].config.get("key_reward")
            if k and k not in keys:
                keys.add(k)
                changed = True
        for c in plan.corridors:
            if c.passage_config:  # a secret, a gate, a seal or a hidden drop
                continue
            if c.lock_config and c.lock_config.get("key") not in keys:
                continue
            ends = [(c.a, c.b)] + ([(c.b, c.a)] if c.is_bidirectional else [])
            for x, y in ends:
                if x in seen and y not in seen:
                    seen.add(y)
                    changed = True
        for idx, target in plan.portals.items():
            if idx in seen and target not in seen:
                seen.add(target)
                changed = True
    return boss in seen


def test_every_plan_is_passable_and_well_formed():
    for params, plan in _plans():
        where = f"{params} seed={plan.seed}"
        rooms = plan.rooms
        assert [r.role for r in rooms].count("entrance") == 1, where
        assert [r.room_type for r in rooms].count("boss") == 1, where
        boss = next(r for r in rooms if r.room_type == "boss")
        assert boss.floor == params["floors"], where
        assert _boss_reachable_with_keys_only(plan), where
        # The way to the boss is fought through: a battle on every floor's path.
        for f in range(1, params["floors"] + 1):
            middle = [r for r in rooms if r.floor == f and r.on_path and not r.role and r.room_type != "rest"]
            if middle:
                assert any(r.room_type == "battle" for r in middle), where
        # Rooms of one floor never share a grid cell (the 3D board lays them out by it).
        cells = [(r.floor, r.cell) for r in rooms]
        assert len(cells) == len(set(cells)), where
        assert len(rooms) <= params["floors"] * params["rooms_per_floor"], where
        for r in rooms:
            validate_room_config(r.room_type, r.config)
            if r.room_type in ("battle", "boss"):
                assert r.config["mob_template_ids"], where
            assert r.name and r.description, where
        pairs = set()
        for c in plan.corridors:
            validate_lock_config(c.lock_config)
            validate_passage_config(c.passage_config)
            assert c.a != c.b, where
            pair = frozenset((c.a, c.b))
            assert pair not in pairs, f"{where}: duplicate corridor"
            pairs.add(pair)
            fa, fb = rooms[c.a].floor, rooms[c.b].floor
            if c.passage_type == "corridor":
                assert fa == fb, where
                # Neighbouring cells: short straight corridors.
                assert abs(rooms[c.a].cell[0] - rooms[c.b].cell[0]) + abs(rooms[c.a].cell[1] - rooms[c.b].cell[1]) == 1
            else:
                assert fb == fa + 1, where
            if c.passage_type == "drop":
                assert not c.is_bidirectional and rooms[c.b].room_type != "boss", where


def test_each_key_opens_a_door_and_lies_where_it_can_be_reached():
    for params, plan in _plans():
        given = [r.config["key_reward"] for r in plan.rooms if r.config.get("key_reward")]
        doors = [c.lock_config["key"] for c in plan.corridors if c.lock_config]
        assert sorted(given) == sorted(doors), f"{params} seed={plan.seed}"
        if not params.get("locks", True):
            assert not doors


def test_gates_and_seals_only_bar_optional_branches():
    """A party without a warrior or a mage must still reach the boss and every key."""
    for params, plan in _plans():
        for c in plan.corridors:
            cfg = c.passage_config or {}
            if "gate" in cfg or "seal" in cfg:
                root = plan.rooms[c.b]
                assert not root.on_path and root.top_branch == root.idx
                behind = [r for r in plan.rooms if r.top_branch == root.idx]
                assert not any(r.config.get("key_reward") for r in behind)


def test_no_locks_no_secrets_means_plain_corridors():
    plan = generate(GenParams(seed=3, floors=2, rooms_per_floor=10, level=10, locks=False, secrets=False), CATALOG)
    assert not any(c.lock_config or c.passage_config for c in plan.corridors)
    assert not any(r.config.get("dark") for r in plan.rooms)


def test_same_seed_same_dungeon():
    a = generate(GenParams(seed=77, floors=2, rooms_per_floor=12, level=20, party_size=3), CATALOG)
    b = generate(GenParams(seed=77, floors=2, rooms_per_floor=12, level=20, party_size=3), CATALOG)
    c = generate(GenParams(seed=78, floors=2, rooms_per_floor=12, level=20, party_size=3), CATALOG)
    dump = lambda p: [(r.cell, r.room_type, r.name, r.config) for r in p.rooms]  # noqa: E731
    assert dump(a) == dump(b)
    assert dump(a) != dump(c)


def test_mobs_and_loot_follow_the_level():
    plan = generate(GenParams(seed=5, floors=1, rooms_per_floor=12, level=20, party_size=2), CATALOG)
    levels = {m["id"]: m for m in MOBS}
    boss = next(r for r in plan.rooms if r.room_type == "boss")
    assert levels[boss.config["mob_template_ids"][0]]["tier"] == "boss"
    assert levels[boss.config["mob_template_ids"][0]]["level"] == 20
    for r in plan.rooms:
        if r.room_type == "battle":
            for mid in r.config["mob_template_ids"]:
                m = levels[mid]
                assert m["tier"] in ("normal", "elite")
                assert 20 - generator.MOB_LEVEL_BELOW <= m["level"] <= 20 + generator.MOB_LEVEL_ABOVE
    low = generate(GenParams(seed=5, floors=1, rooms_per_floor=12, level=3), CATALOG)
    for r in low.rooms:
        for e in r.config.get("loot_table", []) + r.config.get("boss_loot", []):
            item = next(i for i in ITEMS if i["id"] == e["item_id"])
            assert item["item_rarity"] == "common", "rare finds only from level 10"


def test_admin_pools_override_the_level_choice():
    plan = generate(GenParams(seed=9, floors=1, rooms_per_floor=10, level=30, mob_pool=[1, 2], boss_pool=[3],
                              loot_pool=[1000]), CATALOG)
    for r in plan.rooms:
        if r.room_type == "boss":
            assert r.config["mob_template_ids"][0] == 3
        elif r.room_type == "battle":
            assert set(r.config["mob_template_ids"]) <= {1, 2}
        for e in r.config.get("loot_table", []):
            assert e["item_id"] == 1000


def test_an_empty_catalog_is_reported_not_crashed():
    plan = generate(GenParams(seed=1, floors=1, rooms_per_floor=8, level=10), Catalog())
    assert any("мобов" in w for w in plan.warnings)
    assert any("босса" in w for w in plan.warnings)
    assert any("предметов" in w for w in plan.warnings)


def test_event_choices_are_stored_like_the_editor_saves_them():
    for _, plan in _plans():
        for r in plan.rooms:
            for ch in r.config.get("choices", []):
                assert isinstance(ch["outcome_data"], str)
                json.loads(ch["outcome_data"])


# ---------------------------------------------------------------------------
#  The endpoint: real catalog SQL against tables shaped like the game's.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def catalog_tables(db_session):
    await db_session.execute(text(
        "CREATE TABLE mob_templates (id INTEGER PRIMARY KEY, name TEXT, tier TEXT, level INTEGER)"))
    await db_session.execute(text(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, item_type TEXT, item_rarity TEXT, "
        "item_level INTEGER, price INTEGER, max_stack_size INTEGER, is_unique INTEGER, blueprint_recipe_id INTEGER)"))
    for m in MOBS:
        await db_session.execute(text("INSERT INTO mob_templates (id, tier, level) VALUES (:id, :tier, :level)"), m)
    for i in ITEMS:
        await db_session.execute(text(
            "INSERT INTO items (id, item_type, item_rarity, item_level, price, max_stack_size, is_unique, "
            "blueprint_recipe_id) VALUES (:id, :item_type, :item_rarity, :item_level, :price, :max_stack_size, 0, NULL)"
        ), i)
    # Never offered: a one-of-a-kind item and a recipe.
    await db_session.execute(text(
        "INSERT INTO items (id, item_type, item_rarity, item_level, price, max_stack_size, is_unique, "
        "blueprint_recipe_id) VALUES (9001, 'consumable', 'common', 0, 1, 1, 1, NULL), "
        "(9002, 'recipe', 'common', 0, 1, 1, 0, NULL)"))
    await db_session.commit()
    yield
    await db_session.execute(text("DROP TABLE mob_templates"))
    await db_session.execute(text("DROP TABLE items"))
    await db_session.commit()


async def _generate(client, dungeon_id, **body):
    return await client.post(f"/dungeons/admin/dungeons/{dungeon_id}/generate", json=body)


@pytest.mark.asyncio
async def test_generate_writes_a_valid_draft_and_switches_the_dungeon_off(admin_client, catalog_tables):
    d = (await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload(recommended_level=12))).json()
    resp = await _generate(admin_client, d["id"], floors=2, rooms_per_floor=9, seed=42, theme="ice")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["seed"] == 42
    assert body["validation"]["valid"] is True, body["validation"]["errors"]
    detail = (await admin_client.get(f"/dungeons/admin/dungeons/{d['id']}")).json()
    assert detail["is_active"] is False
    assert detail["theme"] == "ice"
    assert detail["recommended_level"] == 12
    assert len(detail["rooms"]) == body["rooms"]
    assert len(detail["corridors"]) == body["corridors"]
    assert {r["floor"] for r in detail["rooms"]} == {1, 2}
    offered = set()
    for r in detail["rooms"]:
        cfg = r["room_config"] or {}
        for e in cfg.get("loot_table", []) + cfg.get("boss_loot", []) + (cfg.get("stash") or {}).get("items", []):
            offered.add(e["item_id"])
        if r["room_type"] == "teleport":
            assert cfg["target_room_id"] in {x["id"] for x in detail["rooms"]}
    assert not offered & {9001, 9002}


@pytest.mark.asyncio
async def test_generate_asks_before_replacing_rooms(admin_client, catalog_tables, dungeon_with_rooms):
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    resp = await _generate(admin_client, dungeon_id, seed=1)
    assert resp.status_code == 409
    detail = (await admin_client.get(f"/dungeons/admin/dungeons/{dungeon_id}")).json()
    assert len(detail["rooms"]) == 3  # untouched
    resp = await _generate(admin_client, dungeon_id, seed=1, replace=True)
    assert resp.status_code == 200
    detail = (await admin_client.get(f"/dungeons/admin/dungeons/{dungeon_id}")).json()
    assert "Boss Room" not in {r["name"] for r in detail["rooms"]}
    # Generating again with the same seed rebuilds the same map.
    again = await _generate(admin_client, dungeon_id, seed=1, replace=True)
    detail2 = (await admin_client.get(f"/dungeons/admin/dungeons/{dungeon_id}")).json()
    assert again.status_code == 200
    names = lambda d: sorted((r["name"], r["position_x"], r["position_y"]) for r in d["rooms"])  # noqa: E731
    assert names(detail) == names(detail2)


@pytest.mark.asyncio
async def test_generate_refused_while_a_group_is_inside(admin_client, catalog_tables, db_session):
    import models
    d = (await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload())).json()
    db_session.add(models.DungeonSession(dungeon_id=d["id"], leader_character_id=5, status="active",
                                          last_activity_at=datetime.utcnow()))
    await db_session.commit()
    resp = await _generate(admin_client, d["id"], seed=1)
    assert resp.status_code == 409
    assert "группа" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_generate_needs_the_edit_permission(no_auth_client):
    resp = await _generate(no_auth_client, 1, seed=1)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"floors": 0}, {"floors": 6}, {"rooms_per_floor": 3}, {"rooms_per_floor": 21},
    {"difficulty": "nightmare"}, {"theme": "jungle"}, {"party_size": 5}, {"level": 0},
    {"mob_pool": [0]}, {"loot_pool": ["1; DROP TABLE items"]}, {"seed": -1},
])
async def test_generate_rejects_bad_parameters(admin_client, body):
    d = (await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload())).json()
    resp = await _generate(admin_client, d["id"], **body)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_unknown_dungeon(admin_client, catalog_tables):
    resp = await _generate(admin_client, 987654, seed=1)
    assert resp.status_code == 404


def test_room_spread_looks_like_a_dungeon():
    """Across many seeds: battles are the commonest room and every dungeon has a find."""
    counts = defaultdict(int)
    for seed in range(60):
        plan = generate(GenParams(seed=seed, floors=1, rooms_per_floor=12, level=15, party_size=2), CATALOG)
        assert any(r.room_type == "treasure" for r in plan.rooms)
        for r in plan.rooms:
            counts[r.room_type] += 1
    assert counts["battle"] == max(counts.values())
    assert counts["merchant"] > 0 and counts["event"] > 0 and counts["trap"] > 0
