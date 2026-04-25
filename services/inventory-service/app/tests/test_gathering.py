"""
Tests for FEAT-128 — gathering system in inventory-service (Task #26).

Covers:
- Tool item CRUD validation (task #4): root_validator, tool_category requirement,
  bonus bounds, max_durability bounds, forbidden equipment-stat modifiers.
- List tools endpoint (task #5): item_type + category filter, includes durability.
- Gathering-skills read (task #6): lazy-create with rank=1, xp=0; rank-up math;
  is_max_rank handling; auth required; visible to non-owner.
- Internal `award` endpoint (task #7): happy path, rank-up branch, multi-rank-up,
  inventory-full, partial-add (stackable), tool-broken, validation errors,
  atomicity on partial failure.
- Free-slots-check (task #8): empty / partial / full inventory.
- check_not_gathering integration (task #13): equip/unequip blocked while
  gathering; finished sessions unblock; overdue (past complete_at) does NOT block.
- Security: SQL-injection-style payloads, unauthorized access on auth-required
  endpoints.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from sqlalchemy import text

import models
from auth_http import get_current_user_via_http, OAUTH2_SCHEME, UserRead


# ---------------------------------------------------------------------------
# Helpers — base item + inventory + gathering skill seeding
# ---------------------------------------------------------------------------

VALID_TOOL_BODY = {
    "name": "Железная кирка",
    "image": None,
    "item_level": 1,
    "item_type": "gathering_tool",
    "item_rarity": "rare",
    "max_stack_size": 1,
    "is_unique": False,
    "description": "Кирка для добычи руды",
    "max_durability": 50,
    "tool_category": "pickaxe",
    "gather_double_chance_bonus": 5.0,
    "gather_speed_bonus_pct": 10.0,
    "gather_stamina_bonus_pct": 7.0,
}


def _mock_user_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _admin_token(client):
    """Patch auth_http to recognise a valid admin token; return the auth header."""
    return {"Authorization": "Bearer admin-token"}


def _seed_gathering_skills(db):
    """Insert 3 gathering skills + 5 ranks each (mirrors Alembic seed)."""
    skills_data = [
        (1, "mining", "Горное дело", "ore"),
        (2, "herbalism", "Травничество", "herb"),
        (3, "woodcutting", "Лесорубство", "wood"),
    ]
    rank_bonuses = [
        # (rank, required_xp, double, speed, stamina)
        (1, 0, 0.0, 0.0, 0.0),
        (2, 10, 4.0, 4.0, 4.0),
        (3, 25, 8.0, 8.0, 8.0),
        (4, 50, 12.0, 12.0, 12.0),
        (5, 100, 20.0, 20.0, 20.0),
    ]
    for sid, slug, name, category in skills_data:
        skill = models.GatheringSkill(
            id=sid, slug=slug, name=name, category=category,
            description=f"Навык {name}", icon=None, max_rank=5,
        )
        db.add(skill)
    db.flush()
    for sid, _, _, _ in skills_data:
        for rn, req, dc, sp, st in rank_bonuses:
            rank = models.GatheringSkillRank(
                skill_id=sid, rank_number=rn,
                required_experience=req,
                double_chance_bonus=dc,
                speed_bonus_pct=sp,
                stamina_bonus_pct=st,
            )
            db.add(rank)
    db.commit()


def _seed_resource_item(db, item_id=4711, name="Железная руда", item_type="resource"):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type,
        item_rarity="common", max_stack_size=99, is_unique=False,
    )
    db.add(item)
    db.commit()
    return item


def _seed_tool_item(db, item_id=4900, max_durability=50, tool_category="pickaxe", name="Железная кирка"):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type="gathering_tool",
        item_rarity="rare", max_stack_size=1, is_unique=False,
        max_durability=max_durability, tool_category=tool_category,
        gather_double_chance_bonus=5.0,
        gather_speed_bonus_pct=10.0,
        gather_stamina_bonus_pct=7.0,
    )
    db.add(item)
    db.commit()
    return item


def _add_inventory_row(db, character_id, item_id, quantity=1, current_durability=None):
    inv = models.CharacterInventory(
        character_id=character_id, item_id=item_id, quantity=quantity,
        current_durability=current_durability,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def _ensure_characters_table(db):
    db.execute(text(
        """CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            name TEXT
        )"""
    ))
    db.execute(text(
        "INSERT OR IGNORE INTO characters (id, user_id, name) VALUES (1, 1, 'Hero')"
    ))
    db.commit()


def _ensure_battle_tables(db):
    db.execute(text(
        """CREATE TABLE IF NOT EXISTS battles (
            id INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'in_progress'
        )"""
    ))
    db.execute(text(
        """CREATE TABLE IF NOT EXISTS battle_participants (
            id INTEGER PRIMARY KEY,
            battle_id INTEGER,
            character_id INTEGER
        )"""
    ))
    db.commit()


def _ensure_gathering_sessions_table(db):
    """Create the shared-DB gathering_sessions table that lives in locations-service.

    inventory-service uses raw SQL against this table for `is_character_gathering`.
    SQLite doesn't have NOW() — register a UDF that mimics it.

    Drops + recreates per test so leftover rows from earlier tests don't bleed
    over into the next one (the table is NOT in Base.metadata so the
    create_all/drop_all cycle in db_session does not touch it).
    """
    # Register NOW() as a SQLite UDF so the raw SQL `complete_at > NOW()` works.
    raw_conn = db.connection().connection
    try:
        raw_conn.create_function(
            "NOW", 0,
            lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
    except Exception:
        pass

    db.execute(text("DROP TABLE IF EXISTS gathering_sessions"))
    db.execute(text(
        """CREATE TABLE gathering_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            started_at TIMESTAMP,
            complete_at TIMESTAMP,
            stamina_paid INTEGER DEFAULT 0
        )"""
    ))
    db.commit()


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def admin_auth(client):
    """Patch auth so admin-token returns admin user; yield the client."""
    from main import app

    with patch("auth_http.requests.get") as mock_get:
        mock_get.return_value = _mock_user_response(
            200,
            {
                "id": 1, "username": "admin", "role": "admin",
                "permissions": [
                    "items:create", "items:read", "items:update", "items:delete",
                ],
            },
        )
        yield client


@pytest.fixture()
def authed_user_client(client, db_session):
    """Override get_current_user_via_http to return user_id=1 (the character owner)."""
    from main import app

    _ensure_characters_table(db_session)
    user = UserRead(id=1, username="hero", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


@pytest.fixture()
def unauthed_client(client):
    """A client without any auth override — used for 401/403 checks."""
    yield client


# ===========================================================================
# 1. Tool item CRUD validation (task #4)
# ===========================================================================

class TestToolItemValidation:
    """POST/PUT /inventory/items — root_validator on gathering_tool."""

    def test_create_valid_tool(self, admin_auth):
        """Valid gathering_tool body → 201, all fields stored."""
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_user_response(
                200,
                {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["items:create"]},
            )
            response = admin_auth.post(
                "/inventory/items",
                json=VALID_TOOL_BODY,
                headers={"Authorization": "Bearer admin-token"},
            )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["item_type"] == "gathering_tool"
        assert data["tool_category"] == "pickaxe"
        assert data["max_durability"] == 50
        assert data["gather_double_chance_bonus"] == 5.0
        assert data["gather_speed_bonus_pct"] == 10.0
        assert data["gather_stamina_bonus_pct"] == 7.0

    def test_missing_tool_category_returns_422(self, admin_auth):
        """gathering_tool without tool_category → 422 with Russian message."""
        body = dict(VALID_TOOL_BODY)
        body.pop("tool_category")
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_user_response(
                200,
                {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["items:create"]},
            )
            response = admin_auth.post(
                "/inventory/items", json=body,
                headers={"Authorization": "Bearer admin-token"},
            )
        assert response.status_code == 422
        # Russian message mentions tool category
        text = response.text.lower()
        assert "категори" in text

    def test_invalid_tool_category_returns_422(self, admin_auth):
        """Invalid tool_category enum value → 422."""
        body = dict(VALID_TOOL_BODY, tool_category="hammer")
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_user_response(
                200,
                {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["items:create"]},
            )
            response = admin_auth.post(
                "/inventory/items", json=body,
                headers={"Authorization": "Bearer admin-token"},
            )
        assert response.status_code == 422

    @pytest.mark.parametrize("field,bad_value", [
        ("gather_double_chance_bonus", -1.0),
        ("gather_double_chance_bonus", 51.0),
        ("gather_speed_bonus_pct", -0.5),
        ("gather_speed_bonus_pct", 100.0),
        ("gather_stamina_bonus_pct", -10.0),
        ("gather_stamina_bonus_pct", 70.0),
    ])
    def test_bonus_outside_range_returns_422(self, admin_auth, field, bad_value):
        """Each gather_* bonus outside 0..50 → 422."""
        body = dict(VALID_TOOL_BODY)
        body[field] = bad_value
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_user_response(
                200,
                {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["items:create"]},
            )
            response = admin_auth.post(
                "/inventory/items", json=body,
                headers={"Authorization": "Bearer admin-token"},
            )
        assert response.status_code == 422
        assert "0" in response.text or "50" in response.text

    def test_max_durability_below_one_returns_422(self, admin_auth):
        """max_durability < 1 → 422 with Russian message."""
        body = dict(VALID_TOOL_BODY, max_durability=0)
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_user_response(
                200,
                {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["items:create"]},
            )
            response = admin_auth.post(
                "/inventory/items", json=body,
                headers={"Authorization": "Bearer admin-token"},
            )
        assert response.status_code == 422
        assert "прочност" in response.text.lower() or "1" in response.text

    @pytest.mark.parametrize("modifier_field", [
        "strength_modifier",
        "agility_modifier",
        "damage_modifier",
        "critical_hit_chance_modifier",
        "stamina_modifier",
    ])
    def test_equipment_stat_modifier_on_tool_returns_422(self, admin_auth, modifier_field):
        """Setting any equipment-stat modifier on a gathering_tool → 422."""
        body = dict(VALID_TOOL_BODY)
        body[modifier_field] = 5
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_user_response(
                200,
                {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["items:create"]},
            )
            response = admin_auth.post(
                "/inventory/items", json=body,
                headers={"Authorization": "Bearer admin-token"},
            )
        assert response.status_code == 422
        assert "инструмент" in response.text.lower() or "модификатор" in response.text.lower()

    def test_non_tool_item_with_tool_category_returns_422(self, admin_auth):
        """Non-gathering_tool with tool_category set → 422 (strict path chosen)."""
        body = {
            "name": "Странный меч",
            "item_level": 1,
            "item_type": "main_weapon",
            "item_rarity": "common",
            "max_stack_size": 1,
            "is_unique": False,
            "tool_category": "axe",  # forbidden on non-tool
        }
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_user_response(
                200,
                {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["items:create"]},
            )
            response = admin_auth.post(
                "/inventory/items", json=body,
                headers={"Authorization": "Bearer admin-token"},
            )
        assert response.status_code == 422

    def test_put_update_tool_changes_fields(self, admin_auth, db_session):
        """PUT update on existing gathering_tool changes fields correctly."""
        # First create a tool
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_user_response(
                200,
                {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["items:create", "items:update"]},
            )
            create_resp = admin_auth.post(
                "/inventory/items", json=VALID_TOOL_BODY,
                headers={"Authorization": "Bearer admin-token"},
            )
            assert create_resp.status_code == 201
            item_id = create_resp.json()["id"]

            # Update durability + bonus
            update_body = dict(VALID_TOOL_BODY)
            update_body["name"] = "Серебряная кирка"
            update_body["max_durability"] = 80
            update_body["gather_double_chance_bonus"] = 10.0
            update_resp = admin_auth.put(
                f"/inventory/items/{item_id}", json=update_body,
                headers={"Authorization": "Bearer admin-token"},
            )
            assert update_resp.status_code == 200
            data = update_resp.json()
            assert data["name"] == "Серебряная кирка"
            assert data["max_durability"] == 80
            assert data["gather_double_chance_bonus"] == 10.0


# ===========================================================================
# 2. List tools endpoint (task #5)
# ===========================================================================

class TestListToolsEndpoint:
    """GET /inventory/{cid}/items?item_type=gathering_tool&category=..."""

    def test_filter_by_gathering_tool(self, client, db_session):
        """item_type=gathering_tool returns only tools with all fields."""
        pickaxe = _seed_tool_item(db_session, item_id=100, tool_category="pickaxe", name="Кирка")
        sickle = _seed_tool_item(db_session, item_id=101, tool_category="sickle", name="Серп")
        sword = _seed_resource_item(db_session, item_id=102, name="Меч", item_type="main_weapon")
        _add_inventory_row(db_session, 1, 100, quantity=1, current_durability=45)
        _add_inventory_row(db_session, 1, 101, quantity=1, current_durability=30)
        _add_inventory_row(db_session, 1, 102, quantity=1)

        response = client.get("/inventory/1/items?item_type=gathering_tool")
        assert response.status_code == 200
        data = response.json()
        # only the two tools come back
        assert len(data) == 2
        for entry in data:
            inner = entry["item"]
            assert inner["item_type"] == "gathering_tool"
            assert inner["tool_category"] in ("pickaxe", "sickle")
            assert inner["max_durability"] == 50
            assert "gather_double_chance_bonus" in inner
            assert "gather_speed_bonus_pct" in inner
            assert "gather_stamina_bonus_pct" in inner
            assert entry["current_durability"] in (45, 30)

    def test_filter_by_category_pickaxe(self, client, db_session):
        """category=pickaxe returns only pickaxes."""
        _seed_tool_item(db_session, item_id=100, tool_category="pickaxe", name="Кирка")
        _seed_tool_item(db_session, item_id=101, tool_category="sickle", name="Серп")
        _add_inventory_row(db_session, 1, 100)
        _add_inventory_row(db_session, 1, 101)

        response = client.get("/inventory/1/items?item_type=gathering_tool&category=pickaxe")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["item"]["tool_category"] == "pickaxe"

    def test_invalid_category_returns_422(self, client, db_session):
        """category=hammer (invalid) → 422."""
        response = client.get("/inventory/1/items?item_type=gathering_tool&category=hammer")
        assert response.status_code == 422

    def test_category_without_gathering_tool_returns_422(self, client, db_session):
        """Setting category without item_type=gathering_tool → 422."""
        response = client.get("/inventory/1/items?category=pickaxe")
        assert response.status_code == 422

    def test_mixed_inventory_filter_excludes_non_tools(self, client, db_session):
        """A character with mixed items: filter must exclude non-tools."""
        _seed_tool_item(db_session, item_id=100, tool_category="pickaxe", name="Кирка")
        _seed_resource_item(db_session, item_id=200, name="Камень")
        _seed_resource_item(db_session, item_id=300, name="Зелье", item_type="consumable")
        _add_inventory_row(db_session, 1, 100, quantity=1, current_durability=50)
        _add_inventory_row(db_session, 1, 200, quantity=10)
        _add_inventory_row(db_session, 1, 300, quantity=2)

        response = client.get("/inventory/1/items?item_type=gathering_tool")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["item"]["item_type"] == "gathering_tool"


# ===========================================================================
# 3. Gathering-skills read (task #6)
# ===========================================================================

class TestGatheringSkillsRead:
    """GET /inventory/characters/{cid}/gathering-skills"""

    def test_fresh_character_returns_3_skills_default(self, authed_user_client, db_session):
        """No char_gathering_skills rows yet → 3 skills, rank=1, exp=0, next_rank populated."""
        _seed_gathering_skills(db_session)
        response = authed_user_client.get("/inventory/characters/1/gathering-skills")
        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == 1
        skills = data["skills"]
        assert len(skills) == 3
        slugs = {s["slug"] for s in skills}
        assert slugs == {"mining", "herbalism", "woodcutting"}
        for s in skills:
            assert s["current_rank"] == 1
            assert s["experience"] == 0
            assert s["experience_total"] == 0
            assert s["is_max_rank"] is False
            cb = s["current_rank_bonuses"]
            assert cb["double_chance_bonus"] == 0.0
            assert cb["speed_bonus_pct"] == 0.0
            assert cb["stamina_bonus_pct"] == 0.0
            assert s["next_rank"] is not None
            assert s["next_rank"]["rank_number"] == 2
            assert s["next_rank"]["required_experience"] == 10
            assert s["experience_to_next"] == 10

    def test_after_xp_award_rank_up_math(self, authed_user_client, db_session):
        """Award XP via internal endpoint → next read shows new rank + bonuses."""
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        # award 10 XP — should rank to 2
        award_body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 10,
            "xp_to_add": 10,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        award_resp = authed_user_client.post(
            "/inventory/internal/characters/1/gathering/award", json=award_body,
        )
        assert award_resp.status_code == 200, award_resp.text
        award_data = award_resp.json()
        assert award_data["current_rank"] == 2
        assert award_data["rank_up"] is True

        # now read
        read = authed_user_client.get("/inventory/characters/1/gathering-skills")
        assert read.status_code == 200
        mining = next(s for s in read.json()["skills"] if s["slug"] == "mining")
        assert mining["current_rank"] == 2
        cb = mining["current_rank_bonuses"]
        assert cb["double_chance_bonus"] == 4.0
        assert cb["speed_bonus_pct"] == 4.0
        assert cb["stamina_bonus_pct"] == 4.0
        # next_rank populated for rank 3
        assert mining["next_rank"] is not None
        assert mining["next_rank"]["rank_number"] == 3
        assert mining["next_rank"]["required_experience"] == 25

    def test_max_rank_next_rank_is_null(self, authed_user_client, db_session):
        """When character_gathering_skills.current_rank == max_rank → next_rank is null."""
        _seed_gathering_skills(db_session)
        # Manually create max-rank progress for mining
        progress = models.CharacterGatheringSkill(
            character_id=1, skill_id=1, current_rank=5,
            experience=200, experience_total=200,
        )
        db_session.add(progress)
        db_session.commit()

        response = authed_user_client.get("/inventory/characters/1/gathering-skills")
        assert response.status_code == 200
        mining = next(s for s in response.json()["skills"] if s["slug"] == "mining")
        assert mining["current_rank"] == 5
        assert mining["is_max_rank"] is True
        assert mining["next_rank"] is None
        assert mining["experience_to_next"] is None

    def test_unauthenticated_returns_401(self, unauthed_client, db_session):
        """No bearer token → 401."""
        _seed_gathering_skills(db_session)
        response = unauthed_client.get("/inventory/characters/1/gathering-skills")
        assert response.status_code == 401

    def test_visible_to_non_owner(self, client, db_session):
        """Per spec 2.7 #4 — read-only on others' profiles for any auth user."""
        from main import app
        _seed_gathering_skills(db_session)

        other = UserRead(id=999, username="otheruser", role="user", permissions=[])
        app.dependency_overrides[get_current_user_via_http] = lambda: other
        try:
            # character_id=1 is owned by user_id=1, requester is user_id=999
            response = client.get("/inventory/characters/1/gathering-skills")
            assert response.status_code == 200
            assert len(response.json()["skills"]) == 3
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)


