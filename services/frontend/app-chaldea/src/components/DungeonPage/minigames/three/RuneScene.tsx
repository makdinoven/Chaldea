import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import type { RunesParams } from '../../../../api/dungeons';
import { createSwirlTexture } from '../../../DungeonBoard3D/decorTextures';
import { createWallBlockTexture } from '../../../DungeonBoard3D/stoneTextures';
import type { RuneOutcome, RunePhase } from '../useRunes';
import { CraftLights, Halo, SparkField, SparkPool, pointer, useJolt } from './craftKit';
import { glowTexture, runeTextures, stoneTexture } from './craftTextures';

/*
  The illusory wall in 3D: a crypt wall, and in it a panel of nine rune stones
  that is not quite there — a slow shimmer runs over it. The runes flare violet
  one by one; then the mage touches them back. A true touch glows blue, a wrong
  one red and the wall shudders. Dispelled, the stones fade into motes and a
  dark passage opens behind them.
*/

export const RUNE_CAMERA = { position: [0, 0.05, 3.3] as [number, number, number], fov: 32 };

const STONE = 0.44;
const GAP = 0.1;
const STEP = STONE + GAP;
const GRID_Y = 0.02;
const FADE_MS = 1100;

const VIOLET = new THREE.Color('#b07aff');
const BLUE = new THREE.Color('#76a6ff');
const RED = new THREE.Color('#ff5a4a');
const DIM = new THREE.Color('#5a4a7a');

const stoneAt = (g: number): [number, number] => [((g % 3) - 1) * STEP, GRID_Y + (1 - Math.floor(g / 3)) * STEP];

interface RuneSceneProps {
  params: RunesParams;
  phase: RunePhase;
  lit: number | null;
  flash: { glyph: number; good: boolean } | null;
  outcome: RuneOutcome | null;
  onTouch: (glyph: number) => void;
}

