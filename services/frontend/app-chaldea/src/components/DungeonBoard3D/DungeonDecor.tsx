import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { createSoftSpotTexture, mulberry32 } from '../pages/BattlePage/Arena3D/textures';
import { SQUARE, type Piece, type RoomInfo, type WallSegment } from './dioramaLayout';
import { FLOOR_THICKNESS, WALL_HEIGHT, WALL_THICKNESS, torchWalls, wallRise } from './DioramaPieces';
import type { BoardRoomType } from './boardTypes';
import {
  createCrackTexture,
  createDebrisTexture,
  createGrassTexture,
  createMossTexture,
  createPuddleTexture,
  createRuneCircleTexture,
  createSplatterTexture,
  createStainTexture,
  createVineTexture,
  createWebTexture,
} from './decorTextures';

/*
  The dungeon's dressing, so no two rooms look alike: cracks, moss and litter
  on the flagstones; pools of water, blood or glowing slime; vines spilling
  over the walls, seepage stains and cobwebs in the corners; glowing mushrooms,
  grass, crystals, skulls, chains and roots; drips falling into puddles and
  motes drifting in the air (dust, fireflies, spores, embers, portal sparks).

  What a room gets follows its kind (blood and chains where fights are, embers
  in the lair, grass round the campfire) and a mood drawn from its id —
  overgrown, flooded, slimy or dry — so the same kind of room differs from one
  to the next. Everything is seeded: a room looks the same on every visit.
*/

type Liquid = 'water' | 'blood' | 'slime';
type MoteKind = 'dust' | 'fireflies' | 'spores' | 'embers' | 'arcane';
type DecorTheme = BoardRoomType | 'corridor';

/** How much of each thing a theme scatters, per ~12 floor squares (fractions round at random). */
interface Recipe {
  cracks: number;
  moss: number;
  debris: number;
  puddles: number;
  liquid: Liquid;
  splatter: number;
  scorch: number;
  embers: number;
  vines: number;
  stains: number;
  chains: number;
  /** Chance of a cobweb in each corner. */
  webs: number;
  grass: number;
  mushrooms: number;
  crystals: number;
  skulls: number;
  roots: number;
  drips: number;
  /** Rats scurrying along the walls. */
  rats: number;
  motes?: MoteKind;
}

const NONE: Recipe = {
  cracks: 0, moss: 0, debris: 0, puddles: 0, liquid: 'water', splatter: 0, scorch: 0, embers: 0,
  vines: 0, stains: 0, chains: 0, webs: 0, grass: 0, mushrooms: 0, crystals: 0, skulls: 0, roots: 0, drips: 0, rats: 0,
};

const RECIPES: Record<DecorTheme, Recipe> = {
  corridor: { ...NONE, cracks: 1.2, moss: 0.7, debris: 0.6, puddles: 0.5, vines: 0.5, stains: 0.5, grass: 0.3, mushrooms: 0.4, drips: 0.3, rats: 0.25 },
  entrance: { ...NONE, cracks: 1, moss: 2, debris: 1, puddles: 1, vines: 2.5, stains: 1, grass: 3, webs: 0.4, drips: 0.5, motes: 'dust' },
  battle: { ...NONE, cracks: 2, moss: 0.5, debris: 1, splatter: 2, liquid: 'blood', puddles: 0.6, scorch: 1, chains: 2, skulls: 1.2, webs: 0.5, stains: 1, rats: 0.3, motes: 'dust' },
  boss: { ...NONE, cracks: 1, embers: 3, splatter: 2, liquid: 'blood', puddles: 0.8, scorch: 1.5, chains: 3, skulls: 2.5, webs: 0.7, motes: 'embers' },
  treasure: { ...NONE, cracks: 1, debris: 1, crystals: 3, webs: 1, stains: 0.5, motes: 'dust' },
  trap: { ...NONE, cracks: 2, splatter: 1.2, liquid: 'blood', scorch: 2, debris: 1, webs: 0.7, skulls: 1, stains: 1 },
  event: { ...NONE, cracks: 1, moss: 2, puddles: 2, vines: 2, mushrooms: 2, grass: 1, drips: 1, stains: 0.5, motes: 'spores' },
  rest: { ...NONE, moss: 2, grass: 4, mushrooms: 1, vines: 1.2, debris: 1, puddles: 0.5, motes: 'fireflies' },
  merchant: { ...NONE, debris: 2, cracks: 1, webs: 0.8, stains: 0.5, moss: 0.5, rats: 0.5, motes: 'dust' },
  teleport: { ...NONE, cracks: 1, moss: 1, crystals: 1, motes: 'arcane' },
  fork: { ...NONE, cracks: 1, moss: 1.5, puddles: 1, mushrooms: 2, vines: 1.5, roots: 1, stains: 1, drips: 0.5, motes: 'spores' },
  deadend: { ...NONE, cracks: 3, debris: 2, webs: 1, roots: 2, moss: 1, skulls: 0.6, stains: 1, rats: 0.6 },
};

/** Kinds of room that keep their look; the rest take a mood. */
const FIXED_LOOK = new Set<DecorTheme>(['battle', 'boss', 'trap', 'treasure', 'teleport']);

type Mood = 'plain' | 'overgrown' | 'flooded' | 'slimy' | 'dry';
const MOODS: Mood[] = ['plain', 'overgrown', 'flooded', 'slimy', 'dry'];

const withMood = (recipe: Recipe, mood: Mood): Recipe => {
  switch (mood) {
    case 'overgrown':
      return {
        ...recipe,
        vines: recipe.vines * 2 + 1,
        moss: recipe.moss * 2 + 1,
        grass: recipe.grass * 1.5 + 1,
        mushrooms: recipe.mushrooms * 1.5 + 0.5,
        roots: recipe.roots + 0.7,
        motes: recipe.motes ?? 'fireflies',
      };
    case 'flooded':
      return { ...recipe, puddles: recipe.puddles + 2, drips: recipe.drips + 1.2, stains: recipe.stains * 2 + 1, liquid: 'water' };
    case 'slimy':
      return { ...recipe, puddles: recipe.puddles + 1.2, liquid: 'slime', mushrooms: recipe.mushrooms + 1, stains: recipe.stains + 0.5, motes: recipe.motes ?? 'spores' };
    case 'dry':
      return {
        ...recipe,
        cracks: recipe.cracks + 1.5,
        debris: recipe.debris + 1,
        webs: Math.min(1, recipe.webs + 0.5),
        rats: recipe.rats + 0.3,
        vines: recipe.vines * 0.3,
        moss: recipe.moss * 0.3,
        grass: recipe.grass * 0.3,
        puddles: 0,
        drips: 0,
      };
    default:
      return recipe;
  }
};

