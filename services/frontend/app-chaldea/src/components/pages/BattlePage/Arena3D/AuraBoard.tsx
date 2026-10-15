import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import type { AuraKind } from "./arenaTypes";
import { createFrostTexture, createPuddleRimTexture, createPuddleTexture, createSoftSpotTexture } from "./textures";

// What a card covers of the board seen from above (half-extents at scale 1): the
// DOM card hides anything under it, so these states play out around its edges.
const HALF_W = 0.95;
const HALF_D = 1.25;
const BOARD_Y = 0.02;
// How long a state takes to settle in when it is first laid on.
const GROW_MS = 900;

type Vec3 = [number, number, number];

const easeOut = (k: number) => 1 - (1 - Math.min(1, Math.max(0, k))) ** 3;

const seeded = (seed: number) => () => {
  seed = (seed * 16807) % 2147483647;
  return (seed - 1) / 2147483646;
};

// Canvas textures are shared by every card on the board and live as long as the page.
let frostTexture: THREE.Texture | null = null;
let puddleTexture: THREE.Texture | null = null;
let puddleRimTexture: THREE.Texture | null = null;
let spotTexture: THREE.Texture | null = null;
const frost = () => (frostTexture ??= createFrostTexture());
const puddle = () => (puddleTexture ??= createPuddleTexture());
const puddleRim = () => (puddleRimTexture ??= createPuddleRimTexture());
const spot = () => (spotTexture ??= createSoftSpotTexture());

/** 0 → 1 as a state settles in; already 1 for one that was on before the board loaded. */
const useGrowth = (instant: boolean) => {
  const born = useRef(instant ? -Infinity : performance.now());
  return () => easeOut((performance.now() - born.current) / GROW_MS);
};

interface StateProps {
  scale: number;
  instant: boolean;
}

// Angles round the card that the camera can see past it: its sides and the near
// edge (anything behind the card, or rising over it, disappears under the DOM card).
const visibleAngle = (rand: () => number) => -0.35 + rand() * (Math.PI + 0.7);

/** A point just outside the card's outline, `angle` round from its right edge. */
const aroundCard = (angle: number, margin: number, scale: number): [number, number] => {
  // Push a ray from the centre out to the card's rectangle, then a little beyond.
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const reach = Math.min(HALF_W / Math.abs(c || 1e-6), HALF_D / Math.abs(s || 1e-6));
  return [c * (reach + margin) * scale, s * (reach + margin) * scale];
};

// ── Freeze ────────────────────────────────────────────────────────────────────

interface Shard {
  at: [number, number];
  height: number;
  radius: number;
  tilt: [number, number];
  delay: number;
}

const SHARDS: Shard[] = (() => {
  const rand = seeded(7);
  const shards: Shard[] = [];
  // Clusters round the card, thickest along the near edge the camera sees best.
  const clusters = [0.15, 0.75, 1.25, 1.6, 1.95, 2.45, 3.3, 4.2, 5.1, 5.7];
  clusters.forEach((angle, i) => {
    const [cx, cz] = aroundCard(angle, 0.12, 1);
    const count = 2 + Math.floor(rand() * 2);
    for (let j = 0; j < count; j++) {
      const out = Math.atan2(cz, cx);
      shards.push({
        at: [cx + (rand() - 0.5) * 0.3, cz + (rand() - 0.5) * 0.3],
        height: (j === 0 ? 0.42 : 0.18) + rand() * 0.28,
        radius: 0.05 + rand() * 0.05,
        // Lean away from the card, as if the cold pushed them out of the board.
        tilt: [Math.sin(out) * (0.25 + rand() * 0.35), -Math.cos(out) * (0.25 + rand() * 0.35)],
        delay: i * 0.05 + j * 0.08,
      });
    }
  });
  return shards;
})();

