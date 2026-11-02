/** Small shared pieces of the «Регионы» tab (FEAT-182): 0–100 bars, hunger badge, price multiplier, bank badge,
 * FEAT-194 class mix cell and money-vs-norm badge. */
import { formatDecimal } from './economyLabels';
import EventIcon from '../../common/EventIcon';
import type { EconClassKey, EconClassMix, EconEventBadge, EconRegionItem } from '../../../types/economy';
import { ClassMixBar } from '../../WorldPage/RegionClassBar';

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

/** «Банк» marker of a region with an enabled bank (FEAT-184). */
export const BankBadge = ({ className = '' }: { className?: string }) => (
  <span
    title="В регионе есть банк"
    className={`inline-flex rounded-full border border-gold/40 bg-gold/10 px-2 py-0.5 text-gold text-[10px] uppercase tracking-[0.06em] whitespace-nowrap ${className}`}
  >
    Банк
  </span>
);

/** Small icons of the region's active events (FEAT-187, `EconRegionItem.active_events`); name in the tooltip. */
export const EventBadges = ({ events, className = '' }: { events?: EconEventBadge[]; className?: string }) => {
  if (!events || events.length === 0) return null;
  return (
    <span className={`inline-flex flex-wrap items-center gap-1 ${className}`}>
      {events.map((ev, i) => (
        <span
          key={`${i}-${ev.name}`}
          title={`Событие: ${ev.name}`}
          className={`inline-flex items-center justify-center rounded-full border w-5 h-5 ${
            ev.kind === 'good' ? 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy' : 'border-site-red/40 bg-site-red/10 text-site-red'
          }`}
        >
          <EventIcon name={ev.icon} size={12} title={ev.name} />
        </span>
      ))}
    </span>
  );
};

/* ------------------------------------------------------------------ FEAT-194 social classes */

/** Short class names for tight cells: Б / З / Бг. */
export const CLASS_SHORT: Record<EconClassKey, string> = { poor: 'Б', middling: 'З', rich: 'Бг' };
export const CLASS_LABELS: Record<EconClassKey, string> = { poor: 'Бедные', middling: 'Зажиточные', rich: 'Богатые' };
export const CLASS_ORDER: EconClassKey[] = ['poor', 'middling', 'rich'];

const PERCENT = 100;
/** Money vs norm: below this share of the norm the region reads «ниже нормы» (gold), above the upper — «излишек». */
const NORM_LOW = 0.95;
const NORM_HIGH = 1.05;

/** 0.3512 → «35,1». */
export const sharePct = (share: number, digits = 1): string => formatDecimal(share * PERCENT, digits);

/** Signed shift in percentage points: −0.00015 → «−0,015». */
export const signedPp = (delta: number): string => {
  const pp = delta * PERCENT;
  const sign = pp > 0 ? '+' : pp < 0 ? '−' : '';
  return `${sign}${formatDecimal(Math.abs(pp), 3)}`;
};

/** The region's shares, or null when it has no classes. */
export const regionMix = (r: {
  class_poor?: number | null;
  class_middling?: number | null;
  class_rich?: number | null;
}): EconClassMix | null =>
  r.class_poor == null || r.class_middling == null || r.class_rich == null
    ? null
    : { poor: r.class_poor, middling: r.class_middling, rich: r.class_rich };

/** Mini bar + «Б 35 · З 45 · Бг 20 %» + the last recount shift (admin «Регионы»). */
export const ClassMixCell = ({ region }: { region: EconRegionItem }) => {
  const mix = regionMix(region);
  if (!mix) return <span className="text-white/30 text-xs">—</span>;
  const dpoor = region.class_dpoor ?? 0;
  const drich = region.class_drich ?? 0;
  const moved = dpoor !== 0 || drich !== 0;
  return (
    <span className="flex flex-col gap-1 min-w-[110px]">
      <ClassMixBar
        poor={mix.poor}
        middling={mix.middling}
        rich={mix.rich}
        heightClass="h-1.5"
        title={`Бедные ${sharePct(mix.poor)} %, зажиточные ${sharePct(mix.middling)} %, богатые ${sharePct(mix.rich)} %`}
      />
      <span className="text-white/70 text-xs whitespace-nowrap">
        {CLASS_ORDER.map((k) => `${CLASS_SHORT[k]} ${sharePct(mix[k], 0)}`).join(' · ')} %
      </span>
      {moved && (
        <span className="text-white/40 text-[11px] whitespace-nowrap" title="Сдвиг долей за последний пересчёт, п. п.">
          сдвиг: Б {signedPp(dpoor)} · Бг {signedPp(drich)} п. п.
        </span>
      )}
    </span>
  );
};

/** «82 % нормы» — residents' money vs the wealth norm (gold below, blue above). */
export const MoneyVsNorm = ({ ratio, className = '' }: { ratio?: number | null; className?: string }) => {
  if (ratio == null || !Number.isFinite(ratio)) return null;
  const tone = ratio < NORM_LOW ? 'text-gold' : ratio > NORM_HIGH ? 'text-site-blue' : 'text-white/60';
  return (
    <span className={`${tone} text-[11px] whitespace-nowrap ${className}`} title="Деньги жителей относительно нормы богатства">
      {formatDecimal(ratio * PERCENT, 0)} % нормы
    </span>
  );
};
