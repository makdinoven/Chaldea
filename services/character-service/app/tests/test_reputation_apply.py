"""FEAT-197 QA (task 9): reputation_crud.apply_reputation (the single write path) + reputation_notify payloads.

World: tests/reputation_world.py (country 1 = regions 10/11/12, country 2 = region 20). RabbitMQ is never touched:
``reputation_notify._send`` is a recorder.
"""

from datetime import timedelta

import pytest

import reputation_core as rc
import reputation_crud
import reputation_notify
from tests.reputation_world import (  # noqa: F401  (rep_world is a fixture)
    ALPHA, BETA, GAMMA, MERCHANT, R_DUNY, R_HOLMY, R_OST, R_PASHNI, USER_ALPHA, apply, days_ago, exec_, log_rows, q,
    rep_world, rows, sent_payloads, set_value, value, values,
)


# --------------------------------------------------------------------------------------------- basics

def test_default_action_points_and_echo_to_same_country_only(rep_world):
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="quest_reward:cq:1")
    assert r.applied and not r.duplicate and r.skipped is None
    assert values(rep_world, ALPHA) == {R_OST: 10, R_PASHNI: 2, R_HOLMY: 2}       # region 20 is another country
    log = log_rows(rep_world, ALPHA)
    assert [(x[1], x[2], x[3], bool(x[4]), x[5], x[6], x[7], x[8]) for x in log] == [
        (R_OST, "quest_complete", "quest_reward:cq:1", False, None, 10, 10, 10),
        (R_PASHNI, "quest_complete", "quest_reward:cq:1", True, R_OST, 2, 2, 2),
        (R_HOLMY, "quest_complete", "quest_reward:cq:1", True, R_OST, 2, 2, 2),
    ]
    assert all(x[12] is None for x in log)                                          # system actor
    assert [c.region_id for c in r.changes] == [R_OST, R_PASHNI, R_HOLMY]          # lock order = region_id


def test_lock_order_is_by_region_even_from_a_higher_origin(rep_world):
    r = apply(rep_world, character_id=ALPHA, region_id=R_HOLMY, action=rc.ACTION_CRIME, idem_key="crime:1")
    assert [c.region_id for c in r.changes] == [R_OST, R_PASHNI, R_HOLMY]
    assert [c.is_echo for c in r.changes] == [True, True, False]
    assert values(rep_world, ALPHA) == {R_OST: -10, R_PASHNI: -10, R_HOLMY: -50}


def test_country_with_one_region_has_no_echo(rep_world):
    apply(rep_world, character_id=GAMMA, region_id=R_DUNY, action=rc.ACTION_CRIME, idem_key="k")
    assert values(rep_world, GAMMA) == {R_DUNY: -50}


def test_echo_false_and_small_delta_without_echo_rows(rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="a", delta=500,
          echo=False)
    apply(rep_world, character_id=BETA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="b", delta=4)
    assert values(rep_world, ALPHA) == {R_OST: 500}
    assert values(rep_world, BETA) == {R_OST: 4}                                    # echo of 4 × 20 % = 0


def test_explicit_delta_overrides_points_and_may_be_negative(rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="q", delta=-25)
    assert values(rep_world, ALPHA) == {R_OST: -25, R_PASHNI: -5, R_HOLMY: -5}


# --------------------------------------------------------------------------------------------- idempotency

def test_repeat_key_is_a_silent_duplicate(rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="quest_reward:cq:5")
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="quest_reward:cq:5")
    assert r.duplicate and not r.applied and r.changes == []
    assert values(rep_world, ALPHA)[R_OST] == 10
    assert len(log_rows(rep_world, ALPHA)) == 3


def test_same_key_other_character_is_still_one_event_per_region(rep_world):
    """UNIQUE(event_key, region_id) is global: keys must carry the character (all sources do)."""
    apply(rep_world, character_id=ALPHA, region_id=R_DUNY, action=rc.ACTION_QUEST, idem_key="shared")
    r = apply(rep_world, character_id=GAMMA, region_id=R_DUNY, action=rc.ACTION_QUEST, idem_key="shared")
    assert r.duplicate