/* ── The kit: shared textures, geometries and materials ── */

const decal = (params: THREE.MeshStandardMaterialParameters) =>
  new THREE.MeshStandardMaterial({
    transparent: true,
    depthWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
    roughness: 0.95,
    ...params,
  });

const glowSprite = (map: THREE.Texture, color: string, opacity: number) =>
  new THREE.SpriteMaterial({ map, color, transparent: true, opacity, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false });

export const useDecorKit = () => {
  const kit = useMemo(() => {
    const tex = {
      cracks: [11, 23, 37].map((s) => createCrackTexture(s)),
      ember: createCrackTexture(91, true),
      moss: [5, 17].map(createMossTexture),
      puddle: [3, 29].map(createPuddleTexture),
      splatter: createSplatterTexture(13),
      rune: createRuneCircleTexture(),
      vines: [7, 19].map(createVineTexture),
      grass: createGrassTexture(41),
      web: createWebTexture(),
      stain: createStainTexture(61),
      debris: [8, 44].map(createDebrisTexture),
      glow: createSoftSpotTexture(),
    };
    const capHalf = new THREE.SphereGeometry(1, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2);
    const geo = {
      plane: new THREE.PlaneGeometry(1, 1),
      stem: new THREE.CylinderGeometry(0.7, 1, 1, 6),
      cap: capHalf,
      crystal: new THREE.OctahedronGeometry(1, 0),
      link: new THREE.TorusGeometry(0.014, 0.0045, 6, 12),
      ball: new THREE.SphereGeometry(1, 12, 10),
      box: new THREE.BoxGeometry(1, 1, 1),
      ripple: new THREE.RingGeometry(0.8, 1, 24),
    };
    const water = { color: '#6a8ca4', roughness: 0.03, metalness: 0.15, emissive: '#0c2232', opacity: 0.6 };
    const mats = {
      cracks: tex.cracks.map((map) => decal({ map })),
      moss: tex.moss.map((map) => decal({ map })),
      debris: tex.debris.map((map) => decal({ map })),
      water: tex.puddle.map((map) => decal({ map, ...water })),
      blood: decal({ map: tex.puddle[1], color: '#7a0c0c', roughness: 0.1, metalness: 0.2, emissive: '#1e0000', opacity: 0.9 }),
      bloodSplatter: decal({ map: tex.splatter, color: '#7a0c0c', roughness: 0.2, metalness: 0.2, opacity: 0.9 }),
      slime: decal({
        map: tex.puddle[0], color: '#3c7a18', roughness: 0.15, emissive: '#56ff2a', emissiveMap: tex.puddle[0], emissiveIntensity: 0.45,
      }),
      ember: decal({ map: tex.ember, color: '#401406', emissive: '#ff5a14', emissiveMap: tex.ember, emissiveIntensity: 1.4, toneMapped: false }),
      scorch: new THREE.MeshBasicMaterial({ map: tex.glow, color: '#000000', transparent: true, opacity: 0.6, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1 }),
      rune: {
        blue: decal({ map: tex.rune, color: '#2a4a80', emissive: '#4a8aff', emissiveMap: tex.rune, emissiveIntensity: 1.1, toneMapped: false }),
        red: decal({ map: tex.rune, color: '#801a10', emissive: '#ff3a24', emissiveMap: tex.rune, emissiveIntensity: 1.1, toneMapped: false }),
        spent: decal({ map: tex.rune, color: '#3a3436', opacity: 0.7 }),
      },
      vines: tex.vines.map(
        (map) => new THREE.MeshStandardMaterial({ map, alphaTest: 0.35, side: THREE.DoubleSide, roughness: 0.85 }),
      ),
      grass: new THREE.MeshStandardMaterial({ map: tex.grass, alphaTest: 0.4, side: THREE.DoubleSide, roughness: 0.9 }),
      web: decal({ map: tex.web, side: THREE.DoubleSide, opacity: 0.55, roughness: 1 }),
      stain: decal({ map: tex.stain }),
      stem: new THREE.MeshStandardMaterial({ color: '#d8d0c0', roughness: 0.8 }),
      capTeal: new THREE.MeshStandardMaterial({ color: '#2ad8b0', emissive: '#2affd8', emissiveIntensity: 0.9, roughness: 0.5 }),
      capViolet: new THREE.MeshStandardMaterial({ color: '#9a3ad8', emissive: '#c05aff', emissiveIntensity: 0.9, roughness: 0.5 }),
      crystal: new THREE.MeshStandardMaterial({
        color: '#8a5ad8', emissive: '#a06aff', emissiveIntensity: 0.8, roughness: 0.15, metalness: 0.2, transparent: true, opacity: 0.88,
      }),
      iron: new THREE.MeshStandardMaterial({ color: '#2c2a2e', metalness: 0.75, roughness: 0.45 }),
      bone: new THREE.MeshStandardMaterial({ color: '#d8ccb0', roughness: 0.7 }),
      socket: new THREE.MeshBasicMaterial({ color: '#0a0806' }),
      root: new THREE.MeshStandardMaterial({ color: '#3a2a1c', roughness: 0.95 }),
      fur: new THREE.MeshStandardMaterial({ color: '#3d3330', roughness: 0.95 }),
      tail: new THREE.MeshStandardMaterial({ color: '#b08a80', roughness: 0.7 }),
      eye: new THREE.MeshBasicMaterial({ color: '#ff3a2a' }),
      spider: new THREE.MeshStandardMaterial({ color: '#141014', roughness: 0.5, metalness: 0.2 }),
      thread: new THREE.MeshBasicMaterial({ color: '#d8d8e0', transparent: true, opacity: 0.6 }),
      drop: new THREE.MeshBasicMaterial({ color: '#cfe8ff', transparent: true, opacity: 0.85 }),
      bubble: new THREE.MeshStandardMaterial({ color: '#5aa82a', emissive: '#56ff2a', emissiveIntensity: 0.5, roughness: 0.1, transparent: true, opacity: 0.8 }),
      glowTeal: glowSprite(tex.glow, '#2affd8', 0.35),
      glowViolet: glowSprite(tex.glow, '#c05aff', 0.35),
      glowCrystal: glowSprite(tex.glow, '#a06aff', 0.45),
    };
    return { tex, geo, mats };
  }, []);
  useEffect(
    () => () => {
      const dispose = (v: unknown) => {
        if (Array.isArray(v)) v.forEach(dispose);
        else if (v instanceof THREE.Texture || v instanceof THREE.Material || v instanceof THREE.BufferGeometry) v.dispose();
        else if (v && typeof v === 'object') Object.values(v).forEach(dispose);
      };
      dispose(kit);
    },
    [kit],
  );
  return kit;
};

