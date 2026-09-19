"""FEAT-171 review #1 — the user-service half of the fixes.

Three things are proved here, each as **absence of the key** for the wrong
viewer (a `null` would mean the value still travelled through the model):

* **§5 #2 — `GET /users/{id}` stopped returning `email` anonymously.** A real
  person's e-mail address was reachable with no token at all, on a route whose
  only cross-service callers read `username`. The owner and an
  admin/moderator holding `users:read` still get it. `GET /users/admins`
  answered the same fat schema, i.e. every administrator's address in one
  anonymous request — covered too.
* **§5 #4 — the inheritance direction.** The public schema is now the base and
  the private one extends it, in both pairs. The test asserts the *direction*,
  not just today's fields: an inverted pair would make a future private field
  leak by default, which is the whole point of the fix.
* **§5 #5 — U1's privilege rule matches `can_view_private`.** A moderator
  whose `characters:read` is revoked used to keep seeing gold here while
  getting 403 on `/characters/{id}/full_profile`.
"""

import pytest

import models
import schemas
from tests.test_feat171_profile_gold import (  # noqa: F401 — fixtures reused
    CHARACTER_ID,
    GOLD,
    _auth_header,
    _make_user,
    character_short,
    grant_role_permission,
    seed_permission,
)


# The keys a public user card must never carry.
PRIVATE_USER_KEYS = ("email", "password", "hashed_password", "password_hash",
                     "access_token", "refresh_token", "last_ip", "ip")


@pytest.fixture()
def people(db_session):
    """Five viewers around one target account."""
    target = _make_user(db_session, "target", "target@test.com")
    stranger = _make_user(db_session, "nosy", "nosy@test.com")
    admin = _make_user(db_session, "boss", "boss@test.com", role="admin")
    mod_ok = _make_user(db_session, "modok", "modok@test.com", role="moderator")
    mod_bare = _make_user(db_session, "modbare", "modbare@test.com",
                          role="moderator")

    users_read = seed_permission(db_session, "users", "read")
    seed_permission(db_session, "characters", "read")
    grant_role_permission(db_session, mod_ok, "moderator", users_read)
    # mod_bare shares the moderator role row but we revoke the permission
    # explicitly, mirroring the Reviewer's live "granted = 0" account.
    grant_role_permission(db_session, mod_bare, "moderator", None)
    db_session.add(models.UserPermission(
        user_id=mod_bare.id, permission_id=users_read.id, granted=False,
    ))
    db_session.commit()

    return {
        "target": target, "stranger": stranger, "admin": admin,
        "mod_ok": mod_ok, "mod_bare": mod_bare,
    }


# ===========================================================================
# §5 #2 — GET /users/{id} no longer hands out e-mail addresses
# ===========================================================================