const RuneScene = ({ params, phase, lit, flash, outcome, onTouch }: RuneSceneProps) => {
  const [hovered, setHovered] = useState<number | null>(null);
  const textures = useMemo(() => {
    const wall = createWallBlockTexture();
    wall.wrapS = wall.wrapT = THREE.RepeatWrapping;
    wall.repeat.set(11, 7);
    return { wall, stone: stoneTexture(), swirl: createSwirlTexture() };
  }, []);
  const materials = useMemo(
    () =>
      Array.from({ length: params.glyphs }, (_, g) => {
        const rune = runeTextures(g);
        // The rune is cut on a plate over the stone's face: its groove, and the glow running in it.
        return new THREE.MeshStandardMaterial({
          map: rune.groove,
          emissiveMap: rune.glow,
          emissive: DIM.clone(),
          emissiveIntensity: 0.25,
          roughness: 0.9,
          transparent: true,
          depthWrite: false,
        });
      }),
    [params.glyphs, textures],
  );
  const stoneMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ map: textures.stone, color: '#a49e94', roughness: 0.88, transparent: true }),
    [textures],
  );
  const stones = useRef<(THREE.Group | null)[]>([]);
  const shimmer = useRef<THREE.Mesh>(null);
  const shimmerMat = useRef<THREE.MeshBasicMaterial>(null);
  const runeLight = useRef<THREE.PointLight>(null);
  const halo = useRef<THREE.Sprite>(null);
  const glow = useMemo(() => glowTexture(), []);
  const sparks = useMemo(() => new SparkPool(80), []);
  const jolt = useJolt();
  const seen = useRef<{ flash: typeof flash; outcomeAt: number }>({ flash: null, outcomeAt: -Infinity });

  useFrame((state, delta) => {
    const now = performance.now();
    // What just happened: a touch flashes, a wrong one jolts, the end throws motes.
    if (flash && flash !== seen.current.flash) {
      seen.current.flash = flash;
      const [x, y] = stoneAt(flash.glyph);
      sparks.burst(new THREE.Vector3(x, y, 0.15), flash.good ? BLUE : RED, flash.good ? 10 : 16, flash.good ? 0.6 : 1);
      if (!flash.good) jolt.kick(0.035);
    }
    if (outcome && seen.current.outcomeAt === -Infinity) {
      seen.current.outcomeAt = now;
      if (outcome === 'open') {
        for (let g = 0; g < params.glyphs; g++) {
          const [x, y] = stoneAt(g);
          sparks.burst(new THREE.Vector3(x, y, 0.1), VIOLET, 7, 0.5, { up: 0.2, life: 1.2 });
        }
      }
    }
    const dispelled = outcome === 'open' ? Math.min(1, (now - seen.current.outcomeAt) / FADE_MS) : 0;

    materials.forEach((m, g) => {
      let colour = DIM;
      let target = 0.25;
      if (lit === g) {
        colour = VIOLET;
        target = 3.2;
      } else if (flash?.glyph === g) {
        colour = flash.good ? BLUE : RED;
        target = 2.6;
      } else if (outcome && outcome !== 'open') {
        colour = RED;
        target = 0.8;
      } else if (phase === 'input' && hovered === g) {
        colour = VIOLET;
        target = 0.9;
      } else if (phase === 'input') {
        target = 0.45;
      }
      m.emissive.lerp(colour, Math.min(1, delta * 14));
      m.emissiveIntensity = THREE.MathUtils.damp(m.emissiveIntensity, target, 12, delta);
      m.opacity = 1 - dispelled;
      stoneMaterial.opacity = 1 - dispelled;
      const stone = stones.current[g];
      if (stone) {
        const [x, y] = stoneAt(g);
        // The wall is not quite there: each stone drifts a hair in and out.
        stone.position.set(x, y, Math.sin(now * 0.0013 + g * 1.7) * 0.012 - dispelled * 0.4);
        stone.scale.setScalar(1 - dispelled * 0.3);
        stone.visible = dispelled < 1;
      }
    });

    // The violet light and its halo ride the lit rune.
    if (halo.current) {
      const at = lit ?? flash?.glyph ?? null;
      const m = halo.current.material as THREE.SpriteMaterial;
      m.opacity = THREE.MathUtils.damp(m.opacity, at !== null ? 0.55 : 0, 14, delta);
      if (at !== null) {
        const [x, y] = stoneAt(at);
        halo.current.position.set(x, y, 0.1);
        m.color.copy(lit !== null ? VIOLET : flash?.good ? BLUE : RED);
      }
    }
    if (runeLight.current) {
      const at = lit ?? flash?.glyph ?? null;
      runeLight.current.intensity = THREE.MathUtils.damp(runeLight.current.intensity, at !== null ? 6 : 0, 14, delta);
      if (at !== null) {
        const [x, y] = stoneAt(at);
        runeLight.current.position.set(x, y, 0.6);
        runeLight.current.color.copy(lit !== null ? VIOLET : flash?.good ? BLUE : RED);
      }
    }

    // The shimmer over the panel: slow, flaring as the illusion breaks.
    if (shimmer.current && shimmerMat.current) {
      shimmer.current.rotation.z += delta * 0.15;
      shimmerMat.current.opacity = dispelled > 0 ? 0.35 * (1 - dispelled) : 0.09 + Math.sin(now * 0.002) * 0.03;
    }

    state.camera.position.x = Math.sin(now * 0.0004) * 0.05;
    state.camera.position.z = RUNE_CAMERA.position[2] - dispelled * 0.25;
    state.camera.lookAt(0, 0.05, 0);
  });

  const panel = STEP * 3 + 0.12;
  return (
    <>
      <CraftLights candle={[-1.7, 1.1, 1.5]} />
      <pointLight ref={runeLight} distance={2.2} decay={1} intensity={0} />
      {/* The crypt wall */}
      <mesh position={[0, 0, -0.3]}>
        <planeGeometry args={[8, 5]} />
        <meshStandardMaterial map={textures.wall} color="#6c6862" roughness={0.95} />
      </mesh>
      {/* The passage behind the illusion */}
      <mesh position={[0, GRID_Y, -0.26]}>
        <planeGeometry args={[panel, panel]} />
        <meshBasicMaterial color="#020203" />
      </mesh>
      <Halo position={[0, GRID_Y + 0.1, -0.24]} color="#6a7cff" scale={0.9} opacity={0.12} />

      <group ref={jolt.group}>
        {/* The frame round the panel */}
        {(
          [
            [0, GRID_Y + panel / 2 + 0.06, panel + 0.24, 0.12],
            [0, GRID_Y - panel / 2 - 0.06, panel + 0.24, 0.12],
            [-panel / 2 - 0.06, GRID_Y, 0.12, panel],
            [panel / 2 + 0.06, GRID_Y, 0.12, panel],
          ] as const
        ).map(([x, y, w, h]) => (
          <mesh key={`${x},${y}`} position={[x, y, -0.18]}>
            <boxGeometry args={[w, h, 0.22]} />
            <meshStandardMaterial map={textures.stone} color="#857f74" roughness={0.9} />
          </mesh>
        ))}

        {materials.map((m, g) => (
          <group
            key={g}
            ref={(el) => {
              stones.current[g] = el;
            }}
            onClick={(e) => {
              e.stopPropagation();
              onTouch(g);
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHovered(g);
              if (phase === 'input') pointer.onPointerOver();
            }}
            onPointerOut={() => {
              setHovered((h) => (h === g ? null : h));
              pointer.onPointerOut();
            }}
          >
            <RoundedBox args={[STONE, STONE, 0.16]} radius={0.035} smoothness={3} material={stoneMaterial} />
            <mesh position={[0, 0, 0.081]} material={m}>
              <planeGeometry args={[STONE * 0.8, STONE * 0.8]} />
            </mesh>
          </group>
        ))}

        <mesh ref={shimmer} position={[0, GRID_Y, 0.12]} raycast={() => null}>
          <planeGeometry args={[panel * 1.1, panel * 1.1]} />
          <meshBasicMaterial
            ref={shimmerMat}
            map={textures.swirl}
            color="#a58aff"
            transparent
            opacity={0.1}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </mesh>
        <sprite ref={halo} scale={[0.9, 0.9, 1]} raycast={() => null}>
          <spriteMaterial map={glow} transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
        </sprite>
        <SparkField pool={sparks} max={80} gravity={-1.2} />
      </group>
      <Halo position={[-2.1, 1.3, 0.4]} color="#ff9a40" />
    </>
  );
};

export default RuneScene;
