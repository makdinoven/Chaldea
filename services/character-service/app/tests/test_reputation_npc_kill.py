"""FEAT-197 QA (task 9): NPC kill reputation through PUT /characters/internal/npc-status/{id} (§3.4, §3.14 A5).

* conditional alive -> dead transition; a repeated report is a no-op (``killed`` = false, no reputation);
* every PLAYER among ``killer_character_ids`` gets the full weight (NPC killers ignored);
* weight = per-NPC override ?? role weight ?? '*' weight (bandit is positive);
* old payload without killers (backward compatible) only kills; resurrection never touches reputation.
"""

import pytest
from fastapi.testclient import TestClient

import auth_http
import main
import reputation_crud
from main import app
from tests.reputation_world import (  # noqa: F401  (rep_world is a fixture)
    ALPHA, BANDIT, BETA, GAMMA, GUARD, MERCHANT, NO_ROLE, NOWHERE, OVERRIDE, R_DUNY, R_HOLMY, R_OST, R_PASHNI,
    SCRIBE, USER_ALPHA, USER_BETA, exec_, log_rows, q, rep_world, sent_payloads, value, values,
)

TOKEN = "test-internal-token"
HEADERS = {"X-Internal-Token": TOKEN}


@pytest.fixture
def api(rep_world, monkeypatch):
    def override_get_db():
        session = rep_world()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[main.get_db] = override_get_db
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(main.get_db, None)


def kill(api, npc_id, killers=None, battle_id=77, status="dead", headers=HEADERS):
    body = {"status": status}
    if killers is not None:
        body["killer_character_ids"] = killers
    if battle_id is not None:
        body["battle_id"] = battle_id
    return api.put(f"/characters/internal/npc-status/{npc_id}", json=body, headers=headers)


def npc_status(f, npc_id):
    return q(f, "SELECT npc_status FROM characters WHERE id = :i", i=npc_id)


def test_merchant_kill_hits_every_player_on_the_winning_side(api, rep_world):
    resp = kill(api, MERCHANT, killers=[ALPHA, BETA, BANDIT, MERCHANT])
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "status": "dead", "killed": True}
    assert npc_status(rep_world, MERCHANT) == "dead"
    for cid in (ALPHA, BETA):                                  # full weight each, no split
        assert values(rep_world, cid) == {R_OST: -150, R_PASHNI: -30, R_HOLMY: -30}
    assert values(rep_world, BANDIT) == {} and values(rep_world, MERCHANT) == {}
    origin = [x for x in log_rows(rep_world, ALPHA) if not x[4]]
    assert [(x[2], x[3]) for x in origin] == [("npc_kill", f"npc_kill:{MERCHANT}:77:{ALPHA}")]
    assert origin[0][11] == f"Убит NPC «Лавочник» (#{MERCHANT}) в бою #77"


def test_repeated_death_report_is_a_noop(api, rep_world):
    kill(api, MERCHANT, killers=[ALPHA])
    resp = kill(api, MERCHANT, killers=[ALPHA])
    assert resp.status_code == 200 and resp.json()["killed"] is False
    resp = kill(api, MERCHANT, killers=[ALPHA], battle_id=78)  # even another battle id
    assert resp.json()["killed"] is False
    assert value(rep_world, ALPHA, R_OST) == -150
    assert len(log_rows(rep_world, ALPHA)) == 3


@pytest.mark.parametrize("npc_id,points", [
    (BANDIT, 20),          # positive: killing a bandit is good
    (GUARD, -300),
    (SCRIBE, -150),        # role without a weight row -> '*'
    (OVERRIDE, -5),        # per-NPC override beats the guard weight
])
def test_kill_weight_resolution(api, rep_world, npc_id, points):
    kill(api, npc_id, killers=[ALPHA])
    assert value(rep_world, ALPHA, R_OST) == points


def test_null_role_npc_uses_the_fallback_weight(rep_world):
    import models
    db = rep_world()
    try:
        npc = db.get(models.Character, NO_ROLE)
        results = reputation_crud.apply_npc_kill(db, npc, battle_id=5, killer_ids=[ALPHA, NO_ROLE, 0])
        db.commit()
    finally:
        db.close()
    assert len(results) == 1 and value(rep_world, ALPHA, R_OST) == -150      # '*' weight; the NPC itself skipped


def test_null_role_npc_can_be_killed_through_the_endpoint(api, rep_world):
    assert kill(api, NO_ROLE, killers=[ALPHA]).status_code == 200


def test_role_weights_from_the_table_and_positive_override(api, rep_world):
    db = rep_world()
    try:
        reputation_crud.replace_roles(db, [type("W", (), {"role": "*", "points": -77})(),
                                           type("W", (), {"role": "guard", "points": -10})()])
        db.commit()
    finally:
        db.close()
    kill(api, SCRIBE, killers=[ALPHA])
    assert value(rep_world, ALPHA, R_OST) == -77
    kill(api, GUARD, killers=[BETA])
    assert value(rep_world, BETA, R_OST) == -10
    exec_(rep_world, "UPDATE characters SET reputation_kill_points = 40, npc_status = 'alive' WHERE id = :i",
          i=GUARD)
    kill(api, GUARD, killers=[GAMMA], battle_id=99)
    assert value(rep_world, GAMMA, R_OST) == 40                # positive override allowed (user decision)


