import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { QuadraticBezierLine } from "@react-three/drei";
import * as THREE from "three";
import type { ArenaAim } from "./arenaTypes";
import { createSoftSpotTexture } from "./textures";

// Must stay well below BattlePage's 3D MIN_TURN_GAP_MS (2600): the next state ends the HP hold.
export const FLIGHT_MS = 850;
const IMPACT_MS = 2200;
const EMBER_COUNT = 44;
// Approximate footprint of the DOM fighter card on the board, in world units.
const CARD_HALF_W = 1.15;
const CARD_HALF_D = 1.5;
const GRAVITY = 5.5;
// Embers cool from white-hot through orange to a dull coal as they fall and lie.
const EMBER_HOT = new THREE.Color("#ffe1a0");
const EMBER_WARM = new THREE.Color("#ff6a1a");
const EMBER_COLD = new THREE.Color("#4a0e04");
const ARC_HEIGHT = 2.6;
const CARD_HEIGHT = 0.9;

export type Vec3 = [number, number, number];

export interface Strike {
  id: number;
  from: Vec3;
  to: Vec3;
  color: string;
  startedAt: number;
}

export interface Impact {
  id: number;
  at: Vec3;
  color: string;
  startedAt: number;
}

const lift = (p: Vec3, y: number): THREE.Vector3 => new THREE.Vector3(p[0], y, p[2]);

const arcMid = (a: THREE.Vector3, b: THREE.Vector3, height: number) =>
  a.clone().lerp(b, 0.5).setY(Math.max(a.y, b.y) + height);

const TRAIL_GHOSTS = 7;
const TRAIL_SPACING = 0.035;
const smoothstep = (k: number) => k * k * (3 - 2 * k);

/** A glowing bolt flying along an arc from attacker to target, with a fading wake. */
export const Projectile = ({ strike, onLand }: { strike: Strike; onLand: (s: Strike) => void }) => {
  const head = useRef<THREE.Group>(null);
  const ghosts = useRef<(THREE.Mesh | null)[]>([]);
  const landed = useRef(false);
  const curve = useMemo(() => {
    const a = lift(strike.from, CARD_HEIGHT);
    const b = lift(strike.to, CARD_HEIGHT);
    return new THREE.QuadraticBezierCurve3(a, arcMid(a, b, ARC_HEIGHT * 0.6), b);
  }, [strike.from, strike.to]);

  useFrame(() => {
    if (landed.current) return;
    const k = (performance.now() - strike.startedAt) / FLIGHT_MS;
    if (k >= 1) {
      landed.current = true;
      onLand(strike);
      return;
    }
    head.current?.position.copy(curve.getPoint(smoothstep(Math.max(0, k))));
    ghosts.current.forEach((ghost, i) => {
      if (!ghost) return;
      const kg = k - (i + 1) * TRAIL_SPACING;
      ghost.visible = kg > 0;
      if (kg > 0) ghost.position.copy(curve.getPoint(smoothstep(kg)));
    });
  });

  return (
    <>
      <group ref={head} position={curve.getPoint(0)}>
        <mesh>
          <sphereGeometry args={[0.2, 16, 16]} />
          <meshBasicMaterial color="#fff6d8" toneMapped={false} />
        </mesh>
        <mesh>
          <sphereGeometry args={[0.42, 16, 16]} />
          <meshBasicMaterial color={strike.color} transparent opacity={0.5} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
        </mesh>
        <pointLight color={strike.color} intensity={25} distance={5} />
      </group>
      {Array.from({ length: TRAIL_GHOSTS }, (_, i) => {
        const fade = 1 - (i + 1) / (TRAIL_GHOSTS + 1);
        return (
          <mesh key={i} ref={(m) => (ghosts.current[i] = m)} visible={false}>
            <sphereGeometry args={[0.3 * fade + 0.05, 12, 12]} />
            <meshBasicMaterial
              color={strike.color}
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
      if (age < 0.35) mat.color.copy(EMBER_HOT).lerp(EMBER_WARM, age / 0.35);
      else mat.color.copy(EMBER_WARM).lerp(EMBER_COLD, (age - 0.35) / 0.65);
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
      <pointLight ref={light} color="#ff7a2a" distance={4} />
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
