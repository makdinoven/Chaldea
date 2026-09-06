"""
FEAT-155 — the starting characteristics are frozen at approval.

The passport block «Оценка при вступлении» promises a record of what a
Скиталец arrived with. Before this feature it was filled by a live call to
character-attributes-service, so it printed the character's *current* build:
the caption lied, and a stranger's passport leaked their actual point spend.

The property under test mirrors rule 12d for the granted kit
(`test_granted_kit_snapshot.py`): **granted == snapshotted**. The subrace preset
is resolved ONCE in the approve handler, and that one result is both sent to
character-attributes-service and written to `characters.starting_attributes`,
so the two cannot diverge.

Also covered: the snapshot survives later stat growth, and a character created
before the column existed reconstructs the subrace preset (never the live
build) and is flagged as a reconstruction.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import database
from database import Base
import models
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


DEFAULT_LOCATION_ID = 700

# A real subrace preset: exactly 100 points (rule 5).
SUBRACE_PRESET = {
    "strength": 12, "agility": 14, "intelligence": 20, "endurance": 8,
    "health": 10, "mana": 12, "energy": 6, "stamina": 9,
    "charisma": 5, "luck": 4,
}

_ADMIN_USER = UserRead(id=1, username="admin", role="admin", permissions=[
    "characters:create", "characters:read", "characters:update",
    "characters:delete", "characters:approve",
])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def stub_outbound():
    """Keep approval and the passport off the network."""
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
        yield user_service


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
        yield {"attributes": attrs}


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

def _preset_subrace(db, subrace_id=4, preset=None):
    subrace = db.query(models.Subrace).filter_by(id_subrace=subrace_id).one()
    subrace.stat_preset = dict(preset if preset is not None else SUBRACE_PRESET)
    db.commit()
    return subrace


def _seed_request(db, class_id=1, subrace_id=4, name="Аэлис"):
    req = models.CharacterRequest(
        user_id=42,
        name=name,
        id_race=2,
        id_subrace=subrace_id,
        id_class=class_id,
        biography="Био",
        personality="Характер",
        appearance="Высокая эльфийка",
        sex="female",
        age=120,
        avatar="https://example.com/a.webp",
        status="pending",
        request_type="creation",
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
# (a) granted == snapshotted
# ===========================================================================

class TestGrantedEqualsSnapshotted:
    def test_approval_writes_the_snapshot(self, db_session, client, cross_service):
        _preset_subrace(db_session)
        req = _seed_request(db_session)

        _approve(client, req.id)

        character = db_session.query(models.Character).one()
        assert character.starting_attributes == SUBRACE_PRESET

    def test_the_snapshot_is_what_was_sent_to_the_attributes_service(
        self, db_session, client, cross_service
    ):
        """
        One resolution, two consumers. If these ever disagree, the passport is
        describing a character that was never created.
        """
        _preset_subrace(db_session)
        req = _seed_request(db_session)

        _approve(client, req.id)

        sent = cross_service["attributes"].call_args.args[1]
        character = db_session.query(models.Character).one()
        assert character.starting_attributes == sent

    def test_the_preset_is_resolved_exactly_once(self, db_session, client, cross_service):
        """A second resolution is a second chance to diverge (D17)."""
        _preset_subrace(db_session)
        req = _seed_request(db_session)

        with patch("crud.generate_attributes_for_subrace",
                   wraps=__import__("crud").generate_attributes_for_subrace) as resolver:
            _approve(client, req.id)

        assert resolver.call_count == 1

    def test_the_snapshot_sums_to_one_hundred(self, db_session, client, cross_service):
        _preset_subrace(db_session)
        req = _seed_request(db_session)
        _approve(client, req.id)

        character = db_session.query(models.Character).one()
        assert sum(character.starting_attributes.values()) == 100

    def test_the_passport_shows_the_snapshot(self, db_session, client, cross_service):
        _preset_subrace(db_session)
        req = _seed_request(db_session)
        _approve(client, req.id)
        character = db_session.query(models.Character).one()

        data = client.get(f"/characters/{character.id}/public").json()
        assert data["starting_attributes"] == character.starting_attributes
        assert data["starting_attributes_is_snapshot"] is True

    def test_two_subraces_are_snapshotted_apart(self, db_session, client, cross_service):
        """The record is per character, not a shared template read at render time."""
        _preset_subrace(db_session, subrace_id=4)
        other = dict(SUBRACE_PRESET, strength=20, agility=6)
        _preset_subrace(db_session, subrace_id=5, preset=other)

        _approve(client, _seed_request(db_session, subrace_id=4, name="Лесная").id)
        _approve(client, _seed_request(db_session, subrace_id=5, name="Иной").id)

        chars = {c.name: c for c in db_session.query(models.Character).all()}
        assert chars["Лесная"].starting_attributes["strength"] == 12
        assert chars["Иной"].starting_attributes["strength"] == 20


# ===========================================================================
# (b) the record does not move
# ===========================================================================

class TestSnapshotIsNotRetroactive:
    def test_editing_the_subrace_preset_leaves_the_record_alone(
        self, db_session, client, cross_service
    ):
        """
        The mirror of the rule-12d kit test: a template edited afterwards must
        not rewrite an already-issued record.
        """
        _preset_subrace(db_session)
        _approve(client, _seed_request(db_session, name="Старая").id)

        _preset_subrace(db_session, preset=dict(SUBRACE_PRESET, strength=40, luck=0))

        db_session.expire_all()
        character = db_session.query(models.Character).filter_by(name="Старая").one()
        assert character.starting_attributes["strength"] == 12

        passport = client.get(f"/characters/{character.id}/public").json()
        assert passport["starting_attributes"]["strength"] == 12
        assert passport["starting_attributes_is_snapshot"] is True

    def test_a_character_approved_after_the_edit_gets_the_new_preset(
        self, db_session, client, cross_service
    ):
        _preset_subrace(db_session)
        _approve(client, _seed_request(db_session, name="Старая").id)

        _preset_subrace(db_session, preset=dict(SUBRACE_PRESET, strength=40, luck=0))
        _approve(client, _seed_request(db_session, name="Новая").id)

        chars = {c.name: c for c in db_session.query(models.Character).all()}
        assert chars["Старая"].starting_attributes["strength"] == 12
        assert chars["Новая"].starting_attributes["strength"] == 40


# ===========================================================================
# (c) a character created before the column existed
# ===========================================================================

class TestPreFeatureCharacter:
    def test_the_subrace_preset_is_reconstructed_and_flagged(
        self, db_session, client, cross_service
    ):
        _preset_subrace(db_session)
        _approve(client, _seed_request(db_session).id)
        character = db_session.query(models.Character).one()

        # Simulate a row written before FEAT-155.
        character.starting_attributes = None
        db_session.commit()

        data = client.get(f"/characters/{character.id}/public").json()
        assert data["starting_attributes"] == SUBRACE_PRESET
        assert data["starting_attributes_is_snapshot"] is False

    def test_the_reconstruction_never_reads_the_live_build(
        self, db_session, client, cross_service, stub_outbound
    ):
        """
        The pre-feature path is exactly where the old code leaked. It must not
        touch character-attributes-service at all.
        """
        _preset_subrace(db_session)
        _approve(client, _seed_request(db_session).id)
        character = db_session.query(models.Character).one()
        character.starting_attributes = None
        db_session.commit()

        stub_outbound.reset_mock()
        client.get(f"/characters/{character.id}/public")

        attribute_calls = [
            c for c in stub_outbound.call_args_list if "/attributes/" in c.args[0]
        ]
        assert attribute_calls == []
