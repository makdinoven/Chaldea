import { useMemo, useCallback, memo, useState } from 'react';
import ReactFlow, {
  Controls,
  BaseEdge,
  getSmoothStepPath,
  getStraightPath,
  type Node,
  type Edge,
  type EdgeProps,
  type NodeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';
import PlayerNodeComponent from './PlayerNodeComponent';
import { computeNodeState } from './utils/computeNodeState';
import { combineTrees } from './utils/combineTrees';
import type {
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
  NodeVisualState,
} from './types';

import warriorArt from '../../assets/skillTreeWarrior.png';
import mageArt from '../../assets/skillTreeMage.png';
import rogueArt from '../../assets/skillTreeRogue.png';

/* Map class_id -> art image (DB: 1=Warrior, 2=Rogue, 3=Mage) */
const classArtMap: Record<number, string> = {
  1: warriorArt,
  2: rogueArt,
  3: mageArt,
};

/* Map class_id -> gradient colors (DB: 1=Warrior, 2=Rogue, 3=Mage) */
const classGradientColors: Record<number, { bright: [string, string]; dim: [string, string] }> = {
  1: {
    bright: ['#fbbf24', '#ef4444'],  // Warrior — gold → red
    dim: ['rgba(251,191,36,0.3)', 'rgba(239,68,68,0.2)'],
  },
  2: {
    bright: ['#fbbf24', '#34d399'],  // Rogue — gold → green
    dim: ['rgba(251,191,36,0.3)', 'rgba(52,211,153,0.2)'],
  },
  3: {
    bright: ['#a78bfa', '#38bdf8'],  // Mage — purple → blue
    dim: ['rgba(167,139,250,0.3)', 'rgba(56,189,248,0.2)'],
  },
};

const defaultGradient = classGradientColors[1];

/* Custom gradient edge component */
const GradientEdge = memo(({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) => {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 16,
  });

  const gradientId = `gradient-${id}`;
  const colors = (data?.colors ?? defaultGradient.dim) as [string, string];
  const strokeWidth = (data?.strokeWidth ?? 1) as number;
  const glowing = (data?.glowing ?? false) as boolean;

  return (
    <>
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={colors[0]} />
          <stop offset="100%" stopColor={colors[1]} />
        </linearGradient>
      </defs>
      {/* Glow layer */}
      {glowing && (
        <BaseEdge
          id={`${id}-glow`}
          path={edgePath}
          style={{
            stroke: `url(#${gradientId})`,
            strokeWidth: strokeWidth + 4,
            opacity: 0.3,
            filter: 'blur(3px)',
          }}
        />
      )}
      {/* Main line */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: `url(#${gradientId})`,
          strokeWidth,
        }}
      />
    </>
  );
});

/**
 * Link between two class sectors of the combined wheel. Purely scenic — a
 * character can only ever choose nodes in its own class tree, so these are
 * drawn as severed, dashed lines rather than as a walkable path.
 */
const BridgeEdge = memo(({ id, sourceX, sourceY, targetX, targetY }: EdgeProps) => {
  const [edgePath] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  return (
    <BaseEdge
      id={id}
      path={edgePath}
      style={{
        stroke: 'rgba(255,255,255,0.14)',
        strokeWidth: 1.5,
        strokeDasharray: '2 10',
      }}
    />
  );
});

export interface TreeView {
  tree: FullClassTreeResponse;
  progress: CharacterTreeProgressResponse | null;
  /** Another class's tree: visible for reference, but nothing in it is choosable. */
  readOnly: boolean;
}

interface PlayerTreeCanvasProps {
  views: TreeView[];
  onNodeClick: (nodeId: number) => void;
}

/** Admin nodes are 100px; player hex nodes are 40px, or 70px when large. */
const ADMIN_NODE_SIZE = 100;
const playerNodeSize = (nodeType: string) =>
  nodeType === 'root' || nodeType === 'subclass_choice' ? 70 : 40;

