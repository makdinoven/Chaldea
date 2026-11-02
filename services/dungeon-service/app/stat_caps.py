"""FEAT-195: soft/hard caps on character stats (diminishing returns).

CANONICAL FILE: services/character-attributes-service/app/stat_caps.py
Byte-identical copies live in battle-service and dungeon-service
(checked by scripts/check_econ_copies.sh). Edit the canonical file and copy
it byte-for-byte. The charisma discount in econ_core.py has its own Decimal
implementation of the same piecewise function; the frontend mirror is
src/utils/statCaps.ts.

eff(x) is applied to the TOTAL of a stat (points + gear + food + perks +
battle buffs), never to each source separately. The stat number itself is not
changed - only what it converts into (resists, dodge, crit, max resources,
damage, initiative, luck bonuses, charisma discount, dungeon checks).
"""

SOFT_CAP = 100          # full effect up to here
HARD_CAP = 200          # half effect between SOFT_CAP and HARD_CAP
SOFT_RATE = 0.5         # effect per point between SOFT_CAP and HARD_CAP
HARD_RATE = 0.25        # quarter effect above HARD_CAP


def effective_stat(value) -> float:
    """eff(x): x<=100 -> x; 100<x<=200 -> 100+(x-100)*0.5; x>200 -> 150+(x-200)*0.25.

    None/non-numeric -> 0.0. Negative values are linear (x).
    """
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        x = float(value)
    except (TypeError, ValueError):
        return 0.0
    if x != x:  # NaN
        return 0.0
    if x <= SOFT_CAP:
        return x
    if x <= HARD_CAP:
        return SOFT_CAP + (x - SOFT_CAP) * SOFT_RATE
    return SOFT_CAP + (HARD_CAP - SOFT_CAP) * SOFT_RATE + (x - HARD_CAP) * HARD_RATE


def effective_delta(old, new) -> float:
    """eff(new) - eff(old): what a change of a stat from old to new is worth."""
    return effective_stat(new) - effective_stat(old)
