import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useDispatch } from 'react-redux';
import { apiErrorMessage } from '../../../../api/errors';
import { fetchFenceOffers, sellToFence } from '../../../../api/fence';
import { useCurrency } from '../../../../hooks/useCurrency';
import { fetchInventory, fetchProfile } from '../../../../redux/slices/profileSlice';
import type { AppDispatch } from '../../../../redux/store';
import { useAppSelector } from '../../../../redux/store';
import type { FenceOffer } from '../../../../types/caravans';
import { getClientPrefs } from '../../../../utils/clientPrefs';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import ConfirmationModal from '../../../ui/ConfirmationModal';

interface FenceModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

/** Backend `quantity` bound of one sale (feature file 3.13 A14). */
const QUANTITY_MAX = 999;
const HTTP_CONFLICT = 409;

const parseQty = (raw: string): number => {
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

const maxFor = (offer: FenceOffer): number => Math.max(0, Math.min(offer.max_quantity, QUANTITY_MAX));

/**
 * FEAT-211 — «Скупщик» NPC: sells stolen bales for marks from the fence's own cash.
 * Ordinary merchants never buy stolen goods; the fence pays less than the market.
 */
const FenceModal = ({ npcId, npcName, npcAvatar, onClose }: FenceModalProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;
  const { format } = useCurrency();

  const [offers, setOffers] = useState<FenceOffer[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  /** Guards double submits between the click and the re-render that disables the button. */
  const pendingRef = useRef(false);

  const load = useCallback(async () => {
    if (!characterId) {
      setLoading(false);
      setLoadError('Нужен персонаж, чтобы торговать со скупщиком');
      return;
    }
    setLoading(true);
    try {
      setOffers(await fetchFenceOffers(npcId, characterId));
      setLoadError(null);
    } catch (err) {
      const text = apiErrorMessage(err, 'Не удалось открыть скупку');
      setLoadError(text);
      toast.error(text);
    } finally {
      setLoading(false);
    }
  }, [npcId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Keep the selection valid after every reload.
  useEffect(() => {
    if (!offers) return;
    if (selectedId !== null && offers.some((o) => o.item_id === selectedId)) return;
    setSelectedId(offers[0]?.item_id ?? null);
    setQuantity('1');
  }, [offers, selectedId]);

  const selected = offers?.find((o) => o.item_id === selectedId) ?? null;
  const max = selected ? maxFor(selected) : 0;
  const qty = Math.min(parseQty(quantity), max);
  const total = selected ? qty * selected.unit_price : 0;
  const canSell = Boolean(selected && qty > 0 && !pending);

  const selectOffer = (itemId: number) => {
    if (itemId === selectedId) return;
    setSelectedId(itemId);
    setQuantity('1');
    setActionError(null);
  };

  const changeQuantity = (raw: string) => {
    const digits = raw.replace(/[^\d]/g, '').slice(0, 3);
    const n = parseQty(digits);
    setQuantity(n > max ? String(max) : digits);
    setActionError(null);
  };

  const sell = async () => {
    if (pendingRef.current || !characterId || !selected || qty <= 0) return;
    pendingRef.current = true;
    setPending(true);
    setActionError(null);
    setResult(null);
    try {
      const res = await sellToFence(npcId, { character_id: characterId, item_id: selected.item_id, quantity: qty });
      if (res.success) {
        const text = `Продано: «${res.item_name ?? selected.item_name}» ×${res.quantity} за ${format(res.total_price)}`;
        setResult(text);
        toast.success(text);
      } else {
        const text = res.message || 'Скупщик не купил товар';
        setActionError(text);
        toast.error(text);
      }
    } catch (err) {
      const fallback =
        axios.isAxiosError(err) && err.response?.status === HTTP_CONFLICT
          ? 'У скупщика сейчас нет денег'
          : 'Не удалось продать краденое';
      const text = apiErrorMessage(err, fallback);
      setActionError(text);
      toast.error(text);
    } finally {
      pendingRef.current = false;
      setPending(false);
      // Wallet and bag changed (or the item came back after a failure): show the fresh state.
      dispatch(fetchProfile(characterId));
      dispatch(fetchInventory(characterId));
      void load();
    }
  };

  const requestSell = () => {
    if (!canSell) return;
    if (getClientPrefs().confirmDangerous) setConfirmOpen(true);
    else void sell();
  };

  const icon = (
    <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
      {npcAvatar ? (
        <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-lg" aria-hidden>
          🎭
        </div>
      )}
    </div>
  );

  return (
    <ModalShell open onClose={onClose} title={npcName} size="lg" icon={icon} dismissible={!pending}>
      {loading && !offers ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : !offers ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-site-red text-sm">{loadError ?? 'Не удалось открыть скупку'}</p>
          {characterId && (
            <button type="button" className="btn-line" onClick={() => void load()}>
              Повторить
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4 min-w-0">
          <p className="text-white/60 text-xs sm:text-sm">
            Скупщик берёт краденый товар — дешевле рынка и без лишних вопросов. Обычные торговцы краденое не покупают.
          </p>
          {loadError && <p className="text-site-red text-xs sm:text-sm">{loadError}</p>}

          <section className="flex flex-col gap-2">
            <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Что возьмёт</h3>
            {offers.length === 0 ? (
              <p className="text-white/50 text-sm">У вас нет краденого, которое берёт этот скупщик.</p>
            ) : (
              <ul className="flex flex-col gap-1.5 max-h-[320px] overflow-y-auto gold-scrollbar">
                {offers.map((o) => {
                  const active = o.item_id === selectedId;
                  return (
                    <li key={o.item_id}>
                      <button
                        type="button"
                        onClick={() => selectOffer(o.item_id)}
                        disabled={pending}
                        aria-pressed={active}
                        className={`w-full flex items-center gap-3 rounded-card border px-3 py-2 text-left transition-colors duration-200 ease-site disabled:opacity-60 ${
                          active ? 'border-gold/60 bg-gold/10' : 'border-white/10 bg-white/[0.03] hover:border-white/30'
                        }`}
                      >
                        <div className="w-10 h-10 rounded bg-black/40 overflow-hidden shrink-0 flex items-center justify-center">
                          {o.item_image ? (
                            <img src={o.item_image} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <span className="text-lg" aria-hidden>
                              📦
                            </span>
                          )}
                        </div>
                        <div className="flex flex-col min-w-0 flex-1">
                          <span className={`text-sm font-medium break-words ${active ? 'text-gold' : 'text-white'}`}>
                            {o.item_name}
                          </span>
                          <span className="text-white/60 text-xs">
                            {o.group_name} · {format(o.unit_price)} за шт.
                          </span>
                        </div>
                        <span className="text-xs shrink-0 text-right text-white/70">
                          в сумке:
                          <br />
                          <span className="text-white font-medium">{o.max_quantity}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {selected && (
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
                {max > 1 && (
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
              <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                <span className="text-white/70 text-sm">
                  Получите: <span className="text-gold font-medium">{format(total)}</span>
                </span>
                <button
                  type="button"
                  className="btn-blue w-full sm:w-auto sm:ml-auto !px-6"
                  disabled={!canSell}
                  onClick={requestSell}
                >
                  {pending ? 'Продаём...' : 'Продать'}
                </button>
              </div>
              {actionError && <p className="text-site-red text-xs sm:text-sm">{actionError}</p>}
            </section>
          )}

          {result && !actionError && (
            <p className="rounded-card border border-stat-energy/30 bg-stat-energy/[0.06] px-3 py-2 text-white/80 text-xs sm:text-sm">
              {result}
            </p>
          )}
        </div>
      )}

      <ConfirmationModal
        isOpen={confirmOpen}
        title="Продать краденое?"
        message={selected ? `«${selected.item_name}» ×${qty} за ${format(total)}` : ''}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => {
          setConfirmOpen(false);
          void sell();
        }}
      />
    </ModalShell>
  );
};

export default FenceModal;
