import { useMemo, useState, useRef, useCallback, useEffect } from 'react';
import type { RoomExit, RoomView, SessionState, ExploredRoomInfo } from '../../api/dungeons';
import { ROOM_COLORS, ROOM_TYPE_ICONS, ROOM_TYPE_LABELS } from './dungeonConstants';

// --- Types ---

interface DungeonMapProps {
  sessionState: SessionState;
  stabilityType: 'static' | 'unstable' | 'chaotic';
  onMoveToRoom?: (corridorId: number) => void;
  isMoving?: boolean;
  movingToRoomId?: number | null;
}

interface MapRoom {
  id: number;
  name: string;
  room_type: string;
  x: number;
  y: number;
  is_cleared: boolean;
  /** 'current' | 'visited' | 'exit_unexplored' */
  visibility: 'current' | 'visited' | 'exit_unexplored';
}

interface MapCorridor {
  corridorId: number;
  fromRoomId: number;
  toRoomId: number;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  sourceHandle: string | null;
  targetHandle: string | null;
  staminaCost: number;
  isExitPath: boolean;
}

// --- Constants ---

const ROOM_W = 100;
const ROOM_H = 80;
const ROOM_W_SM = 80;
const ROOM_H_SM = 60;
const PADDING = 80;
const BFS_SPACING_X = 160;
const BFS_SPACING_Y = 140;

const MIN_ZOOM = 0.3;
const MAX_ZOOM = 3.0;

// --- Handle position mapping ---

const getHandleOffset = (
  handle: string | null,
  roomW: number,
  roomH: number,
): { x: number; y: number } => {
  if (!handle) return { x: roomW / 2, y: roomH / 2 };

  const [side, numStr] = handle.split('-');
  const num = parseInt(numStr ?? '2', 10);

  // 1 = 25%, 2 = 50%, 3 = 75%
  const fraction = num === 1 ? 0.25 : num === 3 ? 0.75 : 0.5;

  switch (side) {
    case 't':
      return { x: roomW * fraction, y: 0 };
    case 'b':
      return { x: roomW * fraction, y: roomH };
    case 'l':
      return { x: 0, y: roomH * fraction };
    case 'r':
      return { x: roomW, y: roomH * fraction };
    default:
      return { x: roomW / 2, y: roomH / 2 };
  }
};

/** Auto-assign handle sides based on relative room positions when handles are null */
const autoHandleSide = (
  fromX: number, fromY: number, toX: number, toY: number,
  roomW: number, roomH: number,
): { src: string; tgt: string } => {
  const dx = (toX + roomW / 2) - (fromX + roomW / 2);
  const dy = (toY + roomH / 2) - (fromY + roomH / 2);
  if (Math.abs(dx) > Math.abs(dy)) {
    return { src: dx > 0 ? 'r-2' : 'l-2', tgt: dx > 0 ? 'l-2' : 'r-2' };
  }
  return { src: dy > 0 ? 'b-2' : 't-2', tgt: dy > 0 ? 't-2' : 'b-2' };
};

