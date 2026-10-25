import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { createRuneCircleTexture } from '../../../DungeonBoard3D/decorTextures';
import { createWallBlockTexture } from '../../../DungeonBoard3D/stoneTextures';
import { CraftLights, Halo, SparkField, SparkPool, pointer, useJolt } from './craftKit';
import { stoneTexture } from './craftTextures';
import { beatPhase, pulseAt } from '../sealBeat';

/*
  The magic seal in 3D: a rune circle burnt into a stone door, crystals set
  round its ring. The sigil starts at the lit crystal; at each step a few of
  the others resonate — the true one pulses in time with the circle's beat
  (a wave runs out to the ring and the ring flares), the false ones off it.
  Touch the true one and a line of violet fire runs to it; a false one sparks
  red and goes dark. Traced to the end, the circle
  flares and the seal crumbles into motes; broken, it flashes red.
*/

export const SEAL_CAMERA = { position: [0, 0, 4.1] as [number, number, number], fov: 34 };

const RING_R = 0.82;
const NODE = 0.12;
/** A finger-sized reach round each crystal. */
const NODE_REACH = 0.21;
const FLARE_MS = 1200;

const VIOLET = new THREE.Color('#b07aff');
const BRIGHT = new THREE.Color('#e8d4ff');
const RED = new THREE.Color('#ff4a3a');
const DARK = new THREE.Color('#2a2238');

const nodeAt = (i: number, n: number): [number, number] => {
  const a = (i / n) * Math.PI * 2 + Math.PI / 2;
  return [Math.cos(a) * RING_R, Math.sin(a) * RING_R];
};

export type SealEnd = 'open' | 'broke' | null;

interface SealSceneProps {
  nodes: number;
  beatMs: number;
  path: number[];
  pulsing: number[];
  /** How far off the beat each of `pulsing` pulses (0 — in time). */
  offsets: number[];
  /** Crystals that sparked (false ones, ruled out). */
  sparked: number[];
  end: SealEnd;
  onTouch: (node: number) => void;
}

