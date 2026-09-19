"""FEAT-171 review fix: locations-service must not proxy private character data
to anonymous callers.

The review found `GET /locations/npcs/{npc_id}/shop?character_id=X` unauthenticated
while it calls the hardened `GET /attributes/internal/{X}` **with the internal
token**: the returned `discounted_buy_price` inverts straight back into that
character's `charisma` (live: 20 → 19 ⇒ charisma 30).

These tests pin the new contract for every locations-service route that takes a
`character_id` and answers with something derived from that character's private
state:

* guest (no token)                → 403, and **no** private number in the body
* stranger (another player)       → 403
* owner                           → 200 + the personal numbers
* admin/moderator + characters:read → 200 (admin sees everything, per §1)
* unknown character               → 404 (never reveal existence)

The public shop window (no `character_id`) stays open for guests and carries
base prices only.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth_http import UserRead

OWNER = UserRead(id=10, username="owner", role="user", permissions=[])
STRANGER = UserRead(id=99, username="stranger", role="user", permissions=[])
ADMIN = UserRead(id=1, username="admin", role="admin", permissions=["characters:read"])
MOD_NO_PERM = UserRead(id=2, username="mod", role="moderator", permissions=[])

CHARACTER_ID = 7
OWNER_USER_ID = OWNER.id


def _character_db(owner_id=OWNER_USER_ID, exists=True):
    """Async-session double: the only statement these routes run before the gate
    is visibility's `SELECT user_id FROM characters WHERE id = :cid`."""
    session = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = (owner_id,) if exists else None
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.fixture()
def gated_client(client):
    """`client`, plus a helper that sets the viewer and the character's owner."""
    from database import get_db
    from main import app, get_optional_user

    def _configure(viewer=None, owner_id=OWNER_USER_ID, exists=True):
        session = _character_db(owner_id=owner_id, exists=exists)

        async def _db():
            yield session

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_optional_user] = lambda: viewer
        return session

    yield client, _configure
    app.dependency_overrides.pop(get_optional_user, None)


def _shop_item(buy_price=20):
    item = MagicMock()
    item.id = 1
    item.npc_id = 5
    item.item_id = 3
    item.buy_price = buy_price
    item.sell_price = buy_price // 2
    item.stock = None
    item.is_active = True
    item.item_name = "Меч"
    item.item_image = None
    item.item_rarity = "common"
    item.item_type = "weapon"
    item.created_at = None
    item.discounted_buy_price = None
    return item


# ===========================================================================
# 1. NPC shop — the reported hole
# ===========================================================================
@patch("main._fetch_charisma", new_callable=AsyncMock, return_value=30)
@patch("crud.get_npc_shop_items_player", new_callable=AsyncMock)
class TestNpcShopGate:
    PATH = f"/locations/npcs/5/shop?character_id={CHARACTER_ID}"

    def test_guest_is_refused(self, mock_items, mock_charisma, gated_client):
        client, configure = gated_client
        configure(viewer=None)
        mock_items.return_value = [_shop_item()]

        resp = client.get(self.PATH)

        assert resp.status_code == 403
        assert "владельцу" in resp.json()["detail"]

    def test_guest_never_sees_the_discounted_price(
        self, mock_items, mock_charisma, gated_client
    ):
        """The actual attack: 20 → 19 inverts to charisma = 30. The number must
        not appear anywhere in the guest's response, and the attributes service
        must not be consulted on an anonymous caller's behalf at all."""
        client, configure = gated_client
        configure(viewer=None)
        mock_items.return_value = [_shop_item(buy_price=20)]

        resp = client.get(self.PATH)

        assert "19" not in resp.text
        assert "discounted_buy_price" not in resp.text
        mock_charisma.assert_not_awaited()

    def test_stranger_is_refused(self, mock_items, mock_charisma, gated_client):
        client, configure = gated_client
        configure(viewer=STRANGER)
        mock_items.return_value = [_shop_item()]

        resp = client.get(self.PATH)

        assert resp.status_code == 403
        mock_charisma.assert_not_awaited()

    def test_moderator_without_permission_is_refused(
        self, mock_items, mock_charisma, gated_client
    ):
        client, configure = gated_client
        configure(viewer=MOD_NO_PERM)
        mock_items.return_value = [_shop_item()]

        assert client.get(self.PATH).status_code == 403

    def test_owner_still_gets_the_discount(self, mock_items, mock_charisma, gated_client):
        client, configure = gated_client
        configure(viewer=OWNER)
        mock_items.return_value = [_shop_item(buy_price=20)]

        resp = client.get(self.PATH)

        assert resp.status_code == 200
        # charisma 30 → 6% → ceil(20 * 0.94) = 19
        assert resp.json()[0]["discounted_buy_price"] == 19

    def test_admin_gets_the_discount(self, mock_items, mock_charisma, gated_client):
        client, configure = gated_client
        configure(viewer=ADMIN)
        mock_items.return_value = [_shop_item(buy_price=20)]

        resp = client.get(self.PATH)

        assert resp.status_code == 200
        assert resp.json()[0]["discounted_buy_price"] == 19

    def test_unknown_character_is_404_not_403(
        self, mock_items, mock_charisma, gated_client
    ):
        client, configure = gated_client
        configure(viewer=OWNER, exists=False)
        mock_items.return_value = [_shop_item()]

        resp = client.get(self.PATH)

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Персонаж не найден"

    def test_npc_character_has_no_private_layer(
        self, mock_items, mock_charisma, gated_client
    ):
        """`user_id IS NULL` (NPC/mob) stays public — FEAT-171 Q6."""
        client, configure = gated_client
        configure(viewer=None, owner_id=None)
        mock_items.return_value = [_shop_item(buy_price=20)]

        resp = client.get(self.PATH)

        assert resp.status_code == 200

    def test_public_shop_window_still_open_for_guests(
        self, mock_items, mock_charisma, gated_client
    ):
        """No `character_id` → base prices for everyone, and the private key is
        ABSENT rather than `null` (review #2, residual 2)."""
        client, configure = gated_client
        configure(viewer=None)
        mock_items.return_value = [_shop_item(buy_price=20)]

        resp = client.get("/locations/npcs/5/shop")

        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["buy_price"] == 20
        assert "discounted_buy_price" not in body[0]
        assert "discounted_buy_price" not in resp.text
        mock_charisma.assert_not_awaited()


