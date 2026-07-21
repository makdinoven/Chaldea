import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { GraphEdge, GraphLocation } from '../../api/worldGraph';
import type { RouteResult } from './graphUtils';
import type { WorldLayout } from './layout';
import { COUNTRY_COLORS, ROUTE_COLOR } from './theme';

export interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MapCanvasHandle {
  fitBounds: (bounds: Bounds, padding?: number) => void;
  centerOn: (x: number, y: number, scale?: number) => void;
}

interface MapCanvasProps {
  layout: WorldLayout;
  locations: GraphLocation[];
  edges: GraphEdge[];
  countryIndexOf: (countryId: number) => number;
  colorFor: (locationId: number) => string;
  route: RouteResult | null;
  waypointIds: Set<number>;
  endpointIds: Set<number>;
  isolatedIds: Set<number>;
  selectedEdgeIndex: number | null;
  selectedLocationId: number | null;
  onLocationClick: (locationId: number) => void;
  onEdgeClick: (edgeIndex: number) => void;
  onBackgroundClick: () => void;
}

const MIN_SCALE = 0.04;
const MAX_SCALE = 4;
/** Below this scale labels are unreadable, so they are kept out of the DOM. */
const LABEL_SCALE = 0.55;
/** Hard cap so a wide viewport can never mount an unbounded label set. */
const MAX_LABELS = 400;
/**
 * Below this scale the region blobs are only a few dozen pixels across and
 * their captions collide into an unreadable pile, so only country names show.
 */
const REGION_CAPTION_SCALE = 0.13;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

/**
 * The static picture of the world. Memoised on the things that actually change
 * it (layout, colouring, route) — never on the viewport, so panning and zooming
 * never re-render a single SVG element.
 */
