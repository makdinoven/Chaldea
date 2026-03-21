import { useMemo, useCallback, memo, useState } from 'react';
import ReactFlow, {
  Controls,
  BaseEdge,
  getSmoothStepPath,
  type Node,
  type Edge,
  type EdgeProps,
  type NodeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';
import PlayerNodeComponent from './PlayerNodeComponent';
import { computeNodeState } from './utils/computeNodeState';
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


interface PlayerTreeCanvasProps {
  tree: FullClassTreeResponse;
  progress: CharacterTreeProgressResponse | null;
  onNodeClick: (nodeId: number) => void;
}

const PlayerTreeCanvas = ({
  tree,
  progress,
  onNodeClick,
}: PlayerTreeCanvasProps) => {
  const nodeTypes = useMemo(() => ({
    playerNode: PlayerNodeComponent,
  }), []);

  const edgeTypes = useMemo(() => ({
    gradient: GradientEdge,
  }), []);

  const chosenNodeIds = useMemo(() => {
    if (!progress) return new Set<number>();
    return new Set(progress.chosen_nodes.map((cn) => cn.node_id));
  }, [progress]);

  const characterLevel = progress?.character_level ?? 0;

  const { nodes, edges } = useMemo(() => {
    const rfNodes: Node[] = tree.nodes.map((apiNode) => {
      const visualState: NodeVisualState = computeNodeState(
        apiNode,
        tree.connections,
        chosenNodeIds,
        characterLevel,
        tree.nodes
      );

      // Admin nodes are 100px. Player hex nodes vary (40/70px).
      // Adjust position so centers align.
      const adminSize = 100;
      const nodeType = apiNode.node_type ?? 'regular';
      const playerSize = (nodeType === 'root' || nodeType === 'subclass_choice') ? 70 : 40;
      const offset = (adminSize - playerSize) / 2;

      return {
        id: String(apiNode.id),
        type: 'playerNode',
        position: { x: apiNode.position_x + offset, y: apiNode.position_y + offset },
        data: {
          ...apiNode,
          visualState,
          classId: tree.class_id,
        },
        draggable: false,
        selectable: true,
        connectable: false,
      };
    });

    /* ---------- Edges with gradient styling ---------- */
    const gradient = classGradientColors[tree.class_id] ?? defaultGradient;
    const rfEdges: Edge[] = tree.connections.map((conn) => {
      const sourceChosen = chosenNodeIds.has(Number(conn.from_node_id));
      const targetChosen = chosenNodeIds.has(Number(conn.to_node_id));
      const bothChosen = sourceChosen && targetChosen;
      const oneChosen = sourceChosen || targetChosen;

      let colors: [string, string] = ['rgba(255,255,255,0.06)', 'rgba(255,255,255,0.03)'];
      let strokeWidth = 1;
      let glowing = false;

      if (bothChosen) {
        colors = gradient.bright;
        strokeWidth = 2.5;
        glowing = true;
      } else if (oneChosen) {
        colors = gradient.dim;
        strokeWidth = 1.5;
      }

      return {
        id: String(conn.id ?? `edge-${conn.from_node_id}-${conn.to_node_id}`),
        source: String(conn.from_node_id),
        target: String(conn.to_node_id),
        type: 'gradient',
        data: { colors, strokeWidth, glowing },
      };
    });

    return { nodes: rfNodes, edges: rfEdges };
  }, [tree, chosenNodeIds, characterLevel]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      onNodeClick(Number(node.id));
    },
    [onNodeClick]
  );

  const classArt = classArtMap[tree.class_id] ?? warriorArt;

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
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `url(${classArt})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          opacity: 0.25,
        }}
      />

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
