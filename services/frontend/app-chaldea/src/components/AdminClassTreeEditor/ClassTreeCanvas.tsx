import { useMemo, useCallback } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  type NodeMouseHandler,
  type EdgeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';
import TreeNodeComponent from './TreeNodeComponent';
import AlignmentGuides from './AlignmentGuides';

interface ClassTreeCanvasProps {
  nodes: Node[];
  edges: Edge[];
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: OnConnect;
  onNodeClick: (nodeId: string) => void;
  onEdgeDelete: (edgeId: string) => void;
}

const SNAP_GRID: [number, number] = [10, 10];

const ClassTreeCanvas = ({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeClick,
  onEdgeDelete,
}: ClassTreeCanvasProps) => {
  const nodeTypes = useMemo(() => ({ treeNode: TreeNodeComponent }), []);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      onNodeClick(node.id);
    },
    [onNodeClick]
  );

  const handleEdgeClick: EdgeMouseHandler = useCallback(
    (_event, edge) => {
      if (window.confirm('Удалить связь между узлами?')) {
        onEdgeDelete(edge.id);
      }
    },
    [onEdgeDelete]
  );

  return (
    <div className="w-full h-full relative" style={{ minHeight: 400 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        nodeTypes={nodeTypes}
        fitView
        selectNodesOnDrag={false}
        elevateNodesOnSelect={true}
        snapToGrid={true}
        snapGrid={SNAP_GRID}
        defaultEdgeOptions={{
          style: { stroke: '#f0d95c', strokeWidth: 2 },
          type: 'default',
        }}
        className="bg-transparent"
      >
        <Background color="#ffffff15" gap={20} size={1} />
        <Controls className="!bg-site-bg !border-white/10 !rounded-card [&_button]:!bg-site-bg [&_button]:!border-white/10 [&_button]:!fill-white [&_button:hover]:!bg-white/10" />
        <MiniMap
          nodeColor="#f0d95c"
          maskColor="rgba(26,26,46,0.8)"
          className="!bg-site-bg !border-white/10 !rounded-card"
        />
        <AlignmentGuides />
      </ReactFlow>
    </div>
  );
};

export default ClassTreeCanvas;
