// FEAT-206 — admin lists of a faction's economy: debts, quartermaster purchases (retry / refund),
// tick history and the treasury's ledger operations. Shared rows are reused by the admin character card.
import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowRight } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  FACTION_DEBT_SOURCE_LABEL,
  FACTION_DEBT_STATUS_LABEL,
  FACTION_QM_PURCHASE_STATUS_LABEL,
  adminFactionDebts,
  adminFactionEconHistory,
  adminFactionEconOperations,
  adminFactionQmPurchases,
  adminRefundQmPurchase,
  adminRetryQmPurchase,
  qmErrorText,
  type FactionDebtAdmin,
  type FactionDebtStatus,
  type FactionEconHistoryRow,
  type FactionPage,
  type FactionQmPurchase,
  type FactionQmPurchaseStatus,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import type { EconOperation } from '../../../types/economy';
import { accountDisplayName, formatDateTime, opTypeLabel } from '../EconomyPage/economyLabels';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import { Pager } from './ApplicationsTab';
import { OPTION } from './adminShared';

const PAGE_SIZE = 20;

const SECTION = 'gray-bg p-4 sm:p-6 flex flex-col gap-3 min-w-0';
const H3 = 'gold-text text-lg font-medium uppercase tracking-[0.06em]';
const SELECT = 'input-underline !w-auto !text-sm';

const dt = (v: string | null | undefined): string => (v ? formatDateTime(v) : '—');

const ListError = ({ text, onRetry }: { text: string; onRetry: () => void }) => (
  <div className="flex flex-wrap items-center gap-3">
    <p className="text-site-red text-sm">{text}</p>
    <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={onRetry}>
      Повторить
    </button>
  </div>
);

/** A paged list loader with error state. */
const usePaged = <T,>(fetcher: (page: number) => Promise<FactionPage<T>>, errorText: string, deps: unknown[]) => {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<FactionPage<T> | null>(null);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await fetcher(page));
    } catch (e) {
      setError(apiErrorMessage(e, errorText));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, ...deps]);
  useEffect(() => {
    void load();
  }, [load]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setPage(1), deps);
  return { page, setPage, data, error, load };
};

/* ── Debts ── */

export const DebtRow = ({ d, showFaction = false }: { d: FactionDebtAdmin; showFaction?: boolean }) => {
  const { format } = useCurrency();
  const left = d.amount - d.paid;
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 bg-white/[0.03] rounded-card p-3 min-w-0">
      <div className="flex-1 min-w-0">
        <p className="text-white text-sm break-words">
          {showFaction ? d.faction_name ?? `Фракция #${d.faction_id}` : d.character.name ?? `#${d.character.id}`}
          <span className="text-white/40 text-xs"> · {FACTION_DEBT_SOURCE_LABEL[d.source] ?? d.source}</span>
        </p>
        <p className="text-white/50 text-xs break-words">
          {format(d.amount)}, выплачено {format(d.paid)}
          {d.status === 'open' && left > 0 ? ` · осталось ${format(left)}` : ''} · создан {dt(d.created_at)}
          {d.paid_at ? ` · закрыт ${dt(d.paid_at)}` : ''}
        </p>
      </div>
      <span className={`text-xs shrink-0 ${d.status === 'open' ? 'text-gold-light' : 'text-stat-energy'}`}>
        {FACTION_DEBT_STATUS_LABEL[d.status] ?? d.status}
      </span>
    </div>
  );
};

export const FactionDebtsList = ({ factionId, reloadKey }: { factionId: number; reloadKey: number }) => {
  const [status, setStatus] = useState<FactionDebtStatus | 'all'>('open');
  const { page, setPage, data, error, load } = usePaged<FactionDebtAdmin>(
    (p) => adminFactionDebts(factionId, status, p, PAGE_SIZE),
    'Не удалось загрузить долги фракции',
    [factionId, status, reloadKey],
  );
  return (
    <section className={SECTION}>
      <div className="flex flex-wrap items-center gap-3">
        <h3 className={H3}>Долги перед игроками</h3>
        <select value={status} onChange={(e) => setStatus(e.target.value as FactionDebtStatus | 'all')} className={SELECT}>
          <option value="open" className={OPTION}>Не выплаченные</option>
          <option value="paid" className={OPTION}>Выплаченные</option>
          <option value="all" className={OPTION}>Все</option>
        </select>
      </div>
      <p className="text-white/40 text-xs">
        Выплачиваются из казны по очереди (сначала старые, частями), как только в казне появляются марки.
      </p>
      {error && <ListError text={error} onRetry={() => void load()} />}
      {data && data.items.length === 0 && <p className="text-white/50 text-sm">Долгов нет.</p>}
      <div className="flex flex-col gap-2">
        {data?.items.map((d) => <DebtRow key={d.id} d={d} />)}
      </div>
      {data && <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} />}
    </section>
  );
};

/* ── Quartermaster purchases ── */

