// FEAT-207 — «Предметы» tab of the faction donation dialog: eligible plain stacks with quantity steppers →
// value + points preview (shared daily cap with marks) → confirmation → one request with a client request_id.
// A hook returning the body and the footer, so the dialog keeps one ModalShell for both tabs.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { Minus, Package, Plus } from 'lucide-react';
import {
  FACTION_ITEM_DONATION_LINES_MAX,
  FACTION_ITEM_DONATION_QTY_MAX,
  donateItemsToFaction,
  donationPointsPreview,
  fetchFactionItemDonation,
  secondsToDate,
  type FactionItemDonationOptions,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { newRequestId } from '../../../api/reputationAdmin';
import { useCurrency } from '../../../hooks/useCurrency';
import RemainingText from '../../CommonComponents/RemainingText';
import LoadingState from '../shared/LoadingState';

/** Backend duplicate text — the same request again: info, not an error. */
const DUPLICATE_TEXT = 'Это пожертвование уже выполнено';
const isDuplicate = (err: unknown): boolean =>
  axios.isAxiosError(err) && err.response?.status === 409 && err.response.data?.detail === DUPLICATE_TEXT;

const fmt = (n: number) => n.toLocaleString('ru-RU');

const pointsWord = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'очко';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'очка';
  return 'очков';
};

interface UseItemDonationArgs {
  /** The tab is visible (loads on first show). */
  active: boolean;
  characterId: number;
  factionId: number | null;
  factionName: string;
  onDone: () => void;
  onClose: () => void;
}