/** Build an orthogonal SVG path with one 90-degree bend */
const buildCorridorPath = (
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  sourceHandle: string | null,
  targetHandle: string | null,
  roomW: number,
  roomH: number,
): string => {
  // Auto-assign handles if missing
  const auto = (!sourceHandle || !targetHandle)
    ? autoHandleSide(fromX, fromY, toX, toY, roomW, roomH)
    : null;
  const effectiveSrcHandle = sourceHandle ?? auto?.src ?? 't-2';
  const effectiveTgtHandle = targetHandle ?? auto?.tgt ?? 't-2';

  const srcOff = getHandleOffset(effectiveSrcHandle, roomW, roomH);
  const tgtOff = getHandleOffset(effectiveTgtHandle, roomW, roomH);

  const sx = fromX + srcOff.x;
  const sy = fromY + srcOff.y;
  const tx = toX + tgtOff.x;
  const ty = toY + tgtOff.y;

  // Determine bend direction based on handle sides
  const srcSide = effectiveSrcHandle.split('-')[0];
  const tgtSide = effectiveTgtHandle.split('-')[0];

  const isHorizontalSrc = srcSide === 'l' || srcSide === 'r';
  const isHorizontalTgt = tgtSide === 'l' || tgtSide === 'r';

  let bendX: number;
  let bendY: number;

  if (isHorizontalSrc && !isHorizontalTgt) {
    bendX = tx;
    bendY = sy;
  } else if (!isHorizontalSrc && isHorizontalTgt) {
    bendX = sx;
    bendY = ty;
  } else if (isHorizontalSrc && isHorizontalTgt) {
    bendX = (sx + tx) / 2;
    bendY = sy;
    return `M ${sx} ${sy} L ${bendX} ${sy} L ${bendX} ${ty} L ${tx} ${ty}`;
  } else {
    bendX = sx;
    bendY = (sy + ty) / 2;
    return `M ${sx} ${sy} L ${sx} ${bendY} L ${tx} ${bendY} L ${tx} ${ty}`;
  }

  return `M ${sx} ${sy} L ${bendX} ${bendY} L ${tx} ${ty}`;
};

// --- BFS fallback layout ---

const bfsLayout = (
  currentRoom: RoomView,
  exploredRooms: ExploredRoomInfo[],
): Map<number, { x: number; y: number }> => {
  const positions = new Map<number, { x: number; y: number }>();
  const visited = new Set<number>();
  const queue: { id: number; depth: number; index: number }[] = [];
  const depthBuckets = new Map<number, number>();

  // Build adjacency from exits
  const adj = new Map<number, number[]>();
  for (const exit of currentRoom.exits) {
    if (!adj.has(currentRoom.id)) adj.set(currentRoom.id, []);
    adj.get(currentRoom.id)!.push(exit.to_room_id);
    if (!adj.has(exit.to_room_id)) adj.set(exit.to_room_id, []);
    adj.get(exit.to_room_id)!.push(currentRoom.id);
  }

  queue.push({ id: currentRoom.id, depth: 0, index: 0 });
  visited.add(currentRoom.id);

  while (queue.length > 0) {
    const item = queue.shift()!;
    const countAtDepth = depthBuckets.get(item.depth) ?? 0;
    depthBuckets.set(item.depth, countAtDepth + 1);

    positions.set(item.id, {
      x: PADDING + countAtDepth * BFS_SPACING_X,
      y: PADDING + item.depth * BFS_SPACING_Y,
    });

    const neighbors = adj.get(item.id) ?? [];
    for (const n of neighbors) {
      if (!visited.has(n)) {
        visited.add(n);
        queue.push({ id: n, depth: item.depth + 1, index: 0 });
      }
    }
  }

  // Place explored rooms not yet positioned
  for (const room of exploredRooms) {
    if (!positions.has(room.id)) {
      const countAtDepth = depthBuckets.get(0) ?? 0;
      depthBuckets.set(0, countAtDepth + 1);
      positions.set(room.id, {
        x: PADDING + countAtDepth * BFS_SPACING_X,
        y: PADDING,
      });
    }
  }

  // Center nodes per depth
  const allPositions = Array.from(positions.entries());
  const maxX = Math.max(...allPositions.map(([, p]) => p.x)) + PADDING;
  const depthGroups = new Map<number, { id: number; x: number; y: number }[]>();

  for (const [id, pos] of allPositions) {
    if (!depthGroups.has(pos.y)) depthGroups.set(pos.y, []);
    depthGroups.get(pos.y)!.push({ id, ...pos });
  }

  for (const group of depthGroups.values()) {
    const groupWidth = (group.length - 1) * BFS_SPACING_X;
    const offset = (maxX - groupWidth) / 2;
    group.forEach((item, i) => {
      positions.set(item.id, { x: offset + i * BFS_SPACING_X, y: item.y });
    });
  }

  return positions;
};

