"""FEAT-180 stage 6b: a character reading in a house library (`characters.reading_since`)
is activity-locked in battle-service like a sleeper, with its own reason and message."""

import os
import sys
from datetime import datetime

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import activity_lock  # noqa: E402

pytestmark = pytest.mark.real_activity_lock


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Db:
    def __init__(self, row):
        self.row, self.queries = row, []

    async def execute(self, query, params=None):
        self.queries.append(str(query))
        return _Result(self.row)


def test_reading_has_its_own_reason_and_message():
    lock = activity_lock.compute_lock(None, None, reading_since=datetime.utcnow())
    assert (lock["locked"], lock["reason"]) == (True, activity_lock.REASON_READING)
    assert activity_lock.lock_message(lock, subject="Ваш персонаж") == (
        "Ваш персонаж читает — сначала нужно закончить чтение")


@pytest.mark.asyncio
async def test_the_query_reads_the_reading_column():
    db = _Db((None, None, None, "2026-10-28 10:00:00"))
    with pytest.raises(HTTPException) as exc:
        await activity_lock.check_not_activity_locked(db, 1)
    assert exc.value.status_code == 409 and "читает" in exc.value.detail
    assert "reading_since" in db.queries[0]


@pytest.mark.asyncio
async def test_a_short_row_reads_as_not_reading():
    assert (await activity_lock.get_activity_lock(_Db((None, None)), 1))["locked"] is False