class TestUserByIdHidesTheEmail:

    def test_a_guest_gets_no_email_key(self, client, people):
        r = client.get(f"/users/{people['target'].id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "email" not in body, (
            "GET /users/{id} still returns a real person's e-mail to an "
            "anonymous caller"
        )

    def test_another_player_gets_no_email_key(self, client, people):
        r = client.get(
            f"/users/{people['target'].id}",
            headers=_auth_header(people["stranger"]),
        )
        assert r.status_code == 200, r.text
        assert "email" not in r.json()

    @pytest.mark.parametrize("key", PRIVATE_USER_KEYS)
    def test_no_other_sensitive_key_travels_either(self, client, people, key):
        body = client.get(f"/users/{people['target'].id}").json()
        assert key not in body, f"public user card leaks {key!r}"

    def test_the_owner_still_sees_their_own_email(self, client, people):
        target = people["target"]
        r = client.get(f"/users/{target.id}", headers=_auth_header(target))
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "target@test.com"

    def test_an_admin_still_sees_the_email(self, client, people):
        r = client.get(
            f"/users/{people['target'].id}",
            headers=_auth_header(people["admin"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "target@test.com"

    def test_a_moderator_with_users_read_sees_the_email(self, client, people):
        r = client.get(
            f"/users/{people['target'].id}",
            headers=_auth_header(people["mod_ok"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "target@test.com"

    def test_a_moderator_without_users_read_does_not(self, client, people):
        r = client.get(
            f"/users/{people['target'].id}",
            headers=_auth_header(people["mod_bare"]),
        )
        assert r.status_code == 200, r.text
        assert "email" not in r.json()

    def test_the_assertions_are_not_vacuous(self, client, people):
        """`not in` proves nothing unless the key exists for the right
        viewer — here it does, on the very same route."""
        target = people["target"]
        owner_body = client.get(
            f"/users/{target.id}", headers=_auth_header(target)
        ).json()
        guest_body = client.get(f"/users/{target.id}").json()
        assert "email" in owner_body and "email" not in guest_body

    def test_the_public_card_still_carries_what_callers_need(
        self, client, people
    ):
        """character-service and locations-service read `username` from here
        with no token; breaking that would blank every author name."""
        body = client.get(f"/users/{people['target'].id}").json()
        assert body["username"] == "target"
        assert body["id"] == people["target"].id
        assert "avatar" in body and "registered_at" in body and "role" in body

    def test_a_missing_user_is_404_in_russian(self, client, people):
        r = client.get("/users/999999")
        assert r.status_code == 404
        assert r.json()["detail"] == "Пользователь не найден"


class TestAdminsListHidesEmails:
    """One anonymous request used to return every administrator's address."""

    def test_guest_listing_has_no_email(self, client, people):
        r = client.get("/users/admins")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows, "fixture must produce at least one admin"
        for row in rows:
            assert "email" not in row

    def test_the_consumer_still_gets_what_it_uses(self, client, people):
        """notification-service's `get_admins()` only reads `id`."""
        rows = client.get("/users/admins").json()
        assert all(isinstance(row["id"], int) for row in rows)


# ===========================================================================
# §5 #4 — public schema is the BASE, private extends it
# ===========================================================================

class TestSchemaInheritanceDirection:

    def test_user_read_extends_the_public_card(self):
        assert issubclass(schemas.UserRead, schemas.UserPublicRead)
        assert not issubclass(schemas.UserPublicRead, schemas.UserRead)

    def test_the_public_user_card_has_no_email_field(self):
        assert "email" not in schemas.UserPublicRead.__fields__
        assert "email" in schemas.UserRead.__fields__

    def test_profile_response_extends_the_stranger_shape(self):
        assert issubclass(
            schemas.UserProfileResponse, schemas.UserProfileStrangerResponse
        )
        assert not issubclass(
            schemas.UserProfileStrangerResponse, schemas.UserProfileResponse
        )

    def test_a_new_private_field_cannot_leak_by_inheritance(self):
        """The regression the inversion prevents: declare a private field on
        the fat model and the public one must stay clean."""
        class FatterProfile(schemas.UserProfileResponse):
            secret_note: str = "x"

        assert "secret_note" in FatterProfile.__fields__
        assert "secret_note" not in schemas.UserProfileStrangerResponse.__fields__

    def test_character_short_still_extends_the_public_card(self):
        """The same direction one level down — untouched, asserted anyway so
        the pair cannot be flipped back unnoticed."""
        assert issubclass(schemas.CharacterShort, schemas.CharacterShortPublic)
        assert "currency_balance" not in schemas.CharacterShortPublic.__fields__

    def test_a_character_short_instance_cannot_smuggle_gold(self):
        """Pydantic v1 keeps an instance of a subclass as-is. The handler
        therefore converts a model to a dict before building the stranger
        response; prove the conversion is what strips the key."""
        fat = schemas.CharacterShort(
            id=1, name="A", avatar="a.webp", currency_balance=999,
        )
        stranger = schemas.UserProfileStrangerResponse(
            id=1, username="u",
            post_stats=schemas.PostStatsResponse(total_posts=0),
            character=fat.dict(),
        )
        assert "currency_balance" not in stranger.dict()["character"]


# ===========================================================================
# §5 #5 — U1's gold rule now matches can_view_private
# ===========================================================================

class TestProfileGoldNeedsThePermission:

    @pytest.fixture()
    def owner_with_gold(self, db_session):
        owner = _make_user(
            db_session, "goldowner", "goldowner@test.com",
            current_character=CHARACTER_ID,
        )
        return owner

    def test_moderator_without_characters_read_sees_no_gold(
        self, client, db_session, people, owner_with_gold, character_short
    ):
        r = client.get(
            f"/users/{owner_with_gold.id}/profile",
            headers=_auth_header(people["mod_bare"]),
        )
        assert r.status_code == 200, r.text
        assert "currency_balance" not in r.json()["character"], (
            "a moderator whose characters:read is revoked gets 403 on "
            "/characters/{id}/full_profile — U1 must agree with it"
        )

    def test_moderator_with_characters_read_sees_gold(
        self, client, db_session, people, owner_with_gold, character_short
    ):
        perm = db_session.query(models.Permission).filter_by(
            module="characters", action="read"
        ).first()
        db_session.add(models.RolePermission(
            role_id=people["mod_ok"].role_id, permission_id=perm.id,
        ))
        db_session.commit()
        r = client.get(
            f"/users/{owner_with_gold.id}/profile",
            headers=_auth_header(people["mod_ok"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["character"]["currency_balance"] == GOLD

    def test_admin_still_sees_gold(
        self, client, people, owner_with_gold, character_short
    ):
        r = client.get(
            f"/users/{owner_with_gold.id}/profile",
            headers=_auth_header(people["admin"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["character"]["currency_balance"] == GOLD

    def test_the_owner_is_unaffected_by_the_permission_rule(
        self, client, people, owner_with_gold, character_short
    ):
        r = client.get(
            f"/users/{owner_with_gold.id}/profile",
            headers=_auth_header(owner_with_gold),
        )
        assert r.status_code == 200, r.text
        assert r.json()["character"]["currency_balance"] == GOLD
