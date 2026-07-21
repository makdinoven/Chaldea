import type { GraphEdge, WorldGraph } from '../../api/worldGraph';

export type RouteMode = 'energy' | 'steps';

export interface AdjEntry {
  to: number;
  cost: number;
  /** Index into WorldGraph.edges — lets the renderer highlight the exact edge. */
  edgeIndex: number;
}

export type Adjacency = Map<number, AdjEntry[]>;

/**
 * Directed adjacency list. A pair contributes both directions only when both
 * DB rows exist; a missing reverse row yields a genuinely one-way link.
 */
export const buildAdjacency = (edges: GraphEdge[]): Adjacency => {
  const adj: Adjacency = new Map();
  const push = (from: number, to: number, cost: number, edgeIndex: number) => {
    const list = adj.get(from);
    if (list) list.push({ to, cost, edgeIndex });
    else adj.set(from, [{ to, cost, edgeIndex }]);
  };
  edges.forEach((edge, edgeIndex) => {
    if (edge.cost_ab !== null) push(edge.a, edge.b, edge.cost_ab, edgeIndex);
    if (edge.cost_ba !== null) push(edge.b, edge.a, edge.cost_ba, edgeIndex);
  });
  return adj;
};

/**
 * Weakly connected components — an edge counts regardless of direction, so a
 * component means "these locations form one landmass on the map".
 */
export const findComponents = (graph: WorldGraph): Map<number, number> => {
  const undirected = new Map<number, number[]>();
  const link = (from: number, to: number) => {
    const list = undirected.get(from);
    if (list) list.push(to);
    else undirected.set(from, [to]);
  };
  graph.edges.forEach((edge) => {
    link(edge.a, edge.b);
    link(edge.b, edge.a);
  });

  const componentOf = new Map<number, number>();
  let next = 0;
  // Iterate in a stable order so component ids (and therefore colours) stay
  // identical between reloads.
  const ids = graph.locations.map((l) => l.id).sort((a, b) => a - b);
  for (const start of ids) {
    if (componentOf.has(start)) continue;
    const id = next++;
    const stack = [start];
    componentOf.set(start, id);
    while (stack.length) {
      const node = stack.pop() as number;
      for (const neighbour of undirected.get(node) ?? []) {
        if (!componentOf.has(neighbour)) {
          componentOf.set(neighbour, id);
          stack.push(neighbour);
        }
      }
    }
  }
  return componentOf;
};

export interface Leg {
  from: number;
  to: number;
  /** Full node sequence including both endpoints. Empty when unreachable. */
  nodes: number[];
  edgeIndices: number[];
  energy: number;
  steps: number;
  reachable: boolean;
}

export interface RouteResult {
  legs: Leg[];
  nodes: number[];
  edgeIndices: Set<number>;
  energy: number;
  steps: number;
  complete: boolean;
}

/**
 * Dijkstra over energy_cost, or BFS over hop count. Both share this routine —
 * in 'steps' mode every edge is treated as weight 1, which reduces Dijkstra to
 * a shortest-hop search while keeping one code path.
 *
 * Uses a linear scan for the next frontier node rather than a binary heap: the
 * world is ~2k nodes, so the simpler code is not worth optimising away.
 */
const shortestPath = (
  adj: Adjacency,
  from: number,
  to: number,
  mode: RouteMode,
): Leg => {
  const empty: Leg = {
    from, to, nodes: [], edgeIndices: [], energy: 0, steps: 0, reachable: false,
  };
  if (from === to) {
    return { ...empty, nodes: [from], reachable: true };
  }

  const dist = new Map<number, number>([[from, 0]]);
  const prev = new Map<number, { node: number; edgeIndex: number }>();
  const settled = new Set<number>();
  const frontier = new Set<number>([from]);

  while (frontier.size) {
    let current = -1;
    let best = Infinity;
    for (const node of frontier) {
      const d = dist.get(node) ?? Infinity;
      if (d < best) {
        best = d;
        current = node;
      }
    }
    if (current === -1) break;
    frontier.delete(current);
    settled.add(current);
    if (current === to) break;

    for (const edge of adj.get(current) ?? []) {
      if (settled.has(edge.to)) continue;
      const weight = mode === 'steps' ? 1 : edge.cost;
      const candidate = best + weight;
      if (candidate < (dist.get(edge.to) ?? Infinity)) {
        dist.set(edge.to, candidate);
        prev.set(edge.to, { node: current, edgeIndex: edge.edgeIndex });
        frontier.add(edge.to);
      }
    }
  }

  if (!settled.has(to)) return empty;

  const nodes: number[] = [to];
  const edgeIndices: number[] = [];
  let energy = 0;
  let cursor = to;
  while (cursor !== from) {
    const step = prev.get(cursor);
    if (!step) return empty;
    edgeIndices.push(step.edgeIndex);
    // Re-read the true energy cost: in 'steps' mode dist holds hop counts.
    const traversed = (adj.get(step.node) ?? []).find(
      (e) => e.to === cursor && e.edgeIndex === step.edgeIndex,
    );
    energy += traversed?.cost ?? 0;
    cursor = step.node;
    nodes.push(cursor);
  }
  nodes.reverse();
  edgeIndices.reverse();

  return {
    from,
    to,
    nodes,
    edgeIndices,
    energy,
    steps: nodes.length - 1,
    reachable: true,
  };
};

/**
 * Chains shortest paths through every waypoint in order. A complex route is
 * just the concatenation of its legs; one unreachable leg does not discard the
 * others, so the user still sees which part of the route is broken.
 */
export const computeRoute = (
  adj: Adjacency,
  waypoints: number[],
  mode: RouteMode,
): RouteResult | null => {
  const points = waypoints.filter((id) => Number.isFinite(id));
  if (points.length < 2) return null;

  const legs: Leg[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    legs.push(shortestPath(adj, points[i], points[i + 1], mode));
  }

  const nodes: number[] = [];
  const edgeIndices = new Set<number>();
  let energy = 0;
  let steps = 0;
  legs.forEach((leg) => {
    leg.edgeIndices.forEach((index) => edgeIndices.add(index));
    energy += leg.energy;
    steps += leg.steps;
    leg.nodes.forEach((node, index) => {
      // Drop the duplicated junction between consecutive legs.
      if (index === 0 && nodes.length && nodes[nodes.length - 1] === node) return;
      nodes.push(node);
    });
  });

  return {
    legs,
    nodes,
    edgeIndices,
    energy,
    steps,
    complete: legs.every((leg) => leg.reachable),
  };
};
