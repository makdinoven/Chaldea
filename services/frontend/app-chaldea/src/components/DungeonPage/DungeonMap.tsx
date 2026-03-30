import { useMemo, useState, useRef, useCallback, useEffect } from 'react';
import type { RoomView, SessionState } from '../../api/dungeons';

// --- Types ---

interface ExploredRoom {
  id: number;
  name: string;
  room_type: string;
  is_cleared: boolean;
  reliability: 'reliable' | 'uncertain' | 'memory_only';
}

interface MapNode {
  id: number;
  label: string;
  room_type: string;
  x: number;
  y: number;
  explored: boolean;
  isCurrent: boolean;
  is_cleared: boolean;
  reliability: 'reliable' | 'uncertain' | 'memory_only';
}

interface MapEdge {
  from: number;
  to: number;
  bidirectional: boolean;
  corridorId: number;
}

interface DungeonMapProps {
  sessionState: SessionState;
  stabilityType: 'static' | 'unstable' | 'chaotic';
  onRoomClick?: (roomId: number) => void;
}

// --- Constants ---

const NODE_RADIUS = 24;
const NODE_SPACING_X = 140;
const NODE_SPACING_Y = 120;
const PADDING = 60;

const ROOM_TYPE_COLORS: Record<string, string> = {
  battle: '#ef4444',
  boss: '#991b1b',
  treasure: '#f0d95c',
  trap: '#f97316',
  event: '#a855f7',
  rest: '#22c55e',
  merchant: '#76a6bd',
  fork: '#6b7280',
  teleport: '#06b6d4',
  deadend: '#92400e',
};

const ROOM_TYPE_ICONS: Record<string, string> = {
  battle: '\u2694',
  boss: '\uD83D\uDC80',
  treasure: '\uD83D\uDCE6',
  trap: '\u26A0',
  event: '\u2753',
  rest: '\uD83D\uDCA4',
  merchant: '\uD83D\uDCB0',
  fork: '\u2B50',
  teleport: '\uD83C\uDF00',
  deadend: '\u2716',
};

// --- Helper: build explored room map from session state exits ---

const buildExploredRooms = (
  currentRoom: RoomView | null,
): { rooms: Map<number, ExploredRoom>; edges: MapEdge[] } => {
  const rooms = new Map<number, ExploredRoom>();
  const edges: MapEdge[] = [];

  if (!currentRoom) return { rooms, edges };

  // Current room is always explored
  rooms.set(currentRoom.id, {
    id: currentRoom.id,
    name: currentRoom.name,
    room_type: currentRoom.room_type,
    is_cleared: currentRoom.is_cleared,
    reliability: 'reliable',
  });

  // Add exits as edges + unexplored rooms
  for (const exit of currentRoom.exits) {
    edges.push({
      from: currentRoom.id,
      to: exit.to_room_id,
      bidirectional: true, // Assume bidirectional for display
      corridorId: exit.corridor_id,
    });

    if (!rooms.has(exit.to_room_id)) {
      rooms.set(exit.to_room_id, {
        id: exit.to_room_id,
        name: exit.explored ? exit.to_room_name : '???',
        room_type: exit.explored ? 'fork' : 'unknown',
        is_cleared: false,
        reliability: exit.reliability ?? 'reliable',
      });
    }
  }

  return { rooms, edges };
};

// --- Helper: simple tree layout ---

