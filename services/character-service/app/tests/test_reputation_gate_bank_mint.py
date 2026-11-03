"""FEAT-197 QA (task 9): reputation gates of the banker (NPC gate + loan tier) and the minter (NPC gate).

Reuses the worlds of ``test_econ_bank_api`` (banker 50 @ region 10) and ``test_econ_mint_api`` (minter 60 @ 10).
The two worlds share fixture names, so each lives in its own class with module-level aliases.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import reputation_notify
import tests.test_econ_bank_api as bank_t
import tests.test_econ_mint_api as mint_t

engine = bank_t.engine
factory = mint_t.factory
world = mint_t.world


@pytest.fixture(autouse=True)
def no_rabbit(monkeypatch):
    monkeypatch.setattr(reputation_notify, "_send", MagicMock())


# --------------------------------------------------------------------------------------------- bank

@pytest.fixture
def bank_client(engine):
    bank_t._as_user(7)
    return TestClient(bank_t.app)


def _bank_exec(engine, sql, **params):
    with engine.factory() as db:
        db.execute(text(sql), params)
        db.commit()


def _bank_rep(engine, val, region_id=10, cid=bank_t.ALPHA):
    _bank_exec(engine, "INSERT INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
                       "VALUES (:c, :r, :v, NULL, CURRENT_TIMESTAMP)", c=cid, r=region_id, v=val)


def test_bank_loan_tier_gate(bank_client, engine):
    _bank_exec(engine, "UPDATE econ_banks SET loan_min_reputation_tier = 'familiar' WHERE region_id = 10")
    view = bank_client.get(bank_t._url(), params={"character_id": bank_t.ALPHA}).json()
    assert view["loan_refusal"] == "Нужна репутация: Знакомое лицо" and view["max_loan_now"] == 0
    assert view["reputation_lock"] is None                                     # deposits stay open
    resp = bank_t._post(bank_client, "loan", {"amount": 500, "term_days": 7})
    assert resp.status_code == 403 and resp.json()["detail"] == "Нужна репутация: Знакомое лицо"
    assert bank_t._post(bank_client, "deposit", {"kind": "demand", "amount": 100}).status_code == 200
    _bank_rep(engine, 100)
    assert bank_t._post(bank_client, "loan", {"amount": 500, "term_days": 7}).status_code == 200


def test_bank_npc_gate_blocks_every_write_but_not_the_view(bank_client, engine):
    _bank_exec(engine, "UPDATE characters SET reputation_min_tier = 'trusted' WHERE id = :i", i=bank_t.BANKER)
    resp = bank_t._post(bank_client, "deposit", {"kind": "demand", "amount": 100})
    assert resp.status_code == 403 and resp.json()["detail"] == "Нужна репутация: Свой человек"
    assert bank_t._post(bank_client, "loan", {"amount": 500, "term_days": 7}).status_code == 403
    view = bank_client.get(bank_t._url(), params={"character_id": bank_t.ALPHA})
    assert view.status_code == 200
    assert view.json()["reputation_lock"] == "Нужна репутация: Свой человек"
    assert view.json()["loan_refusal"] == "Нужна репутация: Свой человек"
    _bank_rep(engine, 300)
    assert bank_t._post(bank_client, "deposit", {"kind": "demand", "amount": 100}).status_code == 200


def test_bank_admin_sets_and_clears_the_loan_tier(engine):
    bank_t._as_user(1, permissions=["economy:settings", "economy:read"])
    client = TestClient(bank_t.app)
    url = "/characters/admin/economy/banks/10"
    resp = client.put(url, json={"is_enabled": True, "loan_min_reputation_tier": "defender"})
    assert resp.status_code == 200, resp.text
    with engine.factory() as db:
        assert db.execute(text("SELECT loan_min_reputation_tier FROM econ_banks WHERE region_id = 10")).scalar() \
            == "defender"
    assert client.put(url, json={"is_enabled": True}).status_code == 200          # omitted = unchanged
    with engine.factory() as db:
        assert db.execute(text("SELECT loan_min_reputation_tier FROM econ_banks WHERE region_id = 10")).scalar() \
            == "defender"
    assert client.put(url, json={"is_enabled": True, "loan_min_reputation_tier": None}).status_code == 200
    with engine.factory() as db:
        assert db.execute(text("SELECT loan_min_reputation_tier FROM econ_banks WHERE region_id = 10")).scalar() \
            is None
    resp = client.put(url, json={"is_enabled": True, "loan_min_reputation_tier": "god'; --"})
    assert resp.status_code == 422


# --------------------------------------------------------------------------------------------- mint

def test_mint_npc_gate(world):
    mint_world = world
    mint_t._as_user(7)
    client = TestClient(mint_t.app)
    mint_t._exec(mint_world, "UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :i", i=mint_t.MINTER)
    mint_t._give(mint_world, mint_t.ALPHA, mint_t.ORE, 3)
    resp = mint_t._post(client, quantity=1)
    assert resp.status_code == 403 and resp.json()["detail"] == "Нужна репутация: Знакомое лицо"
    assert mint_t._inv(mint_world)[0][1] == 3                                  # nothing taken
    v = mint_t._view(client)
    assert v.status_code == 200 and v.json()["reputation_lock"] == "Нужна репутация: Знакомое лицо"
    mint_t._exec(mint_world, "INSERT INTO character_reputation (character_id, region_id, value, decay_at, "
                             "updated_at) VALUES (:c, 10, 150, NULL, CURRENT_TIMESTAMP)", c=mint_t.ALPHA)
    assert mint_t._post(client, quantity=1, request_id=str(uuid.uuid4())[:20]).status_code == 200
    assert mint_t._view(client).json()["reputation_lock"] is None
