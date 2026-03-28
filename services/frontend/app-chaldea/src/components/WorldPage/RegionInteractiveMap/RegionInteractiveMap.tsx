import { useMemo, useState, useRef, useEffect } from 'react';
import { motion } from 'motion/react';

export interface MapItem {
  id: number;
  name: string;
  type: 'location' | 'district' | 'arrow';
  map_icon_url: string | null;
  map_x: number | null;
  map_y: number | null;
  marker_type: string | null;
  image_url: string | null;
  map_image_url?: string | null;
  district_id?: number | null;
  parent_district_id?: number | null;
  recommended_level?: number | null;
  target_region_id?: number | null;
  target_region_name?: string | null;
  paired_arrow_id?: number | null;
}

interface ArrowEdge {
  location_id: number;
  arrow_id: number;
  energy_cost?: number;
  path_data?: PathWaypoint[] | null;
}

interface PathWaypoint {
  x: number;
  y: number;
}

interface NeighborEdge {
  from_id: number;
  to_id: number;
  energy_cost?: number;
  path_data?: PathWaypoint[] | null;
}

interface DistrictPositionData {
  id: number;
  x: number | null;
  y: number | null;
  locations: { id: number; name: string; map_x: number | null; map_y: number | null }[];
}

interface RegionInteractiveMapProps {
  mapImageUrl: string;
  mapItems: MapItem[];
  neighborEdges: NeighborEdge[];
  arrowEdges?: ArrowEdge[];
  districts?: DistrictPositionData[];
  currentLocationId?: number | null;
  onLocationClick: (locationId: number) => void;
  onDistrictClick: (districtId: number) => void;
  onArrowClick?: (targetRegionId: number) => void;
  isCityMap?: boolean;
}

const MARKER_COLORS: Record<string, string> = {
  safe: '#88B332',
  dangerous: '#F37753',
  dungeon: '#B875BD',
  farm: '#FB923C',
};

const MARKER_ICONS: Record<string, string> = {
  safe: '\u{1F3E0}',
  dangerous: '\u{2694}\uFE0F',
  dungeon: '\u{1F3F0}',
  farm: '\u{1F479}',
};

const MARKER_BADGE_COLORS: Record<string, string> = {
  safe: 'text-green-400',
  dangerous: 'text-red-400',
  dungeon: 'text-purple-400',
  farm: 'text-orange-400',
};

const renderMapBadge = (markerType?: string | null, recommendedLevel?: number | null) => {
  const icon = MARKER_ICONS[markerType ?? ''] ?? '';
  const color = MARKER_BADGE_COLORS[markerType ?? ''] ?? 'text-white/50';
  const showLevel = (markerType === 'dangerous' || markerType === 'farm') && recommendedLevel;
  const levelStr = showLevel ? `\u{00B7} \u0423\u0440.${recommendedLevel}` : '';
  const parts = [icon, levelStr].filter(Boolean).join(' ');
  if (!parts) return null;
  return (
    <span
      className={`text-[8px] sm:text-[10px] bg-black/60 px-1 py-0.5 rounded whitespace-nowrap ${color}`}
      style={{ textShadow: '0 1px 2px rgba(0,0,0,0.8)' }}
    >
      {parts}
    </span>
  );
};

