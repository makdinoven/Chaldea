import { useCallback, useEffect, useState } from 'react';
import { useStore, type ReactFlowState } from 'reactflow';

const SNAP_THRESHOLD = 5; // px — how close to snap
const NODE_CENTER_OFFSET = 50; // half of 100px node width/height

interface GuideLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * Renders alignment guide lines (like Figma) when dragging a node.
 * Shows red dashed lines when the dragged node's center aligns with
 * any other node's center on the X or Y axis.
 */
const AlignmentGuides = () => {
  const [guides, setGuides] = useState<GuideLine[]>([]);

  const nodes = useStore((s: ReactFlowState) => s.nodeInternals);
  const transform = useStore((s: ReactFlowState) => s.transform);

  // Listen for node drag via DOM events
  const handleNodeDrag = useCallback(() => {
    const nodeArray = Array.from(nodes.values());
    const dragging = nodeArray.find((n) => n.dragging);
    if (!dragging) {
      setGuides([]);
      return;
    }

    const dragCenterX = (dragging.position?.x ?? 0) + NODE_CENTER_OFFSET;
    const dragCenterY = (dragging.position?.y ?? 0) + NODE_CENTER_OFFSET;

    const newGuides: GuideLine[] = [];
    const allX: number[] = [];
    const allY: number[] = [];

    for (const node of nodeArray) {
      if (node.id === dragging.id) continue;
      const cx = (node.position?.x ?? 0) + NODE_CENTER_OFFSET;
      const cy = (node.position?.y ?? 0) + NODE_CENTER_OFFSET;
      allX.push(cx);
      allY.push(cy);
    }

    // Find X alignment
    for (const cx of allX) {
      if (Math.abs(dragCenterX - cx) < SNAP_THRESHOLD) {
        const minY = Math.min(dragCenterY, ...allY.filter((y) => {
          const matchNode = nodeArray.find((n) => {
            const nx = (n.position?.x ?? 0) + NODE_CENTER_OFFSET;
            return Math.abs(nx - cx) < 2 && n.id !== dragging.id;
          });
          return matchNode !== undefined;
        }));
        const maxY = Math.max(dragCenterY, ...allY.filter((y) => {
          const matchNode = nodeArray.find((n) => {
            const nx = (n.position?.x ?? 0) + NODE_CENTER_OFFSET;
            return Math.abs(nx - cx) < 2 && n.id !== dragging.id;
          });
          return matchNode !== undefined;
        }));

        newGuides.push({
          x1: cx, y1: minY - 50,
          x2: cx, y2: maxY + 50,
        });
        break;
      }
    }

    // Find Y alignment
    for (const cy of allY) {
      if (Math.abs(dragCenterY - cy) < SNAP_THRESHOLD) {
        const matchingX = allX.filter((x) => {
          const matchNode = nodeArray.find((n) => {
            const ny = (n.position?.y ?? 0) + NODE_CENTER_OFFSET;
            return Math.abs(ny - cy) < 2 && n.id !== dragging.id;
          });
          return matchNode !== undefined;
        });

        const minX = Math.min(dragCenterX, ...matchingX);
        const maxX = Math.max(dragCenterX, ...matchingX);

        newGuides.push({
          x1: minX - 50, y1: cy,
          x2: maxX + 50, y2: cy,
        });
        break;
      }
    }

    setGuides(newGuides);
  }, [nodes]);

  // Poll for dragging state (ReactFlow doesn't expose a nice drag event for this)
  useEffect(() => {
    const interval = setInterval(handleNodeDrag, 16); // ~60fps
    return () => clearInterval(interval);
  }, [handleNodeDrag]);

  if (guides.length === 0) return null;

  const [zoomX, zoomY, zoom] = transform;

  return (
    <svg
      className="absolute inset-0 pointer-events-none"
      style={{ zIndex: 1000, overflow: 'visible' }}
    >
      {guides.map((g, i) => (
        <line
          key={i}
          x1={g.x1 * zoom + zoomX}
          y1={g.y1 * zoom + zoomY}
          x2={g.x2 * zoom + zoomX}
          y2={g.y2 * zoom + zoomY}
          stroke="#f87171"
          strokeWidth={1}
          strokeDasharray="4 3"
          opacity={0.8}
        />
      ))}
    </svg>
  );
};

export default AlignmentGuides;
