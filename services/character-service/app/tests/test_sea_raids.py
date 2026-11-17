"""FEAT-214 QA (T10): the sea monster raid lifecycle, the internal result endpoint, the safe-landing / delete fixes
and the public ship fields (features/FEAT-214 §3.8–3.10).

* start (after the ship commit): spawn the pack, battle-service (mocked) → ``fighting`` + battle notices with the
  battle link; a refusal (409 / transport / crash) or a spawn failure → ``aborted`` + despawn; a row starts once;
* settle: the battle-service callback (token, won / lost / aborted, idempotent ``already``, ``unknown``, a foreign
  battle id) and the poll (finished / 404 / running / error, only after 2 min); stale ``starting`` rows expire or
  attach to their tagged battle; leftover monsters are despawned; the hold is released by the next pass;
* ``safe_land`` / the pass never move a player out of a battle and land him once the battle is over; ``delete_ship``
  is refused while a deck battle / an active raid runs;
* ``ShipPublicOut``: ``storm`` / ``departure_postponed`` / ``raid`` in the deck and the captain views.
"""

import json
from datetime import timedelta

import pytest

import battle_client
import models
import sea_admin
import sea_core
import sea_pass
import sea_raid_crud
from tests.sea_storm_world import (  # noqa: F401  (fixtures)
    MONSTER_TPL, active_mob_ids, add_monster, add_storm, http_error, in_battle, raid, raids, set_params, storm,
    ws_events,
)
from tests.sea_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, CAPTAIN, DECK, GAMMA, INTERNAL, P_A, START, USER_ALPHA, USER_BETA, Z1, Z2, Z3, api, as_user, buy,
    client, depart, exec_, law_world, loc, now, place, q, rep_world, rows, run_ship, sea, set_ship, ship,
)

RESULT = "/characters/internal/sea/raid-result"
DELETE = "/characters/admin/sea/ships/{}"


def _raid_at_sea(f, *players, max_active=1):
    """Depart, put ``players`` aboard, a monster in 502 → the attack on the 502 entry; returns (t, raid rows)."""
    add_monster(f, Z2, max_active=max_active)
    _out, t = depart(f)
    for cid in players:
        place(f, cid, DECK)
    run_ship(f, t + timedelta(minutes=10))
    return t, raids(f)


def _row(f, *, status="starting", players=(ALPHA,), mob_ids=None, battle_id=None, created=None, started=None,
         placed=None, despawned=False, key=None):
    """A raid row inserted directly (the roll itself is covered by test_sea_storm_pass)."""
    add_monster(f, Z2) if q(f, "SELECT COUNT(*) FROM mob_templates WHERE id = :t", t=MONSTER_TPL) == 0 else None
    db = f()
    try:
        # JSON columns: an explicit None would be stored as JSON 'null' — leave them unset for SQL NULL (as plan_raid)
        extra = {k: v for k, v in (("placed_ids", placed), ("mob_ids", mob_ids)) if v is not None}
        r = models.SeaRaid(ship_id=f.ship_id, attack_key=key or f"k{now().timestamp()}{status}{battle_id}",
                           group_no=0, deck_location_id=DECK, zone_id=Z2, mob_template_id=MONSTER_TPL,
                           monster_name="Кракен", player_ids=list(players), battle_id=battle_id, status=status,
                           mobs_despawned=despawned, created_at=created or now(), started_at=started, **extra)
        db.add(r)
        db.commit()
        return int(r.id)
    finally:
        db.close()


def _followups(f, when=None):
    return sea_raid_crud.raid_followups(f, when or now())


def _post(c, body, headers=INTERNAL):
    return c.post(RESULT, json=body, headers=headers)


# =============================================================================================== start

