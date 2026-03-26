"""
QA tests for FEAT-084: Alchemist essence extraction system.

Tests covering extract-essence endpoint, extract-info endpoint,
profession checks, success chance, XP/rank-up, and security.
"""

import pytest
from unittest.mock import patch
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_characters_table(db):
    """Create minimal characters + battle tables for ownership/battle checks."""
    db.execute(text("DROP TABLE IF EXISTS battle_participants"))
    db.execute(text("DROP TABLE IF EXISTS battles"))
    db.execute(text("DROP TABLE IF EXISTS characters"))
    db.execute(text(
        """CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'TestChar',
            user_id INTEGER NOT NULL,
            current_location_id INTEGER DEFAULT 1,
            currency_balance INTEGER DEFAULT 0
        )"""
    ))
    db.execute(text(
        """CREATE TABLE battles (
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending'
        )"""
    ))
    db.execute(text(
        """CREATE TABLE battle_participants (
            id INTEGER PRIMARY KEY,
            battle_id INTEGER NOT NULL,
            character_id INTEGER NOT NULL
        )"""
    ))
    db.commit()


def _insert_character(db, char_id, user_id, name="TestChar"):
    db.execute(text(
        "INSERT OR IGNORE INTO characters (id, name, user_id) VALUES (:cid, :name, :uid)"
    ), {"cid": char_id, "name": name, "uid": user_id})
    db.commit()


def _create_profession(db, prof_id=1, name="Алхимик", slug="alchemist"):
    prof = models.Profession(
        id=prof_id, name=name, slug=slug, description="Test",
        sort_order=1, is_active=True,
    )
    db.add(prof)
    db.flush()
    return prof


def _create_rank(db, profession_id=1, rank_number=1, name="Ученик",
                 required_experience=0):
    rank = models.ProfessionRank(
        profession_id=profession_id, rank_number=rank_number,
        name=name, required_experience=required_experience,
    )
    db.add(rank)
    db.flush()
    return rank


def _create_item(db, item_id, name, item_type="resource", max_stack=99,
                 essence_result_item_id=None, **kwargs):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type,
        item_rarity=kwargs.pop("item_rarity", "common"),
        max_stack_size=max_stack, is_unique=False,
        essence_result_item_id=essence_result_item_id,
        **kwargs,
    )
    db.add(item)
    db.flush()
    return item


def _add_inventory(db, char_id, item_id, quantity):
    inv = models.CharacterInventory(
        character_id=char_id, item_id=item_id, quantity=quantity,
    )
    db.add(inv)
    db.flush()
    return inv


def _assign_profession(db, char_id, profession_id, rank=1, experience=0):
    cp = models.CharacterProfession(
        character_id=char_id, profession_id=profession_id,
        current_rank=rank, experience=experience,
    )
    db.add(cp)
    db.flush()
    return cp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_user1 = UserRead(id=1, username="player1", role="user", permissions=[])


@pytest.fixture()
def extract_env(client, db_session):
    """Full essence extraction test environment: alchemist with crystal."""
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Alchemist")

    # Profession + ranks
    prof = _create_profession(db_session, 1, "Алхимик", "alchemist")
    _create_rank(db_session, profession_id=prof.id, rank_number=1,
                 name="Ученик", required_experience=0)
    _create_rank(db_session, profession_id=prof.id, rank_number=2,
                 name="Подмастерье", required_experience=50)

    # Essence item (result of extraction)
    essence = _create_item(db_session, 100, "Эссенция огня", "resource",
                           max_stack=99)

    # Crystal item (input for extraction) — points to essence
    crystal = _create_item(db_session, 200, "Кристалл огня", "resource",
                           max_stack=99, essence_result_item_id=essence.id)

    # Regular resource (not a crystal — no essence_result_item_id)
    ore = _create_item(db_session, 300, "Железная руда", "resource",
                       max_stack=99)

    # Add crystal and ore to inventory
    crystal_inv = _add_inventory(db_session, 1, crystal.id, 5)
    ore_inv = _add_inventory(db_session, 1, ore.id, 10)

    _assign_profession(db_session, 1, prof.id, rank=1, experience=0)
    db_session.commit()

    from main import app
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    yield {
        "client": client,
        "db": db_session,
        "app": app,
        "profession": prof,
        "crystal": crystal,
        "essence": essence,
        "ore": ore,
        "crystal_inv": crystal_inv,
        "ore_inv": ore_inv,
    }

    app.dependency_overrides.pop(get_current_user_via_http, None)


