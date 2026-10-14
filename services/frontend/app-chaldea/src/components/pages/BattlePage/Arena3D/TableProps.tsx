import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import {
  createCardBackTexture,
  createCoinFaceTexture,
  createDieFaceTexture,
  createFeatherTexture,
  createParchmentTexture,
  createRuneGlyphTexture,
  createSoftSpotTexture,
  createTurnTallyTexture,
  createWaxSealTexture,
  createWoodSplitTexture,
  TALLY_WORLD_DEPTH,
  TALLY_WORLD_WIDTH,
} from "./textures";
import { TURN_DURATION_MS } from "./arenaTypes";

type Vec3 = [number, number, number];

/** A canvas texture created once per mount and freed on unmount. */
const useOwnedTexture = (create: () => THREE.Texture) => {
  const texture = useMemo(create, [create]);
  useEffect(() => () => texture.dispose(), [texture]);
  return texture;
};

const BRASS = { color: "#9a7432", metalness: 0.75, roughness: 0.35 } as const;

// --- Dice of fate ---

const DIE_SIZE = 0.42;
const ROLL_MS = 1300;
const FLASH_MS = 1400;
const DROP_HEIGHT = 2.4;
// BoxGeometry face order is +x, -x, +y, -y, +z, -z; opposite faces sum to seven.
const FACE_VALUES = [3, 4, 6, 1, 2, 5];
// Idle rest poses before the first critical roll (3 and 5 face up).
const IDLE_ROTATIONS: Vec3[] = [
  [0, 0.4, Math.PI / 2],
  [Math.PI / 2, -0.3, 0],
];
const ROLL_SPIN: Vec3[] = [
  [Math.PI * 6, Math.PI * 3, Math.PI * 4],
  [Math.PI * 4, Math.PI * 5, Math.PI * 6],
];

interface DieProps {
  index: number;
  rest: Vec3;
  rollAt: number | null;
  materials: THREE.Material[];
}

/** A bone die: tumbles in from above on a critical hit and settles with the 6 up. */
const Die = ({ index, rest, rollAt, materials }: DieProps) => {
  const mesh = useRef<THREE.Mesh>(null);
  const hasRolled = rollAt !== null;

  useFrame(() => {
    const m = mesh.current;
    if (!m) return;
    const yaw = index === 0 ? 0.35 : -0.5;
    if (!hasRolled) {
      const [rx, ry, rz] = IDLE_ROTATIONS[index];
      m.position.set(rest[0], rest[1] + DIE_SIZE / 2, rest[2]);
      m.rotation.set(rx, ry, rz);
      return;
    }
    const k = Math.min(1, (performance.now() - rollAt) / ROLL_MS);
    const ease = 1 - (1 - k) ** 3;
    // Thrown in from the board's side, bouncing twice before it settles.
    const fromX = rest[0] - 2.2 - index * 0.5;
    const fromZ = rest[2] - 1.2 + index * 0.6;
    const bounce = Math.abs(Math.sin(k * Math.PI * 2.5)) * DROP_HEIGHT * (1 - k) ** 1.6;
    m.position.set(
      THREE.MathUtils.lerp(fromX, rest[0], ease),
      rest[1] + DIE_SIZE / 2 + bounce,
      THREE.MathUtils.lerp(fromZ, rest[2], ease),
    );
    const [sx, sy, sz] = ROLL_SPIN[index];
    m.rotation.set(sx * (1 - ease), yaw + sy * (1 - ease), sz * (1 - ease));
  });

  return (
    <mesh ref={mesh} material={materials}>
      <boxGeometry args={[DIE_SIZE, DIE_SIZE, DIE_SIZE]} />
    </mesh>
  );
};