def test_unique_constraint_is_the_hard_guarantee(rep_world):
    """A racing writer that skipped the pre-check is stopped by UNIQUE(event_key, region_id) at flush."""
    from sqlalchemy.exc import IntegrityError
    import models

    apply(rep_world, character_id=ALPHA, region_id=R_DUNY, action=rc.ACTION_QUEST, idem_key="race")
    db = rep_world()
    try:
        db.add(models.ReputationLog(character_id=ALPHA, region_id=R_DUNY, action="quest_complete", event_key="race",
                                    is_echo=False, requested_delta=1, applied_delta=1, value_after=1,
                                    tier_before="wanderer", tier_after="wanderer",
                                    created_at=reputation_crud.now_utc()))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- clamp / skip / errors

def test_clamp_to_range_logs_requested_and_applied(rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="up", delta=2000,
          echo=False)
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="up2", delta=50,
          echo=False)
    assert value(rep_world, ALPHA, R_OST) == 1000
    log = log_rows(rep_world, ALPHA)
    assert [(x[6], x[7], x[8]) for x in log] == [(2000, 1000, 1000), (50, 0, 1000)]
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="dn", delta=-5000,
          echo=False)
    assert value(rep_world, ALPHA, R_OST) == -1000


def test_capped_legend_still_echoes_the_requested_delta(rep_world):
    set_value(rep_world, ALPHA, R_OST, 995)
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="e", delta=100)
    assert values(rep_world, ALPHA) == {R_OST: 1000, R_PASHNI: 20, R_HOLMY: 20}


def test_npc_has_no_reputation(rep_world):
    r = apply(rep_world, character_id=MERCHANT, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="n")
    assert r.skipped == reputation_crud.SKIP_NPC and not r.applied
    assert q(rep_world, "SELECT COUNT(*) FROM character_reputation") == 0
    assert q(rep_world, "SELECT COUNT(*) FROM reputation_log") == 0


def test_zero_delta_is_skipped(rep_world):
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_NPC_KILL, idem_key="z")
    assert r.skipped == reputation_crud.SKIP_ZERO
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="z2", delta=0)
    assert r.skipped == reputation_crud.SKIP_ZERO
    assert q(rep_world, "SELECT COUNT(*) FROM reputation_log") == 0


@pytest.mark.parametrize("kwargs,status", [
    ({"character_id": 999}, 404),
    ({"region_id": 999}, 404),
    ({"action": "no_such_action"}, 404),
    ({"idem_key": "k" * 192}, 400),
    ({"idem_key": ""}, 400),
])
def test_errors(rep_world, kwargs, status):
    base = {"character_id": ALPHA, "region_id": R_OST, "action": rc.ACTION_QUEST, "idem_key": "k"}
    base.update(kwargs)
    with pytest.raises(reputation_crud.ReputationError) as exc:
        apply(rep_world, **base)
    assert exc.value.status_code == status
    assert q(rep_world, "SELECT COUNT(*) FROM reputation_log") == 0


def test_key_of_exactly_191_chars_is_accepted(rep_world):
    assert apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_QUEST, idem_key="k" * 191).applied


def test_sql_injection_in_action_code_is_just_an_unknown_action(rep_world):
    with pytest.raises(reputation_crud.ReputationError) as exc:
        apply(rep_world, character_id=ALPHA, region_id=R_OST, action="x' OR '1'='1", idem_key="inj")
    assert exc.value.status_code == 404
    assert q(rep_world, "SELECT COUNT(*) FROM characters") == 10


def test_long_reason_is_truncated_to_the_column(rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="r", delta=5,
          reason="я" * 900, actor_user_id=1, echo=False)
    assert len(log_rows(rep_world, ALPHA)[0][11]) == reputation_crud.MAX_REASON


# --------------------------------------------------------------------------------------------- daily cap

