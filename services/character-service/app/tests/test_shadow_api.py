"""FEAT-199 QA (task 7): shadow / renown HTTP contracts (§3.7).

* admin settings: GET (reputation:read; defaults without a row), PUT (reputation:settings only; moderator 403),
  validation 400 / 422 in Russian, SQL-injection strings stored literally, a changed suspicion decay materialises
  the regions at the OLD rate first;
* admin crimes list: default ``open``, status / region / character filters, paging bounds, 422 for bad filters;
* regions suspicion list; renown adjust (reason, UUID request_id replay, NPC 400, unknown 404, zero / huge delta 422,
  fame tier-up notice, infamy silent);
* player / public: private ``/{id}/renown`` (owner + staff; 403 stranger, 404 unknown), tier names only — never the
  numbers; public passport carries only the fame tier; fame-tiers list names only; region card suspicion text only;
* law admin character card: crime snapshot fields + renown numbers / log.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import economy_api
import main
from main import app
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, MERCHANT, R_DUNY, R_OST, R_PASHNI, USER_ALPHA, USER_BETA, api, as_admin, as_moderator,
    as_user, exec_, law_world, now, q, rep_world, rid, rows,
)
from tests.shadow_world import (
    crime, make_deferred, payloads, renown, renown_log, set_renown, set_suspicion, suspicion, ws_types,
)

import shadow_core as sc


# =============================================================================================== settings

def _settings_body(**overrides):
    s = {n: (float(v) if not isinstance(v, (bool, int)) else v)
         for n, v in ((n, getattr(sc.DEFAULT_SETTINGS, n)) for n in sc.SETTINGS_FIELDS)}
    s.update(overrides.pop("settings", {}))
    fame = [{"code": t.code, "name": t.name, "min_value": t.min_value, "witness_pct": float(t.witness_pct)}
            for t in sc.DEFAULT_TIERS if t.scale == "fame"]
    infamy = [{"code": t.code, "name": t.name, "min_value": t.min_value}
              for t in sc.DEFAULT_TIERS if t.scale == "infamy"]
    body = {"settings": s, "fame_tiers": fame, "infamy_tiers": infamy}
    body.update(overrides)
    return body


def test_get_settings_defaults_without_a_row(api, law_world):
    as_moderator()
    resp = api.get("/characters/admin/shadow/settings")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["settings"]["witness_base_safe_pct"] == 70 and body["settings"]["reveal_days"] == 3
    assert body["settings"]["witness_enabled"] is True
    assert [t["code"] for t in body["fame_tiers"]] == list(sc.FAME_CODES)
    assert [t["code"] for t in body["infamy_tiers"]] == list(sc.INFAMY_CODES)
    assert body["fame_tiers"][4]["witness_pct"] == 15


def test_settings_rbac(api, law_world):
    as_user(USER_ALPHA)
    assert api.get("/characters/admin/shadow/settings").status_code == 403
    as_moderator()                                                      # read + manage, no settings
    assert api.put("/characters/admin/shadow/settings", json=_settings_body()).status_code == 403
    as_user(3, "editor", ["reputation:settings"])                       # settings only
    assert api.put("/characters/admin/shadow/settings", json=_settings_body()).status_code == 200


def test_put_settings_stores_values_and_tiers(api, law_world):
    as_admin()
    body = _settings_body(settings={"witness_base_safe_pct": 60.5, "reveal_days": 5, "witness_enabled": False})
    body["fame_tiers"][1]["name"] = "Слышали о нём"
    body["fame_tiers"][1]["min_value"] = 40
    resp = api.put("/characters/admin/shadow/settings", json=body)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["settings"]["witness_base_safe_pct"] == 60.5 and out["settings"]["reveal_days"] == 5
    assert out["settings"]["witness_enabled"] is False
    assert out["fame_tiers"][1] == {"code": "familiar", "sort_order": 2, "name": "Слышали о нём", "min_value": 40,
                                    "witness_pct": 2}
    again = api.get("/characters/admin/shadow/settings").json()
    assert again == out
    # a second save (the tier rows exist now) works too — UNIQUE(scale, sort_order) two-pass rewrite
    assert api.put("/characters/admin/shadow/settings", json=body).status_code == 200
    assert q(law_world, "SELECT COUNT(*) FROM renown_tiers") == 10


@pytest.mark.parametrize("settings,fragment", [
    ({"witness_min_pct": 60, "witness_max_pct": 50}, "минимум не может быть больше максимума"),
    ({"witness_base_safe_pct": 150}, "от 0 до 100"),
    ({"reveal_days": 0}, "Срок раскрытия"),
    ({"suspicion_uneasy_at": 60}, "Пороги подозрения"),
])
def test_put_settings_validation_400(api, law_world, settings, fragment):
    as_admin()
    resp = api.put("/characters/admin/shadow/settings", json=_settings_body(settings=settings))
    assert resp.status_code == 400 and fragment in resp.json()["detail"]
    assert q(law_world, "SELECT COUNT(*) FROM shadow_settings") == 0


def test_put_settings_tier_validation(api, law_world):
    as_admin()
    body = _settings_body()
    body["fame_tiers"] = body["fame_tiers"][:4]
    assert api.put("/characters/admin/shadow/settings", json=body).status_code == 400
    body = _settings_body()
    body["infamy_tiers"][2]["min_value"] = 50
    resp = api.put("/characters/admin/shadow/settings", json=body)
    assert resp.status_code == 400 and "строго возрастать" in resp.json()["detail"]
    body = _settings_body()
    body["fame_tiers"][0]["code"] = "' OR 1=1 --"
    assert api.put("/characters/admin/shadow/settings", json=body).status_code == 400


@pytest.mark.parametrize("mutate", [
    lambda b: b["settings"].update(witness_base_safe_pct="'; DROP TABLE shadow_settings; --"),
    lambda b: b["settings"].pop("reveal_days"),
    lambda b: b.pop("fame_tiers"),
    lambda b: b["fame_tiers"][0].update(name="x" * 61),
    lambda b: b.update(fame_tiers=b["fame_tiers"] * 3),
])
def test_put_settings_schema_422(api, law_world, mutate):
    as_admin()
    body = _settings_body()
    mutate(body)
    assert api.put("/characters/admin/shadow/settings", json=body).status_code == 422


def test_tier_name_with_sql_is_stored_literally(api, law_world):
    as_admin()
    body = _settings_body()
    evil = "Robert'); DROP TABLE renown_tiers;--"
    body["fame_tiers"][4]["name"] = evil
    assert api.put("/characters/admin/shadow/settings", json=body).status_code == 200
    assert q(law_world, "SELECT name FROM renown_tiers WHERE scale = 'fame' AND code = 'legend'") == evil


def test_changed_decay_materialises_at_the_old_rate(api, law_world):
    set_suspicion(law_world, R_OST, 50, decay_at=now() - timedelta(days=2))     # 5 / day -> 40 now
    as_admin()
    resp = api.put("/characters/admin/shadow/settings", json=_settings_body(settings={"suspicion_decay_per_day": 1}))
    assert resp.status_code == 200, resp.text
    assert suspicion(law_world, R_OST) == 40


# =============================================================================================== crimes list

def test_crimes_list_default_open_and_filters(api, law_world):
    a = make_deferred(law_world, character_id=ALPHA)
    b = make_deferred(law_world, character_id=BETA, masked=True)
    c = make_deferred(law_world, character_id=GAMMA, region_id=R_DUNY, npc_id=MERCHANT, battle=78)
    exec_(law_world, "UPDATE law_crimes SET status = 'closed' WHERE id = :i", i=c)
    as_moderator()
    body = api.get("/characters/admin/shadow/crimes").json()
    assert body["total"] == 2 and {x["id"] for x in body["items"]} == {a, b}
    item = [x for x in body["items"] if x["id"] == b][0]
    assert item["status"] == "masked" and item["masked"] is True and item["character_name"] == "Бета"
    assert item["region_name"] == "Ост" and item["victim_name"] == "Лавочник" and item["location_name"] == "Рынок"
    assert item["witness_chance_pct"] == 40 and item["witness_roll_pct"] == 77.7 and item["reputation_delta"] == -150
    assert api.get("/characters/admin/shadow/crimes?status=masked").json()["total"] == 1
    assert api.get("/characters/admin/shadow/crimes?status=closed").json()["items"][0]["id"] == c
    assert api.get("/characters/admin/shadow/crimes?status=all").json()["total"] == 3
    assert api.get("/characters/admin/shadow/crimes?status=all&region_id=20").json()["total"] == 1
    assert api.get(f"/characters/admin/shadow/crimes?status=all&character_id={ALPHA}").json()["total"] == 1
    page = api.get("/characters/admin/shadow/crimes?status=all&page=2&page_size=2").json()
    assert page["total"] == 3 and len(page["items"]) == 1


@pytest.mark.parametrize("query", [
    "status=bogus", "status=open'%20OR%20'1'='1", "page_size=51", "page_size=0", "page=0", "region_id=1%20OR%201=1",
    "character_id=-1",
])
def test_crimes_list_rejects_bad_filters(api, law_world, query):
    make_deferred(law_world)
    as_admin()
    assert api.get(f"/characters/admin/shadow/crimes?{query}").status_code == 422


def test_crimes_list_rbac(api, law_world):
    as_user(USER_ALPHA)
    assert api.get("/characters/admin/shadow/crimes").status_code == 403
    as_user(3, "editor", ["reputation:manage"])
    assert api.get("/characters/admin/shadow/crimes").status_code == 403


def test_regions_suspicion_list(api, law_world):
    set_suspicion(law_world, R_OST, 55)
    set_suspicion(law_world, R_PASHNI, 10, decay_at=now() - timedelta(days=5))    # decayed to 0 -> hidden
    as_moderator()
    resp = api.get("/characters/admin/shadow/regions/suspicion")
    assert resp.status_code == 200
    assert resp.json() == [{"region_id": R_OST, "region_name": "Ост", "value": 55, "code": "alarmed",
                            "label": "Край встревожен"}]
    as_user(USER_ALPHA)
    assert api.get("/characters/admin/shadow/regions/suspicion").status_code == 403


# =============================================================================================== renown adjust

def _adjust(api, cid=ALPHA, **body):
    payload = {"scale": "fame", "delta": 600, "reason": "За подвиг", "request_id": rid()}
    payload.update(body)
    return api.post(f"/characters/admin/shadow/characters/{cid}/renown-adjust", json=payload)


def test_renown_adjust_fame_and_replay(api, law_world, stub_law_notify_send):
    as_moderator()
    req = rid()
    resp = _adjust(api, request_id=req)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"scale": "fame", "value_before": 0, "value_after": 600, "tier_before": "nameless",
                           "tier_after": "famous", "duplicate": False}
    sent = payloads(stub_law_notify_send)
    assert [(p["ws_type"], p["category"], p["message"]) for p in sent] == [
        ("fame_tier", "progress", "Ваша слава растёт: теперь вы — «Знаменитый»")]
    replay = _adjust(api, request_id=req, delta=5)
    assert replay.status_code == 200
    assert replay.json() == {"scale": "fame", "value_before": 0, "value_after": 600, "tier_before": "nameless",
                             "tier_after": "famous", "duplicate": True}
    assert renown(law_world, ALPHA) == (600, 0) and stub_law_notify_send.call_count == 1
    log = renown_log(law_world, ALPHA)
    assert log == [(f"renown:staff:{req}", "fame", "staff", 600, 600, "nameless", "famous", 2)]
    assert q(law_world, "SELECT reason FROM renown_log") == "За подвиг"


def test_renown_adjust_infamy_is_silent_and_clamped(api, law_world, stub_law_notify_send):
    as_admin()
    assert _adjust(api, scale="infamy", delta=500).json()["tier_after"] == "rumored"
    resp = _adjust(api, scale="infamy", delta=-10000)
    assert resp.json()["value_after"] == 0 and resp.json()["tier_after"] == "none"
    assert stub_law_notify_send.call_count == 0


def test_renown_adjust_fame_down_is_silent(api, law_world, stub_law_notify_send):
    set_renown(law_world, ALPHA, fame=700)
    as_admin()
    assert _adjust(api, delta=-680).json()["tier_after"] == "nameless"
    assert stub_law_notify_send.call_count == 0


def test_renown_adjust_errors(api, law_world):
    as_admin()
    assert _adjust(api, cid=MERCHANT).status_code == 400
    assert _adjust(api, cid=MERCHANT).json()["detail"] == "У NPC нет славы"
    assert _adjust(api, cid=99999).status_code == 404
    for body in ({"delta": 0}, {"delta": 10001}, {"scale": "glory"}, {"reason": "ab"}, {"request_id": "nope"},
                 {"scale": "fame'; --"}):
        assert _adjust(api, **body).status_code == 422, body
    as_user(3, "editor", ["reputation:read", "reputation:settings"])
    assert _adjust(api).status_code == 403
    assert renown(law_world, ALPHA) == (0, 0)


# =============================================================================================== player / public

def test_private_renown_owner_sees_tier_names_only(api, law_world):
    set_renown(law_world, ALPHA, fame=125, infamy=450)
    as_user(USER_ALPHA)
    resp = api.get(f"/characters/{ALPHA}/renown")
    assert resp.status_code == 200
    assert resp.json() == {
        "fame": {"tier_code": "familiar", "tier_name": "Знакомое имя", "progress": 0.5,
                 "next_tier_name": "Известный"},
        "rumors": {"tier_code": "rumored", "tier_name": "О вас ходят слухи"},
    }
    assert "125" not in resp.text and "450" not in resp.text


def test_private_renown_without_a_row(api, law_world):
    as_user(USER_ALPHA)
    body = api.get(f"/characters/{ALPHA}/renown").json()
    assert body["fame"]["tier_code"] == "nameless" and body["rumors"]["tier_code"] == "none"


def test_private_renown_access(api, law_world):
    as_user(USER_BETA)
    assert api.get(f"/characters/{ALPHA}/renown").status_code == 403
    as_user(USER_BETA, "editor", ["characters:read"])                   # not a privileged role
    assert api.get(f"/characters/{ALPHA}/renown").status_code == 403
    as_moderator()                                                      # staff with characters:read
    assert api.get(f"/characters/{ALPHA}/renown").status_code == 200
    as_user(USER_ALPHA)
    assert api.get("/characters/99999/renown").status_code == 404


def test_private_renown_requires_auth(api, law_world):
    app.dependency_overrides.pop(main.get_current_user_via_http, None)
    assert api.get(f"/characters/{ALPHA}/renown").status_code == 401


def test_fame_tiers_public_has_names_only(api, law_world):
    resp = api.get("/characters/renown/fame-tiers")
    assert resp.status_code == 200
    assert resp.json()[0] == {"code": "nameless", "name": "Безвестный", "sort_order": 1}
    assert len(resp.json()) == 5 and "min_value" not in resp.text and "witness" not in resp.text
    assert "О вас" not in resp.text                                     # no infamy tiers


def test_public_passport_shows_fame_tier_only(api, law_world, monkeypatch):
    monkeypatch.setattr(main.httpx, "get", MagicMock(side_effect=RuntimeError("no user-service in tests")))
    set_renown(law_world, ALPHA, fame=650, infamy=3000)
    resp = api.get(f"/characters/{ALPHA}/public")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fame_tier_code"] == "famous" and body["fame_tier_name"] == "Знаменитый"
    assert "infamy" not in resp.text and "rumors" not in resp.text and "dreaded" not in resp.text
    assert "650" not in resp.text and "3000" not in resp.text
    other = api.get(f"/characters/{BETA}/public").json()
    assert other["fame_tier_code"] == "nameless" and other["fame_tier_name"] == "Безвестный"


@pytest.fixture
def econ_api(api, law_world):
    def override():
        s = law_world()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[economy_api.get_db] = override
    yield api
    app.dependency_overrides.pop(economy_api.get_db, None)


def test_region_card_suspicion_text_only(econ_api, law_world):
    resp = econ_api.get(f"/characters/economy/regions/{R_OST}/card")
    assert resp.status_code == 200, resp.text
    assert resp.json()["suspicion"] is None
    set_suspicion(law_world, R_OST, 27)
    body = econ_api.get(f"/characters/economy/regions/{R_OST}/card").json()
    assert body["suspicion"] == {"code": "uneasy", "label": "В крае неспокойно"}
    assert "27" not in str(body["suspicion"])
    set_suspicion(law_world, R_OST, 85)
    assert econ_api.get(f"/characters/economy/regions/{R_OST}/card").json()["suspicion"]["code"] == "fear"


def test_region_card_invalid_region_has_null_suspicion(econ_api):
    assert econ_api.get("/characters/economy/regions/0/card").json()["suspicion"] is None


def test_player_law_state_has_no_crime_list_or_infamy_number(api, law_world):
    make_deferred(law_world)
    as_user(USER_ALPHA)
    resp = api.get(f"/characters/{ALPHA}/law")
    assert resp.status_code == 200
    text_ = resp.text
    assert "unwitnessed" not in text_ and "witness" not in text_ and "reveal" not in text_
    assert "infamy" not in text_


# =============================================================================================== law admin card

def test_admin_character_card_has_snapshot_and_renown(api, law_world):
    cid = make_deferred(law_world, masked=True)
    as_moderator()
    resp = api.get(f"/characters/admin/law/characters/{ALPHA}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    item = [c for c in body["crimes"] if c["id"] == cid][0]
    for key in ("status", "masked", "witness_chance_pct", "witness_roll_pct", "reputation_delta", "wanted_floor",
                "reveal_attempts", "next_roll_at", "reveal_until", "revealed_at"):
        assert key in item, key
    assert item["status"] == "masked" and item["masked"] is True
    assert body["renown"] == {"fame": 0, "fame_tier_name": "Безвестный", "infamy": 150,
                              "infamy_tier_name": "Шёпот в тавернах"}
    assert body["renown_log"][0]["scale"] == "infamy" and body["renown_log"][0]["source"] == "crime"
    assert crime(law_world, cid)["status"] == "masked"
