import { useMemo, useRef, type ComponentType } from 'react';
import { useFrame } from '@react-three/fiber';
import { Sparkles } from '@react-three/drei';
import * as THREE from 'three';
import { createSoftSpotTexture } from '../../pages/BattlePage/Arena3D/textures';
import { FoldingStrap, Rivet, createRibbonGeometry, noRaycast, useDisposable, useMetal, type BookFrame, type DressingProps } from './bookParts';
import { createSealTexture } from './bookTextures';

/*
  What makes each class's book its own. Every class supplies up to four parts:

  - Cover: fittings on the front board, drawn from the board's top face
    (x from the spine to the fore-edge, z across, y up off the leather).
  - Spine: fittings on the spine, from the hinge; the spine's outer face is at
    x = -cover. Hidden with the spine once the book lies open.
  - Fastening: what holds the book shut, in the closed book's frame.
  - Extras: anything else that belongs to the book, in the same frame.

  Cover fittings turn face-down with the board as the book opens and sink out
  of sight under the table, the way the front of a real open book does.
*/

export interface ClassDressing {
  Cover?: ComponentType<DressingProps>;
  Spine?: ComponentType<DressingProps>;
  Fastening?: ComponentType<DressingProps>;
  Extras?: ComponentType<DressingProps>;
}


/** How far a ribbon lying on the table floats above it, so it never flickers into the wood. */
const RIBBON_LIFT = 0.012;

