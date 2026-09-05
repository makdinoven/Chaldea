import type {
  TreeNodeInTreeResponse,
  TreeNodeConnectionInTree,
  NodeVisualState,
} from '../types';

/**
 * Works out what each node of a tree looks like to a given character.
 *
 * The states split along one line: whether a node can still be had.
 *
 * - chosen: already taken
 * - available: can be taken right now
 * - locked: not yet — the level is too low, or the chain leading to it is not
 *   walked — but still perfectly possible later
 * - blocked: an alternative at the same fork was taken, so this one is gone
 * - unreachable: every route to it runs through a blocked node, so it is gone
 *   too, however far down the tree it sits
 *
 * That last state is the point of doing this per tree rather than per node: a
 * dead branch does not end at the fork, it carries on to everything hanging off
 * it, and nothing about a single node tells you that.
 */

interface TreeGraph {
  /** node id -> ids of connected nodes on a lower ring. */
  parents: Map<number, number[]>;
  /** node id -> ids of nodes that share a parent and sit on the same ring. */
  siblings: Map<number, number[]>;
  byId: Map<number, TreeNodeInTreeResponse>;
  ringOrder: number[];
}

const buildGraph = (
  nodes: TreeNodeInTreeResponse[],
  connections: TreeNodeConnectionInTree[],
): TreeGraph => {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const neighbours = new Map<number, Set<number>>();
  for (const conn of connections) {
    const from = Number(conn.from_node_id);
    const to = Number(conn.to_node_id);
    if (!byId.has(from) || !byId.has(to)) continue;
    if (!neighbours.has(from)) neighbours.set(from, new Set());
    if (!neighbours.has(to)) neighbours.set(to, new Set());
    neighbours.get(from)!.add(to);
    neighbours.get(to)!.add(from);
  }

  // Connections are stored without direction, so a node's parents are simply
  // its neighbours on a lower ring.
  const parents = new Map<number, number[]>();
  const children = new Map<number, number[]>();
  for (const node of nodes) {
    const linked = [...(neighbours.get(node.id) ?? [])];
    parents.set(
      node.id,
      linked.filter((id) => (byId.get(id)?.level_ring ?? 0) < node.level_ring),
    );
    children.set(
      node.id,
      linked.filter((id) => (byId.get(id)?.level_ring ?? 0) > node.level_ring),
    );
  }

  // Siblings share a parent and a ring: taking one gives up the others.
  const siblings = new Map<number, number[]>();
  for (const node of nodes) {
    const found = new Set<number>();
    for (const parentId of parents.get(node.id) ?? []) {
      for (const childId of children.get(parentId) ?? []) {
        if (childId !== node.id && byId.get(childId)?.level_ring === node.level_ring) {
          found.add(childId);
        }
      }
    }
    siblings.set(node.id, [...found]);
  }

  const ringOrder = [...new Set(nodes.map((n) => n.level_ring))].sort((a, b) => a - b);
  return { parents, siblings, byId, ringOrder };
};

export interface TreeStates {
  state: Map<number, NodeVisualState>;
  /** Nodes that can no longer be taken, whether blocked outright or cut off. */
  dead: Set<number>;
}

export const computeTreeStates = (
  nodes: TreeNodeInTreeResponse[],
  connections: TreeNodeConnectionInTree[],
  chosenNodeIds: Set<number>,
  characterLevel: number,
): TreeStates => {
  const graph = buildGraph(nodes, connections);

  const blocked = new Set<number>();
  for (const node of nodes) {
    if (chosenNodeIds.has(node.id)) continue;
    if ((graph.siblings.get(node.id) ?? []).some((id) => chosenNodeIds.has(id))) {
      blocked.add(node.id);
    }
  }

  /*
    A node is still alive if it is taken, or if it is not blocked and some
    parent is alive — you have to walk through a parent to reach it. Parents
    always sit on a lower ring, so working outwards ring by ring settles it in
    one pass.
  */
  const alive = new Set<number>();
  const byRing = new Map<number, TreeNodeInTreeResponse[]>();
  for (const node of nodes) {
    byRing.set(node.level_ring, [...(byRing.get(node.level_ring) ?? []), node]);
  }
  for (const ring of graph.ringOrder) {
    for (const node of byRing.get(ring) ?? []) {
      if (chosenNodeIds.has(node.id)) {
        alive.add(node.id);
        continue;
      }
      if (blocked.has(node.id)) continue;
      const parents = graph.parents.get(node.id) ?? [];
      // A root hangs from nothing; so does a node whose links were never drawn.
      if (node.node_type === 'root' || parents.length === 0) {
        alive.add(node.id);
        continue;
      }
      if (parents.some((id) => alive.has(id))) alive.add(node.id);
    }
  }

  const dead = new Set<number>();
  const state = new Map<number, NodeVisualState>();
  for (const node of nodes) {
    if (chosenNodeIds.has(node.id)) {
      state.set(node.id, 'chosen');
      continue;
    }
    if (blocked.has(node.id)) {
      state.set(node.id, 'blocked');
      dead.add(node.id);
      continue;
    }
    if (!alive.has(node.id)) {
      state.set(node.id, 'unreachable');
      dead.add(node.id);
      continue;
    }
    if (characterLevel < node.level_ring) {
      state.set(node.id, 'locked');
      continue;
    }
    if (node.node_type === 'root') {
      state.set(node.id, 'available');
      continue;
    }
    const parents = graph.parents.get(node.id) ?? [];
    state.set(
      node.id,
      parents.some((id) => chosenNodeIds.has(id)) ? 'available' : 'locked',
    );
  }

  return { state, dead };
};
