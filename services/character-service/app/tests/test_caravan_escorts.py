"""FEAT-212 QA (#9): player escorts of physical caravans in character-service (features/FEAT-212 §3.7–3.13).

Complements the developer smoke files (``test_caravan_escort_foundation.py`` — lock reason / masking on synthetic rows;
``test_caravan_escort_core.py`` — C1 key whitelist, happy hire, seats, gate 403/503, ride + pay of one escort, leave,
channel basics) and the guild window gate (``test_econ_guild_api.py::test_view_needs_the_dialogue_gate_too``) and the
departure window (``test_physical_caravans.py::test_departure_window_holds_a_new_caravan_at_the_gate``) — none of
those is repeated here. This file covers:

* every remaining C2 refusal of §3.7 in its contract order (tier, wanted, reputation, seats off, lock, battle,
  gathering, caravan gone / wrong gate / raided / not physical, dead caravaneer) and that a refusal changes nothing;
* C1 never leaks the number of escorts (PM decision 1);
* stepping: escorts ride along, but not while the caravan is held (post hold / active raid);
* delivery: split between several escorts with the remainder kept by the seller, the repelled-raid bonus, the
  robbery cut (pure), world sum 0 + escrow invariant; cancel → no pay, no rewards;
* rewards step: reputation in both regions, defense reputation + fame, faction points under the kill day cap,
  idempotent re-run;
* housekeeping (stale row, dangling column, old channel messages);
* hidden escort on live endpoints (``/by_location``, public ``short_info``) after a real hire;
* admin A4 ``escort_count`` / A5 ``escorts``;
* security: no token → 401 on C1–C6, someone else's character → 403, injection / oversize text in the channel.

Raid integration (``begin_raid`` / ``settle_raid`` with escorts) is QA task 10 and is NOT tested here; raids appear
only as rows inserted directly. Lean on purpose: reuses the FEAT-211 raid world (``rw`` / ``api``).
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import caravan_escort_crud as escorts
import econ_sim
import locations_client
import main
import models
from auth_http import get_current_user_via_http
from main import app
from tests.test_caravan_raids import (  # noqa: F401  (fixtures)
    INTERNAL, MATE, MATE_USER, OTHER_USER, RAIDER, STRANGER, USER, _as_user, _gold, api, rw,
)
from tests.test_econ_tick import _balance, _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import _exec, _set_params
from tests.test_econ_tick_events import calendar  # noqa: F401
from tests.test_physical_caravans import (  # noqa: F401
    L_GATE1, L_GATE2, L_ROAD1, L_ROAD2, START, _check, _gate, _pass, _walk, world,
)

NPC = 601
VIEW = f"/characters/caravans/caravaneer/{NPC}"
JOB = "/characters/caravans/escort"
LEAVE = "/characters/caravans/escort/leave"
MESSAGES = "/characters/caravans/escort/messages"
ADMIN_CARAVANS = "/characters/admin/economy/caravans"
TRIO = (RAIDER, MATE, STRANGER)
OWNERS = {RAIDER: USER, MATE: MATE_USER, STRANGER: OTHER_USER}


def _hire_url(caravan_id):
    return f"/characters/caravans/{caravan_id}/escort/hire"


@pytest.fixture
def esc(api, rw, monkeypatch):
    """The FEAT-211 raid world + a caravaneer at L_GATE1 (the seller gate) and an open dialogue gate (mocked)."""
    db = rw()
    try:
        db.add(models.Character(id=NPC, name="Караванщик", user_id=None, id_subrace=1, id_class=1, id_race=1,
                                appearance="-", avatar="-", is_npc=True, npc_role=escorts.CARAVANEER_ROLE,
                                current_location_id=L_GATE1, level=1, currency_balance=0))
        db.commit()
    finally:
        db.close()
    rw.gate = AsyncMock(return_value=True)
    monkeypatch.setattr(locations_client, "check_npc_gate", rw.gate)

    def override_main_db():
        session = rw()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[main.get_db] = override_main_db
    yield api
    app.dependency_overrides.pop(main.get_db, None)


def _hire(client, f, character=RAIDER):
    _as_user(OWNERS[character])
    return client.post(_hire_url(f.cid), json={"character_id": character, "npc_id": NPC})


def _hire_ok(client, f, *characters):
    for cid in characters:
        resp = _hire(client, f, cid)
        assert resp.status_code == 201, resp.text
    _as_user(USER)


def _col(f, cid):
    return _scalar(f, "SELECT escort_caravan_id FROM characters WHERE id = :c", c=cid)


def _loc(f, cid):
    return _scalar(f, "SELECT current_location_id FROM characters WHERE id = :c", c=cid)


def _escort_rows(f):
    return {int(r[0]): (r[1], int(r[2]), int(r[3]), int(r[4]))
            for r in _rows(f, "SELECT character_id, status, fee, bonus, rewards_done FROM econ_caravan_escorts")}


def _raid_row(f, status, *, in_raid=()):
    _exec(f, "INSERT INTO econ_caravan_raids (caravan_id, leader_character_id, location_id, status, created_at) "
             "VALUES (:c, 999, :loc, :s, :now)", c=f.cid, loc=L_GATE1, s=status, now=datetime.utcnow())
    for cid in in_raid:
        _exec(f, "UPDATE econ_caravan_escorts SET in_raid = 1 WHERE character_id = :c", c=cid)


def _refused(client, f, status, detail, character=RAIDER):
    resp = _hire(client, f, character)
    assert (resp.status_code, resp.json()["detail"]) == (status, detail), resp.text
    assert _col(f, character) is None
    assert _scalar(f, "SELECT COUNT(*) FROM econ_caravan_escorts WHERE character_id = :c", c=character) == 0


# ===================================================================================================================
# C2 refusals (§3.7) — the caravan side
# ===================================================================================================================

def test_hire_refused_when_the_caravan_left_or_is_elsewhere(esc, rw):
    _exec(rw, "UPDATE econ_caravans SET route_index = 1")
    _refused(esc, rw, 409, escorts.MSG_CARAVAN_GONE)
    _exec(rw, "UPDATE econ_caravans SET route_index = 0, current_location_id = :l", l=L_ROAD1)
    _refused(esc, rw, 400, escorts.MSG_WRONG_GATE)
    _exec(rw, "UPDATE econ_caravans SET current_location_id = :l, is_physical = 0", l=L_GATE1)
    _refused(esc, rw, 404, escorts.MSG_CARAVAN_NOT_FOUND)
    _as_user(USER)
    resp = esc.post(_hire_url(987654), json={"character_id": RAIDER, "npc_id": NPC})
    assert (resp.status_code, resp.json()["detail"]) == (404, escorts.MSG_CARAVAN_NOT_FOUND)


def test_hire_refused_after_a_raid_and_caravan_no_longer_listed(esc, rw):
    _raid_row(rw, "repelled")                                       # even a finished raid closes the hire window
    _refused(esc, rw, 409, escorts.MSG_RAIDED)
    _as_user(USER)
    assert esc.get(VIEW, params={"character_id": RAIDER}).json()["caravans"] == []


def test_hire_refused_when_hiring_is_off(esc, rw):
    _set_params(rw, caravan_escort_seats=0)
    _refused(esc, rw, 409, escorts.MSG_HIRING_OFF)
    body = esc.get(VIEW, params={"character_id": RAIDER}).json()
    assert body["seats_enabled"] is False and body["caravans"][0]["has_seats"] is False
    assert body["caravans"][0]["pay_estimate"] == 0


def test_dead_caravaneer_or_wrong_role_is_404(esc, rw):
    _exec(rw, "UPDATE characters SET npc_status = 'dead' WHERE id = :n", n=NPC)
    _refused(esc, rw, 404, escorts.MSG_CARAVANEER_NOT_FOUND)
    _exec(rw, "UPDATE characters SET npc_status = 'alive', npc_role = 'fence' WHERE id = :n", n=NPC)
    _refused(esc, rw, 404, escorts.MSG_CARAVANEER_NOT_FOUND)
    rw.gate.assert_not_called()                                     # refused before the HTTP gate


# ===================================================================================================================
# C2 refusals — the character side
# ===================================================================================================================

def test_hire_refused_for_a_locked_character(esc, rw):
    _exec(rw, "UPDATE characters SET unconscious_until = :t WHERE id = :c",
          t=datetime.utcnow() + timedelta(hours=2), c=RAIDER)
    resp = _hire(esc, rw)
    assert resp.status_code == 409 and resp.json()["detail"].startswith("Персонаж без сознания")
    assert _col(rw, RAIDER) is None
    item = esc.get(VIEW, params={"character_id": RAIDER}).json()["caravans"][0]
    assert item["can_hire"] is False and item["reason"].startswith("Персонаж без сознания")


def test_hire_refused_in_battle_and_while_gathering(esc, rw):
    _exec(rw, "CREATE TABLE battles (id INTEGER PRIMARY KEY, status VARCHAR(20))")
    _exec(rw, "CREATE TABLE battle_participants (id INTEGER PRIMARY KEY AUTOINCREMENT, battle_id INTEGER, "
              "character_id INTEGER, dropped_out_at DATETIME NULL)")
    _exec(rw, "CREATE TABLE gathering_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, "
              "status VARCHAR(20), complete_at DATETIME NULL)")
    _exec(rw, "INSERT INTO battles (id, status) VALUES (1, 'in_progress'), (2, 'finished')")
    _exec(rw, "INSERT INTO battle_participants (battle_id, character_id) VALUES (1, :c)", c=RAIDER)
    _refused(esc, rw, 409, escorts.MSG_IN_BATTLE)
    _exec(rw, "UPDATE battle_participants SET battle_id = 2")       # a finished battle does not count
    _exec(rw, "INSERT INTO gathering_sessions (character_id, status) VALUES (:c, 'active')", c=RAIDER)
    _refused(esc, rw, 409, escorts.MSG_GATHERING)
    _exec(rw, "UPDATE gathering_sessions SET status = 'completed'")
    assert _hire(esc, rw).status_code == 201


def test_hire_refused_when_wanted_in_the_seller_region(esc, rw):
    _exec(rw, "INSERT INTO character_wanted (character_id, region_id, value, decay_at, updated_at) "
              "VALUES (:c, 1, 50, NULL, :now)", c=RAIDER, now=datetime.utcnow())
    _refused(esc, rw, 403, escorts.MSG_WANTED)
    _exec(rw, "UPDATE character_wanted SET region_id = 2")          # wanted in the BUYER region only: fine
    assert _hire(esc, rw).status_code == 201


def test_hire_refused_below_neutral_reputation_in_the_seller_region(esc, rw):
    _exec(rw, "INSERT INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
              "VALUES (:c, 1, -300, NULL, :now)", c=RAIDER, now=datetime.utcnow())
    resp = _hire(esc, rw)
    assert resp.status_code == 403 and resp.json()["detail"].startswith("Нужна репутация")
    assert _col(rw, RAIDER) is None


def test_npc_tier_gate_refuses_view_and_hire(esc, rw):
    _exec(rw, "UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :n", n=NPC)
    for resp in (esc.get(VIEW, params={"character_id": RAIDER}), _hire(esc, rw)):
        assert resp.status_code == 403 and resp.json()["detail"].startswith("Нужна репутация")
    assert _col(rw, RAIDER) is None


def test_refusal_order_seats_before_character(esc, rw):
    """§3.7 order: the caravan / seat checks come before the character's own state."""
    _set_params(rw, caravan_escort_seats=1)
    _hire_ok(esc, rw, MATE)
    _exec(rw, "UPDATE characters SET unconscious_until = :t WHERE id = :c",
          t=datetime.utcnow() + timedelta(hours=2), c=RAIDER)
    _refused(esc, rw, 409, escorts.MSG_NO_SEATS)