const SealScene = ({ nodes, beatMs, path, pulsing, offsets, sparked, end, onTouch }: SealSceneProps) => {
  const [hovered, setHovered] = useState<number | null>(null);
  const textures = useMemo(() => {
    const wall = createWallBlockTexture();
    wall.wrapS = wall.wrapT = THREE.RepeatWrapping;
    wall.repeat.set(10, 6);
    return { wall, stone: stoneTexture(), circle: createRuneCircleTexture() };
  }, []);
  const crystalMats = useMemo(
    () =>
      Array.from(
        { length: nodes },
        () =>
          new THREE.MeshStandardMaterial({
            color: '#3a3248',
            emissive: DARK.clone(),
            emissiveIntensity: 0.4,
            metalness: 0.2,
            roughness: 0.15,
            transparent: true,
          }),
      ),
    [nodes],
  );
  const circleMat = useRef<THREE.MeshBasicMaterial>(null);
  const wave = useRef<THREE.Mesh>(null);
  const waveMat = useRef<THREE.MeshBasicMaterial>(null);
  const crystals = useRef<(THREE.Mesh | null)[]>([]);
  const lineMats = useRef<(THREE.MeshBasicMaterial | null)[]>([]);
  const sparks = useMemo(() => new SparkPool(120), []);
  const jolt = useJolt();
  const seen = useRef({ path: 1, sparked: 0, endAt: -Infinity });

  useFrame((state, delta) => {
    const now = performance.now();
    if (path.length > seen.current.path) {
      seen.current.path = path.length;
      const [x, y] = nodeAt(path[path.length - 1], nodes);
      sparks.burst(new THREE.Vector3(x, y, 0.12), VIOLET, 12, 0.6, { up: 0.2 });
    }
    if (sparked.length > seen.current.sparked) {
      seen.current.sparked = sparked.length;
      const [x, y] = nodeAt(sparked[sparked.length - 1], nodes);
      sparks.burst(new THREE.Vector3(x, y, 0.12), RED, 20, 1.1);
      jolt.kick(0.04);
    }
    if (end && seen.current.endAt === -Infinity) {
      seen.current.endAt = now;
      if (end === 'open') {
        for (let a = 0; a < 24; a++) {
          const t = (a / 24) * Math.PI * 2;
          sparks.burst(new THREE.Vector3(Math.cos(t) * RING_R, Math.sin(t) * RING_R, 0.1), BRIGHT, 3, 0.5, { up: 0, life: 1.3 });
        }
      } else {
        sparks.burst(new THREE.Vector3(0, 0, 0.1), RED, 40, 1.4, { spread: 2 });
        jolt.kick(0.06);
      }
    }
    const sinceEnd = now - seen.current.endAt;
    const flare = end === 'open' ? Math.min(1, sinceEnd / FLARE_MS) : 0;
    const burnt = end === 'broke' ? Math.min(1, sinceEnd / FLARE_MS) : 0;

    // The beat: a wave runs from the centre out to the ring in the second half of it, and the ring flares as it lands.
    const phase = beatPhase(now, beatMs);
    const flareNow = pulseAt(phase);
    if (wave.current && waveMat.current) {
      const run = phase >= 0.5 ? (phase - 0.5) * 2 : -1;
      wave.current.visible = run >= 0 && !end;
      wave.current.scale.setScalar(Math.max(0.01, run) * RING_R);
      waveMat.current.opacity = 0.15 + run * 0.45;
    }
    if (circleMat.current) {
      const base = 0.25 + flareNow * 0.45 + (path.length - 1) * 0.05;
      circleMat.current.opacity = end === 'open' ? (flare < 0.3 ? 1 : Math.max(0, 1 - (flare - 0.3) / 0.7)) : base;
      circleMat.current.color.copy(burnt > 0 ? RED : flare > 0 ? BRIGHT : VIOLET);
      if (burnt > 0) circleMat.current.opacity = 0.9 * (1 - burnt) + 0.15;
    }

    crystalMats.forEach((m, i) => {
      const crystal = crystals.current[i];
      const head = i === path[path.length - 1];
      const onPath = path.includes(i);
      const resonates = !end && pulsing.includes(i);
      let colour = DARK;
      let target = 0.4;
      if (sparked.includes(i)) {
        colour = RED;
        target = 0.5;
      } else if (onPath) {
        colour = head ? BRIGHT : VIOLET;
        target = head ? 3 : 2;
      } else if (resonates) {
        // Each resonating crystal pulses on its own offset from the beat; the true one in time.
        const k = pulsing.indexOf(i);
        colour = VIOLET;
        target = 0.6 + pulseAt(beatPhase(now, beatMs, offsets[k] ?? 0)) * 3.4 + (hovered === i ? 0.5 : 0);
      }
      if (end === 'open') target = 3.5 * (1 - flare);
      m.emissive.lerp(colour, Math.min(1, delta * 12));
      // A resonating pulse is followed closely, or the beat would blur.
      m.emissiveIntensity = resonates ? target : THREE.MathUtils.damp(m.emissiveIntensity, target, 10, delta);
      m.opacity = 1 - Math.max(0, flare - 0.5) * 2;
      if (crystal) {
        const [x, y] = nodeAt(i, nodes);
        crystal.rotation.y += delta * (resonates ? 1.6 : 0.5);
        const pop = resonates ? 1 + pulseAt(beatPhase(now, beatMs, offsets[pulsing.indexOf(i)] ?? 0)) * 0.35 : 1;
        crystal.scale.setScalar(pop);
        crystal.position.set(x * (1 + flare * 0.6), y * (1 + flare * 0.6), 0.12 + flare * 0.5);
      }
    });
    lineMats.current.forEach((m) => {
      if (m) m.opacity = end === 'open' ? Math.max(0, 1 - flare * 1.4) : burnt > 0 ? 0.3 : 0.85 + Math.sin(now * 0.01) * 0.1;
    });

    state.camera.position.x = Math.sin(now * 0.0004) * 0.04;
    state.camera.lookAt(0, 0, 0);
  });

  return (
    <>
      <CraftLights candle={[-1.7, 1.0, 1.6]} spot={[0, 1.6, 2.6]} spotIntensity={8} />
      <mesh position={[0, 0, -0.1]}>
        <planeGeometry args={[8, 5]} />
        <meshStandardMaterial map={textures.wall} color="#4e4a44" roughness={0.95} />
      </mesh>
      <group ref={jolt.group}>
        {/* The stone door the seal is burnt into */}
        <mesh position={[0, 0, -0.04]}>
          <circleGeometry args={[1.12, 64]} />
          <meshStandardMaterial map={textures.stone} color="#6c6670" roughness={0.9} />
        </mesh>
        <mesh position={[0, 0, 0.002]} raycast={() => null}>
          <planeGeometry args={[2.2, 2.2]} />
          <meshBasicMaterial
            ref={circleMat}
            map={textures.circle}
            color={VIOLET}
            transparent
            opacity={0.35}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </mesh>
        <Halo position={[0, 0, 0.02]} color="#8a5aff" scale={2.2} opacity={0.1} />
        {/* The beat's wave, running out to the ring */}
        <mesh ref={wave} position={[0, 0, 0.01]} raycast={() => null}>
          <ringGeometry args={[0.96, 1, 64]} />
          <meshBasicMaterial
            ref={waveMat}
            color={VIOLET}
            transparent
            opacity={0.3}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </mesh>

        {/* The traced lines of the sigil */}
        {path.slice(1).map((n, i) => {
          const [ax, ay] = nodeAt(path[i], nodes);
          const [bx, by] = nodeAt(n, nodes);
          const len = Math.hypot(bx - ax, by - ay);
          return (
            <mesh key={i} position={[(ax + bx) / 2, (ay + by) / 2, 0.06]} rotation={[0, 0, Math.atan2(by - ay, bx - ax)]} raycast={() => null}>
              <boxGeometry args={[len, 0.03, 0.01]} />
              <meshBasicMaterial
                ref={(m) => {
                  lineMats.current[i] = m;
                }}
                color={BRIGHT}
                transparent
                opacity={0.9}
                depthWrite={false}
                blending={THREE.AdditiveBlending}
                toneMapped={false}
              />
            </mesh>
          );
        })}

        {crystalMats.map((m, i) => (
          <mesh
            key={i}
            ref={(el) => {
              crystals.current[i] = el;
            }}
            material={m}
            onClick={(e) => {
              e.stopPropagation();
              if (!end && pulsing.includes(i)) onTouch(i);
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHovered(i);
              if (!end && pulsing.includes(i)) pointer.onPointerOver();
            }}
            onPointerOut={() => {
              setHovered((h) => (h === i ? null : h));
              pointer.onPointerOut();
            }}
          >
            <octahedronGeometry args={[NODE, 0]} />
            <mesh>
              <sphereGeometry args={[NODE_REACH, 12, 8]} />
              <meshBasicMaterial transparent opacity={0} depthWrite={false} />
            </mesh>
          </mesh>
        ))}
        <SparkField pool={sparks} max={120} gravity={-0.8} />
      </group>
      <Halo position={[-2.1, 1.2, 0.4]} color="#ff9a40" />
    </>
  );
};

export default SealScene;
