import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import {
  fetchEconomyGoodsGroups,
  fetchEconomyMerchants,
  fetchEconomyRegions,
  postEconomyMerchantsFund,
} from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import type {
  EconMerchant,
  EconMerchantFundResult,
  EconMerchantRow,
  EconMerchantsResponse,
  EconRegionItem,
} from '../../../types/economy';
import { formatDateTime, formatPercent, merchantFundSkipText, merchantReasonText } from './economyLabels';

const COMMENT_MIN = 3;
const COMMENT_MAX = 500;
const ORIGIN_PLAYER = 'player';
/** Cash below this share of the target is shown red (the merchant can barely restock). */
const CASH_LOW_SHARE = 0.5;

type LivingFilter = 'all' | 'living' | 'legacy';

const LIVING_FILTER_LABEL: Record<LivingFilter, string> = {
  all: 'Все',
  living: 'Живой рынок',
  legacy: 'Обычные магазины',
};

const merchantTitle = (m: EconMerchant) => m.name ?? `Персонаж #${m.npc_id} (удалён)`;

/* ------------------------------------------------------------------ small pieces */

const StatusBadge = ({ m }: { m: EconMerchant }) =>
  m.living ? (
    <span className="inline-flex rounded-full border border-stat-energy/40 bg-stat-energy/10 px-2 py-0.5 text-stat-energy text-xs whitespace-nowrap">
      живой рынок
    </span>
  ) : (
    <span className="inline-flex flex-col gap-0.5 min-w-0">
      <span className="inline-flex self-start rounded-full border border-white/20 bg-white/[0.04] px-2 py-0.5 text-white/60 text-xs whitespace-nowrap">
        обычный магазин
      </span>
      <span className="text-white/40 text-xs break-words">{merchantReasonText(m.reason)}</span>
    </span>
  );