const PlayerTreeCanvas = ({ views, onNodeClick }: PlayerTreeCanvasProps) => {
  const nodeTypes = useMemo(() => ({
    playerNode: PlayerNodeComponent,
  }), []);

  const edgeTypes = useMemo(() => ({
    gradient: GradientEdge,
    bridge: BridgeEdge,
  }), []);

  const combined = views.length > 1;

  const { nodes, edges } = useMemo(() => {
    // In combined mode the trees are arranged into one wheel; in single-tree
    // mode the authored coordinates are used as-is.
    const layout = combined ? combineTrees(views.map((v) => v.tree)) : null;

    const rfNodes: Node[] = [];
    const rfEdges: Edge[] = [];

    for (const view of views) {
      const { tree, progress, readOnly } = view;
      const chosenNodeIds = new Set(
        (progress?.chosen_nodes ?? []).map((cn) => cn.node_id),
      );
      const characterLevel = progress?.character_level ?? 0;

      for (const apiNode of tree.nodes) {
        // A foreign tree carries no progress, so every node in it would come
        // out "locked" anyway — but say so explicitly rather than relying on
        // that, so a foreign root never pulses as if it were available.
        const visualState: NodeVisualState = readOnly
          ? 'locked'
          : computeNodeState(
              apiNode,
              tree.connections,
              chosenNodeIds,
              characterLevel,
              tree.nodes,
            );

        const placed = layout?.positions.get(apiNode.id);
        const baseX = placed?.x ?? apiNode.position_x;
        const baseY = placed?.y ?? apiNode.position_y;
        // Centre the (smaller) player node on the admin node's slot.
        const offset = (ADMIN_NODE_SIZE - playerNodeSize(apiNode.node_type ?? 'regular')) / 2;

        rfNodes.push({
          id: String(apiNode.id),
          type: 'playerNode',
          position: { x: baseX + offset, y: baseY + offset },
          data: {
            ...apiNode,
            visualState,
            classId: tree.class_id,
            foreign: readOnly,
          },
          draggable: false,
          selectable: true,
          connectable: false,
        });
      }

      /* ---------- Edges with gradient styling ---------- */
      const gradient = classGradientColors[tree.class_id] ?? defaultGradient;
      for (const conn of tree.connections) {
        const sourceChosen = chosenNodeIds.has(Number(conn.from_node_id));
        const targetChosen = chosenNodeIds.has(Number(conn.to_node_id));
        const bothChosen = sourceChosen && targetChosen;
        const oneChosen = sourceChosen || targetChosen;

        // Unchosen connections must still read on the dark class art — the old
        // 0.06/0.03 white was effectively invisible. Keep a clear tier:
        // none chosen -> visible neutral, one -> dim class color, both -> bright.
        let colors: [string, string] = ['rgba(255,255,255,0.32)', 'rgba(255,255,255,0.2)'];
        let strokeWidth = 1.5;
        let glowing = false;

        if (bothChosen) {
          colors = gradient.bright;
          strokeWidth = 2.5;
          glowing = true;
        } else if (oneChosen) {
          colors = gradient.dim;
          strokeWidth = 1.5;
        } else if (readOnly) {
          // Another class's branches sit behind the player's own.
          colors = ['rgba(255,255,255,0.16)', 'rgba(255,255,255,0.1)'];
        }

        rfEdges.push({
          id: String(conn.id ?? `edge-${conn.from_node_id}-${conn.to_node_id}`),
          source: String(conn.from_node_id),
          target: String(conn.to_node_id),
          type: 'gradient',
          data: { colors, strokeWidth, glowing },
        });
      }
    }

    for (const bridge of layout?.bridges ?? []) {
      rfEdges.push({
        id: bridge.id,
        source: String(bridge.fromNodeId),
        target: String(bridge.toNodeId),
        type: 'bridge',
        focusable: false,
        interactionWidth: 0,
      });
    }

    return { nodes: rfNodes, edges: rfEdges };
  }, [views, combined]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      onNodeClick(Number(node.id));
    },
    [onNodeClick]
  );

  // The class art only makes sense behind a single class's tree; the combined
  // wheel spans all three, so it gets the plain vignette instead.
  const classArt = combined ? null : classArtMap[views[0]?.tree.class_id ?? 1] ?? warriorArt;

  // Lock minZoom to fitView level + compute translate bounds from node positions
  const [initialZoom, setInitialZoom] = useState<number | null>(null);

  const translateExtent = useMemo((): [[number, number], [number, number]] => {
    if (nodes.length === 0) return [[-Infinity, -Infinity], [Infinity, Infinity]];
    const xs = nodes.map((n) => n.position.x);
    const ys = nodes.map((n) => n.position.y);
    const pad = 150; // extra padding around edges
    return [
      [Math.min(...xs) - pad, Math.min(...ys) - pad],
      [Math.max(...xs) + pad, Math.max(...ys) + pad],
    ];
  }, [nodes]);

  return (
    <div className="relative w-full h-full min-h-[400px] overflow-hidden">
      {/* ---- Class art as fixed background ---- */}
      {classArt && (
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `url(${classArt})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            opacity: 0.25,
          }}
        />
      )}

      {/* ---- Dark radial vignette over the art ---- */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(circle at 50% 50%, rgba(10,10,18,0.15) 0%, rgba(10,10,18,0.6) 55%, rgba(10,10,18,0.9) 80%)',
        }}
      />

      {/* ---- Subtle grid overlay ---- */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.04]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      {/* ---- ReactFlow canvas ---- */}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        panOnDrag={true}
        panOnScroll={false}
        zoomOnScroll={true}
        zoomOnPinch={true}
        zoomOnDoubleClick={true}
        fitView
        fitViewOptions={{ padding: 0.1 }}
        minZoom={initialZoom ?? 0.1}
        maxZoom={2.5}
        translateExtent={translateExtent}
        onInit={(instance) => {
          // After fitView, lock minZoom to current zoom (= fully zoomed out state)
          setTimeout(() => {
            const { zoom } = instance.getViewport();
            setInitialZoom(zoom);
          }, 150);
        }}
        defaultEdgeOptions={{ type: 'default' }}
        className="!bg-transparent"
        style={{ position: 'relative', zIndex: 2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Controls
          showInteractive={false}
          className="
            !bg-[#1a1a2e]/80 !border-white/5 !rounded-lg !shadow-none
            [&_button]:!bg-transparent [&_button]:!border-white/5
            [&_button]:!fill-white/50 [&_button:hover]:!fill-white
            [&_button:hover]:!bg-white/5
          "
        />
      </ReactFlow>
    </div>
  );
};

export default PlayerTreeCanvas;
