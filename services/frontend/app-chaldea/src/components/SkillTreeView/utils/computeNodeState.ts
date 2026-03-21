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

  // Prerequisite check: at least one parent must be chosen
  const parentNodeIds = connections
    .filter((c) => Number(c.to_node_id) === node.id)
    .map((c) => Number(c.from_node_id));

  const hasChosenParent = parentNodeIds.some((pid) => chosenNodeIds.has(pid));
  if (!hasChosenParent) return 'locked';

  // Branch conflict: check if any sibling from same parent at same level_ring is chosen
  for (const parentId of parentNodeIds) {
    const siblingNodeIds = connections
      .filter(
        (c) => Number(c.from_node_id) === parentId && Number(c.to_node_id) !== node.id
      )
      .map((c) => Number(c.to_node_id));

    // Filter to same level_ring siblings only
    const sameLevelSiblings = siblingNodeIds.filter((sid) => {
      const siblingNode = allNodes.find((n) => n.id === sid);
      return siblingNode && siblingNode.level_ring === node.level_ring;
    });

    if (sameLevelSiblings.some((sid) => chosenNodeIds.has(sid))) return 'blocked';
  }

  return 'available';
};
