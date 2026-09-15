import { useLayoutEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { Compass, X } from 'lucide-react';
import type { TargetLevel } from '../../../redux/actions/worldMapActions';

interface MapZoneCardProps {
  /** Anchor on the zone, in percent of the map box */
  anchor: { x: number; y: number };
  /** Map box size in px, used to keep the card inside it */
  box: { width: number; height: number };
  title: string;
  emblemUrl: string | null;
  level: TargetLevel | null;
  onGo: () => void;
  onClose: () => void;
}

/** Below this map width the card is compact and docks to the top/bottom edge */
const COMPACT_BOX_WIDTH = 560;
/** Horizontal gap between the zone anchor and the card (wide layout) */
const CARD_GAP = 44;
const EDGE_PADDING = 8;
const RING_RADIUS = 5;

export const formatLevelRange = (level: TargetLevel | null): string | null => {
  if (!level || (level.min == null && level.max == null)) return null;
  const min = level.min ?? level.max;
  const max = level.max ?? level.min;
  return min === max ? `${min}` : `${min} – ${max}`;
};

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), Math.max(min, max));

/**
 * Parchment info card for a map zone (country / region), with a callout line
 * to the zone. Positioned inside the map box: beside the anchor on wide maps,
 * docked to the top or bottom edge on narrow ones.
 */
const MapZoneCard = ({ anchor, box, title, emblemUrl, level, onGo, onClose }: MapZoneCardProps) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardSize, setCardSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const node = cardRef.current;
    if (!node) return;
    const measure = () => setCardSize({ width: node.offsetWidth, height: node.offsetHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const compact = box.width < COMPACT_BOX_WIDTH;
  const ax = (anchor.x / 100) * box.width;
  const ay = (anchor.y / 100) * box.height;
  const { width: cw, height: ch } = cardSize;

  let left: number;
  let top: number;
  if (compact) {
    // Dock to the edge away from the zone so the card does not cover it
    left = clamp(ax - cw / 2, EDGE_PADDING, box.width - cw - EDGE_PADDING);
    top = ay > box.height / 2 ? EDGE_PADDING : box.height - ch - EDGE_PADDING;
  } else {
    const fitsRight = ax + CARD_GAP + cw + EDGE_PADDING <= box.width;
    left = fitsRight ? ax + CARD_GAP : ax - CARD_GAP - cw;
    left = clamp(left, EDGE_PADDING, box.width - cw - EDGE_PADDING);
    top = clamp(ay - ch / 2 - 24, EDGE_PADDING, box.height - ch - EDGE_PADDING);
  }

  // Callout ends at the point of the card rectangle closest to the anchor
  const lineEnd = {
    x: clamp(ax, left, left + cw),
    y: clamp(ay, top, top + ch),
  };
  const measured = cw > 0 && ch > 0;
  const levelText = formatLevelRange(level);

  return (
    <>
      {measured && (
        <svg className="absolute inset-0 w-full h-full pointer-events-none z-20" aria-hidden>
          <line
            x1={ax}
            y1={ay}
            x2={lineEnd.x}
            y2={lineEnd.y}
            stroke="#f5e6c8"
            strokeWidth={1.5}
            style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.6))' }}
          />
          <circle cx={ax} cy={ay} r={RING_RADIUS} fill="rgba(26,26,46,0.55)" stroke="#f5e6c8" strokeWidth={1.5} />
        </svg>
      )}

      <motion.div
        ref={cardRef}
        role="dialog"
        aria-label={title}
        initial={{ opacity: 0, scale: 0.94 }}
        animate={{ opacity: measured ? 1 : 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.94 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        onClick={(e) => e.stopPropagation()}
        className={`map-zone-card book-page absolute z-30 ${compact ? 'w-[190px] p-2.5' : 'w-[250px] p-3.5'}`}
        style={{ left, top }}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute top-1.5 right-1.5 text-ink-muted hover:text-ink transition-colors"
        >
          <X size={compact ? 14 : 16} />
        </button>

        <div className="flex items-center gap-2.5 pr-4">
          <div
            className={`shrink-0 rounded-full border border-[#8a6a3a]/60 bg-parchment-dark/60 flex items-center justify-center overflow-hidden ${
              compact ? 'w-8 h-8' : 'w-11 h-11'
            }`}
          >
            {emblemUrl ? (
              <img src={emblemUrl} alt="" className="w-full h-full object-cover" />
            ) : (
              <Compass size={compact ? 18 : 24} className="text-[#7a4a22]" strokeWidth={1.6} />
            )}
          </div>
          <h3 className={`lore-heading min-w-0 break-words ${compact ? 'text-base' : 'text-xl'}`}>{title}</h3>
        </div>

        {levelText && (
          <div className={`flex flex-col items-center ${compact ? 'mt-1.5' : 'mt-2.5'}`}>
            <span className={`text-ink-muted uppercase tracking-[0.08em] ${compact ? 'text-[9px]' : 'text-[11px]'}`}>
              Рекомендуемый уровень
            </span>
            <span className={`map-zone-card-ribbon mt-1 ${compact ? 'text-sm px-4' : 'text-base px-6'}`}>
              {levelText}
            </span>
          </div>
        )}

        <button
          type="button"
          onClick={onGo}
          className={`w-full mt-2.5 rounded-card border border-[#7a4a22]/50 text-[#5a3414] font-medium hover:bg-[#7a4a22]/10 transition-colors ${
            compact ? 'py-1 text-xs' : 'py-1.5 text-sm'
          }`}
        >
          Перейти
        </button>
      </motion.div>
    </>
  );
};

export default MapZoneCard;
