"""FEAT-197 QA (task 9): reputation HTTP API (contract §3.5) on SQLite.

Player endpoints: private access (owner / staff with characters:read), no numbers in payloads.
Admin endpoints: RBAC reputation:read / manage / settings (moderator = read + manage, §3.14 A3).
Internal apply: X-Internal-Token, retry-safe. RabbitMQ is never touched (``reputation_notify._send`` recorder).
"""

import re
import uuid

import pytest
from fastapi.testclient import TestClient

import auth_http
import main
import reputation_api
import reputation_core as rc
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.reputation_world import (  # noqa: F401  (rep_world is a fixture)
    ALPHA, BETA, GAMMA, MERCHANT, R_DUNY, R_HOLMY, R_OST, R_PASHNI, USER_ALPHA, USER_BETA, apply, log_rows, q,
    rep_world, sent_payloads, set_value, value, values,
)

TOKEN = "test-internal-token"
INTERNAL = {"X-Internal-Token": TOKEN}
ALL_REP = ["reputation:read", "reputation:manage", "reputation:settings"]


@pytest.fixture
def api(rep_world, monkeypatch):
    def override_get_db():
        session = rep_world()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[reputation_api.get_db] = override_get_db
    app.dependency_overrides[main.get_db] = override_get_db
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    yield TestClient(app, raise_server_exceptions=False)
    for dep in (reputation_api.get_db, main.get_db, get_current_user_via_http):
        app.dependency_overrides.pop(dep, None)


def as_user(user_id=USER_ALPHA, role="user", permissions=()):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username=f"u{user_id}", role=role, permissions=list(permissions))


def as_admin():
    as_user(1, "admin", ALL_REP + ["characters:read"])


def as_moderator():
    as_user(2, "moderator", ["reputation:read", "reputation:manage", "characters:read"])


def _adjust(api, body, cid=ALPHA):
    payload = {"region_id": R_OST, "reason": "Награда за помощь", "request_id": str(uuid.uuid4())}
    payload.update(body)
    return api.post(f"/characters/admin/reputation/characters/{cid}/adjust", json=payload)


