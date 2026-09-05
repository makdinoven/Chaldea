import { useCallback, useMemo } from 'react';
import ReactFlow, {
  Controls,
  MiniMap,
  ConnectionMode,
  type Connection,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type EdgeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';
import toast from 'react-hot-toast';
import PlayerNodeComponent from '../SkillTreeView/PlayerNodeComponent';
import {
  GradientEdge,
  BridgeEdge,
  classGradientColors,
  defaultGradient,
} from '../SkillTreeView/treeEdges';

/**
 * The class wheel, exactly as players see it, but editable: click a node to
 * inspect it, drag from anywhere on one node to another to link them, click a
 * link to remove it. Node positions come from the shared wheel layout, so there
 * is nothing to drag around.
 */

interface CombinedTreeCanvasProps {
  nodes: Node[];
  edges: Edge[];
  onNodeClick: (nodeId: string) => void;
  onEdgeDelete: (edgeId: string) => void;
  /** Returns an error message when the link is not allowed, else null. */
  onConnectNodes: (params: Connection) => string | null;
}

const MINIMAP_CLASS_COLORS: Record<number, string> = {
  1: '#f87171',
  2: '#34d399',
  3: '#38bdf8',
};

const CombinedTreeCanvas = ({
  nodes,
  edges,
  onNodeClick,
  onEdgeDelete,
  onConnectNodes,
}: CombinedTreeCanvasProps) => {
  const nodeTypes = useMemo(() => ({ playerNode: PlayerNodeComponent }), []);
  const edgeTypes = useMemo(() => ({ gradient: GradientEdge, bridge: BridgeEdge }), []);

  // Colour each link by the class that owns it, the same way the player view does.
  const colouredEdges = useMemo(
    () =>
      edges.map((edge) => {
        if (edge.type !== 'gradient') return edge;
        const classId = (edge.data?.classId ?? 1) as number;
        const gradient = classGradientColors[classId] ?? defaultGradient;
        return { ...edge, data: { ...edge.data, colors: gradient.faint, strokeWidth: 1.5 } };
      }),
    [edges],
  );

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => onNodeClick(node.id),
    [onNodeClick],
  );

  const handleEdgeClick: EdgeMouseHandler = useCallback(
    (_event, edge) => {
      // Sector bridges are decoration derived from the layout, not stored links.
      if (edge.type === 'bridge') return;
      if (window.confirm('Удалить связь между узлами?')) onEdgeDelete(edge.id);
    },
    [onEdgeDelete],
  );

  const handleConnect = useCallback(
    (params: Connection) => {
      const error = onConnectNodes(params);
      if (error) toast.error(error);
    },
    [onConnectNodes],
  );

  return (
    <div className="w-full h-full relative bg-[#12121e]" style={{ minHeight: 400 }}>
      {/* Same vignette the player view uses, so the preview is honest */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(circle at 50% 50%, rgba(10,10,18,0.15) 0%, rgba(10,10,18,0.6) 55%, rgba(10,10,18,0.9) 80%)',
        }}
      />
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.04]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      <ReactFlow
        nodes={nodes}
        edges={colouredEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onConnect={handleConnect}
        // Handles cover the whole node while editing, so a drop lands on
        // whichever handle happens to be on top; loose mode accepts either.
        connectionMode={ConnectionMode.Loose}
        connectionLineStyle={{ stroke: '#f0d95c', strokeWidth: 2 }}
        nodesDraggable={false}
        nodesConnectable
        elementsSelectable
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.1}
        maxZoom={2.5}
        className="!bg-transparent"
        style={{ position: 'relative', zIndex: 2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Controls
          showInteractive={false}
          className="!bg-site-bg !border-white/10 !rounded-card [&_button]:!bg-site-bg [&_button]:!border-white/10 [&_button]:!fill-white [&_button:hover]:!bg-white/10"
        />
        <MiniMap
          nodeColor={(node) => MINIMAP_CLASS_COLORS[(node.data?.classId ?? 1) as number] ?? '#f0d95c'}
          maskColor="rgba(18,18,30,0.8)"
          className="!bg-site-bg !border-white/10 !rounded-card"
        />
      </ReactFlow>
    </div>
  );
};

export default CombinedTreeCanvas;
