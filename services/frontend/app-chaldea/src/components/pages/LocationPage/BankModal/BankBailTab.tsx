import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import ConfirmDialog from '../ConfirmDialog';
import RemainingText from '../../../CommonComponents/RemainingText';
import {
  fetchPrisoners,
  LAW_QUERY_MAX,
  payBail,
  type LawPrisonerOut,
} from '../../../../api/law';
import { bankErrorText } from './bankFormat';
import { BankCard, BankSection } from './BankParts';

/**
 * FEAT-198 — «Залог» tab of the bank: find a prisoner (any region's jail) and
 * pay the bail from the current character's purse at this banker.
 */

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 400;

interface BankBailTabProps {
  characterId: number;
  npcId: number;
  /** Bank actions are blocked (reputation lock / another request). */
  pending: boolean;
  wallet: number;
  /** After a paid bail: refresh the wallet. */
  onPaid: () => void;
}

const BankBailTab = ({ characterId, npcId, pending, wallet, onPaid }: BankBailTabProps) => {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [items, setItems] = useState<LawPrisonerOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<LawPrisonerOut | null>(null);
  const [paying, setPaying] = useState(false);
  const payingRef = useRef(false);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(async (q: string, nextPage: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPrisoners(q, nextPage, PAGE_SIZE);
      setItems((prev) => (nextPage === 1 ? data.items : [...prev, ...data.items]));
      setTotal(data.total);
      setPage(nextPage);
    } catch (err) {
      setError(bankErrorText(err, 'Не удалось загрузить список узников'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(debounced, 1);
  }, [debounced, load]);

  const pay = async (prisoner: LawPrisonerOut) => {
    setConfirming(null);
    if (payingRef.current) return;
    payingRef.current = true;
    setPaying(true);
    try {
      const res = await payBail(characterId, npcId, prisoner.character_id);
      toast.success(res.message);
      onPaid();
    } catch (err) {
      toast.error(bankErrorText(err, 'Не удалось внести залог'));
    } finally {
      payingRef.current = false;
      setPaying(false);
      void load(debounced, 1);
    }
  };

  const blocked = pending || paying;

  return (
    <BankSection title="Залог за узника">
      <p className="text-white/50 text-xs leading-snug">
        Внесите залог за любого узника — он сразу выйдет на свободу. Деньги уходят в казну края, где стоит
        тюрьма. Заплатить можно у банкира любого края.
      </p>
      <label className="flex flex-col gap-0.5 min-w-0">
        <span className="text-white/50 text-[11px] uppercase tracking-wide">Имя узника</span>
        <input
          type="text"
          value={query}
          maxLength={LAW_QUERY_MAX}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по имени"
          className="input-underline !text-sm w-full min-w-0"
        />
      </label>

      {error && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-site-red text-xs sm:text-sm">{error}</span>
          <button type="button" className="btn-line !text-xs !py-1 !px-3" onClick={() => void load(debounced, 1)}>
            Повторить
          </button>
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="flex items-center justify-center py-6">
          <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : items.length === 0 && !error ? (
        <p className="text-white/50 text-sm text-center py-4">
          {debounced ? 'Никого не нашли' : 'Тюрьмы пусты'}
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((p) => {
            const tooExpensive = p.bail_price > wallet;
            return (
              <BankCard key={p.character_id} className="!flex-row items-center gap-3 flex-wrap">
                <div className="gold-outline relative w-10 h-10 rounded-full overflow-hidden bg-black/40 shrink-0">
                  {p.avatar ? (
                    <img src={p.avatar} alt={p.name} className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-base" aria-hidden>
                      ⛓️
                    </div>
                  )}
                </div>
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-white text-sm font-medium truncate">
                    {p.character_id === characterId ? `${p.name} (вы)` : p.name}
                  </span>
                  <span className="text-white/50 text-xs break-words">
                    {p.region_name ? `Край «${p.region_name}»` : 'Край неизвестен'}
                    {p.location_name ? ` · «${p.location_name}»` : ''}
                  </span>
                  <span className="text-white/50 text-xs">
                    <RemainingText until={p.until} doneText="срок истёк" />
                  </span>
                </div>
                <div className="flex flex-col items-stretch sm:items-end gap-1 w-full sm:w-auto">
                  <span className="text-gold text-sm font-medium sm:text-right">
                    {p.bail_price.toLocaleString('ru-RU')} золота
                  </span>
                  <button
                    type="button"
                    disabled={blocked || tooExpensive || p.character_id === characterId}
                    title={tooExpensive ? 'Не хватает золота в кошельке' : undefined}
                    onClick={() => setConfirming(p)}
                    className="btn-blue w-full sm:w-auto !text-xs !py-1.5 !px-4 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Внести залог
                  </button>
                </div>
              </BankCard>
            );
          })}
          {items.length < total && (
            <button
              type="button"
              disabled={loading}
              onClick={() => void load(debounced, page + 1)}
              className="btn-line w-full sm:w-auto self-center !text-xs !py-1.5 !px-5 disabled:opacity-50"
            >
              {loading ? 'Загрузка...' : 'Показать ещё'}
            </button>
          )}
        </div>
      )}

      {confirming && (
        <ConfirmDialog
          title="Внести залог?"
          message={`Заплатить ${confirming.bail_price.toLocaleString('ru-RU')} золота за «${confirming.name}»? Узник сразу выйдет на свободу.`}
          confirmLabel="Внести залог"
          onConfirm={() => void pay(confirming)}
          onCancel={() => setConfirming(null)}
        />
      )}
    </BankSection>
  );
};

export default BankBailTab;