def _no_value_numbers(obj):
    """No key of the player payload may carry a reputation number."""
    forbidden = {"value", "delta", "applied_delta", "requested_delta", "value_after", "reason", "points",
                 "min_value", "max_value", "event_key", "actor_user_id"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in forbidden, k
            _no_value_numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_value_numbers(v)


# =============================================================================================== player

def test_player_view_lists_visited_regions_without_numbers(api, rep_world):
    set_value(rep_world, ALPHA, R_OST, 350)
    set_value(rep_world, ALPHA, R_DUNY, -650)
    as_user(USER_ALPHA)
    resp = api.get(f"/characters/{ALPHA}/reputation")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    _no_value_numbers(data)
    by_region = {r["region_id"]: r for r in data["regions"]}
    assert set(by_region) == {R_OST, R_DUNY}
    assert by_region[R_OST] == {"region_id": R_OST, "region_name": "Ост", "country_id": 1,
                                "country_name": "Мидденгерд", "tier_code": "trusted", "tier_name": "Свой человек",
                                "progress": round(50 / 300, 3), "trade_refused": False}
    assert by_region[R_DUNY]["tier_code"] == "outlaw" and by_region[R_DUNY]["trade_refused"] is True
    assert [t["code"] for t in data["tiers"]] == list(rc.TIER_CODES)
    assert set(data["tiers"][0]) == {"code", "name", "sort_order"}
    assert "350" not in resp.text and "650" not in resp.text


def test_player_view_one_region_defaults_to_wanderer(api, rep_world):
    as_user(USER_ALPHA)
    data = api.get(f"/characters/{ALPHA}/reputation", params={"region_id": R_HOLMY}).json()
    assert len(data["regions"]) == 1
    assert (data["regions"][0]["tier_code"], data["regions"][0]["progress"]) == ("wanderer", 0.497)
    assert api.get(f"/characters/{ALPHA}/reputation", params={"region_id": 999}).status_code == 404
    assert api.get(f"/characters/{ALPHA}/reputation", params={"region_id": 0}).status_code == 422


def test_player_view_applies_lazy_decay(api, rep_world):
    from tests.reputation_world import days_ago
    set_value(rep_world, ALPHA, R_DUNY, -650, decay_at=days_ago(10))         # effective -550 -> outcast
    as_user(USER_ALPHA)
    regions = api.get(f"/characters/{ALPHA}/reputation").json()["regions"]
    assert regions[0]["tier_code"] == "outcast"


def test_player_view_access(api, rep_world):
    as_user(USER_BETA)                                                     # another player
    assert api.get(f"/characters/{ALPHA}/reputation").status_code == 403
    assert api.get(f"/characters/{ALPHA}/reputation/history").status_code == 403
    as_user(2, "moderator", ["reputation:read"])                           # staff without characters:read
    assert api.get(f"/characters/{ALPHA}/reputation").status_code == 403
    as_user(3, "editor", ["characters:read"])                              # not a privileged role
    assert api.get(f"/characters/{ALPHA}/reputation").status_code == 403
    as_moderator()
    assert api.get(f"/characters/{ALPHA}/reputation").status_code == 200
    as_admin()
    assert api.get(f"/characters/{ALPHA}/reputation/history").status_code == 200
    assert api.get("/characters/999/reputation").status_code == 404
    assert api.get("/characters/999/reputation/history").status_code == 404


def test_player_view_of_an_npc_is_empty(api, rep_world):
    as_user(USER_ALPHA)
    data = api.get(f"/characters/{MERCHANT}/reputation").json()
    assert data["regions"] == [] and len(data["tiers"]) == 8


def test_player_view_requires_auth(rep_world):
    def override_get_db():
        s = rep_world()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[reputation_api.get_db] = override_get_db
    try:
        resp = TestClient(app).get(f"/characters/{ALPHA}/reputation")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(reputation_api.get_db, None)


def test_player_history_phrases_only(api, rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="q1")
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="a1", delta=-300,
          reason="Секретная причина 42", actor_user_id=1, echo=False)
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="z", delta=0)
    as_user(USER_ALPHA)
    resp = api.get(f"/characters/{ALPHA}/reputation/history")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    _no_value_numbers(data)
    assert data["total"] == 4
    items = data["items"]
    texts = [i["text"] for i in items]
    assert "Жители края «Ост» стали относиться к вам хуже" in texts
    assert "Жители края «Ост» стали относиться к вам лучше" in texts
    assert "До жителей края «Пашни» дошли слухи о вас — к вам стали относиться лучше" in texts
    for i in items:
        assert set(i) == {"created_at", "region_id", "region_name", "direction", "action_name", "text",
                          "tier_after_name", "tier_changed"}
        assert not any(ch.isdigit() for ch in i["text"] + i["action_name"] + i["tier_after_name"])
    assert "Секретная" not in resp.text and "300" not in resp.text
    down = next(i for i in items if i["direction"] == "down")
    assert down["action_name"] == "Решение властей" and down["tier_changed"] is True
    assert down["tier_after_name"] == "На заметке"                          # 10 - 300 = -290


def test_player_history_shows_decay_phrase(api, rep_world):
    from tests.reputation_world import days_ago
    set_value(rep_world, ALPHA, R_DUNY, -100, decay_at=days_ago(3))
    apply(rep_world, character_id=ALPHA, region_id=R_DUNY, action=rc.ACTION_QUEST, idem_key="q")
    as_user(USER_ALPHA)
    items = api.get(f"/characters/{ALPHA}/reputation/history", params={"region_id": R_DUNY}).json()["items"]
    decay = [i for i in items if i["action_name"] == rc.DECAY_ACTION_NAME]
    assert len(decay) == 1 and decay[0]["text"] == "Жители края «Дюны» понемногу забывают ваши проступки"
    assert decay[0]["direction"] == "up"


def test_player_history_paging_and_limits(api, rep_world):
    for i in range(5):
        apply(rep_world, character_id=GAMMA, region_id=R_DUNY, action=rc.ACTION_QUEST, idem_key=f"q{i}")
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(id=9, username="g", role="user",
                                                                           permissions=[])
    page = api.get(f"/characters/{GAMMA}/reputation/history", params={"page": 2, "page_size": 2}).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    assert api.get(f"/characters/{GAMMA}/reputation/history", params={"page_size": 51}).status_code == 422
    assert api.get(f"/characters/{GAMMA}/reputation/history", params={"page": 0}).status_code == 422


# =============================================================================================== admin RBAC