# ===================================================================================================================
# C1: no seat / escort counts (PM decision 1)
# ===================================================================================================================

def test_c1_never_reveals_how_many_escorts_ride(esc, rw):
    _as_user(MATE_USER)
    before = esc.get(VIEW, params={"character_id": MATE}).json()["caravans"][0]
    _hire_ok(esc, rw, RAIDER, STRANGER)                             # 2 of 3 seats taken
    _as_user(MATE_USER)
    resp = esc.get(VIEW, params={"character_id": MATE})
    after = resp.json()["caravans"][0]
    assert after == before                                          # identical for 0 and 2 escorts
    for leak in ("seats_total", "seats_taken", "escorts", "escort_count", "route", "value"):
        assert leak not in resp.text
    # the escort's own panel may show the seats and the fellows
    _as_user(USER)
    job = esc.get(JOB, params={"character_id": RAIDER}).json()["escort"]
    assert job["seats_total"] == 3 and [e["character_id"] for e in job["escorts"]] == [RAIDER, STRANGER]


# ===================================================================================================================
# stepping
# ===================================================================================================================

def test_escorts_ride_along_but_not_while_held(esc, rw):
    _hire_ok(esc, rw, RAIDER, MATE)
    _gate(rw, rw.cid)                                               # a post hold at the gate
    assert _pass(rw, START)["held"] == 1
    assert (_loc(rw, RAIDER), _loc(rw, MATE)) == (L_GATE1, L_GATE1)
    _exec(rw, "UPDATE action_gates SET status = 'consumed'")
    assert _pass(rw, START + timedelta(minutes=5))["moved"] == 1
    assert (_loc(rw, RAIDER), _loc(rw, MATE), _loc(rw, STRANGER)) == (L_ROAD1, L_ROAD1, L_GATE1)
    job = esc.get(JOB, params={"character_id": RAIDER}).json()["escort"]
    assert (job["state"], job["route_index"], job["current_location_id"]) == ("on_road", 1, L_ROAD1)

    _raid_row(rw, "fighting")                                       # an active raid holds the wagon and its escorts
    for minutes in (60, 600):
        _pass(rw, START + timedelta(minutes=minutes))
    assert (_loc(rw, RAIDER), _loc(rw, MATE)) == (L_ROAD1, L_ROAD1)
    assert esc.get(JOB, params={"character_id": RAIDER}).json()["escort"]["state"] == "under_attack"


