import { useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { GateParams } from '../../../../api/dungeons';
import { createWallBlockTexture, createFlagstoneTexture } from '../../../DungeonBoard3D/stoneTextures';
import type { GateOutcome, GateState } from '../warrior';
import { CraftLights, Halo, SparkField, SparkPool, useJolt } from './craftKit';
import { doorPlanksTexture, ironTexture, stoneTexture } from './craftTextures';

/*
  Holding up a gate in 3D: a doorway in old stone, and in it a portcullis (or
  a slab) on two chains. It rises while held and sinks when let go; a surge
  wrenches it down with a fall of grit. Gold notches on the jambs mark the
  band to keep its foot in. Let it reach the floor and it slams in dust;
  held long enough, a timber prop is wedged under it.
*/

export const GATE_CAMERA = { position: [0, 0.1, 3.3] as [number, number, number], fov: 34 };

const FLOOR_Y = -0.78;
const OPENING_W = 1.2;
const OPENING_H = 1.45;
const GATE_H = 1.5;
const BARS = 7;
const PROP_MS = 600;
const SLAM_MS = 260;

interface GateSceneProps {
  params: GateParams;
  live: MutableRefObject<GateState>;
  pressed: boolean;
  outcome: GateOutcome | null;
}

const GateScene = ({ params, live, pressed, outcome }: GateSceneProps) => {
  const slab = params.look === 'slab';
  const [lo, hi] = params.zone;
  const textures = useMemo(() => {
    const wall = createWallBlockTexture();
    wall.wrapS = wall.wrapT = THREE.RepeatWrapping;
    wall.repeat.set(10, 6);
    const floor = createFlagstoneTexture();
    floor.wrapS = floor.wrapT = THREE.RepeatWrapping;
    floor.repeat.set(4, 2);
    return { wall, floor, iron: ironTexture(), stone: stoneTexture(), planks: doorPlanksTexture() };
  }, []);
  const materials = useMemo(
    () => ({
      iron: new THREE.MeshStandardMaterial({ map: textures.iron, color: '#8a8a92', metalness: 0.8, roughness: 0.45 }),
      chain: new THREE.MeshStandardMaterial({ map: textures.iron, color: '#7a7a82', metalness: 0.85, roughness: 0.4, emissive: '#ff5a2a', emissiveIntensity: 0 }),
      slab: new THREE.MeshStandardMaterial({ map: textures.stone, color: '#8a857c', roughness: 0.9 }),
      jamb: new THREE.MeshStandardMaterial({ map: textures.stone, color: '#7d786f', roughness: 0.9 }),
      wall: new THREE.MeshStandardMaterial({ map: textures.wall, color: '#5e5a54', roughness: 0.95 }),
      notch: new THREE.MeshBasicMaterial({ color: '#ffcf5a', transparent: true, opacity: 0.5, toneMapped: false }),
      prop: new THREE.MeshStandardMaterial({ map: textures.planks, color: '#a0794e', roughness: 0.85 }),
    }),
    [textures],
  );
  const gate = useRef<THREE.Group>(null);
  const chains = useRef<(THREE.Mesh | null)[]>([]);
  const prop = useRef<THREE.Group>(null);
  const sparks = useMemo(() => new SparkPool(100), []);
  const jolt = useJolt(360);
  const shown = useRef({ y: 0, surging: false, endAt: -Infinity });

  const footY = (level: number) => FLOOR_Y + level * OPENING_H;

  useFrame((state, delta) => {
    const now = performance.now();
    const g = live.current;
    if (outcome && shown.current.endAt === -Infinity) {
      shown.current.endAt = now;
      if (outcome === 'broke' || outcome === 'time') {
        jolt.kick(0.07);
        sparks.burst(new THREE.Vector3(0, FLOOR_Y + 0.05, 0.2), '#8d8270', 50, 1.2, { size: 1.4, life: 1.4, spread: 2.5, up: 0.3 });
      }
    }
    const sinceEnd = now - shown.current.endAt;
    // The gate's foot: as played; a slam drops it to the floor.
    let level = g.level;
    if (outcome && outcome !== 'open') level = Math.max(0, level * (1 - Math.min(1, sinceEnd / SLAM_MS)));
    const y = footY(level);
    shown.current.y = y;
    if (gate.current) gate.current.position.y = y + GATE_H / 2;

    // A surge: the chains glow hot, grit falls, the gate jolts.
    const surging = !outcome && params.surges.some((s) => s.at_ms <= g.t && g.t < s.at_ms + s.dur_ms);
    if (surging && !shown.current.surging) {
      jolt.kick(0.025);
      sparks.burst(new THREE.Vector3(0, OPENING_H + FLOOR_Y - 0.05, 0.15), '#9a8c78', 14, 0.4, { size: 0.8, life: 1.2, up: 0 });
    }
    shown.current.surging = surging;
    materials.chain.emissiveIntensity = THREE.MathUtils.damp(materials.chain.emissiveIntensity, surging ? 0.8 : pressed ? 0.15 : 0, 10, delta);

    // The chains run from the gate's top up into the wall.
    chains.current.forEach((chain) => {
      if (!chain) return;
      const top = FLOOR_Y + OPENING_H + 0.9;
      const from = y + GATE_H;
      const len = Math.max(0.01, top - from);
      chain.scale.y = len;
      chain.position.y = from + len / 2;
    });

    // The gold notches brighten while the foot is in the band.
    const inside = level >= lo && level <= hi;
    materials.notch.opacity = THREE.MathUtils.damp(materials.notch.opacity, inside ? 1 : 0.45, 10, delta);

    // Held long enough: a timber prop is wedged under the foot.
    if (prop.current) {
      const k = outcome === 'open' ? Math.min(1, sinceEnd / PROP_MS) : 0;
      prop.current.visible = k > 0;
      const height = Math.max(0.05, y - FLOOR_Y);
      prop.current.scale.y = height;
      prop.current.position.set(THREE.MathUtils.lerp(-1.2, -0.3, k), FLOOR_Y + height / 2, 0.08);
      prop.current.rotation.z = THREE.MathUtils.lerp(1.2, 0.08, k);
    }

    state.camera.position.x = Math.sin(now * 0.0004) * 0.05;
    state.camera.lookAt(0, -0.05, 0);
  });

  const lintelY = FLOOR_Y + OPENING_H;
  const notchH = (hi - lo) * OPENING_H;
  return (
    <>
      <CraftLights candle={[-1.7, 1.0, 1.6]} spot={[0, 1.8, 2.6]} />
      {/* The dark beyond the doorway */}
      <mesh position={[0, FLOOR_Y + OPENING_H / 2, -0.4]}>
        <planeGeometry args={[OPENING_W, OPENING_H]} />
        <meshStandardMaterial color="#060505" roughness={1} />
      </mesh>
      <Halo position={[0, FLOOR_Y + 0.6, -0.38]} color="#6a7cff" scale={1.1} opacity={0.08} />
      <mesh position={[0, FLOOR_Y, 0.4]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[6, 2.2]} />
        <meshStandardMaterial map={textures.floor} color="#4c4842" roughness={1} />
      </mesh>

      <group ref={jolt.group}>
        {/* The gate, behind the wall's face: it slides up into the stone */}
        <group ref={gate} position={[0, FLOOR_Y + GATE_H / 2, -0.12]}>
          {slab ? (
            <mesh material={materials.slab}>
              <boxGeometry args={[OPENING_W + 0.1, GATE_H, 0.18]} />
            </mesh>
          ) : (
            <>
              {Array.from({ length: BARS }, (_, i) => {
                const x = -OPENING_W / 2 + 0.08 + (i * (OPENING_W - 0.16)) / (BARS - 1);
                return (
                  <group key={i} position={[x, 0, 0]}>
                    <mesh material={materials.iron}>
                      <cylinderGeometry args={[0.022, 0.022, GATE_H, 8]} />
                    </mesh>
                    <mesh position={[0, -GATE_H / 2 - 0.05, 0]} rotation={[Math.PI, 0, 0]} material={materials.iron}>
                      <coneGeometry args={[0.03, 0.1, 8]} />
                    </mesh>
                  </group>
                );
              })}
              {[-0.45, 0.05, 0.55].map((yy) => (
                <mesh key={yy} position={[0, yy, 0.02]} material={materials.iron}>
                  <boxGeometry args={[OPENING_W + 0.04, 0.05, 0.04]} />
                </mesh>
              ))}
            </>
          )}
        </group>
        {[-OPENING_W / 2 + 0.12, OPENING_W / 2 - 0.12].map((x, i) => (
          <mesh
            key={x}
            ref={(el) => {
              chains.current[i] = el;
            }}
            position={[x, 0, -0.1]}
            material={materials.chain}
          >
            <cylinderGeometry args={[0.014, 0.014, 1, 6]} />
          </mesh>
        ))}

        {/* The wall's face: above the lintel it hides the raised gate */}
        <mesh position={[0, lintelY + 1.3, 0]} material={materials.wall}>
          <boxGeometry args={[6, 2.6, 0.12]} />
        </mesh>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * (OPENING_W / 2 + 1.6), FLOOR_Y + OPENING_H / 2, 0]} material={materials.wall}>
            <boxGeometry args={[3.2, OPENING_H, 0.12]} />
          </mesh>
        ))}
        {/* Jambs and lintel */}
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * (OPENING_W / 2 + 0.09), FLOOR_Y + OPENING_H / 2, 0.06]} material={materials.jamb}>
            <boxGeometry args={[0.18, OPENING_H, 0.2]} />
          </mesh>
        ))}
        <mesh position={[0, lintelY + 0.1, 0.06]} material={materials.jamb}>
          <boxGeometry args={[OPENING_W + 0.36, 0.2, 0.22]} />
        </mesh>
        {/* The gold notches: the band for the gate's foot */}
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * (OPENING_W / 2 + 0.005), footY((lo + hi) / 2), 0.165]} material={materials.notch}>
            <planeGeometry args={[0.05, notchH]} />
          </mesh>
        ))}

        {/* The prop wedged under the gate when it holds */}
        <group ref={prop} visible={false}>
          <mesh material={materials.prop}>
            <boxGeometry args={[0.09, 1, 0.09]} />
          </mesh>
        </group>
        <SparkField pool={sparks} max={100} gravity={-1.6} dull />
      </group>
      <Halo position={[-2.1, 1.2, 0.4]} color="#ff9a40" />
    </>
  );
};

export default GateScene;
