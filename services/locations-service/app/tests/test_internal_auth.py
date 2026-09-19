"""
FEAT-169 — the two locations-service routes that were reachable anonymously.

**1. Quest progress (moved + gated).**
`POST /locations/quests/progress/update` advanced any character's quest
objective by an arbitrary increment, and finishing an objective pays the quest
reward. It had **zero callers** anywhere in the repo, so it was moved under the
already-403'd internal prefix and given the fail-closed gate:

    POST /locations/quests/internal/progress/update   (verify_internal_token)

The old path must be **gone**, not aliased — a 404, so a forgotten caller fails
loudly instead of quietly bypassing the gate.

**2. NPC dialogue choice (JWT only, deliberately no ownership check).**
`POST /locations/npcs/{npc_id}/dialogue/{node_id}/choose` gained
`get_current_user_via_http`. See `TestDialogueChooseHasNoOwnershipCheckByDesign`
below before "fixing" the missing ownership check — its absence is a design
decision, pinned here on purpose.

`verify_internal_token` lives in `main.py` in this service and reads a
**module-level** constant captured at import, so the tests pin
`main.INTERNAL_SERVICE_TOKEN` rather than the env var.
"""

import os
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import main
from auth_http import UserRead, get_current_user_via_http
from database import get_db

TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}

NEW_PATH = "/locations/quests/internal/progress/update"
OLD_PATH = "/locations/quests/progress/update"

PROGRESS_BODY = {
    "character_id": 7, "quest_id": 3, "objective_id": 11, "increment": 5,
}

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def progress_calls(monkeypatch):
    """Record every time the handler actually reaches the CRUD layer — a guard
    that rejected *after* writing progress would show up here."""
    calls = []

    async def fake_update(session, character_id, quest_id, objective_id, increment):
        calls.append((character_id, quest_id, objective_id, increment))
        return {"objective_id": objective_id, "current_progress": increment,
                "is_completed": False}

    monkeypatch.setattr(main.crud, "update_quest_progress", fake_update)
    return calls


def _post(client, headers=None, path=NEW_PATH):
    return client.post(path, json=PROGRESS_BODY, headers=headers or {})


# ══════════════════════════════════════════════════════════════════════════════
# 1. Quest progress — outsiders rejected, nothing written
# ══════════════════════════════════════════════════════════════════════════════


class TestQuestProgressRejectsOutsiders:

    def test_no_header_returns_401_and_writes_nothing(self, client, progress_calls):
        response = _post(client)
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"
        assert progress_calls == [], "quest progress advanced for a rejected caller"

    def test_wrong_header_returns_401(self, client, progress_calls):
        response = _post(client, WRONG_HEADERS)
        assert response.status_code == 401
        assert response.json()["detail"] == "Недействительный internal token"
        assert progress_calls == []

    def test_empty_header_value_returns_401(self, client, progress_calls):
        assert _post(client, {"X-Internal-Token": ""}).status_code == 401
        assert progress_calls == []

    def test_player_bearer_token_is_not_accepted(self, client, progress_calls):
        """No browser caller exists: a JWT must not open a reward-paying route."""
        response = _post(client, {"Authorization": "Bearer player-jwt"})
        assert response.status_code == 401
        assert progress_calls == []

    def test_auth_runs_before_schema_validation(self, client, progress_calls):
        """A malformed anonymous body must still be a 401, not a 422 — the
        request must not reach the handler at all."""
        response = client.post(NEW_PATH, json={"nonsense": True})
        assert response.status_code == 401, response.text
        assert progress_calls == []

    def test_header_name_is_case_insensitive_but_value_is_not(self, client,
                                                              progress_calls):
        assert _post(client, {"x-internal-token": TOKEN}).status_code not in (401, 503)
        assert _post(client, {"X-Internal-Token": TOKEN.upper()}).status_code == 401


class TestQuestProgressFailsClosed:

    def test_empty_token_returns_503_and_never_200(self, client, monkeypatch,
                                                   progress_calls):
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "")
        for headers in ({}, GOOD_HEADERS, WRONG_HEADERS, {"X-Internal-Token": ""}):
            response = _post(client, headers)
            assert response.status_code == 503, response.text
            assert response.json()["detail"] == "Internal service token не настроен"
        assert progress_calls == []


