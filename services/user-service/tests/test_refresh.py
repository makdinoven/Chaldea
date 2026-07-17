"""
FEAT-150 Task #5 — Tests for the reworked POST /users/refresh and the
token `type` claim enforcement (D2 rotation + D4 type confusion).

Covers:
(a) valid refresh token in JSON body → 200 with access_token / refresh_token /
    token_type=bearer; the new access token works on /users/me;
(b) rotation: the returned refresh token differs from the input and itself
    works again on /users/refresh (stateless sliding window);
(c) type confusion: access token sent to /users/refresh → 401,
    refresh token used as Bearer on /users/me → 401;
(d) legacy tokens WITHOUT the `type` claim (crafted via jose directly)
    accepted on both endpoints (backward compatibility);
(e) expired / garbage / wrong-secret / missing-sub / unknown-user token → 401;
(f) every failure mode returns the single generic Russian detail;
(g) refreshed access token carries type="access" and current_character
    re-read from the DB (present when set, absent when NULL);
(h) missing `refresh_token` field in body → 422.

NOTE on rotation asserts: tokens carry no iat/jti by design, so a token
minted and refreshed within the same second would be byte-identical.
Input tokens are therefore crafted with a non-default expires_delta so the
rotated token's `exp` (and thus its bytes) always differs.
"""

from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from jose import jwt

import models
from auth import (
    SECRET_KEY,
    ALGORITHM,
    create_access_token,
    create_refresh_token,
)
from crud import create_user
from schemas import UserCreate

GENERIC_401_DETAIL = "Недействительный или истёкший refresh-токен"
CHARACTER_ID = 42

# Non-default lifetime for input refresh tokens: guarantees the rotated
# token (default 7d exp) is byte-different even within the same second.
INPUT_REFRESH_DELTA = timedelta(days=3)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, username="refresher", email="refresher@test.com",
               password="Pass1234", current_character=None):
    """Create a user via CRUD; optionally set the active character id."""
    user = create_user(db, UserCreate(email=email, username=username, password=password))
    if current_character is not None:
        db.query(models.User).filter(models.User.id == user.id).update(
            {models.User.current_character: current_character}
        )
        db.commit()
        db.refresh(user)
    return user


def _refresh_token_for(user, expires_delta=INPUT_REFRESH_DELTA):
    """Build a valid refresh token like login does (sub + optional character)."""
    token_data = {"sub": user.email}
    if user.current_character is not None:
        token_data["current_character"] = user.current_character
    return create_refresh_token(data=token_data, role=user.role,
                                expires_delta=expires_delta)


def _legacy_token(email, role="user", lifetime=timedelta(hours=1)):
    """Craft a pre-FEAT-150 token via jose directly: NO `type` claim."""
    payload = {
        "sub": email,
        "role": role,
        "exp": datetime.utcnow() + lifetime,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _post_refresh(client, token):
    return client.post("/users/refresh", json={"refresh_token": token})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _assert_generic_401(resp):
    """Every failure mode must return the same generic Russian message."""
    assert resp.status_code == 401
    assert resp.json()["detail"] == GENERIC_401_DETAIL


# ---------------------------------------------------------------------------
# 1. Happy path + rotation (sliding window)
# ---------------------------------------------------------------------------

class TestRefreshHappyPath:

    def test_valid_refresh_returns_three_fields(self, client, db_session):
        """(a) 200 with access_token, refresh_token, token_type=bearer."""
        user = _make_user(db_session)
        resp = _post_refresh(client, _refresh_token_for(user))

        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"access_token", "refresh_token", "token_type"}
        assert data["token_type"] == "bearer"
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["access_token"] != data["refresh_token"]

    def test_refreshed_access_token_works_on_me(self, client, db_session):
        """(a) The new access token authenticates GET /users/me."""
        user = _make_user(db_session)
        resp = _post_refresh(client, _refresh_token_for(user))
        assert resp.status_code == 200
        access = resp.json()["access_token"]

        me = client.get("/users/me", headers=_bearer(access))
        assert me.status_code == 200
        assert me.json()["email"] == user.email

    def test_refresh_token_is_rotated(self, client, db_session):
        """(b) Response carries a NEW refresh token, different from the input."""
        user = _make_user(db_session)
        input_refresh = _refresh_token_for(user)  # non-default 3d lifetime
        resp = _post_refresh(client, input_refresh)

        assert resp.status_code == 200
        rotated = resp.json()["refresh_token"]
        assert rotated != input_refresh
        # Rotated token is a proper refresh token with the default (longer) exp
        old_payload = jwt.decode(input_refresh, SECRET_KEY, algorithms=[ALGORITHM])
        new_payload = jwt.decode(rotated, SECRET_KEY, algorithms=[ALGORITHM])
        assert new_payload["type"] == "refresh"
        assert new_payload["exp"] > old_payload["exp"]

    def test_rotated_refresh_token_works_again(self, client, db_session):
        """(b) Sliding window: the rotated refresh token itself refreshes OK."""
        user = _make_user(db_session)
        first = _post_refresh(client, _refresh_token_for(user))
        assert first.status_code == 200
        rotated = first.json()["refresh_token"]

        second = _post_refresh(client, rotated)
        assert second.status_code == 200
        data = second.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]
        assert data["refresh_token"]


