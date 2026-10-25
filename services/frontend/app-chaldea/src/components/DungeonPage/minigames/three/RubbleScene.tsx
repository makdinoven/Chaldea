import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { RubbleParams } from '../../../../api/dungeons';
import { createCrackTexture } from '../../../DungeonBoard3D/decorTextures';
import { createWallBlockTexture } from '../../../DungeonBoard3D/stoneTextures';
import { CraftLights, Halo, SparkField, SparkPool, pointer, useJolt } from './craftKit';
import { stoneTexture } from './craftTextures';

/*
  The cave-in in 3D: a tunnel mouth choked by a pile of boulders, propped by a
  timber or two. Cracks run deep in the stones that bear the rest (mostly): a
  hairline, a crack shedding dust, a split stone sagging with sand running out.
  The lower stones bear more often. A
  pulled stone rolls out and drops away; a bearing one shakes the pile and a
  prop snaps; once the props are gone, the pile slumps in a cloud of dust.
  Cleared, the last stones roll aside and the draught from beyond lifts the dust.
*/

export const RUBBLE_CAMERA = { position: [0, 0.15, 3.4] as [number, number, number], fov: 32 };

/** The pile from the bottom up: four, three, two. */
const ROWS = [[0, 1, 2, 3], [4, 5, 6], [7, 8]];
const SIZE = 0.46;
const STEP_X = 0.42;
const STEP_Y = 0.34;
const BASE_Y = -0.58;
const FALL_MS = 900;
const SLUMP_MS = 900;
const OPEN_MS = 1000;

/** A stone's place in the pile, a little off the neat rows. */
const boulderSpot = (i: number): [number, number] => {
  const r = ROWS.findIndex((row) => row.includes(i));
  const row = ROWS[r];
  const k = row.indexOf(i);
  return [(k - (row.length - 1) / 2) * STEP_X + Math.sin(i * 12.9) * 0.04, BASE_Y + r * STEP_Y + Math.cos(i * 7.3) * 0.03];
};
/** How each stone lies: tipped one way or another. */
const boulderTilt = (i: number): [number, number, number] => [Math.sin(i * 3.1) * 0.5, Math.cos(i * 5.7) * 0.8, Math.sin(i * 1.9) * 0.4];

/** Rubble that fills the mouth round the stones to pull (not to be pulled itself). */
const GRAVEL: [number, number, number, number][] = Array.from({ length: 26 }, (_, i) => {
  const side = i % 2 ? 1 : -1;
  const low = i < 10;
  const x = low ? (i / 10 - 0.5) * 1.8 : side * (0.62 + ((i * 0.37) % 0.3));
  const y = low ? -0.76 + ((i * 0.13) % 0.06) : -0.7 + ((i * 0.29) % 1) * 0.95;
  return [x, y, -0.12 - ((i * 0.17) % 0.18), 0.12 + ((i * 0.23) % 0.14)];
});

/** A lumpy boulder: an icosphere pushed in and out by a seeded wobble. */
const boulderGeometry = (seed: number) => {
  const geometry = new THREE.IcosahedronGeometry(SIZE / 2, 2);
  const pos = geometry.attributes.position;
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i);
    const n = Math.sin(v.x * 17 + seed) * Math.cos(v.y * 13 + seed * 1.7) * Math.sin(v.z * 11 + seed * 0.7);
    v.multiplyScalar(1 + n * 0.24);
    v.y *= 0.78;
    v.x *= 1.08;
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  geometry.computeVertexNormals();
  return geometry;
};

export type RubbleEnd = 'open' | 'broke' | null;

/** What a stone's cracks look like, by depth: none, a hairline, a crack, a split. */
const CRACK_LOOK: ({ size: number; opacity: number; twin: boolean } | null)[] = [
  null,
  { size: 0.36, opacity: 0.55, twin: false },
  { size: 0.72, opacity: 0.9, twin: false },
  { size: 0.95, opacity: 1, twin: true },
];
/** How often (ms) a cracked stone sheds dust or sand, by depth. */
const SHED_MS = [0, 0, 1300, 380];
/** A split stone has settled under the weight. */
const SPLIT_SAG = 0.035;
const SPLIT_TILT = 0.14;

/** Said over a stone on hover, by the depth of its cracks. */
export const CRACK_WORDS = ['Цел', 'Трещина', 'Глубокая трещина', 'Раскол — держит вес?'];

interface RubbleSceneProps {
  params: RubbleParams;
  /** Pulled stones: index → came out safely. */
  pulled: Map<number, boolean>;
  end: RubbleEnd;
  onPull: (index: number) => void;
  /** The stone under the pointer (to say what its cracks look like), or null. */
  onHover?: (index: number | null) => void;
}