def test_a_leaver_stays_behind(esc, rw):
    _hire_ok(esc, rw, RAIDER, MATE)
    _pass(rw, START)
    resp = esc.post(LEAVE, json={"character_id": RAIDER})
    assert resp.json() == {"left": True, "location_id": L_ROAD1}
    _pass(rw, START + timedelta(minutes=30))
    assert (_loc(rw, RAIDER), _loc(rw, MATE)) == (L_ROAD1, L_ROAD2)
    assert _escort_rows(rw)[RAIDER][0] == "left"


# ===================================================================================================================
# delivery pay / cancel / invariant
# ===================================================================================================================

def test_pools_robbery_cut_and_caps():
    params = econ_sim.SimParams(caravan_escort_fee_share=0.05, caravan_escort_bonus_share=0.03)
    caravan = SimpleNamespace(value=400, duty=0, paid_purse=400, paid_treasury=0, raid_paid=0)
    assert escorts.pools(escorts._seller_part(caravan), params, False) == (20, 0)
    assert escorts.pools(escorts._seller_part(caravan), params, True) == (20, 12)
    caravan.raid_paid = 100                                         # robbed: the shares shrink with the rest
    assert escorts._seller_part(caravan) == 300
    assert escorts.pools(300, params, True) == (15, 9)
    greedy = econ_sim.SimParams(caravan_escort_fee_share=0.5, caravan_escort_bonus_share=0.5)
    assert escorts.pools(7, greedy, True) == (3, 3)                 # never more than the seller part
    assert escorts.pools(0, params, True) == (0, 0)


