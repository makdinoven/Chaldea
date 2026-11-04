"""FEAT-198 QA (task 9): the encounter choices (§3.5) and the guard battle result.

* fine: ledger ``law_fine`` purse -> region treasury with the 10 % country tax, insufficient 400, wanted -> 0;
* surrender: the forced move (``main._prepare_move`` mocked), jailed_until, wanted cleared, the term, 502 revert;
* flee (RNG mocked): success moves back to the origin without a new stop there and sets the 1 h cooldown (A7);
  failure -> automatic fight; failure with a busy guard -> «flee_failed_blocked»;
* fight (battle-service mocked): busy guard 409, guard_gone, 502 revert, 409 detail pass-through, guard healed;
* battle result: won / lost with jail / lost without jail (forced fine, partial keeps wanted) / aborted /
  idempotent / mismatch 409 / unknown 404 / internal token;
* security: owner only (403 / 404), choice validation, request_id replay (one charge).
"""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import battle_client
import law_crud
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GUARD, GUARD_FARM, GUARD_POST, INTERNAL, L_FARM, L_JAIL, L_MARKET, L_POST, R_OST, R_PASHNI,
    USER_ALPHA, USER_BETA, FixedRng, api, as_user, char_row, encounter, exec_, gold, jail_character,
    law_payloads, law_world, make_encounter, now, q, rep_world, rid, rows, set_gold, set_value, set_wanted,
    treasury, wanted,
)

BATTLE_ID = 555


@pytest.fixture
def battle(monkeypatch):
    mock = AsyncMock(return_value=BATTLE_ID)
    monkeypatch.setattr(battle_client, "create_guard_battle", mock)
    return mock


@pytest.fixture
def roll(monkeypatch):
    """``roll(value)`` fixes the next flee / escape roll (0.0 = success, 0.99 = failure)."""
    def _set(value):
        monkeypatch.setattr(law_crud, "rng", lambda: FixedRng(value))
    return _set


def _wanted_alpha(f, val=150, region=R_OST, location=L_POST, origin=L_MARKET):
    set_wanted(f, ALPHA, region, val)
    return make_encounter(f, location_id=location, from_location_id=origin)


def _choose(api, enc_id, choice, request_id=None, cid=ALPHA, user=USER_ALPHA):
    as_user(user)
    return api.post(f"/characters/{cid}/law/encounter/{enc_id}/choice",
                    json={"choice": choice, "request_id": request_id or rid()})


def _busy(f, character_id, battle_id=900):
    exec_(f, "INSERT INTO battles (id, status) VALUES (:b, 'in_progress')", b=battle_id)
    exec_(f, "INSERT INTO battle_participants (battle_id, character_id) VALUES (:b, :c)", b=battle_id,
          c=character_id)


# =============================================================================================== fine

def test_fine_pays_region_treasury_with_tax_and_clears_wanted(api, law_world):
    enc_id = _wanted_alpha(law_world)
    set_gold(law_world, ALPHA, 500)
    resp = _choose(api, enc_id, "fine")
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "fined"
    assert gold(law_world, ALPHA) == 350
    assert treasury(law_world, "region_treasury", R_OST) == 135                        # 90 %
    assert treasury(law_world, "country_treasury", 1) == 15                            # 10 % tax
    assert rows(law_world, "SELECT op_type, idempotency_key FROM econ_operations") == [("law_fine",
                                                                                       f"law_fine:{enc_id}")]
    assert wanted(law_world, ALPHA, R_OST) == 0
    enc = encounter(law_world, enc_id)
    assert enc.status == "fined" and enc.resolved_at is not None
    assert char_row(law_world, ALPHA).law_encounter_id is None


def test_fine_insufficient_gold_keeps_encounter_pending(api, law_world):
    enc_id = _wanted_alpha(law_world)
    set_gold(law_world, ALPHA, 100)
    resp = _choose(api, enc_id, "fine")
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("Недостаточно") and "штрафа" in resp.json()["detail"]
    assert gold(law_world, ALPHA) == 100 and encounter(law_world, enc_id).status == "pending"
    assert char_row(law_world, ALPHA).law_encounter_id == enc_id
    assert wanted(law_world, ALPHA, R_OST) == 150


