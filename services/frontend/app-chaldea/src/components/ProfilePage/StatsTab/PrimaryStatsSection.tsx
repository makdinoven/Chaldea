import { useCallback, useEffect, useState } from 'react';
import { CharacterAttributes } from '../../../redux/slices/profileSlice';
import { MAIN_STATS, STAT_LABELS } from '../constants';
import { STAT_CAP_NOTE, STAT_CAP_SHORT } from '../../../utils/statCaps';
import { getStealth, type StealthInfo } from '../../../api/shadow';
import { apiErrorMessage } from '../../../api/errors';

interface PrimaryStatsSectionProps {
  attributes: CharacterAttributes;
  /**
   * The viewer's own character (the profile page only ever shows it). When set,
   * the «Скрытность» row gets its effect line from `GET /characters/{id}/stealth`
   * — a private endpoint, so it must never be passed for someone else's character.
   */
  ownCharacterId?: number;
}

const formatPct = (value: number): string =>
  value.toLocaleString('ru-RU', { maximumFractionDigits: 1 });

/** FEAT-201: «−X % к шансу быть замеченным» under the stealth row (owner only). */
const StealthEffectLine = ({ characterId, stealth }: { characterId: number; stealth: number }) => {
  const [info, setInfo] = useState<StealthInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setInfo(await getStealth(characterId));
    } catch (err) {
      setError(apiErrorMessage(err, 'Не удалось загрузить влияние скрытности'));
    }
  }, [characterId]);

  // Refetch whenever the stored total changes (points, gear, food, perks).
  useEffect(() => {
    load();
  }, [load, stealth]);

  if (error) {
    return (
      <p className="text-site-red text-xs leading-snug">
        {error}{' '}
        <button
          type="button"
          onClick={load}
          className="site-link text-xs underline underline-offset-2"
        >
          Повторить
        </button>
      </p>
    );
  }
  if (!info) return null;

  const tooltip =
    `Шанс заметить преступление = база места × (1 − снижение) × слава × размер группы. ` +
    `${formatPct(info.pct_per_point)} % за эффективное очко скрытности, предел — ` +
    `${formatPct(info.max_reduction_pct)} %. Убывающая отдача: ${STAT_CAP_SHORT}. ` +
    `В бою скрытность не действует.`;

  return (
    <p className="text-white/50 text-xs leading-snug break-words" title={tooltip}>
      −{formatPct(info.reduction_pct)} % к шансу быть замеченным
      {info.subclass_bonus > 0 && (
        <span className="text-white/40">
          {' '}(вкл. +{info.subclass_bonus} от подкласса
          {info.subclass_name ? ` «${info.subclass_name}»` : ''})
        </span>
      )}
    </p>
  );
};

const TieredBar = ({ value }: { value: number }) => {
  const greenWidth = Math.min(value, 100);
  const redWidth = Math.min(Math.max(value - 100, 0), 100);
  const blackWidth = Math.min(Math.max(value - 200, 0), 100);

  return (
    <div className="relative h-2 w-full rounded-full bg-white/10 overflow-hidden">
      {/* Green layer: 0-100 */}
      <div
        className="absolute inset-y-0 left-0 rounded-full transition-all duration-300"
        style={{
          width: `${greenWidth}%`,
          background: '#4ade80',
        }}
      />
      {/* Red layer: 100-200 */}
      <div
        className="absolute inset-y-0 left-0 rounded-full transition-all duration-300"
        style={{
          width: `${redWidth}%`,
          background: '#ef4444',
        }}
      />
      {/* Black layer: 200+ */}
      <div
        className="absolute inset-y-0 left-0 rounded-full transition-all duration-300"
        style={{
          width: `${blackWidth}%`,
          background: '#1a1a2e',
        }}
      />
    </div>
  );
};

const PrimaryStatsSection = ({ attributes, ownCharacterId }: PrimaryStatsSectionProps) => {
  return (
    <div>
      {/* FEAT-149: section title row with a fading gold rule (per mock) */}
      <div className="flex items-center gap-3 mb-3.5">
        <h3 className="gold-text text-xs font-medium uppercase tracking-[0.14em] shrink-0">
          Характеристики
        </h3>
        <span
          className="flex-1 h-px bg-gradient-to-r from-gold/40 to-transparent"
          aria-hidden="true"
        />
      </div>
      <div className="flex flex-col gap-3">
        {MAIN_STATS.map((stat) => {
          const value = attributes[stat] ?? 0;
          return (
            // FEAT-195: the bar's green/red/dark tiers are the cap thresholds.
            <div key={stat} className="flex flex-col gap-1" title={STAT_CAP_NOTE}>
              <div className="flex justify-between items-center">
                <span className="text-white text-sm font-medium">
                  {STAT_LABELS[stat]}
                </span>
                <span className="text-white/70 text-sm font-mono">
                  {value}
                </span>
              </div>
              <TieredBar value={value} />
              {stat === 'stealth' && ownCharacterId != null && (
                <StealthEffectLine characterId={ownCharacterId} stealth={value} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PrimaryStatsSection;