export const PurchaseRow = ({
  p,
  canAct,
  busy,
  onRetry,
  onRefund,
  showCharacter = true,
}: {
  p: FactionQmPurchase;
  canAct: boolean;
  busy: boolean;
  onRetry: (p: FactionQmPurchase) => void;
  onRefund: (p: FactionQmPurchase) => void;
  showCharacter?: boolean;
}) => {
  const { format } = useCurrency();
  const err = qmErrorText(p.last_error);
  const statusClass =
    p.status === 'done' ? 'text-stat-energy' : p.status === 'failed' ? 'text-site-red' : p.status === 'refunded' ? 'text-white/60' : 'text-gold-light';
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2 bg-white/[0.03] rounded-card p-3 min-w-0">
      <div className="flex-1 min-w-0">
        <p className="text-white text-sm break-words">
          {p.item.name ?? `Предмет #${p.item.id}`} × {p.quantity} · <span className="text-gold">{format(p.price_total)}</span>
          {showCharacter && <span className="text-white/50"> · {p.character.name ?? `#${p.character.id}`}</span>}
        </p>
        <p className="text-white/50 text-xs break-words">
          <span className={statusClass}>{FACTION_QM_PURCHASE_STATUS_LABEL[p.status] ?? p.status}</span>
          {` · попыток ${p.attempts} · ${dt(p.created_at)}`}
          {err ? ` · ${err}` : ''}
        </p>
      </div>
      {canAct && (p.status === 'failed' || p.status === 'pending') && (
        <div className="flex flex-col sm:flex-row gap-2 shrink-0">
          {p.status === 'failed' && (
            <button
              type="button"
              disabled={busy}
              onClick={() => onRetry(p)}
              className="btn-line !w-full sm:!w-auto !text-xs !py-1.5 !px-4 disabled:opacity-50"
            >
              Повторить выдачу
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => onRefund(p)}
            className="btn-line !w-full sm:!w-auto !text-xs !py-1.5 !px-4 disabled:opacity-50"
          >
            Вернуть деньги
          </button>
        </div>
      )}
    </div>
  );
};

interface PendingAction {
  title: string;
  message: string;
  confirmLabel: string;
  danger: boolean;
  call: () => Promise<FactionQmPurchase>;
  okText: string;
}

/** Retry / refund behind a confirmation dialog; render `dialog` next to the rows. */
export const usePurchaseActions = (
  onDone: () => void,
): { busy: boolean; onRetry: (p: FactionQmPurchase) => void; onRefund: (p: FactionQmPurchase) => void; dialog: ReactNode } => {
  const { format } = useCurrency();
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingAction | null>(null);

  const run = async () => {
    if (!pending || busy) return;
    const action = pending;
    setPending(null);
    setBusy(true);
    try {
      const res = await action.call();
      toast.success(`${action.okText}: ${FACTION_QM_PURCHASE_STATUS_LABEL[res.status] ?? res.status}`);
      onDone();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось выполнить действие с покупкой'));
    } finally {
      setBusy(false);
    }
  };

  const who = (p: FactionQmPurchase) => p.character.name ?? `#${p.character.id}`;
  const what = (p: FactionQmPurchase) => p.item.name ?? `предмет #${p.item.id}`;

  return {
    busy,
    onRetry: (p) =>
      setPending({
        title: 'Повторить выдачу',
        message: `Ещё раз выдать «${what(p)}» × ${p.quantity} персонажу ${who(p)}? Если неясно, дошёл ли предмет, сначала проверьте инвентарь — иначе он может получить его дважды.`,
        confirmLabel: 'Повторить',
        danger: false,
        call: () => adminRetryQmPurchase(p.id),
        okText: 'Выдача запущена',
      }),
    onRefund: (p) =>
      setPending({
        title: 'Вернуть деньги',
        message: `Вернуть ${format(p.price_total)} персонажу ${who(p)} за «${what(p)}» × ${p.quantity}? Товар вернётся интенданту; если в казне не хватит марок — возврат запишется в долг фракции.`,
        confirmLabel: 'Вернуть',
        danger: true,
        call: () => adminRefundQmPurchase(p.id),
        okText: 'Возврат выполнен',
      }),
    dialog: pending ? (
      <ConfirmDialog
        title={pending.title}
        message={pending.message}
        confirmLabel={pending.confirmLabel}
        danger={pending.danger}
        onConfirm={() => void run()}
        onCancel={() => setPending(null)}
      />
    ) : null,
  };
};

