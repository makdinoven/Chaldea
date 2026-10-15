import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Line, QuadraticBezierLine } from "@react-three/drei";
import * as THREE from "three";
import type { ArenaAim } from "./arenaTypes";
import { createSoftSpotTexture } from "./textures";
import { isMelee, PALETTE, sidePalette, STRIKE_MS, type StrikePalette, type StrikeStyle } from "./strikeStyles";

// Must stay well below BattlePage's 3D MIN_TURN_GAP_MS (2600): the next state ends the HP hold.
export const FLIGHT_MS = 850;
const IMPACT_MS = 2200;
const EMBER_COUNT = 44;
// Approximate footprint of the DOM fighter card on the board, in world units.
const CARD_HALF_W = 1.15;
const CARD_HALF_D = 1.5;
const GRAVITY = 5.5;
const ARC_HEIGHT = 2.6;
// A cast effect's orb next to a blow's bolt.
const SPELL_SCALE = 0.62;
const CARD_HEIGHT = 0.9;

export type Vec3 = [number, number, number];

export interface Strike {
  id: number;
  from: Vec3;
  to: Vec3;
  color: string;
  startedAt: number;
  /** The blow never connects (dodged / missed): no burst where it ends. */
  glancing?: boolean;
  /** A cast effect rather than a blow: a smaller orb of its colour. */
  spell?: boolean;
  /** Look of the blow, from its damage type; absent = the plain side-coloured bolt. */
  style?: StrikeStyle;
}

export interface Impact {
  id: number;
  at: Vec3;
  color: string;
  startedAt: number;
  style?: StrikeStyle;
}

/** How long a strike takes to land: blades at the lunge's peak, missiles by element. */
export const strikeMs = (s: Pick<Strike, "style" | "spell">) =>
  s.spell || !s.style ? FLIGHT_MS : STRIKE_MS[s.style];

const paletteOf = (style: StrikeStyle | undefined, color: string): StrikePalette =>
  style && style !== "bolt" ? PALETTE[style] : sidePalette(color);

// How high each kind of missile arcs (× ARC_HEIGHT): wind skims, ice is thrown flat.
const ARC_LIFT: Partial<Record<StrikeStyle, number>> = { wind: 0.2, ice: 0.4, water: 0.7, curse: 0.8 };

const lift = (p: Vec3, y: number): THREE.Vector3 => new THREE.Vector3(p[0], y, p[2]);

const arcMid = (a: THREE.Vector3, b: THREE.Vector3, height: number) =>
  a.clone().lerp(b, 0.5).setY(Math.max(a.y, b.y) + height);

const TRAIL_GHOSTS = 7;
const TRAIL_SPACING = 0.035;
const smoothstep = (k: number) => k * k * (3 - 2 * k);

/**
 * A blow on its way: a missile shaped and coloured by its damage type flying along
 * an arc with a fading wake, a lightning bolt, or — for blades — nothing at all
 * (the attacker's lunge carries it). Calls `onLand` when it arrives.
 */
export const Projectile = ({ strike, onLand }: { strike: Strike; onLand: (s: Strike) => void }) => {
  const style: StrikeStyle = strike.spell ? "bolt" : strike.style ?? "bolt";
  const flight = strikeMs(strike);
  if (isMelee(style)) return <LandTimer strike={strike} flight={flight} onLand={onLand} />;
  if (style === "lightning") return <LightningStrike strike={strike} flight={flight} onLand={onLand} />;
  return <Missile strike={strike} style={style} flight={flight} onLand={onLand} />;
};

interface FlightProps {
  strike: Strike;
  flight: number;
  onLand: (s: Strike) => void;
}

/** A blade's blow: nothing flies, it just lands on time. */
const LandTimer = ({ strike, flight, onLand }: FlightProps) => {
  const landed = useRef(false);
  useFrame(() => {
    if (landed.current || performance.now() - strike.startedAt < flight) return;
    landed.current = true;
    onLand(strike);
  });
  return null;
};

const LIGHTNING_SEGMENTS = 12;
const LIGHTNING_JITTER = 0.45;
// The caster gathers charge this long (share of the strike), then the bolt hits.
const LIGHTNING_CHARGE = 0.55;