const DicePair = ({ position, rollAt }: { position: Vec3; rollAt: number | null }) => {
  const faces = useMemo(() => FACE_VALUES.map(createDieFaceTexture), []);
  const materials = useMemo(
    () => faces.map((map) => new THREE.MeshStandardMaterial({ map, roughness: 0.55 })),
    [faces],
  );
  const glow = useMemo(createSoftSpotTexture, []);
  const flash = useRef<THREE.MeshBasicMaterial>(null);

  useEffect(
    () => () => {
      faces.forEach((t) => t.dispose());
      materials.forEach((m) => m.dispose());
      glow.dispose();
    },
    [faces, materials, glow],
  );

  // A gold flare under the dice once they settle on double six.
  useFrame(() => {
    if (!flash.current) return;
    if (rollAt === null) {
      flash.current.opacity = 0;
      return;
    }
    const k = (performance.now() - rollAt - ROLL_MS * 0.85) / FLASH_MS;
    flash.current.opacity = k > 0 && k < 1 ? Math.sin(k * Math.PI) * 0.9 : 0;
  });

  const restA: Vec3 = [position[0] - 0.3, position[1], position[2]];
  const restB: Vec3 = [position[0] + 0.3, position[1], position[2] + 0.25];

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[position[0], 0.01, position[2] + 0.12]}>
        <planeGeometry args={[2.4, 2.4]} />
        <meshBasicMaterial
          ref={flash}
          map={glow}
          color="#f0d95c"
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
      <Die index={0} rest={restA} rollAt={rollAt} materials={materials} />
      <Die index={1} rest={restB} rollAt={rollAt} materials={materials} />
    </group>
  );
};

// --- Coins ---

const COIN_RADIUS = 0.26;
const COIN_THICKNESS = 0.05;
const COIN_STACKS: { offset: [number, number]; count: number }[] = [
  { offset: [0, 0], count: 7 },
  { offset: [0.6, 0.15], count: 4 },
  { offset: [0.2, 0.62], count: 2 },
];
const LOOSE_COINS: { offset: [number, number]; tilt: number }[] = [
  { offset: [-0.55, 0.35], tilt: 0.1 },
  { offset: [0.95, 0.65], tilt: -0.15 },
  { offset: [-0.3, -0.5], tilt: 0.25 },
  { offset: [0.75, -0.45], tilt: 0 },
];

const CoinPile = ({ position }: { position: Vec3 }) => {
  const face = useMemo(createCoinFaceTexture, []);
  const materials = useMemo(() => {
    const edge = new THREE.MeshStandardMaterial({ color: "#b8892c", metalness: 0.8, roughness: 0.35 });
    const cap = new THREE.MeshStandardMaterial({ map: face, metalness: 0.75, roughness: 0.35 });
    // Cylinder material order: side, top, bottom.
    return [edge, cap, cap];
  }, [face]);

  useEffect(
    () => () => {
      face.dispose();
      materials.forEach((m) => m.dispose());
    },
    [face, materials],
  );

  return (
    <group position={position}>
      {COIN_STACKS.flatMap((stack, s) =>
        Array.from({ length: stack.count }, (_, i) => (
          <mesh
            key={`s${s}-${i}`}
            material={materials}
            position={[stack.offset[0] + Math.sin(i * 2.1 + s) * 0.02, COIN_THICKNESS * (i + 0.5), stack.offset[1] + Math.cos(i * 1.7 + s) * 0.02]}
            rotation={[0, i * 0.7, 0]}
          >
            <cylinderGeometry args={[COIN_RADIUS, COIN_RADIUS, COIN_THICKNESS, 24]} />
          </mesh>
        )),
      )}
      {LOOSE_COINS.map((coin, i) => (
        <mesh
          key={`l${i}`}
          material={materials}
          position={[coin.offset[0], COIN_THICKNESS / 2 + Math.abs(coin.tilt) * 0.2, coin.offset[1]]}
          rotation={[coin.tilt, i, coin.tilt * 0.5]}
        >
          <cylinderGeometry args={[COIN_RADIUS, COIN_RADIUS, COIN_THICKNESS, 24]} />
        </mesh>
      ))}
    </group>
  );
};

// --- Hourglass ---

const GLASS_PROFILE: [number, number][] = [
  [0.06, 0.08],
  [0.42, 0.14],
  [0.48, 0.4],
  [0.1, 0.92],
  [0.06, 1.0],
  [0.1, 1.08],
  [0.48, 1.6],
  [0.42, 1.86],
  [0.06, 1.92],
];
const SAND_COLOR = "#d8b26a";

const remaining = (deadline: number | null) =>
  deadline === null ? 1 : THREE.MathUtils.clamp((deadline - Date.now()) / TURN_DURATION_MS, 0, 1);