ADMIN_ROUTES = [
    ("get", "/characters/admin/reputation/settings", None, "reputation:read"),
    ("get", "/characters/admin/reputation/actions", None, "reputation:read"),
    ("get", "/characters/admin/reputation/npc-roles", None, "reputation:read"),
    ("get", f"/characters/admin/reputation/characters/{ALPHA}", None, "reputation:read"),
    ("get", f"/characters/admin/reputation/characters/{ALPHA}/history", None, "reputation:read"),
    ("post", "/characters/admin/reputation/actions", {"code": "bribe", "name": "Взятка", "points": -20},
     "reputation:settings"),
    ("put", "/characters/admin/reputation/actions/crime", {"name": "Преступление", "points": -60},
     "reputation:settings"),
    ("delete", "/characters/admin/reputation/actions/whatever", None, "reputation:settings"),
    ("put", "/characters/admin/reputation/npc-roles", [{"role": "*", "points": -150}], "reputation:settings"),
    ("post", f"/characters/admin/reputation/characters/{ALPHA}/adjust",
     {"region_id": R_OST, "delta": 5, "reason": "Проверка", "request_id": str(uuid.uuid4())}, "reputation:manage"),
]


@pytest.mark.parametrize("method,url,body,perm", ADMIN_ROUTES)
def test_admin_routes_need_their_permission(api, method, url, body, perm):
    others = [p for p in ALL_REP if p != perm] + ["characters:read", "economy:settings"]
    as_user(5, "moderator", others)
    kwargs = {"json": body} if body is not None else {}
    resp = getattr(api, method)(url, **kwargs)
    assert resp.status_code == 403, (url, resp.text)
    assert resp.json()["detail"] == "Недостаточно прав"
    as_user(5, "moderator", [perm])
    resp = getattr(api, method)(url, **kwargs)
    assert resp.status_code != 403, (url, resp.text)


def test_admin_routes_require_auth(rep_world):
    def override_get_db():
        s = rep_world()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[reputation_api.get_db] = override_get_db
    try:
        assert TestClient(app).get("/characters/admin/reputation/settings").status_code == 401
    finally:
        app.dependency_overrides.pop(reputation_api.get_db, None)


def test_moderator_can_adjust_but_not_edit_settings(api):
    as_moderator()
    assert _adjust(api, {"delta": 10}).status_code == 200
    body = api.get("/characters/admin/reputation/settings").json()
    assert api.put("/characters/admin/reputation/settings", json=body).status_code == 403
    assert api.put("/characters/admin/reputation/npc-roles", json=[{"role": "*", "points": 1}]).status_code == 403


# =============================================================================================== admin settings

