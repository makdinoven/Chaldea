"""FEAT-211 QA (#12): raids on physical caravans (stage 2) on SQLite.

Covers (feature file 3.6, 3.8, 3.3 steps 1–3, 3.13 A1–A3, 3.18):
* A2 raid start: owner / auth / validation, every refusal of ``begin_raid`` (404 / 400 / 409 / 403 pre-gate), the
  leader's post gate is checked BEFORE any guard is spawned, one raid per caravan, guard spawn (hidden ``dungeon``
  mobs, template nearest to the location level) and cleanup on every failure — battle-service 4xx relayed, 5xx /
  transport / crash → 503, spawn failure → 500 — leaving no raid row and no guards;
* A3 / ``settle_raid``: won (escrow → raiders through ledger op ``caravan_raid``, untaxed; marks equal + remainder to
  the leader, bales round-robin from the leader; NPC attackers get nothing; shares / logs / notices; caravan released),
  repelled, aborted, duplicate callback, foreign battle id, unknown raid; then the law step, bales via
  inventory-service (mocked; retry / give-up), guard despawn; world money sum 0 and escrow invariant after each step;
* caravan pass hooks: stale ``starting`` raids, lost Tx B re-attached, poll (finished / 404 / running / error),
  expire after ``caravan_raid_battle_max_hours``, follow-ups;
* A1: the response key whitelist (no from / to / route / value), states, 401 / 403 / 404 / 422;
* law (``shadow_crud.caravan_raid_consequences`` in the law world): witnessed / unseen / masked / forced by city
  guards or by the witness switch, reputation in the raid region + seller / buyer regions, infamy, the admin
  «тяжесть», idempotency, and the reveal of a deferred raid through the ``caravan_attack`` reputation action.

battle-service (``battle_client``), inventory-service (``caravan_raid_crud.http_post``) and attributes-service
(``crud._sync_send_attributes_request``) are mocked; RabbitMQ is stubbed by the conftest autouse fixtures.
"""

import json
import sqlite3
import sys
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import auth_http
import battle_client
import caravan_raid_crud as raids
import crud as cs_crud
import econ_ledger
import economy_api
import models
import shadow_crud
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.test_econ_tick import _balance, _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import _exec, _params, _set_params
from tests.test_econ_tick_events import calendar  # noqa: F401  (autouse: no calendar HTTP)
from tests.test_physical_caravans import (  # noqa: F401  (world fixture)
    L_GATE1, L_GATE2, L_ROAD1, _check, _dispatch, _physical_world, _row, world,
)

RAIDER, MATE, STRANGER, FAR = 501, 502, 503, 504
USER, MATE_USER, OTHER_USER = 7, 8, 99
TPL_LOW, TPL_HIGH = 12, 11              # levels 1 and 5
BALE_ID, PLAIN_ID = 9001, 9002
BATTLE = 900
TOKEN = "test-internal-token"
INTERNAL = {"X-Internal-Token": TOKEN}
HERE = "/characters/caravans/here"
RESULT = "/characters/internal/caravans/raid-result"
A1_KEYS = {"id", "group_code", "group_name", "guard_count", "state", "departs_in_sec", "can_attack", "reason"}


def _raid_url(caravan_id):
    return f"/characters/caravans/{caravan_id}/raid"


# ===================================================================================================================
# fixtures
# ===================================================================================================================

class FakeBattle:
    """battle_client.create_caravan_raid_battle stand-in."""

    def __init__(self):
        self.calls = []
        self.error = None
        self.attackers = None

    async def __call__(self, raid_id, caravan_id, leader, group, guard_ids, location_id):
        self.calls.append({"raid_id": raid_id, "caravan_id": caravan_id, "leader": leader, "group": group,
                           "guards": list(guard_ids), "location_id": location_id})
        if self.error is not None:
            raise self.error
        return {"battle_id": BATTLE, "attacker_character_ids": list(self.attackers or [leader])}


class FakeInventory:
    """caravan_raid_crud.http_post stand-in: status per call (last one repeats)."""

    def __init__(self):
        self.calls = []
        self.statuses = [200]

    def __call__(self, url, payload):
        self.calls.append((url, dict(payload)))
        status = self.statuses[min(len(self.calls), len(self.statuses)) - 1]
        if isinstance(status, Exception):
            raise status
        return SimpleNamespace(status_code=status, text="")


class FakeLaw:
    def __init__(self):
        self.calls = []

    def __call__(self, db, raid, caravan, players, *, trade_share=0, now=None):
        self.calls.append({"raid_id": int(raid.id), "caravan_id": int(caravan.id), "players": list(players),
                           "trade_share": trade_share})
        return shadow_crud.KillOutcome()


def _person(db, cid, user, location, *, npc=False, name=None):
    db.add(models.Character(id=cid, name=name or f"Игрок {cid}", user_id=user, id_subrace=1, id_class=1, id_race=1,
                            appearance="-", avatar="-", is_npc=npc, npc_role="mob" if npc else None,
                            current_location_id=location, level=5, currency_balance=0))


@pytest.fixture
def rw(world, seed_fk_data, monkeypatch):
    """The stage-1 world with a physical caravan at L_GATE1 (food, 200 units x 2 = 400 marks paid into escrow),
    raiders 501 (user 7) / 502 (user 8) / 503 (user 99) there, 504 (user 7) elsewhere, the bale items and a guard
    pool of two templates. External calls mocked: ``rw.battle``, ``rw.inventory``, ``rw.law``."""
    monkeypatch.setitem(sys.modules, "caravan_raid_crud", raids)      # stage-1 fixture hides it
    # raw-SQL Decimal binds (guard_mult) work on MySQL; pysqlite needs an adapter (scoped to the test)
    monkeypatch.setitem(sqlite3.adapters, (Decimal, sqlite3.PrepareProtocol), str)
    _exec(world, "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name VARCHAR(100), price NUMERIC, "
                 "item_type VARCHAR(30), is_stolen INTEGER NOT NULL DEFAULT 0, bale_group VARCHAR(32) NULL)")
    _exec(world, "INSERT INTO items (id, name, price, item_type, is_stolen, bale_group) VALUES "
                 "(:b, 'Тюк зерна (краденое)', 50, 'misc', 1, 'food'), (:p, 'Мешок зерна', 50, 'misc', 0, 'food')",
          b=BALE_ID, p=PLAIN_ID)
    db = world()
    try:
        seed_fk_data(db)
        with econ_ledger.allow_direct_balance_write(db):
            for cid, user, loc in ((RAIDER, USER, L_GATE1), (MATE, MATE_USER, L_GATE1),
                                   (STRANGER, OTHER_USER, L_GATE1), (FAR, USER, L_ROAD1)):
                _person(db, cid, user, loc)
            db.flush()
        for tid, level in ((TPL_HIGH, 5), (TPL_LOW, 1)):
            db.add(models.MobTemplate(id=tid, name=f"Охранник {tid}", level=level, id_race=1, id_subrace=1,
                                      id_class=1, base_attributes={"strength": 10, "max_health": 50}))
        db.flush()
        for tid in (TPL_HIGH, TPL_LOW):
            db.add(models.EconCaravanGuardTemplate(mob_template_id=tid, created_at=raids.now_utc()))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(cs_crud, "_sync_send_attributes_request", lambda cid, attrs: None)
    world.battle = FakeBattle()
    monkeypatch.setattr(battle_client, "create_caravan_raid_battle", world.battle)
    world.inventory = FakeInventory()
    monkeypatch.setattr(raids, "http_post", world.inventory)
    world.law = FakeLaw()
    monkeypatch.setattr(shadow_crud, "caravan_raid_consequences", world.law)
    _physical_world(world)
    _dispatch(world)
    world.cid = _row(world).id
    return world


def _as_user(user_id=USER, role="user", permissions=()):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username=f"u{user_id}", role=role, permissions=list(permissions))


@pytest.fixture
def api(rw, monkeypatch):
    def override_get_db():
        session = rw()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    _as_user()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _gate(f, caravan_id, character=RAIDER, location=L_GATE1, status="open"):
    _exec(f, "INSERT INTO action_gates (character_id, location_id, action_type, target_ref, status) "
             "VALUES (:c, :l, 'caravan', :t, :s)", c=character, l=location, t=caravan_id, s=status)


