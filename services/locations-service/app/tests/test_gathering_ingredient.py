"""
FEAT-165 — 4th gathering category `ingredient` (skill `foraging`, «Собирательство»).

Covers:
  * migration 043 vs ORM enum vs the admin Literal;
  * category -> skill slug maps (start and finalize), toolless set;
  * _compute_effective_gather_params: toolless = no x2 penalty, rank double
    chance applies, same caps; tool categories unchanged;
  * crud.start_gathering: a tool sent for an ingredient node -> 422 before any
    tool lookup / stamina spend; without a tool the session gets base time
    (with rank speed) and the rank double chance;
  * finalize sends skill_slug='foraging' with no tool / zero durability to
    inventory-service (contract mirrored in inventory's test_gathering.py);
  * `tool_required` in the player node payload.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import crud
import models
import schemas
from auth_http import get_current_user_via_http, UserRead
from main import app

_VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")

RANK3 = {"speed_pct": 8.0, "stamina_pct": 8.0, "double_chance_pct": 8.0}

# Must stay identical to LOCATIONS_FORAGING_PAYLOAD in
# services/inventory-service/app/tests/test_gathering.py (contract test).
EXPECTED_INVENTORY_PAYLOAD = {
    "skill_slug": "foraging",
    "result_item_id": 4712,
    "result_quantity": 3,
    "xp_to_add": 3,
    "tool_inventory_item_id": None,
    "tool_durability_to_consume": 0,
}


def _load_migration(filename):
    path = os.path.join(_VERSIONS_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ===========================================================================
# 1. Schema: migration 043 == ORM == admin Literal
# ===========================================================================

class TestMigration043:

    @pytest.fixture(scope="class")
    def m043(self):
        return _load_migration("043_gathering_ingredient_category.py")

    def test_orm_enum_matches_migration(self, m043):
        orm_values = tuple(models.GatheringNode.__table__.c.category.type.enums)
        assert orm_values == m043.CATEGORIES_NEW
        assert m043.CATEGORIES_OLD == ("ore", "herb", "wood")

    def test_admin_literal_matches_orm(self):
        literal_values = set(schemas.GatheringCategory.__args__)
        assert literal_values == set(models.GatheringNode.__table__.c.category.type.enums)

    def test_revision_chain(self, m043):
        assert m043.revision == "043_gathering_ingredient"
        assert len(m043.revision) <= 32  # alembic_version_locations.version_num
        m042 = _load_migration("042_recommended_level_ranges.py")
        assert m043.down_revision == m042.revision

    def test_only_one_head_after_043(self, m043):
        """No other migration may claim 043 as its parent twice / fork the chain."""
        children = []
        for name in os.listdir(_VERSIONS_DIR):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(_VERSIONS_DIR, name), encoding="utf-8") as fh:
                src = fh.read()
            if f"down_revision = '{m043.down_revision}'" in src:
                children.append(name)
        assert children == ["043_gathering_ingredient_category.py"]

    def test_downgrade_refuses_with_ingredient_nodes(self, m043):
        bind = MagicMock()
        bind.execute.return_value.fetchall.return_value = [(7,), (9,)]
        with patch.object(m043.op, "get_bind", return_value=bind, create=True), \
             patch.object(m043.op, "execute", create=True) as mock_exec:
            with pytest.raises(RuntimeError) as exc:
                m043.downgrade()
        assert "7, 9" in str(exc.value)
        mock_exec.assert_not_called()

    def test_downgrade_shrinks_when_empty(self, m043):
        bind = MagicMock()
        bind.execute.return_value.fetchall.return_value = []
        with patch.object(m043.op, "get_bind", return_value=bind, create=True), \
             patch.object(m043.op, "execute", create=True) as mock_exec:
            m043.downgrade()
        sql = mock_exec.call_args[0][0]
        assert "ENUM('ore','herb','wood')" in sql
        assert "ingredient" not in sql

    def test_upgrade_widens(self, m043):
        with patch.object(m043.op, "execute", create=True) as mock_exec:
            m043.upgrade()
        assert "ENUM('ore','herb','wood','ingredient')" in mock_exec.call_args[0][0]


class TestAdminSchema:

    def test_ingredient_node_accepted(self):
        node = schemas.GatheringNodeAdminCreate(
            node_name="Грядка", category="ingredient", result_item_id=4712,
            stamina_per_gather=2, daily_bank_max=50,
        )
        assert node.category == "ingredient"

    @pytest.mark.parametrize("category", ["fish", "Ingredient", "ingredients", "ingredient'--", ""])
    def test_unknown_category_rejected(self, category):
        with pytest.raises(ValueError):
            schemas.GatheringNodeAdminCreate(
                node_name="Грядка", category=category, result_item_id=4712,
                stamina_per_gather=2, daily_bank_max=50,
            )

    def test_admin_create_endpoint_accepts_ingredient(self, client):
        admin = UserRead(id=1, username="admin", role="admin", permissions=["gathering:create"])
        app.dependency_overrides[get_current_user_via_http] = lambda: admin
        try:
            with patch("crud.create_gathering_node_admin", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = {
                    "id": 13, "location_id": 542, "node_name": "Грядка",
                    "category": "ingredient", "result_item_id": 4712,
                    "result_quantity_per_gather": 3, "stamina_per_gather": 2,
                    "daily_bank_max": 50, "current_bank": 50,
                    "allow_concurrent_gather": True, "depleted_at": None,
                    "restore_at": None, "is_enabled": True,
                    "created_at": None, "updated_at": None,
                    "result_item_name": "Пшеница", "result_item_image": None,
                    "result_item_type": "resource",
                }
                resp = client.post(
                    "/locations/admin/locations/542/gathering-nodes",
                    json={"node_name": "Грядка", "category": "ingredient",
                          "result_item_id": 4712, "result_quantity_per_gather": 3,
                          "stamina_per_gather": 2, "daily_bank_max": 50},
                    headers={"Authorization": "Bearer x"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)
        assert resp.status_code == 200, resp.text
        assert mock_create.call_args[0][2].category == "ingredient"

    def test_admin_create_ingredient_requires_permission(self, client):
        user = UserRead(id=2, username="u", role="user", permissions=[])
        app.dependency_overrides[get_current_user_via_http] = lambda: user
        try:
            with patch("crud.create_gathering_node_admin", new_callable=AsyncMock) as mock_create:
                resp = client.post(
                    "/locations/admin/locations/542/gathering-nodes",
                    json={"node_name": "Грядка", "category": "ingredient",
                          "result_item_id": 4712, "stamina_per_gather": 2,
                          "daily_bank_max": 50},
                    headers={"Authorization": "Bearer x"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)
        assert resp.status_code == 403
        mock_create.assert_not_awaited()


# ===========================================================================
# 2. Maps and the toolless set
# ===========================================================================

class TestCategoryMaps:

    def test_finalize_map(self):
        assert crud._CATEGORY_TO_SKILL_SLUG == {
            "ore": "mining", "herb": "herbalism", "wood": "woodcutting", "ingredient": "foraging",
        }

    def test_start_map_matches_finalize_map(self):
        assert crud._GATHER_NODE_CATEGORY_TO_SKILL_SLUG == crud._CATEGORY_TO_SKILL_SLUG

    def test_every_orm_category_has_a_skill(self):
        for category in models.GatheringNode.__table__.c.category.type.enums:
            assert category in crud._CATEGORY_TO_SKILL_SLUG

    def test_tool_map_has_no_ingredient(self):
        assert "ingredient" not in crud._GATHER_NODE_CATEGORY_TO_TOOL_CATEGORY
        for category in ("ore", "herb", "wood"):
            assert category in crud._GATHER_NODE_CATEGORY_TO_TOOL_CATEGORY

    def test_toolless_set(self):
        assert crud.TOOLLESS_GATHER_CATEGORIES == frozenset({"ingredient"})
        assert crud.is_tool_required_for_category("ingredient") is False
        for category in ("ore", "herb", "wood"):
            assert crud.is_tool_required_for_category(category) is True


# ===========================================================================
# 3. Formula
# ===========================================================================

class TestToollessFormula:

    def test_no_penalty_and_rank_double_chance(self):
        eff = crud._compute_effective_gather_params(
            base_stamina=5, has_tool=False, rank_bonuses=RANK3,
            tool_bonuses={}, tool_required=False,
        )
        # 1500 s * 0.92 = 1380, NOT doubled
        assert eff["effective_seconds"] == 1380
        assert eff["effective_double_chance_pct"] == 8.0
        assert eff["effective_speed_bonus_pct"] == 8.0
        assert eff["effective_stamina_bonus_pct"] == 8.0
        assert eff["effective_stamina_paid"] == 5

    def test_rank1_is_base_time(self):
        eff = crud._compute_effective_gather_params(
            base_stamina=2, has_tool=False,
            rank_bonuses={"speed_pct": 0.0, "stamina_pct": 0.0, "double_chance_pct": 0.0},
            tool_bonuses={}, tool_required=False,
        )
        assert eff["effective_seconds"] == 2 * 5 * 60
        assert eff["effective_double_chance_pct"] == 0.0
        assert eff["effective_stamina_paid"] == 2

    def test_same_caps_apply(self):
        eff = crud._compute_effective_gather_params(
            base_stamina=10, has_tool=False,
            rank_bonuses={"speed_pct": 95.0, "stamina_pct": 95.0, "double_chance_pct": 95.0},
            tool_bonuses={}, tool_required=False,
        )
        assert eff["effective_speed_bonus_pct"] == 60.0
        assert eff["effective_stamina_bonus_pct"] == 50.0
        assert eff["effective_double_chance_pct"] == 80.0
        assert eff["effective_seconds"] == 1200  # 3000 * 0.4
        assert eff["effective_stamina_paid"] == 5

    def test_tool_bonuses_ignored_without_tool(self):
        eff = crud._compute_effective_gather_params(
            base_stamina=5, has_tool=False, rank_bonuses=RANK3,
            tool_bonuses={"gather_speed_bonus_pct": 30.0, "gather_stamina_bonus_pct": 30.0,
                          "gather_double_chance_bonus": 30.0},
            tool_required=False,
        )
        assert eff["effective_speed_bonus_pct"] == 8.0
        assert eff["effective_double_chance_pct"] == 8.0

    def test_tool_category_without_tool_keeps_penalty(self):
        for kwargs in ({}, {"tool_required": True}):
            eff = crud._compute_effective_gather_params(
                base_stamina=5, has_tool=False, rank_bonuses=RANK3, tool_bonuses={}, **kwargs,
            )
            assert eff["effective_seconds"] == 2760
            assert eff["effective_double_chance_pct"] == 0.0

    def test_tool_category_with_tool_unchanged(self):
        eff = crud._compute_effective_gather_params(
            base_stamina=5, has_tool=True, rank_bonuses=RANK3,
            tool_bonuses={"gather_speed_bonus_pct": 5.0, "gather_stamina_bonus_pct": 10.0,
                          "gather_double_chance_bonus": 2.0},
            tool_required=True,
        )
        assert eff["effective_seconds"] == 1305
        assert eff["effective_double_chance_pct"] == 10.0


# ===========================================================================
# 4. crud.start_gathering
# ===========================================================================

def _node(category, stamina=5):
    return SimpleNamespace(
        id=31, category=category, is_enabled=True, current_bank=40, restore_at=None,
        allow_concurrent_gather=True, stamina_per_gather=stamina, result_item_id=4712,
    )


def _start_db():
    db = MagicMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()

    async def _flush():
        added = db.add.call_args[0][0]
        added.id = 555

    db.flush = AsyncMock(side_effect=_flush)
    return db


class _StartPatches:
    """All collaborators of crud.start_gathering, patched."""

    def __init__(self, node, rank_bonuses=RANK3, stamina=100):
        self.node = node
        self.rank_bonuses = rank_bonuses
        self.stamina = stamina

    def __enter__(self):
        self.patches = {
            "read_char": patch("crud._read_character_for_start", new_callable=AsyncMock,
                               return_value=(10, 542, "Роланд")),
            "finalize": patch("crud.finalize_due_sessions", new_callable=AsyncMock, return_value=[]),
            "battle": patch("main.check_not_in_battle", new_callable=AsyncMock),
            "gathering": patch("main.check_not_gathering", new_callable=AsyncMock),
            "node": patch("crud._load_gathering_node_for_update", new_callable=AsyncMock,
                          return_value=self.node),
            "tool": patch("crud._load_tool_for_gathering", new_callable=AsyncMock,
                          return_value={"gather_double_chance_bonus": 0.0,
                                        "gather_speed_bonus_pct": 0.0,
                                        "gather_stamina_bonus_pct": 0.0}),
            "rank": patch("crud._fetch_rank_bonuses_for_category", new_callable=AsyncMock,
                          return_value=self.rank_bonuses),
            "stamina": patch("crud._read_current_stamina", new_callable=AsyncMock,
                             return_value=self.stamina),
            "free": patch("crud._check_inventory_has_free_slot", new_callable=AsyncMock,
                          return_value=True),
            "spend": patch("crud._consume_stamina_via_attributes", new_callable=AsyncMock,
                           return_value=True),
            "durability": patch("crud._get_tool_current_durability", new_callable=AsyncMock,
                                return_value=50),
            "brief": patch("crud._fetch_item_brief", new_callable=AsyncMock,
                           return_value={4712: {"name": "Пшеница"}}),
            "post": patch("crud.create_post", new_callable=AsyncMock,
                          return_value=SimpleNamespace(id=900)),
            "count": patch("crud._count_active_sessions_on_node", new_callable=AsyncMock,
                           return_value=1),
        }
        self.mocks = {k: p.start() for k, p in self.patches.items()}
        return self.mocks

    def __exit__(self, *exc):
        for p in self.patches.values():
            p.stop()
        return False


def _start(db, tool_inventory_item_id):
    return asyncio.run(crud.start_gathering(
        db, location_id=542, node_id=31, character_id=421,
        tool_inventory_item_id=tool_inventory_item_id, current_user_id=10,
    ))


class TestStartGatheringToolless:

    def test_tool_for_ingredient_node_422_before_side_effects(self):
        db = _start_db()
        with _StartPatches(_node("ingredient")) as m:
            with pytest.raises(HTTPException) as exc:
                _start(db, tool_inventory_item_id=9023)
        assert exc.value.status_code == 422
        assert exc.value.detail == "Для сбора этого ресурса инструмент не нужен"
        m["tool"].assert_not_awaited()
        m["spend"].assert_not_awaited()
        db.add.assert_not_called()

    def test_ingredient_without_tool_creates_session(self):
        db = _start_db()
        with _StartPatches(_node("ingredient", stamina=5)) as m:
            result = _start(db, tool_inventory_item_id=None)

        assert result["session_id"] == 555
        assert result["effective_seconds"] == 1380  # rank speed, no x2 penalty
        assert result["effective_double_chance_pct"] == 8.0
        assert result["effective_stamina_paid"] == 5
        assert result["tool_inventory_item_id"] is None
        assert result["tool_durability_at_start"] is None
        m["rank"].assert_awaited_once_with(421, "ingredient")
        m["spend"].assert_awaited_once_with(421, 5)
        m["tool"].assert_not_awaited()
        m["durability"].assert_not_awaited()
        session_row = db.add.call_args[0][0]
        assert session_row.tool_inventory_item_id is None
        assert session_row.effective_double_chance_pct == 8.0
        delta = session_row.complete_at - session_row.started_at
        assert delta == timedelta(seconds=1380)

    def test_ore_without_tool_keeps_penalty(self):
        db = _start_db()
        with _StartPatches(_node("ore", stamina=5)) as m:
            result = _start(db, tool_inventory_item_id=None)
        assert result["effective_seconds"] == 2760
        assert result["effective_double_chance_pct"] == 0.0
        m["tool"].assert_not_awaited()

    def test_ore_with_tool_still_validates_tool(self):
        db = _start_db()
        with _StartPatches(_node("ore", stamina=5)) as m:
            result = _start(db, tool_inventory_item_id=9023)
        m["tool"].assert_awaited_once_with(db, 9023, 421, "ore")
        assert result["tool_inventory_item_id"] == 9023
        assert result["effective_seconds"] == 1380

    def test_not_enough_stamina_for_ingredient(self):
        db = _start_db()
        with _StartPatches(_node("ingredient", stamina=5), stamina=1) as m:
            with pytest.raises(HTTPException) as exc:
                _start(db, tool_inventory_item_id=None)
        assert exc.value.status_code == 400
        m["spend"].assert_not_awaited()

    def test_foreign_character_403(self):
        db = _start_db()
        with _StartPatches(_node("ingredient")) as m:
            m["read_char"].return_value = (77, 542, "Чужой")
            with pytest.raises(HTTPException) as exc:
                _start(db, tool_inventory_item_id=None)
        assert exc.value.status_code == 403
        m["spend"].assert_not_awaited()


class TestStartEndpointToolless:

    def test_422_is_surfaced_by_the_route(self, client):
        owner = UserRead(id=10, username="owner", role="user", permissions=[])
        app.dependency_overrides[get_current_user_via_http] = lambda: owner
        try:
            with patch("crud.check_action_gate", new_callable=AsyncMock, return_value=True), \
                 patch("crud.consume_action_gate", new_callable=AsyncMock, return_value=True), \
                 patch("crud.start_gathering", new_callable=AsyncMock,
                       side_effect=HTTPException(422, "Для сбора этого ресурса инструмент не нужен")):
                resp = client.post(
                    "/locations/542/gathering-nodes/31/start",
                    json={"character_id": 421, "tool_inventory_item_id": 9023},
                    headers={"Authorization": "Bearer x"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Для сбора этого ресурса инструмент не нужен"

    def test_unauthenticated_401(self, client):
        resp = client.post("/locations/542/gathering-nodes/31/start",
                           json={"character_id": 421, "tool_inventory_item_id": None})
        assert resp.status_code == 401


# ===========================================================================
# 5. Rank bonuses lookup + finalize (cross-service contract)
# ===========================================================================

class _Resp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.text = ""

    def json(self):
        return self._data


class _Client:
    def __init__(self, get_response=None, captured=None, post_response=None):
        self.get_response = get_response
        self.post_response = post_response
        self.captured = captured if captured is not None else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        self.captured["get_url"] = url
        return self.get_response

    async def post(self, url, json=None, **kwargs):
        self.captured["post_url"] = url
        self.captured["json"] = json
        return self.post_response


class TestRankBonusLookup:

    def test_ingredient_uses_foraging_skill(self):
        data = {"skills": [
            {"slug": "herbalism", "current_rank_bonuses": {
                "speed_bonus_pct": 20.0, "stamina_bonus_pct": 20.0, "double_chance_bonus": 20.0}},
            {"slug": "foraging", "current_rank_bonuses": {
                "speed_bonus_pct": 4.0, "stamina_bonus_pct": 5.0, "double_chance_bonus": 6.0}},
        ]}
        with patch("crud.httpx.AsyncClient", return_value=_Client(get_response=_Resp(200, data))):
            result = asyncio.run(crud._fetch_rank_bonuses_for_category(421, "ingredient"))
        assert result == {"speed_pct": 4.0, "stamina_pct": 5.0, "double_chance_pct": 6.0}

    def test_missing_foraging_skill_degrades_to_zero(self):
        data = {"skills": [{"slug": "herbalism", "current_rank_bonuses": {"speed_bonus_pct": 20.0}}]}
        with patch("crud.httpx.AsyncClient", return_value=_Client(get_response=_Resp(200, data))):
            result = asyncio.run(crud._fetch_rank_bonuses_for_category(421, "ingredient"))
        assert result == {"speed_pct": 0.0, "stamina_pct": 0.0, "double_chance_pct": 0.0}


class _Row(SimpleNamespace):
    pass


def _finalize_db(category, granted_bank=40, quantity=3):
    session_row = _Row(
        id=88, node_id=31, character_id=421, tool_inventory_item_id=None,
        complete_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        effective_double_chance_pct=0.0, stamina_paid=2, status="active",
    )
    node_row = _Row(
        id=31, location_id=542, node_name="Грядка", category=category,
        result_item_id=4712, result_quantity_per_gather=quantity,
        current_bank=granted_bank, daily_bank_max=50,
    )
    executed = []

    async def _execute(query, params=None):
        sql = str(query)
        executed.append((sql, params))
        result = MagicMock()
        if "FROM gathering_sessions" in sql and "FOR UPDATE" in sql:
            result.fetchone.return_value = session_row
        elif "FROM gathering_nodes" in sql and "FOR UPDATE" in sql:
            result.fetchone.return_value = node_row
        else:
            result.fetchone.return_value = None
            result.fetchall.return_value = []
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db, executed


class TestFinalizeForaging:

    def test_finalize_sends_foraging_without_tool(self):
        db, _ = _finalize_db("ingredient")
        award = {
            "actual_quantity_added": 3, "inventory_full": False, "xp_awarded": 3,
            "rank_up": False, "current_rank": 1, "tool_broke": False,
            "tool_durability_remaining": None,
        }
        with patch("crud._award_via_inventory", new_callable=AsyncMock, return_value=award) as mock_award, \
             patch("crud._roll_double_units", return_value=0), \
             patch("crud._get_tool_current_durability", new_callable=AsyncMock) as mock_dur:
            summary = asyncio.run(crud._finalize_one_session(db, 88))

        mock_award.assert_awaited_once()
        kwargs = mock_award.call_args.kwargs
        assert kwargs["skill_slug"] == "foraging"
        assert kwargs["tool_inventory_item_id"] is None
        assert kwargs["granted_quantity"] == 3
        assert kwargs["result_item_id"] == 4712
        mock_dur.assert_not_awaited()
        assert summary["skill_slug"] == "foraging"

    @pytest.mark.parametrize("category,slug", [("ore", "mining"), ("herb", "herbalism"), ("wood", "woodcutting")])
    def test_other_categories_unchanged(self, category, slug):
        db, _ = _finalize_db(category)
        with patch("crud._award_via_inventory", new_callable=AsyncMock, return_value={
                "actual_quantity_added": 3, "xp_awarded": 3, "rank_up": False,
                "current_rank": 1, "tool_broke": False}) as mock_award, \
             patch("crud._roll_double_units", return_value=0):
            asyncio.run(crud._finalize_one_session(db, 88))
        assert mock_award.call_args.kwargs["skill_slug"] == slug

    def test_award_payload_matches_inventory_contract(self):
        captured = {}
        client = _Client(captured=captured, post_response=_Resp(200, {"actual_quantity_added": 3}))
        with patch("crud.httpx.AsyncClient", return_value=client):
            asyncio.run(crud._award_via_inventory(
                character_id=421, skill_slug="foraging", result_item_id=4712,
                granted_quantity=3, tool_inventory_item_id=None,
            ))
        assert captured["json"] == EXPECTED_INVENTORY_PAYLOAD
        assert captured["post_url"].endswith("/inventory/internal/characters/421/gathering/award")

    def test_payload_slug_is_accepted_by_inventory_validator_set(self):
        """The inventory validator set, as documented in its schema (kept in sync
        by the mirrored inventory test); every slug locations can send is in it."""
        inventory_slugs = {"mining", "herbalism", "woodcutting", "foraging"}
        assert set(crud._CATEGORY_TO_SKILL_SLUG.values()) <= inventory_slugs


# ===========================================================================
# 6. `tool_required` in the node payload
# ===========================================================================

class TestToolRequiredPayload:

    def test_fetch_nodes_marks_ingredient_toolless(self):
        now = datetime.now(timezone.utc)
        nodes = [
            SimpleNamespace(id=1, node_name="Жила", category="ore", result_item_id=4711,
                            result_quantity_per_gather=3, stamina_per_gather=5,
                            current_bank=10, daily_bank_max=10, allow_concurrent_gather=True,
                            depleted_at=None, restore_at=None, is_enabled=True),
            SimpleNamespace(id=2, node_name="Грядка", category="ingredient", result_item_id=4712,
                            result_quantity_per_gather=3, stamina_per_gather=2,
                            current_bank=10, daily_bank_max=10, allow_concurrent_gather=True,
                            depleted_at=None, restore_at=now, is_enabled=True),
        ]
        result = MagicMock()
        result.scalars.return_value.all.return_value = nodes
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)

        with patch("crud._fetch_item_brief", new_callable=AsyncMock, return_value={}), \
             patch("crud._fetch_active_sessions_for_nodes", new_callable=AsyncMock, return_value={}), \
             patch("crud._fetch_character_brief_map", new_callable=AsyncMock, return_value={}):
            payload = asyncio.run(crud.fetch_gathering_nodes_with_active_sessions(session, 542))

        by_cat = {n["category"]: n for n in payload}
        assert by_cat["ore"]["tool_required"] is True
        assert by_cat["ingredient"]["tool_required"] is False
        # every entry validates against the client schema
        for entry in payload:
            assert schemas.GatheringNodeClient(**entry).tool_required is entry["tool_required"]

    def test_client_schema_defaults_to_tool_required(self):
        fields = schemas.GatheringNodeClient.__fields__
        assert fields["tool_required"].default is True