def test_fine_replay_same_request_id_charges_once(api, law_world):
    enc_id = _wanted_alpha(law_world)
    set_gold(law_world, ALPHA, 500)
    request_id = rid()
    assert _choose(api, enc_id, "fine", request_id).status_code == 200
    again = _choose(api, enc_id, "fine", request_id)
    assert again.status_code == 200 and again.json()["result"] == "fined"
    assert gold(law_world, ALPHA) == 350
    assert q(law_world, "SELECT COUNT(*) FROM econ_operations") == 1
    # a new request on the closed encounter: 409
    assert _choose(api, enc_id, "fine").status_code == 409


def test_outlaw_cannot_pay_a_fine(api, law_world):
    set_value(law_world, ALPHA, R_OST, -700)
    enc_id = make_encounter(law_world)
    resp = _choose(api, enc_id, "fine")
    assert resp.status_code == 400 and resp.json()["detail"] == "Этот вариант сейчас недоступен"
    assert _choose(api, enc_id, "flee").status_code == 400


# =============================================================================================== surrender

def test_surrender_moves_to_jail_and_starts_the_term(api, law_world, stub_law_notify_send):
    enc_id = _wanted_alpha(law_world)
    resp = _choose(api, enc_id, "surrender")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["result"] == "jailed" and data["jail"]["bail_price"] == 300
    assert data["jail"]["location_name"] == "Темница" and data["jail"]["can_escape_at"] is None
    law_world.prepare_move.assert_awaited_once()
    assert law_world.prepare_move.await_args.args[1:] == (ALPHA, L_POST, "jail")
    row = char_row(law_world, ALPHA)
    assert row.current_location_id == L_JAIL and row.law_encounter_id is None and row.jail_region_id == R_OST
    assert timedelta(hours=11, minutes=59) <= row.jailed_until - now() <= timedelta(hours=12)
    assert wanted(law_world, ALPHA, R_OST) == 0
    term = rows(law_world, "SELECT status, location_id, encounter_id, fine_base, bail_price, level_code "
                           "FROM law_jail_terms")
    assert term == [("serving", L_JAIL, enc_id, 150, 300, "offender")]
    assert encounter(law_world, enc_id).status == "jailed"
    assert q(law_world, "SELECT COUNT(*) FROM character_logs WHERE character_id = :c AND event_type = 'jail'",
             c=ALPHA) == 1
    assert any(p["ws_type"] == "law_jailed" for p in law_payloads(stub_law_notify_send))


def test_surrender_move_failure_is_502_and_nothing_changes(api, law_world):
    enc_id = _wanted_alpha(law_world)
    law_world.prepare_move.side_effect = HTTPException(status_code=502, detail="locations down")
    resp = _choose(api, enc_id, "surrender")
    assert resp.status_code == 502 and resp.json()["detail"] == "Не удалось доставить в тюрьму, попробуйте ещё раз"
    assert encounter(law_world, enc_id).status == "pending"
    row = char_row(law_world, ALPHA)
    assert row.current_location_id == L_POST and row.jailed_until is None and row.law_encounter_id == enc_id
    assert q(law_world, "SELECT COUNT(*) FROM law_jail_terms") == 0


def test_surrender_when_jail_location_is_the_current_one_skips_the_move(api, law_world):
    exec_(law_world, "UPDATE Regions SET jail_location_id = :l WHERE id = :r", l=L_POST, r=R_OST)
    enc_id = _wanted_alpha(law_world)
    assert _choose(api, enc_id, "surrender").json()["result"] == "jailed"
    law_world.prepare_move.assert_not_awaited()
    assert char_row(law_world, ALPHA).current_location_id == L_POST


def test_surrender_unavailable_without_jail(api, law_world):
    enc_id = _wanted_alpha(law_world, region=R_PASHNI, location=L_FARM)
    resp = _choose(api, enc_id, "surrender")
    assert resp.status_code == 400


