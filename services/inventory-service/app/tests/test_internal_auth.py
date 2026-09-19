"""
FEAT-169 §3.1 — inventory-service's `/internal/*` routes are service-only, and
the player belt route is owner-only.

Until this feature five mutating internal routes were reachable through the
gateway with no credential at all (only the nginx `return 403` stood in the
way), and `GET /inventory/characters/{cid}/fast_slots` handed anybody the
contents of anybody's belt — potions, poisons and, since FEAT-168, the item
effects and damage rows too. That is reconnaissance before a fight.

Covered here:

    POST /inventory/internal/characters/{cid}/revalidate-equipment   gate I
    POST /inventory/internal/characters/{cid}/consume_item           gate I
    POST /inventory/internal/characters/{cid}/free_slots_check       gate I
    POST /inventory/internal/characters/{cid}/gathering/award        gate I
    POST /inventory/internal/update-durability                       gate I
    GET  /inventory/internal/characters/{cid}/fast_slots  (new twin) gate I
    GET  /inventory/characters/{cid}/fast_slots                      gate P

Gate I semantics (identical to FEAT-162/167): missing or wrong
`X-Internal-Token` → 401; an **unconfigured** `INTERNAL_SERVICE_TOKEN` → 503,
never "open". Gate P: no JWT → 401, unknown character → 404, someone else's
character → 403.

Every rejected call is also checked against the database: the stored rows must
be untouched, so a guard that returned 401 *after* writing would still fail
here.

Note `verify_internal_token` captures the secret into a **module-level**
constant at import time, so the tests pin `auth_http.INTERNAL_SERVICE_TOKEN`
itself — setting the env var afterwards has no effect at all.
"""

import pytest
from sqlalchemy import text

import auth_http
import models
from auth_http import UserRead, get_current_user_via_http


TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}

CID = 1
OWNER_ID = 1
OTHER_USER_ID = 99
OTHER_CID = 2

POTION_ID = 5100
ORE_ID = 5200
ARMOR_ID = 5300

