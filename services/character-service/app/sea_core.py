"""FEAT-213 sea routes — pure rules (no DB, no clock; features/FEAT-213 §3.4, §3.5). FEAT-214 adds the storm /
raid helpers (§3.4 of FEAT-214); their only RNG is the patchable :func:`weather_rng` seam.

A ship is a real location (its deck). It sails a line of ports ``stops[0..n-1]`` (n >= 2): there-and-back by default
(0,1,…,n-1,n-2,…,0,1,…) or a loop (0,1,…,n-1,0,…). Every departure is a **trip**; ``trip_no`` counts the departures
made, so the next departure is always ``trip_no + 1``. A pass (ticket / sailor job / stowaway attempt) covers trips
``first_trip..last_trip``. A leg = the zones from the port zone of one stop to the port zone of the next one
(both inclusive); its duration is ``len(path) × zone_minutes``.
"""

import math
import random
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import caravan_route

CAPTAIN_ROLE = "captain"

# sea_ships.status
STATUS_DOCKED = "docked"
STATUS_SAILING = "sailing"

# sea_ships.blocked_reason
BLOCKED_NO_PATH = "no_path"
BLOCKED_NO_VALID_STOP = "no_valid_stop"
BLOCKED_NO_DECK = "no_deck"

# sea_passes.kind
KIND_TICKET = "ticket"
KIND_SAILOR = "sailor"
KIND_STOWAWAY = "stowaway"
PASS_KINDS = (KIND_TICKET, KIND_SAILOR, KIND_STOWAWAY)

# sea_passes.status
PASS_ACTIVE = "active"
PASS_COMPLETED = "completed"     # ride done / ended by an admin route change
PASS_BURNT = "burnt"             # ticket holder not aboard at departure — no refund («сам виноват»)
PASS_ASHORE = "ashore"           # sailor who did not work, put ashore
PASS_CAUGHT = "caught"           # stowaway caught by the crew
PASS_REFUNDED = "refunded"       # ship removed / deactivated / route changed before the pass started
PASS_EXPIRED = "expired"         # sailor / stowaway holder not aboard at departure
PASS_STATUSES = (PASS_ACTIVE, PASS_COMPLETED, PASS_BURNT, PASS_ASHORE, PASS_CAUGHT, PASS_REFUNDED, PASS_EXPIRED)

DIRECTION_FORWARD = 1
DIRECTION_BACKWARD = -1

# admin ranges (§3.3); the admin API (T3) validates against them
NAME_MAX = 100
CAPACITY_RANGE = (0, 200)
CREW_SLOTS_RANGE = (0, 20)
BOARDING_MINUTES_RANGE = (1, 1440)
ZONE_MINUTES_RANGE = (1, 1440)
FARE_RANGE = (0, 1_000_000)
STOPS_RANGE = (2, 30)
SAILOR_POST_MIN_CHARS_RANGE = (300, 20000)
STOWAWAY_BASE_PCT_RANGE = (0, 100)
STOWAWAY_WANTED_POINTS_RANGE = (1, 1000)
PATH_MAX_ZONES_RANGE = (10, 1000)

DEFAULT_SAILOR_POST_MIN_CHARS = 800
DEFAULT_PATH_MAX_ZONES = 200

# ---------------------------------------------------------------------------------------------------------------------
# FEAT-214 storms and raids (§3.3, §3.4)
# ---------------------------------------------------------------------------------------------------------------------

# sea_storms.status / source
STORM_ACTIVE = "active"
STORM_ENDED = "ended"
STORM_AUTO = "auto"
STORM_ADMIN = "admin"

# sea_raids.status
RAID_STARTING = "starting"
RAID_FIGHTING = "fighting"
RAID_WON = "won"
RAID_LOST = "lost"
RAID_ABORTED = "aborted"
RAID_EXPIRED = "expired"
RAID_ACTIVE_STATUSES = (RAID_STARTING, RAID_FIGHTING)
RAID_FINAL_STATUSES = (RAID_WON, RAID_LOST, RAID_ABORTED, RAID_EXPIRED)

SEA_RAID_TEAM_MAX = 5            # mirrors battle-service BATTLE_MAX_TEAM_SIZE
SEASONS = ("spring", "summer", "autumn", "winter")
MINUTES_PER_HOUR = 60