/** Charge gathers at the caster, then a jagged bolt cracks across to the target. */
const LightningStrike = ({ strike, flight, onLand }: FlightProps) => {
  const pal = PALETTE.lightning;
  const landed = useRef(false);
  const charge = useRef<THREE.Mesh>(null);
  const [points, setPoints] = useState<THREE.Vector3[] | null>(null);
  const lastJitter = useRef(0);
  const a = useMemo(() => lift(strike.from, CARD_HEIGHT), [strike.from]);
  const b = useMemo(() => lift(strike.to, CARD_HEIGHT), [strike.to]);

  useFrame(() => {
    if (landed.current) return;
    const now = performance.now();
    const k = (now - strike.startedAt) / flight;
    if (k >= 1) {
      landed.current = true;
      setPoints(null);
      onLand(strike);
      return;
    }
    if (charge.current) {
      const c = Math.min(1, k / LIGHTNING_CHARGE);
      charge.current.scale.setScalar(0.15 + c * 0.45 + Math.sin(now / 25) * 0.05);
    }
    // Past the charge, re-draw the jagged path a few times a second so it crackles.
    if (k >= LIGHTNING_CHARGE && now - lastJitter.current > 55) {
      lastJitter.current = now;
      const side = new THREE.Vector3(-(b.z - a.z), 0, b.x - a.x).normalize();
      setPoints(
        Array.from({ length: LIGHTNING_SEGMENTS + 1 }, (_, i) => {
          const t = i / LIGHTNING_SEGMENTS;
          const p = a.clone().lerp(b, t);
          if (i === 0 || i === LIGHTNING_SEGMENTS) return p;
          const off = (Math.random() * 2 - 1) * LIGHTNING_JITTER * Math.sin(t * Math.PI);
          return p.addScaledVector(side, off).setY(p.y + (Math.random() - 0.3) * 0.4);
        }),
      );
    }
  });

  return (
    <>
      <mesh ref={charge} position={a}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color={pal.glow} transparent opacity={0.6} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
      </mesh>
      {points && (
        <>
          <Line points={points} color={pal.glow} lineWidth={9} transparent opacity={0.45} toneMapped={false} />
          <Line points={points} color={pal.core} lineWidth={3} toneMapped={false} />
          <pointLight position={b} color={pal.light} intensity={30} distance={6} />
        </>
      )}
    </>
  );
};

/** The missile's head: a different body per element, sized and lit to match. */
const MissileHead = ({ style, pal }: { style: StrikeStyle; pal: StrikePalette }) => {
  const additive = { transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false } as const;
  switch (style) {
    case "ice":
      // A shard: an octahedron drawn out along its flight.
      return (
        <>
          <mesh scale={[0.16, 0.16, 0.55]}>
            <octahedronGeometry args={[1, 0]} />
            <meshBasicMaterial color={pal.core} toneMapped={false} />
          </mesh>
          <mesh scale={[0.3, 0.3, 0.75]}>
            <octahedronGeometry args={[1, 0]} />
            <meshBasicMaterial color={pal.glow} opacity={0.4} {...additive} />
          </mesh>
        </>
      );
    case "wind":
      // Laid flat along its flight, so the camera above sees a whirling ring, not its edge.
      return (
        <group rotation={[Math.PI / 2, 0, 0]}>
          <mesh>
            <torusGeometry args={[0.34, 0.06, 8, 28]} />
            <meshBasicMaterial color={pal.core} opacity={0.9} {...additive} />
          </mesh>
          <mesh>
            <torusGeometry args={[0.22, 0.05, 8, 24]} />
            <meshBasicMaterial color={pal.glow} opacity={0.75} {...additive} />
          </mesh>
        </group>
      );
    case "water":
      return (
        <>
          <mesh scale={[0.22, 0.22, 0.36]}>
            <sphereGeometry args={[1, 16, 16]} />
            <meshBasicMaterial color={pal.core} toneMapped={false} />
          </mesh>
          <mesh scale={[0.38, 0.38, 0.6]}>
            <sphereGeometry args={[1, 16, 16]} />
            <meshBasicMaterial color={pal.glow} opacity={0.5} {...additive} />
          </mesh>
        </>
      );
    case "arcane":
      return (
        <>
          <mesh>
            <sphereGeometry args={[0.18, 16, 16]} />
            <meshBasicMaterial color={pal.core} toneMapped={false} />
          </mesh>
          <mesh>
            <torusGeometry args={[0.36, 0.035, 8, 32]} />
            <meshBasicMaterial color={pal.glow} opacity={0.9} {...additive} />
          </mesh>
          <mesh>
            <sphereGeometry args={[0.4, 16, 16]} />
            <meshBasicMaterial color={pal.glow} opacity={0.35} {...additive} />
          </mesh>
        </>
      );
    default: {
      // Fire, holy, curse and the plain bolt: a glowing core in a halo.
      const halo = style === "holy" ? 0.55 : style === "fire" ? 0.48 : 0.42;
      return (
        <>
          <mesh>
            <sphereGeometry args={[style === "curse" ? 0.16 : 0.2, 16, 16]} />
            <meshBasicMaterial color={pal.core} toneMapped={false} />
          </mesh>
          <mesh>
            <sphereGeometry args={[halo, 16, 16]} />
            <meshBasicMaterial color={pal.glow} opacity={style === "curse" ? 0.7 : 0.5} {...additive} />
          </mesh>
        </>
      );
    }
  }
};