def test_surrender_after_jail_was_removed_is_409(api, law_world):
    enc_id = _wanted_alpha(law_world)
    exec_(law_world, "UPDATE Regions SET jail_location_id = NULL WHERE id = :r", r=R_OST)
    resp = _choose(api, enc_id, "surrender")
    assert resp.status_code == 409 and resp.json()["detail"] == "В этом крае больше нет тюрьмы"
    as_user(USER_ALPHA)
    options = api.get(f"/characters/{ALPHA}/law/encounter").json()["encounter"]["options"]
    assert options == ["fine", "flee", "fight"]                                        # recomputed


# =============================================================================================== flee

def test_flee_success_goes_back_to_origin_without_a_new_stop(api, law_world, roll, battle):
    """A7: back to where they came from (guard 52 stands there and the character is still wanted: no stop),
    wanted unchanged, and the guards of the fled location leave them alone for 1 hour."""
    enc_id = _wanted_alpha(law_world)
    roll(0.0)
    resp = _choose(api, enc_id, "flee")
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "fled" and "Рынок" in resp.json()["message"]
    assert law_world.prepare_move.await_args.args[1:] == (ALPHA, L_POST, "law_flee")
    row = char_row(law_world, ALPHA)
    assert row.current_location_id == L_MARKET and row.law_encounter_id is None
    assert q(law_world, "SELECT COUNT(*) FROM law_encounters") == 1                    # nothing at the origin
    assert wanted(law_world, ALPHA, R_OST) == 150
    enc = encounter(law_world, enc_id)
    assert enc.status == "fled"
    assert timedelta(minutes=59) <= enc.cooldown_until - now() <= timedelta(hours=1)
    log = rows(law_world, "SELECT action, chance_pct, roll_pct FROM law_log WHERE action = 'flee_ok'")
    assert len(log) == 1 and float(log[0][1]) == 20.0 and float(log[0][2]) == 0.0
    assert q(law_world, "SELECT COUNT(*) FROM character_logs WHERE event_type = 'law_flee'") == 1
    battle.assert_not_awaited()
    # walking back into the guarded location inside the hour: not stopped
    resp = api.put(f"/characters/internal/{ALPHA}/update_location", json={"new_location_id": L_POST},
                   headers=INTERNAL)
    assert resp.status_code == 200 and resp.json()["law_encounter"] is None


def test_flee_success_without_origin_stays(api, law_world, roll):
    enc_id = _wanted_alpha(law_world, origin=None)
    roll(0.0)
    resp = _choose(api, enc_id, "flee")
    assert resp.json()["result"] == "fled" and resp.json()["message"] == "Вам удалось скрыться от стражи"
    law_world.prepare_move.assert_not_awaited()
    assert char_row(law_world, ALPHA).current_location_id == L_POST


def test_flee_success_with_unknown_origin_stays(api, law_world, roll):
    enc_id = _wanted_alpha(law_world, origin=98765)                                    # deleted / invalid
    roll(0.0)
    assert _choose(api, enc_id, "flee").json()["result"] == "fled"
    law_world.prepare_move.assert_not_awaited()
    assert char_row(law_world, ALPHA).current_location_id == L_POST


def test_flee_success_move_back_failure_stays(api, law_world, roll):
    enc_id = _wanted_alpha(law_world)
    law_world.prepare_move.side_effect = HTTPException(status_code=502, detail="down")
    roll(0.0)
    resp = _choose(api, enc_id, "flee")
    assert resp.status_code == 200 and resp.json()["result"] == "fled"
    assert char_row(law_world, ALPHA).current_location_id == L_POST
    assert encounter(law_world, enc_id).status == "fled"


def test_flee_failure_starts_the_fight(api, law_world, roll, battle):
    enc_id = _wanted_alpha(law_world)
    exec_(law_world, "UPDATE character_attributes SET current_health = 7, current_mana = 1 WHERE character_id = :g",
          g=GUARD_POST)
    roll(0.99)
    resp = _choose(api, enc_id, "flee")
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "fight" and resp.json()["battle_id"] == BATTLE_ID
    assert resp.json()["message"] == "Бежать не удалось — стражник вступает в бой"
    battle.assert_awaited_once_with(enc_id, ALPHA, GUARD_POST)
    enc = encounter(law_world, enc_id)
    assert (enc.status, enc.battle_id, enc.flee_used) == ("fighting", BATTLE_ID, True)
    assert enc.fight_started_at is not None
    assert rows(law_world, "SELECT current_health, current_mana FROM character_attributes WHERE character_id = :g",
                g=GUARD_POST) == [(100, 50)]                                            # healed before the fight
    assert log_has(law_world, "flee_fail") and log_has(law_world, "fight")
    assert char_row(law_world, ALPHA).law_encounter_id == enc_id                        # still locked