# admin ranges (§3.3); the admin API validates against them
STORM_MINUTES_RANGE = (10, 1440)
STORM_MOVE_PCT_RANGE = (0, 100)
STORM_MAX_MOVES_RANGE = (0, 10)
STORM_SLOW_MULT_RANGE = (1, 10)
STORM_DRIFT_PCT_RANGE = (0, 100)
STORM_HP_PCT_RANGE = (0, 100)
STORM_STAMINA_PCT_RANGE = (0, 100)
STORM_POSTPONE_MINUTES_RANGE = (1, 240)
STORM_POSTPONE_MAX_MINUTES_RANGE = (0, 1440)
STORM_SAILOR_RELIEF_PCT_RANGE = (0, 100)
SEASON_MULT_RANGE = (0, 10)
RAID_CHANCE_MULT_RANGE = (0, 10)
RAID_HOLD_MAX_MINUTES_RANGE = (0, 1440)
RAID_REPELLED_DELAY_MINUTES_RANGE = (0, 120)
STORM_CHANCE_PER_HOUR_RANGE = (0, 100)
STORM_RADIUS_RANGE = (0, 5)

# leg problems (admin preview / blocked reasons)
LEG_NO_ZONE = "no_zone"            # an end port has no (valid) sea zone
LEG_NO_PATH = "no_path"            # no zone path between the two ports
LEG_BAD_OVERRIDE = "bad_override"  # the manual path is not a valid zone chain (the BFS path is used instead)

_TAG_RE = re.compile(r"<[^>]*>")


def plain_length(html: Optional[str]) -> int:
    """Length of a post after stripping HTML tags (the regex of LS ``crud.strip_html_tags``)."""
    return len(_TAG_RE.sub("", html or "").strip())


# =====================================================================================================================
# stop sequence and trips
# =====================================================================================================================

def next_stop(index: int, direction: int, n: int, is_loop: bool) -> Tuple[int, int]:
    """The stop after ``index`` and the direction of that move. There-and-back flips at the ends."""
    if n < 2:
        return index, direction
    if is_loop:
        return (index + 1) % n, DIRECTION_FORWARD
    direction = DIRECTION_FORWARD if direction >= 0 else DIRECTION_BACKWARD
    j = index + direction
    if j < 0 or j >= n:
        direction = -direction
        j = index + direction
    return j, direction


def next_valid_stop(index: int, direction: int, n: int, is_loop: bool,
                    valid: Iterable[int]) -> Optional[Tuple[int, int, int]]:
    """``(stop, direction, skipped)`` — the next stop of the sequence that is valid (invalid ones are skipped, §3.10),
    or None when no other valid stop exists. ``skipped`` = how many invalid stops were passed over."""
    valid_set = {int(v) for v in valid}
    i, d = index, direction
    for skipped in range(2 * max(n, 1) + 1):
        i, d = next_stop(i, d, n, is_loop)
        if i in valid_set and i != index:
            return i, d, skipped
        if n < 2:
            break
    return None


@dataclass(frozen=True)
class Trip:
    trip: int            # trip number (departure counter)
    from_idx: int
    to_idx: int
    direction: int       # direction of this move
    adjacent: bool       # to_idx is the immediate next stop (the leg override applies)


def future_trips(start_idx: int, direction: int, n: int, is_loop: bool, first_trip: int, count: int,
                 valid: Optional[Iterable[int]] = None) -> List[Trip]:
    """The next ``count`` trips starting with trip ``first_trip`` from stop ``start_idx`` (docked: ``stop_index``;
    sailing: ``next_stop_index``). Invalid stops (not in ``valid``) are skipped; stops when no valid one is left."""
    valid_list = list(range(n)) if valid is None else [int(v) for v in valid]
    out: List[Trip] = []
    i, d = int(start_idx), int(direction or DIRECTION_FORWARD)
    for k in range(max(0, int(count))):
        nxt = next_valid_stop(i, d, n, is_loop, valid_list)
        if nxt is None:
            break
        j, d2, skipped = nxt
        out.append(Trip(int(first_trip) + k, i, j, d2, skipped == 0))
        i, d = j, d2
    return out


def override_for(from_idx: int, to_idx: int, n: int, is_loop: bool,
                 overrides: Mapping[int, Optional[Sequence[int]]]) -> Optional[List[int]]:
    """The manual zone path of an adjacent leg: forward i -> i+1 uses stops[i]; the reverse leg i+1 -> i of
    there-and-back uses stops[i] reversed; a loop's last -> first uses stops[n-1]."""
    if is_loop and from_idx == n - 1 and to_idx == 0:
        path = overrides.get(n - 1)
        return [int(z) for z in path] if path else None
    if to_idx == from_idx + 1:
        path = overrides.get(from_idx)
        return [int(z) for z in path] if path else None
    if to_idx == from_idx - 1 and not is_loop:
        path = overrides.get(to_idx)
        return [int(z) for z in reversed(list(path))] if path else None
    return None


