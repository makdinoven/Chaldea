"""FEAT-156 slice C (T4) — move_and_post returns Russian error messages.

Covers the two user-facing 400s a player hits most often:
  * the destination is not adjacent to the current location;
  * the character does not have enough stamina for the move.

Both assert the status code **and** the exact Russian `detail` text, because the
frontend renders `detail` verbatim in a toast (`LocationPage.tsx:411-414`), so the
string itself is part of the user-facing contract.

A third, static test guards against regressions: it parses `main.py` with `ast`
and asserts that no `detail=` literal inside the `move_and_post` body is pure
ASCII Latin — i.e. nobody can slip a new English message back in.

Mocking follows the existing suite: the shared `client` fixture is not used here
because these tests need their own DB session mock, so they mirror
`test_endpoint_auth.py` (own `TestClient` + `get_db` override) and
`test_action_gates.py` (dependency override of `get_current_user_via_http`,
`patch(... new_callable=AsyncMock)` for the async guards).
"""

import ast
import os
import re
import sys
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from database import get_db  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402


# ── expected strings (must match section 3.7 of FEAT-156) ──────────────────
NOT_ADJACENT_MESSAGE = "Целевая локация не является соседней"
NOT_ENOUGH_STAMINA_MESSAGE = "Недостаточно выносливости для перехода"

CHARACTER_ID = 10
CURRENT_LOCATION_ID = 1
DESTINATION_LOCATION_ID = 2

PAYLOAD = {"character_id": CHARACTER_ID, "content": "x" * 10}


# ── helpers ────────────────────────────────────────────────────────────────
def _http_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _session_returning_neighbor(neighbor):
    """Async session mock whose single `execute` feeds the adjacency lookup."""
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = neighbor
    session.execute.return_value = result
    return session


def _httpx_client(get_side_effect):
    """Mock for `async with httpx.AsyncClient(...) as client`."""
    instance = AsyncMock()
    instance.__aenter__.return_value = instance
    instance.__aexit__.return_value = False
    instance.get.side_effect = get_side_effect
    return instance


def _profile_then_attributes(stamina: int):
    """URL-aware `client.get` side effect for the profile / attributes calls."""

    async def _get(url, *args, **kwargs):
        if "/profile" in url:
            return _http_response(
                200,
                {
                    "current_location_id": CURRENT_LOCATION_ID,
                    "travel_cooldown_until": None,
                },
            )
        if "/attributes/" in url:
            return _http_response(200, {"current_stamina": stamina})
        raise AssertionError(f"unexpected outbound GET: {url}")

    return _get


def _call_move_and_post(session, get_side_effect):
    """Drive POST /locations/{dest}/move_and_post with everything mocked."""
    async def _fake_get_db():
        yield session

    app.dependency_overrides[get_db] = _fake_get_db
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=5, username="owner", role="user", permissions=[]
    )
    try:
        with patch("main.verify_character_ownership", new_callable=AsyncMock), \
             patch("main.check_not_in_battle", new_callable=AsyncMock), \
             patch("main.check_not_gathering", new_callable=AsyncMock), \
             patch("httpx.AsyncClient",
                   return_value=_httpx_client(get_side_effect)):
            with TestClient(app) as client:
                return client.post(
                    f"/locations/{DESTINATION_LOCATION_ID}/move_and_post",
                    json=PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_via_http, None)


# ═══════════════════════════════════════════════════════════════════════════
# Runtime tests — the messages a player actually sees
# ═══════════════════════════════════════════════════════════════════════════
class TestMoveAndPostRussianErrors:
    def test_not_adjacent_returns_400_with_russian_detail(self):
        """No LocationNeighbor row -> 400 with the Russian adjacency message."""
        session = _session_returning_neighbor(None)
        response = _call_move_and_post(
            session, _profile_then_attributes(stamina=100)
        )

        assert response.status_code == 400
        assert response.json()["detail"] == NOT_ADJACENT_MESSAGE

    def test_not_enough_stamina_returns_400_with_russian_detail(self):
        """Adjacent location but stamina < energy_cost -> Russian stamina 400."""
        neighbor = MagicMock()
        neighbor.energy_cost = 5
        session = _session_returning_neighbor(neighbor)

        response = _call_move_and_post(
            session, _profile_then_attributes(stamina=1)
        )

        assert response.status_code == 400
        assert response.json()["detail"] == NOT_ENOUGH_STAMINA_MESSAGE

    @pytest.mark.parametrize(
        "message", [NOT_ADJACENT_MESSAGE, NOT_ENOUGH_STAMINA_MESSAGE]
    )
    def test_messages_are_russian(self, message):
        """Sanity guard on the expected constants themselves."""
        assert re.search(r"[А-Яа-яЁё]", message)
        assert not re.search(r"[A-Za-z]", message)


# ═══════════════════════════════════════════════════════════════════════════
# Static guard — no English `detail=` may come back into move_and_post
# ═══════════════════════════════════════════════════════════════════════════
MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "main.py")


def _detail_literals_in_move_and_post():
    """Every static part of every `detail=` literal inside `move_and_post`.

    Handles plain string constants and f-strings (only their literal segments;
    interpolated expressions are runtime values, not translatable text).
    """
    with open(MAIN_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == "move_and_post":
            target = node
            break
    assert target is not None, "move_and_post not found in main.py"

    literals = []
    for node in ast.walk(target):
        if not isinstance(node, ast.keyword) or node.arg != "detail":
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            literals.append(value.value)
        elif isinstance(value, ast.JoinedStr):
            literals.append(
                "".join(
                    part.value
                    for part in value.values
                    if isinstance(part, ast.Constant)
                    and isinstance(part.value, str)
                )
            )
    return literals


def test_move_and_post_has_detail_literals():
    """The guard below is only meaningful if it actually found something."""
    assert len(_detail_literals_in_move_and_post()) >= 6


def test_no_ascii_latin_detail_in_move_and_post():
    """No user-facing `detail=` inside move_and_post may be English.

    A literal is a violation when it contains Latin letters but no Cyrillic —
    i.e. it is an untranslated English message leaking into a player's toast.
    """
    offenders = [
        text
        for text in _detail_literals_in_move_and_post()
        if re.search(r"[A-Za-z]", text) and not re.search(r"[А-Яа-яЁё]", text)
    ]
    assert not offenders, (
        "Untranslated (ASCII-Latin) HTTPException detail(s) found inside "
        f"move_and_post — all user-facing messages must be Russian: {offenders}"
    )