// --- Build map data ---

const buildMapData = (
  sessionState: SessionState,
): { rooms: MapRoom[]; corridors: MapCorridor[] } => {
  const currentRoom = sessionState.current_room;
  if (!currentRoom) return { rooms: [], corridors: [] };

  const exploredRooms = sessionState.explored_rooms ?? [];
  const exitRoomIds = new Set(currentRoom.exits.map((e) => e.to_room_id));

  // Check if we have server-side positions
  const hasPositions =
    currentRoom.position_x != null &&
    currentRoom.position_y != null;

  // Use BFS fallback if positions are missing
  let positionMap: Map<number, { x: number; y: number }> | null = null;
  if (!hasPositions) {
    positionMap = bfsLayout(currentRoom, exploredRooms);
  }

  const getPos = (
    id: number,
    posX: number | null | undefined,
    posY: number | null | undefined,
  ): { x: number; y: number } => {
    if (posX != null && posY != null) return { x: posX, y: posY };
    if (positionMap) return positionMap.get(id) ?? { x: PADDING, y: PADDING };
    return { x: PADDING, y: PADDING };
  };

  const rooms: MapRoom[] = [];
  const roomIdSet = new Set<number>();

  // Current room
  const curPos = getPos(currentRoom.id, currentRoom.position_x, currentRoom.position_y);
  rooms.push({
    id: currentRoom.id,
    name: currentRoom.name,
    room_type: currentRoom.room_type,
    x: curPos.x,
    y: curPos.y,
    is_cleared: currentRoom.is_cleared,
    visibility: 'current',
  });
  roomIdSet.add(currentRoom.id);

  // Explored rooms
  for (const er of exploredRooms) {
    if (roomIdSet.has(er.id)) continue;
    const pos = getPos(er.id, er.position_x, er.position_y);
    rooms.push({
      id: er.id,
      name: er.name,
      room_type: er.room_type,
      x: pos.x,
      y: pos.y,
      is_cleared: er.is_cleared,
      visibility: 'visited',
    });
    roomIdSet.add(er.id);
  }

  // Exit rooms (not yet visited)
  for (const exit of currentRoom.exits) {
    if (roomIdSet.has(exit.to_room_id)) continue;
    const pos = getPos(exit.to_room_id, exit.position_x, exit.position_y);
    rooms.push({
      id: exit.to_room_id,
      name: exit.explored ? exit.to_room_name : '???',
      room_type: exit.explored ? 'fork' : 'unknown',
      x: pos.x,
      y: pos.y,
      is_cleared: false,
      visibility: 'exit_unexplored',
    });
    roomIdSet.add(exit.to_room_id);
  }

  // Corridors from current room exits
  const corridors: MapCorridor[] = [];
  for (const exit of currentRoom.exits) {
    const fromRoom = rooms.find((r) => r.id === currentRoom.id);
    const toRoom = rooms.find((r) => r.id === exit.to_room_id);
    if (!fromRoom || !toRoom) continue;
    corridors.push({
      corridorId: exit.corridor_id,
      fromRoomId: currentRoom.id,
      toRoomId: exit.to_room_id,
      fromX: fromRoom.x,
      fromY: fromRoom.y,
      toX: toRoom.x,
      toY: toRoom.y,
      sourceHandle: exit.source_handle,
      targetHandle: exit.target_handle,
      staminaCost: exit.stamina_cost,
      isExitPath: true,
    });
  }

  // Corridors between explored rooms (from explored_corridors in session state)
  const exitCorridorIds = new Set(corridors.map((c) => c.corridorId));
  for (const ec of sessionState.explored_corridors ?? []) {
    if (exitCorridorIds.has(ec.corridor_id)) continue; // already added as exit path
    const fromRoom = rooms.find((r) => r.id === ec.from_room_id);
    const toRoom = rooms.find((r) => r.id === ec.to_room_id);
    if (!fromRoom || !toRoom) continue;
    corridors.push({
      corridorId: ec.corridor_id,
      fromRoomId: ec.from_room_id,
      toRoomId: ec.to_room_id,
      fromX: fromRoom.x,
      fromY: fromRoom.y,
      toX: toRoom.x,
      toY: toRoom.y,
      sourceHandle: ec.source_handle,
      targetHandle: ec.target_handle,
      staminaCost: 0,
      isExitPath: false,
    });
  }

  return { rooms, corridors };
};

