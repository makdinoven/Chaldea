import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { StarsParams } from '../../../../api/dungeons';
import { starsLayout } from '../intel';
import { CraftLights, Halo, SparkField, SparkPool, pointer } from './craftKit';
import { brassTexture, glowTexture } from './craftTextures';

/*
  Reading in 3D: a brass astrolabe against the night — geared rings, each with
  stars set in it and a gold mark. The rings turn smoothly to where they stand;
  brought home, the constellation lights up and is joined by threads of light.
*/

export const STARS_CAMERA = { position: [0, -0.05, 4.1] as [number, number, number], fov: 36 };

interface StarsSceneProps {
  params: StarsParams;
  offsets: number[];
  playing: boolean;
  whole: boolean;
  onTurn: (ring: number) => void;
}

const StarsScene = ({ params, offsets, playing, whole, onTurn }: StarsSceneProps) => {
  const layout = useMemo(() => starsLayout(params), [params]);
  const textures = useMemo(() => ({ brass: brassTexture(), glow: glowTexture() }), []);
  const radius = (r: number) => 0.42 + r * (0.85 / params.rings);
  const rings = useRef<(THREE.Group | null)[]>([]);
  const angles = useRef(offsets.map(() => 0));
  const threads = useRef<THREE.LineBasicMaterial>(null);
  const sparks = useMemo(() => new SparkPool(60), []);
  const lit = useRef(false);

  // The whole constellation, as points in the chart when every ring is home.
  const points = useMemo(
    () => layout.flatMap((stars, r) => stars.map((s) => new THREE.Vector3(Math.sin(s.angle) * radius(r), Math.cos(s.angle) * radius(r), 0.02))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [layout],
  );
  const threadGeometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points]);

  useFrame((_, delta) => {
    offsets.forEach((o, r) => {
      const target = -(o / params.steps) * Math.PI * 2;
      // the short way round towards the target angle
      const cur = angles.current[r];
      const diff = Math.atan2(Math.sin(target - cur), Math.cos(target - cur));
      angles.current[r] = cur + diff * Math.min(1, delta * 10);
      const g = rings.current[r];
      if (g) g.rotation.z = angles.current[r];
    });
    if (whole && !lit.current) {
      lit.current = true;
      points.forEach((p) => sparks.burst(p.clone(), '#e8d4ff', 3, 0.3, { up: 0, life: 1.2 }));
    }
    if (threads.current) threads.current.opacity = THREE.MathUtils.damp(threads.current.opacity, whole ? 0.8 : 0, 4, delta);
  });

  return (
    <>
      <CraftLights candle={[-1.8, 1.0, 1.6]} spotIntensity={6} />
      <color attach="background" args={['#06050c']} />
      <Halo position={[0, 0, -0.2]} color="#6a5aff" scale={3} opacity={0.12} />
      {/* the gold mark every ring is brought to */}
      <mesh position={[0, radius(params.rings - 1) + 0.16, 0.05]} rotation={[0, 0, Math.PI]}>
        <coneGeometry args={[0.05, 0.12, 3]} />
        <meshStandardMaterial color="#e2c26a" emissive="#d6a84a" emissiveIntensity={0.8} metalness={0.7} roughness={0.3} />
      </mesh>
      {layout.map((stars, r) => (
        <group
          key={r}
          ref={(el) => {
            rings.current[r] = el;
          }}
          onClick={(e) => {
            e.stopPropagation();
            onTurn(r);
          }}
          onPointerOver={(e) => {
            e.stopPropagation();
            if (playing) pointer.onPointerOver();
          }}
          onPointerOut={pointer.onPointerOut}
        >
          <mesh>
            <ringGeometry args={[radius(r) - 0.06, radius(r) + 0.06, 64]} />
            <meshStandardMaterial map={textures.brass} color={whole ? '#f0d890' : '#a88a52'} metalness={0.75} roughness={0.35} side={THREE.DoubleSide} />
          </mesh>
          {/* the ring's own mark */}
          <mesh position={[0, radius(r), 0.02]}>
            <circleGeometry args={[0.03, 12]} />
            <meshBasicMaterial color="#ffd36a" toneMapped={false} />
          </mesh>
          {stars.map((s, k) => (
            <sprite key={k} position={[Math.sin(s.angle) * radius(r), Math.cos(s.angle) * radius(r), 0.03]} scale={0.07 * s.size + 0.03}>
              <spriteMaterial map={textures.glow} color={whole ? '#ffffff' : '#c8c0ff'} transparent depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
            </sprite>
          ))}
        </group>
      ))}
      <lineLoop geometry={threadGeometry}>
        <lineBasicMaterial ref={threads} color="#e8d4ff" transparent opacity={0} />
      </lineLoop>
      <SparkField pool={sparks} max={60} gravity={-0.4} />
    </>
  );
};

export default StarsScene;