def test_settings_roundtrip_and_validation(api, rep_world):
    as_admin()
    body = api.get("/characters/admin/reputation/settings").json()
    assert body["settings"] == {"min_value": -1000, "max_value": 1000, "echo_pct": 20.0, "decay_per_day": 10.0}
    assert [(t["code"], t["min_value"], t["price_pct"], t["sell_pct"], t["trade_refused"]) for t in body["tiers"]] \
        == [("outlaw", None, 0.0, 0.0, True), ("outcast", -599, -25.0, -25.0, False),
            ("watched", -299, -10.0, -10.0, False), ("wanderer", -99, 0.0, 0.0, False),
            ("familiar", 100, 0.0, 0.0, False), ("trusted", 300, 5.0, 0.0, False),
            ("defender", 600, 10.0, 0.0, False), ("legend", 900, 15.0, 0.0, False)]
    body["settings"]["echo_pct"] = 50
    body["tiers"][7]["name"] = "Свет края"
    body["tiers"][5]["min_value"] = 250
    resp = api.put("/characters/admin/reputation/settings", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"]["echo_pct"] == 50.0 and resp.json()["tiers"][7]["name"] == "Свет края"
    # the stored tiers are used from now on
    set_value(rep_world, ALPHA, R_OST, 260)
    as_user(USER_ALPHA)
    assert api.get(f"/characters/{ALPHA}/reputation").json()["regions"][0]["tier_code"] == "trusted"
    as_admin()
    apply(rep_world, character_id=BETA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="e50")
    assert values(rep_world, BETA) == {R_OST: 10, R_PASHNI: 5, R_HOLMY: 5}         # echo 50 %

    bad = api.get("/characters/admin/reputation/settings").json()
    bad["tiers"][4]["min_value"] = 5000
    resp = api.put("/characters/admin/reputation/settings", json=bad)
    assert resp.status_code == 400 and "Пороги" in resp.json()["detail"]
    bad = api.get("/characters/admin/reputation/settings").json()
    bad["tiers"] = bad["tiers"][:7]
    assert api.put("/characters/admin/reputation/settings", json=bad).status_code == 422
    bad = api.get("/characters/admin/reputation/settings").json()
    bad["tiers"][2]["code"] = "hacker'; --"
    assert api.put("/characters/admin/reputation/settings", json=bad).status_code == 400
    bad = api.get("/characters/admin/reputation/settings").json()
    bad["tiers"][0]["name"] = "x" * 61
    assert api.put("/characters/admin/reputation/settings", json=bad).status_code == 422


def test_decay_rate_change_is_not_retroactive(api, rep_world):
    from tests.reputation_world import days_ago
    set_value(rep_world, ALPHA, R_DUNY, -500, decay_at=days_ago(10))          # 100 points accrued at 10/day
    as_admin()
    body = api.get("/characters/admin/reputation/settings").json()
    body["settings"]["decay_per_day"] = 100
    assert api.put("/characters/admin/reputation/settings", json=body).status_code == 200
    assert value(rep_world, ALPHA, R_DUNY) == -400                              # materialised with the OLD rate
    assert [x[2] for x in log_rows(rep_world, ALPHA)] == ["decay"]


def test_actions_crud(api, rep_world):
    as_admin()
    actions = {a["code"]: a for a in api.get("/characters/admin/reputation/actions").json()}
    assert set(rc.BUILTIN_ACTION_CODES) <= set(actions)
    assert (actions["guild_delivery"]["points"], actions["guild_delivery"]["daily_cap"]) == (2, 20)
    assert all(actions[c]["is_builtin"] for c in rc.BUILTIN_ACTION_CODES)

    resp = api.post("/characters/admin/reputation/actions", json={"code": "bribe", "name": " Взятка ", "points": -20})
    assert resp.status_code == 201 and resp.json()["name"] == "Взятка" and resp.json()["is_builtin"] is False
    assert api.post("/characters/admin/reputation/actions",
                    json={"code": "bribe", "name": "Дубль", "points": 1}).status_code == 409
    assert api.post("/characters/admin/reputation/actions",
                    json={"code": "crime", "name": "Дубль", "points": 1}).status_code == 409   # builtin code
    for bad in ({"code": "x'; DROP TABLE reputation_log; --", "name": "a", "points": 1},
                {"code": "ok_code", "name": " ", "points": 1},
                {"code": "ok_code", "name": "a" * 101, "points": 1},
                {"code": "ok_code", "name": "a", "points": 1001},
                {"code": "ok_code", "name": "a", "points": 1, "daily_cap": 0}):
        assert api.post("/characters/admin/reputation/actions", json=bad).status_code == 422, bad

    resp = api.put("/characters/admin/reputation/actions/quest_complete",
                   json={"name": "Выполнено задание", "points": 15})
    assert resp.status_code == 200 and resp.json()["points"] == 15
    apply(rep_world, character_id=GAMMA, region_id=R_DUNY, action=rc.ACTION_QUEST, idem_key="q15")
    assert value(rep_world, GAMMA, R_DUNY) == 15
    assert api.put("/characters/admin/reputation/actions/nope", json={"name": "a", "points": 1}).status_code == 404

    assert api.delete("/characters/admin/reputation/actions/quest_complete").status_code == 409
    assert api.delete("/characters/admin/reputation/actions/bribe").status_code == 204
    assert api.delete("/characters/admin/reputation/actions/bribe").status_code == 404


def test_npc_roles_replace(api, rep_world):
    as_admin()
    roles = {r["role"]: r["points"] for r in api.get("/characters/admin/reputation/npc-roles").json()}
    assert roles == rc.DEFAULT_NPC_ROLE_WEIGHTS
    assert api.put("/characters/admin/reputation/npc-roles",
                   json=[{"role": "bandit", "points": 5}]).status_code == 400            # '*' required
    assert api.put("/characters/admin/reputation/npc-roles",
                   json=[{"role": "*", "points": 1}, {"role": "*", "points": 2}]).status_code == 400
    assert api.put("/characters/admin/reputation/npc-roles",
                   json=[{"role": "*", "points": 1}, {"role": "Guard' OR 1=1", "points": 2}]).status_code == 422
    resp = api.put("/characters/admin/reputation/npc-roles",
                   json=[{"role": "bandit", "points": 5}, {"role": "*", "points": -77}])
    assert resp.status_code == 200
    assert resp.json() == [{"role": "bandit", "points": 5}, {"role": "*", "points": -77}]


# =============================================================================================== admin character

def test_admin_character_view_and_history_have_numbers(api, rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="q")
    as_admin()
    resp = api.get(f"/characters/admin/reputation/characters/{ALPHA}")
    assert resp.status_code == 200
    by_region = {r["region_id"]: r for r in resp.json()}
    assert by_region[R_OST]["value"] == 10 and by_region[R_PASHNI]["value"] == 2
    assert by_region[R_OST]["decaying"] is False
    hist = api.get(f"/characters/admin/reputation/characters/{ALPHA}/history").json()
    assert hist["total"] == 3
    echo = next(i for i in hist["items"] if i["is_echo"])
    assert echo["origin_region_id"] == R_OST and echo["origin_region_name"] == "Ост"
    assert api.get("/characters/admin/reputation/characters/999").status_code == 404


def test_adjust_success_reason_actor_and_no_echo_by_default(api, rep_world):
    as_moderator()
    resp = _adjust(api, {"delta": 120, "reason": "  Спас деревню  "})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"duplicate": False, "changes": [
        {"region_id": R_OST, "is_echo": False, "value_before": 0, "value_after": 120, "tier_before": "wanderer",
         "tier_after": "familiar"}]}
    assert values(rep_world, ALPHA) == {R_OST: 120}
    log = log_rows(rep_world, ALPHA)
    assert (log[0][2], log[0][11], log[0][12]) == ("admin_manual", "Спас деревню", 2)
    assert log[0][3].startswith("admin:2:")
    # tier change published once to the owner
    payloads = sent_payloads(rep_world)
    assert [p["target_value"] for p in payloads] == [USER_ALPHA]
    as_admin()
    item = api.get(f"/characters/admin/reputation/characters/{ALPHA}/history").json()["items"][0]
    assert (item["reason"], item["actor_user_id"], item["applied_delta"]) == ("Спас деревню", 2, 120)


