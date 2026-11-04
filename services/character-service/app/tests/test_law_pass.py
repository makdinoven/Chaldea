"""FEAT-198 QA (task 9): the law scheduler pass (§3.7).

* throttle: the conditional claim on ``law_settings.pass_last_run_at`` (55 s); hooked into the econ scheduler
  BEFORE the economy switch (runs with the tick disabled) and a failure never blocks it;
* expired encounters: auto-surrender with a jail, forced fine without one (decision 5, A3);
* lost callbacks: battle-service polled (mocked) — finished -> applied, 404 / no battle -> back to pending,
  still running / unreachable -> untouched;
* served terms: ``served`` + «Срок заключения окончен» once;
* guard recovery: KO over -> cleared + healed; an idle damaged guard healed; a guard in battle / still KO'd not.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import battle_client
import econ_scheduler
import econ_tick
import law_pass
import reputation_decay
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, GUARD, GUARD_FARM, GUARD_POST, L_FARM, L_JAIL, L_POST, OVERRIDE, R_OST, R_PASHNI, USER_ALPHA,
    char_row, encounter, exec_, gold, jail_character, law_payloads, law_world, make_encounter, now, q, rep_world,
    rows, set_gold, set_wanted, wanted,
)


def _run(f, claim=False, when=None):
    return law_pass.run_pass(f, when, claim=claim)


def _expire(f, enc_id):
    exec_(f, "UPDATE law_encounters SET expires_at = :t WHERE id = :e", t=now() - timedelta(minutes=1), e=enc_id)


def _fighting(f, enc_id, battle_id=555, minutes_ago=5):
    exec_(f, "UPDATE law_encounters SET status = 'fighting', battle_id = :b, fight_started_at = :t WHERE id = :e",
          b=battle_id, t=now() - timedelta(minutes=minutes_ago), e=enc_id)


@pytest.fixture
def poll(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(battle_client, "get_battle_result", mock)
    return mock


# =============================================================================================== throttle / hook

def test_claim_throttle(law_world):
    assert _run(law_world, claim=True)["ran"] is True
    assert _run(law_world, claim=True)["ran"] is False                                  # inside 55 s
    later = now() + timedelta(seconds=56)
    assert _run(law_world, claim=True, when=later)["ran"] is True
    assert _run(law_world, claim=False)["ran"] is True                                  # explicit bypass


def test_claim_without_settings_row(law_world):
    exec_(law_world, "DELETE FROM law_settings")
    assert _run(law_world, claim=True)["ran"] is False


def test_scheduler_runs_the_law_pass_with_the_econ_tick_disabled(law_world, monkeypatch):
    calls = []
    monkeypatch.setattr(reputation_decay, "run_pass", lambda f: calls.append("rep"))
    monkeypatch.setattr(law_pass, "run_pass", lambda f: calls.append("law"))
    monkeypatch.setattr(econ_tick, "is_tick_enabled", lambda s: False)
    tick = MagicMock()
    monkeypatch.setattr(econ_tick, "run_tick", tick)
    assert econ_scheduler.run_scheduled_once(law_world) is None
    assert calls == ["rep", "law"]
    tick.assert_not_called()


def test_scheduler_survives_a_law_pass_failure(law_world, monkeypatch):
    monkeypatch.setattr(reputation_decay, "run_pass", lambda f: None)
    monkeypatch.setattr(law_pass, "run_pass", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(econ_tick, "is_tick_enabled", lambda s: False)
    assert econ_scheduler.run_scheduled_once(law_world) is None


# =============================================================================================== expired encounters

def test_expired_encounter_auto_surrender(law_world, stub_law_notify_send):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    _expire(law_world, enc_id)
    stats = _run(law_world)
    assert stats["auto_resolved"] == 1
    assert encounter(law_world, enc_id).status == "jailed"
    row = char_row(law_world, ALPHA)
    assert row.current_location_id == L_JAIL and row.jailed_until > now() and row.law_encounter_id is None
    assert q(law_world, "SELECT action FROM law_log WHERE event_key = :k", k=f"law:auto:{enc_id}") == "auto_surrender"
    msgs = [p["message"] for p in law_payloads(stub_law_notify_send)]
    assert any(m.startswith("Вы так и не ответили страже — вас заключили") for m in msgs)
    assert _run(law_world)["auto_resolved"] == 0                                        # idempotent


def test_expired_encounter_without_jail_forced_fine(law_world):
    set_wanted(law_world, ALPHA, R_PASHNI, 150)
    set_gold(law_world, ALPHA, 1000)
    enc_id = make_encounter(law_world, location_id=L_FARM)
    _expire(law_world, enc_id)
    assert _run(law_world)["auto_resolved"] == 1
    assert encounter(law_world, enc_id).status == "auto_fined"
    assert gold(law_world, ALPHA) == 850 and wanted(law_world, ALPHA, R_PASHNI) == 0
    assert char_row(law_world, ALPHA).law_encounter_id is None


def test_expired_outlaw_without_jail_partial_fine(law_world):
    from tests.law_world import set_value
    set_value(law_world, ALPHA, R_PASHNI, -700)
    set_wanted(law_world, ALPHA, R_PASHNI, 50)
    set_gold(law_world, ALPHA, 100)
    enc_id = make_encounter(law_world, location_id=L_FARM)
    assert encounter(law_world, enc_id).fine == 400                                     # outlaw minimum level
    _expire(law_world, enc_id)
    _run(law_world)
    assert encounter(law_world, enc_id).status == "auto_fined"
    assert gold(law_world, ALPHA) == 0 and wanted(law_world, ALPHA, R_PASHNI) == 50


def test_not_yet_expired_encounter_untouched(law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    assert _run(law_world)["auto_resolved"] == 0
    assert encounter(law_world, enc_id).status == "pending"


def test_auto_surrender_move_failure_retries_next_pass(law_world):
    from fastapi import HTTPException
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    _expire(law_world, enc_id)
    law_world.prepare_move.side_effect = HTTPException(status_code=502, detail="down")
    assert _run(law_world)["auto_resolved"] == 0
    assert encounter(law_world, enc_id).status == "pending"
    law_world.prepare_move.side_effect = None
    assert _run(law_world)["auto_resolved"] == 1
    assert encounter(law_world, enc_id).status == "jailed"


# =============================================================================================== lost callbacks

def test_lost_callback_finished_battle_is_applied(law_world, poll):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    _fighting(law_world, enc_id)
    poll.return_value = {"status": "finished", "winner_team": 2, "aborted": False}
    stats = _run(law_world)
    assert stats["fights_applied"] == 1
    poll.assert_called_once_with(555)
    assert encounter(law_world, enc_id).status == "jailed"


def test_lost_callback_won(law_world, poll):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    _fighting(law_world, enc_id)
    poll.return_value = {"status": "finished", "winner_team": 1}
    _run(law_world)
    assert encounter(law_world, enc_id).status == "won"
    assert char_row(law_world, ALPHA).law_encounter_id is None


@pytest.mark.parametrize("answer,expected", [
    (battle_client.BATTLE_NOT_FOUND, "pending"),
    ({"status": "in_progress"}, "fighting"),
])
def test_lost_callback_not_found_or_running(law_world, poll, answer, expected):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    _fighting(law_world, enc_id)
    poll.return_value = answer
    _run(law_world)
    assert encounter(law_world, enc_id).status == expected


def test_lost_callback_without_battle_id_resets(law_world, poll):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    exec_(law_world, "UPDATE law_encounters SET status = 'fighting', fight_started_at = :t WHERE id = :e",
          t=now() - timedelta(minutes=5), e=enc_id)
    assert _run(law_world)["fights_reset"] == 1
    poll.assert_not_called()
    assert encounter(law_world, enc_id).status == "pending"


def test_lost_callback_recent_fight_and_unreachable_service(law_world, poll):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    _fighting(law_world, enc_id, minutes_ago=1)                                         # too recent to poll
    _run(law_world)
    poll.assert_not_called()
    _fighting(law_world, enc_id, minutes_ago=3)
    poll.side_effect = battle_client.BattleServiceError("down")
    _run(law_world)
    assert encounter(law_world, enc_id).status == "fighting"


# =============================================================================================== served terms

def test_served_term_notified_once(law_world, stub_law_notify_send):
    term_id = jail_character(law_world, hours=-1)
    stats = _run(law_world)
    assert stats["served"] == 1
    assert rows(law_world, "SELECT status, notified FROM law_jail_terms WHERE id = :t", t=term_id) == [("served", 1)]
    assert char_row(law_world, ALPHA).jail_region_id is None
    msgs = [p for p in law_payloads(stub_law_notify_send) if p["message"] == "Срок заключения окончен — вы свободны"]
    assert len(msgs) == 1 and msgs[0]["target_value"] == USER_ALPHA
    assert _run(law_world)["served"] == 0


def test_serving_term_untouched(law_world):
    term_id = jail_character(law_world, hours=2)
    assert _run(law_world)["served"] == 0
    assert q(law_world, "SELECT status FROM law_jail_terms WHERE id = :t", t=term_id) == "serving"


# =============================================================================================== guard recovery

def test_guard_recovery(law_world):
    exec_(law_world, "UPDATE characters SET unconscious_until = :t WHERE id = :g",
          t=now() - timedelta(minutes=1), g=GUARD_POST)                                 # KO over
    exec_(law_world, "UPDATE characters SET unconscious_until = :t WHERE id = :g",
          t=now() + timedelta(hours=2), g=GUARD_FARM)                                   # still KO'd
    exec_(law_world, "UPDATE character_attributes SET current_health = 5 WHERE character_id IN (:a, :b, :c, :d)",
          a=GUARD_POST, b=GUARD_FARM, c=GUARD, d=OVERRIDE)
    exec_(law_world, "INSERT INTO battles (id, status) VALUES (900, 'in_progress')")
    exec_(law_world, "INSERT INTO battle_participants (battle_id, character_id) VALUES (900, :g)", g=OVERRIDE)
    stats = _run(law_world)
    assert stats["guards_recovered"] == 1 and stats["guards_healed"] == 2
    hp = dict(rows(law_world, "SELECT character_id, current_health FROM character_attributes"))
    assert hp[GUARD_POST] == 100 and hp[GUARD] == 100                                   # healed
    assert hp[GUARD_FARM] == 5 and hp[OVERRIDE] == 5                                    # KO'd / in battle
    assert q(law_world, "SELECT unconscious_until FROM characters WHERE id = :g", g=GUARD_POST) is None
    assert q(law_world, "SELECT unconscious_until FROM characters WHERE id = :g", g=GUARD_FARM) is not None
    assert q(law_world, "SELECT current_health FROM character_attributes WHERE character_id = :c", c=ALPHA) == 100


def test_one_bad_item_does_not_stop_the_pass(law_world, monkeypatch):
    import law_flows
    set_wanted(law_world, ALPHA, R_OST, 150)
    set_wanted(law_world, BETA, R_OST, 150)
    first = make_encounter(law_world)
    second = make_encounter(law_world, character_id=BETA)
    _expire(law_world, first)
    _expire(law_world, second)
    real = law_flows.auto_resolve

    async def flaky(db, encounter_id):
        if encounter_id == first:
            raise RuntimeError("boom")
        return await real(db, encounter_id)

    monkeypatch.setattr(law_flows, "auto_resolve", flaky)
    jail_character(law_world, GAMMA, hours=-1)                                       # a served term
    stats = _run(law_world)
    assert stats["auto_resolved"] == 1 and stats["served"] == 1
    assert encounter(law_world, first).status == "pending"
    assert encounter(law_world, second).status == "jailed"
