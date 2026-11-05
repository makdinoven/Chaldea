"""FEAT-199: the mask flag `items.is_mask`.

A mask is a head item marked `is_mask` (it takes the helmet slot); while worn,
witnesses of a crime see "an unknown in a mask" (character-service reads the
flag by SQL). Locked down here:

- the schema validator: head only, every other type rejected with a Russian
  message, default False;
- create / update / read (admin + internal twin) carry the flag; the public
  card does not expose it;
- `PUT /inventory/items/{id}` that moves the item off the head type clears the
  flag (a partial update may omit it);
- migration `034_item_mask` adds/drops exactly one NOT NULL column with a
  server default of 0, driven by a real Alembic `Operations` on SQLite.
"""

import importlib.util
import os
from unittest.mock import MagicMock, patch

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

import auth_http
import models
import schemas


HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update", "items:read"]}
TOKEN = "test-internal-token"
INTERNAL = {"X-Internal-Token": TOKEN}
MASK_ERROR = "Скрывать личность может только головной убор"

ALL_TYPES = [t.value for t in schemas.ItemType]
NON_HEAD_TYPES = [t for t in ALL_TYPES if t != "head"]


def _auth_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ADMIN
    return resp


def _body(**overrides):
    body = {
        "name": "Маска ночи",
        "item_level": 1,
        "item_type": "head",
        "item_rarity": "common",
        "max_stack_size": 1,
        "is_unique": False,
    }
    body.update(overrides)
    return body


def _post(client, body):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.post("/inventory/items", json=body, headers=HEADERS)


def _put(client, item_id, body):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.put(f"/inventory/items/{item_id}", json=body, headers=HEADERS)


def _admin_get(client, item_id):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.get(f"/inventory/admin/items/{item_id}", headers=HEADERS)


def _stored(db, item_id):
    db.expire_all()
    return db.query(models.Items).get(item_id).is_mask


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


# ===========================================================================
# 1. Schema validator
# ===========================================================================

class TestValidator:

    def test_constant_is_head(self):
        assert schemas.MASK_ITEM_TYPE == "head"

    def test_head_can_be_a_mask(self):
        item = schemas.ItemCreate(**_body(is_mask=True))
        assert item.is_mask is True

    def test_default_is_false(self):
        assert schemas.ItemCreate(**_body()).is_mask is False
        assert schemas.ItemCreate(**_body(item_type="body")).is_mask is False

    @pytest.mark.parametrize("item_type", NON_HEAD_TYPES)
    def test_every_other_type_is_rejected(self, item_type):
        body = _body(item_type=item_type, is_mask=True)
        with pytest.raises(ValidationError) as exc:
            schemas.ItemCreate(**body)
        assert MASK_ERROR in str(exc.value)

    @pytest.mark.parametrize("item_type", NON_HEAD_TYPES)
    def test_false_flag_is_fine_on_any_type(self, item_type):
        """Only a set flag is checked: is_mask=False never trips the validator."""
        try:
            schemas.ItemCreate(**_body(item_type=item_type, is_mask=False))
        except ValidationError as exc:  # other type rules may reject the bare body
            assert MASK_ERROR not in str(exc)

    def test_non_bool_rejected(self):
        with pytest.raises(ValidationError):
            schemas.ItemCreate(**_body(is_mask={"x": 1}))

    def test_read_schema_exposes_the_flag(self):
        assert "is_mask" in schemas.Item.__fields__
        assert schemas.Item.__fields__["is_mask"].default is False

    def test_model_column(self):
        col = models.Items.__table__.c.is_mask
        assert col.nullable is False
        assert str(col.server_default.arg) == "0"


# ===========================================================================
# 2. Create / update / read through the routes
# ===========================================================================

