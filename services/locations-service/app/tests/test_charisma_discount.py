"""
Tests for charisma-based shop discounts in locations-service (FEAT-075, Task 4.9).

Covers:
1. _compute_charisma_discount() — unit tests for discount formula
2. buy_from_npc — integration tests with charisma discount
3. get_npc_shop — shop listing with character_id / without
4. Graceful degradation — attributes-service errors → full price
"""

from unittest.mock import patch, MagicMock, AsyncMock
import math

import pytest

from auth_http import get_current_user_via_http, UserRead


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row(*values):
    """Create a mock row that supports index access."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _result_with_row(row_data):
    result = MagicMock()
    result.fetchone.return_value = row_data
    return result


def _result_with_scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    result.fetchone.return_value = _row(value) if value is not None else None
    return result


def _result_empty():
    result = MagicMock()
    result.fetchone.return_value = None
    result.scalar.return_value = None
    return result


MOCK_USER = UserRead(id=10, username="testuser", role="user", permissions=[])


def _make_shop_item(
    item_id=1, npc_id=5, buy_price=1000, sell_price=500,
    stock=None, is_active=True, shop_item_id=10,
):
    """Create a mock NpcShopItem ORM object."""
    item = MagicMock()
    item.id = shop_item_id
    item.npc_id = npc_id
    item.item_id = item_id
    item.buy_price = buy_price
    item.sell_price = sell_price
    item.stock = stock
    item.is_active = is_active
    item.item_name = "Test Sword"
    item.item_image = None
    item.item_rarity = "common"
    item.item_type = "weapon"
    item.created_at = None
    item.discounted_buy_price = None
    return item


# ===========================================================================
# 1. Unit tests for _compute_charisma_discount()
# ===========================================================================
class TestComputeCharismaDiscount:
    """Unit tests for the _compute_charisma_discount() helper."""

    def test_charisma_zero(self):
        from main import _compute_charisma_discount
        assert _compute_charisma_discount(0) == 0.0

    def test_charisma_50(self):
        from main import _compute_charisma_discount
        assert _compute_charisma_discount(50) == 10.0

    def test_charisma_100(self):
        from main import _compute_charisma_discount
        assert _compute_charisma_discount(100) == 20.0

    def test_charisma_250_cap(self):
        from main import _compute_charisma_discount
        assert _compute_charisma_discount(250) == 50.0

    def test_charisma_300_cap_enforced(self):
        from main import _compute_charisma_discount
        assert _compute_charisma_discount(300) == 50.0

    def test_charisma_none(self):
        from main import _compute_charisma_discount
        assert _compute_charisma_discount(None) == 0.0

    def test_charisma_negative(self):
        from main import _compute_charisma_discount
        assert _compute_charisma_discount(-10) == 0.0

    def test_charisma_1(self):
        from main import _compute_charisma_discount
        assert _compute_charisma_discount(1) == pytest.approx(0.2)


# ===========================================================================
# 2. Integration tests for buy_from_npc with discount
# ===========================================================================
class TestBuyFromNpcWithDiscount:
    """Tests for POST /npcs/{npc_id}/shop/buy with charisma discount."""

    def _setup_buy(self, client, charisma_value, buy_price=1000):
        """Helper: override deps, mock crud and httpx for a buy request."""
        from database import get_db
        from main import app

        shop_item = _make_shop_item(buy_price=buy_price, npc_id=5)

        async def mock_get_db():
            yield MagicMock()

        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        app.dependency_overrides[get_db] = mock_get_db
        return shop_item

    def _make_httpx_mock(self, attrs_resp, inv_resp):
        """Create a mock httpx.AsyncClient that handles both attrs and inventory calls."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=attrs_resp)
        mock_client_instance.post = AsyncMock(return_value=inv_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        return mock_client_instance

    def _buy_request(self, client, app):
        """Execute a standard buy request and clean up overrides."""
        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        try:
            response = client.post(
                "/locations/npcs/5/shop/buy",
                json={"character_id": 1, "shop_item_id": 10, "quantity": 1},
                headers={"Authorization": "Bearer test-token"},
            )
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)
        return response

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_item_name", new_callable=AsyncMock, return_value="Test Sword")
    @patch("crud.decrement_stock", new_callable=AsyncMock)
    @patch("crud.deduct_currency", new_callable=AsyncMock, return_value=9000)
    @patch("crud.get_shop_item_by_id", new_callable=AsyncMock)
    @patch("crud.get_npc_location", new_callable=AsyncMock, return_value=100)
    @patch("crud.get_character_location", new_callable=AsyncMock, return_value=100)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_buy_with_charisma_50_discount(
        self, mock_ownership, mock_char_loc, mock_npc_loc,
        mock_shop_item, mock_deduct, mock_dec_stock,
        mock_item_name, mock_httpx_cls, client,
    ):
        """Purchase with charisma=50 -> price reduced by 10%."""
        from main import app

        mock_shop_item.return_value = _make_shop_item(buy_price=1000, npc_id=5)

        mock_attrs_resp = MagicMock(status_code=200)
        mock_attrs_resp.json.return_value = {"charisma": 50}
        mock_inv_resp = MagicMock(status_code=200)
        mock_httpx_cls.return_value = self._make_httpx_mock(mock_attrs_resp, mock_inv_resp)

        response = self._buy_request(client, app)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["discount_percent"] == 10.0
        assert data["total_price"] == 900

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_item_name", new_callable=AsyncMock, return_value="Test Sword")
    @patch("crud.decrement_stock", new_callable=AsyncMock)
    @patch("crud.deduct_currency", new_callable=AsyncMock, return_value=10000)
    @patch("crud.get_shop_item_by_id", new_callable=AsyncMock)
    @patch("crud.get_npc_location", new_callable=AsyncMock, return_value=100)
    @patch("crud.get_character_location", new_callable=AsyncMock, return_value=100)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_buy_with_charisma_0_full_price(
        self, mock_ownership, mock_char_loc, mock_npc_loc,
        mock_shop_item, mock_deduct, mock_dec_stock,
        mock_item_name, mock_httpx_cls, client,
    ):
        """Purchase with charisma=0 -> full price, no discount."""
        from main import app

        mock_shop_item.return_value = _make_shop_item(buy_price=1000, npc_id=5)

        mock_attrs_resp = MagicMock(status_code=200)
        mock_attrs_resp.json.return_value = {"charisma": 0}
        mock_inv_resp = MagicMock(status_code=200)
        mock_httpx_cls.return_value = self._make_httpx_mock(mock_attrs_resp, mock_inv_resp)

        response = self._buy_request(client, app)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["discount_percent"] == 0.0
        assert data["total_price"] == 1000

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_item_name", new_callable=AsyncMock, return_value="Test Sword")
    @patch("crud.decrement_stock", new_callable=AsyncMock)
    @patch("crud.deduct_currency", new_callable=AsyncMock, return_value=5000)
    @patch("crud.get_shop_item_by_id", new_callable=AsyncMock)
    @patch("crud.get_npc_location", new_callable=AsyncMock, return_value=100)
    @patch("crud.get_character_location", new_callable=AsyncMock, return_value=100)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_buy_with_charisma_250_max_discount(
        self, mock_ownership, mock_char_loc, mock_npc_loc,
        mock_shop_item, mock_deduct, mock_dec_stock,
        mock_item_name, mock_httpx_cls, client,
    ):
        """Purchase with charisma=250 -> 50% discount (max cap)."""
        from main import app

        mock_shop_item.return_value = _make_shop_item(buy_price=1000, npc_id=5)

        mock_attrs_resp = MagicMock(status_code=200)
        mock_attrs_resp.json.return_value = {"charisma": 250}
        mock_inv_resp = MagicMock(status_code=200)
        mock_httpx_cls.return_value = self._make_httpx_mock(mock_attrs_resp, mock_inv_resp)

        response = self._buy_request(client, app)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["discount_percent"] == 50.0
        assert data["total_price"] == 500

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_item_name", new_callable=AsyncMock, return_value="Test Sword")
    @patch("crud.decrement_stock", new_callable=AsyncMock)
    @patch("crud.deduct_currency", new_callable=AsyncMock, return_value=9000)
    @patch("crud.get_shop_item_by_id", new_callable=AsyncMock)
    @patch("crud.get_npc_location", new_callable=AsyncMock, return_value=100)
    @patch("crud.get_character_location", new_callable=AsyncMock, return_value=100)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_buy_discount_in_response(
        self, mock_ownership, mock_char_loc, mock_npc_loc,
        mock_shop_item, mock_deduct, mock_dec_stock,
        mock_item_name, mock_httpx_cls, client,
    ):
        """Verify discount_percent is present in buy response."""
        from main import app

        mock_shop_item.return_value = _make_shop_item(buy_price=100, npc_id=5)

        mock_attrs_resp = MagicMock(status_code=200)
        mock_attrs_resp.json.return_value = {"charisma": 100}
        mock_inv_resp = MagicMock(status_code=200)
        mock_httpx_cls.return_value = self._make_httpx_mock(mock_attrs_resp, mock_inv_resp)

        response = self._buy_request(client, app)

        assert response.status_code == 200
        data = response.json()
        assert "discount_percent" in data
        assert data["discount_percent"] == 20.0
        assert data["total_price"] == 80


