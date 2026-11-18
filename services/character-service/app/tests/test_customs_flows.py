"""FEAT-216 QA (task 15): customs & smuggling DB flows that the developer smoke files do not cover.

Already covered elsewhere (not repeated here): ``test_customs_inspection`` (stop / duty / final node / seller gate /
0 min / raid before & after the post with a simulated raid / cancel after duty / admin detail), ``test_customs_detection``
(alert + hold, failed roll, legal / foreign officer, generic 404, won inspect + seizure + share, repelled inspect,
patrol confiscation / auto fight / 409 fallback / won patrol, economy-run postponement, real consequences),
``test_caravan_smugglers`` (fence list / hire / move / officer refusal / pay-only reward), ``test_customs_officer_api``
(enlist cycle, gates, ownership, admin bans happy path).

Here: the real stealth maths (officer attention, escort stealth incl. subclass points, patrol chance); officers off
watch (wanted / jailed / in battle / escort of the caravan); group inspection with a share remainder and real
consequences for every attacker; a locked officer's 409; a repelled patrol fight followed by a pay-only smuggling
delivery; poll / expire of customs and patrol fights; the goods fallback of a seizure (seizure region → origin →
write-off); the ship-deck region fallback; the escrow invariant after a seizure of a caravan with freight / duty
paid; a bandit raid during an inspection; the masking audit (strangers, alert notice, public escort card); enlist
refusals; admin bans auth / payload validation.

Worlds: ``test_caravan_raids.rw`` (+ ``test_customs_detection.cw``) and ``test_physical_caravans.world``. RNG through
``customs_crud.rng``; battle-service mocked. Pass times sit a minute past due times (SQLite string datetimes).
"""

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

import battle_client
import caravan_escort_crud as escorts
import caravan_escort_public
import caravan_pass
import caravan_raid_crud as raids
import customs_core
import customs_crud
import econ_tick
import economy_caravan_crud as crud
import faction_kills
import law_notify
import models
import renown_crud
import reputation_crud
import sea_cargo
import shadow_core
from auth_http import get_current_user_via_http
from main import app
from tests.test_caravan_raids import (  # noqa: F401  (fixtures)
    A1_KEYS, BATTLE, INTERNAL, MATE, RAIDER, RESULT, STRANGER, USER, _as_user, api, rw,
)
from tests.test_customs_detection import (  # noqa: F401  (fixtures)
    GUARD, FakeCustomsBattle, INSPECT, _alerted, _escort, _guard, _officer, _pass, _raid_row, _seizure_ops, cw,
)
from tests.test_customs_inspection import _check as _dcheck, _foreign, _post
from tests.test_customs_officer_api import ADMIN, ENLIST, NPC, VIEW, cus  # noqa: F401  (fixture)
from tests.test_econ_tick import _balance, _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import _exec, _set_params
from tests.test_econ_tick_events import calendar  # noqa: F401  (autouse: no calendar HTTP)
from tests.test_physical_caravans import (  # noqa: F401
    L_GATE1, L_GATE2, L_ROAD1, L_ROAD2, START, _row, raider, world,
)

REAL_ESCORT_REDUCTION = customs_crud._escort_reduction
REAL_ATTENTION = customs_crud.officer_attention
REAL_CONSEQUENCES = customs_crud.consequences
L_DECK = 777                       # a ship's deck: a location without a region

EXTRA_DDL = (
    "CREATE TABLE IF NOT EXISTS character_attributes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "character_id INTEGER NOT NULL, agility INTEGER DEFAULT 0, stealth INTEGER DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS tree_nodes (id INTEGER PRIMARY KEY, node_type VARCHAR(30), subclass_key VARCHAR(40), "
    "name VARCHAR(100) NULL)",
    "CREATE TABLE IF NOT EXISTS character_tree_progress (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "character_id INTEGER, node_id INTEGER)",
    "CREATE TABLE IF NOT EXISTS battles (id INTEGER PRIMARY KEY, status VARCHAR(20), law_encounter_id INTEGER NULL)",
    "CREATE TABLE IF NOT EXISTS battle_participants (id INTEGER PRIMARY KEY AUTOINCREMENT, battle_id INTEGER, "
    "character_id INTEGER, dropped_out_at DATETIME)",
)