/** An hourglass whose sand drains with the current turn's time. */
const Hourglass = ({ position, turnDeadline }: { position: Vec3; turnDeadline: number | null }) => {
  const glassProfile = useMemo(() => GLASS_PROFILE.map(([r, h]) => new THREE.Vector2(r, h)), []);
  const topSand = useRef<THREE.Mesh>(null);
  const bottomSand = useRef<THREE.Mesh>(null);
  const stream = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    const left = remaining(turnDeadline);
    topSand.current?.scale.set(Math.max(0.05, left) ** 0.5, Math.max(0.02, left), Math.max(0.05, left) ** 0.5);
    bottomSand.current?.scale.set(1, Math.max(0.05, 1 - left), 1);
    if (stream.current) {
      stream.current.visible = left > 0.001 && left < 0.999;
      stream.current.scale.x = 1 + Math.sin(clock.elapsedTime * 20) * 0.15;
    }
  });

  return (
    <group position={position} rotation={[0, 0.5, 0]}>
      {/* Brass frame: a solid foot, an open ring on top (so the sand shows from above) and posts */}
      <mesh position={[0, 0.04, 0]}>
        <cylinderGeometry args={[0.62, 0.66, 0.09, 24]} />
        <meshStandardMaterial color="#9a7432" metalness={0.75} roughness={0.35} />
      </mesh>
      <mesh position={[0, 1.96, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.55, 0.06, 10, 28]} />
        <meshStandardMaterial color="#9a7432" metalness={0.75} roughness={0.35} />
      </mesh>
      {[0, 1, 2].map((i) => {
        const a = (i / 3) * Math.PI * 2;
        return (
          <mesh key={i} position={[Math.cos(a) * 0.55, 1.0, Math.sin(a) * 0.55]}>
            <cylinderGeometry args={[0.035, 0.035, 1.9, 8]} />
            <meshStandardMaterial color="#9a7432" metalness={0.75} roughness={0.35} />
          </mesh>
        );
      })}
      {/* Its own small warm light so it reads beside the board */}
      <pointLight position={[0.8, 2.2, 0.8]} color="#ffb35c" intensity={6} distance={4} decay={1.5} />

      {/* Sand: a cone draining from the upper bulb, a mound growing in the lower */}
      <mesh ref={topSand} position={[0, 1.12, 0]} rotation={[Math.PI, 0, 0]}>
        <coneGeometry args={[0.38, 0.5, 20, 1, false]} />
        <meshStandardMaterial color={SAND_COLOR} roughness={0.9} />
      </mesh>
      <group position={[0, 0.14, 0]}>
        <mesh ref={bottomSand} position={[0, 0.2, 0]}>
          <coneGeometry args={[0.4, 0.4, 20]} />
          <meshStandardMaterial color={SAND_COLOR} roughness={0.9} />
        </mesh>
      </group>
      <mesh ref={stream} position={[0, 0.75, 0]}>
        <cylinderGeometry args={[0.012, 0.012, 0.5, 6]} />
        <meshStandardMaterial color={SAND_COLOR} roughness={0.9} />
      </mesh>

      {/* Glass last, so the sand shows through it */}
      <mesh>
        <latheGeometry args={[glassProfile, 32]} />
        <meshStandardMaterial
          color="#d8e8ff"
          transparent
          opacity={0.3}
          roughness={0.05}
          metalness={0.1}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
};


// --- Decks of fate ---

const CARD_W = 0.62;
const CARD_D = 0.88;
const CARD_T = 0.012;

/** A face-down deck with a couple of cards cast beside it. */
const Deck = ({ position, rotation, cast }: { position: Vec3; rotation: number; cast: boolean }) => {
  const back = useOwnedTexture(createCardBackTexture);
  const materials = useMemo(() => {
    const edge = new THREE.MeshStandardMaterial({ color: "#d8cdb2", roughness: 0.8 });
    const face = new THREE.MeshStandardMaterial({ map: back, roughness: 0.6 });
    // Box faces: +x, -x, +y (back up), -y, +z, -z.
    return [edge, edge, face, face, edge, edge];
  }, [back]);
  useEffect(() => () => materials.forEach((m, i) => (i === 0 || i === 2) && m.dispose()), [materials]);

  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {Array.from({ length: 16 }, (_, i) => (
        <mesh
          key={i}
          material={materials}
          position={[Math.sin(i * 1.3) * 0.012, CARD_T * (i + 0.5), Math.cos(i * 0.9) * 0.012]}
          rotation={[0, Math.sin(i * 2.1) * 0.03, 0]}
        >
          <boxGeometry args={[CARD_W, CARD_T, CARD_D]} />
        </mesh>
      ))}
      {cast &&
        [0.35, -0.25].map((angle, i) => (
          <mesh
            key={`cast${i}`}
            material={materials}
            position={[0.75 + i * 0.25, CARD_T * (0.5 + i), 0.15 - i * 0.25]}
            rotation={[0, angle, 0]}
          >
            <boxGeometry args={[CARD_W, CARD_T, CARD_D]} />
          </mesh>
        ))}
    </group>
  );
};

