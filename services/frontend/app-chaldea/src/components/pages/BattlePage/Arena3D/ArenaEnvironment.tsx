import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Sparkles } from "@react-three/drei";
import * as THREE from "three";
import {
  createBoardTexture,
  createFlameTexture,
  createSoftSpotTexture,
  createWornBrassTextures,
  createTableScarsTexture,
  SCARS_WORLD_DEPTH,
  SCARS_WORLD_WIDTH,
  createRuneCircleTexture,
  createTableWoodTexture,
} from "./textures";
import { TURN_DURATION_MS } from "./arenaTypes";
import TableProps from "./TableProps";

// Landscape on wide screens; on phones the long side runs up the screen.
export const boardSize = (portrait: boolean) =>
  portrait ? { width: 9, depth: 12 } : { width: 12, depth: 9 };
const BOARD_THICKNESS = 0.2;
/** Height of the board's playing surface; fighters stand on it. */
export const BOARD_TOP = BOARD_THICKNESS;
const RIM_WIDTH = 0.34;
const TABLE_WIDTH = 90;
const TABLE_DEPTH = 44;
const RIM_HEIGHT = 0.36;
const CANDLE_LIGHT = "#ffb35c";

// --- Rune circle: the turn clock engraved in the middle of the board ---

const RUNE_RADIUS = 1.9;
const RUNE_SEGMENTS = 96;
const URGENT_FRACTION = 0.1;
const RUNE_GOLD = new THREE.Color("#f0d95c");
const RUNE_URGENT = new THREE.Color("#ff5a3c");

const remainingFraction = (deadline: number | null) =>
  deadline === null ? 1 : THREE.MathUtils.clamp((deadline - Date.now()) / TURN_DURATION_MS, 0, 1);

/**
 * A dim full circle with a lit sector that burns down (clockwise from the far
 * side) as the turn deadline nears; it turns red and pulses in the last 10%.
 */
const RuneCircle = ({ turnDeadline, turnPaused }: { turnDeadline: number | null; turnPaused: boolean }) => {
  const texture = useMemo(createRuneCircleTexture, []);
  const litMaterial = useRef<THREE.MeshBasicMaterial>(null);
  const [step, setStep] = useState(() => Math.round(remainingFraction(turnDeadline) * RUNE_SEGMENTS));

  useEffect(() => () => texture.dispose(), [texture]);

  useFrame(({ clock }) => {
    const fraction = turnPaused ? step / RUNE_SEGMENTS : remainingFraction(turnDeadline);
    const nextStep = Math.round(fraction * RUNE_SEGMENTS);
    if (nextStep !== step) setStep(nextStep);
    if (litMaterial.current) {
      const urgent = fraction < URGENT_FRACTION;
      const pulse = urgent ? Math.sin(clock.elapsedTime * 5) * 0.25 : Math.sin(clock.elapsedTime * 1.3) * 0.15;
      litMaterial.current.opacity = 0.8 + pulse;
      litMaterial.current.color.copy(urgent ? RUNE_URGENT : RUNE_GOLD);
    }
  });

  const thetaLength = (step / RUNE_SEGMENTS) * Math.PI * 2;

  return (
    <group rotation={[-Math.PI / 2, 0, 0]} position={[0, BOARD_TOP + 0.006, 0]}>
      <mesh>
        <circleGeometry args={[RUNE_RADIUS, RUNE_SEGMENTS]} />
        <meshBasicMaterial
          map={texture}
          color="#6b5e2a"
          transparent
          opacity={0.45}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
      {step > 0 && (
        <mesh position={[0, 0, 0.002]}>
          {/* Starts at the far side (+y before the -90° tilt) and shrinks clockwise. */}
          <circleGeometry args={[RUNE_RADIUS, RUNE_SEGMENTS, Math.PI / 2, thetaLength]} />
          <meshBasicMaterial
            ref={litMaterial}
            map={texture}
            transparent
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </mesh>
      )}
    </group>
  );
};

// --- Candles ---

// Short, thick candles on a brass dish: from above they read as round wax tops with
// a flame, not as tubes pointing at the camera.
const CANDLE_SPECS: { offset: [number, number]; height: number; radius: number }[] = [
  { offset: [0, 0], height: 0.4, radius: 0.24 },
  { offset: [0.38, 0.22], height: 0.28, radius: 0.19 },
  { offset: [-0.32, 0.3], height: 0.2, radius: 0.17 },
];
const DISH_RADIUS = 0.78;
const WAX_COLOR = "#8f7a55";

