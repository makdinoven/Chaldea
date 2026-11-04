"""FEAT-198 QA (task 9): jail — escape, bail (self + at a banker), prisoners list, player reads.

* escape (RNG mocked): failure +50 % of the remaining term capped at 168 h (A4) on the term AND the lock column,
  cooldown 409 with the next time, success -> escaped + wanted >= heavy floor (A5), request_id replay;
* self-bail and bail by another player at a banker of ANY region (decision 6): ownership, banker at the payer's
  location, locked payer 409, one bail per term, money into the JAIL region treasury with tax;
* prisoners list: LIKE wildcards escaped, page_size <= 50, q <= 50, SQL-injection strings harmless;
* player reads: private (owner / staff 403 for others), levels only — never raw wanted numbers.
"""

import re
from datetime import datetime, timedelta

import pytest

import law_crud
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BANKER_DUNY, BANKER_MARKET, BETA, GAMMA, L_JAIL, L_MARKET, L_OASIS, MERCHANT, R_DUNY, R_OST, R_PASHNI,
    USER_ALPHA, USER_BETA, USER_GAMMA, FixedRng, api, as_admin, as_user, char_row, exec_, gold, jail_character,
    law_payloads, law_world, make_encounter, now, q, rep_world, rid, rows, set_gold, set_value, set_wanted,
    treasury, wanted,
)


@pytest.fixture
def roll(monkeypatch):
    def _set(value):
        monkeypatch.setattr(law_crud, "rng", lambda: FixedRng(value))
    return _set


def _escape(api, cid=ALPHA, request_id=None, user=USER_ALPHA):
    as_user(user)
    return api.post(f"/characters/{cid}/law/jail/escape", json={"request_id": request_id or rid()})


def _term(f, term_id):
    return rows(f, "SELECT status, until, escape_attempts, next_escape_at FROM law_jail_terms WHERE id = :t",
                t=term_id)[0]


