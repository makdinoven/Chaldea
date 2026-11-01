import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useDispatch } from 'react-redux';
import goldCoinsIcon from '../../../../assets/icons/gold-coins.svg';
import { getMintView, postMint } from '../../../../api/mint';
import { useCurrency } from '../../../../hooks/useCurrency';
import { fetchProfile } from '../../../../redux/slices/profileSlice';
import type { AppDispatch } from '../../../../redux/store';
import { useAppSelector } from '../../../../redux/store';
import type { MintView, MintViewItem } from '../../../../types/economy';
import { seasonText } from '../../../../utils/seasonPeriod';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import { bankErrorText, newRequestId, parseAmount } from '../BankModal/bankFormat';
import { MintLimitBar, mintClosedText } from './MintParts';

interface MintModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

/** Backend `MintIn.quantity` upper bound. */
const QUANTITY_MAX = 10_000;
const HTTP_CONFLICT = 409;
/** `MSG_DUPLICATE` of the backend — a repeated request, shown as info, not as an error. */
const DUPLICATE_TEXT = 'Операция уже выполнена';

const isDuplicate = (err: unknown): boolean =>
  axios.isAxiosError(err) &&
  err.response?.status === HTTP_CONFLICT &&
  err.response.data?.detail === DUPLICATE_TEXT;

/**
 * How many pieces the player may hand in: what is in the bag and the request cap. The season limit does NOT cap the
 * input — the mint accepts as much as fits and the rest of the ore stays in the bag (partial acceptance).
 */
const maxPieces = (item: MintViewItem): number => Math.max(0, Math.min(item.have, QUANTITY_MAX));

