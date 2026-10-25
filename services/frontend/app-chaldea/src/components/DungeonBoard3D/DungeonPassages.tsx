import { useMemo, useRef } from 'react';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';
import { SQUARE, type RoomInfo } from './dioramaLayout';
import { FLOOR_THICKNESS } from './DioramaPieces';
import type { BoardPassage } from './boardTypes';
import { keyInfo } from '../DungeonPage/dungeonConstants';

/*
  Ways between floors, set into a room's floor tiles: a stairwell going down
  into the dark, steps climbing up to the floor above, a ragged hole (a drop,
  one way down) and a lift platform hung on chains. A passage the party can
  take glows; a locked one wears a padlock (its key's colour, iron for a lever).
*/

const STONE = '#6f6b70';
const DARK = '#050407';
const IRON = '#2c2a2e';
const LEVER_LOCK = '#8a8a92';

/** Where the n-th passage of a room sits: the room's back corners, then its front ones. */
export const spotOf = (room: RoomInfo, index: number): [number, number] => {
  const hx = room.size[0] / 2 - SQUARE * 0.75;
  const hz = room.size[1] / 2 - SQUARE * 0.75;
  const corners: [number, number][] = [
    [hx, -hz],
    [-hx, -hz],
    [hx, hz],
    [-hx, hz],
  ];
  const [dx, dz] = corners[index % corners.length];
  return [room.center[0] + dx, room.center[1] + dz];
};

const StairsDown = () => (
  <group>
    {/* The dark well, framed in stone */}
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]}>
      <planeGeometry args={[0.36, 0.36]} />
      <meshBasicMaterial color={DARK} />
    </mesh>
    {[
      [0, -0.19, 0.4, 0.03],
      [0, 0.19, 0.4, 0.03],
      [-0.19, 0, 0.03, 0.4],
      [0.19, 0, 0.03, 0.4],
    ].map(([x, z, w, d], i) => (
      <mesh key={i} position={[x, 0.02, z]}>
        <boxGeometry args={[w, 0.04, d]} />
        <meshStandardMaterial color={STONE} roughness={0.9} />
      </mesh>
    ))}
    {/* Steps sinking into the dark */}
    {[0, 1, 2].map((i) => (
      <mesh key={`s${i}`} position={[0, 0.012 - i * 0.004, -0.11 + i * 0.09]}>
        <boxGeometry args={[0.3, 0.012, 0.07]} />
        <meshStandardMaterial color={STONE} roughness={0.9} transparent opacity={1 - i * 0.3} />
      </mesh>
    ))}
  </group>
);

const StairsUp = () => (
  <group>
    {[0, 1, 2, 3].map((i) => (
      <mesh key={i} position={[0, 0.03 + i * 0.03, 0.12 - i * 0.08]}>
        <boxGeometry args={[0.3, 0.06 + i * 0.06, 0.08]} />
        <meshStandardMaterial color={STONE} roughness={0.88} />
      </mesh>
    ))}
  </group>
);

const DropHole = () => {
  const rim = useMemo(
    () =>
      Array.from({ length: 9 }, (_, i) => {
        const a = (i / 9) * Math.PI * 2;
        return { x: Math.cos(a) * 0.19, z: Math.sin(a) * 0.17, s: 0.03 + ((i * 7) % 3) * 0.012, r: a };
      }),
    [],
  );
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0.4]} position={[0, 0.004, 0]}>
        <circleGeometry args={[0.18, 9]} />
        <meshBasicMaterial color={DARK} />
      </mesh>
      {rim.map((p, i) => (
        <mesh key={i} position={[p.x, p.s / 2, p.z]} rotation={[p.r, p.r * 2, 0]}>
          <boxGeometry args={[p.s, p.s, p.s]} />
          <meshStandardMaterial color="#5c585c" roughness={0.95} />
        </mesh>
      ))}
    </group>
  );
};

