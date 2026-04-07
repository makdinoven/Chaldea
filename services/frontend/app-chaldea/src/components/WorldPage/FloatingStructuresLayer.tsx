import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppSelector } from '../../redux/store';
import {
  selectFloatingStructures,
  selectServerNowOffsetMs,
  type FloatingStructure,
  type RouteWaypoint,
} from '../../redux/slices/floatingStructuresSlice';

/**
 * Computes the (x, y) position along an OPEN polyline at fractional progress in [0, 1].
 * The polyline is traversed from waypoints[0] to waypoints[n-1] (NO wrap-around).
 * Callers are expected to pass `progress` already mapped via a triangle wave so that
 * the structure ping-pongs A -> B -> A -> B ... smoothly.
 */
const interpolatePolyline = (
  waypoints: RouteWaypoint[],
  progress: number,
): RouteWaypoint => {
  if (waypoints.length === 0) return { x: 0, y: 0 };
  if (waypoints.length === 1) return { x: waypoints[0].x, y: waypoints[0].y };

  // Clamp progress into [0, 1]
  let p = progress;
  if (p < 0) p = 0;
  if (p > 1) p = 1;

  // Build segment lengths (open polyline: n-1 segments, no wrap)
  const segLengths: number[] = [];
  let total = 0;
  for (let i = 0; i < waypoints.length - 1; i += 1) {
    const a = waypoints[i];
    const b = waypoints[i + 1];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.sqrt(dx * dx + dy * dy);
    segLengths.push(len);
    total += len;
  }

  if (total === 0) return { x: waypoints[0].x, y: waypoints[0].y };

  let target = p * total;
  for (let i = 0; i < segLengths.length; i += 1) {
    const len = segLengths[i];
    if (target <= len) {
      const a = waypoints[i];
      const b = waypoints[i + 1];
      const t = len === 0 ? 0 : target / len;
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
    }
    target -= len;
  }
  // Floating-point fallback
  const last = waypoints[waypoints.length - 1];
  return { x: last.x, y: last.y };
};

/**
 * Triangle wave: maps a monotonically increasing value into [0, 1] that
 * oscillates 0 -> 1 -> 0 -> 1 ... Period is 2 input units.
 */
const triangleWave = (value: number): number => {
  let v = value % 2;
  if (v < 0) v += 2;
  // 1 - |v - 1| gives 0 at v=0, 1 at v=1, 0 at v=2.
  return 1 - Math.abs(v - 1);
};

interface FloatingStructureMarkerProps {
  structure: FloatingStructure;
  serverNowOffsetMs: number;
  onClick: (id: number) => void;
}

const FloatingStructureMarker = ({
  structure,
  serverNowOffsetMs,
  onClick,
}: FloatingStructureMarkerProps) => {
  const computePosition = (): RouteWaypoint => {
    const startedAtMs = new Date(structure.started_at).getTime();
    if (Number.isNaN(startedAtMs) || !structure.route_json || structure.route_json.length === 0) {
      return { x: 0, y: 0 };
    }
    const tSeconds = (Date.now() - serverNowOffsetMs - startedAtMs) / 1000;
    // Ping-pong: triangle wave maps [0, ∞) → [0, 1] → [1, 0] → ... so the
    // structure travels A → B → A → B continuously along the OPEN polyline.
    const progress = triangleWave(tSeconds * structure.speed);
    return interpolatePolyline(structure.route_json, progress);
  };

  const [pos, setPos] = useState<RouteWaypoint>(() => computePosition());

  useEffect(() => {
    setPos(computePosition());
    const id = window.setInterval(() => {
      setPos(computePosition());
    }, 1000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structure.id, structure.started_at, structure.speed, structure.route_json, serverNowOffsetMs]);

  const handleClick = () => onClick(structure.id);

  return (
    <button
      type="button"
      onClick={handleClick}
      title={structure.name}
      aria-label={structure.name}
      className="pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2 p-0 bg-transparent border-none cursor-pointer touch-manipulation transition-transform duration-200 ease-out hover:scale-110 focus:outline-none focus:ring-2 focus:ring-gold/60 rounded-full"
      style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
    >
      {structure.icon_url ? (
        <img
          src={structure.icon_url}
          alt={structure.name}
          draggable={false}
          className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 object-contain drop-shadow-[0_0_6px_rgba(0,0,0,0.7)] select-none"
        />
      ) : (
        <div className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 rounded-full bg-amber-500/80 border border-amber-200 flex items-center justify-center text-[8px] sm:text-[10px] text-black font-bold shadow-lg">
          {structure.name.slice(0, 2)}
        </div>
      )}
    </button>
  );
};

const FloatingStructuresLayer = () => {
  const navigate = useNavigate();
  const structures = useAppSelector(selectFloatingStructures);
  const serverNowOffsetMs = useAppSelector(selectServerNowOffsetMs);

  if (!structures || structures.length === 0) return null;

  const handleClick = (id: number) => {
    navigate(`/world?citadel=${id}`);
  };

  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute inset-0">
        {structures.map((s) => (
          <FloatingStructureMarker
            key={s.id}
            structure={s}
            serverNowOffsetMs={serverNowOffsetMs}
            onClick={handleClick}
          />
        ))}
      </div>
    </div>
  );
};

export default FloatingStructuresLayer;
