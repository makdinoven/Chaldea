import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Sparkles } from '@react-three/drei';
import * as THREE from 'three';
import { noRaycast, useDisposable, useMetal } from './bookParts';

/*
  The light beside each book, in the manner of its class: a soldier's tallow
  candles on an iron pricket, a rogue's stub burning in the neck of a bottle,
  a mage's candles hanging in the air with cold flames. Each casts its own
  colour of light onto its book.
*/

interface FlameProps {
  flame: THREE.Texture;
  glow: THREE.Texture;
  position: [number, number, number];
  colour: string;
  core: string;
  /** Larger flames for thick candles. */
  size?: number;
  /** How restless the flame is: 1 steady, 2 guttering. */
  unrest?: number;
  seed: number;
}

/** A tongue of flame with a bright core and a soft halo, flickering. */
const Flame = ({ flame, glow, position, colour, core, size = 1, unrest = 1, seed }: FlameProps) => {
  const tongue = useRef<THREE.Sprite>(null);
  const material = useRef<THREE.SpriteMaterial>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime * 9 * unrest + seed * 7;
    const flick = 1 + (Math.sin(t) * 0.08 + Math.sin(t * 2.3) * 0.05) * unrest;
    tongue.current?.scale.set(0.34 * size * (2 - flick), 0.66 * size * flick, 1);
    if (material.current) material.current.opacity = 0.85 + Math.sin(t * 1.7) * 0.1;
  });
  return (
    <group position={position}>
      <sprite ref={tongue} raycast={noRaycast} scale={[0.34 * size, 0.66 * size, 1]}>
        <spriteMaterial
          ref={material}
          map={flame}
          color={colour}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </sprite>
      <sprite raycast={noRaycast} position={[0, -0.04 * size, 0.01]} scale={[0.11 * size, 0.22 * size, 1]}>
        <spriteMaterial map={flame} color={core} transparent depthWrite={false} toneMapped={false} />
      </sprite>
      <sprite raycast={noRaycast} position={[0, -0.05, 0]} scale={[0.8 * size, 0.8 * size, 1]}>
        <spriteMaterial
          map={glow}
          color={colour}
          transparent
          opacity={0.4}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </sprite>
    </group>
  );
};

interface CandleLightProps {
  colour: string;
  glow: THREE.Texture;
  /** Base strength of the light it throws. */
  intensity: number;
  lightPosition: [number, number, number];
  unrest?: number;
  seed: number;
}

/** The pool of light a candle throws on the table, and the light itself, both flickering. */
const CandleLight = ({ colour, glow, intensity, lightPosition, unrest = 1, seed }: CandleLightProps) => {
  const light = useRef<THREE.PointLight>(null);
  const pool = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime * 7 * unrest + seed * 11;
    const flick = 0.85 + (Math.sin(t) * 0.07 + Math.sin(t * 2.3) * 0.05 + Math.sin(t * 5.1) * 0.03) * unrest;
    if (light.current) light.current.intensity = intensity * flick;
    if (pool.current) pool.current.opacity = 0.38 * flick;
  });
  return (
    <>
      <mesh raycast={noRaycast} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]}>
        <planeGeometry args={[3.6, 3.6]} />
        <meshBasicMaterial
          ref={pool}
          map={glow}
          color={colour}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
      <pointLight ref={light} position={lightPosition} color={colour} distance={11} decay={1.5} />
    </>
  );
};

interface CandleProps {
  position: [number, number, number];
  flame: THREE.Texture;
  glow: THREE.Texture;
  seed: number;
}

/* ===================== Warrior: tallow on an iron pricket ===================== */

const TALLOW = '#cdb98a';

/** Overall size of the pricket and its candles. */
const PRICKET_SCALE = 1.25;