def test_guild_daily_cap_per_region(rep_world):
    for i in range(10):
        r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key=f"guild:1:{i}")
        assert r.applied
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key="guild:1:x")
    assert r.skipped == reputation_crud.SKIP_CAP
    assert value(rep_world, ALPHA, R_OST) == 20
    # another region has its own cap
    assert apply(rep_world, character_id=GAMMA, region_id=R_DUNY, action=rc.ACTION_GUILD, idem_key="g:3").applied


def test_daily_cap_reduces_the_last_delta(rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key="g1", delta=15)
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key="g2", delta=15)
    assert r.changes[0].applied_delta == 5 and value(rep_world, ALPHA, R_OST) == 20


def test_daily_cap_ignores_echo_rows_staff_and_negative(rep_world):
    # echo rows of region 10 from region 11 deliveries do not count against region 10
    for i in range(4):
        apply(rep_world, character_id=ALPHA, region_id=R_PASHNI, action=rc.ACTION_GUILD, idem_key=f"p{i}",
              delta=20 if i == 0 else 5)
    assert apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key="o1",
                 delta=20).changes[0].applied_delta == 20
    # staff edits are not capped
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key="staff", delta=30,
              actor_user_id=1)
    assert r.changes[0].applied_delta == 30
    # negative deltas are never capped
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key="neg", delta=-3)
    assert r.applied


def test_daily_cap_resets_next_utc_day(rep_world):
    apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key="d1", delta=20)
    exec_(rep_world, "UPDATE reputation_log SET created_at = :t", t=days_ago(1))
    assert apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_GUILD, idem_key="d2").applied


# --------------------------------------------------------------------------------------------- tiers / decay

def test_tier_changes_are_reported_with_user_and_region(rep_world):
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="t", delta=100)
    assert [(c.region_id, c.user_id, c.region_name, c.tier_before, c.tier_after, c.tier_after_name, c.direction)
            for c in r.tier_changes] == [(R_OST, USER_ALPHA, "Ост", "wanderer", "familiar", "Знакомое лицо", "up")]
    r = apply(rep_world, character_id=ALPHA, region_id=R_OST, action=rc.ACTION_ADMIN, idem_key="t2", delta=-800)
    assert [(c.region_id, c.tier_after, c.direction) for c in r.tier_changes] == [
        (R_OST, "outlaw", "down"), (R_PASHNI, "watched", "down"), (R_HOLMY, "watched", "down")]   # -700 / -140
    assert sent_payloads(rep_world) == []                       # apply itself never publishes


def test_apply_materialises_pending_decay_first(rep_world):
    set_value(rep_world, ALPHA, R_DUNY, -100, decay_at=days_ago(2))
    r = apply(rep_world, character_id=ALPHA, region_id=R_DUNY, action=rc.ACTION_QUEST, idem_key="after-decay")
    assert r.changes[0].value_before == -80 and r.changes[0].value_after == -70
    log = log_rows(rep_world, ALPHA)
    assert [(x[2], x[7], x[8]) for x in log] == [("decay", 20, -80), ("quest_complete", 10, -70)]
    assert log[0][3].startswith(f"decay:{ALPHA}:{R_DUNY}:")


def test_decay_anchor_lifecycle(rep_world):
    def anchor():
        return q(rep_world, "SELECT decay_at FROM character_reputation WHERE character_id = :c AND region_id = :r",
                 c=GAMMA, r=R_DUNY)

    apply(rep_world, character_id=GAMMA, region_id=R_DUNY, action=rc.ACTION_CRIME, idem_key="c1")
    first = anchor()
    assert first is not None                                    # 0 -> -50: decay starts now
    apply(rep_world, character_id=GAMMA, region_id=R_DUNY, action=rc.ACTION_CRIME, idem_key="c2")
    assert anchor() == first                                    # still negative: anchor unchanged
    apply(rep_world, character_id=GAMMA, region_id=R_DUNY, action=rc.ACTION_ADMIN, idem_key="c3", delta=200)
    assert anchor() is None and value(rep_world, GAMMA, R_DUNY) == 100


