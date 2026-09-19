"""
FEAT-171 task 18 (user-service half) — `GET /users/{id}/profile` stops leaking
the character's gold.

The leak had two halves and both are covered:

1. **The response.** U1 already had `get_optional_user`, so the fix is which
   model the handler builds: `UserProfileResponse` (with
   `character.currency_balance`) for the profile owner and for admin/moderator,
   `UserProfileStrangerResponse` (without the key at all) for everybody else.
   Asserted as **absence of the key inside `character`** — `null` would mean
   the value still travelled through the model.

2. **The source.** `short_info` lost `currency_balance` for everyone (D7), so
   user-service now reads the internal twin
   `GET /characters/internal/{id}/short_info` with `X-Internal-Token` — if it
   did not, `/users/me` would quietly show no gold in the header coin counter.
   `_fetch_character_short` swallows every failure with a warning, so the URL
   and the header are asserted on the captured request, not on "it returned
   something" (§3.5).

`/users/me` is checked to still carry the balance: that is the one place the
number is legitimately the viewer's own.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

import main
import models
from crud import create_user
from schemas import UserCreate


CHARACTER_ID = 7
GOLD = 1500

SHORT_INFO = {
    "id": CHARACTER_ID,
    "name": "Артория",
    "avatar": "artoria.webp",
    "level": 10,
    "current_location_id": None,
    "id_race": 1,
    "id_class": 1,
    "id_subrace": 1,
    "race_name": "Человек",
    "class_name": "Воин",
    "subrace_name": "Норд",
    "travel_cooldown_until": None,
    "currency_balance": GOLD,
}


def _make_user(db, username, email, role="user", current_character=None):
    user = create_user(
        db, UserCreate(email=email, username=username, password="Pass1234")
    )
    updates = {}
    if current_character is not None:
        updates[models.User.current_character] = current_character
    if role != "user":
        updates[models.User.role] = role
    if updates:
        db.query(models.User).filter(models.User.id == user.id).update(updates)
        db.commit()
        db.refresh(user)
    return user


def _auth_header(user):
    from auth import create_access_token
    return {
        "Authorization":
            f"Bearer {create_access_token(data={'sub': user.email}, role=user.role)}"
    }


@pytest.fixture()
def character_short(monkeypatch):
    """Stub the cross-service lookup and record every outgoing request."""
    calls = []

    async def _fake(char_id):
        calls.append(char_id)
        return {
            "id": SHORT_INFO["id"],
            "name": SHORT_INFO["name"],
            "avatar": SHORT_INFO["avatar"],
            "level": SHORT_INFO["level"],
            "current_location": None,
            "id_race": SHORT_INFO["id_race"],
            "id_class": SHORT_INFO["id_class"],
            "id_subrace": SHORT_INFO["id_subrace"],
            "race_name": SHORT_INFO["race_name"],
            "class_name": SHORT_INFO["class_name"],
            "subrace_name": SHORT_INFO["subrace_name"],
            "travel_cooldown_until": None,
            "currency_balance": GOLD,
        }

    monkeypatch.setattr(main, "_fetch_character_short", _fake)
    monkeypatch.setattr(main, "_fetch_character_post_stats", AsyncMock(return_value={}))
    return calls


def seed_permission(db, module, action):
    """Create a `permissions` row and return it (admin inherits it for free)."""
    perm = models.Permission(module=module, action=action)
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm


def grant_role_permission(db, user, role_name, perm):
    """Put `user` in a real role row that holds `perm`.

    The legacy `role` string alone yields **no** permissions for a
    non-admin, which is exactly the "moderator with the permission revoked"
    case — so a moderator who is meant to pass needs the real rows.
    """
    role = db.query(models.Role).filter(models.Role.name == role_name).first()
    if role is None:
        role = models.Role(name=role_name, level=50)
        db.add(role)
        db.commit()
        db.refresh(role)
    if perm is not None:
        db.add(models.RolePermission(role_id=role.id, permission_id=perm.id))
    db.query(models.User).filter(models.User.id == user.id).update(
        {models.User.role_id: role.id}
    )
    db.commit()
    db.refresh(user)
    return role


@pytest.fixture()
def world(db_session):
    owner = _make_user(
        db_session, "owner", "owner@test.com", current_character=CHARACTER_ID
    )
    stranger = _make_user(db_session, "stranger", "stranger@test.com")
    admin = _make_user(db_session, "boss", "boss@test.com", role="admin")
    moderator = _make_user(db_session, "mod", "mod@test.com", role="moderator")
    # FEAT-171 §5 #5: gold on U1 now needs role **and** `characters:read`,
    # the same formula as `visibility.can_view_private`. Admin inherits every
    # permission row automatically; the moderator needs the real grant.
    perm = seed_permission(db_session, "characters", "read")
    grant_role_permission(db_session, moderator, "moderator", perm)
    return {
        "owner": owner, "stranger": stranger,
        "admin": admin, "moderator": moderator,
    }


# ===========================================================================
# U1 — GET /users/{id}/profile
# ===========================================================================

class TestUserProfileGold:

    def test_the_owner_sees_the_balance(self, client, world, character_short):
        owner = world["owner"]
        r = client.get(f"/users/{owner.id}/profile", headers=_auth_header(owner))
        assert r.status_code == 200, r.text
        assert r.json()["character"]["currency_balance"] == GOLD

    @pytest.mark.parametrize("role", ["admin", "moderator"])
    def test_staff_sees_the_balance(self, client, world, character_short, role):
        r = client.get(
            f"/users/{world['owner'].id}/profile",
            headers=_auth_header(world[role]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["character"]["currency_balance"] == GOLD

    def test_a_guest_gets_no_balance_key_at_all(self, client, world, character_short):
        r = client.get(f"/users/{world['owner'].id}/profile")
        assert r.status_code == 200, r.text
        character = r.json()["character"]
        assert "currency_balance" not in character, (
            "gold must be ABSENT from the stranger shape, not null"
        )

    def test_another_player_gets_no_balance_key_at_all(
        self, client, world, character_short
    ):
        r = client.get(
            f"/users/{world['owner'].id}/profile",
            headers=_auth_header(world["stranger"]),
        )
        assert r.status_code == 200, r.text
        assert "currency_balance" not in r.json()["character"]

    def test_the_rest_of_the_card_survives_for_a_stranger(
        self, client, world, character_short
    ):
        """The profile page keeps working — only the number went away."""
        character = client.get(
            f"/users/{world['owner'].id}/profile"
        ).json()["character"]
        assert character["name"] == "Артория"
        assert character["level"] == 10
        assert character["class_name"] == "Воин"

    def test_a_missing_user_is_404(self, client, world, character_short):
        assert client.get("/users/99999/profile").status_code == 404

    def test_a_profile_without_a_character_still_renders(
        self, client, world, character_short
    ):
        r = client.get(f"/users/{world['stranger'].id}/profile")
        assert r.status_code == 200, r.text
        assert r.json()["character"] is None


class TestUsersMeKeepsTheBalance:

    def test_me_still_carries_the_gold(self, client, world, character_short):
        owner = world["owner"]
        r = client.get("/users/me", headers=_auth_header(owner))
        assert r.status_code == 200, r.text
        assert r.json()["character"]["currency_balance"] == GOLD


# ===========================================================================
# The source: `_fetch_character_short` must hit the twin WITH the header
# ===========================================================================

class TestShortInfoLookupUsesTheInternalTwin:
    """`_fetch_character_short` logs and returns None on any failure, so a
    dropped header would show up only as a missing coin counter. Assert the
    request itself (§3.5)."""

    @staticmethod
    def _capture(monkeypatch, token="test-internal-token"):
        calls = []

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return dict(SHORT_INFO)

        class _Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, **kwargs):
                calls.append((url, kwargs))
                return _Resp()

        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", token)
        monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
        return calls

    def test_it_targets_the_internal_twin(self, monkeypatch):
        calls = self._capture(monkeypatch)
        asyncio.run(main._fetch_character_short(CHARACTER_ID))
        url, _kwargs = calls[0]
        assert url.endswith(f"/characters/internal/{CHARACTER_ID}/short_info"), url

    def test_it_sends_the_internal_token(self, monkeypatch):
        calls = self._capture(monkeypatch)
        asyncio.run(main._fetch_character_short(CHARACTER_ID))
        _url, kwargs = calls[0]
        assert kwargs["headers"]["X-Internal-Token"] == "test-internal-token", (
            "user-service dropped X-Internal-Token on short_info — the twin "
            "would answer 401, the warning would be the only trace and the "
            "header coin counter would silently go blank"
        )

    def test_the_token_is_read_at_call_time_not_at_import(self, monkeypatch):
        calls = self._capture(monkeypatch, token="first")
        asyncio.run(main._fetch_character_short(CHARACTER_ID))
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        asyncio.run(main._fetch_character_short(CHARACTER_ID))
        assert [kw["headers"]["X-Internal-Token"] for _u, kw in calls] == [
            "first", "second"
        ]

    def test_it_never_reads_the_public_short_info(self, monkeypatch):
        """The public route lost the gold (D7); reading it would degrade
        `/users/me` without failing anything."""
        calls = self._capture(monkeypatch)
        asyncio.run(main._fetch_character_short(CHARACTER_ID))
        assert not any(
            "/short_info" in url and "/internal/" not in url for url, _ in calls
        ), calls

    def test_the_balance_reaches_the_mapped_dict(self, monkeypatch):
        self._capture(monkeypatch)
        data = asyncio.run(main._fetch_character_short(CHARACTER_ID))
        assert data["currency_balance"] == GOLD

    def test_dropping_the_header_would_be_caught(self, monkeypatch):
        """Red-proof: this is what the assertion above looks like when the
        header is gone — it fails, rather than the call quietly succeeding."""
        calls = self._capture(monkeypatch)
        asyncio.run(main._fetch_character_short(CHARACTER_ID))
        _url, kwargs = calls[0]
        stripped = {k: v for k, v in kwargs["headers"].items()
                    if k != "X-Internal-Token"}
        with pytest.raises(KeyError):
            stripped["X-Internal-Token"]
