import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import type { SearchParams } from '../../../../api/dungeons';
import { createFlagstoneTexture } from '../../../DungeonBoard3D/stoneTextures';
import { CraftLights, Halo, SparkField, SparkPool, pointer, useJolt } from './craftKit';
import { brassTexture, doorPlanksTexture, stoneTexture, tracesTexture } from './craftTextures';

/*
  Searching a room in 3D: its floor seen from above, slab by slab, a candle at
  the edge. A slab looked under is lifted aside in a puff of dust, and the
  traces beneath glow — drag marks pointing the way, mostly towards a stash.
  The stash is a small chest in a hollow that glows gold when found.
*/

export const SEARCH_CAMERA = { position: [0, 2.8, 2.35] as [number, number, number], fov: 38 };
/** On a phone the floor is seen from nearly straight above: every slab the same size under the finger. */
const PHONE_QUERY = '(max-width: 639px)';
const PHONE_CAMERA: [number, number, number] = [0, 3.45, 0.12];

const TILE = 0.5;
const GAP = 0.03;
const LIFT_MS = 450;

interface SearchSceneProps {
  params: SearchParams;
  /** Looked-under slabs: "x,y" → the way the traces point (0 up, clockwise by eighths), null where the stash was. */
  looks: Map<string, number | null>;
  over: boolean;
  onLook: (x: number, y: number) => void;
}

