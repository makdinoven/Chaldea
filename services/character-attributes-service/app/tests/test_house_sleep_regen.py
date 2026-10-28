"""FEAT-180 stage 2: sleeping in a house bedroom multiplies rest.

`characters.asleep_since` / `sleep_regen_factor` (character-service columns,
set by locations-service) weight the rest hours since falling asleep; satiety
still adds on top, busy time still gives nothing.
"""

from datetime import datetime, timedelta

import regen

T0 = datetime(2026, 10, 27, 12, 0, 0)


def h(n):
    return T0 + timedelta(hours=n)


def test_awake_rest_is_plain():
    assert regen._effective_hours(T0, h(2), [], None, 0.0, None, 1.0) == 2.0


def test_sleep_multiplies_only_the_hours_since_falling_asleep():
    assert regen._effective_hours(T0, h(3), [], None, 0.0, h(1), 2.5) == 1.0 + 2 * 2.5


def test_sleep_and_satiety_stack():
    # Satiety (+50%) ends at hour 2; asleep from hour 1 with x2.
    total = regen._effective_hours(T0, h(3), [], h(2), 0.5, h(1), 2.0)
    assert total == 1 * 1.5 + 1 * 1.5 * 2.0 + 1 * 2.0


def test_busy_time_gives_nothing_even_asleep():
    busy = [(h(1), h(2))]
    assert regen._effective_hours(T0, h(3), busy, None, 0.0, T0, 2.0) == 2 * 2.0


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
            raise RuntimeError("no such column")
        return _Rows(self.row)


def test_get_sleep_reads_the_columns_and_tolerates_old_schemas():
    assert regen.get_sleep(_Db(row=(h(1), 2.5)), 1) == (h(1), 2.5)
    assert regen.get_sleep(_Db(row=(None, None)), 1) == (None, 1.0)
    assert regen.get_sleep(_Db(fail=True), 1) == (None, 1.0)