const WorldBase = memo(({
  layout,
  locations,
  edges,
  countryIndexOf,
  colorFor,
  route,
  waypointIds,
  endpointIds,
  isolatedIds,
  selectedEdgeIndex,
  selectedLocationId,
}: Pick<MapCanvasProps,
  'layout' | 'locations' | 'edges' | 'countryIndexOf' | 'colorFor' | 'route'
  | 'waypointIds' | 'endpointIds' | 'isolatedIds' | 'selectedEdgeIndex' | 'selectedLocationId'
>) => {
  const routeEdges = route?.edgeIndices ?? new Set<number>();
  const routeNodes = useMemo(() => {
    const map = new Map<number, number>();
    route?.nodes.forEach((id, index) => {
      if (!map.has(id)) map.set(id, index + 1);
    });
    return map;
  }, [route]);
  const dimmed = Boolean(route && route.nodes.length);
  const positions = layout.positions;

  const regionOf = useMemo(
    () => new Map(locations.map((l) => [l.id, l.region_id])),
    [locations],
  );
  const locationById = useMemo(
    () => new Map(locations.map((l) => [l.id, l])),
    [locations],
  );

  return (
    <>
      {/* Country and region islands, drawn as smoothed blobs */}
      <g>
        {layout.countries.map((country) => {
          const color = COUNTRY_COLORS[countryIndexOf(country.countryId) % COUNTRY_COLORS.length];
          return (
            <path
              key={`c-${country.countryId}`}
              d={country.hullPath}
              fill={color}
              fillOpacity={0.05}
              stroke={color}
              strokeOpacity={0.45}
              strokeWidth={1.5}
            />
          );
        })}
        {layout.regions.map((region) => {
          const color = COUNTRY_COLORS[countryIndexOf(region.countryId) % COUNTRY_COLORS.length];
          return (
            <path
              key={`r-${region.regionId}`}
              d={region.hullPath}
              fill={color}
              fillOpacity={0.08}
              stroke={color}
              strokeOpacity={0.3}
              strokeWidth={1}
              strokeDasharray="9 7"
            />
          );
        })}
      </g>

      {/* Base edges */}
      <g strokeLinecap="round">
        {edges.map((edge, index) => {
          if (routeEdges.has(index)) return null;
          const from = positions.get(edge.a);
          const to = positions.get(edge.b);
          if (!from || !to) return null;
          const crossRegion = regionOf.get(edge.a) !== regionOf.get(edge.b);
          const oneWay = edge.cost_ab === null || edge.cost_ba === null;
          return (
            <line
              key={index}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={
                index === selectedEdgeIndex
                  ? '#ffffff'
                  : crossRegion ? '#e879a6' : oneWay ? '#f0d95c' : '#7f8ea3'
              }
              strokeWidth={index === selectedEdgeIndex ? 4 : crossRegion ? 1.8 : 1}
              strokeDasharray={
                index === selectedEdgeIndex ? undefined : crossRegion || oneWay ? '6 4' : undefined
              }
              strokeOpacity={
                index === selectedEdgeIndex ? 1 : dimmed ? 0.07 : crossRegion ? 0.85 : 0.3
              }
            />
          );
        })}
      </g>

      {/* Route edges on top */}
      {route && (
        <g strokeLinecap="round">
          {[...routeEdges].map((index) => {
            const edge = edges[index];
            const from = positions.get(edge.a);
            const to = positions.get(edge.b);
            if (!from || !to) return null;
            return (
              <line
                key={`route-${index}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={ROUTE_COLOR}
                strokeWidth={3.2}
                strokeOpacity={0.95}
              />
            );
          })}
        </g>
      )}

      {/* Locations */}
      <g>
        {locations.map((location) => {
          const point = positions.get(location.id);
          if (!point) return null;
          const onRoute = routeNodes.has(location.id);
          const isWaypoint = waypointIds.has(location.id);
          const isEndpoint = endpointIds.has(location.id);
          const radius = isEndpoint || isWaypoint ? 9 : onRoute ? 6.5 : 5;
          const faded = dimmed && !onRoute && !isWaypoint;
          return (
            <circle
              key={location.id}
              data-loc={location.id}
              cx={point.x}
              cy={point.y}
              r={radius}
              fill={colorFor(location.id)}
              fillOpacity={faded ? 0.16 : 1}
              stroke={
                isEndpoint ? '#ffffff' : onRoute || isWaypoint ? ROUTE_COLOR : 'rgba(255,255,255,0.3)'
              }
              strokeWidth={onRoute || isWaypoint ? 2.5 : 1.4}
              strokeOpacity={faded ? 0.16 : 1}
              strokeDasharray={isolatedIds.has(location.id) && !onRoute ? '3 2' : undefined}
              className="cursor-pointer"
            />
          );
        })}
      </g>

      {selectedLocationId !== null && positions.has(selectedLocationId) && (
        <circle
          className="pointer-events-none"
          cx={positions.get(selectedLocationId)!.x}
          cy={positions.get(selectedLocationId)!.y}
          r={15}
          fill="none"
          stroke="#ffffff"
          strokeWidth={2}
          strokeDasharray="4 3"
        />
      )}

    </>
  );
});
WorldBase.displayName = 'WorldBase';

/**
 * Region and country captions. Font sizes are divided by the viewport scale so
 * the text keeps a constant size on screen — otherwise captions are invisible
 * when zoomed out and enormous when zoomed in.
 */
const CaptionLayer = memo(({
  layout,
  countryIndexOf,
  scale,
}: Pick<MapCanvasProps, 'layout' | 'countryIndexOf'> & { scale: number }) => {
  const k = scale || 1;
  return (
    <g className="pointer-events-none select-none group-[.wm-busy]:hidden">
      {scale >= REGION_CAPTION_SCALE && layout.regions.map((region) => (
        <text
          key={`rl-${region.regionId}`}
          x={region.labelX}
          y={region.labelY}
          textAnchor="middle"
          fill={COUNTRY_COLORS[countryIndexOf(region.countryId) % COUNTRY_COLORS.length]}
          fontSize={13 / k}
          fontWeight={600}
        >
          {region.name}
          <tspan fill="rgba(255,255,255,0.4)" fontSize={11 / k}> · {region.count}</tspan>
        </text>
      ))}
      {layout.countries.map((country) => (
        <text
          key={`cl-${country.countryId}`}
          x={country.labelX}
          y={country.labelY}
          textAnchor="middle"
          fill={COUNTRY_COLORS[countryIndexOf(country.countryId) % COUNTRY_COLORS.length]}
          // Tie the caption to the country's footprint, otherwise a two-location
          // country shouts as loudly as a 600-location one and the two labels
          // collide.
          fontSize={Math.max(11, Math.min(24, country.width * 0.01)) / k}
          fontWeight={700}
          letterSpacing={1.5 / k}
        >
          {country.name.toUpperCase()}
        </text>
      ))}
    </g>
  );
});
CaptionLayer.displayName = 'CaptionLayer';

/**
 * Labels live in their own memo boundary. The visible set changes on every
 * settled gesture, and re-rendering the 4000-element base layer alongside it
 * cost over a second per change.
 */
const LabelLayer = memo(({
  labelIds,
  locations,
  positions,
  route,
  waypointIds,
  scale,
}: {
  labelIds: number[];
  locations: GraphLocation[];
  positions: Map<number, { x: number; y: number }>;
  route: RouteResult | null;
  waypointIds: Set<number>;
  scale: number;
}) => {
  const locationById = useMemo(() => new Map(locations.map((l) => [l.id, l])), [locations]);
  const routeNodes = useMemo(() => new Set(route?.nodes ?? []), [route]);
  const dimmed = Boolean(route && route.nodes.length);
  if (labelIds.length === 0) return null;

  return (
    <g className="pointer-events-none select-none group-[.wm-busy]:hidden">
      {labelIds.map((id) => {
        const location = locationById.get(id);
        const point = positions.get(id);
        if (!location || !point) return null;
        const faded = dimmed && !routeNodes.has(id) && !waypointIds.has(id);
        return (
          <text
            key={`l-${id}`}
            x={point.x}
            y={point.y + 13 / (scale || 1)}
            textAnchor="middle"
            fontSize={11 / (scale || 1)}
            fill="#ffffff"
            fillOpacity={faded ? 0.15 : 0.75}
          >
            {location.name}
          </text>
        );
      })}
    </g>
  );
});
LabelLayer.displayName = 'LabelLayer';

const MapCanvas = forwardRef<MapCanvasHandle, MapCanvasProps>((props, ref) => {
  const { layout, locations, edges, onLocationClick, onEdgeClick, onBackgroundClick } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<SVGGElement>(null);
  const viewportRectRef = useRef<SVGRectElement>(null);
  const transform = useRef({ x: 0, y: 0, k: 0.2 });
  const layoutOrigin = useRef({ x: layout.x, y: layout.y });
  layoutOrigin.current = { x: layout.x, y: layout.y };
  const busyTimer = useRef<number | null>(null);
  const [labelIds, setLabelIds] = useState<number[]>([]);
  const [renderScale, setRenderScale] = useState(1);

  /**
   * Writes the viewport straight to the DOM. Deliberately bypasses React:
   * a pan is then a single composited transform instead of a re-render of
   * thousands of elements.
   */
  const applyTransform = useCallback(() => {
    const { x, y, k } = transform.current;
    // Transform the <g> rather than a wrapping div: a CSS transform forces the
    // browser to rasterise the whole 8000x6000 canvas as a single layer, which
    // cost second-long stalls at high zoom. Inside the SVG only the visible
    // area is ever rasterised.
    contentRef.current?.setAttribute('transform', `translate(${x} ${y}) scale(${k})`);

    const rect = viewportRectRef.current;
    const container = containerRef.current;
    if (rect && container) {
      const scale = Number(rect.dataset.scale ?? 1);
      rect.setAttribute('x', String((-x / k - layoutOrigin.current.x) * scale));
      rect.setAttribute('y', String((-y / k - layoutOrigin.current.y) * scale));
      rect.setAttribute('width', String((container.clientWidth / k) * scale));
      rect.setAttribute('height', String((container.clientHeight / k) * scale));
    }
  }, []);

  /**
   * Recomputes which labels are mounted. Only nodes inside the current viewport
   * qualify, so the DOM holds tens of <text> nodes instead of two thousand.
   * Called when a gesture settles, never per frame.
   */
  const refreshLabels = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const { x, y, k } = transform.current;
    setRenderScale((current) => (Math.abs(current - k) < 1e-6 ? current : k));
    if (k < LABEL_SCALE) {
      setLabelIds((current) => (current.length === 0 ? current : []));
      return;
    }
    const margin = 40;
    const left = -x / k - margin;
    const top = -y / k - margin;
    const right = (container.clientWidth - x) / k + margin;
    const bottom = (container.clientHeight - y) / k + margin;

    const visible: number[] = [];
    for (const location of locations) {
      const point = layout.positions.get(location.id);
      if (!point) continue;
      if (point.x >= left && point.x <= right && point.y >= top && point.y <= bottom) {
        visible.push(location.id);
        if (visible.length >= MAX_LABELS) break;
      }
    }
    setLabelIds((current) =>
      current.length === visible.length && current.every((id, i) => id === visible[i])
        ? current
        : visible,
    );
  }, [layout, locations]);

  /** Labels are dropped while the user is actively panning or zooming. */
  const markBusy = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    container.classList.add('wm-busy');
    if (busyTimer.current) window.clearTimeout(busyTimer.current);
    busyTimer.current = window.setTimeout(() => {
      container.classList.remove('wm-busy');
      refreshLabels();
    }, 140);
  }, [refreshLabels]);

  const setScale = useCallback((nextScale: number, originX: number, originY: number) => {
    const t = transform.current;
    const k = clamp(nextScale, MIN_SCALE, MAX_SCALE);
    // Keep the world point under the cursor anchored while zooming.
    t.x = originX - ((originX - t.x) / t.k) * k;
    t.y = originY - ((originY - t.y) / t.k) * k;
    t.k = k;
    applyTransform();
  }, [applyTransform]);

  const fitBounds = useCallback((bounds: Bounds, padding = 0.08) => {
    const container = containerRef.current;
    if (!container || bounds.width <= 0 || bounds.height <= 0) return;
    const width = container.clientWidth;
    const height = container.clientHeight;
    const k = clamp(
      Math.min(width / bounds.width, height / bounds.height) * (1 - padding),
      MIN_SCALE,
      MAX_SCALE,
    );
    // The SVG viewBox maps the layout origin to the content div's (0,0), so
    // world coordinates must be rebased before being scaled into screen space.
    transform.current = {
      k,
      x: width / 2 - (bounds.x + bounds.width / 2) * k,
      y: height / 2 - (bounds.y + bounds.height / 2) * k,
    };
    applyTransform();
    refreshLabels();
  }, [applyTransform, refreshLabels, layout.x, layout.y]);

  const centerOn = useCallback((x: number, y: number, scale = 1.2) => {
    const container = containerRef.current;
    if (!container) return;
    const k = clamp(scale, MIN_SCALE, MAX_SCALE);
    transform.current = {
      k,
      x: container.clientWidth / 2 - x * k,
      y: container.clientHeight / 2 - y * k,
    };
    applyTransform();
    refreshLabels();
  }, [applyTransform, refreshLabels, layout.x, layout.y]);

  useImperativeHandle(ref, () => ({ fitBounds, centerOn }), [fitBounds, centerOn]);

  // Initial framing of the whole world.
  useEffect(() => {
    fitBounds({ x: layout.x, y: layout.y, width: layout.width, height: layout.height });
  }, [layout, fitBounds]);

  // Pointer-based panning and pinch zoom.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const pointers = new Map<number, { x: number; y: number }>();
    let pinchDistance = 0;
    let moved = false;

    /**
     * The zoom controls sit inside the canvas. Capturing the pointer on them
     * would retarget pointerup to the container, so the browser never
     * synthesises a click on the button and the control appears dead.
     */
    const isControl = (target: EventTarget | null) =>
      target instanceof Element && Boolean(target.closest('button, a, input, select, textarea'));

    const onPointerDown = (event: PointerEvent) => {
      if (isControl(event.target)) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      moved = false;
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinchDistance = Math.hypot(a.x - b.x, a.y - b.y);
      }
      container.setPointerCapture(event.pointerId);
      markBusy();
    };

    const onPointerMove = (event: PointerEvent) => {
      // Not registered in pointerdown (started on a control) — nothing to pan.
      const previous = pointers.get(event.pointerId);
      if (!previous) return;
      const next = { x: event.clientX, y: event.clientY };
      pointers.set(event.pointerId, next);

      if (pointers.size === 1) {
        const dx = next.x - previous.x;
        const dy = next.y - previous.y;
        if (Math.abs(dx) > 1 || Math.abs(dy) > 1) moved = true;
        transform.current.x += dx;
        transform.current.y += dy;
        applyTransform();
        markBusy();
      } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinchDistance > 0) {
          const rect = container.getBoundingClientRect();
          setScale(
            transform.current.k * (distance / pinchDistance),
            (a.x + b.x) / 2 - rect.left,
            (a.y + b.y) / 2 - rect.top,
          );
        }
        pinchDistance = distance;
        moved = true;
        markBusy();
      }
    };

    const endPointer = (event: PointerEvent) => {
      if (isControl(event.target)) return;
      pointers.delete(event.pointerId);
      if (pointers.size < 2) pinchDistance = 0;
      if (container.hasPointerCapture(event.pointerId)) {
        container.releasePointerCapture(event.pointerId);
      }
      // A drag must not be mistaken for a click.
      if (moved || !(event.target instanceof Element)) return;

      const hit = event.target.closest('[data-loc]');
      if (hit) {
        onLocationClick(Number(hit.getAttribute('data-loc')));
        return;
      }

      // Edges are 1px lines — far too thin to hit reliably, and widening the
      // clickable stroke would mean 2000 extra DOM nodes. Instead find the
      // nearest segment geometrically, which costs nothing until a click.
      const rect = container.getBoundingClientRect();
      const { x: tx, y: ty, k } = transform.current;
      const worldX = (event.clientX - rect.left - tx) / k;
      const worldY = (event.clientY - rect.top - ty) / k;
      const tolerance = 9 / k;

      let bestIndex = -1;
      let bestDistance = tolerance;
      for (let i = 0; i < edges.length; i += 1) {
        const from = layout.positions.get(edges[i].a);
        const to = layout.positions.get(edges[i].b);
        if (!from || !to) continue;
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const lengthSq = dx * dx + dy * dy;
        const t = lengthSq === 0
          ? 0
          : Math.max(0, Math.min(1, ((worldX - from.x) * dx + (worldY - from.y) * dy) / lengthSq));
        const distance = Math.hypot(worldX - (from.x + t * dx), worldY - (from.y + t * dy));
        if (distance < bestDistance) {
          bestDistance = distance;
          bestIndex = i;
        }
      }

      if (bestIndex >= 0) onEdgeClick(bestIndex);
      else onBackgroundClick();
    };

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = container.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * 0.0016);
      setScale(
        transform.current.k * factor,
        event.clientX - rect.left,
        event.clientY - rect.top,
      );
      markBusy();
    };

    container.addEventListener('pointerdown', onPointerDown);
    container.addEventListener('pointermove', onPointerMove);
    container.addEventListener('pointerup', endPointer);
    container.addEventListener('pointercancel', endPointer);
    container.addEventListener('wheel', onWheel, { passive: false });

    return () => {
      container.removeEventListener('pointerdown', onPointerDown);
      container.removeEventListener('pointermove', onPointerMove);
      container.removeEventListener('pointerup', endPointer);
      container.removeEventListener('pointercancel', endPointer);
      container.removeEventListener('wheel', onWheel);
      if (busyTimer.current) window.clearTimeout(busyTimer.current);
    };
  }, [applyTransform, setScale, markBusy, onLocationClick, onEdgeClick, onBackgroundClick, edges, layout]);

  /**
   * Keep the framing sensible when the window or orientation changes. The world
   * point sitting at the centre of the viewport stays at the centre, otherwise
   * shrinking the window pushes the map off-screen entirely.
   */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    let previous = { width: container.clientWidth, height: container.clientHeight };
    const observer = new ResizeObserver(() => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (width === 0 || height === 0) return;
      const t = transform.current;
      const centreX = (previous.width / 2 - t.x) / t.k;
      const centreY = (previous.height / 2 - t.y) / t.k;
      t.x = width / 2 - centreX * t.k;
      t.y = height / 2 - centreY * t.k;
      previous = { width, height };
      applyTransform();
      refreshLabels();
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [applyTransform, refreshLabels]);

  const minimapScale = useMemo(
    () => Math.min(220 / layout.width, 140 / layout.height),
    [layout],
  );
  const mmX = (x: number) => (x - layout.x) * minimapScale;
  const mmY = (y: number) => (y - layout.y) * minimapScale;

  useEffect(() => {
    if (viewportRectRef.current) {
      viewportRectRef.current.dataset.scale = String(minimapScale);
      applyTransform();
    }
  }, [minimapScale, applyTransform]);

  const zoomBy = (factor: number) => {
    const container = containerRef.current;
    if (!container) return;
    const { x, y, k } = transform.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    /*
     * Anchor the zoom on the centre of mass of whatever is currently on screen
     * rather than the raw viewport centre. The countries sit far apart, so the
     * geometric centre is often empty space — zooming about it walked the
     * camera into a void and never reached any locations.
     */
    let originX = width / 2;
    let originY = height / 2;
    let anchorDistance = Number.POSITIVE_INFINITY;
    let seen = 0;
    for (const location of locations) {
      const point = layout.positions.get(location.id);
      if (!point) continue;
      const screenX = point.x * k + x;
      const screenY = point.y * k + y;
      if (screenX < 0 || screenX > width || screenY < 0 || screenY > height) continue;
      seen += 1;
      // Nearest visible location to the centre, not the centroid of them all:
      // with two clusters at opposite edges the centroid lands in the gap
      // between them and the camera zooms into nothing.
      const distance = (screenX - width / 2) ** 2 + (screenY - height / 2) ** 2;
      if (distance < anchorDistance) {
        anchorDistance = distance;
        originX = screenX;
        originY = screenY;
      }
    }
    if (seen === 0) {
      // Already stranded in empty space (a window resize can do this). Zooming
      // about any origin would just dig deeper, so recentre on the closest
      // location instead — that makes the control self-correcting.
      const centreWorldX = (width / 2 - x) / k;
      const centreWorldY = (height / 2 - y) / k;
      let nearest: { x: number; y: number } | null = null;
      let nearestDistance = Number.POSITIVE_INFINITY;
      for (const location of locations) {
        const point = layout.positions.get(location.id);
        if (!point) continue;
        const distance = (point.x - centreWorldX) ** 2 + (point.y - centreWorldY) ** 2;
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearest = point;
        }
      }
      if (nearest) {
        const nextScale = clamp(k * factor, MIN_SCALE, MAX_SCALE);
        transform.current = {
          k: nextScale,
          x: width / 2 - nearest.x * nextScale,
          y: height / 2 - nearest.y * nextScale,
        };
        applyTransform();
        markBusy();
        return;
      }
    }

    setScale(k * factor, originX, originY);
    // Label refresh is debounced inside markBusy so it never runs per frame
    // during a wheel gesture; the buttons must trigger it too, otherwise
    // zooming in with them never brings the location names back.
    markBusy();
  };

  return (
    <div
      ref={containerRef}
      className="group relative h-full w-full touch-none overflow-hidden"
      style={{ cursor: 'grab' }}
    >
      <svg
        className="absolute inset-0 h-full w-full"
        style={{ maxWidth: 'none', display: 'block' }}
      >
        <g ref={contentRef}>
          
          <WorldBase
            layout={layout}
            locations={locations}
            edges={props.edges}
            countryIndexOf={props.countryIndexOf}
            colorFor={props.colorFor}
            route={props.route}
            waypointIds={props.waypointIds}
            endpointIds={props.endpointIds}
            isolatedIds={props.isolatedIds}
            selectedEdgeIndex={props.selectedEdgeIndex}
            selectedLocationId={props.selectedLocationId}
          />
          <CaptionLayer
            layout={layout}
            countryIndexOf={props.countryIndexOf}
            scale={renderScale}
          />
          <LabelLayer
            labelIds={labelIds}
            locations={locations}
            positions={layout.positions}
            route={props.route}
            waypointIds={props.waypointIds}
            scale={renderScale}
          />
        </g>
      </svg>

      {/* Minimap */}
      <div className="pointer-events-none absolute right-3 top-16 hidden rounded-lg border border-gold-dark/25 bg-[#0d0e15]/90 p-1.5 md:block">
        <svg width={220} height={140}>
          {layout.regions.map((region) => (
            <rect
              key={region.regionId}
              x={mmX(region.x)}
              y={mmY(region.y)}
              width={region.width * minimapScale}
              height={region.height * minimapScale}
              rx={2}
              fill={COUNTRY_COLORS[props.countryIndexOf(region.countryId) % COUNTRY_COLORS.length]}
              fillOpacity={0.35}
            />
          ))}
          {props.route?.nodes.map((id) => {
            const point = layout.positions.get(id);
            if (!point) return null;
            return (
              <circle
                key={`mm-${id}`}
                cx={mmX(point.x)}
                cy={mmY(point.y)}
                r={1.6}
                fill={ROUTE_COLOR}
              />
            );
          })}
          <rect
            ref={viewportRectRef}
            fill="none"
            stroke={ROUTE_COLOR}
            strokeWidth={1}
            strokeOpacity={0.8}
          />
        </svg>
      </div>

      {/* Zoom controls */}
      <div className="absolute bottom-4 right-3 flex flex-col overflow-hidden rounded-lg border border-white/15 bg-[#0d0e15]/90">
        {[
          { label: '+', title: 'Приблизить', action: () => zoomBy(1.7) },
          { label: '−', title: 'Отдалить', action: () => zoomBy(1 / 1.7) },
          {
            label: '⛶',
            title: 'Показать весь мир',
            action: () => fitBounds({ x: layout.x, y: layout.y, width: layout.width, height: layout.height }),
          },
        ].map((control) => (
          <button
            key={control.title}
            type="button"
            title={control.title}
            aria-label={control.title}
            className="h-9 w-9 text-[15px] text-white/60 transition-colors hover:bg-white/10 hover:text-gold"
            onClick={control.action}
          >
            {control.label}
          </button>
        ))}
      </div>
    </div>
  );
});

MapCanvas.displayName = 'MapCanvas';

export default MapCanvas;