# ===================================================================================================================
# helpers
# ===================================================================================================================

def _tables(f):
    for ddl in EXTRA_DDL:
        _exec(f, ddl)


def _real_stealth(f, monkeypatch):
    _tables(f)
    monkeypatch.setattr(customs_crud, "_escort_reduction", REAL_ESCORT_REDUCTION)
    monkeypatch.setattr(customs_crud, "officer_attention", REAL_ATTENTION)


def _stealth(f, cid, value):
    _exec(f, "INSERT INTO character_attributes (character_id, stealth, agility) VALUES (:c, :s, 0)", c=cid, s=value)


def _subclass(f, cid, key):
    _exec(f, "INSERT INTO tree_nodes (id, node_type, subclass_key) VALUES (1, 'subclass_choice', :k)", k=key)
    _exec(f, "INSERT INTO character_tree_progress (character_id, node_id) VALUES (:c, 1)", c=cid)


def _in_battle(f, cid):
    _tables(f)
    _exec(f, "INSERT INTO battles (id, status) VALUES (4242, 'in_progress')")
    _exec(f, "INSERT INTO battle_participants (battle_id, character_id) VALUES (4242, :c)", c=cid)


def _wanted(f, cid, region=1, value=500):
    _exec(f, "INSERT INTO character_wanted (character_id, region_id, value, decay_at, updated_at) "
             "VALUES (:c, :r, :v, NULL, :t)", c=cid, r=region, v=value, t=START)


def _jail(f, cid, until=datetime(2100, 1, 1)):
    _exec(f, "UPDATE characters SET jailed_until = :u WHERE id = :c", u=until, c=cid)


def _roll(pct):
    """An rng whose roll (floor to 0.01 of ``random() × 100``) lands on ``pct``."""
    return SimpleNamespace(random=lambda: float(pct) / 100)


def _hit(chance):
    return _roll(Decimal(chance) - Decimal("0.005"))          # one cent under the chance → success


def _miss(chance):
    return _roll(Decimal(chance) + Decimal("0.005"))          # exactly the chance → failure (roll < chance only)


def _session(f):
    db = f()
    return db, econ_tick.load_params(db)


def _gold(f, cid):
    return int(_scalar(f, "SELECT currency_balance FROM characters WHERE id = :c", c=cid))


def _stock(f, region):
    value = _scalar(f, "SELECT stock FROM econ_region_goods WHERE region_id = :r AND group_code = 'food'", r=region)
    return None if value is None else float(value)


def _seize(f, *, kind=customs_core.KIND_PATROL, location=L_ROAD1, now=START):
    db, params = _session(f)
    db.close()
    return customs_crud.confiscate_tx(f, _row(f).id, kind=kind, location_id=location, now=now, params=params)


# ===================================================================================================================
# detection: the real stealth maths
# ===================================================================================================================