def test_zero_override_gives_nothing(api, rep_world):
    exec_(rep_world, "UPDATE characters SET reputation_kill_points = 0 WHERE id = :i", i=GUARD)
    assert kill(api, GUARD, killers=[ALPHA]).json()["killed"] is True
    assert q(rep_world, "SELECT COUNT(*) FROM reputation_log") == 0


def test_old_payload_without_killers_only_kills(api, rep_world):
    resp = api.put(f"/characters/internal/npc-status/{MERCHANT}", json={"status": "dead"}, headers=HEADERS)
    assert resp.status_code == 200 and resp.json()["killed"] is True
    assert npc_status(rep_world, MERCHANT) == "dead"
    assert q(rep_world, "SELECT COUNT(*) FROM reputation_log") == 0
    assert kill(api, MERCHANT, killers=[]).json()["killed"] is False


def test_kill_without_battle_id_still_keys_the_event(api, rep_world):
    assert kill(api, MERCHANT, killers=[ALPHA], battle_id=None).json()["killed"] is True
    key = [x[3] for x in log_rows(rep_world, ALPHA) if not x[4]][0]
    assert key.startswith(f"npc_kill:{MERCHANT}:t") and key.endswith(f":{ALPHA}")


def test_npc_without_region_dies_without_reputation(api, rep_world):
    assert kill(api, NOWHERE, killers=[ALPHA]).json()["killed"] is True
    assert npc_status(rep_world, NOWHERE) == "dead"
    assert q(rep_world, "SELECT COUNT(*) FROM reputation_log") == 0


def test_resurrection_never_touches_reputation(api, rep_world):
    kill(api, MERCHANT, killers=[ALPHA])
    resp = kill(api, MERCHANT, killers=[ALPHA], status="alive")
    assert resp.status_code == 200 and resp.json()["status"] == "alive" and resp.json()["killed"] is False
    assert len(log_rows(rep_world, ALPHA)) == 3
    # a new death after the resurrection counts again (different battle)
    assert kill(api, MERCHANT, killers=[ALPHA], battle_id=78).json()["killed"] is True
    assert value(rep_world, ALPHA, R_OST) == -300


def test_tier_change_from_a_kill_is_published_to_each_player(api, rep_world):
    kill(api, GUARD, killers=[ALPHA, BETA])                     # 0 -> -300: Скиталец -> Изгой
    payloads = sent_payloads(rep_world)
    by_user = {p["target_value"]: p["message"] for p in payloads}
    assert by_user == {USER_ALPHA: "Жители края «Ост» стали относиться к вам хуже: теперь вы — Изгой",
                       USER_BETA: "Жители края «Ост» стали относиться к вам хуже: теперь вы — Изгой"}


def test_auth_and_validation(api, rep_world):
    assert kill(api, MERCHANT, killers=[ALPHA], headers={}).status_code == 401
    assert kill(api, MERCHANT, killers=[ALPHA], headers={"X-Internal-Token": "x"}).status_code == 401
    assert kill(api, MERCHANT, killers=list(range(1, 60))).status_code == 422       # max 50 ids
    assert kill(api, MERCHANT, killers=["1; DROP TABLE characters"]).status_code == 422
    assert kill(api, MERCHANT, status="in_battle").status_code == 422
    assert kill(api, ALPHA, killers=[BETA]).status_code == 404                     # a player is not an NPC
    assert kill(api, 999, killers=[ALPHA]).status_code == 404
    assert npc_status(rep_world, MERCHANT) == "alive"


def test_reputation_failure_rolls_back_the_death(api, rep_world, monkeypatch):
    def boom(*_a, **_k):
        raise reputation_crud.ReputationError(404, "Регион не найден")

    monkeypatch.setattr(reputation_crud, "apply_npc_kill", boom)
    resp = kill(api, MERCHANT, killers=[ALPHA])
    assert resp.status_code == 500
    assert npc_status(rep_world, MERCHANT) == "alive"           # same transaction: nothing half-applied


# --------------------------------------------------------------------------------------------- NPC admin schema

@pytest.mark.parametrize("payload,expected", [
    ({"reputation_min_tier": "trusted", "reputation_kill_points": -40}, ("trusted", -40)),
    ({"reputation_min_tier": "  ", "reputation_kill_points": ""}, (None, None)),
    ({"reputation_min_tier": None, "reputation_kill_points": 1000}, (None, 1000)),
    ({}, (None, None)),
])
def test_npc_update_schema_accepts(payload, expected):
    import schemas
    m = schemas.NpcUpdate(**payload)
    assert (m.reputation_min_tier, m.reputation_kill_points) == expected


@pytest.mark.parametrize("payload", [
    {"reputation_min_tier": "god"},
    {"reputation_min_tier": "trusted'; DROP TABLE characters; --"},
    {"reputation_min_tier": 5},
    {"reputation_kill_points": 1001},
    {"reputation_kill_points": -1001},
])
def test_npc_update_schema_rejects(payload):
    import pydantic
    import schemas
    with pytest.raises(pydantic.ValidationError):
        schemas.NpcUpdate(**payload)
