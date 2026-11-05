"""FEAT-204 guard patrols — pure maths (no I/O, no project imports).

A guard NPC either stands at a fixed post (the default; no ``guard_patrols`` row) or patrols:

* ``route`` — an ordered list of locations, walked ``loop`` (A→B→C→A…) or ``pingpong`` (A→B→C→B→A…);
* ``zone``  — a set of locations (a district subtree or an explicit list); every step goes to a random neighbouring
  location inside the zone (over ``LocationNeighbors``), avoiding an immediate backtrack.

The DB layer (``patrol_crud``) resolves the lists / neighbours and passes a ``pick`` callable backed by the patchable
RNG seam, so everything here is deterministic.
"""

from datetime import datetime, timedelta
from typing import Callable, List, Optional, Sequence, Tuple

MODE_POST, MODE_ROUTE, MODE_ZONE = "post", "route", "zone"
MODES = (MODE_POST, MODE_ROUTE, MODE_ZONE)
MOVING_MODES = (MODE_ROUTE, MODE_ZONE)
STYLE_LOOP, STYLE_PINGPONG = "loop", "pingpong"
STYLES = (STYLE_LOOP, STYLE_PINGPONG)
ZONE_DISTRICT, ZONE_LOCATIONS = "district", "locations"
ZONE_KINDS = (ZONE_DISTRICT, ZONE_LOCATIONS)
KIND_ROUTE, KIND_ZONE = "route", "zone"           # guard_patrol_points.kind

DEFAULT_INTERVAL_MIN, MIN_INTERVAL_MIN, MAX_INTERVAL_MIN = 20, 5, 1440
DEFAULT_JITTER_PCT, MAX_JITTER_PCT = 25, 50
MIN_POINTS, MAX_ROUTE_POINTS, MAX_ZONE_POINTS = 2, 30, 100
MIN_DELAY = timedelta(minutes=1)
BLOCKED_RETRY = timedelta(minutes=2)              # a blocked guard is looked at again after this

HINT_SOON_MIN, HINT_SHORT_MIN = 5, 15             # ≤5 → soon, ≤15 → short, else long
HINT_SOON, HINT_SHORT, HINT_LONG = "soon", "short", "long"

# blocked reasons (the step and the admin status line)
BLOCK_NOT_GUARD = "not_guard"
BLOCK_DEAD = "dead"
BLOCK_KO = "ko"
BLOCK_BATTLE = "battle"
BLOCK_ENCOUNTER = "encounter"


def _ids(values) -> List[int]:
    return [int(v) for v in (values or ())]


def validate(mode: str, style: str, zone_kind: str, route_ids: Sequence[int], zone_ids: Sequence[int],
             district_id: Optional[int], interval_min: int, jitter_pct: int) -> List[str]:
    """Russian errors of a patrol config (existence of locations / districts is checked by the DB layer).

    The list of the ACTIVE mode is validated fully; the other stored list only for its size."""
    errors: List[str] = []
    if mode not in MODES:
        return ["Неизвестный режим патруля"]
    if style not in STYLES:
        errors.append("Неизвестный порядок обхода маршрута")
    if zone_kind not in ZONE_KINDS:
        errors.append("Неизвестный вид зоны патруля")
    if not (MIN_INTERVAL_MIN <= int(interval_min) <= MAX_INTERVAL_MIN):
        errors.append(f"Интервал патруля: от {MIN_INTERVAL_MIN} до {MAX_INTERVAL_MIN} минут")
    if not (0 <= int(jitter_pct) <= MAX_JITTER_PCT):
        errors.append(f"Разброс интервала: от 0 до {MAX_JITTER_PCT} %")
    route = _ids(route_ids)
    zone = _ids(zone_ids)
    if any(x <= 0 for x in route + zone):
        errors.append("Неверный идентификатор локации")
    if len(route) > MAX_ROUTE_POINTS:
        errors.append(f"В маршруте не больше {MAX_ROUTE_POINTS} точек")
    if len(zone) > MAX_ZONE_POINTS:
        errors.append(f"В зоне патруля не больше {MAX_ZONE_POINTS} локаций")
    if mode == MODE_ROUTE:
        if len(route) < MIN_POINTS:
            errors.append(f"В маршруте нужно хотя бы {MIN_POINTS} точки")
        elif any(route[i] == route[i + 1] for i in range(len(route) - 1)) or \
                (style == STYLE_LOOP and route[0] == route[-1]):
            errors.append("Одна и та же локация не может идти в маршруте два раза подряд")
    elif mode == MODE_ZONE and zone_kind == ZONE_LOCATIONS:
        if len(zone) < MIN_POINTS:
            errors.append(f"В зоне патруля нужно хотя бы {MIN_POINTS} локации")
        elif len(set(zone)) != len(zone):
            errors.append("Локации в зоне патруля не должны повторяться")
    elif mode == MODE_ZONE and zone_kind == ZONE_DISTRICT and not district_id:
        errors.append("Выберите район зоны патруля")
    return errors