const pointsToPathD = (points: Array<{ x: number; y: number }>): string =>
  points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x},${p.y}`).join(' ');

const RegionInteractiveMap = ({
  mapImageUrl,
  mapItems,
  neighborEdges,
  arrowEdges = [],
  districts = [],
  currentLocationId,
  onLocationClick,
  onDistrictClick,
  onArrowClick,
  isCityMap = false,
}: RegionInteractiveMapProps) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  // Only render items that have both map_x and map_y
  const mappedItems = useMemo(
    () => mapItems.filter((item) => item.map_x != null && item.map_y != null),
    [mapItems],
  );

  // Build a set of mapped item IDs for quick lookup (edges can connect locations or districts)
  const mappedLocationIds = useMemo(() => {
    const ids = new Set(mappedItems.filter((i) => i.type === 'location' || i.type === 'district').map((i) => i.id));
    // Include district child locations that fall back to district position
    for (const d of districts) {
      if (d.x != null && d.y != null) {
        for (const loc of d.locations) {
          ids.add(loc.id);
        }
      }
    }
    return ids;
  }, [mappedItems, districts]);

  // Build a map of item id -> position for SVG lines (locations + districts)
  // Uses numeric keys for locations/districts, string keys like "arrow-{id}" for arrows
  const positionMap = useMemo(() => {
    const map = new Map<number | string, { x: number; y: number }>();
    for (const item of mappedItems) {
      if (item.map_x != null && item.map_y != null) {
        if (item.type === 'arrow') {
          map.set(`arrow-${item.id}`, { x: item.map_x, y: item.map_y });
        } else {
          map.set(item.id, { x: item.map_x, y: item.map_y });
        }
      }
    }
    // Fallback: district child locations without own coordinates use district position
    for (const d of districts) {
      if (d.x != null && d.y != null) {
        for (const loc of d.locations) {
          if (!map.has(loc.id)) {
            map.set(loc.id, { x: d.x, y: d.y });
          }
        }
      }
    }
    return map;
  }, [mappedItems, districts]);

  // Find which district contains the current location (for zone arrow indicator)
  const currentDistrictId = useMemo(() => {
    if (currentLocationId == null) return null;
    for (const d of districts) {
      for (const loc of d.locations) {
        if (loc.id === currentLocationId) return d.id;
      }
    }
    return null;
  }, [currentLocationId, districts]);

  // Filter edges: only draw where both endpoints are mapped locations
  const visibleEdges = useMemo(
    () => neighborEdges.filter((e) => mappedLocationIds.has(e.from_id) && mappedLocationIds.has(e.to_id)),
    [neighborEdges, mappedLocationIds],
  );

  // Filter arrow edges: only draw where both endpoints exist in positionMap
  const visibleArrowEdges = useMemo(
    () => arrowEdges.filter((e) => positionMap.has(e.location_id) && positionMap.has(`arrow-${e.arrow_id}`)),
    [arrowEdges, positionMap],
  );

  // Reset mapLoaded on image URL change
  useEffect(() => {
    setMapLoaded(false);
  }, [mapImageUrl]);

  const itemKey = (item: MapItem) => `${item.type}-${item.id}`;

  const handleItemClick = (item: MapItem) => {
    if (item.type === 'location') {
      onLocationClick(item.id);
    } else if (item.type === 'arrow') {
      if (onArrowClick && item.target_region_id != null) {
        onArrowClick(item.target_region_id);
      }
    } else {
      onDistrictClick(item.id);
    }
  };

  return (
    <motion.div
      ref={containerRef}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="relative w-full rounded-map overflow-hidden select-none"
    >
      {/* Map background image */}
      <img
        src={mapImageUrl}
        alt="Карта региона"
        className="w-full h-auto block"
        draggable={false}
        onLoad={() => setMapLoaded(true)}
      />

      {mapLoaded && (
        <>
          {/* SVG overlay for neighbor lines */}
          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            <defs>
              <filter id="path-glow-active" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="0.8" in="SourceGraphic" result="blur1" />
                <feGaussianBlur stdDeviation="0.3" in="SourceGraphic" result="blur2" />
                <feMerge>
                  <feMergeNode in="blur1" />
                  <feMergeNode in="blur2" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="path-glow-inactive" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="0.4" in="SourceGraphic" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="particle-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="0.3" in="SourceGraphic" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              {/* Motion paths for active edges */}
              {visibleEdges.map((edge) => {
                const from = positionMap.get(edge.from_id);
                const to = positionMap.get(edge.to_id);
                if (!from || !to) return null;
                const isActive = currentLocationId != null &&
                  (edge.from_id === currentLocationId || edge.to_id === currentLocationId);
                if (!isActive) return null;

                const edgeKey = `${edge.from_id}-${edge.to_id}`;
                const hasPath = edge.path_data && edge.path_data.length > 0;
                const allPoints = hasPath ? [from, ...edge.path_data!, to] : [from, to];

                // Particles travel outward from currentLocationId
                const orientedPoints = edge.to_id === currentLocationId
                  ? [...allPoints].reverse()
                  : allPoints;

                return (
                  <path
                    key={`motion-${edgeKey}`}
                    id={`path-motion-${edgeKey}`}
                    d={pointsToPathD(orientedPoints)}
                    fill="none"
                  />
                );
              })}
              {/* Motion paths for active arrow edges */}
              {visibleArrowEdges.map((edge) => {
                const from = positionMap.get(edge.location_id);
                const to = positionMap.get(`arrow-${edge.arrow_id}`);
                if (!from || !to) return null;
                const isActive = currentLocationId != null && edge.location_id === currentLocationId;
                if (!isActive) return null;

                const edgeKey = `arrow-${edge.location_id}-${edge.arrow_id}`;
                const hasPath = edge.path_data && edge.path_data.length > 0;
                const allPoints = hasPath ? [from, ...edge.path_data!, to] : [from, to];

                return (
                  <path
                    key={`motion-${edgeKey}`}
                    id={`path-motion-${edgeKey}`}
                    d={pointsToPathD(allPoints)}
                    fill="none"
                  />
                );
              })}
            </defs>
            {visibleEdges.map((edge) => {
              const from = positionMap.get(edge.from_id);
              const to = positionMap.get(edge.to_id);
              if (!from || !to) return null;

              const isActive = currentLocationId != null &&
                (edge.from_id === currentLocationId || edge.to_id === currentLocationId);
              const edgeKey = `${edge.from_id}-${edge.to_id}`;
              const hasPath = edge.path_data && edge.path_data.length > 0;

              // Build points string for polyline
              const allPoints = hasPath ? [from, ...edge.path_data!, to] : [from, to];
              const pointsStr = allPoints.map((p) => `${p.x},${p.y}`).join(' ');

              return (
                <g key={edgeKey}>
                  {/* Layer 1: Dark underlay (always) */}
                  <polyline
                    points={pointsStr}
                    fill="none"
                    stroke="rgba(0, 0, 0, 0.55)"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />

                  {/* Layer 2: Glow (active with pulse, inactive subtle) */}
                  {isActive ? (
                    <polyline
                      points={pointsStr}
                      fill="none"
                      stroke="rgba(240, 217, 92, 0.5)"
                      strokeWidth="1.0"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      filter="url(#path-glow-active)"
                    >
                      <animate
                        attributeName="opacity"
                        values="0.3;0.7;0.3"
                        dur="2s"
                        repeatCount="indefinite"
                      />
                    </polyline>
                  ) : (
                    <polyline
                      points={pointsStr}
                      fill="none"
                      stroke="rgba(240, 217, 92, 0.35)"
                      strokeWidth="0.6"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      filter="url(#path-glow-inactive)"
                    />
                  )}

                  {/* Layer 3: Base gold dashes (always) */}
                  <polyline
                    points={pointsStr}
                    fill="none"
                    stroke={isActive ? 'rgba(240, 217, 92, 0.5)' : 'rgba(240, 217, 92, 0.3)'}
                    strokeWidth={isActive ? '0.4' : '0.3'}
                    strokeDasharray="1 0.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />

                  {/* Layer 4: Running particles (active only) */}
                  {isActive && (
                    <>
                      {[0, 1, 2].map((i) => (
                        <circle
                          key={i}
                          r="0.4"
                          fill="rgba(240, 217, 92, 0.6)"
                          filter="url(#particle-glow)"
                        >
                          <animateMotion
                            dur="6s"
                            repeatCount="indefinite"
                            begin={`${i * 2}s`}
                          >
                            <mpath href={`#path-motion-${edgeKey}`} />
                          </animateMotion>
                        </circle>
                      ))}
                    </>
                  )}
                </g>
              );
            })}
            {/* Arrow edges — same visual style as neighbor edges */}
            {visibleArrowEdges.map((edge) => {
              const from = positionMap.get(edge.location_id);
              const to = positionMap.get(`arrow-${edge.arrow_id}`);
              if (!from || !to) return null;

              const isActive = currentLocationId != null && edge.location_id === currentLocationId;
              const edgeKey = `arrow-${edge.location_id}-${edge.arrow_id}`;
              const hasPath = edge.path_data && edge.path_data.length > 0;

              const allPoints = hasPath ? [from, ...edge.path_data!, to] : [from, to];
              const pointsStr = allPoints.map((p) => `${p.x},${p.y}`).join(' ');

              return (
                <g key={edgeKey}>
                  <polyline
                    points={pointsStr}
                    fill="none"
                    stroke="rgba(0, 0, 0, 0.55)"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {isActive ? (
                    <polyline
                      points={pointsStr}
                      fill="none"
                      stroke="rgba(240, 217, 92, 0.5)"
                      strokeWidth="1.0"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      filter="url(#path-glow-active)"
                    >
                      <animate
                        attributeName="opacity"
                        values="0.3;0.7;0.3"
                        dur="2s"
                        repeatCount="indefinite"
                      />
                    </polyline>
                  ) : (
                    <polyline
                      points={pointsStr}
                      fill="none"
                      stroke="rgba(240, 217, 92, 0.35)"
                      strokeWidth="0.6"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      filter="url(#path-glow-inactive)"
                    />
                  )}
                  <polyline
                    points={pointsStr}
                    fill="none"
                    stroke={isActive ? 'rgba(240, 217, 92, 0.5)' : 'rgba(240, 217, 92, 0.3)'}
                    strokeWidth={isActive ? '0.4' : '0.3'}
                    strokeDasharray="1 0.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {isActive && (
                    <>
                      {[0, 1, 2].map((i) => (
                        <circle
                          key={i}
                          r="0.4"
                          fill="rgba(240, 217, 92, 0.6)"
                          filter="url(#particle-glow)"
                        >
                          <animateMotion
                            dur="6s"
                            repeatCount="indefinite"
                            begin={`${i * 2}s`}
                          >
                            <mpath href={`#path-motion-${edgeKey}`} />
                          </animateMotion>
                        </circle>
                      ))}
                    </>
                  )}
                </g>
              );
            })}
          </svg>

          {/* Map item icons */}
          {mappedItems.map((item) => {
            const key = itemKey(item);
            const isCurrent =
              (item.type === 'location' && item.id === currentLocationId) ||
              (item.type === 'district' && item.id === currentDistrictId);
            const isHovered = key === hoveredId;

            return (
              <div
                key={key}
                className="absolute pointer-events-auto"
                style={{
                  left: `${item.map_x}%`,
                  top: `${item.map_y}%`,
                  transform: 'translate(-50%, -50%)',
                  zIndex: isCurrent ? 20 : isHovered ? 15 : 10,
                }}
              >
                {/* Icon + label wrapper */}
                <button
                  onClick={() => handleItemClick(item)}
                  onMouseEnter={() => setHoveredId(key)}
                  onMouseLeave={() => setHoveredId(null)}
                  className="flex flex-col items-center gap-1 cursor-pointer group bg-transparent border-none p-0"
                >
                  {/* Icon container */}
                  <div
                    className={`
                      relative flex items-center justify-center
                      transition-all duration-300 ease-site
                      ${isHovered ? 'scale-[1.15] drop-shadow-[0_0_12px_rgba(240,217,92,0.6)]' : ''}
                    `}
                  >
                    {/* "You are here" arrow above current location */}
                    {isCurrent && (
                      <div className="absolute -top-5 inset-x-0 flex justify-center animate-bounce pointer-events-none">
                        <svg width="20" height="14" viewBox="0 0 14 10" fill="none">
                          <path d="M7 10L1 2h12L7 10z" fill="rgba(240,217,92,0.9)" stroke="rgba(0,0,0,0.55)" strokeWidth="1" />
                        </svg>
                      </div>
                    )}

                    {/* Hover glow ring */}
                    {isHovered && !isCurrent && (
                      <div
                        className="absolute -inset-2 rounded-full pointer-events-none"
                        style={{
                          background: 'radial-gradient(circle, rgba(240,217,92,0.2) 0%, transparent 70%)',
                        }}
                      />
                    )}
                    {item.type === 'arrow' ? (
                      /* Arrow marker: directional arrow icon */
                      <div
                        className="w-[44px] h-[44px] sm:w-[50px] sm:h-[50px] rounded-full flex items-center justify-center border-2 border-cyan-400/60 bg-cyan-900/60"
                      >
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="sm:w-[28px] sm:h-[28px]">
                          <path d="M5 12h14M13 6l6 6-6 6" stroke="rgba(100,220,255,0.9)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                    ) : isCityMap ? (
                      /* City map: round icons with image */
                      (() => {
                        const imgUrl = item.map_icon_url || item.image_url;
                        const borderStyle = isCurrent
                          ? 'border-[6px] border-red-500 shadow-[0_0_14px_rgba(239,68,68,0.7),0_0_5px_rgba(239,68,68,0.4)]'
                          : isHovered
                            ? 'border-[6px] border-gold shadow-[0_0_12px_rgba(240,217,92,0.5)]'
                            : 'border-[6px] border-gold';
                        if (imgUrl) {
                          return (
                            <div className={`rounded-full p-[4px] transition-all duration-300 ease-site ${
                              isCurrent
                                ? 'bg-red-500 shadow-[0_0_14px_rgba(239,68,68,0.7),0_0_5px_rgba(239,68,68,0.4)]'
                                : isHovered
                                  ? 'bg-gold shadow-[0_0_12px_rgba(240,217,92,0.5)]'
                                  : 'bg-gold'
                            }`}>
                              <div className="w-[48px] h-[48px] rounded-full overflow-hidden">
                                <img src={imgUrl} alt={item.name} className="w-full h-full object-cover" draggable={false} />
                              </div>
                            </div>
                          );
                        }
                        return (
                          <div
                            className={`w-[54px] h-[54px] rounded-full flex items-center justify-center text-sm transition-all duration-300 ease-site ${borderStyle}`}
                            style={{ backgroundColor: item.type === 'district' ? 'rgba(180,130,50,0.5)' : (MARKER_COLORS[item.marker_type ?? ''] ?? '#76a6bd') + '99' }}
                          >
                            <span className="leading-none">{item.type === 'district' ? '\u{2666}' : (MARKER_ICONS[item.marker_type ?? ''] ?? '\u{1F4CD}')}</span>
                          </div>
                        );
                      })()
                    ) : item.map_icon_url ? (
                      /* Region map: custom icon image */
                      <img
                        src={item.map_icon_url}
                        alt={item.name}
                        className={`
                          w-[50px] h-[50px] object-contain
                        `}
                        draggable={false}
                      />
                    ) : (
                      /* Region map: fallback marker circle */
                      <div
                        className={`
                          w-[50px] h-[50px] rounded-full
                          flex items-center justify-center
                          border-2 text-sm sm:text-base
                          border-white/50
                        `}
                        style={{
                          backgroundColor:
                            (MARKER_COLORS[item.marker_type ?? ''] ?? '#76a6bd') + '99',
                        }}
                      >
                        <span className="leading-none">
                          {MARKER_ICONS[item.marker_type ?? ''] ?? '\u{1F4CD}'}
                        </span>
                      </div>
                    )}

                    {/* Marker badge — top-right above icon */}
                    {renderMapBadge(item.marker_type, item.recommended_level) && (
                      <div className="absolute -top-3 left-1/2 pointer-events-none">
                        {renderMapBadge(item.marker_type, item.recommended_level)}
                      </div>
                    )}

                    {/* City map indicator for districts with map_image_url */}
                    {item.type === 'district' && item.map_image_url && (
                      <div className="absolute -bottom-1 -right-1 w-4 h-4 sm:w-5 sm:h-5 bg-amber-500/90 rounded-full flex items-center justify-center pointer-events-none border border-amber-300/50">
                        <span className="text-[8px] sm:text-[10px] leading-none">{'\u{1F5FA}\uFE0F'}</span>
                      </div>
                    )}
                  </div>

                  {/* Item name label */}
                  <span
                    className={`
                      text-xs sm:text-sm font-semibold text-center
                      whitespace-nowrap max-w-[100px] sm:max-w-[140px] truncate
                      transition-all duration-300 ease-site
                      ${isHovered ? 'text-gold scale-110' : 'text-white'}
                    `}
                    style={{
                      textShadow: isHovered
                        ? '0 0 12px rgba(240,217,92,0.9), 0 0 4px rgba(240,217,92,0.5), 0 1px 3px rgba(0,0,0,0.9)'
                        : '0 0 8px rgba(240,217,92,0.7), 0 1px 3px rgba(0,0,0,0.9)',
                    }}
                  >
                    {item.name}
                  </span>

                  {/* "You are here" badge */}
                  {isCurrent && (
                    <span
                      className="
                        text-[10px] sm:text-xs font-medium text-gold
                        bg-site-bg px-1.5 py-0.5 rounded-card
                        border border-gold/40 whitespace-nowrap
                      "
                      style={{
                        textShadow: '0 1px 2px rgba(0,0,0,0.6)',
                      }}
                    >
                        Вы здесь
                    </span>
                  )}
                </button>
              </div>
            );
          })}
        </>
      )}

      {/* Loading state before map image is loaded */}
      {!mapLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-site-dark/50">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
            <p className="text-white/50 text-sm">Загрузка карты...</p>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default RegionInteractiveMap;
