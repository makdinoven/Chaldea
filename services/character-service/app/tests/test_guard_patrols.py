"""FEAT-204 QA (task 7): guard patrols.

* ``patrol_core`` (pure): ``validate`` (every Russian message, bounds), ``next_delay`` (interval ± jitter, ≥ 1 min),
  ``route_step`` (loop / pingpong incl. both ends and n = 2, resync, off-route return), ``zone_step`` (neighbours ∩
  zone, no immediate backtrack, isolated / outside-zone jump, tiny zone), ``departure_bucket`` (thresholds, held);
* ``patrol_crud.step_guard``: locks + schedule (not due = no-op, replay idempotent, ``force``), route / zone moves
  over a real ``LocationNeighbors`` table, deleted locations skipped, blocked reasons (KO / dead / battle / held by an
  encounter incl. the 30-min hold cap / not a guard) → no move + retry in 2 min, deleted NPC → config removed;
* the arrival sweep: a wanted (offline) character in the new location is caught (``source='patrol'``, the arriving
  guard, ``from_location_id`` NULL, 24 h, notice «Вас заметил патруль…» after the commit, ``by_patrol``); slip =
  silent ``slipped`` row; ``n_guards`` includes the arriving guard; ``detect_enabled`` off; exclusions (jail, open
  encounter, flee cooldown, KO, dungeon, asleep, reading, house, battle, not wanted, NPCs); outlaw; the 200 cap;
  per-character transactions; a sweep failure keeps the move;
* ``law_pass``: the patrol step + stats, ``patrols_enabled`` off;
* ``GET /characters/npcs/by_location``: the ``patrol_departure`` buckets;
* admin API ``GET/PUT /characters/admin/npcs/{id}/patrol`` + ``POST …/step``: defaults, every 400, 404, optional
  fields keep values, scheduling, warnings, outcomes, RBAC; role change → post; NPC delete cleanup;
* law settings ``patrols_enabled`` / ``patrol_encounter_hold_min``; migration 044 up / down / re-run;
* «Драться» after the patrol guard left: another free guard here, else ``guard_gone``.

Randomness: ``patrol_crud.patrol_rng`` (zone pick + jitter) and ``law_crud.detection_rng`` (detection roll).
"""

import importlib.util
import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

import battle_client
import econ_ledger
import law_core as lc
import law_crud
import law_notify
import law_pass
import main
import models
import patrol_api
import patrol_core as pc
import patrol_crud
from main import app
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, GUARD_POST, L_MARKET, L_POST, MERCHANT, R_OST, R_PASHNI, USER_ALPHA, USER_BETA, api,
    as_admin, as_user, char_row, encounter, exec_, law_payloads, law_world, now, q, rep_world, rid, rows, set_value,
    set_wanted,
)

D = Decimal

# ------------------------------------------------------------------------------------------------ the patrol world
# district 600 «Квартал» (region 10): 601 «Северная улица», 602 «Южная улица», 603 «Площадь», 604 «Глухой двор»
# (isolated); child district 607 «Задворки» (parent 600): 606 «Задворки»; 605 «Окраина» @ region 11 (outside);
# district 608 «Тупик» with one location 609. Passages (both directions): 601-602, 602-603, 601-603, 603-606, 601-605.
D_QUARTER, D_BACK, D_DEADEND = 600, 607, 608
L_N, L_S, L_SQ, L_YARD, L_EDGE, L_BACK, L_DEAD = 601, 602, 603, 604, 605, 606, 609
NAMES = {L_N: "Северная улица", L_S: "Южная улица", L_SQ: "Площадь", L_YARD: "Глухой двор", L_EDGE: "Окраина",
         L_BACK: "Задворки", L_DEAD: "Тупичок"}
EDGES = ((L_N, L_S), (L_S, L_SQ), (L_N, L_SQ), (L_SQ, L_BACK), (L_N, L_EDGE))
PATROL, POST_GUARD, MOB = 90, 70, 71
ZONE_SUBTREE = [L_N, L_S, L_SQ, L_YARD, L_BACK]
ADMIN_PERMS = ["npcs:read", "npcs:update", "npcs:delete"]
BASE = "/characters/admin/npcs"


class SeqRng:
    """``random()`` returns the given values in order, then repeats the last one."""

    def __init__(self, *values):
        self.values = list(values) or [0.5]
        self.calls = 0

    def random(self):
        self.calls += 1
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


class ExplodingRng:
    def random(self):
        raise AssertionError("no detection roll expected on this path")


def patrol_roll(monkeypatch, *values):
    rng = SeqRng(*values)
    monkeypatch.setattr(patrol_crud, "patrol_rng", lambda: rng)
    return rng


def detect_roll(monkeypatch, value):
    rng = SeqRng(value)
    monkeypatch.setattr(law_crud, "detection_rng", lambda: rng)
    return rng


def no_detect_roll(monkeypatch):
    monkeypatch.setattr(law_crud, "detection_rng", lambda: ExplodingRng())


def _add_npc(db, cid, name, role, loc, **fields):
    db.add(models.Character(id=cid, name=name, user_id=None, id_subrace=1, id_class=1, id_race=1, appearance="-",
                            avatar="-", is_npc=True, npc_role=role, npc_status=fields.get("npc_status", "alive"),
                            current_location_id=loc, level=5, currency_balance=0))


@pytest.fixture
def pw(law_world, monkeypatch):
    """law_world + the patrol districts / locations / passages + the patrol guard 90 @601 (no patrol row)."""
    f = law_world
    exec_(f, "CREATE TABLE IF NOT EXISTS LocationNeighbors (id INTEGER PRIMARY KEY AUTOINCREMENT, "
             "location_id INTEGER NOT NULL, neighbor_id INTEGER NOT NULL, energy_cost INTEGER DEFAULT 0, "
             "path_data TEXT NULL, is_auto_arrow INTEGER NOT NULL DEFAULT 0)")
    exec_(f, "INSERT INTO Districts (id, name, region_id, parent_district_id) VALUES (600, 'Квартал', 10, NULL), "
             "(607, 'Задворки', 10, 600), (608, 'Тупик', 10, NULL)")
    db = f()
    try:
        for lid, name in NAMES.items():
            district = {L_EDGE: None, L_BACK: D_BACK, L_DEAD: D_DEADEND}.get(lid, D_QUARTER)
            region = R_PASHNI if lid == L_EDGE else R_OST
            db.execute(text("INSERT INTO Locations (id, name, district_id, region_id) VALUES (:i, :n, :d, :r)"),
                       {"i": lid, "n": name, "d": district, "r": region})
        for a, b in EDGES:
            for x, y in ((a, b), (b, a)):
                db.execute(text("INSERT INTO LocationNeighbors (location_id, neighbor_id) VALUES (:a, :b)"),
                           {"a": x, "b": y})
        with econ_ledger.allow_direct_balance_write(db):
            _add_npc(db, PATROL, "Патрульный Ивар", "guard", L_N)
            db.flush()
        db.execute(text("INSERT INTO character_attributes (character_id) VALUES (:c)"), {"c": PATROL})
        db.commit()
    finally:
        db.close()
    patrol_roll(monkeypatch, 0.5)                       # pick = the middle candidate, delay = exactly the interval
    return f


@pytest.fixture
def papi(api, pw):
    """The law_world client + the patrol router's own get_db."""
    def override_get_db():
        session = pw()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[patrol_api.get_db] = override_get_db
    yield api
    app.dependency_overrides.pop(patrol_api.get_db, None)


def as_npc_admin(perms=ADMIN_PERMS):
    as_user(1, "admin", list(perms))


# ------------------------------------------------------------------------------------------------ data helpers

def set_patrol(f, npc_id=PATROL, mode="route", style="loop", route=(), zone=(), zone_kind="locations",
               district=None, interval=20, jitter=25, next_move_at="due", route_index=0, route_dir=1, last=None):
    at = now() - timedelta(minutes=1) if next_move_at == "due" else next_move_at
    db = f()
    try:
        db.add(models.GuardPatrol(npc_id=npc_id, mode=mode, route_style=style, zone_kind=zone_kind,
                                  zone_district_id=district, interval_min=interval, jitter_pct=jitter,
                                  next_move_at=at, route_index=route_index, route_dir=route_dir,
                                  last_location_id=last, updated_at=now()))
        for kind, ids in ((pc.KIND_ROUTE, route), (pc.KIND_ZONE, zone)):
            for pos, lid in enumerate(ids):
                db.add(models.GuardPatrolPoint(npc_id=npc_id, kind=kind, position=pos, location_id=lid))
        db.commit()
    finally:
        db.close()


def step(f, at=None, force=False, npc_id=PATROL):
    db = f()
    try:
        return patrol_crud.step_guard(db, npc_id, at or now(), force=force)
    finally:
        db.close()


def loc(f, cid=PATROL):
    return q(f, "SELECT current_location_id FROM characters WHERE id = :c", c=cid)


def patrol_row(f, npc_id=PATROL):
    db = f()
    try:
        p = db.get(models.GuardPatrol, npc_id)
        if p is None:
            return None
        return {c: getattr(p, c) for c in ("mode", "route_style", "zone_kind", "zone_district_id", "interval_min",
                                           "jitter_pct", "next_move_at", "route_index", "route_dir",
                                           "last_location_id", "last_moved_at", "updated_by_user_id")}
    finally:
        db.close()


def points(f, kind, npc_id=PATROL):
    return [r[0] for r in rows(f, "SELECT location_id FROM guard_patrol_points WHERE npc_id = :n AND kind = :k "
                                  "ORDER BY position", n=npc_id, k=kind)]


def put_at(f, cid, location_id):
    exec_(f, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=location_id, c=cid)


def add_post_guard(f, cid=POST_GUARD, location_id=L_S, role="guard"):
    db = f()
    try:
        with econ_ledger.allow_direct_balance_write(db):
            _add_npc(db, cid, f"НПС {cid}", role, location_id)
            db.commit()
    finally:
        db.close()
    return cid


