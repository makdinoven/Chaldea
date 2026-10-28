"""FEAT-180 stage 6b: a shrine's 'regen' blessing (locations-service `house_buffs`)
multiplies rest by (1 + value) for the part of the settled stretch before it expires,
stacking with satiety and sleep like they stack with each other."""

from datetime import datetime, timedelta

import regen

T0 = datetime(2026, 10, 28, 12, 0, 0)


def h(n):
    return T0 + timedelta(hours=n)


def test_shrine_weights_rest_until_it_expires():
    # +10 % until hour 2, then plain rest up to hour 3.
    assert regen._effective_hours(T0, h(3), [], None, 0.0, None, 1.0, h(2), 0.10) == 2 * 1.1 + 1


def test_shrine_running_through_the_window_covers_all_of_it():
    assert regen._effective_hours(T0, h(2), [], None, 0.0, None, 1.0, h(2), 0.15) == 2 * 1.15


def test_shrine_stacks_with_satiety_and_sleep():
    # Satiety +50 % to hour 1, shrine +10 % to hour 2, asleep x2 from hour 1.
    total = regen._effective_hours(T0, h(3), [], h(1), 0.5, h(1), 2.0, h(2), 0.10)
    assert abs(total - (1 * 1.5 * 1.1 + 1 * 2.0 * 1.1 + 1 * 2.0)) < 1e-9


def test_busy_time_gives_nothing_with_a_blessing():
    assert regen._effective_hours(T0, h(2), [(T0, h(1))], None, 0.0, None, 1.0, h(2), 0.10) == 1.1


class _Rows:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Db:
    def __init__(self, row=None, fail=False):
        self.row, self.fail = row, fail

    def execute(self, *_a, **_k):
        if self.fail:
            raise RuntimeError("no such table: house_buffs")
        return _Rows(self.row)


def test_get_shrine_regen_reads_the_row_and_tolerates_missing_tables():
    assert regen.get_shrine_regen(_Db(row=(h(5), 0.15)), 1) == (h(5), 0.15)
    assert regen.get_shrine_regen(_Db(row=("2026-10-28 17:00:00", 0.05)), 1) == (h(5), 0.05)
    assert regen.get_shrine_regen(_Db(row=None), 1) == (None, 0.0)
    assert regen.get_shrine_regen(_Db(fail=True), 1) == (None, 0.0)


class _Attr:
    """A full-enough attributes row for settle_regen."""

    def __init__(self, anchor):
        self.character_id = 1
        self.regen_anchor_at = anchor
        for r in regen.REGEN_RESOURCES:
            setattr(self, f"current_{r}", 0)
            setattr(self, f"max_{r}", 1000)
            setattr(self, f"regen_carry_{r}", 0.0)


def test_settle_applies_an_expired_blessing_only_up_to_its_end(monkeypatch):
    monkeypatch.setattr(regen, "is_regen_eligible", lambda db, cid: True)
    monkeypatch.setattr(regen, "get_satiety", lambda db, cid: None)
    monkeypatch.setattr(regen, "load_busy_intervals", lambda db, cid, a, b: [])
    monkeypatch.setattr(regen, "get_sleep", lambda db, cid: (None, 1.0))
    seen = {}

    def _hours(anchor, now, busy, se, sb, asl, sf, shrine_end=None, shrine_bonus=0.0):
        seen.update(end=shrine_end, bonus=shrine_bonus)
        return 0.0

    monkeypatch.setattr(regen, "_effective_hours", _hours)
    # Expired before the anchor: clamped to the anchor, so no stretch gets the bonus.
    monkeypatch.setattr(regen, "get_shrine_regen", lambda db, cid: (T0 - timedelta(hours=1), 0.1))
    regen.settle_regen(None, _Attr(T0), now=h(3))
    assert seen == {"end": T0, "bonus": 0.1}
    # Still running past now: clamped to now (all the stretch gets it).
    monkeypatch.setattr(regen, "get_shrine_regen", lambda db, cid: (h(10), 0.1))
    regen.settle_regen(None, _Attr(T0), now=h(3))
    assert seen["end"] == h(3)
