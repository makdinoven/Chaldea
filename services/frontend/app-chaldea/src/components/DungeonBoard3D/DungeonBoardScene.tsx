import { useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { createDieFaceTexture, createFlameTexture, createSoftSpotTexture } from '../pages/BattlePage/Arena3D/textures';
import { createChalkTexture, createDoorWoodTexture, createMistTexture, createReachRingTexture, disposeAll } from './tileTextures';
import { THEME_LOOK } from './dungeonThemes';
import { paintTheme } from './themePaint';
import { toTexture } from '../pages/BattlePage/Arena3D/textures';
import { buildDioramaLayout, corridorKey, ownerKey, SQUARE, type DioramaLayout, type RoomInfo } from './dioramaLayout';
import { FLOOR_THICKNESS, PieceMesh, Rising, Torches, WALL_THICKNESS, type StoneMaterials } from './DioramaPieces';
import { furnishingFootprints, RoomFurnishing, type Footprint } from './RoomFurnishing';
import type { BoardDungeon, BoardMember, BoardRoom } from './boardTypes';
import { ChalkOutline, Door, DoorMist, type DoorMaterials, type DungeonStability } from './DungeonDoors';
import BoardFog from './BoardFog';
import { playDungeonSound } from '../../utils/dungeonSounds';
import RockBed, { ROCK_EDGE, type RockRect } from './RockBed';
import { EnemyFigure, enemySpots, RoomEnemies, useEnemyKit, type EnemyKit } from './EnemyFigures';
import { SparkField, SparkPool } from '../DungeonPage/minigames/three/craftKit';
import { FloorShift, PassageMarker, spotOf } from './DungeonPassages';
import { PieceDecor, useDecorKit, useDecorPulse } from './DungeonDecor';
import { PartyMiniature } from './PartyMiniature';
import { PartyMarks, type BoardMark } from './PartyMarks';

/*
  A dungeon as a miniature on the table of fates. The gods build it piece by
  piece as the party goes: a corridor ends in a shut door where nobody has been
  yet; when the party walks through, the door swings open and the stone room
  rises out of the board behind it. What shows beyond a shut door follows the
  dungeon's stability (see DungeonDoors). The party is a handful of ivory
  figurines; risky corridors are decided by a throw of the gods' dice.
*/

const BOARD_MARGIN = 1.6;
const BOARD_THICKNESS = 0.2;
const BOARD_TOP = BOARD_THICKNESS;
/** A room cell of the editor's grid on the table (ROOM_SPACING squares), and half a room's breadth. */
const ROOM_CELL_WORLD = 7 * SQUARE;
const ROOM_HALF_WORLD = 3 * SQUARE;
const CAMERA_FOV = 40;
const CAMERA_PITCH = THREE.MathUtils.degToRad(63);
/** Camera distance: the party's room and the ones around it fill the view. */
const CAMERA_DISTANCE = 6.2;
/** The room starts rising once its door is well open. */
const RISE_DELAY_MS = 600;
/** A teleport has no corridor to walk: the figurines leap across instead. */
const HOP_HEIGHT = 0.5;
const HOP_SECONDS = 0.9;
const HOP_STAGGER = 0.25;
/** Walking pace of the figurines along a corridor, world units per second. */
const WALK_SPEED = 1.3;
/** Each step lifts a figurine a little: steps per world unit, and how high. */
const STEP_RATE = 9;
const STEP_HEIGHT = 0.05;
const PAWN_SCALE = 0.6;
/** How quickly a figure turns to face where it walks. */
const TURN_RATE = 8;
const DICE_SECONDS = 1.1;
/** Figurines in single file down a corridor stand this far apart. */
const CORRIDOR_FILE_GAP = 0.26;
/** How far ahead of the party an ambush blocks the corridor. */
const CORRIDOR_AMBUSH_GAP = 0.42;
const AMBUSHERS = 2;

type Vec3 = [number, number, number];

const NO_MARKS: BoardMark[] = [];

export interface DiceThrow {
  values: [number, number];
  /** performance.now() when thrown; a new value throws again. */
  at: number;
}

/**
 * The party halfway down a corridor: caught by an ambush (enemies block the
 * way on), or crossing a trapped stretch (the trap springs at `trap.at`).
 */
export interface CorridorScene {
  from: number;
  to: number;
  ambush: boolean;
  trap: { at: number; passed: boolean } | null;
}

/** The span of the floor shown, in room cells (every room, known or not): the rock is laid under all of it. */
export interface FloorSpan {
  minCol: number;
  maxCol: number;
  minRow: number;
  maxRow: number;
}

export interface DungeonBoardSceneProps {
  dungeon: BoardDungeon;
  party: BoardMember[];
  currentRoomId: number;
  revealed: Set<number>;
  cleared: Set<number>;
  reachable: Set<number>;
  dice: DiceThrow | null;
  /** The party halfway down a corridor (an ambush, a trap), or null. */
  corridor?: CorridorScene | null;
  /** The whole floor's span (a live run): the rock under it is laid at once and never grows. */
  span?: FloorSpan | null;
  /** The party's flags (where each would go) and flashing marks. */
  marks?: BoardMark[];
  lowGraphics?: boolean;
  /** Multiplies the camera distance: below 1 closer, above 1 farther. */
  zoom?: number;
  /** Look at the middle of the whole dungeon instead of following the party. */
  overview?: boolean;
  /**
   * Keep rooms where they were built while the known map grows (a live run):
   * the board is laid under the dungeon instead of the dungeon being centred.
   */
  fixedOrigin?: boolean;
  /** What a shut door gives away: chalk outline (static), nothing (unstable), mist (chaotic). */
  stability?: DungeonStability;
  onTileClick: (roomId: number) => void;
  /** The figurines have finished walking into this room (also once on mount). */
  onPartyArrived?: (roomId: number) => void;
  /** The pointer is over a room or its door (screen position), or over nothing (null). */
  onRoomHover?: (hover: { roomId: number; x: number; y: number } | null) => void;
  /** The floor on the table: a new one rises from below (or settles from above). */
  floor?: number;
}

/* ── Camera ── */

/** Looks down at the party from the players' side of the table and drifts after it. */
/** On a portrait screen the party is drawn this share of the height below the middle, clear of the page's top overlays. */
const PORTRAIT_LIFT = 0.1;
/** A press that moves the pointer further than this (px) drags the camera instead of clicking. */
const DRAG_THRESHOLD_PX = 5;

interface CameraRigProps {
  focus: Vec3;
  zoom: number;
  overview: boolean;
  /** The area the view may be dragged over: centre and half extents on the board. */
  bounds?: { center: [number, number]; half: [number, number] };
  /** Set while (and right after) the board is being dragged, so the release is not taken for a click. */
  dragged?: { current: boolean };
}

const CameraRig = ({ focus, zoom, overview, bounds, dragged }: CameraRigProps) => {
  const { camera, size, gl } = useThree();
  const target = useRef(new THREE.Vector3(...focus));
  // Where the player has dragged the view, on top of what it follows.
  const pan = useRef(new THREE.Vector3());
  const portrait = size.width < size.height;
  const goal = (portrait ? CAMERA_DISTANCE * 1.45 : CAMERA_DISTANCE) * zoom;
  const current = useRef(goal);

  const place = () => {
    const distance = current.current;
    const x = target.current.x + pan.current.x;
    const z = target.current.z + pan.current.z;
    camera.position.set(x, Math.sin(CAMERA_PITCH) * distance, z + Math.cos(CAMERA_PITCH) * distance);
    camera.lookAt(x, 0, z);
    camera.updateMatrixWorld();
  };

  // A new room to follow or the whole map: the drag is let go, and the view glides back.
  const focusKey = `${focus[0]},${focus[2]},${overview}`;
  useEffect(() => {
    target.current.add(pan.current);
    pan.current.set(0, 0, 0);
  }, [focusKey]);

  // Hold the left button (or a finger) and drag: the board follows the pointer.
  useEffect(() => {
    const el = gl.domElement;
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -BOARD_TOP);
    const ray = new THREE.Raycaster();
    const boardPoint = (e: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      ray.setFromCamera(
        new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1),
        camera,
      );
      return ray.ray.intersectPlane(plane, new THREE.Vector3());
    };
    let press: { id: number; x: number; y: number; grab: THREE.Vector3 | null } | null = null;
    let dragging = false;
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || press) return;
      press = { id: e.pointerId, x: e.clientX, y: e.clientY, grab: boardPoint(e) };
      dragging = false;
      if (dragged) dragged.current = false;
    };
    const move = (e: PointerEvent) => {
      if (!press || e.pointerId !== press.id || !press.grab) return;
      if (!dragging) {
        if (Math.hypot(e.clientX - press.x, e.clientY - press.y) < DRAG_THRESHOLD_PX) return;
        dragging = true;
        if (dragged) dragged.current = true;
        el.setPointerCapture(e.pointerId);
        document.body.style.cursor = 'grabbing';
      }
      const at = boardPoint(e);
      if (!at) return;
      pan.current.x += press.grab.x - at.x;
      pan.current.z += press.grab.z - at.z;
      if (bounds) {
        // Keep the view over the dungeon: the point looked at stays inside its area.
        const lx = target.current.x + pan.current.x;
        const lz = target.current.z + pan.current.z;
        const cx = THREE.MathUtils.clamp(lx, bounds.center[0] - bounds.half[0], bounds.center[0] + bounds.half[0]);
        const cz = THREE.MathUtils.clamp(lz, bounds.center[1] - bounds.half[1], bounds.center[1] + bounds.half[1]);
        pan.current.x += cx - lx;
        pan.current.z += cz - lz;
      }
      place();
    };
    const up = (e: PointerEvent) => {
      if (!press || e.pointerId !== press.id) return;
      press = null;
      if (dragging) {
        document.body.style.cursor = '';
        if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      }
      dragging = false;
    };
    el.style.touchAction = 'none';
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gl, camera, bounds?.center[0], bounds?.center[1], bounds?.half[0], bounds?.half[1]]);
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    if (portrait && !overview) {
      cam.setViewOffset(size.width, size.height, 0, -size.height * PORTRAIT_LIFT, size.width, size.height);
    } else {
      cam.clearViewOffset();
    }
  }, [camera, portrait, overview, size.width, size.height]);
  useFrame((_, delta) => {
    const k = 1 - Math.exp(-delta * 2.5);
    target.current.lerp(new THREE.Vector3(focus[0], 0, focus[2]), k);
    current.current += (goal - current.current) * k;
    place();
  });
  return null;
};