/** Bookmark ribbons slipping out between the pages at the tail and trailing over the table. */
const BookmarkRibbons = ({ frame, ribbons }: { frame: BookFrame; ribbons: { x: number; color: string; drift: number }[] }) => {
  const { hingeY, pageDepth } = frame;
  const tail = pageDepth / 2;
  const geometries = useMemo(
    () =>
      ribbons.map(({ x, drift }) => {
        const curve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(x, hingeY - 0.04, tail - 0.08),
          new THREE.Vector3(x, hingeY - 0.04, tail + 0.04),
          new THREE.Vector3(x + drift * 0.2, hingeY * 0.45, tail + 0.16),
          new THREE.Vector3(x + drift * 0.5, RIBBON_LIFT, tail + 0.42),
          new THREE.Vector3(x + drift, RIBBON_LIFT, tail + 0.95),
        ]);
        // The smoothed curve overshoots where it meets the table; keep every
        // point above it, or the ribbon dips through the wood.
        const points = curve.getPoints(32).map((p) => p.setY(Math.max(p.y, RIBBON_LIFT)));
        return createRibbonGeometry(points, 0.085);
      }),
    [ribbons, hingeY, tail],
  );
  return (
    <group>
      {geometries.map((geometry, i) => (
        <mesh key={i} geometry={geometry} castShadow>
          <meshStandardMaterial color={ribbons[i].color} roughness={0.55} metalness={0.1} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  );
};

/* ===================== Warrior: an ironbound tome ===================== */

const useIron = () => useMetal('#5f6166', 0.62);

/** Plain iron straps across the board, flat corner plates and a low boss, all of it thin and dull with use. */
const WarriorCover = ({ frame }: DressingProps) => {
  const iron = useIron();
  const dark = useMetal('#2f3034', 0.6);
  const { boardWidth: bw, boardDepth: bd } = frame;
  const bandZ = [-bd * 0.3, bd * 0.3];
  const rivetXs = useMemo(() => {
    const xs: number[] = [];
    for (let x = 0.3; x < bw - 0.2; x += 0.6) xs.push(x);
    return xs;
  }, [bw]);
  const corners: [number, number, number, number][] = [
    [0, -bd / 2, 1, 1],
    [bw, -bd / 2, -1, 1],
    [0, bd / 2, 1, -1],
    [bw, bd / 2, -1, -1],
  ];
  // Set high, leaving the board below it for the name.
  const boss: [number, number] = [bw * 0.55, -bd * 0.1];

  return (
    <group>
      {bandZ.map((z) => (
        <group key={z}>
          <mesh position={[bw / 2, 0.01, z]} material={iron} castShadow>
            <boxGeometry args={[bw - 0.04, 0.02, 0.15]} />
          </mesh>
          {rivetXs.map((x) => (
            <Rivet key={x} position={[x, 0.02, z]} radius={0.028} material={dark} />
          ))}
        </group>
      ))}
      {corners.map(([cx, cz, sx, sz]) => (
        <group key={`${cx}${cz}`}>
          <mesh position={[cx + sx * 0.25, 0.01, cz + sz * 0.07]} material={iron} castShadow>
            <boxGeometry args={[0.5, 0.02, 0.14]} />
          </mesh>
          <mesh position={[cx + sx * 0.07, 0.01, cz + sz * 0.25]} material={iron} castShadow>
            <boxGeometry args={[0.14, 0.02, 0.5]} />
          </mesh>
          <Rivet position={[cx + sx * 0.08, 0.02, cz + sz * 0.08]} radius={0.028} material={dark} />
        </group>
      ))}
      <group position={[boss[0], 0, boss[1]]}>
        <mesh position={[0, 0.01, 0]} material={iron} castShadow>
          <cylinderGeometry args={[0.46, 0.47, 0.02, 40]} />
        </mesh>
        <mesh position={[0, 0.02, 0]} scale={[1, 0.3, 1]} material={iron} castShadow>
          <sphereGeometry args={[0.3, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
        </mesh>
        <mesh position={[0, 0.02 + 0.3 * 0.3, 0]} scale={[1, 0.6, 1]} material={dark} castShadow>
          <sphereGeometry args={[0.055, 12, 8]} />
        </mesh>
        {Array.from({ length: 8 }, (_, i) => {
          const a = (i / 8) * Math.PI * 2;
          return <Rivet key={i} position={[Math.cos(a) * 0.39, 0.02, Math.sin(a) * 0.39]} radius={0.025} material={dark} />;
        })}
      </group>
    </group>
  );
};

/** Raised bands across a heavy spine. */
const WarriorSpine = ({ frame }: DressingProps) => {
  const iron = useIron();
  const { cover, closedHeight, boardDepth: bd } = frame;
  return (
    <group>
      {[-0.36, -0.12, 0.12, 0.36].map((t) => (
        <mesh key={t} position={[-cover - 0.025, 0, t * bd]} material={iron} castShadow>
          <boxGeometry args={[0.05, closedHeight + 0.02, 0.16]} />
        </mesh>
      ))}
    </group>
  );
};

/** Two iron hasps over the fore-edge, each ending in a heavy ring. */
const WarriorFastening = ({ frame, progress }: DressingProps) => {
  const iron = useIron();
  const { boardWidth: bw, boardDepth: bd, closedHeight } = frame;
  const t = 0.05;
  return (
    <group>
      {[-bd * 0.3, bd * 0.3].map((z) => (
        <FoldingStrap
          key={z}
          anchor={[bw + t, 0, z]}
          height={closedHeight + t}
          reach={0.6}
          width={0.2}
          thickness={t}
          material={iron}
          progress={progress}
        >
          <mesh position={[-0.05, 0.02, 0]} rotation={[Math.PI / 2, 0, 0]} material={iron} castShadow>
            <torusGeometry args={[0.12, 0.03, 8, 20]} />
          </mesh>
          <Rivet position={[0.45, 0, 0]} radius={0.045} material={iron} />
        </FoldingStrap>
      ))}
    </group>
  );
};


const EMBER = '#ff7a2a';

/**
 * Embers still glowing in the burnt corners of the open pages, and the odd
 * spark drifting up off the book.
 */
const WarriorExtras = ({ frame, progress }: DressingProps) => {
  const glow = useDisposable(createSoftSpotTexture, []);
  const embers = useRef<(THREE.Sprite | null)[]>([]);
  const sparks = useRef<THREE.Group>(null);
  const { pageWidth: pw, pageDepth: pd, hingeY, boardWidth: bw } = frame;
  // The outer corners of both pages once the book lies open.
  const corners: [number, number][] = [
    [pw - 0.12, -pd / 2 + 0.12],
    [pw - 0.12, pd / 2 - 0.12],
    [-pw + 0.12, -pd / 2 + 0.12],
    [-pw + 0.12, pd / 2 - 0.12],
  ];

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const open = progress.current.cover;
    embers.current.forEach((s, i) => {
      if (!s) return;
      const flicker = 0.55 + 0.25 * Math.sin(t * 5.3 + i * 2.1) + 0.15 * Math.sin(t * 11.7 + i);
      (s.material as THREE.SpriteMaterial).opacity = open > 0.9 ? flicker * 0.35 : 0;
    });
    if (sparks.current) sparks.current.position.x = (bw / 2) * (1 - open);
  });

  return (
    <group>
      {corners.map(([x, z], i) => (
        <sprite raycast={noRaycast}
          key={i}
          ref={(s) => {
            embers.current[i] = s;
          }}
          position={[x, hingeY + 0.12, z]}
          scale={[0.38, 0.38, 1]}
        >
          <spriteMaterial map={glow} color={EMBER} transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
        </sprite>
      ))}
      <group ref={sparks} position={[0, 0.9, 0]}>
        <Sparkles raycast={noRaycast} count={16} scale={[bw * 1.6, 1.6, pd]} size={2.4} speed={0.55} opacity={0.85} color="#ffa04a" noise={1.5} />
      </group>
    </group>
  );
};

/* ===================== Rogue: a wrapped leather journal ===================== */

const useSilver = () => useMetal('#b9bfc4', 0.3, 0.9);

/** A blade outline for the dagger, tip toward +y. */
const bladeShape = () => {
  const s = new THREE.Shape();
  s.moveTo(-0.065, 0);
  s.lineTo(0.065, 0);
  s.lineTo(0.045, 1.05);
  s.lineTo(0, 1.32);
  s.lineTo(-0.045, 1.05);
  s.closePath();
  return s;
};

/** A dagger tucked under two leather loops on the board. */
const RogueCover = ({ frame }: DressingProps) => {
  const silver = useSilver();
  const steel = useMetal('#d3d7dc', 0.22, 0.85);
  const grip = useDisposable(() => new THREE.MeshStandardMaterial({ color: '#2a1a10', roughness: 0.8 }), []);
  const loop = useDisposable(() => new THREE.MeshStandardMaterial({ color: '#3a2618', roughness: 0.75 }), []);
  const blade = useDisposable(
    () => new THREE.ExtrudeGeometry(bladeShape(), { depth: 0.018, bevelEnabled: true, bevelThickness: 0.006, bevelSize: 0.008, bevelSegments: 1 }),
    [],
  );
  const { boardWidth: bw, boardDepth: bd } = frame;
  const x = bw * 0.13;

  return (
    <group position={[x, 0, bd * 0.08]}>
      {/* Laid flat, point toward the head of the book */}
      <mesh geometry={blade} material={steel} position={[0, 0.03, 0.1]} rotation={[-Math.PI / 2, 0, 0]} castShadow />
      <mesh position={[0, 0.045, 0.12]} material={silver} castShadow>
        <boxGeometry args={[0.44, 0.05, 0.07]} />
      </mesh>
      <mesh position={[0, 0.045, 0.37]} rotation={[Math.PI / 2, 0, 0]} material={grip} castShadow>
        <cylinderGeometry args={[0.045, 0.045, 0.44, 12]} />
      </mesh>
      <mesh position={[0, 0.05, 0.62]} material={silver} castShadow>
        <sphereGeometry args={[0.07, 14, 10]} />
      </mesh>
      {[-0.55, 0.38].map((z) => (
        <group key={z} position={[0, 0, z]}>
          <mesh position={[0, 0.085, 0]} material={loop} castShadow>
            <boxGeometry args={[0.36, 0.025, 0.11]} />
          </mesh>
          <Rivet position={[-0.16, 0.098, 0]} radius={0.025} material={silver} />
          <Rivet position={[0.16, 0.098, 0]} radius={0.025} material={silver} />
        </group>
      ))}
    </group>
  );
};

/** A wide leather flap wrapped round the fore-edge, held by a silver concho. */
const RogueFastening = ({ frame, progress, leather }: DressingProps) => {
  const silver = useSilver();
  const { boardWidth: bw, boardDepth: bd, closedHeight } = frame;
  const t = 0.035;
  return (
    <FoldingStrap
      anchor={[bw + t, 0, 0]}
      height={closedHeight + t}
      reach={bw * 0.34}
      width={bd * 0.88}
      thickness={t}
      material={leather}
      progress={progress}
    >
      <group position={[0.22, 0, 0]}>
        <mesh position={[0, 0.018, 0]} material={silver} castShadow>
          <cylinderGeometry args={[0.17, 0.18, 0.036, 24]} />
        </mesh>
        <mesh position={[0, 0.036, 0]} rotation={[Math.PI / 2, 0, 0]} material={silver}>
          <torusGeometry args={[0.15, 0.018, 8, 24]} />
        </mesh>
        <mesh position={[0, 0.04, 0]} scale={[1, 0.5, 1]} material={silver}>
          <sphereGeometry args={[0.06, 12, 8]} />
        </mesh>
      </group>
    </FoldingStrap>
  );
};

const MIST_PUFFS = 7;

/**
 * Ribbons trailing from the pages, a low dark haze clinging to the table round the book,
 * and a few sickly green wisps of whatever was spilled on it.
 */
const RogueExtras = ({ frame, progress }: DressingProps) => {
  const glow = useDisposable(createSoftSpotTexture, []);
  const puffs = useRef<(THREE.Mesh | null)[]>([]);
  const fumes = useRef<THREE.Group>(null);
  const { boardWidth: bw, boardDepth: bd } = frame;

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const open = progress.current.cover;
    const cx = (bw / 2) * (1 - open);
    const rx = bw * (0.7 + open * 0.5);
    puffs.current.forEach((s, i) => {
      if (!s) return;
      const a = t * 0.07 + (i / MIST_PUFFS) * Math.PI * 2;
      s.position.set(cx + Math.cos(a) * rx, 0.015, Math.sin(a) * bd * 0.6);
      const swell = 2.2 + Math.sin(t * 0.4 + i * 1.3) * 0.5;
      s.scale.set(swell * 1.4, swell, 1);
      (s.material as THREE.MeshBasicMaterial).opacity = 0.5 + Math.sin(t * 0.5 + i) * 0.12;
    });
    if (fumes.current) fumes.current.position.x = cx;
  });

  return (
    <group>
      <BookmarkRibbons
        frame={frame}
        ribbons={[
          { x: 0.32, color: '#5c1a1a', drift: 0.15 },
          { x: 0.46, color: '#27402f', drift: 0.35 },
          { x: 0.58, color: '#16120f', drift: 0.55 },
        ]}
      />
      {/* Lying flat on the table, so the book itself covers whatever drifts under it */}
      {Array.from({ length: MIST_PUFFS }, (_, i) => (
        <mesh
          key={i}
          raycast={noRaycast}
          ref={(m) => {
            puffs.current[i] = m;
          }}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[1, 1]} />
          <meshBasicMaterial map={glow} color="#050605" transparent depthWrite={false} />
        </mesh>
      ))}
      <group ref={fumes} position={[0, 0.7, 0]}>
        <Sparkles raycast={noRaycast} count={14} scale={[bw * 1.5, 1.2, bd * 0.9]} size={2.2} speed={0.25} opacity={0.6} color="#9be05a" noise={0.8} />
      </group>
    </group>
  );
};