def test_real_stealth_maths_decide_the_officer_roll(cw, monkeypatch):
    """Officer «внимательность» = his stealth through the guards' curve; caravan stealth = base + the best escort
    (subclass points included). A roll exactly on the chance misses, one cent below hits."""
    _real_stealth(cw, monkeypatch)
    _stealth(cw, RAIDER, 40)
    _stealth(cw, MATE, 30)
    _stealth(cw, STRANGER, 45)
    _subclass(cw, MATE, shadow_core.SUBCLASS_AGENT)
    _escort(cw, MATE)
    _escort(cw, STRANGER)
    _officer(cw)
    db, params = _session(cw)
    try:
        s = renown_crud.load_shadow_settings(db)
        attention = customs_crud.officer_attention(db, RAIDER, s)
        assert attention == shadow_core.stealth_reduction_pct(40, s) > 0
        mate = shadow_core.effective_stealth(30, shadow_core.subclass_stealth_points(shadow_core.SUBCLASS_AGENT, s))
        assert mate > 45                                                       # the subclass makes MATE the best
        stealth = int(params.customs_caravan_stealth) + int(mate)
        assert customs_crud._escort_reduction(db, [MATE, STRANGER], params, s) == \
            (shadow_core.stealth_reduction_pct(stealth, s), stealth)
        reduction = shadow_core.stealth_reduction_pct(stealth, s)
    finally:
        db.close()
    chance = customs_core.detection_chance(params.customs_detect_base_pct, attention, reduction,
                                           params.customs_detect_min_pct, params.customs_detect_max_pct)
    assert Decimal(params.customs_detect_min_pct) < chance < Decimal(params.customs_detect_base_pct)

    cw.roll = _miss(chance)
    _pass(cw)
    assert (_row(cw).current_location_id, _row(cw).customs_alert_officer_id) == (L_ROAD1, None)
    _exec(cw, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_ROAD2, c=RAIDER)
    cw.roll = _hit(chance)
    assert _pass(cw, START + timedelta(minutes=30)).get("customs_alert") == 1
    row = _row(cw)
    assert (row.current_location_id, row.customs_alert_officer_id) == (L_ROAD2, RAIDER)


def test_escort_stealth_lowers_the_patrol_chance(cw, monkeypatch):
    _real_stealth(cw, monkeypatch)
    _set_params(cw, customs_patrol_detect_pct=50)
    _stealth(cw, MATE, 60)
    _escort(cw, MATE)
    _guard(cw)
    db, params = _session(cw)
    try:
        reduction = shadow_core.stealth_reduction_pct(int(params.customs_caravan_stealth) + 60,
                                                      renown_crud.load_shadow_settings(db))
    finally:
        db.close()
    chance = customs_core.patrol_chance(50, reduction, params.customs_detect_max_pct)
    assert Decimal(0) < chance < Decimal(50)

    cw.roll = _roll((chance + Decimal(50)) / 2)                               # would hit without the escort's stealth
    _pass(cw)
    assert cw.customs.calls == [] and _raid_row(cw) is None and _row(cw).status == "in_transit"
    _exec(cw, "UPDATE characters SET current_location_id = :l WHERE id = :g", l=L_ROAD2, g=GUARD)
    cw.roll = _hit(chance)
    assert _pass(cw, START + timedelta(minutes=30)).get("customs_patrol_fight") == 1
    assert cw.customs.calls[0]["escorts"] == [MATE] and cw.customs.calls[0]["location_id"] == L_ROAD2


@pytest.mark.parametrize("case", ["wanted", "jailed", "in_battle", "escort"])
def test_officer_off_watch_does_not_roll(cw, case):
    _officer(cw)
    if case == "wanted":
        _wanted(cw, RAIDER, region=1)
    elif case == "jailed":
        _jail(cw, RAIDER)
    elif case == "in_battle":
        _in_battle(cw, RAIDER)
    else:
        _escort(cw, RAIDER)                                                    # a smuggler of this very caravan
    stats = _pass(cw)
    assert stats["moved"] == 1 and "customs_alert" not in stats
    assert _row(cw).customs_alert_officer_id is None


# ===================================================================================================================
# officer fights
# ===================================================================================================================

class GroupBattle(FakeCustomsBattle):
    """The officer brought his squad: battle-service reports three player attackers."""

    async def __call__(self, *args, **kwargs):
        out = await super().__call__(*args, **kwargs)
        out["attacker_character_ids"] = [RAIDER, MATE, STRANGER]
        return out


