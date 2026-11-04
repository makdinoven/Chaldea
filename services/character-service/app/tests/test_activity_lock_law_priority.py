"""FEAT-198 QA (task 10): the canonical activity_lock (character-service) — the full reason
priority matrix jail > law_encounter > unconscious > dungeon > asleep > reading, the
`lock_for_character` read of the two new columns and the relative messages. The three copies
(locations, battle, inventory) run the same matrix in their own suites."""

import itertools
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import activity_lock  # noqa: E402

REASONS = ["jail", "law_encounter", "unconscious", "dungeon", "asleep", "reading"]


def _character(present):
    later = datetime.utcnow() + timedelta(hours=3)
    return SimpleNamespace(
        jailed_until=later if "jail" in present else None,
        law_encounter_id=5 if "law_encounter" in present else None,
        unconscious_until=later if "unconscious" in present else None,
        dungeon_session_id=7 if "dungeon" in present else None,
        asleep_since=datetime.utcnow() if "asleep" in present else None,
        reading_since=datetime.utcnow() if "reading" in present else None,
    )


@pytest.mark.parametrize(
    "present",
    [set(c) for n in range(len(REASONS) + 1) for c in itertools.combinations(REASONS, n)],
    ids=lambda s: "+".join(sorted(s)) or "free",
)
def test_priority_matrix_through_lock_for_character(present):
    lock = activity_lock.lock_for_character(_character(present))
    expected = next((r for r in REASONS if r in present), None)
    assert lock["reason"] == expected
    assert lock["locked"] is (expected is not None)
    assert lock["law_encounter_id"] == (5 if expected == "law_encounter" else None)
    assert (lock["until"] is not None) is (expected in ("jail", "unconscious"))


def test_served_term_with_pending_encounter_is_the_encounter():
    c = _character({"law_encounter"})
    c.jailed_until = datetime.utcnow() - timedelta(seconds=1)
    assert activity_lock.lock_for_character(c)["reason"] == "law_encounter"


def test_messages_have_no_absolute_time():
    jail = activity_lock.lock_for_character(_character({"jail"}))
    msg = activity_lock.lock_message(jail, subject="Арья")
    assert msg.startswith("Арья в тюрьме — осталось ")
    assert "МСК" not in msg and ":" not in msg
    enc = activity_lock.lock_for_character(_character({"law_encounter"}))
    assert activity_lock.lock_message(enc) == "Персонаж остановлен стражей — сначала нужно решить, как поступить"