/** Freeze: rime spreads over the board round the card, ice crystals push up through it, the light goes cold. */
const Freeze = ({ scale, instant }: StateProps) => {
  const growth = useGrowth(instant);
  const patch = useRef<THREE.Mesh>(null);
  const patchMaterial = useRef<THREE.MeshBasicMaterial>(null);
  const shards = useRef<(THREE.Group | null)[]>([]);
  const light = useRef<THREE.PointLight>(null);

  useFrame(() => {
    const k = growth();
    if (patch.current) patch.current.scale.setScalar(0.4 + 0.6 * k);
    if (patchMaterial.current) patchMaterial.current.opacity = 0.85 * k;
    shards.current.forEach((g, i) => {
      if (!g) return;
      const own = Math.min(1, Math.max(0, (k * (1 + SHARDS[i].delay * 2) - SHARDS[i].delay * 2)));
      g.scale.set(1, Math.max(0.001, easeOut(own)), 1);
    });
    if (light.current) light.current.intensity = 1.6 * k;
  });

  return (
    <group>
      <mesh ref={patch} rotation={[-Math.PI / 2, 0, 0]} position={[0, BOARD_Y, 0]}>
        <planeGeometry args={[HALF_W * 2 * 2 * scale, HALF_D * 2 * 1.7 * scale]} />
        <meshBasicMaterial ref={patchMaterial} map={frost()} color="#cfe6f6" transparent opacity={0} depthWrite={false} />
      </mesh>
      {SHARDS.map((s, i) => (
        <group
          key={i}
          ref={(g) => (shards.current[i] = g)}
          position={[s.at[0] * scale, BOARD_Y, s.at[1] * scale]}
          rotation={[s.tilt[0], 0, s.tilt[1]]}
        >
          <mesh position={[0, (s.height * scale) / 2, 0]}>
            <coneGeometry args={[s.radius * scale, s.height * scale, 5]} />
            <meshStandardMaterial
              color="#8fbedc"
              emissive="#2d5a7a"
              emissiveIntensity={0.45}
              roughness={0.1}
              metalness={0.1}
              transparent
              opacity={0.78}
              flatShading
            />
          </mesh>
        </group>
      ))}
      <pointLight ref={light} color="#a6d8ff" intensity={0} distance={3.5 * scale} decay={1.5} position={[0, 0.6, HALF_D * scale]} />
    </group>
  );
};

// ── Armor break ───────────────────────────────────────────────────────────────

const GRAVITY = 11;
const FLAKE_COUNT = 14;

interface Flake {
  from: Vec3;
  velocity: Vec3;
  spin: Vec3;
  rest: Vec3;
  size: [number, number];
  /** Seconds until it lands on the board. */
  falls: number;
}

const makeFlakes = (scale: number): Flake[] => {
  const rand = seeded(19);
  return Array.from({ length: FLAKE_COUNT }, () => {
    const angle = rand() * Math.PI * 2;
    const [x, z] = aroundCard(angle, -0.05, scale);
    const out = 0.7 + rand() * 1.1;
    const vy = 1.4 + rand() * 1.6;
    const y = (0.5 + rand() * 0.6) * scale;
    const falls = (vy + Math.sqrt(vy * vy + 2 * GRAVITY * (y - BOARD_Y))) / GRAVITY;
    return {
      from: [x, y, z],
      velocity: [Math.cos(angle) * out, vy, Math.sin(angle) * out],
      spin: [(rand() - 0.5) * 18, (rand() - 0.5) * 18, (rand() - 0.5) * 18],
      // Lying flat on the board, a little askew.
      rest: [-Math.PI / 2 + (rand() - 0.5) * 0.4, (rand() - 0.5) * 0.4, rand() * Math.PI * 2],
      size: [(0.06 + rand() * 0.08) * scale, (0.04 + rand() * 0.06) * scale],
      falls,
    };
  });
};