def test_group_inspection_splits_the_share_and_rewards_every_attacker(api, cw, monkeypatch):
    monkeypatch.setattr(customs_crud, "consequences", REAL_CONSEQUENCES)
    cw.customs = GroupBattle()
    monkeypatch.setattr(battle_client, "create_customs_battle", cw.customs)
    _officer(cw)
    _exec(cw, "UPDATE characters SET current_location_id = :l WHERE id IN (:a, :b)", l=L_ROAD1, a=MATE, b=STRANGER)
    _alerted(cw)
    resp = api.post(INSPECT.format(cw.cid), json={"character_id": RAIDER, "group": True})
    assert resp.status_code == 201, resp.text
    assert cw.customs.calls[0]["group"] is True and cw.customs.calls[0]["leader"] == RAIDER
    country = _balance(cw, "country_treasury", 1)
    gold = {cid: _gold(cw, cid) for cid in (RAIDER, MATE, STRANGER)}
    raid_id = _raid_row(cw)[0]
    resp = api.post(RESULT, json={"battle_id": BATTLE, "caravan_raid_id": raid_id, "winner_team": 0,
                                  "aborted": False}, headers=INTERNAL)
    assert resp.status_code == 200 and resp.json()["status"] == "won"
    _dcheck(cw)
    db, params = _session(cw)
    db.close()
    pool = customs_core.officer_pool(400, params.customs_officer_share)
    each, remainder = customs_core.officer_split(pool, 3)
    assert remainder > 0                                                       # 80 / 3: the remainder exists
    for cid in (RAIDER, MATE, STRANGER):
        assert _gold(cw, cid) == gold[cid] + each
    assert _balance(cw, "country_treasury", 1) == country + 400 - 3 * each   # remainder + rest → the country
    assert _raid_row(cw)[5] == 3 * each
    # counters only for the enlisted officer; fame + reputation for every player attacker
    assert _rows(cw, "SELECT character_id, seizures, earned FROM econ_customs_officers") == [(RAIDER, 1, each)]
    fame = {r[0] for r in _rows(cw, "SELECT character_id FROM renown_log WHERE scale = 'fame' "
                                    "AND source = 'customs_seizure'")}
    assert fame == {RAIDER, MATE, STRANGER}
    reps = {r[0] for r in _rows(cw, "SELECT character_id FROM character_reputation WHERE region_id = 1")}
    assert reps >= {RAIDER, MATE, STRANGER}
    assert _rows(cw, "SELECT COUNT(*) FROM law_crimes") == [(0,)]           # no escorts → no smuggling crimes


def test_locked_officer_gets_409_and_keeps_the_alert(api, cw):
    _officer(cw)
    _alerted(cw)
    _jail(cw, RAIDER)
    resp = api.post(INSPECT.format(cw.cid), json={"character_id": RAIDER})
    assert resp.status_code == 409 and "тюрьме" in resp.json()["detail"]
    assert _row(cw).customs_alert_officer_id == RAIDER and cw.customs.calls == [] and _raid_row(cw) is None


def test_repelled_patrol_then_the_smugglers_are_paid_only(api, cw, monkeypatch):
    """Escorts beat the guards: the caravan moves on (never checked again), no seizure / crime; on delivery the
    smuggler gets the smuggler fee + the repelled bonus and NO reputation / fame / faction deed."""
    _guard(cw)
    _escort(cw)
    assert _pass(cw).get("customs_patrol_fight") == 1
    raid_id = _raid_row(cw)[0]
    resp = api.post(RESULT, json={"battle_id": BATTLE, "caravan_raid_id": raid_id, "winner_team": 1,
                                  "aborted": False}, headers=INTERNAL)
    assert resp.status_code == 200 and resp.json()["status"] == "repelled"
    row = _row(cw)
    assert row.status == "in_transit" and row.next_move_at is not None and row.cancel_reason is None
    assert _seizure_ops(cw) == [] and cw.consequences == []
    assert _rows(cw, "SELECT status FROM econ_caravan_escorts") == [("active",)]

    def boom(*a, **k):
        raise AssertionError("a smuggling run earns pay only")
    monkeypatch.setattr(faction_kills, "apply_caravan_deed", boom)
    monkeypatch.setattr(reputation_crud, "apply_reputation", boom)
    monkeypatch.setattr(renown_crud, "add_fame", boom)
    db, params = _session(cw)
    db.close()
    fee, bonus = escorts.pools(400, params, True, True)
    assert bonus > 0 and fee == escorts.pools(400, params, False, True)[0]
    now = datetime.utcnow().replace(microsecond=0)
    for hours in (1, 2, 3):                                                   # the settle used the real clock
        stats = _pass(cw, now + timedelta(hours=hours))
        assert stats["failed"] == 0 and "customs_alert" not in stats and "customs_seized" not in stats
        if _row(cw).status == "delivered":
            break
    assert _row(cw).status == "delivered"
    assert _gold(cw, MATE) == fee + bonus
    assert _rows(cw, "SELECT status, rewards_done FROM econ_caravan_escorts") == [("delivered", 1)]