/* ===================== Mage: a fine, enchanted volume ===================== */

const MAGIC = '#7fb2ff';
const useGold = () => useMetal('#d9ab55', 0.25, 1);

/** Fine gold filigree at the corners and a glowing crystal in a gold setting. */
const MageCover = ({ frame }: DressingProps) => {
  const gold = useGold();
  const glow = useDisposable(createSoftSpotTexture, []);
  const crystal = useRef<THREE.MeshStandardMaterial>(null);
  const halo = useRef<THREE.SpriteMaterial>(null);
  const { boardWidth: bw, boardDepth: bd } = frame;
  const centre: [number, number] = [bw / 2, -bd * 0.06];
  const corners: [number, number, number, number][] = [
    [0, -bd / 2, 1, 1],
    [bw, -bd / 2, -1, 1],
    [0, bd / 2, 1, -1],
    [bw, bd / 2, -1, -1],
  ];

  useFrame(({ clock }) => {
    const pulse = 0.5 + 0.5 * Math.sin(clock.elapsedTime * 1.8);
    if (crystal.current) crystal.current.emissiveIntensity = 0.9 + pulse * 1.2;
    if (halo.current) halo.current.opacity = 0.35 + pulse * 0.4;
  });

  return (
    <group>
      {corners.map(([cx, cz, sx, sz]) => (
        // The arc is built in the (+x, -z) quarter and mirrored into each corner.
        <group key={`${cx}${cz}`} position={[cx + sx * 0.42, 0.012, cz + sz * 0.42]} scale={[-sx, 1, sz]}>
          {[0.3, 0.2].map((r) => (
            <mesh key={r} rotation={[-Math.PI / 2, 0, 0]} material={gold}>
              <torusGeometry args={[r, 0.014, 6, 24, Math.PI / 2]} />
            </mesh>
          ))}
          <mesh position={[0.21, 0.01, -0.21]} material={gold}>
            <sphereGeometry args={[0.035, 10, 8]} />
          </mesh>
        </group>
      ))}
      <group position={[centre[0], 0, centre[1]]}>
        <mesh position={[0, 0.03, 0]} rotation={[Math.PI / 2, 0, 0]} material={gold} castShadow>
          <torusGeometry args={[0.3, 0.04, 10, 40]} />
        </mesh>
        {Array.from({ length: 6 }, (_, i) => {
          const a = (i / 6) * Math.PI * 2;
          return (
            <mesh key={i} position={[Math.cos(a) * 0.27, 0.07, Math.sin(a) * 0.27]} rotation={[0, -a, 0.5]} material={gold}>
              <boxGeometry args={[0.03, 0.1, 0.03]} />
            </mesh>
          );
        })}
        <mesh position={[0, 0.1, 0]} castShadow>
          <cylinderGeometry args={[0.15, 0.27, 0.16, 8]} />
          <meshStandardMaterial
            ref={crystal}
            color={MAGIC}
            emissive={MAGIC}
            emissiveIntensity={1.2}
            roughness={0.08}
            metalness={0.2}
            flatShading
            toneMapped={false}
          />
        </mesh>
        <sprite raycast={noRaycast} position={[0, 0.25, 0]} scale={[1.3, 1.3, 1]}>
          <spriteMaterial
            ref={halo}
            map={glow}
            color={MAGIC}
            transparent
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </sprite>
      </group>
    </group>
  );
};

