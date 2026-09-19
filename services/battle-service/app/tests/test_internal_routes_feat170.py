"""
FEAT-170 (QA task #14) — route-side auth matrix for battle-service's three
`/battles/internal/` routes, plus the sweep that keeps future routes honest.

Routes covered (all gated in task #12):
  * `GET  /battles/internal/{battle_id}/state`        (main.py:1394)
  * `POST /battles/internal/{battle_id}/action`       (main.py:1451, keeps
                                                       `skip_ownership=True`)
  * `POST /battles/internal/party/leave-on-move`      (main.py:6393)

Contract asserted for each (§3.2), exact Russian `detail` included:

    | condition                       | status | detail                             |
    |---------------------------------|--------|------------------------------------|
    | no `X-Internal-Token`           | 401    | Недействительный internal token    |
    | wrong `X-Internal-Token`        | 401    | Недействительный internal token    |
    | INTERNAL_SERVICE_TOKEN empty    | 503    | Internal service token не настроен  |
    | correct `X-Internal-Token`      | route runs unchanged                        |

**Every rejection case also asserts that nothing was written.** A guard that
401s *after* mutating state would be worthless, and the assertion is cheap: the
handler's only side-effecting collaborator (`load_state`, `_make_action_core`,
`_prune_party_by_location` / the DB session) is patched and must stay untouched.

GOTCHA, the one the developers hit repeatedly: `verify_internal_token` compares
against `auth_http.INTERNAL_SERVICE_TOKEN`, a **module-level constant captured
at import time**. `monkeypatch.setenv` does nothing for the incoming guard —
tests must `monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", ...)`.
(The *outgoing* helper `main._internal_token_headers()` reads `os.environ` at
call time, so `setenv` is the right tool there — see `test_internal_headers.py`.)
"""

import os
import sys

from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

for _mod_name in (
    "redis_state",
    "mongo_client",
    "mongo_helpers",
    "tasks",
    "inventory_client",
    "character_client",
    "skills_client",
    "buffs",
    "battle_engine",
):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

_redis_state_mock = sys.modules["redis_state"]
_redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
_redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
_redis_state_mock.state_key = MagicMock(return_value="battle:1:state")
_redis_state_mock.init_battle_state = AsyncMock()
_redis_state_mock.load_state = AsyncMock(return_value=None)
_redis_state_mock.save_state = AsyncMock()
_redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())
_redis_state_mock.cache_snapshot = AsyncMock()
_redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)

_tasks_mock = sys.modules["tasks"]
_tasks_mock.save_log = MagicMock()
_tasks_mock.save_log.delay = MagicMock()

import auth_http  # noqa: E402
import main  # noqa: E402

from database import get_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

main.app.router.on_startup.clear()


TOKEN = "feat170-route-token"
GOOD = {"X-Internal-Token": TOKEN}
WRONG = {"X-Internal-Token": "not-the-token"}

DETAIL_401 = "Недействительный internal token"
DETAIL_503 = "Internal service token не настроен"

#: The routes this feature gated, as (method, path) — used by the sweep below
#: so a deleted route is as loud as an ungated one.
GATED_ROUTES = (
    ("GET", "/battles/internal/{battle_id}/state"),
    ("POST", "/battles/internal/{battle_id}/action"),
    ("POST", "/battles/internal/party/leave-on-move"),
)


@pytest.fixture()
def good_token(monkeypatch):
    """Point the guard's module-level constant at a known value.

    `setenv` is deliberately NOT used: the constant was captured at import time
    and would keep whatever the container started with.
    """
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