const Flame = ({ texture, position, seed }: { texture: THREE.Texture; position: [number, number, number]; seed: number }) => {
  const sprite = useRef<THREE.Sprite>(null);
  const material = useRef<THREE.SpriteMaterial>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime * 9 + seed * 7;
    const flick = 1 + Math.sin(t) * 0.08 + Math.sin(t * 2.3) * 0.05;
    sprite.current?.scale.set(0.42 * (2 - flick), 0.78 * flick, 1);
    if (material.current) material.current.opacity = 0.85 + Math.sin(t * 1.7) * 0.1;
  });
  return (
    <group position={position}>
      <sprite ref={sprite} scale={[0.42, 0.78, 1]}>
        <spriteMaterial
          ref={material}
          map={texture}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </sprite>
      {/* Opaque core: the tongue of flame stays visible over the lit wax */}
      <sprite position={[0, -0.05, 0.01]} scale={[0.13, 0.26, 1]}>
        <spriteMaterial map={texture} color="#fff3c8" transparent depthWrite={false} toneMapped={false} />
      </sprite>
    </group>
  );
};

/** A brass dish of half-melted candles with one shared flickering light. */
const CandleCluster = ({
  position,
  seed,
  flame,
  glow,
  brass,
}: {
  position: [number, number, number];
  seed: number;
  flame: THREE.Texture;
  glow: THREE.Texture;
  brass: THREE.Material;
}) => {
  const light = useRef<THREE.PointLight>(null);
  const pool = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime * 7 + seed * 11;
    const flick = 0.85 + Math.sin(t) * 0.07 + Math.sin(t * 2.3) * 0.05 + Math.sin(t * 5.1) * 0.03;
    if (light.current) light.current.intensity = 16 * flick;
    if (pool.current) pool.current.opacity = 0.4 * flick;
  });
  return (
    <group position={position}>
      {/* Warm pool of light on the table around the dish */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]}>
        <planeGeometry args={[3.6, 3.6]} />
        <meshBasicMaterial
          ref={pool}
          map={glow}
          color={CANDLE_LIGHT}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>

      {/* Brass dish */}
      <mesh position={[0, 0.03, 0]} material={brass}>
        <cylinderGeometry args={[DISH_RADIUS, DISH_RADIUS * 0.92, 0.06, 32]} />
      </mesh>
      <mesh position={[0, 0.07, 0]} rotation={[Math.PI / 2, 0, 0]} material={brass}>
        <torusGeometry args={[DISH_RADIUS, 0.04, 8, 32]} />
      </mesh>

      {CANDLE_SPECS.map((c, i) => (
        <group key={i} position={[c.offset[0], 0.06, c.offset[1]]}>
          <mesh position={[0, c.height / 2, 0]}>
            <cylinderGeometry args={[c.radius, c.radius * 1.06, c.height, 20]} />
            <meshStandardMaterial color={WAX_COLOR} roughness={0.85} />
          </mesh>
          {/* Melted rim and the hollow it leaves around the wick */}
          <mesh position={[0, c.height, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[c.radius * 0.82, c.radius * 0.2, 8, 20]} />
            <meshStandardMaterial color={WAX_COLOR} roughness={0.85} />
          </mesh>
          <mesh position={[0, c.height - 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[c.radius * 0.7, 20]} />
            <meshStandardMaterial color="#5e4c30" roughness={0.6} emissive="#ff8a2c" emissiveIntensity={0.15} />
          </mesh>
          {/* A drip running down the side */}
          <mesh position={[c.radius * 0.95, c.height * 0.7, 0]} scale={[0.6, 1.8, 0.6]}>
            <sphereGeometry args={[c.radius * 0.22, 8, 8]} />
            <meshStandardMaterial color={WAX_COLOR} roughness={0.5} />
          </mesh>
          <mesh position={[0, c.height + 0.05, 0]}>
            <cylinderGeometry args={[0.012, 0.012, 0.1, 6]} />
            <meshBasicMaterial color="#1a120a" />
          </mesh>
          <Flame texture={flame} position={[0, c.height + 0.36, 0]} seed={seed * 3 + i} />
          {/* Soft halo so the flame reads even against the lit wax below it */}
          <sprite position={[0, c.height + 0.3, 0]} scale={[0.9, 0.9, 1]}>
            <spriteMaterial map={glow} color={CANDLE_LIGHT} transparent opacity={0.45} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
          </sprite>
        </group>
      ))}
      {/* Off to the side and low, so the wax tops aren't burnt white from straight above */}
      <pointLight ref={light} position={[0.9, 0.7, 0.9]} color={CANDLE_LIGHT} distance={10} decay={1.5} />
    </group>
  );
};