def _dt(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


# =============================================================================================== escape

def test_escape_failure_extends_by_half_and_sets_cooldown(api, law_world, roll):
    term_id = jail_character(law_world, hours=10)
    roll(0.99)
    resp = _escape(api)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is False and data["message"].startswith("Побег не удался")
    # A8: a relative duration (14 h 59 min .. 15 h), never a clock time / «МСК»
    assert data["message"].startswith("Побег не удался — срок увеличен, осталось 1")
    assert "МСК" not in data["message"] and not re.search(r"\d\d:\d\d", data["message"])
    status, until, attempts, next_at = _term(law_world, term_id)
    assert status == "serving" and attempts == 1
    assert timedelta(hours=14, minutes=59) <= _dt(until) - now() <= timedelta(hours=15)
    assert timedelta(hours=5, minutes=59) <= _dt(next_at) - now() <= timedelta(hours=6)
    assert char_row(law_world, ALPHA).jailed_until == _dt(until)                       # lock column follows
    assert data["jail"]["escape_attempts"] == 1 and data["jail"]["can_escape_at"] is not None
    log = rows(law_world, "SELECT chance_pct, roll_pct FROM law_log WHERE action = 'escape_fail'")
    assert float(log[0][0]) == 5.0 and float(log[0][1]) == 99.0


def test_escape_failure_capped_at_168_hours(api, law_world, roll):
    term_id = jail_character(law_world, hours=150)
    roll(0.99)
    assert _escape(api).json()["success"] is False
    until = _dt(_term(law_world, term_id)[1])
    assert timedelta(hours=167, minutes=59) <= until - now() <= timedelta(hours=168)


def test_escape_cooldown_409(api, law_world, roll):
    jail_character(law_world, next_escape_at=now() + timedelta(hours=3))
    roll(0.0)
    resp = _escape(api)
    assert resp.status_code == 409 and resp.json()["detail"].startswith("Следующая попытка побега — через ")
    assert resp.json()["detail"] in ("Следующая попытка побега — через 3 ч",
                                     "Следующая попытка побега — через 2 ч 59 мин")
    assert char_row(law_world, ALPHA).jailed_until > now()


def test_escape_success_frees_and_sets_heavy_wanted(api, law_world, roll, stub_law_notify_send):
    term_id = jail_character(law_world, hours=10)
    set_wanted(law_world, ALPHA, R_OST, 0)
    roll(0.0)
    resp = _escape(api)
    assert resp.status_code == 200 and resp.json()["success"] is True and resp.json()["jail"] is None
    status, until, attempts, _next = _term(law_world, term_id)
    assert status == "escaped" and attempts == 1
    row = char_row(law_world, ALPHA)
    assert row.jailed_until <= now() and row.jail_region_id is None
    assert wanted(law_world, ALPHA, R_OST) == 600                                       # heavy floor (A5)
    assert q(law_world, "SELECT decay_at FROM character_wanted WHERE character_id = :c AND region_id = :r",
             c=ALPHA, r=R_OST) is not None                                              # decays normally
    assert rows(law_world, "SELECT crime_type, event_key FROM law_crimes") == [
        ("jail_escape", f"crime:escape:{term_id}:1")]
    assert any(p["ws_type"] == "law_released" for p in law_payloads(stub_law_notify_send))
    assert _escape(api).status_code == 409                                              # not jailed any more


def test_escape_double_click_is_a_no_op(api, law_world, roll):
    term_id = jail_character(law_world, hours=10)
    roll(0.99)
    request_id = rid()
    first = _escape(api, request_id=request_id)
    second = _escape(api, request_id=request_id)
    assert first.status_code == second.status_code == 200
    assert second.json()["success"] is False
    assert _term(law_world, term_id)[2] == 1                                            # one attempt only


def test_escape_owner_only(api, law_world, roll):
    jail_character(law_world)
    roll(0.0)
    assert _escape(api, user=USER_BETA).status_code == 403
    assert _escape(api, cid=99999).status_code == 404
    as_user(USER_ALPHA)
    assert api.post(f"/characters/{ALPHA}/law/jail/escape", json={"request_id": "1; DROP TABLE x"}).status_code == 422
    assert char_row(law_world, ALPHA).jailed_until > now()


def test_escape_not_jailed_409(api, law_world):
    assert _escape(api).status_code == 409


# =============================================================================================== self-bail

def _self_bail(api, cid=ALPHA, request_id=None, user=USER_ALPHA):
    as_user(user)
    return api.post(f"/characters/{cid}/law/jail/bail", json={"request_id": request_id or rid()})


def test_self_bail_pays_jail_region_and_frees(api, law_world):
    term_id = jail_character(law_world)
    set_gold(law_world, ALPHA, 1000)
    resp = _self_bail(api)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"message": "Залог внесён — вы свободны", "jail": None}
    assert gold(law_world, ALPHA) == 700
    assert treasury(law_world, "region_treasury", R_OST) == 270
    assert treasury(law_world, "country_treasury", 1) == 30
    assert rows(law_world, "SELECT op_type, idempotency_key FROM econ_operations") == [
        ("law_bail", f"law_bail:{term_id}")]
    assert _term(law_world, term_id)[0] == "bailed"
    assert q(law_world, "SELECT bailed_by_character_id FROM law_jail_terms") == ALPHA
    assert char_row(law_world, ALPHA).jailed_until <= now()


def test_self_bail_insufficient_and_replay(api, law_world):
    jail_character(law_world)
    set_gold(law_world, ALPHA, 100)
    resp = _self_bail(api)
    assert resp.status_code == 400 and "залога" in resp.json()["detail"]
    set_gold(law_world, ALPHA, 1000)
    request_id = rid()
    assert _self_bail(api, request_id=request_id).status_code == 200
    assert _self_bail(api, request_id=request_id).status_code == 200                   # replay: no second charge
    assert gold(law_world, ALPHA) == 700
    assert _self_bail(api).status_code == 409                                           # not jailed now


def test_self_bail_owner_only(api, law_world):
    jail_character(law_world)
    set_gold(law_world, BETA, 1000)
    assert _self_bail(api, user=USER_BETA).status_code == 403
    assert gold(law_world, ALPHA) == 0 and char_row(law_world, ALPHA).jailed_until > now()


# =============================================================================================== bail by another player

def _bail(api, payer=BETA, banker=BANKER_MARKET, prisoner=ALPHA, user=USER_BETA, request_id=None):
    as_user(user)
    return api.post("/characters/law/bail", json={"payer_character_id": payer, "banker_npc_id": banker,
                                                   "prisoner_character_id": prisoner,
                                                   "request_id": request_id or rid()})


