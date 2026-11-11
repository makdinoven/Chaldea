"""FEAT-211 QA (#12): the fence («Скупщик», NPC role ``fence``) on SQLite — admin A11/A12 and the tick refill.

* A11 ``GET /characters/admin/npcs/{id}/fence``: defaults without a row, cash / region / ``refill_active``,
  404 for a missing NPC / a player / a mob;
* A12 ``PUT``: upsert, goods groups validated / de-duplicated / canonical order, ``[]`` = every group, role must be
  ``fence`` (409), ranges (400, Russian), wrong types / too many groups (422), SQL-ish group codes refused (400);
* auth: 401 without a user, 403 without ``npcs:read`` / ``npcs:update``;
* ``econ_tick._fence_pass``: region purse → fences (ascending id) up to ``cash_target`` within
  ``floor(purse × fence_purse_share)``; one untaxed ``merchant_trade`` op keyed ``fence:<run>:r<region>``
  (``fence: true``); idempotent per run, topped up again next run; dead / inactive / non-fence / outside a simulated
  region skipped; a failing region is isolated; the world money sum stays 0;
* pure helpers ``refill_budget`` / ``allocate`` / ``normalize_groups`` / ``parse_groups``.
"""

import json

import pytest
from fastapi.testclient import TestClient

import econ_core as core
import econ_ledger
import econ_tick
import fence_api
import fence_crud
import models
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.econ_contract_cases import WORLD_SUM_SQL
from tests.test_econ_tick import _add_region, _balance, _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import _exec, _params, _set_params

FENCE, FENCE2, MERCHANT, DEAD, SLEEPY, FAR_FENCE, MOB, PLAYER = 700, 701, 702, 703, 704, 705, 706, 501
L_TOWN, L_WILD = 101, 301                     # region 1 (simulated), region 3 (no economy)
URL = "/characters/admin/npcs/{}/fence"
READ, UPDATE = ["npcs:read"], ["npcs:read", "npcs:update"]


# ===================================================================================================================
# fixtures
# ===================================================================================================================

@pytest.fixture
def fw(factory, seed_fk_data):
    """Region 1 (simulated, start purse) with town 101; region 3 without economy (location 301); NPCs: fences 700 /
    701 @101, merchant 702 @101, dead fence 703, fence 704 (deactivated by its row), fence 705 @301, mob 706;
    player 501."""
    _add_region(factory, 1)
    _exec(factory, "INSERT INTO Regions (id, name, country_id) VALUES (3, 'Глушь', 1)")
    _exec(factory, "INSERT INTO Locations (id, name, region_id) VALUES (:a, 'Город', 1), (:b, 'Пустырь', 3)",
          a=L_TOWN, b=L_WILD)
    db = factory()
    try:
        seed_fk_data(db)
        with econ_ledger.allow_direct_balance_write(db):
            for cid, role, status, loc, npc in (
                    (FENCE, "fence", "alive", L_TOWN, True), (FENCE2, "fence", "alive", L_TOWN, True),
                    (MERCHANT, "merchant", "alive", L_TOWN, True), (DEAD, "fence", "dead", L_TOWN, True),
                    (SLEEPY, "fence", "alive", L_TOWN, True), (FAR_FENCE, "fence", "alive", L_WILD, True),
                    (MOB, "mob", "alive", L_TOWN, True), (PLAYER, None, None, L_TOWN, False)):
                db.add(models.Character(id=cid, name=f"НПС {cid}", user_id=None if npc else 7, id_subrace=1,
                                        id_class=1, id_race=1, appearance="-", avatar="-", is_npc=npc,
                                        npc_role=role, npc_status=status, current_location_id=loc, level=5,
                                        currency_balance=0))
            db.flush()
        db.add(models.EconFence(npc_id=SLEEPY, is_active=False, price_pct=40, cash_target=2000))
        db.commit()
    finally:
        db.close()
    return factory


@pytest.fixture
def api(fw):
    def override_get_db():
        session = fw()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[fence_api.get_db] = override_get_db
    _as(UPDATE)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(fence_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _as(permissions, role="moderator"):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=3, username="mod", role=role, permissions=list(permissions))


def _body(**kw):
    body = {"is_active": True, "price_pct": 35, "accepted_groups": ["ore_metal", "food"], "cash_target": 1500}
    body.update(kw)
    return body