/** A missile along an arc with a fading wake — shape and colour from its element. */
const Missile = ({ strike, style, flight, onLand }: FlightProps & { style: StrikeStyle }) => {
  const pal = paletteOf(style, strike.color);
  const head = useRef<THREE.Group>(null);
  const body = useRef<THREE.Group>(null);
  const ghosts = useRef<(THREE.Mesh | null)[]>([]);
  const landed = useRef(false);
  const curve = useMemo(() => {
    const a = lift(strike.from, CARD_HEIGHT);
    const b = lift(strike.to, CARD_HEIGHT);
    return new THREE.QuadraticBezierCurve3(a, arcMid(a, b, ARC_HEIGHT * (ARC_LIFT[style] ?? 0.6)), b);
  }, [strike.from, strike.to, style]);

  useFrame(({ clock }) => {
    if (landed.current) return;
    const k = (performance.now() - strike.startedAt) / flight;
    if (k >= 1) {
      landed.current = true;
      onLand(strike);
      return;
    }
    const at = smoothstep(Math.max(0, k));
    if (head.current) {
      head.current.position.copy(curve.getPoint(at));
      // Point shards, drops and rings along their flight.
      head.current.lookAt(curve.getPoint(Math.min(1, at + 0.02)));
    }
    if (body.current) {
      const t = clock.elapsedTime;
      if (style === "fire") body.current.scale.setScalar(1 + Math.sin(t * 38) * 0.14);
      if (style === "wind") body.current.rotation.y = t * 14;
      if (style === "arcane") body.current.rotation.z = t * 6;
    }
    ghosts.current.forEach((ghost, i) => {
      if (!ghost) return;
      const kg = k - (i + 1) * TRAIL_SPACING;
      ghost.visible = kg > 0;
      if (kg > 0) ghost.position.copy(curve.getPoint(smoothstep(kg)));
    });
  });

  // Fire leaves a fat wake, wind and ice barely any.
  const wake = style === "fire" ? 0.42 : style === "wind" || style === "ice" ? 0.16 : 0.3;
  return (
    <>
      <group ref={head} position={curve.getPoint(0)} scale={strike.spell ? SPELL_SCALE : 1}>
        <group ref={body}>
          <MissileHead style={style} pal={pal} />
        </group>
        <pointLight color={pal.light} intensity={25} distance={5} />
      </group>
      {Array.from({ length: TRAIL_GHOSTS }, (_, i) => {
        const fade = 1 - (i + 1) / (TRAIL_GHOSTS + 1);
        return (
          <mesh key={i} ref={(m) => (ghosts.current[i] = m)} visible={false}>
            <sphereGeometry args={[wake * fade + 0.05, 12, 12]} />
            <meshBasicMaterial
              color={pal.glow}
              transparent
              opacity={0.55 * fade}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
              toneMapped={false}
            />
          </mesh>
        );
      })}
    </>
  );
};

