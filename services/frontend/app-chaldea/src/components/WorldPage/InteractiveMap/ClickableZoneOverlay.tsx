import { useEffect, useRef, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import type { ClickableZone } from '../../../redux/actions/worldMapActions';
import MapZoneCard from './MapZoneCard';

interface CountryEmblemData {
  id: number;
  emblem_url: string | null;
}

interface ClickableZoneOverlayProps {
  zones: ClickableZone[];
  onZoneClick: (zone: ClickableZone) => void;
  countries?: CountryEmblemData[];
}

const getPolygonCenter = (points: { x: number; y: number }[]): { x: number; y: number } => {
  if (points.length === 0) return { x: 50, y: 50 };
  const sum = points.reduce(
    (acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }),
    { x: 0, y: 0 },
  );
  return { x: sum.x / points.length, y: sum.y / points.length };
};

const DEFAULT_OUTLINE_COLOR = '#f0d95c';
const HEX_COLOR = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** Zone colour for the coastline glow; zones without a valid colour glow gold */
const outlineColor = (zone: ClickableZone): string =>
  zone.stroke_color && HEX_COLOR.test(zone.stroke_color) ? zone.stroke_color.toLowerCase() : DEFAULT_OUTLINE_COLOR;

const withAlpha = (hex: string, alpha: number): string => {
  const full = hex.length === 4 ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}` : hex;
  const r = parseInt(full.slice(1, 3), 16);
  const g = parseInt(full.slice(3, 5), 16);
  const b = parseInt(full.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

/** Zones grouped by outline colour: a CSS drop-shadow only works on a whole <svg>, not on its paths */
const groupByColor = (list: ClickableZone[]): [string, ClickableZone[]][] => {
  const groups = new Map<string, ClickableZone[]>();
  for (const zone of list) {
    const color = outlineColor(zone);
    groups.set(color, [...(groups.get(color) ?? []), zone]);
  }
  return [...groups.entries()];
};

const ClickableZoneOverlay = ({ zones, onZoneClick, countries }: ClickableZoneOverlayProps) => {
  const [hoveredTargetKey, setHoveredTargetKey] = useState<string | null>(null);
  // Tap/click opens the target's card; navigation happens from the card
  const [selectedTargetKey, setSelectedTargetKey] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const measure = () => setBox({ width: node.clientWidth, height: node.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!selectedTargetKey) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedTargetKey(null);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selectedTargetKey]);

  const getTargetKey = (zone: ClickableZone) => `${zone.target_type}:${zone.target_id}`;

  const isHighlighted = (zone: ClickableZone) => {
    const key = getTargetKey(zone);
    return hoveredTargetKey === key || selectedTargetKey === key;
  };

  const selectedZones = selectedTargetKey ? zones.filter((z) => getTargetKey(z) === selectedTargetKey) : [];
  const selectedZone = selectedZones.find((z) => z.label) ?? selectedZones[0] ?? null;

  // Card anchor: average of the centres of all shapes of the selected target
  const cardAnchor = (() => {
    if (selectedZones.length === 0) return null;
    const centers = selectedZones.map((z) => getPolygonCenter(z.zone_data));
    const avg = centers.reduce((acc, c) => ({ x: acc.x + c.x, y: acc.y + c.y }), { x: 0, y: 0 });
    return { x: avg.x / centers.length, y: avg.y / centers.length };
  })();

  const preciseZones = zones.filter((z) => Boolean(z.precise_path));
  const hoveredPreciseZones = preciseZones.filter(isHighlighted);

  return (
    <div ref={containerRef} className="absolute inset-0">
      {/*
        Precise coastline outlines. The glow is a CSS drop-shadow on the <svg> box
        itself: it runs in screen space, so it does not stretch with the
        non-uniform 0..100 viewBox. Strokes use non-scaling-stroke for the same reason.
      */}
      {groupByColor(preciseZones).map(([color, group]) => (
        <svg
          key={`outline-${color}`}
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          style={{ filter: `drop-shadow(0 0 2px ${withAlpha(color, 0.75)}) drop-shadow(0 0 6px ${withAlpha(color, 0.35)})` }}
          aria-hidden
        >
          {group.map((zone) => (
            <path
              key={zone.id}
              d={zone.precise_path ?? undefined}
              fill="none"
              stroke={color}
              strokeWidth={1.5}
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              opacity={0.85}
            />
          ))}
        </svg>
      ))}

      {groupByColor(hoveredPreciseZones).map(([color, group]) => (
        <svg
          key={`hover-${color}`}
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          style={{ filter: `drop-shadow(0 0 4px ${withAlpha(color, 0.95)}) drop-shadow(0 0 12px ${withAlpha(color, 0.6)})` }}
          aria-hidden
        >
          {group.map((zone) => (
            <path
              key={zone.id}
              d={zone.precise_path ?? undefined}
              fill={withAlpha(color, 0.14)}
              stroke={color}
              strokeWidth={2.5}
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
      ))}

      {/* Interactive layer: rough polygons (drawn as before) and invisible hit areas for precise outlines */}
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        onClick={(e) => {
          // Tap on empty map area closes the card
          if (e.target === e.currentTarget) setSelectedTargetKey(null);
        }}
      >
        <defs>
          <filter id="zone-glow">
            <feGaussianBlur stdDeviation="0.4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {zones.map((zone) => {
          const hoverHandlers = {
            onMouseEnter: () => setHoveredTargetKey(getTargetKey(zone)),
            onMouseLeave: () => setHoveredTargetKey(null),
            onClick: () => setSelectedTargetKey(getTargetKey(zone)),
          };

          if (zone.precise_path) {
            // Hit area is the land shape only; the look comes from the layers above
            return (
              <path
                key={zone.id}
                d={zone.precise_path}
                className="cursor-pointer"
                fill="rgba(0, 0, 0, 0.001)"
                stroke="none"
                pointerEvents="all"
                {...hoverHandlers}
              />
            );
          }

          const pointsStr = zone.zone_data
            .map((p) => `${p.x},${p.y}`)
            .join(' ');
          const highlighted = isHighlighted(zone);

          return (
            <polygon
              key={zone.id}
              points={pointsStr}
              className="cursor-pointer"
              style={{
                transition: 'fill 0.3s ease, stroke 0.3s ease, stroke-width 0.3s ease',
              }}
              fill={highlighted ? 'rgba(240, 217, 92, 0.2)' : 'rgba(255, 255, 255, 0.05)'}
              stroke={highlighted ? '#f0d95c' : (zone.stroke_color ?? 'rgba(255, 249, 184, 0.3)')}
              strokeWidth={highlighted ? '0.5' : '0.3'}
              filter={highlighted ? 'url(#zone-glow)' : undefined}
              {...hoverHandlers}
            />
          );
        })}
      </svg>

      {/* Info card of the tapped target */}
      <AnimatePresence>
        {selectedZone && cardAnchor && box.width > 0 && (
          <MapZoneCard
            key={selectedTargetKey}
            anchor={cardAnchor}
            box={box}
            title={selectedZone.label ?? 'Без названия'}
            emblemUrl={
              selectedZone.target_type === 'country' && countries
                ? countries.find((c) => c.id === selectedZone.target_id)?.emblem_url ?? null
                : null
            }
            level={selectedZone.target_level ?? null}
            onGo={() => {
              setSelectedTargetKey(null);
              onZoneClick(selectedZone);
            }}
            onClose={() => setSelectedTargetKey(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
};

export default ClickableZoneOverlay;
