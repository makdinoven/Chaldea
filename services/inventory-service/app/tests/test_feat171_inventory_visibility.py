"""
FEAT-171 task 17 — inventory-service: the five-viewer matrix, the thin public
shapes, and the belt hole.

Three things are locked down here.

**1. The matrix.** `GET /inventory/{cid}/items` (I1) and
`GET /inventory/{cid}/equipment` (I2) used to answer *anyone* with the full
private payload. They are now style-B gates, so every one of
guest / another player / owner / admin / moderator-with-`characters:read` /
moderator-**without** it / NPC is asserted, plus a missing character id, which
must answer **404 before** the ownership branch runs — a 403 there would turn
the gate into an existence oracle (§3.8).

**2. Absence, not falsiness.** §1 is explicit that hiding a field in the UI is
not the mechanism. So every private-field assertion below is
`assert "<key>" not in body`, never `assert not body["<key>"]`: a `null` in the
JSON would mean the value still travelled through the response model and one
`response_model_exclude_none` away from coming back.

**3. The belt.** `fast_slot_1..10` are rows in the *same* `equipment_slots`
table, so FEAT-169's gate on `GET /inventory/characters/{id}/fast_slots` was
bypassable with one anonymous `GET /inventory/{id}/equipment` (§2.4.1). The
public view must therefore drop them **in the query**
(`crud.FAST_SLOT_LIKE_PATTERN`), not afterwards — a post-filter is one refactor
away from reopening the hole. `TestBeltIsNotInThePublicView` fills all four
fast slots and proves (a) they are absent, (b) the emitted SQL really carries
the `NOT LIKE`, and (c) the assertion *bites*: with the filter neutralised the
same test data leaks the belt again.
"""

import json
import os

import pytest
from sqlalchemy import event, text

import auth_http
import crud
import models
import schemas
from auth_http import UserRead, get_optional_user
from main import app


TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": TOKEN}

OWNER_ID = 42
STRANGER_ID = 43

PLAYER_CHARACTER = 1
NPC_CHARACTER = 2
MISSING_CHARACTER = 99999


def _user(uid, role, permissions=()):
    return UserRead(id=uid, username=f"u{uid}", role=role, permissions=list(permissions))


GUEST = None
OWNER = _user(OWNER_ID, "user")
STRANGER = _user(STRANGER_ID, "user")
ADMIN = _user(7, "admin", ["characters:read"])
MODERATOR = _user(8, "moderator", ["characters:read"])
MODERATOR_NO_PERM = _user(9, "moderator", [])

# Who may read the private layer of PLAYER_CHARACTER, and who may not.
ALLOWED = [("owner", OWNER), ("admin", ADMIN), ("moderator", MODERATOR)]
REFUSED = [
    ("guest", GUEST),
    ("stranger", STRANGER),
    ("moderator_without_permission", MODERATOR_NO_PERM),
]

# Every key the private inventory row / equipment slot carries that a stranger
# must never see. Checked as *absence*, per §3.8.
PRIVATE_ITEM_NUMBER_KEYS = (
    "price", "item_level", "max_durability", "socket_count", "whetstone_level",
    "strength_modifier", "agility_modifier", "damage_modifier",
    "effects", "damage_entries", "xp_buffs",
)
PRIVATE_SLOT_KEYS = (
    "effective_damage", "enhancement_points_spent", "enhancement_bonuses",
    "socketed_gems", "current_durability", "is_enabled", "item_id", "character_id",
    "id",
)