def _raid(f):
    r = _rows(f, "SELECT id, status, battle_id, attacker_ids, guard_ids, guard_template_id, guard_mult, marks, "
                 "bales, law_done, guards_despawned, leader_character_id, is_group, location_id, region_id, "
                 "stolen_units, stolen_value, payout_op_id FROM econ_caravan_raids")
    if not r:
        return None
    assert len(r) == 1
    keys = ("id", "status", "battle_id", "attacker_ids", "guard_ids", "guard_template_id", "guard_mult", "marks",
            "bales", "law_done", "guards_despawned", "leader", "is_group", "location_id", "region_id",
            "stolen_units", "stolen_value", "payout_op_id")
    out = dict(zip(keys, r[0]))
    for k in ("attacker_ids", "guard_ids"):
        if isinstance(out[k], str):
            out[k] = json.loads(out[k])
    return out


def _guards_alive(f):
    return _scalar(f, "SELECT COUNT(*) FROM active_mobs WHERE spawn_type = 'dungeon'")


def _start(api, f, *, group=False, attackers=None, character=RAIDER):
    _gate(f, f.cid, character)
    f.battle.attackers = attackers
    resp = api.post(_raid_url(f.cid), json={"character_id": character, "group": group})
    assert resp.status_code == 201, resp.text
    return resp.json()["raid_id"]


def _settle(api, raid_id, *, winner=0, aborted=False, battle_id=BATTLE):
    resp = api.post(RESULT, json={"battle_id": battle_id, "caravan_raid_id": raid_id, "winner_team": winner,
                                  "aborted": aborted}, headers=INTERNAL)
    assert resp.status_code == 200, resp.text
    return resp.json()["status"]


def _gold(f, cid):
    return int(_scalar(f, "SELECT currency_balance FROM characters WHERE id = :c", c=cid) or 0)


# ===================================================================================================================
# pure
# ===================================================================================================================

def test_pick_guard_template_nearest_level_ties_to_lower_id():
    pool = [(11, 5), (12, 1), (13, 9), (14, 7)]
    assert raids.pick_guard_template(pool, 6) == 11            # 5 and 7 tie -> lower id
    assert raids.pick_guard_template(pool, None) == 12
    assert raids.pick_guard_template(pool, 100) == 13
    assert raids.pick_guard_template([], 5) is None


# ===================================================================================================================
# A2: raid start
# ===================================================================================================================

def test_raid_start_spawns_hidden_guards_and_starts_the_fight(api, rw):
    raid_id = _start(api, rw)
    raid = _raid(rw)
    assert (raid["id"], raid["status"], raid["battle_id"], raid["attacker_ids"]) == (raid_id, "fighting", BATTLE,
                                                                                    [RAIDER])
    assert (raid["leader"], raid["is_group"], raid["location_id"], raid["region_id"]) == (RAIDER, 0, L_GATE1, 1)
    assert raid["guard_template_id"] == TPL_LOW                 # no recommended level -> level 1 template
    assert len(raid["guard_ids"]) == _row(rw).guard_count == 2
    assert _guards_alive(rw) == 2
    assert {r[0] for r in _rows(rw, "SELECT location_id FROM active_mobs")} == {L_GATE1}
    [call] = rw.battle.calls
    assert (call["raid_id"], call["caravan_id"], call["leader"], call["group"], call["location_id"]) == \
        (raid_id, rw.cid, RAIDER, False, L_GATE1)
    assert call["guards"] == raid["guard_ids"]
    _check(rw)                                                   # nothing paid yet


def test_raid_start_group_flag_and_battle_roster(api, rw):
    _start(api, rw, group=True, attackers=[RAIDER, MATE])
    raid = _raid(rw)
    assert raid["is_group"] == 1 and raid["attacker_ids"] == [RAIDER, MATE]
    assert rw.battle.calls[0]["group"] is True


def test_guard_template_follows_the_location_level(api, rw):
    _exec(rw, "UPDATE Locations SET recommended_level = 6 WHERE id = :l", l=L_GATE1)
    _start(api, rw)
    assert _raid(rw)["guard_template_id"] == TPL_HIGH


def test_leader_without_post_gate_is_refused_before_any_spawn(api, rw):
    _gate(rw, rw.cid, character=MATE)                            # someone else's gate does not count
    _gate(rw, rw.cid + 1)                                        # another caravan
    _gate(rw, rw.cid, status="consumed")
    before = _scalar(rw, "SELECT COUNT(*) FROM characters")
    resp = api.post(_raid_url(rw.cid), json={"character_id": RAIDER})
    assert resp.status_code == 403 and resp.json()["detail"] == raids.MSG_GATE_REQUIRED
    assert _raid(rw) is None and _guards_alive(rw) == 0
    assert _scalar(rw, "SELECT COUNT(*) FROM characters") == before          # no guard character created
    assert rw.battle.calls == []


@pytest.mark.parametrize("bs_status,detail,expected,expected_detail", [
    (409, "Персонаж уже в бою", 409, "Персонаж уже в бою"),
    (403, "Нужен боевой пост с этим караваном, чтобы напасть", 403,
     "Нужен боевой пост с этим караваном, чтобы напасть"),
    (400, {"weird": "shape"}, 400, "Налёт невозможен"),
    (500, "boom", 503, "Сервис боя недоступен — налёт не начат"),
    (502, None, 503, "Сервис боя недоступен — налёт не начат"),
    (None, None, 503, "Сервис боя недоступен — налёт не начат"),          # transport failure
])
def test_battle_service_refusal_leaves_no_trace(api, rw, bs_status, detail, expected, expected_detail):
    _gate(rw, rw.cid)
    rw.battle.error = battle_client.BattleServiceError("x", bs_status, detail)
    resp = api.post(_raid_url(rw.cid), json={"character_id": RAIDER})
    assert resp.status_code == expected and resp.json()["detail"] == expected_detail
    assert _raid(rw) is None and _guards_alive(rw) == 0
    assert len(rw.battle.calls) == 1
    # the caravan may be raided again afterwards
    rw.battle.error = None
    assert api.post(_raid_url(rw.cid), json={"character_id": RAIDER}).status_code == 201


def test_battle_client_crash_is_503_without_leftovers(api, rw):
    _gate(rw, rw.cid)
    rw.battle.error = RuntimeError("unexpected")
    resp = api.post(_raid_url(rw.cid), json={"character_id": RAIDER})
    assert resp.status_code == 503
    assert _raid(rw) is None and _guards_alive(rw) == 0


def test_guard_spawn_failure_is_500_and_removes_spawned_guards(api, rw, monkeypatch):
    real = cs_crud.spawn_mob_from_template
    calls = {"n": 0}

    def flaky(db, template_id, location_id, spawn_type="random", stat_multiplier=1.0):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("attributes down")
        return real(db, template_id, location_id, spawn_type, stat_multiplier)

    monkeypatch.setattr(cs_crud, "spawn_mob_from_template", flaky)
    _gate(rw, rw.cid)
    resp = api.post(_raid_url(rw.cid), json={"character_id": RAIDER})
    assert resp.status_code == 500 and resp.json()["detail"] == raids.MSG_GUARD_SPAWN_FAILED
    assert calls["n"] == 2
    assert _raid(rw) is None and _guards_alive(rw) == 0 and rw.battle.calls == []


def test_one_raid_per_caravan(api, rw):
    _start(api, rw)
    _gate(rw, rw.cid, character=MATE)
    _as_user(MATE_USER)
    resp = api.post(_raid_url(rw.cid), json={"character_id": MATE})
    assert resp.status_code == 409 and resp.json()["detail"] == raids.MSG_ALREADY_RAIDED
    assert len(rw.battle.calls) == 1 and _guards_alive(rw) == 2


@pytest.mark.parametrize("status", ["won", "repelled", "aborted", "expired"])
def test_finished_raid_still_blocks_a_second_raid(api, rw, status):
    raid_id = _start(api, rw)
    _exec(rw, "UPDATE econ_caravan_raids SET status = :s WHERE id = :i", s=status, i=raid_id)
    resp = api.post(_raid_url(rw.cid), json={"character_id": RAIDER})
    assert resp.status_code == 409 and resp.json()["detail"] == raids.MSG_ALREADY_RAIDED


@pytest.mark.parametrize("setup,status,detail", [
    ("unknown", 404, raids.MSG_CARAVAN_NOT_FOUND),
    ("abstract", 404, raids.MSG_CARAVAN_NOT_FOUND),
    ("delivered", 404, raids.MSG_CARAVAN_NOT_FOUND),
    ("elsewhere", 400, raids.MSG_NOT_HERE),
    ("arrived", 409, raids.MSG_ARRIVED),
    ("no_pool", 409, raids.MSG_NO_GUARDS),
])
def test_raid_start_refusals(api, rw, setup, status, detail):
    cid = rw.cid
    _gate(rw, cid)
    if setup == "unknown":
        cid = 987654
    elif setup == "abstract":
        _exec(rw, "UPDATE econ_caravans SET is_physical = 0")
    elif setup == "delivered":
        _exec(rw, "UPDATE econ_caravans SET status = 'delivered'")
    elif setup == "elsewhere":
        _exec(rw, "UPDATE econ_caravans SET current_location_id = :l", l=L_ROAD1)
    elif setup == "arrived":
        _exec(rw, "UPDATE econ_caravans SET arrived_at = :t", t=raids.now_utc())
    elif setup == "no_pool":
        _exec(rw, "DELETE FROM econ_caravan_guard_templates")
    resp = api.post(_raid_url(cid), json={"character_id": RAIDER})
    assert resp.status_code == status and resp.json()["detail"] == detail
    assert _raid(rw) is None and _guards_alive(rw) == 0 and rw.battle.calls == []