/* ── Reachable rooms ── */

/** A pulsing glow on the board under a room the party can walk to. */
const ReachGlow = ({ room, ring, raised }: { room: RoomInfo; ring: THREE.Texture; raised: boolean }) => {
  const material = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }) => {
    if (material.current) material.current.opacity = 0.45 + Math.sin(clock.elapsedTime * 3) * 0.2;
  });
  const y = BOARD_TOP + (raised ? FLOOR_THICKNESS + 0.01 : 0.004);
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[room.center[0], y, room.center[1]]}>
      <planeGeometry args={[room.size[0] * 1.35, room.size[1] * 1.35]} />
      <meshBasicMaterial
        ref={material}
        map={ring}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </mesh>
  );
};

/** How deep the gloom of an unlit dark room is, and how fast it lifts or falls. */
const GLOOM_OPACITY = 0.78;
const GLOOM_HEIGHT = 0.7;
const GLOOM_FADE = 2.5;

/** A dark room sunk in gloom until a light burns in it; the gloom lifts slowly. */
const RoomGloom = ({ room, dark }: { room: RoomInfo; dark: boolean }) => {
  const mesh = useRef<THREE.Mesh>(null);
  const material = useRef<THREE.MeshBasicMaterial>(null);
  useFrame((_, delta) => {
    if (!material.current || !mesh.current) return;
    const target = dark ? GLOOM_OPACITY : 0;
    const k = Math.min(1, delta * GLOOM_FADE);
    material.current.opacity += (target - material.current.opacity) * k;
    mesh.current.visible = material.current.opacity > 0.01;
  });
  return (
    <mesh
      ref={mesh}
      position={[room.center[0], BOARD_TOP + FLOOR_THICKNESS + GLOOM_HEIGHT / 2, room.center[1]]}
      raycast={() => null}
    >
      <boxGeometry args={[room.size[0] * 1.02, GLOOM_HEIGHT, room.size[1] * 1.02]} />
      <meshBasicMaterial ref={material} color="#040306" transparent opacity={dark ? GLOOM_OPACITY : 0} depthWrite={false} />
    </mesh>
  );
};

/** An invisible lid over a built room, so clicking anywhere in it picks it. */
interface PickerProps {
  room: RoomInfo;
  onClick: () => void;
  hoverable: boolean;
  onHover?: (at: { x: number; y: number } | null) => void;
}

const RoomPicker = ({ room, onClick, hoverable, onHover }: PickerProps) => {
  // The hand cursor this lid put up: taken down when the room stops being a way to go
  // (the party has just walked) or the lid goes, not only when the pointer leaves.
  const showing = useRef(false);
  const drop = () => {
    if (!showing.current) return;
    showing.current = false;
    document.body.style.cursor = '';
  };
  useEffect(() => {
    if (!hoverable) drop();
  }, [hoverable]);
  useEffect(() => drop, []);
  return (
    <mesh
      rotation={[-Math.PI / 2, 0, 0]}
      position={[room.center[0], BOARD_TOP + FLOOR_THICKNESS + 0.02, room.center[1]]}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      onPointerOver={() => {
        if (!hoverable) return;
        showing.current = true;
        document.body.style.cursor = 'pointer';
      }}
      onPointerMove={(e) => onHover?.({ x: e.nativeEvent.clientX, y: e.nativeEvent.clientY })}
      onPointerOut={() => {
        drop();
        onHover?.(null);
      }}
    >
      <planeGeometry args={[room.size[0], room.size[1]]} />
      <meshBasicMaterial transparent opacity={0} depthWrite={false} />
    </mesh>
  );
};

/* ── Figurines ── */

/** How far a figurine's base reaches, and how close two of them stand. */
const PAWN_RADIUS = 0.14;
const PAWN_GAP = 0.22;
/** Room left between a figurine's base and the furniture. */
const PAWN_CLEARANCE = 0.06;
/** Grid the figurines look over for a free spot. */
const SPOT_STEP = 0.035;
const ENEMY_RADIUS = 0.12;
const PASSAGE_HALF = 0.2;

