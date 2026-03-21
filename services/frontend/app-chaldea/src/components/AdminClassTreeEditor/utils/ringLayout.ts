import type { Node } from 'reactflow';

interface NodeWithRing {
  level_ring: number;
}

/**
 * Auto-layout algorithm: arrange nodes in concentric rings by level_ring.
 * Center = (centerX, centerY), each ring at increasing radius.
 */
export const autoLayoutRings = (
  nodes: Node[],
  centerX = 400,
  centerY = 400
): Node[] => {
  // Group nodes by level_ring
  const groups = new Map<number, Node[]>();
  for (const node of nodes) {
    const ring = (node.data as NodeWithRing).level_ring ?? 1;
    if (!groups.has(ring)) groups.set(ring, []);
    groups.get(ring)!.push(node);
  }

  // Sort rings by value
  const sortedRings = [...groups.keys()].sort((a, b) => a - b);

  // Map ring values to radii
  const ringRadiusMap: Record<number, number> = {
    1: 0,
    5: 150,
    10: 260,
    15: 370,
    20: 480,
    25: 590,
    30: 700,
    35: 810,
    40: 920,
    45: 1030,
    50: 1140,
  };

  const updatedNodes = new Map<string, Node>();

  for (const ring of sortedRings) {
    const ringNodes = groups.get(ring)!;
    const radius = ringRadiusMap[ring] ?? ring * 20;

    if (radius === 0) {
      // Center node(s) — stack vertically if multiple
      ringNodes.forEach((node, i) => {
        updatedNodes.set(node.id, {
          ...node,
          position: {
            x: centerX,
            y: centerY + i * 80,
          },
        });
      });
    } else {
      // Distribute evenly around the circle
      const count = ringNodes.length;
      const angleStep = (2 * Math.PI) / count;
      const startAngle = -Math.PI / 2; // Start from top

      ringNodes.forEach((node, i) => {
        const angle = startAngle + i * angleStep;
        updatedNodes.set(node.id, {
          ...node,
          position: {
            x: centerX + radius * Math.cos(angle),
            y: centerY + radius * Math.sin(angle),
          },
        });
      });
    }
  }

  return nodes.map((node) => updatedNodes.get(node.id) ?? node);
};


/**
 * Auto-align nodes in horizontal rows by level_ring.
 * Bottom-up: lays out the bottom row evenly, then each parent row
 * centers each parent over its children.
 *
 * Accepts ReactFlow edges (source/target may be parent→child or child→parent;
 * direction is determined by comparing level_ring values).
 */
export const autoAlignRows = (
  nodes: Node[],
  edges: { source: string; target: string }[] = [],
  startY = 80,
  rowGap = 140,
  nodeGap = 160,
): Node[] => {
  if (nodes.length === 0) return nodes;

  // --- helpers ---
  type Ring = number;
  const ringOf = (id: string): Ring => {
    const n = nodes.find((nd) => nd.id === id);
    return (n?.data as { level_ring: number })?.level_ring ?? 0;
  };

  // Group nodes by ring
  const groups = new Map<Ring, Node[]>();
  for (const node of nodes) {
    const r = ringOf(node.id);
    if (!groups.has(r)) groups.set(r, []);
    groups.get(r)!.push(node);
  }
  const sortedRings = [...groups.keys()].sort((a, b) => a - b); // root first

  // Build parent→children map (parent = lower ring)
  const childrenOf = new Map<string, Set<string>>();
  for (const e of edges) {
    const sr = ringOf(e.source);
    const tr = ringOf(e.target);
    if (sr === tr) continue; // same-ring edge, skip
    const [pid, cid] = sr < tr ? [e.source, e.target] : [e.target, e.source];
    if (!childrenOf.has(pid)) childrenOf.set(pid, new Set());
    childrenOf.get(pid)!.add(cid);
  }

  // --- layout bottom-up ---
  const posX = new Map<string, number>(); // node id → x

  const reversedRings = [...sortedRings].reverse(); // leaves first

  for (const ring of reversedRings) {
    const row = groups.get(ring)!;

    // Separate nodes that have positioned children vs those that don't
    const withKids: { node: Node; avgX: number }[] = [];
    const noKids: Node[] = [];

    for (const node of row) {
      const kids = childrenOf.get(node.id);
      if (kids && kids.size > 0) {
        const kidXs = [...kids].map((k) => posX.get(k)).filter((x) => x !== undefined) as number[];
        if (kidXs.length > 0) {
          withKids.push({ node, avgX: kidXs.reduce((a, b) => a + b, 0) / kidXs.length });
          continue;
        }
      }
      noKids.push(node);
    }

    if (withKids.length === 0 && noKids.length > 0) {
      // Pure leaf row — spread evenly
      const w = (noKids.length - 1) * nodeGap;
      noKids.forEach((node, i) => {
        posX.set(node.id, -w / 2 + i * nodeGap);
      });
    } else {
      // Sort parents by their children's center
      withKids.sort((a, b) => a.avgX - b.avgX);

      // Fix overlaps
      for (let i = 1; i < withKids.length; i++) {
        if (withKids[i].avgX - withKids[i - 1].avgX < nodeGap) {
          withKids[i].avgX = withKids[i - 1].avgX + nodeGap;
        }
      }

      for (const { node, avgX } of withKids) {
        posX.set(node.id, avgX);
      }

      // Place orphan nodes (no kids) filling gaps or at the end
      if (noKids.length > 0) {
        const placedXs = withKids.map((w) => w.avgX);
        const minPlaced = Math.min(...placedXs);
        const maxPlaced = Math.max(...placedXs);
        // Place before or after
        noKids.forEach((node, i) => {
          if (i % 2 === 0) {
            posX.set(node.id, maxPlaced + (Math.floor(i / 2) + 1) * nodeGap);
          } else {
            posX.set(node.id, minPlaced - (Math.floor(i / 2) + 1) * nodeGap);
          }
        });
      }
    }
  }

  // --- shift so leftmost node starts at x=200 ---
  const allXs = [...posX.values()];
  const minX = Math.min(...allXs);
  const offsetX = 200 - minX;

  // --- build final positions ---
  return nodes.map((node) => {
    const x = posX.get(node.id);
    if (x === undefined) return node;
    const rowIdx = sortedRings.indexOf(ringOf(node.id));
    return {
      ...node,
      position: { x: x + offsetX, y: startY + rowIdx * rowGap },
    };
  });
};
