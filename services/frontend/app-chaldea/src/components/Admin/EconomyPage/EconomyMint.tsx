import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { RefreshCw, Trash2 } from 'lucide-react';
import { fetchEconomyItemGroups, patchEconomySimParams } from '../../../api/economyAdmin';
import {
  deleteMintItem,
  fetchMintAdmin,
  fetchMintItems,
  fetchMintQuotas,
  putMintCountry,
  putMintItem,
} from '../../../api/mint';
import { apiErrorMessage } from '../../../api/errors';
import useDebounce from '../../../hooks/useDebounce';
import { useCurrency } from '../../../hooks/useCurrency';
import type {
  EconItemGroupRow,
  EconSimParams,
  MintAdminOut,
  MintAdminParams,
  MintCapitalSource,
  MintCountry,
  MintItem,
  QuotaEntry,
} from '../../../types/economy';
import { seasonName, seasonText } from '../../../utils/seasonPeriod';
import { MintLimitBar, mintClosedText } from '../../pages/LocationPage/MintModal/MintParts';
import { formatDateTime, formatQty } from './economyLabels';
import { FieldHint, SimParamHint } from './ParamHint';

/* ------------------------------------------------------------------------------------- constants */

/** Bounds of the mint sim params — mirror `ECON_SIM_PARAM_BOUNDS` (feature file 3.5). */
interface MintParamDef {
  key: keyof MintAdminParams & keyof EconSimParams;
  label: string;
  def: number;
  min: number;
  max: number;
  integer?: boolean;
  /** Changing it creates money → needs economy:emit as well. */
  money: boolean;
}

const MINT_PARAMS: MintParamDef[] = [
  { key: 'mint_season_limit', label: 'Лимит чеканки за сезон (по умолчанию)', def: 0, min: 0, max: 1_000_000_000, integer: true, money: true },
  { key: 'mint_court_marks_per_unit', label: 'Курс двора, денег за единицу руды', def: 8, min: 0.01, max: 10_000, money: true },
  { key: 'mint_court_threshold_pct', label: 'Порог двора, % нормы запаса', def: 100, min: 0, max: 1000, money: false },
];

const LIMIT_MAX = 1_000_000_000;
const RATE_MIN = 1;
const RATE_MAX = 1_000_000;
const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_PAGE_SIZE = 20;
const SEARCH_MAX = 100;
const QUOTA_HISTORY_LIMIT = 20;
const ORE_GROUP = 'ore_metal';

const CAPITAL_SOURCE_LABEL: Record<MintCapitalSource, string> = {
  auto: 'автоматически (шаблон «столица»)',
  manual: 'выбрана вручную',
  none: 'не определена',
};

const SELECT_CLASS =
  'w-full bg-black/30 border border-white/20 rounded px-2 py-1.5 text-white text-sm focus:border-gold/50 outline-none disabled:opacity-40';

const fmtNum = (n: number) => String(n).replace('.', ',');

const parseNum = (raw: string): number => {
  const v = raw.trim().replace(',', '.');
  return v === '' ? Number.NaN : Number(v);
};

const paramError = (p: MintParamDef, raw: string): string | null => {
  const n = parseNum(raw);
  if (!Number.isFinite(n)) return 'Введите число';
  if (p.integer && !Number.isInteger(n)) return 'Только целое число';
  if (n < p.min || n > p.max) return `От ${fmtNum(p.min)} до ${fmtNum(p.max)}`;
  return null;
};

/** Digits only, max 10 — for integer money fields. */
const digitsOnly = (raw: string, max = 10) => raw.replace(/[^\d]/g, '').slice(0, max);

/* ------------------------------------------------------------------------------------- small parts */

const Card = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <section className={`bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0 ${className}`}>
    {children}
  </section>
);

const CardTitle = ({ children }: { children: ReactNode }) => (
  <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">{children}</h2>
);

