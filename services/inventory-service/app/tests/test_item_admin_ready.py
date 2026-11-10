"""
FEAT-210 — inventory-service: the admin items list and the «Готов» mark.

* `GET /inventory/admin/items` (`items:read`) — the whole catalogue as slim
  rows ordered by id, the only list that carries `admin_ready*`. It must be
  matched before `GET /inventory/{character_id}/items` (otherwise "admin" is
  parsed as a character id → 422). Filtering / sorting / pagination are done on
  the client (§3.6), so the backend contract is: every item, id order, slim keys.
* `PUT /inventory/admin/items/{id}/ready` (`items:update`) — idempotent mark:
  re-marking keeps the original who/when, unmarking clears both.
* The mark never leaks into public / internal / admin-detail item bodies and
  survives a regular `PUT /inventory/items/{id}`.
* Migration 036 sits on 035 and only touches plain columns.

State is always read back from the `items` row (silent-failure guard).
"""

import importlib.util
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import auth_http
import models
from auth_http import UserRead, get_current_user_via_http
from main import app

AUTH = {"Authorization": "Bearer fake-token"}
INTERNAL_TOKEN = "test-internal-token"
READY_KEYS = {"admin_ready", "admin_ready_at", "admin_ready_by"}
ROW_KEYS = {
    "id", "name", "image", "item_type", "item_rarity", "item_level",
    "armor_subclass", "weapon_subclass", "resource_subcategory",
} | READY_KEYS

SWORD, ORE, ROBE = 30, 10, 20
MISSING = 99999

EDITOR = UserRead(id=1, username="Редактор_Аня", role="editor",
                  permissions=["items:read", "items:update"])
OTHER_EDITOR = UserRead(id=2, username="other_editor", role="editor",
                        permissions=["items:read", "items:update"])


def _me(uid, role, permissions):
    return {"id": uid, "username": f"u{uid}", "role": role, "permissions": list(permissions)}


def _mock_users_me(user):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = user
    return resp


def _as(user):
    app.dependency_overrides[get_current_user_via_http] = lambda: user


@pytest.fixture()
def items(db_session):
    """Three items inserted out of id order, with every slim column filled somewhere."""
    db_session.add(models.Items(
        id=SWORD, name="Клинок Скитальца", image="https://s3/sword.webp",
        item_type="main_weapon", item_rarity="rare", item_level=7,
        max_stack_size=1, is_unique=False, weapon_subclass="sword", price=500,
    ))
    db_session.add(models.Items(
        id=ORE, name="Медная руда", item_type="resource", item_rarity="common",
        item_level=1, max_stack_size=99, is_unique=False, resource_subcategory="ore",
    ))
    db_session.add(models.Items(
        id=ROBE, name="Роба", item_type="body", item_rarity="common", item_level=2,
        max_stack_size=1, is_unique=False, armor_subclass="cloth",
    ))
    db_session.commit()
    yield db_session
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _row(db, item_id):
    db.expire_all()
    return db.query(models.Items).filter(models.Items.id == item_id).one()


def _mark(db, item_id, by="old_admin", at=datetime(2026, 1, 1, 12, 0, 0)):
    item = _row(db, item_id)
    item.admin_ready, item.admin_ready_at, item.admin_ready_by = True, at, by
    db.commit()


def _ready(client, item_id, body, **kw):
    return client.put(f"/inventory/admin/items/{item_id}/ready", json=body, **kw)


# ===========================================================================
# GET /inventory/admin/items — auth matrix (real auth path, /users/me mocked)
# ===========================================================================

class TestListAuth:

    def test_guest_is_401_not_422(self, items, client):
        r = client.get("/inventory/admin/items")
        assert r.status_code == 401, r.text

    @patch("auth_http.requests.get")
    def test_forged_token_is_401(self, mock_get, items, client):
        rejected = MagicMock(status_code=401)
        rejected.json.return_value = {}
        mock_get.return_value = rejected
        assert client.get("/inventory/admin/items", headers=AUTH).status_code == 401

    @pytest.mark.parametrize("user", [
        _me(4, "user", []),
        _me(5, "moderator", ["mobs:manage"]),
        _me(6, "admin", []),
        _me(7, "editor", ["items:update", "items:create", "items:delete"]),
    ])
    @patch("auth_http.requests.get")
    def test_without_items_read_is_403(self, mock_get, items, client, user):
        mock_get.return_value = _mock_users_me(user)
        r = client.get("/inventory/admin/items", headers=AUTH)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "Недостаточно прав"

    @pytest.mark.parametrize("user", [
        _me(1, "admin", ["items:read", "items:update"]),
        _me(2, "editor", ["items:read"]),
    ])
    @patch("auth_http.requests.get")
    def test_with_items_read_is_200(self, mock_get, items, client, user):
        mock_get.return_value = _mock_users_me(user)
        r = client.get("/inventory/admin/items", headers=AUTH)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