const LiftPlatform = () => (
  <group>
    <mesh position={[0, 0.02, 0]}>
      <boxGeometry args={[0.34, 0.03, 0.34]} />
      <meshStandardMaterial color="#5a4632" roughness={0.85} />
    </mesh>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.17, 0.2, 0]}>
        <cylinderGeometry args={[0.012, 0.012, 0.4, 6]} />
        <meshStandardMaterial color={IRON} metalness={0.7} roughness={0.4} />
      </mesh>
    ))}
    <mesh position={[0, 0.4, 0]}>
      <boxGeometry args={[0.38, 0.03, 0.04]} />
      <meshStandardMaterial color={IRON} metalness={0.7} roughness={0.4} />
    </mesh>
  </group>
);

const Lock = ({ color }: { color: string }) => (
  <group position={[0, 0.22, 0.2]}>
    <mesh>
      <boxGeometry args={[0.085, 0.07, 0.03]} />
      <meshStandardMaterial color={color} metalness={0.75} roughness={0.3} emissive={color} emissiveIntensity={0.25} />
    </mesh>
    <mesh position={[0, 0.045, 0]}>
      <torusGeometry args={[0.026, 0.008, 6, 16, Math.PI]} />
      <meshStandardMaterial color="#9a9aa2" metalness={0.85} roughness={0.25} />
    </mesh>
  </group>
);

interface PassageMarkerProps {
  room: RoomInfo;
  passage: BoardPassage;
  index: number;
  reachable: boolean;
  glow: THREE.Texture;
  onClick: () => void;
  onHover?: (at: { x: number; y: number } | null) => void;
}

export const PassageMarker = ({ room, passage, index, reachable, glow, onClick, onHover }: PassageMarkerProps) => {
  const [x, z] = spotOf(room, index);
  const halo = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }) => {
    if (halo.current) halo.current.opacity = reachable ? 0.4 + Math.sin(clock.elapsedTime * 3) * 0.2 : 0;
  });
  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    onClick();
  };
  const lockColor = passage.lock ? (passage.lock === 'lever' ? LEVER_LOCK : keyInfo(passage.lock).color) : null;
  return (
    <group
      position={[x, FLOOR_THICKNESS, z]}
      onClick={handleClick}
      onPointerOver={() => {
        if (reachable) document.body.style.cursor = 'pointer';
      }}
      onPointerMove={(e) => onHover?.({ x: e.nativeEvent.clientX, y: e.nativeEvent.clientY })}
      onPointerOut={() => {
        if (reachable) document.body.style.cursor = '';
        onHover?.(null);
      }}
    >
      {passage.kind === 'drop' ? (
        <DropHole />
      ) : passage.kind === 'lift' ? (
        <LiftPlatform />
      ) : passage.dir === 'down' ? (
        <StairsDown />
      ) : (
        <StairsUp />
      )}
      {lockColor && <Lock color={lockColor} />}
      {/* A soft glow when the party can take it */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.006, 0]}>
        <planeGeometry args={[SQUARE * 1.4, SQUARE * 1.4]} />
        <meshBasicMaterial
          ref={halo}
          map={glow}
          color="#ffb060"
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
      {/* An easy target for the pointer */}
      <mesh position={[0, 0.1, 0]} visible={false}>
        <boxGeometry args={[0.44, 0.24, 0.44]} />
        <meshBasicMaterial />
      </mesh>
    </group>
  );
};

const SHIFT_MS = 1300;
const SHIFT_DEPTH = 1.4;

/**
 * The table changing floors: going down, the new floor rises from the depths;
 * going up, it settles from above.
 */
export const FloorShift = ({ floor, children }: { floor: number; children: React.ReactNode }) => {
  const group = useRef<THREE.Group>(null);
  const last = useRef(floor);
  const shift = useRef({ at: -Infinity, dir: 0 });
  if (last.current !== floor) {
    shift.current = { at: performance.now(), dir: floor > last.current ? -1 : 1 };
    last.current = floor;
  }
  useFrame(() => {
    const g = group.current;
    if (!g) return;
    const t = Math.min(1, (performance.now() - shift.current.at) / SHIFT_MS);
    const eased = 1 - (1 - t) ** 3;
    g.position.y = shift.current.dir * SHIFT_DEPTH * (1 - eased);
  });
  return <group ref={group}>{children}</group>;
};
