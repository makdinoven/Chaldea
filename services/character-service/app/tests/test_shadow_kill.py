"""FEAT-199 QA (task 7): the crime orchestrator ``shadow_crud.npc_kill_consequences`` through
PUT /characters/internal/npc-status/{id} (battle-service contract unchanged).

* the witness chance on the stored crime row: marker base, EFFECTIVE agility / luck (FEAT-195 caps), subclass keys,
  mask, fame (not for a masked member), group = least stealthy member + size bonus, clamps 5..95; roll boundary;
* always witnessed (no roll at all): positive kill (bandit), guard-encounter battle, ``witness_enabled = 0``,
  jail escape;
* witnessed + unmasked -> immediate reputation + wanted with the FEAT-197/198 keys;
* unwitnessed / masked -> deferred snapshot (exact reputation key / reason / floor / deadlines), no reputation, no
  wanted, «никто не видел» / «в маске» notices, region suspicion once per kill event, infamy for every crime row;
* group: ONE roll, a masked member deferred while the unmasked member is applied;
* repeated npc-status -> no second roll; mask reader fallback only for the missing column (WARNING), other errors
  raise (the whole transition rolls back).
"""

import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import shadow_crud
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BANDIT, BETA, GUARD, MERCHANT, R_HOLMY, R_OST, R_PASHNI, USER_ALPHA, USER_BETA, api, as_user,
    exec_, jail_character, law_world, now, q, rep_world, rid, rows, set_wanted, wanted,
)
from tests.reputation_world import value, values
from tests.shadow_world import (
    MARKET, crimes, dec, dt, give_mask, guard_encounter_battle, kill, no_roll,
    payloads, renown, renown_log, set_attrs, set_marker, set_renown, set_roll, set_subclass, shadow_settings,
    suspicion, ws_types,
)

D = Decimal
SEEN = 0.0           # roll 0.00 -> always below the (>= 5 %) chance
UNSEEN = 0.9999      # roll 99.99 -> always above the (<= 95 %) chance


def _only_crime(f, cid=ALPHA):
    rows_ = crimes(f, cid)
    assert len(rows_) == 1, rows_
    return rows_[0]


# =============================================================================================== witness chance

def test_chance_uses_marker_base_and_roll_boundary(api, law_world, monkeypatch):
    set_marker(law_world, MARKET, "dangerous")                          # base 25, stats 0 -> 25.00
    set_roll(monkeypatch, 0.25)                                         # roll 25.00 is NOT < 25.00 -> unseen
    assert kill(api, MERCHANT, [ALPHA]).status_code == 200
    c = _only_crime(law_world)
    assert dec(c["witness_chance_pct"]) == D("25.00") and dec(c["witness_roll_pct"]) == D("25.00")
    assert c["status"] == "unwitnessed"


def test_roll_just_below_chance_is_witnessed(api, law_world, monkeypatch):
    set_marker(law_world, MARKET, "dangerous")
    set_roll(monkeypatch, 0.2499)
    kill(api, MERCHANT, [ALPHA])
    c = _only_crime(law_world)
    assert c["status"] == "reported" and dec(c["witness_roll_pct"]) == D("24.99")


@pytest.mark.parametrize("marker,expected", [("safe", "70.00"), ("farm", "45.00"), ("dangerous", "25.00"),
                                             ("dungeon", "15.00")])
def test_chance_by_marker(api, law_world, monkeypatch, marker, expected):
    set_marker(law_world, MARKET, marker)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    assert dec(_only_crime(law_world)["witness_chance_pct"]) == D(expected)


def test_chance_uses_effective_stats_with_caps(api, law_world, monkeypatch):
    # raw 300 / 100 would give 70 - 40 = 30; effective 175 + 100 = 275 -> 70 - 27.5 = 42.5
    set_attrs(law_world, ALPHA, agility=300, luck=100)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    assert dec(_only_crime(law_world)["witness_chance_pct"]) == D("42.50")


@pytest.mark.parametrize("key,expected", [("rogue_assassin", "55.00"), ("rogue_trickster", "55.00"),
                                          ("warrior_agent", "60.00"), ("warrior_berserk", "70.00")])
def test_subclass_bonus(api, law_world, monkeypatch, key, expected):
    set_subclass(law_world, ALPHA, key)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    assert dec(_only_crime(law_world)["witness_chance_pct"]) == D(expected)


def test_latest_subclass_choice_wins(api, law_world, monkeypatch):
    set_subclass(law_world, ALPHA, "warrior_berserk")
    set_subclass(law_world, ALPHA, "rogue_assassin")                    # later progress row
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    assert dec(_only_crime(law_world)["witness_chance_pct"]) == D("55.00")


