"""FEAT-145 — combat intent-post validation (min length + target count).

Uses the shared `client` fixture (TestClient with a MagicMock DB) and mocks the
async ownership/battle/gathering guards so validation runs; the post never
reaches the DB because the checks fail first.
"""
from unittest.mock import patch, AsyncMock

from main import app
from auth_http import UserRead, get_current_user_via_http


def _admin():
    # Admin skips the physical-location check in create_new_post.
    app.dependency_overrides[get_current_user_via_http] = \
        lambda: UserRead(id=1, username="a", role="admin", permissions=[])


def _clear():
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _post(client, content, post_type, targets):
    return client.post("/locations/posts/", json={
        "character_id": 1, "location_id": 1, "content": content,
        "post_type": post_type, "targets": targets,
    })


def test_combat_symbols_scale_with_targets(client):
    # v2: 2 mob targets need 400 chars (200 each); 300 is not enough.
    _admin()
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
         patch("main.check_not_in_battle", new_callable=AsyncMock), \
         patch("main.check_not_gathering", new_callable=AsyncMock):
        r = _post(client, "x" * 300, "combat", [1, 2])
    _clear()
    assert r.status_code == 400
    assert "400" in r.json()["detail"]


def _post_gates(client, content, gates):
    return client.post("/locations/posts/", json={
        "character_id": 1, "location_id": 1, "content": content, "gates": gates,
    })


def test_multi_gate_symbols_sum(client):
    # v2 item 8: npc (500) + gathering (500) → needs 1000 chars.
    _admin()
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
         patch("main.check_not_in_battle", new_callable=AsyncMock), \
         patch("main.check_not_gathering", new_callable=AsyncMock):
        r = _post_gates(client, "x" * 700, [
            {"action_type": "npc_dialogue", "targets": [10]},
            {"action_type": "gathering", "targets": [20]},
        ])
    _clear()
    assert r.status_code == 400
    assert "1000" in r.json()["detail"]


def test_combat_post_target_limit(client):
    _admin()
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
         patch("main.check_not_in_battle", new_callable=AsyncMock), \
         patch("main.check_not_gathering", new_callable=AsyncMock):
        # 500 chars → floor(500/200) = 2 targets allowed; 3 requested → rejected.
        r = _post(client, "x" * 500, "combat", [1, 2, 3])
    _clear()
    assert r.status_code == 400


def test_combat_post_needs_a_target(client):
    _admin()
    with patch("main.verify_character_ownership", new_callable=AsyncMock), \
         patch("main.check_not_in_battle", new_callable=AsyncMock), \
         patch("main.check_not_gathering", new_callable=AsyncMock):
        r = _post(client, "x" * 600, "combat", [])
    _clear()
    assert r.status_code == 400