def test_bail_by_another_player_at_a_banker(api, law_world, stub_law_notify_send):
    term_id = jail_character(law_world)
    set_gold(law_world, BETA, 1000)
    resp = _bail(api)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"message": "Залог за «Альфа» внесён — узник свободен", "paid": 300}
    assert gold(law_world, BETA) == 700 and gold(law_world, ALPHA) == 0
    assert treasury(law_world, "region_treasury", R_OST) == 270                        # the JAIL region
    assert _term(law_world, term_id)[0] == "bailed"
    assert q(law_world, "SELECT bailed_by_character_id FROM law_jail_terms") == BETA
    assert char_row(law_world, ALPHA).jailed_until <= now()
    msgs = [p for p in law_payloads(stub_law_notify_send) if p["target_value"] == USER_ALPHA]
    assert msgs and msgs[0]["message"] == "За вас внесли залог: Бета. Вы свободны"


def test_bail_from_a_banker_in_another_region(api, law_world):
    """Decision 6: any bank of any region; the money still goes to the jail region (Ост)."""
    jail_character(law_world)
    set_gold(law_world, GAMMA, 1000)                                                    # Гамма @200 (Дюны)
    resp = _bail(api, payer=GAMMA, banker=BANKER_DUNY, user=USER_GAMMA)
    assert resp.status_code == 200, resp.text
    assert treasury(law_world, "region_treasury", R_OST) == 270
    assert treasury(law_world, "region_treasury", R_DUNY) == 0


def test_bail_checks(api, law_world):
    jail_character(law_world)
    set_gold(law_world, BETA, 1000)
    assert _bail(api, user=USER_GAMMA).status_code == 403                              # payer not owned
    assert _bail(api, banker=BANKER_DUNY).status_code == 400                           # banker elsewhere
    assert _bail(api, banker=MERCHANT).status_code == 404                              # not a banker
    assert _bail(api, banker=99999).status_code == 404
    assert _bail(api, prisoner=GAMMA).status_code == 409                               # not jailed
    assert _bail(api, prisoner=MERCHANT).status_code == 404                            # an NPC
    exec_(law_world, "UPDATE characters SET npc_status = 'dead' WHERE id = :b", b=BANKER_MARKET)
    assert _bail(api).status_code == 409
    exec_(law_world, "UPDATE characters SET npc_status = 'alive' WHERE id = :b", b=BANKER_MARKET)
    set_gold(law_world, BETA, 10)
    assert _bail(api).status_code == 400
    assert gold(law_world, BETA) == 10 and char_row(law_world, ALPHA).jailed_until > now()


def test_bail_payer_locked_409(api, law_world):
    jail_character(law_world)
    set_gold(law_world, BETA, 1000)
    set_wanted(law_world, BETA, R_OST, 150)
    exec_(law_world, "UPDATE characters SET law_encounter_id = 1 WHERE id = :c", c=BETA)
    resp = _bail(api)
    assert resp.status_code == 409 and "стражей" in resp.json()["detail"]
    assert gold(law_world, BETA) == 1000


def test_prisoner_cannot_pay_own_bail_through_a_banker(api, law_world):
    jail_character(law_world)
    set_gold(law_world, ALPHA, 1000)
    resp = _bail(api, payer=ALPHA, prisoner=ALPHA, user=USER_ALPHA)
    assert resp.status_code == 409 and resp.json()["detail"].startswith("Персонаж в тюрьме")
    assert gold(law_world, ALPHA) == 1000


def test_bail_respects_the_banker_reputation_gate(api, law_world):
    """The banker's FEAT-197 NPC gate applies exactly as for every bank write."""
    jail_character(law_world)
    set_gold(law_world, BETA, 1000)
    exec_(law_world, "UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :b", b=BANKER_MARKET)
    resp = _bail(api)
    assert resp.status_code == 403 and resp.json()["detail"].startswith("Нужна репутация")
    assert gold(law_world, BETA) == 1000
    set_value(law_world, BETA, R_OST, 150)
    assert _bail(api).status_code == 200


