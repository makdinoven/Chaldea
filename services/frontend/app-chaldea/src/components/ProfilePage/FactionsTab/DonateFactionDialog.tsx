// FEAT-206 — «Пожертвовать» into a faction treasury: amount → preview (points today, daily cap) →
// confirmation → one request with a client request_id (a double click becomes a duplicate, not a second charge).
import { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useDispatch } from 'react-redux';
import { HandCoins } from 'lucide-react';
import {
  FACTION_DONATION_MAX,
  donateToFaction,
  donationPointsPreview,
  secondsToDate,
  type FactionMembership,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { newRequestId } from '../../../api/reputationAdmin';
import { useCurrency } from '../../../hooks/useCurrency';
import { fetchProfile } from '../../../redux/slices/profileSlice';
import type { AppDispatch } from '../../../redux/store';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import RemainingText from '../../CommonComponents/RemainingText';
import LoadingState from '../shared/LoadingState';
import { useItemDonation } from './useItemDonation';

interface DonateFactionDialogProps {
  characterId: number;
  membership: FactionMembership | null;
  onClose: () => void;
  onDone: () => void;
}

const fmt = (n: number) => n.toLocaleString('ru-RU');
/** Backend `MSG_DONATION_DONE` — the same request again: info, not an error. */
const DUPLICATE_TEXT = 'Это пожертвование уже выполнено';
const isDuplicate = (err: unknown): boolean =>
  axios.isAxiosError(err) && err.response?.status === 409 && err.response.data?.detail === DUPLICATE_TEXT;

const pointsWord = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'очко';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'очка';
  return 'очков';
};

