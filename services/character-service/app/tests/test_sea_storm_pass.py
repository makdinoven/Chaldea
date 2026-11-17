"""FEAT-214 QA (T10): the storm / raid hooks of the sea pass (features/FEAT-214 §3.6, §3.8 roll).

Ship 1 sails trip 1 = zones [501, 502, 503], 10 min per zone; ``depart`` leaves it at 501 (leg_pos 0) with the next
step due 10 min later (502 is the first real zone entry).

* departure postpone: a storm over the port's zone, tickets kept, one deck notice, the total cap, the storm ending;
* stormy zone: slowdown (``storm_extra``), the storm damage targets (no one in a battle, never the Captain), notices,
  drift (re-laid course, the timer unchanged, the raid roll in the post-drift zone);
* the quiet offline catch-up (timing only, no damage / drift / raids);
* sailor relief once per zone; the raid hold (release gives the unused time back, expiry sails on);
* raid roll: never at the pier, groups ≤ 5 evened, pack size, no second roll while a raid is active, «repelled» delay
  when nobody can fight, ``raid_chance_mult`` / disabled rules.
"""

from datetime import datetime, timedelta

import pytest

import models
import sea_core
import sea_pass
import sea_weather
from tests.sea_storm_world import (  # noqa: F401  (fixtures)
    MONSTER_TPL, MONSTER_TPL2, active_mob_ids, add_monster, add_player, add_storm, in_battle, raids, set_params,
    storm, ws_events,
)
from tests.sea_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, CAPTAIN, DECK, GAMMA, P_A, USER_ALPHA, USER_BETA, Z1, Z2, Z3, Z5, add_pass, api, buy, depart,
    exec_, law_world, loc, now, passes, place, post, q, rep_world, rows, run_ship, sea, set_ship, ship,
)


def _sail(f, *players):
    """Depart (empty deck), then put ``players`` aboard; returns the departure time t (next step due t+10)."""
    _out, t = depart(f)
    for cid in players:
        place(f, cid, DECK)
    return t


def _unconscious(f, cid):
    exec_(f, "UPDATE characters SET unconscious_until = :u WHERE id = :c", u=datetime.utcnow() + timedelta(hours=1),
          c=cid)


# =============================================================================================== departure postpone

def test_storm_over_the_port_zone_postpones_the_departure(storm, stub_law_notify_send):
    pid = buy(storm, ALPHA)
    place(storm, ALPHA, DECK)
    add_storm(storm, [Z1], minutes=600)
    out, when = depart(storm)
    s = ship(storm)
    assert (s.status, s.trip_no, s.storm_hold_since) == ("docked", 0, when)
    assert s.departs_at == when + timedelta(minutes=15)
    assert sea_pass.EV_STORM_DELAY in out.events and sea_pass.EV_DEPARTED not in out.events
    assert loc(storm, ALPHA) == DECK and passes(storm)[0].status == "active"
    (n,) = ws_events(stub_law_notify_send, sea_pass.EV_STORM_DELAY)
    assert n["target_value"] == USER_ALPHA and "откладывает отплытие" in n["message"]
    assert passes(storm)[0].id == pid and passes(storm)[0].first_trip == 1


def test_postpone_repeats_quietly_then_the_cap_sails_anyway(storm, stub_law_notify_send):
    buy(storm, ALPHA)
    place(storm, ALPHA, DECK)
    set_params(storm, storm_postpone_minutes=10, storm_postpone_max_minutes=25)
    add_storm(storm, [Z1], minutes=600)
    _out, first = depart(storm)
    run_ship(storm, first + timedelta(minutes=10))
    s = ship(storm)
    assert s.status == "docked" and s.departs_at == first + timedelta(minutes=20) and s.storm_hold_since == first
    run_ship(storm, first + timedelta(minutes=20))
    assert ship(storm).status == "docked"
    out = run_ship(storm, first + timedelta(minutes=30))                    # 30 ≥ 25: the cap
    s = ship(storm)
    assert sea_pass.EV_DEPARTED in out.events
    assert (s.status, s.trip_no, s.storm_hold_since) == ("sailing", 1, None)
    assert loc(storm, ALPHA) == DECK and passes(storm)[0].status == "active"     # the ticket of trip 1 still valid
    assert len(ws_events(stub_law_notify_send, sea_pass.EV_STORM_DELAY)) == 1