def test_character_in_another_location_cannot_raid(api, rw):
    _gate(rw, rw.cid, character=FAR)
    resp = api.post(_raid_url(rw.cid), json={"character_id": FAR})
    assert resp.status_code == 400 and resp.json()["detail"] == raids.MSG_NOT_HERE


def test_npc_cannot_begin_a_raid(rw):
    db = rw()
    try:
        _person(db, 600, None, L_GATE1, npc=True)
        db.commit()
        with pytest.raises(raids.EconomyApiError) as exc:
            raids.begin_raid(db, rw.cid, 600, False)
        assert exc.value.status_code == 400
    finally:
        db.close()


def test_raid_start_auth_and_ownership(api, rw):
    _gate(rw, rw.cid, character=STRANGER)
    resp = api.post(_raid_url(rw.cid), json={"character_id": STRANGER})        # user 7 -> user 99's character
    assert resp.status_code == 403
    assert api.post(_raid_url(rw.cid), json={"character_id": 777777}).status_code == 404
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert api.post(_raid_url(rw.cid), json={"character_id": RAIDER}).status_code == 401
    assert _raid(rw) is None and rw.battle.calls == []


@pytest.mark.parametrize("path,body", [
    ("1", {"character_id": "501"}),                                   # strict int
    ("1", {"character_id": 0}),
    ("1", {"character_id": RAIDER, "extra": 1}),
    ("1", {}),
    ("0", {"character_id": RAIDER}),
    ("1; DROP TABLE econ_caravans", {"character_id": RAIDER}),
    ("1", {"character_id": "501 OR 1=1"}),
])
def test_raid_start_validation(api, rw, path, body):
    resp = api.post(f"/characters/caravans/{path}/raid", json=body)
    assert resp.status_code == 422
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravans") == 1 and _raid(rw) is None


# ===================================================================================================================
# A3 / settlement
# ===================================================================================================================

def test_won_raid_pays_escrow_share_and_bales(api, rw, stub_law_notify_send):
    raid_id = _start(api, rw, attackers=[MATE, RAIDER])
    escrow = _balance(rw, "caravan_escrow", 0)
    assert escrow == 400
    assert _settle(api, raid_id, winner=0) == "won"
    raid = _raid(rw)
    # marks floor(400 x 0.2) = 80, split 40 / 40; units 200 x 0.3 = 60 -> value 120 -> 2 bales of 50, round-robin
    assert (raid["status"], raid["marks"], raid["bales"], raid["stolen_value"]) == ("won", 80, 2, 120)
    assert Decimal(str(raid["stolen_units"])) == Decimal("60")
    assert (_gold(rw, RAIDER), _gold(rw, MATE)) == (40, 40)
    assert _balance(rw, "caravan_escrow", 0) == 320
    row = _row(rw)
    assert (row.raid_paid, Decimal(str(row.stolen_units))) == (80, Decimal("60"))
    _check(rw)
    [(op_id, key, region, meta)] = _rows(rw, "SELECT id, idempotency_key, region_id, metadata FROM econ_operations "
                                             "WHERE op_type = 'caravan_raid'")
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert (key, region, raid["payout_op_id"]) == (f"caravan:c{rw.cid}:raid", 1, op_id)
    assert (meta["raid_id"], meta["battle_id"], meta["bales"], meta["group_code"]) == (raid_id, BATTLE, 2, "food")
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_postings WHERE operation_id = :o AND leg_type = 'tax'", o=op_id) == 0
    shares = _rows(rw, "SELECT character_id, marks, bales, bale_item_id FROM econ_caravan_raid_shares ORDER BY "
                       "character_id")
    assert shares == [(RAIDER, 40, 1, BALE_ID), (MATE, 40, 1, BALE_ID)]
    logs = _rows(rw, "SELECT character_id, description FROM character_logs WHERE event_type = 'caravan_raid' "
                     "ORDER BY character_id")
    assert [c for c, _d in logs] == [RAIDER, MATE]
    assert "40 марок" in logs[0][1] and "Тюк зерна (краденое)" in logs[0][1]
    # notices to both players' users
    sent = [p for call in stub_law_notify_send.call_args_list for p in call.args[0]]
    wins = {p["target_value"]: p["message"] for p in sent if p["ws_type"] == "caravan_raid"}
    assert set(wins) == {USER, MATE_USER} and wins[USER].startswith("Налёт удался: 40 марок")
    # law step, bales, guards
    assert rw.law.calls == [{"raid_id": raid_id, "caravan_id": rw.cid, "players": [RAIDER, MATE],
                             "trade_share": _params(rw).caravan_rep_trade_share}]
    assert raid["law_done"] == 1
    assert sorted((u.rsplit("/", 2)[-2], p["item_id"], p["quantity"]) for u, p in rw.inventory.calls) == \
        [(str(RAIDER), BALE_ID, 1), (str(MATE), BALE_ID, 1)]
    assert all(u.endswith("/items") and "/internal/characters/" in u for u, _p in rw.inventory.calls)
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_raid_shares WHERE bales_delivered_at IS NULL") == 0
    assert raid["guards_despawned"] == 1 and _guards_alive(rw) == 0
    # released: moves on with the rest
    assert row.next_move_at is not None and row.next_move_at > raids.now_utc() - timedelta(minutes=1)


def test_won_raid_remainder_to_leader_and_npc_attackers_get_nothing(api, rw):
    _set_params(rw, caravan_raid_marks_share=0.2025)                           # floor(81) -> 41 / 40
    _exec(rw, "UPDATE items SET price = 20 WHERE id = :i", i=BALE_ID)           # 120 / 20 = 6 bales
    raid_id = _start(api, rw, attackers=[MATE, 600, RAIDER])
    db = rw()
    try:
        _person(db, 600, None, L_GATE1, npc=True)
        db.commit()
    finally:
        db.close()
    assert _settle(api, raid_id) == "won"
    assert (_gold(rw, RAIDER), _gold(rw, MATE), _gold(rw, 600)) == (41, 40, 0)
    assert _rows(rw, "SELECT character_id, marks, bales FROM econ_caravan_raid_shares ORDER BY character_id") == \
        [(RAIDER, 41, 3), (MATE, 40, 3)]
    _check(rw)


def test_won_raid_without_bale_item_pays_only_marks(api, rw):
    _exec(rw, "DELETE FROM items WHERE id = :i", i=BALE_ID)
    raid_id = _start(api, rw)
    assert _settle(api, raid_id) == "won"
    raid = _raid(rw)
    assert (raid["marks"], raid["bales"]) == (80, 0) and _gold(rw, RAIDER) == 80
    assert rw.inventory.calls == []
    _check(rw)


@pytest.mark.parametrize("winner,aborted,expected", [(1, False, "repelled"), (None, False, "repelled"),
                                                     (0, True, "aborted"), (None, True, "aborted")])
def test_lost_or_aborted_raid_changes_nothing(api, rw, stub_law_notify_send, winner, aborted, expected):
    raid_id = _start(api, rw)
    stub_law_notify_send.reset_mock()
    assert _settle(api, raid_id, winner=winner, aborted=aborted) == expected
    raid = _raid(rw)
    assert (raid["status"], raid["marks"], raid["bales"], raid["law_done"]) == (expected, 0, 0, 0)
    assert _gold(rw, RAIDER) == 0 and _balance(rw, "caravan_escrow", 0) == 400
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'caravan_raid'") == 0
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_raid_shares") == 0
    assert rw.law.calls == [] and rw.inventory.calls == []
    assert raid["guards_despawned"] == 1 and _guards_alive(rw) == 0
    assert (_row(rw).raid_paid, Decimal(str(_row(rw).stolen_units))) == (0, Decimal("0"))
    assert stub_law_notify_send.called is (expected == "repelled")
    _check(rw)


def test_duplicate_callback_is_already_and_pays_once(api, rw):
    raid_id = _start(api, rw)
    assert _settle(api, raid_id) == "won"
    assert _settle(api, raid_id) == "already"
    assert _settle(api, raid_id, winner=1) == "already"
    assert _gold(rw, RAIDER) == 80
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'caravan_raid'") == 1
    assert len(rw.law.calls) == 1 and len(rw.inventory.calls) == 1
    _check(rw)