def test_battle_refusal_aborts_and_despawns(storm, stub_law_notify_send):
    storm.bs.error = battle_client.BattleServiceError("refused", 409, "Некому защищать палубу")
    t, (r,) = _raid_at_sea(storm, ALPHA)
    assert (r.status, r.battle_id, r.mobs_despawned) == ("aborted", None, True)
    assert r.ended_at is not None and len(r.mob_ids) == 1 and active_mob_ids(storm) == []
    assert [n for n in ws_events(stub_law_notify_send, "raid") if "battle_id" in n["ws_data"]] == []
    out = run_ship(storm, t + timedelta(minutes=12))
    assert sea_pass.EV_HOLD_RELEASED in out.events
    assert ship(storm).hold_until is None and ship(storm).next_zone_at == t + timedelta(minutes=22)


@pytest.mark.parametrize("error", [battle_client.BattleServiceError("down"), RuntimeError("crash")])
def test_transport_failure_or_crash_aborts(storm, error):
    storm.bs.error = error
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    assert r.status == "aborted" and r.mobs_despawned and active_mob_ids(storm) == []


def test_spawn_failure_aborts_without_a_battle(storm, monkeypatch):
    import crud

    def boom(*a, **kw):
        raise RuntimeError("no template")

    monkeypatch.setattr(crud, "spawn_mob_from_template", boom)
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    assert r.status == "aborted" and storm.bs.calls == []


def test_battle_service_places_only_free_players(storm, stub_law_notify_send):
    storm.bs.skip = {BETA}
    _t, (r,) = _raid_at_sea(storm, ALPHA, BETA)
    assert r.player_ids == [ALPHA, BETA] and r.placed_ids == [ALPHA] and r.status == "fighting"
    battle_notices = [n for n in ws_events(stub_law_notify_send, "raid") if "battle_id" in n["ws_data"]]
    assert [n["target_value"] for n in battle_notices] == [USER_ALPHA]
    assert battle_notices[0]["ws_data"]["sea_raid_id"] == int(r.id)


def test_pack_size_is_capped_by_the_group(storm):
    _t, (r,) = _raid_at_sea(storm, ALPHA, BETA, max_active=5)
    assert len(r.mob_ids) == 2 and active_mob_ids(storm) == sorted(r.mob_ids)
    hidden = rows(storm, "SELECT is_npc, npc_role, current_location_id FROM characters WHERE id = :c",
                  c=r.mob_ids[0])
    assert tuple(hidden[0]) == (1, "mob", DECK)


def test_a_row_starts_only_once(storm):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    db = storm()
    try:
        assert sea_raid_crud.start_raid(db, int(r.id)).status == sea_raid_crud.START_SKIPPED
        assert sea_raid_crud.start_pending(db, storm.ship_id) == []
    finally:
        db.close()
    assert len(storm.bs.calls) == 1


def test_followups_start_a_row_left_unstarted(storm):
    rid = _row(storm)
    stats = _followups(storm)
    assert stats["raid_started"] == 1 and raid(storm, rid).status == "fighting"
    assert storm.bs.calls[0]["players"] == [ALPHA]


def test_mark_fighting_after_a_fast_settle_keeps_the_final_status(storm):
    rid = _row(storm, status="won", mob_ids=[])
    db = storm()
    try:
        assert sea_raid_crud.mark_fighting(db, rid, 950, [ALPHA]) is False
    finally:
        db.close()
    r = raid(storm, rid)
    assert (r.status, r.battle_id, r.placed_ids) == ("won", 950, [ALPHA])


# =============================================================================================== callback endpoint

@pytest.mark.parametrize("body, status, event", [
    ({"winner_team": 0}, "won", "raid_won"),
    ({"winner_team": 1}, "lost", "raid_lost"),
    ({"winner_team": None}, "lost", "raid_lost"),
    ({"winner_team": 0, "aborted": True}, "aborted", None),
])
def test_callback_settles_notifies_and_despawns(client, storm, stub_law_notify_send, body, status, event):
    _t, (r,) = _raid_at_sea(storm, ALPHA, BETA)
    resp = _post(client, {"battle_id": r.battle_id, "sea_raid_id": int(r.id), **body})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": status}
    r2 = raid(storm, r.id)
    assert (r2.status, r2.mobs_despawned) == (status, True) and r2.ended_at is not None
    assert active_mob_ids(storm) == []
    for ev in ("raid_won", "raid_lost"):
        notices = ws_events(stub_law_notify_send, ev)
        if ev == event:
            assert {n["target_value"] for n in notices} == {USER_ALPHA, USER_BETA}
            assert all("Кракен" in n["message"] for n in notices)
        else:
            assert notices == []