// --- Animation marker ---

const useMovementAnimation = (
  isMoving: boolean,
  movingToRoomId: number | null | undefined,
  corridors: MapCorridor[],
  roomW: number,
  roomH: number,
) => {
  const [markerPos, setMarkerPos] = useState<{ x: number; y: number } | null>(null);
  const animRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isMoving || movingToRoomId == null) {
      setMarkerPos(null);
      return;
    }

    const corridor = corridors.find((c) => c.toRoomId === movingToRoomId);
    if (!corridor) {
      setMarkerPos(null);
      return;
    }

    // Auto-assign handles if missing
    const auto = (!corridor.sourceHandle || !corridor.targetHandle)
      ? autoHandleSide(corridor.fromX, corridor.fromY, corridor.toX, corridor.toY, roomW, roomH)
      : null;
    const effSrc = corridor.sourceHandle ?? auto?.src ?? 't-2';
    const effTgt = corridor.targetHandle ?? auto?.tgt ?? 't-2';

    const srcOff = getHandleOffset(effSrc, roomW, roomH);
    const tgtOff = getHandleOffset(effTgt, roomW, roomH);

    const sx = corridor.fromX + srcOff.x;
    const sy = corridor.fromY + srcOff.y;
    const tx = corridor.toX + tgtOff.x;
    const ty = corridor.toY + tgtOff.y;

    // Build waypoints matching the corridor path (orthogonal bends)
    const srcSide = effSrc.split('-')[0];
    const tgtSide = effTgt.split('-')[0];
    const isHSrc = srcSide === 'l' || srcSide === 'r';
    const isHTgt = tgtSide === 'l' || tgtSide === 'r';

    const points: { x: number; y: number }[] = [{ x: sx, y: sy }];
    if (isHSrc && !isHTgt) {
      points.push({ x: tx, y: sy });
    } else if (!isHSrc && isHTgt) {
      points.push({ x: sx, y: ty });
    } else if (isHSrc && isHTgt) {
      const mx = (sx + tx) / 2;
      points.push({ x: mx, y: sy }, { x: mx, y: ty });
    } else {
      const my = (sy + ty) / 2;
      points.push({ x: sx, y: my }, { x: tx, y: my });
    }
    points.push({ x: tx, y: ty });

    // Compute cumulative segment lengths for uniform-speed interpolation
    const segLens: number[] = [];
    let totalLen = 0;
    for (let i = 1; i < points.length; i++) {
      const dx = points[i].x - points[i - 1].x;
      const dy = points[i].y - points[i - 1].y;
      const len = Math.sqrt(dx * dx + dy * dy);
      segLens.push(len);
      totalLen += len;
    }

    const duration = 800;
    let startTime: number | null = null;

    const animate = (timestamp: number) => {
      if (startTime === null) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = progress < 0.5
        ? 2 * progress * progress
        : 1 - Math.pow(-2 * progress + 2, 2) / 2;

      // Interpolate along waypoints
      const targetDist = eased * totalLen;
      let accumulated = 0;
      let px = sx;
      let py = sy;
      for (let i = 0; i < segLens.length; i++) {
        if (accumulated + segLens[i] >= targetDist) {
          const segProgress = segLens[i] > 0 ? (targetDist - accumulated) / segLens[i] : 0;
          px = points[i].x + (points[i + 1].x - points[i].x) * segProgress;
          py = points[i].y + (points[i + 1].y - points[i].y) * segProgress;
          break;
        }
        accumulated += segLens[i];
        px = points[i + 1].x;
        py = points[i + 1].y;
      }

      setMarkerPos({ x: px, y: py });

      if (progress < 1) {
        animRef.current = requestAnimationFrame(animate);
      }
    };

    animRef.current = requestAnimationFrame(animate);

    return () => {
      if (animRef.current != null) cancelAnimationFrame(animRef.current);
    };
  }, [isMoving, movingToRoomId, corridors, roomW, roomH]);

  return markerPos;
};

