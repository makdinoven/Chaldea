"""
Account security: login sessions (`sid`), logout, session list/revocation,
password change, email change, legacy-token migration and the WebSocket kick
call to notification-service.
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import httpx
import pytest
from jose import jwt

import models
import sessions as session_store

# The unpatched function, captured before the autouse fixture replaces it.
_real_notify = session_store.notify_sessions_revoked
from auth import SECRET_KEY, ALGORITHM, SESSION_REVOKED_DETAIL
from crud import create_user
from schemas import UserCreate

PASSWORD = "Secret123"
REFRESH_401 = "Недействительный или истёкший refresh-токен"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def kick_mock():
    """Never reach the real notification-service; tests inspect the mock."""
    with patch("sessions.notify_sessions_revoked") as mock_kick:
        yield mock_kick


@pytest.fixture(autouse=True)
def no_rabbit():
    with patch("main.send_notification_event"):
        yield


def _make_user(db, username="secuser", email="sec@test.com", password=PASSWORD):
    return create_user(db, UserCreate(email=email, username=username, password=password))


def _login(client, identifier="sec@test.com", password=PASSWORD, ua="TestAgent/1.0"):
    resp = client.post(
        "/users/login",
        json={"identifier": identifier, "password": password},
        headers={"User-Agent": ua},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _claims(token):
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _legacy_token(email, token_type="access", role="user"):
    """Token as issued before sessions: no sid/uid/iat."""
    lifetime = timedelta(hours=1) if token_type == "access" else timedelta(days=3)
    payload = {"sub": email, "role": role, "type": token_type,
               "exp": datetime.utcnow() + lifetime}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _sessions(db, user_id):
    db.expire_all()
    return db.query(models.UserSession).filter(models.UserSession.user_id == user_id).all()


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------

class TestSessionCreation:

    def test_login_creates_session_and_sid_claims(self, client, db_session):
        user = _make_user(db_session)
        tokens = _login(client)
        access, refresh = _claims(tokens["access_token"]), _claims(tokens["refresh_token"])

        rows = _sessions(db_session, user.id)
        assert len(rows) == 1
        assert access["sid"] == refresh["sid"] == rows[0].id
        assert access["uid"] == refresh["uid"] == user.id
        assert "iat" in access and "iat" in refresh
        assert access["sub"] == user.email
        assert rows[0].user_agent == "TestAgent/1.0"

    def test_register_creates_session(self, client, db_session):
        resp = client.post("/users/register", json={
            "email": "new@test.com", "username": "newbie", "password": PASSWORD,
        })
        assert resp.status_code == 200, resp.text
        sid = _claims(resp.json()["access_token"])["sid"]
        user = db_session.query(models.User).filter_by(email="new@test.com").first()
        assert [r.id for r in _sessions(db_session, user.id)] == [sid]
        assert client.get("/users/me", headers=_bearer(resp.json()["access_token"])).status_code == 200

    def test_user_agent_truncated(self, client, db_session):
        user = _make_user(db_session)
        _login(client, ua="A" * 600)
        assert len(_sessions(db_session, user.id)[0].user_agent) == 255

    def test_login_purges_stale_sessions(self, client, db_session):
        user = _make_user(db_session)
        old = models.UserSession(
            id="a" * 32, user_id=user.id,
            created_at=datetime.utcnow() - timedelta(days=30),
            last_used_at=datetime.utcnow() - timedelta(days=8),
        )
        db_session.add(old)
        db_session.commit()
        _login(client)
        ids = [r.id for r in _sessions(db_session, user.id)]
        assert "a" * 32 not in ids and len(ids) == 1


# ---------------------------------------------------------------------------
# Session enforcement on /me and /refresh
# ---------------------------------------------------------------------------

class TestSessionEnforcement:

    def test_me_works_with_live_session(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        assert client.get("/users/me", headers=_bearer(tokens["access_token"])).status_code == 200

    def test_revoked_session_rejected_on_me_and_refresh(self, client, db_session):
        user = _make_user(db_session)
        tokens = _login(client)
        db_session.query(models.UserSession).filter_by(user_id=user.id).delete()
        db_session.commit()

        me = client.get("/users/me", headers=_bearer(tokens["access_token"]))
        assert me.status_code == 401
        assert me.json()["detail"] == SESSION_REVOKED_DETAIL

        ref = client.post("/users/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert ref.status_code == 401
        assert ref.json()["detail"] == REFRESH_401

    def test_sid_of_another_user_rejected(self, client, db_session):
        _make_user(db_session)
        other = _make_user(db_session, username="other", email="other@test.com")
        tokens = _login(client)
        # Move the session to another user: the token's sid no longer belongs to it.
        db_session.query(models.UserSession).update({models.UserSession.user_id: other.id})
        db_session.commit()
        assert client.get("/users/me", headers=_bearer(tokens["access_token"])).status_code == 401

    def test_refresh_keeps_sid_and_bumps_last_used(self, client, db_session):
        user = _make_user(db_session)
        tokens = _login(client)
        sid = _claims(tokens["access_token"])["sid"]
        past = datetime.utcnow() - timedelta(hours=2)
        db_session.query(models.UserSession).update({models.UserSession.last_used_at: past})
        db_session.commit()

        resp = client.post("/users/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 200
        assert _claims(resp.json()["access_token"])["sid"] == sid
        assert _claims(resp.json()["refresh_token"])["sid"] == sid
        assert _sessions(db_session, user.id)[0].last_used_at > past

    def test_last_used_at_throttled(self, client, db_session):
        user = _make_user(db_session)
        tokens = _login(client)
        recent = datetime.utcnow() - timedelta(minutes=1)
        db_session.query(models.UserSession).update({models.UserSession.last_used_at: recent})
        db_session.commit()
        client.get("/users/me", headers=_bearer(tokens["access_token"]))
        assert _sessions(db_session, user.id)[0].last_used_at == recent

        stale = datetime.utcnow() - timedelta(minutes=10)
        db_session.query(models.UserSession).update({models.UserSession.last_used_at: stale})
        db_session.commit()
        client.get("/users/me", headers=_bearer(tokens["access_token"]))
        assert _sessions(db_session, user.id)[0].last_used_at > stale

    def test_session_idle_past_refresh_lifetime_is_dead(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        db_session.query(models.UserSession).update(
            {models.UserSession.last_used_at: datetime.utcnow() - timedelta(days=8)})
        db_session.commit()
        assert client.get("/users/me", headers=_bearer(tokens["access_token"])).status_code == 401


# ---------------------------------------------------------------------------
# Legacy tokens (issued before sessions)
# ---------------------------------------------------------------------------

class TestLegacyTokens:

    def test_legacy_access_accepted_until_tokens_valid_after(self, client, db_session):
        user = _make_user(db_session)
        token = _legacy_token(user.email)
        assert client.get("/users/me", headers=_bearer(token)).status_code == 200

        db_session.query(models.User).filter_by(id=user.id).update(
            {models.User.tokens_valid_after: datetime.utcnow()})
        db_session.commit()
        resp = client.get("/users/me", headers=_bearer(token))
        assert resp.status_code == 401
        assert resp.json()["detail"] == SESSION_REVOKED_DETAIL

    def test_legacy_refresh_migrates_to_session(self, client, db_session):
        user = _make_user(db_session)
        resp = client.post("/users/refresh",
                           json={"refresh_token": _legacy_token(user.email, "refresh")},
                           headers={"User-Agent": "LegacyBrowser"})
        assert resp.status_code == 200
        sid = _claims(resp.json()["access_token"])["sid"]
        rows = _sessions(db_session, user.id)
        assert [r.id for r in rows] == [sid]
        assert rows[0].user_agent == "LegacyBrowser"
        assert client.get("/users/me", headers=_bearer(resp.json()["access_token"])).status_code == 200

    def test_legacy_refresh_rejected_after_tokens_valid_after(self, client, db_session):
        user = _make_user(db_session)
        db_session.query(models.User).filter_by(id=user.id).update(
            {models.User.tokens_valid_after: datetime.utcnow()})
        db_session.commit()
        resp = client.post("/users/refresh",
                           json={"refresh_token": _legacy_token(user.email, "refresh")})
        assert resp.status_code == 401
        assert _sessions(db_session, user.id) == []

    def test_optional_user_ignores_revoked_session(self, client, db_session):
        """get_optional_user applies the same session check (no identity leak)."""
        from main import get_optional_user
        user = _make_user(db_session)
        tokens = _login(client)
        assert get_optional_user(db_session, tokens["access_token"]).id == user.id
        db_session.query(models.UserSession).delete()
        db_session.commit()
        assert get_optional_user(db_session, tokens["access_token"]) is None


# ---------------------------------------------------------------------------
# Session list / revoke / logout
# ---------------------------------------------------------------------------

class TestSessionEndpoints:

    def test_list_marks_current_and_hides_other_users(self, client, db_session):
        user = _make_user(db_session)
        _make_user(db_session, username="other", email="other@test.com")
        first = _login(client, ua="Phone")
        second = _login(client, ua="Laptop")
        _login(client, identifier="other@test.com")

        resp = client.get("/users/me/sessions", headers=_bearer(second["access_token"]))
        assert resp.status_code == 200
        items = resp.json()["sessions"]
        assert len(items) == 2
        assert set(items[0].keys()) == {"id", "created_at", "last_used_at", "user_agent", "current"}
        current = [i for i in items if i["current"]]
        assert len(current) == 1
        assert current[0]["id"] == _claims(second["access_token"])["sid"]
        assert {i["user_agent"] for i in items} == {"Phone", "Laptop"}
        assert {i["id"] for i in items} == {r.id for r in _sessions(db_session, user.id)}

    def test_list_ordered_newest_used_first(self, client, db_session):
        _make_user(db_session)
        a = _login(client, ua="A")
        b = _login(client, ua="B")
        sid_a = _claims(a["access_token"])["sid"]
        db_session.query(models.UserSession).filter_by(id=sid_a).update(
            {models.UserSession.last_used_at: datetime.utcnow() + timedelta(minutes=1)})
        db_session.commit()
        items = client.get("/users/me/sessions", headers=_bearer(b["access_token"])).json()["sessions"]
        assert items[0]["id"] == sid_a

    def test_delete_other_session(self, client, db_session, kick_mock):
        user = _make_user(db_session)
        phone = _login(client)
        laptop = _login(client)
        phone_sid = _claims(phone["access_token"])["sid"]

        resp = client.delete(f"/users/me/sessions/{phone_sid}", headers=_bearer(laptop["access_token"]))
        assert resp.status_code == 200
        assert resp.json() == {"detail": "Сессия завершена"}
        assert client.get("/users/me", headers=_bearer(phone["access_token"])).status_code == 401
        assert client.get("/users/me", headers=_bearer(laptop["access_token"])).status_code == 200
        kick_mock.assert_called_once_with(user.id, session_ids=[phone_sid])

    def test_delete_foreign_or_missing_session_404(self, client, db_session, kick_mock):
        _make_user(db_session)
        _make_user(db_session, username="other", email="other@test.com")
        mine = _login(client)
        theirs = _login(client, identifier="other@test.com")
        their_sid = _claims(theirs["access_token"])["sid"]

        for sid in (their_sid, "nonexistent"):
            resp = client.delete(f"/users/me/sessions/{sid}", headers=_bearer(mine["access_token"]))
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Сессия не найдена"
        assert client.get("/users/me", headers=_bearer(theirs["access_token"])).status_code == 200
        kick_mock.assert_not_called()

    def test_delete_current_session_logs_out(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        sid = _claims(tokens["access_token"])["sid"]
        assert client.delete(f"/users/me/sessions/{sid}", headers=_bearer(tokens["access_token"])).status_code == 200
        assert client.get("/users/me", headers=_bearer(tokens["access_token"])).status_code == 401

    def test_revoke_others_keeps_current(self, client, db_session, kick_mock):
        user = _make_user(db_session)
        a = _login(client)
        b = _login(client)
        current = _login(client)
        legacy = _legacy_token(user.email)
        current_sid = _claims(current["access_token"])["sid"]

        resp = client.post("/users/me/sessions/revoke-others", headers=_bearer(current["access_token"]))
        assert resp.status_code == 200
        assert resp.json() == {"detail": "Остальные сеансы завершены", "revoked": 2}
        for tok in (a["access_token"], b["access_token"], legacy):
            assert client.get("/users/me", headers=_bearer(tok)).status_code == 401
        assert client.get("/users/me", headers=_bearer(current["access_token"])).status_code == 200
        assert client.post("/users/refresh", json={"refresh_token": current["refresh_token"]}).status_code == 200
        assert [r.id for r in _sessions(db_session, user.id)] == [current_sid]
        kick_mock.assert_called_once_with(user.id, all_except=current_sid)

    def test_logout_idempotent(self, client, db_session, kick_mock):
        user = _make_user(db_session)
        tokens = _login(client)
        sid = _claims(tokens["access_token"])["sid"]

        for _ in range(2):
            resp = client.post("/users/logout", json={"refresh_token": tokens["refresh_token"]})
            assert resp.status_code == 200
            assert resp.json() == {"detail": "Вы вышли из аккаунта"}
        assert _sessions(db_session, user.id) == []
        assert client.get("/users/me", headers=_bearer(tokens["access_token"])).status_code == 401
        kick_mock.assert_called_once_with(user.id, session_ids=[sid])

    def test_logout_only_touches_own_session(self, client, db_session):
        _make_user(db_session)
        a = _login(client)
        b = _login(client)
        client.post("/users/logout", json={"refresh_token": a["refresh_token"]})
        assert client.get("/users/me", headers=_bearer(b["access_token"])).status_code == 200

    def test_logout_garbage_token_401(self, client, db_session):
        resp = client.post("/users/logout", json={"refresh_token": "not-a-jwt"})
        assert resp.status_code == 401

    def test_logout_legacy_token_ok(self, client, db_session):
        user = _make_user(db_session)
        resp = client.post("/users/logout", json={"refresh_token": _legacy_token(user.email, "refresh")})
        assert resp.status_code == 200

    def test_sessions_require_auth(self, client, db_session):
        assert client.get("/users/me/sessions").status_code == 401
        assert client.post("/users/me/sessions/revoke-others").status_code == 401
        assert client.delete("/users/me/sessions/abc").status_code == 401


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

class TestPasswordChange:

    def _put(self, client, token, current, new):
        return client.put("/users/me/password", headers=_bearer(token),
                          json={"current_password": current, "new_password": new})

    def test_wrong_current(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        resp = self._put(client, tokens["access_token"], "wrong", "NewSecret1")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Неверный текущий пароль"

    def test_same_as_current(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        resp = self._put(client, tokens["access_token"], PASSWORD, PASSWORD)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Новый пароль совпадает с текущим"

    def test_too_short_and_too_long(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        resp = self._put(client, tokens["access_token"], PASSWORD, "123")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Пароль должен содержать минимум 6 символов"
        resp = self._put(client, tokens["access_token"], PASSWORD, "x" * 129)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Пароль слишком длинный"

    def test_success_kills_others_keeps_current(self, client, db_session, kick_mock):
        user = _make_user(db_session)
        other = _login(client)
        current = _login(client)
        legacy = _legacy_token(user.email)
        current_sid = _claims(current["access_token"])["sid"]

        resp = self._put(client, current["access_token"], PASSWORD, "NewSecret1")
        assert resp.status_code == 200
        assert resp.json() == {"detail": "Пароль изменён"}

        assert client.get("/users/me", headers=_bearer(current["access_token"])).status_code == 200
        assert client.get("/users/me", headers=_bearer(other["access_token"])).status_code == 401
        assert client.get("/users/me", headers=_bearer(legacy)).status_code == 401
        assert client.post("/users/refresh", json={"refresh_token": other["refresh_token"]}).status_code == 401
        kick_mock.assert_called_once_with(user.id, all_except=current_sid)

        assert client.post("/users/login", json={"identifier": user.email, "password": PASSWORD}).status_code == 401
        _login(client, password="NewSecret1")

    def test_requires_auth(self, client, db_session):
        resp = client.put("/users/me/password",
                          json={"current_password": PASSWORD, "new_password": "NewSecret1"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Email change
# ---------------------------------------------------------------------------

class TestEmailChange:

    def _put(self, client, token, new_email, password=PASSWORD):
        return client.put("/users/me/email", headers=_bearer(token),
                          json={"new_email": new_email, "password": password})

    def test_wrong_password(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        resp = self._put(client, tokens["access_token"], "fresh@test.com", "wrong")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Неверный пароль"

    def test_same_as_current_case_insensitive(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        resp = self._put(client, tokens["access_token"], "SEC@test.com")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Это ваша текущая почта"

    def test_taken_case_insensitive(self, client, db_session):
        _make_user(db_session)
        _make_user(db_session, username="other", email="other@test.com")
        tokens = _login(client)
        resp = self._put(client, tokens["access_token"], "Other@Test.com")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Эта почта уже занята"

    def test_invalid_email_422(self, client, db_session):
        _make_user(db_session)
        tokens = _login(client)
        assert self._put(client, tokens["access_token"], "not-an-email").status_code == 422

    def test_success_returns_working_tokens(self, client, db_session):
        user = _make_user(db_session)
        tokens = _login(client)
        sid = _claims(tokens["access_token"])["sid"]

        resp = self._put(client, tokens["access_token"], "fresh@test.com")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"access_token", "refresh_token", "token_type"}
        claims = _claims(data["access_token"])
        assert claims["sub"] == "fresh@test.com"
        assert claims["sid"] == sid

        me = client.get("/users/me", headers=_bearer(data["access_token"]))
        assert me.status_code == 200
        assert me.json()["email"] == "fresh@test.com"
        assert client.post("/users/refresh", json={"refresh_token": data["refresh_token"]}).status_code == 200

        assert client.post("/users/login",
                           json={"identifier": "sec@test.com", "password": PASSWORD}).status_code == 401
        _login(client, identifier="fresh@test.com")
        assert db_session.get(models.User, user.id).email == "fresh@test.com"


# ---------------------------------------------------------------------------
# notify_sessions_revoked (the real function, HTTP mocked)
# ---------------------------------------------------------------------------

class TestNotificationKick:

    def test_posts_internal_request(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "tok")
        monkeypatch.setenv("NOTIFICATION_SERVICE_URL", "http://notif:8007")
        with patch("sessions.httpx.post", return_value=MagicMock(status_code=200)) as post:
            _real_notify(7, session_ids=["abc"])
        post.assert_called_once()
        args, kwargs = post.call_args
        assert args[0] == "http://notif:8007/notifications/internal/sessions/revoked"
        assert kwargs["json"] == {"user_id": 7, "session_ids": ["abc"]}
        assert kwargs["headers"] == {"X-Internal-Token": "tok"}

        with patch("sessions.httpx.post", return_value=MagicMock(status_code=200)) as post:
            _real_notify(7, all_except="cur")
        assert post.call_args[1]["json"] == {"user_id": 7, "all_except": "cur"}

    def test_failure_is_swallowed(self):
        with patch("sessions.httpx.post", side_effect=httpx.ConnectError("down")) as post:
            _real_notify(7, session_ids=["abc"])  # no raise
        post.assert_called_once()
        with patch("sessions.httpx.post", return_value=MagicMock(status_code=500)):
            _real_notify(7, all_except="x")  # no raise

    def test_endpoint_survives_notification_outage(self, client, db_session):
        """Real kick function with notification-service down: request still 200."""
        _make_user(db_session)
        a = _login(client)
        b = _login(client)
        with patch("sessions.notify_sessions_revoked", wraps=_real_notify), \
                patch("sessions.httpx.post", side_effect=httpx.ConnectError("down")) as post:
            resp = client.post("/users/me/sessions/revoke-others", headers=_bearer(b["access_token"]))
        assert resp.status_code == 200
        post.assert_called_once()
        assert client.get("/users/me", headers=_bearer(a["access_token"])).status_code == 401



# ---------------------------------------------------------------------------
# Existing character endpoints keep working with session tokens
# ---------------------------------------------------------------------------

class TestCharacterEndpointsWithSessions:

    def test_owner_switches_character_and_lists(self, client, db_session):
        user = _make_user(db_session)
        db_session.add(models.UserCharacter(user_id=user.id, character_id=11))
        db_session.commit()
        tokens = _login(client)

        resp = client.put(f"/users/{user.id}/update_character",
                          json={"current_character": 11}, headers=_bearer(tokens["access_token"]))
        assert resp.status_code == 200
        assert resp.json()["current_character"] == 11

        short = {"id": 11, "name": "Герой", "avatar": None, "level": 1}
        with patch("main._fetch_character_short", return_value=short), \
                patch("main._fetch_character_post_stats", return_value={}):
            resp = client.get(f"/users/{user.id}/characters")
        assert resp.status_code == 200
        assert [c["id"] for c in resp.json()["characters"]] == [11]