const layoutNodes = (
  rooms: Map<number, ExploredRoom>,
  edges: MapEdge[],
  currentRoomId: number,
): MapNode[] => {
  const nodes: MapNode[] = [];
  const positioned = new Set<number>();

  // BFS from current room
  const queue: { id: number; depth: number; index: number }[] = [];
  const depthBuckets = new Map<number, number>();

  queue.push({ id: currentRoomId, depth: 0, index: 0 });
  positioned.add(currentRoomId);

  // Adjacency list
  const adj = new Map<number, number[]>();
  for (const edge of edges) {
    if (!adj.has(edge.from)) adj.set(edge.from, []);
    if (!adj.has(edge.to)) adj.set(edge.to, []);
    adj.get(edge.from)!.push(edge.to);
    adj.get(edge.to)!.push(edge.from);
  }

  while (queue.length > 0) {
    const item = queue.shift()!;
    const room = rooms.get(item.id);
    if (!room) continue;

    const countAtDepth = depthBuckets.get(item.depth) ?? 0;
    depthBuckets.set(item.depth, countAtDepth + 1);

    nodes.push({
      id: item.id,
      label: room.name,
      room_type: room.room_type,
      x: PADDING + countAtDepth * NODE_SPACING_X,
      y: PADDING + item.depth * NODE_SPACING_Y,
      explored: room.name !== '???',
      isCurrent: item.id === currentRoomId,
      is_cleared: room.is_cleared,
      reliability: room.reliability,
    });

    const neighbors = adj.get(item.id) ?? [];
    for (const neighbor of neighbors) {
      if (!positioned.has(neighbor)) {
        positioned.add(neighbor);
        queue.push({ id: neighbor, depth: item.depth + 1, index: 0 });
      }
    }
  }

  // Add any orphan rooms
  for (const [id, room] of rooms) {
    if (!positioned.has(id)) {
      const countAtDepth = depthBuckets.get(0) ?? 0;
      depthBuckets.set(0, countAtDepth + 1);
      nodes.push({
        id,
        label: room.name,
        room_type: room.room_type,
        x: PADDING + countAtDepth * NODE_SPACING_X,
        y: PADDING,
        explored: room.name !== '???',
        isCurrent: false,
        is_cleared: room.is_cleared,
        reliability: room.reliability,
      });
    }
  }

  // Center nodes at each depth level
  const maxWidth = Math.max(...nodes.map((n) => n.x)) + PADDING;
  const depthGroups = new Map<number, MapNode[]>();
  for (const node of nodes) {
    if (!depthGroups.has(node.y)) depthGroups.set(node.y, []);
    depthGroups.get(node.y)!.push(node);
  }
  for (const group of depthGroups.values()) {
    const groupWidth = (group.length - 1) * NODE_SPACING_X;
    const offset = (maxWidth - groupWidth) / 2;
    group.forEach((node, i) => {
      node.x = offset + i * NODE_SPACING_X;
    });
  }

  return nodes;
};

// --- Component ---