// --- Goblet ---

const GOBLET_PROFILE: [number, number][] = [
  [0, 0],
  [0.32, 0],
  [0.3, 0.05],
  [0.08, 0.12],
  [0.06, 0.45],
  [0.1, 0.52],
  [0.3, 0.62],
  [0.34, 0.9],
  [0.32, 0.92],
];

const Goblet = ({ position }: { position: Vec3 }) => {
  const profile = useMemo(() => GOBLET_PROFILE.map(([r, h]) => new THREE.Vector2(r, h)), []);
  return (
    <group position={position}>
      <mesh>
        <latheGeometry args={[profile, 32]} />
        <meshStandardMaterial {...BRASS} side={THREE.DoubleSide} />
      </mesh>
      {/* Dark wine a little below the rim */}
      <mesh position={[0, 0.82, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.31, 32]} />
        <meshStandardMaterial color="#3a0508" roughness={0.15} metalness={0.2} />
      </mesh>
      {/* A spilled drop beside it */}
      <mesh position={[0.45, 0.004, 0.25]} rotation={[-Math.PI / 2, 0, 0]} scale={[1, 0.7, 1]}>
        <circleGeometry args={[0.12, 20]} />
        <meshStandardMaterial color="#2a0306" roughness={0.1} />
      </mesh>
    </group>
  );
};

// --- Inkwell and quill ---

const INKWELL_PROFILE: [number, number][] = [
  [0, 0],
  [0.3, 0],
  [0.32, 0.12],
  [0.26, 0.26],
  [0.12, 0.3],
  [0.12, 0.36],
  [0.1, 0.36],
];

const InkwellAndQuill = ({ position }: { position: Vec3 }) => {
  const profile = useMemo(() => INKWELL_PROFILE.map(([r, h]) => new THREE.Vector2(r, h)), []);
  const feather = useOwnedTexture(createFeatherTexture);
  return (
    <group position={position}>
      <mesh>
        <latheGeometry args={[profile, 24]} />
        <meshStandardMaterial color="#1f4a34" roughness={0.12} metalness={0.25} transparent opacity={0.92} side={THREE.DoubleSide} />
      </mesh>
      {/* Brass collar round the neck */}
      <mesh position={[0, 0.33, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.125, 0.03, 8, 20]} />
        <meshStandardMaterial {...BRASS} />
      </mesh>
      <mesh position={[0, 0.34, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.1, 16]} />
        <meshStandardMaterial color="#05060a" roughness={0.05} />
      </mesh>
      {/* Quill lying across the table, tip toward the inkwell */}
      <group position={[0.15, 0.02, 0.75]} rotation={[0, 0.9, 0]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[0.32, 1.3]} />
          <meshStandardMaterial map={feather} transparent alphaTest={0.05} side={THREE.DoubleSide} roughness={0.8} />
        </mesh>
      </group>
    </group>
  );
};

// --- Sealed letter ---

const SealedLetter = ({ position, rotation }: { position: Vec3; rotation: number }) => {
  const paper = useOwnedTexture(createParchmentTexture);
  const seal = useOwnedTexture(createWaxSealTexture);
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      <mesh position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.2, 0.8]} />
        <meshStandardMaterial map={paper} roughness={0.9} />
      </mesh>
      <mesh position={[0.2, 0.035, 0.05]}>
        <cylinderGeometry args={[0.17, 0.19, 0.05, 20]} />
        <meshStandardMaterial attach="material-0" color="#7a120d" roughness={0.45} />
        <meshStandardMaterial attach="material-1" map={seal} roughness={0.4} />
        <meshStandardMaterial attach="material-2" color="#7a120d" roughness={0.45} />
      </mesh>
    </group>
  );
};

// --- Dagger ---

const BLADE_LENGTH = 1.15;
const BLADE_BURIED = 0.32;
const STEEL = { color: "#d4d8de", metalness: 0.75, roughness: 0.22, emissive: "#2a2420", emissiveIntensity: 0.6 } as const;
const DARK_IRON = { color: "#2a2622", metalness: 0.7, roughness: 0.45 } as const;

/**
 * A dagger driven into the table at a slant, its point buried in split wood.
 * Built along +y from the point at the origin, then tilted as a whole.
 */
