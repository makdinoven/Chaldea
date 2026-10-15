import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import FighterCard, { type DotFx, type FloatingNumber, type OrbRow, type WordTone } from "./FighterCard";
import type { CastFx } from "./CastEffects";
import type { ArenaFighter, DotHit, Evade } from "./arenaTypes";
import type { StrikeStyle } from "./strikeStyles";
import { createSoftSpotTexture } from "./textures";
import AuraBoard from "./AuraBoard";
import { auraKindsOf } from "./Auras";

const HIT_DURATION_MS = 1200;
const NUMBER_LIFETIME_MS = 2300;
// An HP drop this soon after a damage-over-time release, of the tick's size, is that tick.
const DOT_MATCH_MS = 400;
// How long the bleeding / burning / poison overlay plays on the card.
const DOT_FX_MS = 1900;
// How long the heal sparkles play.
const HEAL_FX_MS = 1700;

/** A control word to show on the card: the turn lost, or which skills were cut. */
export interface ControlHit {
  at: number;
  word: string;
  sub?: string;
  tone: WordTone;
}
const SHAKE_AMPLITUDE = 0.12;
// A hammer rocks the card harder than a thrust; everything else shakes as before.
const SHAKE_BY_STYLE: Partial<Record<StrikeStyle, number>> = { crush: 2, pierce: 0.6, lightning: 1.4 };
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
// A dodge: a quick step aside, a beat out there, then a slower step back.
const DODGE_MS = 1100;
const DODGE_OUT = 0.22;
const DODGE_HOLD = 0.45;
const DODGE_DISTANCE = 1.6;
// A damage number this close in time to the turn's crit on this fighter is that crit.
const CRIT_MATCH_MS = 2500;
const EVASION_WORDS = { dodge: "Уклонение", miss: "Промах", absorb: "Поглощено" } as const;
const smoothstep = (k: number) => k * k * (3 - 2 * k);

/** 0 → 1 → 0 over a dodge: out fast, hold, back slower. */
const dodgeReach = (k: number) => {
  if (k <= 0 || k >= 1) return 0;
  if (k < DODGE_OUT) return smoothstep(k / DODGE_OUT);
  if (k < DODGE_HOLD) return 1;
  return 1 - smoothstep((k - DODGE_HOLD) / (1 - DODGE_HOLD));
};

interface Fighter3DProps {
  fighter: ArenaFighter;
  /** Phones: resource orbs in a row under / over the card rather than beside it. */
  orbRow: OrbRow;
  position: [number, number, number];
  /** Set when this fighter just struck: the card leaps toward `toward` and back. */
  lunge: { toward: [number, number, number]; at: number } | null;
  /** Set when a blow at this fighter missed: dodge steps the card aside, both show a word. */
  evade: Evade | null;
  /** performance.now() of this turn's critical hit on this fighter, if any. */
  critAt: number | null;
  /** How the latest blow at this fighter looks (by damage type), if known. */
  hitStyle: StrikeStyle | null;
  /** The latest damage-over-time tick on this fighter, if any. */
  dot: DotHit | null;
  /** Control that fired on this fighter's turn (lost turn / blocked skills), if any. */
  controlHit: ControlHit | null;
  /** An effect cast onto this fighter just landed. */
  castFx: CastFx | null;
  cardDistanceFactor: number;
  /** The card's size on the board relative to the default (rows shrink when crowded). */
  footScale: number;
  onSelect: (fighter: ArenaFighter) => void;
}

