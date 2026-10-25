import { useEffect, useMemo, useRef } from 'react';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';
import { SQUARE, type Doorway, type RoomInfo } from './dioramaLayout';
import { FLOOR_THICKNESS, WALL_HEIGHT } from './DioramaPieces';
import { playDungeonSound } from '../../utils/dungeonSounds';
import { keyInfo } from '../DungeonPage/dungeonConstants';

/*
  Doors of the miniature. A corridor ends in a shut oak door wherever the room
  beyond hasn't been reached; it swings open into the corridor when the party
  walks through, and the room rises behind it. How much the party knows of
  what lies beyond follows the dungeon's stability: a charted («Изученный»)
  dungeon shows the room's outline in chalk on the cloth, an unstable one
  shows only the door, a chaotic one hides the door itself in drifting mist.
*/

export type DungeonStability = 'static' | 'unstable' | 'chaotic';

const POST = 0.06;
const OPENING = SQUARE - POST * 2;
const DOOR_HEIGHT = WALL_HEIGHT * 0.86;
const DOOR_THICKNESS = 0.03;
/** How far the door swings into the corridor, radians (a bit past square). */
const OPEN_ANGLE = 1.75;
const SWING_SPEED = 3;

export interface DoorMaterials {
  wood: THREE.MeshStandardMaterial;
  iron: THREE.MeshStandardMaterial;
  frame: THREE.Material;
}

interface DoorProps {
  doorway: Doorway;
  /**
   * performance.now() when the door swings open: Infinity while it stays shut,
   * −Infinity for a door already open when the board appeared (no swing).
   */
  openAt: number;
  reachable: boolean;
  materials: DoorMaterials;
  glow: THREE.Texture;
  onClick: () => void;
  /** The pointer is over the door (screen position) or has left it (null). */
  onHover?: (at: { x: number; y: number } | null) => void;
  /** A locked door: the kind of key it wants — a padlock of that colour hangs on it. */
  lock?: string;
}

/** A padlock on the corridor side of a locked door, in its key's colour. */
const Padlock = ({ color }: { color: string }) => (
  <group position={[OPENING * 0.8, DOOR_HEIGHT * 0.46, -DOOR_THICKNESS / 2 - 0.03]}>
    <mesh>
      <boxGeometry args={[0.085, 0.07, 0.03]} />
      <meshStandardMaterial color={color} metalness={0.75} roughness={0.3} emissive={color} emissiveIntensity={0.25} />
    </mesh>
    <mesh position={[0, 0.045, 0]}>
      <torusGeometry args={[0.026, 0.008, 6, 16, Math.PI]} />
      <meshStandardMaterial color="#9a9aa2" metalness={0.85} roughness={0.25} />
    </mesh>
    <mesh position={[0, -0.005, -0.016]}>
      <boxGeometry args={[0.012, 0.022, 0.004]} />
      <meshBasicMaterial color="#111" />
    </mesh>
  </group>
);

const setCursor = (cursor: string) => () => {
  document.body.style.cursor = cursor;
};

/**
 * A stone frame with a hinged oak door. Local +Z points into the room, so the
 * door swings towards −Z, flat against the corridor wall. When the party may
 * go through, warm light leaks under it and spills onto the corridor floor.
 */
export const Door = ({ doorway, openAt, reachable, materials, glow, onClick, onHover, lock }: DoorProps) => {
  const leaf = useRef<THREE.Group>(null);
  const angle = useRef(openAt === -Infinity ? OPEN_ANGLE : 0);
  const heardOpen = useRef(openAt === -Infinity);
  const spill = useRef<THREE.MeshBasicMaterial>(null);
  const crack = useRef<THREE.MeshBasicMaterial>(null);
  // Each door glows with its own material, so only the reachable ones pulse.
  const wood = useMemo(() => materials.wood.clone(), [materials.wood]);
  useEffect(() => () => wood.dispose(), [wood]);

  useFrame(({ clock }, delta) => {
    const open = performance.now() >= openAt;
    if (open && !heardOpen.current) {
      heardOpen.current = true;
      playDungeonSound('door');
    }
    angle.current += ((open ? OPEN_ANGLE : 0) - angle.current) * Math.min(1, delta * SWING_SPEED);
    if (leaf.current) leaf.current.rotation.y = angle.current;
    const lit = reachable && !open;
    const pulse = 0.5 + Math.sin(clock.elapsedTime * 3) * 0.5;
    wood.emissive.set(lit ? '#ff8a2a' : '#000000');
    wood.emissiveIntensity = lit ? 0.03 + pulse * 0.07 : 0;
    if (spill.current) spill.current.opacity = lit ? 0.35 + pulse * 0.3 : 0;
    if (crack.current) crack.current.opacity = lit ? 0.7 + pulse * 0.3 : open ? 0 : 0.18;
  });
  const open = openAt <= performance.now();

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    onClick();
  };
  const hover = reachable && !open;

  return (
    <group
      position={[doorway.x, FLOOR_THICKNESS, doorway.z]}
      rotation={[0, Math.atan2(doorway.into[0], doorway.into[1]), 0]}
      onClick={handleClick}
      onPointerOver={hover ? setCursor('pointer') : undefined}
      onPointerMove={(e) => onHover?.({ x: e.nativeEvent.clientX, y: e.nativeEvent.clientY })}
      onPointerOut={() => {
        if (hover) document.body.style.cursor = '';
        onHover?.(null);
      }}
    >
      {/* Stone frame: two jambs and a lintel */}
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * (SQUARE / 2 - POST / 2), WALL_HEIGHT / 2 + 0.01, 0]} material={materials.frame}>
          <boxGeometry args={[POST, WALL_HEIGHT + 0.02, 0.09]} />
        </mesh>
      ))}
      <mesh position={[0, DOOR_HEIGHT + (WALL_HEIGHT + 0.03 - DOOR_HEIGHT) / 2, 0]} material={materials.frame}>
        <boxGeometry args={[SQUARE, WALL_HEIGHT + 0.03 - DOOR_HEIGHT, 0.1]} />
      </mesh>

      {/* The leaf, hinged on the left jamb */}
      <group ref={leaf} position={[-OPENING / 2, 0, 0]}>
        <mesh position={[OPENING / 2, DOOR_HEIGHT / 2, 0]} material={wood}>
          <boxGeometry args={[OPENING, DOOR_HEIGHT, DOOR_THICKNESS]} />
        </mesh>
        {[0.22, 0.75].map((h) => (
          <mesh key={h} position={[OPENING / 2, DOOR_HEIGHT * h, 0]} material={materials.iron}>
            <boxGeometry args={[OPENING * 0.98, 0.022, DOOR_THICKNESS + 0.01]} />
          </mesh>
        ))}
        {lock && <Padlock color={keyInfo(lock).color} />}
        {/* Ring pull on the corridor side */}
        <mesh
          position={[OPENING * 0.8, DOOR_HEIGHT * 0.48, -DOOR_THICKNESS / 2 - 0.012]}
          rotation={[0, 0, 0]}
          material={materials.iron}
        >
          <torusGeometry args={[0.022, 0.006, 6, 14]} />
        </mesh>
      </group>

      {/* Light under the door and its spill on the corridor floor */}
      <mesh position={[0, 0.006, -DOOR_THICKNESS / 2 - 0.004]}>
        <boxGeometry args={[OPENING * 0.9, 0.01, 0.006]} />
        <meshBasicMaterial ref={crack} color="#ffc070" transparent opacity={0.18} toneMapped={false} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, -SQUARE * 0.45]}>
        <planeGeometry args={[SQUARE * 1.1, SQUARE * 0.9]} />
        <meshBasicMaterial
          ref={spill}
          map={glow}
          color="#ffb060"
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
};

