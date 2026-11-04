"""FEAT-198 QA (task 9): staff endpoints (§3.6 admin table, decision 9 — no new permissions).

* RBAC: settings read = reputation:read, write = reputation:settings (admin only); character view =
  reputation:read; release / clear-wanted = reputation:manage (moderator yes, editor / user 403);
* release ends a serving term and/or cancels an open encounter; 409 with nothing to release;
* clear-wanted one region / all regions; reason required (3..500, trimmed); request_id replay is a no-op;
  SQL-injection strings stored as plain text;
* settings PUT: exactly 5 levels, jail_hours 1..168 (A1), a decay change materialises at the OLD rate first.
"""

from datetime import timedelta

import pytest

from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, R_DUNY, R_OST, R_PASHNI, USER_ALPHA, api, as_admin, as_moderator, as_user, char_row, encounter,
    exec_, jail_character, law_payloads, law_world, make_encounter, now, q, rep_world, rid, rows, set_wanted,
    wanted,
)

ADMIN_BASE = "/characters/admin/law"


def as_editor():
    as_user(3, "editor", ["characters:read", "items:create"])


# =============================================================================================== settings

def test_settings_get_rbac_and_seed(api, law_world):
    as_user(USER_ALPHA)
    assert api.get(f"{ADMIN_BASE}/settings").status_code == 403
    as_editor()
    assert api.get(f"{ADMIN_BASE}/settings").status_code == 403
    as_moderator()
    resp = api.get(f"{ADMIN_BASE}/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert [lv["jail_hours"] for lv in data["levels"]] == [2, 12, 24, 72, 168]
    assert data["settings"]["max_remaining_jail_hours"] == 168
    assert "pass_last_run_at" not in data["settings"]


def _settings_body(api):
    as_admin()
    return api.get(f"{ADMIN_BASE}/settings").json()


def test_settings_put_rbac(api, law_world):
    body = _settings_body(api)
    for login in (as_moderator, as_editor, lambda: as_user(USER_ALPHA)):
        login()
        assert api.put(f"{ADMIN_BASE}/settings", json=body).status_code == 403


def test_settings_put_updates_levels(api, law_world):
    body = _settings_body(api)
    body["levels"][0]["name"] = "  Под подозрением  "
    body["levels"][4]["jail_hours"] = 100
    body["settings"]["escape_cooldown_hours"] = 4
    resp = api.put(f"{ADMIN_BASE}/settings", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["levels"][0]["name"] == "Под подозрением"
    assert q(law_world, "SELECT jail_hours FROM law_levels WHERE code = 'enemy'") == 100
    assert q(law_world, "SELECT escape_cooldown_hours FROM law_settings") == 4


@pytest.mark.parametrize("mutate,fragment", [
    (lambda b: b["levels"][4].update(jail_hours=169), "168"),
    (lambda b: b["levels"][0].update(jail_hours=0), "168"),
    (lambda b: b["levels"].pop(), "ровно 5"),
    (lambda b: b["levels"][1].update(code="boss"), "ровно 5"),
    (lambda b: b["levels"][2].update(min_value=50), "возрастать"),
    (lambda b: b["settings"].update(max_remaining_jail_hours=200), "Предел срока"),
    (lambda b: b["settings"].update(bail_multiplier=0.5), "Множитель"),
    (lambda b: b["settings"].update(outlaw_min_level="'; DROP TABLE law_levels; --"), None),
])
def test_settings_put_validation(api, law_world, mutate, fragment):
    body = _settings_body(api)
    mutate(body)
    resp = api.put(f"{ADMIN_BASE}/settings", json=body)
    assert resp.status_code in (400, 422), resp.text
    if fragment and resp.status_code == 400:
        assert fragment in resp.json()["detail"]
    assert q(law_world, "SELECT COUNT(*) FROM law_levels") == 5
    assert q(law_world, "SELECT jail_hours FROM law_levels WHERE code = 'enemy'") == 168


def test_settings_decay_change_materialises_at_old_rate(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 300, decay_at=now() - timedelta(days=2))          # 50/day -> 200
    body = _settings_body(api)
    body["settings"]["decay_per_day"] = 0
    assert api.put(f"{ADMIN_BASE}/settings", json=body).status_code == 200
    assert wanted(law_world, ALPHA, R_OST) == 200
    # decay off: the value holds
    exec_(law_world, "UPDATE character_wanted SET decay_at = :d", d=now() - timedelta(days=10))
    as_admin()
    view = api.get(f"{ADMIN_BASE}/characters/{ALPHA}").json()
    assert view["wanted"][0]["value"] == 200


# =============================================================================================== character view

def test_admin_character_view(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 345)
    enc_id = make_encounter(law_world)
    as_user(USER_ALPHA)
    assert api.get(f"{ADMIN_BASE}/characters/{ALPHA}").status_code == 403
    as_moderator()
    resp = api.get(f"{ADMIN_BASE}/characters/{ALPHA}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["wanted"][0]["value"] == 345 and data["wanted"][0]["level_code"] == "criminal"
    assert data["encounter"]["id"] == enc_id and data["encounter"]["wanted_value"] == 345
    assert data["encounter"]["from_location_id"] == 100
    assert [x["action"] for x in data["log"]] == ["encounter"]
    assert api.get(f"{ADMIN_BASE}/characters/99999").status_code == 404


# =============================================================================================== release

def _release(api, cid=ALPHA, reason="Ошибка стражи", request_id=None):
    return api.post(f"{ADMIN_BASE}/characters/{cid}/release",
                    json={"reason": reason, "request_id": request_id or rid()})


def test_release_rbac(api, law_world):
    jail_character(law_world)
    for login in (as_editor, lambda: as_user(USER_ALPHA)):
        login()
        assert _release(api).status_code == 403
    assert char_row(law_world, ALPHA).jailed_until > now()


def test_moderator_releases_from_jail(api, law_world, stub_law_notify_send):
    term_id = jail_character(law_world)
    as_moderator()
    resp = _release(api, reason="  Помилование  ")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"message": "Персонаж освобождён из тюрьмы", "released": True, "cancelled": False,
                           "duplicate": False}
    assert q(law_world, "SELECT status FROM law_jail_terms WHERE id = :t", t=term_id) == "released"
    row = char_row(law_world, ALPHA)
    assert row.jailed_until <= now() and row.jail_region_id is None
    assert rows(law_world, "SELECT action, reason, actor_user_id FROM law_log") == [
        ("staff_release", "Помилование", 2)]
    assert any(p["message"] == "Решением властей вы освобождены" for p in law_payloads(stub_law_notify_send))


def test_release_cancels_an_open_encounter(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = make_encounter(law_world)
    as_admin()
    resp = _release(api)
    assert resp.json()["cancelled"] is True and resp.json()["released"] is False
    assert encounter(law_world, enc_id).status == "cancelled"
    assert char_row(law_world, ALPHA).law_encounter_id is None
    assert wanted(law_world, ALPHA, R_OST) == 150                                       # wanted untouched


def test_release_replay_and_nothing_to_release(api, law_world):
    jail_character(law_world)
    as_admin()
    request_id = rid()
    assert _release(api, request_id=request_id).json()["released"] is True
    again = _release(api, request_id=request_id)
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert q(law_world, "SELECT COUNT(*) FROM law_log WHERE action = 'staff_release'") == 1
    assert _release(api).status_code == 409                                            # new request: nothing left
    assert _release(api, cid=99999).status_code == 404


@pytest.mark.parametrize("reason", ["", "  ", "ab", "  a ", "x" * 501, None])
def test_release_reason_required(api, law_world, reason):
    jail_character(law_world)
    as_admin()
    body = {"request_id": rid()}
    if reason is not None:
        body["reason"] = reason
    assert api.post(f"{ADMIN_BASE}/characters/{ALPHA}/release", json=body).status_code == 422
    assert char_row(law_world, ALPHA).jailed_until > now()


def test_release_request_id_must_be_uuid(api, law_world):
    jail_character(law_world)
    as_admin()
    resp = api.post(f"{ADMIN_BASE}/characters/{ALPHA}/release",
                    json={"reason": "Ошибка", "request_id": "%' OR '1'='1"})
    assert resp.status_code == 422


def test_reason_with_sql_injection_is_stored_as_text(api, law_world):
    jail_character(law_world)
    as_admin()
    evil = "'); DROP TABLE law_log; -- <script>alert(1)</script>"
    assert _release(api, reason=evil).status_code == 200
    assert q(law_world, "SELECT reason FROM law_log WHERE action = 'staff_release'") == evil
    assert q(law_world, "SELECT COUNT(*) FROM characters") > 0


# =============================================================================================== clear wanted

def _clear(api, region_id=None, reason="Дело закрыто", request_id=None, cid=ALPHA):
    return api.post(f"{ADMIN_BASE}/characters/{cid}/clear-wanted",
                    json={"region_id": region_id, "reason": reason, "request_id": request_id or rid()})


def test_clear_wanted_rbac(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 300)
    for login in (as_editor, lambda: as_user(USER_ALPHA)):
        login()
        assert _clear(api).status_code == 403
    assert wanted(law_world, ALPHA, R_OST) == 300


def test_clear_wanted_one_region_and_all(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 300)
    set_wanted(law_world, ALPHA, R_PASHNI, 200)
    set_wanted(law_world, ALPHA, R_DUNY, 100)
    as_moderator()
    resp = _clear(api, region_id=R_OST)
    assert resp.status_code == 200 and resp.json()["cleared_region_ids"] == [R_OST]
    assert wanted(law_world, ALPHA, R_OST) == 0 and wanted(law_world, ALPHA, R_PASHNI) == 200
    resp = _clear(api)
    assert sorted(resp.json()["cleared_region_ids"]) == [R_PASHNI, R_DUNY]
    assert wanted(law_world, ALPHA, R_PASHNI) == 0 and wanted(law_world, ALPHA, R_DUNY) == 0
    logs = rows(law_world, "SELECT action, region_id, wanted_before, reason FROM law_log ORDER BY id")
    assert logs[0] == ("staff_clear", R_OST, 300, "Дело закрыто")
    assert _clear(api).json() == {"message": "Розыска нет", "cleared_region_ids": [], "duplicate": False}


def test_clear_wanted_replay_unknown_region_and_validation(api, law_world):
    set_wanted(law_world, ALPHA, R_OST, 300)
    as_admin()
    request_id = rid()
    assert _clear(api, request_id=request_id).json()["cleared_region_ids"] == [R_OST]
    set_wanted(law_world, ALPHA, R_OST, 300)
    again = _clear(api, request_id=request_id)
    assert again.json()["duplicate"] is True and wanted(law_world, ALPHA, R_OST) == 300
    assert _clear(api, region_id=999).status_code == 404
    assert _clear(api, region_id=0).status_code == 422
    assert _clear(api, reason="x").status_code == 422
    assert _clear(api, cid=99999).status_code == 404