def test_fame_raises_the_chance(api, law_world, monkeypatch):
    set_renown(law_world, ALPHA, fame=600)                              # famous: +10
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    assert dec(_only_crime(law_world)["witness_chance_pct"]) == D("80.00")


def test_mask_lowers_the_chance_and_hides_fame(api, law_world, monkeypatch):
    set_renown(law_world, ALPHA, fame=1500)                             # legend +15, ignored under a mask
    give_mask(law_world, ALPHA)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    c = _only_crime(law_world)
    assert dec(c["witness_chance_pct"]) == D("60.00") and bool(c["masked"]) is True


def test_head_item_without_mask_flag_is_not_a_mask(api, law_world, monkeypatch):
    give_mask(law_world, ALPHA, is_mask=0)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    c = _only_crime(law_world)
    assert dec(c["witness_chance_pct"]) == D("70.00") and not c["masked"]


def test_clamp_min(api, law_world, monkeypatch):
    set_marker(law_world, MARKET, "dungeon")
    set_attrs(law_world, ALPHA, agility=1000, luck=1000)
    set_subclass(law_world, ALPHA, "rogue_assassin")
    give_mask(law_world, ALPHA)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    assert dec(_only_crime(law_world)["witness_chance_pct"]) == D("5.00")


def test_clamp_max(api, law_world, monkeypatch):
    shadow_settings(law_world, witness_group_per_extra_pct=30)
    set_renown(law_world, ALPHA, fame=1500)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA, BETA])                                  # 70 + 15 + 30 = 115 -> 95
    assert {dec(c["witness_chance_pct"]) for c in crimes(law_world)} == {D("95.00")}


def test_group_chance_is_the_least_stealthy_member_plus_size(api, law_world, monkeypatch):
    set_attrs(law_world, ALPHA, agility=100)                            # 60
    set_subclass(law_world, ALPHA, "rogue_assassin")                    # 45
    rng = set_roll(monkeypatch, UNSEEN)                                 # BETA: 70 (weakest) + 10
    kill(api, MERCHANT, [ALPHA, BETA])
    rows_ = crimes(law_world)
    assert len(rows_) == 2
    assert {dec(c["witness_chance_pct"]) for c in rows_} == {D("80.00")}
    assert {dec(c["witness_roll_pct"]) for c in rows_} == {D("99.99")}    # ONE roll for the group
    assert rng.calls == 1


def test_masked_member_is_anonymous_in_the_group_chance(api, law_world, monkeypatch):
    set_renown(law_world, ALPHA, fame=1500)
    give_mask(law_world, ALPHA)                                         # ALPHA: 70 - 10 = 60 (fame ignored)
    set_attrs(law_world, BETA, agility=200)                             # BETA: 70 - 15 = 55
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA, BETA])
    assert {dec(c["witness_chance_pct"]) for c in crimes(law_world)} == {D("70.00")}     # 60 + 10


def test_npc_killers_do_not_count_for_the_group(api, law_world, monkeypatch):
    rng = set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA, BANDIT, MERCHANT])
    assert dec(_only_crime(law_world)["witness_chance_pct"]) == D("70.00") and rng.calls == 1


# =============================================================================================== immediate path

def test_witnessed_unmasked_kill_applies_at_once_with_unchanged_keys(api, law_world, monkeypatch,
                                                                     stub_law_notify_send):
    set_roll(monkeypatch, SEEN)
    resp = kill(api, MERCHANT, [ALPHA])
    assert resp.json() == {"ok": True, "status": "dead", "killed": True, "knocked_out_until": None}
    c = _only_crime(law_world)
    assert c["status"] == "reported" and c["event_key"] == f"crime:npc_kill:{MERCHANT}:77:{ALPHA}"
    assert c["reputation_key"] == f"npc_kill:{MERCHANT}:77:{ALPHA}" and c["reputation_delta"] == -150
    assert value(law_world, ALPHA, R_OST) == -150 and wanted(law_world, ALPHA, R_OST) == 150
    assert rows(law_world, "SELECT event_key FROM reputation_log WHERE character_id = :c AND is_echo = 0",
                c=ALPHA) == [(f"npc_kill:{MERCHANT}:77:{ALPHA}",)]
    assert suspicion(law_world, R_OST) is None                           # nothing deferred
    assert "law_unseen" not in ws_types(stub_law_notify_send)
    assert "law_wanted" in ws_types(stub_law_notify_send)


# =============================================================================================== always witnessed