class TestRoutes:

    def test_create_mask_and_read_back(self, client, db_session):
        resp = _post(client, _body(is_mask=True))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["is_mask"] is True
        assert _stored(db_session, data["id"]) is True

        admin = _admin_get(client, data["id"])
        assert admin.status_code == 200, admin.text
        assert admin.json()["is_mask"] is True

        internal = client.get(f"/inventory/internal/items/{data['id']}", headers=INTERNAL)
        assert internal.status_code == 200, internal.text
        assert internal.json()["is_mask"] is True

    def test_public_card_does_not_carry_the_flag(self, client):
        item_id = _post(client, _body(is_mask=True)).json()["id"]
        resp = client.get(f"/inventory/items/{item_id}")
        assert resp.status_code == 200
        assert "is_mask" not in resp.json()

    def test_create_default_false(self, client, db_session):
        data = _post(client, _body(name="Шлем")).json()
        assert data["is_mask"] is False
        assert _stored(db_session, data["id"]) is False

    def test_create_non_head_mask_is_422_in_russian(self, client, db_session):
        before = db_session.query(models.Items).count()
        resp = _post(client, _body(name="Маска-кираса", item_type="body", is_mask=True))
        assert resp.status_code == 422
        assert MASK_ERROR in resp.text
        assert db_session.query(models.Items).count() == before

    def test_update_sets_and_clears_the_flag(self, client, db_session):
        item_id = _post(client, _body(name="Капюшон")).json()["id"]
        resp = _put(client, item_id, _body(name="Капюшон", is_mask=True))
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_mask"] is True
        assert _stored(db_session, item_id) is True

        resp = _put(client, item_id, _body(name="Капюшон", is_mask=False))
        assert resp.status_code == 200
        assert resp.json()["is_mask"] is False
        assert _stored(db_session, item_id) is False

    def test_update_without_the_flag_keeps_it_on_head(self, client, db_session):
        item_id = _post(client, _body(is_mask=True)).json()["id"]
        resp = _put(client, item_id, _body(description="Новая"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_mask"] is True
        assert _stored(db_session, item_id) is True

    def test_type_change_off_head_clears_the_flag(self, client, db_session):
        item_id = _post(client, _body(is_mask=True)).json()["id"]
        resp = _put(client, item_id, _body(item_type="body"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_mask"] is False
        assert _stored(db_session, item_id) is False

    def test_update_non_head_with_flag_is_rejected_and_row_untouched(self, client, db_session):
        item_id = _post(client, _body(is_mask=True)).json()["id"]
        resp = _put(client, item_id, _body(item_type="ring", is_mask=True))
        assert resp.status_code == 422
        assert MASK_ERROR in resp.text
        db_session.expire_all()
        row = db_session.query(models.Items).get(item_id)
        assert row.is_mask is True
        assert schemas._enum_value(row.item_type) == "head"

    def test_injection_like_name_is_stored_verbatim(self, client, db_session):
        name = "'; DROP TABLE items; --"
        resp = _post(client, _body(name=name, is_mask=True))
        assert resp.status_code == 201, resp.text
        assert resp.json()["name"] == name
        assert db_session.query(models.Items).filter_by(name=name).count() == 1


# ===========================================================================
# 3. Migration 034_item_mask
# ===========================================================================

_VERSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic", "versions"))


def _load(filename):
    path = os.path.join(_VERSIONS_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def migration_db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    conn = engine.connect()
    conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                      "item_type TEXT NOT NULL)"))
    conn.execute(text("INSERT INTO items (name, item_type) VALUES ('Старый шлем', 'head')"))
    conn.commit()
    mod = _load("034_item_mask.py")
    mod.op = Operations(MigrationContext.configure(conn))
    yield conn, mod
    conn.close()
    engine.dispose()


def _cols(conn):
    return {c["name"]: c for c in inspect(conn).get_columns("items")}


class TestMigration:

    def test_revision_chain(self):
        mod = _load("034_item_mask.py")
        assert mod.revision == "034_item_mask"
        assert mod.down_revision == "033_auction_listing_region"
        assert len(mod.revision) <= 32

    def test_upgrade_downgrade_upgrade(self, migration_db):
        conn, mod = migration_db
        mod.upgrade()
        conn.commit()
        cols = _cols(conn)
        assert "is_mask" in cols
        assert cols["is_mask"]["nullable"] is False
        # existing rows get the server default
        assert conn.execute(text("SELECT is_mask FROM items")).scalar() == 0
        conn.execute(text("INSERT INTO items (name, item_type) VALUES ('Новый', 'body')"))
        assert conn.execute(text("SELECT is_mask FROM items WHERE name='Новый'")).scalar() == 0

        mod.downgrade()
        conn.commit()
        assert "is_mask" not in _cols(conn)
        assert conn.execute(text("SELECT COUNT(*) FROM items")).scalar() == 2

        mod.upgrade()
        conn.commit()
        assert "is_mask" in _cols(conn)