def add_encounter(f, character_id=GAMMA, guard=PATROL, status="pending", created_at=None, location_id=L_S,
                  cooldown_until=None):
    created_at = created_at or now()
    db = f()
    try:
        enc = models.LawEncounter(character_id=character_id, region_id=R_OST, location_id=location_id,
                                  from_location_id=None, guard_npc_id=guard, is_outlaw=False, has_jail=True,
                                  level_code="offender", wanted_value=150, fine=100, jail_hours=4, flee_used=False,
                                  status=status, source="move", created_at=created_at,
                                  expires_at=created_at + timedelta(hours=24), cooldown_until=cooldown_until)
        db.add(enc)
        db.commit()
        return int(enc.id)
    finally:
        db.close()


def add_battle(f, character_id, battle_id=900, status="in_progress"):
    exec_(f, "INSERT INTO battles (id, status) VALUES (:b, :s)", b=battle_id, s=status)
    exec_(f, "INSERT INTO battle_participants (battle_id, character_id) VALUES (:b, :c)", b=battle_id,
          c=character_id)


def law_settings(f, **overrides):
    db = f()
    try:
        row = db.get(models.LawSettings, 1)
        for name, value in overrides.items():
            setattr(row, name, value)
        db.commit()
    finally:
        db.close()


def seed_severity(f):
    for code, pct in {"suspect": 60, "offender": 80, "criminal": 100, "villain": 120, "enemy": 140}.items():
        exec_(f, "UPDATE law_levels SET detect_pct = :p WHERE code = :c", p=pct, c=code)


def encounters_of(f, character_id=ALPHA):
    db = f()
    try:
        out = db.query(models.LawEncounter).filter(models.LawEncounter.character_id == character_id) \
            .order_by(models.LawEncounter.id).all()
        for e in out:
            db.expunge(e)
        return out
    finally:
        db.close()


def law_log(f, character_id=ALPHA):
    return rows(f, "SELECT action, reason, ref_id, chance_pct, roll_pct FROM law_log WHERE character_id = :c "
                   "ORDER BY id", c=character_id)


def route_patrol_into_south(f, **kw):
    """Patrol 90 @601 with the loop route 601 → 602, due now."""
    set_patrol(f, route=(L_N, L_S), **kw)


def dec(v):
    return None if v is None else D(str(v)).quantize(D("0.01"))


# =============================================================================================== pure: validate

def _v(mode="route", style="loop", kind="locations", route=(601, 602), zone=(601, 602), district=None,
       interval=20, jitter=25):
    return pc.validate(mode, style, kind, list(route), list(zone), district, interval, jitter)


def test_validate_ok_configs():
    assert _v() == []
    assert _v(mode="post", route=(), zone=()) == []
    assert _v(mode="zone", kind="district", district=7, zone=()) == []
    assert _v(mode="zone", route=(601,)) == []                        # the inactive list: only its size counts
    assert _v(mode="route", style="pingpong", route=(601, 602, 601)) == []
    assert _v(interval=5, jitter=0) == [] and _v(interval=1440, jitter=50) == []


@pytest.mark.parametrize("kwargs,message", [
    (dict(mode="fly"), "Неизвестный режим патруля"),
    (dict(style="zigzag"), "Неизвестный порядок обхода маршрута"),
    (dict(kind="planet"), "Неизвестный вид зоны патруля"),
    (dict(interval=4), "Интервал патруля: от 5 до 1440 минут"),
    (dict(interval=1441), "Интервал патруля: от 5 до 1440 минут"),
    (dict(jitter=-1), "Разброс интервала: от 0 до 50 %"),
    (dict(jitter=51), "Разброс интервала: от 0 до 50 %"),
    (dict(route=(0, 602)), "Неверный идентификатор локации"),
    (dict(mode="post", zone=(-3, 1)), "Неверный идентификатор локации"),
    (dict(route=tuple(range(1, 32))), "В маршруте не больше 30 точек"),
    (dict(mode="post", zone=tuple(range(1, 102))), "В зоне патруля не больше 100 локаций"),
    (dict(route=(601,)), "В маршруте нужно хотя бы 2 точки"),
    (dict(route=()), "В маршруте нужно хотя бы 2 точки"),
    (dict(route=(601, 601, 602)), "Одна и та же локация не может идти в маршруте два раза подряд"),
    (dict(route=(601, 602, 601)), "Одна и та же локация не может идти в маршруте два раза подряд"),   # loop wrap
    (dict(mode="zone", zone=(601,)), "В зоне патруля нужно хотя бы 2 локации"),
    (dict(mode="zone", zone=(601, 602, 601)), "Локации в зоне патруля не должны повторяться"),
    (dict(mode="zone", kind="district", district=None), "Выберите район зоны патруля"),
])
def test_validate_messages(kwargs, message):
    assert message in _v(**kwargs)


def test_validate_unknown_mode_short_circuits():
    assert _v(mode="x", interval=0, jitter=99) == ["Неизвестный режим патруля"]


def test_validate_collects_several_errors():
    errors = _v(interval=1, jitter=70, route=(601,))
    assert len(errors) == 3


def test_validate_route_upper_bound_is_inclusive():
    assert _v(route=tuple(range(1, 31))) == []
    assert _v(mode="zone", zone=tuple(range(1, 101))) == []


# =============================================================================================== pure: next_delay

@pytest.mark.parametrize("interval,jitter,u,minutes", [
    (20, 0, 0.0, 20), (20, 0, 0.99, 20),
    (20, 25, 0.0, 15), (20, 25, 0.5, 20), (20, 25, 1.0, 25),
    (20, 50, 0.0, 10), (20, 50, 1.0, 30),
    (1440, 25, 0.5, 1440),
])
def test_next_delay(interval, jitter, u, minutes):
    assert pc.next_delay(interval, jitter, u) == timedelta(minutes=minutes)


def test_next_delay_stays_within_the_jitter_band():
    for i in range(100):
        d = pc.next_delay(20, 25, i / 100)
        assert timedelta(minutes=15) <= d <= timedelta(minutes=25)


def test_next_delay_floor_and_clamps():
    assert pc.next_delay(1, 50, 0.0) == pc.MIN_DELAY == timedelta(minutes=1)      # 30 s -> 1 min
    assert pc.next_delay(20, 90, 0.0) == timedelta(minutes=10)                    # jitter clamped to 50
    assert pc.next_delay(20, -5, 0.0) == timedelta(minutes=20)                    # jitter clamped to 0
    assert pc.next_delay(20, 25, 7.0) == timedelta(minutes=25)                    # u clamped to 1
    assert pc.next_delay(20, 25, -1.0) == timedelta(minutes=15)                   # u clamped to 0


# =============================================================================================== pure: route_step

def test_route_loop_advances_and_wraps():
    pts = [1, 2, 3]
    assert pc.route_step(pts, 0, 1, "loop", 1) == (2, 1, 1)
    assert pc.route_step(pts, 1, 1, "loop", 2) == (3, 2, 1)
    assert pc.route_step(pts, 2, 1, "loop", 3) == (1, 0, 1)
    assert pc.route_step(pts, 2, -1, "loop", 3) == (1, 0, 1)                      # loop ignores the direction


def test_route_pingpong_reverses_at_both_ends():
    pts = [1, 2, 3]
    assert pc.route_step(pts, 0, 1, "pingpong", 1) == (2, 1, 1)
    assert pc.route_step(pts, 1, 1, "pingpong", 2) == (3, 2, 1)
    assert pc.route_step(pts, 2, 1, "pingpong", 3) == (2, 1, -1)                  # far end -> back
    assert pc.route_step(pts, 1, -1, "pingpong", 2) == (1, 0, -1)
    assert pc.route_step(pts, 0, -1, "pingpong", 1) == (2, 1, 1)                  # near end -> forward


def test_route_pingpong_two_points_alternate():
    assert pc.route_step([1, 2], 0, 1, "pingpong", 1) == (2, 1, 1)
    assert pc.route_step([1, 2], 1, 1, "pingpong", 2) == (1, 0, -1)
    assert pc.route_step([1, 2], 0, -1, "pingpong", 1) == (2, 1, 1)


def test_route_resync_when_the_index_is_stale():
    assert pc.route_step([1, 2, 3], 0, 1, "loop", 3) == (1, 0, 1)                 # at 3, index says 1
    assert pc.route_step([1, 2, 3], 99, 1, "loop", 2) == (3, 2, 1)                # index out of range
    assert pc.route_step([1, 2, 1, 3], 3, 1, "pingpong", 1) == (2, 1, 1)          # first position of 1


def test_route_off_the_route_returns_to_the_first_point():
    assert pc.route_step([1, 2, 3], 2, -1, "pingpong", 77) == (1, 0, 1)
    assert pc.route_step([1, 2, 3], 1, 1, "loop", None) == (1, 0, 1)


def test_route_degenerate_lists():
    assert pc.route_step([], 0, 1, "loop", 1) == (None, 0, 1)
    assert pc.route_step([5], 0, 1, "loop", 5) == (5, 0, 1)


# =============================================================================================== pure: zone_step

def first(values):
    return values[0]


def last_of(values):
    return values[-1]


def test_zone_picks_a_neighbour_inside_the_zone_only():
    seen = []

    def pick(values):
        seen.append(list(values))
        return values[0]

    assert pc.zone_step(1, [1, 2, 3], [2, 3, 9], None, pick) == (2, False)
    assert seen == [[2, 3]]                                                      # 9 is outside, sorted candidates


def test_zone_no_immediate_backtrack():
    assert pc.zone_step(1, [1, 2, 3], [2, 3], 2, first) == (3, False)
    assert pc.zone_step(1, [1, 2, 3], [2], 2, first) == (2, False)               # the only way out is back


def test_zone_isolated_jumps_to_another_zone_location():
    assert pc.zone_step(4, [1, 2, 4], [], None, first) == (1, True)
    assert pc.zone_step(4, [1, 2, 4], [9], None, last_of) == (2, True)          # neighbour outside the zone
    assert pc.zone_step(4, [1, 2, 4], [4], None, first) == (1, True)            # self-loop is not a move


def test_zone_guard_outside_the_zone_jumps_in():
    assert pc.zone_step(77, [1, 2], [], None, last_of) == (2, True)
    assert pc.zone_step(None, [1, 2], [], None, first) == (1, True)