def test_delivery_splits_pay_keeps_remainder_and_adds_the_bonus(esc, rw):
    _hire_ok(esc, rw, *TRIO)
    _raid_row(rw, "repelled", in_raid=(RAIDER, MATE))
    seller = _balance(rw, "population_purse", 1)
    _walk(rw, 4)
    # fee pool 400 * 5 % = 20 -> 6 each (2 stay with the seller); bonus 400 * 3 % = 12 -> 4 each
    assert {cid: row[:3] for cid, row in _escort_rows(rw).items()} == {c: ("delivered", 6, 4) for c in TRIO}
    assert [_gold(rw, c) for c in TRIO] == [10, 10, 10]
    assert _balance(rw, "population_purse", 1) == seller + 400 - 30
    assert all(_col(rw, c) is None and _loc(rw, c) == L_GATE2 for c in TRIO)
    meta = _scalar(rw, "SELECT metadata FROM econ_operations WHERE op_type = 'caravan_delivery'")
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert sorted(e["character_id"] for e in meta["escorts"]) == sorted(TRIO)
    logs = _rows(rw, "SELECT description FROM character_logs WHERE character_id = :c AND event_type = 'caravan_escort' "
                     "ORDER BY id", c=MATE)
    assert "плата 6 марок (+4 за отбитый налёт)" in logs[-1][0]
    _check(rw)


