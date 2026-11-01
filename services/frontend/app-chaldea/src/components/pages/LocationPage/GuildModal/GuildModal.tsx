import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useDispatch } from 'react-redux';
import goldCoinsIcon from '../../../../assets/icons/gold-coins.svg';
import { getGuildView, postGuildHandIn } from '../../../../api/guild';
import { useCurrency } from '../../../../hooks/useCurrency';
import { fetchProfile } from '../../../../redux/slices/profileSlice';
import type { AppDispatch } from '../../../../redux/store';
import { useAppSelector } from '../../../../redux/store';
import type { GuildOffer, GuildView } from '../../../../types/economy';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import { bankErrorText, newRequestId, parseAmount } from '../BankModal/bankFormat';
import { GuildOrderRow, ItemThumb, guildClosedText, guildXpPreview } from './GuildParts';

interface GuildModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

/** Backend `GuildHandInIn.quantity` upper bound. */
const QUANTITY_MAX = 10_000;
const QUANTITY_DIGITS = 5;
const HTTP_CONFLICT = 409;
/** `MSG_DUPLICATE` of the backend — a repeated request, shown as info, not as an error. */
const DUPLICATE_TEXT = 'Операция уже выполнена';

const isDuplicate = (err: unknown): boolean =>
  axios.isAxiosError(err) &&
  err.response?.status === HTTP_CONFLICT &&
  err.response.data?.detail === DUPLICATE_TEXT;

/**
 * How many pieces the player may type: what is in the bag and the request cap. `max_accept` does NOT cap the input —
 * the guild takes as much as fits and the rest stays in the bag (partial acceptance, the server explains why).
 */
const maxPieces = (offer: GuildOffer): number => Math.max(0, Math.min(offer.have, QUANTITY_MAX));