// --- Board and table ---

// Each bar sits a hair off true — a little tilt and sag from centuries of play.
const RIM_BARS: { side: "far" | "near" | "left" | "right"; tilt: number; sag: number }[] = [
  { side: "far", tilt: 0.004, sag: -0.008 },
  { side: "near", tilt: -0.006, sag: 0.004 },
  { side: "left", tilt: 0.005, sag: -0.004 },
  { side: "right", tilt: -0.003, sag: 0.006 },
];

/** The board's brass rim: tarnished, scratched, dented and rubbed bright in places. */
const BrassRim = ({ width, depth }: { width: number; depth: number }) => {
  const worn = useMemo(createWornBrassTextures, []);
  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        map: worn.map,
        bumpMap: worn.bumpMap,
        bumpScale: 0.03,
        roughnessMap: worn.roughnessMap,
        roughness: 0.9,
        metalness: 0.7,
      }),
    [worn],
  );
  useEffect(
    () => () => {
      worn.map.dispose();
      worn.bumpMap.dispose();
      worn.roughnessMap.dispose();
      material.dispose();
    },
    [worn, material],
  );

  const hw = width / 2 + RIM_WIDTH / 2;
  const hd = depth / 2 + RIM_WIDTH / 2;
  const y = RIM_HEIGHT / 2;
  // All bars are built along x and turned into place, so the wear texture runs along each.
  const bar = (side: (typeof RIM_BARS)[number]["side"]) => {
    const alongX = side === "far" || side === "near";
    const length = alongX ? width + RIM_WIDTH * 2 : depth;
    const position: [number, number, number] =
      side === "far" ? [0, y, -hd] : side === "near" ? [0, y, hd] : side === "left" ? [-hw, y, 0] : [hw, y, 0];
    return { length, position, turn: alongX ? 0 : Math.PI / 2 };
  };

  return (
    <group>
      {RIM_BARS.map(({ side, tilt, sag }) => {
        const { length, position, turn } = bar(side);
        return (
          <mesh
            key={side}
            material={material}
            position={[position[0], position[1] + sag, position[2]]}
            rotation={[tilt, turn, tilt * 0.5]}
          >
            <boxGeometry args={[length, RIM_HEIGHT, RIM_WIDTH]} />
          </mesh>
        );
      })}
      {[-hw, hw].flatMap((x) =>
        [-hd, hd].map((z, i) => (
          <mesh
            key={`c${x}${z}`}
            material={material}
            position={[x, RIM_HEIGHT + 0.08, z]}
            // One corner knob was struck long ago and never quite recovered.
            scale={x < 0 && i === 1 ? [1.08, 0.82, 1] : [1, 1, 1]}
            rotation={[0, (x + z) * 0.7, 0]}
          >
            <sphereGeometry args={[0.2, 16, 12]} />
          </mesh>
        )),
      )}
    </group>
  );
};

interface ArenaEnvironmentProps {
  turnDeadline: number | null;
  turnPaused: boolean;
  portrait: boolean;
  /** Same-origin URL of the location art painted into the board, if any. */
  boardArtUrl: string | null;
  critRollAt: number | null;
  turnNumber: number;
}

/** Loads a same-origin image for canvas use; null until loaded or if it fails. */
const useImage = (url: string | null) => {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    setImage(null);
    if (!url) return;
    const img = new Image();
    let alive = true;
    img.onload = () => alive && setImage(img);
    img.onerror = () => console.warn("Board art failed to load:", url);
    img.src = url;
    return () => {
      alive = false;
    };
  }, [url]);
  return image;
};

