import { Fragment, useEffect, useState } from 'react';
import { ArrowRight, ChevronDown, ChevronRight } from 'lucide-react';
import { fetchEconomyOperations } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import AdminPagination from '../AdminPagination/AdminPagination';
import type { EconAccount, EconOperation, EconPosting, EconSummary } from '../../../types/economy';
import AccountPicker from './AccountPicker';
import {
  ALL_ACCOUNT_KINDS,
  LEG_TYPE_LABELS,
  OP_TYPE_LABELS,
  REGION_TICK_OP,
  accountDisplayName,
  formatDateTime,
  opTypeLabel,
} from './economyLabels';

const PAGE_SIZE = 25;

interface EconomyJournalProps {
  /** Region options for the filter come from the summary tree. */
  summary: EconSummary | null;
}

const PostingLine = ({ p }: { p: EconPosting }) => {
  const { format } = useCurrency();
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
      <span className="text-white/80 break-words">{accountDisplayName(p.from)}</span>
      <ArrowRight size={14} className="text-gold shrink-0" />
      <span className="text-white/80 break-words">{accountDisplayName(p.to)}</span>
      <span className="text-white font-medium">{format(p.amount)}</span>
      {p.leg_type !== 'main' && (
        <span className="text-white/40 text-xs">({LEG_TYPE_LABELS[p.leg_type] ?? p.leg_type})</span>
      )}
    </li>
  );
};

const OperationDetails = ({ op }: { op: EconOperation }) => (
  <div className="flex flex-col gap-2 py-2">
    <ul className="flex flex-col gap-1">
      {op.postings.map((p, i) => (
        <PostingLine key={i} p={p} />
      ))}
    </ul>
    <p className="text-white/40 text-xs break-words">
      Сервис: {op.source_service}
      {op.location_id != null && ` · локация #${op.location_id}`}
      {op.region_id != null && ` · регион #${op.region_id}`}
      {op.actor_user_id != null && ` · админ #${op.actor_user_id}`}
      {op.metadata && Object.keys(op.metadata).length > 0 && ` · ${JSON.stringify(op.metadata)}`}
    </p>
  </div>
);

/**
 * Size of an operation = its largest leg. Legs chain through escrow/treasuries (buyer → escrow →
 * seller + commission), so summing them would count the same money several times.
 */
const opAmount = (op: EconOperation) => op.postings.reduce((m, p) => Math.max(m, p.amount), 0);

