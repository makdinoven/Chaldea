"""FEAT-199 QA (task 7): renown — fame sources, infamy, notifications.

* ``add_renown``: clamp at 0, NPC / zero skipped, idempotent per event key, bad scale / key rejected, tier change
  direction;
* the reputation hook: only automatic (no actor) POSITIVE origin changes feed fame (× ``fame_rep_ratio``), echo
  regions do not count, ``quest_complete`` excluded, ``guild_delivery`` × ``fame_guild_ratio`` (0 by default),
  staff adjust excluded, a duplicate reputation event adds nothing;
* the internal quest endpoint ``POST /characters/internal/fame/apply``: token, default / override / zero points,
  idempotent replay, NPC, unknown character 404, validation 422, tier-up notice;
* notifications: only a fame tier UP is announced (progress, «Ваша слава растёт…»); infamy is silent;
* infamy is never visible to others (no public read exposes it).
"""

import pytest

import renown_crud
import shadow_core as sc
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, MERCHANT, R_HOLMY, R_OST, R_PASHNI, USER_ALPHA, INTERNAL, api, as_user, law_world, q, rep_world,
    rows,
)
from tests.reputation_world import apply, sent_payloads
from tests.shadow_world import payloads, renown, renown_log, set_renown, shadow_settings, ws_types


def _add(f, **kwargs):
    db = f()
    try:
        out = renown_crud.add_renown(db, **kwargs)
        db.commit()
        return out
    finally:
        db.close()


# =============================================================================================== add_renown

def test_add_renown_basic_and_idempotent(law_world):
    res = _add(law_world, character_id=ALPHA, scale="fame", delta=60, source="quest", event_key="k1")
    assert (res.value_before, res.value_after, res.tier_before, res.tier_after) == (0, 60, "nameless", "familiar")
    assert res.change.direction == "up" and res.change.user_id == USER_ALPHA
    dup = _add(law_world, character_id=ALPHA, scale="fame", delta=60, source="quest", event_key="k1")
    assert dup.duplicate is True and renown(law_world, ALPHA) == (60, 0)
    down = _add(law_world, character_id=ALPHA, scale="fame", delta=-500, source="staff", event_key="k2")
    assert down.value_after == 0 and down.change.direction == "down"
    assert renown_log(law_world, ALPHA)[-1][3] == -60                   # applied delta after the clamp


def test_add_renown_skips(law_world):
    assert _add(law_world, character_id=MERCHANT, scale="fame", delta=5, source="quest", event_key="n").skipped
    assert _add(law_world, character_id=ALPHA, scale="fame", delta=0, source="quest", event_key="z").skipped
    assert _add(law_world, character_id=99999, scale="fame", delta=5, source="quest", event_key="u").skipped
    assert q(law_world, "SELECT COUNT(*) FROM renown_log") == 0


@pytest.mark.parametrize("kwargs", [{"scale": "glory", "event_key": "k"}, {"scale": "fame", "event_key": ""},
                                    {"scale": "fame", "event_key": "k" * 192}])
def test_add_renown_rejects_bad_input(law_world, kwargs):
    with pytest.raises(ValueError):
        _add(law_world, character_id=ALPHA, delta=5, source="quest", **kwargs)


def test_infamy_tier_change_is_not_announced():
    up_infamy = renown_crud.RenownChange(ALPHA, USER_ALPHA, "infamy", "none", "О вас не говорят", "whispers",
                                         "Шёпот в тавернах", "up")
    down_fame = renown_crud.RenownChange(ALPHA, USER_ALPHA, "fame", "known", "Известный", "familiar",
                                         "Знакомое имя", "down")
    no_user = renown_crud.RenownChange(ALPHA, None, "fame", "nameless", "Безвестный", "familiar", "Знакомое имя", "up")
    assert renown_crud.fame_notices([up_infamy, down_fame, no_user, None]) == []
    up = renown_crud.RenownChange(ALPHA, USER_ALPHA, "fame", "nameless", "Безвестный", "familiar", "Знакомое имя",
                                  "up")
    [notice] = renown_crud.fame_notices([up])
    assert notice.ws_type == "fame_tier" and notice.category == "progress"
    assert notice.message == "Ваша слава растёт: теперь вы — «Знакомое имя»"
    assert notice.data == {"character_id": ALPHA, "tier_code": "familiar"}


