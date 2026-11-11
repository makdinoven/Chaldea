"""FEAT-211 (§3.2) physical caravan roads — pure functions, no DB, no clock, no RNG.

The graph is ``LocationNeighbors`` (both directions stored, cross-region auto-arrow rows included), loaded once per
caravan pass by ``economy_caravan_crud.load_road_graph`` into an adjacency map ``{location_id: sorted neighbours}``.
Routes are the shortest path by hop count (BFS, neighbours visited in ascending id -> deterministic). Intermediate
nodes in ``blocked`` (``marker_type='dungeon'`` locations) are never walked through; the endpoints are always allowed.
"""

from collections import deque
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

GATE_OVERRIDE = "override"
GATE_STATION = "station"
GATE_NONE = "none"

NO_ROAD_NO_GATE = "no_gate"
NO_ROAD_NO_PATH = "no_path"
NO_ROAD_TOO_LONG = "too_long"


def build_adjacency(edges: Iterable[Tuple[int, int]]) -> Dict[int, List[int]]:
    """``{node: sorted unique neighbours}`` from (location_id, neighbor_id) rows; both directions are added (the
    table stores both, a one-sided row must not make the road one-way). Self-loops are dropped."""
    adj: Dict[int, Set[int]] = {}
    for a, b in edges:
        if a is None or b is None:
            continue
        a, b = int(a), int(b)
        if a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return {node: sorted(neighbours) for node, neighbours in adj.items()}


def shortest_route(adj: Mapping[int, Sequence[int]], blocked: Iterable[int], start: Optional[int],
                   goal: Optional[int], max_steps: int) -> Tuple[Optional[List[int]], Optional[str]]:
    """``(route, None)`` — the list of location ids ``start … goal`` (length >= 2), or ``(None, reason)`` with
    reason ``no_gate`` (an endpoint is missing or start == goal), ``no_path`` or ``too_long`` (more than
    ``max_steps`` hops)."""
    if not start or not goal or int(start) == int(goal):
        return None, NO_ROAD_NO_GATE
    start, goal = int(start), int(goal)
    blocked_set = {int(b) for b in (blocked or ())} - {start, goal}
    parent: Dict[int, Optional[int]] = {start: None}
    queue = deque([start])
    found = False
    while queue:
        node = queue.popleft()
        if node == goal:
            found = True
            break
        for nxt in adj.get(node, ()):
            nxt = int(nxt)
            if nxt in parent or nxt in blocked_set:
                continue
            parent[nxt] = node
            queue.append(nxt)
    if not found:
        return None, NO_ROAD_NO_PATH
    path = [goal]
    while path[-1] != start:
        path.append(parent[path[-1]])
    path.reverse()
    if len(path) - 1 > max(1, int(max_steps)):
        return None, NO_ROAD_TOO_LONG
    return path, None


def effective_gate(override: Optional[int], station: Optional[int]) -> Tuple[Optional[int], str]:
    """The trade gate of a region: the admin override, else the guard station, else none."""
    if override:
        return int(override), GATE_OVERRIDE
    if station:
        return int(station), GATE_STATION
    return None, GATE_NONE