# ===================================================================================================================
# poll / expire of enforcement fights
# ===================================================================================================================

@pytest.mark.parametrize("kind,result,expected", [
    ("customs", {"status": "finished", "winner_team": 0, "aborted": False}, "won"),
    ("patrol", battle_client.BATTLE_NOT_FOUND, "aborted"),
    ("customs", {"status": "in_progress"}, "expired"),
])
def test_poll_and_expire_settle_enforcement_fights(api, cw, monkeypatch, kind, result, expected):
    if kind == "customs":
        _officer(cw)
        _alerted(cw)
        assert api.post(INSPECT.format(cw.cid), json={"character_id": RAIDER}).status_code == 201
    else:
        _guard(cw)
        _escort(cw)
        assert _pass(cw).get("customs_patrol_fight") == 1
    db, params = _session(cw)
    db.close()
    started = START - timedelta(hours=int(params.caravan_raid_battle_max_hours) + 1 if expected == "expired" else 1)
    _exec(cw, "UPDATE econ_caravan_raids SET started_at = :t", t=started)
    polled = []

    def fake_result(battle_id):
        polled.append(battle_id)
        return result
    monkeypatch.setattr(battle_client, "get_battle_result", fake_result)
    _pass(cw, START + timedelta(minutes=5))
    assert polled == [BATTLE]
    raid = _raid_row(cw)
    assert (raid[1], raid[2]) == (kind, expected)
    row = _row(cw)
    if expected == "won":                                                      # poll + follow-up in the same pass
        assert (row.status, row.cancel_reason, raid[4]) == ("cancelled", "seized_customs", 1)
        assert len(_seizure_ops(cw)) == 1
    else:                                                                      # released, never seized
        assert row.status == "in_transit" and row.next_move_at is not None and _seizure_ops(cw) == []
        assert raid[4] == 0 and cw.consequences == []


# ===================================================================================================================
# confiscation: goods, deck, escrow
# ===================================================================================================================

@pytest.mark.parametrize("case", ["seizure_region", "origin", "written_off"])
def test_seized_goods_go_to_the_seizure_region_else_origin_else_written_off(cw, case):
    _exec(cw, "UPDATE econ_caravans SET route_index = 2, current_location_id = :l", l=L_ROAD2)    # region 2
    if case in ("origin", "written_off"):
        _exec(cw, "DELETE FROM econ_region_goods WHERE region_id = 2 AND group_code = 'food'")
    if case == "written_off":
        _exec(cw, "DELETE FROM econ_region_goods WHERE region_id = 1 AND group_code = 'food'")
    before = {r: _stock(cw, r) for r in (1, 2)}
    country = _balance(cw, "country_treasury", 1)
    assert _seize(cw, location=L_ROAD2).status == customs_crud.CHECK_SEIZED
    _dcheck(cw)
    row = _row(cw)
    assert (row.status, row.cancel_reason, row.seized_region_id, row.seized_country_id) == \
        ("cancelled", "seized_patrol", 2, 1)
    assert _balance(cw, "country_treasury", 1) == country + 400
    after = {r: _stock(cw, r) for r in (1, 2)}
    if case == "seizure_region":
        assert after[2] == pytest.approx(before[2] + 200) and after[1] == before[1] and not row.goods_returned
    elif case == "origin":
        assert after[1] == pytest.approx(before[1] + 200) and after[2] is None and row.goods_returned
    else:
        assert after == {1: None, 2: None} and not row.goods_returned
    assert _seize(cw, location=L_ROAD2).status == "already"                   # idempotent
    assert len(_seizure_ops(cw)) == 1


