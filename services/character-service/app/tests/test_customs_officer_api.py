"""FEAT-216 task 5 — developer smoke of the customs officer job (C1–C4) and the admin bans API (A1, A2).

The full flows (detection → inspect → seizure, refusals in depth) are QA task 15. Lean on purpose: reuses the
FEAT-211 raid world (``rw`` / ``api``): raider 501 (user 7) stands at L_GATE1 (region 1, country 1).
"""

from unittest.mock import AsyncMock

import pytest

import customs_core
import customs_crud
import locations_client
import models
from tests.test_caravan_raids import OTHER_USER, RAIDER, USER, _as_user, api, rw  # noqa: F401  (fixtures)
from tests.test_econ_tick import _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import _exec
from tests.test_econ_tick_events import calendar  # noqa: F401
from tests.test_physical_caravans import L_GATE1, L_ROAD1, world  # noqa: F401

NPC = 611
VIEW = f"/characters/customs/officer/{NPC}"
ENLIST = f"/characters/customs/officer/{NPC}/enlist"
RESIGN = "/characters/customs/resign"
JOB = "/characters/customs/job"
ADMIN = "/characters/admin/economy/caravans/customs"


@pytest.fixture
def cus(api, rw, monkeypatch):
    db = rw()
    try:
        db.add(models.Character(id=NPC, name="Таможенник", user_id=None, id_subrace=1, id_class=1, id_race=1,
                                appearance="-", avatar="-", is_npc=True, npc_role=customs_core.CUSTOMS_ROLE,
                                current_location_id=L_GATE1, level=1, currency_balance=0))
        db.commit()
    finally:
        db.close()
    rw.gate = AsyncMock(return_value=True)
    monkeypatch.setattr(locations_client, "check_npc_gate", rw.gate)
    _as_user(USER)
    return api


def test_view_enlist_job_resign_cycle(cus, rw):
    resp = cus.get(VIEW, params={"character_id": RAIDER})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["npc_id"], body["country_id"], body["location_id"]) == (NPC, 1, L_GATE1)
    assert body["job"] is None and body["can_enlist"] is True and body["reason"] is None
    assert set(body["params"]) == {"officer_share", "alert_minutes"}

    resp = cus.post(ENLIST, json={"character_id": RAIDER})
    assert resp.status_code == 201, resp.text
    job = resp.json()["job"]
    assert (job["country_id"], job["status"], job["seizures"], job["earned"]) == (1, "active", 0, 0)
    assert customs_crud.is_active_officer(rw(), RAIDER)

    resp = cus.post(ENLIST, json={"character_id": RAIDER})
    assert (resp.status_code, resp.json()["detail"]) == (409, customs_crud.MSG_ALREADY_OFFICER)
    view = cus.get(VIEW, params={"character_id": RAIDER}).json()
    assert view["can_enlist"] is False and view["job"]["country_id"] == 1

    assert cus.get(JOB, params={"character_id": RAIDER}).json()["job"]["status"] == "active"
    resp = cus.post(RESIGN, json={"character_id": RAIDER})
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert cus.get(JOB, params={"character_id": RAIDER}).json() == {"job": None}
    resp = cus.post(RESIGN, json={"character_id": RAIDER})
    assert (resp.status_code, resp.json()["detail"]) == (409, customs_crud.MSG_NOT_OFFICER)

    # re-enlist reuses the row (one row per character)
    assert cus.post(ENLIST, json={"character_id": RAIDER}).status_code == 201
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_customs_officers WHERE character_id = :c", c=RAIDER) == 1


def test_gates_and_ownership(cus, rw):
    rw.gate.return_value = False
    resp = cus.get(VIEW, params={"character_id": RAIDER})
    assert (resp.status_code, resp.json()["detail"]) == (403, customs_crud.MSG_GATE_CLOSED)
    rw.gate.side_effect = locations_client.GateUnavailable()
    assert cus.post(ENLIST, json={"character_id": RAIDER}).status_code == 503
    rw.gate.side_effect = None
    rw.gate.return_value = True

    _as_user(OTHER_USER)
    assert cus.get(VIEW, params={"character_id": RAIDER}).status_code == 403
    assert cus.post(RESIGN, json={"character_id": RAIDER}).status_code == 403
    _as_user(USER)

    _exec(rw, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_ROAD1, c=RAIDER)
    resp = cus.get(VIEW, params={"character_id": RAIDER})
    assert (resp.status_code, resp.json()["detail"]) == (400, customs_crud.MSG_NOT_AT_NPC)
    _exec(rw, "UPDATE characters SET npc_role = 'caravaneer' WHERE id = :c", c=NPC)
    assert cus.get(VIEW, params={"character_id": RAIDER}).status_code == 404
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_customs_officers") == 0


def test_admin_bans_read_replace(cus, rw):
    _as_user(USER, role="admin", permissions=["economy:read"])
    resp = cus.get(ADMIN)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    codes = [g["code"] for g in body["groups"]]
    assert "food" in codes and {c["country_id"] for c in body["countries"]} >= {1, 2}
    assert all(c["banned_groups"] == [] for c in body["countries"])

    resp = cus.put(f"{ADMIN}/1", json={"banned_groups": ["food"]})
    assert resp.status_code == 403                                        # needs economy:settings
    _as_user(USER, role="admin", permissions=["economy:read", "economy:settings"])
    resp = cus.put(f"{ADMIN}/1", json={"banned_groups": ["food", " food ", ""]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["banned_groups"] == ["food"] and resp.json()["country_id"] == 1
    assert [r[0] for r in _rows(rw, "SELECT group_code FROM econ_country_bans WHERE country_id = 1")] == ["food"]

    resp = cus.put(f"{ADMIN}/1", json={"banned_groups": ["nope"]})
    assert resp.status_code == 400 and "nope" in resp.json()["detail"]
    assert cus.put(f"{ADMIN}/999", json={"banned_groups": []}).status_code == 404
    assert cus.put(f"{ADMIN}/1", json={"banned_groups": []}).json()["banned_groups"] == []
    assert _scalar(rw, "SELECT COUNT(*) FROM econ_country_bans") == 0

    _as_user(USER)
    assert cus.get(ADMIN).status_code == 403


def test_admin_lists_posts_when_the_column_exists(cus, rw):
    cols = {r[1] for r in _rows(rw, "PRAGMA table_info(Locations)")}
    for col in ("is_port", "is_customs"):
        if col not in cols:
            _exec(rw, f"ALTER TABLE Locations ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
    _exec(rw, "UPDATE Locations SET is_customs = 1 WHERE id = :l", l=L_GATE1)
    _as_user(USER, role="admin", permissions=["economy:read"])
    countries = {c["country_id"]: c for c in cus.get(ADMIN).json()["countries"]}
    assert [p["location_id"] for p in countries[1]["posts"]] == [L_GATE1]
    assert countries[1]["posts"][0]["is_port"] is False