PUBLIC_ITEM_CARD_KEYS = {"id", "name", "description", "image_url", "rarity", "type"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    """`verify_internal_token` freezes the secret at import time — pin it."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def world(db_session):
    """Seed `characters` (shared table), items, an inventory and equipment.

    The equipment covers a worn weapon, an empty slot and **all four fast
    slots** — the belt regression needs them filled, not merely present.
    """
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters ("
        " id INTEGER PRIMARY KEY, name TEXT, user_id INTEGER NULL,"
        " currency_balance INTEGER DEFAULT 0)"
    ))
    db_session.execute(
        text("INSERT INTO characters (id, name, user_id) VALUES (:i, 'Игрок', :u)"),
        {"i": PLAYER_CHARACTER, "u": OWNER_ID},
    )
    db_session.execute(
        text("INSERT INTO characters (id, name, user_id) VALUES (:i, 'Моб', NULL)"),
        {"i": NPC_CHARACTER},
    )

    sword = models.Items(
        id=10, name="Клинок Скитальца", image="https://s3/sword.webp",
        full_image="https://s3/sword_full.webp", item_type="weapon",
        item_rarity="legendary", description="Старый меч с зазубренным лезвием.",
        price=2500, item_level=7, max_durability=100, socket_count=2,
    )
    potion = models.Items(
        id=11, name="Зелье лечения", image="https://s3/potion.webp",
        item_type="consumable", item_rarity="common",
        description="Восстанавливает здоровье.", price=50, item_level=1,
    )
    db_session.add_all([sword, potion])
    db_session.flush()

    db_session.add(models.CharacterInventory(
        id=1, character_id=PLAYER_CHARACTER, item_id=potion.id, quantity=5,
        enhancement_points_spent=3, socketed_gems=json.dumps([11, None]),
        current_durability=77,
    ))
    db_session.add(models.EquipmentSlot(
        id=1, character_id=PLAYER_CHARACTER, slot_type="main_weapon",
        item_id=sword.id, enhancement_points_spent=4,
        enhancement_bonuses=json.dumps({"damage_modifier": 5}),
        socketed_gems=json.dumps([11]), current_durability=90,
    ))
    db_session.add(models.EquipmentSlot(
        id=2, character_id=PLAYER_CHARACTER, slot_type="head", item_id=None,
    ))
    for n in (1, 2, 3, 4):
        db_session.add(models.EquipmentSlot(
            id=10 + n, character_id=PLAYER_CHARACTER, slot_type=f"fast_slot_{n}",
            item_id=potion.id,
        ))

    # The NPC gets one worn item so its (public) private layer is non-empty.
    db_session.add(models.EquipmentSlot(
        id=30, character_id=NPC_CHARACTER, slot_type="main_weapon", item_id=sword.id,
    ))
    db_session.add(models.CharacterInventory(
        id=30, character_id=NPC_CHARACTER, item_id=potion.id, quantity=1,
    ))
    db_session.commit()
    yield db_session
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


@pytest.fixture()
def as_viewer(client):
    """Factory: run `client` as a given viewer (`None` = guest, no token)."""
    def _set(viewer):
        if viewer is None:
            app.dependency_overrides.pop(get_optional_user, None)
        else:
            app.dependency_overrides[get_optional_user] = lambda: viewer
        return client
    yield _set
    app.dependency_overrides.pop(get_optional_user, None)


# ===========================================================================
# I1 — GET /inventory/{cid}/items
# ===========================================================================

class TestInventoryItemsGate:

    @pytest.mark.parametrize("name,viewer", REFUSED)
    def test_refused_viewers_get_403(self, world, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/inventory/{PLAYER_CHARACTER}/items")
        assert r.status_code == 403, f"{name}: {r.text}"
        assert r.json()["detail"] == "Эти данные доступны только владельцу персонажа"

    @pytest.mark.parametrize("name,viewer", ALLOWED)
    def test_privileged_viewers_get_the_full_rows(self, world, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/inventory/{PLAYER_CHARACTER}/items")
        assert r.status_code == 200, f"{name}: {r.text}"
        rows = r.json()
        assert len(rows) == 1
        row = rows[0]
        # The owner's payload must not have been thinned along the way.
        assert row["quantity"] == 5
        assert row["enhancement_points_spent"] == 3
        assert row["current_durability"] == 77
        assert row["item"]["price"] == 50

    @pytest.mark.parametrize("name,viewer", REFUSED + ALLOWED)
    def test_npc_inventory_is_public(self, world, as_viewer, name, viewer):
        """Q6: `user_id IS NULL` means 'no private layer', not 'nobody'."""
        r = as_viewer(viewer).get(f"/inventory/{NPC_CHARACTER}/items")
        assert r.status_code == 200, f"{name}: {r.text}"
        assert len(r.json()) == 1

    @pytest.mark.parametrize("name,viewer", REFUSED + ALLOWED)
    def test_missing_character_is_404_not_403(self, world, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/inventory/{MISSING_CHARACTER}/items")
        assert r.status_code == 404, f"{name}: {r.text}"
        assert r.json()["detail"] == "Персонаж не найден"


# ===========================================================================
# I2 — GET /inventory/{cid}/equipment
# ===========================================================================

class TestEquipmentGate:

    @pytest.mark.parametrize("name,viewer", REFUSED)
    def test_refused_viewers_get_403(self, world, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/inventory/{PLAYER_CHARACTER}/equipment")
        assert r.status_code == 403, f"{name}: {r.text}"

    @pytest.mark.parametrize("name,viewer", ALLOWED)
    def test_privileged_viewers_keep_todays_body(self, world, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/inventory/{PLAYER_CHARACTER}/equipment")
        assert r.status_code == 200, f"{name}: {r.text}"
        slots = r.json()
        by_type = {s["slot_type"]: s for s in slots}
        # The owner still sees the belt here — §3.4 I2 keeps the body identical.
        assert {f"fast_slot_{n}" for n in (1, 2, 3, 4)} <= set(by_type)
        weapon = by_type["main_weapon"]
        assert "effective_damage" in weapon
        assert weapon["enhancement_points_spent"] == 4
        assert weapon["current_durability"] == 90

    @pytest.mark.parametrize("name,viewer", REFUSED + ALLOWED)
    def test_npc_equipment_is_public(self, world, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/inventory/{NPC_CHARACTER}/equipment")
        assert r.status_code == 200, f"{name}: {r.text}"

    @pytest.mark.parametrize("name,viewer", REFUSED + ALLOWED)
    def test_missing_character_is_404_not_403(self, world, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/inventory/{MISSING_CHARACTER}/equipment")
        assert r.status_code == 404, f"{name}: {r.text}"


# ===========================================================================
# I2p — GET /inventory/{cid}/equipment/public
# ===========================================================================

class TestPublicEquipmentShape:
    """The one route that stays open: what is worn, and nothing measurable."""

    @pytest.mark.parametrize("name,viewer", REFUSED + ALLOWED)
    def test_every_viewer_including_a_guest_gets_200(
        self, world, as_viewer, name, viewer
    ):
        r = as_viewer(viewer).get(f"/inventory/{PLAYER_CHARACTER}/equipment/public")
        assert r.status_code == 200, f"{name}: {r.text}"

    def test_a_slot_has_exactly_slot_type_and_item(self, world, as_viewer):
        slots = as_viewer(GUEST).get(
            f"/inventory/{PLAYER_CHARACTER}/equipment/public"
        ).json()
        assert slots, "public equipment came back empty — the fixture worn nothing?"
        for slot in slots:
            assert set(slot) == {"slot_type", "item"}, slot

    def test_the_item_card_has_exactly_the_six_public_keys(self, world, as_viewer):
        slots = as_viewer(GUEST).get(
            f"/inventory/{PLAYER_CHARACTER}/equipment/public"
        ).json()
        card = next(s["item"] for s in slots if s["item"] is not None)
        assert set(card) == PUBLIC_ITEM_CARD_KEYS
        # The flavour the user asked for really is there…
        assert card["name"] == "Клинок Скитальца"
        assert card["description"] == "Старый меч с зазубренным лезвием."
        assert card["rarity"] == "legendary"

    @pytest.mark.parametrize("key", PRIVATE_ITEM_NUMBER_KEYS)
    def test_no_item_number_reaches_the_public_card(self, world, as_viewer, key):
        slots = as_viewer(GUEST).get(
            f"/inventory/{PLAYER_CHARACTER}/equipment/public"
        ).json()
        card = next(s["item"] for s in slots if s["item"] is not None)
        assert key not in card, f"{key} must be ABSENT, not null"

    @pytest.mark.parametrize("key", PRIVATE_SLOT_KEYS)
    def test_no_slot_instance_data_reaches_the_public_view(
        self, world, as_viewer, key
    ):
        slots = as_viewer(GUEST).get(
            f"/inventory/{PLAYER_CHARACTER}/equipment/public"
        ).json()
        for slot in slots:
            assert key not in slot, f"{key} must be ABSENT from a public slot"

    def test_an_empty_slot_renders_as_a_null_item_not_a_crash(self, world, as_viewer):
        slots = as_viewer(GUEST).get(
            f"/inventory/{PLAYER_CHARACTER}/equipment/public"
        ).json()
        head = next(s for s in slots if s["slot_type"] == "head")
        assert head["item"] is None

    def test_missing_character_is_404(self, world, as_viewer):
        r = as_viewer(GUEST).get(
            f"/inventory/{MISSING_CHARACTER}/equipment/public"
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Персонаж не найден"

    def test_an_npc_showcase_works_too(self, world, as_viewer):
        r = as_viewer(GUEST).get(f"/inventory/{NPC_CHARACTER}/equipment/public")
        assert r.status_code == 200
        assert [s["slot_type"] for s in r.json()] == ["main_weapon"]


# ===========================================================================
# The belt — FEAT-169 must not regress through this route (§2.4.1)
# ===========================================================================

class TestBeltIsNotInThePublicView:

    def test_all_four_fast_slots_are_filled_in_the_fixture(self, world):
        """Guard on the guard: if the fixture stopped filling the belt, the
        regression test below would pass vacuously forever."""
        filled = world.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == PLAYER_CHARACTER,
            models.EquipmentSlot.slot_type.like("fast_slot_%"),
            models.EquipmentSlot.item_id.isnot(None),
        ).count()
        assert filled == 4

    def test_the_public_view_carries_no_fast_slot_row(self, world, as_viewer):
        slots = as_viewer(GUEST).get(
            f"/inventory/{PLAYER_CHARACTER}/equipment/public"
        ).json()
        leaked = [s["slot_type"] for s in slots
                  if str(s["slot_type"]).startswith("fast_slot_")]
        assert leaked == [], (
            "FEAT-169 regressed: the belt is readable through the public "
            f"equipment route again ({leaked})"
        )
        # …and the route did return the *rest* of the equipment, so the empty
        # belt is a filter, not an empty response.
        assert {"main_weapon", "head"} <= {s["slot_type"] for s in slots}

    def test_the_exclusion_happens_in_the_sql_not_afterwards(self, world):
        """A post-filter would be one refactor away from reopening the hole, so
        the emitted SELECT itself must carry the NOT LIKE."""
        statements = []
        bind = world.get_bind()

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(bind, "before_cursor_execute", _record)
        try:
            crud.get_public_equipment_slots(world, PLAYER_CHARACTER)
        finally:
            event.remove(bind, "before_cursor_execute", _record)

        selects = [s for s in statements if "equipment_slots" in s]
        assert selects, "no query against equipment_slots was emitted"
        assert any("NOT LIKE" in s.upper() for s in selects), (
            "the belt is being filtered in Python, not in the query:\n"
            + "\n".join(selects)
        )

    def test_the_regression_assertion_really_bites(self, world, monkeypatch):
        """Red-proof, permanent: neutralise the query filter and the very same
        fixture leaks all four belt rows again. If this test ever fails, the
        test above has stopped proving anything."""
        monkeypatch.setattr(crud, "FAST_SLOT_LIKE_PATTERN", "__no_such_slot__%")
        slots = crud.get_public_equipment_slots(world, PLAYER_CHARACTER)
        leaked = [s.slot_type for s in slots if s.slot_type.startswith("fast_slot_")]
        assert sorted(leaked) == [f"fast_slot_{n}" for n in (1, 2, 3, 4)], (
            "with the filter disabled the belt should be visible — the "
            "regression test is no longer exercising the filter"
        )

    def test_the_owners_private_route_still_shows_the_belt(self, world, as_viewer):
        """The belt is hidden from the showcase, not deleted: the owner's own
        equipment call is unchanged (§3.4 I2)."""
        slots = as_viewer(OWNER).get(
            f"/inventory/{PLAYER_CHARACTER}/equipment"
        ).json()
        assert len([s for s in slots
                    if str(s["slot_type"]).startswith("fast_slot_")]) == 4


# ===========================================================================
# I3 / I4 — the item card
# ===========================================================================

class TestPublicItemCard:

    def test_single_item_route_is_thin(self, world, client):
        r = client.get("/inventory/items/10")
        assert r.status_code == 200, r.text
        assert set(r.json()) == PUBLIC_ITEM_CARD_KEYS

    @pytest.mark.parametrize("key", PRIVATE_ITEM_NUMBER_KEYS)
    def test_single_item_route_leaks_no_number(self, world, client, key):
        assert key not in client.get("/inventory/items/10").json()

    def test_bulk_route_keeps_the_same_card(self, world, client):
        r = client.get("/inventory/items/bulk", params={"ids": "10,11"})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 2
        for row in rows:
            assert set(row) == PUBLIC_ITEM_CARD_KEYS

    def test_exactly_one_projection_builds_the_card(self, world):
        """§3.2 D5: a second hand-written field list is a review FAIL. The two
        public paths must produce byte-identical cards for the same row."""
        row = world.query(models.Items).filter_by(id=10).one()
        assert schemas.public_item_card(row).dict() == {
            "id": 10,
            "name": "Клинок Скитальца",
            "description": "Старый меч с зазубренным лезвием.",
            "image_url": "https://s3/sword.webp",
            "rarity": "legendary",
            "type": "weapon",
        }

    def test_the_fat_template_still_lives_on_the_internal_twin(self, world, client):
        r = client.get("/inventory/internal/items/10", headers=INTERNAL_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["price"] == 2500
        assert body["item_level"] == 7
        assert body["socket_count"] == 2


# ===========================================================================
# The three internal twins
# ===========================================================================

INTERNAL_PATHS = [
    f"/inventory/internal/characters/{PLAYER_CHARACTER}/items",
    f"/inventory/internal/characters/{PLAYER_CHARACTER}/equipment",
    "/inventory/internal/items/10",
]


class TestInternalTwins:

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_no_header_is_401(self, world, client, path):
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_wrong_header_is_401(self, world, client, path):
        r = client.get(path, headers={"X-Internal-Token": "nope"})
        assert r.status_code == 401

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_unconfigured_secret_fails_closed_with_503(
        self, world, client, path, monkeypatch
    ):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        assert client.get(path, headers=INTERNAL_HEADERS).status_code == 503

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_good_header_is_200(self, world, client, path):
        assert client.get(path, headers=INTERNAL_HEADERS).status_code == 200

    def test_the_equipment_twin_keeps_the_belt_and_the_damage(self, world, client):
        """battle-service reads this one: it must stay the FAT body."""
        slots = client.get(
            f"/inventory/internal/characters/{PLAYER_CHARACTER}/equipment",
            headers=INTERNAL_HEADERS,
        ).json()
        types = {s["slot_type"] for s in slots}
        assert {f"fast_slot_{n}" for n in (1, 2, 3, 4)} <= types
        weapon = next(s for s in slots if s["slot_type"] == "main_weapon")
        assert "effective_damage" in weapon

    def test_the_twins_do_not_check_ownership(self, world, client):
        """Deliberate: the engine reads mobs and NPCs that have no owner, and
        dungeon-service reads any session member."""
        for cid in (PLAYER_CHARACTER, NPC_CHARACTER):
            r = client.get(
                f"/inventory/internal/characters/{cid}/items",
                headers=INTERNAL_HEADERS,
            )
            assert r.status_code == 200, (cid, r.text)


# ===========================================================================
# Security: the gate must not be steerable from the outside
# ===========================================================================

class TestGateSecurity:

    def test_a_path_injection_does_not_reach_the_query(self, world, as_viewer):
        r = as_viewer(GUEST).get("/inventory/1%20OR%201=1/items")
        assert r.status_code in (404, 422), r.text

    def test_a_garbage_bearer_token_is_treated_as_a_guest_not_as_the_owner(
        self, world, client
    ):
        """`get_optional_user` swallows the 401 and returns None, so a forged
        token must land on the refused branch — never on the owner branch."""
        r = client.get(
            f"/inventory/{PLAYER_CHARACTER}/items",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 403, r.text