def test_zone_too_small_means_no_move():
    assert pc.zone_step(1, [1], [2], None, first) == (None, False)
    assert pc.zone_step(1, [1, 1, 1], [2], None, first) == (None, False)         # duplicates collapse
    assert pc.zone_step(1, [], [], None, first) == (None, False)


# =============================================================================================== pure: bucket

@pytest.mark.parametrize("delta,expected", [
    (timedelta(minutes=-10), "soon"), (timedelta(0), "soon"), (timedelta(minutes=5), "soon"),
    (timedelta(minutes=5, seconds=1), "short"), (timedelta(minutes=15), "short"),
    (timedelta(minutes=15, seconds=1), "long"), (timedelta(hours=3), "long"),
])
def test_departure_bucket_thresholds(delta, expected):
    t = now()
    assert pc.departure_bucket(t + delta, t, False) == expected


def test_departure_bucket_held_and_unscheduled():
    t = now()
    assert pc.departure_bucket(None, t, False) is None
    assert pc.departure_bucket(None, t, True) == "long"
    assert pc.departure_bucket(t, t, True) == "long"


# =============================================================================================== step: schedule

def test_no_row_or_post_is_not_patrolling(pw):
    assert step(pw, force=True).outcome == "not_patrolling"
    set_patrol(pw, mode="post", route=(L_N, L_S))
    assert step(pw, force=True).outcome == "not_patrolling"
    assert loc(pw) == L_N


def test_not_due_is_a_noop_and_force_moves(pw):
    t = now()
    route_patrol_into_south(pw, next_move_at=t + timedelta(minutes=5))
    out = step(pw, at=t)
    assert out.outcome == "not_due" and loc(pw) == L_N
    assert patrol_row(pw)["next_move_at"] == t + timedelta(minutes=5)
    out = step(pw, at=t, force=True)
    assert (out.outcome, out.from_location_id, out.to_location_id) == ("moved", L_N, L_S)
    assert loc(pw) == L_S


def test_unscheduled_moving_patrol_is_not_due(pw):
    route_patrol_into_south(pw, next_move_at=None)
    assert step(pw).outcome == "not_due" and loc(pw) == L_N


def test_due_exactly_now_moves(pw):
    t = now()
    route_patrol_into_south(pw, next_move_at=t)
    assert step(pw, at=t).outcome == "moved"


def test_move_updates_location_and_state(pw):
    t = now()
    route_patrol_into_south(pw)
    out = step(pw, at=t)
    assert out.outcome == "moved"
    p = patrol_row(pw)
    assert (p["route_index"], p["route_dir"], p["last_location_id"], p["last_moved_at"]) == (1, 1, L_N, t)
    assert p["next_move_at"] == t + timedelta(minutes=20)                        # rng 0.5 -> the exact interval
    assert loc(pw) == L_S


def test_replay_at_the_same_instant_is_idempotent(pw):
    t = now()
    route_patrol_into_south(pw)
    assert step(pw, at=t).outcome == "moved"
    assert step(pw, at=t).outcome == "not_due"
    assert loc(pw) == L_S


@pytest.mark.parametrize("u,minutes", [(0.0, 15), (0.5, 20), (1.0, 25)])
def test_jitter_scheduling(pw, monkeypatch, u, minutes):
    patrol_roll(monkeypatch, u)
    t = now()
    route_patrol_into_south(pw)
    step(pw, at=t)
    assert patrol_row(pw)["next_move_at"] == t + timedelta(minutes=minutes)


def test_jitter_zero_is_the_exact_interval(pw, monkeypatch):
    patrol_roll(monkeypatch, 0.0)
    t = now()
    route_patrol_into_south(pw, interval=37, jitter=0)
    step(pw, at=t)
    assert patrol_row(pw)["next_move_at"] == t + timedelta(minutes=37)


def test_due_guards_selects_only_due_moving_patrols(pw):
    t = now()
    add_post_guard(pw, 72, L_N)
    add_post_guard(pw, 73, L_N)
    add_post_guard(pw, 74, L_N)
    set_patrol(pw, npc_id=PATROL, route=(L_N, L_S), next_move_at=t - timedelta(minutes=1))
    set_patrol(pw, npc_id=72, route=(L_N, L_S), next_move_at=t - timedelta(minutes=5))
    set_patrol(pw, npc_id=73, mode="post", next_move_at=t - timedelta(minutes=9))
    set_patrol(pw, npc_id=74, mode="zone", zone=(L_N, L_S), next_move_at=t + timedelta(minutes=1))
    db = pw()
    try:
        assert patrol_crud.due_guards(db, t, 10) == [72, PATROL]
        assert patrol_crud.due_guards(db, t, 1) == [72]
    finally:
        db.close()


# =============================================================================================== step: route

def test_route_loop_walks_and_wraps(pw):
    set_patrol(pw, route=(L_N, L_S, L_SQ))
    t = now()
    path = []
    for i in range(4):
        step(pw, at=t + timedelta(hours=i), force=True)
        path.append(loc(pw))
    assert path == [L_S, L_SQ, L_N, L_S]


def test_route_pingpong_walks_back_and_forth(pw):
    set_patrol(pw, route=(L_N, L_S, L_SQ), style="pingpong")
    t = now()
    path = []
    for i in range(6):
        step(pw, at=t + timedelta(hours=i), force=True)
        path.append(loc(pw))
    assert path == [L_S, L_SQ, L_S, L_N, L_S, L_SQ]


def test_route_guard_moved_off_the_route_returns_to_the_first_point(pw):
    put_at(pw, PATROL, L_MARKET)
    set_patrol(pw, route=(L_S, L_SQ), route_index=1)
    out = step(pw)
    assert (out.outcome, out.from_location_id, out.to_location_id) == ("moved", L_MARKET, L_S)
    assert patrol_row(pw)["route_index"] == 0


def test_route_resyncs_a_stale_index(pw):
    put_at(pw, PATROL, L_SQ)
    set_patrol(pw, route=(L_N, L_S, L_SQ), route_index=0)
    step(pw)
    assert loc(pw) == L_N and patrol_row(pw)["route_index"] == 0


def test_route_skips_deleted_locations(pw):
    set_patrol(pw, route=(L_N, 9998, L_S))
    assert step(pw).to_location_id == L_S


def test_route_with_fewer_than_two_live_points_stays_and_reschedules(pw):
    t = now()
    set_patrol(pw, route=(L_N, 9998))
    out = step(pw, at=t)
    assert out.outcome == "stayed" and loc(pw) == L_N
    assert patrol_row(pw)["next_move_at"] == t + timedelta(minutes=20)


# =============================================================================================== step: zone

@pytest.mark.parametrize("u,target", [(0.0, L_S), (0.99, L_SQ)])
def test_zone_district_walks_over_passages_inside_the_zone(pw, monkeypatch, u, target):
    patrol_roll(monkeypatch, u)
    set_patrol(pw, mode="zone", zone_kind="district", district=D_QUARTER)
    out = step(pw)
    assert (out.outcome, out.to_location_id) == ("moved", target)              # never 605 (outside the zone)


def test_zone_random_walk_never_leaves_the_zone(pw, monkeypatch):
    set_patrol(pw, mode="zone", zone_kind="district", district=D_QUARTER)
    t = now()
    for i in range(30):
        patrol_roll(monkeypatch, (i * 37 % 100) / 100)
        step(pw, at=t + timedelta(hours=i), force=True)
        assert loc(pw) in ZONE_SUBTREE


def test_zone_does_not_backtrack_immediately(pw, monkeypatch):
    patrol_roll(monkeypatch, 0.0)
    set_patrol(pw, mode="zone", zone_kind="district", district=D_QUARTER, last=L_S)
    assert step(pw).to_location_id == L_SQ
    assert patrol_row(pw)["last_location_id"] == L_N


def test_zone_backtracks_when_it_is_the_only_way(pw, monkeypatch):
    patrol_roll(monkeypatch, 0.0)
    put_at(pw, PATROL, L_BACK)                                                  # 606: only neighbour 603
    set_patrol(pw, mode="zone", zone_kind="district", district=D_QUARTER, last=L_SQ)
    assert step(pw).to_location_id == L_SQ


def test_zone_isolated_location_jumps(pw, monkeypatch):
    patrol_roll(monkeypatch, 0.0)
    put_at(pw, PATROL, L_YARD)                                                  # 604 has no passages
    set_patrol(pw, mode="zone", zone_kind="district", district=D_QUARTER)
    out = step(pw)
    assert (out.outcome, out.to_location_id) == ("moved", L_N)


def test_zone_guard_outside_the_zone_jumps_in(pw, monkeypatch):
    patrol_roll(monkeypatch, 0.99)
    put_at(pw, PATROL, L_MARKET)
    set_patrol(pw, mode="zone", zone=(L_S, L_SQ))
    assert step(pw).to_location_id == L_SQ


def test_zone_explicit_locations(pw, monkeypatch):
    patrol_roll(monkeypatch, 0.0)
    set_patrol(pw, mode="zone", zone=(L_N, L_SQ, L_BACK))
    assert step(pw).to_location_id == L_SQ                                      # 602 is not in this zone


def test_zone_shrunk_below_two_stays_and_reschedules(pw):
    t = now()
    set_patrol(pw, mode="zone", zone=(L_N, 9998))
    out = step(pw, at=t)
    assert out.outcome == "stayed" and loc(pw) == L_N
    assert patrol_row(pw)["next_move_at"] == t + timedelta(minutes=20)
    exec_(pw, "DELETE FROM guard_patrols")
    set_patrol(pw, mode="zone", zone_kind="district", district=D_DEADEND)
    assert step(pw).outcome == "stayed"


# =============================================================================================== step: blocked

def _assert_blocked(f, out, reason, t):
    assert (out.outcome, out.blocked_reason) == ("blocked", reason)
    assert (out.checked, out.encounters) == (0, 0)
    assert loc(f) == L_N
    assert patrol_row(f)["next_move_at"] == t + pc.BLOCKED_RETRY == t + timedelta(minutes=2)


def test_blocked_knocked_out(pw):
    t = now()
    exec_(pw, "UPDATE characters SET unconscious_until = :u WHERE id = :g", u=t + timedelta(hours=1), g=PATROL)
    route_patrol_into_south(pw)
    _assert_blocked(pw, step(pw, at=t), "ko", t)


