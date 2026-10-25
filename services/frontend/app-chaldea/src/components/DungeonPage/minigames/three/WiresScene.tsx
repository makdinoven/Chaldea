import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { WiresParams } from '../../../../api/dungeons';
import type { RodState } from '../WiresGame';
import { CraftLights, SparkField, SparkPool, pointer, useJolt } from './craftKit';
import { doorPlanksTexture, ironTexture, markTexture } from './craftTextures';

/*
  Disarming in 3D: the trap's mechanism opened up — an iron frame with a row of
  rods running from a spring bar to the trigger. A slack rod cut springs apart
  and a figure glows at its foot (how many taut rods beside it); a taut one cut
  throws red sparks and the mechanism jolts.
*/

export const WIRES_CAMERA = { position: [0, 0.2, 3.2] as [number, number, number], fov: 34 };

const SPAN = 2.2;
const ROD_H = 1.1;
const GAP_OPEN = 0.25;

interface WiresSceneProps {
  params: WiresParams;
  rods: Map<number, RodState>;
  over: boolean;
  onCut: (index: number) => void;
}

const WiresScene = ({ params, rods, over, onCut }: WiresSceneProps) => {
  const [hovered, setHovered] = useState<number | null>(null);
  const textures = useMemo(() => ({ iron: ironTexture(), planks: doorPlanksTexture() }), []);
  const x = (i: number) => (params.wires === 1 ? 0 : -SPAN / 2 + (SPAN * i) / (params.wires - 1));
  const tops = useRef<(THREE.Mesh | null)[]>([]);
  const bottoms = useRef<(THREE.Mesh | null)[]>([]);
  const cutAt = useRef(new Map<number, number>());
  const sparks = useMemo(() => new SparkPool(60), []);
  const jolt = useJolt();
  const rodMats = useMemo(
    () =>
      Array.from(
        { length: params.wires },
        () => new THREE.MeshStandardMaterial({ map: textures.iron, color: '#b0a38a', metalness: 0.8, roughness: 0.35, emissive: '#ffcf5a', emissiveIntensity: 0 }),
      ),
    [params.wires, textures],
  );

  useFrame((state, delta) => {
    const now = performance.now();
    rods.forEach((r, i) => {
      if (!cutAt.current.has(i)) {
        cutAt.current.set(i, now);
        if (r && 'taut' in r) {
          jolt.kick(0.05);
          sparks.burst(new THREE.Vector3(x(i), 0, 0.1), '#ff4a2a', 20, 1.1);
        } else if (!params.shown.some(([s]) => s === i)) {
          sparks.burst(new THREE.Vector3(x(i), 0, 0.1), '#ffd27a', 8, 0.5);
        }
      }
    });
    for (let i = 0; i < params.wires; i++) {
      const r = rods.get(i);
      const k = r ? Math.min(1, (now - (cutAt.current.get(i) ?? now)) / 250) : 0;
      const gap = r ? GAP_OPEN * k : 0;
      const top = tops.current[i];
      const bottom = bottoms.current[i];
      if (top) top.position.y = ROD_H / 4 + gap / 2;
      if (bottom) bottom.position.y = -ROD_H / 4 - gap / 2;
      const m = rodMats[i];
      m.emissive.set(r && 'taut' in r ? '#ff2a1a' : '#ffcf5a');
      m.emissiveIntensity = THREE.MathUtils.damp(m.emissiveIntensity, r && 'taut' in r ? 1 : hovered === i && !over && !r ? 0.5 : 0, 10, delta);
    }
    state.camera.lookAt(0, 0, 0);
  });

  return (
    <>
      <CraftLights candle={[-1.8, 1.0, 1.6]} />
      <mesh position={[0, 0, -0.35]}>
        <planeGeometry args={[6, 4]} />
        <meshStandardMaterial map={textures.planks} color="#5a4a3c" roughness={0.9} />
      </mesh>
      <group ref={jolt.group}>
        {/* the frame: spring bar above, trigger bar below */}
        {[ROD_H / 2 + 0.06, -ROD_H / 2 - 0.06].map((y) => (
          <mesh key={y} position={[0, y, 0]}>
            <boxGeometry args={[SPAN + 0.5, 0.12, 0.16]} />
            <meshStandardMaterial map={textures.iron} color="#5a5a62" metalness={0.7} roughness={0.5} />
          </mesh>
        ))}
        {Array.from({ length: params.wires }, (_, i) => {
          const r = rods.get(i);
          return (
            <group
              key={i}
              position={[x(i), 0, 0]}
              onClick={(e) => {
                e.stopPropagation();
                if (!over && !r) onCut(i);
              }}
              onPointerOver={(e) => {
                e.stopPropagation();
                setHovered(i);
                if (!over && !r) pointer.onPointerOver();
              }}
              onPointerOut={() => {
                setHovered((h) => (h === i ? null : h));
                pointer.onPointerOut();
              }}
            >
              {[0, 1].map((half) => (
                <mesh
                  key={half}
                  ref={(el) => {
                    (half === 0 ? tops : bottoms).current[i] = el;
                  }}
                  position={[0, half === 0 ? ROD_H / 4 : -ROD_H / 4, 0]}
                  material={rodMats[i]}
                >
                  <cylinderGeometry args={[0.025, 0.025, ROD_H / 2, 10]} />
                </mesh>
              ))}
              {/* a fat invisible reach for a finger */}
              <mesh>
                <boxGeometry args={[0.18, ROD_H, 0.2]} />
                <meshBasicMaterial transparent opacity={0} depthWrite={false} />
              </mesh>
              {r && 'cut' in r && (
                <mesh position={[0, -ROD_H / 2 - 0.22, 0.09]}>
                  <planeGeometry args={[0.2, 0.2]} />
                  <meshBasicMaterial
                    map={markTexture(String(r.near))}
                    color={r.near ? '#ffcf5a' : '#9adfa0'}
                    transparent
                    blending={THREE.AdditiveBlending}
                    depthWrite={false}
                    toneMapped={false}
                  />
                </mesh>
              )}
            </group>
          );
        })}
        <SparkField pool={sparks} max={60} />
      </group>
    </>
  );
};

export default WiresScene;