# ---------------------------------------------------------------------------
# 2. Token type confusion (D4)
# ---------------------------------------------------------------------------

class TestTypeConfusion:

    def test_access_token_rejected_on_refresh(self, client, db_session):
        """(c) A typed ACCESS token must not pass /users/refresh."""
        user = _make_user(db_session)
        access = create_access_token(data={"sub": user.email}, role=user.role)
        _assert_generic_401(_post_refresh(client, access))

    def test_refresh_token_rejected_as_bearer_on_me(self, client, db_session):
        """(c) A typed REFRESH token must not authenticate /users/me."""
        user = _make_user(db_session)
        refresh = _refresh_token_for(user)
        resp = client.get("/users/me", headers=_bearer(refresh))
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Legacy tokens without `type` claim (backward compatibility)
# ---------------------------------------------------------------------------

class TestLegacyTokens:

    def test_legacy_token_accepted_on_refresh(self, client, db_session):
        """(d) Pre-deploy token (no `type`) still refreshes."""
        user = _make_user(db_session)
        legacy = _legacy_token(user.email, role=user.role)

        resp = _post_refresh(client, legacy)
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"]
        assert data["refresh_token"]
        # Newly issued tokens are typed even when the input was legacy
        assert jwt.decode(data["access_token"], SECRET_KEY,
                          algorithms=[ALGORITHM])["type"] == "access"
        assert jwt.decode(data["refresh_token"], SECRET_KEY,
                          algorithms=[ALGORITHM])["type"] == "refresh"

    def test_legacy_token_accepted_on_me(self, client, db_session):
        """(d) Pre-deploy token (no `type`) still works as Bearer on /users/me."""
        user = _make_user(db_session)
        legacy = _legacy_token(user.email, role=user.role)

        resp = client.get("/users/me", headers=_bearer(legacy))
        assert resp.status_code == 200
        assert resp.json()["email"] == user.email


# ---------------------------------------------------------------------------
# 4. Failure modes → generic Russian 401 (no oracle)
# ---------------------------------------------------------------------------