def test_adjust_with_echo_and_action_code(api, rep_world):
    as_admin()
    resp = _adjust(api, {"action_code": "crime", "echo": True})
    assert resp.status_code == 200
    assert values(rep_world, ALPHA) == {R_OST: -50, R_PASHNI: -10, R_HOLMY: -10}
    assert _adjust(api, {"action_code": "npc_kill"}).status_code == 400          # 0 points
    assert _adjust(api, {"action_code": "no_such"}).status_code == 404


def test_adjust_is_idempotent_by_request_id(api, rep_world):
    as_admin()
    rid = str(uuid.uuid4())
    assert _adjust(api, {"delta": 50, "request_id": rid}).json()["duplicate"] is False
    resp = _adjust(api, {"delta": 50, "request_id": rid})
    assert resp.status_code == 200 and resp.json() == {"changes": [], "duplicate": True}
    assert value(rep_world, ALPHA, R_OST) == 50
    # the same request id from ANOTHER staff member is another key
    as_moderator()
    assert _adjust(api, {"delta": 50, "request_id": rid}).json()["duplicate"] is False


@pytest.mark.parametrize("body", [
    {"delta": 5, "reason": None},
    {"delta": 5, "reason": "  ab  "},
    {"delta": 5, "reason": "я" * 501},
    {"delta": 5, "action_code": "crime"},
    {},
    {"delta": 0},
    {"delta": 2001},
    {"delta": -2001},
    {"delta": 5, "request_id": "not-a-uuid"},
    {"delta": 5, "region_id": 0},
    {"action_code": "   "},
])
def test_adjust_validation(api, rep_world, body):
    as_admin()
    payload = {"region_id": R_OST, "reason": "Причина", "request_id": str(uuid.uuid4())}
    payload.update(body)
    if payload.get("reason") is None:
        payload.pop("reason")
    resp = api.post(f"/characters/admin/reputation/characters/{ALPHA}/adjust", json=payload)
    assert resp.status_code == 422, resp.text
    assert q(rep_world, "SELECT COUNT(*) FROM reputation_log") == 0