def log_has(f, action):
    return q(f, "SELECT COUNT(*) FROM law_log WHERE action = :a", a=action) >= 1


def test_flee_failure_with_busy_guard_is_blocked(api, law_world, roll, battle):
    enc_id = _wanted_alpha(law_world)
    _busy(law_world, GUARD_POST)
    roll(0.99)
    resp = _choose(api, enc_id, "flee")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["result"] == "flee_failed_blocked" and data["message"] == "Бежать не удалось — стража преградила путь"
    assert data["encounter"]["options"] == ["fine", "surrender", "fight"]               # flee used
    enc = encounter(law_world, enc_id)
    assert enc.status == "pending" and enc.flee_used is True
    battle.assert_not_awaited()
    assert _choose(api, enc_id, "flee").status_code == 400                              # once per encounter


# =============================================================================================== fight

def test_fight_busy_guard_409(api, law_world, battle):
    enc_id = _wanted_alpha(law_world)
    _busy(law_world, GUARD_POST)
    resp = _choose(api, enc_id, "fight")
    assert resp.status_code == 409 and resp.json()["detail"] == "Стражник сейчас занят — попробуйте чуть позже"
    assert encounter(law_world, enc_id).status == "pending"


def test_fight_guard_gone_releases_the_character(api, law_world, battle):
    enc_id = _wanted_alpha(law_world)
    exec_(law_world, "UPDATE characters SET unconscious_until = :t WHERE id = :g",
          t=now() + timedelta(hours=3), g=GUARD_POST)
    resp = _choose(api, enc_id, "fight")
    assert resp.status_code == 200 and resp.json()["result"] == "guard_gone"
    assert encounter(law_world, enc_id).status == "guard_gone"
    assert char_row(law_world, ALPHA).law_encounter_id is None
    assert wanted(law_world, ALPHA, R_OST) == 150
    battle.assert_not_awaited()


def test_fight_battle_service_failure_reverts_to_pending(api, law_world, monkeypatch):
    enc_id = _wanted_alpha(law_world)
    monkeypatch.setattr(battle_client, "create_guard_battle",
                        AsyncMock(side_effect=battle_client.BattleServiceError("down")))
    resp = _choose(api, enc_id, "fight")
    assert resp.status_code == 502 and resp.json()["detail"] == "Не удалось начать бой со стражей"
    enc = encounter(law_world, enc_id)
    assert (enc.status, enc.battle_id, enc.fight_started_at) == ("pending", None, None)
    assert char_row(law_world, ALPHA).law_encounter_id == enc_id


def test_fight_battle_service_409_detail_passes_through(api, law_world, monkeypatch):
    enc_id = _wanted_alpha(law_world)
    monkeypatch.setattr(battle_client, "create_guard_battle", AsyncMock(
        side_effect=battle_client.BattleServiceError("refused", 409, "Стражник уже в бою")))
    resp = _choose(api, enc_id, "fight")
    assert resp.status_code == 409 and resp.json()["detail"] == "Стражник уже в бою"
    assert encounter(law_world, enc_id).status == "pending"


def test_fight_prefers_a_free_second_guard(api, law_world, battle):
    exec_(law_world, "UPDATE characters SET current_location_id = :l WHERE id = :g", l=L_POST, g=GUARD_FARM)
    enc_id = _wanted_alpha(law_world)
    _busy(law_world, GUARD_POST)
    resp = _choose(api, enc_id, "fight")
    assert resp.json()["result"] == "fight"
    battle.assert_awaited_once_with(enc_id, ALPHA, GUARD_FARM)
    assert encounter(law_world, enc_id).guard_npc_id == GUARD_FARM


