import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { DioramaLayout } from './dioramaLayout';
import { FLOOR_THICKNESS } from './DioramaPieces';
import { spotOf as passageSpot } from './DungeonPassages';
import type { BoardDungeon } from './boardTypes';

/*
  What the party says on the table. A member's say on the way on is a little
  flag in their colour planted in the room (or at the door) they would go to;
  a mark — "this way", "careful", "look here" — flashes over a room for a few
  seconds: rings spreading on the floor and a sign bobbing above them.
*/

export type BoardMarkKind = 'vote' | 'go' | 'danger' | 'look';

export interface BoardMark {
  key: string;
  roomId: number;
  /** The member's figurine colour. */
  color: string;
  kind: BoardMarkKind;
  /** performance.now() of a mark; votes stay until the party moves on. */
  at?: number;
}

/** How long a mark flashes over its room. */
export const MARK_SECONDS = 4;
const RING_PULSES = 3;
const FLAG_SCALE = 1.6;
const FLAG_SPACING = 0.15;
const DANGER_COLOR = '#ff5a3a';
/** How far towards the front of a room its marks stand, as a share of its depth. */
const FRONT_SHARE = 0.25;

type Spot = [number, number];

/**
  Where a mark stands: the middle of a room the party has seen, the door into
  one it has not, or — for a room on another floor — the stairs, drop or lift
  that lead there.
*/
const spotOf = (dungeon: BoardDungeon, layout: DioramaLayout, revealed: Set<number>, roomId: number): Spot | null => {
  const room = layout.rooms.get(roomId);
  // In front of whatever stands in the middle of the room.
  if (room && revealed.has(roomId)) return [room.center[0], room.center[1] + room.size[1] * FRONT_SHARE];
  const door = layout.doorways.find((d) => d.roomId === roomId);
  if (door) return [door.x - door.into[0] * 0.12, door.z - door.into[1] * 0.12];
  for (const r of dungeon.rooms) {
    const index = (r.passages ?? []).findIndex((p) => p.target === roomId);
    const from = layout.rooms.get(r.id);
    if (index >= 0 && from) return passageSpot(from, index);
  }
  return room ? room.center : null;
};

/** A member's flag: a pole with a little pennant in their colour, stirring. */
const VoteFlag = ({ position, color, seed }: { position: [number, number, number]; color: string; seed: number }) => {
  const cloth = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (cloth.current) cloth.current.rotation.y = Math.sin(clock.elapsedTime * 3 + seed) * 0.35;
  });
  return (
    <group position={position} scale={FLAG_SCALE}>
      <mesh position={[0, 0.16, 0]}>
        <cylinderGeometry args={[0.006, 0.008, 0.32, 6]} />
        <meshStandardMaterial color="#3a2414" roughness={0.8} />
      </mesh>
      <mesh position={[0, 0.006, 0]}>
        <cylinderGeometry args={[0.03, 0.035, 0.012, 12]} />
        <meshStandardMaterial color="#2a2420" roughness={0.6} />
      </mesh>
      <group ref={cloth} position={[0, 0.28, 0]}>
        <mesh position={[0.045, 0, 0]}>
          <planeGeometry args={[0.09, 0.06]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.6} side={THREE.DoubleSide} />
        </mesh>
      </group>
    </group>
  );
};

