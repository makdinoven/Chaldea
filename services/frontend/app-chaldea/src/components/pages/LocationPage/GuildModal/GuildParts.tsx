import type { GuildOrder, GuildXpInfo } from '../../../../types/economy';

/** FEAT-193 — small pieces and maths of the player «Гильдия торговцев» modal (no state). */

const PERCENT = 100;
/** Guards `floor` against binary fractions such as 0.29 × 100 = 28.999…; the server counts in Decimal. */
const FLOOR_EPSILON = 1e-9;

/** «Гильдия не принимает заказы: регион не участвует в экономике» — the backend may send a reason or a sentence. */
export const guildClosedText = (reason: string | null | undefined): string => {
  const r = (reason ?? '').trim();
  if (!r) return 'Гильдия не принимает заказы';
  if (r.toLowerCase().startsWith('гильдия')) return r;
  return `Гильдия не принимает заказы: ${r}`;
};

/**
 * XP the player gets for `marks` paid at `rate` — the server formula of 3.6a:
 * `floor(min(floor(marks × rate), left_today) × multiplier)`; the daily cap counts XP before the book.
 */
export const guildXpPreview = (marks: number, rate: number, xp: GuildXpInfo): number => {
  if (marks <= 0 || rate <= 0 || xp.daily_cap <= 0) return 0;
  const base = Math.floor(marks * rate + FLOOR_EPSILON);
  const capped = Math.max(0, Math.min(base, xp.left_today));
  return Math.floor(capped * (xp.multiplier > 0 ? xp.multiplier : 1) + FLOOR_EPSILON);
};

/** One order: group, progress bar «выполнено N %», badge when the residents cannot pay until the next recount. */
export const GuildOrderRow = ({ order }: { order: GuildOrder }) => {
  const pct = Math.min(PERCENT, Math.max(0, Math.round(order.filled_pct)));
  return (
    <li className="flex flex-col gap-1.5 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2 min-w-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0">
        <span className="text-white text-sm font-medium break-words">{order.group_name}</span>
        {order.is_food && (
          <span className="rounded-full border border-stat-energy/40 bg-stat-energy/10 px-2 py-px text-[10px] text-stat-energy whitespace-nowrap">
            продовольствие
          </span>
        )}
        {!order.payable && (
          <span className="rounded-full border border-gold/40 bg-gold/10 px-2 py-px text-[10px] text-gold whitespace-nowrap">
            жителям нечем платить до пересчёта
          </span>
        )}
        <span className="text-white/60 text-xs sm:ml-auto whitespace-nowrap">выполнено {pct} %</span>
      </div>
      <div
        className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={PERCENT}
        aria-valuenow={pct}
        aria-label={`${order.group_name}: выполнено ${pct} %`}
      >
        <div className={`h-full ${order.payable ? 'bg-gold/80' : 'bg-white/30'}`} style={{ width: `${pct}%` }} />
      </div>
    </li>
  );
};

interface ItemThumbProps {
  image: string | null;
  fallback: string;
  dim?: boolean;
}

/** Square item picture with an emoji fallback. */
export const ItemThumb = ({ image, fallback, dim = false }: ItemThumbProps) => (
  <div
    className={`w-10 h-10 rounded bg-black/40 overflow-hidden shrink-0 flex items-center justify-center ${dim ? 'opacity-60' : ''}`}
  >
    {image ? (
      <img src={image} alt="" className="w-full h-full object-cover" />
    ) : (
      <span className="text-lg" aria-hidden>
        {fallback}
      </span>
    )}
  </div>
);