def test_postpone_stops_when_the_storm_ends(storm):
    add_storm(storm, [Z1], minutes=40, start=storm.t0)        # active at the departure (t0+31), over by t0+61
    _out, first = depart(storm)
    assert ship(storm).status == "docked"
    out = run_ship(storm, first + timedelta(minutes=30))
    assert sea_pass.EV_DEPARTED in out.events and ship(storm).storm_hold_since is None


def test_postpone_cap_zero_never_postpones(storm):
    set_params(storm, storm_postpone_max_minutes=0)
    add_storm(storm, [Z1], minutes=600)
    out, _ = depart(storm)
    assert sea_pass.EV_DEPARTED in out.events


def test_storm_elsewhere_does_not_postpone(storm):
    add_storm(storm, [Z2, Z3], minutes=600)
    out, _ = depart(storm)
    assert sea_pass.EV_DEPARTED in out.events and ship(storm).storm_hold_since is None


def test_expired_storm_does_not_postpone(storm):
    add_storm(storm, [Z1], start=now() - timedelta(hours=5), minutes=10)
    out, _ = depart(storm)
    assert sea_pass.EV_DEPARTED in out.events


# =============================================================================================== slowdown / damage

def test_stormy_zone_slows_the_ship(storm):
    t = _sail(storm)
    add_storm(storm, [Z2], start=t, minutes=600)
    post(storm, BETA, 100, "раньше")
    out = run_ship(storm, t + timedelta(minutes=10))
    s = ship(storm)
    assert (s.leg_pos, s.current_zone_id, s.storm_extra_minutes) == (1, Z2, 10)
    assert s.next_zone_at == t + timedelta(minutes=30)
    assert s.storm_post_floor_id == q(storm, "SELECT MAX(id) FROM posts")
    assert sea_pass.EV_STORM in out.events


@pytest.mark.parametrize("mult, extra", [(3.0, 20), (1.5, 5), (1.0, 0)])
def test_slowdown_follows_the_settings(storm, mult, extra):
    set_params(storm, storm_slow_mult=mult)
    t = _sail(storm)
    add_storm(storm, [Z2], start=t, minutes=600)
    run_ship(storm, t + timedelta(minutes=10))
    s = ship(storm)
    assert s.storm_extra_minutes == extra and s.next_zone_at == t + timedelta(minutes=20 + extra)
    assert (s.storm_post_floor_id is None) == (extra == 0)


def test_calm_zone_clears_the_storm_delay(storm):
    t = _sail(storm)
    add_storm(storm, [Z2], start=t, minutes=600)
    run_ship(storm, t + timedelta(minutes=10))
    run_ship(storm, t + timedelta(minutes=30))
    s = ship(storm)
    assert (s.current_zone_id, s.storm_extra_minutes, s.storm_post_floor_id) == (Z3, 0, None)
    assert s.next_zone_at == t + timedelta(minutes=40)


def test_storm_damage_targets_skip_players_in_battle_and_the_captain(storm, stub_law_notify_send):
    t = _sail(storm, ALPHA, BETA, GAMMA)
    in_battle(storm, BETA, 77)
    add_storm(storm, [Z2], start=t, minutes=600)
    out = run_ship(storm, t + timedelta(minutes=10))
    assert out.storm_damage_ids == [ALPHA, GAMMA] and loc(storm, CAPTAIN) == DECK
    ((url, payload),) = storm.cas.calls
    assert [i["character_id"] for i in payload["items"]] == [ALPHA, GAMMA]
    assert payload["items"][0]["health_pct"] == 10.0 and payload["items"][0]["stamina_pct"] == 20.0
    assert payload["min_health"] == 1
    notices = ws_events(stub_law_notify_send, sea_pass.EV_STORM)
    assert {n["ws_data"]["character_id"] for n in notices} == {ALPHA, BETA, GAMMA}
    assert all("шторм" in n["message"] and "Северный залив" in n["message"] for n in notices)
    assert notices[0]["ws_data"]["zone_id"] == Z2 and notices[0]["ws_data"]["storm_ends_at"]


