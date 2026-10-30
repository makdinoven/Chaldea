"""FEAT-187 B4: region events admin & public API (contract 3.7 / 3.8) on SQLite.

Covers every endpoint (happy path + refusals + RBAC): templates list / create / update / delete, active list, manual
start (scope expansion, skips, request_id), cancel, history filters + pagination, the region card ``events`` (both
shapes), ``active_events`` in the admin regions list and the events counters of the runs list.

World: country 1 — regions 10 «Столица» (capital), 20 «Гавань» (port), 30 «Нива» (agrarian); 40 «Глушь» without
economy (not participating); country 2 — region 50 «Застава» (fortress). The 14 starter templates of migration 033.
"""

import importlib.util
import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core as core
import economy_api
import economy_events_crud as ev_crud
import locations_client
import models
from auth_http import UserRead, get_current_user_via_http
from main import app

VERSIONS = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _load(filename, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(VERSIONS, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig028 = _load("028_econ_living_regions.py", "migration_028_for_events_admin")
mig033 = _load("033_econ_region_events.py", "migration_033_for_events_admin")

BASE = "/characters/admin/economy"
EVENTS = f"{BASE}/events"
ALL_PERMS = ["economy:read", "economy:emit", "economy:adjust", "economy:settings"]
COMMENT = "Отмена для теста"


@pytest.fixture
def engine(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=eng)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    db = factory()
    for i, g in enumerate(mig028.GROUPS, 1):
        db.add(models.EconGoodsGroup(code=g[0], name=g[1], sort_order=i, base_price=g[2], norm_per_1000=g[3],
                                     norm_days=g[4], prosperity_elasticity=g[5], price_elasticity=g[6],
                                     is_food=bool(g[7])))
    for i, t in enumerate(mig028.TEMPLATES, 1):
        db.add(models.EconRegionTemplate(code=t[0], name=t[1], description=t[2], settlement_noun=t[3],
                                         noun_gender=t[4], default_population=t[5], tax_rate=t[6], sort_order=i))
    db.flush()
    for t in mig028.TEMPLATES:
        for group_code, prod, cmult in mig028.template_goods(t[0]):
            db.add(models.EconTemplateGood(template_code=t[0], group_code=group_code, production_per_1000=prod,
                                           consumption_mult=cmult))
    db.add(models.EconSimSettings(id=1, tick_enabled=True, params=dict(mig028.DEFAULT_PARAMS)))
    for t in mig033.EVENT_TEMPLATES:
        db.add(models.EconEventTemplate(**t))
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд'), (2, 'Север')"))
    db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Столица', 1), (20, 'Гавань', 1), "
                    "(30, 'Нива', 1), (40, 'Глушь', 1), (50, 'Застава', 2)"))
    for region_id, template, population in ((10, "capital", 5000), (20, "port", 3000), (30, "agrarian", 4000),
                                            (50, "fortress", 2000)):
        db.add(models.EconRegion(region_id=region_id, template_code=template, population=population, tax_rate=0.1))
    db.commit()
    db.close()

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    monkeypatch.setattr(locations_client, "get_game_segment_sync", lambda: "summer")
    core.invalidate_settings_cache()
    eng.factory = factory
    yield eng
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)
    core.invalidate_settings_cache()
    eng.dispose()


def _as_user(permissions, user_id=7):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username="tester", role="admin", permissions=list(permissions))


@pytest.fixture
def api(engine):
    _as_user(ALL_PERMS)
    return TestClient(app)


def _templates(api):
    resp = api.get(f"{EVENTS}/templates")
    assert resp.status_code == 200, resp.text
    return {t["code"]: t for t in resp.json()}


def _tid(api, code):
    return _templates(api)[code]["id"]


def _start(api, code, region_id, **body):
    return api.post(f"{EVENTS}/start", json={"template_id": _tid(api, code), "region_id": region_id, **body})


