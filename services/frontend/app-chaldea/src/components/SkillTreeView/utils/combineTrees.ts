import type {
  FullClassTreeResponse,
  TreeNodeInTreeResponse,
} from '../types';
import { LEVEL_RING_OPTIONS } from '../../AdminClassTreeEditor/types';

/**
 * Lays the class trees out as one Path-of-Exile-style wheel.
 *
 * The stored ``position_x`` / ``position_y`` are a grid meant for the admin
 * editor and do not survive being packed into a 120° wedge, so the wheel
 * derives its own polar layout instead: ``level_ring`` becomes the distance
 * from the centre, and each class fans out across its own sector. The authored
 * order within a ring is preserved, so branches still sit where their author
 * put them relative to each other.
 *
 * Nothing here mutates the source data or the stored coordinates.
 */

/** Everything about the wheel's shape, in one place so it can be tuned. */
export interface WheelLayoutConfig {
  /** Distance from the centre to ring 1, where the class roots sit. */
  innerRadius: number;
  /** Distance between two consecutive rings of the ladder. */
  ringSpacing: number;
  /**
   * How a ring's nodes spread across the sector.
   *
   * "arc" keeps a constant gap in pixels between neighbours, so outer rings
   * stay dense and the class reads as a wedge widening outward.
   * "fill" gives every ring the same angular width, so the rings read as
   * concentric arcs and the class reads as a slice of a wheel.
   */
  spread: 'arc' | 'fill';
  /** Target gap, in pixels, between neighbouring nodes on the same ring. Used by "arc". */
  arcSpacing: number;
  /** Share of its 120° sector a class may fill, 0..1. */
  sectorFill: number;
  /** Where the first class sits, in degrees. -90 is straight up. */
  startAngleDeg: number;
}

export const DEFAULT_WHEEL_LAYOUT: WheelLayoutConfig = {
  // Small on purpose: the three class starts should read as one shared centre,
  // parted just enough not to overlap. It also sets where every other ring
  // lands, and the tightest spot on the wheel is where two sectors nearly meet
  // at ring 5 — this puts that ring far enough out for the nodes to clear.
  innerRadius: 115,
  ringSpacing: 150,
  spread: 'fill',
  arcSpacing: 120,
  sectorFill: 0.8,
  startAngleDeg: -90,
};

/** Bridges drawn between each pair of neighbouring sectors. */
const BRIDGES_PER_SECTOR_PAIR = 2;

/**
 * The ladder of ring values a node can sit on, shared with the admin editor.
 *
 * A ring's radius comes from its place on this ladder rather than from its
 * place among the rings a given tree happens to use — otherwise ring 30 would
 * land at a different distance in each class, and the rings would never line up
 * into shared circles across the wheel. A ring nobody filled leaves a real gap.
 */
const RING_LADDER: number[] = LEVEL_RING_OPTIONS.map((o) => o.value);

export interface CombinedNode {
  node: TreeNodeInTreeResponse;
  /** Centre of the node in the combined coordinate space. */
  x: number;
  y: number;
}

export interface CombinedTree {
  tree: FullClassTreeResponse;
  /** Sector index, 0-based, in the order the trees were passed in. */
  sector: number;
  nodes: CombinedNode[];
}

/** A decorative, always-locked link between two neighbouring sectors. */
export interface SectorBridge {
  id: string;
  fromNodeId: string;
  toNodeId: string;
}

export interface CombinedLayout {
  trees: CombinedTree[];
  bridges: SectorBridge[];
  /**
   * Node id -> its centre in the combined space. Keyed by string because the
   * admin editor gives unsaved nodes temporary ids like "temp-6-1".
   */
  positions: Map<string, { x: number; y: number }>;
}

