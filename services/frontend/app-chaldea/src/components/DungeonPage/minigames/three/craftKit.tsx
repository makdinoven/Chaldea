import { useCallback, useEffect, useMemo, useRef, type ReactNode } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Environment, Lightformer } from '@react-three/drei';
import * as THREE from 'three';
import { glowTexture } from './craftTextures';
import { OUTCOME_HOLD_MS } from './holds';

/*
  What every 3D minigame shares: the candlelit stage (lights, reflections),
  sparks, a jolt for a mistake, and the canvas framed with a vignette and a HUD
  over it. The scenes themselves live beside it, one per game.
*/

// ---------------------------------------------------------------- sparks

interface Spark {
  pos: THREE.Vector3;
  vel: THREE.Vector3;
  life: number;
  max: number;
  color: THREE.Color;
  size: number;
}

/** Sparks, dust, motes: bursts of glowing points thrown about and falling. */
export class SparkPool {
  sparks: Spark[] = [];
  constructor(private max = 64) {}

  burst(at: THREE.Vector3, color: THREE.Color | string, count: number, speed: number,
        opts: { size?: number; up?: number; life?: number; spread?: number } = {}) {
    const c = color instanceof THREE.Color ? color : new THREE.Color(color);
    const spread = opts.spread ?? 1;
    for (let i = 0; i < count; i++) {
      const a = Math.random() * Math.PI * 2;
      this.sparks.push({
        pos: at.clone(),
        vel: new THREE.Vector3(
          Math.cos(a) * speed * Math.random() * spread,
          ((opts.up ?? 0.7) + Math.random() * 0.6) * speed,
          (0.2 + Math.random() * 0.6) * speed * 0.6,
        ),
        life: 0,
        max: (opts.life ?? 0.55) * (0.6 + Math.random() * 0.8),
        color: c,
        size: opts.size ?? 1,
      });
    }
    if (this.sparks.length > this.max) this.sparks.splice(0, this.sparks.length - this.max);
  }
}

const SPARK_GRAVITY = -3.2;

/** Draws a SparkPool; give it the same max the pool was made with. `dull` — dust and grit, not glowing. */
export const SparkField = ({
  pool,
  max = 64,
  gravity = SPARK_GRAVITY,
  dull = false,
}: {
  pool: SparkPool;
  max?: number;
  gravity?: number;
  dull?: boolean;
}) => {
  const sprites = useRef<(THREE.Sprite | null)[]>([]);
  const glow = useMemo(() => glowTexture(), []);
  useFrame((_, delta) => {
    sprites.current.forEach((sprite, i) => {
      if (!sprite) return;
      const s = pool.sparks[i];
      if (!s) {
        sprite.visible = false;
        return;
      }
      s.life += delta;
      s.vel.y += gravity * delta;
      s.pos.addScaledVector(s.vel, delta);
      const k = 1 - s.life / s.max;
      sprite.visible = k > 0;
      sprite.position.copy(s.pos);
      sprite.scale.setScalar((dull ? 0.04 + 0.03 * k : 0.05 + 0.1 * k) * s.size);
      const m = sprite.material as THREE.SpriteMaterial;
      m.color.copy(s.color);
      m.opacity = Math.max(0, dull ? k * 0.8 : k);
    });
    pool.sparks = pool.sparks.filter((s) => s.life < s.max);
  });
  return (
    <>
      {Array.from({ length: max }, (_, i) => (
        <sprite
          key={i}
          ref={(el) => {
            sprites.current[i] = el;
          }}
          visible={false}
        >
          <spriteMaterial
            map={glow}
            transparent
            depthWrite={false}
            blending={dull ? THREE.NormalBlending : THREE.AdditiveBlending}
            toneMapped={dull}
          />
        </sprite>
      ))}
    </>
  );
};

// ---------------------------------------------------------------- a jolt

/** A short jolt for a group: `kick()` it, and the group shudders and settles. */
export const useJolt = (ms = 320) => {
  const at = useRef(-Infinity);
  const strength = useRef(0);
  const group = useRef<THREE.Group>(null);
  useFrame(() => {
    if (!group.current) return;
    const since = performance.now() - at.current;
    const k = since < ms ? (1 - since / ms) * strength.current : 0;
    const now = performance.now();
    group.current.position.x = Math.sin(now * 0.09) * k;
    group.current.position.y = Math.cos(now * 0.13) * k * 0.6;
  });
  return {
    group,
    kick: (amount = 0.03) => {
      at.current = performance.now();
      strength.current = amount;
    },
  };
};

// ---------------------------------------------------------------- light

