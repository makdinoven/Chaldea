"""FEAT-207 QA (task #9): closed faction territories — features/FEAT-207 §3.3, §3.4, §3.9, §3.11.

The pure access decision / dungeon texts; the authoritative move gate (``update_location`` 409) and the teleport gate
(403 before any charge, ``locked_reason``); the eject (target order neighbour -> HQ -> station, busy skip, postponed on a
``_prepare_move`` 409, journal + notice, the 5-min sweep, post-commit after leave / admin rule PUT); the internal
check / labels endpoints (party texts, owner vs foreign viewer, validation, token); admin rules (validation,
permissions, delete guards / cascade) and secrecy (a secret faction is never named to a non-member).

The quick happy paths live in ``test_faction_stage3_sanity.py``; nothing here repeats them.
"""

import asyncio
from datetime import datetime

import pytest
from fastapi import HTTPException

import crud
import faction_core as fc
import faction_crud
import faction_territory as ft
import models
from tests.reputation_world import NO_ROLE, SCRIBE
from tests.faction_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, DUNGEON_CRYPT, GAMMA, INTERNAL, L_CITADEL, L_MARKET, L_NIVA, L_STATION, MERCHANT,
    USER_ALPHA, USER_BETA, access_rule, add_rank, as_admin, as_moderator, as_user, exec_, fapi, fw,
    join, location_of, log_types, make_faction, member, notice_texts, place, q, rep_world, rows, run_flow, set_points,
    tw,
)

I = "/characters/internal"
A = "/characters/admin/factions"

PUB = fc.AccessFaction(1, "Орден", False, True)
SEC = fc.AccessFaction(2, "Тень", True, True)
HIDDEN = fc.AccessFaction(3, "Скрытые", False, False)
KNIGHT = fc.AccessRank(5, "Рыцарь", 3)


def move(fapi, cid, loc):
    return fapi.put(f"{I}/{cid}/update_location", json={"new_location_id": loc}, headers=INTERNAL)


def check(fapi, kind, target, ids):
    return fapi.post(f"{I}/factions/access/check", headers=INTERNAL,
                     json={"kind": kind, "target_id": target, "character_ids": ids})


def labels(fapi, kind, targets, character_id=None, user_id=None):
    return fapi.post(f"{I}/factions/access/labels", headers=INTERNAL,
                     json={"kind": kind, "target_ids": targets, "character_id": character_id, "user_id": user_id})


def order(f, name="Орден", **kw):
    """A faction with a one-rank ladder («Послушник», sort 1); returns (faction_id, rank_id)."""
    fid = make_faction(f, name, **kw)
    return fid, add_rank(f, fid, "Послушник", 1)


def eject(f, cid):
    db = f()
    try:
        return asyncio.run(ft.eject(db, cid))
    finally:
        db.close()


def pick(f, cid, loc):
    db = f()
    try:
        return ft.pick_target(db, cid, loc)
    finally:
        db.close()


# ============================================================================================ pure rules


@pytest.mark.parametrize("faction, rank, kw, expected", [
    (None, None, dict(viewer_known=True), (True, None, None, False)),
    (HIDDEN, KNIGHT, dict(viewer_known=True), (True, None, None, False)),             # hidden faction = open
    (PUB, None, dict(viewer_known=False), (None, "Закрыто: Орден", None, True)),
    (SEC, KNIGHT, dict(viewer_known=False), (None, "Закрыто", None, True)),
    (PUB, None, dict(viewer_known=True), (False, "Закрыто: Орден", "Вход только для членов фракции «Орден»", True)),
    (SEC, None, dict(viewer_known=True), (False, "Закрыто", "Сюда вас не пускают", True)),
    (PUB, None, dict(viewer_known=True, is_member=True), (True, "Территория фракции «Орден»", None, True)),
    (PUB, KNIGHT, dict(viewer_known=True, is_member=True, member_rank_order=None),        # member without a rank
     (False, "Закрыто: нужно звание «Рыцарь» во фракции «Орден»", "Нужно звание «Рыцарь» во фракции «Орден»", True)),
    (SEC, KNIGHT, dict(viewer_known=True, is_member=True, member_rank_order=2),           # member may know the name
     (False, "Закрыто: нужно звание «Рыцарь» во фракции «Тень»", "Нужно звание «Рыцарь» во фракции «Тень»", True)),
    (SEC, KNIGHT, dict(viewer_known=True, is_member=True, member_rank_order=4), (True, "Территория фракции «Тень»",
                                                                                 None, True)),
])
def test_access_decision_table(faction, rank, kw, expected):
    d = fc.access_decision(faction, rank, **kw)
    assert (d.allowed, d.label, d.refusal, d.rule) == expected


