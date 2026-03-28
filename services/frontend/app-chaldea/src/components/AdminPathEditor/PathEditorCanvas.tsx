import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import ZoneLocationPicker from './ZoneLocationPicker';

interface PathWaypoint {
  x: number;
  y: number;
}

interface NeighborEdge {
  from_id: number;
  to_id: number;
  energy_cost: number;
  path_data: PathWaypoint[] | null;
}

interface ArrowEdge {
  location_id: number;
  arrow_id: number;
  energy_cost: number;
  path_data: PathWaypoint[] | null;
}

interface MapItemData {
  id: number;
  name: string;
  type: 'location' | 'district' | 'arrow';
  map_icon_url: string | null;
  map_x: number | null;
  map_y: number | null;
  marker_type?: string | null;
  district_id?: number | null;
  parent_district_id?: number | null;
  target_region_id?: number | null;
  target_region_name?: string | null;
}

interface DistrictData {
  id: number;
  name: string;
  x: number | null;
  y: number | null;
  locations: { id: number; name: string; map_x: number | null; map_y: number | null }[];
}

type EditorMode = 'draw' | 'edit' | 'delete';

interface PathEditorCanvasProps {
  mapImageUrl: string;
  mapItems: MapItemData[];
  districts: DistrictData[];
  edges: NeighborEdge[];
  arrowEdges?: ArrowEdge[];
  mode: EditorMode;
  selectedEdgeKey: string | null;
  onSelectEdge: (key: string | null) => void;
  editWaypoints: PathWaypoint[];
  onEditWaypointsChange: (waypoints: PathWaypoint[]) => void;
  drawStartId: number | null;
  drawWaypoints: PathWaypoint[];
  onDrawClick: (locId: number) => void;
  onDrawWaypointAdd: (point: PathWaypoint) => void;
  onDeleteEdge: (fromId: number, toId: number) => void;
  onDeleteArrowEdge?: (locationId: number, arrowId: number) => void;
  onZoneLocationSelect: (districtId: number, locationId: number) => void;
  onArrowDrawClick?: (arrowId: number) => void;
  onEmptyMapClick?: (x: number, y: number) => void;
}

const MARKER_COLORS: Record<string, string> = {
  safe: '#4ade80',
  dangerous: '#f87171',
  dungeon: '#a78bfa',
  farm: '#fb923c',
};