# ===========================================================================
# 2. The same shape on the other per-character reads
# ===========================================================================
@pytest.mark.parametrize(
    "path, crud_target, crud_value",
    [
        (
            f"/locations/npcs/5/quests?character_id={CHARACTER_ID}",
            "crud.get_available_quests_for_npc",
            [],
        ),
        (
            f"/locations/quests/active?character_id={CHARACTER_ID}",
            "crud.get_active_quests",
            [],
        ),
        (
            f"/locations/action-gate/status?character_id={CHARACTER_ID}&location_id=3",
            "crud.open_gates_detail",
            {},
        ),
    ],
)
class TestPerCharacterReadsAreGated:
    def test_guest_refused(self, path, crud_target, crud_value, gated_client):
        client, configure = gated_client
        configure(viewer=None)
        with patch(crud_target, new_callable=AsyncMock, return_value=crud_value):
            assert client.get(path).status_code == 403

    def test_stranger_refused(self, path, crud_target, crud_value, gated_client):
        client, configure = gated_client
        configure(viewer=STRANGER)
        with patch(crud_target, new_callable=AsyncMock, return_value=crud_value):
            assert client.get(path).status_code == 403

    def test_owner_allowed(self, path, crud_target, crud_value, gated_client):
        client, configure = gated_client
        configure(viewer=OWNER)
        with patch(crud_target, new_callable=AsyncMock, return_value=crud_value):
            assert client.get(path).status_code == 200

    def test_admin_allowed(self, path, crud_target, crud_value, gated_client):
        client, configure = gated_client
        configure(viewer=ADMIN)
        with patch(crud_target, new_callable=AsyncMock, return_value=crud_value):
            assert client.get(path).status_code == 200

    def test_unknown_character_404(self, path, crud_target, crud_value, gated_client):
        client, configure = gated_client
        configure(viewer=OWNER, exists=False)
        with patch(crud_target, new_callable=AsyncMock, return_value=crud_value):
            assert client.get(path).status_code == 404


# ===========================================================================
# 3. NPC dialogue — the gate check leaks a per-character boolean
# ===========================================================================
@patch("crud.get_active_dialogue_for_npc", new_callable=AsyncMock)
class TestDialogueGate:
    PATH = f"/locations/npcs/5/dialogue?character_id={CHARACTER_ID}"

    def test_guest_with_character_id_refused(self, mock_dialogue, gated_client):
        client, configure = gated_client
        configure(viewer=None)
        mock_dialogue.return_value = {"id": 1, "npc_text": "Привет", "options": [], "is_end": False}

        with patch("crud.check_action_gate", new_callable=AsyncMock) as gate:
            resp = client.get(self.PATH)

        assert resp.status_code == 403
        gate.assert_not_awaited()

    def test_dialogue_without_character_id_stays_public(self, mock_dialogue, gated_client):
        client, configure = gated_client
        configure(viewer=None)
        mock_dialogue.return_value = {"id": 1, "npc_text": "Привет", "options": [], "is_end": False}

        assert client.get("/locations/npcs/5/dialogue").status_code == 200
