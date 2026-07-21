import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { useAppSelector } from '../../redux/store';
import { selectPermissions } from '../../redux/slices/userSlice';
import { hasPermission } from '../../utils/permissions';
import { fetchWorldGraph, type GraphEdge, type WorldGraph } from '../../api/worldGraph';
import type { LocationFormValues } from '../../api/mapEditor';
import { buildAdjacency, computeRoute, findComponents, type RouteMode, type RouteResult } from './graphUtils';
import { computeLayout, type WorldLayout } from './layout';
import MapCanvas, { type MapCanvasHandle } from './MapCanvas';
import MapLegend, { type ComponentSummary } from './MapLegend';
import MapSearch, { type SearchHit } from './MapSearch';
import NavigatorPanel from './NavigatorPanel';
import EdgeInspector from './EdgeInspector';
import LocationInspector from './LocationInspector';
import {
  COMPONENT_COLORS,
  COUNTRY_COLORS,
  ISOLATED_COLOR,
  MARKER_COLORS,
  levelColor,
  type ColorMode,
} from './theme';

type MapMode = 'navigate' | 'edit';
type Selection =
  | { kind: 'edge'; index: number }
  | { kind: 'location'; id: number }
  | null;

/** Edges are stored with a < b; normalise before comparing or inserting. */
const edgeKey = (a: number, b: number) => (a < b ? `${a}:${b}` : `${b}:${a}`);

