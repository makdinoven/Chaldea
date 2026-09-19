"""
FEAT-171 review #1, issues 1 and 6 — inventory-service.

**Issue 1 — the admin item editor lost its data.** FEAT-171 thinned
`GET /inventory/items/{id}` down to the six-key public card on the belief that
no frontend called it. It does: `api/items.ts::fetchItem` seeds
`ItemsAdminPage/ItemForm`, and the URL was simply hidden behind the axios
`baseURL`. With a thin body the form fell back to its `initialState` defaults
and the subsequent `PUT /inventory/items/{id}` wrote those defaults back — every
modifier, the price, `effects[]` and `damage_entries[]` zeroed on any save.

The fix is a third view of one item: `GET /inventory/admin/items/{id}`, behind
`items:read` (the same permission that already guards the `/admin/items` page
and `GET /admin/items/{id}/conversions`), carrying today's fat `Item` body. The
internal twin cannot serve it — nginx `return 403`s `/inventory/internal/`.

Two properties are locked down here:

1. **The auth matrix.** guest / player / admin / moderator, each with and
   without `items:read`. The permission — not the role — is the gate, exactly
   as on the sibling admin routes.
2. **The body is FAT and complete.** Not "fatter than the public card": the
   admin response must carry *every* field of `schemas.Item`, be byte-identical
   to the internal twin, and specifically hold the keys whose loss was
   destructive (`item_type`, `price`, the `*_modifier` block, `effects`,
   `damage_entries`, `xp_buffs`). The assertions are written against the schema
   itself, so a field added to `Item` later cannot quietly go missing here.

**Issue 6 — `GET /inventory/{id}/equipment-rules`.** Decided to stay public:
its whole body derives from class/subclass, which `GET /characters/{id}/public`
already publishes. Only the error discipline is aligned with the rest of the
feature — a missing character is now 404, not a 200 "no restrictions".
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

import auth_http
import models
import schemas


TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": TOKEN}
AUTH = {"Authorization": "Bearer fake-token"}

ITEM_ID = 10
MISSING_ITEM = 99999

CHARACTER_ID = 1
MISSING_CHARACTER = 99999

PUBLIC_ITEM_CARD_KEYS = {"id", "name", "description", "image_url", "rarity", "type"}

# The keys whose absence silently zeroed real items through the edit form.
DESTRUCTIVE_LOSSES = (
    "item_type", "item_rarity", "item_level", "price", "max_stack_size",
    "is_unique", "socket_count", "max_durability", "weapon_subclass",
    "strength_modifier", "agility_modifier", "damage_modifier",
    "effects", "damage_entries", "xp_buffs",
)


def _user(uid, role, permissions):
    return {"id": uid, "username": f"u{uid}", "role": role, "permissions": list(permissions)}


ITEMS_READ = ["items:read"]

# (name, user payload from /users/me) — everyone who may read the fat card.
ALLOWED = [
    ("admin", _user(1, "admin", ["items:create", "items:read", "items:update"])),
    ("moderator_with_permission", _user(2, "moderator", ITEMS_READ)),
    # Granular by design: the permission is the gate, not the role. Whoever
    # holds `items:read` can already open the admin items page.
    ("player_with_permission", _user(3, "user", ITEMS_READ)),
]

REFUSED = [
    ("player", _user(4, "user", [])),
    ("moderator_without_permission", _user(5, "moderator", ["chat:delete"])),
    ("admin_without_permission", _user(6, "admin", [])),
]


def _mock_users_me(user):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = user
    return resp


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def fat_item(db_session):
    """One item with something in every group the editor writes back."""
    item = models.Items(
        id=ITEM_ID,
        name="Клинок Скитальца",
        description="Старый меч с зазубренным лезвием.",
        image="https://s3/sword.webp",
        full_image="https://s3/sword_full.webp",
        item_type="weapon",
        item_rarity="legendary",
        item_level=7,
        price=2500,
        max_stack_size=1,
        is_unique=True,
        socket_count=2,
        max_durability=100,
        whetstone_level=3,
        weapon_subclass="sword",
        strength_modifier=12,
        agility_modifier=4,
        damage_modifier=18,
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(models.ItemEffect(
        item_id=ITEM_ID, target_side="enemy", effect_name="bleed",
        description="Кровотечение", chance=35, duration=3, magnitude=7.0,
    ))
    db_session.add(models.ItemDamageEntry(
        item_id=ITEM_ID, damage_type="slashing", amount=21.0,
        description="Рубящий удар", weapon_slot="main_weapon",
    ))
    db_session.add(models.ItemXpBuff(
        item_id=ITEM_ID, buff_type="battle", value=0.25, duration_minutes=60,
    ))
    db_session.commit()
    yield db_session
    db_session.query(models.ItemEffect).delete()
    db_session.query(models.ItemDamageEntry).delete()
    db_session.query(models.ItemXpBuff).delete()
    db_session.query(models.Items).delete()
    db_session.commit()


# ===========================================================================
# Auth matrix — GET /inventory/admin/items/{item_id}
# ===========================================================================

class TestAdminItemRouteAuth:

    def test_guest_without_a_token_is_401(self, fat_item, client):
        r = client.get(f"/inventory/admin/items/{ITEM_ID}")
        assert r.status_code == 401, r.text

    @patch("auth_http.requests.get")
    def test_a_forged_token_is_401(self, mock_get, fat_item, client):
        rejected = MagicMock()
        rejected.status_code = 401
        rejected.json.return_value = {}
        mock_get.return_value = rejected
        r = client.get(f"/inventory/admin/items/{ITEM_ID}", headers=AUTH)
        assert r.status_code == 401, r.text

    @pytest.mark.parametrize("name,user", REFUSED)
    @patch("auth_http.requests.get")
    def test_without_items_read_it_is_403(self, mock_get, fat_item, client, name, user):
        mock_get.return_value = _mock_users_me(user)
        r = client.get(f"/inventory/admin/items/{ITEM_ID}", headers=AUTH)
        assert r.status_code == 403, f"{name}: {r.text}"
        assert r.json()["detail"] == "Недостаточно прав"

    @pytest.mark.parametrize("name,user", ALLOWED)
    @patch("auth_http.requests.get")
    def test_with_items_read_it_is_200(self, mock_get, fat_item, client, name, user):
        mock_get.return_value = _mock_users_me(user)
        r = client.get(f"/inventory/admin/items/{ITEM_ID}", headers=AUTH)
        assert r.status_code == 200, f"{name}: {r.text}"

    @patch("auth_http.requests.get")
    def test_a_missing_item_is_404_in_russian(self, mock_get, fat_item, client):
        mock_get.return_value = _mock_users_me(ALLOWED[0][1])
        r = client.get(f"/inventory/admin/items/{MISSING_ITEM}", headers=AUTH)
        assert r.status_code == 404
        assert r.json()["detail"] == "Предмет не найден"


# ===========================================================================
# The body — fat, and provably complete
# ===========================================================================

class TestAdminItemRouteBody:

    @pytest.fixture()
    def body(self, fat_item, client):
        with patch("auth_http.requests.get") as mock_get:
            mock_get.return_value = _mock_users_me(ALLOWED[0][1])
            r = client.get(f"/inventory/admin/items/{ITEM_ID}", headers=AUTH)
        assert r.status_code == 200, r.text
        return r.json()

    def test_it_carries_every_field_of_the_item_schema(self, body):
        """Written against the schema, not a hand-copied list: a field added to
        `Item` tomorrow cannot silently stop reaching the editor."""
        expected = {
            field.alias or name
            for name, field in schemas.Item.__fields__.items()
        }
        assert expected - set(body) == set(), (
            "the admin card is missing fields the editor writes back: "
            f"{sorted(expected - set(body))}"
        )

    @pytest.mark.parametrize("key", DESTRUCTIVE_LOSSES)
    def test_the_keys_whose_loss_zeroed_items_are_present(self, body, key):
        assert key in body, f"{key} missing — PUT would write the form default back"

    def test_the_values_are_the_real_row_not_defaults(self, body):
        assert body["item_type"] == "weapon"
        assert body["price"] == 2500
        assert body["item_level"] == 7
        assert body["socket_count"] == 2
        assert body["whetstone_level"] == 3
        assert body["weapon_subclass"] == "sword"
        assert body["strength_modifier"] == 12
        assert body["damage_modifier"] == 18
        assert body["is_unique"] is True

    def test_the_child_tables_come_along(self, body):
        assert len(body["effects"]) == 1
        assert body["effects"][0]["effect_name"] == "bleed"
        assert body["effects"][0]["chance"] == 35
        assert len(body["damage_entries"]) == 1
        assert body["damage_entries"][0]["damage_type"] == "slashing"
        assert body["damage_entries"][0]["amount"] == 21.0
        assert len(body["xp_buffs"]) == 1
        assert body["xp_buffs"][0]["buff_type"] == "battle"

    def test_it_is_identical_to_the_internal_twin(self, body, fat_item, client):
        """Same document, two doors: services come through
        `/inventory/internal/items/{id}`, the browser through this one. If they
        ever drift, one of the two consumers is reading a different item."""
        twin = client.get(f"/inventory/internal/items/{ITEM_ID}",
                          headers=INTERNAL_HEADERS)
        assert twin.status_code == 200, twin.text
        assert body == twin.json()

    def test_it_is_strictly_fatter_than_the_public_card(self, body, fat_item, client):
        """Guard on the guard: proves the public route really is thin, so the
        completeness assertions above are not passing because nothing was
        thinned in the first place."""
        public = client.get(f"/inventory/items/{ITEM_ID}").json()
        assert set(public) == PUBLIC_ITEM_CARD_KEYS
        assert "price" not in public and "effects" not in public
        assert len(body) > len(public)


# ===========================================================================
# Issue 6 — GET /inventory/{character_id}/equipment-rules
# ===========================================================================

@pytest.fixture()
def characters_table(db_session):
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters ("
        " id INTEGER PRIMARY KEY, user_id INTEGER NULL, id_class INTEGER NULL,"
        " is_npc INTEGER DEFAULT 0)"
    ))
    db_session.execute(text(
        "INSERT INTO characters (id, user_id, id_class, is_npc)"
        f" VALUES ({CHARACTER_ID}, 42, 1, 0)"
    ))
    db_session.commit()
    yield db_session
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


class TestEquipmentRulesStaysPublic:
    """Reference data, not character data — see the module docstring."""

    def test_a_guest_still_gets_200(self, characters_table, client):
        r = client.get(f"/inventory/{CHARACTER_ID}/equipment-rules")
        assert r.status_code == 200, r.text

    @patch("auth_http.requests.get")
    def test_a_stranger_still_gets_200(self, mock_get, characters_table, client):
        mock_get.return_value = _mock_users_me(_user(777, "user", []))
        r = client.get(f"/inventory/{CHARACTER_ID}/equipment-rules", headers=AUTH)
        assert r.status_code == 200, r.text

    def test_the_body_carries_no_character_number(self, characters_table, client):
        body = client.get(f"/inventory/{CHARACTER_ID}/equipment-rules").json()
        # Everything here is derived from the class; nothing about this
        # character's build, money, items or experience may appear.
        assert set(body) <= {
            "restricted", "class_id", "subclass_key", "armor_classes",
            "main_hand_kinds", "off_hand_kinds", "two_handed_kinds",
        }

    def test_a_missing_character_is_now_404(self, characters_table, client):
        """Was a 200 "no restrictions" — the one character-scoped GET without
        the feature's error discipline."""
        r = client.get(f"/inventory/{MISSING_CHARACTER}/equipment-rules")
        assert r.status_code == 404, r.text
        assert r.json()["detail"] == "Персонаж не найден"
