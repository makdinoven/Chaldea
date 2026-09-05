import type { FullClassTreeResponse, TreeNodeInTreeResponse } from '../types';

/**
 * Reorders the nodes inside each ring so the links between rings cross as
 * little as possible, and reports how much it helped.
 *
 * This is the classic barycentre heuristic used for layered graph drawing: a
 * node wants to sit above the average position of the nodes it is joined to on
 * the neighbouring ring. Sweeping down and up a few times and keeping the best
 * result gets close to the minimum without the cost of an exact solver, which
 * is NP-hard even for two layers.
 *
 * Only the order within a ring changes — never a node's ring, its links, or
 * anything else. The result is expressed as new `sort_order` values, which is
 * exactly the knob the wheel layout reads.
 */

/** How many down/up sweeps to try. Beyond a handful the result stops moving. */
const SWEEPS = 8;

export interface UntangleResult {
  /** Node id (as a string) -> its new sort_order. */
  order: Map<string, number>;
  crossingsBefore: number;
  crossingsAfter: number;
  /**
   * True when some node actually moved relative to its neighbours. Renumbering
   * sort_order without changing the order does not count — the button must not
   * claim to have done something it did not.
   */
  changed: boolean;
}

/** The order the wheel currently draws a ring in. Mirrors combineTrees. */
const currentOrder = (nodes: TreeNodeInTreeResponse[]): TreeNodeInTreeResponse[] =>
  [...nodes].sort(
    (a, b) =>
      (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
      a.position_x - b.position_x ||
      String(a.id).localeCompare(String(b.id), undefined, { numeric: true }),
  );

interface Link {
  lowerRing: number;
  upperRing: number;
  lowerId: string;
  upperId: string;
}

/**
 * Counts how many pairs of links cross.
 *
 * Two links between the same pair of rings cross when one starts to the left of
 * the other but ends to its right. Positions are normalised to 0..1 so links
 * that skip a ring, joining rings of different sizes, still compare sensibly.
 */
const countCrossings = (links: Link[], indexOf: Map<string, number>, ringSize: Map<number, number>): number => {
  const pos = (id: string, ring: number) => {
    const size = ringSize.get(ring) ?? 1;
    return size <= 1 ? 0.5 : (indexOf.get(id) ?? 0) / (size - 1);
  };

  // Only links spanning the same two rings can cross each other.
  const groups = new Map<string, { a: number; b: number }[]>();
  for (const link of links) {
    const key = `${link.lowerRing}-${link.upperRing}`;
    const bucket = groups.get(key) ?? [];
    bucket.push({ a: pos(link.lowerId, link.lowerRing), b: pos(link.upperId, link.upperRing) });
    groups.set(key, bucket);
  }

  let crossings = 0;
  for (const bucket of groups.values()) {
    for (let i = 0; i < bucket.length; i++) {
      for (let j = i + 1; j < bucket.length; j++) {
        const p = bucket[i];
        const q = bucket[j];
        if ((p.a - q.a) * (p.b - q.b) < 0) crossings++;
      }
    }
  }
  return crossings;
};

export const untangleRings = (tree: FullClassTreeResponse): UntangleResult => {
  const ringOf = new Map<string, number>();
  for (const node of tree.nodes) ringOf.set(String(node.id), node.level_ring ?? 1);

  const ringValues = [...new Set(tree.nodes.map((n) => n.level_ring ?? 1))].sort((a, b) => a - b);

  /** ring value -> node ids, in their current left-to-right order. */
  const initial = new Map<number, string[]>();
  for (const ring of ringValues) {
    initial.set(
      ring,
      currentOrder(tree.nodes.filter((n) => (n.level_ring ?? 1) === ring)).map((n) => String(n.id)),
    );
  }

  // Links, oriented from the lower ring to the higher one. Same-ring links
  // cannot cross between layers, so they take no part in the ordering.
  const links: Link[] = [];
  for (const conn of tree.connections) {
    const from = String(conn.from_node_id);
    const to = String(conn.to_node_id);
    const fromRing = ringOf.get(from);
    const toRing = ringOf.get(to);
    if (fromRing === undefined || toRing === undefined || fromRing === toRing) continue;
    links.push(
      fromRing < toRing
        ? { lowerRing: fromRing, upperRing: toRing, lowerId: from, upperId: to }
        : { lowerRing: toRing, upperRing: fromRing, lowerId: to, upperId: from },
    );
  }

  const ringSize = new Map(ringValues.map((r) => [r, initial.get(r)!.length]));

  const indexMapOf = (rings: Map<number, string[]>): Map<string, number> => {
    const out = new Map<string, number>();
    for (const ids of rings.values()) ids.forEach((id, i) => out.set(id, i));
    return out;
  };

  const crossingsBefore = countCrossings(links, indexMapOf(initial), ringSize);

  /**
   * Reorders one ring by the average normalised position of everything it is
   * joined to on the other side. A node joined to nothing keeps its own spot,
   * so untouched branches do not all pile up at one end.
   */
  const sweep = (rings: Map<number, string[]>, ringIndex: number, lookBackwards: boolean) => {
    const ring = ringValues[ringIndex];
    const ids = rings.get(ring)!;
    if (ids.length < 2) return;
    const index = indexMapOf(rings);

    const normalised = (id: string) => {
      const r = ringOf.get(id)!;
      const size = ringSize.get(r) ?? 1;
      return size <= 1 ? 0.5 : (index.get(id) ?? 0) / (size - 1);
    };

    const barycentre = new Map<string, number>();
    ids.forEach((id, i) => {
      const neighbours = links
        .filter((l) =>
          lookBackwards
            ? l.upperId === id && l.lowerRing < ring
            : l.lowerId === id && l.upperRing > ring,
        )
        .map((l) => normalised(lookBackwards ? l.lowerId : l.upperId));
      barycentre.set(
        id,
        neighbours.length
          ? neighbours.reduce((a, b) => a + b, 0) / neighbours.length
          : ids.length <= 1 ? 0.5 : i / (ids.length - 1),
      );
    });

    // Ties keep their previous relative order, so a sweep never shuffles for
    // no reason.
    const positionBefore = new Map(ids.map((id, i) => [id, i]));
    rings.set(
      ring,
      [...ids].sort(
        (a, b) =>
          barycentre.get(a)! - barycentre.get(b)! ||
          positionBefore.get(a)! - positionBefore.get(b)!,
      ),
    );
  };

  const clone = (rings: Map<number, string[]>) => new Map([...rings].map(([r, ids]) => [r, [...ids]]));

  let working = clone(initial);
  let best = clone(initial);
  let bestCrossings = crossingsBefore;

  for (let pass = 0; pass < SWEEPS; pass++) {
    const downwards = pass % 2 === 0;
    if (downwards) {
      for (let i = 1; i < ringValues.length; i++) sweep(working, i, true);
    } else {
      for (let i = ringValues.length - 2; i >= 0; i--) sweep(working, i, false);
    }
    const crossings = countCrossings(links, indexMapOf(working), ringSize);
    if (crossings < bestCrossings) {
      bestCrossings = crossings;
      best = clone(working);
    }
  }

  const order = new Map<string, number>();
  for (const ids of best.values()) ids.forEach((id, i) => order.set(id, i));

  const changed = ringValues.some((ring) => {
    const was = initial.get(ring)!;
    const now = best.get(ring)!;
    return was.some((id, i) => now[i] !== id);
  });

  return { order, crossingsBefore, crossingsAfter: bestCrossings, changed };
};
