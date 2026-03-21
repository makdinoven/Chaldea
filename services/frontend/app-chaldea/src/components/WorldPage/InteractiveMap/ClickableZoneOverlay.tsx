import { useState } from 'react';
import { AnimatePresence } from 'motion/react';
import type { ClickableZone } from '../../../redux/actions/worldMapActions';
import MapInfoTooltip from './MapInfoTooltip';

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

const ClickableZoneOverlay = ({ zones, onZoneClick, countries }: ClickableZoneOverlayProps) => {
  const [hoveredTargetKey, setHoveredTargetKey] = useState<string | null>(null);

  const getTargetKey = (zone: ClickableZone) => `${zone.target_type}:${zone.target_id}`;

  const isHighlighted = (zone: ClickableZone) => hoveredTargetKey === getTargetKey(zone);

  // Find the first hovered zone for tooltip display
  const hoveredZone = hoveredTargetKey ? zones.find((z) => getTargetKey(z) === hoveredTargetKey) : null;

  // Compute tooltip center from ALL polygons of the hovered target (average of all centers)
  const tooltipCenter = (() => {
    if (!hoveredTargetKey) return null;
    const relatedZones = zones.filter((z) => getTargetKey(z) === hoveredTargetKey);
    if (relatedZones.length === 0) return null;
    const centers = relatedZones.map((z) => getPolygonCenter(z.zone_data));
    const avg = centers.reduce((acc, c) => ({ x: acc.x + c.x, y: acc.y + c.y }), { x: 0, y: 0 });
    return { x: avg.x / centers.length, y: avg.y / centers.length };
  })();

  return (
    <div className="absolute inset-0">
      {/* SVG polygon overlay */}
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
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
              onMouseEnter={() => setHoveredTargetKey(getTargetKey(zone))}
              onMouseLeave={() => setHoveredTargetKey(null)}
              onClick={() => onZoneClick(zone)}
            />
          );
        })}
      </svg>

      {/* Tooltip */}
      <AnimatePresence>
        {hoveredZone && hoveredZone.label && tooltipCenter && (
          <MapInfoTooltip
            label={hoveredZone.label}
            x={tooltipCenter.x}
            y={tooltipCenter.y}
            emblemUrl={
              hoveredZone.target_type === 'country' && countries
                ? countries.find((c) => c.id === hoveredZone.target_id)?.emblem_url ?? null
                : null
            }
          />
        )}
      </AnimatePresence>
    </div>
  );
};

export default ClickableZoneOverlay;