def test_ko_over_moves_again(pw):
    t = now()
    exec_(pw, "UPDATE characters SET unconscious_until = :u WHERE id = :g", u=t - timedelta(seconds=1), g=PATROL)
    route_patrol_into_south(pw)
    assert step(pw, at=t).outcome == "moved"


def test_blocked_dead(pw):
    t = now()
    exec_(pw, "UPDATE characters SET npc_status = 'dead' WHERE id = :g", g=PATROL)
    route_patrol_into_south(pw)
    _assert_blocked(pw, step(pw, at=t), "dead", t)


def test_blocked_in_battle(pw):
    t = now()
    add_battle(pw, PATROL)
    route_patrol_into_south(pw)
    _assert_blocked(pw, step(pw, at=t), "battle", t)


@pytest.mark.parametrize("status", ["finished", "cancelled"])
def test_finished_battle_does_not_block(pw, status):
    add_battle(pw, PATROL, status=status)
    route_patrol_into_south(pw)
    assert step(pw).outcome == "moved"


def test_blocked_by_a_fresh_pending_encounter(pw):
    t = now()
    add_encounter(pw, created_at=t - timedelta(minutes=10), location_id=L_N)
    route_patrol_into_south(pw)
    _assert_blocked(pw, step(pw, at=t), "encounter", t)


def test_hold_cap_expired_pending_encounter_lets_the_guard_go(pw):
    t = now()
    add_encounter(pw, created_at=t - timedelta(minutes=31), location_id=L_N)
    route_patrol_into_south(pw)
    assert step(pw, at=t).outcome == "moved"


def test_hold_cap_boundary_is_the_setting(pw):
    t = now()
    law_settings(pw, patrol_encounter_hold_min=60)
    add_encounter(pw, created_at=t - timedelta(minutes=45), location_id=L_N)
    route_patrol_into_south(pw)
    assert step(pw, at=t).blocked_reason == "encounter"
    law_settings(pw, patrol_encounter_hold_min=0)                              # 0 = never held by a pending one
    assert step(pw, at=t, force=True).outcome == "moved"


def test_fighting_encounter_holds_regardless_of_age(pw):
    t = now()
    add_encounter(pw, status="fighting", created_at=t - timedelta(hours=5), location_id=L_N)
    route_patrol_into_south(pw)
    assert step(pw, at=t).blocked_reason == "encounter"


@pytest.mark.parametrize("status", ["fined", "jailed", "fled", "guard_gone", "won", "expired"])
def test_closed_encounter_does_not_hold(pw, status):
    add_encounter(pw, status=status, location_id=L_N)
    route_patrol_into_south(pw)
    assert step(pw).outcome == "moved"


def test_encounter_of_another_guard_does_not_hold(pw):
    add_encounter(pw, guard=GUARD_POST, location_id=L_POST)
    route_patrol_into_south(pw)
    assert step(pw).outcome == "moved"


def test_blocked_not_a_guard_any_more(pw):
    t = now()
    exec_(pw, "UPDATE characters SET npc_role = 'merchant' WHERE id = :g", g=PATROL)
    route_patrol_into_south(pw)
    _assert_blocked(pw, step(pw, at=t), "not_guard", t)


def test_force_never_bypasses_a_block(pw):
    t = now()
    add_battle(pw, PATROL)
    route_patrol_into_south(pw, next_move_at=t + timedelta(hours=1))
    _assert_blocked(pw, step(pw, at=t, force=True), "battle", t)


def test_blocked_guard_is_retried_in_two_minutes(pw):
    t = now()
    exec_(pw, "UPDATE characters SET unconscious_until = :u WHERE id = :g", u=t + timedelta(seconds=90), g=PATROL)
    route_patrol_into_south(pw)
    assert step(pw, at=t).outcome == "blocked"
    assert step(pw, at=t + timedelta(minutes=1)).outcome == "not_due"
    assert step(pw, at=t + timedelta(minutes=2)).outcome == "moved"
    assert loc(pw) == L_S


def test_deleted_npc_drops_its_patrol(pw):
    set_patrol(pw, route=(L_N, L_S), zone=(L_N, L_SQ))
    exec_(pw, "DELETE FROM character_attributes WHERE character_id = :g", g=PATROL)
    exec_(pw, "DELETE FROM characters WHERE id = :g", g=PATROL)
    assert step(pw).outcome == "not_patrolling"
    assert patrol_row(pw) is None
    assert q(pw, "SELECT COUNT(*) FROM guard_patrol_points WHERE npc_id = :g", g=PATROL) == 0


def test_override_target_seam_is_inert(pw):
    db = pw()
    try:
        assert patrol_crud._override_target(db, None, now()) is None
    finally:
        db.close()


def test_override_target_seam_drives_the_move(pw, monkeypatch):
    monkeypatch.setattr(patrol_crud, "_override_target", lambda db, patrol, at: L_EDGE)
    route_patrol_into_south(pw)
    assert step(pw).to_location_id == L_EDGE                                    # the pursuit hook reuses the move


# =============================================================================================== sweep: caught

def test_wanted_offline_character_is_caught_by_the_arriving_patrol(pw, stub_law_notify_send):
    t = now()
    add_post_guard(pw)                                                          # 70 @602: lower id than the patrol
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    route_patrol_into_south(pw)
    out = step(pw, at=t)
    assert (out.outcome, out.checked, out.encounters, out.slipped) == ("moved", 1, 1, 0)
    (enc,) = encounters_of(pw)
    assert (enc.source, enc.guard_npc_id, enc.location_id, enc.from_location_id) == ("patrol", PATROL, L_S, None)
    assert (enc.status, enc.level_code, enc.region_id) == ("pending", "offender", R_OST)
    assert enc.expires_at == t + timedelta(hours=24)
    assert char_row(pw, ALPHA).law_encounter_id == enc.id
    assert char_row(pw, ALPHA).current_location_id == L_S                       # nobody is moved by the catch
    (payload,) = law_payloads(stub_law_notify_send)
    assert payload["target_value"] == USER_ALPHA and payload["ws_type"] == "law_encounter"
    assert payload["category"] == "system"
    assert payload["message"].startswith("Вас заметил патруль стражи в «Южная улица». Решите, как поступить, "
                                         "в течение ")
    assert payload["ws_data"] == {"encounter_id": enc.id, "character_id": ALPHA}


def test_patrol_encounter_out_has_by_patrol(pw):
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    route_patrol_into_south(pw)
    step(pw)
    (enc,) = encounters_of(pw)
    db = pw()
    try:
        assert law_crud.encounter_out(db, enc)["by_patrol"] is True
        enc.source = "move"
        assert law_crud.encounter_out(db, enc)["by_patrol"] is False
    finally:
        db.close()


def test_player_encounter_endpoint_shows_by_patrol(papi, pw):
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    route_patrol_into_south(pw)
    step(pw)
    as_user(USER_ALPHA)
    resp = papi.get(f"/characters/{ALPHA}/law/encounter")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    enc = body.get("encounter", body)
    assert enc["by_patrol"] is True and enc["guard_name"] == "Патрульный Ивар"
    assert "guard_npc_id" not in enc and "source" not in enc                    # staff-only fields


def test_notice_is_published_after_the_commit(pw, stub_law_notify_send):
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    route_patrol_into_south(pw)
    committed = []
    stub_law_notify_send.side_effect = lambda payloads: committed.append(
        q(pw, "SELECT law_encounter_id FROM characters WHERE id = :c", c=ALPHA))
    step(pw)
    assert len(committed) == 1 and committed[0] is not None


def test_patrol_message_without_a_location_name():
    t = now()
    msg = law_notify.patrol_encounter_message(None, t + timedelta(hours=24), t)
    assert msg.startswith("Вас заметил патруль стражи. Решите, как поступить, в течение ")


def test_n_guards_includes_the_arriving_guard(pw, monkeypatch):
    seed_severity(pw)                                                           # offender ×0.8, safe base 100
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    add_post_guard(pw)
    detect_roll(monkeypatch, 0.4242)
    route_patrol_into_south(pw)
    step(pw)
    (row,) = law_log(pw)
    assert row[0] == "encounter" and dec(row[3]) == D("88.00")                  # 80 × (1 + 10 % per extra guard)


def test_alone_the_arriving_guard_counts_as_one(pw, monkeypatch):
    seed_severity(pw)
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    detect_roll(monkeypatch, 0.4242)
    route_patrol_into_south(pw)
    step(pw)
    assert dec(law_log(pw)[0][3]) == D("80.00")


def test_slip_past_a_patrol_is_silent(pw, monkeypatch, stub_law_notify_send):
    seed_severity(pw)
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    rng = detect_roll(monkeypatch, 0.9999)
    route_patrol_into_south(pw)
    out = step(pw)
    assert (out.outcome, out.checked, out.encounters, out.slipped) == ("moved", 1, 0, 1)
    assert rng.calls == 1
    assert encounters_of(pw) == [] and char_row(pw, ALPHA).law_encounter_id is None
    ((action, reason, ref_id, chance, roll),) = law_log(pw)
    assert (action, reason, ref_id) == ("slipped", "patrol", L_S)
    assert (dec(chance), dec(roll)) == (D("80.00"), D("99.99"))
    stub_law_notify_send.assert_not_called()


def test_every_arrival_rerolls(pw, monkeypatch):
    seed_severity(pw)
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    rng = detect_roll(monkeypatch, 0.9999)
    set_patrol(pw, route=(L_N, L_S), style="pingpong")
    t = now()
    for i in range(4):                                                          # 602, 601, 602, 601
        step(pw, at=t + timedelta(minutes=i), force=True)
    assert rng.calls == 2
    rng.values = [0.0]
    step(pw, at=t + timedelta(minutes=10), force=True)
    assert len(encounters_of(pw)) == 1


def test_detection_off_always_catches_without_a_roll(pw, monkeypatch):
    law_settings(pw, detect_enabled=False)
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    no_detect_roll(monkeypatch)
    route_patrol_into_south(pw)
    assert step(pw).encounters == 1