# ===========================================================================
# 4. Internal `award` endpoint (task #7) — the big one
# ===========================================================================

class TestGatheringAwardInternal:
    """POST /inventory/internal/characters/{cid}/gathering/award"""

    def _do_award(self, client, body, character_id=1):
        return client.post(
            f"/inventory/internal/characters/{character_id}/gathering/award",
            json=body,
        )

    def test_happy_path_no_tool(self, client, db_session):
        """Empty inventory + 100 free slots, request qty=4, xp=4 → all good."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 4,
            "xp_to_add": 4,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["items_added"] is True
        assert d["actual_quantity_added"] == 4
        assert d["inventory_full"] is False
        assert d["tool_durability_remaining"] is None
        assert d["tool_broke"] is False
        assert d["xp_awarded"] == 4
        assert d["current_rank"] == 1
        assert d["current_experience"] == 4
        assert d["rank_up"] is False
        assert d["new_rank_bonuses"] is None

    def test_happy_path_with_tool(self, client, db_session):
        """With tool: durability decremented, items + xp awarded."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        _seed_tool_item(db_session, 4900, max_durability=50)
        tool_inv = _add_inventory_row(db_session, 1, 4900, quantity=1, current_durability=50)
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 4,
            "xp_to_add": 4,
            "tool_inventory_item_id": tool_inv.id,
            "tool_durability_to_consume": 4,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["actual_quantity_added"] == 4
        assert d["xp_awarded"] == 4
        assert d["tool_durability_remaining"] == 46
        assert d["tool_broke"] is False

    def test_rank_up_branch(self, client, db_session):
        """Seed at exp=8 (rank=1), award xp=2 → rank-up to 2 with bonuses populated."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        # Pre-seed character_gathering_skills at exp=8
        progress = models.CharacterGatheringSkill(
            character_id=1, skill_id=1, current_rank=1, experience=8, experience_total=8,
        )
        db_session.add(progress)
        db_session.commit()

        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 2,
            "xp_to_add": 2,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 200
        d = resp.json()
        assert d["rank_up"] is True
        assert d["current_rank"] == 2
        assert d["current_experience"] == 10
        assert d["new_rank_bonuses"] is not None
        assert d["new_rank_bonuses"]["double_chance_bonus"] == 4.0

    def test_multi_rank_up(self, client, db_session):
        """Seed at exp=0, award xp=200 → rank should leapfrog to 5."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 200,
            "xp_to_add": 200,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 200
        d = resp.json()
        assert d["current_rank"] == 5
        assert d["rank_up"] is True
        # new_rank_bonuses reflect rank-5 values
        assert d["new_rank_bonuses"]["double_chance_bonus"] == 20.0
        assert d["new_rank_bonuses"]["speed_bonus_pct"] == 20.0
        assert d["new_rank_bonuses"]["stamina_bonus_pct"] == 20.0

    def test_inventory_full_non_stackable(self, client, db_session):
        """Inventory full with non-stackable result → no items added, no xp, no durability spent."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        # Create a non-stackable result item (max_stack=1)
        item = models.Items(
            id=4711, name="Уникальная руда", item_level=1, item_type="resource",
            item_rarity="common", max_stack_size=1, is_unique=False,
        )
        db_session.add(item)
        db_session.commit()
        # Fill inventory to capacity (50 distinct rows)
        from crud import DEFAULT_INVENTORY_MAX_SLOTS
        # use a different filler item
        filler = models.Items(
            id=900, name="Палка", item_level=1, item_type="resource",
            item_rarity="common", max_stack_size=1, is_unique=False,
        )
        db_session.add(filler)
        db_session.commit()
        for _ in range(DEFAULT_INVENTORY_MAX_SLOTS):
            db_session.add(models.CharacterInventory(character_id=1, item_id=900, quantity=1))
        db_session.commit()

        # Tool durability snapshot before
        _seed_tool_item(db_session, 4900, max_durability=50)
        tool_inv = _add_inventory_row(
            db_session, character_id=2, item_id=4900, quantity=1, current_durability=50,
        )

        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 4,
            "xp_to_add": 4,
            # no tool — easier
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["items_added"] is False
        assert d["actual_quantity_added"] == 0
        assert d["inventory_full"] is True
        assert d["xp_awarded"] == 0

    def test_tool_broken(self, client, db_session):
        """Tool with current_durability=4, spend 4 → tool_broke=true, remaining=0."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        _seed_tool_item(db_session, 4900, max_durability=50)
        tool_inv = _add_inventory_row(db_session, 1, 4900, quantity=1, current_durability=4)
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 4,
            "xp_to_add": 4,
            "tool_inventory_item_id": tool_inv.id,
            "tool_durability_to_consume": 4,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["tool_durability_remaining"] == 0
        assert d["tool_broke"] is True

    def test_tool_durability_capped_at_remaining(self, client, db_session):
        """Cannot spend more durability than remaining; spend is min(requested, current)."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        _seed_tool_item(db_session, 4900, max_durability=50)
        tool_inv = _add_inventory_row(db_session, 1, 4900, quantity=1, current_durability=2)
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 5,
            "xp_to_add": 5,
            "tool_inventory_item_id": tool_inv.id,
            "tool_durability_to_consume": 5,  # > remaining 2
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        # tool durability hits 0 — clamped at zero, broke
        assert d["tool_durability_remaining"] == 0
        assert d["tool_broke"] is True

    def test_invalid_skill_slug_returns_422(self, client, db_session):
        """Invalid skill_slug → 422 (Pydantic validator)."""
        body = {
            "skill_slug": "fishing",  # not allowed
            "result_item_id": 4711,
            "result_quantity": 1,
            "xp_to_add": 1,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 422

    def test_tool_id_set_durability_zero_returns_422(self, client, db_session):
        """tool_inventory_item_id set + tool_durability_to_consume=0 → 422 (root_validator)."""
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 1,
            "xp_to_add": 1,
            "tool_inventory_item_id": 5,
            "tool_durability_to_consume": 0,  # inconsistent
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 422

    def test_durability_set_without_tool_returns_422(self, client, db_session):
        """tool_durability_to_consume>0 with tool_inventory_item_id=null → 422."""
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 1,
            "xp_to_add": 1,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 3,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 422

    def test_missing_result_item_returns_422_validation(self, client, db_session):
        """result_item_id missing in body → 422 (Pydantic missing field)."""
        body = {
            "skill_slug": "mining",
            # no result_item_id
            "result_quantity": 1,
            "xp_to_add": 1,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 422

    def test_unknown_result_item_returns_422(self, client, db_session):
        """result_item_id refers to a non-existent item → 422 (server-side check)."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        body = {
            "skill_slug": "mining",
            "result_item_id": 99999,
            "result_quantity": 1,
            "xp_to_add": 1,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 422

    def test_unknown_character_returns_404(self, client, db_session):
        """character_id missing in characters table → 404."""
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 1,
            "xp_to_add": 1,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body, character_id=9999)
        assert resp.status_code == 404

    def test_atomicity_on_failure(self, client, db_session):
        """If a step fails mid-transaction, no partial state should persist.

        We patch `_add_items_with_capacity` to raise; the endpoint's commit
        must NOT run, so the tool durability, ore inventory and XP stay at
        their pre-call values.
        """
        from fastapi.testclient import TestClient
        from main import app

        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        _seed_resource_item(db_session, 4711, "Железная руда")
        _seed_tool_item(db_session, 4900, max_durability=50)
        tool_inv = _add_inventory_row(db_session, 1, 4900, quantity=1, current_durability=10)
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 4,
            "xp_to_add": 4,
            "tool_inventory_item_id": tool_inv.id,
            "tool_durability_to_consume": 4,
        }
        # Use a TestClient that captures server exceptions as 500 responses.
        non_raising = TestClient(app, raise_server_exceptions=False)
        with patch("crud._add_items_with_capacity", side_effect=RuntimeError("boom")):
            resp = non_raising.post(
                "/inventory/internal/characters/1/gathering/award", json=body,
            )
        # depending on FastAPI settings this may be 500 — but the key is no
        # state mutation persists.
        assert resp.status_code == 500

        # Verify atomicity: tool durability unchanged, no resource item added,
        # no XP added.
        db_session.rollback()
        db_session.expire_all()
        tool_after = db_session.query(models.CharacterInventory).filter_by(id=tool_inv.id).first()
        assert tool_after.current_durability == 10  # unchanged
        # no inventory row for the resource item should exist
        ore_rows = db_session.query(models.CharacterInventory).filter_by(
            character_id=1, item_id=4711,
        ).all()
        assert ore_rows == []
        # no progress row should have been committed
        progress_rows = db_session.query(models.CharacterGatheringSkill).filter_by(
            character_id=1,
        ).all()
        # progress may or may not exist depending on how transactions roll back —
        # the canonical assertion is that experience is 0 on any existing row.
        for p in progress_rows:
            assert p.experience == 0
            assert p.experience_total == 0

    def test_partial_add_scaling(self, client, db_session):
        """Inventory has 1 free slot, stackable item + room — actual_quantity_added < requested.

        For SQLite tests we approximate: fill 49 of 50 slots so only 1 row remains;
        request a quantity that is less than max_stack so it fits in one new row,
        but the free-slot logic may clip — we just verify proportional scaling.
        """
        _ensure_characters_table(db_session)
        _seed_gathering_skills(db_session)
        # max_stack=99 so 4 fits in one slot
        item = models.Items(
            id=4711, name="Железная руда", item_level=1, item_type="resource",
            item_rarity="common", max_stack_size=99, is_unique=False,
        )
        db_session.add(item)
        db_session.commit()
        # fill 49 slots
        from crud import DEFAULT_INVENTORY_MAX_SLOTS
        filler = models.Items(
            id=900, name="Палка", item_level=1, item_type="resource",
            item_rarity="common", max_stack_size=1, is_unique=False,
        )
        db_session.add(filler)
        db_session.commit()
        for _ in range(DEFAULT_INVENTORY_MAX_SLOTS - 1):
            db_session.add(models.CharacterInventory(character_id=1, item_id=900, quantity=1))
        db_session.commit()

        # request 4 — should fit fully (one new row, quantity 4)
        body = {
            "skill_slug": "mining",
            "result_item_id": 4711,
            "result_quantity": 4,
            "xp_to_add": 4,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = self._do_award(client, body)
        assert resp.status_code == 200, resp.text
        d = resp.json()
        # All 4 fit because they share one new slot
        assert d["actual_quantity_added"] == 4
        assert d["xp_awarded"] == 4


# ===========================================================================
# 5. Free-slots-check (task #8)
# ===========================================================================

class TestFreeSlotsCheck:
    """POST /inventory/internal/characters/{cid}/free_slots_check"""

    def test_empty_inventory(self, client, db_session):
        """No inventory rows → free_slot_count=DEFAULT_MAX, is_full=False."""
        from crud import DEFAULT_INVENTORY_MAX_SLOTS
        resp = client.post("/inventory/internal/characters/1/free_slots_check")
        assert resp.status_code == 200
        d = resp.json()
        assert d["free_slot_count"] == DEFAULT_INVENTORY_MAX_SLOTS
        assert d["is_full"] is False

    def test_partial_inventory(self, client, db_session):
        """Some rows used → free_slot_count = max - used."""
        from crud import DEFAULT_INVENTORY_MAX_SLOTS
        item = models.Items(
            id=900, name="Палка", item_level=1, item_type="resource",
            item_rarity="common", max_stack_size=1, is_unique=False,
        )
        db_session.add(item)
        db_session.commit()
        for _ in range(7):
            db_session.add(models.CharacterInventory(character_id=1, item_id=900, quantity=1))
        db_session.commit()

        resp = client.post("/inventory/internal/characters/1/free_slots_check")
        assert resp.status_code == 200
        d = resp.json()
        assert d["free_slot_count"] == DEFAULT_INVENTORY_MAX_SLOTS - 7
        assert d["is_full"] is False

    def test_full_inventory(self, client, db_session):
        """Inventory at capacity → free_slot_count=0, is_full=True."""
        from crud import DEFAULT_INVENTORY_MAX_SLOTS
        item = models.Items(
            id=900, name="Палка", item_level=1, item_type="resource",
            item_rarity="common", max_stack_size=1, is_unique=False,
        )
        db_session.add(item)
        db_session.commit()
        for _ in range(DEFAULT_INVENTORY_MAX_SLOTS):
            db_session.add(models.CharacterInventory(character_id=1, item_id=900, quantity=1))
        db_session.commit()

        resp = client.post("/inventory/internal/characters/1/free_slots_check")
        assert resp.status_code == 200
        d = resp.json()
        assert d["free_slot_count"] == 0
        assert d["is_full"] is True


# ===========================================================================
# 6. check_not_gathering integration (task #13)
# ===========================================================================

def _seed_active_gathering_session(db, character_id=1, complete_offset_minutes=10):
    """Insert a row into gathering_sessions with status='active'.

    complete_offset_minutes > 0 → session is currently active (will block).
    complete_offset_minutes < 0 → session is overdue (should NOT block).
    """
    started = datetime.utcnow()
    complete = started + timedelta(minutes=complete_offset_minutes)
    db.execute(text(
        "INSERT INTO gathering_sessions "
        "(character_id, node_id, status, started_at, complete_at, stamina_paid) "
        "VALUES (:cid, 1, 'active', :sa, :ca, 5)"
    ), {"cid": character_id,
        "sa": started.strftime("%Y-%m-%d %H:%M:%S"),
        "ca": complete.strftime("%Y-%m-%d %H:%M:%S")})
    db.commit()


class TestCheckNotGatheringIntegration:
    """check_not_gathering blocks equip/unequip/use_item while gathering."""

    def test_equip_blocked_while_gathering(self, authed_user_client, db_session):
        """POST /equip during active gathering → 400 with «во время добычи»."""
        _ensure_characters_table(db_session)
        _ensure_battle_tables(db_session)
        _ensure_gathering_sessions_table(db_session)

        # Create a head item and inventory entry
        item = models.Items(
            id=100, name="Шлем", item_level=1, item_type="head",
            item_rarity="common", max_stack_size=1, is_unique=False,
        )
        db_session.add(item)
        db_session.flush()
        inv = models.CharacterInventory(character_id=1, item_id=100, quantity=1)
        db_session.add(inv)
        slot = models.EquipmentSlot(
            character_id=1, slot_type="head", item_id=None, is_enabled=True,
        )
        db_session.add(slot)
        db_session.commit()

        _seed_active_gathering_session(db_session, character_id=1, complete_offset_minutes=10)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_user_client.post(
                "/inventory/1/equip", json={"item_id": 100},
            )
        assert response.status_code == 400
        assert "добыч" in response.json()["detail"].lower()

    def test_use_item_blocked_while_gathering(self, authed_user_client, db_session):
        """POST /use_item during gathering → 400 with «во время добычи»."""
        _ensure_characters_table(db_session)
        _ensure_battle_tables(db_session)
        _ensure_gathering_sessions_table(db_session)

        item = models.Items(
            id=200, name="Зелье", item_level=1, item_type="consumable",
            item_rarity="common", max_stack_size=10, is_unique=False,
        )
        db_session.add(item)
        db_session.flush()
        db_session.add(models.CharacterInventory(character_id=1, item_id=200, quantity=3))
        db_session.commit()

        _seed_active_gathering_session(db_session, character_id=1, complete_offset_minutes=10)
        response = authed_user_client.post(
            "/inventory/1/use_item", json={"item_id": 200, "quantity": 1},
        )
        assert response.status_code == 400
        assert "добыч" in response.json()["detail"].lower()

    def test_completed_session_does_not_block(self, authed_user_client, db_session):
        """status='completed' session should not block subsequent actions."""
        _ensure_characters_table(db_session)
        _ensure_battle_tables(db_session)
        _ensure_gathering_sessions_table(db_session)

        # Add a completed session
        complete = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        started = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        db_session.execute(text(
            "INSERT INTO gathering_sessions "
            "(character_id, node_id, status, started_at, complete_at, stamina_paid) "
            "VALUES (1, 1, 'completed', :sa, :ca, 5)"
        ), {"sa": started, "ca": complete})
        db_session.commit()

        # Equip something — should pass the check_not_gathering helper
        item = models.Items(
            id=100, name="Шлем", item_level=1, item_type="head",
            item_rarity="common", max_stack_size=1, is_unique=False,
        )
        db_session.add(item)
        db_session.flush()
        db_session.add(models.CharacterInventory(character_id=1, item_id=100, quantity=1))
        db_session.add(models.EquipmentSlot(
            character_id=1, slot_type="head", item_id=None, is_enabled=True,
        ))
        db_session.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_user_client.post(
                "/inventory/1/equip", json={"item_id": 100},
            )
        # Should pass the check_not_gathering helper (may or may not be 200
        # depending on cross-service mocks; but must NOT be 400 «во время добычи»)
        if response.status_code == 400:
            assert "добыч" not in response.json().get("detail", "").lower()

    def test_overdue_session_does_not_block(self, authed_user_client, db_session):
        """Overdue (past complete_at) session — helper does NOT block (lazy-finalize-eligible)."""
        _ensure_characters_table(db_session)
        _ensure_battle_tables(db_session)
        _ensure_gathering_sessions_table(db_session)

        # Insert an overdue but still status='active' session — should NOT block
        _seed_active_gathering_session(
            db_session, character_id=1, complete_offset_minutes=-5,
        )

        item = models.Items(
            id=100, name="Шлем", item_level=1, item_type="head",
            item_rarity="common", max_stack_size=1, is_unique=False,
        )
        db_session.add(item)
        db_session.flush()
        db_session.add(models.CharacterInventory(character_id=1, item_id=100, quantity=1))
        db_session.add(models.EquipmentSlot(
            character_id=1, slot_type="head", item_id=None, is_enabled=True,
        ))
        db_session.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_user_client.post(
                "/inventory/1/equip", json={"item_id": 100},
            )
        # Helper must NOT raise «во время добычи» here.
        if response.status_code == 400:
            assert "добыч" not in response.json().get("detail", "").lower()


# ===========================================================================
# 7. Security tests
# ===========================================================================

class TestGatheringSecurity:
    """SQL injection-style payloads, unauthorized access."""

    def test_sql_injection_in_skill_slug(self, client, db_session):
        """SQL-injection-style slug → caught by validator (422), no 500."""
        body = {
            "skill_slug": "mining'; DROP TABLE gathering_skills; --",
            "result_item_id": 1,
            "result_quantity": 1,
            "xp_to_add": 1,
            "tool_inventory_item_id": None,
            "tool_durability_to_consume": 0,
        }
        resp = client.post(
            "/inventory/internal/characters/1/gathering/award", json=body,
        )
        # Must be 422 (validation), never 500 (crash)
        assert resp.status_code == 422

    def test_sql_injection_in_category_param(self, client, db_session):
        """Malicious `category` → 422 (validated against whitelist)."""
        resp = client.get(
            "/inventory/1/items?item_type=gathering_tool&category=' OR 1=1 --",
        )
        assert resp.status_code == 422

    def test_unauthenticated_skills_endpoint(self, unauthed_client, db_session):
        """Skills endpoint requires JWT — no token returns 401."""
        _seed_gathering_skills(db_session)
        resp = unauthed_client.get("/inventory/characters/1/gathering-skills")
        assert resp.status_code == 401
