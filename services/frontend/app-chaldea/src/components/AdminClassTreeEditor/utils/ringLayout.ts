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
