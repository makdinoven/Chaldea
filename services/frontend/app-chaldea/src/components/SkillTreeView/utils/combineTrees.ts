import type {
  FullClassTreeResponse,
  TreeNodeInTreeResponse,
} from '../types';

/**
 * Lays the class trees out as one Path-of-Exile-style wheel.
 *
 * The stored ``position_x`` / ``position_y`` are a grid meant for the admin
 * editor and do not survive being packed into a 120° wedge, so the wheel
 * derives its own polar layout instead: ``level_ring`` becomes the distance
 * from the centre, and each class fans out across its own sector. The authored
 * left-to-right order within a ring is preserved, so branches still sit where
 * their author put them relative to each other.
 *
 * Nothing here mutates the source data or the stored coordinates.
 */

/** Radius of the innermost ring (where the root nodes sit). */
const INNER_RADIUS = 260;

/** Distance between two consecutive rings. */
const RING_SPACING = 150;

/** Target gap, in pixels, between neighbouring nodes on the same ring. */
const ARC_SPACING = 120;

/** Share of a sector left empty, so neighbouring classes stay visually apart. */
const SECTOR_GAP = 0.2;

/** Sector of the first tree. -90° puts it straight up. */
const FIRST_SECTOR_ANGLE = -Math.PI / 2;

/** Bridges drawn between each pair of neighbouring sectors. */
const BRIDGES_PER_SECTOR_PAIR = 2;

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
  fromNodeId: number;
  toNodeId: number;
}

export interface CombinedLayout {
  trees: CombinedTree[];
  bridges: SectorBridge[];
  /** Node id -> its centre in the combined space. */
  positions: Map<number, { x: number; y: number }>;
}

/** Groups a tree's nodes by level_ring, innermost ring first. */
const byRing = (nodes: TreeNodeInTreeResponse[]): TreeNodeInTreeResponse[][] => {
  const groups = new Map<number, TreeNodeInTreeResponse[]>();
  for (const node of nodes) {
    const ring = node.level_ring ?? 1;
    const bucket = groups.get(ring);
    if (bucket) bucket.push(node);
    else groups.set(ring, [node]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, ringNodes]) =>
      // Keep the order the author laid out left-to-right; fall back to
      // sort_order and id so the result is stable for identical coordinates.
      [...ringNodes].sort(
        (a, b) =>
          a.position_x - b.position_x ||
          (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
          a.id - b.id,
      ),
    );
};

/** Fans one tree out across its sector, ring by ring. */
const placeTree = (
  tree: FullClassTreeResponse,
  sector: number,
  sectorCount: number,
): CombinedTree => {
  if (tree.nodes.length === 0) return { tree, sector, nodes: [] };

  const sectorCentre = FIRST_SECTOR_ANGLE + (2 * Math.PI * sector) / sectorCount;
  const maxSpan = ((2 * Math.PI) / sectorCount) * (1 - SECTOR_GAP);

  const placed: CombinedNode[] = [];
  byRing(tree.nodes).forEach((ringNodes, ringIndex) => {
    const radius = INNER_RADIUS + ringIndex * RING_SPACING;
    const count = ringNodes.length;
    // Even pixel spacing along the arc, but never wider than the sector.
    const step =
      count > 1 ? Math.min(ARC_SPACING / radius, maxSpan / (count - 1)) : 0;

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