AWARD_BODY = {
    "skill_slug": "mining",
    "result_item_id": ORE_ID,
    "result_quantity": 4,
    "xp_to_add": 4,
    "tool_inventory_item_id": None,
    "tool_durability_to_consume": 0,
}
DURABILITY_BODY = {
    "character_id": CID,
    "entries": [{"slot_type": "body", "new_durability": 17}],
}


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    """`auth_http` reads the secret into a module-level constant at import
    time, so the constant is what tests must pin."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def _seed_gathering_skills(db):
    """3 skills × 5 ranks — a trimmed copy of the Alembic seed."""
    for sid, slug, name, category in (
        (1, "mining", "Горное дело", "ore"),
        (2, "herbalism", "Травничество", "herb"),
        (3, "woodcutting", "Лесорубство", "wood"),
    ):
        db.add(models.GatheringSkill(
            id=sid, slug=slug, name=name, category=category,
            description=f"Навык {name}", icon=None, max_rank=5,
        ))
    db.flush()
    for sid in (1, 2, 3):
        for rank_number, required_xp in ((1, 0), (2, 10), (3, 25), (4, 50), (5, 100)):
            db.add(models.GatheringSkillRank(
                skill_id=sid, rank_number=rank_number, required_experience=required_xp,
                double_chance_bonus=0.0, speed_bonus_pct=0.0,
                stamina_bonus_pct=0.0,
            ))
    db.commit()


@pytest.fixture()
def world(client, db_session):
    """Everything the six routes need to answer 200 with a good token."""
    from main import app

    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT)"
    ))
    db_session.execute(text(
        "INSERT INTO characters (id, user_id, name) VALUES "
        f"({CID}, {OWNER_ID}, 'Hero'), ({OTHER_CID}, {OTHER_USER_ID}, 'Stranger')"
    ))
    db_session.commit()

    _seed_gathering_skills(db_session)

    potion = models.Items(
        id=POTION_ID, name="Зелье лечения", item_level=1, item_type="consumable",
        item_rarity="common", max_stack_size=20, is_unique=False,
        health_recovery=30,
    )
    ore = models.Items(
        id=ORE_ID, name="Железная руда", item_level=1, item_type="resource",
        item_rarity="common", max_stack_size=99, is_unique=False,
    )
    armor = models.Items(
        id=ARMOR_ID, name="Латный доспех", item_level=1, item_type="armor",
        item_rarity="rare", max_stack_size=1, is_unique=False,
        max_durability=50, health_modifier=10,
    )
    db_session.add_all([potion, ore, armor])
    db_session.flush()

    db_session.add(models.CharacterInventory(
        character_id=CID, item_id=POTION_ID, quantity=5))
    db_session.add(models.EquipmentSlot(
        character_id=CID, slot_type="fast_slot_1", item_id=POTION_ID, is_enabled=True))
    db_session.add(models.EquipmentSlot(
        character_id=CID, slot_type="body", item_id=ARMOR_ID,
        is_enabled=True, current_durability=42))
    db_session.commit()

    yield db_session

    app.dependency_overrides.pop(get_current_user_via_http, None)
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


def _state(db):
    """Everything the five mutating routes could possibly have written."""
    db.expire_all()
    potion = db.query(models.CharacterInventory).filter_by(
        character_id=CID, item_id=POTION_ID).first()
    ore = db.query(models.CharacterInventory).filter_by(
        character_id=CID, item_id=ORE_ID).first()
    body = db.query(models.EquipmentSlot).filter_by(
        character_id=CID, slot_type="body").first()
    belt = db.query(models.EquipmentSlot).filter_by(
        character_id=CID, slot_type="fast_slot_1").first()
    progress = db.query(models.CharacterGatheringSkill).filter_by(
        character_id=CID).all()
    return {
        "potion_qty": potion.quantity if potion else None,
        "ore_qty": ore.quantity if ore else None,
        "body_durability": body.current_durability if body else None,
        "body_item": body.item_id if body else None,
        "belt_item": belt.item_id if belt else None,
        "gathering": sorted((p.skill_id, p.current_rank, p.experience)
                            for p in progress),
    }


# ---------------------------------------------------------------------------
# The gated routes, as (method, path, body)
# ---------------------------------------------------------------------------

GATED_ROUTES = [
    ("post", f"/inventory/internal/characters/{CID}/revalidate-equipment", None),
    ("post", f"/inventory/internal/characters/{CID}/consume_item", {"item_id": POTION_ID}),
    ("post", f"/inventory/internal/characters/{CID}/free_slots_check", None),
    ("post", f"/inventory/internal/characters/{CID}/gathering/award", AWARD_BODY),
    ("post", "/inventory/internal/update-durability", DURABILITY_BODY),
    ("get", f"/inventory/internal/characters/{CID}/fast_slots", None),
]

_ROUTE_IDS = [
    "revalidate-equipment", "consume_item", "free_slots_check",
    "gathering-award", "update-durability", "fast_slots-twin",
]


def _call(client, method, path, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# 1. The good path — a correct token still gets the real answer
# ══════════════════════════════════════════════════════════════════════════════


class TestGatedRoutesStillWorkForServices:

    @pytest.mark.parametrize("method, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_correct_token_returns_200(self, client, world, method, path, body):
        response = _call(client, method, path, body, GOOD_HEADERS)
        assert response.status_code == 200, response.text

    def test_the_belt_twin_answers_with_the_real_payload(self, client, world):
        """NPC/mob belts have no owner, so the twin must never check ownership."""
        response = client.get(
            f"/inventory/internal/characters/{CID}/fast_slots", headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        slots = response.json()
        assert [s["slot_type"] for s in slots] == ["fast_slot_1"]
        assert slots[0]["item_id"] == POTION_ID
        assert slots[0]["quantity"] == 5
        assert slots[0]["health_recovery"] == 30

    def test_the_twin_serves_an_ownerless_character(self, client, world):
        """A mob row has `user_id IS NULL` — gate P would be impossible."""
        world.execute(text(
            "INSERT INTO characters (id, user_id, name) VALUES (777, NULL, 'Гоблин')"))
        world.add(models.CharacterInventory(character_id=777, item_id=POTION_ID, quantity=2))
        world.add(models.EquipmentSlot(
            character_id=777, slot_type="fast_slot_2", item_id=POTION_ID, is_enabled=True))
        world.commit()

        response = client.get(
            "/inventory/internal/characters/777/fast_slots", headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert response.json()[0]["slot_type"] == "fast_slot_2"


# ══════════════════════════════════════════════════════════════════════════════
# 2. No header / wrong header — rejected, and nothing written
# ══════════════════════════════════════════════════════════════════════════════


class TestGatedRoutesRejectOutsiders:

    @pytest.mark.parametrize("method, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_no_header_returns_401_and_writes_nothing(self, client, world,
                                                      method, path, body):
        before = _state(world)

        response = _call(client, method, path, body)

        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"
        assert _state(world) == before, f"{path} изменил БД, хотя отклонил запрос"

    @pytest.mark.parametrize("method, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_wrong_header_returns_401_and_writes_nothing(self, client, world,
                                                         method, path, body):
        before = _state(world)

        response = _call(client, method, path, body, WRONG_HEADERS)

        assert response.status_code == 401
        assert response.json()["detail"] == "Недействительный internal token"
        assert _state(world) == before

    @pytest.mark.parametrize("method, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_header_value_returns_401(self, client, world, method, path, body):
        response = _call(client, method, path, body, {"X-Internal-Token": ""})
        assert response.status_code == 401

    @pytest.mark.parametrize("method, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_a_player_jwt_does_not_open_an_internal_route(self, client, world,
                                                          method, path, body):
        """These routes have no browser caller — a Bearer token is not a key."""
        response = _call(client, method, path, body,
                         {"Authorization": "Bearer player-jwt"})
        assert response.status_code == 401

    @pytest.mark.parametrize("method, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_header_name_is_case_insensitive_but_the_secret_is_not(
        self, client, world, method, path, body
    ):
        assert _call(client, method, path, body,
                     {"x-internal-token": TOKEN}).status_code == 200
        assert _call(client, method, path, body,
                     {"X-Internal-Token": TOKEN.upper()}).status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 3. Fail-closed: an unconfigured service rejects everything with 503
# ══════════════════════════════════════════════════════════════════════════════


class TestFailClosedWithoutToken:

    @pytest.mark.parametrize("method, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_token_env_returns_503(self, client, world, monkeypatch,
                                         method, path, body):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        response = _call(client, method, path, body, GOOD_HEADERS)
        assert response.status_code == 503, response.text
        assert response.json()["detail"] == "Internal service token не настроен"

    @pytest.mark.parametrize("method, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_token_env_never_allows_the_call(self, client, world, monkeypatch,
                                                   method, path, body):
        """No configuration must never mean "no authentication"."""
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        before = _state(world)

        for headers in ({}, GOOD_HEADERS, WRONG_HEADERS, {"X-Internal-Token": ""}):
            response = _call(client, method, path, body, headers)
            assert response.status_code == 503, (headers, response.text)

        assert _state(world) == before


# ══════════════════════════════════════════════════════════════════════════════
# 4. The player belt route — gate P
# ══════════════════════════════════════════════════════════════════════════════


class TestPlayerFastSlotsRoute:
    """`GET /inventory/characters/{cid}/fast_slots` — JWT + ownership."""

    def _as(self, user_id):
        from main import app
        user = UserRead(id=user_id, username=f"u{user_id}", role="user", permissions=[])
        app.dependency_overrides[get_current_user_via_http] = lambda: user

    def test_anonymous_is_401(self, client, world):
        response = client.get(f"/inventory/characters/{CID}/fast_slots")
        assert response.status_code == 401, response.text

    def test_another_players_character_is_403(self, client, world):
        self._as(OTHER_USER_ID)
        response = client.get(f"/inventory/characters/{CID}/fast_slots")
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "Вы можете управлять только своими персонажами"

    def test_unknown_character_is_404(self, client, world):
        self._as(OWNER_ID)
        response = client.get("/inventory/characters/31337/fast_slots")
        assert response.status_code == 404
        assert response.json()["detail"] == "Персонаж не найден"

    def test_owner_gets_the_full_payload(self, client, world):
        self._as(OWNER_ID)
        response = client.get(f"/inventory/characters/{CID}/fast_slots")
        assert response.status_code == 200, response.text
        slots = response.json()
        assert len(slots) == 1
        assert slots[0]["slot_type"] == "fast_slot_1"
        assert slots[0]["item_id"] == POTION_ID
        assert slots[0]["quantity"] == 5
        assert slots[0]["name"] == "Зелье лечения"
        assert slots[0]["health_recovery"] == 30
        assert slots[0]["effects"] == []
        assert slots[0]["damage_entries"] == []

    def test_the_player_and_the_internal_route_agree(self, client, world):
        """The split must not fork the payload — one `_core`, one answer."""
        self._as(OWNER_ID)
        player = client.get(f"/inventory/characters/{CID}/fast_slots")
        internal = client.get(
            f"/inventory/internal/characters/{CID}/fast_slots", headers=GOOD_HEADERS)
        assert player.status_code == internal.status_code == 200
        assert player.json() == internal.json()

    def test_an_internal_token_is_not_a_substitute_for_the_jwt(self, client, world):
        """The player route must not accept the service secret instead."""
        response = client.get(
            f"/inventory/characters/{CID}/fast_slots", headers=GOOD_HEADERS)
        assert response.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 5. Structural guard — the dependency must stay on every route
# ══════════════════════════════════════════════════════════════════════════════


_INTERNAL_PATHS_REQUIRING_THE_TOKEN = {
    ("POST", "/inventory/internal/characters/{character_id}/revalidate-equipment"),
    ("POST", "/inventory/internal/characters/{character_id}/consume_item"),
    ("POST", "/inventory/internal/characters/{character_id}/free_slots_check"),
    ("POST", "/inventory/internal/characters/{character_id}/gathering/award"),
    ("POST", "/inventory/internal/update-durability"),
    ("GET", "/inventory/internal/characters/{character_id}/fast_slots"),
}


class TestRouteTableKeepsTheGates:

    def _deps(self, route):
        return {
            getattr(dep.call, "__name__", type(dep.call).__name__)
            for dep in route.dependant.dependencies
        }

    def test_every_gated_route_still_carries_verify_internal_token(self):
        import main
        from fastapi.routing import APIRoute

        seen = set()
        for route in main.app.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                key = (method, route.path)
                if key not in _INTERNAL_PATHS_REQUIRING_THE_TOKEN:
                    continue
                seen.add(key)
                assert "verify_internal_token" in self._deps(route), (
                    f"{method} {route.path} снова открыт: deps={sorted(self._deps(route))}"
                )

        missing = _INTERNAL_PATHS_REQUIRING_THE_TOKEN - seen
        assert not missing, f"эти маршруты пропали из таблицы роутов: {sorted(missing)}"

    def test_no_internal_inventory_route_is_left_ungated(self):
        """A future `/inventory/internal/...` route inherits the rule."""
        import main
        from fastapi.routing import APIRoute

        offenders = []
        for route in main.app.routes:
            if not isinstance(route, APIRoute):
                continue
            if "/inventory/internal/" not in route.path:
                continue
            if "verify_internal_token" not in self._deps(route):
                offenders.append(f"{sorted(route.methods)} {route.path}")
        assert not offenders, (
            "внутренний маршрут без verify_internal_token: " + "; ".join(offenders)
        )

    def test_the_player_belt_route_keeps_the_jwt_dependency(self):
        import main
        from fastapi.routing import APIRoute

        for route in main.app.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path != "/inventory/characters/{character_id}/fast_slots":
                continue
            assert "get_current_user_via_http" in self._deps(route), (
                f"пояс снова читается без JWT: deps={sorted(self._deps(route))}"
            )
            return
        raise AssertionError("маршрут пояса игрока пропал из таблицы роутов")