def test_positive_kill_is_never_rolled(api, law_world, monkeypatch):
    no_roll(monkeypatch)
    set_marker(law_world, MARKET, "dungeon")
    assert kill(api, BANDIT, [ALPHA]).status_code == 200
    assert crimes(law_world) == []
    assert value(law_world, ALPHA, R_OST) == 20                          # reputation as before
    assert renown(law_world, ALPHA) == (10, 0)                           # fame via the hook (+20 x 0.5)


def test_guard_encounter_battle_is_always_witnessed_even_masked(api, law_world, monkeypatch):
    guard_encounter_battle(law_world, 77)
    give_mask(law_world, ALPHA)
    no_roll(monkeypatch)
    kill(api, MERCHANT, [ALPHA])
    c = _only_crime(law_world)
    assert c["status"] == "reported" and dec(c["witness_chance_pct"]) == D("100.00")
    assert c["witness_roll_pct"] is None and not c["masked"]
    assert value(law_world, ALPHA, R_OST) == -150 and wanted(law_world, ALPHA, R_OST) == 150


def test_guard_ko_in_an_encounter_fight_is_witnessed_with_heavy_floor(api, law_world, monkeypatch):
    guard_encounter_battle(law_world, 77)
    no_roll(monkeypatch)
    kill(api, GUARD, [ALPHA])
    c = _only_crime(law_world)
    assert c["crime_type"] == "guard_defeat" and c["status"] == "reported"
    assert wanted(law_world, ALPHA, R_OST) >= 600


def test_switch_off_forces_witnessed(api, law_world, monkeypatch):
    shadow_settings(law_world, witness_enabled=False)
    give_mask(law_world, ALPHA)
    no_roll(monkeypatch)
    kill(api, MERCHANT, [ALPHA])
    c = _only_crime(law_world)
    assert c["status"] == "reported" and c["witness_roll_pct"] is None
    assert wanted(law_world, ALPHA, R_OST) == 150


def test_jail_escape_is_always_reported_and_adds_infamy(api, law_world, monkeypatch):
    term = jail_character(law_world, hours=10)
    set_roll(monkeypatch, 0.0)                                          # the escape roll (not a witness roll)
    as_user(USER_ALPHA)
    resp = api.post(f"/characters/{ALPHA}/law/jail/escape", json={"request_id": rid()})
    assert resp.status_code == 200 and resp.json()["success"] is True
    c = _only_crime(law_world)
    assert c["crime_type"] == "jail_escape" and c["status"] == "reported" and c["witness_chance_pct"] is None
    assert renown(law_world, ALPHA) == (0, 10)                          # infamy_min_gain
    assert renown_log(law_world, ALPHA)[0][:3] == (f"infamy:crime:{c['id']}", "infamy", "crime")
    assert term


# =============================================================================================== deferred path

def test_unwitnessed_kill_is_deferred_with_a_snapshot(api, law_world, monkeypatch, stub_law_notify_send):
    set_roll(monkeypatch, UNSEEN)
    before = now()
    resp = kill(api, MERCHANT, [ALPHA])
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "status": "dead", "killed": True, "knocked_out_until": None}
    c = _only_crime(law_world)
    assert c["status"] == "unwitnessed" and not c["masked"]
    assert c["reputation_delta"] == -150
    assert c["reputation_key"] == f"npc_kill:{MERCHANT}:77:{ALPHA}"
    assert c["reputation_reason"] == f"Убит NPC «Лавочник» (#{MERCHANT}) в бою #77"
    assert c["wanted_floor"] is None and c["wanted_points"] == 150 and c["wanted_applied"] == 0
    assert c["resolved_at"] is None and c["revealed_at"] is None and c["reveal_attempts"] == 0
    created = dt(c["created_at"])
    assert created >= before
    assert dt(c["next_roll_at"]) == created + timedelta(days=1)
    assert dt(c["reveal_until"]) == created + timedelta(days=3)
    # nothing applied now
    assert values(law_world, ALPHA) == {} and wanted(law_world, ALPHA, R_OST) is None
    # region suspicion + infamy (hidden) + the hint
    assert suspicion(law_world, R_OST) == 10
    assert renown(law_world, ALPHA) == (0, 150)
    sent = payloads(stub_law_notify_send)
    assert [(p["target_value"], p["ws_type"], p["category"], p["message"]) for p in sent] == [
        (USER_ALPHA, "law_unseen", "progress", "Похоже, никто не видел, что произошло")]
    assert "150" not in sent[0]["message"]


def test_reveal_days_setting_drives_the_deadline(api, law_world, monkeypatch):
    shadow_settings(law_world, reveal_days=7)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    c = _only_crime(law_world)
    assert dt(c["reveal_until"]) == dt(c["created_at"]) + timedelta(days=7)


