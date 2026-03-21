import type {
  TreeNodeInTreeResponse,
  TreeNodeConnectionInTree,
  NodeVisualState,
} from '../types';

/**
 * Compute visual state of a tree node for the player view.
 *
 * - chosen: node is already selected by the player
 * - available: player can choose this node (level ok, prerequisite met, no branch conflict)
 * - locked: level too low or prerequisite not met
 * - blocked: sibling from same parent already chosen (branch conflict)
 */
export const computeNodeState = (
  node: TreeNodeInTreeResponse,
  connections: TreeNodeConnectionInTree[],
  chosenNodeIds: Set<number>,
  characterLevel: number,
  allNodes: TreeNodeInTreeResponse[]
): NodeVisualState => {
  // Already chosen
  if (chosenNodeIds.has(node.id)) return 'chosen';

  // Level check
  if (characterLevel < node.level_ring) return 'locked';

  // Root nodes are always available if level matches
  if (node.node_type === 'root') return 'available';

  // Find connected nodes and determine which are parents (lower level_ring)
  // Connections can go either direction, so check both sides
  const connectedNodeIds = new Set<number>();
  for (const c of connections) {
    const fromId = Number(c.from_node_id);
    const toId = Number(c.to_node_id);
    if (fromId === node.id) connectedNodeIds.add(toId);
    if (toId === node.id) connectedNodeIds.add(fromId);
  }

  // Parents = connected nodes with LOWER level_ring
  const parentNodeIds = [...connectedNodeIds].filter((nid) => {
    const n = allNodes.find((an) => an.id === nid);
    return n && n.level_ring < node.level_ring;
  });

  // Prerequisite check: at least one parent must be chosen
  const hasChosenParent = parentNodeIds.some((pid) => chosenNodeIds.has(pid));
  if (!hasChosenParent) return 'locked';

  // Siblings = other nodes at same level_ring that share a parent
  const siblingNodeIds = new Set<number>();
  for (const parentId of parentNodeIds) {
    for (const c of connections) {
      const fromId = Number(c.from_node_id);
      const toId = Number(c.to_node_id);
      // Find nodes connected to this parent
      if (fromId === parentId && toId !== node.id) {
        const candidate = allNodes.find((n) => n.id === toId);
        if (candidate && candidate.level_ring === node.level_ring) siblingNodeIds.add(toId);
      }
      if (toId === parentId && fromId !== node.id) {
        const candidate = allNodes.find((n) => n.id === fromId);
        if (candidate && candidate.level_ring === node.level_ring) siblingNodeIds.add(fromId);
      }
    }
  }

  // Branch conflict: sibling already chosen
  if ([...siblingNodeIds].some((sid) => chosenNodeIds.has(sid))) return 'blocked';

  return 'available';
};
