import { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import type { DungeonRoom, DungeonCorridor } from '../../../api/dungeons';

interface AdminDungeonGraphProps {
  dungeonId: number;
  rooms: DungeonRoom[];
  corridors: DungeonCorridor[];
}

interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

// Room type -> color mapping
const ROOM_COLORS: Record<string, string> = {
  battle: '#E94545',
  boss: '#8B0000',
  treasure: '#F0D95C',
  trap: '#F97316',
  event: '#A855F7',
  rest: '#22C55E',
  merchant: '#76A6BD',
  fork: '#9CA3AF',
  teleport: '#06B6D4',
  deadend: '#92400E',
};

const NODE_RADIUS = 30;
const ARROW_SIZE = 10;

interface NodePos {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

/**
 * Simple force-directed layout: nodes repel each other,
 * connected nodes attract, everything stays inside bounds.
 */
const computeLayout = (
  rooms: DungeonRoom[],
  corridors: DungeonCorridor[],
  width: number,
  height: number
): Map<number, { x: number; y: number }> => {
  if (rooms.length === 0) return new Map();

  const nodes = new Map<number, NodePos>();

  // Initialize positions in a circle
  const cx = width / 2;
  const cy = height / 2;
  const initRadius = Math.min(width, height) * 0.35;

  rooms.forEach((room, i) => {
    const angle = (2 * Math.PI * i) / rooms.length;
    nodes.set(room.id, {
      x: cx + initRadius * Math.cos(angle),
      y: cy + initRadius * Math.sin(angle),
      vx: 0,
      vy: 0,
    });
  });

  // Build adjacency set for attraction
  const edges = new Set<string>();
  corridors.forEach((c) => {
    edges.add(`${c.from_room_id}-${c.to_room_id}`);
    if (c.is_bidirectional) {
      edges.add(`${c.to_room_id}-${c.from_room_id}`);
    }
  });

  // Simulation iterations
  const iterations = 200;
  const repulsion = 8000;
  const attraction = 0.005;
  const damping = 0.85;
  const pad = NODE_RADIUS + 10;

  for (let iter = 0; iter < iterations; iter++) {
    const temp = 1 - iter / iterations; // cooling

    // Repulsive forces between all pairs
    const ids = Array.from(nodes.keys());
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = nodes.get(ids[i])!;
        const b = nodes.get(ids[j])!;
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (repulsion / (dist * dist)) * temp;
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        a.vx += dx;
        a.vy += dy;
        b.vx -= dx;
        b.vy -= dy;
      }
    }

    // Attractive forces along edges
    corridors.forEach((c) => {
      const a = nodes.get(c.from_room_id);
      const b = nodes.get(c.to_room_id);
      if (!a || !b) return;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = dist * attraction * temp;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    });

    // Apply velocities, enforce bounds
    nodes.forEach((n) => {
      n.x += n.vx;
      n.y += n.vy;
      n.vx *= damping;
      n.vy *= damping;
      n.x = Math.max(pad, Math.min(width - pad, n.x));
      n.y = Math.max(pad, Math.min(height - pad, n.y));
    });
  }

  const result = new Map<number, { x: number; y: number }>();
  nodes.forEach((n, id) => {
    result.set(id, { x: n.x, y: n.y });
  });
  return result;
};

