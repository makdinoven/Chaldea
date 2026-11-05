"""FEAT-201 follow-up: a stat upgrade must not accept negative values.

Before the fix `{"strength": -20, "agility": 21}` spent 1 free point and moved
20 points from strength to agility.
"""
import pytest
from pydantic import ValidationError

from schemas import StatsUpgradeRequest

STATS = ["strength", "agility", "intelligence", "endurance", "health", "energy",
         "mana", "stamina", "charisma", "luck", "stealth"]


@pytest.mark.parametrize("stat", STATS)
def test_negative_value_is_rejected(stat):
    with pytest.raises(ValidationError):
        StatsUpgradeRequest(**{stat: -1})


def test_zero_and_positive_are_accepted():
    req = StatsUpgradeRequest(strength=0, agility=3, stealth=2)
    assert (req.strength, req.agility, req.stealth) == (0, 3, 2)


def test_point_shuffling_exploit_is_rejected():
    with pytest.raises(ValidationError):
        StatsUpgradeRequest(strength=-20, agility=21)