export const FactionPurchasesList = ({
  factionId,
  canAct,
  reloadKey,
  onChanged,
}: {
  factionId: number;
  canAct: boolean;
  reloadKey: number;
  onChanged: () => void;
}) => {
  const [status, setStatus] = useState<FactionQmPurchaseStatus | 'all'>('all');
  const { page, setPage, data, error, load } = usePaged<FactionQmPurchase>(
    (p) => adminFactionQmPurchases(factionId, status, p, PAGE_SIZE),
    'Не удалось загрузить покупки у интенданта',
    [factionId, status, reloadKey],
  );
  const actions = usePurchaseActions(() => {
    void load();
    onChanged();
  });
  return (
    <section className={SECTION}>
      <div className="flex flex-wrap items-center gap-3">
        <h3 className={H3}>Покупки у интенданта</h3>
        <select value={status} onChange={(e) => setStatus(e.target.value as FactionQmPurchaseStatus | 'all')} className={SELECT}>
          <option value="all" className={OPTION}>Все</option>
          {(Object.keys(FACTION_QM_PURCHASE_STATUS_LABEL) as FactionQmPurchaseStatus[]).map((s) => (
            <option key={s} value={s} className={OPTION}>
              {FACTION_QM_PURCHASE_STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>
      {error && <ListError text={error} onRetry={() => void load()} />}
      {data && data.items.length === 0 && <p className="text-white/50 text-sm">Покупок нет.</p>}
      <div className="flex flex-col gap-2">
        {data?.items.map((p) => (
          <PurchaseRow key={p.id} p={p} canAct={canAct} busy={actions.busy} onRetry={actions.onRetry} onRefund={actions.onRefund} />
        ))}
      </div>
      {data && <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} />}
      {actions.dialog}
    </section>
  );
};

/* ── Tick history ── */

export const FactionEconHistoryList = ({ factionId, reloadKey }: { factionId: number; reloadKey: number }) => {
  const { format } = useCurrency();
  const { page, setPage, data, error, load } = usePaged<FactionEconHistoryRow>(
    (p) => adminFactionEconHistory(factionId, p, PAGE_SIZE),
    'Не удалось загрузить историю пересчётов',
    [factionId, reloadKey],
  );
  return (
    <section className={SECTION}>
      <h3 className={H3}>История пересчётов</h3>
      {error && <ListError text={error} onRetry={() => void load()} />}
      {data && data.items.length === 0 && (
        <p className="text-white/50 text-sm">Фракция ещё не участвовала в экономическом пересчёте.</p>
      )}
      <div className="flex flex-col gap-2">
        {data?.items.map((h) => {
          const itemSales = h.item_sales ?? 0;
          const inflow = h.dues + h.profile + itemSales;
          const outflow = h.wages_paid + h.restock_spent + h.debts_paid;
          const membersDelta = h.members_after - h.members_before;
          return (
            <div key={h.id} className="bg-white/[0.03] rounded-card p-3 flex flex-col gap-1 min-w-0">
              <p className="text-white/80 text-sm flex flex-wrap items-center gap-x-2">
                <span className="text-white/40 text-xs">{dt(h.created_at)} · прогон #{h.run_id}</span>
                <span>
                  {format(h.balance_before)} <ArrowRight size={12} className="inline text-gold" /> {format(h.balance_after)}
                </span>
                <span className="text-white/50 text-xs">богатство {h.wealth}</span>
              </p>
              <p className="text-white/55 text-xs break-words">
                приток <span className="text-stat-energy">+{format(inflow)}</span> (взносы {format(h.dues)}, профиль{' '}
                {format(h.profile)}
                {itemSales > 0 ? `, предметы ${format(itemSales)} / ${h.items_sold ?? 0} шт.` : ''}) · отток <span className="text-site-red">−{format(outflow)}</span> (жалованье{' '}
                {format(h.wages_paid)} из {format(h.wages_due)}, закупки {format(h.restock_spent)} / {h.restock_items} шт., долги{' '}
                {format(h.debts_paid)}) · участники {h.members_before} → {h.members_after}
                {membersDelta !== 0 ? ` (${membersDelta > 0 ? '+' : ''}${membersDelta})` : ''}
              </p>
            </div>
          );
        })}
      </div>
      {data && <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} />}
    </section>
  );
};

/* ── Treasury operations ── */

export const FactionOperationsList = ({ factionId, reloadKey }: { factionId: number; reloadKey: number }) => {
  const { format } = useCurrency();
  const { page, setPage, data, error, load } = usePaged<EconOperation>(
    (p) => adminFactionEconOperations(factionId, p, PAGE_SIZE),
    'Не удалось загрузить операции казны',
    [factionId, reloadKey],
  );
  return (
    <section className={SECTION}>
      <h3 className={H3}>Операции казны</h3>
      {error && <ListError text={error} onRetry={() => void load()} />}
      {data && data.items.length === 0 && <p className="text-white/50 text-sm">Операций по казне ещё не было.</p>}
      <div className="flex flex-col gap-2">
        {data?.items.map((op) => (
          <div key={op.id} className="bg-white/[0.03] rounded-card p-3 flex flex-col gap-1 min-w-0">
            <p className="text-white text-sm break-words">
              {opTypeLabel(op.op_type)} <span className="text-white/40 text-xs">· {dt(op.created_at)}</span>
            </p>
            <ul className="flex flex-col gap-0.5">
              {op.postings.map((p, i) => (
                <li key={i} className="flex flex-wrap items-center gap-x-2 text-xs text-white/70">
                  <span className="break-words">{accountDisplayName(p.from)}</span>
                  <ArrowRight size={12} className="text-gold shrink-0" />
                  <span className="break-words">{accountDisplayName(p.to)}</span>
                  <span className="text-white font-medium">{format(p.amount)}</span>
                </li>
              ))}
            </ul>
            {op.comment && <p className="text-white/50 text-xs break-words">Комментарий: {op.comment}</p>}
          </div>
        ))}
      </div>
      {data && <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} />}
    </section>
  );
};