def test_result_of_another_battle_is_ignored(api, rw):
    raid_id = _start(api, rw)
    assert _settle(api, raid_id, battle_id=BATTLE + 1) == "already"
    assert _raid(rw)["status"] == "fighting" and _gold(rw, RAIDER) == 0


def test_unknown_raid_answers_unknown(api, rw):
    assert _settle(api, 424242) == "unknown"


def test_callback_for_a_starting_raid_adopts_the_battle(rw):
    db = rw()
    try:
        db.add(models.EconCaravanRaid(caravan_id=rw.cid, leader_character_id=RAIDER, location_id=L_GATE1,
                                      region_id=1, status="starting", created_at=raids.now_utc()))
        db.commit()
        raid_id = db.query(models.EconCaravanRaid.id).scalar()
        assert raids.battle_result(db, battle_id=BATTLE, raid_id=raid_id, winner_team=0, aborted=False) == "won"
    finally:
        db.close()
    raid = _raid(rw)
    assert (raid["battle_id"], raid["attacker_ids"]) == (BATTLE, [RAIDER])     # leader takes it all
    assert _gold(rw, RAIDER) == 80
    _check(rw)


def test_a3_internal_token_and_validation(api, rw):
    body = {"battle_id": BATTLE, "caravan_raid_id": 1, "winner_team": 0, "aborted": False}
    assert api.post(RESULT, json=body).status_code == 401
    assert api.post(RESULT, json=body, headers={"X-Internal-Token": "wrong"}).status_code == 401
    for bad in ({**body, "caravan_raid_id": 0}, {**body, "battle_id": "x"},
                {**body, "caravan_raid_id": "1 OR 1=1"}, {"battle_id": BATTLE}):
        assert api.post(RESULT, json=bad, headers=INTERNAL).status_code == 422


def test_settlement_after_raid_then_delivery_pays_the_rest(api, rw):
    """Raid 80 of 400 escrow -> the seller gets only 320 on arrival; goods minus stolen units arrive."""
    raid_id = _start(api, rw)
    _settle(api, raid_id)
    seller = _balance(rw, "population_purse", 1)
    _exec(rw, "UPDATE econ_caravans SET route_index = 3, current_location_id = :l, arrived_at = :t, "
              "next_move_at = NULL", l=L_GATE2, t=raids.now_utc())
    import economy_caravan_crud
    assert economy_caravan_crud.deliver_physical_tx(rw, rw.cid, raids.now_utc()).status == "delivered"
    assert _balance(rw, "population_purse", 1) == seller + 320
    assert _balance(rw, "caravan_escrow", 0) == 0
    _check(rw)


# ===================================================================================================================
# bales retry, guard despawn, follow-ups
# ===================================================================================================================

def test_bales_retried_after_transport_error_and_5xx(api, rw):
    import httpx
    rw.inventory.statuses = [httpx.ConnectError("down"), 503, 200]
    raid_id = _start(api, rw, attackers=[RAIDER, MATE])
    _settle(api, raid_id)                                                        # call 1 (error), call 2 (503)
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_raid_shares WHERE bales_delivered_at IS NULL") == 2
    later = raids.now_utc() + timedelta(minutes=5)
    assert raids.raid_followups(rw, later, _params(rw)) == 2                     # both delivered now
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_raid_shares WHERE bales_delivered_at IS NULL") == 0
    assert raids.raid_followups(rw, later, _params(rw)) == 0                     # nothing left
    assert len(rw.inventory.calls) == 4


def test_fresh_undelivered_bales_are_left_to_the_callback(api, rw):
    rw.inventory.statuses = [503]
    raid_id = _start(api, rw)
    _settle(api, raid_id)
    raids.raid_followups(rw, raids.now_utc() - timedelta(minutes=5), _params(rw))
    assert len(rw.inventory.calls) == 1


def test_bales_refused_for_good_stop_retrying(api, rw):
    rw.inventory.statuses = [404]
    raid_id = _start(api, rw)
    _settle(api, raid_id)
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_raid_shares WHERE bales_delivered_at IS NULL") == 0
    raids.raid_followups(rw, raids.now_utc() + timedelta(minutes=5), _params(rw))
    assert len(rw.inventory.calls) == 1


def test_followups_redo_the_law_step_and_despawn(api, rw, monkeypatch):
    raid_id = _start(api, rw)

    def broken(*a, **kw):
        raise RuntimeError("law down")

    real_despawn = cs_crud.despawn_dungeon_mobs
    monkeypatch.setattr(shadow_crud, "caravan_raid_consequences", broken)
    monkeypatch.setattr(cs_crud, "despawn_dungeon_mobs", lambda db, ids: (_ for _ in ()).throw(RuntimeError("x")))
    assert _settle(api, raid_id) == "won"                                        # payout stays, steps retried
    raid = _raid(rw)
    assert (raid["status"], raid["law_done"], raid["guards_despawned"]) == ("won", 0, 0)
    assert _guards_alive(rw) == 2
    monkeypatch.setattr(shadow_crud, "caravan_raid_consequences", rw.law)
    monkeypatch.setattr(cs_crud, "despawn_dungeon_mobs", real_despawn)
    assert raids.raid_followups(rw, raids.now_utc(), _params(rw)) >= 2
    raid = _raid(rw)
    assert (raid["law_done"], raid["guards_despawned"]) == (1, 1) and _guards_alive(rw) == 0
    assert len(rw.law.calls) == 1
    assert raids.law_step(rw(), raid_id) is None                                 # claimed once
    assert _gold(rw, RAIDER) == 80


# ===================================================================================================================
# caravan pass hooks: stale / poll / expire
# ===================================================================================================================

def _insert_raid(f, status, *, created, started=None, battle_id=None, guard_ids=None):
    db = f()
    try:
        raid = models.EconCaravanRaid(caravan_id=f.cid, leader_character_id=RAIDER, location_id=L_GATE1, region_id=1,
                                      status=status, created_at=created, started_at=started, battle_id=battle_id,
                                      attacker_ids=[RAIDER] if status == "fighting" else None,
                                      guard_ids=guard_ids)
        db.add(raid)
        db.commit()
        return int(raid.id)
    finally:
        db.close()


def _spawn_guard(f):
    db = f()
    try:
        _mob, ch = cs_crud.spawn_mob_from_template(db, TPL_LOW, L_GATE1, "dungeon")
        return int(ch.id)
    finally:
        db.close()


def test_stale_starting_raid_is_removed_with_its_guards(rw):
    now = raids.now_utc()
    guard = _spawn_guard(rw)
    _insert_raid(rw, "starting", created=now - timedelta(minutes=11), guard_ids=[guard])
    assert raids.expire_stale_raids(rw, now, _params(rw)) == 1
    assert _raid(rw) is None and _guards_alive(rw) == 0


def test_fresh_starting_raid_is_kept(rw):
    now = raids.now_utc()
    _insert_raid(rw, "starting", created=now - timedelta(minutes=5))
    assert raids.expire_stale_raids(rw, now, _params(rw)) == 0
    assert _raid(rw)["status"] == "starting"


def test_lost_tx_b_is_reattached_through_the_tagged_battle(rw):
    now = raids.now_utc()
    raid_id = _insert_raid(rw, "starting", created=now - timedelta(minutes=11))
    _exec(rw, "CREATE TABLE IF NOT EXISTS battles (id INTEGER PRIMARY KEY, status VARCHAR(20), "
              "caravan_raid_id INTEGER NULL)")
    _exec(rw, "INSERT INTO battles (id, status, caravan_raid_id) VALUES (:b, 'in_progress', :r)", b=BATTLE, r=raid_id)
    assert raids.expire_stale_raids(rw, now, _params(rw)) == 0
    raid = _raid(rw)
    assert (raid["status"], raid["battle_id"]) == ("fighting", BATTLE)


@pytest.mark.parametrize("answer,expected,gold", [
    ({"status": "finished", "winner_team": 0}, "won", 80),
    ({"status": "forfeit", "winner_team": 1}, "repelled", 0),
    ({"status": "finished", "winner_team": None, "aborted": True}, "aborted", 0),
    (battle_client.BATTLE_NOT_FOUND, "aborted", 0),
    ({"status": "in_progress"}, "fighting", 0),
    (battle_client.BattleServiceError("down"), "fighting", 0),
])
def test_poll_settles_lost_callbacks(rw, monkeypatch, answer, expected, gold):
    now = raids.now_utc()
    _insert_raid(rw, "fighting", created=now - timedelta(minutes=10), started=now - timedelta(minutes=3),
                 battle_id=BATTLE)

    def fake(battle_id):
        assert battle_id == BATTLE
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(battle_client, "get_battle_result", fake)
    done = raids.poll_raid_battles(rw, now, _params(rw))
    assert done == (0 if expected == "fighting" else 1)
    assert _raid(rw)["status"] == expected and _gold(rw, RAIDER) == gold
    _check(rw)


