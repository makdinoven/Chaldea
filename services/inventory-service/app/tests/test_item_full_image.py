"""
items.full_image — the uncropped original of an item picture.

photo-service writes it; inventory-service only hands it out:
- GET /inventory/items/{id} returns it (item detail windows show it)
- PUT /inventory/items/{id} cannot overwrite it (admins change it by uploading)
- auction listing responses carry it for the lot detail window
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

import auth_http
import models

# FEAT-171 I3: `GET /inventory/items/{id}` is now the thin public card; the fat
# item template moved to the internal twin, which requires `X-Internal-Token`.
_INTERNAL_TOKEN = "test-internal-token"
_INTERNAL_HEADERS = {"X-Internal-Token": _INTERNAL_TOKEN}


@pytest.fixture(autouse=True)
def _pin_internal_token(monkeypatch):
    """`verify_internal_token` reads a module-level constant — pin it."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _INTERNAL_TOKEN)



FULL = "https://s3/items/item_full_image_1.webp"
ICON = "https://s3/items/item_image_1.webp"

ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin", "permissions": ["items:update"]}


def _auth_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ADMIN
    return resp


def _seed_item(db_session, full_image=FULL):
    item = models.Items(
        id=1, name="Меч", image=ICON, full_image=full_image,
        item_type="weapon", item_rarity="common", item_level=1,
        max_stack_size=1, is_unique=False,
    )
    db_session.add(item)
    db_session.commit()
    return item


class TestItemFullImage:

    def test_get_item_returns_full_image(self, client, db_session):
        _seed_item(db_session)
        body = client.get("/inventory/internal/items/1", headers=_INTERNAL_HEADERS).json()
        assert body["image"] == ICON
        assert body["full_image"] == FULL

    def test_item_without_original_returns_null(self, client, db_session):
        _seed_item(db_session, full_image=None)
        assert client.get("/inventory/internal/items/1", headers=_INTERNAL_HEADERS).json()["full_image"] is None

    def test_put_does_not_overwrite_full_image(self, client, db_session):
        _seed_item(db_session)
        body = client.get("/inventory/internal/items/1", headers=_INTERNAL_HEADERS).json()
        body["full_image"] = "https://evil/other.webp"
        body["name"] = "Меч 2"

        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.put("/inventory/items/1", json=body, headers=ADMIN_HEADERS)

        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Меч 2"
        assert resp.json()["full_image"] == FULL


class TestAuctionFullImage:

    def test_listing_item_carries_full_image(self, db_session):
        import crud

        _seed_item(db_session)
        now = datetime.utcnow()
        listing = models.AuctionListing(
            seller_character_id=1, item_id=1, quantity=1,
            start_price=10, buyout_price=None, current_bid=0,
            status="active", created_at=now, expires_at=now + timedelta(hours=1),
        )
        db_session.add(listing)
        db_session.commit()

        with patch("crud.get_character_name", return_value="Alice"):
            data = crud._build_listing_response(db_session, listing)

        assert data["item"]["image"] == ICON
        assert data["item"]["full_image"] == FULL

    def test_listing_item_carries_weapon_kind(self, db_session):
        import crud

        item = _seed_item(db_session)
        item.weapon_subclass = "sword"
        db_session.commit()
        now = datetime.utcnow()
        listing = models.AuctionListing(
            seller_character_id=1, item_id=1, quantity=1,
            start_price=10, buyout_price=None, current_bid=0,
            status="active", created_at=now, expires_at=now + timedelta(hours=1),
        )
        db_session.add(listing)
        db_session.commit()

        with patch("crud.get_character_name", return_value="Alice"):
            data = crud._build_listing_response(db_session, listing)

        assert data["item"]["weapon_subclass"] == "sword"
        assert data["item"]["armor_subclass"] is None
