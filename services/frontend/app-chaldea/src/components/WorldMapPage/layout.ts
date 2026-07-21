import type { WorldGraph } from '../../api/worldGraph';

export interface Point {
  x: number;
  y: number;
}

export interface RegionBox {
  regionId: number;
  countryId: number;
  name: string;
  countryName: string;
  /** Bounding square used for packing; the drawn shape is `hullPath`. */
  x: number;
  y: number;
  width: number;
  height: number;
  count: number;
  /** Smoothed closed outline of the region's locations. */
  hullPath: string;
  labelX: number;
  labelY: number;
}

export interface CountryBox {
  countryId: number;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  count: number;
  hullPath: string;
  labelX: number;
  labelY: number;
}

export interface WorldLayout {
  positions: Map<number, Point>;
  regions: RegionBox[];
  countries: CountryBox[];
  /** Bounds of the drawn content — blobs and captions overflow the packing grid. */
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Ideal edge length; also sets how densely locations pack inside a region. */
const IDEAL_EDGE = 46;
const ITERATIONS = 260;
const REGION_PADDING = 60;
const REGION_GAP = 46;
const COUNTRY_PADDING = 74;
const COUNTRY_GAP = 150;
const ROTATION_PASSES = 5;

/** Deterministic PRNG so the map looks identical on every reload. */
const mulberry32 = (seed: number) => () => {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

/**
 * Fruchterman-Reingold with a gravity term. Gravity matters here because most
 * regions are internally fragmented (the world has 131 disconnected
 * components) — without it, unconnected clusters would drift apart forever
 * instead of settling into readable islands.
 */
const forceLayout = (nodeIds: number[], edges: Array<[number, number]>, seed: number): Map<number, Point> => {
  const count = nodeIds.length;
  const positions = new Map<number, Point>();
  if (count === 0) return positions;

  const random = mulberry32(seed);
  const span = IDEAL_EDGE * Math.sqrt(Math.max(count, 1)) * 1.6;

  if (count === 1) {
    positions.set(nodeIds[0], { x: 0, y: 0 });
    return positions;
  }

  const index = new Map<number, number>();
  nodeIds.forEach((id, i) => index.set(id, i));

  const px = new Float64Array(count);
  const py = new Float64Array(count);
  const dx = new Float64Array(count);
  const dy = new Float64Array(count);

  // Seed on a spiral rather than uniformly at random: it converges faster and
  // avoids the near-coincident starts that make repulsion explode.
  for (let i = 0; i < count; i += 1) {
    const angle = i * 2.399963; // golden angle
    const radius = span * 0.5 * Math.sqrt((i + 0.5) / count);
    px[i] = Math.cos(angle) * radius + (random() - 0.5) * 2;
    py[i] = Math.sin(angle) * radius + (random() - 0.5) * 2;
  }

  const localEdges: Array<[number, number]> = [];
  edges.forEach(([a, b]) => {
    const ia = index.get(a);
    const ib = index.get(b);
    if (ia !== undefined && ib !== undefined && ia !== ib) localEdges.push([ia, ib]);
  });

  const k = IDEAL_EDGE;
  const kSquared = k * k;
  let temperature = span * 0.12;
  const cooling = temperature / (ITERATIONS + 1);

  for (let step = 0; step < ITERATIONS; step += 1) {
    dx.fill(0);
    dy.fill(0);

    for (let i = 0; i < count; i += 1) {
      for (let j = i + 1; j < count; j += 1) {
        let deltaX = px[i] - px[j];
        let deltaY = py[i] - py[j];
        let distanceSq = deltaX * deltaX + deltaY * deltaY;
        if (distanceSq < 0.01) {
          deltaX = (random() - 0.5) * 0.1;
          deltaY = (random() - 0.5) * 0.1;
          distanceSq = deltaX * deltaX + deltaY * deltaY + 0.01;
        }
        const distance = Math.sqrt(distanceSq);
        const force = kSquared / distanceSq;
        const fx = (deltaX / distance) * force * k;
        const fy = (deltaY / distance) * force * k;
        dx[i] += fx; dy[i] += fy;
        dx[j] -= fx; dy[j] -= fy;
      }
    }

    for (const [ia, ib] of localEdges) {
      const deltaX = px[ia] - px[ib];
      const deltaY = py[ia] - py[ib];
      const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY) || 0.01;
      const force = (distance * distance) / k;
      const fx = (deltaX / distance) * force;
      const fy = (deltaY / distance) * force;
      dx[ia] -= fx; dy[ia] -= fy;
      dx[ib] += fx; dy[ib] += fy;
    }

    for (let i = 0; i < count; i += 1) {
      dx[i] -= px[i] * 0.06;
      dy[i] -= py[i] * 0.06;
      const displacement = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      const limit = Math.min(displacement, temperature);
      px[i] += (dx[i] / displacement) * limit;
      py[i] += (dy[i] / displacement) * limit;
    }

    temperature -= cooling;
  }

  nodeIds.forEach((id, i) => positions.set(id, { x: px[i], y: py[i] }));
  return positions;
};

/** Andrew's monotone chain convex hull. */
const convexHull = (points: Point[]): Point[] => {
  if (points.length < 3) return [...points];
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (o: Point, a: Point, b: Point) =>
    (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);

  const build = (input: Point[]) => {
    const stack: Point[] = [];
    for (const point of input) {
      while (stack.length >= 2 && cross(stack[stack.length - 2], stack[stack.length - 1], point) <= 0) {
        stack.pop();
      }
      stack.push(point);
    }
    stack.pop();
    return stack;
  };

  return [...build(sorted), ...build([...sorted].reverse())];
};

/**
 * Pushes hull vertices outward from the centroid and resamples the outline so
 * even a 2-point region becomes a rounded blob rather than a degenerate line.
 */
const inflateHull = (points: Point[], pad: number): Point[] => {
  if (points.length === 0) return [];
  const cx = points.reduce((sum, p) => sum + p.x, 0) / points.length;
  const cy = points.reduce((sum, p) => sum + p.y, 0) / points.length;

  const hull = convexHull(points);
  // Too few distinct vertices to form a shape — fall back to a circle.
  if (hull.length < 3) {
    const radius = Math.max(
      pad,
      ...points.map((p) => Math.hypot(p.x - cx, p.y - cy) + pad),
    );
    return Array.from({ length: 14 }, (_, i) => {
      const angle = (i / 14) * Math.PI * 2;
      return { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
    });
  }

  const inflated = hull.map((p) => {
    const dx = p.x - cx;
    const dy = p.y - cy;
    const distance = Math.hypot(dx, dy) || 1;
    return { x: p.x + (dx / distance) * pad, y: p.y + (dy / distance) * pad };
  });

  // Insert a bulged midpoint on every long edge so the outline reads as an
  // organic cloud instead of a faceted polygon.
  const dense: Point[] = [];
  for (let i = 0; i < inflated.length; i += 1) {
    const current = inflated[i];
    const next = inflated[(i + 1) % inflated.length];
    dense.push(current);
    const midX = (current.x + next.x) / 2;
    const midY = (current.y + next.y) / 2;
    const dx = midX - cx;
    const dy = midY - cy;
    const distance = Math.hypot(dx, dy) || 1;
    const bulge = Math.min(Math.hypot(next.x - current.x, next.y - current.y) * 0.16, pad * 0.7);
    dense.push({ x: midX + (dx / distance) * bulge, y: midY + (dy / distance) * bulge });
  }
  return dense;
};

/** Closed Catmull-Rom spline rendered as cubic Béziers. */
const smoothClosedPath = (points: Point[]): string => {
  if (points.length < 3) return '';
  const at = (i: number) => points[(i + points.length) % points.length];
  let path = `M ${at(0).x.toFixed(1)} ${at(0).y.toFixed(1)}`;
  for (let i = 0; i < points.length; i += 1) {
    const p0 = at(i - 1);
    const p1 = at(i);
    const p2 = at(i + 1);
    const p3 = at(i + 2);
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    path += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return `${path} Z`;
};

/** Shelf packing: rows of boxes, wrapping once a row exceeds `maxWidth`. */
const packRow = <T extends { width: number; height: number }>(
  boxes: T[],
  maxWidth: number,
  gap: number,
): { placed: Array<T & { x: number; y: number }>; width: number; height: number } => {
  const placed: Array<T & { x: number; y: number }> = [];
  let cursorX = 0;
  let cursorY = 0;
  let rowHeight = 0;
  let widest = 0;

  boxes.forEach((box) => {
    if (cursorX > 0 && cursorX + box.width > maxWidth) {
      cursorX = 0;
      cursorY += rowHeight + gap;
      rowHeight = 0;
    }
    placed.push({ ...box, x: cursorX, y: cursorY });
    cursorX += box.width + gap;
    rowHeight = Math.max(rowHeight, box.height);
    widest = Math.max(widest, cursorX - gap);
  });

  return { placed, width: widest, height: cursorY + rowHeight };
};

interface LocalRegion {
  regionId: number;
  countryId: number;
  name: string;
  countryName: string;
  count: number;
  /** Node offsets relative to the region centre, so rotation is about (0,0). */
  local: Map<number, Point>;
  radius: number;
  width: number;
  height: number;
  angle: number;
  centerX: number;
  centerY: number;
}

/**
 * Builds the whole-world layout: locations are force-laid out inside their own
 * region, regions are packed inside their country, countries are packed into
 * the canvas. Regions are then rotated so the few cross-region corridors run as
 * straight as possible, and each cluster is drawn as a smoothed blob.
 */
export const computeLayout = (graph: WorldGraph): WorldLayout => {
  const locationsByRegion = new Map<number, number[]>();
  const regionOf = new Map<number, number>();
  graph.locations.forEach((location) => {
    regionOf.set(location.id, location.region_id);
    const list = locationsByRegion.get(location.region_id);
    if (list) list.push(location.id);
    else locationsByRegion.set(location.region_id, [location.id]);
  });

  const edgesByRegion = new Map<number, Array<[number, number]>>();
  const crossEdges: Array<{ a: number; b: number; regionA: number; regionB: number }> = [];
  graph.edges.forEach((edge) => {
    const regionA = regionOf.get(edge.a);
    const regionB = regionOf.get(edge.b);
    if (regionA === undefined || regionB === undefined) return;
    if (regionA === regionB) {
      const list = edgesByRegion.get(regionA);
      if (list) list.push([edge.a, edge.b]);
      else edgesByRegion.set(regionA, [[edge.a, edge.b]]);
    } else {
      crossEdges.push({ a: edge.a, b: edge.b, regionA, regionB });
    }
  });

  const countryById = new Map(graph.countries.map((c) => [c.id, c]));
  const localRegions: LocalRegion[] = [];

  graph.regions.forEach((region) => {
    const nodeIds = locationsByRegion.get(region.id) ?? [];
    if (nodeIds.length === 0) return;
    const sorted = [...nodeIds].sort((a, b) => a - b); // stable input order
    const laid = forceLayout(sorted, edgesByRegion.get(region.id) ?? [], region.id);

    let sumX = 0;
    let sumY = 0;
    laid.forEach((point) => {
      sumX += point.x;
      sumY += point.y;
    });
    const cx = sumX / laid.size;
    const cy = sumY / laid.size;

    const local = new Map<number, Point>();
    let radius = 0;
    laid.forEach((point, id) => {
      const offset = { x: point.x - cx, y: point.y - cy };
      local.set(id, offset);
      radius = Math.max(radius, Math.hypot(offset.x, offset.y));
    });

    // A square bounding box keeps packing valid at *any* rotation angle, which
    // is what lets the rotation pass below run after placement.
    const side = (radius + REGION_PADDING) * 2;
    localRegions.push({
      regionId: region.id,
      countryId: region.country_id,
      name: region.name,
      countryName: countryById.get(region.country_id)?.name ?? '—',
      count: nodeIds.length,
      local,
      radius,
      width: side,
      height: side,
      angle: 0,
      centerX: 0,
      centerY: 0,
    });
  });

  const regionById = new Map(localRegions.map((r) => [r.regionId, r]));

  // Order regions so that ones joined by a corridor sit next to each other.
  const neighbourRegions = new Map<number, Set<number>>();
  crossEdges.forEach(({ regionA, regionB }) => {
    if (!neighbourRegions.has(regionA)) neighbourRegions.set(regionA, new Set());
    if (!neighbourRegions.has(regionB)) neighbourRegions.set(regionB, new Set());
    neighbourRegions.get(regionA)!.add(regionB);
    neighbourRegions.get(regionB)!.add(regionA);
  });

  /**
   * Linear order of every region that takes part in a cross-region corridor.
   *
   * The corridors form a tree (a long chain with a couple of branches), and the
   * whole point is that a route entering a region should leave from the far
   * side. That only happens if consecutive chain members are laid out in a
   * line, so the chain is walked depth-first from a leaf and the resulting
   * sequence drives both region and country placement below.
   */
  const chainOrder = new Map<number, number>();
  const branchRegionIds = new Set<number>();
  {
    const neighboursOf = (id: number) => [...(neighbourRegions.get(id) ?? [])];

    /** BFS returning the farthest node reached plus the parent map. */
    const sweep = (start: number) => {
      const parent = new Map<number, number>([[start, -1]]);
      const queue = [start];
      let farthest = start;
      while (queue.length) {
        const node = queue.shift() as number;
        farthest = node;
        neighboursOf(node).forEach((next) => {
          if (!parent.has(next)) {
            parent.set(next, node);
            queue.push(next);
          }
        });
      }
      return { farthest, parent };
    };

    const seen = new Set<number>();
    let position = 0;
    [...neighbourRegions.keys()].sort((a, b) => a - b).forEach((start) => {
      if (seen.has(start)) return;
      // The corridors form a tree, so its longest path (two BFS sweeps) is the
      // trunk. Only the trunk goes in the straight row; side branches drop to
      // the row below so they leave roughly perpendicular instead of doubling
      // back alongside the trunk.
      const first = sweep(start);
      const second = sweep(first.farthest);

      const trunk: number[] = [];
      let cursor: number | undefined = second.farthest;
      while (cursor !== undefined && cursor !== -1) {
        trunk.push(cursor);
        cursor = second.parent.get(cursor);
      }
      trunk.reverse();
      trunk.forEach((id) => {
        chainOrder.set(id, position++);
        seen.add(id);
      });

      second.parent.forEach((_, id) => {
        if (!seen.has(id)) {
          branchRegionIds.add(id);
          seen.add(id);
        }
      });
    });
  }

  const positionInChain = (region: LocalRegion) =>
    chainOrder.get(region.regionId) ?? Number.POSITIVE_INFINITY;

  const byCountry = new Map<number, LocalRegion[]>();
  localRegions.forEach((region) => {
    const list = byCountry.get(region.countryId);
    if (list) list.push(region);
    else byCountry.set(region.countryId, [region]);
  });

  interface PackedCountry {
    countryId: number;
    name: string;
    width: number;
    height: number;
    count: number;
    chainRank: number;
    regions: Array<LocalRegion & { x: number; y: number }>;
  }

  const packedCountries: PackedCountry[] = [];

  byCountry.forEach((regions, countryId) => {
    // Regions on the corridor tree go in one unbroken row, in chain order, so
    // a route crosses them end to end instead of folding back on itself.
    const chained = regions
      .filter((region) => chainOrder.has(region.regionId))
      .sort((a, b) => positionInChain(a) - positionInChain(b));
    // Side branches lead the second row so they sit directly under the trunk.
    const branches = regions
      .filter((region) => branchRegionIds.has(region.regionId))
      .sort((a, b) => a.regionId - b.regionId);
    const loose = [
      ...branches,
      ...regions
        .filter((region) => !chainOrder.has(region.regionId) && !branchRegionIds.has(region.regionId))
        .sort((a, b) => b.count - a.count || a.regionId - b.regionId),
    ];

    const chainRow = packRow(chained, Number.POSITIVE_INFINITY, REGION_GAP);
    // The remaining regions fill rows underneath. Their width must not come
    // from the chain alone — a one-region chain would squeeze them into a
    // single tall column.
    const looseArea = loose.reduce((sum, r) => sum + r.width * r.height, 0);
    const looseWidth = Math.max(
      chainRow.width,
      Math.sqrt(looseArea * 1.9),
      loose[0]?.width ?? 0,
    );
    const loosePack = packRow(loose, looseWidth, REGION_GAP);
    const looseOffsetY = chained.length ? chainRow.height + REGION_GAP : 0;

    // Centre the lower rows under the trunk row, otherwise the country hull
    // is drawn as a lopsided wedge over a lot of empty space.
    const looseOffsetX = Math.max(0, (chainRow.width - loosePack.width) / 2);
    const chainOffsetX = Math.max(0, (loosePack.width - chainRow.width) / 2);
    const placed = [
      ...chainRow.placed.map((region) => ({ ...region, x: region.x + chainOffsetX })),
      ...loosePack.placed.map((region) => ({
        ...region,
        x: region.x + looseOffsetX,
        y: region.y + looseOffsetY,
      })),
    ];

    packedCountries.push({
      countryId,
      name: countryById.get(countryId)?.name ?? '—',
      width: Math.max(chainRow.width, loosePack.width) + COUNTRY_PADDING * 2,
      height: looseOffsetY + loosePack.height + COUNTRY_PADDING * 2,
      count: regions.reduce((sum, r) => sum + r.count, 0),
      chainRank: chained.length ? positionInChain(chained[0]) : Number.POSITIVE_INFINITY,
      regions: placed,
    });
  });

  // Countries follow the chain too, otherwise a corridor leaving one country
  // has to double back to reach the next.
  packedCountries.sort(
    (a, b) => a.chainRank - b.chainRank || b.count - a.count || a.countryId - b.countryId,
  );

  /*
   * Countries carrying the corridor chain go in one unbroken row, ordered by
   * chainRank. Because each country puts its own chain row first (local y = 0),
   * aligning the country tops lines every chain row up at the same height, so
   * the corridor runs straight across country borders instead of folding at
   * each one. Countries with no corridors fill a band underneath.
   */
  const chainCountries = packedCountries.filter((c) => Number.isFinite(c.chainRank));
  const looseCountries = packedCountries.filter((c) => !Number.isFinite(c.chainRank));

  const chainBand = packRow(chainCountries, Number.POSITIVE_INFINITY, COUNTRY_GAP);
  const looseArea = looseCountries.reduce((sum, c) => sum + c.width * c.height, 0);
  const looseBandWidth = Math.max(
    chainBand.width,
    Math.sqrt(looseArea * 1.7),
    looseCountries[0]?.width ?? 0,
  );
  const looseBand = packRow(looseCountries, looseBandWidth, COUNTRY_GAP);
  const looseOffsetY = chainCountries.length ? chainBand.height + COUNTRY_GAP : 0;

  const looseBandOffsetX = Math.max(0, (chainBand.width - looseBand.width) / 2);
  const world = {
    placed: [
      ...chainBand.placed,
      ...looseBand.placed.map((country) => ({
        ...country,
        x: country.x + looseBandOffsetX,
        y: country.y + looseOffsetY,
      })),
    ],
    width: Math.max(chainBand.width, looseBand.width),
    height: looseOffsetY + looseBand.height,
  };

  // Resolve every region's centre in world space.
  world.placed.forEach((country) => {
    country.regions.forEach((region) => {
      const target = regionById.get(region.regionId);
      if (!target) return;
      target.centerX = country.x + COUNTRY_PADDING + region.x + region.width / 2;
      target.centerY = country.y + COUNTRY_PADDING + region.y + region.height / 2;
    });
  });

  /**
   * Rotate each region about its centre to shorten the corridors leaving it.
   * The optimal angle has a closed form (the 2-D Procrustes / Kabsch solution),
   * so no angle sweep is needed; a few passes let neighbours settle together.
   */
  const worldPoint = (region: LocalRegion, nodeId: number): Point | null => {
    const offset = region.local.get(nodeId);
    if (!offset) return null;
    const cos = Math.cos(region.angle);
    const sin = Math.sin(region.angle);
    return {
      x: region.centerX + offset.x * cos - offset.y * sin,
      y: region.centerY + offset.x * sin + offset.y * cos,
    };
  };

  if (crossEdges.length > 0) {
    for (let pass = 0; pass < ROTATION_PASSES; pass += 1) {
      localRegions.forEach((region) => {
        let numerator = 0;
        let denominator = 0;
        crossEdges.forEach((edge) => {
          let ownNode: number;
          let otherNode: number;
          let otherRegionId: number;
          if (edge.regionA === region.regionId) {
            ownNode = edge.a; otherNode = edge.b; otherRegionId = edge.regionB;
          } else if (edge.regionB === region.regionId) {
            ownNode = edge.b; otherNode = edge.a; otherRegionId = edge.regionA;
          } else {
            return;
          }
          const offset = region.local.get(ownNode);
          const other = regionById.get(otherRegionId);
          if (!offset || !other) return;
          const target = worldPoint(other, otherNode);
          if (!target) return;
          // Aim the exit node straight at the partner region's entry node.
          const dx = target.x - region.centerX;
          const dy = target.y - region.centerY;
          numerator += offset.x * dy - offset.y * dx;
          denominator += offset.x * dx + offset.y * dy;
        });
        if (numerator !== 0 || denominator !== 0) {
          region.angle = Math.atan2(numerator, denominator);
        }
      });
    }
  }

  // Bake the final world positions and build the blob outlines.
  const positions = new Map<number, Point>();
  const regionBoxes: RegionBox[] = [];
  const regionHullsByCountry = new Map<number, Point[]>();
  const outlinePoints: Point[] = [];

  localRegions.forEach((region) => {
    const worldPoints: Point[] = [];
    region.local.forEach((_, id) => {
      const point = worldPoint(region, id);
      if (!point) return;
      positions.set(id, point);
      worldPoints.push(point);
    });

    const outline = inflateHull(worldPoints, REGION_PADDING * 0.62);
    outlinePoints.push(...outline);
    const minY = Math.min(...outline.map((p) => p.y));

    regionBoxes.push({
      regionId: region.regionId,
      countryId: region.countryId,
      name: region.name,
      countryName: region.countryName,
      x: region.centerX - region.width / 2,
      y: region.centerY - region.height / 2,
      width: region.width,
      height: region.height,
      count: region.count,
      hullPath: smoothClosedPath(outline),
      labelX: region.centerX,
      labelY: minY - 10,
    });

    const bucket = regionHullsByCountry.get(region.countryId);
    if (bucket) bucket.push(...outline);
    else regionHullsByCountry.set(region.countryId, [...outline]);
  });

  const countryBoxes: CountryBox[] = world.placed.map((country) => {
    const hullPoints = regionHullsByCountry.get(country.countryId) ?? [];
    const outline = inflateHull(hullPoints, COUNTRY_PADDING * 0.5);
    outlinePoints.push(...outline);
    const minY = outline.length ? Math.min(...outline.map((p) => p.y)) : country.y;
    const centerX = outline.length
      ? outline.reduce((sum, p) => sum + p.x, 0) / outline.length
      : country.x + country.width / 2;
    return {
      countryId: country.countryId,
      name: country.name,
      x: country.x,
      y: country.y,
      width: country.width,
      height: country.height,
      count: country.count,
      hullPath: smoothClosedPath(outline),
      labelX: centerX,
      labelY: minY - 26,
    };
  });

  // Country captions sit above their blob, so reserve room for them too.
  const captionAllowance = 40;
  const xs = outlinePoints.map((p) => p.x);
  const ys = outlinePoints.map((p) => p.y);
  const minX = xs.length ? Math.min(...xs) : 0;
  const minY = ys.length ? Math.min(...ys) - captionAllowance : 0;
  const maxX = xs.length ? Math.max(...xs) : world.width;
  const maxY = ys.length ? Math.max(...ys) : world.height;

  return {
    positions,
    regions: regionBoxes,
    countries: countryBoxes,
    x: minX,
    y: minY,
    width: Math.max(maxX - minX, 1),
    height: Math.max(maxY - minY, 1),
  };
};
