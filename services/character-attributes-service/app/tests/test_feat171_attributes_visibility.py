"""
FEAT-171 task 16 — character-attributes-service: the five-viewer matrix on the
five player reads, plus the two internal twins.

Before this feature every one of these answered *anyone*, anonymously, through
the gateway:

| # | route | what it hands over |
|---|---|---|
| A1 | `GET /attributes/{id}`                    | hp/mana/energy/stamina, dodge, crit, damage, 13 `res_*` + 13 `vul_*`, both XP pools |
| A2 | `GET /attributes/{id}/perks`              | the whole perk tree with unlock status |
| A3 | `GET /attributes/{id}/cumulative_stats`   | kills, wins/losses, damage totals, gold earned/spent |
| A4 | `GET /attributes/{id}/passive_experience` | total passive XP |
| A5 | `GET /attributes/{id}/rest-status`        | regen eligibility + the satiety buff |

All five are now **style B** hard gates (§3.4): 403 for a stranger, 404 for a
missing id — and the 404 is checked *before* the ownership branch, because a
403-vs-404 difference is an existence oracle (§3.8).

The sibling services do not lose their data: they read the twins
`GET /attributes/internal/{id}` (A1i) and
`GET /attributes/internal/{id}/passive_experience` (A4i) with
`X-Internal-Token`, which are covered at the bottom including the fail-closed
503 an unconfigured secret must produce.

NPCs and mobs (`user_id IS NULL`) stay public per Q6 — the battle engine, the
bestiary and the NPC modal all depend on it — so the whole matrix is run
against an NPC as well.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


@event.listens_for(_test_engine, "connect")
def _register_greatest(dbapi_conn, connection_record):
    dbapi_conn.create_function("GREATEST", 2, lambda a, b: max(a, b))


_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402

database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import auth_http  # noqa: E402
import models  # noqa: E402
from auth_http import UserRead, get_optional_user  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402
from tests.regen_shared_tables import (  # noqa: E402
    add_character,
    create_shared_tables,
    drop_shared_tables,
)


TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": TOKEN}

OWNER_ID = 42
STRANGER_ID = 43

PLAYER_CHARACTER = 1
NPC_CHARACTER = 2
MISSING_CHARACTER = 99999


def _user(uid, role, permissions=()):
    return UserRead(id=uid, username=f"u{uid}", role=role, permissions=list(permissions))


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

# The five player reads closed by task 7, as `(label, path suffix)`.
GATED = [
    ("A1 attributes", ""),
    ("A2 perks", "/perks"),
    ("A3 cumulative_stats", "/cumulative_stats"),
    ("A4 passive_experience", "/passive_experience"),
    ("A5 rest-status", "/rest-status"),
]


def _path(character_id, suffix):
    return f"/attributes/{character_id}{suffix}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture(autouse=True)
def _no_outbound_calls():
    """`/perks` self-heals through `reconcile_perks`, which reads the C1i twin
    over HTTP. Keep it off the network — the header on that call is task 19's
    subject, not this file's.

    `perk_evaluator` imports httpx *inside* the function (to avoid an import
    cycle), so the patch has to land on the httpx module itself."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value.status_code = 500
        yield mock_get


@pytest.fixture(autouse=True)
def _tables():
    models.Base.metadata.create_all(bind=_test_engine)
    create_shared_tables(_test_engine)
    yield
    drop_shared_tables(_test_engine)
    models.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def db_session():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_attributes(db, character_id, **overrides):
    defaults = dict(
        character_id=character_id,
        current_health=80, max_health=100,
        current_mana=30, max_mana=50,
        current_energy=12, max_energy=20,
        current_stamina=9, max_stamina=15,
        strength=10, agility=10, intelligence=10, endurance=10,
        health=10, mana=7, energy=5, stamina=10, charisma=1, luck=1,
        damage=0, passive_experience=1500, active_experience=250,
    )
    defaults.update(overrides)
    attr = models.CharacterAttributes(**defaults)
    db.add(attr)
    db.commit()
    return attr


@pytest.fixture()
def world(db_session):
    _seed_attributes(db_session, PLAYER_CHARACTER)
    _seed_attributes(db_session, NPC_CHARACTER)
    add_character(db_session, PLAYER_CHARACTER, user_id=OWNER_ID)
    add_character(db_session, NPC_CHARACTER, is_npc=True, user_id=None)
    db_session.add(models.CharacterCumulativeStats(
        character_id=PLAYER_CHARACTER, total_gold_earned=10_000,
        total_gold_spent=2_500, pvp_wins=3,
    ))
    db_session.add(models.CharacterCumulativeStats(character_id=NPC_CHARACTER))
    db_session.commit()
    return db_session