def test_callback_replay_is_already_and_changes_nothing(client, storm, stub_law_notify_send):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    body = {"battle_id": r.battle_id, "sea_raid_id": int(r.id), "winner_team": 0}
    assert _post(client, body).json() == {"status": "won"}
    resp = _post(client, {**body, "winner_team": 1})
    assert resp.json() == {"status": "already"}
    assert raid(storm, r.id).status == "won"
    assert len(ws_events(stub_law_notify_send, "raid_won")) == 1 and ws_events(stub_law_notify_send, "raid_lost") == []


def test_callback_unknown_raid(client, storm):
    assert _post(client, {"battle_id": 5, "sea_raid_id": 999999}).json() == {"status": "unknown"}


def test_callback_with_a_foreign_battle_is_unknown(client, storm):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    resp = _post(client, {"battle_id": int(r.battle_id) + 50, "sea_raid_id": int(r.id), "winner_team": 0})
    assert resp.json() == {"status": "unknown"} and raid(storm, r.id).status == "fighting"
    assert active_mob_ids(storm) == r.mob_ids


def test_callback_settles_a_row_still_starting(client, storm):
    rid = _row(storm, mob_ids=[])
    assert _post(client, {"battle_id": 3, "sea_raid_id": rid, "winner_team": 0}).json() == {"status": "won"}
    r = raid(storm, rid)
    assert (r.status, r.battle_id, r.placed_ids) == ("won", 3, None)


def test_callback_releases_the_hold_on_the_next_pass(client, storm):
    t, (r,) = _raid_at_sea(storm, ALPHA)
    _post(client, {"battle_id": r.battle_id, "sea_raid_id": int(r.id), "winner_team": 0})
    assert ship(storm).hold_until is not None                       # the callback never touches the ship
    out = run_ship(storm, t + timedelta(minutes=14))
    assert sea_pass.EV_HOLD_RELEASED in out.events and ship(storm).next_zone_at == t + timedelta(minutes=24)


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Token": "wrong"}, {"X-Internal-Token": ""}])
def test_callback_needs_the_internal_token(client, storm, headers):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    resp = _post(client, {"battle_id": r.battle_id, "sea_raid_id": int(r.id), "winner_team": 0}, headers=headers)
    assert resp.status_code == 401
    assert raid(storm, r.id).status == "fighting"


@pytest.mark.parametrize("body", [
    {}, {"battle_id": 1}, {"sea_raid_id": 1}, {"battle_id": 0, "sea_raid_id": 1}, {"battle_id": 1, "sea_raid_id": -1},
    {"battle_id": "1; DROP TABLE sea_raids", "sea_raid_id": 1}, {"battle_id": 1, "sea_raid_id": "' OR 1=1 --"},
    {"battle_id": 1, "sea_raid_id": 1, "aborted": "maybe"},
])
def test_callback_validation(client, storm, body):
    assert _post(client, body).status_code == 422
    assert q(storm, "SELECT COUNT(*) FROM sea_raids") == 0