export type DecorKit = ReturnType<typeof useDecorKit>;

/** The glowing things breathe; one call per frame for the whole board. */
export const useDecorPulse = (kit: DecorKit) => {
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const { mats } = kit;
    mats.ember.emissiveIntensity = 1.3 + Math.sin(t * 1.7) * 0.4 + Math.sin(t * 4.1) * 0.15;
    mats.capTeal.emissiveIntensity = 0.85 + Math.sin(t * 1.3) * 0.35;
    mats.capViolet.emissiveIntensity = 0.85 + Math.sin(t * 1.3 + 2) * 0.35;
    mats.glowTeal.opacity = 0.3 + Math.sin(t * 1.3) * 0.12;
    mats.glowViolet.opacity = 0.3 + Math.sin(t * 1.3 + 2) * 0.12;
    mats.crystal.emissiveIntensity = 0.75 + Math.sin(t * 0.8) * 0.25;
    mats.glowCrystal.opacity = 0.4 + Math.sin(t * 0.8) * 0.12;
    mats.slime.emissiveIntensity = 0.4 + Math.sin(t * 2.2) * 0.12;
    mats.rune.blue.emissiveIntensity = 1 + Math.sin(t * 1.1) * 0.3;
    mats.rune.red.emissiveIntensity = 1.1 + Math.sin(t * 3) * 0.45;
  });
};

/* ── Planning: where everything goes ── */

type Vec2 = [number, number];

const INWARD: Record<WallSegment['side'], Vec2> = {
  north: [0, 1],
  south: [0, -1],
  west: [1, 0],
  east: [-1, 0],
};

/** Rotation about y that turns a plane's face (+z) to look along `n`. */
const facing = (n: Vec2) => Math.atan2(n[0], n[1]);

interface FloorDecal {
  material: THREE.Material;
  x: number;
  z: number;
  size: number;
  turn: number;
}

interface WallDecal {
  material: THREE.Material;
  x: number;
  y: number;
  z: number;
  turn: number;
  w: number;
  h: number;
  /** Lying flat (on top of a wall) rather than standing on its face. */
  flat?: boolean;
}

interface Hanging {
  kind: 'vine' | 'chain';
  x: number;
  y: number;
  z: number;
  turn: number;
  length: number;
  variant: number;
  phase: number;
}

interface Clutter {
  kind: 'mushrooms' | 'grass' | 'crystals' | 'skull';
  x: number;
  z: number;
  seed: number;
}

interface Plan {
  floor: FloorDecal[];
  walls: WallDecal[];
  hanging: Hanging[];
  clutter: Clutter[];
  roots: THREE.Vector3[][];
  drips: { x: number; z: number; period: number; offset: number }[];
  bubbles: { x: number; z: number; offset: number }[];
  rune: THREE.Material | null;
  motes: MoteKind | null;
  rats: { from: Vec2; to: Vec2; seed: number }[];
  spiders: { x: number; z: number; top: number; seed: number }[];
}

/** Overall richness of the dressing. */
const DENSITY = 1.9;

const count = (rand: () => number, amount: number) => Math.floor(amount * (0.7 + rand() * 0.6) + rand());