class TestQuestProgressAcceptsTheToken:

    def test_good_header_reaches_the_handler(self, client, progress_calls):
        response = _post(client, GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert progress_calls == [(7, 3, 11, 5)]

    def test_missing_progress_row_is_still_a_404(self, client, monkeypatch):
        """The contract did not change with the move."""
        async def none(*args, **kwargs):
            return None

        monkeypatch.setattr(main.crud, "update_quest_progress", none)
        response = _post(client, GOOD_HEADERS)
        assert response.status_code == 404
        assert response.json()["detail"] == "Прогресс квеста не найден"


# ══════════════════════════════════════════════════════════════════════════════
# 2. The old, ungated path is gone
# ══════════════════════════════════════════════════════════════════════════════


class TestOldQuestProgressPathIsGone:
    """It must **404**, not silently keep working and not 401 from some
    catch-all: an alias left behind would be the hole itself."""

    def test_old_path_returns_404(self, client, progress_calls):
        response = client.post(OLD_PATH, json=PROGRESS_BODY)
        assert response.status_code == 404, response.text
        assert progress_calls == []

    def test_old_path_404s_even_with_a_valid_internal_token(self, client,
                                                            progress_calls):
        response = client.post(OLD_PATH, json=PROGRESS_BODY, headers=GOOD_HEADERS)
        assert response.status_code == 404, response.text
        assert progress_calls == []

    def test_the_old_path_is_not_on_the_route_table(self):
        from fastapi.routing import APIRoute

        paths = {r.path for r in main.app.routes if isinstance(r, APIRoute)}
        assert "/locations/quests/progress/update" not in paths
        assert "/locations/quests/internal/progress/update" in paths


# ══════════════════════════════════════════════════════════════════════════════
# 3. NPC dialogue choice — authentication only
# ══════════════════════════════════════════════════════════════════════════════

CHOOSE_PATH = "/locations/npcs/5/dialogue/42/choose"


def _node(option_id=1, next_node_id=None):
    node = MagicMock()
    option = MagicMock()
    option.id = option_id
    option.next_node_id = next_node_id
    node.options = [option]
    return node


@pytest.fixture()
def dialogue_node(monkeypatch):
    monkeypatch.setattr(main.crud, "get_dialogue_node",
                        AsyncMock(return_value=_node()))


@pytest.fixture()
def authed_client(client):
    main.app.dependency_overrides[get_current_user_via_http] = \
        lambda: UserRead(id=99, username="player")
    yield client
    main.app.dependency_overrides.pop(get_current_user_via_http, None)


class TestDialogueChooseRequiresAuth:

    def test_anonymous_returns_401(self, client, dialogue_node):
        response = client.post(CHOOSE_PATH, json={"option_id": 1})
        assert response.status_code == 401, response.text

    def test_anonymous_never_reaches_the_dialogue_tree(self, client, monkeypatch):
        """The hole was reconnaissance as much as mutation: an anonymous caller
        must not be able to walk NPC dialogue nodes at all."""
        seen = []

        async def fake_get_node(session, node_id):
            seen.append(node_id)
            return _node()

        monkeypatch.setattr(main.crud, "get_dialogue_node", fake_get_node)
        assert client.post(CHOOSE_PATH, json={"option_id": 1}).status_code == 401
        assert seen == []

    def test_authenticated_response_is_unchanged(self, authed_client, dialogue_node):
        """Same body as before the gate: a terminal option ends the dialogue."""
        response = authed_client.post(CHOOSE_PATH, json={"option_id": 1})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["is_end"] is True
        assert data["npc_text"] == "Диалог завершён."
        assert data["options"] == []

    def test_unknown_option_is_still_a_400(self, authed_client, dialogue_node):
        response = authed_client.post(CHOOSE_PATH, json={"option_id": 777})
        assert response.status_code == 400
        assert response.json()["detail"] == "Вариант ответа не найден в этом узле"

    def test_unknown_node_is_still_a_404(self, authed_client, monkeypatch):
        monkeypatch.setattr(main.crud, "get_dialogue_node",
                            AsyncMock(return_value=None))
        response = authed_client.post(CHOOSE_PATH, json={"option_id": 1})
        assert response.status_code == 404
        assert response.json()["detail"] == "Узел диалога не найден"


class TestDialogueChooseHasNoOwnershipCheckByDesign:
    """⚠️ READ BEFORE "FIXING" THIS ROUTE.

    Every other player route in this service pairs `get_current_user_via_http`
    with an ownership check on a `character_id`. This one **deliberately does
    not**, and that is not an oversight:

    * `DialogueChooseRequest` carries **only** `option_id` (`schemas.py:1024`) —
      there is no character to own. Adding one would be a breaking contract
      change plus a frontend change (`NpcDialogueModal.tsx:74`);
    * the handler is pure dialogue-tree navigation and **grants nothing** —
      quests are accepted through the separate `POST /quests/{id}/accept`;
    * authentication alone closes the anonymous hole that FEAT-169 targeted.

    If a future change makes this route mutate character state, the ownership
    check becomes mandatory — and this test should be replaced, not deleted.
    """

    def test_the_route_keeps_its_jwt_dependency(self):
        """The 401 tests above could also pass if the route disappeared — pin
        the dependency itself."""
        import inspect

        sig = inspect.signature(main.choose_dialogue_option)
        assert "current_user" in sig.parameters, \
            "the dialogue-choose route lost its JWT dependency"
        assert sig.parameters["current_user"].default.dependency is \
            get_current_user_via_http

    def test_the_absence_of_the_ownership_check_is_documented(self):
        doc = main.choose_dialogue_option.__doc__ or ""
        assert "deliberately no ownership check" in doc, (
            "the deliberate absence of the ownership check lost its explanatory "
            "docstring — read this test class's docstring before changing the "
            "route"
        )

    def test_the_request_schema_carries_no_character_id(self):
        import schemas

        assert set(schemas.DialogueChooseRequest.__fields__) == {"option_id"}, (
            "DialogueChooseRequest gained a field — if it is a character_id, "
            "this route now needs an ownership check (see the class docstring)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Source sweep — a new call into a gated path must carry the header
# ══════════════════════════════════════════════════════════════════════════════


class TestGatedOutgoingCallsSweep:
    """party-service style (`party/tests/test_internal_headers.py`): reading the
    source catches a *future* call site that the unit tests above do not know
    about. Three of these targets swallow their errors, so a forgotten header
    would cost squad XP, squad rosters or gathering rewards with no exception
    anywhere — the project's recurring silent-failure pattern."""

    GATED_TARGETS = (
        "/party/internal/xp-bonus",
        "/party/internal/active-members",
        "/gathering/award",
        "/free_slots_check",
        "/quests/internal/progress/update",
    )

    def _sources(self):
        for filename in ("main.py", "crud.py"):
            path = os.path.join(_APP_DIR, filename)
            with open(path, encoding="utf-8") as fh:
                yield filename, fh.read()

    @staticmethod
    def _is_prose(source: str, idx: int) -> bool:
        """A comment or a docstring line mentioning the path is not a call."""
        start = source.rfind("\n", 0, idx) + 1
        line = source[start:source.find("\n", idx)].lstrip()
        return line.startswith(("#", '"""', "'''", "*"))

    def test_every_call_into_a_gated_path_passes_the_header_helper(self):
        offenders = []
        checked = 0
        for filename, source in self._sources():
            for target in self.GATED_TARGETS:
                for match in re.finditer(re.escape(target), source):
                    idx = match.start()
                    window = source[max(0, idx - 300): idx + 900]
                    if self._is_prose(source, idx):
                        continue
                    # the route *declaration* of the moved quest route is not a
                    # call site
                    if "@router.post(" in source[max(0, idx - 80): idx]:
                        continue
                    # only outgoing HTTP calls are in scope
                    if not re.search(r"(client|httpx)\.(post|get)\(", window):
                        continue
                    checked += 1
                    if "_internal_token_headers()" not in window:
                        line = source.count("\n", 0, idx) + 1
                        offenders.append(f"{filename}:{line} ({target})")
        assert not offenders, (
            "call(s) into a gated internal path without X-Internal-Token: "
            + "; ".join(offenders)
        )
        # the four known FEAT-169 call sites must actually have been inspected —
        # otherwise a filter change could turn this test into a no-op
        assert checked >= 4, (
            f"the sweep inspected only {checked} call site(s); it is no longer "
            "covering the known callers"
        )