const Dagger = ({ position, tilt }: { position: Vec3; tilt: [number, number, number] }) => {
  const split = useOwnedTexture(createWoodSplitTexture);
  // Blade outline in the XY plane: leaf-shaped, point at y = 0.
  const bladeShape = useMemo(() => {
    const shape = new THREE.Shape();
    shape.moveTo(0, 0);
    shape.quadraticCurveTo(0.11, 0.3, 0.085, BLADE_LENGTH);
    shape.lineTo(-0.085, BLADE_LENGTH);
    shape.quadraticCurveTo(-0.11, 0.3, 0, 0);
    return shape;
  }, []);
  const bladeExtrude = useMemo(
    () => ({ depth: 0.012, bevelEnabled: true, bevelThickness: 0.016, bevelSize: 0.022, bevelSegments: 1, curveSegments: 10 }),
    [],
  );
  const hilt = BLADE_LENGTH;

  return (
    <group position={position}>
      {/* Wood split round the entry point */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]}>
        <planeGeometry args={[1.0, 1.0]} />
        <meshStandardMaterial map={split} transparent depthWrite={false} roughness={0.9} />
      </mesh>
      <group rotation={tilt}>
        <group position={[0, -BLADE_BURIED, -0.006]}>
          <mesh>
            <extrudeGeometry args={[bladeShape, bladeExtrude]} />
            <meshStandardMaterial {...STEEL} />
          </mesh>
          {/* Fuller: a dark groove down the middle of the blade */}
          <mesh position={[0, BLADE_LENGTH * 0.6, 0.03]}>
            <boxGeometry args={[0.022, BLADE_LENGTH * 0.62, 0.004]} />
            <meshStandardMaterial color="#5c6068" metalness={0.8} roughness={0.4} />
          </mesh>
          {/* Crossguard with swept-down tips */}
          <mesh position={[0, hilt + 0.03, 0.006]}>
            <boxGeometry args={[0.42, 0.06, 0.09]} />
            <meshStandardMaterial {...DARK_IRON} />
          </mesh>
          {[-1, 1].map((side) => (
            <mesh key={side} position={[side * 0.23, hilt + 0.0, 0.006]} rotation={[0, 0, side * 0.6]}>
              <coneGeometry args={[0.04, 0.12, 8]} />
              <meshStandardMaterial {...DARK_IRON} />
            </mesh>
          ))}
          {/* Leather-wrapped grip with bands */}
          <mesh position={[0, hilt + 0.26, 0.006]}>
            <cylinderGeometry args={[0.042, 0.05, 0.4, 12]} />
            <meshStandardMaterial color="#3a2414" roughness={0.85} />
          </mesh>
          {[0.1, 0.22, 0.34].map((y) => (
            <mesh key={y} position={[0, hilt + 0.06 + y, 0.006]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.048, 0.01, 6, 14]} />
              <meshStandardMaterial {...DARK_IRON} />
            </mesh>
          ))}
          {/* Pommel */}
          <mesh position={[0, hilt + 0.52, 0.006]}>
            <sphereGeometry args={[0.075, 14, 10]} />
            <meshStandardMaterial {...DARK_IRON} />
          </mesh>
        </group>
      </group>
    </group>
  );
};

/** The sealed letter, pinned to the table by a dagger through it. */
const PinnedLetter = ({ position, rotation }: { position: Vec3; rotation: number }) => (
  <group position={position} rotation={[0, rotation, 0]}>
    <SealedLetter position={[0, 0, 0]} rotation={0} />
    {/* Leaning hard toward the viewer so the whole blade reads from above */}
    <group position={[0.15, 0, 0.05]} scale={1.7}>
      <Dagger position={[0, 0, 0]} tilt={[0.95, 0.4, -0.45]} />
    </group>
  </group>
);

// --- Rune stones ---

const RUNE_STONES: { offset: [number, number]; scale: [number, number, number]; rot: number }[] = [
  { offset: [0, 0], scale: [0.3, 0.1, 0.24], rot: 0.3 },
  { offset: [0.55, 0.3], scale: [0.26, 0.09, 0.22], rot: -0.6 },
  { offset: [0.15, 0.6], scale: [0.28, 0.1, 0.22], rot: 1.1 },
  { offset: [-0.4, 0.45], scale: [0.24, 0.09, 0.2], rot: 2.2 },
];