# ===========================================================================
# 3. Shop listing with character_id parameter
# ===========================================================================
class TestGetNpcShopWithDiscount:
    """Tests for GET /npcs/{npc_id}/shop with/without character_id."""

    @patch("main._fetch_charisma", new_callable=AsyncMock, return_value=50)
    @patch("crud.get_npc_shop_items_player", new_callable=AsyncMock)
    def test_shop_with_character_id_returns_discounted_price(
        self, mock_shop_items, mock_fetch_charisma, client,
    ):
        """GET /npcs/{npc_id}/shop?character_id=X returns discounted_buy_price."""
        item = _make_shop_item(buy_price=1000, npc_id=5)
        mock_shop_items.return_value = [item]

        response = client.get("/locations/npcs/5/shop?character_id=1")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["discounted_buy_price"] is not None
        # charisma=50 → 10% discount: ceil(1000 * 0.9) = 900
        assert data[0]["discounted_buy_price"] == 900

    @patch("crud.get_npc_shop_items_player", new_callable=AsyncMock)
    def test_shop_without_character_id_no_discounted_price(
        self, mock_shop_items, client,
    ):
        """GET /npcs/{npc_id}/shop without character_id → discounted_buy_price is null."""
        item = _make_shop_item(buy_price=1000, npc_id=5)
        mock_shop_items.return_value = [item]

        response = client.get("/locations/npcs/5/shop")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        # Without character_id, the raw items are returned
        # discounted_buy_price should be null/None
        assert data[0].get("discounted_buy_price") is None

    @patch("main._fetch_charisma", new_callable=AsyncMock, return_value=250)
    @patch("crud.get_npc_shop_items_player", new_callable=AsyncMock)
    def test_shop_max_discount_applied(
        self, mock_shop_items, mock_fetch_charisma, client,
    ):
        """GET /npcs/{npc_id}/shop?character_id=X with charisma=250 → 50% discount."""
        item = _make_shop_item(buy_price=1000, npc_id=5)
        mock_shop_items.return_value = [item]

        response = client.get("/locations/npcs/5/shop?character_id=1")

        assert response.status_code == 200
        data = response.json()
        assert data[0]["discounted_buy_price"] == 500

    @patch("main._fetch_charisma", new_callable=AsyncMock, return_value=0)
    @patch("crud.get_npc_shop_items_player", new_callable=AsyncMock)
    def test_shop_zero_charisma_no_discount(
        self, mock_shop_items, mock_fetch_charisma, client,
    ):
        """GET /npcs/{npc_id}/shop?character_id=X with charisma=0 → full price."""
        item = _make_shop_item(buy_price=1000, npc_id=5)
        mock_shop_items.return_value = [item]

        response = client.get("/locations/npcs/5/shop?character_id=1")

        assert response.status_code == 200
        data = response.json()
        # charisma=0 → discount=0% → discounted_buy_price = buy_price
        assert data[0]["discounted_buy_price"] == 1000