/** FEAT-191 — the country mint at a Монетчик NPC in the capital: hand in ore, get marks. */
const MintModal = ({ npcId, npcName, npcAvatar, onClose }: MintModalProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;
  const { format } = useCurrency();

  const [view, setView] = useState<MintView | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState('');
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  /** Server message of the last partial success (only part of the ore was accepted). */
  const [partialNote, setPartialNote] = useState<string | null>(null);
  /** Guards double submits between the click and the re-render that disables the button. */
  const pendingRef = useRef(false);
  /** Idempotency key of the current request: kept for a retry of the same request, new after a success. */
  const requestIdRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!characterId) {
      setLoading(false);
      setLoadError('Нужен персонаж, чтобы пользоваться монетным двором');
      return;
    }
    setLoading(true);
    try {
      setView(await getMintView(npcId, characterId));
      setLoadError(null);
    } catch (err) {
      const text = bankErrorText(err, 'Не удалось открыть монетный двор');
      setLoadError(text);
      toast.error(text);
    } finally {
      setLoading(false);
    }
  }, [npcId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Keep the selection valid: the first ore in the bag, or the first one at all.
  useEffect(() => {
    if (!view) return;
    if (selectedId !== null && view.items.some((i) => i.item_id === selectedId)) return;
    const first = view.items.find((i) => i.have > 0) ?? view.items[0];
    setSelectedId(first ? first.item_id : null);
  }, [view, selectedId]);

  const selected = view?.items.find((i) => i.item_id === selectedId) ?? null;
  const max = selected ? maxPieces(selected) : 0;
  const qty = Math.min(parseAmount(quantity), max);
  /** Pieces the mint will actually take now (the season limit may cut the request). */
  const accepted = selected ? Math.min(qty, selected.max_by_limit) : 0;
  const preview = selected ? accepted * selected.marks_per_item : 0;
  const canMint = Boolean(view?.working && selected && accepted > 0 && !pending);

  const changeRequest = () => {
    requestIdRef.current = null;
    setActionError(null);
    setPartialNote(null);
  };

  const selectItem = (itemId: number) => {
    if (itemId === selectedId) return;
    setSelectedId(itemId);
    setQuantity('');
    changeRequest();
  };

  const changeQuantity = (raw: string) => {
    const digits = raw.replace(/[^\d]/g, '').slice(0, 5);
    const n = parseAmount(digits);
    setQuantity(n > max ? String(max) : digits);
    changeRequest();
  };

  const mint = async () => {
    if (pendingRef.current || !characterId || !selected || qty <= 0) return;
    pendingRef.current = true;
    setPending(true);
    setActionError(null);
    if (!requestIdRef.current) requestIdRef.current = newRequestId();
    try {
      const res = await postMint(npcId, {
        character_id: characterId,
        item_id: selected.item_id,
        quantity: qty,
        request_id: requestIdRef.current,
      });
      requestIdRef.current = null;
      setView(res.view);
      setQuantity('');
      setPartialNote(res.partial ? res.message : null);
      toast.success(res.message);
      // The header balance follows the profile (userSlice matcher on fetchProfile).
      dispatch(fetchProfile(characterId));
    } catch (err) {
      if (isDuplicate(err)) {
        requestIdRef.current = null;
        setQuantity('');
        toast(DUPLICATE_TEXT, { icon: 'ℹ️' });
        dispatch(fetchProfile(characterId));
      } else {
        const text = bankErrorText(err, 'Не удалось отчеканить марки');
        setActionError(text);
        toast.error(text);
      }
      // The bag, the limit or the mint itself may have changed: show the fresh state.
      void load();
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  };

  const icon = (
    <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
      {npcAvatar ? (
        <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-lg" aria-hidden>
          ⚒️
        </div>
      )}
    </div>
  );

  return (
    <ModalShell open onClose={onClose} title={npcName} size="lg" icon={icon} dismissible={!pending}>
      {loading && !view ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : !view ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-site-red text-sm">{loadError ?? 'Не удалось открыть монетный двор'}</p>
          {characterId && (
            <button type="button" className="btn-line" onClick={() => void load()}>
              Повторить
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4 min-w-0">
          {/* Mint, season, wallet */}
          <div className="flex flex-wrap items-start gap-2">
            <div className="flex flex-col min-w-0 flex-1">
              <span className="text-white/50 text-xs uppercase tracking-wide">Монетный двор</span>
              <span className="text-white text-sm sm:text-base font-medium break-words">
                {view.country_name ?? 'Страна'}
                {view.region_name && <span className="text-white/60 font-normal"> · столица «{view.region_name}»</span>}
              </span>
              {view.period && (
                <span className="text-white/60 text-xs sm:text-sm mt-0.5">Сезон: {seasonText(view.period)}</span>
              )}
            </div>
            <div
              className="flex items-center gap-1.5 bg-black/30 rounded-card px-3 py-1.5 shrink-0"
              title="В кошельке"
            >
              <img src={goldCoinsIcon} alt="" className="w-5 h-5" />
              <span className="text-gold font-medium text-sm sm:text-base">{view.wallet.toLocaleString('ru-RU')}</span>
            </div>
          </div>

          {!view.working && (
            <div className="rounded-card border border-white/15 bg-white/[0.03] px-3 py-2 text-xs sm:text-sm text-white/70">
              <span className="text-gold font-medium">{mintClosedText(view.closed_reason)}.</span> Руду сейчас не
              принимают.
            </div>
          )}

          {/* Season limit */}
          {view.limit > 0 && (
            <section className="flex flex-col gap-2">
              <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Лимит сезона</h3>
              <MintLimitBar
                limit={view.limit}
                court={view.minted_court}
                players={view.minted_players}
                remaining={view.remaining}
                format={(n) => format(n)}
              />
              <p className="text-white/50 text-[11px] sm:text-xs">
                Лимит общий для страны: двор чеканит из запасов столицы, игроки — из своей руды.
              </p>
            </section>
          )}

          {/* Accepted ore */}
          <section className="flex flex-col gap-2">
            <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Принимаемая руда</h3>
            {view.items.length === 0 ? (
              <p className="text-white/50 text-sm">Монетный двор пока не принимает руду.</p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {view.items.map((item) => {
                  const active = item.item_id === selectedId;
                  return (
                    <li key={item.item_id}>
                      <button
                        type="button"
                        onClick={() => selectItem(item.item_id)}
                        disabled={pending}
                        aria-pressed={active}
                        className={`w-full flex items-center gap-3 rounded-card border px-3 py-2 text-left transition-colors duration-200 ease-site disabled:opacity-60 ${
                          active
                            ? 'border-gold/60 bg-gold/10'
                            : 'border-white/10 bg-white/[0.03] hover:border-white/30'
                        }`}
                      >
                        <div className="w-10 h-10 rounded bg-black/40 overflow-hidden shrink-0 flex items-center justify-center">
                          {item.image ? (
                            <img src={item.image} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <span className="text-lg" aria-hidden>
                              ⛏️
                            </span>
                          )}
                        </div>
                        <div className="flex flex-col min-w-0 flex-1">
                          <span className={`text-sm font-medium break-words ${active ? 'text-gold' : 'text-white'}`}>
                            {item.name}
                          </span>
                          <span className="text-white/60 text-xs">{format(item.marks_per_item)} за шт.</span>
                        </div>
                        <span
                          className={`text-xs shrink-0 text-right ${item.have > 0 ? 'text-white/70' : 'text-white/35'}`}
                        >
                          в сумке:
                          <br />
                          <span className={item.have > 0 ? 'text-white font-medium' : ''}>{item.have}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* Quantity and the mint button */}
          {selected && (
            <section className="flex flex-col gap-3 rounded-card border border-white/5 bg-white/[0.03] p-3">
              <div className="flex items-end gap-2 min-w-0">
                <label className="flex flex-col gap-0.5 min-w-0 flex-1">
                  <span className="text-white/50 text-[11px] uppercase tracking-wide">Количество, шт.</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={quantity}
                    disabled={pending || !view.working || max === 0}
                    onChange={(e) => changeQuantity(e.target.value)}
                    placeholder="0"
                    className="input-underline !text-sm w-full min-w-0"
                  />
                </label>
                {max > 0 && view.working && (
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => changeQuantity(String(max))}
                    className="shrink-0 text-[11px] uppercase tracking-wide text-gold/80 hover:text-gold disabled:opacity-40 pb-1"
                  >
                    Всё ({max})
                  </button>
                )}
              </div>

              {view.working && selected.have === 0 && (
                <p className="text-white/50 text-xs">Этой руды нет в сумке (принимаются только обычные стопки).</p>
              )}
              {view.working && selected.have > 0 && selected.max_by_limit === 0 && (
                <p className="text-white/50 text-xs">Лимит сезона исчерпан — двор больше не принимает эту руду.</p>
              )}
              {view.working && selected.max_by_limit > 0 && qty > selected.max_by_limit && (
                <p className="text-gold/90 text-xs">
                  Двор примет только {selected.max_by_limit} шт. — лимит сезона, остальная руда останется у вас.
                </p>
              )}
              {view.working &&
                selected.max_by_limit > 0 &&
                selected.max_by_limit < selected.have &&
                qty <= selected.max_by_limit && (
                  <p className="text-white/50 text-xs">
                    До конца сезона двор примет не больше {selected.max_by_limit} шт. этой руды.
                  </p>
                )}

              <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                <span className="text-white/70 text-sm">
                  Получите: <span className="text-gold font-medium">{format(preview)}</span>
                  {accepted > 0 && accepted < qty && (
                    <span className="text-white/50 text-xs"> (за {accepted} из {qty} шт.)</span>
                  )}
                </span>
                <button
                  type="button"
                  className="btn-blue w-full sm:w-auto sm:ml-auto !px-6"
                  disabled={!canMint}
                  onClick={() => void mint()}
                >
                  {pending ? 'Чеканим...' : 'Отчеканить'}
                </button>
              </div>

              {partialNote && !actionError && (
                <p className="rounded-card border border-gold/30 bg-gold/[0.06] px-3 py-2 text-white/80 text-xs sm:text-sm">
                  {partialNote}
                </p>
              )}
              {actionError && <p className="text-site-red text-xs sm:text-sm">{actionError}</p>}
            </section>
          )}
        </div>
      )}
    </ModalShell>
  );
};

export default MintModal;