def test_fight_replay_does_not_start_a_second_battle(api, law_world, battle):
    enc_id = _wanted_alpha(law_world)
    request_id = rid()
    assert _choose(api, enc_id, "fight", request_id).json()["result"] == "fight"
    again = _choose(api, enc_id, "fight", request_id)
    assert again.status_code == 200 and again.json() == {"result": "fight", "message": "Бой со стражей начался",
                                                         "battle_id": BATTLE_ID, "jail": None, "encounter": None}
    assert battle.await_count == 1


def test_replay_after_reverted_fight_is_not_a_blocked_flee(api, law_world, monkeypatch):
    """A 502 reverts the fight to «pending»: replaying that request_id offers the choice again with a neutral
    message — never «бежать не удалось» (the player did not flee)."""
    enc_id = _wanted_alpha(law_world)
    monkeypatch.setattr(battle_client, "create_guard_battle",
                        AsyncMock(side_effect=battle_client.BattleServiceError("down")))
    request_id = rid()
    assert _choose(api, enc_id, "fight", request_id).status_code == 502
    again = _choose(api, enc_id, "fight", request_id)
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["result"] == "flee_failed_blocked" and body["encounter"]["id"] == enc_id
    assert body["message"] == "Стража ждёт вашего решения" and "Бежать" not in body["message"]


# =============================================================================================== security

def test_choice_owner_only_and_validation(api, law_world, battle):
    enc_id = _wanted_alpha(law_world)
    assert _choose(api, enc_id, "fight", user=USER_BETA).status_code == 403            # another user's character
    assert _choose(api, enc_id, "fight", cid=BETA, user=USER_BETA).status_code == 404  # not this char's encounter
    assert _choose(api, enc_id, "fight", cid=99999).status_code == 404
    as_user(USER_ALPHA)
    url = f"/characters/{ALPHA}/law/encounter/{enc_id}/choice"
    assert api.post(url, json={"choice": "bribe", "request_id": rid()}).status_code == 422
    assert api.post(url, json={"choice": "fine' OR 1=1 --", "request_id": rid()}).status_code == 422
    assert api.post(url, json={"choice": "fine", "request_id": "not-a-uuid"}).status_code == 422
    assert api.post(url, json={"choice": "fine"}).status_code == 422
    assert encounter(law_world, enc_id).status == "pending"
    battle.assert_not_awaited()


def test_player_encounter_view_is_owner_only_and_has_no_numbers(api, law_world):
    enc_id = _wanted_alpha(law_world, val=444)
    as_user(USER_BETA)
    assert api.get(f"/characters/{ALPHA}/law/encounter").status_code == 403
    as_user(USER_ALPHA)
    resp = api.get(f"/characters/{ALPHA}/law/encounter")
    assert resp.status_code == 200
    data = resp.json()["encounter"]
    assert data["id"] == enc_id and "444" not in resp.text and "wanted_value" not in data
    assert api.get("/characters/99999/law/encounter").status_code == 404


# =============================================================================================== battle result

def _fighting(api, f, battle, **kw):
    enc_id = _wanted_alpha(f, **kw)
    assert _choose(api, enc_id, "fight").json()["result"] == "fight"
    return enc_id


def _result(api, enc_id, winner_team=None, aborted=False, battle_id=BATTLE_ID, headers=INTERNAL):
    return api.post("/characters/internal/law/battle-result",
                    json={"battle_id": battle_id, "law_encounter_id": enc_id, "winner_team": winner_team,
                          "aborted": aborted}, headers=headers)


def test_battle_won_releases_and_is_idempotent(api, law_world, battle):
    enc_id = _fighting(api, law_world, battle)
    resp = _result(api, enc_id, winner_team=1)
    assert resp.status_code == 200 and resp.json() == {"ok": True, "status": "won", "duplicate": False}
    assert char_row(law_world, ALPHA).law_encounter_id is None
    assert encounter(law_world, enc_id).status == "won"
    assert _result(api, enc_id, winner_team=1).json() == {"ok": True, "status": "won", "duplicate": True}
    assert _result(api, enc_id, winner_team=2).json()["duplicate"] is True             # no late jailing
    assert char_row(law_world, ALPHA).jailed_until is None


