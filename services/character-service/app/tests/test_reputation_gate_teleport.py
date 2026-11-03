"""FEAT-197 QA (task 9): teleport reputation gates — the source NPC gate and the per-link tier (§3.7).

Reuses the world of ``test_teleport`` (masters A @ location 10, B @ 20; player in A with 500 gold); location 10 is
put into region 5 «Ост» here. The outbound locations-service cleanup call is stubbed (``_stub_internal_http``).
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

import reputation_notify
from tests.test_teleport import (  # noqa: F401  (fixtures)
    LOC_A_ID, LOC_B_ID, _stub_internal_http, admin_client, db_session, player_client, world,
)

REGION = 5


@pytest.fixture(autouse=True)
def no_rabbit(monkeypatch):
    monkeypatch.setattr(reputation_notify, "_send", MagicMock())


@pytest.fixture
def region(db_session, world):
    db_session.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд')"))
    db_session.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (:r, 'Ост', 1)"), {"r": REGION})
    db_session.execute(text("UPDATE Locations SET region_id = :r WHERE id = :l"), {"r": REGION, "l": LOC_A_ID})
    db_session.commit()
    return world


def _set(db_session, sql, **params):
    db_session.execute(text(sql), params)
    db_session.commit()


def _rep(db_session, character_id, val):
    _set(db_session, "INSERT INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
                     "VALUES (:c, :r, :v, NULL, CURRENT_TIMESTAMP)", c=character_id, r=REGION, v=val)


def _teleport(client, w):
    return client.post(f"/characters/npcs/{w['npc_a'].id}/teleport", json={"link_id": w["link_ab"].id})


def _location(db_session, cid):
    db_session.expire_all()
    return db_session.execute(text("SELECT current_location_id FROM characters WHERE id = :i"), {"i": cid}).scalar()


def test_link_tier_gate(player_client, db_session, region):
    w = region
    _set(db_session, "UPDATE teleport_links SET min_reputation_tier = 'trusted' WHERE id = :i", i=w["link_ab"].id)
    opts = player_client.get(f"/characters/npcs/{w['npc_a'].id}/teleport-options").json()
    assert opts["locked_reason"] is None
    assert [o["locked_reason"] for o in opts["options"]] == ["Нужна репутация: Свой человек"]
    resp = _teleport(player_client, w)
    assert resp.status_code == 403 and resp.json()["detail"] == "Нужна репутация: Свой человек"
    assert _location(db_session, w["player"].id) == LOC_A_ID
    _rep(db_session, w["player"].id, 300)
    assert player_client.get(f"/characters/npcs/{w['npc_a'].id}/teleport-options").json()["options"][0][
        "locked_reason"] is None
    assert _teleport(player_client, w).status_code == 200
    assert _location(db_session, w["player"].id) == LOC_B_ID


def test_master_npc_gate(player_client, db_session, region):
    w = region
    _set(db_session, "UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :i", i=w["npc_a"].id)
    opts = player_client.get(f"/characters/npcs/{w['npc_a'].id}/teleport-options").json()
    assert opts["locked_reason"] == "Нужна репутация: Знакомое лицо"
    resp = _teleport(player_client, w)
    assert resp.status_code == 403 and resp.json()["detail"] == "Нужна репутация: Знакомое лицо"
    _rep(db_session, w["player"].id, 100)
    assert _teleport(player_client, w).status_code == 200


def test_gate_without_region_is_open(player_client, db_session, world):
    """Location 10 has no region in the base world -> gates cannot apply."""
    _set(db_session, "UPDATE teleport_links SET min_reputation_tier = 'legend' WHERE id = :i", i=world["link_ab"].id)
    assert _teleport(player_client, world).status_code == 200


def test_admin_link_tier_field(admin_client, db_session, world):
    link_id = world["link_ab"].id
    resp = admin_client.patch(f"/characters/admin/teleport-links/{link_id}", json={"min_reputation_tier": "legend"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["min_reputation_tier"] == "legend" and resp.json()["cost_gold"] == 100
    resp = admin_client.patch(f"/characters/admin/teleport-links/{link_id}", json={"cost_gold": 50})
    assert resp.json()["min_reputation_tier"] == "legend" and resp.json()["cost_gold"] == 50   # omitted = unchanged
    resp = admin_client.patch(f"/characters/admin/teleport-links/{link_id}", json={"min_reputation_tier": ""})
    assert resp.status_code == 200 and resp.json()["min_reputation_tier"] is None
    assert admin_client.patch(f"/characters/admin/teleport-links/{link_id}",
                              json={"min_reputation_tier": "x' OR 1=1"}).status_code == 422
    assert admin_client.patch(f"/characters/admin/teleport-links/{link_id}", json={}).status_code == 400