const RuneStone = ({ variant, offset, scale, rot }: { variant: number; offset: [number, number]; scale: [number, number, number]; rot: number }) => {
  const create = useMemo(() => () => createRuneGlyphTexture(variant), [variant]);
  const glyph = useOwnedTexture(create);
  return (
    <group position={[offset[0], 0, offset[1]]} rotation={[0, rot, 0]}>
      <mesh position={[0, scale[1] * 0.8, 0]} scale={scale}>
        <sphereGeometry args={[1, 20, 12]} />
        <meshStandardMaterial color="#5a5650" roughness={0.85} />
      </mesh>
      <mesh position={[0, scale[1] * 1.8 + 0.002, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[scale[0] * 1.1, scale[2] * 1.1]} />
        <meshBasicMaterial map={glyph} transparent depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  );
};

const RuneStones = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    {RUNE_STONES.map((stone, i) => (
      <RuneStone key={i} variant={i} {...stone} />
    ))}
  </group>
);

// --- Turn tally ---

const TALLY_GLOW_MS = 2600;

/** The gods notch every turn of this battle into the table; the newest cut glows. */
const TurnTally = ({ position, turns }: { position: Vec3; turns: number }) => {
  const carved = useMemo(() => createTurnTallyTexture(turns), [turns]);
  const fresh = useMemo(() => createTurnTallyTexture(turns, true), [turns]);
  const glow = useRef<THREE.MeshBasicMaterial>(null);
  const cutAt = useRef<number | null>(null);
  const firstRender = useRef(true);

  useEffect(() => () => carved.dispose(), [carved]);
  useEffect(() => () => fresh.dispose(), [fresh]);
  useEffect(() => {
    // The count already on screen when the page opens isn't a new cut.
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    if (turns > 0) cutAt.current = performance.now();
  }, [turns]);

  useFrame(() => {
    if (!glow.current) return;
    const k = cutAt.current === null ? 1 : (performance.now() - cutAt.current) / TALLY_GLOW_MS;
    glow.current.opacity = k < 1 ? (1 - k) ** 1.5 : 0;
  });

  return (
    <group position={position} rotation={[-Math.PI / 2, 0, 0]}>
      <mesh position={[0, 0, 0.004]}>
        <planeGeometry args={[TALLY_WORLD_WIDTH, TALLY_WORLD_DEPTH]} />
        <meshStandardMaterial map={carved} transparent depthWrite={false} roughness={0.9} />
      </mesh>
      <mesh position={[0, 0, 0.006]}>
        <planeGeometry args={[TALLY_WORLD_WIDTH, TALLY_WORLD_DEPTH]} />
        <meshBasicMaterial
          ref={glow}
          map={fresh}
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
};

// --- Placement ---

interface TablePropsProps {
  boardWidth: number;
  /** Completed turns of this battle — one notch each. */
  turnNumber: number;
  turnDeadline: number | null;
  /** performance.now() of the latest critical hit; the dice roll on each new value. */
  critRollAt: number | null;
}

/**
 * Trappings of the gods' game on the table beside the board: dice of fate, a pile
 * of coins and an hourglass. Kept off the board itself so cards stay readable.
 */
const TableProps = ({ boardWidth, turnNumber, turnDeadline, critRollAt }: TablePropsProps) => {
  // x of the first lane just outside the board; props further out sit in a second lane.
  const near = boardWidth / 2 + 1.25;
  const far = near + 1.8;
  return (
    <group>
      {/* Left: the opponent's deck, the hourglass, the scribe's corner, your deck */}
      <Deck position={[-near - 0.2, 0, -2.6]} rotation={0.15} cast={false} />
      <group position={[-near, 0, 0.2]} scale={0.8}>
        <Hourglass position={[0, 0, 0]} turnDeadline={turnDeadline} />
      </group>
      <InkwellAndQuill position={[-far + 0.1, 0, -1.3]} />
      <PinnedLetter position={[-far + 0.4, 0, 1.9]} rotation={0.2} />
      <Deck position={[-near - 0.2, 0, 2.2]} rotation={-0.1} cast />
      <TurnTally position={[-near - 1.95, 0, 3.15]} turns={turnNumber} />

      {/* Right: the dice of fate, wine, runes and the coins at stake */}
      <DicePair position={[near, 0, -0.4]} rollAt={critRollAt} />
      <Goblet position={[far - 0.2, 0, -2.0]} />
      <RuneStones position={[far, 0, 0.3]} />
      <CoinPile position={[near - 0.3, 0, 1.9]} />
    </group>
  );
};

export default TableProps;