def test_effective_reads_and_gates(rep_world):
    set_value(rep_world, ALPHA, R_OST, 350)
    set_value(rep_world, ALPHA, R_DUNY, -700, decay_at=days_ago(20))         # effective -500 (outcast)
    db = rep_world()
    try:
        assert reputation_crud.effective(db, ALPHA, R_DUNY) == -500
        assert reputation_crud.effective(db, ALPHA, R_HOLMY) == 0
        assert reputation_crud.effective(db, ALPHA, None) == 0
        assert reputation_crud.tier_of(db, ALPHA, R_OST).code == "trusted"
        assert reputation_crud.gate_failure(db, ALPHA, R_OST, "trusted") is None
        assert reputation_crud.gate_failure(db, ALPHA, R_OST, "defender") == "Нужна репутация: Заступник"
        assert reputation_crud.gate_failure(db, ALPHA, R_OST, None) is None
        assert reputation_crud.gate_failure(db, ALPHA, None, "legend") is None      # no region = open
        assert reputation_crud.refused_tier(db, ALPHA, R_DUNY) is None              # outcast still trades
        with pytest.raises(reputation_crud.ReputationError) as exc:
            reputation_crud.require_tier(db, ALPHA, R_OST, "legend")
        assert exc.value.status_code == 403
    finally:
        db.close()
    set_value(rep_world, ALPHA, R_DUNY, -700, decay_at=None)
    db = rep_world()
    try:
        assert reputation_crud.refused_tier(db, ALPHA, R_DUNY).code == "outlaw"
    finally:
        db.close()


def test_npc_gate_uses_the_npc_region(rep_world):
    exec_(rep_world, "UPDATE characters SET reputation_min_tier = 'familiar' WHERE id = :i", i=MERCHANT)
    db = rep_world()
    try:
        assert reputation_crud.npc_gate_failure(db, ALPHA, MERCHANT) == "Нужна репутация: Знакомое лицо"
    finally:
        db.close()
    set_value(rep_world, ALPHA, R_OST, 100)
    db = rep_world()
    try:
        assert reputation_crud.npc_gate_failure(db, ALPHA, MERCHANT) is None
        assert reputation_crud.npc_gate_failure(db, ALPHA, 999) is None
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- notifications

def _change(direction="up", user_id=USER_ALPHA, region="Ост", tier="Знакомое лицо"):
    return reputation_crud.TierChange(ALPHA, user_id, R_OST, region, "wanderer", "Скиталец", "familiar", tier,
                                      direction)


def test_payloads_and_messages_have_no_numbers():
    payloads = reputation_notify.build_payloads([_change("up"), _change("down", tier="Изгой"),
                                                 _change("decay", tier="На заметке"), _change(user_id=None),
                                                 _change(region=None)])
    assert [p["message"] for p in payloads] == [
        "Жители края «Ост» теперь считают вас: Знакомое лицо",
        "Жители края «Ост» стали относиться к вам хуже: теперь вы — Изгой",
        "Жители края «Ост» понемногу забывают ваши проступки: теперь вы — На заметке",
        "Жители края «этого края» теперь считают вас: Знакомое лицо",
    ]
    for p in payloads:
        assert p["target_type"] == "user" and p["target_value"] == USER_ALPHA and p["category"] == "progress"
        assert not any(ch.isdigit() for ch in p["message"])


def test_publish_is_best_effort(monkeypatch):
    def boom(_payloads):
        raise ConnectionError("rabbit down")

    monkeypatch.setattr(reputation_notify, "_send", boom)
    assert reputation_notify.publish_tier_changes([_change()]) == 0


def test_publish_skips_empty_and_npc_only(monkeypatch):
    calls = []
    monkeypatch.setattr(reputation_notify, "_send", calls.append)
    assert reputation_notify.publish_tier_changes([]) == 0
    assert reputation_notify.publish_tier_changes(None) == 0
    assert reputation_notify.publish_tier_changes([_change(user_id=None)]) == 0
    assert calls == []
    assert reputation_notify.publish_tier_changes([_change(), _change("down")]) == 2
    assert len(calls) == 1 and len(calls[0]) == 2
