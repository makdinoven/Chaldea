"""
FEAT-164 — satiety & rest-status endpoints (character-attributes-service).

  * POST /attributes/internal/{id}/satiety — 201 (modifiers + capped recovery +
    row), 409 «Вы уже наелись» (no double bonus), 400 (rarity above legendary,
    unknown modifier, negative recovery), 404, 422, re-eat after expiry;
  * GET /attributes/{id}/rest-status — shape, rate by rarity, busy_reason for
    battle / dungeon / gathering, dungeon lobby = resting, NPC, 404;
  * POST /attributes/internal/settle-regen — settled/missing, validation;
  * security: internal endpoints are blocked at the gateway, rest-status is a
    public read that cannot be abused to gain resources, injection in path.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402

database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import models  # noqa: E402
import regen  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402

from tests.regen_shared_tables import (  # noqa: E402
    add_battle,
    add_character,
    add_dungeon,
    add_gathering,
    create_shared_tables,
    drop_shared_tables,
    skip_or_fail_missing,
)

CID = 11
SATIETY_URL = f"/attributes/internal/{CID}/satiety"


@pytest.fixture(autouse=True)
def _setup_tables():
    # Shared tables first: another test module registers a reduced `characters`
    # model in Base.metadata; create_all then skips the existing table.
    create_shared_tables(_test_engine)
    models.Base.metadata.create_all(bind=_test_engine)
    yield
    drop_shared_tables(_test_engine)
    models.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def db():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    def _override_get_db():
        s = _TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def now_s():
    return datetime.utcnow().replace(microsecond=0)


def seed(db, character_id=CID, is_npc=False, **values):
    add_character(db, character_id, is_npc=is_npc)
    base = dict(
        current_health=50, max_health=100,
        current_mana=75, max_mana=75,
        current_energy=50, max_energy=50,
        current_stamina=100, max_stamina=100,
        regen_anchor_at=now_s(),
    )
    base.update(values)
    db.add(models.CharacterAttributes(character_id=character_id, **base))
    db.commit()


def reload(db, character_id=CID):
    db.expire_all()
    return db.query(models.CharacterAttributes).filter_by(character_id=character_id).one()


def payload(**kw):
    body = {
        "item_id": 345,
        "source_item_name": "Жаркое из кабана",
        "rarity": "rare",
        "modifiers": {"strength": 2, "health": 1, "res_fire": 1.5},
        "recovery": {"health_recovery": 30, "mana_recovery": 0, "energy_recovery": 0, "stamina_recovery": 0},
    }
    body.update(kw)
    return body


# ---------------------------------------------------------------------------
# POST /attributes/internal/{id}/satiety
# ---------------------------------------------------------------------------


class TestApplySatiety:
    def test_success_applies_modifiers_recovery_and_row(self, client, db):
        seed(db, strength=10)
        before = datetime.utcnow() - timedelta(seconds=2)
        resp = client.post(SATIETY_URL, json=payload())
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["stats_changed"] is True
        sat = body["satiety"]
        assert sat["item_id"] == 345
        assert sat["source_item_name"] == "Жаркое из кабана"
        assert sat["rarity"] == "rare"
        assert sat["regen_bonus_percent"] == 100
        assert sat["modifiers"] == {"strength": 2, "health": 1, "res_fire": 1.5}
        started = datetime.fromisoformat(sat["started_at"])
        expires = datetime.fromisoformat(sat["expires_at"])
        assert expires - started == timedelta(hours=24)
        assert started >= before.replace(microsecond=0)
        assert 24 * 3600 - 5 <= sat["remaining_seconds"] <= 24 * 3600

        attr = reload(db)
        assert attr.strength == 12
        assert attr.res_fire == pytest.approx(1.5)
        assert attr.res_physical == pytest.approx(0.0)  # no derived propagation
        assert attr.health == 1
        assert attr.max_health == 110  # +1 point = +10 max
        # 50 + 10 (max shift) + 30 recovery = 90, capped at new max 110
        assert attr.current_health == 90

        row = regen.get_satiety(db, CID)
        assert row is not None and row.regen_bonus == pytest.approx(1.0)

    @pytest.mark.parametrize(
        "rarity,percent", [("common", 50), ("rare", 100), ("epic", 150), ("legendary", 200)]
    )
    def test_regen_bonus_percent_by_rarity(self, client, db, rarity, percent):
        seed(db)
        resp = client.post(SATIETY_URL, json=payload(rarity=rarity, modifiers={}))
        assert resp.status_code == 201
        assert resp.json()["satiety"]["regen_bonus_percent"] == percent

    def test_recovery_capped_at_max(self, client, db):
        seed(db, current_mana=70)
        resp = client.post(
            SATIETY_URL,
            json=payload(modifiers={}, recovery={"health_recovery": 500, "mana_recovery": 500}),
        )
        assert resp.status_code == 201
        attr = reload(db)
        assert attr.current_health == 100
        assert attr.current_mana == 75
        assert resp.json()["stats_changed"] is False

    def test_second_eat_rejected_without_double_bonus(self, client, db):
        seed(db, strength=10)
        assert client.post(SATIETY_URL, json=payload()).status_code == 201
        resp = client.post(SATIETY_URL, json=payload(rarity="legendary"))
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Вы уже наелись"
        attr = reload(db)
        assert attr.strength == 12
        assert attr.max_health == 110
        assert db.query(models.CharacterSatiety).count() == 1
        assert regen.get_satiety(db, CID).rarity == "rare"

    def test_eat_again_after_expiry_replaces_bonus(self, client, db):
        seed(db, strength=10)
        assert client.post(SATIETY_URL, json=payload(modifiers={"strength": 2})).status_code == 201
        row = regen.get_satiety(db, CID)
        row.expires_at = now_s() - timedelta(seconds=1)
        db.commit()
        resp = client.post(SATIETY_URL, json=payload(rarity="epic", modifiers={"strength": 3}))
        assert resp.status_code == 201, resp.text
        assert reload(db).strength == 13  # 10 - 2 + 3
        assert regen.get_satiety(db, CID).rarity == "epic"

    @pytest.mark.parametrize("rarity", ["mythical", "divine", "demonic", "garbage", ""])
    def test_rarity_above_legendary_rejected(self, client, db, rarity):
        seed(db)
        resp = client.post(SATIETY_URL, json=payload(rarity=rarity))
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Недопустимая редкость еды"
        assert regen.get_satiety(db, CID) is None

    def test_unknown_modifier_rejected(self, client, db):
        seed(db)
        resp = client.post(SATIETY_URL, json=payload(modifiers={"strength": 1, "current_health": 999}))
        assert resp.status_code == 400
        assert "current_health" in resp.json()["detail"]
        assert reload(db).strength == 0

    def test_sql_injection_modifier_key_rejected(self, client, db):
        seed(db)
        resp = client.post(SATIETY_URL, json=payload(modifiers={"strength; DROP TABLE character_attributes; --": 1}))
        assert resp.status_code == 400
        assert reload(db).current_health == 50

    def test_negative_recovery_rejected(self, client, db):
        seed(db)
        resp = client.post(SATIETY_URL, json=payload(recovery={"health_recovery": -10}))
        assert resp.status_code == 400
        assert reload(db).current_health == 50
        assert regen.get_satiety(db, CID) is None

    def test_long_name_rejected(self, client, db):
        seed(db)
        resp = client.post(SATIETY_URL, json=payload(source_item_name="x" * 201))
        assert resp.status_code == 422

    def test_non_numeric_modifier_rejected(self, client, db):
        seed(db)
        resp = client.post(SATIETY_URL, json=payload(modifiers={"strength": "a lot"}))
        assert resp.status_code == 422

    def test_missing_attributes_404(self, client):
        resp = client.post("/attributes/internal/99999/satiety", json=payload())
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Атрибуты персонажа не найдены"

    def test_settles_regen_before_applying(self, client, db):
        seed(db, current_health=0, regen_anchor_at=now_s() - timedelta(hours=2))
        resp = client.post(SATIETY_URL, json=payload(modifiers={}, recovery={}))
        assert resp.status_code == 201
        attr = reload(db)
        assert attr.current_health == 10
        # satiety started now → no bonus for past time
        assert attr.regen_anchor_at >= now_s() - timedelta(seconds=5)


# ---------------------------------------------------------------------------
# GET /attributes/{id}/rest-status
# ---------------------------------------------------------------------------


class TestRestStatus:
    def test_resting_without_satiety(self, client, db):
        seed(db)
        resp = client.get(f"/attributes/{CID}/rest-status")
        assert resp.status_code == 200
        assert resp.json() == {
            "character_id": CID,
            "is_resting": True,
            "busy_reason": None,
            "base_regen_percent_per_hour": 5.0,
            "regen_percent_per_hour": 5.0,
            "satiety": None,
        }

    def test_with_satiety_rate_and_info(self, client, db):
        seed(db)
        client.post(SATIETY_URL, json=payload(rarity="legendary", modifiers={"strength": 2}))
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["regen_percent_per_hour"] == pytest.approx(15.0)
        sat = body["satiety"]
        assert set(sat) == {
            "item_id", "source_item_name", "rarity", "regen_bonus_percent",
            "modifiers", "started_at", "expires_at", "remaining_seconds",
        }
        assert sat["rarity"] == "legendary"
        assert sat["regen_bonus_percent"] == 200
        assert sat["modifiers"] == {"strength": 2}

    def test_expired_satiety_not_reported_and_removed(self, client, db):
        seed(db, strength=10)
        client.post(SATIETY_URL, json=payload(modifiers={"strength": 2}))
        row = regen.get_satiety(db, CID)
        row.expires_at = now_s() - timedelta(minutes=1)
        db.commit()
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["satiety"] is None
        assert body["regen_percent_per_hour"] == 5.0
        assert reload(db).strength == 10

    def test_busy_battle(self, client, db):
        seed(db)
        add_battle(db, CID, status="in_progress", created_at=now_s(), joined_at=now_s())
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["is_resting"] is False
        assert body["busy_reason"] == "battle"

    def test_busy_dungeon(self, client, db):
        seed(db)
        add_dungeon(db, CID, status="active", started_at=now_s() - timedelta(minutes=5))
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["is_resting"] is False
        assert body["busy_reason"] == "dungeon"

    def test_dungeon_lobby_is_resting(self, client, db):
        seed(db)
        add_dungeon(db, CID, status="forming", started_at=None)
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["is_resting"] is True
        assert body["busy_reason"] is None

    def test_busy_gathering(self, client, db):
        seed(db)
        add_gathering(db, CID, started_at=now_s() - timedelta(minutes=5), complete_at=now_s() + timedelta(hours=1))
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["is_resting"] is False
        assert body["busy_reason"] == "gathering"

    def test_finished_gathering_is_resting(self, client, db):
        seed(db)
        add_gathering(
            db, CID,
            started_at=now_s() - timedelta(hours=2),
            complete_at=now_s() - timedelta(hours=1),
            status="completed",
            finished_at=now_s() - timedelta(hours=1),
        )
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["is_resting"] is True

    def test_battle_reported_before_gathering(self, client, db):
        seed(db)
        add_gathering(db, CID, started_at=now_s() - timedelta(minutes=5), complete_at=now_s() + timedelta(hours=1))
        add_battle(db, CID, status="in_progress", created_at=now_s(), joined_at=now_s())
        assert client.get(f"/attributes/{CID}/rest-status").json()["busy_reason"] == "battle"

    def test_satiety_rate_shown_while_busy(self, client, db):
        seed(db)
        client.post(SATIETY_URL, json=payload(rarity="epic", modifiers={}))
        add_battle(db, CID, status="in_progress", created_at=now_s(), joined_at=now_s())
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["is_resting"] is False
        assert body["regen_percent_per_hour"] == pytest.approx(12.5)

    def test_npc(self, client, db):
        seed(db, is_npc=True)
        body = client.get(f"/attributes/{CID}/rest-status").json()
        assert body["is_resting"] is False
        assert body["busy_reason"] is None
        assert body["satiety"] is None

    def test_404(self, client):
        resp = client.get("/attributes/5555/rest-status")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Атрибуты персонажа не найдены"

    def test_public_read_cannot_farm_resources(self, client, db):
        """rest-status is public (no auth, like GET /attributes/{id});
        hammering it must not grant anything beyond real elapsed rest time."""
        seed(db, current_health=0)
        for _ in range(20):
            assert client.get(f"/attributes/{CID}/rest-status").status_code == 200
        assert reload(db).current_health == 0

    @pytest.mark.parametrize("bad", ["abc", "1%20OR%201=1", "1;DROP%20TABLE%20characters"])
    def test_non_integer_id_rejected(self, client, bad):
        assert client.get(f"/attributes/{bad}/rest-status").status_code == 422


# ---------------------------------------------------------------------------
# POST /attributes/internal/settle-regen
# ---------------------------------------------------------------------------


class TestSettleRegenBulk:
    def test_settled_and_missing(self, client, db):
        seed(db, character_id=1, current_health=0, regen_anchor_at=now_s() - timedelta(hours=2))
        seed(db, character_id=2)
        resp = client.post("/attributes/internal/settle-regen", json={"character_ids": [1, 2, 3]})
        assert resp.status_code == 200
        assert resp.json() == {"settled": [1, 2], "missing": [3]}
        assert reload(db, 1).current_health == 10

    @pytest.mark.parametrize(
        "ids", [[], [1, 1], list(range(1, 52)), ["x"]],
    )
    def test_validation(self, client, ids):
        resp = client.post("/attributes/internal/settle-regen", json={"character_ids": ids})
        assert resp.status_code == 422

    def test_fifty_ids_allowed(self, client):
        resp = client.post("/attributes/internal/settle-regen", json={"character_ids": list(range(1, 51))})
        assert resp.status_code == 200
        assert len(resp.json()["missing"]) == 50


# ---------------------------------------------------------------------------
# Gateway protection of internal endpoints
# ---------------------------------------------------------------------------

_GATEWAY_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "docker", "api-gateway")
)


@pytest.mark.parametrize("conf", ["nginx.conf", "nginx.prod.conf"])
def test_internal_attributes_endpoints_blocked_at_gateway(conf):
    path = os.path.join(_GATEWAY_DIR, conf)
    if not os.path.exists(path):
        skip_or_fail_missing(path, f"gateway config {conf}")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    import re

    m = re.search(r"location\s+/attributes/internal/\s*\{([^}]*)\}", src)
    assert m, f"{conf}: /attributes/internal/ must be blocked"
    assert "return 403" in m.group(1)