/** Gold bands round the spine. */
const MageSpine = ({ frame }: DressingProps) => {
  const gold = useGold();
  const { cover, closedHeight, boardDepth: bd } = frame;
  return (
    <group>
      {[-0.42, -0.3, 0.3, 0.42].map((t) => (
        <mesh key={t} position={[-cover - 0.006, 0, t * bd]} material={gold}>
          <boxGeometry args={[0.012, closedHeight, 0.035]} />
        </mesh>
      ))}
    </group>
  );
};

/**
 * No clasp: a ward. A ring of runes hangs over the closed cover, turning, with
 * a seam of light along the fore-edge; opening the book breaks it — the ring
 * spreads and fades.
 */
const MageFastening = ({ frame, progress }: DressingProps) => {
  const seal = useDisposable(createSealTexture, []);
  const ring = useRef<THREE.Mesh>(null);
  const ringMat = useRef<THREE.MeshBasicMaterial>(null);
  const seamMat = useRef<THREE.MeshBasicMaterial>(null);
  const { boardWidth: bw, boardDepth: bd, closedHeight } = frame;

  useFrame(({ clock }, delta) => {
    const k = progress.current.fastening;
    const flicker = 0.85 + Math.sin(clock.elapsedTime * 3.1) * 0.1;
    if (ring.current) {
      ring.current.rotation.z += delta * 0.35;
      ring.current.scale.setScalar(1 + k * 1.8);
      ring.current.visible = k < 0.99;
    }
    if (ringMat.current) ringMat.current.opacity = (1 - k) * 0.8 * flicker;
    if (seamMat.current) seamMat.current.opacity = (1 - k) * 0.9 * flicker;
  });

  return (
    <group>
      <mesh ref={ring} raycast={noRaycast} position={[bw / 2, closedHeight + 0.14, -bd * 0.06]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.9, 1.9]} />
        <meshBasicMaterial
          ref={ringMat}
          map={seal}
          color={MAGIC}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
      <mesh raycast={noRaycast} position={[bw + 0.012, closedHeight / 2, 0]}>
        <boxGeometry args={[0.012, 0.035, bd * 0.86]} />
        <meshBasicMaterial
          ref={seamMat}
          color={MAGIC}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
};

