import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
import { CheckCircle2, RefreshCw, TriangleAlert } from 'lucide-react';
import {
  fetchCaravanOverview,
  fetchCaravans,
  fetchEconomyGoodsGroups,
  fetchEconomyRegions,
  patchEconomySimParams,
  putTradePair,
} from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import type {
  CaravanList,
  CaravanOverview,
  CaravanParams,
  CaravanRow,
  CaravanStatus,
  CaravanStatusFilter,
  EconGoodsGroup,
  EconRegionItem,
  EconSimParams,
  TradePair,
} from '../../../types/economy';
import { formatDateTime, formatDecimal, formatQty } from './economyLabels';
import { FieldHint, SimParamHint } from './ParamHint';

/* ------------------------------------------------------------------------------------- constants */

type CaravanParamKey = keyof CaravanParams & keyof EconSimParams;

/** Bounds and defaults of the caravan sim params — mirror `ECON_SIM_PARAM_BOUNDS` (feature file 3.10). */
interface CaravanParamDef {
  key: CaravanParamKey;
  label: string;
  def: number;
  min: number;
  max: number;
  integer?: boolean;
}

const CARAVAN_PARAMS: CaravanParamDef[] = [
  { key: 'caravan_surplus_share', label: 'Доля излишка продавца за пересчёт', def: 0.25, min: 0, max: 1 },
  { key: 'caravan_purse_share', label: 'Доля кошелька покупателя за пересчёт', def: 0.25, min: 0, max: 1 },
  { key: 'caravan_treasury_food_share', label: 'Доля казны на доплату за еду', def: 0.5, min: 0, max: 1 },
  { key: 'caravan_travel_domestic', label: 'В пути внутри страны, пересчётов', def: 1, min: 1, max: 8, integer: true },
  { key: 'caravan_travel_foreign', label: 'В пути между странами, пересчётов', def: 2, min: 1, max: 8, integer: true },
  { key: 'caravan_min_value', label: 'Минимальная сделка, денег', def: 10, min: 1, max: 1_000_000, integer: true },
  { key: 'caravan_max_per_run', label: 'Предел караванов за пересчёт', def: 200, min: 1, max: 5000, integer: true },
];

const ENABLED_DEF = { def: 1, min: 0, max: 1 };

const DUTY_MIN = 0;
const DUTY_MAX = 100;
const DEFAULT_DUTY = 10;
const PAIRS_PAGE = 30;
const LIST_PAGE = 20;

const STATUS_TABS: { id: CaravanStatusFilter; label: string }[] = [
  { id: 'in_transit', label: 'В пути' },
  { id: 'delivered', label: 'Доставлены' },
  { id: 'cancelled', label: 'Отменены' },
  { id: 'all', label: 'Все' },
];

const STATUS_LABEL: Record<CaravanStatus, string> = {
  in_transit: 'в пути',
  delivered: 'доставлен',
  cancelled: 'отменён',
};

const CANCEL_REASON_LABEL: Record<string, string> = {
  destination_left: 'регион назначения вышел из пересчёта',
  destination_deleted: 'регион назначения удалён',
};

const SELECT_CLASS =
  'w-full bg-black/30 border border-white/20 rounded px-2 py-1.5 text-white text-sm focus:border-gold/50 outline-none disabled:opacity-40';

const fmtNum = (n: number) => String(n).replace('.', ',');

const parseNum = (raw: string): number => {
  const v = raw.trim().replace(',', '.');
  return v === '' ? Number.NaN : Number(v);
};

const paramError = (p: { min: number; max: number; integer?: boolean }, raw: string): string | null => {
  const n = parseNum(raw);
  if (!Number.isFinite(n)) return 'Введите число';
  if (p.integer && !Number.isInteger(n)) return 'Только целое число';
  if (n < p.min || n > p.max) return `От ${fmtNum(p.min)} до ${fmtNum(p.max)}`;
  return null;
};

/** Duty: 0…100 with up to two decimals (the backend rounds to 2). */
const dutyError = (raw: string): string | null => {
  const n = parseNum(raw);
  if (!Number.isFinite(n)) return 'Введите число';
  if (n < DUTY_MIN || n > DUTY_MAX) return `От ${DUTY_MIN} до ${DUTY_MAX}`;
  return null;
};

const regionName = (name: string | null, id: number) => name ?? `Регион #${id} (удалён)`;
const countryName = (name: string | null, id: number) => name ?? `Страна #${id} (удалена)`;