@pytest.fixture()
def empty_token(monkeypatch):
    """The fail-closed case: no token configured at all -> every call 503s."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")


@pytest.fixture()
def client():
    with TestClient(main.app) as c:
        yield c


def _battle_state():
    return {
        "turn_number": 5,
        "next_actor": 1,
        "first_actor": 1,
        "turn_order": [1, 2],
        "total_turns": 5,
        "last_turn": None,
        "deadline_at": "2026-01-01T00:00:00",
        "participants": {
            "1": {
                "character_id": 10, "hp": 100, "mana": 50, "energy": 50,
                "stamina": 50, "team": 0, "cooldowns": {}, "fast_slots": [],
                "max_hp": 100, "max_mana": 50, "max_energy": 50,
                "max_stamina": 50,
            },
            "2": {
                "character_id": 20, "hp": 0, "mana": 50, "energy": 50,
                "stamina": 50, "team": 1, "cooldowns": {}, "fast_slots": [],
                "max_hp": 100, "max_mana": 50, "max_energy": 50,
                "max_stamina": 50,
            },
        },
        "active_effects": {},
        "rewards": None,
    }


ACTION_BODY = {
    "participant_id": 1,
    "skills": {"attack_skill_id": None, "defense_skill_id": None,
               "support_skill_id": None, "item_id": None},
    "target_id": 2,
}


# ═══════════════════════════════════════════════════════════════════════════
# GET /battles/internal/{battle_id}/state
# ═══════════════════════════════════════════════════════════════════════════


class TestInternalStateGuard:
    """Leaks every participant's HP/mana/cooldowns/belt **and the rewards** of
    any live battle. A read, so "nothing written" here means: the handler never
    ran — `load_state` was never even reached."""

    @pytest.fixture(autouse=True)
    def _patch_state(self, monkeypatch):
        self.load_state = AsyncMock(return_value=_battle_state())
        self.get_cached_snapshot = AsyncMock(return_value=[{"participant_id": 1}])
        monkeypatch.setattr(main, "load_state", self.load_state)
        monkeypatch.setattr(main, "get_redis_client", AsyncMock(return_value=MagicMock()))
        monkeypatch.setattr(main, "get_cached_snapshot", self.get_cached_snapshot)
        monkeypatch.setattr(main, "load_snapshot", AsyncMock(return_value=None))

    def test_no_header_is_401_and_reads_nothing(self, client, good_token):
        resp = client.get("/battles/internal/1/state")

        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == DETAIL_401
        assert not self.load_state.called, (
            "guard пропустил запрос без токена до обработчика — состояние боя "
            "прочитано, значит защита стоит не перед логикой"
        )

    def test_wrong_header_is_401_and_reads_nothing(self, client, good_token):
        resp = client.get("/battles/internal/1/state", headers=WRONG)

        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == DETAIL_401
        assert not self.load_state.called

    def test_empty_configured_token_is_503_and_reads_nothing(
        self, client, empty_token
    ):
        """Fail-closed: a container that never got INTERNAL_SERVICE_TOKEN must
        refuse everyone, not let everyone in."""
        resp = client.get("/battles/internal/1/state", headers=GOOD)

        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"] == DETAIL_503
        assert not self.load_state.called

    def test_correct_header_returns_the_state(self, client, good_token):
        resp = client.get("/battles/internal/1/state", headers=GOOD)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["runtime"]["turn_number"] == 5
        assert set(body["runtime"]["participants"]) == {"1", "2"}
        assert self.load_state.await_count == 1

    def test_correct_header_still_404s_on_a_missing_battle(
        self, client, good_token, monkeypatch
    ):
        """Past the guard the handler behaves exactly as before — a 404 from the
        handler, never a 401 from the guard."""
        monkeypatch.setattr(main, "load_state", AsyncMock(return_value=None))
        resp = client.get("/battles/internal/999/state", headers=GOOD)

        assert resp.status_code == 404, resp.text

    def test_the_public_twin_is_not_reachable_with_the_internal_token(
        self, client, good_token
    ):
        """The browser path `GET /battles/{id}/state` stays JWT-gated; the
        service token must not become a second way in."""
        resp = client.get("/battles/1/state", headers=GOOD)
        assert resp.status_code == 401, resp.text


# ═══════════════════════════════════════════════════════════════════════════
# POST /battles/internal/{battle_id}/action
# ═══════════════════════════════════════════════════════════════════════════


class TestInternalActionGuard:
    """The worst of the three: `_make_action_core(..., skip_ownership=True)`
    acts as **any** participant in **any** battle. Nothing but the token stands
    between an attacker inside the compose network and every live fight, so the
    "nothing was written" assertion is the point of this class."""

    @pytest.fixture(autouse=True)
    def _patch_core(self, monkeypatch):
        self.core = AsyncMock(return_value={
            "ok": True,
            "turn_number": 6,
            "next_actor": 2,
            "deadline_at": "2026-01-01T00:00:00",
            "events": [],
        })
        monkeypatch.setattr(main, "_make_action_core", self.core)

        self.db = AsyncMock()

        async def _fake_get_db():
            yield self.db

        main.app.dependency_overrides[get_db] = _fake_get_db
        yield
        main.app.dependency_overrides.pop(get_db, None)

    def test_no_header_is_401_and_the_turn_is_not_taken(self, client, good_token):
        resp = client.post("/battles/internal/1/action", json=ACTION_BODY)

        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == DETAIL_401
        assert not self.core.called, (
            "ход был выполнен до проверки токена — skip_ownership=True означает, "
            "что кто угодно сходил бы за любого участника любого боя"
        )
        assert not self.db.execute.called

    def test_wrong_header_is_401_and_the_turn_is_not_taken(self, client, good_token):
        resp = client.post("/battles/internal/1/action", json=ACTION_BODY, headers=WRONG)

        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == DETAIL_401
        assert not self.core.called
        assert not self.db.execute.called

    def test_empty_configured_token_is_503_and_the_turn_is_not_taken(
        self, client, empty_token
    ):
        resp = client.post("/battles/internal/1/action", json=ACTION_BODY, headers=GOOD)

        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"] == DETAIL_503
        assert not self.core.called

    def test_guard_rejects_before_body_validation(self, client, good_token):
        """A malformed body without a token must still be a 401, not a 422 —
        otherwise the schema of the internal action route is readable by anyone
        who can reach the port."""
        resp = client.post("/battles/internal/1/action", json={"nonsense": 1})

        assert resp.status_code == 401, resp.text
        assert not self.core.called

    def test_correct_header_takes_the_turn(self, client, good_token):
        resp = client.post("/battles/internal/1/action", json=ACTION_BODY, headers=GOOD)

        assert resp.status_code == 200, resp.text
        assert resp.json()["turn_number"] == 6
        assert self.core.await_count == 1
        args, kwargs = self.core.call_args
        assert args[0] == 1, "battle_id must reach the core unchanged"
        assert kwargs.get("skip_ownership") is True, (
            "the internal action route must keep skip_ownership=True — "
            "autobattle drives mobs that own no character"
        )

    def test_correct_header_still_422s_on_a_bad_body(self, client, good_token):
        """Past the guard, validation is the handler's business again."""
        resp = client.post("/battles/internal/1/action", json={"nonsense": 1},
                           headers=GOOD)

        assert resp.status_code == 422, resp.text
        assert not self.core.called