const DungeonMap = ({ sessionState, stabilityType, onRoomClick }: DungeonMapProps) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [scale, setScale] = useState(1);
  const [dragging, setDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  const currentRoomId = sessionState.current_room?.id ?? 0;

  const { rooms, edges } = useMemo(
    () => buildExploredRooms(sessionState.current_room),
    [sessionState.current_room],
  );

  const nodes = useMemo(
    () => layoutNodes(rooms, edges, currentRoomId),
    [rooms, edges, currentRoomId],
  );

  const nodeMap = useMemo(() => {
    const m = new Map<number, MapNode>();
    for (const n of nodes) m.set(n.id, n);
    return m;
  }, [nodes]);

  // Calculate SVG dimensions
  const svgWidth = useMemo(
    () => Math.max(300, ...nodes.map((n) => n.x + PADDING + NODE_RADIUS)),
    [nodes],
  );
  const svgHeight = useMemo(
    () => Math.max(200, ...nodes.map((n) => n.y + PADDING + NODE_RADIUS)),
    [nodes],
  );

  // Center on current room on first render
  useEffect(() => {
    const currentNode = nodeMap.get(currentRoomId);
    if (currentNode && containerRef.current) {
      const containerWidth = containerRef.current.clientWidth;
      const containerHeight = containerRef.current.clientHeight;
      setPan({
        x: containerWidth / 2 - currentNode.x * scale,
        y: containerHeight / 2 - currentNode.y * scale,
      });
    }
    // Only on mount or when currentRoomId changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRoomId]);

  // Pan handlers
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      setDragging(true);
      dragStartRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
    },
    [pan],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging) return;
      const dx = e.clientX - dragStartRef.current.x;
      const dy = e.clientY - dragStartRef.current.y;
      setPan({ x: dragStartRef.current.panX + dx, y: dragStartRef.current.panY + dy });
    },
    [dragging],
  );

  const handleMouseUp = useCallback(() => {
    setDragging(false);
  }, []);

  // Touch handlers for mobile
  const touchStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 1) {
        const touch = e.touches[0];
        touchStartRef.current = { x: touch.clientX, y: touch.clientY, panX: pan.x, panY: pan.y };
      }
    },
    [pan],
  );

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      const touch = e.touches[0];
      const dx = touch.clientX - touchStartRef.current.x;
      const dy = touch.clientY - touchStartRef.current.y;
      setPan({ x: touchStartRef.current.panX + dx, y: touchStartRef.current.panY + dy });
    }
  }, []);

  // Zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setScale((prev) => Math.min(2, Math.max(0.3, prev - e.deltaY * 0.001)));
  }, []);

  const getNodeFill = (node: MapNode): string => {
    if (!node.explored) return '#374151';
    if (node.reliability === 'memory_only') return '#4b5563';
    if (node.reliability === 'uncertain') return ROOM_TYPE_COLORS[node.room_type] ?? '#6b7280';
    return ROOM_TYPE_COLORS[node.room_type] ?? '#6b7280';
  };

  const getNodeOpacity = (node: MapNode): number => {
    if (!node.explored) return 0.5;
    if (node.reliability === 'memory_only') return 0.4;
    if (node.reliability === 'uncertain') return 0.7;
    return 1;
  };

  const getNodeStroke = (node: MapNode): string => {
    if (node.isCurrent) return '#f0d95c';
    if (!node.explored) return '#6b7280';
    if (node.reliability === 'uncertain') return '#eab308';
    if (node.reliability === 'memory_only') return '#6b7280';
    return '#9ca3af';
  };

  const getNodeStrokeWidth = (node: MapNode): number => {
    return node.isCurrent ? 3 : 1.5;
  };

  if (!sessionState.current_room) {
    return (
      <div className="bg-black/40 rounded-card p-4 backdrop-blur-sm flex items-center justify-center min-h-[200px]">
        <p className="text-white/40 text-sm">Карта недоступна</p>
      </div>
    );
  }

  return (
    <div className="bg-black/40 rounded-card backdrop-blur-sm overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <h3 className="gold-text text-base font-medium uppercase">Карта</h3>
        <div className="flex items-center gap-2">
          {stabilityType === 'unstable' && (
            <span className="text-yellow-400 text-[10px]">Нестабильный</span>
          )}
          {stabilityType === 'chaotic' && (
            <span className="text-red-400 text-[10px]">Хаотичный</span>
          )}
          <button
            onClick={() => setScale((s) => Math.min(2, s + 0.2))}
            className="w-6 h-6 flex items-center justify-center text-white/60 hover:text-white transition-colors text-sm bg-white/5 rounded"
          >
            +
          </button>
          <button
            onClick={() => setScale((s) => Math.max(0.3, s - 0.2))}
            className="w-6 h-6 flex items-center justify-center text-white/60 hover:text-white transition-colors text-sm bg-white/5 rounded"
          >
            -
          </button>
        </div>
      </div>

      {/* SVG container */}
      <div
        ref={containerRef}
        className="relative w-full h-[250px] sm:h-[350px] lg:h-[400px] overflow-hidden cursor-grab active:cursor-grabbing select-none"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onWheel={handleWheel}
      >
        <svg
          ref={svgRef}
          width={svgWidth * scale}
          height={svgHeight * scale}
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="absolute"
          style={{
            left: pan.x,
            top: pan.y,
            width: svgWidth * scale,
            height: svgHeight * scale,
          }}
        >
          {/* Glow filter for current room */}
          <defs>
            <filter id="gold-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feFlood floodColor="#f0d95c" floodOpacity="0.6" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="shadow" />
              <feMerge>
                <feMergeNode in="shadow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Edges */}
          {edges.map((edge) => {
            const fromNode = nodeMap.get(edge.from);
            const toNode = nodeMap.get(edge.to);
            if (!fromNode || !toNode) return null;

            const isUnexplored = !fromNode.explored || !toNode.explored;

            return (
              <line
                key={`edge-${edge.from}-${edge.to}`}
                x1={fromNode.x}
                y1={fromNode.y}
                x2={toNode.x}
                y2={toNode.y}
                stroke={isUnexplored ? '#4b5563' : '#9ca3af'}
                strokeWidth={1.5}
                strokeDasharray={isUnexplored ? '6 4' : 'none'}
                opacity={isUnexplored ? 0.5 : 0.7}
              />
            );
          })}

          {/* Nodes */}
          {nodes.map((node) => (
            <g
              key={node.id}
              onClick={() => onRoomClick?.(node.id)}
              className="cursor-pointer"
              filter={node.isCurrent ? 'url(#gold-glow)' : undefined}
            >
              <circle
                cx={node.x}
                cy={node.y}
                r={NODE_RADIUS}
                fill={getNodeFill(node)}
                stroke={getNodeStroke(node)}
                strokeWidth={getNodeStrokeWidth(node)}
                opacity={getNodeOpacity(node)}
                strokeDasharray={!node.explored ? '4 3' : 'none'}
              />

              {/* Room icon/text */}
              <text
                x={node.x}
                y={node.y + 1}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={node.explored ? 14 : 10}
                fill="white"
                opacity={node.explored ? 0.9 : 0.5}
                style={{ pointerEvents: 'none' }}
              >
                {node.explored
                  ? (ROOM_TYPE_ICONS[node.room_type] ?? '\u25CF')
                  : '???'}
              </text>

              {/* Room name below */}
              <text
                x={node.x}
                y={node.y + NODE_RADIUS + 14}
                textAnchor="middle"
                fontSize={10}
                fill={
                  node.reliability === 'uncertain'
                    ? '#eab308'
                    : node.reliability === 'memory_only'
                      ? '#6b7280'
                      : '#d1d5db'
                }
                opacity={node.explored ? 0.8 : 0.4}
                style={{ pointerEvents: 'none' }}
              >
                {node.label.length > 12 ? node.label.slice(0, 11) + '\u2026' : node.label}
              </text>

              {/* Cleared indicator */}
              {node.is_cleared && node.explored && (
                <text
                  x={node.x + NODE_RADIUS - 4}
                  y={node.y - NODE_RADIUS + 6}
                  textAnchor="middle"
                  fontSize={10}
                  fill="#22c55e"
                  style={{ pointerEvents: 'none' }}
                >
                  {'\u2713'}
                </text>
              )}

              {/* Uncertainty warning for unstable */}
              {node.reliability === 'uncertain' && (
                <text
                  x={node.x - NODE_RADIUS + 4}
                  y={node.y - NODE_RADIUS + 6}
                  textAnchor="middle"
                  fontSize={9}
                  fill="#eab308"
                  style={{ pointerEvents: 'none' }}
                >
                  !
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 px-4 py-2 border-t border-white/5">
        {Object.entries(ROOM_TYPE_COLORS).slice(0, 5).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-white/40 text-[9px]">
              {ROOM_TYPE_LABELS[type] ?? type}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const ROOM_TYPE_LABELS: Record<string, string> = {
  battle: 'Бой',
  boss: 'Босс',
  treasure: 'Сокровище',
  trap: 'Ловушка',
  event: 'Событие',
  rest: 'Отдых',
  merchant: 'Торговец',
  fork: 'Развилка',
  teleport: 'Телепорт',
  deadend: 'Тупик',
};

export default DungeonMap;