const RubbleScene = ({ params, pulled, end, onPull, onHover }: RubbleSceneProps) => {
  const [hovered, setHovered] = useState<number | null>(null);
  const count = params.cracks.length;
  const textures = useMemo(() => {
    const wall = createWallBlockTexture();
    wall.wrapS = wall.wrapT = THREE.RepeatWrapping;
    wall.repeat.set(11, 7);
    return { wall, stone: stoneTexture() };
  }, []);
  const geometries = useMemo(() => Array.from({ length: count }, (_, i) => boulderGeometry(i * 2.3 + 1)), [count]);
  const gravelGeometry = useMemo(() => boulderGeometry(42), []);
  const materials = useMemo(
    () =>
      Array.from(
        { length: count },
        (_, i) =>
          new THREE.MeshStandardMaterial({
            map: textures.stone,
            color: new THREE.Color().setHSL(0.08, 0.05, 0.36 + ((i * 29) % 7) / 70),
            roughness: 0.92,
            flatShading: true,
          }),
      ),
    [count, textures],
  );
  // Cracks on each boulder's face: a split stone has two, crossing.
  const crackMaterials = useMemo(
    () =>
      params.cracks.map((depth, i) => {
        const look = CRACK_LOOK[depth];
        if (!look) return null;
        const make = (seed: number) =>
          new THREE.MeshBasicMaterial({ map: createCrackTexture(seed), transparent: true, opacity: look.opacity, depthWrite: false });
        return { look, first: make(100 + i * 7), second: look.twin ? make(300 + i * 11) : null };
      }),
    [params.cracks],
  );
  const shedAt = useRef<number[]>([]);
  const boulders = useRef<(THREE.Group | null)[]>([]);
  const braces = useRef<(THREE.Group | null)[]>([]);
  const fallen = useRef(new Map<number, { at: number; spin: THREE.Vector3 }>());
  const sparks = useMemo(() => new SparkPool(120), []);
  const jolt = useJolt(450);
  const seen = useRef({ count: 0, collapses: 0, endAt: -Infinity });
  const collapses = [...pulled.values()].filter((safe) => !safe).length;

  useFrame((state, delta) => {
    const now = performance.now();
    if (pulled.size > seen.current.count) {
      seen.current.count = pulled.size;
      const [index, safe] = [...pulled.entries()][pulled.size - 1];
      const [x, y] = boulderSpot(index);
      fallen.current.set(index, { at: now, spin: new THREE.Vector3(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5) });
      sparks.burst(new THREE.Vector3(x, y, 0.2), '#a39784', 10, 0.5, { size: 0.9, life: 1, up: 0.2 });
      if (!safe) {
        // A bearing stone: the pile shakes and dust pours from its top.
        jolt.kick(0.05);
        sparks.burst(new THREE.Vector3(0, BASE_Y + 2.2 * STEP_Y, 0.1), '#8d8270', 30, 0.8, { size: 1.2, life: 1.4, spread: 1.6 });
      }
    }
    if (end && seen.current.endAt === -Infinity) {
      seen.current.endAt = now;
      if (end === 'broke') {
        jolt.kick(0.08);
        sparks.burst(new THREE.Vector3(0, BASE_Y + STEP_Y, 0.2), '#7e7462', 60, 1.3, { size: 1.6, life: 1.8, spread: 2.2 });
      } else {
        sparks.burst(new THREE.Vector3(0, BASE_Y + STEP_Y, -0.1), '#ffd9a0', 30, 0.4, { size: 0.8, life: 1.6, up: 0.6 });
      }
    }
    const sinceEnd = now - seen.current.endAt;
    const slump = end === 'broke' ? Math.min(1, sinceEnd / SLUMP_MS) : 0;
    const parted = end === 'open' ? Math.min(1, sinceEnd / OPEN_MS) : 0;

    for (let i = 0; i < count; i++) {
      const group = boulders.current[i];
      if (!group) continue;
      const [x, y] = boulderSpot(i);
      const fall = fallen.current.get(i);
      if (fall) {
        // Out it comes: rolled towards us, then dropped out of sight.
        const t = Math.min(1, (now - fall.at) / FALL_MS);
        group.position.set(x + fall.spin.x * 0.3 * t, y - t * t * 1.4, 0.15 + t * 0.6);
        group.rotation.set(fall.spin.x * t * 4, fall.spin.y * t * 4, fall.spin.z * t * 4);
        group.visible = t < 1;
        continue;
      }
      const lift = hovered === i && !end ? 0.025 : 0;
      const split = params.cracks[i] >= 3;
      // Slumped: everything sags and settles lower; parted: the stones roll aside.
      const sag = slump * (0.12 + (y - BASE_Y) * 0.35) + (split ? SPLIT_SAG : 0);
      const aside = parted * Math.sign(x || (i % 2 ? 1 : -1)) * 0.9;
      const [rx, ry, rz] = boulderTilt(i);
      group.position.set(x + aside, y + lift - sag, 0);
      group.rotation.set(rx, ry, rz + (split ? SPLIT_TILT : 0) + slump * (i % 2 ? 0.25 : -0.2) - aside * 2);
      // A cracked stone under load sheds dust; a split one runs with sand.
      const every = SHED_MS[params.cracks[i]] ?? 0;
      if (every && !end && now - (shedAt.current[i] ?? 0) > every * (0.7 + Math.random() * 0.6)) {
        shedAt.current[i] = now;
        sparks.burst(
          new THREE.Vector3(x + (Math.random() - 0.5) * SIZE * 0.5, y - sag - SIZE * 0.35, SIZE * 0.45),
          split ? '#c9ae7c' : '#9a8f80',
          split ? 2 : 3,
          0.08,
          { size: split ? 0.45 : 0.6, life: split ? 1.1 : 0.9, up: -0.2, spread: 0.6 },
        );
      }
    }

    // A timber prop snaps for every bearing stone pulled.
    braces.current.forEach((brace, i) => {
      if (!brace) return;
      const broken = i < collapses;
      brace.rotation.z = THREE.MathUtils.damp(brace.rotation.z, (i % 2 ? -1 : 1) * (broken ? 1.3 : 0.35), 6, delta);
      brace.position.y = THREE.MathUtils.damp(brace.position.y, broken ? -0.95 : -0.25, 5, delta);
    });

    state.camera.position.x = Math.sin(now * 0.0004) * 0.05;
    state.camera.lookAt(0, -0.1, 0);
  });

  return (
    <>
      <CraftLights candle={[-1.7, 1.0, 1.6]} spot={[0.2, 1.6, 2.4]} />
      <mesh position={[0, 0, -0.5]}>
        <planeGeometry args={[8, 5]} />
        <meshStandardMaterial map={textures.wall} color="#5e5a54" roughness={0.95} />
      </mesh>
      {/* The tunnel mouth: dark, a warm breath of light from beyond once cleared */}
      <mesh position={[0, -0.2, -0.45]}>
        <planeGeometry args={[1.9, 1.5]} />
        <meshStandardMaterial color="#070606" roughness={1} />
      </mesh>
      {end === 'open' && <Halo position={[0, -0.25, -0.4]} color="#ffcf8a" scale={1.6} opacity={0.35} />}
      {/* The arch round the mouth */}
      {(
        [
          [-1.05, -0.2, 0.22, 1.6],
          [1.05, -0.2, 0.22, 1.6],
          [0, 0.62, 2.32, 0.22],
        ] as const
      ).map(([x, y, w, h]) => (
        <mesh key={`${x},${y}`} position={[x, y, -0.35]}>
          <boxGeometry args={[w, h, 0.3]} />
          <meshStandardMaterial map={textures.stone} color="#8a8a86" roughness={0.9} />
        </mesh>
      ))}
      {/* Rubble round the pile */}
      {GRAVEL.map(([x, y, z, size], i) => (
        <mesh key={i} position={[x, y, z]} rotation={boulderTilt(i + 20)} scale={size / SIZE} geometry={gravelGeometry} raycast={() => null}>
          <meshStandardMaterial map={textures.stone} color="#55524c" roughness={0.95} flatShading />
        </mesh>
      ))}
      {/* The floor */}
      <mesh position={[0, -0.82, 0.2]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[6, 2.4]} />
        <meshStandardMaterial map={textures.stone} color="#4a4640" roughness={1} />
      </mesh>

      <group ref={jolt.group}>
        {/* Timber props holding the pile */}
        {Array.from({ length: params.braces }, (_, i) => (
          <group
            key={i}
            ref={(el) => {
              braces.current[i] = el;
            }}
            position={[i % 2 ? 0.86 : -0.86, -0.25, 0.12]}
            rotation={[0, 0, (i % 2 ? -1 : 1) * 0.35]}
          >
            <mesh>
              <boxGeometry args={[0.08, 1.1, 0.08]} />
              <meshStandardMaterial color="#4a3320" roughness={0.9} />
            </mesh>
          </group>
        ))}

        {geometries.map((geometry, i) => (
          <group
            key={i}
            ref={(el) => {
              boulders.current[i] = el;
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (!end && !pulled.has(i)) onPull(i);
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHovered(i);
              if (!end && !pulled.has(i)) {
                pointer.onPointerOver();
                onHover?.(i);
              }
            }}
            onPointerOut={() => {
              setHovered((h) => (h === i ? null : h));
              pointer.onPointerOut();
              onHover?.(null);
            }}
          >
            <mesh geometry={geometry} material={materials[i]} />
            {crackMaterials[i] && (
              <mesh position={[0, 0.02, SIZE * 0.62]} material={crackMaterials[i]!.first} raycast={() => null}>
                <planeGeometry args={[SIZE * crackMaterials[i]!.look.size, SIZE * crackMaterials[i]!.look.size]} />
              </mesh>
            )}
            {crackMaterials[i]?.second && (
              <mesh position={[0.01, 0, SIZE * 0.63]} rotation={[0, 0, 1.2]} material={crackMaterials[i]!.second!} raycast={() => null}>
                <planeGeometry args={[SIZE * 0.85, SIZE * 0.85]} />
              </mesh>
            )}
          </group>
        ))}
        <SparkField pool={sparks} max={120} gravity={-0.9} dull />
      </group>
      <Halo position={[-2.1, 1.2, 0.4]} color="#ff9a40" />
    </>
  );
};

export default RubbleScene;