def override_problem(path: Optional[Sequence[int]], start_zone: Optional[int], goal_zone: Optional[int],
                     adj: Mapping[int, Sequence[int]], zone_ids: Set[int], max_zones: int) -> Optional[str]:
    """None when the manual path is a valid zone chain start_zone … goal_zone (all zones, consecutive ones adjacent,
    at most ``max_zones`` entries), else ``LEG_BAD_OVERRIDE``."""
    if not path or not start_zone or not goal_zone:
        return LEG_BAD_OVERRIDE
    zones = [int(z) for z in path]
    if len(zones) > max(1, int(max_zones)) or zones[0] != int(start_zone) or zones[-1] != int(goal_zone):
        return LEG_BAD_OVERRIDE
    if any(z not in zone_ids for z in zones):
        return LEG_BAD_OVERRIDE
    for a, b in zip(zones, zones[1:]):
        if a == b or b not in adj.get(a, ()):
            return LEG_BAD_OVERRIDE
    return None


def leg_path(adj: Mapping[int, Sequence[int]], zone_ids: Set[int], start_zone: Optional[int],
             goal_zone: Optional[int], override: Optional[Sequence[int]],
             max_zones: int) -> Tuple[Optional[List[int]], Optional[str], bool]:
    """``(path, problem, used_override)``: the zone path of a leg. A valid override wins; else BFS over the zone
    graph (deterministic, ascending ids). Same zone at both ends -> ``[z]``. ``problem`` is set when the path is
    None (``no_zone`` / ``no_path``), or ``bad_override`` together with the BFS path when the override was invalid."""
    if not start_zone or not goal_zone or int(start_zone) not in zone_ids or int(goal_zone) not in zone_ids:
        return None, LEG_NO_ZONE, False
    start_zone, goal_zone = int(start_zone), int(goal_zone)
    bad_override = None
    if override:
        bad_override = override_problem(override, start_zone, goal_zone, adj, zone_ids, max_zones)
        if bad_override is None:
            return [int(z) for z in override], None, True
    if start_zone == goal_zone:
        return [start_zone], bad_override, False
    path, _reason = caravan_route.shortest_route(adj, set(), start_zone, goal_zone, max_steps=max(1, max_zones - 1))
    if path is None:
        return None, LEG_NO_PATH, False
    return path, bad_override, False


# =====================================================================================================================
# money, seats, entitlement, times
# =====================================================================================================================

def fare(fare_base: int, fare_per_zone: int, zones: int) -> int:
    """Ticket price for legs with ``zones`` zones in total: base + per zone (never negative)."""
    return max(0, int(fare_base or 0) + int(fare_per_zone or 0) * max(0, int(zones or 0)))


def covers(first_trip: int, last_trip: int, trip: int) -> bool:
    return int(first_trip) <= int(trip) <= int(last_trip)


def entitled(kind: str, status: str, first_trip: int, last_trip: int, trip: int) -> bool:
    """A pass gives the passage / the right to stay aboard for ``trip`` (§3.5)."""
    return kind in PASS_KINDS and status == PASS_ACTIVE and covers(first_trip, last_trip, trip)


def seats_left(capacity: int, taken_per_trip: Mapping[int, int], trips: Iterable[int]) -> int:
    """Free seats over every trip of the range (the minimum)."""
    trips = list(trips)
    if not trips:
        return 0
    return max(0, min(int(capacity) - int(taken_per_trip.get(t, 0)) for t in trips))


def leg_minutes(zones: int, zone_minutes: int) -> int:
    return max(1, int(zones)) * max(1, int(zone_minutes))


def current_leg_arrival(next_zone_at: Optional[datetime], leg_len: int, leg_pos: int,
                        zone_minutes: int) -> Optional[datetime]:
    """Sailing: when the ship docks at the end of the current leg."""
    if next_zone_at is None:
        return None
    remaining = max(0, int(leg_len) - int(leg_pos) - 1)
    return next_zone_at + timedelta(minutes=remaining * max(1, int(zone_minutes)))


def arrivals(first_departure: Optional[datetime], legs_zones: Sequence[int], zone_minutes: int,
             boarding_minutes: int) -> List[Optional[datetime]]:
    """Arrival times of consecutive legs when the first of them departs at ``first_departure`` (each following
    leg departs ``boarding_minutes`` after the previous arrival)."""
    out: List[Optional[datetime]] = []
    t = first_departure
    for i, zones in enumerate(legs_zones):
        if t is None:
            out.append(None)
            continue
        if i > 0:
            t = t + timedelta(minutes=max(0, int(boarding_minutes)))
        t = t + timedelta(minutes=leg_minutes(zones, zone_minutes))
        out.append(t)
    return out


def clamp(value: int, bounds: Tuple[int, int]) -> int:
    lo, hi = bounds
    return max(lo, min(hi, int(value)))


