import { useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { ShieldParams } from '../../../../api/dungeons';
import { createWallBlockTexture, createFlagstoneTexture } from '../../../DungeonBoard3D/stoneTextures';
import type { ShieldFlash, ShieldPhase } from '../useShield';
import { CraftLights, Halo, SparkField, SparkPool, useJolt } from './craftKit';
import { doorPlanksTexture, ironTexture } from './craftTextures';

/*
  The party shield in 3D: a dark passage, and the warrior's round shield held
  up before us. Arrows come out of the dark from the left, from above, from
  the right; turn the shield to meet each. One turned aside rings off the iron
  boss in sparks and spins away; one that gets through flashes red and jolts.
*/

export const SHIELD_CAMERA = { position: [0, 0.05, 3.2] as [number, number, number], fov: 40 };

/** Where the shield stands for each side: left, above, right. */
const GUARD: [number, number, number][] = [
  [-0.55, -0.08, 1.0],
  [0, 0.38, 1.0],
  [0.55, -0.08, 1.0],
];
/** The shield faces a little towards where it guards. */
const GUARD_TILT: [number, number][] = [
  [0, 0.45],
  [0.45, 0],
  [0, -0.45],
];
/** Where an arrow comes from on each side. */
const FROM: [number, number, number][] = [
  [-2.6, 0.25, -2.2],
  [0.1, 2.1, -2.2],
  [2.6, 0.25, -2.2],
];
const SHIELD_R = 0.3;
const BOUNCE_MS = 700;
const HIT_MS = 400;
const ARROWS = 4;

interface ShieldSceneProps {
  params: ShieldParams;
  phase: ShieldPhase;
  side: number;
  flash: ShieldFlash | null;
  startedAt: MutableRefObject<number>;
}

/** An arrow: ash shaft, iron head, grey fletching; points along +z. */
const Arrow = ({ shaft, iron }: { shaft: THREE.Material; iron: THREE.Material }) => (
  <>
    <mesh rotation={[Math.PI / 2, 0, 0]} material={shaft}>
      <cylinderGeometry args={[0.012, 0.012, 0.8, 6]} />
    </mesh>
    <mesh position={[0, 0, 0.44]} rotation={[Math.PI / 2, 0, 0]} material={iron}>
      <coneGeometry args={[0.03, 0.1, 6]} />
    </mesh>
    {[0, Math.PI / 2].map((a) => (
      <mesh key={a} position={[0, 0, -0.34]} rotation={[0, 0, a]}>
        <planeGeometry args={[0.07, 0.14]} />
        <meshStandardMaterial color="#c9c2b4" side={THREE.DoubleSide} roughness={0.9} />
      </mesh>
    ))}
  </>
);

const ShieldScene = ({ params, phase, side, flash, startedAt }: ShieldSceneProps) => {
  const textures = useMemo(() => {
    const wall = createWallBlockTexture();
    wall.wrapS = wall.wrapT = THREE.RepeatWrapping;
    wall.repeat.set(4, 2);
    const floor = createFlagstoneTexture();
    floor.wrapS = floor.wrapT = THREE.RepeatWrapping;
    floor.repeat.set(3, 6);
    return { wall, floor, planks: doorPlanksTexture(), iron: ironTexture() };
  }, []);
  const materials = useMemo(
    () => ({
      wood: new THREE.MeshStandardMaterial({ map: textures.planks, color: '#a07a56', roughness: 0.8 }),
      iron: new THREE.MeshStandardMaterial({ map: textures.iron, color: '#9a9aa2', metalness: 0.85, roughness: 0.38 }),
      shaft: new THREE.MeshStandardMaterial({ color: '#6e5536', roughness: 0.85 }),
      head: new THREE.MeshStandardMaterial({ color: '#c8ccd2', metalness: 0.9, roughness: 0.3 }),
    }),
    [textures],
  );
  const shield = useRef<THREE.Group>(null);
  const arrows = useRef<(THREE.Group | null)[]>([]);
  const redFlash = useRef<THREE.MeshBasicMaterial>(null);
  const sparks = useMemo(() => new SparkPool(80), []);
  const jolt = useJolt(380);
  const seen = useRef<ShieldFlash | null>(null);
  /** Arrows that have landed: how they went on (bounced off, or flew past). */
  const after = useRef(new Map<number, { at: number; good: boolean; side: number }>());

  useFrame((state, delta) => {
    const now = performance.now();
    const t = now - startedAt.current;

    // The shield swings to its guard.
    if (shield.current) {
      const [x, y, z] = GUARD[side];
      const [tx, ty] = GUARD_TILT[side];
      shield.current.position.x = THREE.MathUtils.damp(shield.current.position.x, x, 18, delta);
      shield.current.position.y = THREE.MathUtils.damp(shield.current.position.y, y, 18, delta);
      shield.current.position.z = z;
      shield.current.rotation.x = THREE.MathUtils.damp(shield.current.rotation.x, tx, 18, delta);
      shield.current.rotation.y = THREE.MathUtils.damp(shield.current.rotation.y, ty, 18, delta);
    }

    // A blow just landed: sparks off the boss, or a red flash and a jolt.
    if (flash && flash !== seen.current) {
      seen.current = flash;
      const blow = params.blows.findIndex((b, i) => b.side === flash.side && !after.current.has(i) && b.at_ms <= t + 50);
      if (blow >= 0) after.current.set(blow, { at: now, good: flash.good, side: flash.side });
      const [x, y, z] = GUARD[flash.side];
      if (flash.good) sparks.burst(new THREE.Vector3(x, y, z + 0.05), '#ffc46a', 18, 1.3, { size: 0.9 });
      else jolt.kick(0.06);
    }
    if (redFlash.current) {
      const since = flash && !flash.good ? now - flash.at : Infinity;
      redFlash.current.opacity = since < HIT_MS ? 0.28 * (1 - since / HIT_MS) : 0;
    }

    // Arrows in flight (shown warn_ms before they land), and after.
    const flying = params.blows
      .map((b, i) => ({ b, i }))
      .filter(({ b, i }) => phase !== 'ready' && ((b.at_ms - params.warn_ms <= t && t < b.at_ms) || after.current.has(i)))
      .slice(-ARROWS);
    arrows.current.forEach((arrow, slot) => {
      if (!arrow) return;
      const entry = flying[slot];
      if (!entry) {
        arrow.visible = false;
        return;
      }
      const { b, i } = entry;
      const from = new THREE.Vector3(...FROM[b.side]);
      const to = new THREE.Vector3(...GUARD[b.side]);
      const landed = after.current.get(i);
      if (!landed) {
        const k = 1 - (b.at_ms - t) / params.warn_ms;
        arrow.position.lerpVectors(from, to, k);
        arrow.lookAt(to.clone().add(to.clone().sub(from)));
        arrow.visible = true;
        return;
      }
      const since = now - landed.at;
      if (landed.good) {
        // Turned aside: it spins off up and away.
        const k = since / BOUNCE_MS;
        arrow.visible = k < 1;
        arrow.position.set(to.x + (b.side === 2 ? 1 : b.side === 0 ? -1 : 0.4) * k * 1.2, to.y + k * 1.1 - k * k * 1.6, to.z - k * 0.6);
        arrow.rotation.x += delta * 14;
        arrow.rotation.z += delta * 9;
      } else {
        // Through: it flies on past us.
        const k = since / HIT_MS;
        arrow.visible = k < 1;
        const dir = to.clone().sub(from).normalize();
        arrow.position.copy(to).addScaledVector(dir, k * 2);
      }
    });

    state.camera.position.x = Math.sin(now * 0.0005) * 0.04;
    state.camera.lookAt(0, 0.1, 0);
  });

  return (
    <>
      <CraftLights candle={[-1.6, 1.0, 1.8]} spot={[0, 1.8, 3]} spotIntensity={10} />
      {/* The passage running away into the dark */}
      <mesh position={[0, 0.3, -3]}>
        <planeGeometry args={[6, 4]} />
        <meshStandardMaterial map={textures.wall} color="#4a4640" roughness={1} />
      </mesh>
      {[-1.9, 1.9].map((x) => (
        <mesh key={x} position={[x, 0.3, -0.6]} rotation={[0, x < 0 ? Math.PI / 2 : -Math.PI / 2, 0]}>
          <planeGeometry args={[5, 4]} />
          <meshStandardMaterial map={textures.wall} color="#55514a" roughness={1} />
        </mesh>
      ))}
      <mesh position={[0, -0.9, -0.6]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[4, 6]} />
        <meshStandardMaterial map={textures.floor} color="#4a4640" roughness={1} />
      </mesh>
      <Halo position={[0, 0.2, -2.9]} color="#6a7cff" scale={1.4} opacity={0.08} />

      <group ref={jolt.group}>
        {/* The shield: planks, an iron rim and boss */}
        <group ref={shield} position={GUARD[side]}>
          <mesh rotation={[Math.PI / 2, 0, 0]} material={materials.wood}>
            <cylinderGeometry args={[SHIELD_R, SHIELD_R, 0.04, 40]} />
          </mesh>
          <mesh material={materials.iron}>
            <torusGeometry args={[SHIELD_R, 0.022, 10, 48]} />
          </mesh>
          <mesh position={[0, 0, 0.03]} material={materials.iron}>
            <sphereGeometry args={[0.085, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
          </mesh>
          {[-1, 1].map((k) => (
            <mesh key={k} position={[0, k * SHIELD_R * 0.45, 0.022]} material={materials.iron}>
              <boxGeometry args={[SHIELD_R * 1.7, 0.03, 0.01]} />
            </mesh>
          ))}
        </group>
        {Array.from({ length: ARROWS }, (_, i) => (
          <group
            key={i}
            ref={(el) => {
              arrows.current[i] = el;
            }}
            visible={false}
            scale={0.65}
          >
            <Arrow shaft={materials.shaft} iron={materials.head} />
          </group>
        ))}
        <SparkField pool={sparks} max={80} />
      </group>
      {/* A red veil when an arrow gets through */}
      <mesh position={[0, 0, 2.6]} raycast={() => null}>
        <planeGeometry args={[3, 2]} />
        <meshBasicMaterial ref={redFlash} color="#ff2a1a" transparent opacity={0} depthWrite={false} toneMapped={false} />
      </mesh>
    </>
  );
};

export default ShieldScene;