# ===========================================================================
# 1. Happy path — successful extraction
# ===========================================================================

class TestExtractHappyPath:

    def test_extract_essence_success(self, extract_env):
        """Mock random to succeed. Verify: crystal consumed, essence added,
        correct response fields."""
        c = extract_env["client"]
        db = extract_env["db"]
        crystal_inv = extract_env["crystal_inv"]
        essence = extract_env["essence"]

        with patch("main.random.random", return_value=0.5):
            resp = c.post("/inventory/crafting/1/extract-essence", json={
                "crystal_item_id": crystal_inv.id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["crystal_name"] == "Кристалл огня"
        assert data["essence_name"] == "Эссенция огня"
        assert data["crystal_consumed"] is True
        assert data["xp_earned"] == 10
        assert data["new_total_xp"] == 10

        # Verify DB: crystal quantity decreased
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == crystal_inv.id
        ).first()
        assert inv.quantity == 4  # was 5

        # Verify DB: essence added
        ess_inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == essence.id,
        ).first()
        assert ess_inv is not None
        assert ess_inv.quantity == 1


# ===========================================================================
# 2. Failed extraction
# ===========================================================================

class TestExtractFailed:

    def test_extract_failure_crystal_consumed_no_essence(self, extract_env):
        """Mock random to fail. Verify: crystal consumed, no essence added,
        response success=false."""
        c = extract_env["client"]
        db = extract_env["db"]
        crystal_inv = extract_env["crystal_inv"]
        essence = extract_env["essence"]

        with patch("main.random.random", return_value=0.9):
            resp = c.post("/inventory/crafting/1/extract-essence", json={
                "crystal_item_id": crystal_inv.id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["crystal_name"] == "Кристалл огня"
        assert data["essence_name"] is None
        assert data["crystal_consumed"] is True

        # Verify DB: crystal quantity decreased
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == crystal_inv.id
        ).first()
        assert inv.quantity == 4

        # Verify DB: no essence added
        ess_inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == essence.id,
        ).first()
        assert ess_inv is None


# ===========================================================================
# 3. Non-alchemist — blacksmith tries to extract
# ===========================================================================

class TestNonAlchemist:

    def test_blacksmith_cannot_extract(self, extract_env):
        """Blacksmith tries to extract. Expect 400."""
        db = extract_env["db"]
        c = extract_env["client"]
        crystal_inv = extract_env["crystal_inv"]

        # Replace profession to blacksmith
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        db.delete(cp)
        db.flush()

        prof2 = _create_profession(db, 2, "Кузнец", "blacksmith")
        _create_rank(db, profession_id=prof2.id, rank_number=1, name="Новичок")
        _assign_profession(db, 1, prof2.id, rank=1)
        db.commit()

        resp = c.post("/inventory/crafting/1/extract-essence", json={
            "crystal_item_id": crystal_inv.id,
        })

        assert resp.status_code == 400
        assert "алхимик" in resp.json()["detail"].lower()


# ===========================================================================
# 4. No profession
# ===========================================================================

class TestNoProfession:

    def test_no_profession_returns_400(self, extract_env):
        """Character without profession tries to extract. Expect 400."""
        db = extract_env["db"]
        c = extract_env["client"]
        crystal_inv = extract_env["crystal_inv"]

        # Create character without profession
        _insert_character(db, 3, user_id=1, name="NoProfChar")
        db.commit()

        resp = c.post("/inventory/crafting/3/extract-essence", json={
            "crystal_item_id": crystal_inv.id,
        })

        assert resp.status_code == 400
        assert "нет профессии" in resp.json()["detail"]