def test_cancelled_caravan_pays_nothing_and_gives_no_rewards(esc, rw):
    _hire_ok(esc, rw, RAIDER)
    _exec(rw, "UPDATE econ_regions SET population = 0 WHERE region_id = 2")
    _exec(rw, "UPDATE econ_caravans SET route_index = 3, current_location_id = :l, arrived_at = :t, "
              "next_move_at = NULL", l=L_GATE2, t=START - timedelta(minutes=5))
    assert _pass(rw, START)["cancelled"] == 1
    assert _escort_rows(rw)[RAIDER] == ("cancelled", 0, 0, 0)
    assert _gold(rw, RAIDER) == 0 and _col(rw, RAIDER) is None
    _pass(rw, START + timedelta(minutes=30))
    assert _scalar(rw, "SELECT COUNT(*) FROM reputation_log WHERE character_id = :c", c=RAIDER) == 0
    _check(rw)


# ===================================================================================================================
# rewards step
# ===================================================================================================================

def _faction(f, *, cap=None, points=30):
    now = datetime.utcnow()
    db = f()
    try:
        fac = models.Faction(name="Гильдия Дорог", description="-", is_active=True, is_secret=True, sort_order=0,
                             created_at=now, updated_at=now, kill_points_daily_cap=cap)
        db.add(fac)
        db.flush()
        db.add(models.FactionMember(character_id=RAIDER, faction_id=fac.id, status="active", points=0,
                                    joined_at=now))
        db.add(models.FactionEnemy(faction_id=fac.id, kind="escort", ref_id=0, points=points))
        db.commit()
        return int(fac.id)
    finally:
        db.close()


def test_rewards_reputation_defense_fame_faction_and_idempotency(esc, rw):
    fid = _faction(rw, cap=20, points=30)
    _hire_ok(esc, rw, RAIDER, MATE)
    _raid_row(rw, "repelled", in_raid=(RAIDER,))                    # MATE did not fight
    _walk(rw, 4)
    rep = _rows(rw, "SELECT character_id, region_id, action FROM reputation_log WHERE is_echo = 0 "
                    "ORDER BY character_id, region_id, action")
    assert [tuple(r) for r in rep] == [
        (RAIDER, 1, "caravan_defense"), (RAIDER, 1, "caravan_escort"),
        (RAIDER, 2, "caravan_defense"), (RAIDER, 2, "caravan_escort"),
        (MATE, 1, "caravan_escort"), (MATE, 2, "caravan_escort")]
    fame = _rows(rw, "SELECT character_id, delta FROM renown_log WHERE source = 'caravan_defense'")
    assert [tuple(r) for r in fame] == [(RAIDER, 5)]
    assert _scalar(rw, "SELECT points FROM faction_members WHERE character_id = :c AND faction_id = :f",
                   c=RAIDER, f=fid) == 20                           # 30 capped by the kill day cap
    assert all(row[3] == 1 for row in _escort_rows(rw).values())

    counts = lambda: (_scalar(rw, "SELECT COUNT(*) FROM reputation_log"),  # noqa: E731
                      _scalar(rw, "SELECT COUNT(*) FROM renown_log"),
                      _scalar(rw, "SELECT points FROM faction_members WHERE character_id = :c", c=RAIDER))
    before = counts()
    _exec(rw, "UPDATE econ_caravan_escorts SET rewards_done = 0")   # a crashed claim: the re-run must add nothing
    assert escorts.escort_rewards(rw, START + timedelta(hours=3), econ_sim.SimParams()) == 2
    assert counts() == before


def test_rewards_skip_a_gone_region(esc, rw):
    _hire_ok(esc, rw, RAIDER)
    _walk(rw, 3)                                                    # arrived + delivered, rewards in the same pass
    _exec(rw, "UPDATE econ_caravan_escorts SET rewards_done = 0")
    _exec(rw, "DELETE FROM reputation_log")
    _exec(rw, "DELETE FROM Regions WHERE id = 2")
    assert escorts.escort_rewards(rw, START + timedelta(hours=3), econ_sim.SimParams()) == 1
    assert [tuple(r) for r in _rows(rw, "SELECT region_id, action FROM reputation_log WHERE is_echo = 0")] == \
        [(1, "caravan_escort")]