# =============================================================================================== reputation hook

def test_positive_automatic_reputation_feeds_half_fame_origin_only(law_world):
    res = apply(law_world, character_id=ALPHA, region_id=R_OST, action="region_event_help", idem_key="ev:1",
                delta=100)
    assert {c.region_id for c in res.changes} == {R_OST, R_PASHNI, R_HOLMY}       # echoes exist
    assert renown(law_world, ALPHA) == (50, 0)                                     # 100 x 0.5, echoes ignored
    assert renown_log(law_world, ALPHA) == [("fame:rep:ev:1", "fame", "reputation", 50, 50, "nameless",
                                             "familiar", None)]
    assert [c.tier_after for c in res.fame_changes] == ["familiar"]
    # duplicate reputation event -> no second fame
    dup = apply(law_world, character_id=ALPHA, region_id=R_OST, action="region_event_help", idem_key="ev:1",
                delta=100)
    assert dup.duplicate and renown(law_world, ALPHA) == (50, 0)


def test_negative_reputation_gives_no_fame(law_world):
    apply(law_world, character_id=ALPHA, region_id=R_OST, action="npc_kill", idem_key="k", delta=-150)
    assert renown(law_world, ALPHA) == (0, 0)


def test_quest_reputation_gives_no_fame(law_world):
    apply(law_world, character_id=ALPHA, region_id=R_OST, action="quest_complete", idem_key="quest_reward:cq:1",
          delta=10)
    assert renown(law_world, ALPHA) == (0, 0)


def test_guild_delivery_ratio_zero_by_default_then_configurable(law_world):
    apply(law_world, character_id=ALPHA, region_id=R_OST, action="guild_delivery", idem_key="g:1", delta=2)
    assert renown(law_world, ALPHA) == (0, 0)
    shadow_settings(law_world, fame_guild_ratio=1)
    apply(law_world, character_id=ALPHA, region_id=R_OST, action="guild_delivery", idem_key="g:2", delta=2)
    assert renown(law_world, ALPHA) == (2, 0)


def test_staff_reputation_adjust_gives_no_fame(law_world):
    apply(law_world, character_id=ALPHA, region_id=R_OST, action="admin_manual", idem_key="s:1", delta=200,
          actor_user_id=1, reason="тест")
    assert renown(law_world, ALPHA) == (0, 0)


def test_fame_rep_ratio_setting(law_world):
    shadow_settings(law_world, fame_rep_ratio=0)
    apply(law_world, character_id=ALPHA, region_id=R_OST, action="region_event_help", idem_key="ev:2", delta=100)
    assert renown(law_world, ALPHA) == (0, 0)


def test_internal_reputation_apply_publishes_fame_tier(api, law_world, stub_law_notify_send):
    resp = api.post("/characters/internal/reputation/apply", headers=INTERNAL,
                    json={"character_id": ALPHA, "region_id": R_OST, "action": "region_event_help",
                          "idempotency_key": "ev:http:1", "delta": 100})
    assert resp.status_code == 200, resp.text
    assert renown(law_world, ALPHA) == (50, 0)
    assert ws_types(stub_law_notify_send) == ["fame_tier"]


# =============================================================================================== quest fame endpoint

def _fame(api, headers=INTERNAL, **body):
    payload = {"character_id": ALPHA, "source": "quest", "idempotency_key": "fame:quest:cq:1"}
    payload.update(body)
    return api.post("/characters/internal/fame/apply", json=payload, headers=headers)