# ===========================================================================
# GET /inventory/admin/items — body
# ===========================================================================

class TestListBody:

    def test_route_is_not_shadowed_by_character_items(self, items, client):
        _as(EDITOR)
        r = client.get("/inventory/admin/items")
        assert r.status_code == 200, r.text
        # character-inventory rows have character_id/quantity — these are items.
        assert all("quantity" not in row and "character_id" not in row for row in r.json())

    def test_route_declared_before_character_items(self):
        paths = [getattr(route, "path", None) for route in app.routes]
        admin = paths.index("/inventory/admin/items")
        char_items = paths.index("/inventory/{character_id}/items")
        assert admin < char_items

    def test_all_items_ordered_by_id_with_slim_keys(self, items, client):
        _as(EDITOR)
        body = client.get("/inventory/admin/items").json()
        assert [row["id"] for row in body] == [ORE, ROBE, SWORD]
        for row in body:
            assert set(row) == ROW_KEYS
        sword = body[2]
        assert sword == {
            "id": SWORD, "name": "Клинок Скитальца", "image": "https://s3/sword.webp",
            "item_type": "main_weapon", "item_rarity": "rare", "item_level": 7,
            "armor_subclass": None, "weapon_subclass": "sword", "resource_subcategory": None,
            "admin_ready": False, "admin_ready_at": None, "admin_ready_by": None,
        }
        assert body[0]["resource_subcategory"] == "ore"
        assert body[1]["armor_subclass"] == "cloth"

    def test_no_fat_fields(self, items, client):
        _as(EDITOR)
        row = client.get("/inventory/admin/items").json()[0]
        for fat in ("effects", "damage_entries", "xp_buffs", "price", "description",
                    "strength_modifier", "max_stack_size"):
            assert fat not in row

    def test_ready_mark_is_listed(self, items, client):
        _mark(items, ROBE, by="anya", at=datetime(2026, 11, 10, 20, 30, 0))
        _as(EDITOR)
        by_id = {row["id"]: row for row in client.get("/inventory/admin/items").json()}
        assert by_id[ROBE]["admin_ready"] is True
        assert by_id[ROBE]["admin_ready_by"] == "anya"
        assert by_id[ROBE]["admin_ready_at"].startswith("2026-11-10T20:30:00")
        assert by_id[ORE]["admin_ready"] is False
        assert by_id[SWORD]["admin_ready"] is False

    def test_empty_catalogue_is_empty_list(self, db_session, client):
        _as(EDITOR)
        try:
            r = client.get("/inventory/admin/items")
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)
        assert r.status_code == 200
        assert r.json() == []

    def test_query_params_are_ignored(self, items, client):
        """The contract has no params; junk / injection-shaped values change nothing."""
        _as(EDITOR)
        plain = client.get("/inventory/admin/items").json()
        noisy = client.get("/inventory/admin/items",
                           params={"q": "' OR 1=1 --", "page": "-1", "ready": "x"})
        assert noisy.status_code == 200
        assert noisy.json() == plain

    def test_db_error_is_russian_500(self, items, client):
        _as(EDITOR)
        with patch("sqlalchemy.orm.Query.all", side_effect=RuntimeError("boom secret")):
            r = client.get("/inventory/admin/items")
        assert r.status_code == 500
        assert r.json()["detail"] == "Внутренняя ошибка сервера"
        assert "boom" not in r.text


# ===========================================================================
# PUT /inventory/admin/items/{id}/ready — auth
# ===========================================================================

class TestReadyAuth:

    def test_guest_is_401(self, items, client):
        assert _ready(client, ORE, {"ready": True}).status_code == 401
        assert _row(items, ORE).admin_ready is False

    @pytest.mark.parametrize("user", [
        _me(4, "user", []),
        _me(5, "editor", ["items:read"]),  # read-only editor
        _me(6, "admin", []),
        _me(7, "moderator", ["mobs:manage"]),
    ])
    @patch("auth_http.requests.get")
    def test_without_items_update_is_403(self, mock_get, items, client, user):
        mock_get.return_value = _mock_users_me(user)
        r = _ready(client, ORE, {"ready": True}, headers=AUTH)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "Недостаточно прав"
        assert _row(items, ORE).admin_ready is False

    @patch("auth_http.requests.get")
    def test_with_items_update_is_200_and_by_is_username(self, mock_get, items, client):
        mock_get.return_value = _mock_users_me(_me(8, "editor", ["items:update"]))
        r = _ready(client, ORE, {"ready": True}, headers=AUTH)
        assert r.status_code == 200, r.text
        assert r.json()["admin_ready_by"] == "u8"
        assert _row(items, ORE).admin_ready_by == "u8"