def _fence_row(f, npc_id):
    r = _rows(f, "SELECT is_active, price_pct, accepted_groups, cash_target, updated_by FROM econ_fences "
                 "WHERE npc_id = :n", n=npc_id)
    return r[0] if r else None


def _cash(f, cid):
    return int(_scalar(f, "SELECT currency_balance FROM characters WHERE id = :c", c=cid) or 0)


def _world_sum(f):
    return int(_scalar(f, WORLD_SUM_SQL))


# ===================================================================================================================
# pure helpers
# ===================================================================================================================

def test_refill_budget():
    assert fence_crud.refill_budget(1000, 0.1) == 100
    assert fence_crud.refill_budget(999, 0.1) == 99                         # floor
    assert fence_crud.refill_budget(0, 0.5) == 0 and fence_crud.refill_budget(-5, 0.5) == 0
    assert fence_crud.refill_budget(1000, 0) == 0 and fence_crud.refill_budget(1000, None) == 0


def test_allocate_in_order_up_to_target_within_budget():
    assert fence_crud.allocate(500, [(1, 0, 300), (2, 100, 400), (3, 0, 100)]) == {1: 300, 2: 200}
    assert fence_crud.allocate(1000, [(1, 500, 300), (2, 0, 50)]) == {2: 50}  # over target -> nothing
    assert fence_crud.allocate(0, [(1, 0, 10)]) == {}


def test_normalize_and_parse_groups():
    assert fence_crud.normalize_groups(["ore_metal", "food", " food "]) == ["food", "ore_metal"]
    assert fence_crud.normalize_groups([]) == []
    for bad in (["gold"], ["food", ""], ["'; DROP TABLE econ_fences; --"]):
        with pytest.raises(fence_crud.FenceError) as exc:
            fence_crud.normalize_groups(bad)
        assert (exc.value.status_code, exc.value.detail) == (400, "Неизвестная группа товаров")
    assert fence_crud.parse_groups(None) == [] and fence_crud.parse_groups("not json") == []
    assert fence_crud.parse_groups('["wood", "food", "junk"]') == ["food", "wood"]
    assert fence_crud.parse_groups(b'["herbs"]') == ["herbs"] and fence_crud.parse_groups({"a": 1}) == []


# ===================================================================================================================
# A11 / A12
# ===================================================================================================================

def test_a11_defaults_without_a_row(api, fw):
    resp = api.get(URL.format(FENCE))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"npc_id": FENCE, "is_active": True, "price_pct": 40, "accepted_groups": [],
                           "cash_target": 2000, "cash": 0, "region_id": 1, "region_name": "Регион 1",
                           "refill_active": True}


@pytest.mark.parametrize("npc,refill", [(MERCHANT, False), (DEAD, False), (SLEEPY, False), (FAR_FENCE, False)])
def test_a11_refill_active_only_for_live_active_fences_in_a_simulated_region(api, npc, refill):
    body = api.get(URL.format(npc)).json()
    assert body["refill_active"] is refill
    if npc == FAR_FENCE:
        assert (body["region_id"], body["region_name"]) == (3, "Глушь")


@pytest.mark.parametrize("npc", [PLAYER, MOB, 999999])
def test_a11_a12_not_an_npc_is_404(api, npc):
    for resp in (api.get(URL.format(npc)), api.put(URL.format(npc), json=_body())):
        assert resp.status_code == 404 and resp.json()["detail"] == "НПС не найден"