def test_dungeon_refusal_texts():
    assert fc.dungeon_refusal(PUB, None, ["Бета"], party=False) == "Подземелье только для членов фракции «Орден»"
    assert fc.dungeon_refusal(PUB, None, ["Альфа", "Бета"], party=True) == \
        "Подземелье только для членов фракции «Орден» — не проходят: Альфа, Бета"
    assert fc.dungeon_refusal(PUB, KNIGHT, ["Бета"], party=True) == \
        "Нужно звание «Рыцарь» во фракции «Орден» — не проходят: Бета"
    assert fc.dungeon_refusal(SEC, KNIGHT, ["Бета"], party=False) == "Подземелье закрыто"
    party = fc.dungeon_refusal(SEC, None, ["Бета"], party=True)
    assert party == "Подземелье закрыто — войти могут не все участники отряда" and "Бета" not in party


# ============================================================================================ move gate


def test_refused_move_leaves_the_character_in_place_and_left_member_is_refused_again(fapi, tw):
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    r = move(fapi, BETA, L_CITADEL)
    assert r.status_code == 409 and location_of(tw, BETA) == L_MARKET
    join(tw, BETA, fid)
    assert move(fapi, BETA, L_CITADEL).status_code == 200 and location_of(tw, BETA) == L_CITADEL
    move(fapi, BETA, L_MARKET)
    run_flow(tw, faction_crud.leave, BETA, fid)
    assert move(fapi, BETA, L_CITADEL).json()["detail"] == "Вход только для членов фракции «Орден»"


def test_staying_in_the_same_closed_location_is_not_a_move(fapi, tw):
    """A forced move may have put him there; a same-location update must not 409 (the eject sweep handles it)."""
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    place(tw, BETA, L_CITADEL)
    assert move(fapi, BETA, L_CITADEL).status_code == 200


def test_rank_gate_uses_the_rank_order_not_the_id(fapi, tw):
    fid = make_faction(tw, "Орден")
    knight = add_rank(tw, fid, "Рыцарь", 5, min_points=100)        # created first: lower id, higher order
    novice = add_rank(tw, fid, "Послушник", 1)
    access_rule(tw, fid, L_CITADEL, rank=knight)
    join(tw, ALPHA, fid)
    assert member(tw, ALPHA, fid)["rank_id"] == novice
    assert move(fapi, ALPHA, L_CITADEL).json()["detail"] == "Нужно звание «Рыцарь» во фракции «Орден»"
    exec_(tw, "UPDATE faction_members SET rank_id = :r WHERE character_id = :c", r=knight, c=ALPHA)
    assert move(fapi, ALPHA, L_CITADEL).status_code == 200


# ============================================================================================ teleport gate


def _teleport_world(f):
    """NPC 53 @100 -> NPC 56 @120 «Цитадель» (both teleport masters, link cost 10); user 7 plays Альфа."""
    exec_(f, "UPDATE characters SET npc_role = :r WHERE id IN (:a, :b)", r=crud.TELEPORT_ROLE, a=NO_ROLE,
          b=SCRIBE)
    place(f, SCRIBE, L_CITADEL)
    exec_(f, "INSERT INTO users (id, username, current_character) VALUES (:u, 'alpha', :c)", u=USER_ALPHA, c=ALPHA)
    db = f()
    try:
        link = models.TeleportLink(from_npc_id=NO_ROLE, to_npc_id=SCRIBE, cost_gold=10)
        db.add(link)
        db.commit()
        return int(link.id)
    finally:
        db.close()