def test_quest_fame_default_points(api, law_world, stub_law_notify_send):
    resp = _fame(api, ref_id=1)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"applied": True, "duplicate": False, "tier_changed": False}
    assert renown(law_world, ALPHA) == (5, 0)
    assert renown_log(law_world, ALPHA)[0][:4] == ("fame:quest:cq:1", "fame", "quest", 5)
    assert q(law_world, "SELECT ref_id FROM renown_log") == 1
    assert stub_law_notify_send.call_count == 0


def test_quest_fame_default_follows_settings(api, law_world):
    shadow_settings(law_world, fame_quest_default=12)
    _fame(api)
    assert renown(law_world, ALPHA) == (12, 0)


def test_quest_fame_override_and_tier_up(api, law_world, stub_law_notify_send):
    resp = _fame(api, points=50)
    assert resp.json() == {"applied": True, "duplicate": False, "tier_changed": True}
    assert renown(law_world, ALPHA) == (50, 0)
    sent = payloads(stub_law_notify_send)
    assert [(p["target_value"], p["ws_type"], p["message"]) for p in sent] == [
        (USER_ALPHA, "fame_tier", "Ваша слава растёт: теперь вы — «Знакомое имя»")]


def test_quest_fame_replay_is_idempotent(api, law_world):
    assert _fame(api, points=10).json()["applied"] is True
    replay = _fame(api, points=10)
    assert replay.status_code == 200
    assert replay.json() == {"applied": False, "duplicate": True, "tier_changed": False}
    assert renown(law_world, ALPHA) == (10, 0)


def test_quest_fame_zero_points_and_npc(api, law_world):
    assert _fame(api, points=0).json() == {"applied": False, "duplicate": False, "tier_changed": False}
    assert _fame(api, character_id=MERCHANT, idempotency_key="fame:quest:cq:2").json()["applied"] is False
    assert q(law_world, "SELECT COUNT(*) FROM renown_log") == 0


def test_quest_fame_unknown_character(api, law_world):
    assert _fame(api, character_id=99999).status_code == 404


@pytest.mark.parametrize("body", [
    {"source": "pvp"}, {"source": "quest' OR '1'='1"}, {"points": 1001}, {"points": -1}, {"idempotency_key": ""},
    {"idempotency_key": "k" * 192}, {"character_id": 0}, {"character_id": "1; DROP TABLE characters"},
])
def test_quest_fame_validation(api, law_world, body):
    assert _fame(api, **body).status_code == 422
    assert q(law_world, "SELECT COUNT(*) FROM characters") > 0


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Token": "wrong"}])
def test_quest_fame_requires_the_internal_token(api, law_world, headers):
    assert _fame(api, headers=headers).status_code == 401
    assert renown(law_world, ALPHA) == (0, 0)


# =============================================================================================== infamy visibility

def test_infamy_is_never_exposed_to_another_player(api, law_world):
    set_renown(law_world, ALPHA, fame=0, infamy=2600)
    as_user(8)                                                          # Бета's owner
    assert api.get(f"/characters/{ALPHA}/renown").status_code == 403
    assert api.get(f"/characters/{ALPHA}/law").status_code == 403
    tiers = api.get("/characters/renown/fame-tiers").text
    assert "dreaded" not in tiers and "шёпотом" not in tiers


def test_reputation_notify_not_used_for_fame(law_world):
    apply(law_world, character_id=ALPHA, region_id=R_OST, action="region_event_help", idem_key="ev:3", delta=100)
    assert all(p.get("ws_type") != "fame_tier" for p in sent_payloads(law_world))


def test_default_tiers_match_witness_bonus():
    fame = sc.scale_tiers(sc.DEFAULT_TIERS, "fame")
    assert [(t.code, t.min_value) for t in fame] == [("nameless", 0), ("familiar", 50), ("known", 200),
                                                     ("famous", 600), ("legend", 1500)]
