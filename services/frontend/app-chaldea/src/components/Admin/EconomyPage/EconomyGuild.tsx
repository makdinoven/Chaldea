import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
import { RefreshCw } from 'lucide-react';
import { fetchEconomyGoodsGroups, fetchEconomyRegions, patchEconomySimParams } from '../../../api/economyAdmin';
import { fetchGuildAdmin } from '../../../api/guild';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import type {
  EconGoodsGroup,
  EconRegionItem,
  EconSimParams,
  GuildAdminOut,
  GuildAdminParams,
  GuildOrderRow,
  GuildRegionRow,
  GuildStatusFilter,
} from '../../../types/economy';
import { formatDateTime, formatDecimal, formatQty, guildCloseReasonText } from './economyLabels';
import { SimParamHint } from './ParamHint';

/* ------------------------------------------------------------------------------------- constants */

type GuildParamKey = keyof GuildAdminParams & keyof EconSimParams;

/** Bounds and defaults of the guild sim params — mirror `ECON_SIM_PARAM_BOUNDS` (feature file 3.4). */
interface GuildParamDef {
  key: GuildParamKey;
  label: string;
  def: number;
  min: number;
  max: number;
  integer?: boolean;
}

const GUILD_PARAMS: GuildParamDef[] = [
  { key: 'guild_markup_pct', label: 'Надбавка к местной цене, %', def: 20, min: 0, max: 200 },
  { key: 'guild_open_threshold_pct', label: 'Порог открытия заказа, % нормы', def: 80, min: 1, max: 100 },
  { key: 'guild_min_order_value', label: 'Минимальный заказ, денег', def: 50, min: 1, max: 1_000_000, integer: true },
  { key: 'guild_purse_share', label: 'Доля кошелька жителей за пересчёт', def: 0.25, min: 0, max: 1 },
  { key: 'guild_treasury_food_share', label: 'Доля казны на доплату за еду', def: 0.25, min: 0, max: 1 },
  { key: 'guild_xp_per_mark', label: 'Опыт за марку', def: 0.1, min: 0, max: 10 },
  {
    key: 'guild_xp_per_mark_merchant_items',
    label: 'Опыт за марку (товары торговцев)',
    def: 0.05,
    min: 0,
    max: 10,
  },
  { key: 'guild_xp_daily_cap', label: 'Лимит опыта в сутки', def: 200, min: 0, max: 1_000_000, integer: true },
];

const ENABLED_DEF = { def: 1, min: 0, max: 1 };
const LIST_PAGE = 20;

const STATUS_TABS: { id: GuildStatusFilter; label: string }[] = [
  { id: 'open', label: 'Открытые' },
  { id: 'closed', label: 'Закрытые' },
  { id: 'all', label: 'Все' },
];