@pytest.fixture()
def as_viewer(world):
    def _override_get_db():
        yield world

    app.dependency_overrides[get_db] = _override_get_db

    def _set(viewer):
        if viewer is None:
            app.dependency_overrides.pop(get_optional_user, None)
        else:
            app.dependency_overrides[get_optional_user] = lambda: viewer
        return TestClient(app)

    yield _set
    app.dependency_overrides.clear()


# ===========================================================================
# The matrix, run across all five gated reads
# ===========================================================================

class TestTheFiveGatedReads:

    @pytest.mark.parametrize("label,suffix", GATED)
    @pytest.mark.parametrize("name,viewer", REFUSED)
    def test_refused_viewers_get_403(self, as_viewer, label, suffix, name, viewer):
        r = as_viewer(viewer).get(_path(PLAYER_CHARACTER, suffix))
        assert r.status_code == 403, f"{label} / {name}: {r.text}"
        assert r.json()["detail"] == "Эти данные доступны только владельцу персонажа"

    @pytest.mark.parametrize("label,suffix", GATED)
    @pytest.mark.parametrize("name,viewer", ALLOWED)
    def test_privileged_viewers_get_200(self, as_viewer, label, suffix, name, viewer):
        r = as_viewer(viewer).get(_path(PLAYER_CHARACTER, suffix))
        assert r.status_code == 200, f"{label} / {name}: {r.text}"

    @pytest.mark.parametrize("label,suffix", GATED)
    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_an_npc_stays_public(self, as_viewer, label, suffix, name, viewer):
        """Q6: `user_id IS NULL` means the character has no private layer."""
        r = as_viewer(viewer).get(_path(NPC_CHARACTER, suffix))
        assert r.status_code == 200, f"{label} / {name}: {r.text}"

    @pytest.mark.parametrize("label,suffix", GATED)
    @pytest.mark.parametrize("name,viewer", EVERYONE)
    def test_missing_id_is_404_before_the_ownership_branch(
        self, as_viewer, label, suffix, name, viewer
    ):
        r = as_viewer(viewer).get(_path(MISSING_CHARACTER, suffix))
        assert r.status_code == 404, (
            f"{label} / {name}: got {r.status_code}; a 403 here would let an "
            "attacker enumerate character ids"
        )
        assert r.json()["detail"] == "Персонаж не найден"

    @pytest.mark.parametrize("label,suffix", GATED)
    def test_a_forged_bearer_token_is_not_the_owner(self, as_viewer, label, suffix):
        """`get_optional_user` swallows the 401 and yields None, so an
        unverifiable token must land on the refused branch."""
        app.dependency_overrides.pop(get_optional_user, None)
        r = as_viewer(GUEST).get(
            _path(PLAYER_CHARACTER, suffix),
            headers={"Authorization": "Bearer forged"},
        )
        assert r.status_code == 403, f"{label}: {r.text}"


# ===========================================================================
# The owner's bodies did not get thinner along the way
# ===========================================================================

class TestOwnerBodiesAreUnchanged:

    def test_attributes_still_carry_the_numbers(self, as_viewer):
        body = as_viewer(OWNER).get(_path(PLAYER_CHARACTER, "")).json()
        assert body["current_health"] == 80
        assert body["max_stamina"] == 15
        assert body["passive_experience"] == 1500
        assert body["active_experience"] == 250
        # The 26 resistance/vulnerability keys are the bulk of the leak.
        assert len([k for k in body if k.startswith(("res_", "vul_"))]) >= 20

    def test_cumulative_stats_still_carry_the_gold(self, as_viewer):
        body = as_viewer(OWNER).get(
            _path(PLAYER_CHARACTER, "/cumulative_stats")
        ).json()
        assert body["total_gold_earned"] == 10_000
        assert body["total_gold_spent"] == 2_500

    def test_passive_experience_body(self, as_viewer):
        body = as_viewer(OWNER).get(
            _path(PLAYER_CHARACTER, "/passive_experience")
        ).json()
        assert body == {"passive_experience": 1500}

    def test_perks_body_shape(self, as_viewer):
        body = as_viewer(OWNER).get(_path(PLAYER_CHARACTER, "/perks")).json()
        assert body["character_id"] == PLAYER_CHARACTER
        assert isinstance(body["perks"], list)

    def test_rest_status_body_shape(self, as_viewer):
        body = as_viewer(OWNER).get(_path(PLAYER_CHARACTER, "/rest-status")).json()
        assert body["character_id"] == PLAYER_CHARACTER
        assert "is_resting" in body


