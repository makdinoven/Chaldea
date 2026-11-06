// FEAT-206 — «Интендант» of a faction: the faction's assortment with the rank discount, locked rows
// (non-members / low rank), quantity + confirmation, one request per click with a client request_id.
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useDispatch } from 'react-redux';
import { Flag, Lock } from 'lucide-react';
import goldCoinsIcon from '../../../../assets/icons/gold-coins.svg';
import {
  QM_QUANTITY_MAX,
  buyFromQuartermaster,
  fetchQuartermaster,
  type QuartermasterItem,
  type QuartermasterView,
} from '../../../../api/factions';
import { useCurrency } from '../../../../hooks/useCurrency';
import { fetchProfile } from '../../../../redux/slices/profileSlice';
import type { AppDispatch } from '../../../../redux/store';
import { useAppSelector } from '../../../../redux/store';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import { bankErrorText, newRequestId, parseAmount } from '../BankModal/bankFormat';
import { ItemThumb } from '../GuildModal/GuildParts';

interface QuartermasterModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

const HTTP_CONFLICT = 409;
/** Backend `MSG_DONE` — a repeated request: info, not an error. */
const DUPLICATE_TEXT = 'Покупка уже выполнена';
const QUANTITY_DIGITS = 2;

const isDuplicate = (err: unknown): boolean =>
  axios.isAxiosError(err) && err.response?.status === HTTP_CONFLICT && err.response.data?.detail === DUPLICATE_TEXT;

const canBuy = (row: QuartermasterItem): boolean => !row.locked_reason && row.stock > 0;

