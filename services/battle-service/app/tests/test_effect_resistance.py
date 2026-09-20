"""Effect resistance in battle must read `res_effects`, not raw endurance.

The profile shows «Сопр. эффектам» = endurance ×0.2 + luck ×0.1, plus whatever
equipment and perks add through `res_effects_modifier`
(`character-attributes-service/app/crud.py::compute_derived_stats`). Battle,
however, recomputed the penalty itself from the defender's raw `endurance`,
which meant two things silently: luck bought nothing against being stunned or
poisoned, and every item with `res_effects_modifier` was decorative in combat.
Nothing raised — the number was simply never read.

These tests pin the stat that `_filter_effects_by_chance` consumes. A revert to
`endurance` fails `test_ignores_raw_endurance`, because there the two values
disagree on purpose.
"""

from unittest.mock import patch

import pytest

import main


def _effect(chance):
    return {"effect_name": "Stun", "chance": chance, "duration": 2, "magnitude": 0}


def _filter(effects, luck_bonus=0.0, res_effects=0.0):
    return main._filter_effects_by_chance(effects, luck_bonus, res_effects)


@patch("main.roll_chance")
def test_resistance_is_subtracted_from_the_chance(roll):
    """80 % effect against 30 resistance rolls at 50 %."""
    roll.return_value = True
    _filter([_effect(80)], res_effects=30.0)
    roll.assert_called_once_with(50.0)


@patch("main.roll_chance")
def test_luck_and_resistance_meet_in_one_number(roll):
    roll.return_value = True
    _filter([_effect(60)], luck_bonus=5.0, res_effects=20.0)
    roll.assert_called_once_with(45.0)


@patch("main.roll_chance")
def test_ignores_raw_endurance(roll):
    """The regression guard.

    A defender with endurance 10 and luck 10 has res_effects 3.0 (10×0.2 +
    10×0.1). The old code read endurance and doubled it to 2.0. Feeding the
    stat the caller now passes must produce 3.0 of resistance, not 2.0 — and
    certainly not 10×0.2 of whatever is handed in.
    """
    roll.return_value = True
    _filter([_effect(50)], res_effects=3.0)
    roll.assert_called_once_with(47.0)
    assert roll.call_args[0][0] != 48.0, "resistance was re-derived, not used as given"


@patch("main.roll_chance")
def test_chance_never_goes_negative(roll):
    roll.return_value = False
    _filter([_effect(10)], res_effects=90.0)
    roll.assert_called_once_with(0)


@patch("main.roll_chance")
def test_only_effects_that_pass_are_returned(roll):
    roll.side_effect = [True, False, True]
    kept = _filter([_effect(50), _effect(50), _effect(50)], res_effects=10.0)
    assert len(kept) == 2


@pytest.mark.parametrize("value", [None, 0, 0.0])
def test_missing_resistance_is_treated_as_zero(value):
    """An attributes payload without the key must not crash the turn."""
    with patch("main.roll_chance") as roll:
        roll.return_value = True
        _filter([_effect(70)], res_effects=value)
        roll.assert_called_once_with(70)