const planDecor = (
  kit: DecorKit,
  piece: Piece,
  seed: number,
  room: RoomInfo | null,
  portal: 'blue' | 'red' | undefined,
  spent: boolean,
): Plan => {
  const rand = mulberry32(seed * 7919 + 17);
  const theme: DecorTheme = room ? room.type : 'corridor';
  const mood: Mood = FIXED_LOOK.has(theme) ? 'plain' : MOODS[Math.floor(rand() * MOODS.length)];
  const recipe = withMood(RECIPES[theme], mood);
  const area = piece.floor.length / 12;
  const n = (amount: number) => count(rand, amount * DENSITY * Math.max(0.35, area));
  const pick = <T,>(list: T[]) => list[Math.floor(rand() * list.length)];
  const { mats } = kit;

  // Which sides of each square are walled: corners have two.
  const sqKey = (x: number, z: number) => `${Math.round(x * 100)},${Math.round(z * 100)}`;
  const walledSides = new Map<string, number>();
  const squareOf = (w: WallSegment): Vec2 => {
    const [nx, nz] = INWARD[w.side];
    return [w.x + (nx * SQUARE) / 2, w.z + (nz * SQUARE) / 2];
  };
  piece.walls.forEach((w) => {
    const k = sqKey(...squareOf(w));
    walledSides.set(k, (walledSides.get(k) ?? 0) + 1);
  });
  const torches = new Set(torchWalls(piece));
  const walls = piece.walls.map((w, index) => ({ w, index, top: FLOOR_THICKNESS + WALL_HEIGHT * wallRise(seed, index) }));
  // The camera looks north: a south wall shows its back, so nothing hangs on its inner face.
  const hangable = walls.filter((x) => x.w.side !== 'south' && !(room && torches.has(x.w)));
  // Small things stand by walls but not in corners (passages and barrels live there),
  // nor where a room's own furniture stands (enemies at the back, bedrolls at the sides).
  const besideWall = walls.filter(({ w }) => {
    if ((walledSides.get(sqKey(...squareOf(w))) ?? 0) > 1) return false;
    if ((theme === 'battle' || theme === 'boss') && w.side === 'north') return false;
    if (theme === 'rest' && (w.side === 'west' || w.side === 'east')) return false;
    return true;
  });

  const facePoint = (w: WallSegment, out: number, along: number): Vec2 => {
    const [nx, nz] = INWARD[w.side];
    const [ax, az] = w.alongX ? [1, 0] : [0, 1];
    const off = WALL_THICKNESS / 2 + out;
    return [w.x + nx * off + ax * along, w.z + nz * off + az * along];
  };

  const floorSpot = (keepOffCentre: boolean): Vec2 => {
    for (let tries = 0; ; tries++) {
      const sq = pick(piece.floor);
      const x = sq.x + (rand() - 0.5) * SQUARE * 0.7;
      const z = sq.z + (rand() - 0.5) * SQUARE * 0.7;
      if (!room || !keepOffCentre || tries > 6 || Math.hypot(x - room.center[0], z - room.center[1]) > 0.32) return [x, z];
    }
  };
  /** A spot on the floor close to a wall (moss creeps along the edges). */
  const edgeSpot = (): Vec2 => {
    if (walls.length === 0) return floorSpot(false);
    const { w } = pick(walls);
    return facePoint(w, 0.04 + rand() * 0.08, (rand() - 0.5) * SQUARE * 0.8);
  };

  const plan: Plan = {
    floor: [], walls: [], hanging: [], clutter: [], roots: [], drips: [], bubbles: [], rune: null, motes: null, rats: [], spiders: [],
  };
  const lay = (material: THREE.Material, at: Vec2, size: number) =>
    plan.floor.push({ material, x: at[0], z: at[1], size, turn: rand() * Math.PI * 2 });

  for (let i = n(recipe.cracks); i > 0; i--) lay(pick(mats.cracks), floorSpot(false), 0.32 + rand() * 0.3);
  for (let i = n(recipe.moss); i > 0; i--) lay(pick(mats.moss), edgeSpot(), 0.26 + rand() * 0.24);
  for (let i = n(recipe.debris); i > 0; i--) lay(pick(mats.debris), floorSpot(false), 0.22 + rand() * 0.18);
  for (let i = n(recipe.scorch); i > 0; i--) lay(mats.scorch, floorSpot(false), 0.25 + rand() * 0.2);
  for (let i = n(recipe.embers); i > 0; i--) lay(mats.ember, floorSpot(true), 0.3 + rand() * 0.25);
  for (let i = n(recipe.splatter); i > 0; i--) lay(mats.bloodSplatter, floorSpot(true), 0.18 + rand() * 0.16);
  for (let i = n(recipe.puddles); i > 0; i--) {
    const at = floorSpot(true);
    const material = recipe.liquid === 'blood' ? mats.blood : recipe.liquid === 'slime' ? mats.slime : pick(mats.water);
    lay(material, at, 0.16 + rand() * 0.2);
    if (recipe.liquid === 'slime') plan.bubbles.push({ x: at[0], z: at[1], offset: rand() * 10 });
    if (recipe.liquid === 'water' && plan.drips.length < Math.max(1, n(recipe.drips))) {
      plan.drips.push({ x: at[0], z: at[1], period: 2.4 + rand() * 2.2, offset: rand() * 5 });
    }
  }

  // On the walls: stains, cracks, moss creeping up from the floor.
  for (let i = n(recipe.stains); i > 0 && hangable.length; i--) {
    const { w, top } = pick(hangable);
    const h = 0.18 + rand() * 0.14;
    const [x, z] = facePoint(w, 0.003, (rand() - 0.5) * 0.1);
    plan.walls.push({ material: mats.stain, x, y: top - h / 2 - 0.005, z, turn: facing(INWARD[w.side]), w: 0.2 + rand() * 0.15, h });
  }
  for (let i = n(recipe.cracks * 0.6); i > 0 && hangable.length; i--) {
    const { w } = pick(hangable);
    const [x, z] = facePoint(w, 0.004, (rand() - 0.5) * 0.15);
    const size = 0.14 + rand() * 0.1;
    plan.walls.push({
      material: pick(mats.cracks), x, y: FLOOR_THICKNESS + 0.1 + rand() * 0.18, z, turn: facing(INWARD[w.side]), w: size, h: size,
    });
  }
  for (let i = n(recipe.moss * 0.7); i > 0 && walls.length; i--) {
    const { w } = pick(walls);
    const [x, z] = facePoint(w, 0.005, (rand() - 0.5) * 0.12);
    plan.walls.push({ material: pick(mats.moss), x, y: FLOOR_THICKNESS + 0.05, z, turn: facing(INWARD[w.side]), w: 0.36, h: 0.14 });
  }

  // Hanging from the wall tops: vines (with leaves spilling over the top) and chains.
  const used = new Set<number>();
  const freeWall = () => {
    const free = hangable.filter((x) => !used.has(x.index));
    if (!free.length) return null;
    const x = pick(free);
    used.add(x.index);
    return x;
  };
  for (let i = n(recipe.vines); i > 0; i--) {
    const spot = freeWall();
    if (!spot) break;
    const { w, top } = spot;
    const [x, z] = facePoint(w, 0.003, (rand() - 0.5) * 0.08);
    plan.hanging.push({
      kind: 'vine', x, y: top, z, turn: facing(INWARD[w.side]), length: 0.2 + rand() * 0.16, variant: Math.floor(rand() * 2), phase: rand() * 6,
    });
    // A clump of leaves on top of the wall the vine falls from.
    plan.walls.push({
      material: pick(mats.moss), x: w.x, y: top + 0.002, z: w.z, turn: w.alongX ? 0 : Math.PI / 2, w: SQUARE * 0.95, h: WALL_THICKNESS * 2.6, flat: true,
    });
  }
  for (let i = n(recipe.chains); i > 0; i--) {
    const spot = freeWall();
    if (!spot) break;
    const { w, top } = spot;
    const [x, z] = facePoint(w, 0.016, (rand() - 0.5) * 0.2);
    plan.hanging.push({
      kind: 'chain', x, y: top - 0.03, z, turn: facing(INWARD[w.side]), length: 5 + Math.floor(rand() * 4), variant: 0, phase: rand() * 6,
    });
  }

  // Standing by the walls: mushrooms, grass, crystals, skulls.
  const stand = (kind: Clutter['kind'], amount: number) => {
    for (let i = n(amount); i > 0 && besideWall.length; i--) {
      const { w } = pick(besideWall);
      const [x, z] = facePoint(w, 0.05 + rand() * 0.04, (rand() - 0.5) * SQUARE * 0.6);
      plan.clutter.push({ kind, x, z, seed: Math.floor(rand() * 1e6) });
    }
  };
  stand('mushrooms', recipe.mushrooms);
  stand('grass', recipe.grass);
  stand('crystals', recipe.crystals);
  stand('skull', recipe.skulls);

  // Roots breaking through a wall and crawling over the floor.
  for (let i = n(recipe.roots); i > 0 && besideWall.length; i--) {
    const { w, top } = pick(besideWall);
    const along = (rand() - 0.5) * 0.2;
    const sway = (rand() - 0.5) * 0.25;
    const at = (out: number, side: number, y: number) => {
      const [x, z] = facePoint(w, out, along + side);
      return new THREE.Vector3(x, y, z);
    };
    plan.roots.push([
      at(0, 0, top - 0.04),
      at(0.025, sway * 0.2, top - 0.17),
      at(0.05, sway * 0.5, FLOOR_THICKNESS + 0.015),
      at(0.13 + rand() * 0.06, sway, FLOOR_THICKNESS + 0.006),
      at(0.22 + rand() * 0.06, sway * 1.4, FLOOR_THICKNESS + 0.004),
    ]);
  }

  // Cobwebs strung across a room's corners, up under the ceiling.
  if (room) {
    const [cx, cz] = room.center;
    const [hw, hd] = [room.size[0] / 2, room.size[1] / 2];
    [-1, 1].forEach((sx) =>
      [-1, 1].forEach((sz) => {
        if (rand() >= recipe.webs) return;
        const corner = sqKey(cx + sx * (hw - SQUARE / 2), cz + sz * (hd - SQUARE / 2));
        if ((walledSides.get(corner) ?? 0) < 2) return; // a doorway there
        const size = 0.22 + rand() * 0.08;
        const d = size / 2 / Math.SQRT2;
        const n2: Vec2 = [-sx, -sz];
        if (rand() < 0.5) {
          // Its spider, let down on a thread a little way out of the corner.
          const out = d + 0.05;
          plan.spiders.push({
            x: cx + sx * hw + n2[0] * out,
            z: cz + sz * hd + n2[1] * out,
            top: FLOOR_THICKNESS + WALL_HEIGHT * 0.92,
            seed: Math.floor(rand() * 1e6),
          });
        }
        plan.walls.push({
          material: mats.web,
          x: cx + sx * hw + n2[0] * d,
          y: FLOOR_THICKNESS + WALL_HEIGHT * 0.92 - size / 2,
          z: cz + sz * hd + n2[1] * d,
          turn: facing(n2),
          w: size,
          h: size,
        });
      }),
    );
  }

  // Rats run to and fro along a straight stretch of wall.
  for (let i = n(recipe.rats); i > 0 && besideWall.length; i--) {
    const { w } = pick(besideWall);
    const line = (x: WallSegment) => (w.alongX ? x.z : x.x);
    const pos = (x: WallSegment) => (w.alongX ? x.x : x.z);
    const run = piece.walls.filter((x) => x.side === w.side && Math.abs(line(x) - line(w)) < 0.01).map(pos);
    // The unbroken stretch the chosen segment sits in.
    let lo = pos(w);
    let hi = pos(w);
    while (run.some((p) => Math.abs(p - (lo - SQUARE)) < 0.01)) lo -= SQUARE;
    while (run.some((p) => Math.abs(p - (hi + SQUARE)) < 0.01)) hi += SQUARE;
    if (hi - lo < SQUARE) continue;
    const at = (along: number) => facePoint(w, 0.035, along - pos(w));
    plan.rats.push({ from: at(lo - SQUARE * 0.3), to: at(hi + SQUARE * 0.3), seed: Math.floor(rand() * 1e6) });
  }

  if (theme === 'teleport') plan.rune = spent ? mats.rune.spent : portal === 'red' ? mats.rune.red : mats.rune.blue;
  plan.motes = recipe.motes === 'arcane' && spent ? null : (recipe.motes ?? null);
  return plan;
};