def test_storm_damage_percentages_follow_the_settings(storm):
    set_params(storm, storm_hp_pct=25.0, storm_stamina_pct=0.0)
    t = _sail(storm, ALPHA)
    add_storm(storm, [Z2], start=t, minutes=600)
    run_ship(storm, t + timedelta(minutes=10))
    item = storm.cas.calls[0][1]["items"][0]
    assert (item["health_pct"], item["stamina_pct"]) == (25.0, 0.0)


def test_storm_damage_failure_never_breaks_the_pass(storm):
    storm.cas.status = 503
    t = _sail(storm, ALPHA)
    add_storm(storm, [Z2], start=t, minutes=600)
    out = run_ship(storm, t + timedelta(minutes=10))
    assert sea_pass.EV_STORM in out.events and ship(storm).current_zone_id == Z2


def test_empty_deck_in_a_storm_sends_no_damage(storm):
    t = _sail(storm)
    add_storm(storm, [Z2], start=t, minutes=600)
    run_ship(storm, t + timedelta(minutes=10))
    assert storm.cas.calls == []


# =============================================================================================== quiet catch-up

def test_offline_catch_up_is_quiet_but_keeps_the_storm_timing(storm, stub_law_notify_send):
    t = _sail(storm, ALPHA)
    add_storm(storm, [Z2], start=t, minutes=600)
    add_monster(storm, Z2)
    set_params(storm, storm_drift_pct=100.0)
    out = run_ship(storm, t + timedelta(minutes=35))      # Z2 skipped through (due t+30), Z3 is the real entry
    s = ship(storm)
    assert (s.leg_pos, s.current_zone_id) == (2, Z3)
    assert s.next_zone_at == t + timedelta(minutes=40)    # 10 + 10 (storm) + 10
    assert out.storm_damage_ids == [] and storm.cas.calls == []
    assert raids(storm) == [] and sea_pass.EV_STORM not in out.events and sea_pass.EV_DRIFT not in out.events
    assert ws_events(stub_law_notify_send, sea_pass.EV_STORM) == []


def test_catch_up_to_arrival_rolls_nothing(storm):
    t = _sail(storm, ALPHA)
    for z in (Z2, Z3):
        add_monster(storm, z, tpl=MONSTER_TPL if z == Z2 else MONSTER_TPL2, name=f"Змей {z}")
    out = run_ship(storm, t + timedelta(hours=3))
    assert sea_pass.EV_ARRIVED in out.events and raids(storm) == []


# =============================================================================================== drift

def test_drift_re_lays_the_course_from_a_neighbour(storm, stub_law_notify_send):
    set_params(storm, storm_drift_pct=100.0)
    t = _sail(storm, ALPHA)
    add_storm(storm, [Z2], start=t, minutes=600)
    out = run_ship(storm, t + timedelta(minutes=10))
    s = ship(storm)
    assert sea_pass.EV_DRIFT in out.events
    assert (s.current_zone_id, s.leg_pos, s.leg_path) == (Z1, 0, [Z1, Z2, Z3])   # 502's other neighbour = 501
    assert s.next_zone_at == t + timedelta(minutes=30)                           # the zone timer is unchanged
    (n,) = ws_events(stub_law_notify_send, sea_pass.EV_DRIFT)
    assert "снёс" in n["message"] and "Пролив Ветров" in n["message"] and n["ws_data"]["zone_id"] == Z1


