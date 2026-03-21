import { useMemo, useCallback } from 'react';
import ReactFlow, {
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';
import PlayerNodeComponent from './PlayerNodeComponent';
import { autoLayoutRings } from '../AdminClassTreeEditor/utils/ringLayout';
import { computeNodeState } from './utils/computeNodeState';
import type {
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
  NodeVisualState,
} from './types';

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
  const nodeTypes = useMemo(() => ({ playerNode: PlayerNodeComponent }), []);

  const chosenNodeIds = useMemo(() => {
    if (!progress) return new Set<number>();
    return new Set(progress.chosen_nodes.map((cn) => cn.node_id));
  }, [progress]);

  const characterLevel = progress?.character_level ?? 0;

  const { nodes, edges } = useMemo(() => {
    // Build nodes with visual state
    const rfNodes: Node[] = tree.nodes.map((apiNode) => {
      const visualState: NodeVisualState = computeNodeState(
        apiNode,
        tree.connections,
        chosenNodeIds,
        characterLevel,
        tree.nodes
      );

      return {
        id: String(apiNode.id),
        type: 'playerNode',
        position: { x: apiNode.position_x, y: apiNode.position_y },
        data: {
          ...apiNode,
          visualState,
        },
        draggable: false,
        selectable: true,
        connectable: false,
      };
    });

    // Auto-layout by rings
    const layoutNodes = autoLayoutRings(rfNodes);

    // Build edges with color based on state
    const rfEdges: Edge[] = tree.connections.map((conn) => {
      const sourceChosen = chosenNodeIds.has(Number(conn.from_node_id));
      const targetChosen = chosenNodeIds.has(Number(conn.to_node_id));
      const isGold = sourceChosen && targetChosen;

      return {
        id: String(conn.id ?? `edge-${conn.from_node_id}-${conn.to_node_id}`),
        source: String(conn.from_node_id),
        target: String(conn.to_node_id),
        type: 'default',
        style: {
          stroke: isGold ? '#f0d95c' : 'rgba(255,255,255,0.15)',
          strokeWidth: isGold ? 2.5 : 1.5,
        },
        animated: isGold,
      };
    });

    return { nodes: layoutNodes, edges: rfEdges };
  }, [tree, chosenNodeIds, characterLevel]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      onNodeClick(Number(node.id));
    },
    [onNodeClick]
  );

  return (
    <div className="w-full h-full min-h-[400px]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        defaultEdgeOptions={{
          type: 'default',
        }}
        className="bg-transparent"
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#ffffff10" gap={20} size={1} />
        <Controls
          showInteractive={false}
          className="!bg-site-bg !border-white/10 !rounded-card [&_button]:!bg-site-bg [&_button]:!border-white/10 [&_button]:!fill-white [&_button:hover]:!bg-white/10"
        />
      </ReactFlow>
    </div>
  );
};

export default PlayerTreeCanvas;