# ═══════════════════════════════════════════════════════════════════════════
# POST /battles/internal/party/leave-on-move
# ═══════════════════════════════════════════════════════════════════════════


class TestPartyLeaveOnMoveGuard:
    """Removes a character from a forming party (disbanding it if they led it).
    Griefing-grade, and the caller (locations-service) swallows every error — so
    the only thing that can catch a regression is this matrix."""

    @pytest.fixture(autouse=True)
    def _patch_db(self, monkeypatch):
        self.prune = AsyncMock(return_value=True)
        monkeypatch.setattr(main, "_prune_party_by_location", self.prune)

        self.db = AsyncMock()
        result = MagicMock()
        scalars = MagicMock()
        scalars.unique = MagicMock(return_value=MagicMock(
            all=MagicMock(return_value=[MagicMock()])
        ))
        result.scalars = MagicMock(return_value=scalars)
        self.db.execute = AsyncMock(return_value=result)

        async def _fake_get_db():
            yield self.db

        main.app.dependency_overrides[get_db] = _fake_get_db
        yield
        main.app.dependency_overrides.pop(get_db, None)

    def test_no_header_is_401_and_the_party_is_untouched(self, client, good_token):
        resp = client.post("/battles/internal/party/leave-on-move?character_id=10")

        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == DETAIL_401
        assert not self.db.execute.called, (
            "запрос дошёл до БД без токена — отряд можно было бы развалить "
            "любому, кто достучался до порта"
        )
        assert not self.prune.called

    def test_wrong_header_is_401_and_the_party_is_untouched(self, client, good_token):
        resp = client.post(
            "/battles/internal/party/leave-on-move?character_id=10", headers=WRONG
        )

        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == DETAIL_401
        assert not self.db.execute.called
        assert not self.prune.called

    def test_empty_configured_token_is_503_and_the_party_is_untouched(
        self, client, empty_token
    ):
        resp = client.post(
            "/battles/internal/party/leave-on-move?character_id=10", headers=GOOD
        )

        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"] == DETAIL_503
        assert not self.db.execute.called
        assert not self.prune.called

    def test_guard_rejects_before_query_validation(self, client, good_token):
        """`character_id` is required; without a token the answer is still 401."""
        resp = client.post("/battles/internal/party/leave-on-move")

        assert resp.status_code == 401, resp.text
        assert not self.db.execute.called

    def test_correct_header_prunes_the_party(self, client, good_token):
        resp = client.post(
            "/battles/internal/party/leave-on-move?character_id=10", headers=GOOD
        )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"ok": True}
        assert self.db.execute.await_count == 1
        assert self.prune.await_count == 1

    def test_correct_header_still_422s_without_character_id(self, client, good_token):
        resp = client.post("/battles/internal/party/leave-on-move", headers=GOOD)

        assert resp.status_code == 422, resp.text
        assert not self.db.execute.called