# ===========================================================================
# A2 keeps its write-on-GET (D8) — narrowed, not fixed, and that is deliberate
# ===========================================================================

class TestPerksStillReconcileOnGet:

    def test_the_gate_did_not_silently_remove_the_self_heal(self, as_viewer):
        """D8: converting this GET into a read-only one is a separate task and
        must not be smuggled in here. If `reconcile_perks` disappears, this
        test goes red and the ISSUES entry has to be revisited on purpose."""
        with patch("perk_evaluator.reconcile_perks") as reconcile:
            as_viewer(OWNER).get(_path(PLAYER_CHARACTER, "/perks"))
        reconcile.assert_called_once()

    def test_a_stranger_cannot_trigger_the_write(self, as_viewer):
        """The amplifier is now reachable only by authenticated owners/admins."""
        with patch("perk_evaluator.reconcile_perks") as reconcile:
            r = as_viewer(STRANGER).get(_path(PLAYER_CHARACTER, "/perks"))
        assert r.status_code == 403
        reconcile.assert_not_called()


# ===========================================================================
# The two internal twins
# ===========================================================================

INTERNAL_PATHS = [
    f"/attributes/internal/{PLAYER_CHARACTER}",
    f"/attributes/internal/{PLAYER_CHARACTER}/passive_experience",
]


class TestInternalTwins:

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_no_header_is_401(self, as_viewer, path):
        assert as_viewer(GUEST).get(path).status_code == 401

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_wrong_header_is_401(self, as_viewer, path):
        assert as_viewer(GUEST).get(
            path, headers={"X-Internal-Token": "nope"}
        ).status_code == 401

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_unconfigured_secret_fails_closed_with_503(
        self, as_viewer, path, monkeypatch
    ):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        assert as_viewer(GUEST).get(
            path, headers=INTERNAL_HEADERS
        ).status_code == 503

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_good_header_is_200(self, as_viewer, path):
        assert as_viewer(GUEST).get(path, headers=INTERNAL_HEADERS).status_code == 200

    @pytest.mark.parametrize("path", INTERNAL_PATHS)
    def test_an_admin_jwt_does_not_open_an_internal_route(self, as_viewer, path):
        r = as_viewer(ADMIN).get(path, headers={"Authorization": "Bearer x"})
        assert r.status_code == 401

    def test_the_twin_body_equals_the_owner_body(self, as_viewer):
        """§3.4 A1i: 'identical to A1 today'. If the twin ever forks, the
        battle engine and the profile start disagreeing about the same stats."""
        client = as_viewer(OWNER)
        owner = client.get(_path(PLAYER_CHARACTER, "")).json()
        twin = client.get(
            f"/attributes/internal/{PLAYER_CHARACTER}", headers=INTERNAL_HEADERS
        ).json()
        assert twin == owner

    def test_the_passive_experience_twin_body_equals_the_owner_body(self, as_viewer):
        client = as_viewer(OWNER)
        owner = client.get(_path(PLAYER_CHARACTER, "/passive_experience")).json()
        twin = client.get(
            f"/attributes/internal/{PLAYER_CHARACTER}/passive_experience",
            headers=INTERNAL_HEADERS,
        ).json()
        assert twin == owner

    def test_the_twins_serve_npcs_without_an_owner(self, as_viewer):
        r = as_viewer(GUEST).get(
            f"/attributes/internal/{NPC_CHARACTER}", headers=INTERNAL_HEADERS
        )
        assert r.status_code == 200

    def test_the_twins_404_a_missing_character(self, as_viewer):
        r = as_viewer(GUEST).get(
            f"/attributes/internal/{MISSING_CHARACTER}", headers=INTERNAL_HEADERS
        )
        assert r.status_code == 404


# ===========================================================================
# The admin surface was not disturbed (§3.4: /attributes/admin/* untouched)
# ===========================================================================

class TestAdminSurfaceUntouched:

    def test_the_admin_read_is_not_behind_the_new_gate(self, as_viewer):
        """It has its own RBAC dependency; the visibility predicate must not
        have been bolted onto it as well."""
        import main as main_module
        import inspect

        source = inspect.getsource(main_module.admin_update_attributes)
        assert "require_private_access" not in source