/** Armor break: flakes of gilding spring off the card's frame and come to rest on the board. */
const ArmorBreak = ({ scale, instant }: StateProps) => {
  const flakes = useMemo(() => makeFlakes(scale), [scale]);
  const meshes = useRef<(THREE.Mesh | null)[]>([]);
  const light = useRef<THREE.PointLight>(null);
  const born = useRef(instant ? -Infinity : performance.now());

  useFrame(() => {
    const t = (performance.now() - born.current) / 1000;
    flakes.forEach((f, i) => {
      const m = meshes.current[i];
      if (!m) return;
      const flying = Math.min(t, f.falls);
      m.position.set(
        f.from[0] + f.velocity[0] * flying,
        Math.max(BOARD_Y, f.from[1] + f.velocity[1] * flying - (GRAVITY * flying * flying) / 2),
        f.from[2] + f.velocity[2] * flying,
      );
      if (t < f.falls) m.rotation.set(f.spin[0] * t, f.spin[1] * t, f.spin[2] * t);
      else m.rotation.set(f.rest[0], f.rest[1], f.rest[2]);
    });
    // A dull glint off the metal as it gives.
    if (light.current) light.current.intensity = Math.max(0, 6 * (1 - t / 0.5));
  });

  return (
    <group>
      {flakes.map((f, i) => (
        <mesh key={i} ref={(m) => (meshes.current[i] = m)} position={f.from}>
          <planeGeometry args={f.size} />
          <meshStandardMaterial
            color="#b8913f"
            emissive="#3a2a0c"
            emissiveIntensity={0.5}
            metalness={0.85}
            roughness={0.35}
            side={THREE.DoubleSide}
          />
        </mesh>
      ))}
      <pointLight ref={light} color="#ffcf7a" intensity={0} distance={3 * scale} decay={1.5} position={[0, 0.9, HALF_D * scale]} />
    </group>
  );
};

// ── Wet ───────────────────────────────────────────────────────────────────────

const RIPPLES = 3;
const RIPPLE_S = 1.6;

/** Wet: a dark puddle gathers round the card, drops from it ringing out across the water. */
const Wet = ({ scale, instant }: StateProps) => {
  const growth = useGrowth(instant);
  const pool = useRef<THREE.Mesh>(null);
  const poolMaterial = useRef<THREE.MeshStandardMaterial>(null);
  const rimMaterial = useRef<THREE.MeshBasicMaterial>(null);
  const sheenMaterial = useRef<THREE.MeshBasicMaterial>(null);
  const rings = useRef<(THREE.Mesh | null)[]>([]);
  const cycles = useRef<number[]>(Array(RIPPLES).fill(-1));
  const rand = useMemo(() => seeded(29), []);

  useFrame(({ clock }) => {
    const k = growth();
    if (pool.current) pool.current.scale.setScalar(0.3 + 0.7 * k);
    if (poolMaterial.current) poolMaterial.current.opacity = 0.85 * k;
    // The meniscus glints as the candlelight wavers.
    if (rimMaterial.current) rimMaterial.current.opacity = (0.65 + Math.sin(clock.elapsedTime * 2.1) * 0.1) * k;
    // A broad soft sheen across the water: the room's light lying on its surface.
    if (sheenMaterial.current) sheenMaterial.current.opacity = 0.22 * k;
    rings.current.forEach((ring, i) => {
      if (!ring) return;
      const time = clock.elapsedTime / RIPPLE_S + i / RIPPLES;
      const cycle = Math.floor(time);
      if (cycle !== cycles.current[i]) {
        // Each drop lands somewhere new along the card's edge.
        cycles.current[i] = cycle;
        const [x, z] = aroundCard(visibleAngle(rand), 0.15 + rand() * 0.25, scale);
        ring.position.set(x, BOARD_Y + 0.004, z);
      }
      const phase = time - cycle;
      ring.scale.setScalar((0.05 + phase * 0.35) * scale);
      (ring.material as THREE.MeshBasicMaterial).opacity = 0.6 * (1 - phase) * k;
    });
  });

  return (
    <group>
      <mesh ref={pool} rotation={[-Math.PI / 2, 0, 0]} position={[0, BOARD_Y, 0]}>
        <planeGeometry args={[HALF_W * 2 * 1.8 * scale, HALF_D * 2 * 1.55 * scale]} />
        <meshStandardMaterial
          ref={poolMaterial}
          color="#0a131d"
          alphaMap={puddle()}
          roughness={0.05}
          metalness={0.6}
          transparent
          opacity={0}
          depthWrite={false}
        />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, BOARD_Y + 0.002, 0]} scale={1}>
        <planeGeometry args={[HALF_W * 2 * 1.8 * scale, HALF_D * 2 * 1.55 * scale]} />
        <meshBasicMaterial
          ref={rimMaterial}
          map={puddleRim()}
          color="#ffe2b8"
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[HALF_W * 0.5 * scale, BOARD_Y + 0.003, HALF_D * 1.1 * scale]}>
        <planeGeometry args={[HALF_W * 2.4 * scale, HALF_D * 0.9 * scale]} />
        <meshBasicMaterial
          ref={sheenMaterial}
          map={spot()}
          alphaMap={puddle()}
          color="#9fc0dc"
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
      {Array.from({ length: RIPPLES }, (_, i) => (
        <mesh key={i} ref={(m) => (rings.current[i] = m)} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.9, 1, 32]} />
          <meshBasicMaterial color="#b8d4ea" transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} />
        </mesh>
      ))}
    </group>
  );
};