def next_delay(interval_min: int, jitter_pct: int, u: float) -> timedelta:
    """``interval × (1 + jitter × (2u − 1))`` for ``u ∈ [0, 1)``, never below one minute."""
    u = min(max(float(u), 0.0), 1.0)
    jitter = min(max(int(jitter_pct), 0), MAX_JITTER_PCT) / 100.0
    minutes = float(int(interval_min)) * (1.0 + jitter * (2.0 * u - 1.0))
    return max(MIN_DELAY, timedelta(seconds=int(round(minutes * 60))))


def route_step(points: Sequence[int], index: int, direction: int, style: str,
               current_location: Optional[int]) -> Tuple[Optional[int], int, int]:
    """``(target, new_index, new_dir)`` of the next route step.

    On its point → advance (loop: the next one, wrapping; pingpong: ``index + dir``, reversing at either end).
    Off its point but somewhere on the route → resync to the first position of the current location, then advance.
    Off the route → return to ``points[0]`` (a direct jump)."""
    points = _ids(points)
    n = len(points)
    if n == 0:
        return None, 0, 1
    direction = -1 if int(direction or 1) < 0 else 1
    current = int(current_location) if current_location else None
    index = int(index or 0)
    if 0 <= index < n and points[index] == current:
        position = index
    elif current in points:
        position = points.index(current)
    else:
        return points[0], 0, 1
    if n == 1:
        return points[0], 0, 1
    if style == STYLE_PINGPONG:
        new_index = position + direction
        if new_index < 0 or new_index >= n:
            direction = -direction
            new_index = position + direction
        return points[new_index], new_index, direction
    new_index = (position + 1) % n
    return points[new_index], new_index, 1


def zone_step(current: Optional[int], zone: Sequence[int], neighbours: Sequence[int], last: Optional[int],
              pick: Callable[[Sequence[int]], int]) -> Tuple[Optional[int], bool]:
    """``(target, jumped)`` of the next zone step: a random neighbour inside the zone (not straight back to ``last``
    when another candidate exists); no candidate (isolated / outside the zone) → a random zone location ≠ current
    (``jumped``). A zone of fewer than 2 locations → ``(None, False)`` (no move)."""
    zone_ids = []
    for x in _ids(zone):
        if x not in zone_ids:
            zone_ids.append(x)
    if len(zone_ids) < MIN_POINTS:
        return None, False
    current = int(current) if current else None
    zone_set = set(zone_ids)
    candidates = sorted({int(n) for n in (neighbours or ()) if int(n) in zone_set and int(n) != current})
    if last is not None and int(last) in candidates and len(candidates) > 1:
        candidates.remove(int(last))
    if candidates:
        return int(pick(candidates)), False
    others = [x for x in zone_ids if x != current]
    return int(pick(others)), True


def departure_bucket(next_move_at: Optional[datetime], now: datetime, held: bool) -> Optional[str]:
    """The player-facing hint: held by an open encounter → long; not scheduled → None; else by the time left."""
    if held:
        return HINT_LONG
    if next_move_at is None:
        return None
    left = next_move_at - now
    if left <= timedelta(minutes=HINT_SOON_MIN):
        return HINT_SOON
    if left <= timedelta(minutes=HINT_SHORT_MIN):
        return HINT_SHORT
    return HINT_LONG
