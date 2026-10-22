"""
Tests for notification categories and per-user notification preferences.

Covers:
- GET/PUT /notifications/me/preferences (defaults, partial update, validation,
  mandatory categories rejected, auth required, unknown stored keys ignored)
- general_notifications consumer filtering:
  off -> nothing saved/pushed; bell -> saved + silent push; all -> loud push;
  mandatory categories ignore preferences; ws_type fallback map; unknown -> system;
  broadcasts are never filtered
- category exposed in the unread/full list endpoints
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from models import Notification, NotificationPreference
from notification_categories import (
    CONFIGURABLE_CATEGORIES,
    INVALID_PREFERENCE_DETAIL,
    WS_TYPE_CATEGORY_MAP,
    resolve_category,
)

DEFAULTS = {c: "all" for c in CONFIGURABLE_CATEGORIES}
URL = "/notifications/me/preferences"


def _set_prefs(db, user_id, prefs):
    db.add(NotificationPreference(user_id=user_id, settings=json.dumps(prefs)))
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestPreferencesEndpoints:

    def test_get_defaults(self, client):
        resp = client.get(URL)
        assert resp.status_code == 200
        assert resp.json() == {"preferences": DEFAULTS}

    def test_put_partial_update(self, client):
        resp = client.put(URL, json={"preferences": {"trade": "off", "social": "bell"}})
        assert resp.status_code == 200
        expected = dict(DEFAULTS, trade="off", social="bell")
        assert resp.json() == {"preferences": expected}
        assert client.get(URL).json() == {"preferences": expected}

    def test_put_merges_with_previous(self, client):
        client.put(URL, json={"preferences": {"trade": "off"}})
        resp = client.put(URL, json={"preferences": {"world": "bell"}})
        assert resp.json()["preferences"]["trade"] == "off"
        assert resp.json()["preferences"]["world"] == "bell"

    def test_put_empty_is_noop(self, client):
        resp = client.put(URL, json={"preferences": {}})
        assert resp.status_code == 200
        assert resp.json() == {"preferences": DEFAULTS}

    @pytest.mark.parametrize("prefs", [
        {"unknown": "all"},
        {"trade": "loud"},
        {"trade": ""},
        {"battle": "off"},
        {"system": "bell"},
        {"trade": "off", "social": "nope"},
        {"trade": "'; DROP TABLE notifications; --"},
    ])
    def test_put_invalid_rejected_and_nothing_saved(self, client, db_session, prefs):
        resp = client.put(URL, json={"preferences": prefs})
        assert resp.status_code == 422
        assert resp.json()["detail"] == INVALID_PREFERENCE_DETAIL
        assert db_session.query(NotificationPreference).count() == 0
        assert client.get(URL).json() == {"preferences": DEFAULTS}

    def test_put_missing_body_422(self, client):
        assert client.put(URL, json={}).status_code == 422

    def test_unknown_and_invalid_stored_values_ignored(self, client, db_session, test_user):
        _set_prefs(db_session, test_user.id, {"legacy": "off", "trade": "bogus", "world": "off"})
        assert client.get(URL).json() == {"preferences": dict(DEFAULTS, world="off")}

    def test_preferences_are_per_user(self, client, db_session):
        _set_prefs(db_session, 777, {"trade": "off"})
        assert client.get(URL).json() == {"preferences": DEFAULTS}

    def test_auth_required(self, db_session):
        from main import app
        from database import get_db

        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            anon = TestClient(app)
            assert anon.get(URL).status_code == 401
            assert anon.put(URL, json={"preferences": {"trade": "off"}}).status_code == 401
        finally:
            app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Consumer
# ═══════════════════════════════════════════════════════════════════════════

def _payload(**kw):
    data = {"target_type": "user", "target_value": 1, "message": "Привет"}
    data.update(kw)
    return data


class TestConsumerFiltering:

    @pytest.fixture(autouse=True)
    def _send(self):
        with patch("consumers.general_notification.send_to_user") as send:
            self.send = send
            yield

    def _handle(self, db, data):
        from consumers.general_notification import handle_notification
        handle_notification(db, data)

    def test_default_mode_saves_and_pushes_loud(self, db_session):
        self._handle(db_session, _payload(category="trade"))
        row = db_session.query(Notification).one()
        assert row.category == "trade"
        msg = self.send.call_args[0][1]
        assert msg["type"] == "notification"
        assert msg["data"]["category"] == "trade"
        assert msg["data"]["silent"] is False

    def test_off_saves_and_pushes_nothing(self, db_session):
        _set_prefs(db_session, 1, {"trade": "off"})
        self._handle(db_session, _payload(category="trade", ws_type="auction_sold", ws_data={"x": 1}))
        assert db_session.query(Notification).count() == 0
        self.send.assert_not_called()

    def test_bell_saves_and_pushes_silent(self, db_session):
        _set_prefs(db_session, 1, {"social": "bell"})
        self._handle(db_session, _payload(category="social", ws_type="friend_request",
                                          ws_data={"from_user_id": 2}))
        row = db_session.query(Notification).one()
        assert row.category == "social"
        msg = self.send.call_args[0][1]
        assert msg["type"] == "friend_request"
        assert msg["data"]["from_user_id"] == 2
        assert msg["data"]["notification_id"] == row.id
        assert msg["data"]["category"] == "social"
        assert msg["data"]["silent"] is True

    def test_off_only_affects_that_user(self, db_session):
        _set_prefs(db_session, 2, {"trade": "off"})
        self._handle(db_session, _payload(category="trade"))
        assert db_session.query(Notification).count() == 1

    @pytest.mark.parametrize("cat", ["battle", "system"])
    def test_mandatory_ignores_preferences(self, db_session, cat):
        # Even a (hand-crafted) stored "off" for a mandatory category is ignored.
        _set_prefs(db_session, 1, {c: "off" for c in CONFIGURABLE_CATEGORIES + ("battle", "system")})
        self._handle(db_session, _payload(category=cat))
        assert db_session.query(Notification).one().category == cat
        assert self.send.call_args[0][1]["data"]["silent"] is False

    def test_ws_type_fallback_when_category_missing(self, db_session):
        _set_prefs(db_session, 1, {"party": "off"})
        self._handle(db_session, _payload(ws_type="party_invitation", ws_data={}))
        assert db_session.query(Notification).count() == 0
        self.send.assert_not_called()

    def test_unknown_category_falls_back_to_ws_type(self, db_session):
        self._handle(db_session, _payload(category="bogus", ws_type="auction_won", ws_data={}))
        assert db_session.query(Notification).one().category == "trade"

    def test_unknown_everything_is_system(self, db_session):
        _set_prefs(db_session, 1, {c: "off" for c in CONFIGURABLE_CATEGORIES})
        self._handle(db_session, _payload(ws_type="something_new", ws_data={}))
        assert db_session.query(Notification).one().category == "system"
        self.send.assert_called_once()

    def test_missing_target_value_does_nothing(self, db_session):
        self._handle(db_session, {"target_type": "user", "message": "x"})
        assert db_session.query(Notification).count() == 0

    def test_broadcast_all_not_filtered(self, db_session):
        _set_prefs(db_session, 1, {"trade": "off"})
        with patch("consumers.general_notification.get_all_users",
                   return_value=[{"id": 1}, {"id": 2}]):
            self._handle(db_session, {"target_type": "all", "message": "Всем", "category": "trade"})
        rows = db_session.query(Notification).all()
        assert {r.user_id for r in rows} == {1, 2}
        assert {r.category for r in rows} == {"trade"}

    def test_broadcast_admins_defaults_to_system(self, db_session):
        with patch("consumers.general_notification.get_admins", return_value=[{"id": 9}]):
            self._handle(db_session, {"target_type": "admins", "message": "Тикет",
                                      "ws_type": "ticket_new_message", "ws_data": {"ticket_id": 3}})
        row = db_session.query(Notification).one()
        assert row.category == "system"
        msg = self.send.call_args[0][1]
        assert msg["data"]["ticket_id"] == 3
        assert msg["data"]["silent"] is False


class TestResolveCategory:

    def test_explicit_wins(self):
        assert resolve_category("world", "auction_sold") == "world"

    @pytest.mark.parametrize("ws_type,cat", sorted(WS_TYPE_CATEGORY_MAP.items()))
    def test_map(self, ws_type, cat):
        assert resolve_category(None, ws_type) == cat

    def test_party_vs_battle(self):
        assert resolve_category(None, "party_invitation") == "party"
        assert resolve_category(None, "party_started") == "battle"
        assert resolve_category(None, "pvp_invitation") == "battle"

    def test_default_system(self):
        assert resolve_category(None, None) == "system"
        assert resolve_category("", "nope") == "system"


# ═══════════════════════════════════════════════════════════════════════════
# List endpoints expose category
# ═══════════════════════════════════════════════════════════════════════════

class TestListCategory:

    def test_unread_and_full_include_category(self, client, db_session):
        db_session.add_all([
            Notification(user_id=1, message="new", status="unread", category="trade"),
            Notification(user_id=1, message="old", status="unread"),
        ])
        db_session.commit()
        for path in ("/notifications/1/unread", "/notifications/1/full"):
            items = client.get(path).json()["items"]
            by_msg = {i["message"]: i for i in items}
            assert by_msg["new"]["category"] == "trade"
            assert "category" in by_msg["old"] and by_msg["old"]["category"] is None


def test_admin_create_publishes_system_category(admin_client):
    with patch("main._publish_admin_notification") as pub:
        resp = admin_client.post("/notifications/create",
                                 json={"target_type": "all", "message": "Объявление"})
    assert resp.status_code == 200
    assert pub.call_args[0][0]["category"] == "system"


def test_preference_lookup_failure_fails_open(db_session):
    """A DB error while reading preferences must not drop the notification."""
    from consumers.general_notification import handle_notification
    with patch("notification_categories.get_preferences", side_effect=RuntimeError("db down")), \
            patch("consumers.general_notification.send_to_user") as send:
        handle_notification(db_session, _payload(category="trade"))
    assert db_session.query(Notification).one().category == "trade"
    assert send.call_args[0][1]["data"]["silent"] is False