// ── Holy / Curse: light from below, motes or smoke rising past the card ─────────

const MOTES = 7;

interface RisingProps extends StateProps {
  color: string;
  blending: THREE.Blending;
  /** Peak opacity, size at the start and at the end of the rise, and how high it goes. */
  peak: number;
  size: [number, number];
  rise: number;
  periodS: number;
}

/** Sprites drifting up from the board round the card and fading as they go. */
const Rising = ({ scale, color, blending, peak, size, rise, periodS }: RisingProps) => {
  const sprites = useRef<(THREE.Sprite | null)[]>([]);
  const cycles = useRef<number[]>(Array(MOTES).fill(-1));
  const rand = useMemo(() => seeded(41), []);

  useFrame(({ clock }) => {
    sprites.current.forEach((sprite, i) => {
      if (!sprite) return;
      const time = clock.elapsedTime / periodS + i / MOTES;
      const cycle = Math.floor(time);
      if (cycle !== cycles.current[i]) {
        cycles.current[i] = cycle;
        const [x, z] = aroundCard(visibleAngle(rand), rand() * 0.3, scale);
        sprite.userData.from = [x, z];
      }
      const phase = time - cycle;
      const [x, z] = sprite.userData.from as [number, number];
      sprite.position.set(x, BOARD_Y + phase * rise * scale, z);
      sprite.scale.setScalar((size[0] + (size[1] - size[0]) * phase) * scale);
      sprite.material.opacity = Math.sin(phase * Math.PI) * peak;
    });
  });

  return (
    <>
      {Array.from({ length: MOTES }, (_, i) => (
        <sprite key={i} ref={(s) => (sprites.current[i] = s)} userData={{ from: [0, 0] }}>
          <spriteMaterial map={spot()} color={color} transparent opacity={0} depthWrite={false} blending={blending} />
        </sprite>
      ))}
    </>
  );
};

/** A pool of colour on the board round the card, breathing slowly. */
const Pool = ({
  scale,
  instant,
  color,
  opacity,
  blending,
}: StateProps & { color: string; opacity: number; blending: THREE.Blending }) => {
  const growth = useGrowth(instant);
  const material = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }) => {
    if (material.current) {
      material.current.opacity = opacity * growth() * (0.85 + Math.sin(clock.elapsedTime * 1.3) * 0.15);
    }
  });
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, BOARD_Y - 0.004, 0]}>
      <planeGeometry args={[HALF_W * 2 * 2.5 * scale, HALF_D * 2 * 2 * scale]} />
      <meshBasicMaterial
        ref={material}
        map={spot()}
        color={color}
        transparent
        opacity={0}
        depthWrite={false}
        blending={blending}
        toneMapped={false}
      />
    </mesh>
  );
};

/** Holy: warm light wells up from the board under the card, motes of it drifting up. */
const Holy = ({ scale, instant }: StateProps) => (
  <group>
    <Pool scale={scale} instant={instant} color="#ffc35a" opacity={0.7} blending={THREE.AdditiveBlending} />
    <Rising
      scale={scale}
      instant={instant}
      color="#ffe2a0"
      blending={THREE.AdditiveBlending}
      peak={1}
      size={[0.22, 0.1]}
      rise={0.9}
      periodS={3.2}
    />
    <pointLight color="#ffd890" intensity={10} distance={4.5 * scale} decay={1.5} position={[0, 0.5, HALF_D * scale]} />
  </group>
);