/** The outline of a charted room drawn in chalk on the cloth, where it will rise. */
export const ChalkOutline = ({ room, chalk }: { room: RoomInfo; chalk: THREE.Texture }) => {
  const [w, d] = room.size;
  const edges = useMemo(() => {
    const line = 0.03;
    return [
      { pos: [room.center[0], room.center[1] - d / 2] as const, size: [w + line, line] as const, len: w },
      { pos: [room.center[0], room.center[1] + d / 2] as const, size: [w + line, line] as const, len: w },
      { pos: [room.center[0] - w / 2, room.center[1]] as const, size: [line, d + line] as const, len: d },
      { pos: [room.center[0] + w / 2, room.center[1]] as const, size: [line, d + line] as const, len: d },
    ];
  }, [room.center, w, d]);
  // Each edge gets its own copy so the stroke repeats along its own length.
  const maps = useMemo(
    () =>
      edges.map((e) => {
        const t = chalk.clone();
        t.needsUpdate = true;
        t.repeat.set(Math.max(1, e.len * 2.2), 1);
        if (e.size[0] < e.size[1]) t.rotation = Math.PI / 2;
        t.center.set(0.5, 0.5);
        return t;
      }),
    [edges, chalk],
  );
  useEffect(() => () => maps.forEach((m) => m.dispose()), [maps]);
  return (
    <group>
      {edges.map((e, i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, 0]} position={[e.pos[0], 0.008, e.pos[1]]} renderOrder={2}>
          <planeGeometry args={[e.size[0], e.size[1]]} />
          <meshBasicMaterial map={maps[i]} transparent opacity={0.75} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
};

const MIST_PUFFS = 9;
const MIST_OPACITY = 0.85;

/** Mist drifting about a door in a chaotic dungeon; it thins away once the door is opened. */
export const DoorMist = ({ doorway, mist, openAt }: { doorway: Doorway; mist: THREE.Texture; openAt: number }) => {
  const group = useRef<THREE.Group>(null);
  const strength = useRef(openAt === -Infinity ? 0 : 1);
  const puffs = useMemo(
    () =>
      Array.from({ length: MIST_PUFFS }, (_, i) => ({
        phase: i * 1.7,
        radius: 0.15 + (i % 3) * 0.12,
        height: 0.03 + (i % 3) * 0.08,
        size: 0.7 + (i % 3) * 0.25,
      })),
    [],
  );
  useFrame(({ clock }, delta) => {
    const g = group.current;
    if (!g) return;
    const open = performance.now() >= openAt;
    strength.current += ((open ? 0 : 1) - strength.current) * Math.min(1, delta * 1.5);
    g.visible = strength.current > 0.02;
    const t = clock.elapsedTime;
    g.children.forEach((child, i) => {
      const p = puffs[i];
      const mesh = child as THREE.Mesh;
      // Drifts about a point a little past the door, over where the room will be.
      mesh.position.set(
        doorway.into[0] * 0.25 + Math.cos(t * 0.25 + p.phase) * p.radius,
        p.height + Math.sin(t * 0.6 + p.phase) * 0.02,
        doorway.into[1] * 0.25 + Math.sin(t * 0.2 + p.phase) * p.radius * 0.8,
      );
      mesh.rotation.z = t * 0.1 + p.phase;
      (mesh.material as THREE.MeshBasicMaterial).opacity = MIST_OPACITY * strength.current;
    });
  });
  return (
    <group ref={group} position={[doorway.x, FLOOR_THICKNESS, doorway.z]}>
      {puffs.map((p, i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[p.size, p.size]} />
          <meshBasicMaterial map={mist} color="#9aa1aa" transparent opacity={MIST_OPACITY} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
};