def test_adjust_refuses_npc_and_unknowns(api, rep_world):
    as_admin()
    resp = _adjust(api, {"delta": 5}, cid=MERCHANT)
    assert resp.status_code == 400 and resp.json()["detail"] == "У NPC нет репутации"
    assert _adjust(api, {"delta": 5}, cid=999).status_code == 404
    assert _adjust(api, {"delta": 5, "region_id": 999}).status_code == 404


def test_adjust_reason_with_markup_is_stored_verbatim_not_executed(api, rep_world):
    as_admin()
    reason = "<script>alert(1)</script>'; DROP TABLE characters; --"
    assert _adjust(api, {"delta": 5, "reason": reason}).status_code == 200
    assert log_rows(rep_world, ALPHA)[0][11] == reason
    assert q(rep_world, "SELECT COUNT(*) FROM characters") == 10


# =============================================================================================== internal

def _internal(api, body=None, headers=INTERNAL):
    payload = {"character_id": ALPHA, "region_id": R_OST, "action": "quest_complete",
               "idempotency_key": "quest_reward:cq:77"}
    payload.update(body or {})
    return api.post("/characters/internal/reputation/apply", json=payload, headers=headers)


def test_internal_apply_needs_the_token(api, rep_world):
    assert _internal(api, headers={}).status_code == 401
    assert _internal(api, headers={"X-Internal-Token": "wrong"}).status_code == 401
    assert q(rep_world, "SELECT COUNT(*) FROM reputation_log") == 0


def test_internal_apply_is_retry_safe(api, rep_world):
    resp = _internal(api)
    assert resp.status_code == 200 and resp.json() == {"applied": True, "duplicate": False, "skipped": None}
    resp = _internal(api)
    assert resp.json() == {"applied": False, "duplicate": True, "skipped": None}
    assert values(rep_world, ALPHA) == {R_OST: 10, R_PASHNI: 2, R_HOLMY: 2}


def test_internal_apply_custom_delta_skips_and_errors(api, rep_world):
    assert _internal(api, {"delta": -40, "idempotency_key": "k1"}).json()["applied"] is True
    assert value(rep_world, ALPHA, R_OST) == -40
    assert _internal(api, {"character_id": MERCHANT, "idempotency_key": "k2"}).json()["skipped"] == "npc"
    assert _internal(api, {"delta": 0, "idempotency_key": "k3"}).json()["skipped"] == "zero"
    assert _internal(api, {"region_id": 999, "idempotency_key": "k4"}).status_code == 404
    assert _internal(api, {"action": "nope", "idempotency_key": "k5"}).status_code == 404
    assert _internal(api, {"character_id": 999, "idempotency_key": "k6"}).status_code == 404
    assert _internal(api, {"idempotency_key": "k" * 192}).status_code == 422
    assert _internal(api, {"reason": "r" * 501, "idempotency_key": "k7"}).status_code == 422
    assert _internal(api, {"delta": 2001, "idempotency_key": "k8"}).status_code == 422


def test_internal_apply_publishes_tier_change_after_commit(api, rep_world):
    assert _internal(api, {"delta": 150}).status_code == 200
    payloads = sent_payloads(rep_world)
    assert payloads == [{"target_type": "user", "target_value": USER_ALPHA, "category": "progress",
                         "message": "Жители края «Ост» теперь считают вас: Знакомое лицо"}]
    rep_world.sent.reset_mock()
    _internal(api, {"delta": 1, "idempotency_key": "small"})
    assert rep_world.sent.call_count == 0


def test_internal_apply_survives_a_rabbit_outage(api, rep_world, monkeypatch):
    import reputation_notify

    def boom(_p):
        raise ConnectionError("down")

    monkeypatch.setattr(reputation_notify, "_send", boom)
    assert _internal(api, {"delta": 150}).status_code == 200
    assert value(rep_world, ALPHA, R_OST) == 150


def test_paths_do_not_shadow_each_other():
    """The reputation router is mounted before the main router; static admin paths must not hit
    /characters/{character_id}/... patterns."""
    paths = [r.path for r in app.routes]
    assert paths.index("/characters/admin/reputation/settings") < paths.index("/characters/{character_id}/reputation")
    assert re.search(r"/characters/internal/reputation/apply", " ".join(paths))