# ===================================================================================================================
# housekeeping
# ===================================================================================================================

def test_housekeeping_releases_stale_rows_dangling_columns_and_old_messages(esc, rw):
    _hire_ok(esc, rw, RAIDER)
    old = datetime.utcnow() - timedelta(days=8)
    _exec(rw, "INSERT INTO econ_caravan_messages (caravan_id, character_id, body, created_at) "
              "VALUES (:c, :r, 'старое', :t)", c=rw.cid, r=RAIDER, t=old)
    _exec(rw, "UPDATE econ_caravans SET status = 'delivered', finished_at = :t", t=old)       # crash after delivery
    _exec(rw, "UPDATE characters SET escort_caravan_id = 4242 WHERE id = :c", c=MATE)       # no row at all
    done = escorts.escort_housekeeping(rw, datetime.utcnow())
    assert done == 3
    assert _escort_rows(rw)[RAIDER][0] == "released"
    assert (_col(rw, RAIDER), _col(rw, MATE)) == (None, None)
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_messages") == 0
    assert escorts.escort_housekeeping(rw, datetime.utcnow()) == 0


def test_housekeeping_keeps_fresh_messages_and_live_escorts(esc, rw):
    _hire_ok(esc, rw, RAIDER)
    assert esc.post(MESSAGES, json={"character_id": RAIDER, "text": "на месте"}).status_code == 201
    assert escorts.escort_housekeeping(rw, datetime.utcnow()) == 0
    assert _col(rw, RAIDER) == rw.cid
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_messages") == 1


# ===================================================================================================================
# hidden escort on live endpoints / admin reads
# ===================================================================================================================

def test_hired_escort_hidden_from_location_and_public_card(esc, rw):
    _hire_ok(esc, rw, RAIDER)
    _pass(rw, START)                                                # now on L_ROAD1
    road = [p["id"] for p in esc.get("/characters/by_location", params={"location_id": L_ROAD1}).json()]
    gate = [p["id"] for p in esc.get("/characters/by_location", params={"location_id": L_GATE1}).json()]
    assert RAIDER not in road and RAIDER not in gate and MATE in gate
    card = esc.get(f"/characters/{RAIDER}/short_info").json()
    assert card["current_location_id"] == L_GATE1 and card["activity_lock"]["locked"] is False
    assert "карав" not in str(card).lower()


def test_profile_public_masks_escort_internal_twin_keeps_real_values(esc, rw, monkeypatch):
    """Task 16: public `/characters/{id}/profile` shows the frozen hire location and no lock; the internal
    twin (locations / dungeon checks) keeps the real road location and the `caravan_escort` lock."""
    class _UserResp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"username": "u"}

    async def _user_get(self, url, *args, **kwargs):
        return _UserResp()

    monkeypatch.setattr(main.httpx.AsyncClient, "get", _user_get)
    _hire_ok(esc, rw, RAIDER)
    _pass(rw, START)                                                # now on L_ROAD1

    public = esc.get(f"/characters/{RAIDER}/profile")
    assert public.status_code == 200, public.text
    public = public.json()
    assert public["current_location_id"] == L_GATE1 and public["activity_lock"]["locked"] is False
    assert "карав" not in str(public).lower()

    internal = esc.get(f"/characters/internal/{RAIDER}/profile", headers=INTERNAL)
    assert internal.status_code == 200, internal.text
    internal = internal.json()
    assert internal["current_location_id"] == L_ROAD1 == _loc(rw, RAIDER)
    assert internal["activity_lock"]["locked"] is True and internal["activity_lock"]["reason"] == "caravan_escort"
    assert {k: v for k, v in internal.items() if k not in ("current_location_id", "activity_lock")} == \
        {k: v for k, v in public.items() if k not in ("current_location_id", "activity_lock")}

    assert esc.get(f"/characters/internal/{RAIDER}/profile").status_code == 401
    assert esc.get(f"/characters/internal/{RAIDER}/profile",
                   headers={"X-Internal-Token": "wrong"}).status_code == 401
    # a non-escort is identical on both routes
    mate_public = esc.get(f"/characters/{MATE}/profile").json()
    assert mate_public == esc.get(f"/characters/internal/{MATE}/profile", headers=INTERNAL).json()
    assert mate_public["current_location_id"] == L_GATE1