def _template_body(**over):
    body = {
        "code": "quake", "name": "Землетрясение", "icon": "zap", "kind": "bad",
        "player_text": "Земля дрожит, дома рушатся.", "admin_note": None, "trigger_kind": "random", "weight": 1,
        "duration_min_days": 2, "duration_max_days": 4, "scope": "region", "spread_chance": 0.1,
        "region_templates": ["mining"], "seasons": ["summer"],
        "effects": [{"type": "production", "groups": ["ore_metal"], "mult": 0.5}, {"type": "merchants_halt"},
                    {"type": "population", "pct": -0.01}],
        "chains": [{"code": "plague", "chance": 0.2}], "is_enabled": True,
    }
    body.update(over)
    return body


# --------------------------------------------------------------------------------------------- RBAC

def test_rbac_401_without_token(engine):
    client = TestClient(app)
    assert client.get(f"{EVENTS}/templates").status_code == 401
    assert client.post(f"{EVENTS}/start", json={"template_id": 1, "region_id": 10}).status_code == 401


def test_rbac_moderator_reads_but_cannot_write(api):
    _as_user(["economy:read"])
    assert api.get(f"{EVENTS}/templates").status_code == 200
    assert api.get(f"{EVENTS}/active").status_code == 200
    assert api.get(f"{EVENTS}/history").status_code == 200
    assert api.post(f"{EVENTS}/templates", json=_template_body()).status_code == 403
    assert api.put(f"{EVENTS}/templates/1", json=_template_body()).status_code == 403
    assert api.delete(f"{EVENTS}/templates/1").status_code == 403
    assert api.post(f"{EVENTS}/start", json={"template_id": 1, "region_id": 10}).status_code == 403
    assert api.post(f"{EVENTS}/1/cancel", json={"comment": COMMENT}).status_code == 403


def test_rbac_no_economy_permission(api):
    _as_user([])
    assert api.get(f"{EVENTS}/templates").status_code == 403
    assert api.get(f"{EVENTS}/history").status_code == 403


# --------------------------------------------------------------------------------------------- templates

def test_templates_list_seeded_ordered(api):
    resp = api.get(f"{EVENTS}/templates")
    items = resp.json()
    assert len(items) == 14
    kinds = [t["kind"] for t in items]
    assert kinds == sorted(kinds)                     # bad before good
    drought = next(t for t in items if t["code"] == "drought")
    assert drought["name"] == "Засуха" and drought["active_count"] == 0
    assert drought["chains"] == [{"code": "livestock", "chance": 0.15}]
    assert drought["seasons"] == ["summer", "lughnasad"]
    assert drought["weight"] == 3.0 and drought["duration_min_days"] == 6.0