/** Thick tallow candles impaled on the spikes of an iron pricket, heavy with drips. */
const WarriorCandle = ({ position, flame, glow, seed }: CandleProps) => {
  const iron = useMetal('#4d4e52', 0.55);
  const tallow = useDisposable(() => new THREE.MeshStandardMaterial({ color: TALLOW, roughness: 0.8 }), []);
  const candles: { x: number; z: number; h: number; r: number }[] = [
    { x: 0, z: 0, h: 0.62, r: 0.2 },
    { x: 0.42, z: 0.18, h: 0.36, r: 0.17 },
  ];
  return (
    <group position={position} scale={PRICKET_SCALE}>
      <CandleLight colour="#ffae52" glow={glow} intensity={16} lightPosition={[0.8, 0.9, 0.8]} seed={seed} />
      {/* Three-legged iron dish */}
      <mesh position={[0.15, 0.11, 0.06]} material={iron} castShadow>
        <cylinderGeometry args={[0.6, 0.5, 0.06, 24]} />
      </mesh>
      {[0, 1, 2].map((i) => {
        const a = (i / 3) * Math.PI * 2;
        return (
          <mesh key={i} position={[0.15 + Math.cos(a) * 0.42, 0.04, 0.06 + Math.sin(a) * 0.42]} material={iron}>
            <boxGeometry args={[0.06, 0.08, 0.06]} />
          </mesh>
        );
      })}
      {candles.map((c, i) => (
        <group key={i} position={[c.x, 0.14, c.z]}>
          <mesh position={[0, c.h / 2, 0]} material={tallow} castShadow>
            <cylinderGeometry args={[c.r * 0.95, c.r * 1.08, c.h, 18]} />
          </mesh>
          {/* Melted rim and long drips down the side */}
          <mesh position={[0, c.h, 0]} rotation={[Math.PI / 2, 0, 0]} material={tallow}>
            <torusGeometry args={[c.r * 0.8, c.r * 0.2, 8, 18]} />
          </mesh>
          {[0.3, 2.1, 4.2].map((a, j) => (
            <mesh key={j} position={[Math.cos(a) * c.r, c.h * (0.55 + j * 0.1), Math.sin(a) * c.r]} scale={[0.5, 2.4, 0.5]} material={tallow}>
              <sphereGeometry args={[c.r * 0.22, 8, 8]} />
            </mesh>
          ))}
          <Flame flame={flame} glow={glow} position={[0, c.h + 0.32, 0]} colour="#ffb04a" core="#fff1c8" size={1.15} seed={seed * 3 + i} />
        </group>
      ))}
      {/* Sparks spat from the wicks */}
      <Sparkles raycast={noRaycast} count={8} scale={[0.8, 1.2, 0.8]} position={[0.15, 1.3, 0.1]} size={2} speed={0.8} color="#ffa04a" />
    </group>
  );
};

/* ===================== Rogue: a stub in a bottle ===================== */

/** Outline of a dark wine bottle, turned on the lathe: base to lip. */
const BOTTLE_PROFILE: [number, number][] = [
  [0, 0],
  [0.2, 0],
  [0.22, 0.03],
  [0.22, 0.52],
  [0.19, 0.62],
  [0.1, 0.72],
  [0.075, 0.8],
  [0.075, 0.95],
  [0.09, 0.97],
  [0.09, 1.0],
];

/** Overall size of the bottle and its stub. */
const BOTTLE_SCALE = 1.2;

