import { useEffect, useRef, useState } from 'react';
import { Hourglass, Utensils } from 'lucide-react';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchAttributes,
  fetchRestStatus,
  selectRestStatus,
  selectRestStatusError,
} from '../../../redux/slices/profileSlice';
import type { RestBusyReason } from '../../../redux/slices/profileSlice';
import { RARITY_TEXT_COLORS } from '../../../constants/items';
import { PERCENTAGE_STATS, STAT_LABELS } from '../constants';

/** Local countdown tick for the satiety timer */
const TICK_MS = 30_000;
/** Periodic refetch so resource values stay current on a long-open page */
const REFRESH_MS = 5 * 60_000;

const BUSY_REASON_LABELS: Record<RestBusyReason, string> = {
  battle: 'в бою',
  dungeon: 'в подземелье',
  gathering: 'на сборе ресурсов',
};

/** "23 ч 15 мин" with minute granularity; "<1 мин" for the tail */
export const formatHoursMinutes = (totalSeconds: number): string => {
  if (totalSeconds <= 0) return '0 мин';
  if (totalSeconds < 60) return '<1 мин';
  const totalMinutes = Math.floor(totalSeconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes} мин`;
  return `${hours} ч ${minutes} мин`;
};

const formatPercent = (value: number): string =>
  Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');

const formatModifier = (key: string, value: number): string => {
  const sign = value > 0 ? '+' : '';
  const suffix = PERCENTAGE_STATS.has(key) ? '%' : '';
  const shown = Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
  return `${sign}${shown}${suffix}`;
};

const RestStatusPanel = () => {
  const dispatch = useAppDispatch();
  const characterId = useAppSelector((state) => state.user.character?.id ?? null);
  const restStatus = useAppSelector(selectRestStatus);
  const restError = useAppSelector(selectRestStatusError);

  // Wall-clock moment the current restStatus snapshot was received
  const [receivedAt, setReceivedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  /** expires_at of the satiety whose expiry already triggered a refetch */
  const expiryHandledRef = useRef<string | null>(null);

  useEffect(() => {
    setReceivedAt(Date.now());
    setNow(Date.now());
  }, [restStatus]);

  const refresh = () => {
    if (!characterId) return;
    dispatch(fetchRestStatus(characterId));
    dispatch(fetchAttributes(characterId));
  };

  // 30 s ticker for the satiety countdown
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  // Refetch every 5 minutes while mounted
  useEffect(() => {
    if (!characterId) return undefined;
    const id = window.setInterval(() => {
      dispatch(fetchRestStatus(characterId));
      dispatch(fetchAttributes(characterId));
    }, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [dispatch, characterId]);

  const satiety = restStatus?.satiety ?? null;
  const remaining = satiety
    ? Math.max(0, satiety.remaining_seconds - Math.floor((now - receivedAt) / 1000))
    : 0;

  // Satiety ran out — reload so the bonus disappears and stats are recomputed
  useEffect(() => {
    // Once per satiety: avoids a refetch loop if the server still reports it
    if (satiety && remaining <= 0 && expiryHandledRef.current !== satiety.expires_at) {
      expiryHandledRef.current = satiety.expires_at;
      refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [satiety, remaining]);

  if (!restStatus) {
    if (restError) {
      return <p className="text-site-red text-xs">{restError}</p>;
    }
    return null;
  }

  const modifiers = Object.entries(satiety?.modifiers ?? {}).filter(([, v]) => v !== 0);

  return (
    <div className="flex flex-col gap-2 w-full min-w-0 text-sm">
      <div className="flex items-start gap-2 text-white">
        <Hourglass size={14} className="mt-0.5 shrink-0 text-gold" aria-hidden="true" />
        <div className="flex flex-col min-w-0">
          <span>
            Восстановление:{' '}
            <span className="gold-text font-medium">
              {formatPercent(restStatus.regen_percent_per_hour)}% в час
            </span>
          </span>
          {!restStatus.is_resting && (
            <span className="text-white/60 text-xs">
              Приостановлено
              {restStatus.busy_reason ? `: ${BUSY_REASON_LABELS[restStatus.busy_reason]}` : ''}
            </span>
          )}
        </div>
      </div>

      {satiety && (
        <div className="flex flex-col gap-1 rounded-card bg-white/[0.05] px-3 py-2 min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5">
            <span className="flex items-center gap-1.5 gold-text text-xs font-medium uppercase tracking-[0.06em]">
              <Utensils size={12} className="text-gold" aria-hidden="true" />
              Сытость
            </span>
            <span className="text-white/70 text-xs">
              {remaining > 0 ? `осталось ${formatHoursMinutes(remaining)}` : 'заканчивается…'}
            </span>
          </div>
          {satiety.source_item_name && (
            <span
              className={`text-sm font-medium break-words ${RARITY_TEXT_COLORS[satiety.rarity] ?? 'text-white'}`}
            >
              {satiety.source_item_name}
            </span>
          )}
          <span className="text-white text-xs">
            +{formatPercent(satiety.regen_bonus_percent)}% к восстановлению
          </span>
          {modifiers.length > 0 && (
            <ul className="flex flex-col gap-0.5 text-xs">
              {modifiers.map(([key, value]) => (
                <li key={key} className="flex justify-between gap-2">
                  <span className="text-white/70 break-words">{STAT_LABELS[key] ?? key}</span>
                  <span className={value > 0 ? 'text-site-blue shrink-0' : 'text-site-red shrink-0'}>
                    {formatModifier(key, value)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {restError && <p className="text-site-red text-xs">{restError}</p>}
    </div>
  );
};

export default RestStatusPanel;
