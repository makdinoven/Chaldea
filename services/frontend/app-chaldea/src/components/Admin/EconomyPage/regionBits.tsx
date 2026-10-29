/** Small shared pieces of the «Регионы» tab (FEAT-182): 0–100 bars, hunger badge, price multiplier. */
import { formatDecimal } from './economyLabels';

/** Same thresholds as the player card: fed < 0.03 ≤ tight < 0.15 ≤ hunger. */
const HUNGER_TIGHT = 0.03;
const HUNGER_SEVERE = 0.15;
/** Same thresholds as the card's shortages / surpluses. */
const PRICE_SHORTAGE = 1.6;
const PRICE_SURPLUS = 0.7;

interface ScaleBarProps {
  /** 0..100 */
  value: number;
  tone: 'stability' | 'prosperity';
  label: string;
}

export const ScaleBar = ({ value, tone, label }: ScaleBarProps) => {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-2 min-w-[90px]" title={`${label}: ${formatDecimal(value, 1)}`}>
      <div className="h-1.5 flex-1 rounded-full bg-white/10 overflow-hidden" aria-hidden="true">
        <div
          className={`h-full rounded-full ${tone === 'stability' ? 'bg-stat-energy' : 'bg-gold'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-white/70 text-xs w-7 text-right shrink-0">{Math.round(value)}</span>
    </div>
  );
};

export const HungerBadge = ({ hunger, simulated }: { hunger: number; simulated: boolean }) => {
  if (!simulated) return <span className="text-white/30 text-xs">—</span>;
  if (hunger >= HUNGER_SEVERE) {
    return (
      <span className="inline-flex rounded-full border border-site-red/50 bg-site-red/10 px-2 py-0.5 text-site-red text-xs whitespace-nowrap">
        голод {Math.round(hunger * 100)}%
      </span>
    );
  }
  if (hunger >= HUNGER_TIGHT) {
    return (
      <span className="inline-flex rounded-full border border-gold/50 bg-gold/10 px-2 py-0.5 text-gold text-xs whitespace-nowrap">
        недоедают {Math.round(hunger * 100)}%
      </span>
    );
  }
  return (
    <span className="inline-flex rounded-full border border-stat-energy/40 bg-stat-energy/10 px-2 py-0.5 text-stat-energy text-xs whitespace-nowrap">
      сыты
    </span>
  );
};

export const priceMultClass = (mult: number): string => {
  if (mult >= PRICE_SHORTAGE) return 'text-site-red';
  if (mult <= PRICE_SURPLUS) return 'text-site-blue';
  return 'text-white';
};

export const PriceMult = ({ mult }: { mult: number }) => (
  <span className={priceMultClass(mult)}>×{formatDecimal(mult, 2)}</span>
);
