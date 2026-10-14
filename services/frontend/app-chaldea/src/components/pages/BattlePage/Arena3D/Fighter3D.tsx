import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import FighterCard, { type FloatingNumber } from "./FighterCard";
import type { ArenaFighter } from "./arenaTypes";
import { createSoftSpotTexture } from "./textures";

const HIT_DURATION_MS = 1200;
const NUMBER_LIFETIME_MS = 2300;
const SHAKE_AMPLITUDE = 0.12;
// Keeps the DOM cards under site modals (z-index 1000) and the navbar.
const CARD_Z_RANGE: [number, number] = [30, 0];

const GLOW_COLORS = {
  acting: "#f0d95c",
  target: "#f37753",
  ally: "#34d399",
} as const;

// Seen from above, any height pushes the card up the screen, so it hugs the board.
const CARD_ANCHOR_Y = 0.45;
// Footprint of the glow / contact shadow on the board, in world units.
const GLOW_SIZE = 3.4;
const SHADOW_SIZE: [number, number] = [2.6, 2.1];
const LUNGE_MS = 650;
const LUNGE_DISTANCE = 0.9;

interface Fighter3DProps {
  fighter: ArenaFighter;
  position: [number, number, number];
  /** Set when this fighter just struck: the card leaps toward `toward` and back. */
  lunge: { toward: [number, number, number]; at: number } | null;
  cardDistanceFactor: number;
  onSelect: (fighter: ArenaFighter) => void;
}

const Fighter3D = ({ fighter, position, lunge, cardDistanceFactor, onSelect }: Fighter3DProps) => {
  const body = useRef<THREE.Group>(null);
  const glowMaterial = useRef<THREE.MeshBasicMaterial>(null);
  const hitLight = useRef<THREE.PointLight>(null);
  const hitStartedAt = useRef<number | null>(null);
  const previousHp = useRef(fighter.hp);
  const nextNumberId = useRef(0);
  const timers = useRef(new Set<number>());
  const [hit, setHit] = useState(false);
  const spot = useMemo(createSoftSpotTexture, []);
  useEffect(() => () => spot.dispose(), [spot]);
  const [numbers, setNumbers] = useState<FloatingNumber[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => window.clearTimeout(t));
  }, []);

  useEffect(() => {
    const later = (fn: () => void, ms: number) => {
      const t = window.setTimeout(() => {
        timers.current.delete(t);
        fn();
      }, ms);
      timers.current.add(t);
    };

    const delta = Math.round(fighter.hp - previousHp.current);
    previousHp.current = fighter.hp;
    if (delta === 0) return;

    const id = nextNumberId.current++;
    setNumbers((list) => [...list, { id, value: delta }]);
    later(() => setNumbers((list) => list.filter((n) => n.id !== id)), NUMBER_LIFETIME_MS);
    if (delta > 0) return;

    hitStartedAt.current = performance.now();
    setHit(true);
    later(() => setHit(false), HIT_DURATION_MS);
  }, [fighter.hp]);

  const glowColor = fighter.isActing
    ? GLOW_COLORS.acting
    : fighter.selection
      ? GLOW_COLORS[fighter.selection]
      : GLOW_COLORS.acting;

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;

    if (body.current) {
      let shake = 0;
      if (hitStartedAt.current !== null) {
        const k = (performance.now() - hitStartedAt.current) / HIT_DURATION_MS;
        if (k >= 1) hitStartedAt.current = null;
        else shake = Math.sin(k * Math.PI * 9) * SHAKE_AMPLITUDE * (1 - k);
      }
      const bob = fighter.isActing && !fighter.isDead ? Math.sin(t * 2.2) * 0.06 + 0.08 : 0;
      let lungeX = 0;
      let lungeZ = 0;
      if (lunge) {
        const k = (performance.now() - lunge.at) / LUNGE_MS;
        if (k >= 0 && k < 1) {
          const dx = lunge.toward[0] - position[0];
          const dz = lunge.toward[2] - position[2];
          const len = Math.hypot(dx, dz) || 1;
          const reach = Math.sin(k * Math.PI) * LUNGE_DISTANCE;
          lungeX = (dx / len) * reach;
          lungeZ = (dz / len) * reach;
        }
      }
      body.current.position.x = shake + lungeX;
      body.current.position.z = lungeZ;
      body.current.position.y = THREE.MathUtils.lerp(body.current.position.y, bob, 0.12);
    }

    if (hitLight.current) {
      const target = hitStartedAt.current !== null ? 12 : 0;
      hitLight.current.intensity = THREE.MathUtils.lerp(hitLight.current.intensity, target, 0.25);
    }

    if (glowMaterial.current) {
      const emphasised = !fighter.isDead && (fighter.isActing || fighter.selection !== null);
      const target = emphasised ? 0.55 + Math.sin(t * 3) * 0.15 : 0;
      glowMaterial.current.opacity = THREE.MathUtils.lerp(glowMaterial.current.opacity, target, 0.1);
    }
  });

  return (
    <group position={position}>
      {/* Colour pooling on the board under whoever is acting or targeted */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
        <planeGeometry args={[GLOW_SIZE, GLOW_SIZE]} />
        <meshBasicMaterial
          ref={glowMaterial}
          map={spot}
          color={glowColor}
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
      {/* Contact shadow: the card is a heavy slab lying on the board */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.015, 0.3]}>
        <planeGeometry args={SHADOW_SIZE} />
        <meshBasicMaterial map={spot} color="#000000" transparent opacity={0.75} depthWrite={false} />
      </mesh>

      <pointLight ref={hitLight} color="#ff3b2f" intensity={0} distance={4} position={[0, 1.6, 0.8]} />

      <group ref={body}>
        <Html
          center
          position={[0, CARD_ANCHOR_Y, 0]}
          distanceFactor={cardDistanceFactor}
          zIndexRange={CARD_Z_RANGE}
        >
          <FighterCard fighter={fighter} hit={hit} numbers={numbers} onSelect={() => onSelect(fighter)} />
        </Html>
      </group>
    </group>
  );
};

export default Fighter3D;