/** What stands on a room's floor: its furniture, its passages and its enemy figurines. */
const roomFootprints = (room: RoomInfo, data: BoardRoom | undefined): Footprint[] => [
  ...furnishingFootprints(room, data?.passages?.length ?? 0),
  ...(data?.passages ?? []).map((_, i) => {
    const [x, z] = spotOf(room, i);
    return { x, z, hx: PASSAGE_HALF, hz: PASSAGE_HALF };
  }),
  ...((data?.enemies ?? 0) > 0
    ? enemySpots(room, data!.enemies!, room.type === 'boss').map(([x, , z]) => ({ x, z, hx: ENEMY_RADIUS, hz: ENEMY_RADIUS, round: true }))
    : []),
];

/** How deep a figurine standing at x, z would sink into a footprint. */
const sinkInto = (x: number, z: number, f: Footprint) => {
  const gap = f.round
    ? Math.max(Math.hypot(x - f.x, z - f.z) - f.hx, 0)
    : Math.hypot(Math.max(Math.abs(x - f.x) - f.hx, 0), Math.max(Math.abs(z - f.z) - f.hz, 0));
  return Math.max(0, PAWN_RADIUS + PAWN_CLEARANCE - gap);
};

/**
  Where the figurines stand: in a row near the front of the room, each moved to
  the nearest spot clear of the furniture, the walls and the others.
*/
const pawnSpots = (room: RoomInfo, total: number, blocked: Footprint[]): Vec3[] => {
  const y = BOARD_TOP + FLOOR_THICKNESS;
  const [cx, cz] = room.center;
  const limX = Math.max(0, room.size[0] / 2 - WALL_THICKNESS - PAWN_RADIUS);
  const limZ = Math.max(0, room.size[1] / 2 - WALL_THICKNESS - PAWN_RADIUS);
  const spread = total > 1 ? Math.min(room.size[0] * 0.62, 0.22 * (total - 1)) : 0;
  const spots: Vec3[] = [];
  for (let i = 0; i < total; i++) {
    const wantX = cx + (total > 1 ? -spread / 2 + (spread * i) / (total - 1) : 0);
    const wantZ = cz + room.size[1] * 0.12 + (i % 2) * 0.08;
    // Clear spots win; failing any, the least crowded one.
    const cost = (x: number, z: number) => {
      let sink = 0;
      blocked.forEach((f) => (sink = Math.max(sink, sinkInto(x, z, f))));
      spots.forEach((p) => (sink = Math.max(sink, PAWN_GAP - Math.hypot(x - p[0], z - p[2]))));
      return sink * 1000 + Math.hypot(x - wantX, z - wantZ);
    };
    let best: Vec3 = [wantX, y, wantZ];
    let bestCost = Infinity;
    for (let x = -limX; x <= limX + 1e-6; x += SPOT_STEP) {
      for (let z = -limZ; z <= limZ + 1e-6; z += SPOT_STEP) {
        const c = cost(cx + x, cz + z);
        if (c < bestCost) {
          bestCost = c;
          best = [cx + x, y, cz + z];
        }
      }
    }
    spots.push(best);
  }
  return spots;
};

interface PawnProps {
  member: BoardMember;
  to: Vec3;
  delay: number;
  /** Corridor waypoints to walk through on the way to `to`; null = leap (a teleport). */
  path: Vec3[] | null;
  /** Changes with every move, so the same target reached twice still sets off. */
  moveKey: number;
  /** This figurine's steps are heard (one is enough for the whole party). */
  audible?: boolean;
}

type Motion =
  | { kind: 'walk'; start: number; points: THREE.Vector3[]; lengths: number[]; total: number }
  | { kind: 'hop'; start: number; from: THREE.Vector3; to: THREE.Vector3 };

/**
 * The way from one room to the next along their corridor: out through the
 * first room's door, square by square down the corridor, in through the other
 * door. Null when no corridor joins them on the board (a teleport).
 */