def test_masked_witnessed_kill_is_deferred_as_masked(api, law_world, monkeypatch, stub_law_notify_send):
    give_mask(law_world, ALPHA)
    set_roll(monkeypatch, SEEN)
    kill(api, MERCHANT, [ALPHA])
    c = _only_crime(law_world)
    assert c["status"] == "masked" and c["masked"]
    assert values(law_world, ALPHA) == {} and wanted(law_world, ALPHA, R_OST) is None
    assert suspicion(law_world, R_OST) == 20                            # suspicion_masked
    assert ws_types(stub_law_notify_send) == ["law_masked"]
    assert payloads(stub_law_notify_send)[0]["message"] == "Свидетели видели лишь неизвестного в маске"


def test_unseen_guard_ko_keeps_the_heavy_floor_snapshot(api, law_world, monkeypatch):
    set_roll(monkeypatch, UNSEEN)
    kill(api, GUARD, [ALPHA])
    c = _only_crime(law_world)
    assert c["crime_type"] == "guard_defeat" and c["status"] == "unwitnessed" and c["wanted_floor"] == 600
    assert wanted(law_world, ALPHA, R_OST) is None


def test_group_seen_masked_member_deferred_unmasked_applied(api, law_world, monkeypatch, stub_law_notify_send):
    give_mask(law_world, ALPHA)
    rng = set_roll(monkeypatch, SEEN)
    kill(api, MERCHANT, [ALPHA, BETA])
    a, b = _only_crime(law_world, ALPHA), _only_crime(law_world, BETA)
    assert (a["status"], b["status"]) == ("masked", "reported")
    assert a["witness_roll_pct"] == b["witness_roll_pct"] and rng.calls == 1
    assert values(law_world, ALPHA) == {} and wanted(law_world, ALPHA, R_OST) is None
    assert value(law_world, BETA, R_OST) == -150 and wanted(law_world, BETA, R_OST) == 150
    assert suspicion(law_world, R_OST) == 20
    by_user = {(p["target_value"], p["ws_type"]) for p in payloads(stub_law_notify_send)}
    assert (USER_ALPHA, "law_masked") in by_user and (USER_BETA, "law_wanted") in by_user
    assert (USER_BETA, "law_masked") not in by_user


def test_group_unseen_everyone_deferred_suspicion_once(api, law_world, monkeypatch):
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA, BETA])
    assert [c["status"] for c in crimes(law_world)] == ["unwitnessed", "unwitnessed"]
    assert suspicion(law_world, R_OST) == 10                            # once per kill event, not per member
    assert renown(law_world, ALPHA) == (0, 150) and renown(law_world, BETA) == (0, 150)


def test_group_unseen_with_a_masked_member_uses_the_strong_suspicion(api, law_world, monkeypatch):
    give_mask(law_world, BETA)
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA, BETA])
    statuses = {c["character_id"]: c["status"] for c in crimes(law_world)}
    assert statuses == {ALPHA: "unwitnessed", BETA: "unwitnessed"}      # unseen -> unwitnessed even masked
    assert suspicion(law_world, R_OST) == 20


def test_suspicion_accumulates_per_event_and_clamps(api, law_world, monkeypatch):
    shadow_settings(law_world, suspicion_max=25)
    set_roll(monkeypatch, UNSEEN)
    exec_(law_world, "UPDATE characters SET npc_status = 'alive' WHERE id = :m", m=MERCHANT)
    kill(api, MERCHANT, [ALPHA], battle_id=1)
    exec_(law_world, "UPDATE characters SET npc_status = 'alive' WHERE id = :m", m=MERCHANT)
    kill(api, MERCHANT, [ALPHA], battle_id=2)
    assert suspicion(law_world, R_OST) == 20
    exec_(law_world, "UPDATE characters SET npc_status = 'alive' WHERE id = :m", m=MERCHANT)
    kill(api, MERCHANT, [ALPHA], battle_id=3)
    assert suspicion(law_world, R_OST) == 25                            # clamped to suspicion_max
    assert renown(law_world, ALPHA) == (0, 450)


def test_witnessed_crime_also_adds_infamy(api, law_world, monkeypatch):
    set_roll(monkeypatch, SEEN)
    kill(api, MERCHANT, [ALPHA])
    c = _only_crime(law_world)
    assert renown(law_world, ALPHA) == (0, 150)
    assert renown_log(law_world, ALPHA) == [(f"infamy:crime:{c['id']}", "infamy", "crime", 150, 150, "none",
                                             "whispers", None)]