# =====================================================================================================================
# FEAT-214 storms and raids — pure helpers (§3.4)
# =====================================================================================================================

def weather_rng() -> random.Random:
    """THE seam of every storm / drift / raid roll (tests patch it)."""
    return random.Random()


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value if value is not None else 0))


def season_mult(season: Optional[str], params) -> Decimal:
    """Storm chance multiplier of a game season (``params.season_mult_<season>``); unknown / None → 1.0."""
    if not season or season not in SEASONS:
        return Decimal("1")
    value = getattr(params, f"season_mult_{season}", None)
    return Decimal("1") if value is None else max(Decimal("0"), _dec(value))


def pass_chance(per_hour_pct, mult, elapsed_minutes) -> Decimal:
    """Chance of an event with ``per_hour_pct`` × ``mult`` per real hour within ``elapsed_minutes``:
    ``1 − (1 − p)^(elapsed/60)``, ``p = min(1, pct × mult / 100)``; ``elapsed`` clamped to [0, 60] (no burst after a
    downtime)."""
    p = min(Decimal("1"), max(Decimal("0"), _dec(per_hour_pct) * _dec(mult) / Decimal("100")))
    elapsed = min(Decimal(MINUTES_PER_HOUR), max(Decimal("0"), _dec(elapsed_minutes)))
    if p <= 0 or elapsed <= 0:
        return Decimal("0")
    if p >= 1:
        return Decimal("1")
    keep = (1.0 - float(p)) ** (float(elapsed) / MINUTES_PER_HOUR)
    return Decimal(str(round(1.0 - keep, 10)))


def split_groups(ids: Iterable[int], cap: int = SEA_RAID_TEAM_MAX) -> List[List[int]]:
    """``ceil(n / cap)`` groups of ascending distinct ids, sizes differ by at most 1 (6 → 3+3, 11 → 4+4+3)."""
    ordered = sorted({int(i) for i in ids})
    n = len(ordered)
    if n == 0:
        return []
    count = math.ceil(n / max(1, int(cap)))
    base, extra = divmod(n, count)
    out: List[List[int]] = []
    pos = 0
    for g in range(count):
        size = base + (1 if g < extra else 0)
        out.append(ordered[pos:pos + size])
        pos += size
    return out


def pack_size(max_active, group_len: int) -> int:
    """Monsters of one battle group: ``min(clamp(max_active, 1, 5), group_len)`` (never 0 for a non-empty group)."""
    per_zone = max(1, min(int(max_active or 0), SEA_RAID_TEAM_MAX))
    return max(1, min(per_zone, int(group_len))) if int(group_len) > 0 else 0


def storm_zones(adj: Mapping[int, Sequence[int]], zone_sea: Mapping[int, Optional[int]], center: int,
                radius: int) -> List[int]:
    """Zones within ``radius`` steps of ``center`` (BFS), only through zones of the centre's sea; ascending ids.
    A centre without a sea covers only itself plus neighbours that have no sea either."""
    center = int(center)
    sea = zone_sea.get(center)
    radius = max(0, int(radius or 0))
    seen = {center}
    queue = deque([(center, 0)])
    while queue:
        zone, dist = queue.popleft()
        if dist >= radius:
            continue
        for nb in adj.get(zone, ()):
            nb = int(nb)
            if nb in seen or nb not in zone_sea or zone_sea.get(nb) != sea:
                continue
            seen.add(nb)
            queue.append((nb, dist + 1))
    return sorted(seen)


def storm_extra(zone_minutes: int, slow_mult) -> int:
    """Storm delay of one zone: ``round(zone_minutes × (slow_mult − 1))`` (never negative)."""
    extra = _dec(max(1, int(zone_minutes or 0))) * (max(Decimal("1"), _dec(slow_mult)) - 1)
    return max(0, int(extra.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def relief(extra: int, pct) -> int:
    """Minutes of the storm delay the sailors win back: ``floor(extra × pct / 100)``."""
    pct = min(Decimal("100"), max(Decimal("0"), _dec(pct)))
    return max(0, int((_dec(max(0, int(extra or 0))) * pct / 100).to_integral_value(rounding=ROUND_FLOOR)))


def pick_drift(adj: Mapping[int, Sequence[int]], current: int, next_zone: Optional[int],
               rng: random.Random) -> Optional[int]:
    """A random zone adjacent to ``current`` other than ``next_zone`` (None if there is none). ``adj`` must be the
    sea-zone graph (only sea zones)."""
    options = sorted({int(z) for z in adj.get(int(current), ()) if int(z) != int(current)
                      and (next_zone is None or int(z) != int(next_zone))})
    if not options:
        return None
    return options[rng.randrange(len(options))]