def test_template_create_and_update(api):
    resp = api.post(f"{EVENTS}/templates", json=_template_body())
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["code"] == "quake" and data["active_count"] == 0
    assert data["effects"] == [{"type": "production", "groups": ["ore_metal"], "mult": 0.5},
                               {"type": "merchants_halt"}, {"type": "population", "pct": -0.01}]
    body = _template_body(name="Сильное землетрясение", is_enabled=False, chains=[])
    body.pop("code")
    resp = api.put(f"{EVENTS}/templates/{data['id']}", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Сильное землетрясение" and resp.json()["is_enabled"] is False
    assert resp.json()["code"] == "quake"


def test_template_code_is_immutable(api):
    tid = _tid(api, "drought")
    body = _templates(api)["drought"]
    for key in ("id", "active_count", "updated_at"):
        body.pop(key)
    body["code"] = "renamed"
    resp = api.put(f"{EVENTS}/templates/{tid}", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == "drought"


def test_template_enable_toggle_round_trip(api):
    """The frontend PUTs the whole template it got from the list (stored effects round-trip)."""
    t = _templates(api)["fair"]
    body = {k: v for k, v in t.items() if k not in ("id", "code", "active_count", "updated_at")}
    body["is_enabled"] = False
    resp = api.put(f"{EVENTS}/templates/{t['id']}", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_enabled"] is False and resp.json()["effects"] == t["effects"]


@pytest.mark.parametrize("over, status, detail", [
    ({"code": "drought"}, 409, "Шаблон с кодом «drought» уже есть"),
    ({"effects": [{"type": "production", "groups": ["unobtainium"], "mult": 1.2}]}, 400,
     "Неизвестная группа товаров: unobtainium"),
    ({"region_templates": ["moon"]}, 400, "Неизвестный шаблон региона: moon"),
    ({"chains": [{"code": "nothing_here", "chance": 0.5}]}, 400,
     "Цепочка ссылается на неизвестное событие: nothing_here"),
    ({"chains": [{"code": "quake", "chance": 0.5}]}, 400, "Событие не может вызывать само себя"),
])
def test_template_create_refusals(api, over, status, detail):
    resp = api.post(f"{EVENTS}/templates", json=_template_body(**over))
    assert resp.status_code == status, resp.text
    assert resp.json()["detail"] == detail


@pytest.mark.parametrize("over", [
    {"effects": []},
    {"effects": [{"type": "labor", "mult": 2.0}]},                         # labor <= 1.5
    {"effects": [{"type": "price", "groups": ["food"], "mult": 0.1}]},     # price >= 0.2
    {"effects": [{"type": "loan_boom", "mult": 0.5}]},                     # loan_boom >= 1
    {"effects": [{"type": "stability", "delta": 1, "mult": 2}]},           # extra field
    {"effects": [{"type": "production", "mult": 2}]},                      # groups missing
    {"effects": [{"type": "population", "pct": 0.9}]},
    {"effects": [{"type": "volcano"}]},
    {"effects": [{"type": "merchants_halt", "foo": 1}]},
    {"icon": "rocket"},
    {"seasons": ["monsoon"]},
    {"duration_min_days": 5, "duration_max_days": 2},
    {"duration_min_days": 0},
    {"spread_chance": 1.5},
    {"weight": -1},
    {"code": "Bad Code"},
    {"code": "x' OR 1=1 --"},
    {"name": "x"},
    {"player_text": "a" * 501},
    {"chains": [{"code": "plague", "chance": 0.1}, {"code": "plague", "chance": 0.2}]},
    {"is_enabled": "yes"},
    {"effects": [{"type": "merchants_halt"}] * 13},
])
def test_template_validation_422(api, over):
    resp = api.post(f"{EVENTS}/templates", json=_template_body(**over))
    assert resp.status_code == 422, resp.text


def test_effect_messages_are_russian(api):
    resp = api.post(f"{EVENTS}/templates", json=_template_body(effects=[{"type": "stability", "delta": 1,
                                                                          "mult": 2}]))
    assert "Лишнее поле «mult» для эффекта «стабильность»" in resp.text
    resp = api.post(f"{EVENTS}/templates", json=_template_body(effects=[{"type": "labor", "mult": 2}]))
    assert "Для эффекта «больные жители» значение — от 0 до 1,5" in resp.text


def test_effect_null_extras_ignored_and_star_group(api):
    body = _template_body(effects=[{"type": "stability", "delta": -1, "mult": None, "groups": None},
                                   {"type": "consumption", "groups": ["food", "*"], "mult": 1.2}])
    resp = api.post(f"{EVENTS}/templates", json=body)
    assert resp.status_code == 201, resp.text
    assert resp.json()["effects"] == [{"type": "stability", "delta": -1.0},
                                      {"type": "consumption", "groups": ["*"], "mult": 1.2}]


def test_template_update_404_and_refusals(api):
    body = _template_body()
    body.pop("code")
    assert api.put(f"{EVENTS}/templates/99999", json=body).json()["detail"] == "Шаблон события не найден"
    tid = _tid(api, "flood")
    resp = api.put(f"{EVENTS}/templates/{tid}", json={**body, "chains": [{"code": "flood", "chance": 0.1}]})
    assert resp.status_code == 400 and resp.json()["detail"] == "Событие не может вызывать само себя"


def test_template_delete(api, engine):
    assert api.delete(f"{EVENTS}/templates/99999").status_code == 404
    # plague is referenced by flood's chain
    resp = api.delete(f"{EVENTS}/templates/{_tid(api, 'plague')}")
    assert resp.status_code == 409 and resp.json()["detail"] == "На это событие ссылаются цепочки: «Потоп»"
    # a running instance keeps its snapshot, template_id becomes NULL
    assert _start(api, "festival", 10, scope="region").status_code == 200
    resp = api.delete(f"{EVENTS}/templates/{_tid(api, 'festival')}")
    assert resp.status_code == 204, resp.text
    assert "festival" not in _templates(api)
    active = api.get(f"{EVENTS}/active").json()
    assert len(active) == 1 and active[0]["template_id"] is None and active[0]["name"] == "Праздник"


# --------------------------------------------------------------------------------------------- start / active

def test_start_single_region(api):
    resp = _start(api, "drought", 10, duration_days=2, request_id="req-00000001")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["skipped"] == []
    (ev,) = data["started"]
    assert ev["region_id"] == 10 and ev["region_name"] == "Столица" and ev["origin"] == "manual"
    assert ev["status"] == "active" and ev["started_by_user_id"] == 7 and ev["game_segment"] == "summer"
    started = datetime.fromisoformat(ev["started_at"])
    ends = datetime.fromisoformat(ev["ends_at"])
    assert ends - started == timedelta(days=2)
    assert _templates(api)["drought"]["active_count"] == 1
    active = api.get(f"{EVENTS}/active", params={"region_id": 10}).json()
    assert [e["id"] for e in active] == [ev["id"]]
    assert api.get(f"{EVENTS}/active", params={"region_id": 20}).json() == []


def test_start_country_scope_root_and_skips(api):
    assert _start(api, "festival", 20, scope="region").status_code == 200
    resp = _start(api, "festival", 10, scope="country")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    regions = [e["region_id"] for e in data["started"]]
    assert regions == [10, 30]                        # 20 already runs it, 40 does not participate, 50 abroad
    root = data["started"][0]
    assert root["root_event_id"] is None and data["started"][1]["root_event_id"] == root["id"]
    assert data["started"][0]["ends_at"] == data["started"][1]["ends_at"]
    assert data["skipped"] == [{"region_id": 20, "region_name": "Гавань",
                                "reason": "В регионе уже идёт «Праздник» — отмените его или дождитесь конца"}]


def test_start_world_scope(api):
    resp = _start(api, "magic_anomaly", 50, scope="world", duration_days=1)
    assert resp.status_code == 200
    assert sorted(e["region_id"] for e in resp.json()["started"]) == [10, 20, 30, 50]


def test_start_disabled_and_low_stability_templates_allowed(api):
    t = _templates(api)["harvest"]
    body = {k: v for k, v in t.items() if k not in ("id", "code", "active_count", "updated_at")}
    body["is_enabled"] = False
    assert api.put(f"{EVENTS}/templates/{t['id']}", json=body).status_code == 200
    assert _start(api, "harvest", 30).status_code == 200
    assert _start(api, "riot", 30).status_code == 200


def test_start_refusals(api):
    resp = api.post(f"{EVENTS}/start", json={"template_id": 99999, "region_id": 10})
    assert resp.status_code == 404 and resp.json()["detail"] == "Шаблон события не найден"
    resp = _start(api, "drought", 777)
    assert resp.status_code == 404 and resp.json()["detail"] == "Регион не найден"
    resp = _start(api, "drought", 40)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Регион не участвует в пересчёте — у него нет шаблона или населения"
    assert _start(api, "drought", 10).status_code == 200
    resp = _start(api, "drought", 10)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "В регионе уже идёт «Засуха» — отмените его или дождитесь конца"


def test_start_same_request_id_409(api):
    assert _start(api, "raid", 50, request_id="abcdef-12345").status_code == 200
    resp = _start(api, "drought", 10, request_id="abcdef-12345")
    assert resp.status_code == 200                    # another region -> another key
    resp = _start(api, "flood", 50, request_id="abcdef-12345")
    assert resp.status_code == 409 and resp.json()["detail"] == "Событие уже запущено"


@pytest.mark.parametrize("body", [
    {"region_id": 10},
    {"template_id": 1, "region_id": 0},
    {"template_id": 1, "region_id": 10, "scope": "galaxy"},
    {"template_id": 1, "region_id": 10, "duration_days": 0},
    {"template_id": 1, "region_id": 10, "duration_days": 400},
    {"template_id": 1, "region_id": 10, "request_id": "short"},
    {"template_id": 1, "region_id": 10, "request_id": "bad id; DROP TABLE x"},
])
def test_start_validation_422(api, body):
    assert api.post(f"{EVENTS}/start", json=body).status_code == 422


def test_start_after_expired_instance(api, engine):
    """An instance whose time is up (not yet ended by a tick) does not block a new start."""
    assert _start(api, "drought", 10, duration_days=1).status_code == 200
    with engine.begin() as conn:
        conn.execute(text("UPDATE econ_region_events SET started_at = :s, ends_at = :e"),
                     {"s": datetime.utcnow() - timedelta(days=3), "e": datetime.utcnow() - timedelta(days=2)})
    assert api.get(f"{EVENTS}/active").json() == []
    assert _start(api, "drought", 10).status_code == 200


# --------------------------------------------------------------------------------------------- cancel

def test_cancel(api):
    ev = _start(api, "plague", 20).json()["started"][0]
    resp = api.post(f"{EVENTS}/{ev['id']}/cancel", json={"comment": "  " + COMMENT + "  "})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "cancelled" and data["cancel_comment"] == COMMENT
    assert data["cancelled_by_user_id"] == 7 and data["ended_at"] is not None
    assert api.get(f"{EVENTS}/active").json() == []
    resp = api.post(f"{EVENTS}/{ev['id']}/cancel", json={"comment": COMMENT})
    assert resp.status_code == 409 and resp.json()["detail"] == "Событие уже закончилось"
    # cancelled -> the same template can run again
    assert _start(api, "plague", 20).status_code == 200


def test_cancel_refusals(api):
    resp = api.post(f"{EVENTS}/424242/cancel", json={"comment": COMMENT})
    assert resp.status_code == 404 and resp.json()["detail"] == "Событие не найдено"
    ev = _start(api, "plague", 20).json()["started"][0]
    assert api.post(f"{EVENTS}/{ev['id']}/cancel", json={"comment": "  "}).status_code == 422
    assert api.post(f"{EVENTS}/{ev['id']}/cancel", json={}).status_code == 422
    assert api.post(f"{EVENTS}/{ev['id']}/cancel", json={"comment": "x" * 501}).status_code == 422


# --------------------------------------------------------------------------------------------- history

def test_history_filters_and_pagination(api, engine):
    _start(api, "drought", 10)
    _start(api, "harvest", 30)
    ev = _start(api, "raid", 50).json()["started"][0]
    api.post(f"{EVENTS}/{ev['id']}/cancel", json={"comment": COMMENT})
    with engine.begin() as conn:                     # one old event for the date filters
        conn.execute(text("UPDATE econ_region_events SET started_at = :s WHERE template_code = 'harvest'"),
                     {"s": datetime(2026, 1, 10, 12, 0)})

    page = api.get(f"{EVENTS}/history").json()
    assert page["total"] == 3 and page["page"] == 1 and page["page_size"] == 50
    assert [e["template_code"] for e in page["items"]][-1] == "harvest"     # started_at desc
    assert api.get(f"{EVENTS}/history", params={"kind": "good"}).json()["total"] == 1
    assert api.get(f"{EVENTS}/history", params={"status": "cancelled"}).json()["total"] == 1
    assert api.get(f"{EVENTS}/history", params={"region_id": 10}).json()["total"] == 1
    assert api.get(f"{EVENTS}/history", params={"template_code": "raid"}).json()["total"] == 1
    assert api.get(f"{EVENTS}/history", params={"origin": "manual"}).json()["total"] == 3
    assert api.get(f"{EVENTS}/history", params={"origin": "riot"}).json()["total"] == 0
    old = api.get(f"{EVENTS}/history", params={"date_from": "2026-01-10", "date_to": "2026-01-10"}).json()
    assert [e["template_code"] for e in old["items"]] == ["harvest"]
    assert api.get(f"{EVENTS}/history", params={"date_from": "2026-01-11"}).json()["total"] == 2
    p2 = api.get(f"{EVENTS}/history", params={"page": 2, "page_size": 2}).json()
    assert p2["total"] == 3 and len(p2["items"]) == 1


@pytest.mark.parametrize("params", [
    {"kind": "neutral"}, {"status": "x"}, {"origin": "magic"}, {"page": 0}, {"page_size": 201},
    {"date_from": "10.01.2026"}, {"template_code": "x' OR '1'='1"}, {"region_id": 0},
])
def test_history_bad_query_422(api, params):
    assert api.get(f"{EVENTS}/history", params=params).status_code == 422


def test_history_dates_reversed_400(api):
    resp = api.get(f"{EVENTS}/history", params={"date_from": "2026-02-01", "date_to": "2026-01-01"})
    assert resp.status_code == 400 and resp.json()["detail"] == "Дата начала периода позже даты конца"


# --------------------------------------------------------------------------------------------- card / regions / runs

def test_card_events_both_shapes(api):
    _start(api, "drought", 10)
    _start(api, "harvest", 10)
    card = TestClient(app).get("/characters/economy/regions/10/card").json()
    assert card["participating"] is True
    assert {e["code"] for e in card["events"]} == {"drought", "harvest"}
    ev = next(e for e in card["events"] if e["code"] == "drought")
    assert set(ev) == {"code", "name", "icon", "kind", "text", "started_at", "ends_at"}     # no effect numbers
    assert ev["text"].startswith("Солнце выжигает поля")
    hidden = TestClient(app).get("/characters/economy/regions/40/card").json()
    assert hidden["participating"] is False and hidden["events"] == []
    assert TestClient(app).get("/characters/economy/regions/0/card").json()["events"] == []


def test_admin_regions_active_events(api):
    _start(api, "drought", 10)
    items = {r["region_id"]: r for r in api.get(f"{BASE}/regions").json()["items"]}
    assert items[10]["active_events"] == [{"name": "Засуха", "icon": "sun", "kind": "bad"}]
    assert items[20]["active_events"] == [] and items[40]["active_events"] == []


def test_runs_list_event_counters(api, engine):
    db = engine.factory()
    now = datetime.utcnow().replace(microsecond=0)
    old = models.EconTickRun(slot=None, trigger_kind="manual", status="done", regions_total=0, regions_done=0,
                             regions_failed=0, started_at=now - timedelta(hours=6), heartbeat_at=now)
    run = models.EconTickRun(slot=None, trigger_kind="manual", status="done", regions_total=0, regions_done=0,
                             regions_failed=0, started_at=now, heartbeat_at=now,
                             error="события — ошибка: проход событий")
    db.add_all([old, run])
    db.commit()
    run_id, old_id = int(run.id), int(old.id)
    base = dict(region_name="R", template_code="drought", name="Засуха", icon="sun", kind="bad", player_text="t",
                trigger_kind="random", effects=[], started_at=now - timedelta(days=2))
    db.add_all([
        models.EconRegionEvent(region_id=10, origin="random", run_id=run_id, status="active",
                               ends_at=now + timedelta(days=1), applied_run_id=run_id,
                               outcome={"treasury_expense": 5, "operation_id": 9}, **base),
        models.EconRegionEvent(region_id=20, origin="spread", run_id=run_id, status="active",
                               ends_at=now + timedelta(days=1), applied_run_id=run_id, outcome={}, **base),
        models.EconRegionEvent(region_id=30, origin="manual", status="ended", ends_at=now - timedelta(hours=1),
                               ended_at=now - timedelta(hours=1), **base),
    ])
    db.commit()
    db.close()
    runs = {r["id"]: r for r in api.get(f"{BASE}/sim").json()["runs"]}
    r = runs[run_id]
    assert (r["events_started"], r["events_spread"], r["events_chained"], r["riots_started"]) == (1, 1, 0, 0)
    assert (r["events_applied"], r["event_expense_ops"], r["events_ended"], r["events_failed"]) == (2, 1, 1, 1)
    assert runs[old_id]["events_ended"] == 0


# --------------------------------------------------------------------------------------------- R1 additions (Q3 gaps)

def test_start_neighbours_scope_country_fallback_and_arrows(api, engine):
    """No transition arrows -> neighbours = the other participating regions of the same country; with arrows ->
    only the arrow neighbours (both directions)."""
    resp = _start(api, "drought", 10, scope="neighbours")
    assert resp.status_code == 200, resp.text
    assert [e["region_id"] for e in resp.json()["started"]] == [10, 20, 30]      # 40 not participating, 50 abroad
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE region_transition_arrows (id INTEGER PRIMARY KEY, region_id BIGINT, "
                          "target_region_id BIGINT, paired_arrow_id BIGINT)"))
        conn.execute(text("INSERT INTO region_transition_arrows (id, region_id, target_region_id) VALUES (1, 50, 20)"))
    resp = _start(api, "plague", 20, scope="neighbours")
    assert resp.status_code == 200, resp.text
    assert [e["region_id"] for e in resp.json()["started"]] == [20, 50]          # arrow 50 -> 20, reversed


def test_start_race_on_active_key_maps_to_409(api, monkeypatch):
    """A concurrent start that took the active_key between the pre-check and the INSERT -> Russian 409."""
    assert _start(api, "drought", 10).status_code == 200
    monkeypatch.setattr(ev_crud, "_active_codes", lambda session, ids: {})       # pre-check misses the running one
    resp = _start(api, "drought", 10, scope="region")
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "В регионе уже идёт «Засуха» — отмените его или дождитесь конца"
    assert len(api.get(f"{EVENTS}/active").json()) == 1


@pytest.mark.parametrize("over", [
    {"weight": 1001},
    {"weight": "много"},
    {"duration_max_days": 366},
    {"admin_note": "x" * 1001},
    {"name": "x" * 101},
    {"region_templates": [f"t{i}" for i in range(51)]},
    {"chains": [{"code": f"c{i}x", "chance": 0.1} for i in range(11)]},
    {"chains": [{"code": "plague", "chance": 1.5}]},
    {"effects": [{"type": "stability", "delta": 11}]},
    {"effects": [{"type": "treasury_expense", "share": 0.95}]},
    {"effects": [{"type": "production", "groups": ["food"], "mult": 5.5}]},
    {"effects": [{"type": "population", "pct": -0.6}]},
    {"effects": [{"type": "production", "groups": [f"g{i}" for i in range(13)], "mult": 1.1}]},
    {"effects": [{"type": "production", "groups": ["Food; DROP"], "mult": 1.1}]},
    {"effects": [{"type": "production", "groups": [], "mult": 1.1}]},
    {"effects": "production"},
    {"kind": "neutral"},
    {"trigger_kind": "always"},
    {"scope": "galaxy"},
    {"spread_chance": 1e308},
])
def test_template_bounds_422(api, over):
    resp = api.post(f"{EVENTS}/templates", json=_template_body(**over))
    assert resp.status_code == 422, resp.text


def test_template_update_validation_422(api):
    tid = _tid(api, "drought")
    body = _template_body(effects=[{"type": "labor", "mult": 3}])
    body.pop("code")
    assert api.put(f"{EVENTS}/templates/{tid}", json=body).status_code == 422
    assert api.put(f"{EVENTS}/templates/abc", json=body).status_code == 422


def test_template_strings_stored_literally(api):
    """SQL- / HTML-like text is stored and echoed as plain data (parameterised SQL, escaping is the UI's job)."""
    name = "Мор'); DROP TABLE econ_region_events; --"
    text_ = "<script>alert(1)</script> «тест»"
    resp = api.post(f"{EVENTS}/templates", json=_template_body(name=name, player_text=text_, chains=[]))
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == name and resp.json()["player_text"] == text_
    assert _start(api, "quake", 50).status_code == 200                       # the events table is still there
    card = TestClient(app).get("/characters/economy/regions/50/card").json()
    assert card["events"][0]["text"] == text_


@pytest.mark.parametrize("body", [
    {"template_id": "abc", "region_id": 10},
    {"template_id": 1, "region_id": 2 ** 70},
    {"template_id": 1, "region_id": 10, "duration_days": "долго"},
    {"template_id": 1, "region_id": 10, "extra": 1, "scope": None, "request_id": "x" * 65},
])
def test_start_wrong_types_422(api, body):
    assert api.post(f"{EVENTS}/start", json=body).status_code == 422