def test_teleport_refused_before_any_charge_and_option_locked(tw):
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    link_id = _teleport_world(tw)
    db = tw()
    try:
        with pytest.raises(HTTPException) as exc:
            crud.execute_teleport(db, USER_ALPHA, NO_ROLE, link_id)
        assert (exc.value.status_code, exc.value.detail) == (403, "Вход только для членов фракции «Орден»")
        db.rollback()
        options = [{"link_id": link_id, "to_location_id": L_CITADEL}, {"link_id": link_id, "to_location_id": L_NIVA}]
        crud.teleport_lock_reasons(db, ALPHA, NO_ROLE, options)
        assert [o["locked_reason"] for o in options] == ["Вход только для членов фракции «Орден»", None]
    finally:
        db.close()
    assert location_of(tw, ALPHA) == L_MARKET
    assert q(tw, "SELECT last_teleport_at FROM characters WHERE id = :c", c=ALPHA) is None


def test_member_passes_the_teleport_gate(tw):
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    link_id = _teleport_world(tw)
    join(tw, ALPHA, fid)
    db = tw()
    try:
        options = [{"link_id": link_id, "to_location_id": L_CITADEL}]
        crud.teleport_lock_reasons(db, ALPHA, NO_ROLE, options)
        assert options[0]["locked_reason"] is None
        with pytest.raises(HTTPException) as exc:            # passes the gate, then fails on gold (0 marks)
            crud.execute_teleport(db, USER_ALPHA, NO_ROLE, link_id)
        assert exc.value.status_code != 403
    finally:
        db.close()


# ============================================================================================ eject


def test_eject_target_order_neighbour_hq_station_none(tw):
    fid, _r = order(tw, hq=L_STATION)
    other, _r2 = order(tw, "Стража")
    access_rule(tw, fid, L_CITADEL)
    assert pick(tw, BETA, L_CITADEL) == L_MARKET                  # first open neighbour, ascending id
    access_rule(tw, other, L_MARKET)
    assert pick(tw, BETA, L_CITADEL) == L_NIVA
    access_rule(tw, other, L_NIVA)
    exec_(tw, "UPDATE factions SET hq_location_id = 300 WHERE id = :fid", fid=fid)
    assert pick(tw, BETA, L_CITADEL) == 300                       # the rule faction's HQ
    exec_(tw, "UPDATE factions SET hq_location_id = NULL WHERE id = :fid", fid=fid)
    assert pick(tw, BETA, L_CITADEL) == L_STATION                 # the region guard station
    access_rule(tw, other, L_STATION)
    assert pick(tw, BETA, L_CITADEL) is None


def test_eject_moves_logs_and_notifies(tw):
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    place(tw, BETA, L_CITADEL)
    notices = eject(tw, BETA)
    assert location_of(tw, BETA) == L_MARKET
    assert tw.moves.calls == [(BETA, L_CITADEL, "faction")]
    assert [n.message for n in notices] == ["Вас выдворили из «Цитадель» в «Рынок»: это территория фракции «Орден»"]
    assert log_types(tw, BETA, fid) == [fc.EV_EJECTED]
    assert q(tw, "SELECT COUNT(*) FROM character_logs WHERE character_id = :c AND event_type = 'faction_eject'",
             c=BETA) == 1
    assert eject(tw, BETA) == []                                  # nothing to do any more


def test_eject_skips_allowed_members_busy_and_postponed(tw):
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    join(tw, ALPHA, fid)
    for cid in (ALPHA, BETA, GAMMA):
        place(tw, cid, L_CITADEL)
    assert eject(tw, ALPHA) == [] and location_of(tw, ALPHA) == L_CITADEL         # a member may stay
    exec_(tw, "INSERT INTO battles (id, status) VALUES (5, 'in_progress')")
    exec_(tw, "INSERT INTO battle_participants (battle_id, character_id) VALUES (5, :c)", c=BETA)
    assert eject(tw, BETA) == [] and location_of(tw, BETA) == L_CITADEL           # in battle: retried later
    assert tw.moves.calls == []
    tw.moves.error = HTTPException(status_code=409, detail="Персонаж находится в подземелье — перенос невозможен")
    assert eject(tw, GAMMA) == [] and location_of(tw, GAMMA) == L_CITADEL
    assert log_types(tw, GAMMA) == []