/** Journal of ledger operations with filters; each operation expands to its legs. */
const EconomyJournal = ({ summary }: EconomyJournalProps) => {
  const { format } = useCurrency();
  const [opType, setOpType] = useState('');
  const [regionId, setRegionId] = useState('');
  const [account, setAccount] = useState<EconAccount | null>(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  // Region ticks add one operation per simulated region every 6 hours — hidden unless asked for.
  const [hideTicks, setHideTicks] = useState(true);
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<EconOperation[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  // Any filter change goes back to the first page.
  useEffect(() => {
    setPage(1);
  }, [opType, regionId, account, dateFrom, dateTo, hideTicks]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEconomyOperations({
      op_type: opType || undefined,
      // An explicit «Пересчёт региона» type filter wins over the hide toggle.
      exclude_op_type: hideTicks && opType !== REGION_TICK_OP ? REGION_TICK_OP : undefined,
      region_id: regionId ? Number(regionId) : undefined,
      account_id: account?.account_id,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      page,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((e) => {
        if (cancelled) return;
        setItems([]);
        setTotal(0);
        setError(apiErrorMessage(e, 'Не удалось загрузить журнал операций'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [opType, regionId, account, dateFrom, dateTo, hideTicks, page]);

  const toggle = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const regions = (summary?.countries ?? [])
    .flatMap((c) => c.regions)
    .sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'ru'));

  const hasFilters = Boolean(opType || regionId || account || dateFrom || dateTo);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="flex flex-col gap-1 min-w-0">
          <label htmlFor="econ-op-type" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Тип операции
          </label>
          <select id="econ-op-type" className="input-underline w-full" value={opType} onChange={(e) => setOpType(e.target.value)}>
            <option value="" className="bg-site-dark text-white">Все</option>
            {Object.entries(OP_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value} className="bg-site-dark text-white">{label}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <label htmlFor="econ-region" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Регион
          </label>
          <select id="econ-region" className="input-underline w-full" value={regionId} onChange={(e) => setRegionId(e.target.value)}>
            <option value="" className="bg-site-dark text-white">Все</option>
            {regions.map((r) => (
              <option key={r.region_id} value={r.region_id} className="bg-site-dark text-white">
                {r.name ?? `Регион #${r.region_id}`}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <label htmlFor="econ-date-from" className="text-white/60 text-xs uppercase tracking-[0.06em]">С даты</label>
          <input id="econ-date-from" type="date" className="input-underline w-full [color-scheme:dark]" value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <label htmlFor="econ-date-to" className="text-white/60 text-xs uppercase tracking-[0.06em]">По дату</label>
          <input id="econ-date-to" type="date" className="input-underline w-full [color-scheme:dark]" value={dateTo}
            onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <div className="sm:col-span-2 lg:col-span-3">
          <AccountPicker
            kinds={ALL_ACCOUNT_KINDS}
            allowAnyKind
            allowInactive
            value={account}
            onChange={setAccount}
            label="Счёт"
            inputId="econ-journal-account"
          />
        </div>
        <label className="flex items-center gap-2 self-end py-2 text-sm text-white/70 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={hideTicks}
            disabled={opType === REGION_TICK_OP}
            onChange={(e) => setHideTicks(e.target.checked)}
            className="w-4 h-4 shrink-0 accent-gold disabled:opacity-40"
          />
          Скрыть пересчёты регионов
        </label>
        {hasFilters && (
          <div className="flex items-end">
            <button
              type="button"
              className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5"
              onClick={() => {
                setOpType('');
                setRegionId('');
                setAccount(null);
                setDateFrom('');
                setDateTo('');
              }}
            >
              Сбросить фильтры
            </button>
          </div>
        )}
      </div>

      {error && <p className="text-site-red text-sm">{error}</p>}
      {loading && !items && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {items && items.length === 0 && !error && (
        <p className="text-white/40 text-sm italic">Операций не найдено.</p>
      )}

      {items && items.length > 0 && (
        <div className={`md:bg-site-bg md:rounded-card md:border md:border-white/[0.07] md:px-4 md:py-2 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {/* Table — md and up */}
          <table className="hidden md:table w-full text-sm">
            <thead>
              <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                <th className="py-2 pr-3 font-normal w-8" />
                <th className="py-2 pr-3 font-normal">№</th>
                <th className="py-2 pr-3 font-normal">Когда</th>
                <th className="py-2 pr-3 font-normal">Операция</th>
                <th className="py-2 pr-3 font-normal">Комментарий</th>
                <th className="py-2 font-normal text-right">Сумма</th>
              </tr>
            </thead>
            <tbody>
              {items.map((op) => {
                const isOpen = expanded.has(op.id);
                return (
                  <Fragment key={op.id}>
                    <tr
                      className="border-b border-white/[0.07] cursor-pointer hover:bg-white/[0.04] transition-colors duration-200 ease-site"
                      onClick={() => toggle(op.id)}
                    >
                      <td className="py-2 pr-3 text-gold">
                        {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      </td>
                      <td className="py-2 pr-3 text-white/50">{op.id}</td>
                      <td className="py-2 pr-3 text-white/70 whitespace-nowrap">{formatDateTime(op.created_at)}</td>
                      <td className="py-2 pr-3 text-white">{opTypeLabel(op.op_type)}</td>
                      <td className="py-2 pr-3 text-white/60 break-words max-w-[280px]">{op.comment ?? '—'}</td>
                      <td className="py-2 text-right text-white whitespace-nowrap">{format(opAmount(op))}</td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-white/[0.07]">
                        <td />
                        <td colSpan={5}>
                          <OperationDetails op={op} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>

          {/* Cards — below md */}
          <ul className="md:hidden flex flex-col gap-3">
            {items.map((op) => {
              const isOpen = expanded.has(op.id);
              return (
                <li key={op.id} className="bg-site-bg rounded-card border border-white/[0.07] p-3">
                  <button type="button" className="w-full text-left flex items-start gap-2" onClick={() => toggle(op.id)} aria-expanded={isOpen}>
                    {isOpen ? <ChevronDown size={16} className="text-gold mt-0.5 shrink-0" /> : <ChevronRight size={16} className="text-gold mt-0.5 shrink-0" />}
                    <span className="flex-1 min-w-0 flex flex-col gap-0.5">
                      <span className="text-white text-sm font-medium break-words">{opTypeLabel(op.op_type)}</span>
                      <span className="text-white/40 text-xs">№{op.id} · {formatDateTime(op.created_at)}</span>
                      {op.comment && <span className="text-white/60 text-xs break-words">{op.comment}</span>}
                    </span>
                    <span className="text-white text-sm shrink-0">{format(opAmount(op))}</span>
                  </button>
                  {isOpen && <OperationDetails op={op} />}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <AdminPagination page={page} totalPages={totalPages} onPageChange={setPage} total={total} pageSize={PAGE_SIZE} />
    </div>
  );
};

export default EconomyJournal;