def test_battle_lost_with_jail_jails(api, law_world, battle):
    enc_id = _fighting(api, law_world, battle)
    resp = _result(api, enc_id, winner_team=2)
    assert resp.json() == {"ok": True, "status": "jailed", "duplicate": False}
    row = char_row(law_world, ALPHA)
    assert row.current_location_id == L_JAIL and row.jailed_until is not None and row.law_encounter_id is None
    assert wanted(law_world, ALPHA, R_OST) == 0
    assert q(law_world, "SELECT COUNT(*) FROM law_jail_terms WHERE status = 'serving'") == 1
    assert _result(api, enc_id, winner_team=2).json()["duplicate"] is True
    assert q(law_world, "SELECT COUNT(*) FROM law_jail_terms") == 1


def test_battle_lost_timeout_without_winner_is_a_loss(api, law_world, battle):
    enc_id = _fighting(api, law_world, battle)
    assert _result(api, enc_id, winner_team=None).json()["status"] == "jailed"


def test_battle_lost_without_jail_forced_fine_full(api, law_world, battle):
    set_gold(law_world, ALPHA, 500)
    enc_id = _fighting(api, law_world, battle, region=R_PASHNI, location=L_FARM)
    resp = _result(api, enc_id, winner_team=2)
    assert resp.json()["status"] == "auto_fined"
    assert gold(law_world, ALPHA) == 350 and wanted(law_world, ALPHA, R_PASHNI) == 0
    assert treasury(law_world, "region_treasury", R_PASHNI) == 135
    assert rows(law_world, "SELECT idempotency_key FROM econ_operations") == [(f"law_fine_forced:{enc_id}",)]
    assert char_row(law_world, ALPHA).law_encounter_id is None


def test_battle_lost_without_jail_partial_fine_keeps_wanted(api, law_world, battle):
    """§3.14 A3: take the gold up to the fine; a partial payment keeps the wanted."""
    set_gold(law_world, ALPHA, 60)
    enc_id = _fighting(api, law_world, battle, region=R_PASHNI, location=L_FARM)
    assert _result(api, enc_id, winner_team=2).json()["status"] == "auto_fined"
    assert gold(law_world, ALPHA) == 0 and wanted(law_world, ALPHA, R_PASHNI) == 150
    assert encounter(law_world, enc_id).status == "auto_fined"
    assert q(law_world, "SELECT amount FROM law_log WHERE action = 'fight_lost'") == 60


def test_battle_lost_without_jail_and_no_gold(api, law_world, battle):
    enc_id = _fighting(api, law_world, battle, region=R_PASHNI, location=L_FARM)
    assert _result(api, enc_id, winner_team=2).json()["status"] == "auto_fined"
    assert q(law_world, "SELECT COUNT(*) FROM econ_operations") == 0
    assert wanted(law_world, ALPHA, R_PASHNI) == 150


def test_battle_aborted_offers_the_choice_again(api, law_world, battle):
    enc_id = _fighting(api, law_world, battle)
    resp = _result(api, enc_id, aborted=True)
    assert resp.json() == {"ok": True, "status": "pending", "duplicate": False}
    enc = encounter(law_world, enc_id)
    assert (enc.status, enc.battle_id, enc.fight_started_at) == ("pending", None, None)
    assert char_row(law_world, ALPHA).law_encounter_id == enc_id


def test_battle_result_errors(api, law_world, battle):
    enc_id = _fighting(api, law_world, battle)
    assert _result(api, enc_id, winner_team=2, battle_id=999).status_code == 409
    assert _result(api, 99999, winner_team=2).status_code == 404
    assert _result(api, enc_id, winner_team=2, headers={}).status_code in (401, 403)
    assert _result(api, enc_id, winner_team=2, headers={"X-Internal-Token": "wrong"}).status_code in (401, 403)
    assert encounter(law_world, enc_id).status == "fighting"


def test_battle_result_on_pending_encounter_is_a_duplicate(api, law_world):
    enc_id = _wanted_alpha(law_world)
    assert _result(api, enc_id, winner_team=2).json() == {"ok": True, "status": "pending", "duplicate": True}
    assert char_row(law_world, ALPHA).jailed_until is None