/* ── Pieces ── */

const Hang = ({ item, kit, register }: { item: Hanging; kit: DecorKit; register: (g: THREE.Group | null) => void }) => (
  <group position={[item.x, item.y, item.z]} rotation={[0, item.turn, 0]}>
    <group ref={register} userData={{ phase: item.phase, kind: item.kind }}>
      {item.kind === 'vine' ? (
        <mesh
          geometry={kit.geo.plane}
          material={kit.mats.vines[item.variant]}
          position={[0, -item.length / 2, 0]}
          scale={[SQUARE * 0.85, item.length, 1]}
        />
      ) : (
        Array.from({ length: item.length }, (_, i) => (
          <mesh
            key={i}
            geometry={kit.geo.link}
            material={kit.mats.iron}
            position={[0, -i * 0.021, 0]}
            rotation={[0, i % 2 ? Math.PI / 2 : 0, 0]}
            scale={i === item.length - 1 ? 1.8 : 1}
          />
        ))
      )}
    </group>
  </group>
);

const Mushrooms = ({ item, kit }: { item: Clutter; kit: DecorKit }) => {
  const rand = mulberry32(item.seed);
  const violet = rand() > 0.55;
  const caps = 3 + Math.floor(rand() * 3);
  return (
    <group position={[item.x, FLOOR_THICKNESS, item.z]}>
      {Array.from({ length: caps }, (_, i) => {
        const h = 0.018 + rand() * 0.04;
        const r = 0.01 + rand() * 0.016;
        const x = (rand() - 0.5) * 0.08;
        const z = (rand() - 0.5) * 0.08;
        return (
          <group key={i} position={[x, 0, z]} rotation={[(rand() - 0.5) * 0.4, 0, (rand() - 0.5) * 0.4]}>
            <mesh geometry={kit.geo.stem} material={kit.mats.stem} position={[0, h / 2, 0]} scale={[r * 0.3, h, r * 0.3]} />
            <mesh
              geometry={kit.geo.cap}
              material={violet ? kit.mats.capViolet : kit.mats.capTeal}
              position={[0, h, 0]}
              scale={[r, r * 0.6, r]}
            />
          </group>
        );
      })}
      <sprite material={violet ? kit.mats.glowViolet : kit.mats.glowTeal} position={[0, 0.04, 0]} scale={[0.2, 0.2, 1]} />
    </group>
  );
};

