"""FEAT-180: a character asleep in a house bedroom is activity-locked until it wakes."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import activity_lock


def test_asleep_locks_with_its_own_reason():
    lock = activity_lock.compute_lock(None, None, asleep_since=datetime.utcnow())
    assert (lock["locked"], lock["reason"]) == (True, activity_lock.REASON_ASLEEP)
    assert "спит" in activity_lock.lock_message(lock)


def test_unconscious_and_dungeon_win_over_sleep():
    now = datetime.utcnow()
    knocked = activity_lock.compute_lock(None, now + timedelta(hours=1), asleep_since=now)
    assert knocked["reason"] == activity_lock.REASON_UNCONSCIOUS
    assert activity_lock.compute_lock(7, None, asleep_since=now)["reason"] == activity_lock.REASON_DUNGEON


def test_lock_for_character_reads_the_column():
    sleeper = SimpleNamespace(dungeon_session_id=None, unconscious_until=None, asleep_since=datetime.utcnow())
    assert activity_lock.lock_for_character(sleeper)["reason"] == activity_lock.REASON_ASLEEP
    awake = SimpleNamespace(dungeon_session_id=None, unconscious_until=None)
    assert activity_lock.lock_for_character(awake)["locked"] is False