const Badge = ({ tone, children, title }: { tone: 'gold' | 'blue' | 'red' | 'green' | 'muted'; children: ReactNode; title?: string }) => {
  const cls = {
    gold: 'border-gold/50 bg-gold/10 text-gold',
    blue: 'border-site-blue/50 bg-site-blue/10 text-site-blue',
    red: 'border-site-red/50 bg-site-red/10 text-site-red',
    green: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy',
    muted: 'border-white/20 text-white/50',
  }[tone];
  return (
    <span title={title} className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap ${cls}`}>
      {children}
    </span>
  );
};

const Warning = ({ children }: { children: ReactNode }) => (
  <p className="text-gold/90 text-xs sm:text-sm rounded-card border border-gold/30 bg-gold/[0.06] px-3 py-2">{children}</p>
);

const Spinner = () => <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

const NO_RIGHTS_TEXT = 'Менять может администратор с правами «economy:settings» и «economy:emit».';

/* ------------------------------------------------------------------------------------- params card */

interface ParamsCardProps {
  params: MintAdminParams;
  canSettings: boolean;
  canEmit: boolean;
  onSaved: () => void;
}

const ParamsCard = ({ params, canSettings, canEmit, onSaved }: ParamsCardProps) => {
  const toForm = (p: MintAdminParams) =>
    Object.fromEntries(MINT_PARAMS.map((d) => [d.key, fmtNum(p[d.key] ?? d.def)])) as Record<MintParamDef['key'], string>;
  const [form, setForm] = useState(() => toForm(params));
  const [saving, setSaving] = useState(false);

  useEffect(() => setForm(toForm(params)), [params]); // eslint-disable-line react-hooks/exhaustive-deps

  const errors = Object.fromEntries(MINT_PARAMS.map((d) => [d.key, paramError(d, form[d.key])])) as Record<
    MintParamDef['key'],
    string | null
  >;
  const changed = MINT_PARAMS.filter((d) => parseNum(form[d.key]) !== (params[d.key] ?? d.def));
  const valid = MINT_PARAMS.every((d) => errors[d.key] === null);
  const editable = (d: MintParamDef) => canSettings && (!d.money || canEmit);

  const save = async () => {
    setSaving(true);
    try {
      const patch: Partial<EconSimParams> = {};
      changed.forEach((d) => {
        patch[d.key] = parseNum(form[d.key]);
      });
      await patchEconomySimParams(patch);
      toast.success('Параметры монетного двора сохранены');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить параметры монетного двора'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-col gap-1">
        <CardTitle>Параметры</CardTitle>
        <p className="text-white/50 text-sm">
          Общие для всех стран. Квота сезона — во вкладке «Настройки».
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {MINT_PARAMS.map((d) => (
          <div key={d.key} className="flex flex-col gap-1 min-w-0">
            <span className="flex items-center gap-1 min-w-0">
              <label htmlFor={`mint-param-${d.key}`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
                {d.label}
              </label>
              <SimParamHint param={d.key} label={d.label} numbers={{ def: d.def, min: d.min, max: d.max }} />
            </span>
            <input
              id={`mint-param-${d.key}`}
              type="text"
              inputMode="decimal"
              className="input-underline w-full"
              value={form[d.key]}
              disabled={!editable(d) || saving}
              onChange={(e) => setForm({ ...form, [d.key]: e.target.value })}
            />
            {errors[d.key] && <p className="text-site-red text-xs">{errors[d.key]}</p>}
          </div>
        ))}
      </div>
      {canSettings ? (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <button
            type="button"
            className="btn-blue w-full sm:w-auto !px-6"
            disabled={!valid || changed.length === 0 || saving}
            onClick={() => void save()}
          >
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
          {!canEmit && (
            <p className="field-hint">Лимит и курс создают деньги — их меняет администратор с правом «economy:emit».</p>
          )}
        </div>
      ) : (
        <p className="field-hint">Изменять параметры может администратор с правом «economy:settings».</p>
      )}
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- country card */

interface CountryCardProps {
  country: MintCountry;
  defaultLimit: number;
  canEdit: boolean;
  format: (n: number) => string;
  onSaved: (c: MintCountry) => void;
}

const CountryCard = ({ country: c, defaultLimit, canEdit, format, onSaved }: CountryCardProps) => {
  const [capital, setCapital] = useState(c.capital_override_id === null ? '' : String(c.capital_override_id));
  const [limit, setLimit] = useState(c.season_limit_override === null ? '' : String(c.season_limit_override));
  const [enabled, setEnabled] = useState(c.is_enabled);
  const [saving, setSaving] = useState(false);

  const limitNum = limit.trim() === '' ? null : Number(limit);
  const limitValid = limitNum === null || (Number.isInteger(limitNum) && limitNum >= 0 && limitNum <= LIMIT_MAX);
  const capitalId = capital === '' ? null : Number(capital);
  const dirty =
    capitalId !== c.capital_override_id || limitNum !== c.season_limit_override || enabled !== c.is_enabled;

  const autoCandidates = c.candidates.filter((r) => r.template_code === 'capital');
  const autoText =
    autoCandidates.length === 1
      ? `Автоматически — «${autoCandidates[0].name}»`
      : autoCandidates.length === 0
        ? 'Автоматически — нет региона с шаблоном «столица»'
        : `Автоматически — регионов «столица»: ${autoCandidates.length}, выберите один`;

  const aliveMinters = c.minters.filter((m) => m.npc_status !== 'dead');
  const mintersInCapital = aliveMinters.filter((m) => m.in_capital);

  const save = async () => {
    setSaving(true);
    try {
      const saved = await putMintCountry(c.country_id, {
        capital_region_id: capitalId,
        season_limit: limitNum,
        is_enabled: enabled,
      });
      toast.success(`Монетный двор: «${saved.country_name ?? c.country_name ?? c.country_id}» сохранён`);
      onSaved(saved);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить настройки страны'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 rounded-card border border-white/10 bg-white/[0.03] p-3 sm:p-4 min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-white text-base font-medium mr-auto break-words">
          {c.country_name ?? `Страна #${c.country_id}`}
        </h3>
        {c.working ? (
          <Badge tone="green">чеканит</Badge>
        ) : (
          <Badge tone="muted" title={mintClosedText(c.closed_reason)}>
            закрыт
          </Badge>
        )}
      </div>

      <p className="text-white/70 text-xs sm:text-sm">
        Столица:{' '}
        <span className="text-white">{c.capital_region_name ? `«${c.capital_region_name}»` : '—'}</span>{' '}
        <span className="text-white/50">({CAPITAL_SOURCE_LABEL[c.capital_source] ?? c.capital_source})</span>
      </p>
      {!c.working && <p className="text-white/60 text-xs sm:text-sm">{mintClosedText(c.closed_reason)}</p>}

      {c.capital_source === 'none' && (
        <Warning>У страны нет столицы: выберите регион вручную — без столицы страна не чеканит.</Warning>
      )}
      {c.override_stale && (
        <Warning>
          Выбранная вручную столица удалена или перенесена в другую страну — используется автоматический выбор.
          Выберите столицу заново.
        </Warning>
      )}

      {c.season_limit > 0 && (
        <MintLimitBar
          limit={c.season_limit}
          court={c.minted_court}
          players={c.minted_players}
          remaining={c.remaining}
          format={format}
        />
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs sm:text-sm">
        <span className="text-white/60">
          Лимит сезона: <span className="text-white">{c.season_limit > 0 ? format(c.season_limit) : 'не задан'}</span>
          {c.season_limit_override === null && <span className="text-white/40"> (по умолчанию)</span>}
        </span>
        <span className="text-white/60">
          Руда в столице:{' '}
          <span className="text-white">
            {c.ore_stock === null ? '—' : formatQty(c.ore_stock)}
            {c.ore_norm !== null && <> из нормы {formatQty(c.ore_norm)}</>}
          </span>
        </span>
      </div>

      {/* minters */}
      <div className="flex flex-col gap-1">
        <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">Монетчики</span>
        {c.minters.length === 0 ? (
          <Warning>
            В стране нет НПС с ролью «Монетчик» — игроки не смогут сдавать руду. Поставьте его в локацию столицы на{' '}
            <Link to="/admin/npcs" className="site-link underline">
              странице НПС
            </Link>
            .
          </Warning>
        ) : (
          <>
            <ul className="flex flex-wrap gap-1.5">
              {c.minters.map((m) => (
                <li key={m.npc_id}>
                  <Badge
                    tone={m.npc_status === 'dead' ? 'red' : m.in_capital ? 'blue' : 'muted'}
                    title={m.location_name ?? undefined}
                  >
                    {m.name ?? `НПС #${m.npc_id}`}
                    {m.location_name ? ` · ${m.location_name}` : ''}
                    {m.npc_status === 'dead' ? ' · мёртв' : !m.in_capital ? ' · не в столице' : ''}
                  </Badge>
                </li>
              ))}
            </ul>
            {mintersInCapital.length === 0 && (
              <Warning>Ни один живой монетчик не стоит в столице — монетный двор принимает руду только там.</Warning>
            )}
          </>
        )}
      </div>

      {/* settings */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-3 border-t border-white/10">
        <div className="flex flex-col gap-1 min-w-0">
          <span className="flex items-center gap-1">
            <label htmlFor={`mint-capital-${c.country_id}`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
              Столица
            </label>
            <FieldHint field="mint_capital" label="Столица" />
          </span>
          <select
            id={`mint-capital-${c.country_id}`}
            className={SELECT_CLASS}
            value={capital}
            disabled={!canEdit || saving}
            onChange={(e) => setCapital(e.target.value)}
          >
            <option value="">{autoText}</option>
            {c.candidates.map((r) => (
              <option key={r.region_id} value={String(r.region_id)}>
                {r.name}
                {r.template_code === 'capital' ? ' (шаблон «столица»)' : ''}
              </option>
            ))}
            {c.capital_override_id !== null && !c.candidates.some((r) => r.region_id === c.capital_override_id) && (
              <option value={String(c.capital_override_id)}>Регион #{c.capital_override_id} (недоступен)</option>
            )}
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <span className="flex items-center gap-1">
            <label htmlFor={`mint-limit-${c.country_id}`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
              Свой лимит за сезон
            </label>
            <FieldHint field="mint_country_limit" label="Свой лимит за сезон" />
          </span>
          <input
            id={`mint-limit-${c.country_id}`}
            type="text"
            inputMode="numeric"
            className="input-underline w-full"
            placeholder={`по умолчанию: ${defaultLimit.toLocaleString('ru-RU')}`}
            value={limit}
            disabled={!canEdit || saving}
            onChange={(e) => setLimit(digitsOnly(e.target.value))}
          />
          {!limitValid && <p className="text-site-red text-xs">От 0 до {LIMIT_MAX.toLocaleString('ru-RU')}</p>}
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <span className="flex items-center gap-1">
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Двор</span>
            <FieldHint field="mint_country_enabled" label="Двор включён" />
          </span>
          <label className="flex items-center gap-2 text-sm text-white cursor-pointer py-1.5">
            <input
              type="checkbox"
              className="accent-gold w-4 h-4"
              checked={enabled}
              disabled={!canEdit || saving}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            {enabled ? 'Включён' : 'Выключен'}
          </label>
        </div>
      </div>
      {canEdit && (
        <button
          type="button"
          className="btn-blue w-full sm:w-auto sm:self-start !px-6"
          disabled={!dirty || !limitValid || saving}
          onClick={() => void save()}
        >
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------------------------- ore items */

interface ItemRowProps {
  item: MintItem;
  canEdit: boolean;
  format: (n: number) => string;
  onSaved: (item: MintItem) => void;
  onDeleted: (itemId: number) => void;
}

const ItemRow = ({ item, canEdit, format, onSaved, onDeleted }: ItemRowProps) => {
  const [rate, setRate] = useState(String(item.marks_per_item));
  const [enabled, setEnabled] = useState(item.is_enabled);
  const [busy, setBusy] = useState(false);

  const rateNum = Number(rate);
  const rateValid = rate !== '' && Number.isInteger(rateNum) && rateNum >= RATE_MIN && rateNum <= RATE_MAX;
  const dirty = rateNum !== item.marks_per_item || enabled !== item.is_enabled;

  const save = async () => {
    setBusy(true);
    try {
      const saved = await putMintItem(item.item_id, { marks_per_item: rateNum, is_enabled: enabled });
      toast.success(`«${saved.name}»: сохранено`);
      onSaved(saved);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить руду'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Убрать «${item.name}» из списка руды для чеканки?`)) return;
    setBusy(true);
    try {
      await deleteMintItem(item.item_id);
      toast.success(`«${item.name}» убрана из списка`);
      onDeleted(item.item_id);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось убрать руду'));
      setBusy(false);
    }
  };

  return (
    <li className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-card border border-white/10 bg-white/[0.03] p-3 min-w-0">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="w-10 h-10 rounded bg-black/40 overflow-hidden shrink-0 flex items-center justify-center">
          {item.image ? (
            <img src={item.image} alt="" className="w-full h-full object-cover" />
          ) : (
            <span aria-hidden>⛏️</span>
          )}
        </div>
        <div className="flex flex-col min-w-0">
          <span className="text-white text-sm font-medium break-words">{item.name}</span>
          <span className="text-white/50 text-xs">
            #{item.item_id} · {format(item.marks_per_item)} за шт.
          </span>
          {!item.valid && (
            <span className="text-site-red text-xs">
              Группа предмета не «Руда и металл» — монетчик его не принимает.
            </span>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-0.5 w-28">
          <span className="text-white/50 text-[11px] uppercase tracking-wide">Денег за шт.</span>
          <input
            type="text"
            inputMode="numeric"
            className="input-underline !text-sm w-full"
            value={rate}
            disabled={!canEdit || busy}
            onChange={(e) => setRate(digitsOnly(e.target.value, 7))}
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-white cursor-pointer pb-1">
          <input
            type="checkbox"
            className="accent-gold w-4 h-4"
            checked={enabled}
            disabled={!canEdit || busy}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Принимать
        </label>
        {canEdit && (
          <>
            <button
              type="button"
              className="btn-blue !px-4 !py-1.5 !text-sm"
              disabled={!dirty || !rateValid || busy}
              onClick={() => void save()}
            >
              Сохранить
            </button>
            <button
              type="button"
              className="p-1.5 text-white/50 hover:text-site-red transition-colors duration-200 ease-site disabled:opacity-40"
              disabled={busy}
              onClick={() => void remove()}
              aria-label={`Убрать «${item.name}»`}
              title="Убрать из списка"
            >
              <Trash2 size={16} />
            </button>
          </>
        )}
      </div>
      {!rateValid && (
        <p className="text-site-red text-xs sm:basis-full">
          Целое число от {RATE_MIN} до {RATE_MAX.toLocaleString('ru-RU')}
        </p>
      )}
    </li>
  );
};

interface AddItemProps {
  existing: Set<number>;
  format: (n: number) => string;
  onAdded: (item: MintItem) => void;
}

/** Search among items of the «Руда и металл» group and add one with a rate. */
const AddItem = ({ existing, format, onAdded }: AddItemProps) => {
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, SEARCH_DEBOUNCE_MS) as string;
  const [rows, setRows] = useState<EconItemGroupRow[] | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<EconItemGroupRow | null>(null);
  const [rate, setRate] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchEconomyItemGroups({ q: debounced.trim() || undefined, group: ORE_GROUP, page: 1, page_size: SEARCH_PAGE_SIZE })
      .then((res) => {
        if (cancelled) return;
        setRows(res.items);
        setSearchError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось найти предметы');
        setSearchError(msg);
        toast.error(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  const rateNum = Number(rate);
  const rateValid = rate !== '' && Number.isInteger(rateNum) && rateNum >= RATE_MIN && rateNum <= RATE_MAX;

  const pick = (row: EconItemGroupRow) => {
    setPicked(row);
    // A starting point: the item's own price (the backend checks only the bounds).
    setRate(String(Math.max(RATE_MIN, Math.min(RATE_MAX, Math.round(row.price) || RATE_MIN))));
  };

  const add = async () => {
    if (!picked) return;
    setSaving(true);
    try {
      const saved = await putMintItem(picked.item_id, { marks_per_item: rateNum, is_enabled: true });
      toast.success(`«${saved.name}» добавлена: ${format(saved.marks_per_item)} за шт.`);
      onAdded(saved);
      setPicked(null);
      setRate('');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось добавить руду'));
    } finally {
      setSaving(false);
    }
  };

  const candidates = (rows ?? []).filter((r) => !existing.has(r.item_id));

  return (
    <div className="flex flex-col gap-3 pt-3 border-t border-white/10">
      <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Добавить руду</span>
      <input
        type="search"
        className="input-underline w-full sm:max-w-[360px]"
        placeholder="Поиск по названию среди «Руда и металл»"
        maxLength={SEARCH_MAX}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {searchError ? (
        <p className="text-site-red text-sm">{searchError}</p>
      ) : loading && !rows ? (
        <Spinner />
      ) : candidates.length === 0 ? (
        <p className="text-white/40 text-sm">
          {rows && rows.length > 0 ? 'Все найденные предметы уже в списке.' : 'Ничего не найдено.'}
        </p>
      ) : (
        <ul className="flex flex-wrap gap-1.5 max-h-[180px] overflow-y-auto gold-scrollbar">
          {candidates.map((r) => (
            <li key={r.item_id}>
              <button
                type="button"
                onClick={() => pick(r)}
                className={`chip-outline rounded-full px-3 py-1 text-xs ${picked?.item_id === r.item_id ? 'chip-outline-active' : ''}`}
              >
                {r.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {picked && (
        <div className="flex flex-wrap items-end gap-3">
          <span className="text-white text-sm">«{picked.name}»</span>
          <label className="flex flex-col gap-0.5 w-32">
            <span className="flex items-center gap-1 text-white/50 text-[11px] uppercase tracking-wide">
              Денег за шт.
              <FieldHint field="mint_item_rate" label="Денег за штуку" />
            </span>
            <input
              type="text"
              inputMode="numeric"
              className="input-underline !text-sm w-full"
              value={rate}
              disabled={saving}
              onChange={(e) => setRate(digitsOnly(e.target.value, 7))}
            />
          </label>
          <button
            type="button"
            className="btn-blue !px-4 !py-1.5 !text-sm"
            disabled={!rateValid || saving}
            onClick={() => void add()}
          >
            {saving ? 'Добавляю...' : 'Добавить'}
          </button>
          <button type="button" className="btn-line !text-sm" disabled={saving} onClick={() => setPicked(null)}>
            Отмена
          </button>
          {!rateValid && (
            <p className="text-site-red text-xs basis-full">
              Целое число от {RATE_MIN} до {RATE_MAX.toLocaleString('ru-RU')}
            </p>
          )}
        </div>
      )}
    </div>
  );
};

const ItemsCard = ({ canEdit, format }: { canEdit: boolean; format: (n: number) => string }) => {
  const [items, setItems] = useState<MintItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMintItems()
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить список руды');
        setError(msg);
        toast.error(msg);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const upsert = (item: MintItem) =>
    setItems((prev) => {
      const list = prev ?? [];
      return list.some((i) => i.item_id === item.item_id)
        ? list.map((i) => (i.item_id === item.item_id ? item : i))
        : [...list, item];
    });

  return (
    <Card>
      <div className="flex flex-col gap-1">
        <CardTitle>Руда для чеканки</CardTitle>
        <p className="text-white/50 text-sm">
          Какие предметы монетчик принимает от игроков и сколько платит за штуку. Только группа «Руда и металл» и
          только обычные стопки; сданная руда пополняет запас столицы.
        </p>
      </div>
      {error ? (
        <p className="text-site-red text-sm">{error}</p>
      ) : !items ? (
        <Spinner />
      ) : items.length === 0 ? (
        <p className="text-white/40 text-sm">Список пуст — монетчики пока ничего не принимают.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <ItemRow
              key={`${item.item_id}-${item.marks_per_item}-${item.is_enabled}`}
              item={item}
              canEdit={canEdit}
              format={format}
              onSaved={upsert}
              onDeleted={(id) => setItems((prev) => (prev ?? []).filter((i) => i.item_id !== id))}
            />
          ))}
        </ul>
      )}
      {canEdit && items && (
        <AddItem existing={new Set(items.map((i) => i.item_id))} format={format} onAdded={upsert} />
      )}
      {!canEdit && <p className="field-hint">{NO_RIGHTS_TEXT}</p>}
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- quota history */

const QuotaHistory = ({ format }: { format: (n: number) => string }) => {
  const [rows, setRows] = useState<QuotaEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMintQuotas(QUOTA_HISTORY_LIMIT)
      .then((list) => {
        if (!cancelled) setRows(list);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить историю квот');
        setError(msg);
        toast.error(msg);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card>
      <CardTitle>История квот сезона</CardTitle>
      {error ? (
        <p className="text-site-red text-sm">{error}</p>
      ) : !rows ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <p className="text-white/40 text-sm">Квота ещё не выдавалась.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-white/10">
          {rows.map((q) => (
            <li key={q.operation_id} className="flex flex-wrap items-baseline gap-x-4 gap-y-0.5 py-2 text-sm">
              <span className="text-white font-medium">{seasonName(q.season, q.year)}</span>
              <span className="text-gold">{format(q.amount)}</span>
              <span className="text-white/60">регионов: {q.regions}</span>
              <span className="text-white/40 text-xs sm:ml-auto">
                {formatDateTime(q.created_at)} · операция #{q.operation_id}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};

/* ------------------------------------------------------------------------------------- tab */

interface EconomyMintProps {
  canSettings: boolean;
  canEmit: boolean;
}

/** «Монетный двор» (FEAT-191): capital and mint of every country, params, accepted ore, season quota history. */
const EconomyMint = ({ canSettings, canEmit }: EconomyMintProps) => {
  const { format } = useCurrency();
  const fmt = useCallback((n: number) => format(n), [format]);
  const [data, setData] = useState<MintAdminOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const canMoney = canSettings && canEmit;

  const load = useCallback(() => {
    setLoading(true);
    fetchMintAdmin()
      .then((d) => {
        setData(d);
        setLoadError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить монетный двор');
        setLoadError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const replaceCountry = (c: MintCountry) =>
    setData((prev) =>
      prev ? { ...prev, countries: prev.countries.map((x) => (x.country_id === c.country_id ? c : x)) } : prev,
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
      {/* period */}
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-white text-sm sm:text-base mr-auto">
          {data.period ? (
            <>
              Сезон: <span className="text-gold">{seasonText(data.period)}</span>
            </>
          ) : (
            <span className="text-site-red">Календарь мира недоступен — монетные дворы и квота не работают.</span>
          )}
        </p>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Обновить
        </button>
      </div>

      {data.params.mint_season_limit <= 0 && (
        <Warning>
          Лимит чеканки по умолчанию — 0: монетные дворы стран без своего лимита закрыты. Задайте лимит ниже.
        </Warning>
      )}

      <ParamsCard params={data.params} canSettings={canSettings} canEmit={canEmit} onSaved={load} />

      <Card>
        <div className="flex flex-col gap-1">
          <CardTitle>Страны</CardTitle>
          <p className="text-white/50 text-sm">
            Двор одной страны — в её столице. Лимит за сезон общий для двора и игроков.
          </p>
        </div>
        {data.countries.length === 0 ? (
          <p className="text-white/40 text-sm">Стран пока нет.</p>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {data.countries.map((c) => (
              <CountryCard
                key={`${c.country_id}-${c.capital_override_id}-${c.season_limit_override}-${c.is_enabled}`}
                country={c}
                defaultLimit={data.params.mint_season_limit}
                canEdit={canMoney}
                format={fmt}
                onSaved={replaceCountry}
              />
            ))}
          </div>
        )}
        {!canMoney && <p className="field-hint">{NO_RIGHTS_TEXT}</p>}
      </Card>

      <ItemsCard canEdit={canMoney} format={fmt} />

      <QuotaHistory format={fmt} />
    </div>
  );
};

export default EconomyMint;
