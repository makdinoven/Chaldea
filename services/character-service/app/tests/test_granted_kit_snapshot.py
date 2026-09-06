"""
FEAT-154 (task #33) — rule 12d: the granted starter kit is frozen at approval.

The property under test is **preview == granted == snapshotted**: what the wizard
showed the player, what was actually sent to inventory/skills, and what the
passport shows forever after all come from ONE call to crud.resolve_starter_kit.

Also covered:
- a later admin edit of the kit leaves an existing character's granted_kit
  byte-identical, while a newly approved character gets the new contents
- a character with granted_kit IS NULL (created before the feature, D18) gets a
  live reconstruction and granted_kit_is_snapshot = false
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import database
from database import Base
import models
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


ORIGIN_SHINZO = 7
ORIGIN_MIDDENGERD = 3
DEFAULT_LOCATION_ID = 700

_ADMIN_USER = UserRead(id=1, username="admin", role="admin", permissions=[
    "characters:create", "characters:read", "characters:update",
    "characters:delete", "characters:approve",
])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def stub_outbound():
    """Keep approval off the network entirely (locations, user-service, AMQP)."""
    with patch("main.locations_client") as locations, \
         patch("main.httpx.get") as user_service, \
         patch("main.send_character_approved_notification", new_callable=AsyncMock), \
         patch("main.publish_character_inventory", new_callable=AsyncMock), \
         patch("main.publish_character_skills", new_callable=AsyncMock), \
         patch("main.publish_character_attributes", new_callable=AsyncMock):
        locations.probe_starting_point = AsyncMock(return_value=True)
        locations.get_default_starting_point_id = AsyncMock(return_value=DEFAULT_LOCATION_ID)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"username": "player"}
        user_service.return_value = resp
        yield


@pytest.fixture
def cross_service():
    with patch("crud.send_inventory_request", new_callable=AsyncMock) as inv, \
         patch("crud.send_skills_presets_request", new_callable=AsyncMock) as skills, \
         patch("crud.send_attributes_request", new_callable=AsyncMock) as attrs, \
         patch("crud.assign_character_to_user", new_callable=AsyncMock) as assign:
        inv.return_value = {"status": "ok"}
        skills.return_value = {"status": "ok"}
        attrs.return_value = {"id": 999}
        assign.return_value = True
        yield {"inventory": inv, "skills": skills}


@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = lambda: _ADMIN_USER
    app.dependency_overrides[get_current_user_via_http] = lambda: _ADMIN_USER
    app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_kit(db, class_id=1, origin_id=0, items=None, skills=None, currency=100):
    kit = models.StarterKit(
        class_id=class_id,
        origin_id=origin_id,
        items=items if items is not None else [{"item_id": 4, "quantity": 1}],
        skills=skills if skills is not None else [{"skill_id": 1}],
        currency_amount=currency,
    )
    db.add(kit)
    db.commit()
    db.refresh(kit)
    return kit


def _seed_request(db, origin_id=None, class_id=1, name="Аэлис"):
    req = models.CharacterRequest(
        user_id=42,
        name=name,
        id_race=2,
        id_subrace=4,
        id_class=class_id,
        biography="Био",
        personality="Характер",
        appearance="Высокая эльфийка",
        sex="female",
        age=120,
        avatar="https://example.com/a.webp",
        status="pending",
        request_type="creation",
        origin_id=origin_id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _approve(client, req_id):
    response = client.post(f"/characters/requests/{req_id}/approve")
    assert response.status_code == 200, response.text
    return response.json()


# ===========================================================================
# (a) preview == granted == snapshotted
# ===========================================================================

class TestPreviewEqualsGrantedEqualsSnapshot:
    def test_the_three_views_agree(self, db_session, client, cross_service):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)
        _seed_kit(
            db_session, class_id=1, origin_id=ORIGIN_SHINZO,
            items=[{"item_id": 42, "quantity": 2}, {"item_id": 43, "quantity": 1}],
            skills=[{"skill_id": 9}, {"skill_id": 10}],
            currency=333,
        )

        # 1. What the wizard showed the player on the «Путь» step.
        preview = client.get(
            "/characters/starter-kits/resolve",
            params={"class_id": 1, "origin_id": ORIGIN_SHINZO},
        ).json()

        req = _seed_request(db_session, origin_id=ORIGIN_SHINZO)
        _approve(client, req.id)
        character = db_session.query(models.Character).one()

        # 2. What was actually granted.
        granted_items = cross_service["inventory"].call_args.args[1]
        granted_skill_ids = cross_service["skills"].call_args.kwargs["skill_ids"]

        # 3. What the passport will show forever.
        snapshot = character.granted_kit

        assert preview["items"] == snapshot["items"] == granted_items
        assert [s["skill_id"] for s in snapshot["skills"]] == [
            s["skill_id"] for s in preview["skills"]
        ]
        # granted skills = kit skills + the universal subrace skill (id 7)
        assert granted_skill_ids == [9, 10, 7]
        assert preview["currency_amount"] == snapshot["currency_amount"] == 333
        assert character.currency_balance == 333
        assert snapshot["resolved_from"] == preview["resolved_from"] == "exact"

    def test_snapshot_records_the_moment_of_issue(self, db_session, client, cross_service):
        _seed_kit(db_session, class_id=1, origin_id=0)
        req = _seed_request(db_session)
        _approve(client, req.id)

        snapshot = db_session.query(models.Character).one().granted_kit
        assert "granted_at" in snapshot and snapshot["granted_at"]
        assert set(snapshot.keys()) >= {
            "class_id", "origin_id", "resolved_from", "items", "skills",
            "currency_amount", "granted_at",
        }

    def test_class_default_is_snapshotted_when_no_override_exists(
        self, db_session, client, cross_service
    ):
        """Rule 12b — the system works while the matrix is only partly filled."""
        _seed_kit(db_session, class_id=1, origin_id=0,
                  items=[{"item_id": 4, "quantity": 1}], currency=100)
        req = _seed_request(db_session, origin_id=ORIGIN_MIDDENGERD)
        _approve(client, req.id)

        snapshot = db_session.query(models.Character).one().granted_kit
        assert snapshot["resolved_from"] == "class_default"
        assert snapshot["items"] == [{"item_id": 4, "quantity": 1}]
        assert snapshot["currency_amount"] == 100

    def test_two_origins_of_the_same_class_get_different_kits(
        self, db_session, client, cross_service
    ):
        """Rule 12a — a warrior from Shinzo and one from Middengerd differ."""
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO,
                  items=[{"item_id": 42, "quantity": 1}], currency=333)
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_MIDDENGERD,
                  items=[{"item_id": 77, "quantity": 1}], currency=111)

        first = _seed_request(db_session, origin_id=ORIGIN_SHINZO, name="Шинзо")
        _approve(client, first.id)
        second = _seed_request(db_session, origin_id=ORIGIN_MIDDENGERD, name="Мидден")
        _approve(client, second.id)

        chars = {c.name: c for c in db_session.query(models.Character).all()}
        assert chars["Шинзо"].granted_kit["items"] == [{"item_id": 42, "quantity": 1}]
        assert chars["Мидден"].granted_kit["items"] == [{"item_id": 77, "quantity": 1}]
        assert chars["Шинзо"].currency_balance == 333
        assert chars["Мидден"].currency_balance == 111

    def test_empty_kit_is_snapshotted_honestly(self, db_session, client, cross_service):
        req = _seed_request(db_session, origin_id=ORIGIN_SHINZO)
        _approve(client, req.id)

        snapshot = db_session.query(models.Character).one().granted_kit
        assert snapshot["resolved_from"] == "none"
        assert snapshot["items"] == []
        assert snapshot["skills"] == []
        assert snapshot["currency_amount"] == 0
        cross_service["inventory"].assert_not_called()

    def test_passport_shows_the_snapshot(self, db_session, client, cross_service):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)
        req = _seed_request(db_session)
        _approve(client, req.id)
        character = db_session.query(models.Character).one()

        data = client.get(f"/characters/{character.id}/public").json()
        assert data["granted_kit_is_snapshot"] is True
        assert data["granted_kit"] == character.granted_kit


# ===========================================================================
# (b) a later admin edit must not rewrite an existing passport
# ===========================================================================

class TestSnapshotIsNotRetroactive:
    def test_editing_the_kit_leaves_the_existing_snapshot_byte_identical(
        self, db_session, client, cross_service
    ):
        _seed_kit(db_session, class_id=1, origin_id=0,
                  items=[{"item_id": 4, "quantity": 1}], skills=[{"skill_id": 1}], currency=100)

        old_req = _seed_request(db_session, name="Старый")
        _approve(client, old_req.id)
        old_character = db_session.query(models.Character).filter_by(name="Старый").one()
        frozen = json.dumps(old_character.granted_kit, sort_keys=True, ensure_ascii=False)

        # The admin reworks the class default afterwards.
        response = client.put("/characters/starter-kits/1", json={
            "items": [{"item_id": 99, "quantity": 3}],
            "skills": [{"skill_id": 55}],
            "currency_amount": 5000,
        })
        assert response.status_code == 200

        db_session.expire_all()
        old_character = db_session.query(models.Character).filter_by(name="Старый").one()
        assert json.dumps(
            old_character.granted_kit, sort_keys=True, ensure_ascii=False
        ) == frozen

        # And the passport still reports the record, not a reconstruction.
        passport = client.get(f"/characters/{old_character.id}/public").json()
        assert passport["granted_kit_is_snapshot"] is True
        assert passport["granted_kit"]["items"] == [{"item_id": 4, "quantity": 1}]
        assert passport["granted_kit"]["currency_amount"] == 100

    def test_a_character_approved_after_the_edit_gets_the_new_contents(
        self, db_session, client, cross_service
    ):
        _seed_kit(db_session, class_id=1, origin_id=0,
                  items=[{"item_id": 4, "quantity": 1}], currency=100)

        old_req = _seed_request(db_session, name="Старый")
        _approve(client, old_req.id)

        client.put("/characters/starter-kits/1", json={
            "items": [{"item_id": 99, "quantity": 3}],
            "skills": [{"skill_id": 55}],
            "currency_amount": 5000,
        })

        new_req = _seed_request(db_session, name="Новый")
        _approve(client, new_req.id)

        db_session.expire_all()
        chars = {c.name: c for c in db_session.query(models.Character).all()}
        assert chars["Старый"].granted_kit["items"] == [{"item_id": 4, "quantity": 1}]
        assert chars["Новый"].granted_kit["items"] == [{"item_id": 99, "quantity": 3}]
        assert chars["Новый"].currency_balance == 5000

    def test_deleting_an_override_does_not_touch_an_issued_snapshot(
        self, db_session, client, cross_service
    ):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO,
                  items=[{"item_id": 42, "quantity": 2}], currency=333)

        req = _seed_request(db_session, origin_id=ORIGIN_SHINZO)
        _approve(client, req.id)
        character = db_session.query(models.Character).one()
        frozen = json.dumps(character.granted_kit, sort_keys=True, ensure_ascii=False)

        assert client.delete(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}"
        ).status_code == 200

        db_session.expire_all()
        character = db_session.query(models.Character).one()
        assert json.dumps(character.granted_kit, sort_keys=True, ensure_ascii=False) == frozen
        assert character.granted_kit["items"] == [{"item_id": 42, "quantity": 2}]


# ===========================================================================
# (c) D18 — no snapshot means an honest live reconstruction
# ===========================================================================

class TestNullSnapshotFallback:
    def _seed_pre_feature_character(self, db, origin_id=None):
        char = models.Character(
            name="Ветеран",
            id_race=2, id_subrace=4, id_class=1,
            appearance="Старый персонаж",
            avatar="https://example.com/old.webp",
            user_id=None,
            origin_id=origin_id,
            granted_kit=None,
        )
        db.add(char)
        db.commit()
        db.refresh(char)
        return char

    def test_null_snapshot_falls_back_to_a_live_resolve(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0,
                  items=[{"item_id": 4, "quantity": 1}], currency=100)
        char = self._seed_pre_feature_character(db_session)

        data = client.get(f"/characters/{char.id}/public").json()
        assert data["granted_kit_is_snapshot"] is False
        assert data["granted_kit"]["items"] == [{"item_id": 4, "quantity": 1}]
        assert data["granted_kit"]["currency_amount"] == 100
        assert data["granted_kit"]["resolved_from"] == "exact"

    def test_reconstruction_honours_the_characters_origin(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO,
                  items=[{"item_id": 42, "quantity": 2}], currency=333)
        char = self._seed_pre_feature_character(db_session, origin_id=ORIGIN_SHINZO)

        kit = client.get(f"/characters/{char.id}/public").json()["granted_kit"]
        assert kit["resolved_from"] == "exact"
        assert kit["currency_amount"] == 333

    def test_reconstruction_of_a_class_without_a_kit_is_empty_not_an_error(
        self, db_session, client
    ):
        char = self._seed_pre_feature_character(db_session)

        response = client.get(f"/characters/{char.id}/public")
        assert response.status_code == 200
        data = response.json()
        assert data["granted_kit_is_snapshot"] is False
        assert data["granted_kit"]["resolved_from"] == "none"
        assert data["granted_kit"]["items"] == []

    def test_reconstruction_tracks_later_admin_edits(self, db_session, client):
        """A reconstruction is a live view by definition — unlike a snapshot."""
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)
        char = self._seed_pre_feature_character(db_session)

        assert client.get(f"/characters/{char.id}/public").json()["granted_kit"][
            "currency_amount"
        ] == 100

        client.put("/characters/starter-kits/1", json={
            "items": [], "skills": [], "currency_amount": 777,
        })

        data = client.get(f"/characters/{char.id}/public").json()
        assert data["granted_kit"]["currency_amount"] == 777
        assert data["granted_kit_is_snapshot"] is False