/** Motes of light rising off the pages once the book lies open. */
const MageExtras = ({ frame, progress }: DressingProps) => {
  const motes = useRef<THREE.Group>(null);
  const { hingeY, pageWidth, pageDepth } = frame;

  useFrame(() => {
    if (motes.current) motes.current.visible = progress.current.cover > 0.6;
  });

  return (
    <group>
      <group ref={motes} position={[0, hingeY + 0.5, 0]}>
        <Sparkles raycast={noRaycast} count={40} scale={[pageWidth * 2, 1, pageDepth]} size={3} speed={0.4} opacity={0.7} color="#a8c8ff" />
      </group>
      <BookmarkRibbons frame={frame} ribbons={[{ x: 0.4, color: '#c9a24e', drift: 0.3 }]} />
    </group>
  );
};

/* DB class ids: 1=Warrior, 2=Rogue, 3=Mage */
export const DRESSINGS: Record<number, ClassDressing> = {
  1: { Cover: WarriorCover, Spine: WarriorSpine, Fastening: WarriorFastening, Extras: WarriorExtras },
  2: { Cover: RogueCover, Fastening: RogueFastening, Extras: RogueExtras },
  3: { Cover: MageCover, Spine: MageSpine, Fastening: MageFastening, Extras: MageExtras },
};
