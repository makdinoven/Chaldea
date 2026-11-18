"""FEAT-216 customs & smuggling — pure maths and constants (no I/O, no DB, no clock, no RNG).

* Customs posts are ``Locations.is_customs`` (locations-service). A legal foreign physical caravan bound for a country
  with posts is routed through one of them and stops there (``customs_state`` pending -> inspecting -> cleared),
  paying its duty physically (op ``caravan_duty``). Contraband caravans avoid every post.
* Detection (§3.0 A13, "как у стражи"): the officer's «внимательность» is his own stealth put through the same curve
  as the guards' stealth maths (``shadow_core.stealth_reduction_pct``); the caravan's stealth is a base param plus the
  best effective stealth of its active player escorts. The roll itself is ``law_core.roll_succeeds``.
* A contraband caravan is illegal in country X iff X is its destination country or its goods group is banned in X
  (§3.0 A12).
"""

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Iterable, List, Mapping, Optional, Tuple

import law_core

# econ_caravan_raids.kind — one fight per caravan whatever the kind (uq_econ_caravan_raids_caravan)
KIND_RAID = "raid"          # FEAT-211 bandits
KIND_CUSTOMS = "customs"    # a player customs officer (+ his free squad) vs the caravan guards and escorts
KIND_PATROL = "patrol"      # guard NPCs at the location vs the player escorts (server-started)
KINDS = (KIND_RAID, KIND_CUSTOMS, KIND_PATROL)
ENFORCEMENT_KINDS = (KIND_CUSTOMS, KIND_PATROL)

# econ_caravans.customs_state (NULL = no post on the route)
STATE_PENDING = "pending"
STATE_INSPECTING = "inspecting"
STATE_CLEARED = "cleared"
STATES = (STATE_PENDING, STATE_INSPECTING, STATE_CLEARED)
# the duty left the escrow at the post (econ_caravan.settled_duty)
DUTY_SETTLED_STATES = (STATE_INSPECTING, STATE_CLEARED)

# econ_caravans.cancel_reason of a confiscated caravan
REASON_SEIZED_CUSTOMS = "seized_customs"
REASON_SEIZED_PATROL = "seized_patrol"
SEIZURE_REASONS = (REASON_SEIZED_CUSTOMS, REASON_SEIZED_PATROL)

# econ_customs_officers.status
OFFICER_ACTIVE = "active"
OFFICER_RESIGNED = "resigned"

# characters.npc_role of the «Таможенник» NPC
CUSTOMS_ROLE = "customs"

# law_crimes.crime_type of a seized smuggler escort
CRIME_SMUGGLING = law_core.CRIME_SMUGGLING

MAX_BANNED_GROUPS = 64

_HUNDRED = Decimal(100)
_CENT = Decimal("0.01")


def _dec(value) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _clamp_pct(value) -> Decimal:
    return max(Decimal(0), min(_HUNDRED, _dec(value)))


# --------------------------------------------------------------------------------------------------- detection

def detection_chance(base, attention_pct, reduction_pct, lo, hi) -> Decimal:
    """A customs officer notices a contraband caravan:
    ``clamp(base × (1 + attention / 100) × (1 − reduction / 100), lo, hi)`` (percent, 2 decimals).
    ``attention_pct`` = the officer's stealth through ``stealth_reduction_pct``; ``reduction_pct`` = the caravan's
    stealth through the same curve. ``lo > hi`` is treated as ``lo = hi``."""
    value = _dec(base)
    value *= (_HUNDRED + max(Decimal(0), _dec(attention_pct))) / _HUNDRED
    value *= (_HUNDRED - _clamp_pct(reduction_pct)) / _HUNDRED
    high = _clamp_pct(hi)
    low = min(_clamp_pct(lo), high)
    value = max(low, min(high, value))
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def patrol_chance(base, reduction_pct, hi) -> Decimal:
    """Guards at a location notice a contraband caravan: ``clamp(base × (1 − reduction / 100), 0, hi)``
    (percent, 2 decimals)."""
    value = _dec(base) * (_HUNDRED - _clamp_pct(reduction_pct)) / _HUNDRED
    value = max(Decimal(0), min(_clamp_pct(hi), value))
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def caravan_stealth(base, escort_effective_stealths: Iterable = ()) -> int:
    """A contraband caravan's stealth: the base param plus the best effective stealth of its active escorts
    (none / negative values count as 0)."""
    best = 0
    for value in escort_effective_stealths or ():
        best = max(best, int(_dec(value).to_integral_value(rounding=ROUND_FLOOR)))
    return max(0, int(_dec(base).to_integral_value(rounding=ROUND_FLOOR))) + max(0, best)


# --------------------------------------------------------------------------------------------------- legality

def illegal_in(country_id: Optional[int], caravan_to_country: Optional[int], group_code: Optional[str],
               bans: Optional[Mapping[int, Iterable[str]]]) -> bool:
    """Is a contraband caravan (bound for ``caravan_to_country``, carrying ``group_code``) illegal in ``country_id``?
    Yes in its destination country and in every country that bans the group; no country → never."""
    if country_id is None:
        return False
    country_id = int(country_id)
    if caravan_to_country is not None and country_id == int(caravan_to_country):
        return True
    banned = (bans or {}).get(country_id) or ()
    return bool(group_code) and group_code in banned


def is_banned(bans: Optional[Mapping[int, Iterable[str]]], country_id: Optional[int],
              group_code: Optional[str]) -> bool:
    """Does ``country_id`` forbid importing ``group_code``?"""
    if country_id is None or not group_code:
        return False
    return group_code in ((bans or {}).get(int(country_id)) or ())


# --------------------------------------------------------------------------------------------------- money

def officer_split(pool: int, n: int) -> Tuple[int, int]:
    """The officers' pool split among ``n`` players: ``(per_head, remainder)`` with ``per_head = floor(pool / n)``;
    ``n <= 0`` → ``(0, pool)`` (the whole pool stays with the country)."""
    pool = max(0, int(pool or 0))
    n = int(n or 0)
    if n <= 0:
        return 0, pool
    each = pool // n
    return each, pool - each * n


def officer_pool(rest: int, share) -> int:
    """``floor(rest × share)``, never above ``rest`` nor below 0."""
    rest = max(0, int(rest or 0))
    value = int((Decimal(rest) * max(Decimal(0), _dec(share))).to_integral_value(rounding=ROUND_FLOOR))
    return max(0, min(rest, value))


# --------------------------------------------------------------------------------------------------- admin

def normalize_ban_codes(codes: Optional[Iterable[str]], known: Iterable[str]) -> List[str]:
    """Validate a country's banned goods groups: stripped, deduplicated, each a known code, at most
    :data:`MAX_BANNED_GROUPS`. Returns them in the order of ``known``. Raises ``ValueError(code)`` on an unknown
    code (``ValueError("too_many")`` on too many)."""
    known_list = [str(k) for k in known]
    known_set = set(known_list)
    wanted = set()
    for code in codes or ():
        code = (code or "").strip()
        if not code:
            continue
        if code not in known_set:
            raise ValueError(code)
        wanted.add(code)
    if len(wanted) > MAX_BANNED_GROUPS:
        raise ValueError("too_many")
    return [code for code in known_list if code in wanted]