# ===========================================================================
# 5. Not a crystal — regular resource
# ===========================================================================

class TestNotACrystal:

    def test_regular_resource_returns_400(self, extract_env):
        """Try to extract from a regular resource (no essence_result_item_id).
        Expect 400."""
        c = extract_env["client"]
        ore_inv = extract_env["ore_inv"]

        resp = c.post("/inventory/crafting/1/extract-essence", json={
            "crystal_item_id": ore_inv.id,
        })

        assert resp.status_code == 400
        assert "не является кристаллом" in resp.json()["detail"]


# ===========================================================================
# 6. Crystal not in inventory — invalid ID
# ===========================================================================

class TestCrystalNotInInventory:

    def test_invalid_crystal_item_id_returns_404(self, extract_env):
        """Invalid crystal_item_id. Expect 404."""
        c = extract_env["client"]

        resp = c.post("/inventory/crafting/1/extract-essence", json={
            "crystal_item_id": 99999,
        })

        assert resp.status_code == 404
        assert "не найден" in resp.json()["detail"]


# ===========================================================================
# 7. Success chance — boundary test at 75%
# ===========================================================================

class TestSuccessChanceBoundary:

    def test_random_074_is_success(self, extract_env):
        """Roll 0.74 (< 0.75) = success."""
        c = extract_env["client"]

        with patch("main.random.random", return_value=0.74):
            resp = c.post("/inventory/crafting/1/extract-essence", json={
                "crystal_item_id": extract_env["crystal_inv"].id,
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_random_075_is_failure(self, extract_env):
        """Roll 0.75 (>= 0.75) = failure."""
        c = extract_env["client"]

        with patch("main.random.random", return_value=0.75):
            resp = c.post("/inventory/crafting/1/extract-essence", json={
                "crystal_item_id": extract_env["crystal_inv"].id,
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_random_076_is_failure(self, extract_env):
        """Roll 0.76 (> 0.75) = failure."""
        c = extract_env["client"]

        with patch("main.random.random", return_value=0.76):
            resp = c.post("/inventory/crafting/1/extract-essence", json={
                "crystal_item_id": extract_env["crystal_inv"].id,
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is False


# ===========================================================================
# 8. XP awarded — on both success and failure
# ===========================================================================

class TestXPAwarded:

    def test_xp_awarded_on_success(self, extract_env):
        """Verify 10 XP awarded on successful extraction."""
        c = extract_env["client"]

        with patch("main.random.random", return_value=0.1):
            resp = c.post("/inventory/crafting/1/extract-essence", json={
                "crystal_item_id": extract_env["crystal_inv"].id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["xp_earned"] == 10
        assert data["new_total_xp"] == 10

    def test_xp_awarded_on_failure(self, extract_env):
        """Verify 10 XP awarded even on failed extraction."""
        c = extract_env["client"]

        with patch("main.random.random", return_value=0.99):
            resp = c.post("/inventory/crafting/1/extract-essence", json={
                "crystal_item_id": extract_env["crystal_inv"].id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["xp_earned"] == 10
        assert data["new_total_xp"] == 10


# ===========================================================================
# 9. Rank-up on extraction
# ===========================================================================

class TestRankUp:

    def test_rank_up_when_xp_reaches_threshold(self, extract_env):
        """Set XP near rank-up threshold (50), extract once, verify rank-up."""
        db = extract_env["db"]
        c = extract_env["client"]

        # Set XP to 40, extraction awards 10 -> total 50 -> rank 2
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        cp.experience = 40
        db.commit()

        with patch("main.random.random", return_value=0.1):
            resp = c.post("/inventory/crafting/1/extract-essence", json={
                "crystal_item_id": extract_env["crystal_inv"].id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_earned"] == 10
        assert data["new_total_xp"] == 50
        assert data["rank_up"] is True
        assert data["new_rank_name"] == "Подмастерье"

        # Verify DB
        db.expire_all()
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        assert cp.current_rank == 2
        assert cp.experience == 50


# ===========================================================================
# 10. Extract-info endpoint — returns crystals
# ===========================================================================

class TestExtractInfo:

    def test_extract_info_returns_crystals(self, extract_env):
        """Verify GET returns only crystals (items with essence_result_item_id set)."""
        c = extract_env["client"]

        resp = c.get("/inventory/crafting/1/extract-info")

        assert resp.status_code == 200
        data = resp.json()
        assert "crystals" in data
        assert len(data["crystals"]) == 1  # only the crystal, not the ore

        crystal = data["crystals"][0]
        assert crystal["name"] == "Кристалл огня"
        assert crystal["essence_name"] == "Эссенция огня"
        assert crystal["quantity"] == 5
        assert crystal["success_chance"] == 75
        assert crystal["item_id"] == 200
        assert "inventory_item_id" in crystal


# ===========================================================================
# 11. Extract-info empty — no crystals in inventory
# ===========================================================================

class TestExtractInfoEmpty:

    def test_extract_info_no_crystals_returns_empty(self, extract_env):
        """Remove all crystals from inventory, verify empty list."""
        db = extract_env["db"]
        c = extract_env["client"]

        # Delete crystal from inventory
        crystal_inv = extract_env["crystal_inv"]
        db.delete(crystal_inv)
        db.commit()

        resp = c.get("/inventory/crafting/1/extract-info")

        assert resp.status_code == 200
        data = resp.json()
        assert data["crystals"] == []


# ===========================================================================
# 12. Security — no auth, wrong character
# ===========================================================================

class TestExtractionSecurity:

    def test_extract_no_auth_401(self, client):
        """No auth token -> 401."""
        resp = client.post("/inventory/crafting/1/extract-essence", json={
            "crystal_item_id": 1,
        })
        assert resp.status_code == 401

    def test_extract_info_no_auth_401(self, client):
        """No auth token on extract-info -> 401."""
        resp = client.get("/inventory/crafting/1/extract-info")
        assert resp.status_code == 401

    def test_extract_wrong_character_403(self, extract_env):
        """Trying to extract for another user's character -> 403."""
        db = extract_env["db"]
        c = extract_env["client"]

        _insert_character(db, 2, user_id=999, name="OtherPlayer")
        db.commit()

        resp = c.post("/inventory/crafting/2/extract-essence", json={
            "crystal_item_id": 1,
        })
        assert resp.status_code == 403

    def test_extract_info_wrong_character_403(self, extract_env):
        """Trying to get extract-info for another user's character -> 403."""
        db = extract_env["db"]
        c = extract_env["client"]

        _insert_character(db, 2, user_id=999, name="OtherPlayer")
        db.commit()

        resp = c.get("/inventory/crafting/2/extract-info")
        assert resp.status_code == 403


# ===========================================================================
# 13. Battle lock — character in battle can't extract
# ===========================================================================

class TestBattleLock:

    def test_extract_blocked_during_battle(self, extract_env):
        """Character in active battle cannot extract."""
        db = extract_env["db"]
        c = extract_env["client"]

        # Create active battle with character as participant
        db.execute(text(
            "INSERT INTO battles (id, status) VALUES (1, 'active')"
        ))
        db.execute(text(
            "INSERT INTO battle_participants (id, battle_id, character_id) VALUES (1, 1, 1)"
        ))
        db.commit()

        resp = c.post("/inventory/crafting/1/extract-essence", json={
            "crystal_item_id": extract_env["crystal_inv"].id,
        })

        assert resp.status_code == 400
        assert "бо" in resp.json()["detail"].lower()  # "боя" or "бою"
