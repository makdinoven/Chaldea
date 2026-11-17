"""
FEAT-214 §3.7 — POST /attributes/internal/storm-damage (character-attributes-service).

  * damage = ceil(max × pct / 100) for HP and stamina;
  * HP floors at `min_health` (default 1) and is never raised — a character
    already at/below the floor keeps their HP; stamina floors at 0;
  * regen is settled BEFORE the damage (the "before" values are post-settle);
  * unknown ids land in `missing`, the rest are still applied;
  * X-Internal-Token required (401), validation (422): bounds, empty list,
    > 200 items, duplicate ids, min_health < 1;
  * security: injection strings / huge numbers rejected, response leaks nothing.
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
import schemas  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db, _storm_damage_amount  # noqa: E402

from tests.regen_shared_tables import (  # noqa: E402
    add_character,
    create_shared_tables,
    drop_shared_tables,
)

URL = "/attributes/internal/storm-damage"
INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


@pytest.fixture(autouse=True)
def _pin_internal_token(monkeypatch):
    """The check reads a module-level constant captured at import — pin it."""
    import auth_http
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN",
                        INTERNAL_HEADERS["X-Internal-Token"])


@pytest.fixture(autouse=True)
def _setup_tables():
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


def seed(db, character_id, **values):
    add_character(db, character_id)
    base = dict(
        current_health=100, max_health=100,
        current_mana=50, max_mana=50,
        current_energy=50, max_energy=50,
        current_stamina=100, max_stamina=100,
        regen_anchor_at=now_s(),
    )
    base.update(values)
    db.add(models.CharacterAttributes(character_id=character_id, **base))
    db.commit()


def reload(db, character_id):
    db.expire_all()
    return db.query(models.CharacterAttributes).filter_by(character_id=character_id).one()


def post(client, items, headers=INTERNAL_HEADERS, **extra):
    body = {"items": items}
    body.update(extra)
    return client.post(URL, json=body, headers=headers)


def item(cid, hp=0.0, st=0.0):
    return {"character_id": cid, "health_pct": hp, "stamina_pct": st}


# ---------------------------------------------------------------------------
# Damage amount helper
# ---------------------------------------------------------------------------


class TestDamageAmount:
    @pytest.mark.parametrize(
        "maximum,pct,expected",
        [
            (100, 10, 10),      # no float noise → not 11
            (100, 0, 0),
            (0, 50, 0),
            (-5, 50, 0),
            (100, 100, 100),
            (333, 10, 34),      # 33.3 → 34
            (7, 1, 1),          # 0.07 → 1 (ceil)
            (1000, 0.5, 5),
            (250, 12.5, 32),    # 31.25 → 32
        ],
    )
    def test_ceil(self, maximum, pct, expected):
        assert _storm_damage_amount(maximum, pct) == expected


# ---------------------------------------------------------------------------
# Happy path & floors
# ---------------------------------------------------------------------------


class TestStormDamage:
    def test_basic_damage(self, client, db):
        seed(db, 1, current_health=80, max_health=200, current_stamina=60, max_stamina=120)
        resp = post(client, [item(1, hp=10, st=25)])
        assert resp.status_code == 200
        assert resp.json() == {
            "applied": [{
                "character_id": 1,
                "health_before": 80, "health_after": 60,
                "stamina_before": 60, "stamina_after": 30,
            }],
            "missing": [],
        }
        a = reload(db, 1)
        assert a.current_health == 60
        assert a.current_stamina == 30

    def test_ceil_applied(self, client, db):
        seed(db, 1, current_health=100, max_health=333, current_stamina=100, max_stamina=7)
        body = post(client, [item(1, hp=10, st=1)]).json()["applied"][0]
        assert body["health_after"] == 100 - 34
        assert body["stamina_after"] == 100 - 1

    def test_hp_floors_at_default_min_health(self, client, db):
        seed(db, 1, current_health=5, max_health=100)
        body = post(client, [item(1, hp=50)]).json()["applied"][0]
        assert body["health_after"] == 1
        assert reload(db, 1).current_health == 1

    def test_hp_floors_at_custom_min_health(self, client, db):
        seed(db, 1, current_health=30, max_health=100)
        body = post(client, [item(1, hp=100)], min_health=10).json()["applied"][0]
        assert body["health_after"] == 10

    def test_hp_exactly_floor_plus_damage(self, client, db):
        seed(db, 1, current_health=11, max_health=100)
        body = post(client, [item(1, hp=10)]).json()["applied"][0]
        assert body["health_after"] == 1

    @pytest.mark.parametrize("current", [0, 1])
    def test_hp_at_or_below_default_floor_unchanged(self, client, db, current):
        seed(db, 1, current_health=current, max_health=100)
        body = post(client, [item(1, hp=50)]).json()["applied"][0]
        assert body["health_before"] == current
        assert body["health_after"] == current
        assert reload(db, 1).current_health == current

    def test_hp_below_custom_floor_never_raised(self, client, db):
        """Floor 20, HP 5 → stays 5 (the storm never heals)."""
        seed(db, 1, current_health=5, max_health=100)
        body = post(client, [item(1, hp=10)], min_health=20).json()["applied"][0]
        assert body["health_after"] == 5
        assert reload(db, 1).current_health == 5

    def test_hp_never_raised_with_zero_pct(self, client, db):
        seed(db, 1, current_health=3, max_health=100)
        body = post(client, [item(1, hp=0)], min_health=50).json()["applied"][0]
        assert body["health_after"] == 3

    def test_stamina_floors_at_zero(self, client, db):
        seed(db, 1, current_stamina=5, max_stamina=100)
        body = post(client, [item(1, st=100)]).json()["applied"][0]
        assert body["stamina_after"] == 0
        assert reload(db, 1).current_stamina == 0

    def test_stamina_zero_stays_zero(self, client, db):
        seed(db, 1, current_stamina=0, max_stamina=100)
        body = post(client, [item(1, st=50)]).json()["applied"][0]
        assert body["stamina_after"] == 0

    def test_zero_pcts_noop(self, client, db):
        seed(db, 1, current_health=70, current_stamina=40)
        body = post(client, [item(1)]).json()["applied"][0]
        assert (body["health_after"], body["stamina_after"]) == (70, 40)

    def test_default_pcts_are_zero(self, client, db):
        seed(db, 1, current_health=70, current_stamina=40)
        resp = post(client, [{"character_id": 1}])
        assert resp.status_code == 200
        body = resp.json()["applied"][0]
        assert (body["health_after"], body["stamina_after"]) == (70, 40)

    def test_zero_max_no_damage(self, client, db):
        seed(db, 1, current_health=0, max_health=0, current_stamina=0, max_stamina=0)
        body = post(client, [item(1, hp=100, st=100)]).json()["applied"][0]
        assert body["health_after"] == 0
        assert body["stamina_after"] == 0

    def test_other_resources_untouched(self, client, db):
        seed(db, 1, current_mana=33, current_energy=22)
        post(client, [item(1, hp=50, st=50)])
        a = reload(db, 1)
        assert a.current_mana == 33
        assert a.current_energy == 22
        assert a.max_health == 100
        assert a.max_stamina == 100

    def test_multiple_characters_and_missing(self, client, db):
        seed(db, 1, current_health=100)
        seed(db, 2, current_health=50)
        resp = post(client, [item(1, hp=20), item(999, hp=20), item(2, hp=20)])
        assert resp.status_code == 200
        data = resp.json()
        assert data["missing"] == [999]
        assert [a["character_id"] for a in data["applied"]] == [1, 2]
        assert reload(db, 1).current_health == 80
        assert reload(db, 2).current_health == 30

    def test_all_missing(self, client):
        resp = post(client, [item(5, hp=10), item(6, st=10)])
        assert resp.status_code == 200
        assert resp.json() == {"applied": [], "missing": [5, 6]}

    def test_repeated_calls_accumulate_down_to_floor(self, client, db):
        seed(db, 1, current_health=25, max_health=100)
        for _ in range(5):
            post(client, [item(1, hp=10)])
        assert reload(db, 1).current_health == 1


# ---------------------------------------------------------------------------
# Regen is settled before the damage
# ---------------------------------------------------------------------------


class TestSettleBeforeDamage:
    def test_regen_credited_then_damage(self, client, db):
        # Same baseline as test_satiety::TestSettleRegenBulk — 2 h idle → +10 HP of 100.
        seed(db, 1, current_health=0, max_health=100,
             current_stamina=100, max_stamina=100,
             regen_anchor_at=now_s() - timedelta(hours=2))
        body = post(client, [item(1, hp=5)]).json()["applied"][0]
        assert body["health_before"] == 10
        assert body["health_after"] == 5
        assert reload(db, 1).current_health == 5

    def test_settled_hp_above_floor_is_damaged(self, client, db):
        """Stored HP 1 (= floor) but regen lifts it — the damage then applies."""
        seed(db, 1, current_health=1, max_health=100,
             regen_anchor_at=now_s() - timedelta(hours=2))
        body = post(client, [item(1, hp=100)]).json()["applied"][0]
        assert body["health_before"] > 1
        assert body["health_after"] == 1

    def test_anchor_advanced(self, client, db):
        old = now_s() - timedelta(hours=2)
        seed(db, 1, current_health=0, max_health=100, regen_anchor_at=old)
        post(client, [item(1)])
        a = reload(db, 1)
        assert a.regen_anchor_at is None or a.regen_anchor_at > old


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_no_token_401(self, client, db):
        seed(db, 1, current_health=100)
        resp = post(client, [item(1, hp=50)], headers={})
        assert resp.status_code == 401
        assert reload(db, 1).current_health == 100

    def test_wrong_token_401(self, client, db):
        seed(db, 1, current_health=100)
        resp = post(client, [item(1, hp=50)], headers={"X-Internal-Token": "nope"})
        assert resp.status_code == 401
        assert reload(db, 1).current_health == 100

    def test_bearer_instead_of_token_401(self, client):
        resp = post(client, [item(1, hp=50)], headers={"Authorization": "Bearer test-internal-token"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Validation (422)
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize(
        "items",
        [
            [],
            [item(0)],
            [item(-1)],
            [item(1, hp=-0.1)],
            [item(1, hp=100.01)],
            [item(1, st=-1)],
            [item(1, st=101)],
            [item(1), item(1)],
            [item(1, hp=10), item(2), item(1, st=10)],
            [{"health_pct": 10}],
            [{"character_id": "abc"}],
            [{"character_id": 1, "health_pct": "lots"}],
        ],
    )
    def test_bad_items(self, client, items):
        assert post(client, items).status_code == 422

    def test_too_many_items(self, client):
        items = [item(i) for i in range(1, schemas.STORM_DAMAGE_MAX_ITEMS + 2)]
        assert post(client, items).status_code == 422

    def test_max_items_allowed(self, client):
        items = [item(i) for i in range(1, schemas.STORM_DAMAGE_MAX_ITEMS + 1)]
        resp = post(client, items)
        assert resp.status_code == 200
        assert len(resp.json()["missing"]) == schemas.STORM_DAMAGE_MAX_ITEMS

    @pytest.mark.parametrize("min_health", [0, -5, "x"])
    def test_bad_min_health(self, client, min_health):
        assert post(client, [item(1)], min_health=min_health).status_code == 422

    def test_missing_items_key(self, client):
        assert client.post(URL, json={}, headers=INTERNAL_HEADERS).status_code == 422

    def test_boundaries_accepted(self, client, db):
        seed(db, 1)
        resp = post(client, [item(1, hp=0, st=100)])
        assert resp.status_code == 200
        resp = post(client, [item(1, hp=100, st=0)])
        assert resp.status_code == 200

    def test_duplicate_does_not_partially_apply(self, client, db):
        seed(db, 1, current_health=100)
        assert post(client, [item(1, hp=50), item(1, hp=50)]).status_code == 422
        assert reload(db, 1).current_health == 100


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


class TestSecurity:
    @pytest.mark.parametrize(
        "cid",
        ["1 OR 1=1", "1; DROP TABLE character_attributes;--", "<script>alert(1)</script>"],
    )
    def test_injection_in_character_id(self, client, db, cid):
        seed(db, 1, current_health=100)
        resp = post(client, [{"character_id": cid, "health_pct": 50}])
        assert resp.status_code == 422
        assert reload(db, 1).current_health == 100

    def test_injection_in_pct(self, client, db):
        seed(db, 1, current_health=100)
        resp = post(client, [{"character_id": 1, "health_pct": "50; DROP TABLE x"}])
        assert resp.status_code == 422
        assert reload(db, 1).current_health == 100

    def test_huge_numbers_rejected(self, client):
        assert post(client, [item(1, hp=1e308)]).status_code == 422

    def test_huge_min_health_never_raises_hp(self, client, db):
        """A caller cannot heal by passing a giant floor."""
        seed(db, 1, current_health=40, max_health=100)
        body = post(client, [item(1, hp=10)], min_health=10**9).json()["applied"][0]
        assert body["health_after"] == 40
        assert reload(db, 1).current_health == 40

    def test_other_character_unaffected(self, client, db):
        seed(db, 1, current_health=100)
        seed(db, 2, current_health=100)
        post(client, [item(1, hp=50)])
        assert reload(db, 2).current_health == 100

    def test_extra_fields_ignored(self, client, db):
        seed(db, 1, current_health=100, max_health=100)
        resp = post(client, [{"character_id": 1, "health_pct": 10, "current_health": 9999}],
                    max_health=1)
        assert resp.status_code == 200
        a = reload(db, 1)
        assert a.current_health == 90
        assert a.max_health == 100