const Grass = ({ item, kit }: { item: Clutter; kit: DecorKit }) => {
  const rand = mulberry32(item.seed);
  return (
    <group position={[item.x, FLOOR_THICKNESS, item.z]}>
      {Array.from({ length: 2 + Math.floor(rand() * 3) }, (_, i) => {
        const s = 0.09 + rand() * 0.06;
        const turn = rand() * Math.PI;
        const at: [number, number, number] = [(rand() - 0.5) * 0.09, s / 2, (rand() - 0.5) * 0.09];
        return (
          <group key={i} position={at} rotation={[0, turn, 0]}>
            <mesh geometry={kit.geo.plane} material={kit.mats.grass} scale={[s * 1.2, s, 1]} />
            <mesh geometry={kit.geo.plane} material={kit.mats.grass} rotation={[0, Math.PI / 2, 0]} scale={[s * 1.2, s, 1]} />
          </group>
        );
      })}
    </group>
  );
};

const Crystals = ({ item, kit }: { item: Clutter; kit: DecorKit }) => {
  const rand = mulberry32(item.seed);
  return (
    <group position={[item.x, FLOOR_THICKNESS, item.z]}>
      {Array.from({ length: 3 + Math.floor(rand() * 3) }, (_, i) => {
        const h = 0.04 + rand() * 0.07;
        return (
          <mesh
            key={i}
            geometry={kit.geo.crystal}
            material={kit.mats.crystal}
            position={[(rand() - 0.5) * 0.07, h * 0.6, (rand() - 0.5) * 0.07]}
            rotation={[(rand() - 0.5) * 0.7, rand() * Math.PI, (rand() - 0.5) * 0.7]}
            scale={[0.014 + rand() * 0.008, h, 0.014 + rand() * 0.008]}
          />
        );
      })}
      <sprite material={kit.mats.glowCrystal} position={[0, 0.05, 0]} scale={[0.26, 0.26, 1]} />
    </group>
  );
};

const Skull = ({ item, kit }: { item: Clutter; kit: DecorKit }) => {
  const rand = mulberry32(item.seed);
  return (
    <group position={[item.x, FLOOR_THICKNESS, item.z]} rotation={[0, rand() * Math.PI * 2, (rand() - 0.5) * 0.5]}>
      <mesh geometry={kit.geo.ball} material={kit.mats.bone} position={[0, 0.026, 0]} scale={[0.026, 0.024, 0.03]} />
      <mesh geometry={kit.geo.box} material={kit.mats.bone} position={[0, 0.008, 0.016]} scale={[0.026, 0.012, 0.018]} />
      {[-1, 1].map((s) => (
        <mesh key={s} geometry={kit.geo.ball} material={kit.mats.socket} position={[s * 0.009, 0.028, 0.026]} scale={0.006} />
      ))}
      {rand() > 0.5 && (
        <mesh
          geometry={kit.geo.stem}
          material={kit.mats.bone}
          position={[0.05, 0.008, -0.01]}
          rotation={[Math.PI / 2, 0, rand() * Math.PI]}
          scale={[0.008, 0.1, 0.008]}
        />
      )}
    </group>
  );
};

const Root = ({ points, kit }: { points: THREE.Vector3[]; kit: DecorKit }) => {
  const geometry = useMemo(() => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 20, 0.011, 5), [points]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return <mesh geometry={geometry} material={kit.mats.root} />;
};

const DRIP_FROM = 0.75;