def test_poll_skips_raids_started_less_than_two_minutes_ago(rw, monkeypatch):
    now = raids.now_utc()
    _insert_raid(rw, "fighting", created=now, started=now - timedelta(minutes=1), battle_id=BATTLE)
    monkeypatch.setattr(battle_client, "get_battle_result", lambda b: pytest.fail("must not poll"))
    assert raids.poll_raid_battles(rw, now, _params(rw)) == 0


@pytest.mark.parametrize("answer", [{"status": "in_progress"}, battle_client.BattleServiceError("down")])
def test_raid_battle_running_too_long_expires_without_loot(api, rw, monkeypatch, answer):
    now = raids.now_utc()
    started = now - timedelta(hours=int(_params(rw).caravan_raid_battle_max_hours), minutes=1)
    raid_id = _insert_raid(rw, "fighting", created=started, started=started, battle_id=BATTLE)

    def fake(_b):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(battle_client, "get_battle_result", fake)
    assert raids.poll_raid_battles(rw, now, _params(rw)) == 1
    assert _raid(rw)["status"] == "expired" and _gold(rw, RAIDER) == 0
    assert _row(rw).next_move_at > now                                         # caravan released
    # a late "won" callback finds the raid expired: nothing paid
    assert _settle(api, raid_id, winner=0) == "already"
    assert _gold(rw, RAIDER) == 0 and _raid(rw)["guards_despawned"] == 1
    _check(rw)


# ===================================================================================================================
# A1: caravans here
# ===================================================================================================================

def test_a1_key_whitelist_never_leaks_route_or_value(api, rw):
    resp = api.get(HERE, params={"character_id": RAIDER})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"location_id", "caravans"} and body["location_id"] == L_GATE1
    [c] = body["caravans"]
    assert set(c) == A1_KEYS
    assert (c["id"], c["group_code"], c["guard_count"], c["state"], c["can_attack"], c["reason"]) == \
        (rw.cid, "food", 2, "on_road", True, None)
    assert c["group_name"] and isinstance(c["departs_in_sec"], int) and c["departs_in_sec"] >= 0
    for leak in ("route", "value", "from", "to_", "region", "Застава Оста", "Тракт", "Перевал", "paid", "unit"):
        assert leak not in resp.text


def test_a1_states(api, rw):
    def state():
        [c] = api.get(HERE, params={"character_id": RAIDER}).json()["caravans"]
        return c["state"], c["can_attack"], c["reason"], c["departs_in_sec"]

    _gate(rw, rw.cid)
    assert state() == ("held", True, None, None)
    raid_id = _start(api, rw)
    assert state() == ("under_attack", False, raids.MSG_UNDER_ATTACK, None)
    _settle(api, raid_id)
    assert state() == ("raided", False, raids.MSG_ALREADY_RAIDED, None)


def test_a1_without_guard_pool_cannot_attack(api, rw):
    _exec(rw, "DELETE FROM econ_caravan_guard_templates")
    [c] = api.get(HERE, params={"character_id": RAIDER}).json()["caravans"]
    assert (c["can_attack"], c["reason"]) == (False, raids.MSG_NO_GUARDS)


@pytest.mark.parametrize("setup", ["elsewhere", "abstract", "arrived", "delivered"])
def test_a1_shows_only_physical_caravans_on_the_road_here(api, rw, setup):
    character = RAIDER
    if setup == "elsewhere":
        character = FAR
    elif setup == "abstract":
        _exec(rw, "UPDATE econ_caravans SET is_physical = 0")
    elif setup == "arrived":
        _exec(rw, "UPDATE econ_caravans SET arrived_at = :t", t=raids.now_utc())
    else:
        _exec(rw, "UPDATE econ_caravans SET status = 'delivered'")
    body = api.get(HERE, params={"character_id": character}).json()
    assert body["caravans"] == []


def test_a1_auth_ownership_and_validation(api, rw):
    assert api.get(HERE, params={"character_id": STRANGER}).status_code == 403
    assert api.get(HERE, params={"character_id": 777777}).status_code == 404
    for bad in ("abc", "0", "501 OR 1=1", "501; DROP TABLE econ_caravans; --"):
        assert api.get(HERE, params={"character_id": bad}).status_code == 422
    assert api.get(HERE).status_code == 422
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert api.get(HERE, params={"character_id": RAIDER}).status_code == 401
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravans") == 1


# ===================================================================================================================
# own loot by battle (the battle victory window)
# ===================================================================================================================

def _share_url(battle_id=BATTLE):
    return f"/characters/caravans/raids/by-battle/{battle_id}"


def test_share_is_pending_until_the_settlement_then_shows_own_loot(api, rw, stub_law_notify_send):
    raid_id = _start(api, rw, attackers=[MATE, RAIDER])
    resp = api.get(_share_url(), params={"character_id": RAIDER})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"raid": True, "status": "pending", "marks": 0, "bales": 0, "bale_name": None}
    assert _settle(api, raid_id, winner=0) == "won"
    assert api.get(_share_url(), params={"character_id": RAIDER}).json() == {
        "raid": True, "status": "won", "marks": 40, "bales": 1, "bale_name": "Тюк зерна (краденое)"}
    _as_user(MATE_USER)
    assert api.get(_share_url(), params={"character_id": MATE}).json()["marks"] == 40


def test_share_of_a_repelled_raid_has_no_loot(api, rw, stub_law_notify_send):
    raid_id = _start(api, rw)
    assert _settle(api, raid_id, winner=1) == "repelled"
    assert api.get(_share_url(), params={"character_id": RAIDER}).json() == {
        "raid": True, "status": "repelled", "marks": 0, "bales": 0, "bale_name": None}


def test_share_is_not_a_raid_for_other_battles_and_outsiders(api, rw, stub_law_notify_send):
    none = {"raid": False, "status": None, "marks": 0, "bales": 0, "bale_name": None}
    assert api.get(_share_url(), params={"character_id": RAIDER}).json() == none          # no raid at all
    raid_id = _start(api, rw)
    assert _settle(api, raid_id, winner=0) == "won"
    assert api.get(_share_url(BATTLE + 1), params={"character_id": RAIDER}).json() == none  # another battle
    _as_user(OTHER_USER)
    assert api.get(_share_url(), params={"character_id": STRANGER}).json() == none          # not a raider


def test_share_auth_ownership_and_validation(api, rw):
    assert api.get(_share_url(), params={"character_id": STRANGER}).status_code == 403
    assert api.get(_share_url(), params={"character_id": 777777}).status_code == 404
    for bad in ("abc", "0", "501 OR 1=1"):
        assert api.get(_share_url(), params={"character_id": bad}).status_code == 422
    assert api.get("/characters/caravans/raids/by-battle/0", params={"character_id": RAIDER}).status_code == 422
    assert api.get(_share_url()).status_code == 422
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert api.get(_share_url(), params={"character_id": RAIDER}).status_code == 401


# ===================================================================================================================
# law: shadow_crud.caravan_raid_consequences in the law world
# ===================================================================================================================

from tests.law_world import law_world, wanted  # noqa: E402,F401
from tests.reputation_world import (  # noqa: E402,F401
    ALPHA, BETA, R_DUNY, R_HOLMY, R_OST, R_PASHNI, exec_, log_rows, q, rep_world, value, values,
)
from tests.shadow_world import (  # noqa: E402
    crimes, give_mask, no_roll, renown, set_marker, set_roll, shadow_settings, suspicion,
)

REAL_CONSEQUENCES = shadow_crud.caravan_raid_consequences
L_MARKET, L_POST, L_ROAD = 100, 101, 103          # law world: market (guards 52/54), post (guard 60), road (none)
SEEN, UNSEEN = 0.0, 0.9999


def _consequences(f, players, *, location=L_ROAD, from_region=R_DUNY, to_region=R_PASHNI, trade_share=0.5,
                  raid_id=7):
    raid = SimpleNamespace(id=raid_id, location_id=location, region_id=None, battle_id=BATTLE)
    caravan = SimpleNamespace(id=3, from_region_id=from_region, to_region_id=to_region)
    db = f()
    try:
        out = REAL_CONSEQUENCES(db, raid, caravan, players, trade_share=trade_share)
        db.commit()
        return out
    finally:
        db.close()


