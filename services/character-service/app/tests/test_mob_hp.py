"""
Tests for mob HP enrichment in location mob endpoints (FEAT-152, Task #4).

The shared `character_attributes` table (owned by character-attributes-service,
same MySQL DB) is read by `crud._get_mob_hp_map` — one batched parameterized
SELECT — to populate `current_hp` / `max_hp` on:
  * GET /characters/mobs/by_location      -> MobInLocation
  * GET /characters/mob-packs/by_location -> PackMemberInLocation (per-group SUM)

Covers:
1. HP populated from character_attributes (crud + endpoint)
2. Mob without an attributes row -> current_hp/max_hp are None, no 500
3. character_attributes table missing entirely (fallback) -> None HP, no 500
4. Respawned mob returns full HP (batched read happens AFTER lazy-respawn pass)
5. Pack member groups carry SUMMED HP across living members
   (documented semantic: 2 members at 20/30 and 10/30 -> 30/60)
6. Backward compatibility of MobInLocation / PackMemberInLocation schemas
7. _get_mob_hp_map unit behavior (empty input, only-requested ids)

The character_attributes table is created via raw DDL in the fixture
(established pattern — see test_add_rewards.py): it is not an ORM model
of character-service, so Base.metadata does not manage it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

from sqlalchemy import text

import database
from database import Base
from main import app, get_db
from fastapi.testclient import TestClient
import models
import schemas
import crud


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ATTRS_DDL = (
    "CREATE TABLE character_attributes ("
    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "  character_id INTEGER NOT NULL,"
    "  current_health INTEGER,"
    "  max_health INTEGER,"
    "  current_mana INTEGER,"
    "  max_mana INTEGER,"
    "  current_energy INTEGER,"
    "  max_energy INTEGER,"
    "  current_stamina INTEGER,"
    "  max_stamina INTEGER"
    ")"
)


@pytest.fixture
def db_session(seed_fk_data):
    """Fresh service tables + a raw character_attributes table (cross-service)."""
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    session.execute(text("DROP TABLE IF EXISTS character_attributes"))
    session.execute(text(_ATTRS_DDL))
    session.commit()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.execute(text("DROP TABLE IF EXISTS character_attributes"))
        session.commit()
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def db_session_no_attrs(seed_fk_data):
    """Service tables only — character_attributes table does NOT exist."""
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    session.execute(text("DROP TABLE IF EXISTS character_attributes"))
    session.commit()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


def _make_client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(db_session):
    """Plain client (both by_location endpoints are public — no auth override)."""
    yield _make_client(db_session)
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_attrs(db_session_no_attrs):
    yield _make_client(db_session_no_attrs)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers (mirror test_mob_respawn.py / test_mob_packs.py)
# ---------------------------------------------------------------------------

def _create_mob_template(db, name="Дикий Волк", tier="normal", level=3,
                         respawn_enabled=False, respawn_seconds=None):
    template = models.MobTemplate(
        name=name, tier=tier, level=level,
        id_race=1, id_subrace=1, id_class=1, sex="genderless",
        base_attributes={"strength": 15, "agility": 20},
        xp_reward=50, gold_reward=10,
        respawn_enabled=respawn_enabled, respawn_seconds=respawn_seconds,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _create_mob_character(db, name="Волк", location_id=1, level=3):
    char = models.Character(
        name=name,
        id_race=1, id_subrace=1, id_class=1, sex="genderless",
        level=level, avatar="", appearance="",
        is_npc=True, npc_role="mob",
        user_id=None, request_id=None,
        currency_balance=0, stat_points=0,
        current_location_id=location_id,
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


def _create_active_mob(db, mob_template_id, character_id, location_id=1,
                       status="alive", battle_id=None, killed_at=None,
                       respawn_at=None):
    am = models.ActiveMob(
        mob_template_id=mob_template_id,
        character_id=character_id,
        location_id=location_id,
        status=status,
        spawn_type="random",
        battle_id=battle_id,
        killed_at=killed_at,
        respawn_at=respawn_at,
    )
    db.add(am)
    db.commit()
    db.refresh(am)
    return am


def _insert_attrs(db, character_id, current_health, max_health):
    db.execute(
        text(
            "INSERT INTO character_attributes "
            "(character_id, current_health, max_health, "
            " current_mana, max_mana, current_energy, max_energy, "
            " current_stamina, max_stamina) "
            "VALUES (:cid, :ch, :mh, 10, 10, 10, 10, 10, 10)"
        ),
        {"cid": character_id, "ch": current_health, "mh": max_health},
    )
    db.commit()


def _pack_payload(members, name="Стая волков"):
    return schemas.MobPackCreate(
        name=name, description="тест",
        respawn_enabled=False, respawn_seconds=None,
        members=[schemas.MobPackMemberInput(mob_template_id=t, quantity=q)
                 for t, q in members],
    )


# ===========================================================================
# 1. HP populated from character_attributes
# ===========================================================================

class TestMobHpPopulated:
    def test_crud_returns_persisted_hp(self, db_session):
        """Alive mob with an attributes row carries its persisted HP."""
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, location_id=10)
        _create_active_mob(db_session, template.id, char.id, location_id=10)
        _insert_attrs(db_session, char.id, current_health=43, max_health=55)

        result = crud.get_mobs_at_location(db_session, location_id=10)

        assert len(result) == 1
        assert result[0]["current_hp"] == 43
        assert result[0]["max_hp"] == 55

    def test_endpoint_returns_hp_fields(self, client, db_session):
        """GET /characters/mobs/by_location exposes current_hp/max_hp."""
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, name="Теневой волк", location_id=7)
        _create_active_mob(db_session, template.id, char.id, location_id=7)
        _insert_attrs(db_session, char.id, current_health=38, max_health=55)

        resp = client.get("/characters/mobs/by_location?location_id=7")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["current_hp"] == 38
        assert data[0]["max_hp"] == 55

    def test_batched_read_maps_hp_per_mob(self, db_session):
        """Several mobs at one location each get their OWN HP values."""
        template = _create_mob_template(db_session)
        expected = {}
        for i, (ch, mh) in enumerate([(10, 30), (25, 40), (55, 55)]):
            char = _create_mob_character(db_session, name=f"Волк{i}", location_id=20)
            _create_active_mob(db_session, template.id, char.id, location_id=20)
            _insert_attrs(db_session, char.id, current_health=ch, max_health=mh)
            expected[char.id] = (ch, mh)

        result = crud.get_mobs_at_location(db_session, location_id=20)

        assert len(result) == 3
        for mob in result:
            ch, mh = expected[mob["character_id"]]
            assert mob["current_hp"] == ch
            assert mob["max_hp"] == mh

    def test_in_battle_mob_shows_last_persisted_hp(self, db_session):
        """in_battle mob shows the last persisted value (documented 3.3 behavior)."""
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, location_id=10)
        _create_active_mob(db_session, template.id, char.id, location_id=10,
                           status="in_battle", battle_id=77)
        _insert_attrs(db_session, char.id, current_health=12, max_health=60)

        result = crud.get_mobs_at_location(db_session, location_id=10)

        assert len(result) == 1
        assert result[0]["status"] == "in_battle"
        assert result[0]["current_hp"] == 12
        assert result[0]["max_hp"] == 60


# ===========================================================================
# 2. Mob without an attributes row -> None, no 500
# ===========================================================================

class TestMobHpMissingRow:
    def test_crud_returns_none_without_attrs_row(self, db_session):
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, location_id=10)
        _create_active_mob(db_session, template.id, char.id, location_id=10)
        # no _insert_attrs call

        result = crud.get_mobs_at_location(db_session, location_id=10)

        assert len(result) == 1
        assert result[0]["current_hp"] is None
        assert result[0]["max_hp"] is None

    def test_endpoint_no_500_without_attrs_row(self, client, db_session):
        template = _create_mob_template(db_session)
        char = _create_mob_character(db_session, location_id=5)
        _create_active_mob(db_session, template.id, char.id, location_id=5)

        resp = client.get("/characters/mobs/by_location?location_id=5")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["current_hp"] is None
        assert data[0]["max_hp"] is None

    def test_mixed_with_and_without_rows(self, db_session):
        """One mob with a row, one without — each resolved independently."""
        template = _create_mob_template(db_session)
        char_with = _create_mob_character(db_session, name="СРядом", location_id=10)
        _create_active_mob(db_session, template.id, char_with.id, location_id=10)
        _insert_attrs(db_session, char_with.id, current_health=20, max_health=30)

        char_without = _create_mob_character(db_session, name="БезРяда", location_id=10)
        _create_active_mob(db_session, template.id, char_without.id, location_id=10)

        result = crud.get_mobs_at_location(db_session, location_id=10)
        by_id = {m["character_id"]: m for m in result}

        assert by_id[char_with.id]["current_hp"] == 20
        assert by_id[char_with.id]["max_hp"] == 30
        assert by_id[char_without.id]["current_hp"] is None
        assert by_id[char_without.id]["max_hp"] is None


# ===========================================================================
# 3. character_attributes table missing entirely (SQLite fallback path)
# ===========================================================================

class TestAttrsTableMissing:
    def test_crud_fallback_to_none(self, db_session_no_attrs):
        """_get_mob_hp_map swallows the missing-table error -> HP None."""
        db = db_session_no_attrs
        template = _create_mob_template(db)
        char = _create_mob_character(db, location_id=10)
        _create_active_mob(db, template.id, char.id, location_id=10)

        result = crud.get_mobs_at_location(db, location_id=10)

        assert len(result) == 1
        assert result[0]["current_hp"] is None
        assert result[0]["max_hp"] is None

    def test_endpoint_no_500_when_table_missing(self, client_no_attrs, db_session_no_attrs):
        db = db_session_no_attrs
        template = _create_mob_template(db)
        char = _create_mob_character(db, location_id=6)
        _create_active_mob(db, template.id, char.id, location_id=6)

        resp = client_no_attrs.get("/characters/mobs/by_location?location_id=6")

        assert resp.status_code == 200
        assert resp.json()[0]["current_hp"] is None


# ===========================================================================
# 4. Respawn: HP read AFTER the lazy-respawn pass -> full HP
# ===========================================================================

class TestRespawnedMobHp:
    def test_respawned_mob_returns_full_hp(self, db_session):
        """Dead mob (0 HP) with expired respawn_at comes back at max_health."""
        template = _create_mob_template(db_session, respawn_enabled=True,
                                        respawn_seconds=60)
        char = _create_mob_character(db_session, location_id=10)
        past = datetime.utcnow() - timedelta(minutes=5)
        _create_active_mob(db_session, template.id, char.id, location_id=10,
                           status="dead", battle_id=42, killed_at=past,
                           respawn_at=past)
        _insert_attrs(db_session, char.id, current_health=0, max_health=55)

        result = crud.get_mobs_at_location(db_session, location_id=10)

        assert len(result) == 1
        assert result[0]["status"] == "alive"
        # Respawn reset current_health = max_health BEFORE the batched HP read.
        assert result[0]["current_hp"] == 55
        assert result[0]["max_hp"] == 55

    def test_respawned_mob_full_hp_via_endpoint(self, client, db_session):
        template = _create_mob_template(db_session, respawn_enabled=True,
                                        respawn_seconds=60)
        char = _create_mob_character(db_session, name="Волк-Респавн", location_id=8)
        past = datetime.utcnow() - timedelta(hours=1)
        _create_active_mob(db_session, template.id, char.id, location_id=8,
                           status="dead", killed_at=past, respawn_at=past)
        _insert_attrs(db_session, char.id, current_health=3, max_health=70)

        resp = client.get("/characters/mobs/by_location?location_id=8")

        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["status"] == "alive"
        assert data[0]["current_hp"] == 70
        assert data[0]["max_hp"] == 70


# ===========================================================================
# 5. Pack member groups: SUMMED HP across living members
# ===========================================================================

class TestPackMemberHp:
    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_group_hp_is_sum_of_members(self, _m, db_session):
        """Documented semantic: 2 members at 20/30 and 10/30 -> group 30/60."""
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=7)

        ids = crud.get_pack_roster(db_session, active_pack.id)["member_character_ids"]
        assert len(ids) == 2
        _insert_attrs(db_session, ids[0], current_health=20, max_health=30)
        _insert_attrs(db_session, ids[1], current_health=10, max_health=30)

        cards = crud.get_packs_at_location(db_session, 7)

        assert len(cards) == 1
        member = cards[0]["members"][0]
        assert member["count"] == 2
        assert member["current_hp"] == 30  # 20 + 10
        assert member["max_hp"] == 60      # 30 + 30

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_dead_member_excluded_from_sum(self, _m, db_session):
        """Only LIVING members are summed (dead ones drop out of the group)."""
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 3)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=9)

        ids = crud.get_pack_roster(db_session, active_pack.id)["member_character_ids"]
        for cid in ids:
            _insert_attrs(db_session, cid, current_health=25, max_health=30)

        # Kill one member.
        dead = db_session.query(models.ActiveMob).filter(
            models.ActiveMob.character_id == ids[0]
        ).first()
        dead.status = "dead"
        db_session.commit()

        cards = crud.get_packs_at_location(db_session, 9)

        member = cards[0]["members"][0]
        assert member["count"] == 2
        assert member["current_hp"] == 50  # 25 + 25 (dead member excluded)
        assert member["max_hp"] == 60

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_group_hp_none_without_attrs_rows(self, _m, db_session):
        """No attributes rows for the group -> HP fields stay None."""
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        crud.place_pack_on_location(db_session, pack.id, location_id=11)
        # no _insert_attrs calls

        cards = crud.get_packs_at_location(db_session, 11)

        member = cards[0]["members"][0]
        assert member["count"] == 2
        assert member["current_hp"] is None
        assert member["max_hp"] is None

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_partial_rows_sum_only_found_members(self, _m, db_session):
        """Member without an attributes row contributes nothing to the sum."""
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=13)

        ids = crud.get_pack_roster(db_session, active_pack.id)["member_character_ids"]
        _insert_attrs(db_session, ids[0], current_health=20, max_health=30)
        # ids[1] has no row

        cards = crud.get_packs_at_location(db_session, 13)

        member = cards[0]["members"][0]
        assert member["count"] == 2
        assert member["current_hp"] == 20
        assert member["max_hp"] == 30

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_pack_endpoint_returns_member_hp(self, _m, client, db_session):
        """GET /characters/mob-packs/by_location exposes summed member HP."""
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=15)

        ids = crud.get_pack_roster(db_session, active_pack.id)["member_character_ids"]
        _insert_attrs(db_session, ids[0], current_health=20, max_health=30)
        _insert_attrs(db_session, ids[1], current_health=10, max_health=30)

        resp = client.get("/characters/mob-packs/by_location?location_id=15")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        member = data[0]["members"][0]
        assert member["current_hp"] == 30
        assert member["max_hp"] == 60

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_multi_template_pack_sums_per_group(self, _m, db_session):
        """Heterogeneous pack: each template-group carries its own sum."""
        t1 = _create_mob_template(db_session, name="Волк")
        t2 = _create_mob_template(db_session, name="Вожак", tier="elite", level=5)
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2), (t2.id, 1)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=17)

        # Map character_ids to their template via ActiveMob rows.
        members = db_session.query(models.ActiveMob).filter(
            models.ActiveMob.pack_group_id == active_pack.id
        ).all()
        for m in members:
            if m.mob_template_id == t1.id:
                _insert_attrs(db_session, m.character_id, current_health=15, max_health=30)
            else:
                _insert_attrs(db_session, m.character_id, current_health=80, max_health=100)

        cards = crud.get_packs_at_location(db_session, 17)

        by_name = {g["name"]: g for g in cards[0]["members"]}
        assert by_name["Волк"]["current_hp"] == 30    # 15 + 15
        assert by_name["Волк"]["max_hp"] == 60        # 30 + 30
        assert by_name["Вожак"]["current_hp"] == 80
        assert by_name["Вожак"]["max_hp"] == 100


# ===========================================================================
# 6. Backward compatibility of the response schemas
# ===========================================================================

class TestSchemaBackwardCompat:
    def test_mob_in_location_validates_without_hp_keys(self):
        """Old-style payload (no HP keys) still validates -> defaults None."""
        mob = schemas.MobInLocation(
            active_mob_id=1, character_id=2, name="Волк",
            level=3, tier="normal", avatar=None, status="alive",
        )
        assert mob.current_hp is None
        assert mob.max_hp is None

    def test_pack_member_validates_without_hp_keys(self):
        member = schemas.PackMemberInLocation(
            name="Волк", tier="normal", level=3, avatar=None, count=2,
        )
        assert member.current_hp is None
        assert member.max_hp is None

    def test_endpoint_keeps_all_preexisting_fields(self, client, db_session):
        """New fields are additive: every pre-FEAT-152 key is still present."""
        template = _create_mob_template(db_session, tier="elite", level=9)
        char = _create_mob_character(db_session, name="Старый Волк",
                                     location_id=21, level=9)
        am = _create_active_mob(db_session, template.id, char.id, location_id=21)
        _insert_attrs(db_session, char.id, current_health=50, max_health=50)

        resp = client.get("/characters/mobs/by_location?location_id=21")

        assert resp.status_code == 200
        data = resp.json()[0]
        assert data["active_mob_id"] == am.id
        assert data["character_id"] == char.id
        assert data["name"] == "Старый Волк"
        assert data["level"] == 9
        assert data["tier"] == "elite"
        assert data["avatar"] == ""
        assert data["status"] == "alive"
        # And the new keys exist in the payload.
        assert "current_hp" in data
        assert "max_hp" in data

    @patch("crud._sync_send_attributes_request", return_value={"id": 100})
    def test_pack_endpoint_keeps_preexisting_fields(self, _m, client, db_session):
        t1 = _create_mob_template(db_session, name="Волк")
        pack = crud.create_mob_pack(db_session, _pack_payload([(t1.id, 2)]))
        active_pack, _ = crud.place_pack_on_location(db_session, pack.id, location_id=23)

        resp = client.get("/characters/mob-packs/by_location?location_id=23")

        assert resp.status_code == 200
        data = resp.json()[0]
        assert data["active_pack_id"] == active_pack.id
        assert data["name"] == "Стая волков"
        assert data["status"] == "alive"
        assert isinstance(data["lead_character_id"], int)
        member = data["members"][0]
        for key in ("name", "tier", "level", "avatar", "count",
                    "current_hp", "max_hp"):
            assert key in member


# ===========================================================================
# 7. _get_mob_hp_map unit behavior
# ===========================================================================

class TestGetMobHpMapUnit:
    def test_empty_ids_returns_empty_map(self, db_session):
        assert crud._get_mob_hp_map(db_session, []) == {}

    def test_returns_only_requested_ids(self, db_session):
        """Batched IN(...) query is scoped to the requested character_ids."""
        _insert_attrs(db_session, 101, current_health=10, max_health=20)
        _insert_attrs(db_session, 102, current_health=30, max_health=40)
        _insert_attrs(db_session, 103, current_health=50, max_health=60)

        hp_map = crud._get_mob_hp_map(db_session, [101, 103])

        assert hp_map == {101: (10, 20), 103: (50, 60)}

    def test_missing_table_returns_empty_map(self, db_session_no_attrs):
        assert crud._get_mob_hp_map(db_session_no_attrs, [1, 2, 3]) == {}
