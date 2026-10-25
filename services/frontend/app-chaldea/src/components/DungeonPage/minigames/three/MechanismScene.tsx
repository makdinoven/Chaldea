import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import type { MechanismParams } from '../../../../api/dungeons';
import { createWallBlockTexture } from '../../../DungeonBoard3D/stoneTextures';
import { CraftLights, Halo, SparkField, SparkPool, pointer, useJolt } from './craftKit';
import { ironTexture, markTexture, stoneTexture } from './craftTextures';

/*
  The hidden mechanism in 3D: a stretch of old wall, five blocks by four. A
  pressed block sinks in with a grind and a figure glows on it — how many steps
  to the lever: warm near, cold far. The lever's block sinks deep and slides
  aside, the iron lever in its niche swings down, and the wall shudders.
*/

export const MECHANISM_CAMERA = { position: [0, 0.05, 3.4] as [number, number, number], fov: 32 };

const BLOCK_W = 0.5;
const BLOCK_H = 0.36;
const GAP = 0.035;
const PRESS_DEPTH = 0.07;
const LEVER_MS = 900;
/** How deep the lever's block sinks: behind the niche's back. */
const LEVER_SINK = 0.5;

/** Warm when close, cold when far (by steps). */
const HEAT = ['#ffd36a', '#ff9a3c', '#d9a24a', '#7fa8ff'];
const heatOf = (distance: number) => new THREE.Color(HEAT[Math.min(HEAT.length - 1, distance)]);

interface MechanismSceneProps {
  params: MechanismParams;
  /** Pressed blocks: "x,y" → steps to the lever. */
  answers: Map<string, number>;
  /** No more presses left (found or not). */
  over: boolean;
  onPress: (x: number, y: number) => void;
}