@pytest.fixture
def lw(law_world):
    set_marker(law_world, L_ROAD, "farm")                       # base 70 (a settlement is always seen)
    return law_world


def _own_rep(f, cid, region):
    """Non-echo reputation log rows of a region: (action, applied delta)."""
    return [(r[2], r[7]) for r in log_rows(f, cid) if r[1] == region and not r[4]]


def test_witnessed_raid_hits_raid_seller_and_buyer_regions(lw, monkeypatch):
    set_roll(monkeypatch, SEEN)
    out = _consequences(lw, [ALPHA])
    [c] = crimes(lw, ALPHA)
    assert (c["crime_type"], c["status"], c["region_id"], c["wanted_points"]) == ("caravan_attack", "reported",
                                                                                  R_OST, 100)
    assert c["reputation_key"] == "caravan_raid:7:1" and c["event_key"] == "crime:caravan_raid:7:1"
    assert wanted(lw, ALPHA, R_OST) and wanted(lw, ALPHA, R_OST) > 0
    assert _own_rep(lw, ALPHA, R_OST) == [("caravan_attack", -100)]
    assert _own_rep(lw, ALPHA, R_DUNY) == [("caravan_attack", -50)]               # seller, other country
    assert _own_rep(lw, ALPHA, R_PASHNI) == [("caravan_attack", -50)]             # buyer
    assert value(lw, ALPHA, R_DUNY) == -50
    assert renown(lw, ALPHA)[1] > 0                                               # infamy
    assert out.wanted_changes


def test_trade_regions_are_distinct_and_skip_the_raid_region(lw, monkeypatch):
    set_roll(monkeypatch, SEEN)
    _consequences(lw, [ALPHA], from_region=R_OST, to_region=R_OST)
    assert _own_rep(lw, ALPHA, R_OST) == [("caravan_attack", -100)]
    assert [r for r in log_rows(lw, ALPHA) if not r[4]] and len([r for r in log_rows(lw, ALPHA) if not r[4]]) == 1


def test_trade_share_zero_and_deleted_region(lw, monkeypatch):
    set_roll(monkeypatch, SEEN)
    _consequences(lw, [ALPHA], trade_share=0)
    assert _own_rep(lw, ALPHA, R_DUNY) == [] and _own_rep(lw, ALPHA, R_PASHNI) == []
    _consequences(lw, [BETA], from_region=9999, to_region=R_PASHNI, raid_id=8)   # seller region gone
    assert _own_rep(lw, BETA, R_PASHNI) == [("caravan_attack", -50)]


def test_unseen_raid_is_deferred_without_reputation(lw, monkeypatch, stub_law_notify_send):
    set_roll(monkeypatch, UNSEEN)
    out = _consequences(lw, [ALPHA])
    [c] = crimes(lw, ALPHA)
    assert c["status"] == "unwitnessed" and c["reputation_delta"] == -100
    assert log_rows(lw, ALPHA) == [] and wanted(lw, ALPHA, R_OST) in (None, 0)
    assert renown(lw, ALPHA)[1] > 0                                               # infamy even unseen
    assert suspicion(lw, R_OST)
    assert out.notices and out.notices[0].user_id == 7


def test_masked_raider_is_deferred_even_when_seen(lw, monkeypatch):
    give_mask(lw, ALPHA)
    set_roll(monkeypatch, SEEN)
    _consequences(lw, [ALPHA, BETA])                                              # one roll for the group
    by = {c["character_id"]: c for c in crimes(lw)}
    assert by[ALPHA]["status"] == "masked" and bool(by[ALPHA]["masked"])
    assert by[BETA]["status"] == "reported"
    assert _own_rep(lw, ALPHA, R_OST) == [] and _own_rep(lw, BETA, R_OST) == [("caravan_attack", -100)]
    assert _own_rep(lw, ALPHA, R_DUNY) == []                                      # deferred: no seller / buyer


@pytest.mark.parametrize("location", [L_MARKET, L_POST])
def test_city_guards_at_the_location_force_witnesses(lw, monkeypatch, location):
    set_marker(lw, location, "dangerous")
    give_mask(lw, ALPHA)                                                          # the mask does not help
    no_roll(monkeypatch)
    _consequences(lw, [ALPHA], location=location)
    [c] = crimes(lw, ALPHA)
    assert c["status"] == "reported" and c["witness_roll_pct"] is None
    assert _own_rep(lw, ALPHA, R_OST) == [("caravan_attack", -100)]


def test_unconscious_guards_do_not_force(lw, monkeypatch):
    exec_(lw, "UPDATE characters SET unconscious_until = :t WHERE id = 60", t=raids.now_utc() + timedelta(hours=1))
    set_marker(lw, L_POST, "farm")
    set_roll(monkeypatch, UNSEEN)
    _consequences(lw, [ALPHA], location=L_POST)
    assert crimes(lw, ALPHA)[0]["status"] == "unwitnessed"


def test_witness_switch_off_forces(lw, monkeypatch):
    shadow_settings(lw, witness_enabled=False)
    no_roll(monkeypatch)
    _consequences(lw, [ALPHA])
    assert crimes(lw, ALPHA)[0]["status"] == "reported"


def test_admin_severity_and_harmless_raid(lw, monkeypatch):
    set_roll(monkeypatch, SEEN)
    exec_(lw, "INSERT INTO reputation_actions (code, name, points, is_builtin, has_source, sort_order) "
              "VALUES ('caravan_attack', 'Нападение на караван', -40, 1, 1, 50)")
    _consequences(lw, [ALPHA])
    [c] = crimes(lw, ALPHA)
    assert (c["wanted_points"], c["reputation_delta"]) == (40, -40)
    assert _own_rep(lw, ALPHA, R_DUNY) == [("caravan_attack", -20)]
    exec_(lw, "UPDATE reputation_actions SET points = 0 WHERE code = 'caravan_attack'")
    _consequences(lw, [BETA], raid_id=8)
    assert crimes(lw, BETA) == [] and log_rows(lw, BETA) == []


def test_npcs_and_repeats_are_ignored(lw, monkeypatch):
    set_roll(monkeypatch, SEEN)
    assert _consequences(lw, [52, 50]).wanted_changes == [] and crimes(lw) == []
    _consequences(lw, [ALPHA])
    _consequences(lw, [ALPHA])
    assert len(crimes(lw, ALPHA)) == 1 and len(_own_rep(lw, ALPHA, R_OST)) == 1
    assert len(_own_rep(lw, ALPHA, R_DUNY)) == 1


def test_reveal_of_a_deferred_raid_uses_the_caravan_action(lw, monkeypatch):
    set_roll(monkeypatch, UNSEEN)
    _consequences(lw, [ALPHA])
    [c] = crimes(lw, ALPHA)
    db = lw()
    try:
        assert shadow_crud.reveal_crime(db, c["id"]) is not None
        db.commit()
    finally:
        db.close()
    assert crimes(lw, ALPHA)[0]["status"] == "reported"
    assert _own_rep(lw, ALPHA, R_OST) == [("caravan_attack", -100)]
    assert wanted(lw, ALPHA, R_OST) > 0
    assert _own_rep(lw, ALPHA, R_DUNY) == []                                      # accepted simplification


# ===================================================================================================================
# FEAT-212 QA (#10): raids on caravans with player escorts (features/FEAT-212 §3.9, §3.10 raid)
# ===================================================================================================================

import asyncio  # noqa: E402

import activity_lock  # noqa: E402
import caravan_escort_crud as escort_crud  # noqa: E402
import faction_core  # noqa: E402
import faction_kills  # noqa: E402
from faction_crud import FlowResult  # noqa: E402

E1, E2, E3, E4, E5 = 511, 512, 513, 514, 515
ESCORT_USERS = {E1: 21, E2: 22, E3: 23, E4: 24, E5: 25}


class EscortBattle(FakeBattle):
    """B1 stand-in that also takes ``escort_character_ids``: answers the sent escorts as placed (``placed`` overrides,
    ``old_bs`` omits the field like a pre-FEAT-212 battle-service)."""

    def __init__(self):
        super().__init__()
        self.kwargs = []
        self.placed = None
        self.old_bs = False

    async def __call__(self, raid_id, caravan_id, leader, group, guard_ids, location_id, **kwargs):
        self.kwargs.append(dict(kwargs))
        out = await super().__call__(raid_id, caravan_id, leader, group, guard_ids, location_id)
        if not self.old_bs:
            sent = kwargs.get("escort_character_ids", [])
            out["escort_character_ids"] = list(sent if self.placed is None else self.placed)
        return out