# ===========================================================================
# PUT /inventory/admin/items/{id}/ready — behaviour
# ===========================================================================

class TestReadyToggle:

    def test_set_marks_who_and_when(self, items, client):
        _as(EDITOR)
        before = datetime.utcnow() - timedelta(seconds=2)
        r = _ready(client, SWORD, {"ready": True})
        after = datetime.utcnow() + timedelta(seconds=2)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"id"} | READY_KEYS
        assert body["id"] == SWORD
        assert body["admin_ready"] is True
        assert body["admin_ready_by"] == "Редактор_Аня"
        row = _row(items, SWORD)
        assert row.admin_ready is True
        assert row.admin_ready_by == "Редактор_Аня"
        assert before <= row.admin_ready_at <= after
        # other items untouched
        assert _row(items, ORE).admin_ready is False
        assert _row(items, ROBE).admin_ready_at is None

    def test_set_again_keeps_original_who_and_when(self, items, client):
        original_at = datetime(2026, 1, 1, 12, 0, 0)
        _mark(items, SWORD, by="first_admin", at=original_at)
        _as(OTHER_EDITOR)
        r = _ready(client, SWORD, {"ready": True})
        assert r.status_code == 200, r.text
        assert r.json()["admin_ready_by"] == "first_admin"
        assert r.json()["admin_ready_at"].startswith("2026-01-01T12:00:00")
        row = _row(items, SWORD)
        assert (row.admin_ready, row.admin_ready_by, row.admin_ready_at) == (True, "first_admin", original_at)

    def test_unset_clears_who_and_when(self, items, client):
        _mark(items, SWORD)
        _as(EDITOR)
        r = _ready(client, SWORD, {"ready": False})
        assert r.status_code == 200, r.text
        assert r.json() == {"id": SWORD, "admin_ready": False,
                            "admin_ready_at": None, "admin_ready_by": None}
        row = _row(items, SWORD)
        assert (row.admin_ready, row.admin_ready_at, row.admin_ready_by) == (False, None, None)

    def test_unset_on_unmarked_is_noop_200(self, items, client):
        _as(EDITOR)
        r = _ready(client, ORE, {"ready": False})
        assert r.status_code == 200
        row = _row(items, ORE)
        assert (row.admin_ready, row.admin_ready_at, row.admin_ready_by) == (False, None, None)

    def test_set_unset_set_gets_fresh_who(self, items, client):
        _mark(items, SWORD, by="first_admin")
        _as(EDITOR)
        assert _ready(client, SWORD, {"ready": False}).status_code == 200
        assert _ready(client, SWORD, {"ready": True}).json()["admin_ready_by"] == "Редактор_Аня"
        assert _row(items, SWORD).admin_ready_at > datetime(2026, 1, 1, 12, 0, 0)

    def test_toggle_does_not_touch_other_columns(self, items, client):
        _as(EDITOR)
        assert _ready(client, SWORD, {"ready": True}).status_code == 200
        row = _row(items, SWORD)
        assert (row.name, row.price, row.item_level, row.weapon_subclass) == \
            ("Клинок Скитальца", 500, 7, "sword")

    def test_missing_item_is_404_in_russian(self, items, client):
        _as(EDITOR)
        r = _ready(client, MISSING, {"ready": True})
        assert r.status_code == 404
        assert r.json()["detail"] == "Предмет не найден"

    @pytest.mark.parametrize("body", [
        {},
        {"ready": True, "admin_ready_by": "hacker"},
        {"ready": True, "extra": 1},
        {"ready": None},
        {"ready": "maybe"},
        {"ready": [1]},
    ])
    def test_bad_body_is_422(self, items, client, body):
        _as(EDITOR)
        r = _ready(client, ORE, body)
        assert r.status_code == 422, r.text
        assert _row(items, ORE).admin_ready is False

    def test_non_int_id_is_422(self, items, client):
        _as(EDITOR)
        assert client.put("/inventory/admin/items/abc/ready", json={"ready": True}).status_code == 422

    def test_db_error_rolls_back_with_russian_500(self, items, client):
        _as(EDITOR)
        with patch("sqlalchemy.orm.Session.commit", side_effect=RuntimeError("boom secret")):
            r = _ready(client, ORE, {"ready": True})
        assert r.status_code == 500
        assert r.json()["detail"] == "Внутренняя ошибка сервера"
        assert "boom" not in r.text
        assert _row(items, ORE).admin_ready is False


# ===========================================================================
# No leak: the mark never shows up outside the admin list / toggle
# ===========================================================================