def test_outlaw_without_wanted_is_caught(pw):
    put_at(pw, ALPHA, L_S)
    set_value(pw, ALPHA, R_OST, -800)                                           # «Вне закона» in Ost
    route_patrol_into_south(pw)
    assert step(pw).encounters == 1
    (enc,) = encounters_of(pw)
    assert enc.is_outlaw is True


# =============================================================================================== sweep: exclusions

def _jailed(f, t):
    exec_(f, "UPDATE characters SET jailed_until = :u WHERE id = :c", u=t + timedelta(hours=5), c=ALPHA)


def _open_encounter(f, t):
    enc_id = add_encounter(f, character_id=ALPHA, guard=GUARD_POST, location_id=L_POST)
    exec_(f, "UPDATE characters SET law_encounter_id = :e WHERE id = :c", e=enc_id, c=ALPHA)


def _flee_cooldown(f, t):
    add_encounter(f, character_id=ALPHA, guard=GUARD_POST, status="fled", location_id=L_S,
                  cooldown_until=t + timedelta(minutes=30))


def _ko(f, t):
    exec_(f, "UPDATE characters SET unconscious_until = :u WHERE id = :c", u=t + timedelta(hours=1), c=ALPHA)


def _dungeon(f, t):
    exec_(f, "UPDATE characters SET dungeon_session_id = 5 WHERE id = :c", c=ALPHA)


def _asleep(f, t):
    exec_(f, "UPDATE characters SET asleep_since = :u WHERE id = :c", u=t - timedelta(hours=1), c=ALPHA)


def _reading(f, t):
    exec_(f, "UPDATE characters SET reading_since = :u WHERE id = :c", u=t - timedelta(hours=1), c=ALPHA)


def _house(f, t):
    exec_(f, "UPDATE characters SET house_room_id = 3 WHERE id = :c", c=ALPHA)


def _battle(f, t):
    add_battle(f, ALPHA, battle_id=901)


def _not_wanted(f, t):
    exec_(f, "DELETE FROM character_wanted WHERE character_id = :c", c=ALPHA)


def _wanted_elsewhere(f, t):
    _not_wanted(f, t)
    set_wanted(f, ALPHA, R_PASHNI, 400)


@pytest.mark.parametrize("setup", [_jailed, _open_encounter, _flee_cooldown, _ko, _dungeon, _asleep, _reading,
                                   _house, _battle, _not_wanted, _wanted_elsewhere],
                         ids=lambda fn: fn.__name__.strip("_"))
def test_sweep_exclusions_never_roll_nor_catch(pw, monkeypatch, stub_law_notify_send, setup):
    t = now()
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    setup(pw, t)
    before = q(pw, "SELECT COUNT(*) FROM law_encounters WHERE character_id = :c", c=ALPHA)
    no_detect_roll(monkeypatch)
    route_patrol_into_south(pw)
    out = step(pw, at=t)
    assert (out.outcome, out.encounters, out.slipped) == ("moved", 0, 0)
    assert q(pw, "SELECT COUNT(*) FROM law_encounters WHERE character_id = :c", c=ALPHA) == before
    assert q(pw, "SELECT COUNT(*) FROM law_log WHERE character_id = :c AND action = 'slipped'", c=ALPHA) == 0
    stub_law_notify_send.assert_not_called()


def test_npcs_are_never_swept(pw, monkeypatch):
    put_at(pw, MERCHANT, L_S)
    add_post_guard(pw, 75, L_S, role="bandit")
    no_detect_roll(monkeypatch)
    route_patrol_into_south(pw)
    out = step(pw)
    assert (out.outcome, out.checked) == ("moved", 0)


def test_only_players_in_the_arrival_location_are_checked(pw):
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    set_wanted(pw, BETA, R_OST, 150)                                            # Beta stays at 100
    route_patrol_into_south(pw)
    out = step(pw)
    assert (out.checked, out.encounters) == (1, 1)
    assert encounters_of(pw, BETA) == []