const WorldMapPage = () => {
  const [graph, setGraph] = useState<WorldGraph | null>(null);
  /**
   * Snapshot the layout is built from. Kept separate from `graph` so editing a
   * link does not reshuffle every node under the user's cursor.
   */
  const [layoutSource, setLayoutSource] = useState<WorldGraph | null>(null);
  const [layout, setLayout] = useState<WorldLayout | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [colorMode, setColorMode] = useState<ColorMode>('marker');
  const [mode, setMode] = useState<MapMode>('navigate');
  const [routeMode, setRouteMode] = useState<RouteMode>('energy');
  const [waypoints, setWaypoints] = useState<Array<number | null>>([null, null]);
  const [activeSlot, setActiveSlot] = useState<number | null>(0);
  const [selection, setSelection] = useState<Selection>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const mapRef = useRef<MapCanvasHandle>(null);

  const permissions = useAppSelector(selectPermissions);
  const canEdit = hasPermission(permissions, 'locations:update');
  const canDelete = hasPermission(permissions, 'locations:delete');

  // The global stylesheet gives #root a max-width and a 100px bottom margin,
  // which would leave a stray scrollbar behind this full-screen page.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchWorldGraph()
      .then((data) => {
        if (cancelled) return;
        setGraph(data);
        setLayoutSource(data);
      })
      .catch(() => {
        if (!cancelled) setError('Не удалось загрузить карту мира. Попробуйте обновить страницу.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The force layout takes a few hundred ms on ~2000 nodes. Defer it by a tick
  // so the loading state actually paints before the main thread blocks.
  useEffect(() => {
    if (!layoutSource) return undefined;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      try {
        setLayout(computeLayout(layoutSource));
      } catch {
        setError('Не удалось построить карту мира.');
      }
    }, 30);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [layoutSource]);

  const locationById = useMemo(
    () => new Map((graph?.locations ?? []).map((l) => [l.id, l])),
    [graph],
  );
  const regionNames = useMemo(
    () => new Map((graph?.regions ?? []).map((r) => [r.id, r.name])),
    [graph],
  );
  const countryIndexMap = useMemo(
    () => new Map((graph?.countries ?? []).map((c, index) => [c.id, index])),
    [graph],
  );
  const countryIndexOf = useCallback(
    (countryId: number) => countryIndexMap.get(countryId) ?? 0,
    [countryIndexMap],
  );
  const maxLevel = useMemo(
    () => (graph?.locations ?? []).reduce((max, l) => Math.max(max, l.recommended_level), 1),
    [graph],
  );

  const adjacency = useMemo(() => buildAdjacency(graph?.edges ?? []), [graph]);
  const componentOf = useMemo(
    () => (graph ? findComponents(graph) : new Map<number, number>()),
    [graph],
  );

  const componentRank = useMemo(() => {
    const sizes = new Map<number, number>();
    componentOf.forEach((componentId) => {
      sizes.set(componentId, (sizes.get(componentId) ?? 0) + 1);
    });
    const ranked = [...sizes.entries()]
      .filter(([, size]) => size > 1)
      .sort((a, b) => b[1] - a[1] || a[0] - b[0]);
    const rank = new Map<number, number>();
    ranked.forEach(([componentId], index) => rank.set(componentId, index));
    return { rank, ranked, total: sizes.size };
  }, [componentOf]);

  const componentSummaries: ComponentSummary[] = useMemo(
    () =>
      componentRank.ranked.slice(0, COMPONENT_COLORS.length).map(([id, size], index) => ({
        id,
        size,
        color: COMPONENT_COLORS[index],
      })),
    [componentRank],
  );

  const isolatedIds = useMemo(() => {
    const set = new Set<number>();
    (graph?.locations ?? []).forEach((location) => {
      if (componentRank.rank.get(componentOf.get(location.id) ?? -1) === undefined) {
        set.add(location.id);
      }
    });
    return set;
  }, [graph, componentOf, componentRank]);

  const route: RouteResult | null = useMemo(() => {
    const points = waypoints.filter((id): id is number => id !== null);
    if (points.length < 2) return null;
    return computeRoute(adjacency, points, routeMode);
  }, [adjacency, waypoints, routeMode]);

  const waypointIds = useMemo(
    () => new Set(waypoints.filter((id): id is number => id !== null)),
    [waypoints],
  );

  const endpointIds = useMemo(() => {
    const points = waypoints.filter((id): id is number => id !== null);
    if (points.length === 0) return new Set<number>();
    return new Set([points[0], points[points.length - 1]]);
  }, [waypoints]);

  const colorFor = useCallback(
    (locationId: number): string => {
      const location = locationById.get(locationId);
      if (!location) return ISOLATED_COLOR;
      switch (colorMode) {
        case 'marker':
          return MARKER_COLORS[location.marker_type] ?? MARKER_COLORS.safe;
        case 'country':
          return COUNTRY_COLORS[countryIndexOf(location.country_id) % COUNTRY_COLORS.length];
        case 'component': {
          const rank = componentRank.rank.get(componentOf.get(locationId) ?? -1);
          if (rank === undefined || rank >= COMPONENT_COLORS.length) return ISOLATED_COLOR;
          return COMPONENT_COLORS[rank];
        }
        case 'level':
        default:
          return levelColor(location.recommended_level, maxLevel);
      }
    },
    [colorMode, locationById, countryIndexOf, componentRank, componentOf, maxLevel],
  );

  const assignWaypoint = useCallback((locationId: number) => {
    setWaypoints((current) => {
      const next = [...current];
      const empty = next.findIndex((value) => value === null);
      setActiveSlot((slot) => {
        const target = slot !== null && slot < next.length ? slot : empty === -1 ? next.length - 1 : empty;
        next[target] = locationId;
        return target + 1 < next.length ? target + 1 : target;
      });
      return next;
    });
  }, []);

  const onLocationClick = useCallback((locationId: number) => {
    if (mode === 'edit') {
      setSelection({ kind: 'location', id: locationId });
      setPanelOpen(true);
    } else {
      assignWaypoint(locationId);
    }
  }, [mode, assignWaypoint]);

  const onEdgeClick = useCallback((edgeIndex: number) => {
    if (mode !== 'edit') return;
    setSelection({ kind: 'edge', index: edgeIndex });
    setPanelOpen(true);
  }, [mode]);

  const onBackgroundClick = useCallback(() => setSelection(null), []);

  const focusLocation = useCallback((locationId: number) => {
    const position = layout?.positions.get(locationId);
    if (position) mapRef.current?.centerOn(position.x, position.y, 1.2);
  }, [layout]);

  const focusHit = useCallback((hit: SearchHit) => {
    if (!layout || !graph) return;
    if (hit.kind === 'location') {
      focusLocation(hit.id);
      if (mode === 'edit') setSelection({ kind: 'location', id: hit.id });
      return;
    }
    if (hit.kind === 'region') {
      const region = layout.regions.find((r) => r.regionId === hit.id);
      if (region) mapRef.current?.fitBounds(region);
      return;
    }
    if (hit.kind === 'country') {
      const country = layout.countries.find((c) => c.countryId === hit.id);
      if (country) mapRef.current?.fitBounds(country);
      return;
    }
    // District: frame the locations that belong to it.
    const points = graph.locations
      .filter((location) => location.district_id === hit.id)
      .map((location) => layout.positions.get(location.id))
      .filter((point): point is { x: number; y: number } => Boolean(point));
    if (points.length === 0) return;
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    mapRef.current?.fitBounds({
      x: minX - 80,
      y: minY - 80,
      width: Math.max(...xs) - minX + 160,
      height: Math.max(...ys) - minY + 160,
    });
  }, [layout, graph, mode, focusLocation]);

  // Frame the whole route whenever it changes so the user sees the result.
  useEffect(() => {
    if (!route?.complete || !layout || route.nodes.length === 0) return;
    const points = route.nodes
      .map((id) => layout.positions.get(id))
      .filter((point): point is { x: number; y: number } => Boolean(point));
    if (points.length === 0) return;
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    mapRef.current?.fitBounds({
      x: minX - 120,
      y: minY - 120,
      width: Math.max(...xs) - minX + 240,
      height: Math.max(...ys) - minY + 240,
    });
  }, [route, layout]);

  // ---- graph mutations, applied locally so the map redraws immediately ----

  const applyEdgeCost = useCallback((edge: GraphEdge, energyCost: number) => {
    setGraph((current) => {
      if (!current) return current;
      const edges = current.edges.map((candidate) =>
        candidate.a === edge.a && candidate.b === edge.b
          ? {
              ...candidate,
              cost_ab: candidate.cost_ab === null ? null : energyCost,
              cost_ba: candidate.cost_ba === null ? null : energyCost,
            }
          : candidate,
      );
      return { ...current, edges };
    });
  }, []);

  const removeEdge = useCallback((a: number, b: number) => {
    setGraph((current) => {
      if (!current) return current;
      const key = edgeKey(a, b);
      const edges = current.edges.filter((candidate) => edgeKey(candidate.a, candidate.b) !== key);
      return {
        ...current,
        edges,
        stats: { ...current.stats, edges: edges.length },
      };
    });
    setSelection(null);
  }, []);

  const addEdge = useCallback((from: number, to: number, cost: number) => {
    setGraph((current) => {
      if (!current) return current;
      const key = edgeKey(from, to);
      if (current.edges.some((candidate) => edgeKey(candidate.a, candidate.b) === key)) {
        return current;
      }
      const [a, b] = from < to ? [from, to] : [to, from];
      // The backend writes both directions, so the new edge is bidirectional.
      const edges = [...current.edges, { a, b, cost_ab: cost, cost_ba: cost, auto: false }];
      return {
        ...current,
        edges,
        stats: { ...current.stats, edges: edges.length },
      };
    });
  }, []);

  const applyLocationValues = useCallback((locationId: number, values: LocationFormValues) => {
    setGraph((current) => {
      if (!current) return current;
      const regionCountry = new Map(current.regions.map((r) => [r.id, r.country_id]));
      const districtRegion = new Map(current.districts.map((d) => [d.id, d.region_id]));
      const nextRegionId = values.district_id
        ? districtRegion.get(values.district_id) ?? values.region_id
        : values.region_id;
      return {
        ...current,
        locations: current.locations.map((location) =>
          location.id === locationId
            ? {
                ...location,
                name: values.name,
                marker_type: values.marker_type,
                recommended_level: values.recommended_level,
                no_quick_move: values.no_quick_move,
                quick_travel_marker: values.quick_travel_marker,
                district_id: values.district_id,
                region_id: nextRegionId ?? location.region_id,
                country_id: regionCountry.get(nextRegionId ?? location.region_id) ?? location.country_id,
              }
            : location,
        ),
      };
    });
  }, []);

  const selectedEdge = useMemo(() => {
    if (selection?.kind !== 'edge' || !graph) return null;
    return graph.edges[selection.index] ?? null;
  }, [selection, graph]);

  const selectedNeighbours = useMemo(() => {
    if (selection?.kind !== 'location' || !graph) return [];
    return graph.edges
      .filter((edge) => edge.a === selection.id || edge.b === selection.id)
      .map((edge) => ({
        id: edge.a === selection.id ? edge.b : edge.a,
        cost: (edge.a === selection.id ? edge.cost_ab : edge.cost_ba) ?? edge.cost_ab ?? edge.cost_ba ?? 1,
      }));
  }, [selection, graph]);

  if (error) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-[#070810] px-6 text-center">
        <p className="text-[15px] text-site-red">{error}</p>
        <Link to="/home" className="site-link text-[13px]">Вернуться на сайт</Link>
      </div>
    );
  }

  if (!graph || !layout) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-[#070810]">
        <div className="h-10 w-10 animate-spin-slow rounded-full border-2 border-gold-dark border-t-transparent" />
        <p className="text-[13px] text-white/50">
          {graph ? 'Строим карту мира…' : 'Загружаем мир…'}
        </p>
      </div>
    );
  }

  const inspector = (() => {
    if (selection?.kind === 'edge' && selectedEdge) {
      return (
        <EdgeInspector
          edge={selectedEdge}
          locationById={locationById}
          regionNames={regionNames}
          canDelete={canDelete}
          onCostChanged={applyEdgeCost}
          onDeleted={(edge) => removeEdge(edge.a, edge.b)}
          onClose={() => setSelection(null)}
          onFocusLocation={focusLocation}
        />
      );
    }
    if (selection?.kind === 'location') {
      return (
        <LocationInspector
          key={selection.id}
          locationId={selection.id}
          locations={graph.locations}
          locationById={locationById}
          regions={graph.regions}
          districts={graph.districts}
          regionNames={regionNames}
          neighbours={selectedNeighbours}
          canEdit={canEdit}
          canDelete={canDelete}
          onSaved={applyLocationValues}
          onNeighbourAdded={addEdge}
          onNeighbourRemoved={removeEdge}
          onClose={() => setSelection(null)}
          onFocusLocation={focusLocation}
        />
      );
    }
    return null;
  })();

  const panelContent = (
    <div className="flex flex-col gap-5">
      {canEdit && (
        <div className="flex overflow-hidden rounded-lg border border-gold-dark/40">
          {(['navigate', 'edit'] as MapMode[]).map((option) => (
            <button
              key={option}
              type="button"
              className={`flex-1 px-3 py-1.5 text-[12px] transition-colors ${
                mode === option ? 'bg-gold-dark/35 text-gold-light' : 'text-white/50 hover:bg-white/5'
              }`}
              onClick={() => {
                setMode(option);
                setSelection(null);
              }}
            >
              {option === 'navigate' ? 'Навигатор' : 'Редактор'}
            </button>
          ))}
        </div>
      )}

      {mode === 'edit' ? (
        inspector ?? (
          <div className="flex flex-col gap-2">
            <h2 className="gold-text text-[15px] font-semibold">Редактор</h2>
            <p className="text-[11px] leading-snug text-white/50">
              Кликните по локации, чтобы отредактировать её и её переходы.
              Кликните по линии между локациями, чтобы изменить стоимость перехода
              или удалить его.
            </p>
            <button
              type="button"
              className="btn-line mt-1 text-[12px]"
              onClick={() => setLayoutSource(graph)}
            >
              Перестроить раскладку
            </button>
            <p className="text-[10px] leading-snug text-white/35">
              Позиции узлов фиксируются при загрузке, чтобы карта не «прыгала» после
              правок. Перестройте раскладку, если меняли принадлежность локаций регионам.
            </p>
          </div>
        )
      ) : (
        <NavigatorPanel
          locations={graph.locations}
          locationById={locationById}
          regionNames={regionNames}
          waypoints={waypoints}
          onWaypointsChange={setWaypoints}
          activeSlot={activeSlot}
          onActiveSlotChange={setActiveSlot}
          mode={routeMode}
          onModeChange={setRouteMode}
          route={route}
          onFocusLocation={focusLocation}
        />
      )}

      <div className="gradient-divider-h" />
      <MapLegend
        colorMode={colorMode}
        onColorModeChange={setColorMode}
        stats={graph.stats}
        countries={graph.countries}
        components={componentSummaries}
        componentCount={componentRank.total}
        maxLevel={maxLevel}
      />
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-[#070810]">
      <MapCanvas
        ref={mapRef}
        layout={layout}
        locations={graph.locations}
        edges={graph.edges}
        countryIndexOf={countryIndexOf}
        colorFor={colorFor}
        route={route}
        waypointIds={waypointIds}
        endpointIds={endpointIds}
        isolatedIds={isolatedIds}
        selectedEdgeIndex={selection?.kind === 'edge' ? selection.index : null}
        selectedLocationId={selection?.kind === 'location' ? selection.id : null}
        onLocationClick={onLocationClick}
        onEdgeClick={onEdgeClick}
        onBackgroundClick={onBackgroundClick}
      />

      <header className="pointer-events-none absolute left-0 top-0 z-20 flex w-full items-start gap-3 p-3 md:p-4">
        <div className="pointer-events-auto shrink-0 rounded-card border border-gold-dark/30 bg-[#0d0e15]/95 px-3 py-2">
          <h1 className="gold-text text-[15px] font-bold leading-none md:text-[18px]">
            Карта мира Chaldea
          </h1>
          <p className="mt-1 text-[10px] text-white/45 md:text-[11px]">
            {graph.stats.locations} локаций · {graph.stats.edges} связей
          </p>
        </div>

        <div className="pointer-events-auto ml-auto w-[min(420px,55vw)] md:w-[380px]">
          <MapSearch graph={graph} countryIndexOf={countryIndexOf} onSelect={focusHit} />
        </div>

        <Link
          to="/home"
          className="pointer-events-auto hidden shrink-0 rounded-card border border-white/10 bg-[#0d0e15]/95
                     px-3 py-2 text-[12px] text-white/60 transition-colors hover:text-gold md:block"
        >
          ← На сайт
        </Link>
      </header>

      {/* Desktop side panel — collapsible to free up the canvas */}
      {!sidebarCollapsed && (
        <aside
          className="gold-scrollbar absolute bottom-4 left-3 top-28 z-20 hidden w-[340px] overflow-y-auto
                     rounded-card border border-gold-dark/30 bg-[#0d0e15]/95 p-4 pt-9 md:block"
        >
          <button
            type="button"
            aria-label="Свернуть панель"
            title="Свернуть панель"
            className="absolute right-3 top-2.5 rounded px-1.5 py-0.5 text-[13px] text-white/40
                       transition-colors hover:text-gold"
            onClick={() => setSidebarCollapsed(true)}
          >
            ‹‹
          </button>
          {panelContent}
        </aside>
      )}

      {sidebarCollapsed && (
        <button
          type="button"
          aria-label="Развернуть панель"
          title="Развернуть панель"
          className="absolute left-3 top-28 z-20 hidden items-center gap-2 rounded-card border
                     border-gold-dark/40 bg-[#0d0e15]/95 px-3 py-2 text-[12px] text-gold-light
                     transition-colors hover:bg-gold-dark/20 md:flex"
          onClick={() => setSidebarCollapsed(false)}
        >
          ›› {mode === 'edit' ? 'Редактор' : 'Навигатор'}
          {route?.complete && mode === 'navigate' && (
            <span className="text-white/55">{route.energy} эн.</span>
          )}
        </button>
      )}

      {/* Mobile drawer */}
      <button
        type="button"
        className="absolute bottom-4 left-3 z-30 rounded-card border border-gold-dark/50 bg-[#0d0e15]/95
                   px-4 py-2.5 text-[13px] text-gold-light md:hidden"
        onClick={() => setPanelOpen(true)}
      >
        {mode === 'edit' ? 'Редактор' : 'Навигатор'}
        {route?.complete && mode === 'navigate' && (
          <span className="ml-2 text-white/60">{route.energy} эн.</span>
        )}
      </button>

      {panelOpen && (
        <div className="absolute inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setPanelOpen(false)}
            role="presentation"
          />
          <div
            className="gold-scrollbar absolute bottom-0 left-0 right-0 max-h-[82vh] overflow-y-auto
                       rounded-t-card-lg border-t border-gold-dark/40 bg-[#0d0e15] p-4"
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[12px] uppercase tracking-wide text-white/45">Панель</span>
              <button
                type="button"
                className="text-white/50 transition-colors hover:text-site-red"
                onClick={() => setPanelOpen(false)}
                aria-label="Закрыть панель"
              >
                ✕
              </button>
            </div>
            {panelContent}
          </div>
        </div>
      )}
    </div>
  );
};

export default WorldMapPage;