/* ------------------------------------------------------------------------------------- small parts */

const Card = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <section className={`bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0 ${className}`}>
    {children}
  </section>
);

const CardTitle = ({ children }: { children: ReactNode }) => (
  <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">{children}</h2>
);

const Warning = ({ children }: { children: ReactNode }) => (
  <p className="text-gold/90 text-xs sm:text-sm rounded-card border border-gold/30 bg-gold/[0.06] px-3 py-2">{children}</p>
);

const Spinner = () => <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

const Stat = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex flex-col gap-0.5 min-w-0 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2">
    <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">{label}</span>
    <span className="text-white text-sm break-words">{children}</span>
  </div>
);

const StatusBadge = ({ status }: { status: CaravanStatus }) => {
  const cls = {
    in_transit: 'border-site-blue/50 bg-site-blue/10 text-site-blue',
    delivered: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy',
    cancelled: 'border-site-red/50 bg-site-red/10 text-site-red',
  }[status] ?? 'border-white/20 text-white/50';
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap ${cls}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
};

/* ------------------------------------------------------------------------------------- state card */

const StateCard = ({ data, format }: { data: CaravanOverview; format: (n: number) => string }) => {
  const { escrow, in_transit: transit, last_run: last } = data;
  return (
    <Card>
      <CardTitle>Состояние</CardTitle>
      {escrow.ok ? (
        <p className="inline-flex items-center gap-2 self-start rounded-full border border-stat-energy/40 bg-stat-energy/10 px-3 py-1.5 text-stat-energy text-sm">
          <CheckCircle2 size={16} className="shrink-0" />
          Счёт «Караваны в пути» сходится: {format(escrow.balance)}
        </p>
      ) : (
        <p className="inline-flex items-start gap-2 self-start rounded-card border border-site-red/50 bg-site-red/10 px-3 py-1.5 text-site-red text-sm">
          <TriangleAlert size={16} className="shrink-0 mt-0.5" />
          Счёт «Караваны в пути» расходится: ожидается {format(escrow.expected)}, на счёте {format(escrow.balance)}
        </p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Караванов в пути">{transit.count}</Stat>
        <Stat label="Товара в пути на сумму">
          {format(transit.value)}
          {transit.duty > 0 && <span className="text-white/50"> + пошлина {format(transit.duty)}</span>}
        </Stat>
        <Stat label="Последний пересчёт">
          {last ? (
            <>
              №{last.run_id}: отправлено {last.dispatched}, доставлено {last.delivered}
              {last.cancelled > 0 && <span className="text-site-red">, отменено {last.cancelled}</span>}
            </>
          ) : (
            <span className="text-white/50">ещё не было</span>
          )}
        </Stat>
        <Stat label="Стран / участвующих регионов">
          {data.countries.length} / {data.countries.reduce((s, c) => s + c.participating_regions, 0)}
        </Stat>
      </div>
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- params card */

interface ParamsCardProps {
  params: CaravanParams;
  canEdit: boolean;
  onSaved: () => void;
}

const ParamsCard = ({ params, canEdit, onSaved }: ParamsCardProps) => {
  const toForm = (p: CaravanParams) =>
    Object.fromEntries(CARAVAN_PARAMS.map((d) => [d.key, fmtNum(p[d.key] ?? d.def)])) as Record<CaravanParamKey, string>;
  const [form, setForm] = useState(() => toForm(params));
  const [enabled, setEnabled] = useState((params.caravans_enabled ?? ENABLED_DEF.def) === 1);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(toForm(params));
    setEnabled((params.caravans_enabled ?? ENABLED_DEF.def) === 1);
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  const errors = Object.fromEntries(CARAVAN_PARAMS.map((d) => [d.key, paramError(d, form[d.key])])) as Record<
    CaravanParamKey,
    string | null
  >;
  const changed = CARAVAN_PARAMS.filter((d) => parseNum(form[d.key]) !== (params[d.key] ?? d.def));
  const enabledChanged = (enabled ? 1 : 0) !== (params.caravans_enabled ?? ENABLED_DEF.def);
  const valid = CARAVAN_PARAMS.every((d) => errors[d.key] === null);

  const save = async () => {
    setSaving(true);
    try {
      const patch: Partial<EconSimParams> = {};
      changed.forEach((d) => {
        patch[d.key] = parseNum(form[d.key]);
      });
      if (enabledChanged) patch.caravans_enabled = enabled ? 1 : 0;
      await patchEconomySimParams(patch);
      toast.success('Параметры караванов сохранены');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить параметры караванов'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-col gap-1">
        <CardTitle>Параметры</CardTitle>
        <p className="text-white/50 text-sm">Общие для всего мира. Действуют со следующего пересчёта.</p>
      </div>
      <div className="flex flex-col gap-1">
        <span className="flex items-center gap-1">
          <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Караваны</span>
          <SimParamHint param="caravans_enabled" label="Караваны включены" numbers={ENABLED_DEF} />
        </span>
        <label className="flex items-center gap-2 text-sm text-white cursor-pointer py-1.5 self-start">
          <input
            type="checkbox"
            className="accent-gold w-4 h-4"
            checked={enabled}
            disabled={!canEdit || saving}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {enabled ? 'Отправляются' : 'Новые не отправляются (идущие доезжают)'}
        </label>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {CARAVAN_PARAMS.map((d) => (
          <div key={d.key} className="flex flex-col gap-1 min-w-0">
            <span className="flex items-center gap-1 min-w-0">
              <label htmlFor={`caravan-param-${d.key}`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
                {d.label}
              </label>
              <SimParamHint param={d.key} label={d.label} numbers={{ def: d.def, min: d.min, max: d.max }} />
            </span>
            <input
              id={`caravan-param-${d.key}`}
              type="text"
              inputMode={d.integer ? 'numeric' : 'decimal'}
              className="input-underline w-full"
              value={form[d.key]}
              disabled={!canEdit || saving}
              onChange={(e) => setForm({ ...form, [d.key]: e.target.value })}
            />
            {errors[d.key] && <p className="text-site-red text-xs">{errors[d.key]}</p>}
          </div>
        ))}
      </div>
      {canEdit ? (
        <button
          type="button"
          className="btn-blue w-full sm:w-auto sm:self-start !px-6"
          disabled={!valid || (changed.length === 0 && !enabledChanged) || saving}
          onClick={() => void save()}
        >
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      ) : (
        <p className="field-hint">Изменять параметры может администратор с правом «economy:settings».</p>
      )}
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- trade pairs */

interface PairRowProps {
  pair: TradePair;
  canEdit: boolean;
  onSaved: (p: TradePair) => void;
}

const PairRow = ({ pair, canEdit, onSaved }: PairRowProps) => {
  const [enabled, setEnabled] = useState(pair.is_enabled);
  const [duty, setDuty] = useState(fmtNum(pair.duty_pct));
  const [saving, setSaving] = useState(false);

  const err = dutyError(duty);
  const dutyNum = parseNum(duty);
  const dirty = enabled !== pair.is_enabled || (err === null && dutyNum !== pair.duty_pct);
  const nameA = countryName(pair.name_a, pair.country_a);
  const nameB = countryName(pair.name_b, pair.country_b);

  const save = async () => {
    setSaving(true);
    try {
      const saved = await putTradePair({
        country_a: pair.country_a,
        country_b: pair.country_b,
        is_enabled: enabled,
        duty_pct: Math.round(dutyNum * 100) / 100,
      });
      toast.success(
        `«${nameA}» ↔ «${nameB}»: ${saved.is_enabled ? `торгуют, пошлина ${formatDecimal(saved.duty_pct)} %` : 'не торгуют'}`,
      );
      onSaved(saved);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить торговлю между странами'));
    } finally {
      setSaving(false);
    }
  };

  const fieldId = `pair-${pair.country_a}-${pair.country_b}`;

  return (
    <li className="flex flex-col md:flex-row md:flex-wrap md:items-center gap-3 rounded-card border border-white/10 bg-white/[0.03] p-3 min-w-0">
      <div className="flex flex-col min-w-0 md:flex-1">
        <span className="text-white text-sm font-medium break-words">
          {nameA} <span className="text-gold/70">↔</span> {nameB}
        </span>
        <span className={`text-xs ${pair.is_enabled ? 'text-stat-energy' : 'text-white/40'}`}>
          {pair.is_enabled ? `торгуют · пошлина ${formatDecimal(pair.duty_pct)} %` : 'не торгуют'}
          {pair.updated_at && <span className="text-white/40"> · изменено {formatDateTime(pair.updated_at)}</span>}
        </span>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-2 text-sm text-white cursor-pointer pb-1">
          <input
            type="checkbox"
            className="accent-gold w-4 h-4"
            checked={enabled}
            disabled={!canEdit || saving}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          торгуют
        </label>
        <div className="flex flex-col gap-0.5 w-28">
          <span className="flex items-center gap-1">
            <label htmlFor={fieldId} className="text-white/50 text-[11px] uppercase tracking-wide">
              Пошлина, %
            </label>
            <FieldHint field="trade_pair_duty" label="Пошлина, %" />
          </span>
          <input
            id={fieldId}
            type="text"
            inputMode="decimal"
            className="input-underline !text-sm w-full"
            value={duty}
            disabled={!canEdit || saving}
            onChange={(e) => setDuty(e.target.value.slice(0, 6))}
          />
        </div>
        {canEdit && (
          <button
            type="button"
            className="btn-blue !px-4 !py-1.5 !text-sm"
            disabled={!dirty || err !== null || saving}
            onClick={() => void save()}
          >
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        )}
      </div>
      {err && <p className="text-site-red text-xs md:basis-full">{err}</p>}
    </li>
  );
};

interface PairsCardProps {
  data: CaravanOverview;
  canEdit: boolean;
  onSaved: (p: TradePair) => void;
}

const PairsCard = ({ data, canEdit, onSaved }: PairsCardProps) => {
  const [query, setQuery] = useState('');
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [shown, setShown] = useState(PAIRS_PAGE);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.pairs.filter((p) => {
      if (onlyOpen && !p.is_enabled) return false;
      if (!q) return true;
      return (p.name_a ?? '').toLowerCase().includes(q) || (p.name_b ?? '').toLowerCase().includes(q);
    });
  }, [data.pairs, query, onlyOpen]);

  useEffect(() => setShown(PAIRS_PAGE), [query, onlyOpen]);

  const openCount = data.pairs.filter((p) => p.is_enabled).length;

  return (
    <Card>
      <div className="flex flex-col gap-1">
        <span className="flex items-center gap-1">
          <CardTitle>Торговля между странами</CardTitle>
          <FieldHint field="trade_pair_enabled" label="Торгуют" />
        </span>
        <p className="text-white/50 text-sm">
          Одна галочка на пару — в обе стороны. По умолчанию страны не торгуют, пошлина {DEFAULT_DUTY} %. Внутри
          страны караваны ходят всегда, пошлины нет. Открыто пар: {openCount} из {data.pairs.length}.
        </p>
      </div>
      {data.countries.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {data.countries.map((c) => (
            <li
              key={c.country_id}
              className="rounded-full border border-white/15 px-2.5 py-0.5 text-[11px] text-white/70"
              title="Регионов, участвующих в пересчёте"
            >
              {c.name}: {c.participating_regions}
            </li>
          ))}
        </ul>
      )}
      {data.pairs.length === 0 ? (
        <p className="text-white/40 text-sm">
          {data.countries.length < 2 ? 'Стран меньше двух — торговать между странами некому.' : 'Пар стран нет.'}
        </p>
      ) : (
        <>
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <input
              type="search"
              className="input-underline w-full sm:max-w-[320px]"
              placeholder="Поиск по названию страны"
              maxLength={100}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              type="button"
              onClick={() => setOnlyOpen((v) => !v)}
              className={`chip-outline rounded-full px-3 py-1 text-xs self-start sm:self-auto ${onlyOpen ? 'chip-outline-active' : ''}`}
            >
              Только торгующие
            </button>
          </div>
          {filtered.length === 0 ? (
            <p className="text-white/40 text-sm">Ничего не найдено.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {filtered.slice(0, shown).map((p) => (
                <PairRow
                  key={`${p.country_a}-${p.country_b}-${p.is_enabled}-${p.duty_pct}`}
                  pair={p}
                  canEdit={canEdit}
                  onSaved={onSaved}
                />
              ))}
            </ul>
          )}
          {filtered.length > shown && (
            <button type="button" className="btn-line self-start" onClick={() => setShown((n) => n + PAIRS_PAGE)}>
              Показать ещё ({filtered.length - shown})
            </button>
          )}
        </>
      )}
      {!canEdit && <p className="field-hint">Открывать торговлю может администратор с правом «economy:settings».</p>}
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- caravans list */

const routeText = (c: CaravanRow) => {
  const from = regionName(c.from_region_name, c.from_region_id);
  const to = regionName(c.to_region_name, c.to_region_id);
  const foreign = c.from_country_id !== c.to_country_id;
  return {
    from: foreign ? `${from} (${countryName(c.from_country_name, c.from_country_id)})` : from,
    to: foreign ? `${to} (${countryName(c.to_country_name, c.to_country_id)})` : to,
  };
};

const resultText = (c: CaravanRow): string => {
  if (c.status === 'in_transit') return c.runs_left > 0 ? `ещё пересчётов: ${c.runs_left}` : 'приедет в следующем пересчёте';
  if (c.status === 'delivered') return c.finished_run_id ? `доставлен в пересчёте №${c.finished_run_id}` : 'доставлен';
  const reason = (c.cancel_reason && CANCEL_REASON_LABEL[c.cancel_reason]) || c.cancel_reason || 'причина неизвестна';
  const goods = c.goods_returned === false ? 'товар списан' : 'товар вернулся продавцу';
  return `${reason}; ${goods}, деньги возвращены покупателю`;
};

const CaravanItem = ({ c, format }: { c: CaravanRow; format: (n: number) => string }) => {
  const route = routeText(c);
  return (
    <li className="flex flex-col gap-2 rounded-card border border-white/10 bg-white/[0.03] p-3 min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={c.status} />
        <span className="text-white text-sm font-medium">{c.group_name ?? c.group_code}</span>
        <span className="text-white/60 text-sm">{formatQty(c.units)} ед.</span>
        <span className="text-white/40 text-xs ml-auto">
          #{c.id} · {formatDateTime(c.created_at)}
        </span>
      </div>
      <p className="text-white/80 text-sm break-words">
        {route.from} <span className="text-gold/70">→</span> {route.to}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-4 gap-y-1 text-xs text-white/60">
        <span>
          Цена: <span className="text-white">{format(c.value)}</span> ({formatDecimal(c.unit_price, 4)} за ед.)
        </span>
        <span>
          Пошлина:{' '}
          <span className="text-white">{c.duty > 0 ? `${format(c.duty)} (${formatDecimal(c.duty_pct)} %)` : 'нет'}</span>
        </span>
        <span>
          Платили: жители <span className="text-white">{format(c.paid_purse)}</span>
          {c.paid_treasury > 0 && (
            <>
              , казна <span className="text-white">{format(c.paid_treasury)}</span>
            </>
          )}
        </span>
        <span>
          В пути: {c.travel_runs} пересч. · отправлен в №{c.dispatch_run_id}
        </span>
      </div>
      <p className={`text-xs ${c.status === 'cancelled' ? 'text-site-red' : 'text-white/50'}`}>
        {resultText(c)}
        {c.finished_at && ` · ${formatDateTime(c.finished_at)}`}
      </p>
    </li>
  );
};

const CaravansCard = ({ format, reloadKey }: { format: (n: number) => string; reloadKey: number }) => {
  const [status, setStatus] = useState<CaravanStatusFilter>('in_transit');
  const [regionId, setRegionId] = useState('');
  const [group, setGroup] = useState('');
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<CaravanList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [regions, setRegions] = useState<EconRegionItem[]>([]);
  const [groups, setGroups] = useState<EconGoodsGroup[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([fetchEconomyRegions(), fetchEconomyGoodsGroups()]).then(([r, g]) => {
      if (cancelled) return;
      if (r.status === 'fulfilled') setRegions(r.value);
      else toast.error(apiErrorMessage(r.reason, 'Не удалось загрузить регионы для фильтра'));
      if (g.status === 'fulfilled') setGroups(g.value);
      else toast.error(apiErrorMessage(g.reason, 'Не удалось загрузить группы товаров для фильтра'));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchCaravans({
      status,
      region_id: regionId === '' ? undefined : Number(regionId),
      group_code: group || undefined,
      limit: LIST_PAGE,
      offset,
    })
      .then((res) => {
        if (cancelled) return;
        setList(res);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить караваны');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status, regionId, group, offset, reloadKey]);

  const changeFilter = (fn: () => void) => {
    fn();
    setOffset(0);
  };

  const total = list?.total ?? 0;
  const page = Math.floor(offset / LIST_PAGE) + 1;
  const pages = Math.max(1, Math.ceil(total / LIST_PAGE));
  const sortedRegions = useMemo(
    () => [...regions].sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'ru')),
    [regions],
  );

  return (
    <Card>
      <div className="flex flex-col gap-1">
        <CardTitle>Караваны</CardTitle>
        <p className="text-white/50 text-sm">Новые сверху. Регион в фильтре — откуда или куда.</p>
      </div>
      <div className="flex gap-1 sm:gap-2 border-b border-white/10 overflow-x-auto gold-scrollbar">
        {STATUS_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => changeFilter(() => setStatus(t.id))}
            className={`px-3 py-2 -mb-px border-b-2 text-xs sm:text-sm uppercase tracking-[0.06em] whitespace-nowrap transition-colors duration-200 ease-site ${
              t.id === status ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:max-w-[640px]">
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Регион</span>
          <select
            className={SELECT_CLASS}
            value={regionId}
            onChange={(e) => changeFilter(() => setRegionId(e.target.value))}
          >
            <option value="">Все регионы</option>
            {sortedRegions.map((r) => (
              <option key={r.region_id} value={String(r.region_id)}>
                {r.name ?? `Регион #${r.region_id}`}
                {r.country_name ? ` (${r.country_name})` : ''}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Товар</span>
          <select className={SELECT_CLASS} value={group} onChange={(e) => changeFilter(() => setGroup(e.target.value))}>
            <option value="">Все группы</option>
            {groups.map((g) => (
              <option key={g.code} value={g.code}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error ? (
        <p className="text-site-red text-sm">{error}</p>
      ) : !list ? (
        <Spinner />
      ) : list.items.length === 0 ? (
        <p className="text-white/40 text-sm">Караванов нет.</p>
      ) : (
        <ul className={`flex flex-col gap-2 ${loading ? 'opacity-60' : ''}`}>
          {list.items.map((c) => (
            <CaravanItem key={c.id} c={c} format={format} />
          ))}
        </ul>
      )}
      {total > LIST_PAGE && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-line !text-sm"
            disabled={offset === 0 || loading}
            onClick={() => setOffset((o) => Math.max(0, o - LIST_PAGE))}
          >
            Назад
          </button>
          <span className="text-white/60 text-sm">
            Страница {page} из {pages} · всего {total}
          </span>
          <button
            type="button"
            className="btn-line !text-sm"
            disabled={offset + LIST_PAGE >= total || loading}
            onClick={() => setOffset((o) => o + LIST_PAGE)}
          >
            Дальше
          </button>
        </div>
      )}
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- tab */

/** «Караваны» (FEAT-192): params, escrow check, counters, trade between countries, caravans list. */
const EconomyCaravans = ({ canSettings }: { canSettings: boolean }) => {
  const { format } = useCurrency();
  const fmt = useCallback((n: number) => format(n), [format]);
  const [data, setData] = useState<CaravanOverview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(() => {
    setLoading(true);
    fetchCaravanOverview()
      .then((d) => {
        setData(d);
        setLoadError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить караваны');
        setLoadError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const refresh = () => {
    load();
    setReloadKey((k) => k + 1);
  };

  const replacePair = (p: TradePair) =>
    setData((prev) =>
      prev
        ? {
            ...prev,
            pairs: prev.pairs.map((x) =>
              x.country_a === p.country_a && x.country_b === p.country_b ? { ...x, ...p, name_a: p.name_a ?? x.name_a, name_b: p.name_b ?? x.name_b } : x,
            ),
          }
        : prev,
    );

  if (loadError && !data) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-site-red text-sm">{loadError}</p>
        <button type="button" className="btn-line" onClick={load}>
          Повторить
        </button>
      </div>
    );
  }
  if (!data) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-white/70 text-sm mr-auto">
          Караваны ходят в каждом пересчёте — и по расписанию, и по «Пересчитать сейчас».
        </p>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Обновить
        </button>
      </div>

      {(data.params.caravans_enabled ?? 1) !== 1 && (
        <Warning>Караваны выключены: новые не отправляются, те, что уже в пути, доезжают и рассчитываются.</Warning>
      )}

      <StateCard data={data} format={fmt} />
      <ParamsCard params={data.params} canEdit={canSettings} onSaved={load} />
      <PairsCard data={data} canEdit={canSettings} onSaved={replacePair} />
      <CaravansCard format={fmt} reloadKey={reloadKey} />
    </div>
  );
};

export default EconomyCaravans;