def test_sweep_ejects_only_who_may_not_stand_there(tw):
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    join(tw, ALPHA, fid)
    for cid in (ALPHA, BETA, GAMMA):
        place(tw, cid, L_CITADEL)
    place(tw, MERCHANT, L_CITADEL)                                # NPCs are never ejected
    db = tw()
    try:
        assert ft.players_in_closed(db) == [BETA, GAMMA]
    finally:
        db.close()
    assert ft.sweep(tw) == 2
    assert [location_of(tw, c) for c in (ALPHA, BETA, GAMMA, MERCHANT)] == [L_CITADEL, L_MARKET, L_MARKET, L_CITADEL]
    assert len(notice_texts(tw)) == 2
    exec_(tw, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=fid)
    place(tw, BETA, L_CITADEL)
    assert ft.sweep(tw) == 0                                      # hidden faction: the territory is open


def test_leave_route_ejects_after_commit(fapi, tw):
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    join(tw, ALPHA, fid)
    place(tw, ALPHA, L_CITADEL)
    as_user(USER_ALPHA)
    assert fapi.post(f"/characters/{ALPHA}/factions/{fid}/leave").status_code == 200
    assert location_of(tw, ALPHA) == L_MARKET and fc.EV_EJECTED in log_types(tw, ALPHA, fid)


def test_admin_rule_put_ejects_present_players(fapi, tw):
    fid, _r = order(tw)
    place(tw, BETA, L_CITADEL)
    as_admin()
    assert fapi.put(f"{A}/access/location/{L_CITADEL}", json={"faction_id": fid}).status_code == 200
    assert location_of(tw, BETA) == L_MARKET


def test_eject_failure_does_not_fail_the_admin_put(fapi, tw):
    fid, _r = order(tw)
    place(tw, BETA, L_CITADEL)
    tw.moves.error = RuntimeError("locations-service down")
    as_admin()
    r = fapi.put(f"{A}/access/location/{L_CITADEL}", json={"faction_id": fid})
    assert r.status_code == 200 and location_of(tw, BETA) == L_CITADEL


# ============================================================================================ internal check / labels


def test_internal_check_variants(fapi, tw):
    fid = make_faction(tw, "Орден")
    add_rank(tw, fid, "Послушник", 1)
    knight = add_rank(tw, fid, "Рыцарь", 2, min_points=100)
    join(tw, ALPHA, fid)
    assert check(fapi, "dungeon", DUNGEON_CRYPT, [ALPHA, BETA]).json() == {
        "rule": False, "allowed": True, "failed_character_ids": [], "detail": None}
    access_rule(tw, fid, L_CITADEL)
    out = check(fapi, "location", L_CITADEL, [ALPHA, BETA]).json()
    assert out["failed_character_ids"] == [BETA] and out["detail"] == "Вход только для членов фракции «Орден»"
    assert check(fapi, "location", L_CITADEL, [ALPHA, MERCHANT]).json()["allowed"] is True     # NPCs pass
    access_rule(tw, fid, DUNGEON_CRYPT, kind="dungeon", rank=knight)
    assert check(fapi, "dungeon", DUNGEON_CRYPT, [ALPHA]).json()["detail"] == \
        "Нужно звание «Рыцарь» во фракции «Орден»"
    assert check(fapi, "dungeon", DUNGEON_CRYPT, [ALPHA, BETA]).json()["detail"] == \
        "Нужно звание «Рыцарь» во фракции «Орден» — не проходят: Альфа, Бета"
    exec_(tw, "UPDATE factions SET is_active = 0 WHERE id = :fid", fid=fid)
    assert check(fapi, "dungeon", DUNGEON_CRYPT, [BETA]).json()["rule"] is False