// --- Component ---

const DungeonMap = ({
  sessionState,
  stabilityType,
  onMoveToRoom,
  isMoving = false,
  movingToRoomId = null,
}: DungeonMapProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [scale, setScale] = useState(1);
  const [dragging, setDragging] = useState(false);
  const [hoveredRoomId, setHoveredRoomId] = useState<number | null>(null);
  const dragStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const touchStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const pinchStartRef = useRef<number | null>(null);
  const pinchScaleStartRef = useRef<number>(1);

  const currentRoom = sessionState.current_room;
  const currentRoomId = currentRoom?.id ?? 0;

  // Determine if mobile
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 1024);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const roomW = isMobile ? ROOM_W_SM : ROOM_W;
  const roomH = isMobile ? ROOM_H_SM : ROOM_H;

  const { rooms, corridors } = useMemo(
    () => buildMapData(sessionState),
    [sessionState],
  );

  // Exit room IDs (clickable)
  const exitMap = useMemo(() => {
    const m = new Map<number, RoomExit>();
    if (currentRoom) {
      for (const exit of currentRoom.exits) {
        m.set(exit.to_room_id, exit);
      }
    }
    return m;
  }, [currentRoom]);

  // SVG viewBox dimensions
  const { svgW, svgH } = useMemo(() => {
    if (rooms.length === 0) return { svgW: 400, svgH: 300 };
    const maxX = Math.max(...rooms.map((r) => r.x + roomW));
    const maxY = Math.max(...rooms.map((r) => r.y + roomH));
    return {
      svgW: maxX + PADDING * 2,
      svgH: maxY + PADDING * 2,
    };
  }, [rooms, roomW, roomH]);

  // Auto-center on current room
  useEffect(() => {
    const curRoom = rooms.find((r) => r.id === currentRoomId);
    if (curRoom && containerRef.current) {
      const cw = containerRef.current.clientWidth;
      const ch = containerRef.current.clientHeight;
      setPan({
        x: cw / 2 - (curRoom.x + roomW / 2) * scale,
        y: ch / 2 - (curRoom.y + roomH / 2) * scale,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRoomId, roomW, roomH]);

  // Movement animation
  const markerPos = useMovementAnimation(isMoving, movingToRoomId, corridors, roomW, roomH);

  // --- Pan handlers ---
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
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

  const handleMouseUp = useCallback(() => setDragging(false), []);

  // --- Touch handlers ---
  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 1) {
        const t = e.touches[0];
        touchStartRef.current = { x: t.clientX, y: t.clientY, panX: pan.x, panY: pan.y };
      } else if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        pinchStartRef.current = Math.hypot(dx, dy);
        pinchScaleStartRef.current = scale;
      }
    },
    [pan, scale],
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 1 && pinchStartRef.current === null) {
        const t = e.touches[0];
        const dx = t.clientX - touchStartRef.current.x;
        const dy = t.clientY - touchStartRef.current.y;
        setPan({ x: touchStartRef.current.panX + dx, y: touchStartRef.current.panY + dy });
      } else if (e.touches.length === 2 && pinchStartRef.current !== null) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.hypot(dx, dy);
        const newScale = pinchScaleStartRef.current * (dist / pinchStartRef.current);
        setScale(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, newScale)));
      }
    },
    [],
  );

  const handleTouchEnd = useCallback(() => {
    pinchStartRef.current = null;
  }, []);

  // --- Zoom ---
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setScale((prev) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, prev - e.deltaY * 0.001)));
  }, []);

  // --- Room click ---
  const handleRoomClick = useCallback(
    (roomId: number) => {
      if (isMoving || !onMoveToRoom) return;
      const exit = exitMap.get(roomId);
      if (!exit) return;
      onMoveToRoom(exit.corridor_id);
    },
    [isMoving, onMoveToRoom, exitMap],
  );

  // --- Get stamina cost for tooltip ---
  const getStaminaCost = (roomId: number): number | null => {
    const exit = exitMap.get(roomId);
    return exit?.stamina_cost ?? null;
  };

  if (!currentRoom) {
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
        <h3 className="gold-text text-base font-medium uppercase tracking-wider">Карта</h3>
        <div className="flex items-center gap-2">
          {stabilityType === 'unstable' && (
            <span className="text-yellow-400 text-[10px]">Нестабильный</span>
          )}
          {stabilityType === 'chaotic' && (
            <span className="text-red-400 text-[10px]">Хаотичный</span>
          )}
          <button
            onClick={() => setScale((s) => Math.min(MAX_ZOOM, s + 0.2))}
            className="w-6 h-6 flex items-center justify-center text-white/60 hover:text-white transition-colors text-sm bg-white/5 rounded"
            title="Приблизить"
          >
            +
          </button>
          <button
            onClick={() => setScale((s) => Math.max(MIN_ZOOM, s - 0.2))}
            className="w-6 h-6 flex items-center justify-center text-white/60 hover:text-white transition-colors text-sm bg-white/5 rounded"
            title="Отдалить"
          >
            -
          </button>
        </div>
      </div>

      {/* SVG container */}
      <div
        ref={containerRef}
        className="relative w-full h-[280px] sm:h-[380px] lg:h-[460px] overflow-hidden cursor-grab active:cursor-grabbing select-none"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onWheel={handleWheel}
      >
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${svgW} ${svgH}`}
          preserveAspectRatio="xMidYMid meet"
          style={{ position: 'absolute', left: 0, top: 0 }}
        >
          <defs>
            {/* Background gradient */}
            <radialGradient id="dm-bg-grad" cx="50%" cy="50%" r="70%">
              <stop offset="0%" stopColor="#1a1a2e" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#0d0d1a" stopOpacity="1" />
            </radialGradient>

            {/* Noise texture filter */}
            <filter id="dm-noise">
              <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" result="noise" />
              <feColorMatrix in="noise" type="saturate" values="0" result="grayNoise" />
              <feBlend in="SourceGraphic" in2="grayNoise" mode="multiply" />
            </filter>

            {/* Gold glow for current room */}
            <filter id="dm-gold-glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feFlood floodColor="#f0d95c" floodOpacity="0.5" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="shadow" />
              <feMerge>
                <feMergeNode in="shadow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Corridor glow for active paths */}
            <filter id="dm-path-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feFlood floodColor="#f0d95c" floodOpacity="0.3" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="shadow" />
              <feMerge>
                <feMergeNode in="shadow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Blur filter for unexplored exits */}
            <filter id="dm-fog-blur">
              <feGaussianBlur stdDeviation="1.5" />
            </filter>

            {/* Movement marker glow */}
            <filter id="dm-marker-glow" x="-100%" y="-100%" width="300%" height="300%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feFlood floodColor="#f0d95c" floodOpacity="0.8" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="shadow" />
              <feMerge>
                <feMergeNode in="shadow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Pulsing animation for current room */}
            <style>{`
              @keyframes dm-pulse {
                0%, 100% { opacity: 0.6; }
                50% { opacity: 1; }
              }
              .dm-current-glow {
                animation: dm-pulse 2s ease-in-out infinite;
              }
              @keyframes dm-marker-pulse {
                0%, 100% { r: 6; opacity: 0.8; }
                50% { r: 9; opacity: 1; }
              }
            `}</style>
          </defs>

          {/* Transform group for pan/zoom */}
          <g transform={`translate(${pan.x / 1} ${pan.y / 1}) scale(${scale})`}>
            {/* Background rect */}
            <rect
              x={-PADDING}
              y={-PADDING}
              width={svgW + PADDING * 2}
              height={svgH + PADDING * 2}
              fill="url(#dm-bg-grad)"
              rx={8}
            />

            {/* Corridors */}
            {corridors.map((c) => {
              const pathD = buildCorridorPath(
                c.fromX,
                c.fromY,
                c.toX,
                c.toY,
                c.sourceHandle,
                c.targetHandle,
                roomW,
                roomH,
              );

              const isAnimating = isMoving && movingToRoomId === c.toRoomId;
              const color = c.isExitPath
                ? (ROOM_COLORS[rooms.find((r) => r.id === c.toRoomId)?.room_type ?? ''] ?? '#9ca3af')
                : '#4b5563';

              return (
                <g key={`corridor-${c.corridorId}`}>
                  <path
                    d={pathD}
                    fill="none"
                    stroke={c.isExitPath ? color : '#4b5563'}
                    strokeWidth={c.isExitPath ? 2.5 : 1.5}
                    strokeOpacity={c.isExitPath ? 0.7 : 0.3}
                    strokeLinecap="round"
                    filter={isAnimating ? 'url(#dm-path-glow)' : (c.isExitPath ? 'url(#dm-path-glow)' : undefined)}
                  />
                  {/* Dashed overlay for unexplored exits */}
                  {!exitMap.get(c.toRoomId)?.explored && (
                    <path
                      d={pathD}
                      fill="none"
                      stroke={color}
                      strokeWidth={1}
                      strokeOpacity={0.3}
                      strokeDasharray="6 4"
                      strokeLinecap="round"
                    />
                  )}
                </g>
              );
            })}

            {/* Rooms */}
            {rooms.map((room) => {
              const isClickable = exitMap.has(room.id) && !isMoving;
              const isHovered = hoveredRoomId === room.id;
              const staminaCost = getStaminaCost(room.id);
              const roomColor = ROOM_COLORS[room.room_type] ?? '#6b7280';
              const roomIcon = ROOM_TYPE_ICONS[room.room_type] ?? '';
              const roomLabel = ROOM_TYPE_LABELS[room.room_type] ?? '';

              let opacity = 1;
              let filterAttr: string | undefined;
              let strokeColor = '#4b5563';
              let strokeWidth = 1.5;
              let fillColor = 'rgba(26, 26, 46, 0.9)';
              let textColor = '#d4d4d8';
              let nameText = room.name.length > 14 ? room.name.slice(0, 13) + '\u2026' : room.name;

              if (room.visibility === 'current') {
                strokeColor = '#f0d95c';
                strokeWidth = 2.5;
                fillColor = 'rgba(40, 38, 30, 0.95)';
                textColor = '#f0d95c';
                filterAttr = 'url(#dm-gold-glow)';
              } else if (room.visibility === 'visited') {
                opacity = 0.7;
                strokeColor = roomColor;
                strokeWidth = 1.5;
              } else if (room.visibility === 'exit_unexplored') {
                opacity = 0.35;
                filterAttr = 'url(#dm-fog-blur)';
                nameText = '???';
                strokeColor = '#6b7280';
                textColor = '#9ca3af';
              }

              if (isHovered && isClickable) {
                opacity = Math.min(opacity + 0.3, 1);
                strokeColor = '#f0d95c';
                strokeWidth = 2.5;
              }

              return (
                <g
                  key={`room-${room.id}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRoomClick(room.id);
                  }}
                  onMouseEnter={() => isClickable && setHoveredRoomId(room.id)}
                  onMouseLeave={() => setHoveredRoomId(null)}
                  style={{
                    cursor: isClickable ? 'pointer' : 'default',
                    opacity,
                    transition: 'opacity 0.2s ease',
                  }}
                  filter={filterAttr}
                >
                  {/* Pulsing glow ring for current room */}
                  {room.visibility === 'current' && (
                    <rect
                      x={room.x - 4}
                      y={room.y - 4}
                      width={roomW + 8}
                      height={roomH + 8}
                      rx={10}
                      fill="none"
                      stroke="#f0d95c"
                      strokeWidth={1.5}
                      className="dm-current-glow"
                    />
                  )}

                  {/* Room background */}
                  <rect
                    x={room.x}
                    y={room.y}
                    width={roomW}
                    height={roomH}
                    rx={8}
                    fill={fillColor}
                    stroke={strokeColor}
                    strokeWidth={strokeWidth}
                  />

                  {/* Colored top accent bar */}
                  {room.visibility !== 'exit_unexplored' && (
                    <rect
                      x={room.x + 1}
                      y={room.y + 1}
                      width={roomW - 2}
                      height={3}
                      rx={2}
                      fill={roomColor}
                      opacity={0.8}
                    />
                  )}

                  {/* Room icon */}
                  <text
                    x={room.x + roomW / 2}
                    y={room.y + (isMobile ? 22 : 28)}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={isMobile ? 16 : 20}
                    fill="white"
                    style={{ pointerEvents: 'none' }}
                  >
                    {room.visibility === 'exit_unexplored' ? '?' : roomIcon}
                  </text>

                  {/* Room name */}
                  <text
                    x={room.x + roomW / 2}
                    y={room.y + (isMobile ? 42 : 52)}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={isMobile ? 8 : 10}
                    fill={textColor}
                    style={{ pointerEvents: 'none' }}
                  >
                    {nameText}
                  </text>

                  {/* Room type label */}
                  {room.visibility !== 'exit_unexplored' && roomLabel && (
                    <text
                      x={room.x + roomW / 2}
                      y={room.y + roomH - (isMobile ? 8 : 10)}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fontSize={isMobile ? 7 : 8}
                      fill="#9ca3af"
                      opacity={0.6}
                      style={{ pointerEvents: 'none' }}
                    >
                      {roomLabel}
                    </text>
                  )}

                  {/* Cleared checkmark */}
                  {room.is_cleared && room.visibility !== 'exit_unexplored' && (
                    <text
                      x={room.x + roomW - 12}
                      y={room.y + 12}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fontSize={11}
                      fill="#22c55e"
                      style={{ pointerEvents: 'none' }}
                    >
                      {'\u2713'}
                    </text>
                  )}

                  {/* Stamina cost tooltip on hover */}
                  {isHovered && staminaCost !== null && (
                    <g>
                      <rect
                        x={room.x + roomW / 2 - 36}
                        y={room.y - 28}
                        width={72}
                        height={22}
                        rx={4}
                        fill="rgba(0,0,0,0.85)"
                        stroke="#f0d95c"
                        strokeWidth={0.5}
                      />
                      <text
                        x={room.x + roomW / 2}
                        y={room.y - 17}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fontSize={10}
                        fill="#f0d95c"
                        style={{ pointerEvents: 'none' }}
                      >
                        {`\u26A1 ${staminaCost} стамины`}
                      </text>
                    </g>
                  )}

                  {/* SVG title for native tooltip fallback */}
                  {isClickable && staminaCost !== null && (
                    <title>{`Перейти (${staminaCost} стамины)`}</title>
                  )}
                </g>
              );
            })}

            {/* Movement animation marker */}
            {markerPos && (
              <circle
                cx={markerPos.x}
                cy={markerPos.y}
                r={8}
                fill="#f0d95c"
                filter="url(#dm-marker-glow)"
                style={{ transition: 'none' }}
              />
            )}
          </g>
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 px-4 py-2 border-t border-white/5">
        {Object.entries(ROOM_COLORS).slice(0, 6).map(([type, color]) => (
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

export default DungeonMap;
