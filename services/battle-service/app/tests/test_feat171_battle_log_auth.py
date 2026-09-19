"""FEAT-171 review #1 issue #2 — the battle log is no longer anonymous.

`GET /battles/battles/{id}/logs` and `.../logs/{turn_number}` had **no** auth
dependency at all and are proxied by the gateway, so a guest could walk
sequential `battle_id`s and read `{"event": "pve_rewards", "xp": 30,
"gold": 5}` and `{"event": "skill_use", "skill_id": 9003}` — the XP, gold and
skills §1 declares private.

The matrix below is the five-viewer matrix of the rest of the feature, adapted
to a battle-shaped subject:

| viewer                              | expected |
|-------------------------------------|----------|
| guest (no token)                    | 401      |
| another player, elsewhere           | 403      |
| participant                         | 200      |
| co-located spectator, live battle   | 200      |
| co-located player, finished battle  | 403      |
| admin/moderator **with** characters:read | 200 |
| moderator **without** the permission     | 403 |
| missing battle id                   | 404 (before any 403) |

Every 401/403 case also asserts the **payload never appears**, so a gate that
returned the logs alongside an error status could not pass.
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

for mod_name in [
    "redis_state", "mongo_client", "mongo_helpers", "tasks",
    "inventory_client", "character_client", "skills_client", "buffs",
    "battle_engine", "rabbitmq_publisher",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.init_battle_state = AsyncMock()
redis_state_mock.load_state = AsyncMock(return_value=None)
redis_state_mock.save_state = AsyncMock()
redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())
redis_state_mock.cache_snapshot = AsyncMock()
redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)
redis_state_mock.state_key = MagicMock(side_effect=lambda bid: f"battle:{bid}:state")

tasks_mock = sys.modules["tasks"]
tasks_mock.save_log = MagicMock()
tasks_mock.save_log.delay = MagicMock()

import main  # noqa: E402
from main import app  # noqa: E402
from database import get_db  # noqa: E402
import battle_visibility  # noqa: E402

app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


BATTLE_ID = 1
LOCATION_ID = 100

AUTH_HEADERS = {"Authorization": "Bearer fake-token"}

# The two payloads the Reviewer read with no token whatsoever.
REWARD_EVENT = {"event": "pve_rewards", "xp": 30, "gold": 5, "items": []}
SKILL_EVENT = {"event": "skill_use", "who": 21, "skill_id": 9003, "kind": "attack"}
SECRET_MARKERS = ("pve_rewards", "skill_use", "9003", "gold")


def _user(uid=1, role="user", permissions=()):
    return {
        "id": uid, "username": f"u{uid}",
        "role": role, "permissions": list(permissions),
    }


def _auth_response(user):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = user
    return resp


class _Row(tuple):
    """A fetchone() row."""


class _FakeDb:
    """Answers the three queries `battle_visibility` can make.

    Dispatch is on a distinctive fragment of each statement, so a rewritten
    query fails loudly instead of silently matching the wrong branch.
    """

    def __init__(self, battle_row, participant_user_ids=(), located_user_ids=()):
        self.battle_row = battle_row
        self.participant_user_ids = set(participant_user_ids)
        self.located_user_ids = set(located_user_ids)
        self.seen = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.seen.append(sql)
        result = MagicMock()
        if "FROM battles" in sql:
            result.fetchone.return_value = self.battle_row
        elif "battle_participants" in sql:
            hit = params.get("uid") in self.participant_user_ids
            result.fetchone.return_value = _Row((1,)) if hit else None
        elif "current_location_id" in sql:
            hit = params.get("uid") in self.located_user_ids
            result.fetchone.return_value = _Row((1,)) if hit else None
        else:  # pragma: no cover — a new query must be taught to this fake
            raise AssertionError(f"unexpected query: {sql}")
        return result


def _install_db(db):
    async def _fake_get_db():
        yield db

    app.dependency_overrides[get_db] = _fake_get_db


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def mongo_logs(monkeypatch):
    """Make both routes able to produce real log documents when allowed."""
    class _Cursor:
        def __init__(self, docs):
            self._docs = docs

        def sort(self, *a, **kw):
            return self

        def limit(self, *a, **kw):
            return self

        def __aiter__(self):
            async def _gen():
                for d in self._docs:
                    yield d
            return _gen()

    class _Collection:
        def find(self, *a, **kw):
            return _Cursor([{"_id": "abc", "battle_id": BATTLE_ID,
                             "turn_number": 1,
                             "events": [REWARD_EVENT, SKILL_EVENT]}])

    class _Db:
        battle_logs = _Collection()

    monkeypatch.setattr(main, "get_mongo_db", lambda: _Db())
    monkeypatch.setattr(
        main, "get_logs_for_turn",
        AsyncMock(return_value=[{
            "battle_id": BATTLE_ID,
            "turn_number": 1,
            "events": [REWARD_EVENT, SKILL_EVENT],
            "timestamp": "2026-09-19T12:00:00",
        }]),
    )


def _active_battle(location_id=LOCATION_ID, status="in_progress"):
    return _Row((location_id, status))


def _assert_no_payload(response):
    body = response.text
    for marker in SECRET_MARKERS:
        assert marker not in body, f"the gate leaked {marker!r} anyway: {body}"


# ===========================================================================
# Guests
# ===========================================================================

class TestGuestsAreRejected:

    @pytest.mark.parametrize("path", [
        f"/battles/battles/{BATTLE_ID}/logs",
        f"/battles/battles/{BATTLE_ID}/logs/1",
    ])
    def test_no_token_is_401(self, path, mongo_logs):
        _install_db(_FakeDb(_active_battle()))
        with TestClient(app) as client:
            r = client.get(path)
        assert r.status_code == 401, r.text
        _assert_no_payload(r)

    @patch("auth_http.requests.get")
    def test_invalid_token_is_401(self, mock_auth, mongo_logs):
        bad = MagicMock()
        bad.status_code = 401
        bad.json.return_value = {}
        mock_auth.return_value = bad
        _install_db(_FakeDb(_active_battle()))
        with TestClient(app) as client:
            r = client.get(
                f"/battles/battles/{BATTLE_ID}/logs", headers=AUTH_HEADERS
            )
        assert r.status_code == 401
        _assert_no_payload(r)


# ===========================================================================
# The matrix
# ===========================================================================

@patch("auth_http.requests.get")
class TestWhoMayRead:

    PATHS = [
        f"/battles/battles/{BATTLE_ID}/logs",
        f"/battles/battles/{BATTLE_ID}/logs/1",
    ]

    @pytest.mark.parametrize("path", PATHS)
    def test_a_participant_reads_the_log(self, mock_auth, path, mongo_logs):
        mock_auth.return_value = _auth_response(_user(uid=5))
        _install_db(_FakeDb(_active_battle(), participant_user_ids={5}))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text
        assert "pve_rewards" in r.text

    @pytest.mark.parametrize("path", PATHS)
    def test_an_outsider_is_403(self, mock_auth, path, mongo_logs):
        mock_auth.return_value = _auth_response(_user(uid=9))
        _install_db(_FakeDb(_active_battle(), participant_user_ids={5}))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == battle_visibility.FORBIDDEN_DETAIL
        _assert_no_payload(r)

    @pytest.mark.parametrize("path", PATHS)
    def test_a_co_located_spectator_reads_a_live_battle(
        self, mock_auth, path, mongo_logs
    ):
        """Verbatim the rule of `GET /{battle_id}/spectate`, which the
        spectator UI uses to load the state these logs annotate."""
        mock_auth.return_value = _auth_response(_user(uid=9))
        _install_db(_FakeDb(
            _active_battle(), participant_user_ids={5}, located_user_ids={9},
        ))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("path", PATHS)
    def test_the_spectator_window_closes_when_the_battle_ends(
        self, mock_auth, path, mongo_logs
    ):
        """Standing in a room does not grant the archive of every battle ever
        fought there — only the participants keep their history."""
        mock_auth.return_value = _auth_response(_user(uid=9))
        _install_db(_FakeDb(
            _active_battle(status="finished"),
            participant_user_ids={5}, located_user_ids={9},
        ))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 403, r.text
        _assert_no_payload(r)

    @pytest.mark.parametrize("path", PATHS)
    def test_a_participant_still_reads_a_finished_battle(
        self, mock_auth, path, mongo_logs
    ):
        mock_auth.return_value = _auth_response(_user(uid=5))
        _install_db(_FakeDb(
            _active_battle(status="finished"), participant_user_ids={5},
        ))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("path", PATHS)
    @pytest.mark.parametrize("role", ["admin", "moderator"])
    def test_staff_with_the_permission_reads_anything(
        self, mock_auth, role, path, mongo_logs
    ):
        mock_auth.return_value = _auth_response(
            _user(uid=99, role=role, permissions=["characters:read"])
        )
        _install_db(_FakeDb(
            _active_battle(status="finished"), participant_user_ids={5},
        ))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("path", PATHS)
    def test_a_moderator_without_the_permission_is_403(
        self, mock_auth, path, mongo_logs
    ):
        """Same split as `can_view_private`: the role alone is not enough."""
        mock_auth.return_value = _auth_response(
            _user(uid=99, role="moderator", permissions=["items:read"])
        )
        _install_db(_FakeDb(
            _active_battle(status="finished"), participant_user_ids={5},
        ))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 403, r.text
        _assert_no_payload(r)

    @pytest.mark.parametrize("path", PATHS)
    def test_an_ordinary_player_with_the_permission_is_still_403(
        self, mock_auth, path, mongo_logs
    ):
        """The permission counts only together with a privileged role."""
        mock_auth.return_value = _auth_response(
            _user(uid=99, role="user", permissions=["characters:read"])
        )
        _install_db(_FakeDb(_active_battle(), participant_user_ids={5}))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 403, r.text

    @pytest.mark.parametrize("path", PATHS)
    def test_a_missing_battle_is_404_before_403(
        self, mock_auth, path, mongo_logs
    ):
        mock_auth.return_value = _auth_response(_user(uid=9))
        _install_db(_FakeDb(None))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 404, r.text
        assert r.json()["detail"] == battle_visibility.NOT_FOUND_DETAIL

    @pytest.mark.parametrize("path", PATHS)
    def test_a_battle_without_a_location_has_no_spectators(
        self, mock_auth, path, mongo_logs
    ):
        mock_auth.return_value = _auth_response(_user(uid=9))
        _install_db(_FakeDb(
            _active_battle(location_id=None), located_user_ids={9},
        ))
        with TestClient(app) as client:
            r = client.get(path, headers=AUTH_HEADERS)
        assert r.status_code == 403, r.text


# ===========================================================================
# The predicate itself
# ===========================================================================

class TestThePredicate:
    """Unit-level checks, so a route refactor cannot quietly drop the rule."""

    @staticmethod
    def _run(db, user):
        import asyncio
        from auth_http import UserRead
        return asyncio.run(
            battle_visibility.can_view_battle_logs(db, BATTLE_ID, UserRead(**user))
        )

    def test_missing_battle_raises_404(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            self._run(_FakeDb(None), _user())
        assert exc.value.status_code == 404

    def test_participant_true(self):
        assert self._run(
            _FakeDb(_active_battle(), participant_user_ids={1}), _user()
        ) is True

    def test_outsider_false(self):
        assert self._run(_FakeDb(_active_battle()), _user()) is False

    def test_pending_battle_still_allows_spectators(self):
        assert self._run(
            _FakeDb(_active_battle(status="pending"), located_user_ids={1}),
            _user(),
        ) is True

    def test_enum_member_status_is_normalised(self):
        """SQLAlchemy may hand back the Enum member instead of the string."""
        from models import BattleStatus
        row = _Row((LOCATION_ID, BattleStatus.in_progress))
        assert self._run(_FakeDb(row, located_user_ids={1}), _user()) is True

    def test_privileged_needs_both_role_and_permission(self):
        db = _FakeDb(_active_battle())
        assert self._run(
            db, _user(role="admin", permissions=["characters:read"])
        ) is True
        assert self._run(db, _user(role="admin", permissions=[])) is False
        assert self._run(
            db, _user(role="user", permissions=["characters:read"])
        ) is False

    def test_the_privileged_branch_short_circuits_the_queries(self):
        """Staff must not need a character at all."""
        db = _FakeDb(_active_battle())
        assert self._run(
            db, _user(role="moderator", permissions=["characters:read"])
        ) is True
        assert not any("battle_participants" in sql for sql in db.seen)
