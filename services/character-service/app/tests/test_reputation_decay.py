"""FEAT-197 QA (task 9): the hourly decay pass (§3.6) and its hook in the economy scheduler.

* runs even when the economy tick is disabled (it is called before ``is_tick_enabled``);
* throttled by ``reputation_settings.decay_last_run_at`` (conditional UPDATE, 1 h);
* materialises only on a tier change / reaching 0 / >= DECAY_MIN_POINTS, journals ``decay``, notifies after commit;
* only negative values decay; a zero rate does nothing.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import econ_scheduler
import econ_tick
import reputation_crud
import reputation_decay
from tests.reputation_world import (  # noqa: F401  (rep_world is a fixture)
    ALPHA, BETA, GAMMA, R_DUNY, R_OST, R_PASHNI, USER_ALPHA, days_ago, exec_, log_rows, q, rep_world, rows,
    sent_payloads, set_value, value,
)


def now():
    return reputation_crud.now_utc()


def test_pass_materialises_tier_changes_and_notifies(rep_world):
    set_value(rep_world, ALPHA, R_OST, -320, decay_at=days_ago(3))      # -290: Изгой -> На заметке
    set_value(rep_world, BETA, R_OST, -40, decay_at=days_ago(5))        # reaches 0
    set_value(rep_world, GAMMA, R_DUNY, -500, decay_at=days_ago(1))     # 10 points, same tier: left lazy
    set_value(rep_world, ALPHA, R_PASHNI, 200)                          # positive never decays
    stats = reputation_decay.run_pass(rep_world, now())
    assert stats == {"ran": True, "rows": 3, "tier_changes": 1}
    assert value(rep_world, ALPHA, R_OST) == -290
    assert value(rep_world, BETA, R_OST) == 0
    assert q(rep_world, "SELECT decay_at FROM character_reputation WHERE character_id = :c", c=BETA) is None
    assert value(rep_world, GAMMA, R_DUNY) == -500                      # stored value lags, readers use effective
    assert value(rep_world, ALPHA, R_PASHNI) == 200
    assert [(x[1], x[2], x[7], x[8], x[9], x[10]) for x in log_rows(rep_world, ALPHA)] == [
        (R_OST, "decay", 30, -290, "outcast", "watched")]
    assert len(log_rows(rep_world, BETA)) == 1 and log_rows(rep_world, GAMMA) == []
    assert sent_payloads(rep_world) == [{
        "target_type": "user", "target_value": USER_ALPHA, "category": "progress",
        "message": "Жители края «Ост» понемногу забывают ваши проступки: теперь вы — На заметке"}]


def test_pass_materialises_big_accruals_without_tier_change(rep_world):
    set_value(rep_world, GAMMA, R_DUNY, -580, decay_at=days_ago(5))     # 50 points, still Изгой
    reputation_decay.run_pass(rep_world, now())
    assert value(rep_world, GAMMA, R_DUNY) == -530
    assert sent_payloads(rep_world) == []


def test_pass_keeps_fractions_between_runs(rep_world):
    anchor = days_ago(10) - timedelta(hours=12)                         # 105 points accrued
    set_value(rep_world, ALPHA, R_OST, -600, decay_at=anchor)
    t = now()
    reputation_decay.run_pass(rep_world, t)
    assert value(rep_world, ALPHA, R_OST) == -495
    db = rep_world()
    try:
        assert reputation_crud.effective(db, ALPHA, R_OST, now=t) == -495
        assert reputation_crud.effective(db, ALPHA, R_OST, now=t + timedelta(hours=12)) == -490
    finally:
        db.close()


def test_pass_is_throttled_hourly(rep_world):
    set_value(rep_world, ALPHA, R_OST, -320, decay_at=days_ago(3))
    t = now()
    assert reputation_decay.run_pass(rep_world, t)["ran"] is True
    set_value(rep_world, BETA, R_OST, -320, decay_at=days_ago(3))
    assert reputation_decay.run_pass(rep_world, t + timedelta(minutes=59))["ran"] is False
    assert value(rep_world, BETA, R_OST) == -320
    assert reputation_decay.run_pass(rep_world, t + timedelta(minutes=60))["ran"] is True
    assert value(rep_world, BETA, R_OST) == -290


def test_claim_without_settings_row_does_not_run(rep_world):
    exec_(rep_world, "DELETE FROM reputation_settings")
    set_value(rep_world, ALPHA, R_OST, -320, decay_at=days_ago(3))
    assert reputation_decay.run_pass(rep_world, now())["ran"] is False
    assert value(rep_world, ALPHA, R_OST) == -320


def test_zero_rate_does_nothing(rep_world):
    exec_(rep_world, "UPDATE reputation_settings SET decay_per_day = 0")
    set_value(rep_world, ALPHA, R_OST, -320, decay_at=days_ago(30))
    stats = reputation_decay.run_pass(rep_world, now())
    assert stats["ran"] is True and stats["rows"] == 0
    assert value(rep_world, ALPHA, R_OST) == -320


def test_pass_walks_batches(rep_world, monkeypatch):
    monkeypatch.setattr(reputation_decay, "BATCH_SIZE", 2)
    for cid, rid in ((ALPHA, R_OST), (ALPHA, R_PASHNI), (BETA, R_OST), (GAMMA, R_DUNY), (GAMMA, 12)):
        set_value(rep_world, cid, rid, -40, decay_at=days_ago(5))
    stats = reputation_decay.run_pass(rep_world, now())
    assert stats["rows"] == 5
    assert rows(rep_world, "SELECT COUNT(*) FROM character_reputation WHERE value <> 0") == [(0,)]


def test_failed_batch_is_rolled_back_and_the_pass_continues(rep_world, monkeypatch):
    monkeypatch.setattr(reputation_decay, "BATCH_SIZE", 1)
    set_value(rep_world, ALPHA, R_OST, -40, decay_at=days_ago(5))
    set_value(rep_world, BETA, R_OST, -40, decay_at=days_ago(5))
    real = reputation_decay._process_batch
    calls = []

    def flaky(db, keys, *a, **k):
        calls.append(keys)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return real(db, keys, *a, **k)

    monkeypatch.setattr(reputation_decay, "_process_batch", flaky)
    stats = reputation_decay.run_pass(rep_world, now())
    assert stats["rows"] == 1
    assert value(rep_world, ALPHA, R_OST) == -40 and value(rep_world, BETA, R_OST) == 0


def test_rabbit_outage_does_not_break_the_pass(rep_world, monkeypatch):
    import reputation_notify
    monkeypatch.setattr(reputation_notify, "_send", MagicMock(side_effect=ConnectionError("down")))
    set_value(rep_world, ALPHA, R_OST, -320, decay_at=days_ago(3))
    assert reputation_decay.run_pass(rep_world, now())["tier_changes"] == 1
    assert value(rep_world, ALPHA, R_OST) == -290


# --------------------------------------------------------------------------------------------- scheduler hook

def test_scheduler_runs_decay_even_with_the_economy_tick_disabled(rep_world, monkeypatch):
    set_value(rep_world, ALPHA, R_OST, -320, decay_at=days_ago(3))
    monkeypatch.setattr(econ_tick, "is_tick_enabled", lambda _s: False)
    run_tick = MagicMock()
    monkeypatch.setattr(econ_tick, "run_tick", run_tick)
    assert econ_scheduler.run_scheduled_once(rep_world) is None
    run_tick.assert_not_called()
    assert value(rep_world, ALPHA, R_OST) == -290


def test_scheduler_survives_a_decay_failure(rep_world, monkeypatch):
    monkeypatch.setattr(reputation_decay, "run_pass", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(econ_tick, "is_tick_enabled", lambda _s: False)
    assert econ_scheduler.run_scheduled_once(rep_world) is None


def test_manual_economy_tick_does_not_run_decay(monkeypatch):
    """§3.6: only the scheduler calls the pass — econ_tick itself never imports it."""
    import inspect
    assert "reputation_decay" not in inspect.getsource(econ_tick)