/** Cash vs the cash target (living merchants); a legacy merchant has no target. */
const CashBar = ({ m, format }: { m: EconMerchant; format: (n: number, short?: boolean) => string }) => {
  if (m.cash_target <= 0) {
    return (
      <span className="flex flex-col gap-0.5">
        <span className="text-white/80 whitespace-nowrap">{format(m.cash, true)}</span>
        <span className="text-white/30 text-xs">без нормы</span>
      </span>
    );
  }
  const share = m.cash / m.cash_target;
  const pct = Math.max(0, Math.min(100, share * 100));
  const tone = share >= 1 ? 'bg-stat-energy' : share >= CASH_LOW_SHARE ? 'bg-gold' : 'bg-site-red';
  return (
    <span className="flex flex-col gap-1 min-w-[120px]" title={`Касса ${format(m.cash)} из нормы ${format(m.cash_target)}`}>
      <span className="text-xs whitespace-nowrap">
        <span className="text-white/80">{format(m.cash, true)}</span>
        <span className="text-white/40"> / {format(m.cash_target, true)}</span>
      </span>
      <span className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden" aria-hidden="true">
        <span className={`block h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </span>
    </span>
  );
};

const LastTrade = ({ m, format }: { m: EconMerchant; format: (n: number, short?: boolean) => string }) => {
  const t = m.last_trade;
  if (!t) return <span className="text-white/30 text-xs">{m.living ? 'ещё не торговал' : '—'}</span>;
  return (
    <span className="flex flex-col gap-0.5 text-xs text-white/60">
      <span className="text-white/40">{formatDateTime(t.at)}</span>
      <span>
        продал {t.sold_items} шт. на <span className="text-white/80">{format(t.sold_value, true)}</span>
        {t.tax > 0 && <>, налог {format(t.tax, true)}</>}
      </span>
      <span>
        закупил {t.restock_items} шт. на <span className="text-white/80">{format(t.restock_value, true)}</span>
        {t.upkeep > 0 && <>, содержание {format(t.upkeep, true)}</>}
      </span>
    </span>
  );
};

const RowBadges = ({ row }: { row: EconMerchantRow }) => (
  <>
    {row.origin === ORIGIN_PLAYER && (
      <span className="inline-flex rounded-full border border-site-blue/40 bg-site-blue/10 px-2 py-0.5 text-site-blue text-[11px] whitespace-nowrap">
        скуплено у игроков
      </span>
    )}
    {row.off_market && (
      <span className="inline-flex rounded-full border border-white/20 px-2 py-0.5 text-white/50 text-[11px] whitespace-nowrap">
        вне рынка
      </span>
    )}
    {!row.is_active && (
      <span className="inline-flex rounded-full border border-site-red/40 px-2 py-0.5 text-site-red text-[11px] whitespace-nowrap">
        не продаётся
      </span>
    )}
  </>
);

interface RowsListProps {
  m: EconMerchant;
  groupName: (code: string | null) => string;
  format: (n: number, short?: boolean) => string;
}

/** The merchant's shop rows: base vs current prices, stock vs restock target. */
const RowsList = ({ m, groupName, format }: RowsListProps) => {
  if (m.rows.length === 0) return <p className="text-white/40 text-xs italic">В магазине нет товаров.</p>;

  const price = (base: number, current: number | null, market: boolean) =>
    market && current !== null && current !== base ? (
      <>
        <span className="text-white">{format(current, true)}</span>{' '}
        <span className="text-white/30 line-through">{format(base, true)}</span>
      </>
    ) : (
      <span className="text-white/80">{base > 0 ? format(base, true) : '—'}</span>
    );

  const stock = (row: EconMerchantRow) =>
    row.stock === null ? (
      <span className="text-white/50">без ограничений</span>
    ) : (
      <>
        <span className={row.stock === 0 ? 'text-site-red' : 'text-white/80'}>{row.stock}</span>
        <span className="text-white/40"> / {row.restock_target}</span>
      </>
    );

  return (
    <ul className="flex flex-col divide-y divide-white/[0.07]">
      <li className="hidden md:grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 pb-1.5 text-white/40 text-[11px] uppercase tracking-[0.06em]">
        <span>Предмет</span>
        <span>Группа</span>
        <span>Продаёт</span>
        <span>Скупает</span>
        <span>Запас / норма</span>
      </li>
      {m.rows.map((row) => (
        <li
          key={row.row_id}
          className="py-2 grid grid-cols-2 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs"
        >
          <span className="col-span-2 md:col-span-1 flex flex-wrap items-center gap-1.5 min-w-0">
            <span className="text-white break-words">{row.item_name ?? `Предмет #${row.item_id}`}</span>
            <RowBadges row={row} />
          </span>
          <span className="text-white/60 break-words">
            <span className="md:hidden text-white/40">Группа: </span>
            {groupName(row.group)}
          </span>
          <span className="whitespace-nowrap">
            <span className="md:hidden text-white/40">Продаёт: </span>
            {price(row.base_buy, row.ask, row.market)}
          </span>
          <span className="whitespace-nowrap">
            <span className="md:hidden text-white/40">Скупает: </span>
            {price(row.base_sell, row.bid, row.market)}
          </span>
          <span className="whitespace-nowrap">
            <span className="md:hidden text-white/40">Запас: </span>
            {stock(row)}
          </span>
        </li>
      ))}
    </ul>
  );
};

/* ------------------------------------------------------------------ fund dialog */

interface FundDialogProps {
  /** Region of the list filter, when one is chosen — the admin may limit the top-up to it. */
  region: { id: number; name: string } | null;
  livingCount: number;
  onClose: () => void;
  onDone: (result: EconMerchantFundResult) => void;
}