const QuartermasterModal = ({ npcId, npcName, npcAvatar, onClose }: QuartermasterModalProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;
  const { format } = useCurrency();

  const [view, setView] = useState<QuartermasterView | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<{ text: string; delivered: boolean } | null>(null);
  const pendingRef = useRef(false);
  /** Kept for a retry of the same request; a new one after a success or any change. */
  const requestIdRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!characterId) {
      setLoading(false);
      setLoadError('Нужен персонаж, чтобы говорить с интендантом');
      return;
    }
    setLoading(true);
    try {
      setView(await fetchQuartermaster(npcId, characterId));
      setLoadError(null);
    } catch (err) {
      const text = bankErrorText(err, 'Не удалось открыть лавку интенданта');
      setLoadError(text);
      toast.error(text);
    } finally {
      setLoading(false);
    }
  }, [npcId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const items = view?.items ?? [];
  const selected = items.find((i) => i.qm_item_id === selectedId) ?? null;
  const max = selected ? Math.min(selected.stock, QM_QUANTITY_MAX) : 0;
  const qty = Math.min(parseAmount(quantity), max);
  const total = selected ? selected.final_price * qty : 0;
  const discount = view?.rank?.discount_pct ?? 0;
  const enough = view ? total <= view.balance : false;

  const changeRequest = () => {
    requestIdRef.current = null;
    setActionError(null);
    setConfirming(false);
  };

  const select = (row: QuartermasterItem) => {
    if (!canBuy(row) || pending) return;
    setSelectedId(row.qm_item_id === selectedId ? null : row.qm_item_id);
    setQuantity('1');
    setResult(null);
    changeRequest();
  };

  const changeQuantity = (raw: string) => {
    const digits = raw.replace(/[^\d]/g, '').slice(0, QUANTITY_DIGITS);
    const n = parseAmount(digits);
    setQuantity(n > max ? String(max) : digits);
    changeRequest();
  };

  const buy = async () => {
    if (pendingRef.current || !characterId || !selected || qty <= 0) return;
    pendingRef.current = true;
    setPending(true);
    setActionError(null);
    if (!requestIdRef.current) requestIdRef.current = newRequestId();
    try {
      const res = await buyFromQuartermaster(npcId, {
        character_id: characterId,
        qm_item_id: selected.qm_item_id,
        quantity: qty,
        request_id: requestIdRef.current,
      });
      requestIdRef.current = null;
      setResult({ text: res.message, delivered: res.delivered });
      setConfirming(false);
      setSelectedId(null);
      toast.success(res.delivered ? res.message : `Куплено за ${format(res.price_total)}`);
      dispatch(fetchProfile(characterId));
    } catch (err) {
      if (isDuplicate(err)) {
        requestIdRef.current = null;
        setConfirming(false);
        toast(DUPLICATE_TEXT, { icon: 'ℹ️' });
        dispatch(fetchProfile(characterId));
      } else {
        const text = bankErrorText(err, 'Не удалось купить у интенданта');
        setActionError(text);
        toast.error(text);
      }
    } finally {
      pendingRef.current = false;
      setPending(false);
      // Stock, the balance and the rank may have changed: show the fresh state.
      void load();
    }
  };

  const icon = (
    <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
      {npcAvatar ? (
        <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-lg" aria-hidden>
          🎖️
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
          <p className="text-site-red text-sm break-words">{loadError ?? 'Не удалось открыть лавку интенданта'}</p>
          {characterId && (
            <button type="button" className="btn-line" onClick={() => void load()}>
              Повторить
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4 min-w-0">
          {/* Faction, rank, wallet */}
          <div className="flex flex-wrap items-start gap-3">
            <div className="w-11 h-11 shrink-0 rounded-[10px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
              <div className="w-full h-full rounded-[8px] bg-site-dark flex items-center justify-center overflow-hidden">
                {view.faction.emblem_url ? (
                  <img src={view.faction.emblem_url} alt="" className="w-full h-full object-cover" />
                ) : (
                  <Flag size={20} strokeWidth={1.6} className="text-gold/70" />
                )}
              </div>
            </div>
            <div className="flex flex-col min-w-0 flex-1">
              <span className="text-white/50 text-xs uppercase tracking-wide">Интендант фракции</span>
              <span className="text-white text-sm sm:text-base font-medium break-words">«{view.faction.name}»</span>
              {view.member ? (
                <span className="text-white/60 text-xs sm:text-sm mt-0.5 break-words">
                  {view.rank ? (
                    <>
                      Ваше звание: <span className="text-gold">{view.rank.name}</span>
                      {discount > 0 ? ` · скидка ${discount} %` : ' · без скидки'}
                    </>
                  ) : (
                    'Вы без звания — скидки нет'
                  )}
                </span>
              ) : (
                <span className="text-white/60 text-xs sm:text-sm mt-0.5">
                  Товары продаются только членам фракции.
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 bg-black/30 rounded-card px-3 py-1.5 shrink-0" title="В кошельке">
              <img src={goldCoinsIcon} alt="" className="w-5 h-5" />
              <span className="text-gold font-medium text-sm sm:text-base">{view.balance.toLocaleString('ru-RU')}</span>
            </div>
          </div>

          {/* Assortment */}
          <section className="flex flex-col gap-2">
            <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Товары</h3>
            {items.length === 0 ? (
              <p className="text-white/50 text-sm">У интенданта сейчас ничего нет — загляните позже.</p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {items.map((row) => {
                  const active = row.qm_item_id === selectedId;
                  const buyable = canBuy(row);
                  return (
                    <li key={row.qm_item_id}>
                      <button
                        type="button"
                        onClick={() => select(row)}
                        disabled={pending || !buyable}
                        aria-pressed={active}
                        className={`w-full flex items-center gap-3 rounded-card border px-3 py-2 text-left transition-colors duration-200 ease-site ${
                          active
                            ? 'border-gold/60 bg-gold/10'
                            : buyable
                              ? 'border-white/10 bg-white/[0.03] hover:border-white/30'
                              : 'border-white/5 bg-white/[0.02] cursor-default'
                        }`}
                      >
                        <ItemThumb image={row.item.image} fallback="📦" dim={!buyable} />
                        <div className="flex flex-col min-w-0 flex-1">
                          <span
                            className={`text-sm font-medium break-words ${
                              active ? 'text-gold' : buyable ? 'text-white' : 'text-white/60'
                            }`}
                          >
                            {row.item.name}
                          </span>
                          <span className="text-white/60 text-xs">
                            {row.final_price < row.price && (
                              <span className="line-through text-white/35 mr-1">{format(row.price, true)}</span>
                            )}
                            <span className="text-gold/90">{format(row.final_price)}</span> за шт.
                          </span>
                          {row.locked_reason && (
                            <span className="text-white/50 text-[11px] inline-flex items-center gap-1 break-words">
                              <Lock size={11} className="shrink-0" />
                              {row.locked_reason}
                            </span>
                          )}
                        </div>
                        <span className="text-xs shrink-0 text-right text-white/70">
                          {row.stock > 0 ? (
                            <>
                              в наличии:
                              <br />
                              <span className="text-white font-medium">{row.stock}</span>
                            </>
                          ) : (
                            <span className="text-white/45">Нет в наличии</span>
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* Quantity, total, confirmation */}
          {selected && (
            <section className="flex flex-col gap-3 rounded-card border border-white/5 bg-white/[0.03] p-3">
              <div className="flex items-end gap-2 min-w-0">
                <label className="flex flex-col gap-0.5 min-w-0 flex-1">
                  <span className="text-white/50 text-[11px] uppercase tracking-wide">
                    Количество, шт. (до {max})
                  </span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={quantity}
                    disabled={pending}
                    onChange={(e) => changeQuantity(e.target.value)}
                    placeholder="1"
                    className="input-underline !text-sm w-full min-w-0"
                  />
                </label>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                <span className="text-white/70 text-sm">
                  Итого: <span className="text-gold font-medium">{format(total)}</span>
                  {!enough && qty > 0 && <span className="text-site-red text-xs"> — не хватает марок</span>}
                </span>
                {!confirming ? (
                  <button
                    type="button"
                    className="btn-blue w-full sm:w-auto sm:ml-auto !px-6"
                    disabled={pending || qty <= 0 || !enough}
                    onClick={() => setConfirming(true)}
                  >
                    Купить
                  </button>
                ) : (
                  <div className="flex flex-col sm:flex-row gap-2 sm:ml-auto w-full sm:w-auto">
                    <button
                      type="button"
                      className="btn-line w-full sm:w-auto"
                      disabled={pending}
                      onClick={() => setConfirming(false)}
                    >
                      Отмена
                    </button>
                    <button
                      type="button"
                      className="btn-blue w-full sm:w-auto !px-6"
                      disabled={pending}
                      onClick={() => void buy()}
                    >
                      {pending ? 'Покупаем...' : 'Да, купить'}
                    </button>
                  </div>
                )}
              </div>
              {confirming && (
                <p className="text-white/60 text-xs break-words">
                  Купить «{selected.item.name}» × {qty} за {format(total)}? Марки уйдут в казну фракции.
                </p>
              )}
              {actionError && <p className="text-site-red text-xs sm:text-sm break-words">{actionError}</p>}
            </section>
          )}

          {!selected && actionError && <p className="text-site-red text-xs sm:text-sm break-words">{actionError}</p>}
          {result && (
            <p
              className={`rounded-card border px-3 py-2 text-xs sm:text-sm text-white/80 ${
                result.delivered ? 'border-stat-energy/30 bg-stat-energy/[0.06]' : 'border-gold/30 bg-gold/[0.06]'
              }`}
            >
              {result.text}
            </p>
          )}
        </div>
      )}
    </ModalShell>
  );
};

export default QuartermasterModal;