def test_repeated_npc_status_does_not_roll_again(api, law_world, monkeypatch):
    rng = set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA])
    assert rng.calls == 1
    resp = kill(api, MERCHANT, [ALPHA])
    assert resp.json()["killed"] is False
    resp = kill(api, MERCHANT, [ALPHA], battle_id=78)
    assert resp.json()["killed"] is False
    assert rng.calls == 1 and len(crimes(law_world)) == 1 and suspicion(law_world, R_OST) == 10
    assert renown(law_world, ALPHA) == (0, 150)


def test_kill_without_battle_uses_a_time_stamp_key(api, law_world, monkeypatch):
    set_roll(monkeypatch, UNSEEN)
    kill(api, MERCHANT, [ALPHA], battle_id=None)
    c = _only_crime(law_world)
    assert c["reputation_key"].startswith(f"npc_kill:{MERCHANT}:t") and c["reputation_key"].endswith(f":{ALPHA}")
    assert c["event_key"] == "crime:" + c["reputation_key"]


# =============================================================================================== mask reader

def _drop_mask_column(f):
    exec_(f, "DROP TABLE items")
    exec_(f, "CREATE TABLE items (id INTEGER PRIMARY KEY, name VARCHAR(100), item_type VARCHAR(30))")


def test_mask_reader_missing_column_is_a_warning_and_no_mask(law_world, caplog):
    _drop_mask_column(law_world)
    exec_(law_world, "INSERT INTO items (id, name, item_type) VALUES (1, 'Шлем', 'head')")
    exec_(law_world, "INSERT INTO equipment_slots (character_id, slot_type, item_id) VALUES (:c, 'head', 1)", c=ALPHA)
    db = law_world()
    try:
        with caplog.at_level(logging.WARNING, logger="character-service.shadow"):
            assert shadow_crud.wears_mask(db, ALPHA) is False
        assert any("is_mask" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)
        # the outer transaction stays usable after the savepoint rollback
        assert db.execute(text("SELECT COUNT(*) FROM characters")).scalar() > 0
    finally:
        db.close()


def test_kill_still_works_when_the_mask_column_is_missing(api, law_world, monkeypatch):
    _drop_mask_column(law_world)
    set_roll(monkeypatch, UNSEEN)
    assert kill(api, MERCHANT, [ALPHA]).status_code == 200
    c = _only_crime(law_world)
    assert c["status"] == "unwitnessed" and not c["masked"]


def test_mask_reader_other_errors_raise(law_world):
    exec_(law_world, "DROP TABLE equipment_slots")
    db = law_world()
    try:
        with pytest.raises(OperationalError):
            shadow_crud.wears_mask(db, ALPHA)
    finally:
        db.close()


def test_kill_with_a_broken_foreign_table_rolls_back_everything(api, law_world, monkeypatch):
    exec_(law_world, "DROP TABLE equipment_slots")
    set_roll(monkeypatch, UNSEEN)
    resp = kill(api, MERCHANT, [ALPHA])
    assert resp.status_code == 500
    assert q(law_world, "SELECT npc_status FROM characters WHERE id = :m", m=MERCHANT) == "alive"
    assert crimes(law_world) == [] and suspicion(law_world, R_OST) is None


def test_missing_mask_column_message_matcher():
    class E(Exception):
        pass
    assert shadow_crud._missing_mask_column(E("(1054, \"Unknown column 'i.is_mask' in 'where clause'\")"))
    assert shadow_crud._missing_mask_column(E("no such column: i.is_mask"))
    assert not shadow_crud._missing_mask_column(E("no such table: equipment_slots"))
    assert not shadow_crud._missing_mask_column(E("Unknown column 'i.other' in 'where clause'"))


# =============================================================================================== flee / escape

def test_flee_and_escape_use_effective_stats(law_world):
    import law_crud
    set_attrs(law_world, ALPHA, agility=300, luck=0)                    # effective 175
    db = law_world()
    try:
        s = law_crud.load_settings(db)
        assert law_crud.effective_attributes_of(db, ALPHA) == (D("175.00"), D("0.00"))
        assert law_crud.flee_chance(db, ALPHA, s) == D("63.75")          # 20 + 175 x 0.25 (raw would be 85)
        assert law_crud.escape_chance(db, ALPHA, s) == D("31.25")        # 5 + 175 x 0.15 (raw would be 50)
    finally:
        db.close()


def test_effective_stats_without_attributes_row(law_world):
    import law_crud
    exec_(law_world, "DELETE FROM character_attributes WHERE character_id = :c", c=ALPHA)
    db = law_world()
    try:
        assert law_crud.effective_attributes_of(db, ALPHA) == (D("0.00"), D("0.00"))
    finally:
        db.close()