def test_drift_roll_can_fail(storm):
    set_params(storm, storm_drift_pct=50.0)
    storm.rng.values = [0.6]
    t = _sail(storm)
    add_storm(storm, [Z2], start=t, minutes=600)
    out = run_ship(storm, t + timedelta(minutes=10))
    assert sea_pass.EV_DRIFT not in out.events and ship(storm).current_zone_id == Z2


def test_no_drift_without_a_storm(storm):
    set_params(storm, storm_drift_pct=100.0)
    t = _sail(storm)
    out = run_ship(storm, t + timedelta(minutes=10))
    assert sea_pass.EV_DRIFT not in out.events and ship(storm).current_zone_id == Z2


def test_raid_roll_after_a_drift_uses_the_post_drift_zone(storm):
    set_params(storm, storm_drift_pct=100.0)
    t = _sail(storm, ALPHA)
    add_storm(storm, [Z2], start=t, minutes=600)
    add_monster(storm, Z2, tpl=MONSTER_TPL2, name="Змей залива")
    add_monster(storm, Z1, name="Кракен пролива")
    run_ship(storm, t + timedelta(minutes=10))
    (r,) = raids(storm)
    assert (r.zone_id, r.monster_name, r.mob_template_id) == (Z1, "Кракен пролива", MONSTER_TPL)
    assert r.attack_key.startswith(f"{storm.ship_id}:1:0:{Z1}:")


# =============================================================================================== sailor relief

def _relief_setup(f, kind="sailor", aboard=True):
    t = _sail(f, *( [ALPHA] if aboard else [] ))
    add_pass(f, ALPHA, kind=kind, first=1, last=1)
    add_storm(f, [Z2], start=t, minutes=600)
    run_ship(f, t + timedelta(minutes=10))
    assert ship(f).next_zone_at == t + timedelta(minutes=30)
    return t


def test_sailor_post_after_the_stormy_entry_wins_back_time_once(storm, stub_law_notify_send):
    t = _relief_setup(storm)
    post(storm, ALPHA, DECK, "м" * 800)
    out = run_ship(storm, t + timedelta(minutes=11))
    s = ship(storm)
    assert sea_pass.EV_STORM_RELIEF in out.events
    assert s.next_zone_at == t + timedelta(minutes=25) and s.storm_post_floor_id is None
    (n,) = ws_events(stub_law_notify_send, sea_pass.EV_STORM_RELIEF)
    assert "Матросы удержали паруса" in n["message"]
    post(storm, ALPHA, DECK, "м" * 800)
    again = run_ship(storm, t + timedelta(minutes=12))
    assert sea_pass.EV_STORM_RELIEF not in again.events and ship(storm).next_zone_at == t + timedelta(minutes=25)


def test_relief_percentage_follows_the_settings(storm):
    set_params(storm, storm_sailor_relief_pct=100.0)
    t = _relief_setup(storm)
    post(storm, ALPHA, DECK, "м" * 800)
    run_ship(storm, t + timedelta(minutes=11))
    assert ship(storm).next_zone_at == t + timedelta(minutes=20)


def test_relief_never_moves_the_timer_before_now(storm):
    set_params(storm, storm_sailor_relief_pct=100.0)
    t = _relief_setup(storm)
    post(storm, ALPHA, DECK, "м" * 800)
    run_ship(storm, t + timedelta(minutes=25))
    assert ship(storm).next_zone_at == t + timedelta(minutes=25)


@pytest.mark.parametrize("case", ["post_before", "short_post", "ticket", "not_aboard", "elsewhere"])
def test_no_relief(storm, case):
    if case == "post_before":
        t = _sail(storm, ALPHA)
        add_pass(storm, ALPHA, kind="sailor")
        add_storm(storm, [Z2], start=t, minutes=600)
        post(storm, ALPHA, DECK, "м" * 800)                    # written before the stormy entry
        run_ship(storm, t + timedelta(minutes=10))
    else:
        t = _relief_setup(storm, kind="ticket" if case == "ticket" else "sailor", aboard=case != "not_aboard")
        content = "м" * 10 if case == "short_post" else "м" * 800
        post(storm, ALPHA, 100 if case == "elsewhere" else DECK, content)
    out = run_ship(storm, t + timedelta(minutes=11))
    assert sea_pass.EV_STORM_RELIEF not in out.events and ship(storm).next_zone_at == t + timedelta(minutes=30)


