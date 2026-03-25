import { isPerkActive } from '../../../types/perks';
import type { CharacterPerk } from '../../../types/perks';

interface PerkNodeProps {
  perk: CharacterPerk;
  x: number;
  y: number;
  categoryColor: string;
  onSelect: (perk: CharacterPerk) => void;
}

/** Hexagon size (distance from center to vertex) */
const HEX_SIZE = 22;

/** Generate hexagon points string centered at (cx, cy) */
function hexPoints(cx: number, cy: number, size: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 2;
    pts.push(`${cx + size * Math.cos(angle)},${cy + size * Math.sin(angle)}`);
  }
  return pts.join(' ');
}

/** Elder Futhark runes */
const RUNES = [
  'ᚨ', 'ᚠ', 'ᚢ', 'ᚦ', 'ᚱ', 'ᚲ', 'ᚷ', 'ᚹ',
  'ᚺ', 'ᚾ', 'ᛁ', 'ᛃ', 'ᛇ', 'ᛈ', 'ᛉ', 'ᛊ',
  'ᛏ', 'ᛒ', 'ᛖ', 'ᛗ', 'ᛚ', 'ᛜ', 'ᛞ', 'ᛟ',
];

const RARITY_GLOW = {
  common: 0.4,
  rare: 0.6,
  legendary: 0.8,
} as const;

const RARITY_ACCENT: Record<string, string> = {
  common: '',
  rare: 'rgba(168,85,247,0.35)',
  legendary: 'rgba(240,217,92,0.4)',
};

const PerkNode = ({ perk, x, y, categoryColor, onSelect }: PerkNodeProps) => {
  const active = isPerkActive(perk);
  const isLegendaryLocked = perk.rarity === 'legendary' && !active;

  const rune = RUNES[(perk.id ?? 0) % RUNES.length];

  // Progress 0..1 for inactive perks
  let progressPct = 0;
  if (!active && perk.conditions.length > 0) {
    const progs = perk.conditions.map((c) => {
      const key = c.stat ?? c.type;
      const entry = perk.progress?.[key];
      if (!entry) return 0;
      return Math.min(1, entry.current / entry.required);
    });
    progressPct = progs.reduce((a, b) => a + b, 0) / progs.length;
  }

  const glowMul = RARITY_GLOW[perk.rarity] ?? RARITY_GLOW.common;
  const accent = RARITY_ACCENT[perk.rarity] ?? '';
  const filterId = `perk-glow-${perk.id}`;
  const clipId = `perk-fill-${perk.id}`;
  const glowColor = accent || categoryColor;

  const borderColor = active
    ? categoryColor
    : 'rgba(255,255,255,0.12)';
  const fillColor = active
    ? categoryColor.replace(/[\d.]+\)$/, '0.15)')
    : 'rgba(255,255,255,0.03)';

  // Rune colors: dim base + bright fill clipped by progress
  const runeDim = 'rgba(255,255,255,0.12)';
  const runeBright = active
    ? 'rgba(255,255,255,0.9)'
    : categoryColor.replace(/[\d.]+\)$/, '0.7)');

  // Progress fill rect: from bottom to top (y goes down in SVG)
  // Clip covers the lower progressPct portion of the rune area
  const runeArea = HEX_SIZE * 1.2; // approximate rune bounding box
  const fillTop = y - runeArea / 2 + runeArea * (1 - progressPct);

  const runeSymbol = isLegendaryLocked ? '?' : rune;
  const runeFontSize = isLegendaryLocked ? 14 : 16;

  return (
    <g
      className="cursor-pointer"
      onClick={() => onSelect(perk)}
    >
      {/* Glow filter for active perks */}
      {active && (
        <defs>
          <filter id={filterId} x="-80%" y="-80%" width="260%" height="260%">
            <feDropShadow
              dx="0" dy="0"
              stdDeviation={5 * glowMul}
              floodColor={glowColor}
              floodOpacity={glowMul}
            />
          </filter>
        </defs>
      )}

      {/* Clip path for progress fill (inactive only) */}
      {!active && progressPct > 0 && (
        <defs>
          <clipPath id={clipId}>
            <rect
              x={x - runeArea}
              y={fillTop}
              width={runeArea * 2}
              height={runeArea}
            />
          </clipPath>
        </defs>
      )}

      {/* Main hexagon */}
      <polygon
        points={hexPoints(x, y, HEX_SIZE)}
        fill={fillColor}
        stroke={borderColor}
        strokeWidth={active ? 2.5 : 1.5}
        filter={active ? `url(#${filterId})` : undefined}
        opacity={active ? 1 : 0.5}
      />

      {/* Inner decorative hexagon (active only) */}
      {active && (
        <polygon
          points={hexPoints(x, y, HEX_SIZE * 0.65)}
          fill="none"
          stroke={borderColor}
          strokeWidth={0.8}
          opacity={0.25}
        />
      )}

      {/* Rune: dim base layer (always visible) */}
      <text
        x={x}
        y={y + 1}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={runeFontSize}
        fontWeight="bold"
        fill={active ? runeBright : runeDim}
        className="pointer-events-none select-none"
        style={active ? {
          textShadow: `0 0 8px ${glowColor}, 0 0 16px ${glowColor}40`,
        } : undefined}
      >
        {runeSymbol}
      </text>

      {/* Rune: bright fill layer clipped by progress (inactive + has progress) */}
      {!active && progressPct > 0 && (
        <text
          x={x}
          y={y + 1}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={runeFontSize}
          fontWeight="bold"
          fill={runeBright}
          clipPath={`url(#${clipId})`}
          className="pointer-events-none select-none"
          style={{ textShadow: `0 0 6px ${glowColor}` }}
        >
          {runeSymbol}
        </text>
      )}

      {/* Invisible larger hit area */}
      <circle
        cx={x}
        cy={y}
        r={HEX_SIZE + 8}
        fill="transparent"
      />
    </g>
  );
};

export { HEX_SIZE };
export default PerkNode;