const Fighter3D = ({
  fighter,
  orbRow,
  position,
  lunge,
  evade,
  critAt,
  hitStyle,
  dot,
  controlHit,
  castFx,
  cardDistanceFactor,
  footScale,
  onSelect,
}: Fighter3DProps) => {
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
  const [dotFx, setDotFx] = useState<DotFx | null>(null);
  const [healFx, setHealFx] = useState<number | null>(null);
  const auraKey = fighter.isDead ? "" : auraKindsOf(fighter.effects).join(",");
  const auras = useMemo(() => (auraKey ? (auraKey.split(",") as ReturnType<typeof auraKindsOf>) : []), [auraKey]);

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

    const now = performance.now();
    const tick =
      delta < 0 && dot && now - dot.at < DOT_MATCH_MS && Math.abs(-delta - dot.amount) <= 1 ? dot : null;
    const id = nextNumberId.current++;
    setNumbers((list) => [...list, { id, value: delta, spawnedAt: now, dots: tick?.kinds }]);
    later(() => setNumbers((list) => list.filter((n) => n.id !== id)), NUMBER_LIFETIME_MS);
    if (delta > 0) {
      setHealFx(id);
      later(() => setHealFx((fx) => (fx === id ? null : fx)), HEAL_FX_MS);
      return;
    }

    if (tick) {
      // The wound acts up on its own — no blade, just the effect's own show.
      setDotFx({ id, kinds: tick.kinds });
      later(() => setDotFx((fx) => (fx?.id === id ? null : fx)), DOT_FX_MS);
      return;
    }

    hitStartedAt.current = performance.now();
    setHit(true);
    later(() => setHit(false), HIT_DURATION_MS);
  }, [fighter.hp]);

  useEffect(() => {
    if (!evade) return;
    const t = window.setTimeout(() => {
      timers.current.delete(t);
      const id = nextNumberId.current++;
      setNumbers((list) => [...list, { id, value: 0, spawnedAt: performance.now(), word: EVASION_WORDS[evade.kind], tone: evade.kind === "absorb" ? "absorb" : "evade" }]);
      const done = window.setTimeout(() => {
        timers.current.delete(done);
        setNumbers((list) => list.filter((n) => n.id !== id));
      }, NUMBER_LIFETIME_MS);
      timers.current.add(done);
    }, Math.max(0, evade.at - performance.now()));
    timers.current.add(t);
  }, [evade]);

  useEffect(() => {
    if (!controlHit) return;
    const id = nextNumberId.current++;
    const { word, sub, tone } = controlHit;
    setNumbers((list) => [...list, { id, value: 0, spawnedAt: performance.now(), word, sub, tone }]);
    const t = window.setTimeout(() => {
      timers.current.delete(t);
      setNumbers((list) => list.filter((n) => n.id !== id));
    }, NUMBER_LIFETIME_MS);
    timers.current.add(t);
  }, [controlHit]);

  const shownNumbers = numbers.map((n) =>
    n.value < 0 && critAt !== null && Math.abs(n.spawnedAt - critAt) < CRIT_MATCH_MS ? { ...n, critical: true } : n,
  );

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
        else shake = Math.sin(k * Math.PI * 9) * SHAKE_AMPLITUDE * (hitStyle ? SHAKE_BY_STYLE[hitStyle] ?? 1 : 1) * (1 - k);
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
      let dodgeX = 0;
      let dodgeZ = 0;
      if (evade?.kind === "dodge") {
        const reach = dodgeReach((performance.now() - evade.at) / DODGE_MS) * DODGE_DISTANCE;
        dodgeX = evade.away[0] * reach;
        dodgeZ = evade.away[1] * reach;
      }
      body.current.position.x = shake + lungeX + dodgeX;
      body.current.position.z = lungeZ + dodgeZ;
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

      <AuraBoard kinds={auras} scale={footScale} />

      <pointLight ref={hitLight} color="#ff3b2f" intensity={0} distance={4} position={[0, 1.6, 0.8]} />

      <group ref={body}>
        <Html
          center
          position={[0, CARD_ANCHOR_Y, 0]}
          distanceFactor={cardDistanceFactor}
          zIndexRange={CARD_Z_RANGE}
        >
          <FighterCard
            fighter={fighter}
            hit={hit}
            hitStyle={hitStyle}
            dotFx={dotFx}
            castFx={castFx}
            healFx={healFx}
            orbRow={orbRow}
            numbers={shownNumbers}
            onSelect={() => onSelect(fighter)}
          />
        </Html>
      </group>
    </group>
  );
};

export default Fighter3D;