interface CraftLightsProps {
  /** Where the candle burns (it flickers). */
  candle?: [number, number, number];
  /** Where the pool of light falls. */
  spot?: [number, number, number];
  spotIntensity?: number;
}

/** The candlelit stage: a warm key, the flickering candle, a cool rim, a pool of light, reflections for metal. */
export const CraftLights = ({ candle = [-1.6, 1.2, 1.6], spot = [0.4, 1.9, 2.6], spotIntensity = 14 }: CraftLightsProps) => {
  const flame = useRef<THREE.PointLight>(null);
  useFrame(() => {
    const now = performance.now();
    if (flame.current) flame.current.intensity = 6 + Math.sin(now * 0.011) * 0.9 + Math.sin(now * 0.037) * 0.6;
  });
  return (
    <>
      <color attach="background" args={['#0a0807']} />
      <fog attach="fog" args={['#0a0807', 6, 12]} />
      <hemisphereLight args={['#c8b8a0', '#20160e', 1.1]} />
      <directionalLight position={[-2.5, 2.5, 3]} intensity={1.6} color="#ffe2bc" />
      <pointLight ref={flame} position={candle} color="#ffb46a" distance={6} decay={1} />
      <directionalLight position={[2.5, 1.2, -1]} intensity={1.1} color="#7d9cff" />
      <spotLight position={spot} angle={0.42} penumbra={0.7} intensity={spotIntensity} distance={8} decay={1} color="#ffe8c8" />
      <Environment resolution={64} frames={1}>
        <Lightformer form="rect" intensity={2.2} color="#ffbf80" position={[-3, 2, 3]} scale={[3, 2, 1]} />
        <Lightformer form="rect" intensity={0.8} color="#6c86ff" position={[3, 1, -2]} scale={[2, 3, 1]} />
        <Lightformer form="ring" intensity={0.6} color="#ffffff" position={[0, 3, 2]} scale={1.5} />
      </Environment>
    </>
  );
};

/** A glow halo (additive sprite), for a candle at the edge of the light or a lit rune. */
export const Halo = ({ position, color, scale = 1.6, opacity = 0.18 }: {
  position: [number, number, number];
  color: string;
  scale?: number;
  opacity?: number;
}) => {
  const glow = useMemo(() => glowTexture(), []);
  return (
    <sprite position={position} scale={[scale, scale, 1]}>
      <spriteMaterial map={glow} color={color} transparent opacity={opacity} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
    </sprite>
  );
};

// ---------------------------------------------------------------- the stage

interface CraftStageProps {
  children: ReactNode;
  /** Over the picture: counters, marks (not clickable). */
  hud?: ReactNode;
  camera: { position: [number, number, number]; fov: number };
  /** A press anywhere on the picture (timing games); scenes with things to click leave it out. */
  onPress?: () => void;
  aspect?: string;
}

/** The canvas in its frame: rounded, vignetted, the HUD laid over it. */
export const CraftStage = ({ children, hud, camera, onPress, aspect = 'aspect-[16/10]' }: CraftStageProps) => {
  // A pointer cursor left over from hovering something in the scene.
  useEffect(() => () => {
    document.body.style.cursor = '';
  }, []);
  return (
  <div
    // On a phone the picture runs out to the window's edges (over the body's padding): every bit of width counts.
    className={`relative -mx-4 w-[calc(100%+2rem)] sm:mx-0 sm:w-full ${aspect} sm:rounded-card overflow-hidden border-y sm:border border-white/10 shadow-card touch-manipulation ${onPress ? 'cursor-pointer' : ''}`}
    onPointerDown={
      onPress
        ? (e) => {
            e.preventDefault();
            onPress();
          }
        : undefined
    }
  >
    <Canvas dpr={[1, 2]} camera={camera} gl={{ antialias: true, powerPreference: 'high-performance' }}>
      {children}
    </Canvas>
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_45%_40%,transparent_55%,rgba(0,0,0,0.6)_100%)]" />
    {hud && <div className="pointer-events-none absolute inset-0">{hud}</div>}
  </div>
  );
};

/** Pointer over something to click in a scene. */
export const pointer = {
  onPointerOver: () => {
    document.body.style.cursor = 'pointer';
  },
  onPointerOut: () => {
    document.body.style.cursor = '';
  },
};


/** Calls `onDone` with the same arguments OUTCOME_HOLD_MS later. */
export const useHeldDone = <A extends unknown[]>(onDone: (...args: A) => void) =>
  useCallback((...args: A) => {
    setTimeout(() => onDone(...args), OUTCOME_HOLD_MS);
  }, [onDone]);
