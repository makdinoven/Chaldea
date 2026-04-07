// Shared waypoint helpers for floating-structure route editing.
//
// TODO: in the future these helpers may be extracted from
// `RegionMapEditor.tsx` and shared, but per FEAT-123 §3.5 we are explicitly
// forbidden from touching `RegionMapEditor.tsx`, so they are inlined here.

import type { RouteWaypoint } from '../../redux/slices/floatingStructuresSlice';

/** Clamp a percentage coordinate to the [0, 100] range. */
export const clampPct = (value: number): number => {
  if (Number.isNaN(value)) return 0;
  if (value < 0) return 0;
  if (value > 100) return 100;
  return value;
};

/**
 * Convert a click event on a container element into percentage coordinates
 * relative to that container.
 */
export const eventToPct = (
  e: { clientX: number; clientY: number },
  container: HTMLElement,
): RouteWaypoint => {
  const rect = container.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * 100;
  const y = ((e.clientY - rect.top) / rect.height) * 100;
  return { x: clampPct(x), y: clampPct(y) };
};

/** Append a waypoint to the end of the polyline. */
export const addWaypoint = (
  waypoints: RouteWaypoint[],
  point: RouteWaypoint,
): RouteWaypoint[] => [...waypoints, point];

/** Insert a waypoint at a specific index (used for "insert into segment"). */
export const insertWaypoint = (
  waypoints: RouteWaypoint[],
  index: number,
  point: RouteWaypoint,
): RouteWaypoint[] => {
  const next = waypoints.slice();
  next.splice(index, 0, point);
  return next;
};

/** Delete the waypoint at the given index. */
export const deleteWaypoint = (
  waypoints: RouteWaypoint[],
  index: number,
): RouteWaypoint[] => waypoints.filter((_, i) => i !== index);

/** Replace a waypoint at the given index. */
export const updateWaypoint = (
  waypoints: RouteWaypoint[],
  index: number,
  point: RouteWaypoint,
): RouteWaypoint[] => waypoints.map((w, i) => (i === index ? point : w));

/**
 * Squared distance from a point to the segment (a, b).
 * Used to find which segment a click landed on.
 */
const distSqPointToSegment = (
  p: RouteWaypoint,
  a: RouteWaypoint,
  b: RouteWaypoint,
): number => {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) {
    const ex = p.x - a.x;
    const ey = p.y - a.y;
    return ex * ex + ey * ey;
  }
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / lenSq;
  if (t < 0) t = 0;
  if (t > 1) t = 1;
  const projX = a.x + t * dx;
  const projY = a.y + t * dy;
  const ex = p.x - projX;
  const ey = p.y - projY;
  return ex * ex + ey * ey;
};

/**
 * Find the index *after* which a new waypoint should be inserted, based on
 * which segment of the OPEN polyline is closest to the click point. The
 * polyline is treated as ping-pong (A → B → A), so the wrap-around segment
 * (last → first) is NOT considered.
 *
 * Returns the insertion index (i.e. `splice(index, 0, point)`) only when the
 * click is *clearly* on a segment line. Otherwise returns `null` so the caller
 * can fall back to append-at-end (the safer default). The threshold is
 * intentionally tight (1.5% of container size ≈ 8–12px on a typical map) to
 * avoid stealing clicks that the user intended as "append after B".
 *
 * Returns `null` if fewer than 2 waypoints exist, or if no segment is within
 * the threshold.
 */
export const findInsertIndex = (
  waypoints: RouteWaypoint[],
  point: RouteWaypoint,
  thresholdPct = 1.5,
): number | null => {
  if (waypoints.length < 2) return null;
  let bestDistSq = Infinity;
  let bestIdx = -1;
  for (let i = 0; i < waypoints.length - 1; i++) {
    const a = waypoints[i];
    const b = waypoints[i + 1];
    const d = distSqPointToSegment(point, a, b);
    if (d < bestDistSq) {
      bestDistSq = d;
      bestIdx = i;
    }
  }
  if (bestIdx === -1) return null;
  if (Math.sqrt(bestDistSq) > thresholdPct) return null;
  return bestIdx + 1;
};

/**
 * Build the SVG `points` string from waypoints in percentage coordinates.
 * Output is identical for `<polygon>` and `<polyline>`; the editor uses
 * `<polyline>` (open ping-pong route).
 */
export const waypointsToPolygonPoints = (waypoints: RouteWaypoint[]): string =>
  waypoints.map((w) => `${w.x},${w.y}`).join(' ');