const DonateFactionDialog = ({ characterId, membership, onClose, onDone }: DonateFactionDialogProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const [raw, setRaw] = useState('');
  const [step, setStep] = useState<'input' | 'confirm'>('input');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingRef = useRef(false);
  /** One key per confirmed amount: a retry after a network error re-sends the same key (no double charge). */
  const requestIdRef = useRef<string | null>(null);
  const { format } = useCurrency();

  const info = membership?.donation ?? null;
  const open = membership !== null;

  // FEAT-207: «Марки» / «Предметы». Items are offered only while the faction economy ticks.
  const marksEnabled = !!info?.enabled;
  const itemsEnabled = !!info?.items_enabled;
  const [tab, setTab] = useState<'marks' | 'items'>('marks');
  const items = useItemDonation({
    active: open && tab === 'items',
    characterId,
    // null while closed: the next opening starts with a fresh list.
    factionId: open ? membership.faction.id : null,
    factionName: membership?.faction.name ?? '',
    onDone,
    onClose,
  });

  useEffect(() => {
    if (open) {
      setRaw('');
      setStep('input');
      setError(null);
      requestIdRef.current = null;
      setTab(!marksEnabled && itemsEnabled ? 'items' : 'marks');
    }
  }, [open, membership?.membership_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const resetAt = useMemo(() => secondsToDate(info?.resets_in_seconds), [info?.resets_in_seconds]);

  const amount = /^\d+$/.test(raw.trim()) ? Number(raw.trim()) : NaN;
  const amountValid = Number.isInteger(amount) && amount >= 1 && amount <= FACTION_DONATION_MAX;
  const gain = info && amountValid ? donationPointsPreview(info, amount) : 0;
  const capLeft = info ? Math.max(0, info.daily_cap - info.points_today) : 0;
  const capReached = info ? info.daily_cap === 0 || capLeft === 0 : true;

  const next = () => {
    if (!amountValid) {
      setError(`Введите сумму от 1 до ${format(FACTION_DONATION_MAX)}`);
      return;
    }
    setError(null);
    requestIdRef.current = null;
    setStep('confirm');
  };

  const submit = async () => {
    if (!membership || !amountValid || pendingRef.current) return;
    pendingRef.current = true;
    setBusy(true);
    setError(null);
    if (!requestIdRef.current) requestIdRef.current = newRequestId();
    try {
      const res = await donateToFaction(characterId, membership.faction.id, amount, requestIdRef.current);
      requestIdRef.current = null;
      toast.success(
        res.points_delta > 0
          ? `Пожертвовано ${format(amount)}: +${res.points_delta} ${pointsWord(res.points_delta)}`
          : `Пожертвовано ${format(amount)}`,
      );
      if (res.rank_ups > 0) toast.success('Новое звание во фракции!');
      dispatch(fetchProfile(characterId));
      onDone();
      onClose();
    } catch (err) {
      if (isDuplicate(err)) {
        requestIdRef.current = null;
        toast(DUPLICATE_TEXT, { icon: 'ℹ️' });
        dispatch(fetchProfile(characterId));
        onDone();
        onClose();
      } else {
        // The same key stays for «Пожертвовать» again (a lost answer is not charged twice).
        setError(apiErrorMessage(err, 'Не удалось пожертвовать марки'));
      }
    } finally {
      pendingRef.current = false;
      setBusy(false);
    }
  };

  return (
    <ModalShell
      open={open}
      onClose={onClose}
      title="Пожертвование фракции"
      icon={<HandCoins size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      size="sm"
      dismissible={!busy && !items.busy}
      footer={
        tab === 'items' ? (
          items.footer
        ) : !marksEnabled ? (
          <button type="button" className="btn-line w-full sm:w-auto" onClick={onClose}>
            Закрыть
          </button>
        ) : step === 'input' ? (
          <>
            <button type="button" className="btn-line w-full sm:w-auto" onClick={onClose}>
              Отмена
            </button>
            <button
              type="button"
              className="btn-blue w-full sm:w-auto disabled:opacity-50"
              onClick={next}
              disabled={!raw.trim()}
            >
              Далее
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="btn-line w-full sm:w-auto"
              onClick={() => {
                requestIdRef.current = null;
                setError(null);
                setStep('input');
              }}
              disabled={busy}
            >
              Назад
            </button>
            <button
              type="button"
              className="btn-blue w-full sm:w-auto disabled:opacity-50"
              onClick={() => void submit()}
              disabled={busy}
            >
              {busy ? <LoadingState size="xs" /> : 'Пожертвовать'}
            </button>
          </>
        )
      }
    >
      {membership && info && (
        <div className="flex flex-col gap-1.5 mb-4">
          <div className="flex gap-1 border-b border-white/10" role="tablist">
            {(
              [
                { key: 'marks', label: 'Марки', disabled: false },
                { key: 'items', label: 'Предметы', disabled: !itemsEnabled },
              ] as const
            ).map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                disabled={t.disabled || busy || items.busy}
                onClick={() => {
                  setError(null);
                  setTab(t.key);
                }}
                className={`flex-1 sm:flex-none px-4 py-2 -mb-px border-b-2 text-sm uppercase tracking-[0.06em] transition-colors duration-200 ease-site disabled:opacity-40 disabled:cursor-not-allowed ${
                  tab === t.key ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {!itemsEnabled && info.items_disabled_reason && (
            <p className="text-white/45 text-[11px] break-words">Предметы сейчас не принимаются: {info.items_disabled_reason}</p>
          )}
        </div>
      )}
      {membership && info && tab === 'items' && items.body}
      {membership && info && tab === 'marks' && !marksEnabled && (
        <p className="text-sm text-white/70">Пожертвование марками сейчас недоступно.</p>
      )}
      {membership && info && tab === 'marks' && marksEnabled && (
        <div className="flex flex-col gap-3 text-sm text-white/85">
          <p>
            Марки уйдут в казну фракции <span className="text-gold">«{membership.faction.name}»</span> и не вернутся.
          </p>

          {step === 'input' ? (
            <label className="flex flex-col gap-1">
              <span className="text-white/60 text-xs">Сумма, марок</span>
              <input
                type="text"
                inputMode="numeric"
                autoFocus
                value={raw}
                onChange={(e) => setRaw(e.target.value.replace(/[^\d]/g, '').slice(0, 7))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') next();
                }}
                className="input-underline w-full text-base"
                placeholder="например, 100"
              />
            </label>
          ) : (
            <p className="text-white">
              Пожертвовать <span className="gold-text font-medium font-mono tabular-nums">{format(amount)}</span>?
            </p>
          )}

          <ul className="flex flex-col gap-1.5 text-xs text-white/70">
            <li>
              Курс: {format(info.marks_per_point)} = 1 очко фракции
              {info.daily_cap > 0 ? `, не больше ${fmt(info.daily_cap)} очков в сутки` : ''}.
            </li>
            {info.daily_cap > 0 && (
              <li>
                Сегодня получено очков: {fmt(info.points_today)} из {fmt(info.daily_cap)}
                {info.marks_today > 0 ? ` (пожертвовано ${format(info.marks_today)})` : ''}.
              </li>
            )}
            {amountValid && (
              <li className={gain > 0 ? 'text-stat-energy' : 'text-white/70'}>
                {gain > 0
                  ? `Это пожертвование даст +${fmt(gain)} ${pointsWord(gain)}.`
                  : capReached
                    ? 'Очков за сегодня больше не будет — марки уйдут как чистое пожертвование.'
                    : `Пока без очков: до следующего очка не хватает марок (остаток засчитается сегодня).`}
              </li>
            )}
            {capReached && info.daily_cap > 0 && resetAt && (
              <li>
                Лимит обновится — <RemainingText until={resetAt} prefix="осталось" doneText="лимит уже обновился" />
              </li>
            )}
          </ul>

          {error && <p className="text-site-red text-xs break-words">{error}</p>}
        </div>
      )}
    </ModalShell>
  );
};

export default DonateFactionDialog;