/** The table of fates: a candle-lit board, seen from above, on which the gods play. */
const ArenaEnvironment = ({ turnDeadline, turnPaused, portrait, boardArtUrl, critRollAt, turnNumber }: ArenaEnvironmentProps) => {
  const { width, depth } = boardSize(portrait);
  const art = useImage(boardArtUrl);
  const wood = useMemo(createTableWoodTexture, []);
  const board = useMemo(() => createBoardTexture(width, depth, art), [width, depth, art]);
  const flame = useMemo(createFlameTexture, []);
  const glow = useMemo(createSoftSpotTexture, []);
  const scars = useMemo(createTableScarsTexture, []);
  const brass = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#8a6a2e", metalness: 0.7, roughness: 0.38 }),
    [],
  );
  const boardSide = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#1a120c", roughness: 0.8 }),
    [],
  );

  const spot = useRef<THREE.SpotLight>(null);
  useEffect(() => {
    // The target isn't part of the scene graph, so its matrix must be set by hand.
    const light = spot.current;
    if (!light) return;
    light.target.position.set(0, 0, -0.5);
    light.target.updateMatrixWorld();
  }, []);

  useEffect(() => {
    wood.repeat.set(TABLE_WIDTH / 11, TABLE_DEPTH / 11);
    return () => {
      wood.dispose();
      flame.dispose();
      glow.dispose();
      scars.dispose();
      brass.dispose();
      boardSide.dispose();
    };
  }, [wood, flame, glow, scars, brass, boardSide]);

  // The board texture is redrawn when the orientation flips; free only the old one.
  useEffect(() => () => board.dispose(), [board]);

  const candleX = width / 2 + 1.1;
  const candleZ = depth / 2 - 0.6;

  return (
    <group>
      <hemisphereLight args={["#4a4566", "#0a0705", 0.45]} />
      {/* A cone of light falling on the board from the void above */}
      <spotLight
        ref={spot}
        position={[0, 13, 2]}
        angle={0.55}
        penumbra={0.9}
        intensity={260}
        decay={1.6}
        color="#f2e4c8"
      />

      {/* Table — wide enough to run past both screen edges on any aspect ratio */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.001, 0]}>
        <planeGeometry args={[TABLE_WIDTH, TABLE_DEPTH]} />
        <meshStandardMaterial map={wood} roughness={0.85} />
      </mesh>

      {/* Gouges, rings, burns and the gods' old score left by countless games */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, 0]}>
        <planeGeometry args={[SCARS_WORLD_WIDTH, SCARS_WORLD_DEPTH]} />
        <meshStandardMaterial map={scars} transparent depthWrite={false} roughness={0.9} />
      </mesh>

      {/* Board */}
      <mesh position={[0, BOARD_THICKNESS / 2, 0]} material={boardSide}>
        <boxGeometry args={[width, BOARD_THICKNESS, depth]} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, BOARD_TOP + 0.002, 0]}>
        <planeGeometry args={[width, depth]} />
        <meshStandardMaterial map={board} roughness={0.7} metalness={0.15} />
      </mesh>
      <BrassRim width={width} depth={depth} />
      <RuneCircle turnDeadline={turnDeadline} turnPaused={turnPaused} />

      <CandleCluster position={[-candleX, 0, candleZ]} seed={1} flame={flame} glow={glow} brass={brass} />
      <CandleCluster position={[candleX, 0, candleZ]} seed={2} flame={flame} glow={glow} brass={brass} />
      <CandleCluster position={[-candleX, 0, -candleZ]} seed={3} flame={flame} glow={glow} brass={brass} />
      <CandleCluster position={[candleX, 0, -candleZ]} seed={4} flame={flame} glow={glow} brass={brass} />

      {/* Phones get a portrait board with no room beside it for props */}
      {!portrait && <TableProps boardWidth={width} turnNumber={turnNumber} turnDeadline={turnDeadline} critRollAt={critRollAt} />}

      {/* Dust drifting through the light cone */}
      <Sparkles count={60} scale={[10, 6, 8]} position={[0, 3, 0]} size={1.6} speed={0.18} color="#f2e4c8" opacity={0.5} />

      <fog attach="fog" args={["#050407", 20, 40]} />
    </group>
  );
};

export default ArenaEnvironment;
