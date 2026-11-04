"""FEAT-199 QA (task 7): deferred crimes — reveal / close, the law-pass reveal step and the staff actions.

* ``reveal_crime``: conditional UPDATE (second call = None, nothing applied twice), the STORED reputation key (an
  earlier apply of the same key -> ``duplicate``), the wanted (incl. the guard floor), infamy NOT added again;
* ``close_crime``: conditional, no reputation / wanted, no player notice;
* ``roll_reveal`` / ``law_pass._reveal_crimes``: only due rows (``next_roll_at <= now``) roll, one roll per row per
  ``next_roll_at`` (daily), chance from the region's EFFECTIVE suspicion, mask × factor, three failed rolls -> closed,
  catch-up after downtime, one failing crime does not stop the others, «раскрыто» notice after the commit;
* staff reveal / close: RBAC (reputation:manage; editor / user 403), reason 3..500 + UUID request_id, 404 / 409,
  actor + reason in law_log, reveal notifies the player, close does not;
* suspicion lazy decay.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

import law_pass
import shadow_crud
import shadow_core as sc
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GUARD, MERCHANT, R_OST, USER_ALPHA, api, as_admin, as_moderator, as_user, exec_, law_world, now,
    q, rep_world, rid, rows, wanted,
)
from tests.reputation_world import apply, value, values
from tests.shadow_world import (
    crime, crimes, dec, dt, make_deferred, payloads, renown, set_roll, set_suspicion, shadow_settings, suspicion,
    ws_types,
)

D = Decimal


def _db_call(f, fn, *args, **kwargs):
    db = f()
    try:
        out = fn(db, *args, **kwargs)
        db.commit()
        return out
    finally:
        db.close()


def _log(f, crime_id):
    return rows(f, "SELECT action, event_key, chance_pct, roll_pct, reason, actor_user_id FROM law_log "
                   "WHERE ref_id = :r AND action IN ('reveal', 'reveal_fail', 'crime_closed', 'staff_reveal', "
                   "'staff_close') ORDER BY id", r=crime_id)


# =============================================================================================== reveal_crime

def test_reveal_applies_stored_snapshot_once(law_world):
    cid = make_deferred(law_world)
    assert renown(law_world, ALPHA) == (0, 150)
    result = _db_call(law_world, shadow_crud.reveal_crime, cid)
    assert result is not None and result.character_id == ALPHA and result.user_id == USER_ALPHA
    assert result.region_name == "Ост"
    c = crime(law_world, cid)
    assert c["status"] == "reported" and c["revealed_at"] is not None and c["resolved_at"] is not None
    assert value(law_world, ALPHA, R_OST) == -150 and wanted(law_world, ALPHA, R_OST) == 150
    keys = [r[0] for r in rows(law_world, "SELECT event_key FROM reputation_log WHERE character_id = :c "
                                          "AND is_echo = 0", c=ALPHA)]
    assert keys == [f"npc_kill:{MERCHANT}:77:{ALPHA}"]
    assert [r[0] for r in _log(law_world, cid)] == ["reveal"]
    # second call: conditional UPDATE matches nothing -> no double apply
    assert _db_call(law_world, shadow_crud.reveal_crime, cid) is None
    assert value(law_world, ALPHA, R_OST) == -150 and wanted(law_world, ALPHA, R_OST) == 150
    assert renown(law_world, ALPHA) == (0, 150)                         # infamy only once (at the crime)


def test_reveal_with_an_already_applied_reputation_key_is_a_duplicate(law_world):
    cid = make_deferred(law_world)
    apply(law_world, character_id=ALPHA, region_id=R_OST, action="npc_kill",
          idem_key=f"npc_kill:{MERCHANT}:77:{ALPHA}", delta=-150, reason="race")
    before = values(law_world, ALPHA)
    result = _db_call(law_world, shadow_crud.reveal_crime, cid)
    assert result is not None and result.tier_changes == []
    assert values(law_world, ALPHA) == before                           # silent duplicate, not doubled
    assert wanted(law_world, ALPHA, R_OST) == 150                       # the wanted still applies once


def test_reveal_guard_crime_applies_the_heavy_floor(law_world):
    cid = make_deferred(law_world, npc_id=GUARD, floor=600, points=40, rep_delta=-40, crime_type="guard_defeat")
    _db_call(law_world, shadow_crud.reveal_crime, cid)
    assert wanted(law_world, ALPHA, R_OST) == 600


def test_reveal_and_close_ignore_non_open_rows(law_world):
    cid = make_deferred(law_world)
    assert _db_call(law_world, shadow_crud.close_crime, cid) is True
    assert _db_call(law_world, shadow_crud.reveal_crime, cid) is None
    assert _db_call(law_world, shadow_crud.close_crime, cid) is False
    c = crime(law_world, cid)
    assert c["status"] == "closed" and c["resolved_at"] is not None and c["revealed_at"] is None
    assert values(law_world, ALPHA) == {} and wanted(law_world, ALPHA, R_OST) is None
    assert [r[0] for r in _log(law_world, cid)] == ["crime_closed"]


def test_reveal_of_a_reported_crime_is_a_noop(law_world):
    import law_crud
    db = law_world()
    try:
        res = law_crud.register_crime(db, crime_type="npc_kill", character_id=ALPHA, region_id=R_OST, points=150,
                                      event_key="crime:x:1")
        db.commit()
        crime_id = res.crime_id
    finally:
        db.close()
    assert _db_call(law_world, shadow_crud.reveal_crime, crime_id) is None
    assert wanted(law_world, ALPHA, R_OST) == 150


# =============================================================================================== roll_reveal / pass

def _run(f, when):
    return law_pass.run_pass(f, when, claim=False)


def test_pass_skips_rows_not_due_yet(law_world, monkeypatch):
    make_deferred(law_world)
    rng = set_roll(monkeypatch, 0.0)
    stats = _run(law_world, now() + timedelta(hours=23))
    assert stats["reveal_rolls"] == 0 and rng.calls == 0


def test_pass_success_reveals_and_notifies(law_world, monkeypatch, stub_law_notify_send):
    cid = make_deferred(law_world)
    set_roll(monkeypatch, 0.0)
    stats = _run(law_world, now() + timedelta(days=1, minutes=1))
    assert (stats["reveal_rolls"], stats["revealed"], stats["closed"]) == (1, 1, 0)
    assert crime(law_world, cid)["status"] == "reported"
    assert value(law_world, ALPHA, R_OST) == -150 and wanted(law_world, ALPHA, R_OST) == 150
    sent = payloads(stub_law_notify_send)
    revealed = [p for p in sent if p["ws_type"] == "law_revealed"]
    assert len(revealed) == 1 and revealed[0]["category"] == "system" and revealed[0]["target_value"] == USER_ALPHA
    assert "Ост" in revealed[0]["message"] and "раскрыто" in revealed[0]["message"]
    assert "law_wanted" in ws_types(stub_law_notify_send)
    reveal = _log(law_world, cid)[0]
    assert reveal[0] == "reveal" and reveal[1] == f"law:reveal:{cid}" and dec(reveal[2]) == D("15.00")


def test_pass_failure_moves_next_roll_by_one_day(law_world, monkeypatch, stub_law_notify_send):
    cid = make_deferred(law_world)
    first = dt(crime(law_world, cid)["next_roll_at"])
    rng = set_roll(monkeypatch, 0.99)
    when = now() + timedelta(days=1, minutes=1)
    stats = _run(law_world, when)
    assert (stats["reveal_rolls"], stats["revealed"]) == (1, 0)
    c = crime(law_world, cid)
    assert c["status"] == "unwitnessed" and c["reveal_attempts"] == 1
    assert dt(c["next_roll_at"]) == first + timedelta(days=1)
    log = _log(law_world, cid)
    assert log[0][:2] == ("reveal_fail", f"law:reveal_roll:{cid}:1") and dec(log[0][3]) == D("99.00")
    # the same day: no second roll (daily cadence from next_roll_at, not from the pass interval)
    _run(law_world, when + timedelta(minutes=5))
    assert rng.calls == 1 and crime(law_world, cid)["reveal_attempts"] == 1
    assert values(law_world, ALPHA) == {} and stub_law_notify_send.call_count == 0


def test_three_failed_rolls_close_the_case(law_world, monkeypatch, stub_law_notify_send):
    created = now()
    cid = make_deferred(law_world, created=created)
    set_roll(monkeypatch, 0.99)
    for day in (1, 2):
        stats = _run(law_world, created + timedelta(days=day, seconds=1))
        assert stats["closed"] == 0 and crime(law_world, cid)["status"] == "unwitnessed"
    stats = _run(law_world, created + timedelta(days=3, seconds=1))
    assert stats["closed"] == 1
    c = crime(law_world, cid)
    assert c["status"] == "closed" and c["reveal_attempts"] == 3
    assert [r[0] for r in _log(law_world, cid)] == ["reveal_fail", "reveal_fail", "reveal_fail", "crime_closed"]
    assert values(law_world, ALPHA) == {} and wanted(law_world, ALPHA, R_OST) is None
    assert stub_law_notify_send.call_count == 0                         # the player never learns about the case
    assert _run(law_world, created + timedelta(days=10))["reveal_rolls"] == 0


def test_catch_up_after_downtime_is_one_roll_per_pass(law_world, monkeypatch):
    created = now()
    cid = make_deferred(law_world, created=created)
    rng = set_roll(monkeypatch, 0.99)
    late = created + timedelta(days=2, hours=12)
    _run(law_world, late)
    assert rng.calls == 1 and crime(law_world, cid)["reveal_attempts"] == 1
    _run(law_world, late)
    assert rng.calls == 2 and crime(law_world, cid)["reveal_attempts"] == 2
    assert dt(crime(law_world, cid)["next_roll_at"]) == created + timedelta(days=3)
    _run(law_world, late)                                               # next roll is in the future now
    assert rng.calls == 2


def test_reveal_chance_grows_with_effective_suspicion(law_world, monkeypatch):
    cid = make_deferred(law_world)
    when = now() + timedelta(days=1, minutes=1)
    set_suspicion(law_world, R_OST, 55, decay_at=when - timedelta(days=1))   # decays 5/day -> 50 at the roll
    set_roll(monkeypatch, 0.99)
    _run(law_world, when)
    assert dec(_log(law_world, cid)[0][2]) == D("35.00")                # 15 + 50 x 0.4


def test_masked_crime_reveal_chance_is_halved(law_world, monkeypatch):
    cid = make_deferred(law_world, masked=True)
    assert crime(law_world, cid)["status"] == "masked"
    set_suspicion(law_world, R_OST, 50, decay_at=now() + timedelta(days=1, minutes=1))
    set_roll(monkeypatch, 0.99)
    _run(law_world, now() + timedelta(days=1, minutes=1))
    assert dec(_log(law_world, cid)[0][2]) == D("17.50")


def test_reveal_roll_success_boundary(law_world, monkeypatch):
    cid = make_deferred(law_world)
    set_roll(monkeypatch, 0.15)                                         # roll 15.00 is not < 15.00
    _run(law_world, now() + timedelta(days=1, minutes=1))
    assert crime(law_world, cid)["status"] == "unwitnessed"


def test_one_failing_crime_does_not_stop_the_others(law_world, monkeypatch):
    bad = make_deferred(law_world, character_id=ALPHA)
    good = make_deferred(law_world, character_id=BETA)
    real = shadow_crud.roll_reveal

    def flaky(db, crime_id, when):
        if crime_id == bad:
            raise RuntimeError("boom")
        return real(db, crime_id, when)

    monkeypatch.setattr(shadow_crud, "roll_reveal", flaky)
    set_roll(monkeypatch, 0.0)
    stats = _run(law_world, now() + timedelta(days=1, minutes=1))
    assert stats["revealed"] == 1
    assert crime(law_world, bad)["status"] == "unwitnessed"
    assert crime(law_world, good)["status"] == "reported" and wanted(law_world, BETA, R_OST) == 150


def test_pass_runs_without_the_econ_tick(law_world, monkeypatch):
    import econ_scheduler
    import econ_tick
    make_deferred(law_world)
    set_roll(monkeypatch, 0.0)
    exec_(law_world, "UPDATE law_crimes SET next_roll_at = :t", t=now() - timedelta(minutes=1))
    import reputation_decay
    from unittest.mock import MagicMock
    monkeypatch.setattr(reputation_decay, "run_pass", lambda f: None)
    monkeypatch.setattr(econ_tick, "is_tick_enabled", lambda s: False)
    tick = MagicMock()
    monkeypatch.setattr(econ_tick, "run_tick", tick)
    assert econ_scheduler.run_scheduled_once(law_world) is None
    tick.assert_not_called()
    assert crimes(law_world)[0]["status"] == "reported"


# =============================================================================================== suspicion decay

def test_suspicion_decays_lazily(law_world):
    set_suspicion(law_world, R_OST, 30, decay_at=now() - timedelta(days=2))     # 5 / day
    db = law_world()
    try:
        s = shadow_crud.load_settings(db)
        assert shadow_crud.effective_suspicion(db, R_OST, s, now()) == 20
        assert shadow_crud.region_suspicion_state(db, R_OST) == {"code": "uneasy", "label": "В крае неспокойно"}
        assert shadow_crud.effective_suspicion(db, R_OST, s, now() + timedelta(days=10)) == 0
        assert shadow_crud.region_suspicion_state(db, R_OST, now=now() + timedelta(days=10)) is None
        assert shadow_crud.effective_suspicion(db, None, s, now()) == 0
    finally:
        db.close()
    assert suspicion(law_world, R_OST) == 30                            # read never writes


def test_add_suspicion_materialises_before_adding(law_world):
    set_suspicion(law_world, R_OST, 30, decay_at=now() - timedelta(days=2))
    db = law_world()
    try:
        s = shadow_crud.load_settings(db)
        assert shadow_crud.add_suspicion(db, R_OST, 10, s, now()) == 30          # 20 + 10
        db.commit()
    finally:
        db.close()
    assert suspicion(law_world, R_OST) == 30


# =============================================================================================== staff reveal / close

def _reveal(api, cid, reason="Свидетель нашёлся", request_id=None):
    return api.post(f"/characters/admin/shadow/crimes/{cid}/reveal",
                    json={"reason": reason, "request_id": request_id or rid()})


def _close(api, cid, reason="Нет улик", request_id=None):
    return api.post(f"/characters/admin/shadow/crimes/{cid}/close",
                    json={"reason": reason, "request_id": request_id or rid()})


def test_staff_reveal(api, law_world, stub_law_notify_send):
    cid = make_deferred(law_world)
    as_admin()
    resp = _reveal(api, cid, reason="  Свидетель нашёлся  ")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"] == "Преступление раскрыто" and body["crime"]["status"] == "reported"
    assert body["crime"]["id"] == cid and body["crime"]["character_name"] == "Альфа"
    assert value(law_world, ALPHA, R_OST) == -150 and wanted(law_world, ALPHA, R_OST) == 150
    log = _log(law_world, cid)
    assert log == [("staff_reveal", f"law:staff_reveal:{cid}", None, None, "Свидетель нашёлся", 1)]
    assert "law_revealed" in ws_types(stub_law_notify_send)
    # second click / replay: 409, nothing applied twice
    again = _reveal(api, cid)
    assert again.status_code == 409 and again.json()["detail"] == "Дело уже раскрыто или закрыто"
    assert value(law_world, ALPHA, R_OST) == -150 and wanted(law_world, ALPHA, R_OST) == 150


def test_staff_close_without_player_notice(api, law_world, stub_law_notify_send):
    cid = make_deferred(law_world)
    as_moderator()
    resp = _close(api, cid)
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Дело закрыто" and resp.json()["crime"]["status"] == "closed"
    assert stub_law_notify_send.call_count == 0
    assert values(law_world, ALPHA) == {} and wanted(law_world, ALPHA, R_OST) is None
    assert _log(law_world, cid) == [("staff_close", f"law:staff_close:{cid}", None, None, "Нет улик", 2)]
    assert _close(api, cid).status_code == 409
    assert _reveal(api, cid).status_code == 409


def test_staff_actions_unknown_crime(api, law_world):
    as_admin()
    assert _reveal(api, 99999).status_code == 404
    assert _close(api, 99999).json()["detail"] == "Преступление не найдено"


@pytest.mark.parametrize("perms", [["reputation:read"], ["reputation:read", "reputation:settings"], []])
def test_staff_actions_need_manage(api, law_world, perms):
    cid = make_deferred(law_world)
    as_user(3, "editor", perms)
    assert _reveal(api, cid).status_code == 403
    assert _close(api, cid).status_code == 403
    assert crime(law_world, cid)["status"] == "unwitnessed"


def test_player_cannot_reveal_own_crime(api, law_world):
    cid = make_deferred(law_world)
    as_user(USER_ALPHA)
    assert _reveal(api, cid).status_code == 403


@pytest.mark.parametrize("body", [
    {"request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
    {"reason": "  a ", "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
    {"reason": "x" * 501, "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
    {"reason": "Нормальная причина"},
    {"reason": "Нормальная причина", "request_id": "'; DROP TABLE law_crimes; --"},
    {"reason": 12345, "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
])
def test_staff_action_validation(api, law_world, body):
    cid = make_deferred(law_world)
    as_admin()
    resp = api.post(f"/characters/admin/shadow/crimes/{cid}/reveal", json=body)
    assert resp.status_code == 422
    assert crime(law_world, cid)["status"] == "unwitnessed"


def test_staff_reason_with_sql_is_stored_literally(api, law_world):
    cid = make_deferred(law_world)
    as_admin()
    evil = "x'); DROP TABLE law_crimes; --"
    assert _close(api, cid, reason=evil).status_code == 200
    assert q(law_world, "SELECT reason FROM law_log WHERE event_key = :k", k=f"law:staff_close:{cid}") == evil
    assert q(law_world, "SELECT COUNT(*) FROM law_crimes") == 1


def test_crime_id_path_must_be_an_int(api, law_world):
    as_admin()
    resp = api.post("/characters/admin/shadow/crimes/1%20OR%201=1/reveal",
                    json={"reason": "Причина", "request_id": rid()})
    assert resp.status_code in (404, 422)


def test_reveal_setting_constants():
    assert shadow_crud.REVEAL_STEP == timedelta(hours=24)
    assert sc.DEFAULT_SETTINGS.reveal_days == 3