# =============================================================================================== raid roll + hold

def test_raid_holds_the_ship_and_starts_a_battle(storm, stub_law_notify_send):
    add_monster(storm, Z2, max_active=1)
    t = _sail(storm, ALPHA, BETA)
    out = run_ship(storm, t + timedelta(minutes=10))
    s = ship(storm)
    assert sea_pass.EV_RAID in out.events and out.raids_planned
    assert s.hold_until == t + timedelta(minutes=130) and s.next_zone_at == t + timedelta(minutes=140)
    (r,) = raids(storm)
    assert (r.status, r.player_ids, r.group_no, r.zone_id, r.deck_location_id) == \
        ("fighting", [ALPHA, BETA], 0, Z2, DECK)
    assert r.battle_id == 901 and r.placed_ids == [ALPHA, BETA] and len(r.mob_ids) == 1
    (call,) = storm.bs.calls
    assert call == {"raid_id": int(r.id), "location_id": DECK, "players": [ALPHA, BETA], "mobs": r.mob_ids}
    assert loc(storm, r.mob_ids[0]) == DECK and active_mob_ids(storm) == r.mob_ids
    pass_notices = [n for n in ws_events(stub_law_notify_send, sea_pass.EV_RAID) if "battle_id" not in n["ws_data"]]
    battle_notices = [n for n in ws_events(stub_law_notify_send, sea_pass.EV_RAID) if "battle_id" in n["ws_data"]]
    assert {n["target_value"] for n in pass_notices} == {USER_ALPHA, USER_BETA}
    assert all("Кракен" in n["message"] for n in pass_notices)
    assert {(n["target_value"], n["ws_data"]["battle_id"], n["ws_data"]["location_id"]) for n in battle_notices} == \
        {(USER_ALPHA, 901, DECK), (USER_BETA, 901, DECK)}


def test_ship_does_not_step_while_holding(storm):
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=10))
    run_ship(storm, t + timedelta(minutes=60))
    s = ship(storm)
    assert (s.leg_pos, s.current_zone_id, s.hold_until) == (1, Z2, t + timedelta(minutes=130))


def test_hold_release_gives_the_unused_hold_back(storm):
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=10))
    exec_(storm, "UPDATE sea_raids SET status = 'won'")
    out = run_ship(storm, t + timedelta(minutes=15))
    s = ship(storm)
    assert sea_pass.EV_HOLD_RELEASED in out.events
    assert s.hold_until is None and s.next_zone_at == t + timedelta(minutes=25)   # 5 min of the fight lost


def test_hold_release_steps_in_the_same_pass_when_due(storm):
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=10))
    exec_(storm, "UPDATE sea_raids SET status = 'lost'")
    out = run_ship(storm, t + timedelta(minutes=125))          # next = t+140 − 5 = t+135 > now: no step yet
    assert sea_pass.EV_HOLD_RELEASED in out.events and ship(storm).current_zone_id == Z2
    assert ship(storm).next_zone_at == t + timedelta(minutes=135)


def test_hold_expires_and_the_ship_sails_on_with_the_battle(storm, stub_law_notify_send):
    add_monster(storm, Z2)
    add_monster(storm, Z3, tpl=MONSTER_TPL2, name="Змей бухты")
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=10))
    out = run_ship(storm, t + timedelta(minutes=130))
    assert sea_pass.EV_HOLD_EXPIRED in out.events and ship(storm).hold_until is None
    (n,) = ws_events(stub_law_notify_send, sea_pass.EV_HOLD_EXPIRED)
    assert "бой на палубе продолжается" in n["message"]
    out = run_ship(storm, t + timedelta(minutes=140))
    s = ship(storm)
    assert (s.current_zone_id, s.leg_pos) == (Z3, 2)
    assert len(raids(storm)) == 1                              # no second roll while the first raid fights
    assert raids(storm)[0].status == "fighting"