def test_several_players_each_get_a_check(pw, stub_law_notify_send):
    for cid in (ALPHA, BETA, GAMMA):
        put_at(pw, cid, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    set_wanted(pw, BETA, R_OST, 150)
    route_patrol_into_south(pw)
    out = step(pw)
    assert (out.checked, out.encounters) == (3, 2)                              # Gamma is not wanted
    assert {p["target_value"] for p in law_payloads(stub_law_notify_send)} == {USER_ALPHA, USER_BETA}


def test_sweep_cap(pw, monkeypatch):
    assert patrol_crud.PATROL_SWEEP_LIMIT == 200
    monkeypatch.setattr(patrol_crud, "PATROL_SWEEP_LIMIT", 2)
    for cid in (ALPHA, BETA, GAMMA):
        put_at(pw, cid, L_S)
        set_wanted(pw, cid, R_OST, 150)
    route_patrol_into_south(pw)
    out = step(pw)
    assert (out.checked, out.encounters) == (2, 2)
    assert encounters_of(pw, GAMMA) == []                                       # by id: Alpha, Beta first


def test_one_failing_character_does_not_stop_the_others(pw, monkeypatch, stub_law_notify_send):
    put_at(pw, ALPHA, L_S)
    put_at(pw, BETA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    set_wanted(pw, BETA, R_OST, 150)
    real = law_crud.check_patrol_arrival

    def flaky(db, character, location_id, **kw):
        result = real(db, character, location_id, **kw)
        if character.id == ALPHA:
            raise RuntimeError("boom after writing")
        return result

    monkeypatch.setattr(law_crud, "check_patrol_arrival", flaky)
    route_patrol_into_south(pw)
    out = step(pw)
    assert (out.outcome, out.checked, out.encounters) == ("moved", 1, 1)
    assert encounters_of(pw, ALPHA) == [] and char_row(pw, ALPHA).law_encounter_id is None   # rolled back
    assert len(encounters_of(pw, BETA)) == 1
    assert [p["target_value"] for p in law_payloads(stub_law_notify_send)] == [USER_BETA]
    assert loc(pw) == L_S


def test_sweep_failure_keeps_the_move(pw, monkeypatch):
    def broken(*a, **kw):
        raise RuntimeError("sweep down")

    monkeypatch.setattr(patrol_crud, "_sweep", broken)
    route_patrol_into_south(pw)
    out = step(pw)
    assert (out.outcome, out.checked) == ("moved", 0)
    assert loc(pw) == L_S and patrol_row(pw)["last_location_id"] == L_N


def test_check_patrol_arrival_ignores_a_character_elsewhere(pw, monkeypatch):
    set_wanted(pw, ALPHA, R_OST, 150)
    put_at(pw, PATROL, L_S)
    no_detect_roll(monkeypatch)
    db = pw()
    try:
        ch = law_crud.lock_character(db, ALPHA)                                # Alpha @100
        assert law_crud.check_patrol_arrival(db, ch, L_S, guard_id=PATROL) == law_crud.EntryResult()
        npc = law_crud.lock_character(db, MERCHANT)
        assert law_crud.check_patrol_arrival(db, npc, L_MARKET, guard_id=PATROL) == law_crud.EntryResult()
        assert law_crud.check_patrol_arrival(db, None, L_S, guard_id=PATROL) == law_crud.EntryResult()
    finally:
        db.close()


def test_check_entry_still_uses_the_first_guard(pw):
    """Regression: the entry check keeps guards[0] and its own source (the shared core takes guard_id only for
    patrols)."""
    add_post_guard(pw)
    put_at(pw, PATROL, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    db = pw()
    try:
        ch = law_crud.lock_character(db, ALPHA)
        ch.current_location_id = L_S
        res = law_crud.check_entry(db, ch, L_S, "move", from_location_id=L_MARKET)
        assert (res.encounter.guard_npc_id, res.encounter.source) == (POST_GUARD, "move")
        assert res.encounter.from_location_id == L_MARKET
        db.rollback()
        ch = law_crud.lock_character(db, ALPHA)
        res = law_crud.check_entry(db, ch, L_S, "bogus")
        assert res.encounter.source == "move"                                   # unknown source is clamped
        db.rollback()
    finally:
        db.close()


# =============================================================================================== law pass

def test_law_pass_moves_due_patrols_and_counts(pw):
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    route_patrol_into_south(pw)
    stats = law_pass.run_pass(pw, now(), claim=False)
    assert stats["patrol_moves"] == 1 and stats["patrol_checked"] == 1
    assert stats["patrol_encounters"] == 1 and stats["patrol_slips"] == 0
    assert loc(pw) == L_S


def test_law_pass_counts_blocked(pw):
    add_battle(pw, PATROL)
    route_patrol_into_south(pw)
    stats = law_pass.run_pass(pw, now(), claim=False)
    assert (stats["patrol_moves"], stats["patrol_blocked"]) == (0, 1)


def test_law_pass_skips_patrols_when_switched_off(pw):
    law_settings(pw, patrols_enabled=False)
    route_patrol_into_south(pw)
    stats = law_pass.run_pass(pw, now(), claim=False)
    assert stats["patrol_moves"] == 0 and loc(pw) == L_N


def test_law_pass_one_bad_guard_does_not_stop_the_rest(pw, monkeypatch):
    add_post_guard(pw, 72, L_N)
    set_patrol(pw, npc_id=72, route=(L_N, L_SQ), next_move_at=now() - timedelta(minutes=5))
    route_patrol_into_south(pw)
    real = patrol_crud.step_guard

    def flaky(db, npc_id, at=None, **kw):
        if npc_id == 72:
            raise RuntimeError("bad guard")
        return real(db, npc_id, at, **kw)

    monkeypatch.setattr(patrol_crud, "step_guard", flaky)
    stats = law_pass.run_pass(pw, now(), claim=False)
    assert stats["patrol_moves"] == 1 and loc(pw) == L_S and loc(pw, 72) == L_N


# =============================================================================================== public hint

def _npcs(api, location_id):
    resp = api.get(f"/characters/npcs/by_location?location_id={location_id}")
    assert resp.status_code == 200, resp.text
    return {n["id"]: n for n in resp.json()}


@pytest.mark.parametrize("delta,bucket", [
    (timedelta(minutes=-3), "soon"), (timedelta(minutes=3), "soon"), (timedelta(minutes=10), "short"),
    (timedelta(minutes=25), "long"),
])
def test_patrol_departure_buckets(papi, pw, delta, bucket):
    route_patrol_into_south(pw, next_move_at=now() + delta)
    npc = _npcs(papi, L_N)[PATROL]
    assert npc["patrol_departure"] == bucket


def test_departure_held_guard_is_long(papi, pw):
    add_encounter(pw, location_id=L_N)
    route_patrol_into_south(pw, next_move_at=now() + timedelta(minutes=1))
    assert _npcs(papi, L_N)[PATROL]["patrol_departure"] == "long"


def test_departure_none_for_posts_and_non_guards(papi, pw):
    out = _npcs(papi, L_MARKET)
    assert out and all(n["patrol_departure"] is None for n in out.values())     # guards 52/54 + merchants
    set_patrol(pw, mode="post", route=(L_N, L_S), next_move_at=now())
    assert _npcs(papi, L_N)[PATROL]["patrol_departure"] is None


def test_departure_none_when_switched_off(papi, pw):
    law_settings(pw, patrols_enabled=False)
    route_patrol_into_south(pw, next_move_at=now() + timedelta(minutes=3))
    assert _npcs(papi, L_N)[PATROL]["patrol_departure"] is None


def test_departure_payload_has_no_minutes(papi, pw):
    route_patrol_into_south(pw, next_move_at=now() + timedelta(minutes=12))
    npc = _npcs(papi, L_N)[PATROL]
    assert set(npc) == {"id", "name", "avatar", "level", "class_name", "race_name", "npc_role", "patrol_departure"}


def test_patrol_guard_appears_in_the_new_location(papi, pw):
    route_patrol_into_south(pw)
    step(pw)
    assert PATROL not in _npcs(papi, L_N) and PATROL in _npcs(papi, L_S)


# =============================================================================================== admin API: GET

def test_get_defaults_without_a_row(papi, pw):
    as_npc_admin()
    resp = papi.get(f"{BASE}/{PATROL}/patrol")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data == {
        "npc_id": PATROL, "npc_role": "guard", "mode": "post", "route_style": "loop", "route": [],
        "zone_kind": "district", "zone_district_id": None, "zone_district_name": None, "zone_locations": [],
        "interval_min": 20, "jitter_pct": 25, "current_location_id": L_N, "current_location_name": "Северная улица",
        "next_move_at": None, "last_moved_at": None, "blocked_reason": None, "patrols_enabled": True,
        "warnings": [],
    }


def test_get_live_blocked_reason_and_switch(papi, pw):
    exec_(pw, "UPDATE characters SET unconscious_until = :u WHERE id = :g", u=now() + timedelta(hours=1), g=PATROL)
    law_settings(pw, patrols_enabled=False)
    route_patrol_into_south(pw)
    as_npc_admin()
    data = papi.get(f"{BASE}/{PATROL}/patrol").json()
    assert (data["blocked_reason"], data["patrols_enabled"], data["mode"]) == ("ko", False, "route")
    assert [p["name"] for p in data["route"]] == ["Северная улица", "Южная улица"]


def test_get_non_guard_npc_is_allowed(papi, pw):
    as_npc_admin()
    data = papi.get(f"{BASE}/{MERCHANT}/patrol").json()
    assert (data["npc_role"], data["mode"]) == ("merchant", "post")


@pytest.mark.parametrize("method,suffix", [("get", "/patrol"), ("put", "/patrol"), ("post", "/patrol/step")])
@pytest.mark.parametrize("target", ["mob", "player", "missing"])
def test_404_for_mobs_players_and_missing(papi, pw, method, suffix, target):
    add_post_guard(pw, MOB, L_S, role="mob")
    npc_id = {"mob": MOB, "player": ALPHA, "missing": 99999}[target]
    as_npc_admin()
    kwargs = {"json": {"mode": "post"}} if method == "put" else {}
    resp = getattr(papi, method)(f"{BASE}/{npc_id}{suffix}", **kwargs)
    assert resp.status_code == 404 and resp.json()["detail"] == "NPC не найден"


# =============================================================================================== admin API: PUT

def _put(api, body, npc_id=PATROL):
    as_npc_admin()
    return api.put(f"{BASE}/{npc_id}/patrol", json=body)


def test_put_route_stores_and_schedules(papi, pw):
    t = now()
    resp = _put(papi, {"mode": "route", "route_style": "pingpong", "route_location_ids": [L_N, L_S, L_SQ],
                       "interval_min": 30, "jitter_pct": 10})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "route" and data["route_style"] == "pingpong" and data["warnings"] == []
    assert [(p["location_id"], p["name"]) for p in data["route"]] == [
        (L_N, "Северная улица"), (L_S, "Южная улица"), (L_SQ, "Площадь")]
    assert (data["interval_min"], data["jitter_pct"]) == (30, 10)
    p = patrol_row(pw)
    assert (p["route_index"], p["route_dir"], p["updated_by_user_id"]) == (0, 1, 1)
    assert t + timedelta(minutes=29) <= p["next_move_at"] <= t + timedelta(minutes=31)
    assert points(pw, "route") == [L_N, L_S, L_SQ]


def test_put_route_index_is_the_current_position(papi, pw):
    put_at(pw, PATROL, L_SQ)
    _put(papi, {"mode": "route", "route_location_ids": [L_N, L_S, L_SQ]})
    assert patrol_row(pw)["route_index"] == 2


def test_put_optional_fields_keep_values_and_schedule(papi, pw):
    assert _put(papi, {"mode": "route", "route_style": "pingpong", "route_location_ids": [L_N, L_S],
                       "zone_kind": "locations", "zone_location_ids": [L_N, L_SQ], "interval_min": 45,
                       "jitter_pct": 5}).status_code == 200
    marker = now() + timedelta(hours=9)
    exec_(pw, "UPDATE guard_patrols SET next_move_at = :m", m=marker)
    data = _put(papi, {"mode": "route"}).json()
    assert data["route_style"] == "pingpong" and data["zone_kind"] == "locations"
    assert [p["location_id"] for p in data["route"]] == [L_N, L_S]
    assert [p["location_id"] for p in data["zone_locations"]] == [L_N, L_SQ]
    assert (data["interval_min"], data["jitter_pct"]) == (45, 5)
    assert patrol_row(pw)["next_move_at"] == marker                             # nothing changed -> kept
    _put(papi, {"mode": "route", "interval_min": 50})
    assert patrol_row(pw)["next_move_at"] != marker                             # interval changed -> rescheduled


def test_put_switching_modes_keeps_both_lists(papi, pw):
    _put(papi, {"mode": "zone", "zone_kind": "locations", "zone_location_ids": [L_N, L_S]})
    _put(papi, {"mode": "route", "route_location_ids": [L_S, L_SQ]})
    assert points(pw, "zone") == [L_N, L_S] and points(pw, "route") == [L_S, L_SQ]
    data = _put(papi, {"mode": "post"}).json()
    assert data["mode"] == "post" and data["next_move_at"] is None and data["warnings"] == []
    assert patrol_row(pw)["next_move_at"] is None
    assert points(pw, "zone") == [L_N, L_S] and points(pw, "route") == [L_S, L_SQ]


def test_put_zone_district(papi, pw):
    data = _put(papi, {"mode": "zone", "zone_kind": "district", "zone_district_id": D_QUARTER}).json()
    assert (data["zone_district_id"], data["zone_district_name"], data["warnings"]) == (D_QUARTER, "Квартал", [])
    assert patrol_row(pw)["next_move_at"] is not None


def test_put_explicit_null_district_clears_it(papi, pw):
    _put(papi, {"mode": "zone", "zone_kind": "district", "zone_district_id": D_QUARTER})
    _put(papi, {"mode": "route", "route_location_ids": [L_N, L_S], "zone_district_id": None})
    assert patrol_row(pw)["zone_district_id"] is None
    _put(papi, {"mode": "zone", "zone_kind": "district", "zone_district_id": D_QUARTER})
    _put(papi, {"mode": "route"})                                               # omitted -> kept
    assert patrol_row(pw)["zone_district_id"] == D_QUARTER


def test_put_inactive_list_drops_unknown_locations_silently(papi, pw):
    resp = _put(papi, {"mode": "route", "route_location_ids": [L_N, L_S], "zone_location_ids": [L_N, 9999]})
    assert resp.status_code == 200
    assert points(pw, "zone") == [L_N]


@pytest.mark.parametrize("body,message", [
    ({"mode": "fly"}, "Неизвестный режим патруля"),
    ({"mode": "route", "route_style": "zigzag", "route_location_ids": [L_N, L_S]},
     "Неизвестный порядок обхода маршрута"),
    ({"mode": "zone", "zone_kind": "planet", "zone_location_ids": [L_N, L_S]}, "Неизвестный вид зоны патруля"),
    ({"mode": "route", "route_location_ids": [L_N, L_S], "interval_min": 4}, "Интервал патруля: от 5 до 1440 минут"),
    ({"mode": "route", "route_location_ids": [L_N, L_S], "interval_min": 1441},
     "Интервал патруля: от 5 до 1440 минут"),
    ({"mode": "route", "route_location_ids": [L_N, L_S], "jitter_pct": 51}, "Разброс интервала: от 0 до 50 %"),
    ({"mode": "route", "route_location_ids": [L_N, L_S], "jitter_pct": -1}, "Разброс интервала: от 0 до 50 %"),
    ({"mode": "route", "route_location_ids": [L_N]}, "В маршруте нужно хотя бы 2 точки"),
    ({"mode": "route"}, "В маршруте нужно хотя бы 2 точки"),
    ({"mode": "route", "route_location_ids": list(range(1, 32))}, "В маршруте не больше 30 точек"),
    ({"mode": "route", "route_location_ids": [L_N, L_N, L_S]},
     "Одна и та же локация не может идти в маршруте два раза подряд"),
    ({"mode": "route", "route_location_ids": [L_N, L_S, L_N]},
     "Одна и та же локация не может идти в маршруте два раза подряд"),
    ({"mode": "route", "route_location_ids": [0, L_S]}, "Неверный идентификатор локации"),
    ({"mode": "route", "route_location_ids": [L_N, 9999, 9998]}, "Локация не найдена: 9998, 9999"),
    ({"mode": "zone", "zone_kind": "locations", "zone_location_ids": [L_N]},
     "В зоне патруля нужно хотя бы 2 локации"),
    ({"mode": "zone", "zone_kind": "locations", "zone_location_ids": [L_N, L_S, L_N]},
     "Локации в зоне патруля не должны повторяться"),
    ({"mode": "zone", "zone_kind": "locations", "zone_location_ids": list(range(1, 102))},
     "В зоне патруля не больше 100 локаций"),
    ({"mode": "zone", "zone_kind": "locations", "zone_location_ids": [L_N, 9999]}, "Локация не найдена: 9999"),
    ({"mode": "zone", "zone_kind": "district"}, "Выберите район зоны патруля"),
    ({"mode": "zone", "zone_kind": "district", "zone_district_id": 9999}, "Район не найден"),
    ({"mode": "zone", "zone_kind": "district", "zone_district_id": D_DEADEND},
     "В районе должно быть хотя бы 2 локации"),
])
def test_put_validation_400(papi, pw, body, message):
    resp = _put(papi, body)
    assert resp.status_code == 400, resp.text
    assert message in resp.json()["detail"]
    assert patrol_row(pw) is None and points(pw, "route") == [] and points(pw, "zone") == []


def test_put_validation_joins_several_errors(papi, pw):
    resp = _put(papi, {"mode": "route", "route_location_ids": [L_N], "interval_min": 1, "jitter_pct": 90})
    assert resp.status_code == 400
    assert resp.json()["detail"].count("; ") == 2


def test_put_pingpong_may_revisit_the_first_point(papi, pw):
    resp = _put(papi, {"mode": "route", "route_style": "pingpong", "route_location_ids": [L_N, L_S, L_N]})
    assert resp.status_code == 200, resp.text


def test_put_non_guard_only_post(papi, pw):
    resp = _put(papi, {"mode": "route", "route_location_ids": [L_N, L_S]}, npc_id=MERCHANT)
    assert resp.status_code == 400 and resp.json()["detail"] == "Патруль доступен только стражникам"
    assert _put(papi, {"mode": "post"}, npc_id=MERCHANT).status_code == 200


@pytest.mark.parametrize("body", [
    {"mode": "'; DROP TABLE guard_patrols; --"},
    {"mode": "route", "route_location_ids": ["abc", L_S]},
    {"mode": "route", "route_location_ids": list(range(1, 202))},
    {"mode": "route", "interval_min": "много"},
    {},
])
def test_put_bad_input_is_422(papi, pw, body):
    assert _put(papi, body).status_code == 422
    assert patrol_row(pw) is None


def test_put_injection_like_short_mode_is_a_plain_400(papi, pw):
    resp = _put(papi, {"mode": "' OR 1=1"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Неизвестный режим патруля"
    assert q(pw, "SELECT COUNT(*) FROM characters") > 0


def test_put_non_integer_ids_are_rejected(papi, pw):
    resp = _put(papi, {"mode": "route", "route_location_ids": ["<script>alert(1)</script>", L_S]})
    assert resp.status_code == 422


# ------------------------------------------------------------------------------------------------ warnings

def test_warning_for_non_adjacent_route_points(papi, pw):
    data = _put(papi, {"mode": "route", "route_location_ids": [L_N, L_S, L_YARD]}).json()
    assert data["warnings"] == [
        "«Южная улица» и «Глухой двор» не соседние — стражник перейдёт напрямую",
        "«Глухой двор» и «Северная улица» не соседние — стражник перейдёт напрямую",        # the loop closes
    ]
    data = _put(papi, {"mode": "route", "route_style": "pingpong"}).json()
    assert data["warnings"] == ["«Южная улица» и «Глухой двор» не соседние — стражник перейдёт напрямую"]


def test_warning_two_point_loop_is_one_pair(papi, pw):
    data = _put(papi, {"mode": "route", "route_location_ids": [L_S, L_YARD]}).json()
    assert len(data["warnings"]) == 1


def test_warning_zone_over_several_regions(papi, pw):
    data = _put(papi, {"mode": "zone", "zone_kind": "locations", "zone_location_ids": [L_N, L_EDGE]}).json()
    assert data["warnings"] == ["Локации зоны находятся в разных регионах"]


def test_warning_zone_without_passages(papi, pw):
    data = _put(papi, {"mode": "zone", "zone_kind": "locations", "zone_location_ids": [L_S, L_YARD]}).json()
    assert data["warnings"] == ["Между локациями зоны нет переходов — стражник будет перемещаться напрямую"]


def test_put_saved_config_moves_on_step(papi, pw):
    _put(papi, {"mode": "route", "route_location_ids": [L_N, L_S]})
    assert step(pw, force=True).to_location_id == L_S


# =============================================================================================== admin API: step

def test_step_endpoint_moves_and_reports(papi, pw, stub_law_notify_send):
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    route_patrol_into_south(pw, next_move_at=now() + timedelta(hours=1))         # not due: «Шаг сейчас» forces
    as_npc_admin()
    resp = papi.post(f"{BASE}/{PATROL}/patrol/step")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (data["outcome"], data["from_location_id"], data["to_location_id"]) == ("moved", L_N, L_S)
    assert (data["checked"], data["encounters"], data["slipped"], data["blocked_reason"]) == (1, 1, 0, None)
    assert data["patrol"]["current_location_id"] == L_S
    assert data["patrol"]["last_moved_at"] is not None
    assert len(law_payloads(stub_law_notify_send)) == 1


def test_step_endpoint_blocked(papi, pw):
    add_encounter(pw, location_id=L_N)
    route_patrol_into_south(pw)
    as_npc_admin()
    data = papi.post(f"{BASE}/{PATROL}/patrol/step").json()
    assert (data["outcome"], data["blocked_reason"]) == ("blocked", "encounter")
    assert data["patrol"]["blocked_reason"] == "encounter"
    assert loc(pw) == L_N


def test_step_endpoint_not_patrolling(papi, pw):
    as_npc_admin()
    data = papi.post(f"{BASE}/{PATROL}/patrol/step").json()
    assert data["outcome"] == "not_patrolling" and data["to_location_id"] is None


def test_step_endpoint_stayed(papi, pw):
    set_patrol(pw, route=(L_N, 9998))
    as_npc_admin()
    assert papi.post(f"{BASE}/{PATROL}/patrol/step").json()["outcome"] == "stayed"


# =============================================================================================== admin API: RBAC

def test_rbac_read_only_can_get_but_not_write(papi, pw):
    as_npc_admin(["npcs:read"])
    assert papi.get(f"{BASE}/{PATROL}/patrol").status_code == 200
    assert papi.put(f"{BASE}/{PATROL}/patrol", json={"mode": "post"}).status_code == 403
    assert papi.post(f"{BASE}/{PATROL}/patrol/step").status_code == 403
    assert patrol_row(pw) is None


def test_rbac_update_without_read_cannot_get(papi, pw):
    as_npc_admin(["npcs:update"])
    assert papi.get(f"{BASE}/{PATROL}/patrol").status_code == 403
    assert papi.put(f"{BASE}/{PATROL}/patrol", json={"mode": "post"}).status_code == 200


@pytest.mark.parametrize("role,perms", [("user", []), ("editor", ["items:create"]),
                                        ("moderator", ["reputation:read", "characters:read"])])
def test_rbac_roles_without_npc_permissions_are_rejected(papi, pw, role, perms):
    as_user(5, role, perms)
    assert papi.get(f"{BASE}/{PATROL}/patrol").status_code == 403
    assert papi.put(f"{BASE}/{PATROL}/patrol", json={"mode": "post"}).status_code == 403
    assert papi.post(f"{BASE}/{PATROL}/patrol/step").status_code == 403


def test_unauthenticated_is_401(papi, pw):
    from auth_http import get_current_user_via_http
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert papi.get(f"{BASE}/{PATROL}/patrol").status_code == 401
    assert papi.put(f"{BASE}/{PATROL}/patrol", json={"mode": "post"}).status_code == 401
    assert papi.post(f"{BASE}/{PATROL}/patrol/step").status_code == 401


# =============================================================================================== NPC role / delete

def test_role_change_away_from_guard_resets_to_post(papi, pw):
    set_patrol(pw, route=(L_N, L_S), zone=(L_N, L_SQ))
    as_npc_admin()
    resp = papi.put(f"{BASE}/{PATROL}", json={"npc_role": "merchant"}, headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200, resp.text
    p = patrol_row(pw)
    assert (p["mode"], p["next_move_at"]) == ("post", None)
    assert points(pw, "route") == [L_N, L_S] and points(pw, "zone") == [L_N, L_SQ]


def test_other_npc_edits_keep_the_patrol(papi, pw):
    set_patrol(pw, route=(L_N, L_S))
    as_npc_admin()
    resp = papi.put(f"{BASE}/{PATROL}", json={"name": "Патрульный Ивар Старший"},
                    headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200, resp.text
    assert patrol_row(pw)["mode"] == "route"


def test_npc_delete_removes_the_patrol(papi, pw, monkeypatch):
    class _NoNet:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            raise RuntimeError("no network in tests")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(main.httpx, "AsyncClient", _NoNet)
    set_patrol(pw, route=(L_N, L_S), zone=(L_N, L_SQ))
    as_npc_admin()
    resp = papi.delete(f"{BASE}/{PATROL}", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200, resp.text
    assert patrol_row(pw) is None
    assert q(pw, "SELECT COUNT(*) FROM guard_patrol_points WHERE npc_id = :g", g=PATROL) == 0


def test_disable_and_delete_helpers_without_a_row_are_noops(pw):
    db = pw()
    try:
        patrol_crud.disable_patrol(db, PATROL)
        patrol_crud.delete_patrol(db, PATROL)
        db.commit()
    finally:
        db.close()
    assert patrol_row(pw) is None


# =============================================================================================== law settings

def test_law_settings_get_has_the_patrol_fields(papi, pw):
    as_admin()
    s = papi.get("/characters/admin/law/settings").json()["settings"]
    assert (s["patrols_enabled"], s["patrol_encounter_hold_min"]) == (True, 30)


def test_law_settings_put_stores_and_omission_keeps(papi, pw):
    as_admin()
    body = papi.get("/characters/admin/law/settings").json()
    body["settings"].update(patrols_enabled=False, patrol_encounter_hold_min=45)
    resp = papi.put("/characters/admin/law/settings", json=body)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["settings"]["patrols_enabled"], resp.json()["settings"]["patrol_encounter_hold_min"]) == \
        (False, 45)
    body = papi.get("/characters/admin/law/settings").json()
    body["settings"].pop("patrols_enabled")
    body["settings"].pop("patrol_encounter_hold_min")
    resp = papi.put("/characters/admin/law/settings", json=body)
    assert resp.status_code == 200, resp.text
    assert not q(pw, "SELECT patrols_enabled FROM law_settings")
    assert q(pw, "SELECT patrol_encounter_hold_min FROM law_settings") == 45


@pytest.mark.parametrize("value,ok", [(-1, False), (0, True), (1440, True), (1441, False)])
def test_law_settings_hold_bounds(papi, pw, value, ok):
    as_admin()
    body = papi.get("/characters/admin/law/settings").json()
    body["settings"]["patrol_encounter_hold_min"] = value
    resp = papi.put("/characters/admin/law/settings", json=body)
    if ok:
        assert resp.status_code == 200, resp.text
    else:
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Сколько патрульный ждёт ответа: от 0 до 1440 мин"


def test_law_settings_defaults_in_code():
    assert lc.DEFAULT_SETTINGS.patrols_enabled is True
    assert lc.DEFAULT_SETTINGS.patrol_encounter_hold_min == 30
    assert lc.SOURCE_PATROL == "patrol" and lc.SOURCE_PATROL in lc.ENTRY_SOURCES


# =============================================================================================== «Драться» later

def _caught_then_guard_leaves(f):
    put_at(f, ALPHA, L_S)
    set_wanted(f, ALPHA, R_OST, 150)
    set_patrol(f, route=(L_N, L_S))
    t = now()
    step(f, at=t, force=True)
    (enc,) = encounters_of(f)
    exec_(f, "UPDATE law_encounters SET created_at = :c WHERE id = :e", c=t - timedelta(minutes=31), e=enc.id)
    out = step(f, at=t, force=True)                                             # the hold is over -> back to 601
    assert out.outcome == "moved" and loc(f) == L_N
    return enc.id


@pytest.fixture
def battle(monkeypatch):
    mock = AsyncMock(return_value=555)
    monkeypatch.setattr(battle_client, "create_guard_battle", mock)
    return mock


def _fight(api, enc_id):
    as_user(USER_ALPHA)
    return api.post(f"/characters/{ALPHA}/law/encounter/{enc_id}/choice",
                    json={"choice": "fight", "request_id": rid()})


def test_fight_after_the_patrol_left_takes_another_free_guard(papi, pw, battle):
    enc_id = _caught_then_guard_leaves(pw)
    add_post_guard(pw)                                                          # 70 stands at 602
    resp = _fight(papi, enc_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "fight"
    battle.assert_awaited_once_with(enc_id, ALPHA, POST_GUARD)
    assert encounter(pw, enc_id).guard_npc_id == POST_GUARD


def test_fight_after_the_patrol_left_without_guards_is_guard_gone(papi, pw, battle):
    enc_id = _caught_then_guard_leaves(pw)
    resp = _fight(papi, enc_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "guard_gone"
    assert encounter(pw, enc_id).status == "guard_gone"
    assert char_row(pw, ALPHA).law_encounter_id is None
    battle.assert_not_awaited()


def test_fight_while_the_patrol_waits_uses_it(papi, pw, battle):
    put_at(pw, ALPHA, L_S)
    set_wanted(pw, ALPHA, R_OST, 150)
    route_patrol_into_south(pw)
    step(pw)
    (enc,) = encounters_of(pw)
    assert step(pw, force=True).blocked_reason == "encounter"                   # held within 30 min
    resp = _fight(papi, enc.id)
    assert resp.json()["result"] == "fight"
    battle.assert_awaited_once_with(enc.id, ALPHA, PATROL)
    exec_(pw, "UPDATE law_encounters SET created_at = :c WHERE id = :e", c=now() - timedelta(hours=5), e=enc.id)
    assert step(pw, force=True).blocked_reason == "encounter"                   # fighting holds regardless


# =============================================================================================== migration 044

_MIG_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "044_guard_patrols.py")


def _load_044():
    spec = importlib.util.spec_from_file_location("migration_044_guard_patrols_qa", _MIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeMySQL:
    """information_schema + DDL emulation: tables -> columns, indexes."""

    def __init__(self, tables=("law_settings", "law_encounters")):
        self.tables = {t: {"columns": set(), "indexes": set()} for t in tables}
        self.statements = []

    def execute(self, clause, params=None):
        sql = str(clause)
        result = MagicMock()
        t = self.tables.get(params["t"])
        if "information_schema.columns" in sql:
            result.scalar.return_value = int(t is not None and params["c"] in t["columns"])
        elif "information_schema.tables" in sql:
            result.scalar.return_value = int(t is not None)
        elif "information_schema.statistics" in sql:
            result.scalar.return_value = int(t is not None and params["i"] in t["indexes"])
        else:
            raise AssertionError(f"unexpected bind SQL: {sql}")
        return result

    def op_execute(self, sql):
        sql = str(sql)
        self.statements.append(sql)
        words = sql.replace("(", " ( ").split()
        if sql.startswith("CREATE TABLE"):
            name = words[2]
            assert name not in self.tables, f"duplicate table {name}"
            self.tables[name] = {"columns": {"*"}, "indexes": set()}
        elif sql.startswith("DROP TABLE"):
            del self.tables[words[2]]
        elif sql.startswith("ALTER TABLE") and words[3:5] == ["ADD", "COLUMN"]:
            cols = self.tables[words[2]]["columns"]
            assert words[5] not in cols, f"duplicate column {words[5]}"
            cols.add(words[5])
        elif sql.startswith("ALTER TABLE") and words[3:5] == ["DROP", "COLUMN"]:
            self.tables[words[2]]["columns"].remove(words[5])
        elif sql.startswith("CREATE INDEX"):
            idx = self.tables[words[4]]["indexes"]
            assert words[2] not in idx
            idx.add(words[2])
        elif sql.startswith("DROP INDEX"):
            self.tables[words[4]]["indexes"].remove(words[2])
        else:
            raise AssertionError(f"unexpected DDL: {sql}")


@pytest.fixture
def fake_mysql(monkeypatch):
    mig = _load_044()
    db = FakeMySQL()
    monkeypatch.setattr(mig.op, "get_bind", lambda: db, raising=False)
    monkeypatch.setattr(mig.op, "execute", db.op_execute, raising=False)
    return mig, db


def _state(db):
    return {name: (set(t["columns"]), set(t["indexes"])) for name, t in db.tables.items()}


UPGRADED = {
    "law_settings": ({"patrols_enabled", "patrol_encounter_hold_min"}, set()),
    "law_encounters": (set(), {"ix_law_enc_guard"}),
    "guard_patrols": ({"*"}, set()),
    "guard_patrol_points": ({"*"}, set()),
}


def test_migration_044_revision():
    mig = _load_044()
    assert mig.revision == "044_guard_patrols" and len(mig.revision) <= 32
    assert mig.down_revision == "043_guard_detection"


def test_migration_044_up(fake_mysql):
    mig, db = fake_mysql
    mig.upgrade()
    assert _state(db) == UPGRADED


def test_migration_044_rerun_is_a_noop(fake_mysql):
    mig, db = fake_mysql
    mig.upgrade()
    before = len(db.statements)
    mig.upgrade()
    assert len(db.statements) == before


def test_migration_044_down_then_up(fake_mysql):
    mig, db = fake_mysql
    mig.upgrade()
    mig.downgrade()
    assert _state(db) == {"law_settings": (set(), set()), "law_encounters": (set(), set())}
    before = len(db.statements)
    mig.downgrade()                                                             # re-run of the downgrade: no-op
    assert len(db.statements) == before
    mig.upgrade()
    assert _state(db) == UPGRADED


def test_migration_044_partial_state_adds_only_the_missing(fake_mysql):
    mig, db = fake_mysql
    db.tables["guard_patrols"] = {"columns": {"*"}, "indexes": set()}
    db.tables["law_settings"]["columns"].add("patrols_enabled")
    mig.upgrade()
    assert _state(db) == UPGRADED
    assert not any("CREATE TABLE guard_patrols " in s for s in db.statements)


def test_migration_044_without_the_law_tables(monkeypatch):
    mig = _load_044()
    db = FakeMySQL(tables=())
    monkeypatch.setattr(mig.op, "get_bind", lambda: db, raising=False)
    monkeypatch.setattr(mig.op, "execute", db.op_execute, raising=False)
    mig.upgrade()
    assert set(db.tables) == {"guard_patrols", "guard_patrol_points"}         # columns / index skipped
    mig.downgrade()
    assert db.tables == {}


def test_migration_044_ddl_matches_the_models():
    mig = _load_044()
    for ddl in (mig._CREATE_PATROLS, mig._CREATE_POINTS):
        assert "ENUM" not in ddl and "FOREIGN KEY" not in ddl
    for name in models.GuardPatrol.__table__.columns.keys():
        assert f" {name} " in mig._CREATE_PATROLS, name
    for name in models.GuardPatrolPoint.__table__.columns.keys():
        assert f" {name} " in mig._CREATE_POINTS, name
    assert "ix_guard_patrols_due" in mig._CREATE_PATROLS
    assert "uq_guard_patrol_point" in mig._CREATE_POINTS and "ix_guard_patrol_point_loc" in mig._CREATE_POINTS
    defaults = {c: ddl.split("DEFAULT ")[1] for _t, c, ddl in mig._COLUMNS}
    assert defaults == {"patrols_enabled": "1", "patrol_encounter_hold_min": "30"}
    assert {"patrols_enabled", "patrol_encounter_hold_min"} <= set(models.LawSettings.__table__.columns.keys())
    assert "ix_law_enc_guard" in {i.name for i in models.LawEncounter.__table__.indexes}
    for ident in ("ix_guard_patrols_due", "uq_guard_patrol_point", "ix_guard_patrol_point_loc", "ix_law_enc_guard"):
        assert len(ident) <= 64