def test_one_bail_per_term(api, law_world):
    jail_character(law_world)
    set_gold(law_world, BETA, 1000)
    exec_(law_world, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_OASIS, c=GAMMA)
    set_gold(law_world, GAMMA, 1000)
    request_id = rid()
    assert _bail(api, request_id=request_id).status_code == 200
    replay = _bail(api, request_id=request_id)
    assert replay.status_code == 200 and replay.json()["paid"] == 300                   # same request: no-op
    second = _bail(api, payer=GAMMA, banker=BANKER_DUNY, user=USER_GAMMA)
    assert second.status_code == 409 and second.json()["detail"] == "Залог уже внесён"
    assert gold(law_world, BETA) == 700 and gold(law_world, GAMMA) == 1000
    assert q(law_world, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'law_bail'") == 1


def test_bail_validation(api, law_world):
    as_user(USER_BETA)
    body = {"payer_character_id": 0, "banker_npc_id": BANKER_MARKET, "prisoner_character_id": ALPHA,
            "request_id": rid()}
    assert api.post("/characters/law/bail", json=body).status_code == 422
    body.update(payer_character_id=BETA, request_id="x")
    assert api.post("/characters/law/bail", json=body).status_code == 422


# =============================================================================================== prisoners

def _prisoners(api, **params):
    as_user(USER_GAMMA)
    return api.get("/characters/law/prisoners", params=params)


def test_prisoners_list(api, law_world):
    jail_character(law_world, ALPHA, hours=5)
    jail_character(law_world, BETA, hours=-1)                                           # served lazily: not listed
    resp = _prisoners(api)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert (item["character_id"], item["name"], item["region_name"], item["location_name"], item["bail_price"]) == \
        (ALPHA, "Альфа", "Ост", "Темница", 300)
    assert set(item) == {"character_id", "name", "avatar", "region_name", "location_name", "until", "bail_price"}


def test_prisoners_search_escapes_like_wildcards(api, law_world):
    jail_character(law_world, ALPHA)
    jail_character(law_world, BETA)
    assert _prisoners(api, q="Аль").json()["total"] == 1
    assert _prisoners(api, q="%").json()["total"] == 0                                  # wildcard is literal
    assert _prisoners(api, q="_").json()["total"] == 0
    exec_(law_world, "UPDATE characters SET name = 'Бе%та' WHERE id = :c", c=BETA)
    assert [i["character_id"] for i in _prisoners(api, q="%").json()["items"]] == [BETA]
    for evil in ("'; DROP TABLE characters; --", "\" OR 1=1 --", "\\"):
        resp = _prisoners(api, q=evil)
        assert resp.status_code == 200 and resp.json()["total"] == 0
    assert q(law_world, "SELECT COUNT(*) FROM characters") > 0


def test_prisoners_paging_and_limits(api, law_world):
    jail_character(law_world, ALPHA, hours=1)
    jail_character(law_world, BETA, hours=2)
    page = _prisoners(api, page=2, page_size=1).json()
    assert page["total"] == 2 and [i["character_id"] for i in page["items"]] == [BETA]
    assert _prisoners(api, page_size=51).status_code == 422
    assert _prisoners(api, page_size=0).status_code == 422
    assert _prisoners(api, page=0).status_code == 422
    assert _prisoners(api, q="x" * 51).status_code == 422


# =============================================================================================== player reads

def test_player_law_state_levels_only(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 345)
    set_wanted(law_world, ALPHA, R_PASHNI, 100, decay_at=now() - timedelta(days=3))   # decayed to 0: hidden
    as_user(USER_ALPHA)
    resp = api.get(f"/characters/{ALPHA}/law")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["wanted"] == [{"region_id": R_OST, "region_name": "Ост", "level_code": "criminal",
                               "level_name": "Преступник", "fine": 400, "jail_hours": 24, "decaying": True}]
    assert data["encounter"] is None and data["jail"] is None
    assert "345" not in resp.text


def test_player_law_state_with_jail_and_privacy(api, law_world):
    jail_character(law_world)
    as_user(USER_BETA)
    assert api.get(f"/characters/{ALPHA}/law").status_code == 403
    assert api.get(f"/characters/{ALPHA}/law/jail").status_code == 403
    as_user(USER_BETA, "editor", ["characters:read"])
    assert api.get(f"/characters/{ALPHA}/law").status_code == 403                      # editor is not staff here
    as_admin()
    assert api.get(f"/characters/{ALPHA}/law").status_code == 200
    as_user(USER_ALPHA)
    jail = api.get(f"/characters/{ALPHA}/law/jail").json()["jail"]
    assert jail["bail_price"] == 300 and jail["escape_chance_pct"] == 5.0
    assert jail["region_name"] == "Ост" and jail["location_name"] == "Темница"
    assert "status" not in jail and "level_code" not in jail                           # staff-only fields
    assert api.get("/characters/99999/law").status_code == 404


def test_encounter_shown_in_player_state(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    as_user(USER_ALPHA)
    data = api.get(f"/characters/{ALPHA}/law").json()
    assert data["encounter"]["id"] == enc_id and data["encounter"]["options"][0] == "fine"
    assert "wanted_value" not in data["encounter"]