/** Embers shaken loose from the struck card, raining onto the board and dying out there. */
export const ImpactBurst = ({ impact, onDone }: { impact: Impact; onDone: (i: Impact) => void }) => {
  const embers = useRef<(THREE.Sprite | null)[]>([]);
  const light = useRef<THREE.PointLight>(null);
  const done = useRef(false);
  // Sparks cool from their element's hot colour through warm to a dull cold one.
  const colors = useMemo(() => {
    const pal = paletteOf(impact.style, impact.color);
    return { hot: new THREE.Color(pal.hot), warm: new THREE.Color(pal.warm), cold: new THREE.Color(pal.cold), light: pal.light };
  }, [impact.style, impact.color]);

  const seeds = useMemo(
    () =>
      Array.from({ length: EMBER_COUNT }, () => {
        // Shed from the card's outline (the DOM card covers anything under it),
        // drifting a little outward as they fall.
        const side = Math.floor(Math.random() * 4);
        const along = Math.random() * 2 - 1;
        const ox = side < 2 ? (side === 0 ? -1 : 1) * CARD_HALF_W : along * CARD_HALF_W;
        const oz = side >= 2 ? (side === 2 ? -1 : 1) * CARD_HALF_D : along * CARD_HALF_D;
        const out = 0.25 + Math.random() * 0.7;
        return {
          ox,
          oz,
          vx: Math.sign(ox || along) * out * (side < 2 ? 1 : 0.3),
          vz: Math.sign(oz || along) * out * (side >= 2 ? 1 : 0.3),
          // A small hop at most: they tumble down rather than burst upward.
          vy: Math.random() * 1.1,
          size: 0.035 + Math.random() * 0.045,
          // Each ember cools at its own pace, so the pile doesn't go dark all at once.
          life: 0.55 + Math.random() * 0.45,
          flicker: Math.random() * 20,
        };
      }),
    [],
  );
  const glow = useMemo(createSoftSpotTexture, []);
  const materials = useMemo(
    () =>
      seeds.map(
        () =>
          new THREE.SpriteMaterial({
            map: glow,
            transparent: true,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
            toneMapped: false,
          }),
      ),
    [glow, seeds],
  );
  useEffect(
    () => () => {
      glow.dispose();
      materials.forEach((m) => m.dispose());
    },
    [glow, materials],
  );

  useFrame(() => {
    if (done.current) return;
    const ms = performance.now() - impact.startedAt;
    if (ms >= IMPACT_MS) {
      done.current = true;
      onDone(impact);
      return;
    }
    const t = ms / 1000;
    embers.current.forEach((sprite, i) => {
      if (!sprite) return;
      const e = seeds[i];
      const age = Math.min(1, ms / (IMPACT_MS * e.life));
      const floor = -CARD_HEIGHT + 0.22;
      const y = Math.max(floor, e.vy * t - GRAVITY * 0.5 * t * t);
      // Once on the board they stop sliding.
      const travel = y === floor ? Math.min(t, 0.45) : t;
      sprite.position.set(e.ox + e.vx * travel, y, e.oz + e.vz * travel);
      const mat = materials[i];
      if (age < 0.35) mat.color.copy(colors.hot).lerp(colors.warm, age / 0.35);
      else mat.color.copy(colors.warm).lerp(colors.cold, (age - 0.35) / 0.65);
      const flicker = 0.8 + Math.sin(t * 18 + e.flicker) * 0.2;
      mat.opacity = (1 - age * age) * flicker;
      sprite.scale.setScalar(e.size * 2 * (1 - age * 0.4));
    });
    if (light.current) light.current.intensity = 14 * Math.max(0, 1 - ms / 600);
  });

  return (
    <group position={[impact.at[0], CARD_HEIGHT, impact.at[2]]}>
      {seeds.map((_, i) => (
        <sprite key={i} ref={(m) => (embers.current[i] = m)} material={materials[i]} />
      ))}
      <pointLight ref={light} color={colors.light} distance={4} />
    </group>
  );
};

const AIM_COLORS: Record<ArenaAim["kind"], string> = {
  attack: "#f37753",
  ally: "#34d399",
};

// DOM cards always draw over the canvas, so the arc anchors on the front lip of
// each pedestal (toward the camera) where nothing covers it.
const PEDESTAL_FRONT = 1.0;

/** Marching dashed arc from the viewer to whoever their queued skill will hit. */
export const AimArc = ({ from, to, kind }: { from: Vec3; to: Vec3; kind: ArenaAim["kind"] }) => {
  const line = useRef<{ material: { dashOffset: number } } | null>(null);
  const start = useMemo(() => lift(from, 0.3).setZ(from[2] + PEDESTAL_FRONT), [from]);
  const end = useMemo(() => lift(to, 0.3).setZ(to[2] + PEDESTAL_FRONT), [to]);
  const mid = useMemo(() => arcMid(start, end, ARC_HEIGHT * 1.35), [start, end]);

  useFrame((_, delta) => {
    if (line.current) line.current.material.dashOffset -= delta * 1.6;
  });

  return (
    <QuadraticBezierLine
      ref={line as never}
      start={start}
      end={end}
      mid={mid}
      color={AIM_COLORS[kind]}
      lineWidth={4}
      dashed
      dashSize={0.4}
      gapSize={0.2}
      transparent
      opacity={0.9}
      toneMapped={false}
    />
  );
};