const STATUS_LABEL: Record<string, string> = {
  open: 'открыт',
  filled: 'выполнен',
  closed: 'закрыт',
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

const regionName = (name: string | null, id: number) => name ?? `Регион #${id} (удалён)`;

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

const StatusBadge = ({ status }: { status: string }) => {
  const cls =
    {
      open: 'border-site-blue/50 bg-site-blue/10 text-site-blue',
      filled: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy',
      closed: 'border-white/20 bg-white/5 text-white/60',
    }[status] ?? 'border-white/20 text-white/50';
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap ${cls}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
};

/* ------------------------------------------------------------------------------------- state card */

const StateCard = ({ data, format }: { data: GuildAdminOut; format: (n: number) => string }) => {
  const t = data.totals;
  return (
    <Card>
      <CardTitle>Состояние</CardTitle>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <Stat label="Открытых заказов">{t.open}</Stat>
        <Stat label="Осталось заказать на">{format(t.units_left_value)}</Stat>
        <Stat label="Выплачено за 7 дней">{format(t.paid_last_7d)}</Stat>
        <Stat label="Сдач за 7 дней">{t.hand_ins_last_7d}</Stat>
        <Stat label="Опыта за 7 дней">{t.xp_last_7d.toLocaleString('ru-RU')}</Stat>
      </div>
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- params card */

interface ParamsCardProps {
  params: GuildAdminParams;
  canEdit: boolean;
  onSaved: () => void;
}

const ParamsCard = ({ params, canEdit, onSaved }: ParamsCardProps) => {
  const toForm = (p: GuildAdminParams) =>
    Object.fromEntries(GUILD_PARAMS.map((d) => [d.key, fmtNum(p[d.key] ?? d.def)])) as Record<GuildParamKey, string>;
  const [form, setForm] = useState(() => toForm(params));
  const [enabled, setEnabled] = useState((params.guild_enabled ?? ENABLED_DEF.def) === 1);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(toForm(params));
    setEnabled((params.guild_enabled ?? ENABLED_DEF.def) === 1);
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  const errors = Object.fromEntries(GUILD_PARAMS.map((d) => [d.key, paramError(d, form[d.key])])) as Record<
    GuildParamKey,
    string | null
  >;
  const changed = GUILD_PARAMS.filter((d) => parseNum(form[d.key]) !== (params[d.key] ?? d.def));
  const enabledChanged = (enabled ? 1 : 0) !== (params.guild_enabled ?? ENABLED_DEF.def);
  const valid = GUILD_PARAMS.every((d) => errors[d.key] === null);

  const save = async () => {
    setSaving(true);
    try {
      const patch: Partial<EconSimParams> = {};
      changed.forEach((d) => {
        patch[d.key] = parseNum(form[d.key]);
      });
      if (enabledChanged) patch.guild_enabled = enabled ? 1 : 0;
      await patchEconomySimParams(patch);
      toast.success('Параметры гильдии сохранены');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить параметры гильдии'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-col gap-1">
        <CardTitle>Параметры</CardTitle>
        <p className="text-white/50 text-sm">
          Общие для всего мира. Заказы и бюджеты пересчитываются со следующего пересчёта; цена и опыт при сдаче — сразу.
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <span className="flex items-center gap-1">
          <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Заказы гильдии</span>
          <SimParamHint param="guild_enabled" label="Заказы гильдии включены" numbers={ENABLED_DEF} />
        </span>
        <label className="flex items-center gap-2 text-sm text-white cursor-pointer py-1.5 self-start">
          <input
            type="checkbox"
            className="accent-gold w-4 h-4"
            checked={enabled}
            disabled={!canEdit || saving}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {enabled ? 'Открываются' : 'Выключены (открытые закроются в ближайшем пересчёте)'}
        </label>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {GUILD_PARAMS.map((d) => (
          <div key={d.key} className="flex flex-col gap-1 min-w-0">
            <span className="flex items-center gap-1 min-w-0">
              <label htmlFor={`guild-param-${d.key}`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
                {d.label}
              </label>
              <SimParamHint param={d.key} label={d.label} numbers={{ def: d.def, min: d.min, max: d.max }} />
            </span>
            <input
              id={`guild-param-${d.key}`}
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

/* ------------------------------------------------------------------------------------- regions card */

const RegionItem = ({ r, format }: { r: GuildRegionRow; format: (n: number) => string }) => {
  const alive = r.masters.filter((m) => m.npc_status !== 'dead');
  return (
    <li className="flex flex-col gap-2 rounded-card border border-white/10 bg-white/[0.03] p-3 min-w-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-white text-sm font-medium break-words">{regionName(r.region_name, r.region_id)}</span>
        <span className="text-white/60 text-xs">открытых заказов: {r.open_orders}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-white/60">
        <span>
          Бюджет из кошелька жителей: <span className="text-white">{format(r.guild_budget)}</span>
        </span>
        <span>
          Доплата казны за еду: <span className="text-white">{format(r.guild_food_budget)}</span>
        </span>
      </div>
      {r.masters.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {r.masters.map((m) => (
            <li
              key={m.npc_id}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] ${
                m.npc_status === 'dead' ? 'border-site-red/40 text-site-red/80' : 'border-white/15 text-white/70'
              }`}
            >
              📜 {m.name}
              {m.location_name && <span className="text-white/45"> · {m.location_name}</span>}
              {m.npc_status === 'dead' && ' · мёртв'}
            </li>
          ))}
        </ul>
      )}
      {alive.length === 0 && <Warning>Нет представителя гильдии — заказы никто не примет.</Warning>}
    </li>
  );
};

const RegionsCard = ({ regions, format }: { regions: GuildRegionRow[]; format: (n: number) => string }) => {
  const sorted = useMemo(
    () => [...regions].sort((a, b) => (a.region_name ?? '').localeCompare(b.region_name ?? '', 'ru')),
    [regions],
  );
  const withoutMaster = regions.filter((r) => !r.masters.some((m) => m.npc_status !== 'dead')).length;
  return (
    <Card>
      <div className="flex flex-col gap-1">
        <CardTitle>Регионы</CardTitle>
        <p className="text-white/50 text-sm">
          Регионы, участвующие в пересчёте: бюджет гильдии на текущий пересчёт и представители (НПС с ролью «Гильдия
          торговцев»). Без представителя: {withoutMaster} из {regions.length}.
        </p>
      </div>
      {sorted.length === 0 ? (
        <p className="text-white/40 text-sm">Нет регионов, участвующих в пересчёте.</p>
      ) : (
        <ul className="grid grid-cols-1 lg:grid-cols-2 gap-2">
          {sorted.map((r) => (
            <RegionItem key={r.region_id} r={r} format={format} />
          ))}
        </ul>
      )}
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- orders list */

const OrderItem = ({ o, format }: { o: GuildOrderRow; format: (n: number) => string }) => {
  const pct = o.units_total > 0 ? Math.min(100, Math.max(0, Math.round((o.units_filled / o.units_total) * 100))) : 0;
  return (
    <li className="flex flex-col gap-2 rounded-card border border-white/10 bg-white/[0.03] p-3 min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={o.status} />
        <span className="text-white text-sm font-medium">{o.group_name ?? o.group_code}</span>
        <span className="text-white/60 text-sm break-words">{regionName(o.region_name, o.region_id)}</span>
        <span className="text-white/40 text-xs sm:ml-auto">
          #{o.id} · {formatDateTime(o.opened_at)}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-4 gap-y-1 text-xs text-white/60">
        <span>
          Осталось: <span className="text-white">{formatQty(o.units_left)}</span> из {formatQty(o.units_total)} ед.
        </span>
        <span>
          Сдано: <span className="text-white">{formatQty(o.units_filled)} ед.</span> ({o.pieces} шт., сдач {o.hand_ins})
          {o.status === 'open' && o.units_filled > 0 && pct > 0 && <span className="text-white/40"> · {pct} %</span>}
        </span>
        <span>
          Выплачено: <span className="text-white">{format(o.paid_total)}</span>
          {o.paid_treasury > 0 && <span className="text-white/50"> (казна {format(o.paid_treasury)})</span>}
        </span>
        <span>
          Множитель ×{formatDecimal(o.price_mult, 3)} · надбавка {formatDecimal(o.markup_pct)} %
        </span>
      </div>
      {o.status !== 'open' && (
        <p className="text-xs text-white/50">
          {o.status === 'filled' ? 'выполнен' : guildCloseReasonText(o.close_reason)}
          {o.closed_at && ` · ${formatDateTime(o.closed_at)}`}
        </p>
      )}
    </li>
  );
};

interface OrdersCardProps {
  format: (n: number) => string;
  reloadKey: number;
}

const OrdersCard = ({ format, reloadKey }: OrdersCardProps) => {
  const [status, setStatus] = useState<GuildStatusFilter>('open');
  const [regionId, setRegionId] = useState('');
  const [group, setGroup] = useState('');
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<{ total: number; items: GuildOrderRow[] } | null>(null);
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
    fetchGuildAdmin({
      status,
      region_id: regionId === '' ? undefined : Number(regionId),
      group_code: group || undefined,
      limit: LIST_PAGE,
      offset,
    })
      .then((res) => {
        if (cancelled) return;
        setList({ total: res.total, items: res.items });
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить заказы гильдии');
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
        <CardTitle>Заказы</CardTitle>
        <p className="text-white/50 text-sm">Новые сверху. История заказов хранится.</p>
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
        <p className="text-white/40 text-sm">Заказов нет.</p>
      ) : (
        <ul className={`flex flex-col gap-2 ${loading ? 'opacity-60' : ''}`}>
          {list.items.map((o) => (
            <OrderItem key={o.id} o={o} format={format} />
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

/** «Гильдия» (FEAT-193): params, totals, regions with budgets and guild masters, the orders list. */
const EconomyGuild = ({ canSettings }: { canSettings: boolean }) => {
  const { format } = useCurrency();
  const fmt = useCallback((n: number) => format(n), [format]);
  const [data, setData] = useState<GuildAdminOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  // The overview (params, totals, regions) — the orders card loads its own page of the same endpoint.
  const load = useCallback(() => {
    setLoading(true);
    fetchGuildAdmin({ status: 'open', limit: 1 })
      .then((d) => {
        setData(d);
        setLoadError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить гильдию торговцев');
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
          Заказы открываются, обновляются и закрываются в каждом пересчёте — и по расписанию, и по «Пересчитать сейчас».
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

      {(data.params.guild_enabled ?? 1) !== 1 && (
        <Warning>Заказы гильдии выключены: новые не открываются, открытые закроются в ближайшем пересчёте.</Warning>
      )}

      <StateCard data={data} format={fmt} />
      <ParamsCard params={data.params} canEdit={canSettings} onSaved={refresh} />
      <RegionsCard regions={data.regions} format={fmt} />
      <OrdersCard format={fmt} reloadKey={reloadKey} />
    </div>
  );
};

export default EconomyGuild;