def test_hold_max_zero_means_no_hold(storm):
    set_params(storm, raid_hold_max_minutes=0)
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=10))
    s = ship(storm)
    assert s.hold_until is None and s.next_zone_at == t + timedelta(minutes=20) and len(raids(storm)) == 1


def test_no_attack_at_the_pier(storm):
    add_monster(storm, Z1)
    buy(storm, ALPHA)
    place(storm, ALPHA, DECK)
    out, t = depart(storm)
    assert sea_pass.EV_DEPARTED in out.events and raids(storm) == []
    assert ship(storm).hold_until is None and ship(storm).next_zone_at == t + timedelta(minutes=10)


def test_last_zone_rolls_but_arrival_and_the_dock_do_not(storm):
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=20))                 # Z3 entered (pos 2), no monster yet
    assert ship(storm).current_zone_id == Z3 and raids(storm) == []
    add_monster(storm, Z3)                                     # appears after the Z3 entry
    out = run_ship(storm, t + timedelta(minutes=30))           # arrival in the port of zone 503
    assert sea_pass.EV_ARRIVED in out.events and raids(storm) == []
    run_ship(storm, t + timedelta(minutes=31))                 # docked
    assert raids(storm) == []


def test_last_zone_entry_can_be_attacked(storm):
    add_monster(storm, Z3)
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=20))
    (r,) = raids(storm)
    assert r.zone_id == Z3 and r.attack_key.startswith(f"{storm.ship_id}:1:2:{Z3}:")


def test_six_players_are_split_into_two_battles_of_three(storm):
    add_monster(storm, Z2, max_active=5)
    t = _sail(storm, ALPHA, BETA, GAMMA)
    for i, cid in enumerate((801, 802, 803)):
        add_player(storm, cid, 700 + i, DECK)
    run_ship(storm, t + timedelta(minutes=10))
    rs = raids(storm)
    assert [r.player_ids for r in rs] == [[ALPHA, BETA, GAMMA], [801, 802, 803]]
    assert [r.group_no for r in rs] == [0, 1] and len({r.attack_key for r in rs}) == 1
    assert [len(r.mob_ids) for r in rs] == [3, 3]              # pack = min(max_active, group size)
    assert [r.battle_id for r in rs] == [901, 902] and [r.status for r in rs] == ["fighting", "fighting"]


def test_eleven_players_are_four_four_three(storm):
    add_monster(storm, Z2, max_active=2)
    t = _sail(storm, ALPHA, BETA, GAMMA)
    for i, cid in enumerate(range(801, 809)):
        add_player(storm, cid, 700 + i, DECK)
    run_ship(storm, t + timedelta(minutes=10))
    rs = raids(storm)
    assert [len(r.player_ids) for r in rs] == [4, 4, 3] and [len(r.mob_ids) for r in rs] == [2, 2, 2]


@pytest.mark.parametrize("how", ["battle", "unconscious", "zero_hp", "gathering"])
def test_nobody_able_to_fight_is_repelled_with_a_delay(storm, stub_law_notify_send, how):
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA)
    if how == "battle":
        in_battle(storm, ALPHA, 55)
    elif how == "unconscious":
        _unconscious(storm, ALPHA)
    elif how == "zero_hp":
        exec_(storm, "UPDATE character_attributes SET current_health = 0 WHERE character_id = :c", c=ALPHA)
    else:
        exec_(storm, "INSERT INTO gathering_sessions (character_id, status) VALUES (:c, 'active')", c=ALPHA)
    out = run_ship(storm, t + timedelta(minutes=10))
    s = ship(storm)
    assert sea_pass.EV_RAID_REPELLED in out.events and raids(storm) == []
    assert s.next_zone_at == t + timedelta(minutes=25) and s.hold_until is None
    (n,) = ws_events(stub_law_notify_send, sea_pass.EV_RAID_REPELLED)
    assert "отбилась" in n["message"] and "Кракен" in n["message"]
    assert storm.bs.calls == []