def test_labels_are_viewer_aware_only_for_the_owner(fapi, tw):
    fid, _r = order(tw)
    sec, _r2 = order(tw, "Тень", secret=True)
    access_rule(tw, fid, L_CITADEL)
    access_rule(tw, sec, L_STATION)
    join(tw, ALPHA, sec)
    targets = [L_MARKET, L_CITADEL, L_STATION]
    own = labels(fapi, "location", targets, ALPHA, USER_ALPHA).json()["items"]
    assert own == [{"target_id": L_CITADEL, "access_label": "Закрыто: Орден", "access_allowed": False},
                   {"target_id": L_STATION, "access_label": "Территория фракции «Тень»", "access_allowed": True}]
    foreign = labels(fapi, "location", targets, ALPHA, USER_BETA).json()["items"]      # someone else's character
    assert foreign == [{"target_id": L_CITADEL, "access_label": "Закрыто: Орден", "access_allowed": None},
                       {"target_id": L_STATION, "access_label": "Закрыто", "access_allowed": None}]
    assert labels(fapi, "location", targets).json()["items"] == foreign                 # no viewer at all


@pytest.mark.parametrize("path, body", [
    ("check", {"kind": "castle", "target_id": 1, "character_ids": [1]}),
    ("check", {"kind": "location", "target_id": 1, "character_ids": []}),
    ("check", {"kind": "location", "target_id": 1, "character_ids": list(range(1, 22))}),
    ("check", {"kind": "location", "target_id": "1", "character_ids": [1]}),
    ("check", {"kind": "location", "target_id": 1, "character_ids": ["1 OR 1=1"]}),
    ("labels", {"kind": "location", "target_ids": list(range(1, 202))}),
    ("labels", {"kind": "location'; DROP TABLE factions; --", "target_ids": [1]}),
    ("labels", {"kind": "castle", "target_ids": [1]}),
])
def test_internal_validation(fapi, tw, path, body):
    assert fapi.post(f"{I}/factions/access/{path}", headers=INTERNAL, json=body).status_code == 422
    assert q(tw, "SELECT COUNT(*) FROM factions") == 0                              # table still there


@pytest.mark.parametrize("method, path", [
    ("post", "/factions/access/check"), ("post", "/factions/access/labels"),
    ("post", "/factions/battle-result"), ("get", f"/factions/{ALPHA}/passive-modifiers"),
])
def test_internal_endpoints_need_the_token(fapi, tw, method, path):
    for headers in ({}, {"X-Internal-Token": "wrong"}):
        r = getattr(fapi, method)(f"{I}{path}", headers=headers,
                                  **({"json": {}} if method == "post" else {}))
        assert r.status_code == 401


# ============================================================================================ admin rules


def test_admin_rule_validation(fapi, tw):
    fid, _r = order(tw)
    _other, other_rank = order(tw, "Стража")
    as_admin()
    put = lambda kind, target, body: fapi.put(f"{A}/access/{kind}/{target}", json=body)  # noqa: E731
    r = put("location", L_CITADEL, {"faction_id": fid, "min_rank_id": other_rank})
    assert (r.status_code, r.json()["detail"]) == (422, "Звание должно принадлежать выбранной фракции")
    assert put("location", L_CITADEL, {"faction_id": 9999}).status_code == 422
    assert put("castle", L_CITADEL, {"faction_id": fid}).status_code == 422
    assert put("location", L_CITADEL, {"faction_id": "1"}).status_code == 422                 # strict int
    r = put("dungeon", 999, {"faction_id": fid})
    assert (r.status_code, r.json()["detail"]) == (404, "Подземелье не найдено")
    assert put("dungeon", DUNGEON_CRYPT, {"faction_id": fid}).json()["rule"]["faction_name"] == "Орден"
    assert put("dungeon", DUNGEON_CRYPT, {"faction_id": _other}).json()["rule"]["faction_name"] == "Стража"   # upsert
    assert q(tw, "SELECT COUNT(*) FROM faction_access_rules") == 1
    assert fapi.get(f"{A}/{_other}/territory").json() == [
        {"kind": "dungeon", "target_id": DUNGEON_CRYPT, "target_name": "Склеп", "min_rank": None}]
    assert fapi.delete(f"{A}/access/dungeon/{DUNGEON_CRYPT}").json() == {"ok": True}
    assert fapi.delete(f"{A}/access/dungeon/{DUNGEON_CRYPT}").json() == {"ok": True}           # idempotent