/** FEAT-193 — «Гильдия торговцев» NPC: the region's open orders; hand in items of a wanted group for marks and XP. */
const GuildModal = ({ npcId, npcName, npcAvatar, onClose }: GuildModalProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;
  const { format } = useCurrency();

  const [view, setView] = useState<GuildView | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState('');
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  /** Server message of the last successful hand-in (kept in the modal; partial ones are highlighted). */
  const [result, setResult] = useState<{ text: string; partial: boolean } | null>(null);
  /** Guards double submits between the click and the re-render that disables the button. */
  const pendingRef = useRef(false);
  /** Idempotency key of the current request: kept for a retry of the same request, new after a success. */
  const requestIdRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!characterId) {
      setLoading(false);
      setLoadError('Нужен персонаж, чтобы сдавать товары гильдии');
      return;
    }
    setLoading(true);
    try {
      setView(await getGuildView(npcId, characterId));
      setLoadError(null);
    } catch (err) {
      const text = bankErrorText(err, 'Не удалось открыть гильдию торговцев');
      setLoadError(text);
      toast.error(text);
    } finally {
      setLoading(false);
    }
  }, [npcId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Keep the selection valid: the same item if it is still accepted, otherwise the first offer.
  useEffect(() => {
    if (!view) return;
    if (selectedId !== null && view.offers.some((o) => o.item_id === selectedId)) return;
    setSelectedId(view.offers[0]?.item_id ?? null);
  }, [view, selectedId]);

  const offers = view?.offers ?? [];
  const selected = offers.find((o) => o.item_id === selectedId) ?? null;
  const max = selected ? maxPieces(selected) : 0;
  const qty = Math.min(parseAmount(quantity), max);
  /** Pieces the guild takes now (order volume and the residents' money may cut the request). */
  const accepted = selected ? Math.min(qty, selected.max_accept) : 0;
  const marks = selected ? accepted * selected.unit_price : 0;
  const xpInfo = view?.xp ?? null;
  const xpOn = Boolean(xpInfo && xpInfo.daily_cap > 0);
  const xpGain = selected && xpInfo ? guildXpPreview(marks, selected.xp_rate, xpInfo) : 0;
  const lowerXpRate = Boolean(selected && xpInfo && selected.xp_rate < xpInfo.per_mark);
  const canHandIn = Boolean(view?.working && selected && accepted > 0 && !pending);
  const groupName = (code: string): string =>
    view?.orders.find((o) => o.group_code === code)?.group_name ?? code;

  const changeRequest = () => {
    requestIdRef.current = null;
    setActionError(null);
    setResult(null);
  };

  const selectOffer = (itemId: number) => {
    if (itemId === selectedId) return;
    setSelectedId(itemId);
    setQuantity('');
    changeRequest();
  };

  const changeQuantity = (raw: string) => {
    const digits = raw.replace(/[^\d]/g, '').slice(0, QUANTITY_DIGITS);
    const n = parseAmount(digits);
    setQuantity(n > max ? String(max) : digits);
    changeRequest();
  };

  const handIn = async () => {
    if (pendingRef.current || !characterId || !selected || qty <= 0) return;
    pendingRef.current = true;
    setPending(true);
    setActionError(null);
    if (!requestIdRef.current) requestIdRef.current = newRequestId();
    try {
      const res = await postGuildHandIn(npcId, {
        character_id: characterId,
        item_id: selected.item_id,
        quantity: qty,
        request_id: requestIdRef.current,
      });
      requestIdRef.current = null;
      setView(res.view);
      setQuantity('');
      setResult({ text: res.message, partial: res.partial });
      toast.success(res.message);
      // Wallet in the header and the character's XP / level follow the profile.
      dispatch(fetchProfile(characterId));
    } catch (err) {
      if (isDuplicate(err)) {
        requestIdRef.current = null;
        setQuantity('');
        toast(DUPLICATE_TEXT, { icon: 'ℹ️' });
        dispatch(fetchProfile(characterId));
      } else {
        const text = bankErrorText(err, 'Не удалось сдать товар гильдии');
        setActionError(text);
        toast.error(text);
      }
      // The bag, the order or the residents' money may have changed: show the fresh state.
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
          📜
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
          <p className="text-site-red text-sm">{loadError ?? 'Не удалось открыть гильдию торговцев'}</p>
          {characterId && (
            <button type="button" className="btn-line" onClick={() => void load()}>
              Повторить
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4 min-w-0">
          {/* Guild, region, wallet */}
          <div className="flex flex-wrap items-start gap-2">
            <div className="flex flex-col min-w-0 flex-1">
              <span className="text-white/50 text-xs uppercase tracking-wide">Гильдия торговцев</span>
              <span className="text-white text-sm sm:text-base font-medium break-words">
                {view.region_name ? `Регион «${view.region_name}»` : 'Регион'}
              </span>
              {view.working && view.markup_pct > 0 && (
                <span className="text-white/60 text-xs sm:text-sm mt-0.5">
                  Платит местную цену с надбавкой до +{view.markup_pct.toLocaleString('ru-RU')} %
                </span>
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
              <span className="text-gold font-medium">{guildClosedText(view.closed_reason)}.</span> Товары сейчас не
              принимают.
            </div>
          )}

          {/* Orders */}
          {view.working && (
            <section className="flex flex-col gap-2">
              <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Заказы</h3>
              {view.orders.length === 0 ? (
                <p className="text-white/50 text-sm">
                  Региону сейчас ничего не нужно. Заказы обновляются при пересчёте — загляните позже.
                </p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {view.orders.map((o) => (
                    <GuildOrderRow key={o.order_id} order={o} />
                  ))}
                </ul>
              )}
            </section>
          )}

          {/* What the player can hand in */}
          {view.working && view.orders.length > 0 && (
            <section className="flex flex-col gap-2">
              <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Что можно сдать</h3>
              {offers.length === 0 ? (
                <p className="text-white/50 text-sm">
                  В сумке нет подходящих предметов. Принимаются обычные стопки без заточки, камней и износа.
                </p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {offers.map((offer) => {
                    const active = offer.item_id === selectedId;
                    return (
                      <li key={offer.item_id}>
                        <button
                          type="button"
                          onClick={() => selectOffer(offer.item_id)}
                          disabled={pending}
                          aria-pressed={active}
                          className={`w-full flex items-center gap-3 rounded-card border px-3 py-2 text-left transition-colors duration-200 ease-site disabled:opacity-60 ${
                            active
                              ? 'border-gold/60 bg-gold/10'
                              : 'border-white/10 bg-white/[0.03] hover:border-white/30'
                          }`}
                        >
                          <ItemThumb image={offer.image} fallback="📦" />
                          <div className="flex flex-col min-w-0 flex-1">
                            <span className={`text-sm font-medium break-words ${active ? 'text-gold' : 'text-white'}`}>
                              {offer.name}
                            </span>
                            <span className="text-white/60 text-xs">
                              {format(offer.unit_price)} за шт. · {groupName(offer.group_code)}
                            </span>
                            {offer.capped_by_merchants && (
                              <span className="text-white/45 text-[11px]">цена ограничена ценами торговцев</span>
                            )}
                          </div>
                          <span className="text-xs shrink-0 text-right text-white/70">
                            в сумке:
                            <br />
                            <span className="text-white font-medium">{offer.have}</span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          )}

          {/* Quantity, preview and the hand-in button */}
          {view.working && selected && (
            <section className="flex flex-col gap-3 rounded-card border border-white/5 bg-white/[0.03] p-3">
              <div className="flex items-end gap-2 min-w-0">
                <label className="flex flex-col gap-0.5 min-w-0 flex-1">
                  <span className="text-white/50 text-[11px] uppercase tracking-wide">Количество, шт.</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={quantity}
                    disabled={pending || max === 0}
                    onChange={(e) => changeQuantity(e.target.value)}
                    placeholder="0"
                    className="input-underline !text-sm w-full min-w-0"
                  />
                </label>
                {max > 0 && (
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => changeQuantity(String(Math.min(max, Math.max(1, selected.max_accept))))}
                    className="shrink-0 text-[11px] uppercase tracking-wide text-gold/80 hover:text-gold disabled:opacity-40 pb-1"
                  >
                    Сколько примут ({Math.min(max, Math.max(1, selected.max_accept))})
                  </button>
                )}
              </div>

              {selected.max_accept === 0 && (
                <p className="text-white/50 text-xs">
                  Сейчас гильдия не может принять этот товар — у жителей не хватает денег. Загляните после пересчёта.
                </p>
              )}
              {selected.max_accept > 0 && qty > selected.max_accept && (
                <p className="text-gold/90 text-xs">
                  Гильдия примет до {selected.max_accept} шт., остальное останется у вас.
                </p>
              )}

              <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                <span className="text-white/70 text-sm">
                  Получите: <span className="text-gold font-medium">{format(marks)}</span>
                  {xpOn && xpGain > 0 && (
                    <>
                      {' '}
                      и <span className="text-site-blue font-medium">{xpGain.toLocaleString('ru-RU')} опыта</span>
                    </>
                  )}
                  {accepted > 0 && accepted < qty && (
                    <span className="text-white/50 text-xs"> (за {accepted} из {qty} шт.)</span>
                  )}
                </span>
                <button
                  type="button"
                  className="btn-blue w-full sm:w-auto sm:ml-auto !px-6"
                  disabled={!canHandIn}
                  onClick={() => void handIn()}
                >
                  {pending ? 'Сдаём...' : 'Сдать'}
                </button>
              </div>

              {xpOn && xpInfo && (
                <div className="flex flex-col gap-0.5 text-[11px] sm:text-xs text-white/50">
                  {xpInfo.left_today <= 0 ? (
                    <span>Опыт за сдачу в гильдию на сегодня исчерпан — марки начисляются как обычно.</span>
                  ) : (
                    <span>
                      Опыта от гильдии сегодня можно получить ещё {xpInfo.left_today.toLocaleString('ru-RU')}
                      {xpInfo.multiplier > 1 && ' (книга опыта увеличит его)'}.
                    </span>
                  )}
                  {lowerXpRate && <span>За товары, которые продают торговцы, опыта вдвое меньше.</span>}
                </div>
              )}

              {result && !actionError && (
                <p
                  className={`rounded-card border px-3 py-2 text-xs sm:text-sm ${
                    result.partial
                      ? 'border-gold/30 bg-gold/[0.06] text-white/80'
                      : 'border-stat-energy/30 bg-stat-energy/[0.06] text-white/80'
                  }`}
                >
                  {result.text}
                </p>
              )}
              {actionError && <p className="text-site-red text-xs sm:text-sm">{actionError}</p>}
            </section>
          )}

          {/* Result after the last offer of the bag was handed in (no selection left) */}
          {view.working && !selected && (result || actionError) && (
            <div className="flex flex-col gap-1">
              {result && !actionError && (
                <p
                  className={`rounded-card border px-3 py-2 text-xs sm:text-sm text-white/80 ${
                    result.partial ? 'border-gold/30 bg-gold/[0.06]' : 'border-stat-energy/30 bg-stat-energy/[0.06]'
                  }`}
                >
                  {result.text}
                </p>
              )}
              {actionError && <p className="text-site-red text-xs sm:text-sm">{actionError}</p>}
            </div>
          )}

          {/* Items of wanted groups the guild refuses */}
          {view.working && view.refused.length > 0 && (
            <section className="flex flex-col gap-2">
              <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Не принимается</h3>
              <ul className="flex flex-col gap-1.5">
                {view.refused.map((r) => (
                  <li
                    key={r.item_id}
                    className="flex items-start gap-3 rounded-card border border-white/5 bg-white/[0.02] px-3 py-2 min-w-0"
                  >
                    <ItemThumb image={r.image} fallback="📦" dim />
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="text-white/70 text-sm break-words">
                        {r.name} <span className="text-white/40 text-xs">× {r.have}</span>
                      </span>
                      <span className="text-white/50 text-xs break-words">{r.reason}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </ModalShell>
  );
};

export default GuildModal;
