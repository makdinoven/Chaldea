"""
Tests for mob packs (FEAT-147): named heterogeneous groups of mobs.

Covers:
1. Pack template CRUD (create / detail / update-replace-members / delete) + endpoints
2. place_pack_on_location — spawns every member ×quantity, tags pack_group_id
3. get_packs_at_location — composition grouping, lead = smallest living member id,
   lazy pack-level respawn
4. get_mobs_at_location — excludes packed mobs (shown only via the pack card)
5. get_pack_roster — living member character_ids (internal, battle-service)
6. Pack status rollup on member death (all dead -> pack dead + respawn_at)
7. delete_active_mob_pack / delete_mob_pack teardown (no leaked mobs)
8. Security / auth (admin endpoints gated, public/internal open)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

import database
from database import Base
from main import app, get_db
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from fastapi.testclient import TestClient
import models
import schemas
import crud


_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=["mobs:manage"],
)


# ---------------------------------------------------------------------------
# Fixtures (mirror test_mob_spawning.py)
# ---------------------------------------------------------------------------

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

    def override_admin():
        return _ADMIN_USER

    def override_token():
        return "fake-admin-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def noauth_client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_mob_template(db, name="Дикий Волк", tier="normal", level=3):
    template = models.MobTemplate(
        name=name, tier=tier, level=level,
        id_race=1, id_subrace=1, id_class=1, sex="genderless",
        base_attributes={"strength": 15, "agility": 20},
        xp_reward=50, gold_reward=10,
        respawn_enabled=False, respawn_seconds=None,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _pack_payload(members, name="Стая волков", respawn_enabled=False, respawn_seconds=None):
    return schemas.MobPackCreate(
        name=name, description="тест",
        respawn_enabled=respawn_enabled, respawn_seconds=respawn_seconds,
        members=[schemas.MobPackMemberInput(mob_template_id=t, quantity=q) for t, q in members],
    )


# ===========================================================================
# 1. Pack template CRUD
# ===========================================================================

class TestPackTemplateCrud:
    def test_create_pack_with_members(self, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        t2 = _create_mob_template(db_session, name="Вожак", tier="elite")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 3), (t2.id, 1)]))

        detail = crud.get_mob_pack_detail(db_session, pack.id)
        assert detail["name"] == "Стая волков"
        assert len(detail["members"]) == 2
        by_id = {m["mob_template_id"]: m for m in detail["members"]}
        assert by_id[t1.id]["quantity"] == 3
        assert by_id[t2.id]["quantity"] == 1
        assert by_id[t2.id]["template_name"] == "Вожак"

    def test_update_replaces_members(self, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        t2 = _create_mob_template(db_session, name="Медведь")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))

        crud.update_mob_pack(
            db_session, pack,
            schemas.MobPackUpdate(
                name="Новое имя",
                members=[schemas.MobPackMemberInput(mob_template_id=t2.id, quantity=5)],
            ),
        )
        detail = crud.get_mob_pack_detail(db_session, pack.id)
        assert detail["name"] == "Новое имя"
        assert len(detail["members"]) == 1
        assert detail["members"][0]["mob_template_id"] == t2.id
        assert detail["members"][0]["quantity"] == 5

    def test_list_counts(self, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        t2 = _create_mob_template(db_session, name="Вожак")
        crud.create_mob_pack(db_session, _pack_payload([(t1.id, 3), (t2.id, 2)], name="A"))
        items, total = crud.get_mob_packs(db_session)
        assert total == 1
        assert items[0]["member_count"] == 2
        assert items[0]["total_mobs"] == 5

    def test_create_endpoint(self, client, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        resp = client.post("/characters/admin/mob-packs", json={
            "name": "Стая", "respawn_enabled": False, "respawn_seconds": None,
            "members": [{"mob_template_id": t1.id, "quantity": 4}],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Стая"
        assert data["members"][0]["quantity"] == 4

    def test_get_detail_404(self, client, db_session):
        assert client.get("/characters/admin/mob-packs/99999").status_code == 404


# ===========================================================================
# 2. Placement
# ===========================================================================

class TestPlacePack:
    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_place_spawns_all_members(self, _m, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        t2 = _create_mob_template(db_session, name="Вожак", tier="elite")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 3), (t2.id, 1)]))

        active_pack, created = crud.place_pack_on_location(db_session, pack.id, location_id=42)
        assert created == 4

        members = db_session.query(models.ActiveMob).filter(
            models.ActiveMob.pack_group_id == active_pack.id
        ).all()
        assert len(members) == 4
        # Members are tagged and located correctly.
        assert all(m.location_id == 42 for m in members)
        assert all(m.pack_group_id == active_pack.id for m in members)

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_place_empty_pack_raises(self, _m, db_session):
        pack = crud.create_mob_pack(db_session, _pack_payload([]))
        with pytest.raises(ValueError):
            crud.place_pack_on_location(db_session, pack.id, location_id=1)


# ===========================================================================
# 3. Location display + roster
# ===========================================================================

class TestPackDisplayAndRoster:
    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_packs_at_location_composition_and_lead(self, _m, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        t2 = _create_mob_template(db_session, name="Вожак", tier="elite")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2), (t2.id, 1)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=7)

        cards = crud.get_packs_at_location(db_session, 7)
        assert len(cards) == 1
        card = cards[0]
        assert card["active_pack_id"] == active_pack.id
        comp = {m["name"]: m["count"] for m in card["members"]}
        assert comp == {"Волк": 2, "Вожак": 1}

        roster = crud.get_pack_roster(db_session, active_pack.id)
        assert len(roster["member_character_ids"]) == 3
        assert card["lead_character_id"] == min(roster["member_character_ids"])
        assert roster["lead_character_id"] == card["lead_character_id"]

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_packed_mobs_excluded_from_standalone_list(self, _m, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 3)]))
        crud.place_pack_on_location(db_session, pack.id, location_id=9)

        # Standalone mob list must not include pack members.
        assert crud.get_mobs_at_location(db_session, 9) == []

    def test_roster_404(self, client, db_session):
        assert client.get("/characters/internal/mob-pack/99999").status_code == 404

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_by_location_endpoint(self, _m, client, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        crud.place_pack_on_location(db_session, pack.id, location_id=11)

        resp = client.get("/characters/mob-packs/by_location?location_id=11")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["members"][0]["count"] == 2


# ===========================================================================
# 4. Status rollup on member death
# ===========================================================================

class TestPackRollup:
    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_all_dead_marks_pack_dead(self, _m, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=3)
        ids = crud.get_pack_roster(db_session, active_pack.id)["member_character_ids"]

        crud.update_active_mob_status(db_session, ids[0], "dead")
        ap = crud.get_active_mob_pack_by_id(db_session, active_pack.id)
        assert ap.status == "alive"  # one still alive

        crud.update_active_mob_status(db_session, ids[1], "dead")
        ap = crud.get_active_mob_pack_by_id(db_session, active_pack.id)
        assert ap.status == "dead"
        # respawn disabled -> pack no longer shown
        assert crud.get_packs_at_location(db_session, 3) == []

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_dead_pack_lazy_respawn(self, _m, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(
            db_session, _pack_payload([(t1.id, 2)], respawn_enabled=True, respawn_seconds=60)
        )
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=4)
        ids = crud.get_pack_roster(db_session, active_pack.id)["member_character_ids"]
        for cid in ids:
            crud.update_active_mob_status(db_session, cid, "dead")

        ap = crud.get_active_mob_pack_by_id(db_session, active_pack.id)
        assert ap.status == "dead"
        assert ap.respawn_at is not None
        # Force respawn_at into the past, then a location read should revive it.
        ap.respawn_at = datetime.utcnow() - timedelta(seconds=5)
        db_session.commit()

        cards = crud.get_packs_at_location(db_session, 4)
        assert len(cards) == 1
        ap = crud.get_active_mob_pack_by_id(db_session, active_pack.id)
        assert ap.status == "alive"
        # Fresh members were created.
        assert len(crud.get_pack_roster(db_session, active_pack.id)["member_character_ids"]) == 2


# ===========================================================================
# 5. Teardown
# ===========================================================================

class TestPackTeardown:
    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_delete_active_pack_removes_mobs(self, _m, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=6)
        member_char_ids = [m.character_id for m in db_session.query(models.ActiveMob).filter(
            models.ActiveMob.pack_group_id == active_pack.id).all()]

        crud.delete_active_mob_pack(db_session, active_pack)

        assert crud.get_active_mob_pack_by_id(db_session, active_pack.id) is None
        for cid in member_char_ids:
            assert db_session.query(models.Character).filter_by(id=cid).first() is None

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_delete_template_tears_down_instances(self, _m, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=8)

        crud.delete_mob_pack(db_session, pack)

        # No orphaned active mobs left behind (would otherwise leak as standalone).
        assert db_session.query(models.ActiveMob).filter(
            models.ActiveMob.pack_group_id == active_pack.id).count() == 0
        assert db_session.query(models.ActiveMobPack).filter_by(id=active_pack.id).first() is None
        assert db_session.query(models.MobPack).filter_by(id=pack.id).first() is None


# ===========================================================================
# 6. Auth
# ===========================================================================

class TestPackAuth:
    def test_admin_list_requires_auth(self, noauth_client, db_session):
        assert noauth_client.get("/characters/admin/mob-packs").status_code in (401, 403)

    def test_place_requires_auth(self, noauth_client, db_session):
        resp = noauth_client.post(
            "/characters/admin/mob-packs/place",
            json={"pack_id": 1, "location_id": 1},
        )
        assert resp.status_code in (401, 403)

    def test_public_by_location_no_auth(self, noauth_client, db_session):
        assert noauth_client.get(
            "/characters/mob-packs/by_location?location_id=1"
        ).status_code == 200