# ===========================================================================
# 4. Graceful degradation — attributes-service errors
# ===========================================================================
class TestGracefulDegradation:
    """When attributes-service fails, purchase should proceed at full price."""

    def _buy_request(self, client, app):
        """Execute a standard buy request with auth override."""
        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        try:
            response = client.post(
                "/locations/npcs/5/shop/buy",
                json={"character_id": 1, "shop_item_id": 10, "quantity": 1},
                headers={"Authorization": "Bearer test-token"},
            )
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)
        return response

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_item_name", new_callable=AsyncMock, return_value="Test Sword")
    @patch("crud.decrement_stock", new_callable=AsyncMock)
    @patch("crud.deduct_currency", new_callable=AsyncMock, return_value=9000)
    @patch("crud.get_shop_item_by_id", new_callable=AsyncMock)
    @patch("crud.get_npc_location", new_callable=AsyncMock, return_value=100)
    @patch("crud.get_character_location", new_callable=AsyncMock, return_value=100)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_attributes_service_500_full_price(
        self, mock_ownership, mock_char_loc, mock_npc_loc,
        mock_shop_item, mock_deduct, mock_dec_stock,
        mock_item_name, mock_httpx_cls, client,
    ):
        """Attributes-service returns 500 -> purchase proceeds at full price."""
        from main import app

        mock_shop_item.return_value = _make_shop_item(buy_price=1000, npc_id=5)

        mock_attrs_resp = MagicMock(status_code=500)
        mock_attrs_resp.json.return_value = {}
        mock_inv_resp = MagicMock(status_code=200)

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_attrs_resp)
        mock_client_instance.post = AsyncMock(return_value=mock_inv_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        response = self._buy_request(client, app)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["discount_percent"] == 0.0
        assert data["total_price"] == 1000

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_item_name", new_callable=AsyncMock, return_value="Test Sword")
    @patch("crud.decrement_stock", new_callable=AsyncMock)
    @patch("crud.deduct_currency", new_callable=AsyncMock, return_value=9000)
    @patch("crud.get_shop_item_by_id", new_callable=AsyncMock)
    @patch("crud.get_npc_location", new_callable=AsyncMock, return_value=100)
    @patch("crud.get_character_location", new_callable=AsyncMock, return_value=100)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_attributes_service_timeout_full_price(
        self, mock_ownership, mock_char_loc, mock_npc_loc,
        mock_shop_item, mock_deduct, mock_dec_stock,
        mock_item_name, mock_httpx_cls, client,
    ):
        """Attributes-service timeout -> purchase proceeds at full price."""
        from main import app
        import httpx as httpx_module

        mock_shop_item.return_value = _make_shop_item(buy_price=1000, npc_id=5)

        mock_inv_resp = MagicMock(status_code=200)

        async def smart_get(*args, **kwargs):
            raise httpx_module.ReadTimeout("Connection timed out")

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(side_effect=smart_get)
        mock_client_instance.post = AsyncMock(return_value=mock_inv_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        response = self._buy_request(client, app)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["discount_percent"] == 0.0
        assert data["total_price"] == 1000

    @patch("main._fetch_charisma", new_callable=AsyncMock, return_value=None)
    @patch("crud.get_npc_shop_items_player", new_callable=AsyncMock)
    def test_shop_listing_graceful_degradation(
        self, mock_shop_items, mock_fetch_charisma, client,
    ):
        """Shop listing with character_id when attributes-service fails → full price."""
        item = _make_shop_item(buy_price=1000, npc_id=5)
        mock_shop_items.return_value = [item]

        response = client.get("/locations/npcs/5/shop?character_id=1")

        assert response.status_code == 200
        data = response.json()
        # _fetch_charisma returns None → discount=0% → discounted_buy_price = buy_price
        assert data[0]["discounted_buy_price"] == 1000