/** Curse: the board darkens round the card and dark smoke curls up past it. */
const Curse = ({ scale, instant }: StateProps) => (
  <group>
    <Pool scale={scale} instant={instant} color="#050108" opacity={0.85} blending={THREE.NormalBlending} />
    <Rising
      scale={scale}
      instant={instant}
      color="#5a3a6e"
      blending={THREE.NormalBlending}
      peak={0.75}
      size={[0.5, 1.2]}
      rise={0.8}
      periodS={4.2}
    />
    <pointLight color="#8a3ab8" intensity={3} distance={3.5 * scale} decay={1.5} position={[0, 0.5, HALF_D * scale]} />
  </group>
);

// ── Electrify ─────────────────────────────────────────────────────────────────

const ARC_MS = 160;

/** A jagged path from a point on the card's edge down to the board beside it. */
const makeArc = (rand: () => number, scale: number): Vec3[] => {
  const angle = visibleAngle(rand);
  const [x0, z0] = aroundCard(angle, -0.05, scale);
  const [x1, z1] = aroundCard(angle + (rand() - 0.5) * 0.4, 0.3 + rand() * 0.3, scale);
  const y0 = (0.35 + rand() * 0.5) * scale;
  const steps = 7;
  return Array.from({ length: steps + 1 }, (_, i) => {
    const k = i / steps;
    const jitter = i === 0 || i === steps ? 0 : 0.09 * scale;
    return [
      x0 + (x1 - x0) * k + (rand() - 0.5) * jitter * 2,
      y0 + (BOARD_Y - y0) * k + (rand() - 0.5) * jitter,
      z0 + (z1 - z0) * k + (rand() - 0.5) * jitter * 2,
    ] as Vec3;
  });
};

/** Electrify: now and then a spark jumps from the card to the board, lighting it blue for a blink. */
const Electrify = ({ scale }: StateProps) => {
  const rand = useMemo(() => seeded(61), []);
  const [arc, setArc] = useState<{ points: Vec3[]; at: number } | null>(null);
  const next = useRef(performance.now() + 400);
  const light = useRef<THREE.PointLight>(null);

  useFrame(() => {
    const now = performance.now();
    if (now >= next.current) {
      setArc({ points: makeArc(rand, scale), at: now });
      next.current = now + 700 + rand() * 1500;
    }
    if (light.current) {
      const k = arc ? (now - arc.at) / ARC_MS : 1;
      light.current.intensity = k < 1 ? 9 * (1 - k) : 0;
    }
  });

  useEffect(() => {
    if (!arc) return;
    const t = window.setTimeout(() => setArc((a) => (a === arc ? null : a)), ARC_MS);
    return () => window.clearTimeout(t);
  }, [arc]);

  return (
    <group>
      {arc && (
        <>
          <Line points={arc.points} color="#5fb6ff" lineWidth={5} transparent opacity={0.35} />
          <Line points={arc.points} color="#e6f6ff" lineWidth={1.6} />
        </>
      )}
      <pointLight
        ref={light}
        color="#8fd0ff"
        intensity={0}
        distance={3 * scale}
        decay={1.5}
        position={arc ? arc.points[arc.points.length - 1] : [0, 0.4, HALF_D * scale]}
      />
    </group>
  );
};

const STATES = {
  freeze: Freeze,
  armorbreak: ArmorBreak,
  wet: Wet,
  holy: Holy,
  curse: Curse,
  electrify: Electrify,
} as const;

interface AuraBoardProps {
  kinds: AuraKind[];
  /** The card's size on the board relative to the default. */
  scale: number;
}

/**
 * The lingering states on a fighter, played out on the table round its card:
 * rime and ice, flakes of gilding, a puddle, light or shadow, sparks. The card
 * itself only changes colour; everything with substance lives in the scene.
 */
const AuraBoard = ({ kinds, scale }: AuraBoardProps) => {
  // States already on when the board loaded appear settled, not freshly cast.
  const settled = useRef(new Set(kinds));
  useEffect(() => {
    settled.current.forEach((k) => {
      if (!kinds.includes(k)) settled.current.delete(k);
    });
  }, [kinds]);

  return (
    <>
      {kinds.map((kind) => {
        const State = STATES[kind];
        return <State key={kind} scale={scale} instant={settled.current.has(kind)} />;
      })}
    </>
  );
};

export default AuraBoard;