def test_admin_list_and_detail_show_escorts(esc, rw):
    _hire_ok(esc, rw, RAIDER, MATE)
    esc.post(LEAVE, json={"character_id": RAIDER})
    _as_user(1, role="admin", permissions=["economy:read"])
    items = esc.get(ADMIN_CARAVANS, params={"kind": "physical"}).json()["items"]
    assert items[0]["escort_count"] == 1                            # active only
    detail = esc.get(f"{ADMIN_CARAVANS}/{rw.cid}").json()
    assert [(e["character_id"], e["status"], e["in_raid"]) for e in detail["escorts"]] == \
        [(RAIDER, "left", False), (MATE, "active", False)]
    assert detail["escorts"][0]["ended_at"] is not None
    _as_user(USER)                                                  # a player cannot read it
    assert esc.get(f"{ADMIN_CARAVANS}/{rw.cid}").status_code == 403


# ===================================================================================================================
# security
# ===================================================================================================================

def _all_calls(client, f, character):
    return [client.get(VIEW, params={"character_id": character}),
            client.post(_hire_url(f.cid), json={"character_id": character, "npc_id": NPC}),
            client.get(JOB, params={"character_id": character}),
            client.post(LEAVE, json={"character_id": character}),
            client.get(MESSAGES, params={"character_id": character}),
            client.post(MESSAGES, json={"character_id": character, "text": "привет"})]


def test_no_token_is_401_everywhere(esc, rw):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert [r.status_code for r in _all_calls(TestClient(app), rw, RAIDER)] == [401] * 6
    assert _col(rw, RAIDER) is None
    rw.gate.assert_not_called()


def test_someone_elses_character_is_403_everywhere(esc, rw):
    _hire_ok(esc, rw, MATE)                                         # MATE (user 8) is a real escort
    rw.gate.reset_mock()
    _as_user(USER)                                                  # user 7 tries to drive MATE
    assert [r.status_code for r in _all_calls(esc, rw, MATE)] == [403] * 6
    assert _col(rw, MATE) == rw.cid
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_messages") == 0
    rw.gate.assert_not_called()                                     # owner refused before the HTTP gate
    # an NPC is never an escort, even if somehow owned
    _exec(rw, "UPDATE characters SET user_id = :u WHERE id = :n", u=USER, n=NPC)
    resp = esc.get(f"/characters/caravans/caravaneer/{NPC}", params={"character_id": NPC})
    assert (resp.status_code, resp.json()["detail"]) == (403, escorts.MSG_NOT_PLAYER)


def test_channel_stores_injection_as_plain_text_and_rejects_oversize(esc, rw):
    _hire_ok(esc, rw, RAIDER, MATE)
    payload = "<script>alert(1)</script>'; DROP TABLE econ_caravan_messages; --"
    resp = esc.post(MESSAGES, json={"character_id": RAIDER, "text": payload})
    assert resp.status_code == 201 and resp.json()["body"] == payload
    _as_user(MATE_USER)
    page = esc.get(MESSAGES, params={"character_id": MATE}).json()  # a fellow escort reads it verbatim
    assert [m["body"] for m in page["messages"]] == [payload]
    assert esc.post(MESSAGES, json={"character_id": MATE, "text": "я" * 501}).status_code == 400
    assert esc.post(MESSAGES, json={"character_id": MATE, "text": "я" * 5000}).status_code == 422
    assert esc.post(MESSAGES, json={"character_id": 0, "text": "x"}).status_code == 422
    assert esc.get(MESSAGES, params={"character_id": MATE, "after_id": -1}).status_code == 422
    assert esc.get(MESSAGES, params={"character_id": MATE, "after_id": "1 OR 1=1"}).status_code == 422
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_caravan_messages") == 1


def test_channel_is_per_caravan(esc, rw):
    """A message of another caravan's escort never shows up in this channel."""
    _hire_ok(esc, rw, RAIDER)
    _exec(rw, "INSERT INTO econ_caravan_messages (caravan_id, character_id, body, created_at) "
              "VALUES (:c, :m, 'чужой', :t)", c=rw.cid + 100, m=MATE, t=datetime.utcnow())
    assert esc.get(MESSAGES, params={"character_id": RAIDER}).json()["messages"] == []