/** Groups a tree's nodes by level_ring, innermost ring first. */
const byRing = (nodes: TreeNodeInTreeResponse[]): [number, TreeNodeInTreeResponse[]][] => {
  const groups = new Map<number, TreeNodeInTreeResponse[]>();
  for (const node of nodes) {
    const ring = node.level_ring ?? 1;
    const bucket = groups.get(ring);
    if (bucket) bucket.push(node);
    else groups.set(ring, [node]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([ring, ringNodes]) => [
      ring,
      // sort_order is the author's explicit knob, so it wins. A ring that never
      // set it (all zeros) ties and falls through to the left-to-right order
      // drawn in the editor, which is how older trees stay put.
      [...ringNodes].sort(
        (a, b) =>
          (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
          a.position_x - b.position_x ||
          String(a.id).localeCompare(String(b.id), undefined, { numeric: true }),
      ),
    ]);
};

/** Radius of a ring, by its place on the shared ladder. */
const radiusOfRing = (ring: number, fallbackIndex: number, config: WheelLayoutConfig): number => {
  const laddered = RING_LADDER.indexOf(ring);
  const index = laddered >= 0 ? laddered : fallbackIndex;
  return config.innerRadius + index * config.ringSpacing;
};

/** Fans one tree out across its sector, ring by ring. */
const placeTree = (
  tree: FullClassTreeResponse,
  sector: number,
  sectorCount: number,
  config: WheelLayoutConfig,
): CombinedTree => {
  if (tree.nodes.length === 0) return { tree, sector, nodes: [] };

  const sectorCentre =
    (config.startAngleDeg * Math.PI) / 180 + (2 * Math.PI * sector) / sectorCount;
  const maxSpan = ((2 * Math.PI) / sectorCount) * config.sectorFill;

  const placed: CombinedNode[] = [];
  byRing(tree.nodes).forEach(([ring, ringNodes], ringIndex) => {
    const radius = radiusOfRing(ring, ringIndex, config);
    const count = ringNodes.length;
    const evenAngle = count > 1 ? maxSpan / (count - 1) : 0;
    // "arc" keeps neighbours a fixed distance apart but never spills out of the
    // sector; "fill" simply uses the whole sector on every ring.
    const step =
      config.spread === 'fill'
        ? evenAngle
        : count > 1
          ? Math.min(config.arcSpacing / radius, evenAngle)
          : 0;

    ringNodes.forEach((node, i) => {
      const angle = sectorCentre + (i - (count - 1) / 2) * step;
      placed.push({
        node,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      });
    });
  });

  return { tree, sector, nodes: placed };
};

/**
 * Picks the visually shortest links between two neighbouring sectors, without
 * reusing a node. These are decoration: a player can never travel across one,
 * because the backend only ever lets you choose nodes in your own class tree.
 */
const bridgeSectors = (a: CombinedTree, b: CombinedTree, limit: number): SectorBridge[] => {
  const pairs: { from: CombinedNode; to: CombinedNode; distance: number }[] = [];
  for (const from of a.nodes) {
    for (const to of b.nodes) {
      pairs.push({ from, to, distance: Math.hypot(from.x - to.x, from.y - to.y) });
    }
  }
  pairs.sort((p, q) => p.distance - q.distance);

  const used = new Set<string>();
  const bridges: SectorBridge[] = [];
  for (const pair of pairs) {
    if (bridges.length >= limit) break;
    const fromId = String(pair.from.node.id);
    const toId = String(pair.to.node.id);
    if (used.has(fromId) || used.has(toId)) continue;
    used.add(fromId);
    used.add(toId);
    bridges.push({ id: `bridge-${fromId}-${toId}`, fromNodeId: fromId, toNodeId: toId });
  }
  return bridges;
};

/** Arranges the given trees into one wheel. Trees without nodes are kept but contribute nothing. */
export const combineTrees = (
  trees: FullClassTreeResponse[],
  config: WheelLayoutConfig = DEFAULT_WHEEL_LAYOUT,
): CombinedLayout => {
  const placed = trees.map((tree, i) => placeTree(tree, i, trees.length, config));

  const positions = new Map<string, { x: number; y: number }>();
  for (const t of placed) {
    for (const n of t.nodes) positions.set(String(n.node.id), { x: n.x, y: n.y });
  }

  const bridges: SectorBridge[] = [];
  const populated = placed.filter((t) => t.nodes.length > 0);
  // Every sector is bridged to the next one around the wheel. With two sectors
  // that is a single bridge, not the same pair twice.
  const pairCount = populated.length === 2 ? 1 : populated.length;
  for (let i = 0; i < pairCount; i++) {
    const a = populated[i];
    const b = populated[(i + 1) % populated.length];
    if (a && b && a !== b) bridges.push(...bridgeSectors(a, b, BRIDGES_PER_SECTOR_PAIR));
  }

  return { trees: placed, bridges, positions };
};