def test_seizure_on_a_ship_deck_falls_back_to_the_raid_region(cw):
    _exec(cw, "INSERT INTO Locations (id, name, region_id) VALUES (:i, 'Палуба', NULL)", i=L_DECK)
    _officer(cw)
    db = cw()
    try:
        raid = models.EconCaravanRaid(caravan_id=cw.cid, leader_character_id=RAIDER, location_id=L_DECK, region_id=2,
                                      status="won", attacker_ids=[RAIDER], created_at=START, kind="customs")
        db.add(raid)
        db.commit()
        raid_id = raid.id
    finally:
        db.close()
    stock = _stock(cw, 2)
    gold = _gold(cw, RAIDER)
    db, params = _session(cw)
    db.close()
    assert customs_crud.confiscate_raid(cw, raid_id, START, params).status == customs_crud.CHECK_SEIZED
    _dcheck(cw)
    row = _row(cw)
    assert (row.cancel_reason, row.seized_region_id, row.seized_country_id) == ("seized_customs", 2, 1)
    assert _stock(cw, 2) == pytest.approx(stock + 200)
    share = customs_core.officer_pool(400, params.customs_officer_share)
    assert _gold(cw, RAIDER) == gold + share
    assert _rows(cw, "SELECT seized_done, officer_paid FROM econ_caravan_raids") == [(1, share)]
    assert customs_crud.confiscate_raid(cw, raid_id, START, params).status == "already"


def test_seizure_after_freight_takes_only_the_escrow_rest(cw):
    _exec(cw, "UPDATE econ_caravans SET freight = 60, sea_board_port_id = :p", p=L_GATE1)
    db = cw()
    try:
        row = crud._lock_caravan(db, cw.cid)
        assert sea_cargo.charge_freight(db, row, None, START) is not None
        db.commit()
    finally:
        db.close()
    _dcheck(cw)
    assert _balance(cw, "caravan_escrow", 0) == 340
    country = _balance(cw, "country_treasury", 1)
    result = _seize(cw, location=L_GATE1)
    assert (result.status, result.amount) == (customs_crud.CHECK_SEIZED, 340)
    _dcheck(cw)
    assert _balance(cw, "caravan_escrow", 0) == 0
    assert _balance(cw, "country_treasury", 1) == country + 340


def test_seizure_after_duty_takes_only_the_escrow_rest(world, monkeypatch):
    monkeypatch.setitem(sys.modules, "caravan_raid_crud", raids)           # the stage-1 world hides it
    _foreign(world)                                                          # seller country 2 → buyer country 1
    _post(world, 1)
    caravan_pass.run_pass(world, now=START, force=True, rng=lambda: 0.5)
    _dcheck(world)
    assert (_row(world).customs_state, _row(world).duty_paid) == ("inspecting", 40)
    seller_country = _balance(world, "country_treasury", 2)
    duty_country = _balance(world, "country_treasury", 1)
    result = _seize(world, location=L_ROAD1)                                 # region 1 = country 2
    assert (result.status, result.amount) == (customs_crud.CHECK_SEIZED, 400)
    _dcheck(world)
    assert _balance(world, "caravan_escrow", 0) == 0
    assert _balance(world, "country_treasury", 2) == seller_country + 400
    assert _balance(world, "country_treasury", 1) == duty_country           # the duty stays where it was paid