class FakeDeeds:
    def __init__(self):
        self.calls = []
        self.error = None

    def __call__(self, db, character_id, kind, event_key, now=None):
        self.calls.append((int(character_id), kind, event_key))
        if self.error is not None:
            raise self.error
        return FlowResult(data={"applied": [1]})


@pytest.fixture
def erw(api, rw, monkeypatch):
    """The raid world + five escort-capable players at L_GATE1, an escort-aware B1 stand-in, faction deeds mocked."""
    db = rw()
    try:
        with econ_ledger.allow_direct_balance_write(db):
            for cid, user in ESCORT_USERS.items():
                _person(db, cid, user, L_GATE1)
            db.commit()
    finally:
        db.close()
    rw.battle = EscortBattle()
    monkeypatch.setattr(battle_client, "create_caravan_raid_battle", rw.battle)
    rw.deeds = FakeDeeds()
    monkeypatch.setattr(faction_kills, "apply_caravan_deed", rw.deeds)
    return rw


def _hire_escorts(f, *cids):
    for cid in cids:
        _exec(f, "INSERT INTO econ_caravan_escorts (caravan_id, character_id, status, hire_location_id, in_raid, fee, "
                 "bonus, rewards_done, joined_at) VALUES (:car, :c, 'active', :l, 0, 0, 0, 0, :t)",
              car=f.cid, c=cid, l=L_GATE1, t=raids.now_utc())
        _exec(f, "UPDATE characters SET escort_caravan_id = :car WHERE id = :c", car=f.cid, c=cid)


def _escorts(f):
    return {int(r[0]): (r[1], int(r[2] or 0)) for r in _rows(f, "SELECT character_id, status, in_raid "
                                                               "FROM econ_caravan_escorts")}


def _escort_ids(f):
    v = _scalar(f, "SELECT escort_ids FROM econ_caravan_raids")
    return json.loads(v) if isinstance(v, str) else v


def _col(f, cid):
    return _scalar(f, "SELECT escort_caravan_id FROM characters WHERE id = :c", c=cid)


def _settle_f(api, raid_id, *, winner=0, aborted=False, fallen=None):
    body = {"battle_id": BATTLE, "caravan_raid_id": raid_id, "winner_team": winner, "aborted": aborted}
    if fallen is not None:
        body["fallen_character_ids"] = fallen
    resp = api.post(RESULT, json=body, headers=INTERNAL)
    assert resp.status_code == 200, resp.text
    return resp.json()["status"]


def _escort_notices(stub):
    return {(p["target_value"], p["message"]) for call in stub.call_args_list for p in call.args[0]
            if p["ws_type"] == escort_crud.WS_CARAVAN_ESCORT}


def _escort_logs(f):
    return {(int(c), d) for c, d in _rows(f, "SELECT character_id, description FROM character_logs "
                                             "WHERE event_type = :e", e=escort_crud.LOG_EVENT_TYPE)}


# ---- raid start ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("guards,escorts,mobs", [
    (2, 0, 2), (2, 1, 2), (5, 2, 3), (3, 3, 2), (5, 4, 1), (5, 5, 1),
])
def test_escorts_reduce_the_guard_mobs(erw, api, guards, escorts, mobs):
    _exec(erw, "UPDATE econ_caravans SET guard_count = :g", g=guards)
    team = list(ESCORT_USERS)[:escorts]
    _hire_escorts(erw, *team)
    _start(api, erw)
    raid = _raid(erw)
    assert len(raid["guard_ids"]) == _guards_alive(erw) == mobs
    [kw] = erw.battle.kwargs
    if escorts:
        assert kw == {"escort_character_ids": team[:4]}                 # asc id, at most 4 (one mob always stays)
    else:
        assert kw == {}                                                  # exactly the FEAT-211 call
    assert len(raid["guard_ids"]) + len(kw.get("escort_character_ids", [])) <= raids.MAX_GUARDS
    assert _escort_ids(erw) == team[:4]


def test_placed_escorts_are_the_answer_intersected_with_the_sent_ones(erw, api):
    _hire_escorts(erw, E1, E2)
    erw.battle.placed = [E2, 9999]                                       # E1 skipped by BS, 9999 never sent
    _start(api, erw)
    assert _escort_ids(erw) == [E2]
    assert _escorts(erw) == {E1: ("active", 0), E2: ("active", 1)}
    assert _raid(erw)["status"] == "fighting"


def test_old_battle_service_without_the_field_places_nobody(erw, api):
    _hire_escorts(erw, E1)
    erw.battle.old_bs = True
    _start(api, erw)
    assert _escort_ids(erw) == [] and _escorts(erw) == {E1: ("active", 0)}


def test_battle_client_payload_and_old_answer(monkeypatch):
    sent, answers = [], [{"battle_id": 5, "attacker_character_ids": [1], "escort_character_ids": [3]},
                         {"battle_id": 6, "attacker_character_ids": [1]}]

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            sent.append((url, json, headers))
            body = answers[len(sent) - 1]
            return SimpleNamespace(status_code=200, text="", json=lambda: body)

    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(battle_client.httpx, "AsyncClient", Client)
    out = asyncio.run(battle_client.create_caravan_raid_battle(1, 2, 1, False, [7, 8], 3,
                                                               escort_character_ids=[3, "4"]))
    assert out == {"battle_id": 5, "attacker_character_ids": [1], "escort_character_ids": [3]}
    url, payload, headers = sent[0]
    assert url.endswith("/battles/internal/caravan-raid") and headers == INTERNAL
    assert payload["escort_character_ids"] == [3, 4] and payload["guard_character_ids"] == [7, 8]
    out = asyncio.run(battle_client.create_caravan_raid_battle(1, 2, 1, False, [7], 3))
    assert out["escort_character_ids"] == []                             # old battle-service answer
    assert sent[1][1]["escort_character_ids"] == []


def test_escort_cannot_lead_a_raid_and_nothing_spawns(erw, api):
    _hire_escorts(erw, RAIDER)
    _gate(erw, erw.cid)
    resp = api.post(_raid_url(erw.cid), json={"character_id": RAIDER})
    expected = activity_lock.lock_message({"locked": True, "reason": activity_lock.REASON_CARAVAN_ESCORT})
    assert resp.status_code == 409 and resp.json()["detail"] == expected
    assert "карав" not in expected.lower()                               # neutral text, the job stays secret
    assert _raid(erw) is None and _guards_alive(erw) == 0 and erw.battle.calls == []


def test_escort_squadmate_stays_on_the_guard_side(erw, api):
    _hire_escorts(erw, MATE)
    raid_id = _start(api, erw, group=True, attackers=[RAIDER])           # BS left the escort out of the attackers
    assert erw.battle.kwargs == [{"escort_character_ids": [MATE]}]
    assert _settle_f(api, raid_id, winner=0) == "won"
    assert _raid(erw)["attacker_ids"] == [RAIDER]
    assert (_gold(erw, RAIDER), _gold(erw, MATE)) == (80, 0)
    assert _escorts(erw) == {MATE: ("fallen", 1)}
    _check(erw)


# ---- settlement ----------------------------------------------------------------------------------------------------

def test_won_raid_drops_every_placed_escort_at_the_raid_location(erw, api, stub_law_notify_send):
    _hire_escorts(erw, E1, E2, E3)
    erw.battle.placed = [E1, E2]                                         # E3 was not in the fight
    raid_id = _start(api, erw)
    assert _settle_f(api, raid_id, winner=0) == "won"
    assert _escorts(erw) == {E1: ("fallen", 1), E2: ("fallen", 1), E3: ("active", 0)}
    assert (_col(erw, E1), _col(erw, E2), _col(erw, E3)) == (None, None, erw.cid)
    assert {_scalar(erw, "SELECT current_location_id FROM characters WHERE id = :c", c=c) for c in (E1, E2)} == \
        {L_GATE1}
    assert _scalar(erw, "SELECT COUNT(*) FROM econ_caravan_escorts WHERE ended_at IS NULL") == 1
    assert _rows(erw, "SELECT SUM(fee), SUM(bonus) FROM econ_caravan_escorts") == [(0, 0)]
    assert (_gold(erw, E1), _gold(erw, E2)) == (0, 0)
    assert _escort_logs(erw) == {(E1, raids.MSG_ESCORT_FALLEN), (E2, raids.MSG_ESCORT_FALLEN)}
    assert _escort_notices(stub_law_notify_send) == {(21, raids.MSG_ESCORT_FALLEN), (22, raids.MSG_ESCORT_FALLEN)}
    _check(erw)