/** A drop falling from the dark above into a puddle, and the ripple it leaves. */
const Drip = ({ x, z, period, offset, kit }: { x: number; z: number; period: number; offset: number; kit: DecorKit }) => {
  const drop = useRef<THREE.Mesh>(null);
  const ring = useRef<THREE.Mesh>(null);
  const ringMaterial = useMemo(
    () => new THREE.MeshBasicMaterial({ color: '#cfe8ff', transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }),
    [],
  );
  useEffect(() => () => ringMaterial.dispose(), [ringMaterial]);
  useFrame(({ clock }) => {
    const t = ((clock.elapsedTime + offset) % period) / period;
    const fall = 0.22;
    if (drop.current) {
      drop.current.visible = t < fall;
      const k = t / fall;
      drop.current.position.y = DRIP_FROM - (DRIP_FROM - FLOOR_THICKNESS) * k * k;
    }
    if (ring.current) {
      const r = t < fall ? 0 : (t - fall) / (1 - fall);
      const s = 0.005 + Math.sqrt(r) * 0.09;
      ring.current.scale.set(s, s, 1);
      ringMaterial.opacity = t < fall ? 0 : (1 - r) * 0.65;
    }
  });
  return (
    <group position={[x, 0, z]}>
      <mesh ref={drop} geometry={kit.geo.ball} material={kit.mats.drop} scale={[0.006, 0.01, 0.006]} />
      <mesh
        ref={ring}
        geometry={kit.geo.ripple}
        material={ringMaterial}
        position={[0, FLOOR_THICKNESS + 0.004, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
      />
    </group>
  );
};

/** Slime bubbling: a bubble swells and pops, again and again. */
const Bubbles = ({ x, z, offset, kit }: { x: number; z: number; offset: number; kit: DecorKit }) => {
  const bubbles = useRef<(THREE.Mesh | null)[]>([]);
  const spots = useMemo(() => {
    const rand = mulberry32(Math.floor(offset * 1000));
    return Array.from({ length: 3 }, () => ({ dx: (rand() - 0.5) * 0.1, dz: (rand() - 0.5) * 0.1, period: 1.4 + rand() * 1.6, at: rand() * 3 }));
  }, [offset]);
  useFrame(({ clock }) => {
    spots.forEach((b, i) => {
      const mesh = bubbles.current[i];
      if (!mesh) return;
      const t = ((clock.elapsedTime + b.at + offset) % b.period) / b.period;
      const s = t < 0.85 ? 0.004 + t * 0.016 : 0.0001;
      mesh.scale.setScalar(s);
    });
  });
  return (
    <group position={[x, FLOOR_THICKNESS + 0.002, z]}>
      {spots.map((b, i) => (
        <mesh
          key={i}
          ref={(m) => {
            bubbles.current[i] = m;
          }}
          geometry={kit.geo.ball}
          material={kit.mats.bubble}
          position={[b.dx, 0, b.dz]}
        />
      ))}
    </group>
  );
};

const MOTE_LOOKS: Record<MoteKind, { color: string; count: number; size: number; rise: number; drift: number; twinkle: number }> = {
  dust: { color: '#ffe2a8', count: 16, size: 0.028, rise: 0.004, drift: 0.05, twinkle: 0.6 },
  fireflies: { color: '#d8ff5a', count: 12, size: 0.05, rise: 0, drift: 0.12, twinkle: 2.4 },
  spores: { color: '#5affd0', count: 18, size: 0.034, rise: 0.012, drift: 0.06, twinkle: 1 },
  embers: { color: '#ff7a2a', count: 26, size: 0.04, rise: 0.09, drift: 0.04, twinkle: 3 },
  arcane: { color: '#7ab8ff', count: 20, size: 0.036, rise: 0.05, drift: 0.03, twinkle: 2 },
};
const MOTE_FLOOR = 0.07;
const MOTE_CEILING = 0.55;

/** Specks in the air of a room: they drift, rise and twinkle (additive: dark = gone). */
const Motes = ({
  room,
  kind,
  red,
  seed,
  glow,
}: {
  room: RoomInfo;
  kind: MoteKind;
  red: boolean;
  seed: number;
  glow: THREE.Texture;
}) => {
  const look = MOTE_LOOKS[kind];
  const { geometry, base, material } = useMemo(() => {
    const rand = mulberry32(seed * 31 + 5);
    const base = Array.from({ length: look.count }, () => ({
      x: room.center[0] + (rand() - 0.5) * (room.size[0] - 0.2),
      z: room.center[1] + (rand() - 0.5) * (room.size[1] - 0.2),
      y: rand(),
      phase: rand() * Math.PI * 2,
      speed: 0.6 + rand() * 0.8,
    }));
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(look.count * 3), 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(look.count * 3), 3));
    const material = new THREE.PointsMaterial({
      map: glow,
      size: look.size,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      toneMapped: false,
    });
    return { geometry, base, material };
  }, [room, look, seed, glow]);
  useEffect(
    () => () => {
      geometry.dispose();
      material.dispose();
    },
    [geometry, material],
  );
  const tint = useMemo(() => new THREE.Color(kind === 'arcane' && red ? '#ff5a48' : look.color), [kind, red, look]);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const pos = geometry.getAttribute('position') as THREE.BufferAttribute;
    const col = geometry.getAttribute('color') as THREE.BufferAttribute;
    const span = MOTE_CEILING - MOTE_FLOOR;
    base.forEach((m, i) => {
      const lift = (m.y + (t * look.rise * m.speed) / span) % 1;
      const y = MOTE_FLOOR + lift * span + Math.sin(t * 0.7 * m.speed + m.phase) * 0.02;
      const x = m.x + Math.sin(t * 0.4 * m.speed + m.phase) * look.drift;
      const z = m.z + Math.cos(t * 0.33 * m.speed + m.phase * 1.3) * look.drift;
      pos.setXYZ(i, x, y, z);
      // Fade in at the floor, out at the top, and twinkle.
      const edge = Math.min(1, lift * 5, (1 - lift) * 4);
      const blink = 0.55 + 0.45 * Math.sin(t * look.twinkle * m.speed + m.phase * 3);
      const b = Math.max(0, (look.rise > 0 ? edge : 1) * blink);
      col.setXYZ(i, tint.r * b, tint.g * b, tint.b * b);
    });
    pos.needsUpdate = true;
    col.needsUpdate = true;
  });
  return <points geometry={geometry} material={material} frustumCulled={false} />;
};

const RuneCircle = ({ room, material, kit }: { room: RoomInfo; material: THREE.Material; kit: DecorKit }) => {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) ref.current.rotation.z = clock.elapsedTime * 0.15;
  });
  return (
    <mesh
      ref={ref}
      geometry={kit.geo.plane}
      material={material}
      position={[room.center[0], FLOOR_THICKNESS + 0.003, room.center[1]]}
      rotation={[-Math.PI / 2, 0, 0]}
      scale={[0.95, 0.95, 1]}
    />
  );
};

/**
 * A rat: it sits sniffing at one end of a wall, darts along it to the other end,
 * and sits there a while before running back.
 */
const Rat = ({ from, to, seed, kit }: { from: Vec2; to: Vec2; seed: number; kit: DecorKit }) => {
  const body = useRef<THREE.Group>(null);
  const timing = useMemo(() => {
    const rand = mulberry32(seed);
    const length = Math.hypot(to[0] - from[0], to[1] - from[1]);
    return { run: length / (0.45 + rand() * 0.25), rest: 1.5 + rand() * 3, offset: rand() * 20 };
  }, [from, to, seed]);
  const heading = Math.atan2(to[0] - from[0], to[1] - from[1]);
  useFrame(({ clock }) => {
    const g = body.current;
    if (!g) return;
    const { run, rest, offset } = timing;
    const t = (clock.elapsedTime + offset) % ((run + rest) * 2);
    // Out (run, rest), then back (run, rest).
    const back = t >= run + rest;
    const local = back ? t - run - rest : t;
    const running = local < run;
    const k = running ? local / run : 1;
    const eased = k * k * (3 - 2 * k);
    const f = back ? 1 - eased : eased;
    // A scurrying bob while it runs, a twitching nose while it sits.
    const bob = running ? Math.abs(Math.sin(clock.elapsedTime * 40)) * 0.004 : 0;
    g.position.set(from[0] + (to[0] - from[0]) * f, FLOOR_THICKNESS + bob, from[1] + (to[1] - from[1]) * f);
    const sniff = running ? 0 : Math.sin(clock.elapsedTime * 9 + seed) * 0.25;
    g.rotation.y = heading + (back ? Math.PI : 0) + sniff;
  });
  return (
    <group ref={body}>
      <mesh geometry={kit.geo.ball} material={kit.mats.fur} position={[0, 0.016, 0]} scale={[0.016, 0.015, 0.03]} />
      <mesh geometry={kit.geo.ball} material={kit.mats.fur} position={[0, 0.02, 0.03]} scale={[0.01, 0.01, 0.014]} />
      {[-1, 1].map((s) => (
        <mesh key={s} geometry={kit.geo.ball} material={kit.mats.fur} position={[s * 0.007, 0.03, 0.026]} scale={0.005} />
      ))}
      <mesh geometry={kit.geo.ball} material={kit.mats.eye} position={[0, 0.022, 0.044]} scale={0.003} />
      <mesh
        geometry={kit.geo.stem}
        material={kit.mats.tail}
        position={[0, 0.008, -0.055]}
        rotation={[Math.PI / 2 - 0.15, 0, 0]}
        scale={[0.0025, 0.05, 0.0025]}
      />
    </group>
  );
};