def test_bandit_raid_during_inspection_does_not_cut_the_stop_short(world, raider, monkeypatch):
    monkeypatch.setitem(sys.modules, "caravan_raid_crud", raids)
    _foreign(world)
    _post(world, 1)                                                          # the post = L_ROAD1, where the raider is
    caravan_pass.run_pass(world, now=START, force=True, rng=lambda: 0.5)
    row = _row(world)
    assert row.customs_state == "inspecting"
    until = row.customs_until
    db = world()
    try:
        here = raids.caravans_here(db, RAIDER, now=until - timedelta(minutes=25))
    finally:
        db.close()
    item = here["caravans"][0]
    assert (item["state"], item["departs_in_sec"], item["can_inspect"]) == (raids.STATE_INSPECTION, 25 * 60, False)
    db = world()
    try:
        raid = models.EconCaravanRaid(caravan_id=row.id, leader_character_id=RAIDER, location_id=L_ROAD1, region_id=1,
                                      status="fighting", battle_id=BATTLE, attacker_ids=[RAIDER], created_at=START,
                                      started_at=START, kind="raid")
        db.add(raid)
        db.commit()
        out = raids.settle_raid(db, raid.id, battle_id=BATTLE, winner_team=1, aborted=False,
                                now=START + timedelta(minutes=2), rng=lambda: 0.0)
    finally:
        db.close()
    assert out.status == "repelled"
    assert _row(world).next_move_at == until                                  # not now + step delay
    _dcheck(world)
    assert caravan_pass.run_pass(world, now=until - timedelta(minutes=2), force=True)["moved"] == 0
    stats = caravan_pass.run_pass(world, now=until + timedelta(minutes=1), force=True, rng=lambda: 0.5)
    assert stats["moved"] == 1
    row = _row(world)
    assert (row.route_index, row.customs_state, row.duty_paid) == (2, "cleared", 40)
    assert len(_rows(world, "SELECT id FROM econ_operations WHERE op_type = 'caravan_duty'")) == 1
    _dcheck(world)


# ===================================================================================================================
# masking audit
# ===================================================================================================================

def test_strangers_never_learn_a_caravan_is_contraband(cw, monkeypatch):
    def here(cid):
        db = cw()
        try:
            return raids.caravans_here(db, cid, now=START)["caravans"]
        finally:
            db.close()

    contraband = here(STRANGER)
    _exec(cw, "UPDATE econ_caravans SET is_contraband = 0")
    assert here(STRANGER) == contraband and set(contraband[0]) == A1_KEYS   # identical to a legal caravan
    _exec(cw, "UPDATE econ_caravans SET is_contraband = 1")

    published = []
    monkeypatch.setattr(law_notify, "publish", lambda notices: published.extend(notices) or len(published))
    _officer(cw)
    _set_params(cw, customs_alert_minutes=10)
    _pass(cw)
    assert [(n.user_id, n.ws_type) for n in published] == [(USER, customs_crud.WS_CUSTOMS_ALERT)]
    assert published[0].data["character_id"] == RAIDER
    _exec(cw, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_ROAD1, c=STRANGER)
    other, officer = here(STRANGER)[0], here(RAIDER)[0]
    assert (other["state"], other["can_inspect"], other["inspect_in_sec"], other["departs_in_sec"]) == \
        (raids.STATE_HELD, False, None, None)
    assert (officer["can_inspect"], officer["inspect_in_sec"]) == (True, 600)
    assert {k: v for k, v in other.items() if k not in ("can_inspect", "inspect_in_sec")} == \
        {k: v for k, v in officer.items() if k not in ("can_inspect", "inspect_in_sec")}

    # a smuggler's public card shows him where he was hired (the fence), unlocked; nothing about the cargo
    _escort(cw, MATE)
    _exec(cw, "UPDATE econ_caravan_escorts SET hire_location_id = :l WHERE character_id = :c", l=L_GATE2, c=MATE)
    _exec(cw, "UPDATE characters SET escort_caravan_id = :car WHERE id = :c", car=cw.cid, c=MATE)
    db = cw()
    try:
        mate = db.get(models.Character, MATE)
        body = caravan_escort_public.mask_body(db, mate, {"current_location_id": L_ROAD1,
                                                          "activity_lock": {"locked": True}})
    finally:
        db.close()
    assert body["current_location_id"] == L_GATE2 and not body["activity_lock"].get("locked")
    assert set(body) == {"current_location_id", "activity_lock"}


