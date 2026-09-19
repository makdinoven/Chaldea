"""
FEAT-169 — the whole `/party/internal/` prefix is service-to-service only.

Until this feature both routes were reachable with nothing but a DB session:

    POST /party/internal/xp-bonus       — hands out passive XP to squadmates
    GET  /party/internal/active-members — reveals who is grouped with whom, where

The only protection was the gateway rule `location /party/internal/ { return 403; }`
— a single layer, and one that does nothing for anything already inside the
Docker network. Both now carry the fail-closed `verify_internal_token` from the
new leaf module `app/internal_auth.py` (FEAT-169 M1).

Matrix per route: no header / wrong header / empty header value / a player
Bearer JWT / header-name casing, plus the fail-closed case where
`INTERNAL_SERVICE_TOKEN` is empty (503, never 200) and the happy path.

`xp-bonus` is checked against its *effect* as well: a rejected call must award
no XP at all. A guard that answered 401 after already calling
`_award_passive_xp` would still fail here.

`verify_internal_token` reads a **module-level** constant captured at import,
so every test pins `internal_auth.INTERNAL_SERVICE_TOKEN` — setting the env var
after import has no effect (the trap documented in FEAT-162/167).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import crud
import internal_auth
import main
import models
from database import get_db

TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

# character_id -> character row stub (the `characters` table belongs to
# character-service; party-service reads it straight from the shared MySQL).
CHARS: dict = {}
# every (character_id, amount) passive-XP award the handler attempted
AWARDS: list = []


def _reg(char_id, user_id, loc=1):
    CHARS[char_id] = {
        "id": char_id, "user_id": user_id, "current_location_id": loc,
        "name": f"Char{char_id}", "avatar": None,
    }


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    models.Base.metadata.create_all(bind=_engine)
    monkeypatch.setattr(internal_auth, "INTERNAL_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(crud, "get_character_info", lambda db, cid: CHARS.get(cid))
    monkeypatch.setattr(
        crud, "get_characters_map",
        lambda db, ids: {cid: CHARS[cid] for cid in ids if cid in CHARS},
    )
    monkeypatch.setattr(crud, "get_attributes_map", lambda db, ids: {})
    monkeypatch.setattr(
        main, "_award_passive_xp", lambda cid, amt: AWARDS.append((cid, amt))
    )
    CHARS.clear()
    AWARDS.clear()
    yield
    main.app.dependency_overrides.clear()
    models.Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def client():
    def override_db():
        db = _TestSession()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_db
    yield TestClient(main.app, raise_server_exceptions=False)
    main.app.dependency_overrides.clear()


@pytest.fixture()
def party():
    """A squad of two co-located characters — the setup in which `xp-bonus`
    really pays out, so a missing guard would be visible as an award."""
    _reg(1, user_id=10, loc=1)
    _reg(2, user_id=20, loc=1)
    db = _TestSession()
    p = models.Party(name="Отряд", leader_character_id=1)
    db.add(p)
    db.flush()
    for cid, leader in ((1, True), (2, False)):
        db.add(models.PartyMember(
            party_id=p.id, character_id=cid, user_id=cid * 10,
            is_leader=leader, status=models.MemberStatus.accepted,
        ))
    db.commit()
    pid = p.id
    db.close()
    return pid


XP_BODY = {
    "character_id": 1, "base_xp": 100, "source": "combat",
    "location_id": 1, "participant_character_ids": [1],
}
MEMBERS_PARAMS = {"character_id": 1, "location_id": 1}


def _xp(client, headers=None):
    return client.post("/party/internal/xp-bonus", json=XP_BODY,
                       headers=headers or {})


def _members(client, headers=None):
    return client.get("/party/internal/active-members", params=MEMBERS_PARAMS,
                      headers=headers or {})


# Both routes, as callables taking (client, headers)
ROUTES = [("POST /party/internal/xp-bonus", _xp),
          ("GET /party/internal/active-members", _members)]
_ROUTE_IDS = [name for name, _ in ROUTES]


# ══════════════════════════════════════════════════════════════════════════════
# 1. Outsiders are rejected
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalRoutesRejectOutsiders:

    @pytest.mark.parametrize("name, call", ROUTES, ids=_ROUTE_IDS)
    def test_no_header_returns_401(self, client, party, name, call):
        response = call(client, None)
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"

    @pytest.mark.parametrize("name, call", ROUTES, ids=_ROUTE_IDS)
    def test_wrong_header_returns_401(self, client, party, name, call):
        response = call(client, WRONG_HEADERS)
        assert response.status_code == 401
        assert response.json()["detail"] == "Недействительный internal token"

    @pytest.mark.parametrize("name, call", ROUTES, ids=_ROUTE_IDS)
    def test_empty_header_value_returns_401(self, client, party, name, call):
        assert call(client, {"X-Internal-Token": ""}).status_code == 401

    @pytest.mark.parametrize("name, call", ROUTES, ids=_ROUTE_IDS)
    def test_player_bearer_token_is_not_accepted(self, client, party, name, call):
        """Neither route has a browser caller: a player JWT must not open them,
        and a player must not be able to read other squads' rosters."""
        assert call(client, {"Authorization": "Bearer player-jwt"}).status_code == 401

    @pytest.mark.parametrize("name, call", ROUTES, ids=_ROUTE_IDS)
    def test_header_name_is_case_insensitive_but_value_is_not(
        self, client, party, name, call
    ):
        assert call(client, {"x-internal-token": TOKEN}).status_code not in (401, 503)
        assert call(client, {"X-Internal-Token": TOKEN.upper()}).status_code == 401

    def test_rejected_xp_bonus_grants_no_xp(self, client, party):
        """The damage this hole did: anyone could pump passive XP into a whole
        squad by POSTing a body. Every rejected shape must leave AWARDS empty —
        a guard that runs after `_award_passive_xp` would fail here."""
        for headers in (None, WRONG_HEADERS, {"X-Internal-Token": ""},
                        {"Authorization": "Bearer player-jwt"}):
            response = _xp(client, headers)
            assert response.status_code == 401, response.text
        assert AWARDS == [], f"XP was awarded to a rejected caller: {AWARDS}"

    def test_rejected_active_members_leaks_no_roster(self, client, party):
        """The response body must carry no squad information at all."""
        body = _members(client, None).json()
        assert set(body) == {"detail"}
        assert "member_character_ids" not in body


