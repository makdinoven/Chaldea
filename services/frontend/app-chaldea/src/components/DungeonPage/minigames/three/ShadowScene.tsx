import { useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { ShadowParams } from '../../../../api/dungeons';
import { createFlagstoneTexture, createWallBlockTexture } from '../../../DungeonBoard3D/stoneTextures';
import { shadowLit, type ShadowOutcome, type ShadowState } from '../intel';
import { CraftLights, Halo, SparkField, SparkPool, useJolt } from './craftKit';
import { ironTexture } from './craftTextures';

/*
  Scouting in 3D: a long corridor seen from above and behind, a hooded rogue at
  its mouth, lanterns hanging over some of its flagstones. Each flares in turn
  and throws a pool of light on the floor; a rogue caught in one flashes red.
*/

export const SHADOW_CAMERA = { position: [0, 3.2, 3.6] as [number, number, number], fov: 40 };

const CELL = 0.42;
const WALK_MS = 140;

interface ShadowSceneProps {
  params: ShadowParams;
  live: MutableRefObject<ShadowState>;
  outcome: ShadowOutcome | null;
}

const ShadowScene = ({ params, live, outcome }: ShadowSceneProps) => {
  const total = params.cells + 2;
  const x0 = -((total - 1) * CELL) / 2;
  const cellX = (i: number) => x0 + i * CELL;
  const textures = useMemo(() => {
    const floor = createFlagstoneTexture();
    const wall = createWallBlockTexture();
    wall.wrapS = wall.wrapT = THREE.RepeatWrapping;
    wall.repeat.set(total, 1);
    return { floor, wall, iron: ironTexture() };
  }, [total]);
  const lamps = useRef<(THREE.PointLight | null)[]>([]);
  const glows = useRef<(THREE.MeshBasicMaterial | null)[]>([]);
  const pools = useRef<(THREE.MeshBasicMaterial | null)[]>([]);
  const rogue = useRef<THREE.Group>(null);
  const cloak = useRef<THREE.MeshStandardMaterial>(null);
  const shown = useRef({ x: cellX(0), seen: false });
  const sparks = useMemo(() => new SparkPool(40), []);
  const jolt = useJolt();

  useFrame((state, delta) => {
    const s = live.current;
    params.lamps.forEach((lamp, i) => {
      const lit = lamp ? shadowLit(lamp, s.t) : false;
      const light = lamps.current[i];
      if (light) light.intensity = THREE.MathUtils.damp(light.intensity, lit ? 3.2 : 0, 20, delta);
      const glow = glows.current[i];
      if (glow) glow.color.set(lit ? '#ffd27a' : '#4a3a20');
      const pool = pools.current[i];
      if (pool) pool.opacity = THREE.MathUtils.damp(pool.opacity, lit ? 0.55 : 0, 20, delta);
    });
    // The rogue steps from flagstone to flagstone.
    const target = cellX(Math.min(s.pos, total - 1));
    shown.current.x = THREE.MathUtils.damp(shown.current.x, target, 1000 / WALK_MS, delta);
    if (rogue.current) {
      rogue.current.position.x = shown.current.x;
      rogue.current.position.y = Math.abs(Math.sin((shown.current.x - target) * 12)) * 0.03;
    }
    if (outcome === 'broke' && !shown.current.seen) {
      shown.current.seen = true;
      jolt.kick(0.04);
      sparks.burst(new THREE.Vector3(shown.current.x, 0.4, 0), '#ff4a3a', 18, 0.9);
    }
    if (cloak.current) cloak.current.emissiveIntensity = THREE.MathUtils.damp(cloak.current.emissiveIntensity, shown.current.seen ? 1.4 : 0, 8, delta);
    state.camera.position.x = THREE.MathUtils.damp(state.camera.position.x, shown.current.x * 0.6, 3, delta);
    state.camera.lookAt(shown.current.x * 0.6, 0, 0);
  });

  return (
    <>
      <CraftLights candle={[-2.5, 1.5, 1.2]} spot={[0, 3, 2]} spotIntensity={3} />
      <group ref={jolt.group}>
        {Array.from({ length: total }, (_, i) => (
          <mesh key={i} position={[cellX(i), 0, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[CELL * 0.97, CELL * 1.6]} />
            <meshStandardMaterial map={textures.floor} color={i === 0 || i === total - 1 ? '#3a3632' : '#6a645c'} roughness={0.95} />
          </mesh>
        ))}
        {/* the corridor's far wall */}
        <mesh position={[0, 0.35, -0.38]}>
          <boxGeometry args={[total * CELL + 0.4, 0.7, 0.1]} />
          <meshStandardMaterial map={textures.wall} color="#5a554e" roughness={0.95} />
        </mesh>
        {params.lamps.map((lamp, i) =>
          lamp ? (
            <group key={i} position={[cellX(i + 1), 0, 0]}>
              <mesh position={[0, 0.62, -0.3]} rotation={[Math.PI / 2, 0, 0]}>
                <cylinderGeometry args={[0.012, 0.012, 0.2, 6]} />
                <meshStandardMaterial map={textures.iron} color="#7a7a82" metalness={0.8} roughness={0.4} />
              </mesh>
              <mesh position={[0, 0.58, -0.2]}>
                <boxGeometry args={[0.07, 0.09, 0.07]} />
                <meshBasicMaterial
                  ref={(m) => {
                    glows.current[i] = m;
                  }}
                  color="#4a3a20"
                  toneMapped={false}
                />
              </mesh>
              <pointLight
                ref={(l) => {
                  lamps.current[i] = l;
                }}
                position={[0, 0.5, -0.1]}
                color="#ffcf7a"
                distance={0.9}
                decay={1.5}
                intensity={0}
              />
              <mesh position={[0, 0.005, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                <circleGeometry args={[CELL * 0.62, 24]} />
                <meshBasicMaterial
                  ref={(m) => {
                    pools.current[i] = m;
                  }}
                  color="#ffd27a"
                  transparent
                  opacity={0}
                  depthWrite={false}
                  blending={THREE.AdditiveBlending}
                  toneMapped={false}
                />
              </mesh>
            </group>
          ) : null,
        )}
        {/* the rogue: a hooded figure */}
        <group ref={rogue} position={[cellX(0), 0, 0.05]}>
          <mesh position={[0, 0.16, 0]}>
            <coneGeometry args={[0.1, 0.32, 10]} />
            <meshStandardMaterial ref={cloak} color="#3a3450" emissive="#ff2a1a" emissiveIntensity={0} roughness={0.8} />
          </mesh>
          <mesh position={[0, 0.34, 0]}>
            <sphereGeometry args={[0.06, 12, 8]} />
            <meshStandardMaterial color="#2a2638" roughness={0.8} />
          </mesh>
        </group>
        <SparkField pool={sparks} max={40} />
      </group>
      {outcome === 'open' && <Halo position={[cellX(total - 1), 0.3, 0]} color="#7fd0ff" scale={0.8} opacity={0.3} />}
    </>
  );
};

export default ShadowScene;