const MechanismScene = ({ params, answers, over, onPress }: MechanismSceneProps) => {
  const [hovered, setHovered] = useState<string | null>(null);
  const textures = useMemo(() => {
    const wall = createWallBlockTexture();
    wall.wrapS = wall.wrapT = THREE.RepeatWrapping;
    wall.repeat.set(11, 7);
    return { wall, stone: stoneTexture(), iron: ironTexture() };
  }, []);
  const blocks = useMemo(() => {
    const list: { key: string; x: number; y: number; pos: [number, number] }[] = [];
    const w = params.cols * (BLOCK_W + GAP);
    const h = params.rows * (BLOCK_H + GAP);
    for (let y = 0; y < params.rows; y++) {
      for (let x = 0; x < params.cols; x++) {
        // Courses offset a little, like laid stone.
        const shift = y % 2 ? 0.04 : -0.04;
        list.push({
          key: `${x},${y}`,
          x,
          y,
          pos: [-w / 2 + (x + 0.5) * (BLOCK_W + GAP) + shift, h / 2 - (y + 0.5) * (BLOCK_H + GAP) + 0.02],
        });
      }
    }
    return list;
  }, [params.cols, params.rows]);
  const stoneMats = useMemo(
    () =>
      blocks.map(
        (_, i) =>
          new THREE.MeshStandardMaterial({
            map: textures.stone,
            color: new THREE.Color().setHSL(0.08, 0.06, 0.5 + ((i * 37) % 9) / 90),
            roughness: 0.9,
          }),
      ),
    [blocks, textures],
  );
  const faceMats = useRef(new Map<string, THREE.MeshStandardMaterial>());
  const groups = useRef(new Map<string, THREE.Group>());
  const lever = useRef<THREE.Group>(null);
  const sparks = useMemo(() => new SparkPool(70), []);
  const jolt = useJolt();
  const seen = useRef({ count: 0, foundAt: -Infinity, overAt: -Infinity, caught: false });
  const found = [...answers.entries()].find(([, d]) => d === 0)?.[0] ?? null;

  const faceMaterial = (key: string, distance: number) => {
    let m = faceMats.current.get(key);
    if (!m) {
      m = new THREE.MeshStandardMaterial({
        map: markTexture(distance === 0 ? '✦' : String(distance)),
        emissiveMap: markTexture(distance === 0 ? '✦' : String(distance)),
        emissive: heatOf(distance),
        emissiveIntensity: 0,
        color: '#000',
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      faceMats.current.set(key, m);
    }
    return m;
  };

  useFrame((state, delta) => {
    const now = performance.now();
    if (answers.size > seen.current.count) {
      seen.current.count = answers.size;
      const last = [...answers.entries()][answers.size - 1];
      const block = blocks.find((b) => b.key === last[0]);
      if (block) {
        sparks.burst(new THREE.Vector3(block.pos[0], block.pos[1] - BLOCK_H / 2, 0.1), '#9a8c78', 10, 0.5,
          { size: 0.7, life: 0.9, up: 0.1 });
        jolt.kick(last[1] === 0 ? 0.04 : 0.012);
      }
      if (last[1] === 0) seen.current.foundAt = now;
    }
    if (over && seen.current.overAt === -Infinity) {
      seen.current.overAt = now;
      if (!found) {
        // The presses ran out: the wall settles with a fall of grit.
        for (const b of blocks) {
          if (Math.random() < 0.3) sparks.burst(new THREE.Vector3(b.pos[0], b.pos[1], 0.1), '#7a6e60', 3, 0.3, { size: 0.6, life: 1 });
        }
      }
    }
    const opened = found ? Math.min(1, (now - seen.current.foundAt) / LEVER_MS) : 0;

    blocks.forEach((b) => {
      const group = groups.current.get(b.key);
      if (!group) return;
      const distance = answers.get(b.key);
      const pressed = distance !== undefined;
      let z = pressed ? -PRESS_DEPTH : hovered === b.key && !over ? 0.015 : 0;
      if (b.key === found) {
        // The lever's block sinks deep into the wall, baring the niche.
        z = -PRESS_DEPTH - Math.min(1, opened * 2) * (LEVER_SINK - PRESS_DEPTH);
      }
      group.position.z = THREE.MathUtils.damp(group.position.z, z, 16, delta);
      const face = faceMats.current.get(b.key);
      if (face) face.emissiveIntensity = THREE.MathUtils.damp(face.emissiveIntensity, 1.3 + Math.sin(now * 0.004) * 0.15, 6, delta);
    });

    if (lever.current) {
      const pull = Math.max(0, opened * 2 - 1);
      lever.current.rotation.z = THREE.MathUtils.lerp(0.7, -0.7, pull);
      if (opened >= 1 && !seen.current.caught) {
        // The mechanism catches: one shudder, a breath of dust.
        seen.current.caught = true;
        jolt.kick(0.035);
        sparks.burst(new THREE.Vector3(0, -0.6, 0.15), '#a89880', 24, 0.9, { size: 0.8, life: 1.2, spread: 2 });
      }
    }

    state.camera.position.x = Math.sin(now * 0.0004) * 0.05;
    state.camera.lookAt(0, 0.02, 0);
  });

  const leverBlock = found ? blocks.find((b) => b.key === found) : null;
  return (
    <>
      <CraftLights candle={[-1.8, 1.0, 1.6]} />
      <mesh position={[0, 0, -0.32]}>
        <planeGeometry args={[8, 5]} />
        <meshStandardMaterial map={textures.wall} color="#5e5a54" roughness={0.95} />
      </mesh>
      {/* The dark behind the blocks, and the lever's niche */}
      <mesh position={[0, 0.02, -0.22]}>
        <planeGeometry args={[params.cols * (BLOCK_W + GAP) + 0.12, params.rows * (BLOCK_H + GAP) + 0.06]} />
        <meshStandardMaterial color="#0c0b0a" roughness={1} />
      </mesh>
      <group ref={jolt.group}>
        {blocks.map((b, i) => {
          const distance = answers.get(b.key);
          return (
            <group
              key={b.key}
              ref={(el) => {
                if (el) groups.current.set(b.key, el);
              }}
              position={[b.pos[0], b.pos[1], 0]}
              onClick={(e) => {
                e.stopPropagation();
                if (!over && distance === undefined) onPress(b.x, b.y);
              }}
              onPointerOver={(e) => {
                e.stopPropagation();
                setHovered(b.key);
                if (!over && distance === undefined) pointer.onPointerOver();
              }}
              onPointerOut={() => {
                setHovered((h) => (h === b.key ? null : h));
                pointer.onPointerOut();
              }}
            >
              <RoundedBox args={[BLOCK_W, BLOCK_H, 0.3]} radius={0.03} smoothness={3} position={[0, 0, -0.15]} material={stoneMats[i]} />
              {distance !== undefined && (
                <mesh position={[0, 0, 0.003]} material={faceMaterial(b.key, distance)}>
                  <planeGeometry args={[BLOCK_H * 0.8, BLOCK_H * 0.8]} />
                </mesh>
              )}
            </group>
          );
        })}

        {/* The lever, waiting in the niche behind its block */}
        {leverBlock && (
          <group position={[leverBlock.pos[0], leverBlock.pos[1], -0.2]}>
            <mesh>
              <boxGeometry args={[BLOCK_W * 0.9, BLOCK_H * 0.9, 0.02]} />
              <meshStandardMaterial color="#141210" roughness={1} />
            </mesh>
            <mesh position={[0, 0, 0.03]} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[0.04, 0.04, 0.05, 16]} />
              <meshStandardMaterial map={textures.iron} color="#9a9aa2" metalness={0.8} roughness={0.45} />
            </mesh>
            <group ref={lever} position={[0, 0, 0.05]}>
              <mesh position={[0, 0.1, 0]}>
                <boxGeometry args={[0.03, 0.2, 0.03]} />
                <meshStandardMaterial map={textures.iron} color="#a8a8b0" metalness={0.85} roughness={0.4} />
              </mesh>
              <mesh position={[0, 0.21, 0]}>
                <sphereGeometry args={[0.035, 14, 10]} />
                <meshStandardMaterial color="#5a3a22" roughness={0.7} />
              </mesh>
            </group>
            <Halo position={[0, 0, 0.1]} color="#ffd36a" scale={0.6} opacity={0.25} />
          </group>
        )}
        <SparkField pool={sparks} max={70} gravity={-2} dull />
      </group>
      <Halo position={[-2.1, 1.2, 0.4]} color="#ff9a40" />
    </>
  );
};

export default MechanismScene;