# ══════════════════════════════════════════════════════════════════════════════
# 2. Fail-closed: an unconfigured service rejects everything with 503
# ══════════════════════════════════════════════════════════════════════════════


class TestFailClosedWithoutToken:

    @pytest.mark.parametrize("name, call", ROUTES, ids=_ROUTE_IDS)
    def test_empty_token_env_returns_503_and_never_200(
        self, client, party, monkeypatch, name, call
    ):
        monkeypatch.setattr(internal_auth, "INTERNAL_SERVICE_TOKEN", "")
        for headers in (None, GOOD_HEADERS, WRONG_HEADERS,
                        {"X-Internal-Token": ""}):
            response = call(client, headers)
            assert response.status_code == 503, response.text
            assert response.json()["detail"] == "Internal service token не настроен"
        assert AWARDS == [], "XP leaked out of an unconfigured service"


# ══════════════════════════════════════════════════════════════════════════════
# 3. The internal callers still work
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalRoutesAcceptTheToken:

    def test_xp_bonus_still_pays_the_squad(self, client, party):
        """battle-service, locations-service and party-service itself must keep
        working: the +10% self-bonus and the trickle to the co-located mate."""
        response = _xp(client, GOOD_HEADERS)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["applied"] is True
        assert data["self_bonus"] == 10
        assert set(AWARDS) == {(1, 10), (2, 10)}

    def test_active_members_still_returns_the_roster(self, client, party):
        response = _members(client, GOOD_HEADERS)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["leader_character_id"] == 1
        assert set(data["member_character_ids"]) == {1, 2}


# ══════════════════════════════════════════════════════════════════════════════
# 4. Route-table sweep — nobody may quietly un-gate the prefix
# ══════════════════════════════════════════════════════════════════════════════


class TestTheWholeInternalPrefixIsGated:

    def test_every_party_internal_route_requires_the_token(self):
        """Any future route under `/party/internal/` is internal by definition;
        adding one without the dependency fails here."""
        from fastapi.routing import APIRoute

        ungated = []
        seen = set()
        for route in main.app.routes:
            if not isinstance(route, APIRoute):
                continue
            if "/party/internal/" not in route.path:
                continue
            seen.add(route.path)
            names = {
                getattr(dep.call, "__name__", type(dep.call).__name__)
                for dep in route.dependant.dependencies
            }
            if "verify_internal_token" not in names:
                ungated.append(f"{sorted(route.methods)} {route.path}")

        assert seen >= {"/party/internal/xp-bonus",
                        "/party/internal/active-members"}, sorted(seen)
        assert not ungated, f"ungated internal route(s): {ungated}"
