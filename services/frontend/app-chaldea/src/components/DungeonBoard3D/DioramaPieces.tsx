import { useEffect, useLayoutEffect, useMemo, useRef, type ReactNode } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { mulberry32 } from '../pages/BattlePage/Arena3D/textures';
import { SQUARE, type Piece, type WallSegment } from './dioramaLayout';

/*
  The miniature's pieces. Floors, walls and corner posts are instanced — one
  draw call per kind per piece however many squares it has — and each piece
  rises out of the board when the party first reaches it.
*/

export const FLOOR_THICKNESS = 0.06;
export const WALL_HEIGHT = 0.4;
export const WALL_THICKNESS = 0.08;
const PILLAR = 0.11;
const RISE_SECONDS = 1.5;

export interface StoneMaterials {
  floor: THREE.Material;
  wall: THREE.Material;
  pillar: THREE.Material;
}

/** How tall the i-th wall segment of a piece stands, as a share of WALL_HEIGHT (the same draw PieceMesh makes). */
export const wallRise = (seed: number, i: number) => 0.92 + mulberry32(seed * 1301 + i)() * 0.14;

/** The far-wall segments that carry a piece's torches: one near each end of it. */
export const torchWalls = (piece: Piece): WallSegment[] => {
  const north = piece.walls.filter((w) => w.side === 'north').sort((a, b) => a.x - b.x);
  return north.length >= 3 ? [north[0], north[north.length - 1]] : north.slice(0, 1);
};

const easeOutBack = (t: number) => {
  const c = 1.4;
  return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
};

/** Grows its children up out of the board, starting at `appearAt` (performance.now, ms). */
export const Rising = ({ appearAt, children }: { appearAt: number; children: ReactNode }) => {
  const group = useRef<THREE.Group>(null);
  useFrame(() => {
    const g = group.current;
    if (!g) return;
    const t = THREE.MathUtils.clamp((performance.now() - appearAt) / 1000 / RISE_SECONDS, 0, 1);
    const s = t <= 0 ? 0.001 : Math.max(0.001, easeOutBack(t));
    g.scale.set(1, s, 1);
    g.visible = t > 0;
  });
  return <group ref={group}>{children}</group>;
};

const useInstances = (
  count: number,
  place: (i: number, m: THREE.Matrix4, c: THREE.Color) => void,
) => {
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const m = new THREE.Matrix4();
    const c = new THREE.Color();
    for (let i = 0; i < count; i++) {
      place(i, m, c);
      mesh.setMatrixAt(i, m);
      mesh.setColorAt(i, c);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });
  return ref;
};

/** Floor squares, walls and posts of one room or corridor. */
export const PieceMesh = ({ piece, materials, seed }: { piece: Piece; materials: StoneMaterials; seed: number }) => {
  const floorGeometry = useMemo(() => new THREE.BoxGeometry(SQUARE * 0.98, FLOOR_THICKNESS, SQUARE * 0.98), []);
  const wallGeometry = useMemo(() => new THREE.BoxGeometry(SQUARE, WALL_HEIGHT, WALL_THICKNESS), []);
  const pillarGeometry = useMemo(() => new THREE.BoxGeometry(PILLAR, WALL_HEIGHT + 0.05, PILLAR), []);
  useEffect(
    () => () => {
      floorGeometry.dispose();
      wallGeometry.dispose();
      pillarGeometry.dispose();
    },
    [floorGeometry, wallGeometry, pillarGeometry],
  );

  const floor = useInstances(piece.floor.length, (i, m, c) => {
    const rand = mulberry32(seed * 977 + i);
    const sq = piece.floor[i];
    // Each square turned a quarter at random so the slabs don't repeat in rows.
    m.makeRotationY(Math.floor(rand() * 4) * (Math.PI / 2));
    m.setPosition(sq.x, FLOOR_THICKNESS / 2, sq.z);
    c.setScalar(0.85 + rand() * 0.25);
  });
  const walls = useInstances(piece.walls.length, (i, m, c) => {
    const rand = mulberry32(seed * 1301 + i);
    const w: WallSegment = piece.walls[i];
    const h = wallRise(seed, i);
    rand();
    m.compose(
      new THREE.Vector3(w.x, FLOOR_THICKNESS + (WALL_HEIGHT * h) / 2, w.z),
      new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), w.alongX ? 0 : Math.PI / 2),
      new THREE.Vector3(1, h, 1),
    );
    c.setScalar(0.8 + rand() * 0.25);
  });
  const pillars = useInstances(piece.pillars.length, (i, m, c) => {
    const p = piece.pillars[i];
    m.makeTranslation(p.x, FLOOR_THICKNESS + (WALL_HEIGHT + 0.05) / 2, p.z);
    c.setScalar(0.75);
  });

  return (
    <group>
      <instancedMesh ref={floor} args={[floorGeometry, materials.floor, piece.floor.length]} />
      {piece.walls.length > 0 && (
        <instancedMesh ref={walls} args={[wallGeometry, materials.wall, piece.walls.length]} />
      )}
      {piece.pillars.length > 0 && (
        <instancedMesh ref={pillars} args={[pillarGeometry, materials.pillar, piece.pillars.length]} />
      )}
    </group>
  );
};

/* ── Fire ── */

/** A small flickering flame sprite with a halo. */
export const Fire = ({
  position,
  flame,
  glow,
  seed,
  size = 0.22,
  color = '#ffb35c',
}: {
  position: [number, number, number];
  flame: THREE.Texture;
  glow: THREE.Texture;
  seed: number;
  size?: number;
  color?: string;
}) => {
  const sprite = useRef<THREE.Sprite>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime * 9 + seed * 7;
    const flick = 1 + Math.sin(t) * 0.1 + Math.sin(t * 2.3) * 0.06;
    sprite.current?.scale.set(size * 0.6 * (2 - flick), size * flick, 1);
  });
  return (
    <group position={position}>
      <sprite ref={sprite}>
        <spriteMaterial map={flame} transparent depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
      </sprite>
      <sprite scale={[size * 2.6, size * 2.6, 1]}>
        <spriteMaterial map={glow} color={color} transparent opacity={0.5} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
      </sprite>
    </group>
  );
};

/** Wall torches: an iron bracket on the far wall of the room with a flame on top. */
export const Torches = ({
  piece,
  flame,
  glow,
  seed,
  color,
}: {
  piece: Piece;
  flame: THREE.Texture;
  glow: THREE.Texture;
  seed: number;
  /** The halo round the flame (the dungeon's look). */
  color?: string;
}) => {
  // The far (north) wall faces the camera; one torch near each end of it.
  const spots = torchWalls(piece);
  return (
    <>
      {spots.map((w, i) => (
        <group key={i} position={[w.x, FLOOR_THICKNESS, w.z + WALL_THICKNESS / 2 + 0.03]}>
          <mesh position={[0, WALL_HEIGHT * 0.72, 0]}>
            <boxGeometry args={[0.04, 0.12, 0.05]} />
            <meshStandardMaterial color="#2a2420" metalness={0.6} roughness={0.5} />
          </mesh>
          <Fire position={[0, WALL_HEIGHT * 0.72 + 0.1, 0.02]} flame={flame} glow={glow} seed={seed * 5 + i} size={0.14} color={color} />
        </group>
      ))}
    </>
  );
};