def test_repelled_on_an_empty_deck_uses_the_settings_delay(storm):
    set_params(storm, raid_repelled_delay_minutes=0)
    add_monster(storm, Z2)
    t = _sail(storm)
    out = run_ship(storm, t + timedelta(minutes=10))
    assert sea_pass.EV_RAID_REPELLED in out.events and ship(storm).next_zone_at == t + timedelta(minutes=20)


def test_only_able_players_are_pulled_in(storm):
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA, BETA, GAMMA)
    in_battle(storm, BETA, 55)
    _unconscious(storm, GAMMA)
    run_ship(storm, t + timedelta(minutes=10))
    (r,) = raids(storm)
    assert r.player_ids == [ALPHA]


@pytest.mark.parametrize("change", ["mult_zero", "disabled", "chance_zero", "no_rule"])
def test_no_raid(storm, change):
    if change == "mult_zero":
        set_params(storm, raid_chance_mult=0.0)
    if change != "no_rule":
        add_monster(storm, Z2, chance=0.0 if change == "chance_zero" else 100.0, enabled=change != "disabled")
    t = _sail(storm, ALPHA)
    out = run_ship(storm, t + timedelta(minutes=10))
    assert raids(storm) == [] and sea_pass.EV_RAID not in out.events
    assert sea_pass.EV_RAID_REPELLED not in out.events and ship(storm).next_zone_at == t + timedelta(minutes=20)


def test_raid_chance_multiplier_scales_the_roll(storm):
    add_monster(storm, Z2, chance=30.0)
    set_params(storm, raid_chance_mult=2.0)
    storm.rng.values = [0.55]                                  # 55 < 30 × 2
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=10))
    assert len(raids(storm)) == 1


def test_storm_and_raid_on_the_same_entry(storm):
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA)
    add_storm(storm, [Z2], start=t, minutes=600)
    out = run_ship(storm, t + timedelta(minutes=10))
    assert sea_pass.EV_STORM in out.events and sea_pass.EV_RAID in out.events
    assert storm.cas.ids == [ALPHA] and len(raids(storm)) == 1
    assert ship(storm).next_zone_at == t + timedelta(minutes=30 + 120)


def test_attack_key_is_unique_per_entry(storm):
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=10))
    (r,) = raids(storm)
    stamp = int((t + timedelta(minutes=20)).timestamp() // 60)
    assert r.attack_key == f"{storm.ship_id}:1:1:{Z2}:{stamp}" and len(r.attack_key) <= 48


def test_duplicate_plan_is_ignored(storm):
    import sea_raid_crud
    add_monster(storm, Z2)
    t = _sail(storm, ALPHA)
    run_ship(storm, t + timedelta(minutes=10))
    db = storm()
    try:
        s = db.get(models.SeaShip, storm.ship_id)
        s.next_zone_at = t + timedelta(minutes=20)              # the same entry as the planned attack
        pick = sea_raid_crud.MonsterPick(MONSTER_TPL, "Кракен", 1)
        assert sea_raid_crud.plan_raid(db, s, pick, [ALPHA], t) == []
        db.rollback()
    finally:
        db.close()
    assert len(raids(storm)) == 1


def test_without_the_053_tables_the_ship_sails_plainly(storm, monkeypatch):
    add_storm(storm, [Z2], minutes=600)
    exec_(storm, "DROP TABLE sea_raids")
    t = _sail(storm, ALPHA)
    out = run_ship(storm, t + timedelta(minutes=10))
    s = ship(storm)
    assert s.current_zone_id == Z2 and s.next_zone_at == t + timedelta(minutes=20)
    assert sea_pass.EV_STORM not in out.events and storm.cas.calls == []
