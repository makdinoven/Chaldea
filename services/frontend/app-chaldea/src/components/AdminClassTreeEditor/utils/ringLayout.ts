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
 * Auto-align nodes in horizontal rows by level_ring (one row per ring,
 * lowest ring on top). Within each row the order is decided top-down by the
 * barycenter (average order) of each node's parents, so children sit under
 * their parents and edges don't cross. Nodes with several parents land between
 * them; orphan nodes keep a stable position by id.
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

  type Ring = number;
  const ringOf = (id: string): Ring => {
    const n = nodes.find((nd) => nd.id === id);
    return (n?.data as { level_ring: number })?.level_ring ?? 0;
  };
  const byId = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });

  // Group nodes by ring (top-most ring first)
  const groups = new Map<Ring, Node[]>();
  for (const node of nodes) {
    const r = ringOf(node.id);
    if (!groups.has(r)) groups.set(r, []);
    groups.get(r)!.push(node);
  }
  const sortedRings = [...groups.keys()].sort((a, b) => a - b);

  // child → parents (parent = lower ring)
  const parentsOf = new Map<string, string[]>();
  for (const e of edges) {
    const sr = ringOf(e.source);
    const tr = ringOf(e.target);
    if (sr === tr) continue; // same-ring edge, skip
    const [pid, cid] = sr < tr ? [e.source, e.target] : [e.target, e.source];
    if (!parentsOf.has(cid)) parentsOf.set(cid, []);
    parentsOf.get(cid)!.push(pid);
  }

  // Decide each row's order top-down using parents' barycenter.
  const orderIndex = new Map<string, number>(); // node id → index within its row
  sortedRings.forEach((ring, rowIdx) => {
    const row = groups.get(ring)!;
    let ordered: Node[];
    if (rowIdx === 0) {
      // Top row (roots): keep current left-to-right order, stable by id.
      ordered = [...row].sort((a, b) => a.position.x - b.position.x || byId(a.id, b.id));
    } else {
      const barycenter = (n: Node): number => {
        const idxs = (parentsOf.get(n.id) ?? [])
          .map((p) => orderIndex.get(p))
          .filter((x): x is number => x !== undefined);
        // Parentless nodes sink to the right but stay deterministic.
        return idxs.length ? idxs.reduce((a, b) => a + b, 0) / idxs.length : Number.MAX_SAFE_INTEGER;
      };
      ordered = [...row].sort((a, b) => barycenter(a) - barycenter(b) || byId(a.id, b.id));
    }
    ordered.forEach((n, i) => orderIndex.set(n.id, i));
  });

  // Assign x per row, each row centered around 0 by its order.
  const posX = new Map<string, number>();
  for (const ring of sortedRings) {
    const ordered = [...groups.get(ring)!].sort(
      (a, b) => orderIndex.get(a.id)! - orderIndex.get(b.id)!,
    );
    const width = (ordered.length - 1) * nodeGap;
    ordered.forEach((n, i) => posX.set(n.id, -width / 2 + i * nodeGap));
  }

  // Shift so the leftmost node starts at x=200.
  const offsetX = 200 - Math.min(...posX.values());

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