/** A spider let down from a corner on its thread, slowly rising and dropping. */
const Spider = ({ x, z, top, seed, kit }: { x: number; z: number; top: number; seed: number; kit: DecorKit }) => {
  const body = useRef<THREE.Group>(null);
  const thread = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const drop = 0.1 + (Math.sin(clock.elapsedTime * 0.5 + seed) * 0.5 + 0.5) * 0.12;
    if (body.current) {
      body.current.position.y = top - drop;
      body.current.rotation.y = Math.sin(clock.elapsedTime * 0.7 + seed) * 0.6;
    }
    if (thread.current) {
      thread.current.position.y = top - drop / 2;
      thread.current.scale.y = drop;
    }
  });
  return (
    <group position={[x, 0, z]}>
      <mesh ref={thread} geometry={kit.geo.stem} material={kit.mats.thread} scale={[0.0008, 1, 0.0008]} />
      <group ref={body}>
        <mesh geometry={kit.geo.ball} material={kit.mats.spider} position={[0, -0.012, 0]} scale={[0.014, 0.014, 0.016]} />
        <mesh geometry={kit.geo.ball} material={kit.mats.spider} position={[0, -0.002, 0]} scale={0.008} />
        {[-1, 1].flatMap((s) =>
          [0, 1, 2, 3].map((i) => (
            <mesh
              key={`${s}${i}`}
              geometry={kit.geo.box}
              material={kit.mats.spider}
              position={[s * 0.014, -0.006, (i - 1.5) * 0.007]}
              rotation={[0, (i - 1.5) * 0.35 * s, s * 0.6]}
              scale={[0.022, 0.0018, 0.0018]}
            />
          )),
        )}
      </group>
    </group>
  );
};

interface PieceDecorProps {
  kit: DecorKit;
  piece: Piece;
  seed: number;
  /** The room this piece is, or null for a corridor. */
  room: RoomInfo | null;
  portal?: 'blue' | 'red';
  spent?: boolean;
  lowGraphics?: boolean;
}

/** All the dressing of one room or corridor. */
export const PieceDecor = ({ kit, piece, seed, room, portal, spent = false, lowGraphics = false }: PieceDecorProps) => {
  const plan = useMemo(() => planDecor(kit, piece, seed, room, portal, spent), [kit, piece, seed, room, portal, spent]);
  const swaying = useRef<THREE.Group[]>([]);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    swaying.current.forEach((g) => {
      const phase = g.userData.phase as number;
      if (g.userData.kind === 'vine') {
        g.rotation.x = -(0.035 + 0.03 * Math.sin(t * 0.9 + phase));
      } else {
        g.rotation.x = -(0.03 + 0.02 * Math.sin(t * 1.3 + phase));
        g.rotation.z = Math.sin(t * 1.1 + phase) * 0.06;
      }
    });
  });
  return (
    <group>
      {plan.floor.map((d, i) => (
        <mesh
          key={`f${i}`}
          geometry={kit.geo.plane}
          material={d.material}
          position={[d.x, FLOOR_THICKNESS + 0.0015 + i * 0.0002, d.z]}
          rotation={[-Math.PI / 2, 0, d.turn]}
          scale={[d.size, d.size, 1]}
        />
      ))}
      {plan.rune && room && <RuneCircle room={room} material={plan.rune} kit={kit} />}
      {plan.walls.map((d, i) =>
        d.flat ? (
          <mesh
            key={`w${i}`}
            geometry={kit.geo.plane}
            material={d.material}
            position={[d.x, d.y, d.z]}
            rotation={[-Math.PI / 2, 0, d.turn]}
            scale={[d.w, d.h, 1]}
          />
        ) : (
          <mesh
            key={`w${i}`}
            geometry={kit.geo.plane}
            material={d.material}
            position={[d.x, d.y, d.z]}
            rotation={[0, d.turn, 0]}
            scale={[d.w, d.h, 1]}
          />
        ),
      )}
      {plan.hanging
        .filter((h) => !lowGraphics || h.kind === 'vine')
        .map((h, i) => (
          <Hang
            key={`h${i}`}
            item={h}
            kit={kit}
            register={(g) => {
              if (g && !swaying.current.includes(g)) swaying.current.push(g);
              swaying.current = swaying.current.filter((x) => x.parent);
            }}
          />
        ))}
      {!lowGraphics && (
        <>
          {plan.clutter.map((c, i) =>
            c.kind === 'mushrooms' ? (
              <Mushrooms key={`c${i}`} item={c} kit={kit} />
            ) : c.kind === 'grass' ? (
              <Grass key={`c${i}`} item={c} kit={kit} />
            ) : c.kind === 'crystals' ? (
              <Crystals key={`c${i}`} item={c} kit={kit} />
            ) : (
              <Skull key={`c${i}`} item={c} kit={kit} />
            ),
          )}
          {plan.roots.map((points, i) => (
            <Root key={`r${i}`} points={points} kit={kit} />
          ))}
          {plan.drips.map((d, i) => (
            <Drip key={`d${i}`} {...d} kit={kit} />
          ))}
          {plan.bubbles.map((b, i) => (
            <Bubbles key={`b${i}`} {...b} kit={kit} />
          ))}
          {plan.rats.map((r, i) => (
            <Rat key={`rat${i}`} {...r} kit={kit} />
          ))}
          {plan.spiders.map((sp, i) => (
            <Spider key={`sp${i}`} {...sp} kit={kit} />
          ))}
          {plan.motes && room && (
            <Motes room={room} kind={plan.motes} red={portal === 'red'} seed={seed} glow={kit.tex.glow} />
          )}
        </>
      )}
    </group>
  );
};