/** «Пополнить кассы торговцев»: one emission per region bringing living merchants up to their cash target. */
const FundDialog = ({ region, livingCount, onClose, onDone }: FundDialogProps) => {
  const [onlyRegion, setOnlyRegion] = useState(region !== null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  const trimmed = comment.trim();
  const commentValid = trimmed.length >= COMMENT_MIN && trimmed.length <= COMMENT_MAX;

  const submit = async () => {
    setBusy(true);
    try {
      const result = await postEconomyMerchantsFund({
        ...(region && onlyRegion ? { region_ids: [region.id] } : {}),
        comment: trimmed,
      });
      onDone(result);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось пополнить кассы торговцев'));
      setBusy(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      dismissible={!busy}
      title="Пополнить кассы торговцев"
      size="md"
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button
            type="button"
            className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
            disabled={!commentValid || busy}
            onClick={submit}
          >
            {busy ? 'Пополнение...' : 'Пополнить'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4 text-sm">
        <p className="text-white/80">
          Кассы живых торговцев будут доведены до нормы новыми деньгами (эмиссия, одна операция на регион). Торговцы,
          у которых касса уже не меньше нормы, пропускаются — повторное нажатие ничего не добавит.
        </p>
        <p className="text-white/50">Живых торговцев в списке: {livingCount}.</p>
        {region && (
          <label htmlFor="econ-fund-region" className="flex items-start gap-3 cursor-pointer select-none">
            <input
              id="econ-fund-region"
              type="checkbox"
              checked={onlyRegion}
              onChange={(e) => setOnlyRegion(e.target.checked)}
              className="w-4 h-4 mt-0.5 shrink-0 accent-gold"
            />
            <span className="flex flex-col gap-0.5">
              <span className="text-white">Только регион «{region.name}»</span>
              <span className="text-white/40 text-xs">Без галочки — все живые торговцы мира.</span>
            </span>
          </label>
        )}
        <div className="flex flex-col gap-1">
          <label htmlFor="econ-fund-comment" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Комментарий (обязательно)
          </label>
          <textarea
            id="econ-fund-comment"
            className="textarea-bordered w-full"
            rows={3}
            maxLength={COMMENT_MAX}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Причина: попадёт в журнал операций"
          />
          {comment !== '' && !commentValid && (
            <p className="text-site-red text-xs">От {COMMENT_MIN} до {COMMENT_MAX} символов</p>
          )}
        </div>
      </div>
    </ModalShell>
  );
};

/* ------------------------------------------------------------------ tab */

interface EconomyMerchantsProps {
  canSettings: boolean;
  canEmit: boolean;
  /** Called after the fund — it emits money, so the summary is refreshed. */
  onMoneyChanged: () => void;
}

/** «Торговцы» (FEAT-183): every NPC with a shop — status, cash vs target, stock, last background trade; cash top-up. */
const EconomyMerchants = ({ canSettings, canEmit, onMoneyChanged }: EconomyMerchantsProps) => {
  const { format } = useCurrency();
  const [data, setData] = useState<EconMerchantsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [regions, setRegions] = useState<EconRegionItem[]>([]);
  const [groupNames, setGroupNames] = useState<Record<string, string>>({});
  const [regionId, setRegionId] = useState('');
  const [living, setLiving] = useState<LivingFilter>('all');
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());
  const [fundOpen, setFundOpen] = useState(false);
  const [fundResult, setFundResult] = useState<EconMerchantFundResult | null>(null);

  const canFund = canSettings && canEmit;

  useEffect(() => {
    fetchEconomyRegions()
      .then(setRegions)
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить список регионов')));
    fetchEconomyGoodsGroups()
      .then((groups) => setGroupNames(Object.fromEntries(groups.map((g) => [g.code, g.name]))))
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить группы товаров')));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    fetchEconomyMerchants({
      region_id: regionId ? Number(regionId) : undefined,
      living: living === 'all' ? undefined : living === 'living',
    })
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить торговцев');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, [regionId, living]);

  useEffect(load, [load]);

  const sortedRegions = useMemo(
    () => [...regions].sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'ru')),
    [regions],
  );

  const regionName = (id: number) => regions.find((r) => r.region_id === id)?.name ?? `Регион #${id}`;
  const groupName = (code: string | null) => (code ? groupNames[code] ?? code : 'без группы');
  const merchantName = (npcId: number) => {
    const m = data?.items.find((x) => x.npc_id === npcId);
    return m ? merchantTitle(m) : `НПС #${npcId}`;
  };

  const toggle = (npcId: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(npcId)) next.delete(npcId);
      else next.add(npcId);
      return next;
    });

  const selectedRegion = regionId ? { id: Number(regionId), name: regionName(Number(regionId)) } : null;
  const items = data?.items ?? [];

  const regionCell = (m: EconMerchant) => (
    <>
      <span className="block text-white/80 break-words">
        {m.region_name ?? (m.region_id !== null ? `Регион #${m.region_id}` : 'без региона')}
      </span>
      {m.living && m.tax_rate !== null && (
        <span className="block text-white/40 text-xs">налог {formatPercent(m.tax_rate)}</span>
      )}
    </>
  );

  return (
    <div className="flex flex-col gap-5">
      <p className="text-white/50 text-sm max-w-3xl">
        НПС с магазином в регионе симуляции — живой торговец: цены следуют рынку региона, запас ограничен и
        пополняется со склада региона, жители покупают у него товар каждые 6 часов, а налог с выручки идёт в казну.
        Остальные — обычные магазины с ценами и запасом, заданными вручную.
      </p>

      {/* filters + actions */}
      <div className="flex flex-col lg:flex-row lg:items-end gap-4">
        <div className="flex flex-col gap-1 min-w-0 lg:w-64">
          <label htmlFor="econ-merchants-region" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Регион
          </label>
          <select
            id="econ-merchants-region"
            className="input-underline w-full"
            value={regionId}
            onChange={(e) => setRegionId(e.target.value)}
          >
            <option value="" className="bg-site-dark text-white">
              Все регионы
            </option>
            {sortedRegions.map((r) => (
              <option key={r.region_id} value={r.region_id} className="bg-site-dark text-white">
                {r.name ?? `Регион #${r.region_id}`}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-0 lg:w-56">
          <label htmlFor="econ-merchants-living" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Тип
          </label>
          <select
            id="econ-merchants-living"
            className="input-underline w-full"
            value={living}
            onChange={(e) => setLiving(e.target.value as LivingFilter)}
          >
            {(Object.keys(LIVING_FILTER_LABEL) as LivingFilter[]).map((k) => (
              <option key={k} value={k} className="bg-site-dark text-white">
                {LIVING_FILTER_LABEL[k]}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-3 lg:ml-auto">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
          {canFund && (
            <button
              type="button"
              className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
              onClick={() => setFundOpen(true)}
            >
              Пополнить кассы торговцев
            </button>
          )}
        </div>
      </div>

      {/* totals */}
      {data && (
        <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="bg-site-bg rounded-card border border-white/[0.07] px-4 py-3 flex flex-col gap-0.5">
            <dt className="text-white/50 text-xs uppercase tracking-[0.06em]">Торговцев</dt>
            <dd className="text-white text-lg">{data.totals.merchants}</dd>
          </div>
          <div className="bg-site-bg rounded-card border border-white/[0.07] px-4 py-3 flex flex-col gap-0.5">
            <dt className="text-white/50 text-xs uppercase tracking-[0.06em]">На живом рынке</dt>
            <dd className="text-white text-lg">{data.totals.living}</dd>
          </div>
          <div className="bg-site-bg rounded-card border border-white/[0.07] px-4 py-3 flex flex-col gap-0.5">
            <dt className="text-white/50 text-xs uppercase tracking-[0.06em]">Деньги в кассах</dt>
            <dd className="text-white text-lg">{format(data.totals.cash)}</dd>
          </div>
        </dl>
      )}

      {fundResult && (
        <div className="text-sm text-white/80 rounded-card border border-stat-energy/30 bg-stat-energy/[0.06] px-4 py-3 flex flex-col gap-1">
          <span>
            Пополнено касс: {fundResult.funded} из {fundResult.merchants}. Выпущено: {format(fundResult.emitted)}
            {fundResult.operation_ids.length > 0 && (
              <span className="text-white/50"> (операций: {fundResult.operation_ids.length})</span>
            )}
          </span>
          {fundResult.skipped.length > 0 && (
            <ul className="text-white/50 text-xs flex flex-col gap-0.5">
              {fundResult.skipped.map((s) => (
                <li key={s.npc_id} className="break-words">
                  {merchantName(s.npc_id)} — {merchantFundSkipText(s.reason)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {error && !data && <p className="text-site-red text-sm">{error}</p>}
      {!data && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {data && items.length === 0 && <p className="text-white/40 text-sm italic">Торговцев не найдено.</p>}

      {data && items.length > 0 && (
        <div className={`transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {/* Table — lg and up */}
          <div className="hidden lg:block bg-site-bg rounded-card border border-white/[0.07] px-4 py-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                  <th className="py-2 pr-3 font-normal">НПС</th>
                  <th className="py-2 pr-3 font-normal">Регион</th>
                  <th className="py-2 pr-3 font-normal">Статус</th>
                  <th className="py-2 pr-3 font-normal">Касса / норма</th>
                  <th className="py-2 pr-3 font-normal text-right">Товар на складе</th>
                  <th className="py-2 font-normal">Последняя торговля</th>
                </tr>
              </thead>
              <tbody>
                {items.map((m) => {
                  const open = expanded.has(m.npc_id);
                  return (
                    <Fragment key={m.npc_id}>
                      <tr
                        onClick={() => toggle(m.npc_id)}
                        className={`align-top cursor-pointer hover:bg-white/[0.04] transition-colors duration-200 ease-site ${
                          open ? '' : 'border-b border-white/[0.07] last:border-b-0'
                        }`}
                      >
                        <td className="py-2 pr-3">
                          <span className="flex items-start gap-1.5">
                            {open ? (
                              <ChevronDown size={15} className="text-gold shrink-0 mt-0.5" />
                            ) : (
                              <ChevronRight size={15} className="text-gold shrink-0 mt-0.5" />
                            )}
                            <span className="min-w-0">
                              <span className="block text-white break-words">{merchantTitle(m)}</span>
                              <span className="block text-white/40 text-xs">
                                #{m.npc_id} · товаров {m.rows.length}
                              </span>
                            </span>
                          </span>
                        </td>
                        <td className="py-2 pr-3">{regionCell(m)}</td>
                        <td className="py-2 pr-3 max-w-[220px]">
                          <StatusBadge m={m} />
                        </td>
                        <td className="py-2 pr-3">
                          <CashBar m={m} format={format} />
                        </td>
                        <td className="py-2 pr-3 text-right whitespace-nowrap text-white/80">
                          {format(m.stock_value, true)}
                        </td>
                        <td className="py-2">
                          <LastTrade m={m} format={format} />
                        </td>
                      </tr>
                      {open && (
                        <tr className="border-b border-white/[0.07] last:border-b-0">
                          <td colSpan={6} className="pb-3 pl-6 pr-2">
                            <RowsList m={m} groupName={groupName} format={format} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Cards — below lg */}
          <ul className="lg:hidden grid grid-cols-1 md:grid-cols-2 gap-3">
            {items.map((m) => {
              const open = expanded.has(m.npc_id);
              return (
                <li
                  key={m.npc_id}
                  className={`bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-2 text-sm min-w-0 ${
                    open ? 'md:col-span-2' : ''
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => toggle(m.npc_id)}
                    aria-expanded={open}
                    className="flex items-start gap-2 text-left w-full"
                  >
                    <span className="flex-1 min-w-0">
                      <span className="block text-white font-medium break-words">{merchantTitle(m)}</span>
                      <span className="block text-white/40 text-xs break-words">
                        {m.region_name ?? 'без региона'} · товаров {m.rows.length}
                        {m.living && m.tax_rate !== null && ` · налог ${formatPercent(m.tax_rate)}`}
                      </span>
                    </span>
                    {open ? (
                      <ChevronDown size={16} className="text-gold shrink-0 mt-0.5" />
                    ) : (
                      <ChevronRight size={16} className="text-gold shrink-0 mt-0.5" />
                    )}
                  </button>
                  <StatusBadge m={m} />
                  <span className="grid grid-cols-2 gap-3">
                    <span className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-white/40 text-xs">Касса / норма</span>
                      <CashBar m={m} format={format} />
                    </span>
                    <span className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-white/40 text-xs">Товар на складе</span>
                      <span className="text-white/80 text-xs">{format(m.stock_value, true)}</span>
                    </span>
                  </span>
                  <span className="flex flex-col gap-0.5">
                    <span className="text-white/40 text-xs">Последняя торговля</span>
                    <LastTrade m={m} format={format} />
                  </span>
                  {open && (
                    <div className="border-t border-white/10 pt-2">
                      <RowsList m={m} groupName={groupName} format={format} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {fundOpen && (
        <FundDialog
          region={selectedRegion}
          livingCount={data?.totals.living ?? 0}
          onClose={() => setFundOpen(false)}
          onDone={(result) => {
            setFundOpen(false);
            setFundResult(result);
            if (result.emitted > 0) {
              toast.success(`Кассы пополнены: ${result.funded}. Выпущено ${format(result.emitted)}`);
            } else {
              toast.success('Пополнять нечего: кассы уже не меньше нормы');
            }
            load();
            onMoneyChanged();
          }}
        />
      )}
    </div>
  );
};

export default EconomyMerchants;