const SearchScene = ({ params, looks, over, onLook }: SearchSceneProps) => {
  const [hovered, setHovered] = useState<string | null>(null);
  const phone = useMemo(() => typeof window !== 'undefined' && window.matchMedia(PHONE_QUERY).matches, []);
  const textures = useMemo(() => {
    const floor = createFlagstoneTexture();
    floor.wrapS = floor.wrapT = THREE.RepeatWrapping;
    floor.repeat.set(8, 6);
    return { floor, stone: stoneTexture(), traces: tracesTexture(), planks: doorPlanksTexture(), brass: brassTexture() };
  }, []);
  const tiles = useMemo(() => {
    const list: { key: string; x: number; y: number; pos: [number, number] }[] = [];
    const w = params.cols * (TILE + GAP);
    const d = params.rows * (TILE + GAP);
    for (let y = 0; y < params.rows; y++) {
      for (let x = 0; x < params.cols; x++) {
        list.push({ key: `${x},${y}`, x, y, pos: [-w / 2 + (x + 0.5) * (TILE + GAP), -d / 2 + (y + 0.5) * (TILE + GAP)] });
      }
    }
    return list;
  }, [params.cols, params.rows]);
  const slabMats = useMemo(
    () =>
      tiles.map(
        (_, i) =>
          new THREE.MeshStandardMaterial({
            map: textures.stone,
            color: new THREE.Color().setHSL(0.08, 0.05, 0.42 + ((i * 31) % 9) / 100),
            roughness: 0.92,
          }),
      ),
    [tiles, textures],
  );
  const traceMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        map: textures.traces,
        color: '#ffcf7a',
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
    [textures],
  );
  const slabs = useRef(new Map<string, THREE.Group>());
  const lifted = useRef(new Map<string, number>());
  const sparks = useMemo(() => new SparkPool(80), []);
  const jolt = useJolt();
  const seen = useRef(0);

  useFrame((state, delta) => {
    const now = performance.now();
    if (looks.size > seen.current) {
      seen.current = looks.size;
      const [key, way] = [...looks.entries()][looks.size - 1];
      lifted.current.set(key, now);
      const tile = tiles.find((t) => t.key === key);
      if (tile) {
        sparks.burst(new THREE.Vector3(tile.pos[0], 0.05, tile.pos[1]), '#a39784', 12, 0.5, { size: 0.8, life: 0.9, up: 0.6 });
        if (way === null) {
          sparks.burst(new THREE.Vector3(tile.pos[0], 0.1, tile.pos[1]), '#ffd36a', 24, 0.8, { size: 1, life: 1.4, up: 1 });
          jolt.kick(0.015);
        }
      }
    }
    tiles.forEach((t) => {
      const group = slabs.current.get(t.key);
      if (!group) return;
      const at = lifted.current.get(t.key);
      if (at !== undefined) {
        // Lifted and laid on its neighbour, clear of the hollow so the traces show.
        const k = Math.min(1, (now - at) / LIFT_MS);
        const arc = Math.sin(k * Math.PI) * 0.25;
        const side = t.x < params.cols - 1 ? 1 : -1;
        group.position.set(t.pos[0] + side * k * TILE * 0.9, 0.05 + arc + k * 0.1, t.pos[1] - k * TILE * 0.15);
        group.rotation.set(0, k * 0.3, side * k * 0.08);
      } else {
        const lift = hovered === t.key && !over ? 0.02 : 0;
        group.position.set(t.pos[0], THREE.MathUtils.damp(group.position.y, lift, 14, delta), t.pos[1]);
      }
    });
    traceMat.opacity = 0.75 + Math.sin(now * 0.004) * 0.2;
    if (phone) {
      // Looking straight down, "up" on the screen is the far side of the floor; no sway (it would roll the view).
      state.camera.up.set(0, 0, -1);
      state.camera.position.set(...PHONE_CAMERA);
      state.camera.lookAt(0, 0, 0);
    } else {
      state.camera.position.x = Math.sin(now * 0.0004) * 0.05;
      state.camera.lookAt(0, 0, 0.05);
    }
  });

  return (
    <>
      <CraftLights candle={[-1.9, 1.2, 0.6]} spot={[0, 2.6, 1.2]} spotIntensity={10} />
      {/* The rest of the room's floor round the searched part */}
      <mesh position={[0, -0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[8, 6]} />
        <meshStandardMaterial map={textures.floor} color="#4a4640" roughness={1} />
      </mesh>
      <group ref={jolt.group}>
        {tiles.map((t, i) => {
          const way = looks.get(t.key);
          const looked = looks.has(t.key);
          return (
            <group key={t.key}>
              {/* Under the slab: dark earth, and the traces or the stash */}
              <mesh position={[t.pos[0], 0.001, t.pos[1]]} rotation={[-Math.PI / 2, 0, 0]}>
                <planeGeometry args={[TILE, TILE]} />
                <meshStandardMaterial color="#1a1612" roughness={1} />
              </mesh>
              {looked && way !== null && way !== undefined && (
                <mesh position={[t.pos[0], 0.004, t.pos[1]]} rotation={[-Math.PI / 2, 0, -(way * Math.PI) / 4]} material={traceMat}>
                  <planeGeometry args={[TILE * 0.85, TILE * 0.85]} />
                </mesh>
              )}
              {looked && way === null && (
                <group position={[t.pos[0], 0.06, t.pos[1]]}>
                  <mesh>
                    <boxGeometry args={[0.28, 0.12, 0.2]} />
                    <meshStandardMaterial map={textures.planks} color="#8a6440" roughness={0.8} />
                  </mesh>
                  <mesh position={[0, 0.07, 0]}>
                    <boxGeometry args={[0.3, 0.03, 0.22]} />
                    <meshStandardMaterial map={textures.brass} color="#e6d2a0" metalness={0.8} roughness={0.3} />
                  </mesh>
                  <Halo position={[0, 0.15, 0]} color="#ffcf5a" scale={0.8} opacity={0.5} />
                </group>
              )}
              <group
                ref={(el) => {
                  if (el) slabs.current.set(t.key, el);
                }}
                position={[t.pos[0], 0, t.pos[1]]}
                onClick={(e) => {
                  e.stopPropagation();
                  if (!over && !looked) onLook(t.x, t.y);
                }}
                onPointerOver={(e) => {
                  e.stopPropagation();
                  setHovered(t.key);
                  if (!over && !looked) pointer.onPointerOver();
                }}
                onPointerOut={() => {
                  setHovered((h) => (h === t.key ? null : h));
                  pointer.onPointerOut();
                }}
              >
                <RoundedBox args={[TILE, 0.1, TILE]} radius={0.02} smoothness={2} position={[0, 0.05, 0]} material={slabMats[i]} />
              </group>
            </group>
          );
        })}
        <SparkField pool={sparks} max={80} gravity={-1.6} />
      </group>
      <Halo position={[-2.0, 1.0, 0.6]} color="#ff9a40" scale={1.4} />
    </>
  );
};

export default SearchScene;
