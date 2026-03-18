import { useState } from 'react';
import { AnimatePresence } from 'motion/react';
import type { ClickableZone } from '../../../redux/actions/worldMapActions';
import MapInfoTooltip from './MapInfoTooltip';

interface ClickableZoneOverlayProps {
  zones: ClickableZone[];
  onZoneClick: (zone: ClickableZone) => void;
}

const getPolygonCenter = (points: { x: number; y: number }[]): { x: number; y: number } => {
  if (points.length === 0) return { x: 50, y: 50 };
  const sum = points.reduce(
    (acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }),
    { x: 0, y: 0 },
  );
  return { x: sum.x / points.length, y: sum.y / points.length };
};

const ClickableZoneOverlay = ({ zones, onZoneClick }: ClickableZoneOverlayProps) => {
  const [hoveredZoneId, setHoveredZoneId] = useState<number | null>(null);

  const hoveredZone = zones.find((z) => z.id === hoveredZoneId);
  const tooltipCenter = hoveredZone ? getPolygonCenter(hoveredZone.zone_data) : null;

  return (
    <div className="absolute inset-0">
      {/* SVG polygon overlay */}
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        {zones.map((zone) => {
          const pointsStr = zone.zone_data
            .map((p) => `${p.x},${p.y}`)
            .join(' ');

          return (
            <polygon
              key={zone.id}
              points={pointsStr}
              className="cursor-pointer transition-all duration-200 ease-site"
              fill={hoveredZoneId === zone.id ? 'rgba(118, 166, 189, 0.25)' : 'rgba(255, 255, 255, 0.05)'}
              stroke={hoveredZoneId === zone.id ? '#76a6bd' : 'rgba(255, 249, 184, 0.3)'}
              strokeWidth="0.3"
              onMouseEnter={() => setHoveredZoneId(zone.id)}
              onMouseLeave={() => setHoveredZoneId(null)}
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
          />
        )}
      </AnimatePresence>
    </div>
  );
};

export default ClickableZoneOverlay;