# ===================================================================================================================
# officer enlist refusals, admin bans auth / validation
# ===================================================================================================================

def test_enlist_refusals(cus, rw):
    def refused(status, detail=None, contains=None):
        view = cus.get(VIEW, params={"character_id": RAIDER})
        resp = cus.post(ENLIST, json={"character_id": RAIDER})
        assert resp.status_code == status, resp.text
        if detail:
            assert resp.json()["detail"] == detail
        if contains:
            assert contains in resp.json()["detail"]
        if view.status_code == 200:
            assert view.json()["can_enlist"] is False and view.json()["reason"] == resp.json()["detail"]

    _wanted(rw, RAIDER, region=1)
    refused(403, customs_crud.MSG_WANTED)
    _exec(rw, "DELETE FROM character_wanted")
    _wanted(rw, RAIDER, region=2)                                            # wanted elsewhere does not matter
    _exec(rw, "INSERT INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
              "VALUES (:c, 1, -500, NULL, :t)", c=RAIDER, t=START)
    refused(403, contains="Скиталец")
    _exec(rw, "DELETE FROM character_reputation")
    _jail(rw, RAIDER)
    refused(409, contains="тюрьме")
    _exec(rw, "UPDATE characters SET jailed_until = NULL WHERE id = :c", c=RAIDER)
    _in_battle(rw, RAIDER)
    refused(409, customs_crud.MSG_IN_BATTLE)
    _exec(rw, "DELETE FROM battle_participants")
    _exec(rw, "UPDATE characters SET npc_status = 'dead' WHERE id = :n", n=NPC)
    refused(404, customs_crud.MSG_NPC_NOT_FOUND)
    _exec(rw, "UPDATE characters SET npc_status = 'alive' WHERE id = :n", n=NPC)
    _exec(rw, "INSERT INTO Locations (id, name, region_id) VALUES (:i, 'Палуба', NULL)", i=L_DECK)
    _exec(rw, "UPDATE characters SET current_location_id = :l WHERE id IN (:n, :c)", l=L_DECK, n=NPC, c=RAIDER)
    refused(404, customs_crud.MSG_NPC_NO_COUNTRY)
    _exec(rw, "UPDATE characters SET current_location_id = :l WHERE id IN (:n, :c)", l=L_GATE1, n=NPC, c=RAIDER)
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_customs_officers") == 0
    assert cus.post(ENLIST, json={"character_id": RAIDER}).status_code == 201


def test_admin_bans_auth_and_payload_validation(cus, rw):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert cus.get(ADMIN).status_code == 401
    assert cus.put(f"{ADMIN}/1", json={"banned_groups": []}).status_code == 401
    _as_user(USER, role="editor", permissions=["items:create"])
    assert cus.get(ADMIN).status_code == 403
    _as_user(USER, role="admin", permissions=["economy:read", "economy:settings"])
    too_long = ["food"] * (customs_core.MAX_BANNED_GROUPS * 4 + 1)
    assert cus.put(f"{ADMIN}/1", json={"banned_groups": too_long}).status_code == 422
    assert cus.put(f"{ADMIN}/1", json={"banned_groups": "food"}).status_code == 422
    assert cus.put(f"{ADMIN}/0", json={"banned_groups": []}).status_code in (404, 422)
    assert cus.put(f"{ADMIN}/1", json={"banned_groups": ["food' OR 1=1 --"]}).status_code == 400
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_country_bans") == 0
    resp = cus.put(f"{ADMIN}/2", json={"banned_groups": ["food"] * 10})
    assert resp.status_code == 200 and resp.json()["banned_groups"] == ["food"]
    countries = {c["country_id"]: c for c in cus.get(ADMIN).json()["countries"]}
    assert countries[2]["banned_groups"] == ["food"] and countries[1]["banned_groups"] == []
