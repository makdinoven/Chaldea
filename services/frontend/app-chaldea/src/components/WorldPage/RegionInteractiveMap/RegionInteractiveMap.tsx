import { useMemo, useState, useRef, useEffect } from 'react';
import { motion } from 'motion/react';

export interface MapItem {
  id: number;
  name: string;
  type: 'location' | 'district';
  map_icon_url: string | null;
  map_x: number | null;
  map_y: number | null;
  marker_type: string | null;
  image_url: string | null;
}

interface NeighborEdge {
  from_id: number;
  to_id: number;
}

interface RegionInteractiveMapProps {
  mapImageUrl: string;
  mapItems: MapItem[];
  neighborEdges: NeighborEdge[];
  currentLocationId?: number | null;
  onLocationClick: (locationId: number) => void;
  onDistrictClick: (districtId: number) => void;
}

const MARKER_COLORS: Record<string, string> = {
  safe: '#88B332',
  dangerous: '#F37753',
  dungeon: '#B875BD',
};

const MARKER_ICONS: Record<string, string> = {
  safe: '\u{1F3E0}',
  dangerous: '\u{2694}\uFE0F',
  dungeon: '\u{1F3F0}',
};

const RegionInteractiveMap = ({
  mapImageUrl,
  mapItems,
  neighborEdges,
  currentLocationId,
  onLocationClick,
  onDistrictClick,
}: RegionInteractiveMapProps) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  // Only render items that have both map_x and map_y
  const mappedItems = useMemo(
    () => mapItems.filter((item) => item.map_x != null && item.map_y != null),
    [mapItems],
  );

  // Build a set of mapped location IDs for quick lookup (edges only connect locations)
  const mappedLocationIds = useMemo(
    () => new Set(mappedItems.filter((i) => i.type === 'location').map((i) => i.id)),
    [mappedItems],
  );

  // Build a map of location id -> position for SVG lines
  const positionMap = useMemo(() => {
    const map = new Map<number, { x: number; y: number }>();
    for (const item of mappedItems) {
      if (item.type === 'location') {
        map.set(item.id, { x: item.map_x!, y: item.map_y! });
      }
    }
    return map;
  }, [mappedItems]);

  // Filter edges: only draw where both endpoints are mapped locations
  const visibleEdges = useMemo(
    () => neighborEdges.filter((e) => mappedLocationIds.has(e.from_id) && mappedLocationIds.has(e.to_id)),
    [neighborEdges, mappedLocationIds],
  );

  // Reset mapLoaded on image URL change
  useEffect(() => {
    setMapLoaded(false);
  }, [mapImageUrl]);

  const itemKey = (item: MapItem) => `${item.type}-${item.id}`;

  const handleItemClick = (item: MapItem) => {
    if (item.type === 'location') {
      onLocationClick(item.id);
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
            {visibleEdges.map((edge) => {
              const from = positionMap.get(edge.from_id);
              const to = positionMap.get(edge.to_id);
              if (!from || !to) return null;

              return (
                <line
                  key={`${edge.from_id}-${edge.to_id}`}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke="rgba(240, 217, 92, 0.4)"
                  strokeWidth="0.3"
                  strokeDasharray="1 0.6"
                  strokeLinecap="round"
                />
              );
            })}
          </svg>

          {/* Map item icons */}
          {mappedItems.map((item) => {
            const key = itemKey(item);
            const isCurrent = item.type === 'location' && item.id === currentLocationId;
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
                  title={item.name}
                >
                  {/* Icon container */}
                  <div
                    className={`
                      relative flex items-center justify-center
                      transition-transform duration-200 ease-site
                      ${isHovered ? 'scale-110' : ''}
                      ${isCurrent ? 'drop-shadow-[0_0_8px_rgba(240,217,92,0.7)]' : ''}
                    `}
                  >
                    {/* Gold glow ring for current location */}
                    {isCurrent && (
                      <div
                        className="absolute -inset-1.5 rounded-full animate-pulse"
                        style={{
                          background:
                            'radial-gradient(circle, rgba(240,217,92,0.35) 0%, transparent 70%)',
                        }}
                      />
                    )}

                    {item.map_icon_url ? (
                      /* Custom icon image */
                      <img
                        src={item.map_icon_url}
                        alt={item.name}
                        className={`
                          max-w-[80px] sm:max-w-[100px] md:max-w-[120px] h-auto
                          ${isCurrent ? 'ring-2 ring-gold rounded-sm' : ''}
                        `}
                        draggable={false}
                      />
                    ) : (
                      /* Fallback marker circle */
                      <div
                        className={`
                          w-10 h-10 sm:w-12 sm:h-12 md:w-14 md:h-14 rounded-full
                          flex items-center justify-center
                          border-2 text-sm sm:text-base
                          ${isCurrent ? 'border-gold shadow-[0_0_10px_rgba(240,217,92,0.6)]' : 'border-white/50'}
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
                  </div>

                  {/* Item name label */}
                  <span
                    className={`
                      gold-text text-xs sm:text-sm font-medium text-center
                      whitespace-nowrap max-w-[100px] sm:max-w-[140px] truncate
                      transition-all duration-200 ease-site
                      ${isHovered ? 'brightness-125 scale-105' : ''}
                    `}
                    style={{
                      textShadow: '0 1px 3px rgba(0,0,0,0.8), 0 0 6px rgba(0,0,0,0.6)',
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