def test_a12_saves_and_normalizes(api, fw):
    resp = api.put(URL.format(FENCE), json=_body(accepted_groups=["ore_metal", "food", "food"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["price_pct"], body["accepted_groups"], body["cash_target"], body["is_active"]) == \
        (35, ["food", "ore_metal"], 1500, True)
    active, pct, groups, target, by = _fence_row(fw, FENCE)
    groups = json.loads(groups) if isinstance(groups, str) else groups
    assert (bool(active), pct, groups, target, by) == (True, 35, ["food", "ore_metal"], 1500, 3)
    # update in place; [] = every group (stored NULL); deactivate
    body = api.put(URL.format(FENCE), json=_body(accepted_groups=[], is_active=False, price_pct=100,
                                                 cash_target=0)).json()
    assert (body["accepted_groups"], body["is_active"], body["refill_active"], body["price_pct"]) == \
        ([], False, False, 100)
    assert _fence_row(fw, FENCE)[2] in (None, "null")                    # SQL NULL or JSON null: both = all groups
    assert fence_crud.parse_groups(_fence_row(fw, FENCE)[2]) == []
    assert _scalar(fw, "SELECT COUNT(*) FROM econ_fences WHERE npc_id = :n", n=FENCE) == 1


def test_a12_role_must_be_fence(api, fw):
    resp = api.put(URL.format(MERCHANT), json=_body())
    assert resp.status_code == 409 and resp.json()["detail"] == "Настройки скупки доступны только скупщику"
    assert _fence_row(fw, MERCHANT) is None


@pytest.mark.parametrize("patch,detail", [
    ({"price_pct": 0}, "Процент цены должен быть от 1 до 100"),
    ({"price_pct": 101}, "Процент цены должен быть от 1 до 100"),
    ({"cash_target": -1}, "Касса скупщика должна быть от 0 до 10000000"),
    ({"cash_target": 10_000_001}, "Касса скупщика должна быть от 0 до 10000000"),
    ({"accepted_groups": ["gold"]}, "Неизвестная группа товаров"),
    ({"accepted_groups": ["'; DROP TABLE econ_fences; --"]}, "Неизвестная группа товаров"),
    ({"accepted_groups": ["food\" OR 1=1 --"]}, "Неизвестная группа товаров"),
])
def test_a12_validation_400_keeps_the_row(api, fw, patch, detail):
    api.put(URL.format(FENCE), json=_body())
    resp = api.put(URL.format(FENCE), json=_body(**patch))
    assert resp.status_code == 400 and resp.json()["detail"] == detail
    assert _fence_row(fw, FENCE)[1] == 35
    assert _scalar(fw, "SELECT COUNT(*) FROM econ_fences") == 2


@pytest.mark.parametrize("patch", [{"price_pct": "abc"}, {"cash_target": "много"}, {"accepted_groups": "food"},
                                   {"accepted_groups": ["food"] * 25}, {"is_active": "maybe"}])
def test_a12_validation_422(api, fw, patch):
    assert api.put(URL.format(FENCE), json=_body(**patch)).status_code == 422
    assert _fence_row(fw, FENCE) is None


def test_a11_a12_bad_path_is_422(api):
    assert api.get(URL.format("abc")).status_code == 422
    assert api.put(URL.format("1 OR 1=1"), json=_body()).status_code == 422


def test_auth(api, fw):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    assert api.get(URL.format(FENCE)).status_code == 401
    assert api.put(URL.format(FENCE), json=_body()).status_code == 401
    _as([], role="user")
    assert api.get(URL.format(FENCE)).status_code == 403
    assert api.put(URL.format(FENCE), json=_body()).status_code == 403
    _as(READ)
    assert api.get(URL.format(FENCE)).status_code == 200
    assert api.put(URL.format(FENCE), json=_body()).status_code == 403
    assert _fence_row(fw, FENCE) is None
    _as(["npcs:update"])                                         # update alone can write (and reads the result)
    assert api.put(URL.format(FENCE), json=_body()).status_code == 200


# ===================================================================================================================
# the tick's _fence_pass
# ===================================================================================================================

def _run(f, run_id=1, summary=None):
    econ_tick._fence_pass(f, run_id, _params(f), summary)


def _summary(run_id=1):
    return econ_tick.RunSummary(run_id=run_id, trigger="manual", slot=None, status="running")


def _targets(f, **by_npc):
    db = f()
    try:
        for npc, target in by_npc.items():
            db.merge(models.EconFence(npc_id=int(npc[1:]), is_active=True, price_pct=40, cash_target=target))
        db.commit()
    finally:
        db.close()


def test_refill_tops_up_fences_in_order_within_the_purse_share(fw):
    _set_params(fw, fence_purse_share=0.1)
    purse = _balance(fw, "population_purse", 1)
    budget = purse // 10
    _targets(fw, n700=budget - 100, n701=10 ** 6)               # 701 gets only what is left
    world = _world_sum(fw)
    s = _summary()
    _run(fw, summary=s)
    assert (_cash(fw, FENCE), _cash(fw, FENCE2)) == (budget - 100, 100)
    assert _balance(fw, "population_purse", 1) == purse - budget
    assert (s.fences_refilled, s.fence_cash_added, s.fence_failed_region_ids) == (2, budget, [])
    for npc in (MERCHANT, DEAD, SLEEPY, FAR_FENCE, MOB, PLAYER):
        assert _cash(fw, npc) == 0
    assert _world_sum(fw) == world == 0
    [(op_id, op_type, key, meta)] = _rows(fw, "SELECT id, op_type, idempotency_key, metadata FROM econ_operations "
                                              "WHERE idempotency_key LIKE 'fence:%'")
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert (op_type, key, meta["fence"], meta["budget"], meta["total"]) == ("merchant_trade", "fence:1:r1", True,
                                                                           budget, budget)
    assert _scalar(fw, "SELECT COUNT(*) FROM econ_postings WHERE operation_id = :o AND leg_type = 'tax'",
                   o=op_id) == 0


def test_refill_is_idempotent_per_run_and_stops_at_target(fw):
    _set_params(fw, fence_purse_share=0.5)
    _targets(fw, n700=300, n701=200)
    _run(fw, 1)
    _run(fw, 1)                                                  # same run again: duplicate key, nothing new
    assert (_cash(fw, FENCE), _cash(fw, FENCE2)) == (300, 200)
    assert _scalar(fw, "SELECT COUNT(*) FROM econ_operations WHERE idempotency_key LIKE 'fence:%'") == 1
    _run(fw, 2)                                                  # at target: nothing posted
    assert _scalar(fw, "SELECT COUNT(*) FROM econ_operations WHERE idempotency_key LIKE 'fence:%'") == 1
    # the fence spent money (paid a player) -> topped up again next run
    db = fw()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_NPC_SHOP_SELL, source_service="test", apply_tax=False,
                                   legs=[core.Leg(core.AccountRef.character(FENCE),
                                                  core.AccountRef.character(PLAYER), 120)])
        db.commit()
    finally:
        db.close()
    _run(fw, 3)
    assert (_cash(fw, FENCE), _cash(fw, PLAYER)) == (300, 120)
    assert _rows(fw, "SELECT idempotency_key FROM econ_operations WHERE idempotency_key LIKE 'fence:%' "
                     "ORDER BY id") == [("fence:1:r1",), ("fence:3:r1",)]
    assert _world_sum(fw) == 0


def test_refill_nothing_without_share_or_purse(fw):
    _set_params(fw, fence_purse_share=0)
    _run(fw)
    assert _cash(fw, FENCE) == 0
    _set_params(fw, fence_purse_share=1)
    _exec(fw, "UPDATE econ_regions SET population = 0 WHERE region_id = 1")      # region left the simulation
    _run(fw)
    assert _cash(fw, FENCE) == 0
    assert _scalar(fw, "SELECT COUNT(*) FROM econ_operations WHERE idempotency_key LIKE 'fence:%'") == 0


def test_refill_skips_a_fence_that_lost_the_role(fw):
    _set_params(fw, fence_purse_share=0.5)
    _targets(fw, n700=100, n701=100)
    _exec(fw, "UPDATE characters SET npc_role = 'merchant' WHERE id = :c", c=FENCE)
    _run(fw)
    assert (_cash(fw, FENCE), _cash(fw, FENCE2)) == (0, 100)


def test_failing_region_is_isolated_and_counted(fw, monkeypatch):
    _set_params(fw, fence_purse_share=0.5)
    real = fence_crud.refill_region

    def boom(db, **kw):
        real(db, **kw)
        raise RuntimeError("crash after posting")

    monkeypatch.setattr(fence_crud, "refill_region", boom)
    s = _summary()
    _run(fw, summary=s)
    assert s.fence_failed_region_ids == [1] and s.fences_refilled == 0
    assert _cash(fw, FENCE) == 0                                 # rolled back
    monkeypatch.setattr(fence_crud, "refill_region", real)
    _run(fw)                                                     # retried with the same run key
    assert _cash(fw, FENCE) == 2000 and _world_sum(fw) == 0


def test_pass_without_the_fence_table_is_skipped(fw):
    _exec(fw, "DROP TABLE econ_fences")
    _run(fw)                                                     # no exception
    assert _cash(fw, FENCE) == 0
