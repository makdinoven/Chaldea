import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchRegionEconomyCard } from '../../api/regionEconomy';
import type { RegionCardData, RegionGroupLevel, RegionGroupTrend } from '../../api/regionEconomy';
import { apiErrorMessage } from '../../api/errors';

/**
 * Player-facing "how is the region doing" card (FEAT-182, F4).
 * Words (phrases) + per-group price arrows; never any money numbers.
 * Renders nothing for regions outside the simulation (`participating=false`).
 */

interface RegionEconomyCardProps {
  regionId: number;
}

const ERROR_TEXT = 'Не удалось загрузить состояние региона';

/** States that deserve an alert tone in the phrase line. */
const ALERT_STATES = new Set(['hunger', 'riot', 'unrest', 'debt']);
const WARN_STATES = new Set(['tight', 'uneasy', 'low', 'very_high']);

const LEVEL_TEXT: Record<RegionGroupLevel, string> = {
  very_low: 'очень дёшево',
  low: 'дёшево',
  normal: 'обычно',
  high: 'дорого',
  very_high: 'очень дорого',
};

const LEVEL_CLASS: Record<RegionGroupLevel, string> = {
  very_low: 'text-site-blue',
  low: 'text-site-blue/80',
  normal: 'text-white/40',
  high: 'text-gold/80',
  very_high: 'text-gold',
};

const TREND_META: Record<RegionGroupTrend, { glyph: string; title: string; className: string }> = {
  up: { glyph: '▲', title: 'Цены растут', className: 'text-gold' },
  down: { glyph: '▼', title: 'Цены падают', className: 'text-site-blue' },
  flat: { glyph: '—', title: 'Цены без изменений', className: 'text-white/40' },
};

const phraseTone = (phrase: string, card: RegionCardData): string => {
  const states = [card.food, card.stability, card.treasury, card.price_level];
  const match = states.find((s) => s.label === phrase);
  if (match && ALERT_STATES.has(match.state)) return 'text-site-red';
  if (match && WARN_STATES.has(match.state)) return 'text-gold';
  if (phrase.startsWith('Нехватка')) return 'text-gold';
  if (phrase.startsWith('Избыток')) return 'text-site-blue';
  return 'text-white/80';
};

const RegionEconomyCard = ({ regionId }: RegionEconomyCardProps) => {
  const [card, setCard] = useState<RegionCardData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setCard(null);
    setFailed(false);
    fetchRegionEconomyCard(regionId)
      .then((data) => {
        if (cancelled) return;
        setCard(data.participating ? data : null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setFailed(true);
        toast.error(apiErrorMessage(e, ERROR_TEXT), { id: 'region-economy-card' });
      });
    return () => {
      cancelled = true;
    };
  }, [regionId]);

  if (failed) {
    return <p className="text-site-red/80 text-xs text-center mb-3">{ERROR_TEXT}</p>;
  }
  if (!card) return null;

  return (
    <section
      aria-label="Состояние региона"
      className="mx-auto mb-4 w-full max-w-3xl px-1 sm:px-0"
    >
      <ul className="flex flex-wrap justify-center gap-x-3 gap-y-1 text-sm">
        {card.phrases.map((phrase, i) => (
          <li key={`${i}-${phrase}`} className="flex items-center gap-3">
            {i > 0 && <span className="text-gold/40" aria-hidden="true">·</span>}
            <span className={phraseTone(phrase, card)}>{phrase}</span>
          </li>
        ))}
      </ul>

      {card.groups.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gold/15">
          <p className="gold-text text-xs uppercase tracking-wider text-center mb-2">Цены на товары</p>
          <ul className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1">
            {card.groups.map((group) => {
              const trend = TREND_META[group.trend] ?? TREND_META.flat;
              const level = LEVEL_TEXT[group.level] ?? LEVEL_TEXT.normal;
              const levelClass = LEVEL_CLASS[group.level] ?? LEVEL_CLASS.normal;
              return (
                <li
                  key={group.code}
                  className="flex items-center justify-between gap-2 text-xs min-w-0"
                  title={`${group.name}: ${level}, ${trend.title.toLowerCase()}`}
                >
                  <span className="text-white/75 min-w-0 leading-tight break-words">{group.name}</span>
                  <span className="flex items-center gap-1.5 shrink-0">
                    <span className={levelClass}>{level}</span>
                    <span className={`${trend.className} text-[10px] w-3 text-center`} aria-label={trend.title}>
                      {trend.glyph}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
};

export default RegionEconomyCard;