# ═══════════════════════════════════════════════════════════════════════════
# app.routes sweep — the check that survives us
# ═══════════════════════════════════════════════════════════════════════════
# This is the ad-hoc check the developers ran by hand during task #12, made
# permanent. It is the only assertion in the file that stays true for routes
# nobody has written yet: add a `/internal/` route without the guard and this
# goes red, whatever it is called and whoever adds it.


def _flat_dependency_funcs(route) -> set:
    """Every dependency callable reachable from `route`, sub-dependencies too.

    Walking only `route.dependant.dependencies` would miss a guard attached
    indirectly (e.g. a composite dependency that itself Depends on the guard),
    and a future refactor doing exactly that would silently empty this check.
    """
    found = set()
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return found

    stack = list(getattr(dependant, "dependencies", []) or [])
    seen = set()
    while stack:
        dep = stack.pop()
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        call = getattr(dep, "call", None)
        if call is not None:
            found.add(call)
        stack.extend(getattr(dep, "dependencies", []) or [])
    return found


class TestEveryInternalRouteIsGated:
    """Walk `main.app.routes`: every route whose path contains `/internal/`
    must carry `verify_internal_token` among its flattened dependencies."""

    def _internal_routes(self):
        out = []
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if "/internal/" not in path:
                continue
            for method in sorted(getattr(route, "methods", set()) or {"?"}):
                out.append((method, path, route))
        return out

    def test_every_internal_route_carries_the_guard(self):
        offenders = []
        checked = 0
        for method, path, route in self._internal_routes():
            checked += 1
            funcs = _flat_dependency_funcs(route)
            names = {getattr(f, "__name__", "") for f in funcs}
            if auth_http.verify_internal_token not in funcs \
                    and "verify_internal_token" not in names:
                offenders.append(f"{method} {path}")

        assert checked >= len(GATED_ROUTES), (
            "свип перестал находить internal-маршруты — путь отрефакторили, и "
            f"проверка стала пустой (найдено {checked}, ожидалось хотя бы "
            f"{len(GATED_ROUTES)})"
        )
        assert not offenders, (
            "маршрут с сегментом /internal/ без verify_internal_token — он "
            "держится только на правиле nginx: " + "; ".join(sorted(offenders))
        )

    def test_the_three_feat170_routes_are_still_registered(self):
        """Guard for the sweep itself: deleting a route must be as loud as
        leaving one open."""
        registered = {(m, p) for m, p, _ in self._internal_routes()}
        missing = [f"{m} {p}" for m, p in GATED_ROUTES if (m, p) not in registered]
        assert not missing, (
            "маршрут FEAT-170 исчез из приложения: " + "; ".join(missing)
        )

    def test_the_public_twins_are_not_internal_and_stay_jwt_gated(self):
        """`GET /battles/{battle_id}/state` and `POST /battles/{battle_id}/action`
        are the browser's paths; they must NOT pick up the internal guard (a
        player has no service token) and must keep their JWT dependency."""
        for method, path in (
            ("GET", "/battles/{battle_id}/state"),
            ("POST", "/battles/{battle_id}/action"),
        ):
            route = next(
                r for r in main.app.routes
                if getattr(r, "path", "") == path
                and method in (getattr(r, "methods", set()) or set())
            )
            names = {getattr(f, "__name__", "")
                     for f in _flat_dependency_funcs(route)}
            assert "verify_internal_token" not in names, (
                f"{method} {path} — публичный двойник получил internal-guard, "
                "игрок не сможет играть"
            )
            assert "get_current_user_via_http" in names, (
                f"{method} {path} потерял JWT-проверку"
            )