/** A candle stub pushed into the neck of an empty bottle, wax run down the glass. */
const RogueCandle = ({ position, flame, glow, seed }: CandleProps) => {
  const profile = useMemo(() => BOTTLE_PROFILE.map(([r, h]) => new THREE.Vector2(r, h)), []);
  const wax = useDisposable(() => new THREE.MeshStandardMaterial({ color: '#e4dcc4', roughness: 0.6 }), []);
  return (
    <group position={position}>
      <CandleLight colour="#d8d68a" glow={glow} intensity={15} lightPosition={[0.7, 1.1, 0.7]} unrest={1.6} seed={seed} />
      <group scale={BOTTLE_SCALE}>
        <mesh castShadow>
          <latheGeometry args={[profile, 28]} />
          <meshStandardMaterial color="#16241a" roughness={0.12} metalness={0.3} transparent opacity={0.9} side={THREE.DoubleSide} />
        </mesh>
        {/* The stub, and wax run down the neck and over the shoulder */}
        <mesh position={[0, 1.08, 0]} material={wax} castShadow>
          <cylinderGeometry args={[0.07, 0.075, 0.18, 14]} />
        </mesh>
        {[
          [0.08, 0.92, 0, 2.2],
          [-0.06, 0.86, 0.05, 3.2],
          [0.15, 0.62, 0.08, 1.6],
          [-0.1, 0.7, -0.12, 2],
        ].map(([x, y, z, len], i) => (
          <mesh key={i} position={[x, y, z]} scale={[0.5, len, 0.5]} material={wax}>
            <sphereGeometry args={[0.04, 8, 8]} />
          </mesh>
        ))}
        {/* A restless flame with a sickly green root */}
        <Flame flame={flame} glow={glow} position={[0, 1.36, 0]} colour="#ffd27a" core="#f4ffd0" size={0.8} unrest={1.8} seed={seed * 5} />
        <sprite raycast={noRaycast} position={[0, 1.2, 0.01]} scale={[0.1, 0.12, 1]}>
          <spriteMaterial map={glow} color="#7fd65a" transparent opacity={0.8} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
        </sprite>
      </group>
    </group>
  );
};

/* ===================== Mage: candles hanging in the air ===================== */

const MAGE_CANDLES = [
  { x: 0, z: 0, h: 0.42, lift: 0.45, phase: 0 },
  { x: 0.45, z: 0.2, h: 0.32, lift: 0.3, phase: 2.1 },
  { x: -0.3, z: 0.25, h: 0.5, lift: 0.6, phase: 4.2 },
];

/** Overall size of the floating candles and how high they hang. */
const MAGE_SCALE = 1.5;

/** Slender white candles floating over the table, slowly rising and falling, burning cold. */
const MageCandle = ({ position, flame, glow, seed }: CandleProps) => {
  const wax = useDisposable(
    () => new THREE.MeshStandardMaterial({ color: '#f4f2ff', roughness: 0.4, emissive: '#9cc4ff', emissiveIntensity: 0.15 }),
    [],
  );
  const candles = useRef<(THREE.Group | null)[]>([]);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    candles.current.forEach((g, i) => {
      if (!g) return;
      const c = MAGE_CANDLES[i];
      g.position.y = c.lift + Math.sin(t * 0.8 + c.phase) * 0.12;
      g.rotation.z = Math.sin(t * 0.6 + c.phase) * 0.06;
    });
  });
  return (
    <group position={position} scale={MAGE_SCALE}>
      <CandleLight colour="#8fb8ff" glow={glow} intensity={13} lightPosition={[0.6, 1.8, 0.6]} unrest={0.6} seed={seed} />
      {MAGE_CANDLES.map((c, i) => (
        <group
          key={i}
          ref={(g) => {
            candles.current[i] = g;
          }}
          position={[c.x, c.lift, c.z]}
        >
          <mesh position={[0, c.h / 2, 0]} material={wax} castShadow>
            <cylinderGeometry args={[0.065, 0.07, c.h, 14]} />
          </mesh>
          <Flame flame={flame} glow={glow} position={[0, c.h + 0.22, 0]} colour="#a8d0ff" core="#ffffff" size={0.75} unrest={0.6} seed={seed * 7 + i} />
        </group>
      ))}
    </group>
  );
};

/* DB class ids: 1=Warrior, 2=Rogue, 3=Mage */
const CANDLES: Record<number, (props: CandleProps) => JSX.Element> = {
  1: WarriorCandle,
  2: RogueCandle,
  3: MageCandle,
};

const ClassCandle = ({ classId, ...props }: CandleProps & { classId: number }) => {
  const Candle = CANDLES[classId] ?? WarriorCandle;
  return <Candle {...props} />;
};

export default ClassCandle;