def test_callback_db_error_is_a_generic_500(client, storm, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def boom(*a, **kw):
        raise OperationalError("SELECT secret", {}, Exception("password=hunter2"))

    monkeypatch.setattr(sea_raid_crud, "settle", boom)
    resp = _post(client, {"battle_id": 1, "sea_raid_id": 1, "winner_team": 0})
    assert resp.status_code == 500 and resp.json()["detail"] == "Не удалось завершить бой с морскими монстрами"
    assert "hunter2" not in resp.text


# =============================================================================================== poll / stale / despawn

def test_poll_settles_a_finished_battle_after_two_minutes(storm, stub_law_notify_send):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    started = raid(storm, r.id).started_at
    storm.poll.answer = {"status": "finished", "winner_team": 0, "aborted": False}
    assert _followups(storm, started + timedelta(minutes=1))["raid_polled"] == 0 and storm.poll.calls == []
    stats = _followups(storm, started + timedelta(minutes=3))
    assert stats["raid_polled"] == 1 and storm.poll.calls == [r.battle_id]
    r2 = raid(storm, r.id)
    assert (r2.status, r2.mobs_despawned) == ("won", True) and active_mob_ids(storm) == []
    assert len(ws_events(stub_law_notify_send, "raid_won")) == 1


@pytest.mark.parametrize("answer, status", [
    (battle_client.BATTLE_NOT_FOUND, "aborted"),
    ({"status": "forfeit", "winner_team": 1}, "lost"),
    ({"status": "finished", "winner_team": 0, "aborted": True}, "aborted"),
    ({"status": "in_progress"}, "fighting"),
    (battle_client.BattleServiceError("down"), "fighting"),
])
def test_poll_outcomes(storm, answer, status):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    storm.poll.answer = answer
    _followups(storm, raid(storm, r.id).started_at + timedelta(minutes=5))
    assert raid(storm, r.id).status == status
    assert (active_mob_ids(storm) == []) == (status != "fighting")


def test_poll_then_callback_is_already(client, storm):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    storm.poll.answer = {"status": "finished", "winner_team": 1}
    _followups(storm, raid(storm, r.id).started_at + timedelta(minutes=5))
    resp = _post(client, {"battle_id": r.battle_id, "sea_raid_id": int(r.id), "winner_team": 0})
    assert resp.json() == {"status": "already"} and raid(storm, r.id).status == "lost"


def test_fighting_row_without_a_battle_is_aborted_by_the_poll(storm):
    rid = _row(storm, status="fighting", mob_ids=[], started=now() - timedelta(minutes=10))
    _followups(storm)
    assert raid(storm, rid).status == "aborted" and storm.poll.calls == []


def test_stale_starting_row_expires_and_despawns(storm):
    rid = _row(storm, mob_ids=[], created=now() - timedelta(minutes=11))
    stats = _followups(storm)
    r = raid(storm, rid)
    assert stats["raid_expired"] == 1 and (r.status, r.mobs_despawned) == ("expired", True)


def test_fresh_starting_row_is_left_alone(storm):
    rid = _row(storm, mob_ids=[], created=now() - timedelta(minutes=9))
    assert _followups(storm)["raid_expired"] == 0 and raid(storm, rid).status == "starting"


def test_stale_row_with_a_tagged_battle_is_attached(storm):
    exec_(storm, "ALTER TABLE battles ADD COLUMN sea_raid_id INTEGER NULL")
    rid = _row(storm, mob_ids=[], created=now() - timedelta(minutes=11))
    exec_(storm, "INSERT INTO battles (id, status, sea_raid_id) VALUES (444, 'in_progress', :r)", r=rid)
    _followups(storm)
    r = raid(storm, rid)
    assert (r.status, r.battle_id, r.placed_ids) == ("fighting", 444, [ALPHA]) and r.started_at is not None


def test_final_rows_with_monsters_left_are_despawned(storm):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    exec_(storm, "UPDATE sea_raids SET status = 'won', mobs_despawned = 0")
    assert active_mob_ids(storm) == r.mob_ids
    assert _followups(storm)["raid_despawned"] == 1
    assert active_mob_ids(storm) == [] and raid(storm, r.id).mobs_despawned
    assert _followups(storm)["raid_despawned"] == 0


def test_despawn_is_guarded(storm):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    db = storm()
    try:
        assert sea_raid_crud.despawn_mobs(db, int(r.id)) is False             # still fighting
        assert sea_raid_crud.despawn_mobs(db, 999999) is False
    finally:
        db.close()
    assert active_mob_ids(storm) == r.mob_ids


def test_monsters_are_despawned_even_when_the_ship_is_gone(client, storm):
    _t, (r,) = _raid_at_sea(storm, ALPHA)
    exec_(storm, "DELETE FROM sea_ships")
    assert _post(client, {"battle_id": r.battle_id, "sea_raid_id": int(r.id), "winner_team": 1}).json() == \
        {"status": "lost"}
    assert active_mob_ids(storm) == []


def test_run_pass_reports_the_raid_followups(storm):
    stats = sea_pass.run_pass(storm, now=storm.t0 + timedelta(minutes=31), force=True)
    assert {"raid_started", "raid_expired", "raid_polled", "raid_despawned"} <= set(stats)


# =============================================================================================== safe landing / delete

def test_safe_landing_keeps_a_fighter_aboard_then_lands_him(storm):
    buy(storm, ALPHA)
    buy(storm, BETA)
    place(storm, ALPHA, DECK)
    place(storm, BETA, DECK)
    _out, t = depart(storm)
    in_battle(storm, ALPHA, 66)
    exec_(storm, "DELETE FROM Locations WHERE id IN (103, 200, 110)")
    out = run_ship(storm, t + timedelta(minutes=30))
    s = ship(storm)
    assert sea_pass.EV_SAFE_LANDING in out.events and (s.is_active, s.docked_port_id) == (False, None)
    assert loc(storm, BETA) == START and loc(storm, ALPHA) == DECK
    assert [a.character_id for a in out.ashore] == [BETA]
    again = run_ship(storm, t + timedelta(minutes=31))                    # still fighting → stays
    assert loc(storm, ALPHA) == DECK and sea_pass.EV_SAFE_LANDING not in again.events
    exec_(storm, "UPDATE battles SET status = 'finished' WHERE id = 66")
    out = run_ship(storm, t + timedelta(minutes=32))
    assert sea_pass.EV_SAFE_LANDING in out.events and loc(storm, ALPHA) == START


def test_safe_land_result_lists_the_kept_fighters(storm):
    place(storm, ALPHA, DECK)
    place(storm, BETA, DECK)
    in_battle(storm, ALPHA, 66)
    import sea_crud
    db = storm()
    try:
        s = sea_crud.get_ship(db, storm.ship_id, lock=True)
        result = sea_crud.safe_land(db, s, sea_core.BLOCKED_NO_VALID_STOP, now())
        db.commit()
    finally:
        db.close()
    assert result.kept_in_battle == [ALPHA] and [a.character_id for a in result.ashore] == [BETA]
    assert loc(storm, ALPHA) == DECK


def test_vanished_deck_keeps_the_fighter_until_his_battle_ends(storm):
    place(storm, ALPHA, DECK)
    place(storm, BETA, DECK)
    in_battle(storm, ALPHA, 66)
    exec_(storm, "DELETE FROM Locations WHERE id = :d", d=DECK)
    out = run_ship(storm, storm.t0 + timedelta(minutes=1))
    assert sea_pass.EV_SAFE_LANDING in out.events and loc(storm, BETA) == P_A and loc(storm, ALPHA) == DECK
    again = run_ship(storm, storm.t0 + timedelta(minutes=2))
    assert sea_pass.EV_SAFE_LANDING not in again.events and loc(storm, ALPHA) == DECK
    exec_(storm, "UPDATE battles SET status = 'finished' WHERE id = 66")
    run_ship(storm, storm.t0 + timedelta(minutes=3))
    assert loc(storm, ALPHA) == P_A


@pytest.fixture
def deleter(client):
    as_user(1, "admin", ["locations:delete"])
    return client


def test_delete_is_refused_during_a_deck_battle(deleter, storm):
    place(storm, ALPHA, DECK)
    in_battle(storm, ALPHA, 66)
    resp = deleter.delete(DELETE.format(storm.ship_id))
    assert (resp.status_code, resp.json()["detail"]) == (409, sea_admin.MSG_DELETE_BATTLE)
    assert ship(storm) is not None and loc(storm, ALPHA) == DECK


@pytest.mark.parametrize("status", ["starting", "fighting"])
def test_delete_is_refused_while_a_raid_is_active(deleter, storm, status):
    _row(storm, status=status, mob_ids=[])
    resp = deleter.delete(DELETE.format(storm.ship_id))
    assert (resp.status_code, resp.json()["detail"]) == (409, sea_admin.MSG_DELETE_BATTLE)


def test_delete_after_the_raid_is_fine(deleter, storm):
    _row(storm, status="won", mob_ids=[], despawned=True)
    place(storm, ALPHA, DECK)
    resp = deleter.delete(DELETE.format(storm.ship_id))
    assert resp.status_code in (200, 204), resp.text
    assert ship(storm) is None and loc(storm, ALPHA) == P_A


# =============================================================================================== public views

def _deck(c, character=ALPHA):
    return c.get(f"/characters/sea/decks/{DECK}", params={"character_id": character})


def _captain(c, character=ALPHA):
    return c.get(f"/characters/sea/captain/{CAPTAIN}", params={"character_id": character})


@pytest.fixture
def alpha(client):
    as_user(USER_ALPHA)
    return client


def test_calm_ship_has_empty_storm_fields(alpha, storm):
    body = _deck(alpha).json()["ship"]
    assert (body["storm"], body["departure_postponed"], body["raid"]) == (None, False, None)


def test_storm_over_the_current_zone_is_shown(alpha, storm):
    t = now()
    add_storm(storm, [Z1], start=t, minutes=60)
    for body in (_deck(alpha).json()["ship"], _captain(alpha).json()["ship"]):
        assert body["storm"]["zone_id"] == Z1 and body["storm"]["zone_name"] == "Пролив Ветров"
        assert body["storm"]["ends_at"].startswith((t + timedelta(minutes=60)).isoformat()[:16])


def test_storm_elsewhere_or_expired_is_not_shown(alpha, storm):
    add_storm(storm, [Z2], minutes=60)
    add_storm(storm, [Z1], start=now() - timedelta(hours=3), minutes=60)
    assert _deck(alpha).json()["ship"]["storm"] is None


def test_departure_postponed_only_while_docked(alpha, storm):
    set_ship(storm, storm_hold_since=now())
    assert _deck(alpha).json()["ship"]["departure_postponed"] is True
    assert _captain(alpha).json()["ship"]["departure_postponed"] is True
    set_ship(storm, status="sailing", docked_port_id=None, leg_path=[Z1, Z2, Z3], leg_pos=0, next_port_id=200,
             next_stop_index=1, next_zone_at=now() + timedelta(minutes=5))
    assert _deck(alpha).json()["ship"]["departure_postponed"] is False


def test_raid_state_lists_the_fighting_battles(alpha, storm):
    hold = now() + timedelta(minutes=90)
    set_ship(storm, hold_until=hold)
    _row(storm, status="fighting", battle_id=901, mob_ids=[], key="a")
    _row(storm, status="starting", mob_ids=None, key="b")
    _row(storm, status="won", battle_id=777, mob_ids=[], key="c")
    raid_out = _deck(alpha).json()["ship"]["raid"]
    assert raid_out["monster_name"] == "Кракен" and raid_out["battles"] == [{"battle_id": 901}]
    assert raid_out["hold_until"].startswith(hold.isoformat()[:16])


def test_raid_just_rolled_has_no_battle_yet(alpha, storm):
    _row(storm, status="starting", mob_ids=None)
    assert _deck(alpha).json()["ship"]["raid"] == {"monster_name": "Кракен", "hold_until": None, "battles": []}


def test_finished_raids_are_not_shown(alpha, storm):
    _row(storm, status="lost", battle_id=5, mob_ids=[])
    assert _deck(alpha).json()["ship"]["raid"] is None


def test_views_survive_missing_storm_tables(alpha, storm):
    exec_(storm, "DROP TABLE sea_raids")
    exec_(storm, "DROP TABLE sea_storm_zones")
    resp = _deck(alpha)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ship"]["storm"] is None and resp.json()["ship"]["raid"] is None


def test_raid_ids_are_stored_as_json_lists(storm):
    _t, (r,) = _raid_at_sea(storm, ALPHA, BETA)
    raw = q(storm, "SELECT player_ids FROM sea_raids WHERE id = :r", r=r.id)
    assert json.loads(raw) == [ALPHA, BETA]