const corridorPath = (layout: DioramaLayout, fromId: number, toId: number): Vec3[] | null => {
  const key = corridorKey(fromId, toId);
  const exit = layout.doorways.find((d) => d.corridor === key && d.roomId === fromId);
  const entry = layout.doorways.find((d) => d.corridor === key && d.roomId === toId);
  const piece = layout.pieces.get(ownerKey({ kind: 'corridor', key }));
  if (!exit || !entry || !piece) return null;
  const y = BOARD_TOP + FLOOR_THICKNESS;
  const left = piece.floor.map((f) => [f.x, f.z] as [number, number]);
  const route: Vec3[] = [[exit.x, y, exit.z]];
  let at: [number, number] = [exit.x, exit.z];
  // Squares in walking order: always the nearest one next to where we stand.
  while (left.length > 0) {
    let best = 0;
    let bestD = Infinity;
    left.forEach(([x, z], i) => {
      const d = Math.hypot(x - at[0], z - at[1]);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    if (bestD > SQUARE * 1.5) break;
    at = left.splice(best, 1)[0];
    route.push([at[0], y, at[1]]);
  }
  route.push([entry.x, y, entry.z]);
  return route;
};

/** The point `dist` back along a route from its point `index` (towards its start). */
const pointBack = (route: Vec3[], index: number, dist: number): Vec3 => {
  let left = dist;
  for (let i = index; i > 0; i--) {
    const [ax, ay, az] = route[i];
    const [bx, , bz] = route[i - 1];
    const seg = Math.hypot(bx - ax, bz - az);
    if (seg >= left && seg > 0) {
      const k = left / seg;
      return [ax + (bx - ax) * k, ay, az + (bz - az) * k];
    }
    left -= seg;
  }
  return route[0];
};

/** The middle square of a corridor's route (the doors at its ends excluded). */
const routeMiddle = (route: Vec3[]) => Math.max(1, Math.min(route.length - 2, Math.floor(route.length / 2)));

/** The party in single file halfway down a corridor: the first at the middle, the rest behind. */
const corridorSpots = (route: Vec3[], count: number): Vec3[] => {
  const m = routeMiddle(route);
  return Array.from({ length: Math.max(1, count) }, (_, i) => pointBack(route, m, i * CORRIDOR_FILE_GAP));
};

/** Who waits ahead in the corridor: a few squares past the middle, towards its far end. */
const corridorAhead = (route: Vec3[], count: number): Vec3[] => {
  const m = routeMiddle(route);
  const reversed = [...route].reverse();
  const from = route.length - 1 - m;
  return Array.from({ length: count }, (_, i) => pointBack(reversed, from, CORRIDOR_AMBUSH_GAP + i * CORRIDOR_FILE_GAP));
};

/** Turn the figure towards an angle, the short way round. */
const turnTowards = (g: THREE.Object3D, yaw: number, delta: number) => {
  const diff = Math.atan2(Math.sin(yaw - g.rotation.y), Math.cos(yaw - g.rotation.y));
  g.rotation.y += diff * Math.min(1, delta * TURN_RATE);
};

/** A member's miniature (see PartyMiniature). It walks the corridors step by step, facing the way it goes. */
const Pawn = ({ member, to, delay, path, moveKey, audible = false }: PawnProps) => {
  const group = useRef<THREE.Group>(null);
  const facing = useRef<THREE.Group>(null);
  const lastStep = useRef(-1);
  const from = useRef(new THREE.Vector3(...to));
  const motion = useRef<Motion | null>(null);

  const [tx, ty, tz] = to;
  useEffect(() => {
    const target = new THREE.Vector3(tx, ty, tz);
    if (target.distanceTo(from.current) < 0.01) {
      // Sent back before it set off (the move is being shown step by step): stay put.
      motion.current = null;
      return;
    }
    const start = performance.now() / 1000 + delay;
    if (path && path.length > 0) {
      const points = [from.current.clone(), ...path.map((p) => new THREE.Vector3(...p)), target];
      const lengths = points.slice(1).map((p, i) => p.distanceTo(points[i]));
      motion.current = { kind: 'walk', start, points, lengths, total: lengths.reduce((a, b) => a + b, 0) };
    } else {
      motion.current = { kind: 'hop', start, from: from.current.clone(), to: target };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tx, ty, tz, delay, moveKey]);

  useFrame((_, delta) => {
    const g = group.current;
    if (!g) return;
    const m = motion.current;
    const now = performance.now() / 1000;
    if (!m) {
      g.position.copy(from.current);
      // At rest it turns back to face the players.
      if (facing.current) turnTowards(facing.current, 0, delta);
      return;
    }
    if (m.kind === 'hop') {
      const t = THREE.MathUtils.clamp((now - m.start) / HOP_SECONDS, 0, 1);
      const eased = t * t * (3 - 2 * t);
      const p = m.from.clone().lerp(m.to, eased);
      g.position.set(p.x, p.y + Math.sin(Math.PI * t) * HOP_HEIGHT, p.z);
      if (t >= 1) {
        from.current.copy(m.to);
        motion.current = null;
      }
      return;
    }
    const walked = Math.max(0, now - m.start) * WALK_SPEED;
    if (walked >= m.total) {
      from.current.copy(m.points[m.points.length - 1]);
      g.position.copy(from.current);
      motion.current = null;
      return;
    }
    let left = walked;
    let i = 0;
    while (i < m.lengths.length - 1 && left > m.lengths[i]) {
      left -= m.lengths[i];
      i += 1;
    }
    // A footfall each time the figurine comes down.
    const step = Math.floor((walked * STEP_RATE) / Math.PI);
    if (audible && step !== lastStep.current) {
      lastStep.current = step;
      playDungeonSound('step');
    }
    const seg = m.lengths[i] > 0 ? left / m.lengths[i] : 1;
    const p = m.points[i].clone().lerp(m.points[i + 1], seg);
    const ahead = m.points[i + 1];
    if (facing.current && Math.hypot(ahead.x - m.points[i].x, ahead.z - m.points[i].z) > 0.001) {
      turnTowards(facing.current, Math.atan2(ahead.x - m.points[i].x, ahead.z - m.points[i].z), delta);
    }
    g.position.set(p.x, p.y + Math.abs(Math.sin(walked * STEP_RATE)) * STEP_HEIGHT, p.z);
  });

  const scale = PAWN_SCALE * (member.leader ? 1.15 : 1);
  return (
    <group ref={group} scale={[scale, scale * 1.1, scale]}>
      <group ref={facing}>
        <PartyMiniature member={member} />
      </group>
    </group>
  );
};

/* ── Dice ── */

/** Face order of a box: +x, -x, +y, -y, +z, -z. The rolled value goes on top (+y). */
const faceOrder = (value: number) => {
  const others = [1, 2, 3, 4, 5, 6].filter((v) => v !== value);
  return [others[0], others[1], value, others[2], others[3], others[4]];
};

/** Two bone dice thrown from the players' edge of the board; they tumble and settle on the result. */
const Dice = ({ dice, near }: { dice: DiceThrow | null; near: Vec3 }) => {
  const faces = useMemo(() => [1, 2, 3, 4, 5, 6].map((v) => createDieFaceTexture(v)), []);
  useEffect(() => () => disposeAll(faces), [faces]);
  const first = useRef<THREE.Mesh>(null);
  const second = useRef<THREE.Mesh>(null);
  const materials = useMemo(
    () =>
      (dice?.values ?? [1, 1]).map((v) =>
        faceOrder(v).map((f) => new THREE.MeshStandardMaterial({ map: faces[f - 1], roughness: 0.5 })),
      ),
    [dice, faces],
  );
  useEffect(() => () => materials.flat().forEach((m) => m.dispose()), [materials]);
  // The dice land where the party stood when they were thrown, and stay there when it moves on.
  const anchor = useRef<{ at: number; near: Vec3 } | null>(null);
  if (dice && anchor.current?.at !== dice.at) anchor.current = { at: dice.at, near };
  const thrownAt = dice?.at;
  useEffect(() => {
    if (thrownAt !== undefined) playDungeonSound('dice', Math.max(0, thrownAt - performance.now()));
  }, [thrownAt]);
  const base = anchor.current?.near ?? near;

  useFrame(() => {
    if (!dice) return;
    const t = THREE.MathUtils.clamp((performance.now() - dice.at) / 1000 / DICE_SECONDS, 0, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    [first, second].forEach((ref, i) => {
      const m = ref.current;
      if (!m) return;
      const land = new THREE.Vector3(base[0] - 0.3 + i * 0.6, BOARD_TOP + 0.11, base[2] + 1.2);
      const start = new THREE.Vector3(land.x + 2.5 - i, BOARD_TOP + 2, land.z + 3);
      const p = start.clone().lerp(land, eased);
      p.y += Math.abs(Math.sin(t * Math.PI * 3)) * (1 - t) * 0.8;
      m.position.copy(p);
      const spin = (1 - eased) * 14;
      m.rotation.set(spin * (1.1 + i * 0.3), spin * 0.7, spin * (0.9 - i * 0.2));
    });
  });

  if (!dice) return null;
  return (
    <>
      <mesh key={`${dice.at}-a`} ref={first} material={materials[0]}>
        <boxGeometry args={[0.22, 0.22, 0.22]} />
      </mesh>
      <mesh key={`${dice.at}-b`} ref={second} material={materials[1]}>
        <boxGeometry args={[0.22, 0.22, 0.22]} />
      </mesh>
    </>
  );
};

/* ── In the corridor: an ambush, a trap ── */

const AMBUSH_RISE_MS = 500;
/** A beaten ambush is taken off the table this long after the fight. */
const AMBUSH_GONE_MS = 4000;
const AMBUSH_FLASH_MS = 900;

/** Enemies rising out of the dark ahead of the party, a red flare as they come. */
const CorridorAmbush = ({
  kit,
  route,
  appearAt,
  defeatedAt,
}: {
  kit: EnemyKit;
  route: Vec3[];
  appearAt: number;
  defeatedAt: number;
}) => {
  const spots = useMemo(() => corridorAhead(route, AMBUSHERS), [route]);
  const look = route[routeMiddle(route)];
  const groups = useRef<(THREE.Group | null)[]>([]);
  const flare = useRef<THREE.PointLight>(null);
  // Seen already when the board appeared (a reload): no rising, they are simply there.
  const shownAt = useRef(appearAt);
  useFrame(() => {
    const since = performance.now() - shownAt.current;
    groups.current.forEach((g, i) => {
      if (!g) return;
      const k = THREE.MathUtils.clamp((since - i * 120) / AMBUSH_RISE_MS, 0, 1);
      g.scale.set(1, Math.max(0.001, k), 1);
      g.visible = k > 0;
    });
    if (flare.current) {
      const lit = since > 0 && since < AMBUSH_FLASH_MS ? 7 * (1 - since / AMBUSH_FLASH_MS) : 1.2;
      flare.current.intensity = performance.now() > defeatedAt ? 0 : lit;
    }
  });
  return (
    <>
      {spots.map((p, i) => (
        <group
          key={i}
          ref={(el) => {
            groups.current[i] = el;
          }}
          position={p}
          rotation={[0, Math.atan2(look[0] - p[0], look[2] - p[2]), 0]}
        >
          <EnemyFigure kit={kit} position={[0, 0, 0]} defeatedAt={defeatedAt + i * 120} seed={i * 5 + 3} />
        </group>
      ))}
      <pointLight ref={flare} position={[spots[0][0], spots[0][1] + 0.5, spots[0][2]]} color="#ff3a1a" distance={2.4} decay={1.4} />
    </>
  );
};

const TRAP_STRIKE_MS = 140;
const TRAP_HOLD_MS = 650;
const TRAP_SINK_MS = 350;
const TRAP_SPIKES = 7;
/** Tall enough to show over the corridor's near wall. */
const TRAP_SPIKE_H = 0.34;

/** Spikes out of the corridor floor round the party: a strike in red, or a slow rise caught and set back, in gold. */
const CorridorTrap = ({ route, trap }: { route: Vec3[]; trap: { at: number; passed: boolean } }) => {
  const spots = useMemo(() => {
    const m = routeMiddle(route);
    return Array.from({ length: TRAP_SPIKES }, (_, i) => {
      // Under the party's single file: from the first figurine back past the last.
      const [x, y, z] = pointBack(route, m, 0.04 + i * 0.09);
      const side = (i % 3) - 1;
      return [x + side * 0.08, y, z + ((i * 7) % 3 - 1) * 0.05] as Vec3;
    });
  }, [route]);
  const spikes = useRef<(THREE.Mesh | null)[]>([]);
  const light = useRef<THREE.PointLight>(null);
  const sparks = useMemo(() => new SparkPool(40), []);
  const burst = useRef(false);
  useFrame(() => {
    const since = performance.now() - trap.at;
    // The moment it springs: a spray of red over the party, or a glint of gold where it was caught.
    if (since >= 0 && !burst.current) {
      burst.current = true;
      const [mx, my, mz] = route[routeMiddle(route)];
      sparks.burst(new THREE.Vector3(mx, my + 0.25, mz), trap.passed ? '#ffd36a' : '#ff3a1a', trap.passed ? 14 : 26,
        trap.passed ? 0.5 : 0.9, { size: 0.8 });
    }
    let h = 0;
    if (since >= 0) {
      if (trap.passed) {
        // Caught in time: they creep up, and are set back down.
        const up = THREE.MathUtils.clamp(since / 500, 0, 1) * 0.5;
        const down = THREE.MathUtils.clamp((since - 600) / TRAP_SINK_MS, 0, 1);
        h = up * (1 - down);
      } else {
        const up = THREE.MathUtils.clamp(since / TRAP_STRIKE_MS, 0, 1);
        const down = THREE.MathUtils.clamp((since - TRAP_STRIKE_MS - TRAP_HOLD_MS) / TRAP_SINK_MS, 0, 1);
        h = up * (1 - down);
      }
    }
    spikes.current.forEach((s, i) => {
      if (!s) return;
      const k = Math.max(0.001, h * (0.8 + ((i * 13) % 5) * 0.06));
      s.scale.set(1, k, 1);
      s.position.y = spots[i][1] + (TRAP_SPIKE_H * k) / 2;
      s.visible = h > 0.01;
    });
    if (light.current) {
      const flash = since >= 0 && since < 900 ? 1 - since / 900 : 0;
      light.current.intensity = flash * (trap.passed ? 3 : 6);
    }
  });
  const m = route[routeMiddle(route)];
  return (
    <>
      {spots.map((p, i) => (
        <mesh
          key={i}
          ref={(el) => {
            spikes.current[i] = el;
          }}
          position={p}
          visible={false}
        >
          <coneGeometry args={[0.032, TRAP_SPIKE_H, 6]} />
          <meshStandardMaterial color="#8a8a92" metalness={0.8} roughness={0.35} />
        </mesh>
      ))}
      <pointLight
        ref={light}
        position={[m[0], m[1] + 0.4, m[2]]}
        color={trap.passed ? '#ffd36a' : '#ff3a1a'}
        intensity={0}
        distance={2}
        decay={1.4}
      />
      <SparkField pool={sparks} max={40} gravity={-1.6} />
    </>
  );
};

/* ── Dice: where they may land ── */

/** Dice land clear of every room and corridor (on the open table), as near the party as can be, the players' side first. */
const freeTableSpot = (layout: DioramaLayout, near: Vec3): Vec3 => {
  const squares: [number, number][] = [];
  layout.pieces.forEach((piece) => piece.floor.forEach((f) => squares.push([f.x, f.z])));
  const clearance = SQUARE * 0.5 + 0.28;
  const clear = (x: number, z: number) => squares.every(([sx, sz]) => Math.hypot(sx - x, sz - z) > clearance);
  // The two dice land side by side, 0.3 either way of the spot, a little towards the players.
  const fits = (x: number, z: number) => clear(x - 0.3, z + 1.2) && clear(x + 0.3, z + 1.2);
  let best: Vec3 | null = null;
  let bestScore = Infinity;
  for (let ring = 0; ring <= 14; ring++) {
    for (let a = 0; a < Math.max(1, ring * 8); a++) {
      const t = (a / Math.max(1, ring * 8)) * Math.PI * 2;
      const x = near[0] + Math.cos(t) * ring * 0.25;
      const z = near[2] + Math.sin(t) * ring * 0.25;
      if (!fits(x, z)) continue;
      const score = Math.hypot(x - near[0], z - near[2]) + (z < near[2] ? 0.6 : 0);
      if (score < bestScore) {
        bestScore = score;
        best = [x, near[1], z];
      }
    }
    if (best) break;
  }
  return best ?? near;
};

/** The party carries a lantern: a warm light that follows it over the miniature. */
/** Lava veins in the walls glow fainter than the cracks underfoot. */
const WALL_GLOW_SHARE = 0.55;

const Lantern = ({ at, color }: { at: Vec3; color: string }) => {
  const light = useRef<THREE.PointLight>(null);
  const pos = useRef(new THREE.Vector3(...at));
  useFrame(({ clock }, delta) => {
    pos.current.lerp(new THREE.Vector3(at[0], 2.2, at[2] + 0.6), 1 - Math.exp(-delta * 3));
    if (light.current) {
      light.current.position.copy(pos.current);
      light.current.intensity = 6 + Math.sin(clock.elapsedTime * 6) * 0.4;
    }
  });
  return <pointLight ref={light} color={color} distance={7} decay={1.3} />;
};

/* ── Scene ── */

const Board = ({
  dungeon,
  party,
  currentRoomId,
  revealed,
  cleared,
  reachable,
  dice,
  corridor = null,
  span = null,
  lowGraphics = false,
  marks = NO_MARKS,
  zoom = 1,
  overview = false,
  fixedOrigin = false,
  stability = 'unstable',
  onTileClick,
  onPartyArrived,
  onRoomHover,
  floor = 1,
}: DungeonBoardSceneProps) => {
  const hoverRoom = (roomId: number) => (at: { x: number; y: number } | null) =>
    onRoomHover?.(at ? { roomId, ...at } : null);
  const layout = useMemo(() => buildDioramaLayout(dungeon, { fixedOrigin }), [dungeon, fixedOrigin]);
  // The rock's span: the whole floor when the run says how big it is, and anything already built beyond it.
  const cell = ROOM_CELL_WORLD;
  const known: RockRect = {
    x0: layout.center[0] - layout.width / 2,
    x1: layout.center[0] + layout.width / 2,
    z0: layout.center[1] - layout.depth / 2,
    z1: layout.center[1] + layout.depth / 2,
  };
  const rx0 = Math.min(known.x0, span ? span.minCol * cell - ROOM_HALF_WORLD : Infinity);
  const rx1 = Math.max(known.x1, span ? span.maxCol * cell + ROOM_HALF_WORLD : -Infinity);
  const rz0 = Math.min(known.z0, span ? span.minRow * cell - ROOM_HALF_WORLD : Infinity);
  const rz1 = Math.max(known.z1, span ? span.maxRow * cell + ROOM_HALF_WORLD : -Infinity);
  const rock = useMemo<RockRect>(
    () => ({ x0: rx0 - BOARD_MARGIN, x1: rx1 + BOARD_MARGIN, z0: rz0 - BOARD_MARGIN, z1: rz1 + BOARD_MARGIN }),
    [rx0, rx1, rz0, rz1],
  );
  const width = rock.x1 - rock.x0;
  const depth = rock.z1 - rock.z0;
  const rockCenter = useMemo<[number, number]>(() => [(rock.x0 + rock.x1) / 2, (rock.z0 + rock.z1) / 2], [rock]);

  const ring = useMemo(createReachRingTexture, []);
  const flame = useMemo(createFlameTexture, []);
  const glow = useMemo(createSoftSpotTexture, []);
  // The dungeon's look (FEAT-176): its walls and floor, painted, and the glow of lava where it has any.
  const theme = dungeon.theme ?? 'stone';
  const look = THEME_LOOK[theme];
  const stone = useMemo(() => {
    const painted = paintTheme(theme);
    const floorMap = toTexture(painted.floor);
    const wallMap = toTexture(painted.wall);
    const floorGlow = painted.floorGlow ? toTexture(painted.floorGlow) : null;
    const wallGlow = painted.wallGlow ? toTexture(painted.wallGlow) : null;
    const glow = (map: THREE.Texture | null, share = 1) =>
      map && look.glow
        ? { emissiveMap: map, emissive: new THREE.Color(look.glow), emissiveIntensity: (look.glowIntensity ?? 1) * share }
        : {};
    const materials: StoneMaterials = {
      floor: new THREE.MeshStandardMaterial({ map: floorMap, roughness: look.floorRough, metalness: look.floorMetal, ...glow(floorGlow) }),
      wall: new THREE.MeshStandardMaterial({ map: wallMap, roughness: look.wallRough, metalness: look.wallMetal, ...glow(wallGlow, WALL_GLOW_SHARE) }),
      pillar: new THREE.MeshStandardMaterial({ map: wallMap, roughness: look.wallRough, metalness: look.wallMetal }),
    };
    return { maps: [floorMap, wallMap, floorGlow, wallGlow].filter((m): m is THREE.CanvasTexture => !!m), materials };
  }, [theme, look]);
  const doorKit = useMemo(() => {
    const woodMap = createDoorWoodTexture();
    const chalk = createChalkTexture();
    const mist = createMistTexture();
    const materials: DoorMaterials = {
      wood: new THREE.MeshStandardMaterial({ map: woodMap, roughness: 0.85 }),
      iron: new THREE.MeshStandardMaterial({ color: '#2c2a2e', roughness: 0.45, metalness: 0.7 }),
      frame: stone.materials.wall,
    };
    return { woodMap, chalk, mist, materials };
  }, [stone]);
  useEffect(() => () => disposeAll([ring, flame, glow]), [ring, flame, glow]);
  useEffect(
    () => () => {
      disposeAll([doorKit.woodMap, doorKit.chalk, doorKit.mist]);
      doorKit.materials.wood.dispose();
      doorKit.materials.iron.dispose();
    },
    [doorKit],
  );
  useEffect(
    () => () => {
      disposeAll(stone.maps);
      Object.values(stone.materials).forEach((m) => m.dispose());
    },
    [stone],
  );

  // Where the figurines stand in a room, clear of what is in it.
  const roomData = useMemo(() => new Map(dungeon.rooms.map((r) => [r.id, r])), [dungeon]);
  const partySpots = (room: RoomInfo, roomId: number) =>
    pawnSpots(room, Math.max(1, party.length), roomFootprints(room, roomData.get(roomId)));

  // Where the party stands: in a room, or halfway down a corridor (an ambush, a trap).
  const routeOf = (from: number, to: number) => corridorPath(layout, from, to);
  const stopRoute = corridor && corridor.from === currentRoomId ? routeOf(corridor.from, corridor.to) : null;
  const placeKey = stopRoute && corridor ? `c${corridor.from}-${corridor.to}` : `r${currentRoomId}`;
  const placeSpots = (key: string): Vec3[] => {
    if (key.startsWith('c')) {
      const [from, to] = key.slice(1).split('-').map(Number);
      const route = routeOf(from, to);
      if (route) return corridorSpots(route, party.length);
    }
    const roomId = Number(key.slice(1));
    const room = layout.rooms.get(roomId);
    return room ? partySpots(room, roomId) : [];
  };

  // The party's current walk: the way from where it stood, and when it reaches the door of where it goes.
  const walk = useRef<{
    place: string;
    roomId: number;
    path: Vec3[] | null;
    key: number;
    doorAt: number;
    arriveAt: number;
  }>({ place: placeKey, roomId: currentRoomId, path: null, key: 0, doorAt: 0, arriveAt: 0 });
  if (walk.current.place !== placeKey) {
    const prev = walk.current.place;
    let path: Vec3[] | null = null;
    if (prev.startsWith('r') && placeKey.startsWith('r')) {
      // Room to room: down the corridor joining them.
      path = routeOf(Number(prev.slice(1)), currentRoomId);
    } else if (prev.startsWith('r') && placeKey.startsWith('c') && stopRoute) {
      // Into a corridor and halfway down it.
      path = stopRoute.slice(0, routeMiddle(stopRoute));
    } else if (prev.startsWith('c') && placeKey.startsWith('r')) {
      // From halfway down a corridor: on to its far room, or back where the party came from.
      const [from, to] = prev.slice(1).split('-').map(Number);
      const route = routeOf(from, to);
      if (route) {
        const m = routeMiddle(route);
        if (currentRoomId === to) path = route.slice(m + 1);
        else if (currentRoomId === from) path = route.slice(0, m).reverse();
      }
    }
    const start = performance.now();
    const fromSpot = placeSpots(prev)[0];
    const targets = placeSpots(placeKey);
    let doorAt = start;
    // The last figurine sets off a little after the first.
    const stagger = Math.max(0, party.length - 1) * HOP_STAGGER * 1000;
    let arriveAt = start + HOP_SECONDS * 1000 + stagger;
    if (fromSpot && path && path.length > 0) {
      const points = [fromSpot, ...path];
      const length = points.slice(1).reduce((sum, p, i) => sum + Math.hypot(p[0] - points[i][0], p[2] - points[i][2]), 0);
      doorAt = start + (length / WALK_SPEED) * 1000;
      const last = path[path.length - 1];
      const spot = targets[0] ?? last;
      arriveAt = doorAt + (Math.hypot(spot[0] - last[0], spot[2] - last[2]) / WALK_SPEED) * 1000 + stagger;
    } else {
      path = null;
    }
    walk.current = { place: placeKey, roomId: currentRoomId, path, key: start, doorAt, arriveAt };
  }
  const standSpots = placeSpots(placeKey);

  // An ambush in the corridor stays on the table after the fight: won, its figures topple and sink.
  const ambushMemo = useRef<{ key: string; route: Vec3[]; to: number; appearAt: number; defeatedAt: number } | null>(null);
  if (stopRoute && corridor?.ambush) {
    if (ambushMemo.current?.key !== placeKey) {
      ambushMemo.current = { key: placeKey, route: stopRoute, to: corridor.to, appearAt: walk.current.arriveAt, defeatedAt: Infinity };
    }
  } else if (ambushMemo.current && ambushMemo.current.defeatedAt === Infinity) {
    if (currentRoomId === ambushMemo.current.to) ambushMemo.current.defeatedAt = performance.now();
    else ambushMemo.current = null;
  }
  if (ambushMemo.current && performance.now() - ambushMemo.current.defeatedAt > AMBUSH_GONE_MS) ambushMemo.current = null;
  const ambushShown = ambushMemo.current;

  const lastFloor = useRef(floor);
  useEffect(() => {
    if (lastFloor.current === floor) return;
    lastFloor.current = floor;
    playDungeonSound('rise');
  }, [floor]);

  // Say when the figurines are in: the page holds the room's news till then.
  const arrived = useRef(onPartyArrived);
  arrived.current = onPartyArrived;
  const walkKey = walk.current.key;
  useEffect(() => {
    const { roomId, arriveAt, place } = walk.current;
    // Halfway down a corridor the party has not arrived anywhere.
    if (place.startsWith('c')) return;
    const wait = Math.max(0, arriveAt - performance.now());
    const timer = setTimeout(() => arrived.current?.(roomId), wait);
    return () => clearTimeout(timer);
  }, [walkKey]);

  // Enemies of a room topple when it is cleared during the run; rooms cleared before the board appeared have none.
  const enemyKit = useEnemyKit();
  const decorKit = useDecorKit();
  useDecorPulse(decorKit);
  const clearedAt = useRef<Map<number, number> | null>(null);
  if (clearedAt.current === null) clearedAt.current = new Map([...cleared].map((id) => [id, -Infinity]));
  cleared.forEach((id) => {
    if (!clearedAt.current!.has(id)) clearedAt.current!.set(id, performance.now());
  });

  // When each room was first reached, so it rises once — rooms open from the start are simply there.
  const revealedAt = useRef(new Map<number, number>());
  const firstLook = revealedAt.current.size === 0;
  const now = performance.now();
  revealed.forEach((id) => {
    if (revealedAt.current.has(id)) return;
    // The room the party is walking into opens when it reaches the door, not before.
    const at = id === currentRoomId && walk.current.path ? Math.max(now, walk.current.doorAt) : now;
    revealedAt.current.set(id, firstLook ? -Infinity : at);
    if (!firstLook) playDungeonSound('rise', at - now + RISE_DELAY_MS);
  });
  // A room hidden again (a move shown step by step holds it back) rises anew when it returns.
  revealedAt.current.forEach((_, id) => {
    if (!revealed.has(id)) revealedAt.current.delete(id);
  });
  const riseAt = (roomId: number) => (revealedAt.current.get(roomId) ?? Infinity) + RISE_DELAY_MS;

  // Fog of war: built rooms, plus shut doors into the rooms next to them.
  const neighbours = useMemo(() => {
    const set = new Set<number>();
    dungeon.corridors.forEach((c) => {
      if (revealed.has(c.from)) set.add(c.to);
      if (revealed.has(c.to)) set.add(c.from);
    });
    return set;
  }, [dungeon, revealed]);

  // A drag of the board ends with a release over some room: that is not a click on it.
  const dragged = useRef(false);
  const tileClick = (roomId: number) => {
    if (!dragged.current) onTileClick(roomId);
  };
  const bounds = useMemo(
    () => ({ center: rockCenter, half: [width / 2, depth / 2] as [number, number] }),
    [rockCenter, width, depth],
  );

  // Locked doors still shut in this run: the key each corridor wants.
  const locks = useMemo(() => {
    const map = new Map<string, string>();
    dungeon.corridors.forEach((c) => {
      if (c.lock) map.set(corridorKey(c.from, c.to), c.lock);
    });
    return map;
  }, [dungeon]);

  const here = layout.rooms.get(currentRoomId);
  const hereSpots = useMemo(
    () => (here ? pawnSpots(here, Math.max(1, party.length), roomFootprints(here, roomData.get(currentRoomId))) : []),
    [here, currentRoomId, party.length, roomData],
  );
  const middle: Vec3 = [layout.center[0], BOARD_TOP, layout.center[1]];
  const corridorFocus = stopRoute ? stopRoute[routeMiddle(stopRoute)] : null;
  const focus: Vec3 = corridorFocus
    ? [corridorFocus[0], BOARD_TOP, corridorFocus[2]]
    : here
      ? [here.center[0], BOARD_TOP, here.center[1]]
      : middle;
  // Where thrown dice land: the open table near the party, never in a wall.
  const [fx, , fz] = focus;
  const diceSpot = useMemo(() => freeTableSpot(layout, [fx, BOARD_TOP, fz]), [layout, fx, fz]);

  return (
    <>
      <CameraRig focus={overview ? middle : focus} zoom={zoom} overview={overview} bounds={bounds} dragged={dragged} />
      <RockBed rect={rock} top={BOARD_TOP} lowGraphics={lowGraphics} tint={look.rock} />
      <Lantern at={focus} color={look.lantern} />
      <FloorShift floor={floor}>
      <BoardFog
        dungeon={dungeon}
        layout={layout}
        revealed={revealed}
        width={width + ROCK_EDGE * 2}
        depth={depth + ROCK_EDGE * 2}
        center={rockCenter}
        y={BOARD_TOP + 0.004}
      />

      <group position={[0, BOARD_TOP, 0]}>
        {/* Corridors: built from the moment one end is reached */}
        {dungeon.corridors
          .filter((c) => revealed.has(c.from) || revealed.has(c.to))
          .map((c) => {
            const piece = layout.pieces.get(ownerKey({ kind: 'corridor', key: corridorKey(c.from, c.to) }));
            if (!piece) return null;
            const at = Math.min(
              revealed.has(c.from) ? riseAt(c.from) : Infinity,
              revealed.has(c.to) ? riseAt(c.to) : Infinity,
            );
            return (
              <Rising key={`c${c.from}-${c.to}`} appearAt={at + 150}>
                <PieceMesh piece={piece} materials={stone.materials} seed={c.from * 31 + c.to} />
                <PieceDecor kit={decorKit} piece={piece} seed={c.from * 31 + c.to} room={null} lowGraphics={lowGraphics} />
              </Rising>
            );
          })}

        {/* Rooms */}
        {dungeon.rooms
          .filter((r) => revealed.has(r.id))
          .map((r) => {
            const piece = layout.pieces.get(ownerKey({ kind: 'room', id: r.id }));
            const info = layout.rooms.get(r.id)!;
            if (!piece) return null;
            return (
              <Rising key={`r${r.id}`} appearAt={riseAt(r.id)}>
                <PieceMesh piece={piece} materials={stone.materials} seed={r.id} />
                <Torches piece={piece} flame={flame} glow={glow} seed={r.id} color={look.torch} />
                <PieceDecor
                  kit={decorKit}
                  piece={piece}
                  seed={r.id}
                  room={info}
                  portal={r.portal}
                  spent={r.portal === 'red' && cleared.has(r.id)}
                  lowGraphics={lowGraphics}
                />
                <RoomFurnishing
                  room={info}
                  flame={flame}
                  glow={glow}
                  portal={r.portal}
                  spent={r.portal === 'red' && cleared.has(r.id)}
                  done={cleared.has(r.id)}
                  lowGraphics={lowGraphics}
                  passages={r.passages?.length ?? 0}
                />
                {r.dark !== undefined && <RoomGloom room={info} dark={r.dark} />}
                {(r.passages ?? []).map((p, i) => (
                  <PassageMarker
                    key={`pass${p.target}`}
                    room={info}
                    passage={p}
                    index={i}
                    reachable={reachable.has(p.target)}
                    glow={glow}
                    onClick={() => tileClick(p.target)}
                    onHover={hoverRoom(p.target)}
                  />
                ))}
                {(r.enemies ?? 0) > 0 && clearedAt.current!.get(r.id) !== -Infinity && (
                  <RoomEnemies
                    kit={enemyKit}
                    room={info}
                    count={r.enemies ?? 0}
                    defeatedAt={clearedAt.current!.get(r.id) ?? Infinity}
                  />
                )}
              </Rising>
            );
          })}
      </group>

      {/* Doors where corridors reach rooms: shut until the party walks through */}
      <group position={[0, BOARD_TOP, 0]}>
        {layout.doorways
          .filter((d) => {
            const [a, b] = d.corridor.split('-').map(Number);
            return revealed.has(a) || revealed.has(b);
          })
          .map((d) => {
            const [a, b] = d.corridor.split('-').map(Number);
            // A locked door stays shut even onto a room the party already knows.
            const openAt =
              revealed.has(d.roomId) && !locks.has(d.corridor) ? (revealedAt.current.get(d.roomId) ?? -Infinity) : Infinity;
            const corridorAt = Math.min(revealed.has(a) ? riseAt(a) : Infinity, revealed.has(b) ? riseAt(b) : Infinity);
            return (
              <Rising key={`door${d.corridor}|${d.roomId}`} appearAt={corridorAt + 150}>
                <Door
                  doorway={d}
                  openAt={openAt}
                  reachable={reachable.has(d.roomId)}
                  materials={doorKit.materials}
                  glow={glow}
                  onClick={() => tileClick(d.roomId)}
                  onHover={hoverRoom(d.roomId)}
                  lock={locks.get(d.corridor)}
                />
                {stability === 'chaotic' && <DoorMist doorway={d} mist={doorKit.mist} openAt={openAt} />}
              </Rising>
            );
          })}
        {/* No corridor reaches it on the grid (rooms drawn over each other): a door where the room will be */}
        {dungeon.rooms
          .filter((r) => neighbours.has(r.id) && !revealed.has(r.id) && !layout.doorways.some((d) => d.roomId === r.id))
          .map((r) => {
            const info = layout.rooms.get(r.id)!;
            return (
              <Door
                key={`lone${r.id}`}
                doorway={{ roomId: r.id, corridor: '', x: info.center[0], z: info.center[1], into: [0, 1] }}
                openAt={Infinity}
                reachable={reachable.has(r.id)}
                materials={doorKit.materials}
                glow={glow}
                onClick={() => tileClick(r.id)}
                onHover={hoverRoom(r.id)}
              />
            );
          })}
        {/* Scouted rooms not yet entered: what waits there, floating over the rock */}
        {dungeon.rooms
          .filter((r) => r.scouted && !revealed.has(r.id))
          .map((r) => {
            const info = layout.rooms.get(r.id);
            if (!info) return null;
            return (
              <Html
                key={`scout${r.id}`}
                center
                position={[info.center[0], 0.35, info.center[1]]}
                zIndexRange={[0, 0]}
                style={{ pointerEvents: 'none' }}
              >
                <div className="whitespace-nowrap rounded-card border border-[#8a7cb8]/60 bg-black/75 px-2 py-1 text-[11px] text-white/90 shadow-card">
                  <span className="text-[#b9aee0] mr-1">⌕</span>
                  {r.scouted}
                </div>
              </Html>
            );
          })}
        {/* A charted dungeon: the shape of each room beyond a shut door, in chalk */}
        {stability === 'static' &&
          dungeon.rooms
            .filter((r) => neighbours.has(r.id) && !revealed.has(r.id))
            .map((r) => <ChalkOutline key={`chalk${r.id}`} room={layout.rooms.get(r.id)!} chalk={doorKit.chalk} />)}
      </group>

      {dungeon.rooms
        .filter((r) => reachable.has(r.id) && revealed.has(r.id))
        .map((r) => (
          <ReachGlow key={`glow${r.id}`} room={layout.rooms.get(r.id)!} ring={ring} raised />
        ))}
      {dungeon.rooms
        .filter((r) => revealed.has(r.id))
        .map((r) => (
          <RoomPicker
            key={`pick${r.id}`}
            room={layout.rooms.get(r.id)!}
            hoverable={reachable.has(r.id)}
            onClick={() => tileClick(r.id)}
            onHover={hoverRoom(r.id)}
          />
        ))}

      <group position={[0, BOARD_TOP, 0]}>
        <PartyMarks marks={marks} dungeon={dungeon} layout={layout} revealed={revealed} />
      </group>

      {here &&
        party.map((m, i) => (
          <Pawn
            key={m.id}
            member={m}
            to={standSpots[i] ?? hereSpots[i]}
            delay={i * HOP_STAGGER}
            path={walk.current.path}
            moveKey={walk.current.key}
            audible={i === 0}
          />
        ))}
        {ambushShown && (
          <CorridorAmbush
            kit={enemyKit}
            route={ambushShown.route}
            appearAt={ambushShown.appearAt}
            defeatedAt={ambushShown.defeatedAt}
          />
        )}
        {stopRoute && corridor?.trap && <CorridorTrap route={stopRoute} trap={corridor.trap} />}
      </FloorShift>
      <Dice dice={dice} near={diceSpot} />
    </>
  );
};

const DungeonBoardScene = (props: DungeonBoardSceneProps) => (
  <Canvas
    dpr={props.lowGraphics ? 1 : [1, 1.75]}
    gl={{ antialias: !props.lowGraphics, powerPreference: 'high-performance' }}
    camera={{ fov: CAMERA_FOV, near: 0.1, far: 120, position: [0, 8, 6] }}
    onPointerMissed={() => {
      document.body.style.cursor = '';
    }}
  >
    <color attach="background" args={['#050407']} />
    <Board {...props} />
  </Canvas>
);

export default DungeonBoardScene;
