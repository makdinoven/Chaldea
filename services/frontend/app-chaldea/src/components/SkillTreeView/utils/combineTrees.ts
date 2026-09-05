import type {
  FullClassTreeResponse,
  TreeNodeInTreeResponse,
} from '../types';

/**
 * Lays the three class trees out as one Path-of-Exile-style wheel.
 *
 * Each tree keeps the layout its author drew in the admin editor — we only
 * apply a rigid transform (rotate + translate) so that the tree's root sits on
 * an inner ring and the rest of it grows outward into its own 120° sector.
 * Nothing here mutates the source data or the stored coordinates.
 */

/** Distance from the wheel's centre to each tree's root node. */
const INNER_RADIUS = 420;

/** Sector of the first tree. -90° puts it straight up. */
const FIRST_SECTOR_ANGLE = -Math.PI / 2;

/** Bridges drawn between each pair of neighbouring sectors. */
const BRIDGES_PER_SECTOR_PAIR = 2;

export interface CombinedNode {
  node: TreeNodeInTreeResponse;
  /** Position in the combined coordinate space. */
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
  fromNodeId: number;
  toNodeId: number;
}

export interface CombinedLayout {
  trees: CombinedTree[];
  bridges: SectorBridge[];
  /** Node id -> its position in the combined space. */
  positions: Map<number, { x: number; y: number }>;
}

const centroidOf = (nodes: TreeNodeInTreeResponse[]) => {
  const sum = nodes.reduce(
    (acc, n) => ({ x: acc.x + n.position_x, y: acc.y + n.position_y }),
    { x: 0, y: 0 },
  );
  return { x: sum.x / nodes.length, y: sum.y / nodes.length };
};

/**
 * The node the tree hangs from: its root, else the lowest ring, else the first
 * node. This is what gets pinned to the inner ring.
 */
const anchorOf = (nodes: TreeNodeInTreeResponse[]): TreeNodeInTreeResponse => {
  const root = nodes.find((n) => n.node_type === 'root');
  if (root) return root;
  return nodes.reduce((best, n) => (n.level_ring < best.level_ring ? n : best), nodes[0]);
};

/**
 * Places one tree into its sector.
 *
 * The tree is rotated so the direction "root -> rest of the tree" points
 * radially outward, which keeps hand-drawn layouts readable whichever way they
 * were originally drawn (top-down, bottom-up, sideways).
 */
const placeTree = (tree: FullClassTreeResponse, sector: number, sectorCount: number): CombinedTree => {
  if (tree.nodes.length === 0) return { tree, sector, nodes: [] };

  const sectorAngle = FIRST_SECTOR_ANGLE + (2 * Math.PI * sector) / sectorCount;
  const outward = { x: Math.cos(sectorAngle), y: Math.sin(sectorAngle) };

  const anchor = anchorOf(tree.nodes);
  const centroid = centroidOf(tree.nodes);

  // Direction the tree grows in, in its own coordinate space.
  const growth = { x: centroid.x - anchor.position_x, y: centroid.y - anchor.position_y };
  const growthLength = Math.hypot(growth.x, growth.y);
  // A single-node tree (or a perfectly symmetric one) has no growth direction;
  // treat it as growing "up", which is how the editor lays trees out.
  const growthAngle = growthLength < 1e-6 ? -Math.PI / 2 : Math.atan2(growth.y, growth.x);

  const rotation = sectorAngle - growthAngle;
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);

  const originX = outward.x * INNER_RADIUS;
  const originY = outward.y * INNER_RADIUS;

  const nodes = tree.nodes.map((node) => {
    const localX = node.position_x - anchor.position_x;
    const localY = node.position_y - anchor.position_y;
    return {
      node,
      x: originX + localX * cos - localY * sin,
      y: originY + localX * sin + localY * cos,
    };
  });

  return { tree, sector, nodes };
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

  const used = new Set<number>();
  const bridges: SectorBridge[] = [];
  for (const pair of pairs) {
    if (bridges.length >= limit) break;
    if (used.has(pair.from.node.id) || used.has(pair.to.node.id)) continue;
    used.add(pair.from.node.id);
    used.add(pair.to.node.id);
    bridges.push({
      id: `bridge-${pair.from.node.id}-${pair.to.node.id}`,
      fromNodeId: pair.from.node.id,
      toNodeId: pair.to.node.id,
    });
  }
  return bridges;
};

/** Arranges the given trees into one wheel. Trees without nodes are kept but contribute nothing. */
export const combineTrees = (trees: FullClassTreeResponse[]): CombinedLayout => {
  const placed = trees.map((tree, i) => placeTree(tree, i, trees.length));

  const positions = new Map<number, { x: number; y: number }>();
  for (const t of placed) {
    for (const n of t.nodes) positions.set(n.node.id, { x: n.x, y: n.y });
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