const PathEditorCanvas = ({
  mapImageUrl,
  mapItems,
  districts,
  edges,
  arrowEdges = [],
  mode,
  selectedEdgeKey,
  onSelectEdge,
  editWaypoints,
  onEditWaypointsChange,
  drawStartId,
  drawWaypoints,
  onDrawClick,
  onDrawWaypointAdd,
  onDeleteEdge,
  onDeleteArrowEdge,
  onZoneLocationSelect,
  onArrowDrawClick,
  onEmptyMapClick,
}: PathEditorCanvasProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [draggingWpIndex, setDraggingWpIndex] = useState<number | null>(null);
  const [zonePicker, setZonePicker] = useState<{
    districtId: number;
    x: number;
    y: number;
    locations: { id: number; name: string }[];
  } | null>(null);

  // Reset map loaded on URL change
  useEffect(() => {
    setMapLoaded(false);
  }, [mapImageUrl]);

  // Build position map for locations AND districts
  const positionMap = useMemo(() => {
    const map = new Map<number, { x: number; y: number }>();
    // Include all items with coordinates (locations, districts — not arrows)
    for (const item of mapItems) {
      if (item.type !== 'arrow' && item.map_x != null && item.map_y != null) {
        map.set(item.id, { x: item.map_x, y: item.map_y });
      }
    }
    // Fallback: district child locations without own coordinates use district position
    for (const d of districts) {
      if (d.x != null && d.y != null) {
        if (!map.has(d.id)) {
          map.set(d.id, { x: d.x, y: d.y });
        }
        for (const loc of d.locations) {
          if (!map.has(loc.id)) {
            map.set(loc.id, { x: d.x, y: d.y });
          }
        }
      }
    }
    // Fallback: locations with district_id but still missing — resolve via district position
    for (const item of mapItems) {
      if (!map.has(item.id) && item.district_id != null) {
        const districtPos = map.get(item.district_id);
        if (districtPos) {
          map.set(item.id, { x: districtPos.x, y: districtPos.y });
        }
      }
    }
    return map;
  }, [mapItems, districts]);

  // Build position map for arrows (keyed by arrow id)
  const arrowPosMap = useMemo(() => {
    const map = new Map<number, { x: number; y: number }>();
    for (const item of mapItems) {
      if (item.type === 'arrow' && item.map_x != null && item.map_y != null) {
        map.set(item.id, { x: item.map_x, y: item.map_y });
      }
    }
    return map;
  }, [mapItems]);

  // District position map
  const districtPosMap = useMemo(() => {
    const map = new Map<number, { x: number; y: number }>();
    for (const d of districts) {
      if (d.x != null && d.y != null) {
        map.set(d.id, { x: d.x, y: d.y });
      }
    }
    return map;
  }, [districts]);

  // Convert client coords to percentage
  const clientToPercent = useCallback((clientX: number, clientY: number): { x: number; y: number } | null => {
    const container = containerRef.current;
    if (!container) return null;
    const rect = container.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * 100;
    const y = ((clientY - rect.top) / rect.height) * 100;
    return { x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)) };
  }, []);

  // Find which location/district/arrow was clicked (returns id or null)
  const findClickedMarker = useCallback((px: number, py: number): { type: 'location' | 'district' | 'arrow'; id: number } | null => {
    const threshold = 3; // percentage threshold for click detection

    // Check locations first
    for (const item of mapItems) {
      if (item.type === 'location' && item.map_x != null && item.map_y != null) {
        const dx = px - item.map_x;
        const dy = py - item.map_y;
        if (Math.sqrt(dx * dx + dy * dy) < threshold) {
          return { type: 'location', id: item.id };
        }
      }
    }

    // Check arrows
    for (const item of mapItems) {
      if (item.type === 'arrow' && item.map_x != null && item.map_y != null) {
        const dx = px - item.map_x;
        const dy = py - item.map_y;
        if (Math.sqrt(dx * dx + dy * dy) < threshold) {
          return { type: 'arrow', id: item.id };
        }
      }
    }

    // Check districts
    for (const d of districts) {
      if (d.x != null && d.y != null) {
        const dx = px - d.x;
        const dy = py - d.y;
        if (Math.sqrt(dx * dx + dy * dy) < threshold) {
          return { type: 'district', id: d.id };
        }
      }
    }

    return null;
  }, [mapItems, districts]);

  // Find closest edge to a point (checks both location edges and arrow edges)
  const findClosestEdge = useCallback((px: number, py: number): string | null => {
    let minDist = Infinity;
    let closestKey: string | null = null;
    const threshold = 2;

    for (const edge of edges) {
      const from = positionMap.get(edge.from_id);
      const to = positionMap.get(edge.to_id);
      if (!from || !to) continue;

      const allPoints = [from, ...(edge.path_data || []), to];

      for (let i = 0; i < allPoints.length - 1; i++) {
        const a = allPoints[i];
        const b = allPoints[i + 1];
        const dist = pointToSegmentDist(px, py, a.x, a.y, b.x, b.y);
        if (dist < minDist) {
          minDist = dist;
          closestKey = `${edge.from_id}-${edge.to_id}`;
        }
      }
    }

    // Also check arrow edges
    for (const edge of arrowEdges) {
      const from = positionMap.get(edge.location_id);
      const to = arrowPosMap.get(edge.arrow_id);
      if (!from || !to) continue;

      const allPoints = [from, ...(edge.path_data || []), to];

      for (let i = 0; i < allPoints.length - 1; i++) {
        const a = allPoints[i];
        const b = allPoints[i + 1];
        const dist = pointToSegmentDist(px, py, a.x, a.y, b.x, b.y);
        if (dist < minDist) {
          minDist = dist;
          closestKey = `arrow-${edge.location_id}-${edge.arrow_id}`;
        }
      }
    }

    return minDist < threshold ? closestKey : null;
  }, [edges, arrowEdges, positionMap, arrowPosMap]);

  // Handle SVG click
  const handleSvgClick = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const pt = clientToPercent(e.clientX, e.clientY);
    if (!pt) return;

    if (mode === 'draw') {
      const marker = findClickedMarker(pt.x, pt.y);

      if (marker) {
        if (marker.type === 'district') {
          // Show zone picker
          const district = districts.find((d) => d.id === marker.id);
          if (district && district.locations.length > 0) {
            setZonePicker({
              districtId: marker.id,
              x: district.x ?? pt.x,
              y: district.y ?? pt.y,
              locations: district.locations.map((l) => ({ id: l.id, name: l.name })),
            });
          }
          return;
        }
        if (marker.type === 'arrow') {
          // Arrow clicked in draw mode — delegate to parent
          if (onArrowDrawClick) {
            onArrowDrawClick(marker.id);
          }
          return;
        }
        // Location clicked
        onDrawClick(marker.id);
        return;
      }

      // Click on empty space = add waypoint (only if drawing is active)
      if (drawStartId != null) {
        onDrawWaypointAdd({ x: Math.round(pt.x * 10) / 10, y: Math.round(pt.y * 10) / 10 });
      } else if (onEmptyMapClick) {
        onEmptyMapClick(Math.round(pt.x * 10) / 10, Math.round(pt.y * 10) / 10);
      }
      return;
    }

    if (mode === 'edit') {
      const edgeKey = findClosestEdge(pt.x, pt.y);
      onSelectEdge(edgeKey);
      return;
    }

    if (mode === 'delete') {
      // Check if clicked on an arrow marker first (for arrow deletion)
      const marker = findClickedMarker(pt.x, pt.y);
      if (marker && marker.type === 'arrow' && onArrowDrawClick) {
        onArrowDrawClick(marker.id);
        return;
      }

      const edgeKey = findClosestEdge(pt.x, pt.y);
      if (edgeKey) {
        if (edgeKey.startsWith('arrow-') && onDeleteArrowEdge) {
          // Arrow edge: "arrow-{locationId}-{arrowId}"
          const parts = edgeKey.split('-');
          onDeleteArrowEdge(parseInt(parts[1]), parseInt(parts[2]));
        } else if (!edgeKey.startsWith('arrow-')) {
          const [fromStr, toStr] = edgeKey.split('-');
          onDeleteEdge(parseInt(fromStr), parseInt(toStr));
        }
      }
      return;
    }
  }, [mode, clientToPercent, findClickedMarker, districts, onDrawClick, drawStartId, onDrawWaypointAdd, findClosestEdge, onSelectEdge, onDeleteEdge, onDeleteArrowEdge, onArrowDrawClick, onEmptyMapClick]);

  // Handle double-click on SVG to add waypoint in edit mode
  const handleSvgDoubleClick = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (mode !== 'edit' || !selectedEdgeKey) return;
    const pt = clientToPercent(e.clientX, e.clientY);
    if (!pt) return;

    // Find the closest segment and insert a new point
    const edge = edges.find((ed) => `${ed.from_id}-${ed.to_id}` === selectedEdgeKey);
    if (!edge) return;
    const from = positionMap.get(edge.from_id);
    const to = positionMap.get(edge.to_id);
    if (!from || !to) return;

    const currentWaypoints = editWaypoints;
    const allPoints = [from, ...currentWaypoints, to];
    let bestIdx = 0;
    let bestDist = Infinity;

    for (let i = 0; i < allPoints.length - 1; i++) {
      const a = allPoints[i];
      const b = allPoints[i + 1];
      const d = pointToSegmentDist(pt.x, pt.y, a.x, a.y, b.x, b.y);
      if (d < bestDist) {
        bestDist = d;
        bestIdx = i;
      }
    }

    // Insert new point at bestIdx (adjusting for the 'from' prefix)
    const insertIdx = bestIdx; // 0 means between 'from' and first waypoint
    const newWaypoints = [...currentWaypoints];
    const newPt = { x: Math.round(pt.x * 10) / 10, y: Math.round(pt.y * 10) / 10 };
    newWaypoints.splice(insertIdx, 0, newPt);
    onEditWaypointsChange(newWaypoints);
  }, [mode, selectedEdgeKey, edges, positionMap, editWaypoints, onEditWaypointsChange, clientToPercent]);

  // Waypoint drag handlers
  const handleWaypointMouseDown = useCallback((e: React.MouseEvent, index: number) => {
    e.stopPropagation();
    e.preventDefault();
    setDraggingWpIndex(index);
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (draggingWpIndex === null || mode !== 'edit') return;
    const pt = clientToPercent(e.clientX, e.clientY);
    if (!pt) return;

    const newWaypoints = [...editWaypoints];
    newWaypoints[draggingWpIndex] = { x: Math.round(pt.x * 10) / 10, y: Math.round(pt.y * 10) / 10 };
    onEditWaypointsChange(newWaypoints);
  }, [draggingWpIndex, mode, clientToPercent, editWaypoints, onEditWaypointsChange]);

  const handleMouseUp = useCallback(() => {
    setDraggingWpIndex(null);
  }, []);

  // Right-click to remove waypoint in edit mode
  const handleWaypointContextMenu = useCallback((e: React.MouseEvent, index: number) => {
    e.preventDefault();
    e.stopPropagation();
    if (mode !== 'edit') return;
    const newWaypoints = editWaypoints.filter((_, i) => i !== index);
    onEditWaypointsChange(newWaypoints);
  }, [mode, editWaypoints, onEditWaypointsChange]);

  // Handle zone picker selection
  const handleZoneSelect = useCallback((locationId: number) => {
    if (zonePicker) {
      onZoneLocationSelect(zonePicker.districtId, locationId);
      onDrawClick(locationId);
    }
    setZonePicker(null);
  }, [zonePicker, onZoneLocationSelect, onDrawClick]);

  // Render edges
  const renderEdges = () => {
    return edges.map((edge) => {
      const from = positionMap.get(edge.from_id);
      const to = positionMap.get(edge.to_id);
      if (!from || !to) return null;

      const key = `${edge.from_id}-${edge.to_id}`;
      const isSelected = selectedEdgeKey === key;
      const isEditTarget = mode === 'edit' && isSelected;
      const waypoints = isEditTarget ? editWaypoints : (edge.path_data || []);
      const allPoints = [from, ...waypoints, to];
      const pointsStr = allPoints.map((p) => `${p.x},${p.y}`).join(' ');

      const strokeColor = isSelected
        ? 'rgba(240, 217, 92, 0.95)'
        : 'rgba(255, 255, 255, 0.7)';
      const strokeWidth = isSelected ? '0.9' : '0.5';

      return (
        <g key={key}>
          {/* Clickable wider invisible path for easier selection */}
          <polyline
            points={pointsStr}
            fill="none"
            stroke="transparent"
            strokeWidth="2"
            className="cursor-pointer"
            style={{ pointerEvents: 'stroke' }}
          />
          {/* Visible path */}
          <polyline
            points={pointsStr}
            fill="none"
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeDasharray={isSelected ? '1.5 0.5' : '1.2 0.5'}
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ pointerEvents: 'none' }}
          />
          {/* Draggable waypoint handles in edit mode */}
          {isEditTarget && editWaypoints.map((wp, idx) => (
            <circle
              key={`wp-${idx}`}
              cx={wp.x}
              cy={wp.y}
              r="0.8"
              fill="rgba(240, 217, 92, 0.9)"
              stroke="rgba(0,0,0,0.5)"
              strokeWidth="0.15"
              className="cursor-grab active:cursor-grabbing"
              style={{ pointerEvents: 'all' }}
              onMouseDown={(e) => handleWaypointMouseDown(e, idx)}
              onContextMenu={(e) => handleWaypointContextMenu(e, idx)}
            />
          ))}
        </g>
      );
    });
  };

  // Render arrow edges
  const renderArrowEdges = () => {
    return arrowEdges.map((edge) => {
      const from = positionMap.get(edge.location_id);
      const to = arrowPosMap.get(edge.arrow_id);
      if (!from || !to) return null;

      const key = `arrow-${edge.location_id}-${edge.arrow_id}`;
      const isSelected = selectedEdgeKey === key;
      const waypoints = edge.path_data || [];
      const allPoints = [from, ...waypoints, to];
      const pointsStr = allPoints.map((p) => `${p.x},${p.y}`).join(' ');

      const strokeColor = isSelected
        ? 'rgba(100, 220, 255, 0.95)'
        : 'rgba(100, 220, 255, 0.6)';
      const strokeWidth = isSelected ? '0.9' : '0.5';

      return (
        <g key={key}>
          <polyline
            points={pointsStr}
            fill="none"
            stroke="transparent"
            strokeWidth="2"
            className="cursor-pointer"
            style={{ pointerEvents: 'stroke' }}
          />
          <polyline
            points={pointsStr}
            fill="none"
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeDasharray={isSelected ? '1.5 0.5' : '1.2 0.5'}
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ pointerEvents: 'none' }}
          />
        </g>
      );
    });
  };

  // Render drawing-in-progress path
  const renderDrawingPath = () => {
    if (mode !== 'draw' || drawStartId == null) return null;
    const from = positionMap.get(drawStartId) ?? arrowPosMap.get(drawStartId);
    if (!from) return null;

    const allPoints = [from, ...drawWaypoints];
    const pointsStr = allPoints.map((p) => `${p.x},${p.y}`).join(' ');

    return (
      <g>
        <polyline
          points={pointsStr}
          fill="none"
          stroke="rgba(240, 217, 92, 0.7)"
          strokeWidth="0.4"
          strokeDasharray="0.8 0.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ pointerEvents: 'none' }}
        />
        {drawWaypoints.map((wp, idx) => (
          <circle
            key={`draw-wp-${idx}`}
            cx={wp.x}
            cy={wp.y}
            r="0.6"
            fill="rgba(240, 217, 92, 0.8)"
            stroke="rgba(0,0,0,0.4)"
            strokeWidth="0.1"
            style={{ pointerEvents: 'none' }}
          />
        ))}
      </g>
    );
  };

  // Render location markers (read-only)
  const renderMarkers = () => {
    const items = mapItems.filter((i) => i.map_x != null && i.map_y != null);

    return items.map((item) => {
      const x = item.map_x!;
      const y = item.map_y!;

      if (item.type === 'arrow') {
        return (
          <g key={`marker-arrow-${item.id}`}>
            {/* Arrow marker — cyan diamond */}
            <polygon
              points={`${x},${y - 1.8} ${x + 1.5},${y} ${x},${y + 1.8} ${x - 1.5},${y}`}
              fill="#0ea5e9"
              fillOpacity="0.7"
              stroke="#67e8f9"
              strokeWidth="0.15"
              className="cursor-pointer"
              style={{ pointerEvents: 'all' }}
            />
            {/* Small arrow indicator inside */}
            <text
              x={x}
              y={y + 0.5}
              textAnchor="middle"
              fill="white"
              fontSize="1.6"
              style={{ pointerEvents: 'none' }}
            >
              {'\u27A4'}
            </text>
            <text
              x={x}
              y={y - 2.5}
              textAnchor="middle"
              fill="#67e8f9"
              fontSize="1.3"
              fontWeight="500"
              style={{ pointerEvents: 'none', textShadow: '0 0.2px 0.5px rgba(0,0,0,0.8)' }}
            >
              {item.name}
            </text>
          </g>
        );
      }

      const color = item.type === 'district'
        ? '#b87a2a'
        : (MARKER_COLORS[item.marker_type ?? ''] ?? '#76a6bd');

      return (
        <g key={`marker-${item.type}-${item.id}`}>
          <circle
            cx={x}
            cy={y}
            r={item.type === 'district' ? '1.5' : '1.2'}
            fill={color}
            fillOpacity="0.7"
            stroke="white"
            strokeWidth="0.15"
            strokeOpacity="0.5"
            className="cursor-pointer"
            style={{ pointerEvents: 'all' }}
          />
          <text
            x={x}
            y={y - 2}
            textAnchor="middle"
            fill="white"
            fontSize="1.5"
            fontWeight="500"
            style={{ pointerEvents: 'none', textShadow: '0 0.2px 0.5px rgba(0,0,0,0.8)' }}
          >
            {item.name}
          </text>
        </g>
      );
    });

  };

  // Also render district markers from districts data
  const renderDistrictMarkers = () => {
    return districts
      .filter((d) => d.x != null && d.y != null)
      .filter((d) => !mapItems.some((m) => m.type === 'district' && m.id === d.id))
      .map((d) => (
        <g key={`district-marker-${d.id}`}>
          <circle
            cx={d.x!}
            cy={d.y!}
            r="1.5"
            fill="#b87a2a"
            fillOpacity="0.7"
            stroke="white"
            strokeWidth="0.15"
            strokeOpacity="0.5"
            className="cursor-pointer"
            style={{ pointerEvents: 'all' }}
          />
          <text
            x={d.x!}
            y={d.y! - 2}
            textAnchor="middle"
            fill="white"
            fontSize="1.5"
            fontWeight="500"
            style={{ pointerEvents: 'none', textShadow: '0 0.2px 0.5px rgba(0,0,0,0.8)' }}
          >
            {d.name}
          </text>
        </g>
      ));
  };

  return (
    <div ref={containerRef} className="relative flex-1 min-w-0 overflow-visible">
      <img
        src={mapImageUrl}
        alt="Карта региона"
        className="w-full h-auto block"
        draggable={false}
        onLoad={() => setMapLoaded(true)}
      />

      {mapLoaded && (
        <>
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            onClick={handleSvgClick}
            onDoubleClick={handleSvgDoubleClick}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{ cursor: mode === 'draw' ? (drawStartId ? 'crosshair' : 'pointer') : 'default' }}
          >
            {renderEdges()}
            {renderArrowEdges()}
            {renderDrawingPath()}
            {renderMarkers()}
            {renderDistrictMarkers()}
          </svg>

          {/* Zone picker popup */}
          {zonePicker && (
            <ZoneLocationPicker
              locations={zonePicker.locations}
              position={{ x: zonePicker.x, y: zonePicker.y }}
              containerRef={containerRef}
              onSelect={handleZoneSelect}
              onClose={() => setZonePicker(null)}
            />
          )}
        </>
      )}

      {!mapLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-site-dark/50">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
            <p className="text-white/50 text-sm">Загрузка карты...</p>
          </div>
        </div>
      )}
    </div>
  );
};

// --- Geometry helper ---

function pointToSegmentDist(
  px: number, py: number,
  ax: number, ay: number,
  bx: number, by: number
): number {
  const dx = bx - ax;
  const dy = by - ay;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.sqrt((px - ax) ** 2 + (py - ay) ** 2);

  let t = ((px - ax) * dx + (py - ay) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));

  const projX = ax + t * dx;
  const projY = ay + t * dy;
  return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2);
}

export default PathEditorCanvas;