def test_admin_rule_permissions(fapi, tw):
    fid, _r = order(tw)
    as_user(USER_ALPHA)
    assert fapi.get(f"{A}/access/location/{L_CITADEL}").status_code == 403
    assert fapi.put(f"{A}/access/location/{L_CITADEL}", json={"faction_id": fid}).status_code == 403
    assert fapi.delete(f"{A}/access/location/{L_CITADEL}").status_code == 403
    assert fapi.get(f"{A}/{fid}/territory").status_code == 403
    as_user(2, "moderator", ["factions:read"])
    assert fapi.get(f"{A}/access/location/{L_CITADEL}").json() == {"rule": None}
    assert fapi.put(f"{A}/access/location/{L_CITADEL}", json={"faction_id": fid}).status_code == 403
    as_moderator()
    assert fapi.put(f"{A}/access/location/{L_CITADEL}", json={"faction_id": fid}).status_code == 200


def test_faction_delete_guard_on_item_stock_and_cascade(fapi, tw):
    fid, _r = order(tw)
    access_rule(tw, fid, L_CITADEL)
    exec_(tw, "INSERT INTO faction_enemies (faction_id, kind, ref_id, points) VALUES (:fid, 'hostile', 0, 5)", fid=fid)
    exec_(tw, "INSERT INTO faction_outlaw_regions (faction_id, region_id, level_code) VALUES (:fid, 10, 'criminal')",
          fid=fid)
    exec_(tw, "INSERT INTO faction_item_stock (faction_id, item_id, quantity, updated_at) VALUES (:fid, 501, 2, :n)",
          fid=fid, n=datetime.utcnow())
    as_admin()
    r = fapi.delete(f"{A}/{fid}")
    assert (r.status_code, r.json()["detail"]) == (409, "На складе фракции остались предметы")
    exec_(tw, "UPDATE faction_item_stock SET quantity = 0")
    assert fapi.delete(f"{A}/{fid}").status_code == 200
    for table in ("faction_access_rules", "faction_enemies", "faction_outlaw_regions", "faction_item_stock"):
        assert q(tw, f"SELECT COUNT(*) FROM {table}") == 0, table


# ============================================================================================ secrecy


def test_secret_faction_is_never_named_to_a_non_member(fapi, tw):
    sec, _r = order(tw, "Тень", secret=True)
    access_rule(tw, sec, L_CITADEL)
    access_rule(tw, sec, DUNGEON_CRYPT, kind="dungeon")
    link_id = _teleport_world(tw)
    texts = [move(fapi, ALPHA, L_CITADEL).json()["detail"],
             check(fapi, "dungeon", DUNGEON_CRYPT, [ALPHA]).json()["detail"],
             check(fapi, "location", L_CITADEL, [ALPHA, BETA]).json()["detail"]]
    texts += [i["access_label"] for i in labels(fapi, "location", [L_CITADEL], ALPHA, USER_ALPHA).json()["items"]]
    db = tw()
    try:
        with pytest.raises(HTTPException) as exc:
            crud.execute_teleport(db, USER_ALPHA, NO_ROLE, link_id)
        texts.append(exc.value.detail)
    finally:
        db.close()
    place(tw, BETA, L_CITADEL)
    texts += [n.message for n in eject(tw, BETA)]
    assert texts[:3] == ["Сюда вас не пускают", "Подземелье закрыто", "Сюда вас не пускают"]
    assert texts[-1] == "Вас выдворили из «Цитадель» в «Рынок»: это закрытая территория"
    assert all("Тень" not in t for t in texts), texts