const AdminDungeonGraph = ({ dungeonId, rooms, corridors }: AdminDungeonGraphProps) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [positions, setPositions] = useState<Map<number, { x: number; y: number }>>(new Map());
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

  // Measure container
  useEffect(() => {
    const measure = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setDimensions({
          width: Math.max(400, rect.width),
          height: Math.max(400, Math.min(600, rect.width * 0.65)),
        });
      }
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);

  // Compute layout when data or dimensions change
  useEffect(() => {
    const pos = computeLayout(rooms, corridors, dimensions.width, dimensions.height);
    setPositions(pos);
  }, [rooms, corridors, dimensions]);

  const handleValidate = useCallback(async () => {
    setValidating(true);
    try {
      const { data } = await axios.post<ValidationResult>(
        `/dungeons/admin/dungeons/${dungeonId}/validate`
      );
      setValidation(data);
      if (data.valid && data.warnings.length === 0) {
        toast.success('Граф валиден!');
      } else if (data.valid) {
        toast('Граф валиден, но есть предупреждения', { icon: '⚠️' });
      } else {
        toast.error('Граф содержит ошибки');
      }
    } catch {
      toast.error('Не удалось выполнить валидацию');
    } finally {
      setValidating(false);
    }
  }, [dungeonId]);

  // Draw arrow head
  const renderArrowHead = (
    fromX: number,
    fromY: number,
    toX: number,
    toY: number,
    color: string,
    key: string
  ) => {
    const dx = toX - fromX;
    const dy = toY - fromY;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / dist;
    const uy = dy / dist;

    // Arrow tip at edge of target node
    const tipX = toX - ux * NODE_RADIUS;
    const tipY = toY - uy * NODE_RADIUS;

    const leftX = tipX - ux * ARROW_SIZE + uy * (ARROW_SIZE / 2);
    const leftY = tipY - uy * ARROW_SIZE - ux * (ARROW_SIZE / 2);
    const rightX = tipX - ux * ARROW_SIZE - uy * (ARROW_SIZE / 2);
    const rightY = tipY - uy * ARROW_SIZE + ux * (ARROW_SIZE / 2);

    return (
      <polygon
        key={key}
        points={`${tipX},${tipY} ${leftX},${leftY} ${rightX},${rightY}`}
        fill={color}
      />
    );
  };

  if (rooms.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-center text-white/50 text-sm py-8">
          Нет комнат для отображения графа
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h2 className="text-white text-lg font-medium uppercase tracking-[0.06em]">
          Граф подземелья
        </h2>
        <button
          className="btn-blue !text-base !px-6 !py-2"
          onClick={handleValidate}
          disabled={validating}
        >
          {validating ? 'Проверка...' : 'Проверить граф'}
        </button>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs">
        {Object.entries(ROOM_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: color }} />
            <span className="text-white/60">
              {{
                battle: 'Бой',
                boss: 'Босс',
                treasure: 'Сокровищница',
                trap: 'Ловушка',
                event: 'Событие',
                rest: 'Отдых',
                merchant: 'Торговец',
                fork: 'Развилка',
                teleport: 'Телепорт',
                deadend: 'Тупик',
              }[type] || type}
            </span>
          </div>
        ))}
      </div>

      {/* SVG Graph */}
      <div ref={containerRef} className="gray-bg overflow-hidden rounded-card">
        <svg
          ref={svgRef}
          width={dimensions.width}
          height={dimensions.height}
          viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
          className="w-full"
        >
          {/* Corridors (edges) */}
          {corridors.map((c) => {
            const from = positions.get(c.from_room_id);
            const to = positions.get(c.to_room_id);
            if (!from || !to) return null;

            const edgeColor = 'rgba(255,255,255,0.3)';

            return (
              <g key={c.id}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={edgeColor}
                  strokeWidth={1.5}
                />
                {/* Forward arrow */}
                {renderArrowHead(from.x, from.y, to.x, to.y, edgeColor, `arrow-${c.id}-fwd`)}
                {/* Backward arrow for bidirectional */}
                {c.is_bidirectional &&
                  renderArrowHead(to.x, to.y, from.x, from.y, edgeColor, `arrow-${c.id}-bwd`)}
                {/* Stamina label */}
                <text
                  x={(from.x + to.x) / 2}
                  y={(from.y + to.y) / 2 - 6}
                  textAnchor="middle"
                  fill="rgba(255,255,255,0.5)"
                  fontSize="10"
                >
                  {c.stamina_cost}
                </text>
              </g>
            );
          })}

          {/* Rooms (nodes) */}
          {rooms.map((room) => {
            const pos = positions.get(room.id);
            if (!pos) return null;
            const color = ROOM_COLORS[room.room_type] || '#666';
            const isEntrance = room.is_entrance;

            return (
              <g key={room.id}>
                {/* Entrance highlight ring */}
                {isEntrance && (
                  <circle
                    cx={pos.x}
                    cy={pos.y}
                    r={NODE_RADIUS + 5}
                    fill="none"
                    stroke="#F0D95C"
                    strokeWidth={2.5}
                    strokeDasharray="6 3"
                  />
                )}
                {/* Node circle */}
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={NODE_RADIUS}
                  fill={color}
                  fillOpacity={0.7}
                  stroke="rgba(255,255,255,0.5)"
                  strokeWidth={1}
                />
                {/* Room name (truncated) */}
                <text
                  x={pos.x}
                  y={pos.y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="white"
                  fontSize="9"
                  fontWeight="500"
                >
                  {room.name.length > 10 ? room.name.slice(0, 9) + '…' : room.name}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Validation results */}
      {validation && (
        <div className="gray-bg p-4 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span
              className={`w-3 h-3 rounded-full ${
                validation.valid ? 'bg-green-500' : 'bg-site-red'
              }`}
            />
            <span className={`text-sm font-medium ${validation.valid ? 'text-green-400' : 'text-site-red'}`}>
              {validation.valid ? 'Граф валиден' : 'Граф содержит ошибки'}
            </span>
          </div>

          {validation.errors.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-xs text-site-red font-medium uppercase">Ошибки:</span>
              {validation.errors.map((err, i) => (
                <span key={i} className="text-sm text-site-red/80 pl-3">
                  &bull; {err}
                </span>
              ))}
            </div>
          )}

          {validation.warnings.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gold font-medium uppercase">Предупреждения:</span>
              {validation.warnings.map((warn, i) => (
                <span key={i} className="text-sm text-gold/80 pl-3">
                  &bull; {warn}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AdminDungeonGraph;