def test_repelled_raid_drops_only_the_fallen_and_pays_the_rest_with_bonus(erw, api, stub_law_notify_send):
    _hire_escorts(erw, E1, E2)
    raid_id = _start(api, erw)
    assert _settle_f(api, raid_id, winner=1, fallen=[E1, RAIDER]) == "repelled"
    assert _escorts(erw) == {E1: ("fallen", 1), E2: ("active", 1)}
    assert (_col(erw, E1), _col(erw, E2)) == (None, erw.cid)
    assert _escort_logs(erw) == {(E1, raids.MSG_ESCORT_FALLEN_REPELLED)}
    assert _escort_notices(stub_law_notify_send) == {(21, raids.MSG_ESCORT_FALLEN_REPELLED),
                                                     (22, raids.MSG_ESCORT_REPELLED)}
    _check(erw)
    # delivery: the survivor gets fee + bonus, the fallen one nothing
    _exec(erw, "UPDATE econ_caravans SET route_index = 3, current_location_id = :l, arrived_at = :t, "
               "next_move_at = NULL", l=L_GATE2, t=raids.now_utc())
    import economy_caravan_crud
    assert economy_caravan_crud.deliver_physical_tx(erw, erw.cid, raids.now_utc()).status == "delivered"
    rows = {int(r[0]): (r[1], int(r[2]), int(r[3])) for r in _rows(
        erw, "SELECT character_id, status, fee, bonus FROM econ_caravan_escorts")}
    assert rows[E1] == ("fallen", 0, 0)
    status, fee, bonus = rows[E2]
    assert status == "delivered" and fee > 0 and bonus > 0
    assert (_gold(erw, E1), _gold(erw, E2)) == (0, fee + bonus)
    _check(erw)


@pytest.mark.parametrize("fallen", [None, []])
def test_repelled_raid_without_fallen_ids_keeps_every_escort(erw, api, fallen):
    _hire_escorts(erw, E1, E2)
    raid_id = _start(api, erw)
    assert _settle_f(api, raid_id, winner=1, fallen=fallen) == "repelled"
    assert _escorts(erw) == {E1: ("active", 1), E2: ("active", 1)}
    assert (_col(erw, E1), _col(erw, E2)) == (erw.cid, erw.cid)


def test_aborted_raid_keeps_the_escorts(erw, api, stub_law_notify_send):
    _hire_escorts(erw, E1)
    raid_id = _start(api, erw)
    stub_law_notify_send.reset_mock()
    assert _settle_f(api, raid_id, aborted=True, fallen=[E1]) == "aborted"
    assert _escorts(erw)[E1][0] == "active" and _col(erw, E1) == erw.cid
    assert _escort_notices(stub_law_notify_send) == set() and _escort_logs(erw) == set()


def test_expired_raid_releases_the_escorts(erw, api, monkeypatch, stub_law_notify_send):
    _hire_escorts(erw, E1, E2)
    _start(api, erw)
    now = raids.now_utc()
    old = now - timedelta(hours=int(_params(erw).caravan_raid_battle_max_hours), minutes=1)
    _exec(erw, "UPDATE econ_caravan_raids SET started_at = :t", t=old)
    monkeypatch.setattr(battle_client, "get_battle_result", lambda b: {"status": "in_progress"})
    assert raids.poll_raid_battles(erw, now, _params(erw)) == 1
    assert _raid(erw)["status"] == "expired"
    assert _escorts(erw) == {E1: ("released", 1), E2: ("released", 1)}
    assert (_col(erw, E1), _col(erw, E2)) == (None, None)
    assert _escort_notices(stub_law_notify_send) == {(21, raids.MSG_ESCORT_EXPIRED), (22, raids.MSG_ESCORT_EXPIRED)}
    _check(erw)


def test_settlement_falls_back_to_the_battle_guard_team_when_escort_ids_were_lost(erw):
    _hire_escorts(erw, E1, E2, E3)
    now = raids.now_utc()
    raid_id = _insert_raid(erw, "fighting", created=now, started=now, battle_id=BATTLE)
    _exec(erw, "CREATE TABLE IF NOT EXISTS battle_participants (id INTEGER PRIMARY KEY AUTOINCREMENT, "
               "battle_id INTEGER, character_id INTEGER, team INTEGER)")
    for cid, team, battle in ((RAIDER, 0, BATTLE), (E1, 1, BATTLE), (E2, 0, BATTLE), (E3, 1, BATTLE + 1)):
        _exec(erw, "INSERT INTO battle_participants (battle_id, character_id, team) VALUES (:b, :c, :t)",
              b=battle, c=cid, t=team)
    assert _escort_ids(erw) is None
    db = erw()
    try:
        assert raids.battle_result(db, battle_id=BATTLE, raid_id=raid_id, winner_team=0, aborted=False) == "won"
    finally:
        db.close()
    assert _escort_ids(erw) == [E1]
    assert _escorts(erw) == {E1: ("fallen", 1), E2: ("active", 0), E3: ("active", 0)}


@pytest.mark.parametrize("answer,out", [
    ({"status": "finished", "winner_team": 1, "fallen_character_ids": [E2, "x", None]}, {E2}),
    ({"status": "finished", "winner_team": 1}, set()),                  # old battle-service: nobody falls
])
def test_poll_reads_fallen_ids(erw, monkeypatch, answer, out):
    _hire_escorts(erw, E1, E2)
    now = raids.now_utc()
    db = erw()
    try:
        db.add(models.EconCaravanRaid(caravan_id=erw.cid, leader_character_id=RAIDER, location_id=L_GATE1,
                                      region_id=1, status="fighting", created_at=now - timedelta(minutes=10),
                                      started_at=now - timedelta(minutes=5), battle_id=BATTLE,
                                      attacker_ids=[RAIDER], escort_ids=[E1, E2]))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(battle_client, "get_battle_result", lambda b: answer)
    assert raids.poll_raid_battles(erw, now, _params(erw)) == 1
    assert {c for c, (s, _r) in _escorts(erw).items() if s == "fallen"} == out
    assert _raid(erw)["status"] == "repelled"


def test_a3_with_fallen_ids_keeps_the_internal_auth(api, erw):
    body = {"battle_id": BATTLE, "caravan_raid_id": 1, "winner_team": 1, "fallen_character_ids": [E1]}
    assert api.post(RESULT, json=body).status_code == 401
    assert api.post(RESULT, json=body, headers={"X-Internal-Token": "wrong"}).status_code == 401
    for bad in ({**body, "fallen_character_ids": ["x"]}, {**body, "fallen_character_ids": "1 OR 1=1"}):
        assert api.post(RESULT, json=bad, headers=INTERNAL).status_code == 422


# ---- faction raid points (once per raid) ---------------------------------------------------------------------------

def test_faction_raid_points_once_per_won_raid(erw, api):
    raid_id = _start(api, erw, attackers=[MATE, RAIDER])
    assert _settle_f(api, raid_id, winner=0) == "won"
    expected = [(cid, faction_core.ENEMY_RAID, raids.raid_faction_key(raid_id, cid)) for cid in (RAIDER, MATE)]
    assert erw.deeds.calls == expected
    assert expected[0][2] == f"faction:caravan_raid:r{raid_id}:{RAIDER}"
    assert _scalar(erw, "SELECT faction_done FROM econ_caravan_raids") == 1
    assert _settle_f(api, raid_id, winner=0) == "already"                # duplicate callback
    raids.raid_followups(erw, raids.now_utc() + timedelta(minutes=5), _params(erw))
    assert raids.raid_faction_points(erw(), raid_id) == 0
    assert erw.deeds.calls == expected


def test_faction_raid_points_retried_by_the_followups(erw, api):
    erw.deeds.error = RuntimeError("factions down")
    raid_id = _start(api, erw)
    assert _settle_f(api, raid_id, winner=0) == "won"                    # payout stays, the step is retried
    assert _scalar(erw, "SELECT faction_done FROM econ_caravan_raids") == 0
    erw.deeds.error, erw.deeds.calls = None, []
    assert raids.raid_followups(erw, raids.now_utc(), _params(erw)) >= 1
    assert erw.deeds.calls == [(RAIDER, faction_core.ENEMY_RAID, raids.raid_faction_key(raid_id, RAIDER))]
    assert _scalar(erw, "SELECT faction_done FROM econ_caravan_raids") == 1
    raids.raid_followups(erw, raids.now_utc(), _params(erw))
    assert len(erw.deeds.calls) == 1


@pytest.mark.parametrize("winner,aborted", [(1, False), (None, True)])
def test_no_faction_raid_points_for_a_failed_raid(erw, api, winner, aborted):
    raid_id = _start(api, erw)
    _settle_f(api, raid_id, winner=winner, aborted=aborted)
    raids.raid_followups(erw, raids.now_utc(), _params(erw))
    assert erw.deeds.calls == [] and raids.raid_faction_points(erw(), raid_id) == 0