export const useItemDonation = ({ active, characterId, factionId, factionName, onDone, onClose }: UseItemDonationArgs) => {
  const { format } = useCurrency();
  const [options, setOptions] = useState<FactionItemDonationOptions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [qty, setQty] = useState<Record<number, number>>({});
  const [step, setStep] = useState<'select' | 'confirm'>('select');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingRef = useRef(false);
  /** One key per confirmed selection: a retry after a lost answer re-sends the same key. */
  const requestIdRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (factionId == null) return;
    setLoadError(null);
    try {
      setOptions(await fetchFactionItemDonation(characterId, factionId));
    } catch (e) {
      setLoadError(apiErrorMessage(e, 'Не удалось загрузить предметы для пожертвования'));
    }
  }, [characterId, factionId]);

  // A new faction (dialog reopened) starts clean.
  useEffect(() => {
    setOptions(null);
    setQty({});
    setStep('select');
    setError(null);
    setLoadError(null);
    requestIdRef.current = null;
  }, [factionId]);

  useEffect(() => {
    if (active && !options && !loadError) void load();
  }, [active, options, loadError, load]);

  const chosen = useMemo(
    () => (options?.items ?? []).filter((i) => (qty[i.item_id] ?? 0) > 0).map((i) => ({ item: i, n: qty[i.item_id] })),
    [options, qty],
  );
  const value = chosen.reduce((sum, c) => sum + c.item.unit_value * c.n, 0);
  const pieces = chosen.reduce((sum, c) => sum + c.n, 0);
  const gain = options ? donationPointsPreview(options, value) : 0;
  const capLeft = options ? Math.max(0, options.daily_cap - options.points_today) : 0;
  const capReached = options ? options.daily_cap === 0 || capLeft === 0 : true;
  const resetAt = useMemo(() => secondsToDate(options?.resets_in_seconds), [options?.resets_in_seconds]);

  const setItemQty = (itemId: number, max: number, n: number) => {
    const limit = Math.min(max, FACTION_ITEM_DONATION_QTY_MAX);
    const next = Math.max(0, Math.min(limit, Number.isFinite(n) ? Math.floor(n) : 0));
    setQty((prev) => {
      const lines = Object.entries(prev).filter(([id, v]) => v > 0 && Number(id) !== itemId).length;
      if (next > 0 && !(prev[itemId] > 0) && lines >= FACTION_ITEM_DONATION_LINES_MAX) {
        toast.error(`За раз — не больше ${FACTION_ITEM_DONATION_LINES_MAX} разных предметов`);
        return prev;
      }
      return { ...prev, [itemId]: next };
    });
  };

  const next = () => {
    if (chosen.length === 0) {
      setError('Выберите хотя бы один предмет');
      return;
    }
    setError(null);
    requestIdRef.current = null;
    setStep('confirm');
  };

  const finish = () => {
    onDone();
    onClose();
  };

  const submit = async () => {
    if (factionId == null || chosen.length === 0 || pendingRef.current) return;
    pendingRef.current = true;
    setBusy(true);
    setError(null);
    if (!requestIdRef.current) requestIdRef.current = newRequestId();
    try {
      const res = await donateItemsToFaction(
        characterId,
        factionId,
        chosen.map((c) => ({ item_id: c.item.item_id, quantity: c.n })),
        requestIdRef.current,
      );
      requestIdRef.current = null;
      toast.success(
        res.points_delta > 0
          ? `Пожертвовано предметов: ${fmt(res.items_given)} на ${format(res.value_total)}: +${res.points_delta} ${pointsWord(res.points_delta)}`
          : `Пожертвовано предметов: ${fmt(res.items_given)} на ${format(res.value_total)}`,
      );
      if (res.rank_ups > 0) toast.success('Новое звание во фракции!');
      finish();
    } catch (err) {
      if (isDuplicate(err)) {
        requestIdRef.current = null;
        toast(DUPLICATE_TEXT, { icon: 'ℹ️' });
        finish();
      } else {
        // The same key stays for a retry (a lost answer is not given twice).
        setError(apiErrorMessage(err, 'Не удалось пожертвовать предметы'));
        // The bag may have changed (not enough items): refresh the list, keep the choice.
        if (axios.isAxiosError(err) && err.response?.status === 400) void load();
      }
    } finally {
      pendingRef.current = false;
      setBusy(false);
    }
  };

  let body: ReactNode;
  if (loadError) {
    body = (
      <div className="flex flex-col gap-2 text-sm">
        <p className="text-site-red text-xs break-words">{loadError}</p>
        <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3 self-start" onClick={() => void load()}>
          Повторить
        </button>
      </div>
    );
  } else if (!options) {
    body = <LoadingState />;
  } else if (!options.enabled) {
    body = (
      <p className="text-sm text-white/70 break-words">
        Фракция сейчас не принимает предметы{options.reason ? `: ${options.reason}` : '.'}
      </p>
    );
  } else {
    body = (
      <div className="flex flex-col gap-3 text-sm text-white/85">
        <p>
          Предметы уйдут на склад фракции <span className="text-gold">«{factionName}»</span> и не вернутся: в пересчёт
          фракция продаст их на рынок края штаба.
        </p>

        {step === 'select' ? (
          options.items.length === 0 ? (
            <p className="text-white/55 text-xs">
              В сумке нет подходящих предметов. Принимаются обычные (не улучшенные и не повреждённые) предметы, которые
              продаются на рынке края штаба; экипировка и квестовые предметы — нет.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5 max-h-[320px] overflow-y-auto gold-scrollbar pr-1">
              {options.items.map((i) => {
                const n = qty[i.item_id] ?? 0;
                const max = Math.min(i.quantity, FACTION_ITEM_DONATION_QTY_MAX);
                return (
                  <li key={i.item_id} className="flex items-center gap-2 bg-white/[0.03] rounded-card p-2 min-w-0">
                    <span className="w-9 h-9 shrink-0 rounded-[8px] overflow-hidden bg-black/40 flex items-center justify-center">
                      {i.image ? (
                        <img src={i.image} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <Package size={16} className="text-white/30" />
                      )}
                    </span>
                    <span className="flex-1 min-w-0 flex flex-col">
                      <span className="text-white text-xs sm:text-sm truncate">{i.name}</span>
                      <span className="text-white/45 text-[11px]">
                        {format(i.unit_value)} за шт. · в сумке {fmt(i.quantity)}
                      </span>
                    </span>
                    <span className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => setItemQty(i.item_id, max, n - 1)}
                        disabled={n <= 0}
                        className="w-8 h-8 flex items-center justify-center rounded-full text-white/70 hover:text-gold disabled:opacity-30"
                        aria-label="Меньше"
                      >
                        <Minus size={14} />
                      </button>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={n}
                        onChange={(e) => setItemQty(i.item_id, max, Number(e.target.value.replace(/[^\d]/g, '') || 0))}
                        className="input-underline !text-sm w-11 text-center"
                        aria-label={`Количество: ${i.name}`}
                      />
                      <button
                        type="button"
                        onClick={() => setItemQty(i.item_id, max, n + 1)}
                        disabled={n >= max}
                        className="w-8 h-8 flex items-center justify-center rounded-full text-white/70 hover:text-gold disabled:opacity-30"
                        aria-label="Больше"
                      >
                        <Plus size={14} />
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          )
        ) : (
          <div className="flex flex-col gap-1">
            <p className="text-white">Пожертвовать:</p>
            <ul className="flex flex-col gap-0.5 text-xs text-white/75">
              {chosen.map((c) => (
                <li key={c.item.item_id} className="break-words">
                  {c.item.name} × {fmt(c.n)} — {format(c.item.unit_value * c.n)}
                </li>
              ))}
            </ul>
          </div>
        )}

        <ul className="flex flex-col gap-1.5 text-xs text-white/70">
          {pieces > 0 && (
            <li className="text-white">
              Выбрано: {fmt(pieces)} шт. на <span className="gold-text font-medium font-mono tabular-nums">{format(value)}</span>
            </li>
          )}
          <li>
            Курс: {format(options.marks_per_point)} = 1 очко фракции
            {options.daily_cap > 0 ? `, общий лимит с марками — ${fmt(options.daily_cap)} очков в сутки` : ''}.
          </li>
          {options.daily_cap > 0 && (
            <li>
              Сегодня получено очков: {fmt(options.points_today)} из {fmt(options.daily_cap)}.
            </li>
          )}
          {pieces > 0 && (
            <li className={gain > 0 ? 'text-stat-energy' : 'text-white/70'}>
              {gain > 0
                ? `Это пожертвование даст +${fmt(gain)} ${pointsWord(gain)}.`
                : capReached
                  ? 'Очков за сегодня больше не будет — предметы уйдут как чистое пожертвование.'
                  : 'Пока без очков: до следующего очка не хватает ценности (остаток засчитается сегодня).'}
            </li>
          )}
          {capReached && options.daily_cap > 0 && resetAt && (
            <li>
              Лимит обновится — <RemainingText until={resetAt} prefix="осталось" doneText="лимит уже обновился" />
            </li>
          )}
        </ul>

        {error && <p className="text-site-red text-xs break-words">{error}</p>}
      </div>
    );
  }

  const ready = !!options && options.enabled;
  const footer: ReactNode =
    step === 'select' || !ready ? (
      <>
        <button type="button" className="btn-line w-full sm:w-auto" onClick={onClose}>
          {ready ? 'Отмена' : 'Закрыть'}
        </button>
        {ready && (
          <button
            type="button"
            className="btn-blue w-full sm:w-auto disabled:opacity-50"
            onClick={next}
            disabled={chosen.length === 0}
          >
            Далее
          </button>
        )}
      </>
    ) : (
      <>
        <button
          type="button"
          className="btn-line w-full sm:w-auto"
          onClick={() => {
            requestIdRef.current = null;
            setError(null);
            setStep('select');
          }}
          disabled={busy}
        >
          Назад
        </button>
        <button type="button" className="btn-blue w-full sm:w-auto disabled:opacity-50" onClick={() => void submit()} disabled={busy}>
          {busy ? <LoadingState size="xs" /> : 'Пожертвовать'}
        </button>
      </>
    );

  return { body, footer, busy };
};
