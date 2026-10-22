import { computeTreeStates } from '../utils/computeNodeState';
import type {
  CharacterTreeProgressResponse,
  FullClassTreeResponse,
  NodeVisualState,
  TreeNodeInTreeResponse,
} from '../types';

/*
  Where a class tree goes on an open book. The tree has the right-hand page to
  itself, growing from its foot to its head; the left-hand page is kept for
  whichever node is being read. The gutter is left clear — anything drawn in
  it folds into the binding.

  Spread coordinates: u runs across both pages, -1 at the left fore-edge, 0 at
  the gutter, 1 at the right fore-edge; v runs up the page, 0 at the tail
  (nearest the reader), 1 at the head.
*/

/** Height on the spread of the first and the last level. */
const FIRST_LEVEL_V = 0.12;
const LAST_LEVEL_V = 0.8;
/** The tree's axis: the middle of the right page, leaving the outer margin free for the level marks. */
const AXIS_U = 0.5;
/** Widest gap between neighbours on a level, and the widest a level may spread either side of the axis. */
const MAX_STEP_U = 0.115;
const MAX_HALF_SPAN_U = 0.34;

export interface SpreadNode {
  id: number;
  node: TreeNodeInTreeResponse;
  u: number;
  v: number;
  state: NodeVisualState;
  /** Subclass picks: drawn larger and named. */
  large: boolean;
}

export type SpreadEdgeKind =
  /** Both ends taken: the path walked, in gold. */
  | 'walked'
  /** From a taken node to one that can be taken now. */
  | 'open'
  /** Not yet reachable: a pencil sketch. */
  | 'locked'
  /** Into a branch the player has closed off. */
  | 'dead'
  /** Another class's book: plain ink throughout. */
  | 'plain';

export interface SpreadEdge {
  from: SpreadNode;
  to: SpreadNode;
  kind: SpreadEdgeKind;
}

export interface SpreadModel {
  nodes: SpreadNode[];
  edges: SpreadEdge[];
  /** Each level and where it sits, for the margin marks. */
  levels: { level: number; v: number }[];
  /** Another class's book: read-only, nothing in it is the player's. */
  foreign: boolean;
  classId: number;
}

/** A level's nodes in the author's order: sort_order first, then left to right in the editor. */
const orderRing = (nodes: TreeNodeInTreeResponse[]) =>
  [...nodes].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.position_x - b.position_x || a.id - b.id);

export const buildSpread = (
  tree: FullClassTreeResponse,
  progress: CharacterTreeProgressResponse | null,
  foreign: boolean,
): SpreadModel => {
  const chosen = new Set((progress?.chosen_nodes ?? []).map((c) => c.node_id));
  const states = computeTreeStates(tree.nodes, tree.connections, chosen, progress?.character_level ?? 0);

  const rings = [...new Set(tree.nodes.map((n) => n.level_ring ?? 1))].sort((a, b) => a - b);
  const vOf = (index: number) =>
    rings.length > 1 ? FIRST_LEVEL_V + ((LAST_LEVEL_V - FIRST_LEVEL_V) * index) / (rings.length - 1) : FIRST_LEVEL_V;

  const nodes: SpreadNode[] = [];
  rings.forEach((ring, index) => {
    const ringNodes = orderRing(tree.nodes.filter((n) => (n.level_ring ?? 1) === ring));
    const count = ringNodes.length;
    const step = count > 1 ? Math.min(MAX_STEP_U, (MAX_HALF_SPAN_U * 2) / (count - 1)) : 0;
    ringNodes.forEach((node, i) => {
      nodes.push({
        id: node.id,
        node,
        u: AXIS_U + (i - (count - 1) / 2) * step,
        v: vOf(index),
        state: foreign ? 'locked' : states.state.get(node.id) ?? 'locked',
        large: node.node_type === 'subclass_choice',
      });
    });
  });

  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges: SpreadEdge[] = [];
  for (const conn of tree.connections) {
    let a = byId.get(Number(conn.from_node_id));
    let b = byId.get(Number(conn.to_node_id));
    if (!a || !b) continue;
    // Connections carry no direction; branches always grow upward.
    if (a.v > b.v) [a, b] = [b, a];
    let kind: SpreadEdgeKind;
    if (foreign) kind = 'plain';
    else if (chosen.has(a.id) && chosen.has(b.id)) kind = 'walked';
    else if (states.dead.has(a.id) || states.dead.has(b.id)) kind = 'dead';
    else if (chosen.has(a.id) && b.state === 'available') kind = 'open';
    else kind = 'locked';
    edges.push({ from: a, to: b, kind });
  }

  return {
    nodes,
    edges,
    levels: rings.map((level, i) => ({ level, v: vOf(i) })),
    foreign,
    classId: tree.class_id,
  };
};