class TestRefreshFailures:

    def test_expired_refresh_token(self, client, db_session):
        """(e/f) Expired refresh token → 401 with the generic Russian detail."""
        user = _make_user(db_session)
        expired = _refresh_token_for(user, expires_delta=timedelta(minutes=-5))
        _assert_generic_401(_post_refresh(client, expired))

    def test_garbage_token(self, client, db_session):
        """(e/f) Malformed token string → 401, not 500."""
        _make_user(db_session)
        _assert_generic_401(_post_refresh(client, "not.a.jwt-at-all"))

    def test_empty_string_token(self, client, db_session):
        """(e/f) Empty string passes Pydantic (str) but fails jose decode → 401."""
        _make_user(db_session)
        _assert_generic_401(_post_refresh(client, ""))

    def test_token_signed_with_wrong_secret(self, client, db_session):
        """(e/f) Security: valid-looking token with a forged signature → 401."""
        user = _make_user(db_session)
        forged = jwt.encode(
            {
                "sub": user.email,
                "role": user.role,
                "type": "refresh",
                "exp": datetime.utcnow() + timedelta(days=7),
            },
            "attacker-guessed-secret",
            algorithm=ALGORITHM,
        )
        _assert_generic_401(_post_refresh(client, forged))

    def test_token_without_sub_claim(self, client, db_session):
        """(e/f) Validly signed refresh token missing `sub` → 401."""
        _make_user(db_session)
        no_sub = jwt.encode(
            {
                "role": "user",
                "type": "refresh",
                "exp": datetime.utcnow() + timedelta(days=7),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        _assert_generic_401(_post_refresh(client, no_sub))

    def test_token_for_unknown_user(self, client, db_session):
        """(e/f) Valid signature but the user no longer exists → 401."""
        _make_user(db_session)
        ghost = create_refresh_token(data={"sub": "deleted@test.com"}, role="user")
        _assert_generic_401(_post_refresh(client, ghost))

    def test_missing_body_field_is_422(self, client, db_session):
        """(h) Missing `refresh_token` key in JSON body → 422 (Pydantic)."""
        resp = client.post("/users/refresh", json={})
        assert resp.status_code == 422

    def test_no_body_at_all_is_422(self, client, db_session):
        """(h) No request body at all → 422, token is NOT read from query."""
        user = _make_user(db_session)
        token = _refresh_token_for(user)
        # Token in query string must be ignored (transport moved to JSON body)
        resp = client.post(f"/users/refresh?refresh_token={token}")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Claims of the refreshed access token (D3 + D4)
# ---------------------------------------------------------------------------

class TestRefreshedTokenClaims:

    def test_access_token_has_type_and_character_from_db(self, client, db_session):
        """(g) type=access + current_character re-read from DB."""
        user = _make_user(db_session, current_character=CHARACTER_ID)
        # Input refresh token deliberately crafted WITHOUT current_character —
        # the endpoint must re-read it from the DB, not copy it from the token.
        stale_refresh = create_refresh_token(
            data={"sub": user.email}, role=user.role,
            expires_delta=INPUT_REFRESH_DELTA,
        )

        resp = _post_refresh(client, stale_refresh)
        assert resp.status_code == 200
        data = resp.json()

        access_payload = jwt.decode(data["access_token"], SECRET_KEY,
                                    algorithms=[ALGORITHM])
        assert access_payload["type"] == "access"
        assert access_payload["sub"] == user.email
        assert access_payload["role"] == user.role
        assert access_payload["current_character"] == CHARACTER_ID
        # Rotated refresh token carries the same re-read claim
        refresh_payload = jwt.decode(data["refresh_token"], SECRET_KEY,
                                     algorithms=[ALGORITHM])
        assert refresh_payload["current_character"] == CHARACTER_ID

    def test_access_token_omits_character_when_null(self, client, db_session):
        """(g) current_character absent from claims when NULL in the DB."""
        user = _make_user(db_session)  # current_character is NULL
        resp = _post_refresh(client, _refresh_token_for(user))
        assert resp.status_code == 200

        access_payload = jwt.decode(resp.json()["access_token"], SECRET_KEY,
                                    algorithms=[ALGORITHM])
        assert "current_character" not in access_payload
        assert access_payload["type"] == "access"

    @patch("main._fetch_character_short", new_callable=AsyncMock)
    def test_refreshed_access_token_works_on_me_with_character(
            self, mock_fetch, client, db_session):
        """(a/g) End-to-end: refreshed token authenticates a user with a character."""
        mock_fetch.return_value = {
            "id": CHARACTER_ID,
            "name": "Артория",
            "avatar": "artoria.webp",
            "level": 10,
            "current_location": None,
        }
        user = _make_user(db_session, current_character=CHARACTER_ID)

        resp = _post_refresh(client, _refresh_token_for(user))
        assert resp.status_code == 200
        access = resp.json()["access_token"]

        me = client.get("/users/me", headers=_bearer(access))
        assert me.status_code == 200
        me_data = me.json()
        assert me_data["email"] == user.email
        assert me_data["current_character_id"] == CHARACTER_ID
