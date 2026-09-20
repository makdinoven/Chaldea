"""A defender's own resistances must reach the damage formula.

`compute_damage_with_rolls` cuts damage by `percent_resists`, and that dict was
built by `build_percent_resist_buffs` — which reads only the temporary
`percent_resist*` modifiers that skills and items hang on a fighter mid-fight.
The permanent columns (`res_physical`, `res_fire`, … — strength, intelligence
and every `res_*_modifier` on a piece of gear) were never read in
battle-service at all. Strength and intelligence bought no defence, and armour
with resistances was decoration. Nothing raised; the numbers simply sat on the
profile.

`build_percent_resist_buffs` now sums both sources into the one percentage the
formula already understands, which keeps a NEGATIVE total meaning
vulnerability — the way Armorbreak, Freeze and Electrify already express it.
"""

import importlib.util
import os

import pytest

# Несколько наборов тестов подменяют sys.modules["buffs"] моком на время импорта,
# поэтому обычный `from buffs import ...` здесь получил бы мок и тихо проверял
# ничего. Грузим настоящий модуль по пути под своим именем — тот же приём, что
# в test_item_effects.py.
_BUFFS_PATH = os.path.join(os.path.dirname(__file__), "..", "buffs.py")
_spec = importlib.util.spec_from_file_location("buffs_resist_under_test", _BUFFS_PATH)
_buffs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_buffs)

RESISTED_DAMAGE_TYPES = _buffs.RESISTED_DAMAGE_TYPES
build_percent_resist_buffs = _buffs.build_percent_resist_buffs
assert not isinstance(build_percent_resist_buffs, __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock)


def test_permanent_resistance_reaches_the_dict():
    resists = build_percent_resist_buffs({}, {"res_fire": 12.5})
    assert resists["fire"] == pytest.approx(12.5)


def test_every_resisted_type_is_picked_up():
    """A type missing from RESISTED_DAMAGE_TYPES would be silently unresisted."""
    attrs = {f"res_{t}": 5.0 for t in RESISTED_DAMAGE_TYPES}
    resists = build_percent_resist_buffs({}, attrs)
    assert set(resists) == set(RESISTED_DAMAGE_TYPES)
    assert all(v == pytest.approx(5.0) for v in resists.values())


def test_permanent_and_combat_resistance_add_up():
    resists = build_percent_resist_buffs({"percent_resist_fire": 15.0}, {"res_fire": 10.0})
    assert resists["fire"] == pytest.approx(25.0)


def test_a_debuff_can_drive_the_total_negative():
    """Armorbreak passes a negative percent — the sum must stay a vulnerability."""
    resists = build_percent_resist_buffs({"percent_resist_physical": -30.0}, {"res_physical": 8.0})
    assert resists["physical"] == pytest.approx(-22.0)


def test_blanket_buff_lands_on_the_all_key():
    resists = build_percent_resist_buffs({"percent_resist": 10.0}, {"res_fire": 4.0})
    assert resists["all"] == pytest.approx(10.0)
    assert resists["fire"] == pytest.approx(4.0)


def test_zero_and_missing_resistances_are_omitted():
    """Keeps the log tidy: only meaningful entries end up in the dict."""
    resists = build_percent_resist_buffs({}, {"res_fire": 0.0, "res_ice": None})
    assert resists == {}


def test_unknown_attribute_keys_are_ignored():
    resists = build_percent_resist_buffs({}, {"res_effects": 30.0, "strength": 50, "res_fire": 3.0})
    # res_effects guards effect application, not damage — it must not land here.
    assert resists == {"fire": pytest.approx(3.0)}


@pytest.mark.parametrize("raw, resist_pct, expected", [
    (100.0, 25.0, 75.0),    # обычное сопротивление
    (100.0, 0.0, 100.0),
    (100.0, -30.0, 130.0),  # уязвимость = отрицательное сопротивление
    (100.0, 120.0, 0.0),    # сверхсопротивление не лечит
])
def test_the_formula_consumes_the_percentage_as_expected(raw, resist_pct, expected):
    """Documents the contract the dict feeds, straight from battle_engine."""
    final = max(0.0, raw * (1 - resist_pct / 100.0))
    assert final == pytest.approx(expected)
