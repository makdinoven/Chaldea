"""
FEAT-171 task 15 — character-service: the five-viewer matrix and the thinned
public shapes.

Five reads changed shape or gained a gate (§3.4):

| route | style | what a stranger must NOT receive |
|---|---|---|
| C1 `GET /{id}/full_profile`  | A | `currency_balance`, `stat_points`, `level_progress`, `attributes` |
| C3 `GET /{id}/public`        | A | `starting_attributes`, `starting_attributes_is_snapshot` |
| C4 `GET /{id}/short_info`    | D7 | `currency_balance` — removed for **everyone**, gold lives on the twin |
| C7 `GET /{id}/post-history`  | A | `xp_earned` |
| C8 `GET /{id}/logs`          | B | the whole route (403) |

Every "must not receive" below is asserted as **absence of the key**
(`assert "currency_balance" not in body`). §1 says the split has to happen in
the API response, not in the UI, and a `null` would mean the value still went
through the response model — one `response_model_exclude_none` away from
coming back. Two structural tests (`TestThePrivateKeysAreReallyAbsent`) prove
the assertions bite by showing the *owner* body does carry the same keys.

The 404-before-403 ordering is checked on every gated route: a 403 for an id
that does not exist would make the gate an existence oracle (§3.8).

NPCs (`user_id IS NULL`) are public per Q6 — the bestiary and the NPC modal
depend on it — so every route is also run against an NPC as a guest.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import auth_http
import database
import models
from database import Base
from main import app, get_db


TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": TOKEN}

OWNER_ID = 42
STRANGER_ID = 43

PLAYER_CHARACTER = 1
NPC_CHARACTER = 2
MISSING_CHARACTER = 99999

PASSIVE_EXPERIENCE = 1500
ATTRIBUTES_PAYLOAD = {
    "current_health": 80, "max_health": 100,
    "current_mana": 30, "max_mana": 50,
    "current_energy": 12, "max_energy": 20,
    "current_stamina": 9, "max_stamina": 15,
}

STARTING_PRESET = {
    "strength": 12, "agility": 14, "intelligence": 20, "endurance": 8,
    "health": 10, "mana": 12, "energy": 6, "stamina": 9,
    "charisma": 5, "luck": 4,
}
GRANTED_KIT = {
    "class_id": 1, "origin_id": 7, "resolved_from": "exact",
    "items": [{"item_id": 5, "quantity": 1}], "skills": [{"skill_id": 4}],
    "currency_amount": 100, "granted_at": "2026-09-06T11:00:00",
}

# A post long enough to have earned XP — otherwise `xp_earned` is 0 for both
# viewers and the "absent vs present" assertion would be indistinguishable.
LONG_POST = "<p>" + ("а" * 450) + "</p>"


def _user(uid, role, permissions=()):
    return auth_http.UserRead(
        id=uid, username=f"u{uid}", role=role, permissions=list(permissions)
    )


GUEST = None
OWNER = _user(OWNER_ID, "user")
STRANGER = _user(STRANGER_ID, "user")
ADMIN = _user(7, "admin", ["characters:read"])
MODERATOR = _user(8, "moderator", ["characters:read"])
MODERATOR_NO_PERM = _user(9, "moderator", [])

ALLOWED = [("owner", OWNER), ("admin", ADMIN), ("moderator", MODERATOR)]
REFUSED = [
    ("guest", GUEST),
    ("stranger", STRANGER),
    ("moderator_without_permission", MODERATOR_NO_PERM),
]
EVERYONE = REFUSED + ALLOWED

FULL_PROFILE_PRIVATE_KEYS = (
    "currency_balance", "stat_points", "level_progress", "attributes",
)
PASSPORT_PRIVATE_KEYS = ("starting_attributes", "starting_attributes_is_snapshot")


# ---------------------------------------------------------------------------
# Outbound stubs — the passport resolves a username over HTTP, and
# `_build_full_profile` reads the A4i / A1i twins.
# ---------------------------------------------------------------------------

def _response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "{}"
    resp.json.return_value = payload
    return resp


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture(autouse=True)
def attributes_stub(monkeypatch):
    """Answer the two internal twins `_build_full_profile` reads, and record
    every outgoing call so the header can be asserted (see task 19's file)."""
    calls = []

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            if url.endswith("/passive_experience"):
                return _response({"passive_experience": PASSIVE_EXPERIENCE})
            return _response(dict(ATTRIBUTES_PAYLOAD))

        async def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return _response({})

    import main as main_module
    monkeypatch.setattr(main_module.httpx, "AsyncClient", _Client)
    return calls


@pytest.fixture(autouse=True)
def username_stub():
    """`/public` resolves the owner's username from user-service."""
    with patch("main.httpx.get") as mock_get:
        mock_get.return_value = _response({"username": "Скиталец"})
        yield mock_get


@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    # `posts` / `Locations` live in locations-service; character-service reads
    # them with raw SQL on the shared DB, so create minimal copies here.
    session.execute(text(
        "CREATE TABLE IF NOT EXISTS posts ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL,"
        " location_id BIGINT NOT NULL, content TEXT,"
        " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    ))
    session.execute(text(
        "CREATE TABLE IF NOT EXISTS Locations ("
        " id BIGINT PRIMARY KEY, name VARCHAR(255) NOT NULL)"
    ))
    session.commit()
    try:
        yield session
    finally:
        session.execute(text("DROP TABLE IF EXISTS posts"))
        session.execute(text('DROP TABLE IF EXISTS "Locations"'))
        session.commit()
        session.close()
        Base.metadata.drop_all(bind=database.engine)


def _seed_character(db, character_id, user_id, **overrides):
    fields = dict(
        id=character_id, name=f"Герой{character_id}", id_race=2, id_subrace=4,
        id_class=1, biography="Био", personality="Характер",
        appearance="Внешность", background="Предыстория", sex="female", age=120,
        avatar="https://s3/a.webp", user_id=user_id, level=3,
        currency_balance=777, stat_points=5, origin_id=7,
        skitaltsy_since_year=1783, skitaltsy_since_segment=2,
        current_location_id=1183, granted_kit=dict(GRANTED_KIT),
        starting_attributes=dict(STARTING_PRESET),
        is_npc=user_id is None,
    )
    fields.update(overrides)
    char = models.Character(**fields)
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


@pytest.fixture
def world(db_session):
    _seed_character(db_session, PLAYER_CHARACTER, OWNER_ID)
    _seed_character(db_session, NPC_CHARACTER, None, npc_role="merchant")
    db_session.execute(
        text("INSERT INTO Locations (id, name) VALUES (1183, 'Цитадель')")
    )
    for cid in (PLAYER_CHARACTER, NPC_CHARACTER):
        db_session.execute(
            text("INSERT INTO posts (character_id, location_id, content) "
                 "VALUES (:c, 1183, :t)"),
            {"c": cid, "t": LONG_POST},
        )
    db_session.add(models.CharacterLog(
        character_id=PLAYER_CHARACTER, event_type="loot",
        description="Получено 500 золота", metadata_={"gold": 500},
    ))
    db_session.add(models.CharacterLog(
        character_id=NPC_CHARACTER, event_type="spawn", description="Появился",
    ))
    db_session.commit()
    return db_session


@pytest.fixture
def as_viewer(world):
    """Factory: a TestClient whose `get_optional_user` yields `viewer`."""
    def override_get_db():
        yield world

    app.dependency_overrides[get_db] = override_get_db

    def _set(viewer):
        if viewer is None:
            app.dependency_overrides.pop(auth_http.get_optional_user, None)
        else:
            app.dependency_overrides[auth_http.get_optional_user] = lambda: viewer
        return TestClient(app)

    yield _set
    app.dependency_overrides.clear()


# ===========================================================================
# C1 — GET /characters/{id}/full_profile
# ===========================================================================

class TestFullProfile:

    @pytest.mark.parametrize("name,viewer", ALLOWED)
    def test_privileged_viewers_get_the_unchanged_body(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/full_profile")
        assert r.status_code == 200, f"{name}: {r.text}"
        body = r.json()
        assert body["currency_balance"] == 777
        assert body["stat_points"] == 5
        assert set(body["level_progress"]) == {
            "current_exp_in_level", "exp_to_next_level", "progress_fraction"
        }
        assert set(body["attributes"]) == {"health", "mana", "energy", "stamina"}
        assert body["attributes"]["health"] == {"current": 80, "max": 100}

    @pytest.mark.parametrize("name,viewer", REFUSED)
    @pytest.mark.parametrize("key", FULL_PROFILE_PRIVATE_KEYS)
    def test_private_keys_are_absent_for_a_stranger(
        self, as_viewer, name, viewer, key
    ):
        r = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/full_profile")
        assert r.status_code == 200, f"{name}: {r.text}"
        assert key not in r.json(), (
            f"{key} reached {name} — it must be ABSENT from the JSON, not null"
        )

    @pytest.mark.parametrize("name,viewer", REFUSED)
    def test_the_showcase_keys_survive(self, as_viewer, name, viewer):
        """A thinner 200, not a 403 — a 403 here fires the red toast in
        `axiosSetup.ts` on a page a guest may legitimately open (§2.10)."""
        body = as_viewer(viewer).get(
            f"/characters/{PLAYER_CHARACTER}/full_profile"
        ).json()
        assert set(body) == {
            "id", "name", "level", "active_title", "active_title_rarity", "avatar"
        }
        assert body["name"] == "Герой1"
        assert body["level"] >= 3

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_an_npc_profile_stays_full_for_everyone(self, as_viewer, name, viewer):
        body = as_viewer(viewer).get(
            f"/characters/{NPC_CHARACTER}/full_profile"
        ).json()
        assert "currency_balance" in body, f"{name}: NPC lost its public numbers"

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_missing_id_is_404_before_the_ownership_branch(
        self, as_viewer, name, viewer
    ):
        r = as_viewer(viewer).get(f"/characters/{MISSING_CHARACTER}/full_profile")
        assert r.status_code == 404, f"{name}: {r.text}"
        assert r.json()["detail"] == "Персонаж не найден"


# ===========================================================================
# C3 — GET /characters/{id}/public
# ===========================================================================

class TestPassport:

    @pytest.mark.parametrize("name,viewer", ALLOWED)
    def test_privileged_viewers_still_see_the_starting_attributes(
        self, as_viewer, name, viewer
    ):
        body = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/public").json()
        assert body["starting_attributes"] == STARTING_PRESET
        assert body["starting_attributes_is_snapshot"] is True

    @pytest.mark.parametrize("name,viewer", REFUSED)
    @pytest.mark.parametrize("key", PASSPORT_PRIVATE_KEYS)
    def test_starting_attributes_are_absent_for_a_stranger(
        self, as_viewer, name, viewer, key
    ):
        r = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/public")
        assert r.status_code == 200, f"{name}: {r.text}"
        assert key not in r.json(), f"{key} reached {name}"

    @pytest.mark.parametrize("name,viewer", REFUSED)
    def test_the_rest_of_the_passport_is_untouched(self, as_viewer, name, viewer):
        """§1: the character is a showcase. Only the numbers went away."""
        body = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/public").json()
        assert body["name"] == "Герой1"
        assert body["level"] == 3
        assert body["race_name"] == "Эльф"
        assert body["biography"] == "Био"
        assert body["origin_id"] == 7
        assert body["skitaltsy_since_year"] == 1783

    @pytest.mark.parametrize("name,viewer", REFUSED)
    def test_granted_kit_stays_public(self, as_viewer, name, viewer):
        """§3.4 C3 / D4: the kit is a record of joining, not a stat block."""
        body = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/public").json()
        assert body["granted_kit"] is not None
        assert body["granted_kit"]["items"] == [{"item_id": 5, "quantity": 1}]
        assert body["granted_kit_is_snapshot"] is True

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_an_npc_passport_keeps_its_numbers(self, as_viewer, name, viewer):
        body = as_viewer(viewer).get(f"/characters/{NPC_CHARACTER}/public").json()
        assert body["starting_attributes"] == STARTING_PRESET, name

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_missing_id_is_404(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{MISSING_CHARACTER}/public")
        assert r.status_code == 404, f"{name}: {r.text}"


# ===========================================================================
# C4 — GET /characters/{id}/short_info (D7: gold leaves for EVERYONE)
# ===========================================================================

class TestShortInfo:

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_never_carries_gold(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/short_info")
        assert r.status_code == 200, f"{name}: {r.text}"
        assert "currency_balance" not in r.json(), (
            f"{name}: short_info is a service-to-service route; gold belongs "
            "to the internal twin only (D7)"
        )

    def test_the_owner_does_not_get_gold_here_either(self, as_viewer):
        """D7 is deliberately a hard field removal, not optional auth: making
        it viewer-dependent would silently thin `/users/me`."""
        body = as_viewer(OWNER).get(
            f"/characters/{PLAYER_CHARACTER}/short_info"
        ).json()
        assert "currency_balance" not in body

    def test_the_rest_of_the_card_is_intact(self, as_viewer):
        body = as_viewer(GUEST).get(
            f"/characters/{PLAYER_CHARACTER}/short_info"
        ).json()
        assert body["name"] == "Герой1"
        assert body["level"] == 3
        assert body["race_name"] == "Эльф"
        assert body["class_name"] == "Воин"
        assert body["is_npc"] is False

    def test_the_internal_twin_still_carries_gold(self, as_viewer):
        body = as_viewer(GUEST).get(
            f"/characters/internal/{PLAYER_CHARACTER}/short_info",
            headers=INTERNAL_HEADERS,
        ).json()
        assert body["currency_balance"] == 777

    def test_the_twin_and_the_public_body_differ_by_exactly_that_one_key(
        self, as_viewer
    ):
        client = as_viewer(GUEST)
        public = client.get(f"/characters/{PLAYER_CHARACTER}/short_info").json()
        internal = client.get(
            f"/characters/internal/{PLAYER_CHARACTER}/short_info",
            headers=INTERNAL_HEADERS,
        ).json()
        assert set(internal) - set(public) == {"currency_balance"}
        assert set(public) - set(internal) == set()


# ===========================================================================
# C7 — GET /characters/{id}/post-history
# ===========================================================================

class TestPostHistory:

    @pytest.mark.parametrize("name,viewer", ALLOWED)
    def test_privileged_viewers_see_the_xp(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/post-history")
        assert r.status_code == 200, f"{name}: {r.text}"
        post = r.json()["posts"][0]
        assert post["xp_earned"] > 0, "the fixture post must earn XP"

    @pytest.mark.parametrize("name,viewer", REFUSED)
    def test_xp_earned_is_absent_for_a_stranger(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/post-history")
        assert r.status_code == 200, f"{name}: {r.text}"
        post = r.json()["posts"][0]
        assert "xp_earned" not in post, f"{name}: xp_earned must be ABSENT"
        # The history itself stays public (§1).
        assert post["content"] == LONG_POST
        assert post["location_name"] == "Цитадель"
        assert post["char_count"] == 450

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_an_npc_history_keeps_xp(self, as_viewer, name, viewer):
        posts = as_viewer(viewer).get(
            f"/characters/{NPC_CHARACTER}/post-history"
        ).json()["posts"]
        assert "xp_earned" in posts[0], name

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_missing_id_is_404(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{MISSING_CHARACTER}/post-history")
        assert r.status_code == 404, f"{name}: {r.text}"
        assert r.json()["detail"] == "Персонаж не найден"


# ===========================================================================
# C8 — GET /characters/{id}/logs (hard gate)
# ===========================================================================

class TestCharacterLogs:

    @pytest.mark.parametrize("name,viewer", REFUSED)
    def test_strangers_get_403(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/logs")
        assert r.status_code == 403, f"{name}: {r.text}"
        assert r.json()["detail"] == "Эти данные доступны только владельцу персонажа"

    @pytest.mark.parametrize("name,viewer", ALLOWED)
    def test_privileged_viewers_read_the_log(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{PLAYER_CHARACTER}/logs")
        assert r.status_code == 200, f"{name}: {r.text}"
        assert r.json()["total"] == 1
        # Q4a: the free-form metadata is exactly why this route closed.
        assert r.json()["logs"][0]["metadata"] == {"gold": 500}

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_an_npc_log_is_public(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{NPC_CHARACTER}/logs")
        assert r.status_code == 200, f"{name}: {r.text}"

    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_missing_id_is_404_not_403(self, as_viewer, name, viewer):
        r = as_viewer(viewer).get(f"/characters/{MISSING_CHARACTER}/logs")
        assert r.status_code == 404, f"{name}: {r.text}"


# ===========================================================================
# The two internal twins
# ===========================================================================

INTERNAL_PATHS = [
    f"/characters/internal/{PLAYER_CHARACTER}/full_profile",
    f"/characters/internal/{PLAYER_CHARACTER}/short_info",
]


class TestInternalTwins:

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_no_header_is_401(self, as_viewer, path):
        assert as_viewer(GUEST).get(path).status_code == 401

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_wrong_header_is_401(self, as_viewer, path):
        r = as_viewer(GUEST).get(path, headers={"X-Internal-Token": "nope"})
        assert r.status_code == 401

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_unconfigured_secret_fails_closed_with_503(
        self, as_viewer, path, monkeypatch
    ):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        assert as_viewer(GUEST).get(
            path, headers=INTERNAL_HEADERS
        ).status_code == 503

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_a_jwt_does_not_open_an_internal_route(self, as_viewer, path):
        """The twins take the header, never the Bearer position."""
        r = as_viewer(ADMIN).get(path, headers={"Authorization": "Bearer x"})
        assert r.status_code == 401

    def test_the_full_profile_twin_is_the_owners_body(self, as_viewer):
        client = as_viewer(OWNER)
        owner = client.get(f"/characters/{PLAYER_CHARACTER}/full_profile").json()
        twin = client.get(
            f"/characters/internal/{PLAYER_CHARACTER}/full_profile",
            headers=INTERNAL_HEADERS,
        ).json()
        # The public route adds `id` for the stranger shape only; the twin is
        # the pre-FEAT-171 body, so compare on the shared keys.
        for key in FULL_PROFILE_PRIVATE_KEYS:
            assert twin[key] == owner[key]
        assert twin["name"] == owner["name"]


# ===========================================================================
# The assertions must bite — proof the private keys are really conditional
# ===========================================================================

class TestThePrivateKeysAreReallyAbsent:
    """A `not in` assertion passes trivially if the key never existed. These
    pair each absence with the presence it is contrasted against, so a handler
    that stopped returning the field to *anyone* also goes red."""

    def test_full_profile_keys_exist_for_the_owner(self, as_viewer):
        body = as_viewer(OWNER).get(
            f"/characters/{PLAYER_CHARACTER}/full_profile"
        ).json()
        for key in FULL_PROFILE_PRIVATE_KEYS:
            assert key in body, key

    def test_passport_keys_exist_for_the_owner(self, as_viewer):
        body = as_viewer(OWNER).get(f"/characters/{PLAYER_CHARACTER}/public").json()
        for key in PASSPORT_PRIVATE_KEYS:
            assert key in body, key

    def test_xp_earned_exists_for_the_owner(self, as_viewer):
        posts = as_viewer(OWNER).get(
            f"/characters/{PLAYER_CHARACTER}/post-history"
        ).json()["posts"]
        assert "xp_earned" in posts[0]

    def test_gold_exists_on_the_twin(self, as_viewer):
        body = as_viewer(GUEST).get(
            f"/characters/internal/{PLAYER_CHARACTER}/short_info",
            headers=INTERNAL_HEADERS,
        ).json()
        assert "currency_balance" in body


# ===========================================================================
# Security
# ===========================================================================

class TestGateSecurity:

    def test_a_forged_bearer_token_lands_on_the_stranger_branch(self, as_viewer):
        """`get_optional_user` swallows the 401 from user-service and returns
        None, so an unverifiable token must never be treated as the owner."""
        app.dependency_overrides.pop(auth_http.get_optional_user, None)
        client = as_viewer(GUEST)
        r = client.get(
            f"/characters/{PLAYER_CHARACTER}/logs",
            headers={"Authorization": "Bearer forged"},
        )
        assert r.status_code == 403, r.text

    @pytest.mark.parametrize(
        "raw", ["1 OR 1=1", "1;DROP TABLE characters--", "%27"]
    )
    def test_injection_in_the_path_never_500s(self, as_viewer, raw):
        r = as_viewer(GUEST).get(f"/characters/{raw}/logs")
        assert r.status_code in (403, 404, 422), (raw, r.status_code)