class TestNoLeak:

    @pytest.fixture()
    def marked(self, items):
        _mark(items, SWORD, by="anya")
        _mark(items, ORE, by="anya")
        return items

    def _assert_clean(self, body):
        text = str(body)
        assert "admin_ready" not in text
        assert "anya" not in text

    def test_public_list(self, marked, client):
        r = client.get("/inventory/items")
        assert r.status_code == 200
        assert {row["id"] for row in r.json()} >= {SWORD, ORE}
        self._assert_clean(r.json())

    def test_public_card(self, marked, client):
        r = client.get(f"/inventory/items/{SWORD}")
        assert r.status_code == 200
        self._assert_clean(r.json())

    def test_admin_detail(self, marked, client):
        _as(EDITOR)
        r = client.get(f"/inventory/admin/items/{SWORD}")
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Клинок Скитальца"
        self._assert_clean(r.json())

    def test_internal_twin(self, marked, client, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", INTERNAL_TOKEN)
        r = client.get(f"/inventory/internal/items/{SWORD}",
                       headers={"X-Internal-Token": INTERNAL_TOKEN})
        assert r.status_code == 200, r.text
        self._assert_clean(r.json())


# ===========================================================================
# A regular item edit keeps the mark (ItemCreate cannot carry it)
# ===========================================================================

class TestItemEditKeepsMark:

    def _put(self, client, **extra):
        body = {"name": "Роба мудреца", "item_type": "body", "item_rarity": "common",
                "item_level": 2, "max_stack_size": 1, "is_unique": False, **extra}
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock), \
             patch("main._reconcile_perks_async", new_callable=AsyncMock):
            return client.put(f"/inventory/items/{ROBE}", json=body)

    def test_edit_keeps_mark(self, items, client):
        at = datetime(2026, 3, 3, 3, 3, 3)
        _mark(items, ROBE, by="anya", at=at)
        _as(EDITOR)
        r = self._put(client)
        assert r.status_code == 200, r.text
        self._no_mark(r.json())
        row = _row(items, ROBE)
        assert row.name == "Роба мудреца"
        assert (row.admin_ready, row.admin_ready_by, row.admin_ready_at) == (True, "anya", at)

    def test_edit_payload_cannot_set_mark(self, items, client):
        _as(EDITOR)
        r = self._put(client, admin_ready=True, admin_ready_by="hacker",
                      admin_ready_at="2026-01-01T00:00:00")
        assert r.status_code in (200, 422), r.text
        row = _row(items, ROBE)
        assert (row.admin_ready, row.admin_ready_by, row.admin_ready_at) == (False, None, None)

    @staticmethod
    def _no_mark(body):
        assert "admin_ready" not in str(body)


# ===========================================================================
# Migration 036
# ===========================================================================

_VERSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "alembic", "versions")


def _load_036():
    path = os.path.join(_VERSIONS_DIR, "036_item_admin_ready.py")
    spec = importlib.util.spec_from_file_location("mig_036_item_admin_ready", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigration036:

    def test_revision_chain(self):
        m = _load_036()
        assert m.revision == "036_item_admin_ready"
        assert m.down_revision == "035_item_stealth_modifier"
        assert len(m.revision) <= 32
        assert os.path.exists(os.path.join(_VERSIONS_DIR, "035_item_stealth_modifier.py"))

    def test_upgrade_adds_three_plain_columns_idempotently(self):
        m = _load_036()
        added = []
        with patch.object(m, "_has_column", return_value=False), \
             patch.object(m.op, "add_column", side_effect=lambda t, c: added.append((t, c))):
            m.upgrade()
        assert [(t, c.name) for t, c in added] == [
            ("items", "admin_ready"), ("items", "admin_ready_at"), ("items", "admin_ready_by"),
        ]
        ready = added[0][1]
        assert ready.nullable is False
        assert str(ready.server_default.arg) == "0"
        assert added[1][1].nullable is True and added[2][1].nullable is True

        added.clear()
        with patch.object(m, "_has_column", return_value=True), \
             patch.object(m.op, "add_column", side_effect=lambda t, c: added.append((t, c))):
            m.upgrade()
        assert added == []

    def test_downgrade_drops_the_columns(self):
        m = _load_036()
        dropped = []
        with patch.object(m, "_has_column", return_value=True), \
             patch.object(m.op, "drop_column", side_effect=lambda t, c: dropped.append((t, c))):
            m.downgrade()
        assert sorted(dropped) == sorted([
            ("items", "admin_ready"), ("items", "admin_ready_at"), ("items", "admin_ready_by"),
        ])

    def test_no_enum_or_item_type_touched(self):
        with open(os.path.join(_VERSIONS_DIR, "036_item_admin_ready.py"), encoding="utf-8") as f:
            src = f.read()
        assert "Enum" not in src and "alter_column" not in src and "item_type" not in src.split('"""', 2)[2]