/** A flashing mark: rings spreading over the floor and a sign bobbing above, fading out. */
const Ping = ({ position, color, kind, at }: { position: [number, number, number]; color: string; kind: BoardMarkKind; at: number }) => {
  const group = useRef<THREE.Group>(null);
  const sign = useRef<THREE.Group>(null);
  const rings = useRef<(THREE.Mesh | null)[]>([]);
  const tint = kind === 'danger' ? DANGER_COLOR : color;
  useFrame(({ clock }) => {
    const age = (performance.now() - at) / 1000;
    const fade = THREE.MathUtils.clamp(1 - (age - (MARK_SECONDS - 0.6)) / 0.6, 0, 1);
    if (group.current) group.current.visible = age < MARK_SECONDS;
    rings.current.forEach((m, i) => {
      if (!m) return;
      const t = (age * 1.2 + i / RING_PULSES) % 1;
      m.scale.setScalar(0.15 + t * 0.9);
      (m.material as THREE.MeshBasicMaterial).opacity = (1 - t) * 0.8 * fade;
    });
    if (sign.current) {
      sign.current.position.y = 0.42 + Math.sin(clock.elapsedTime * 4) * 0.03;
      sign.current.rotation.y = kind === 'look' ? 0 : clock.elapsedTime * 1.5;
      sign.current.scale.setScalar(Math.min(1, age * 5) * fade + 0.0001);
    }
  });
  return (
    <group ref={group} position={position}>
      {Array.from({ length: RING_PULSES }, (_, i) => (
        <mesh
          key={i}
          position={[0, 0.004, 0]}
          rotation={[-Math.PI / 2, 0, 0]}
          ref={(el) => {
            rings.current[i] = el;
          }}
        >
          <ringGeometry args={[0.24, 0.28, 32]} />
          <meshBasicMaterial color={tint} transparent opacity={0} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
      <group ref={sign}>
        {kind === 'go' && (
          // An arrow pointing down at the room.
          <mesh rotation={[Math.PI, 0, 0]}>
            <coneGeometry args={[0.07, 0.16, 4]} />
            <meshStandardMaterial color={tint} emissive={tint} emissiveIntensity={1.2} toneMapped={false} />
          </mesh>
        )}
        {kind === 'danger' && (
          // An exclamation mark.
          <>
            <mesh position={[0, 0.04, 0]}>
              <boxGeometry args={[0.035, 0.13, 0.035]} />
              <meshStandardMaterial color={tint} emissive={tint} emissiveIntensity={1.4} toneMapped={false} />
            </mesh>
            <mesh position={[0, -0.07, 0]}>
              <sphereGeometry args={[0.024, 10, 8]} />
              <meshStandardMaterial color={tint} emissive={tint} emissiveIntensity={1.4} toneMapped={false} />
            </mesh>
          </>
        )}
        {kind === 'look' && (
          // An eye.
          <>
            <mesh scale={[1, 0.55, 1]}>
              <torusGeometry args={[0.07, 0.012, 8, 24]} />
              <meshStandardMaterial color={tint} emissive={tint} emissiveIntensity={1.2} toneMapped={false} />
            </mesh>
            <mesh>
              <sphereGeometry args={[0.026, 12, 10]} />
              <meshStandardMaterial color={tint} emissive={tint} emissiveIntensity={1.6} toneMapped={false} />
            </mesh>
          </>
        )}
      </group>
    </group>
  );
};

/** The party's flags and marks over the board (in board coordinates, on the floor's top). */
export const PartyMarks = ({
  marks,
  dungeon,
  layout,
  revealed,
}: {
  marks: BoardMark[];
  dungeon: BoardDungeon;
  layout: DioramaLayout;
  revealed: Set<number>;
}) => {
  // Several flags on one room stand in a row.
  const flagsAt = new Map<number, number>();
  return (
    <>
      {marks.map((m, i) => {
        const spot = spotOf(dungeon, layout, revealed, m.roomId);
        if (!spot) return null;
        if (m.kind === 'vote') {
          const n = flagsAt.get(m.roomId) ?? 0;
          flagsAt.set(m.roomId, n + 1);
          // 0, +1, -1, +2, -2 … spacings from the middle.
          const offset = (n % 2 ? 1 : -1) * Math.ceil(n / 2) * FLAG_SPACING;
          return <VoteFlag key={m.key} position={[spot[0] + offset, FLOOR_THICKNESS, spot[1]]} color={m.color} seed={i} />;
        }
        return <Ping key={m.key} position={[spot[0], FLOOR_THICKNESS, spot[1]]} color={m.color} kind={m.kind} at={m.at ?? 0} />;
      })}
    </>
  );
};
