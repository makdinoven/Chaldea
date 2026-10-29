import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { ArrowLeft, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import {
  applyEconomyRegionTemplate,
  fetchEconomyRegion,
  fetchEconomyRegionHistory,
  fetchEconomyTemplates,
  putEconomyRegion,
} from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import type {
  EconRegionDetail,
  EconRegionGoods,
  EconRegionGoodsUpdate,
  EconRegionHistoryRow,
  EconRegionTemplate,
  EconRegionUpdate,
} from '../../../types/economy';
import { formatDateTime, formatDecimal, formatPercent } from './economyLabels';
import { HungerBadge, PriceMult, ScaleBar } from './regionBits';

const HISTORY_LIMIT = 40;
const MAX_POPULATION = 10_000_000;
const MAX_TAX_PERCENT = 50;
const MAX_PRODUCTION = 100_000;
const MAX_CONSUMPTION_MULT = 10;

interface GoodsDraft {
  production: string;
  consumption: string;
  stock: string;
  /** Stock is sent only when the admin touched it — a tick may have moved it since the page was loaded. */
  stockTouched: boolean;
}

interface Draft {
  template: string;
  population: string;
  taxPercent: string;
  stability: string;
  prosperity: string;
  goods: Record<string, GoodsDraft>;
}

const toDraft = (d: EconRegionDetail): Draft => ({
  template: d.template_code ?? '',
  population: String(d.population),
  taxPercent: String(Math.round(d.tax_rate * 10000) / 100),
  stability: String(Math.round(d.stability * 100) / 100),
  prosperity: String(Math.round(d.prosperity * 100) / 100),
  goods: Object.fromEntries(
    d.goods.map((g) => [
      g.group_code,
      {
        production: String(g.production_per_1000),
        consumption: String(g.consumption_mult),
        stock: String(Math.round(g.stock * 1000) / 1000),
        stockTouched: false,
      },
    ]),
  ),
});

const inRange = (text: string, min: number, max: number, integer = false): boolean => {
  if (text.trim() === '') return false;
  const n = Number(text);
  return Number.isFinite(n) && n >= min && n <= max && (!integer || Number.isInteger(n));
};

interface RegionEconomyEditorProps {
  regionId: number;
  canEdit: boolean;
  onBack: () => void;
  /** The list behind the editor should reload after a save. */
  onChanged: () => void;
}

const FieldLabel = ({ htmlFor, children }: { htmlFor: string; children: string }) => (
  <label htmlFor={htmlFor} className="text-white/60 text-xs uppercase tracking-[0.06em]">
    {children}
  </label>
);

const HistoryDetails = ({ row, groupNames }: { row: EconRegionHistoryRow; groupNames: Record<string, string> }) => (
  <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-6 gap-y-1 py-2 text-xs">
    {Object.entries(row.goods).map(([code, g]) => (
      <li key={code} className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-white/80 min-w-[120px]">{groupNames[code] ?? code}</span>
        <span className="text-white/50">запас {formatDecimal(g.stock, 1)}</span>
        <PriceMult mult={g.price_mult} />
        <span className="text-white/40">
          +{formatDecimal(g.produced, 1)} / −{formatDecimal(g.consumed, 1)}
        </span>
      </li>
    ))}
  </ul>
);

/** One region's economy: template, population, tax, stability/prosperity, the 12 goods and the tick history. */
const RegionEconomyEditor = ({ regionId, canEdit, onBack, onChanged }: RegionEconomyEditorProps) => {
  const { format } = useCurrency();
  const [detail, setDetail] = useState<EconRegionDetail | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [templates, setTemplates] = useState<EconRegionTemplate[]>([]);
  const [history, setHistory] = useState<EconRegionHistoryRow[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [resetStocks, setResetStocks] = useState(true);
  const [confirmApply, setConfirmApply] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const applyDetail = (d: EconRegionDetail) => {
    setDetail(d);
    setDraft(toDraft(d));
  };

  const loadHistory = useCallback(() => {
    fetchEconomyRegionHistory(regionId, HISTORY_LIMIT)
      .then((rows) => {
        setHistory(rows);
        setHistoryError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить историю региона');
        setHistory([]);
        setHistoryError(msg);
        toast.error(msg);
      });
  }, [regionId]);

  const load = useCallback(() => {
    setLoadError(null);
    fetchEconomyRegion(regionId)
      .then(applyDetail)
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить экономику региона');
        setLoadError(msg);
        toast.error(msg);
      });
    loadHistory();
  }, [regionId, loadHistory]);

  useEffect(load, [load]);

  useEffect(() => {
    let cancelled = false;
    fetchEconomyTemplates()
      .then((list) => {
        if (!cancelled) setTemplates([...list].sort((a, b) => a.sort_order - b.sort_order));
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить шаблоны регионов'));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const groupNames = useMemo(
    () => Object.fromEntries((detail?.goods ?? []).map((g) => [g.group_code, g.name])),
    [detail],
  );

  if (loadError && !detail) {
    return (
      <div className="flex flex-col gap-3">
        <button type="button" onClick={onBack} className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
          <ArrowLeft size={15} />
          Все регионы
        </button>
        <p className="text-site-red text-sm">{loadError}</p>
      </div>
    );
  }
  if (!detail || !draft) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const setGoods = (code: string, patch: Partial<GoodsDraft>) =>
    setDraft({ ...draft, goods: { ...draft.goods, [code]: { ...draft.goods[code], ...patch } } });

  const populationValid = inRange(draft.population, 0, MAX_POPULATION, true);
  const taxValid = inRange(draft.taxPercent, 0, MAX_TAX_PERCENT);
  const stabilityValid = inRange(draft.stability, 0, 100);
  const prosperityValid = inRange(draft.prosperity, 0, 100);
  const goodsErrors = detail.goods.filter((g) => {
    const d = draft.goods[g.group_code];
    return (
      !d ||
      !inRange(d.production, 0, MAX_PRODUCTION) ||
      !inRange(d.consumption, 0, MAX_CONSUMPTION_MULT) ||
      !inRange(d.stock, 0, Number.MAX_SAFE_INTEGER)
    );
  });
  const formValid = populationValid && taxValid && stabilityValid && prosperityValid && goodsErrors.length === 0;
  const templateChanged = (detail.template_code ?? '') !== draft.template;
  const hasGoods = detail.goods.length > 0;

  const save = async () => {
    const body: EconRegionUpdate = {
      template_code: draft.template || null,
      population: Number(draft.population),
      tax_rate: Math.round(Number(draft.taxPercent) * 100) / 10000,
    };
    // Stability / prosperity are moved by every tick — send them only when the admin changed them.
    if (Number(draft.stability) !== Math.round(detail.stability * 100) / 100) body.stability = Number(draft.stability);
    if (Number(draft.prosperity) !== Math.round(detail.prosperity * 100) / 100) body.prosperity = Number(draft.prosperity);
    // A region without goods rows gets them copied from the template by the backend.
    if (hasGoods) {
      body.goods = detail.goods.map((g): EconRegionGoodsUpdate => {
        const d = draft.goods[g.group_code];
        const row: EconRegionGoodsUpdate = {
          group_code: g.group_code,
          production_per_1000: Number(d.production),
          consumption_mult: Number(d.consumption),
        };
        if (d.stockTouched) row.stock = Number(d.stock);
        return row;
      });
    }
    setSaving(true);
    try {
      applyDetail(await putEconomyRegion(regionId, body));
      toast.success('Экономика региона сохранена');
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить экономику региона'));
    } finally {
      setSaving(false);
    }
  };

  const applyTemplate = async () => {
    setConfirmApply(false);
    setSaving(true);
    try {
      applyDetail(await applyEconomyRegionTemplate(regionId, { reset_stocks: resetStocks }));
      toast.success('Шаблон применён');
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось применить шаблон'));
    } finally {
      setSaving(false);
    }
  };

  const toggleHistory = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const numberInput = (
    id: string,
    value: string,
    onChange: (v: string) => void,
    valid: boolean,
    opts: { min: number; max?: number; step: number; widthClass?: string },
  ) => (
    <input
      id={id}
      type="number"
      inputMode="decimal"
      min={opts.min}
      max={opts.max}
      step={opts.step}
      className={`input-underline w-full ${opts.widthClass ?? ''} ${valid ? '' : '!border-site-red'}`}
      value={value}
      disabled={!canEdit}
      onChange={(e) => onChange(e.target.value)}
    />
  );

  const goodsReadOnly = (g: EconRegionGoods) => [
    { label: 'Норма', value: formatDecimal(g.norm_stock, 1) },
    { label: 'Произведено', value: formatDecimal(g.last_produced, 1) },
    { label: 'Потреблено', value: formatDecimal(g.last_consumed, 1) },
    { label: 'Спрос', value: formatDecimal(g.last_demand, 1) },
    { label: 'Испорчено', value: formatDecimal(g.last_spoiled, 1) },
  ];

  const lastFlows = [
    { label: 'Доход жителей', value: detail.last_income },
    { label: 'Налог', value: detail.last_tax },
    { label: 'Жалованье', value: detail.last_wages },
    { label: 'Грант страны', value: detail.last_grant },
  ];

  return (
    <div className="flex flex-col gap-5">
      <button type="button" onClick={onBack} className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />
        Все регионы
      </button>

      <div className="flex flex-col sm:flex-row sm:items-end gap-2">
        <div className="flex flex-col gap-0.5 min-w-0">
          <h2 className="gold-text text-xl sm:text-2xl font-semibold uppercase tracking-[0.06em] break-words">
            {detail.name ?? `Регион #${detail.region_id}`}
          </h2>
          <p className="text-white/50 text-sm">
            {detail.country_name ?? 'Без страны'} ·{' '}
            {detail.simulated ? 'в симуляции' : 'не участвует в симуляции (нужны шаблон и население)'}
            {detail.last_tick_at && ` · пересчёт ${formatDateTime(detail.last_tick_at)}`}
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="sm:ml-auto self-start inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site"
        >
          <RefreshCw size={14} />
          Обновить
        </button>
      </div>

      {/* State overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-1.5 min-w-0">
          <span className="text-white/50 text-[11px] sm:text-xs uppercase tracking-[0.06em]">Стабильность</span>
          <ScaleBar value={detail.stability} tone="stability" label="Стабильность" />
        </div>
        <div className="bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-1.5 min-w-0">
          <span className="text-white/50 text-[11px] sm:text-xs uppercase tracking-[0.06em]">Достаток</span>
          <ScaleBar value={detail.prosperity} tone="prosperity" label="Достаток" />
        </div>
        <div className="bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-1.5 min-w-0">
          <span className="text-white/50 text-[11px] sm:text-xs uppercase tracking-[0.06em]">Еда</span>
          <span className="flex flex-wrap items-center gap-2">
            <HungerBadge hunger={detail.hunger} simulated={detail.simulated} />
            {detail.simulated && (
              <span className="text-white/40 text-xs">прочее {formatPercent(detail.satisfaction, 0)}</span>
            )}
          </span>
        </div>
        <div className="bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-1 min-w-0 text-sm">
          <span className="text-white/50 text-[11px] sm:text-xs uppercase tracking-[0.06em]">Деньги</span>
          <span className="text-white/80 break-words">жители {format(detail.purse)}</span>
          <span className={`break-words ${detail.treasury < 0 ? 'text-site-red' : 'text-white/80'}`}>
            казна {format(detail.treasury)}
          </span>
          <span className="text-white/40 text-xs break-words">резерв казны {format(detail.treasury_target)}</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-white/50">
        <span className="uppercase tracking-[0.06em]">Последний пересчёт:</span>
        {lastFlows.map((f) => (
          <span key={f.label}>
            {f.label} <span className="text-white/80">{format(f.value)}</span>
          </span>
        ))}
      </div>

      {/* Main parameters */}
      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-5 min-w-0">
        <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Параметры</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-5">
          <div className="flex flex-col gap-1 min-w-0 lg:col-span-1">
            <FieldLabel htmlFor="econ-region-template">Шаблон</FieldLabel>
            <select
              id="econ-region-template"
              className="input-underline w-full"
              value={draft.template}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, template: e.target.value })}
            >
              <option value="" className="bg-site-dark text-white">Без шаблона (не симулируется)</option>
              {templates.map((t) => (
                <option key={t.code} value={t.code} className="bg-site-dark text-white">
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <FieldLabel htmlFor="econ-region-population">Население</FieldLabel>
            {numberInput('econ-region-population', draft.population, (v) => setDraft({ ...draft, population: v }), populationValid, {
              min: 0,
              max: MAX_POPULATION,
              step: 100,
            })}
            {!populationValid && <p className="text-site-red text-xs">Целое от 0 до 10 000 000</p>}
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <FieldLabel htmlFor="econ-region-tax">Налог с жителей, %</FieldLabel>
            {numberInput('econ-region-tax', draft.taxPercent, (v) => setDraft({ ...draft, taxPercent: v }), taxValid, {
              min: 0,
              max: MAX_TAX_PERCENT,
              step: 0.5,
            })}
            {!taxValid && <p className="text-site-red text-xs">От 0 до {MAX_TAX_PERCENT}%</p>}
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <FieldLabel htmlFor="econ-region-stability">Стабильность</FieldLabel>
            {numberInput('econ-region-stability', draft.stability, (v) => setDraft({ ...draft, stability: v }), stabilityValid, {
              min: 0,
              max: 100,
              step: 1,
            })}
            {!stabilityValid && <p className="text-site-red text-xs">От 0 до 100</p>}
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <FieldLabel htmlFor="econ-region-prosperity">Достаток</FieldLabel>
            {numberInput('econ-region-prosperity', draft.prosperity, (v) => setDraft({ ...draft, prosperity: v }), prosperityValid, {
              min: 0,
              max: 100,
              step: 1,
            })}
            {!prosperityValid && <p className="text-site-red text-xs">От 0 до 100</p>}
          </div>
        </div>

        {templateChanged && hasGoods && (
          <p className="field-hint">
            Шаблон сменится при сохранении, но товары региона останутся прежними. Чтобы скопировать товары нового
            шаблона, сохраните и нажмите «Применить шаблон».
          </p>
        )}
        {!hasGoods && draft.template && (
          <p className="field-hint">При сохранении товары региона будут скопированы из выбранного шаблона.</p>
        )}

        {canEdit ? (
          <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-3">
            <button
              type="button"
              className="btn-blue w-full sm:w-auto !px-6"
              disabled={!formValid || saving}
              onClick={save}
            >
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
            <button
              type="button"
              className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5"
              disabled={!detail.template_code || templateChanged || saving}
              title={templateChanged ? 'Сначала сохраните выбранный шаблон' : undefined}
              onClick={() => setConfirmApply(true)}
            >
              Применить шаблон
            </button>
            <label className="flex items-center gap-2 text-sm text-white/70 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={resetStocks}
                onChange={(e) => setResetStocks(e.target.checked)}
                className="w-4 h-4 shrink-0 accent-gold"
              />
              запасы — к норме
            </label>
          </div>
        ) : (
          <p className="field-hint">Изменять экономику региона может только администратор с правом «economy:settings».</p>
        )}
      </section>

      {/* Goods */}
      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-3 min-w-0">
        <div className="flex flex-col gap-1">
          <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Товары</h3>
          <p className="text-white/50 text-sm">
            Производство — единиц в сутки на 1000 жителей; потребление — множитель к норме группы. Остальное считает
            пересчёт: последние значения за один шаг (6 часов).
          </p>
        </div>
        {!hasGoods ? (
          <p className="text-white/40 text-sm italic">У региона ещё нет товаров — выберите шаблон и сохраните.</p>
        ) : (
          <>
            {/* Table — lg and up */}
            <div className="hidden lg:block overflow-x-auto gold-scrollbar">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                    <th className="py-2 pr-3 font-normal">Группа</th>
                    <th className="py-2 pr-3 font-normal">Произв./1000</th>
                    <th className="py-2 pr-3 font-normal">Потребл. ×</th>
                    <th className="py-2 pr-3 font-normal">Запас</th>
                    <th className="py-2 pr-3 font-normal text-right">Норма</th>
                    <th className="py-2 pr-3 font-normal text-right">Цена</th>
                    <th className="py-2 pr-3 font-normal text-right">Произв.</th>
                    <th className="py-2 pr-3 font-normal text-right">Потребл.</th>
                    <th className="py-2 pr-3 font-normal text-right">Спрос</th>
                    <th className="py-2 font-normal text-right">Испорч.</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.goods.map((g) => {
                    const d = draft.goods[g.group_code];
                    return (
                      <tr key={g.group_code} className="border-b border-white/[0.07] last:border-b-0">
                        <td className="py-1.5 pr-3 text-white">{g.name}</td>
                        <td className="py-1.5 pr-3 w-28">
                          {numberInput(`econ-g-${g.group_code}-prod`, d.production, (v) => setGoods(g.group_code, { production: v }),
                            inRange(d.production, 0, MAX_PRODUCTION), { min: 0, max: MAX_PRODUCTION, step: 1 })}
                        </td>
                        <td className="py-1.5 pr-3 w-24">
                          {numberInput(`econ-g-${g.group_code}-cons`, d.consumption, (v) => setGoods(g.group_code, { consumption: v }),
                            inRange(d.consumption, 0, MAX_CONSUMPTION_MULT), { min: 0, max: MAX_CONSUMPTION_MULT, step: 0.1 })}
                        </td>
                        <td className="py-1.5 pr-3 w-28">
                          {numberInput(`econ-g-${g.group_code}-stock`, d.stock, (v) => setGoods(g.group_code, { stock: v, stockTouched: true }),
                            inRange(d.stock, 0, Number.MAX_SAFE_INTEGER), { min: 0, step: 1 })}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-white/70">{formatDecimal(g.norm_stock, 1)}</td>
                        <td className="py-1.5 pr-3 text-right whitespace-nowrap">
                          <PriceMult mult={g.price_mult} />
                          {g.prev_price_mult !== g.price_mult && (
                            <span className="text-white/30 text-xs ml-1">(было ×{formatDecimal(g.prev_price_mult, 2)})</span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-white/70">{formatDecimal(g.last_produced, 1)}</td>
                        <td className="py-1.5 pr-3 text-right text-white/70">{formatDecimal(g.last_consumed, 1)}</td>
                        <td className="py-1.5 pr-3 text-right text-white/70">{formatDecimal(g.last_demand, 1)}</td>
                        <td className="py-1.5 text-right text-white/70">{formatDecimal(g.last_spoiled, 1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Cards — below lg */}
            <ul className="lg:hidden grid grid-cols-1 md:grid-cols-2 gap-3">
              {detail.goods.map((g) => {
                const d = draft.goods[g.group_code];
                return (
                  <li key={g.group_code} className="rounded-card border border-white/[0.07] p-3 flex flex-col gap-3">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-white text-sm font-medium">{g.name}</span>
                      <span className="text-sm">
                        <PriceMult mult={g.price_mult} />
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="flex flex-col gap-1 min-w-0">
                        <FieldLabel htmlFor={`econ-gm-${g.group_code}-prod`}>Произв.</FieldLabel>
                        {numberInput(`econ-gm-${g.group_code}-prod`, d.production, (v) => setGoods(g.group_code, { production: v }),
                          inRange(d.production, 0, MAX_PRODUCTION), { min: 0, max: MAX_PRODUCTION, step: 1 })}
                      </div>
                      <div className="flex flex-col gap-1 min-w-0">
                        <FieldLabel htmlFor={`econ-gm-${g.group_code}-cons`}>Потр. ×</FieldLabel>
                        {numberInput(`econ-gm-${g.group_code}-cons`, d.consumption, (v) => setGoods(g.group_code, { consumption: v }),
                          inRange(d.consumption, 0, MAX_CONSUMPTION_MULT), { min: 0, max: MAX_CONSUMPTION_MULT, step: 0.1 })}
                      </div>
                      <div className="flex flex-col gap-1 min-w-0">
                        <FieldLabel htmlFor={`econ-gm-${g.group_code}-stock`}>Запас</FieldLabel>
                        {numberInput(`econ-gm-${g.group_code}-stock`, d.stock, (v) => setGoods(g.group_code, { stock: v, stockTouched: true }),
                          inRange(d.stock, 0, Number.MAX_SAFE_INTEGER), { min: 0, step: 1 })}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-white/50">
                      {goodsReadOnly(g).map((f) => (
                        <span key={f.label}>
                          {f.label} <span className="text-white/80">{f.value}</span>
                        </span>
                      ))}
                    </div>
                  </li>
                );
              })}
            </ul>
            {goodsErrors.length > 0 && (
              <p className="text-site-red text-xs">
                Проверьте значения: производство 0–{MAX_PRODUCTION.toLocaleString('ru-RU')}, потребление 0–
                {MAX_CONSUMPTION_MULT}, запас ≥ 0.
              </p>
            )}
          </>
        )}
      </section>

      {/* History */}
      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-3 min-w-0">
        <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">История пересчётов</h3>
        {historyError && <p className="text-site-red text-sm">{historyError}</p>}
        {!history && !historyError && <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
        {history && history.length === 0 && !historyError && (
          <p className="text-white/40 text-sm italic">Пересчётов ещё не было.</p>
        )}
        {history && history.length > 0 && (
          <>
            <div className="hidden md:block overflow-x-auto gold-scrollbar">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                    <th className="py-2 pr-3 font-normal w-8" />
                    <th className="py-2 pr-3 font-normal">Когда</th>
                    <th className="py-2 pr-3 font-normal text-right">Стаб.</th>
                    <th className="py-2 pr-3 font-normal text-right">Дост.</th>
                    <th className="py-2 pr-3 font-normal text-right">Голод</th>
                    <th className="py-2 pr-3 font-normal text-right">Налог</th>
                    <th className="py-2 pr-3 font-normal text-right">Жалованье</th>
                    <th className="py-2 pr-3 font-normal text-right">Грант</th>
                    <th className="py-2 pr-3 font-normal text-right">Жители</th>
                    <th className="py-2 font-normal text-right">Казна</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => {
                    const isOpen = expanded.has(h.id);
                    return (
                      <Fragment key={h.id}>
                        <tr
                          onClick={() => toggleHistory(h.id)}
                          className="border-b border-white/[0.07] cursor-pointer hover:bg-white/[0.04] transition-colors duration-200 ease-site"
                        >
                          <td className="py-1.5 pr-3 text-gold">{isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</td>
                          <td className="py-1.5 pr-3 text-white/70 whitespace-nowrap">{formatDateTime(h.created_at)}</td>
                          <td className="py-1.5 pr-3 text-right text-white/80">{formatDecimal(h.stability, 1)}</td>
                          <td className="py-1.5 pr-3 text-right text-white/80">{formatDecimal(h.prosperity, 1)}</td>
                          <td className={`py-1.5 pr-3 text-right ${h.hunger >= 0.15 ? 'text-site-red' : 'text-white/80'}`}>
                            {formatPercent(h.hunger, 0)}
                          </td>
                          <td className="py-1.5 pr-3 text-right text-white/80 whitespace-nowrap">{format(h.tax)}</td>
                          <td className="py-1.5 pr-3 text-right text-white/80 whitespace-nowrap">{format(h.wages)}</td>
                          <td className="py-1.5 pr-3 text-right text-white/80 whitespace-nowrap">{format(h.grant_amount)}</td>
                          <td className="py-1.5 pr-3 text-right text-white/80 whitespace-nowrap">{format(h.purse)}</td>
                          <td className={`py-1.5 text-right whitespace-nowrap ${h.treasury < 0 ? 'text-site-red' : 'text-white/80'}`}>
                            {format(h.treasury)}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="border-b border-white/[0.07]">
                            <td />
                            <td colSpan={9}>
                              <HistoryDetails row={h} groupNames={groupNames} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <ul className="md:hidden flex flex-col gap-2">
              {history.map((h) => {
                const isOpen = expanded.has(h.id);
                return (
                  <li key={h.id} className="rounded-card border border-white/[0.07] p-3">
                    <button type="button" className="w-full text-left flex items-start gap-2" onClick={() => toggleHistory(h.id)} aria-expanded={isOpen}>
                      {isOpen ? <ChevronDown size={16} className="text-gold mt-0.5 shrink-0" /> : <ChevronRight size={16} className="text-gold mt-0.5 shrink-0" />}
                      <span className="flex-1 min-w-0 flex flex-col gap-0.5 text-xs">
                        <span className="text-white text-sm">{formatDateTime(h.created_at)}</span>
                        <span className="text-white/50">
                          стаб. {formatDecimal(h.stability, 1)} · дост. {formatDecimal(h.prosperity, 1)} · голод {formatPercent(h.hunger, 0)}
                        </span>
                        <span className="text-white/50 break-words">
                          налог {format(h.tax)} · жалованье {format(h.wages)} · грант {format(h.grant_amount)}
                        </span>
                        <span className="text-white/50 break-words">
                          жители {format(h.purse)} · казна {format(h.treasury)}
                        </span>
                      </span>
                    </button>
                    {isOpen && <HistoryDetails row={h} groupNames={groupNames} />}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </section>

      {confirmApply && (
        <ConfirmDialog
          title="Применить шаблон"
          message={`Производство, потребление и налог региона будут взяты из шаблона «${
            detail.template_name ?? detail.template_code
          }»${resetStocks ? ', запасы выставлены в норму' : ''}. Население не меняется. Ручные правки товаров будут потеряны.`}
          confirmLabel="Применить"
          danger
          onConfirm={applyTemplate}
          onCancel={() => setConfirmApply(false)}
        />
      )}
    </div>
  );
};

export default RegionEconomyEditor;
