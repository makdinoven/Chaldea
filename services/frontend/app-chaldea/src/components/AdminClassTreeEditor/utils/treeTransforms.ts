import type { Node, Edge } from 'reactflow';
import type {
  FullClassTreeResponse,
  FullClassTreeUpdateRequest,
  TreeNodeInTree,
  TreeNodeConnectionInTree,
  TreeNodeSkillEntry,
  TreeNodeInTreeResponse,
} from '../types';

/**
 * Convert API full tree response to ReactFlow nodes and edges.
 */
export const apiToReactFlow = (
  fullTree: FullClassTreeResponse
): { nodes: Node[]; edges: Edge[] } => {
  const nodes: Node[] = fullTree.nodes.map((apiNode) => ({
    id: String(apiNode.id),
    type: 'treeNode',
    position: { x: apiNode.position_x, y: apiNode.position_y },
    data: {
      ...apiNode,
      id: apiNode.id,
    },
  }));

  const edges: Edge[] = fullTree.connections.map((conn) => ({
    id: String(conn.id ?? `edge-${conn.from_node_id}-${conn.to_node_id}`),
    source: String(conn.from_node_id),
    target: String(conn.to_node_id),
    type: 'default',
    style: { stroke: '#f0d95c', strokeWidth: 2 },
  }));

  return { nodes, edges };
};

/**
 * Convert ReactFlow nodes and edges back to API format for PUT request.
 */
export const reactFlowToApi = (
  rfNodes: Node[],
  rfEdges: Edge[],
  treeMetadata: {
    id: number;
    class_id: number;
    name: string;
    description: string | null;
    tree_type: string;
    parent_tree_id: number | null;
    subclass_name: string | null;
    tree_image: string | null;
  }
): FullClassTreeUpdateRequest => {
  const nodes: TreeNodeInTree[] = rfNodes.map((rfNode) => {
    const data = rfNode.data as TreeNodeInTreeResponse;
    const skills: TreeNodeSkillEntry[] = (data.skills ?? []).map((s) => ({
      skill_id: s.skill_id,
      sort_order: s.sort_order ?? 0,
    }));

    return {
      id: data.id,
      level_ring: data.level_ring,
      position_x: rfNode.position.x,
      position_y: rfNode.position.y,
      name: data.name,
      description: data.description ?? null,
      node_type: data.node_type,
      icon_image: data.icon_image ?? null,
      sort_order: data.sort_order ?? 0,
      skills,
    };
  });

  const connections: TreeNodeConnectionInTree[] = rfEdges.map((edge) => {
    // Temp IDs (temp-c-N) and fallback edge-X-Y IDs are kept as strings for new connections
    // Numeric string IDs (from existing DB connections) are converted back to numbers
    const edgeId = edge.id.startsWith('temp-') || edge.id.startsWith('edge-')
      ? edge.id
      : isNaN(Number(edge.id)) ? edge.id : Number(edge.id);

    return {
      id: edgeId,
      from_node_id: isNaN(Number(edge.source)) ? edge.source : Number(edge.source),
      to_node_id: isNaN(Number(edge.target)) ? edge.target : Number(edge.target),
    };
  });

  return {
    ...treeMetadata,
    nodes,
    connections,
  };
};
