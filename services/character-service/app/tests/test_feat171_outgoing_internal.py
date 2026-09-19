"""
FEAT-171 task 19 (character-service) — `full_profile` reads two attribute
routes, and both moved onto the internal twins.

`_build_full_profile` is the body shared by `GET /characters/{id}/full_profile`
and its own twin `GET /characters/internal/{id}/full_profile`. It makes two
outgoing reads, and Pass A repointed both:

| read | was | now |
|---|---|---|
| passive XP | `GET /attributes/{id}/passive_experience` | `/attributes/internal/{id}/passive_experience` (A4i) |
| attributes | `GET /attributes/{id}`                    | `/attributes/internal/{id}` (A1i)                    |

Unlike the dungeon and location callers these two are **not** silent: a non-200
becomes a 404 and the profile fails to render. That is loud, but it is loud in
a way that points at the wrong thing — the player sees «Passive experience not
found», not «the token is wrong» — so the header is asserted on the recorded
request rather than inferred from a green profile.

The third outgoing call in the same handler, `POST .../reconcile-perks`, is
already covered by `test_xp_multiplier_call_shape.py::TestReconcilePerksAfterLevelUp`
(that one *is* swallowed with a warning).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import auth_http
import database
import models
from database import Base
from main import app, get_db


TOKEN = "test-internal-token"
CHARACTER_ID = 1
PASSIVE_EXPERIENCE = 1500
ATTRIBUTES = {
    "current_health": 80, "max_health": 100,
    "current_mana": 30, "max_mana": 50,
    "current_energy": 12, "max_energy": 20,
    "current_stamina": 9, "max_stamina": 15,
}


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.text = "{}"
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _patch(monkeypatch, passive_status=200, attributes_status=200):
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
                return _Resp(passive_status, {"passive_experience": PASSIVE_EXPERIENCE})
            return _Resp(attributes_status, dict(ATTRIBUTES))

        async def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return _Resp(200, {})

    import main as main_module
    monkeypatch.setattr(main_module.httpx, "AsyncClient", _Client)
    return calls


@pytest.fixture(autouse=True)
def token(monkeypatch):
    """`crud._internal_token_headers` reads `auth_http.INTERNAL_SERVICE_TOKEN`
    at call time — pin the constant, not the env var."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


@pytest.fixture()
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    session.add(models.Character(
        id=CHARACTER_ID, name="Герой", id_race=1, id_subrace=1, id_class=1,
        user_id=42, level=3, currency_balance=100, stat_points=0,
        appearance="a", biography="b", personality="p", sex="male",
        avatar="https://s3/a.webp",
    ))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture()
def owner_client(db_session):
    from fastapi.testclient import TestClient

    def override_get_db():
        yield db_session

    owner = auth_http.UserRead(id=42, username="owner", role="user", permissions=[])
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth_http.get_optional_user] = lambda: owner
    yield TestClient(app)
    app.dependency_overrides.clear()


def _reads(calls):
    return [(url, kwargs) for verb, url, kwargs in calls if verb == "GET"]


# ═══════════════════════════════════════════════════════════════════════════
# A4i — the passive-experience read
# ═══════════════════════════════════════════════════════════════════════════

class TestPassiveExperienceRead:

    def test_targets_the_internal_twin(self, monkeypatch, owner_client):
        calls = _patch(monkeypatch)
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        urls = [u for u, _ in _reads(calls) if u.endswith("/passive_experience")]
        assert urls, "full_profile never read the passive experience"
        for url in urls:
            assert f"/attributes/internal/{CHARACTER_ID}/passive_experience" in url, url

    def test_sends_the_internal_token(self, monkeypatch, owner_client):
        calls = _patch(monkeypatch)
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        _url, kwargs = next(
            c for c in _reads(calls) if c[0].endswith("/passive_experience")
        )
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN

    def test_a_401_becomes_a_404_that_blames_the_data_not_the_token(
        self, monkeypatch, owner_client
    ):
        """Loud, but misleading — which is why the header itself is pinned."""
        _patch(monkeypatch, passive_status=401)
        r = owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        assert r.status_code == 404
        assert "token" not in r.text.lower()


# ═══════════════════════════════════════════════════════════════════════════
# A1i — the attributes read
# ═══════════════════════════════════════════════════════════════════════════

class TestAttributesRead:

    def test_targets_the_internal_twin(self, monkeypatch, owner_client):
        calls = _patch(monkeypatch)
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        urls = [
            u for u, _ in _reads(calls)
            if "/attributes/" in u and not u.endswith("/passive_experience")
        ]
        assert urls, "full_profile never read the attributes"
        for url in urls:
            assert url.endswith(f"/attributes/internal/{CHARACTER_ID}"), url

    def test_sends_the_internal_token(self, monkeypatch, owner_client):
        calls = _patch(monkeypatch)
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        _url, kwargs = next(
            c for c in _reads(calls)
            if "/attributes/" in c[0] and not c[0].endswith("/passive_experience")
        )
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN


# ═══════════════════════════════════════════════════════════════════════════
# Both reads together
# ═══════════════════════════════════════════════════════════════════════════

class TestBothReads:

    def test_every_outgoing_read_carries_the_header(self, monkeypatch, owner_client):
        calls = _patch(monkeypatch)
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        reads = _reads(calls)
        assert len(reads) >= 2, reads
        for url, kwargs in reads:
            assert kwargs["headers"]["X-Internal-Token"] == TOKEN, url

    def test_no_read_goes_to_a_player_facing_attributes_route(
        self, monkeypatch, owner_client
    ):
        """A1 and A4 are owner-only now, and character-service holds no user
        token here — the public path would 403 every profile load."""
        calls = _patch(monkeypatch)
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        for url, _ in _reads(calls):
            assert "/attributes/internal/" in url, f"anonymous path survived: {url}"

    def test_the_internal_twin_of_full_profile_uses_the_same_reads(
        self, monkeypatch, owner_client
    ):
        """C1i shares `_build_full_profile`, so it must not have forked into a
        second, header-less implementation."""
        calls = _patch(monkeypatch)
        r = owner_client.get(
            f"/characters/internal/{CHARACTER_ID}/full_profile",
            headers={"X-Internal-Token": TOKEN},
        )
        assert r.status_code == 200, r.text
        for url, kwargs in _reads(calls):
            assert "/attributes/internal/" in url
            assert kwargs["headers"]["X-Internal-Token"] == TOKEN

    def test_the_token_is_read_at_call_time(self, monkeypatch, owner_client):
        calls = _patch(monkeypatch)
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "first")
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "second")
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        sent = {kw["headers"]["X-Internal-Token"] for _u, kw in _reads(calls)}
        assert sent == {"first", "second"}, sent

    def test_dropping_the_header_would_be_caught(self, monkeypatch, owner_client):
        """Red-proof kept in the suite: this is the shape of a headerless call,
        and the assertions above reject it."""
        calls = _patch(monkeypatch)
        owner_client.get(f"/characters/{CHARACTER_ID}/full_profile")
        _url, kwargs = _reads(calls)[0]
        without = {k: v for k, v in kwargs["headers"].items()
                   if k != "X-Internal-Token"}
        with pytest.raises(KeyError):
            without["X-Internal-Token"]
