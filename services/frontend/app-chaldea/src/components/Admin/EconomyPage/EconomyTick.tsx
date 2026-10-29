import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { Play, RefreshCw, RotateCcw } from 'lucide-react';
import { fetchEconomySim, postEconomySimRun, putEconomySim } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import type { EconSimParams, EconSimState, EconTickRun, EconTickStatus, EconTickTrigger } from '../../../types/economy';
import { formatDateTime } from './economyLabels';

/** Poll the state while a run is going so progress and the final status appear by themselves. */
const RUNNING_POLL_MS = 5000;
const RUN_IN_PROGRESS_MESSAGE = 'Пересчёт уже идёт';

type ParamKey = keyof EconSimParams;

interface ParamDef {
  key: ParamKey;
  label: string;
  hint: string;
  min: number;
  max: number;
  /** Defaults of `econ_sim.SimParams` — shown in the hint and used by «Вернуть по умолчанию». */
  def: number;
  integer?: boolean;
}

interface ParamSection {
  title: string;
  intro: string;
  params: ParamDef[];
}

/**
 * Simulation params grouped for a human. Bounds mirror `ECON_SIM_PARAM_BOUNDS` in character-service `schemas.py`
 * (inclusive); the backend validates again and its message is shown as is.
 */
const SECTIONS: ParamSection[] = [
  {
    title: 'Цены',
    intro: 'Цена товара в регионе — множитель к базовой цене группы. Мало запаса — дороже, много — дешевле.',
    params: [
      { key: 'price_min', label: 'Минимальный множитель цены', hint: 'Дешевле этого товар не станет даже при избытке.', min: 0.05, max: 1, def: 0.5 },
      { key: 'price_max', label: 'Максимальный множитель цены', hint: 'Дороже этого товар не станет даже при пустом складе.', min: 1, max: 20, def: 3 },
      { key: 'price_exponent', label: 'Чувствительность цены к запасу', hint: 'Чем больше, тем резче цена реагирует на запас. 0,631: тройной запас — цена ×0,5.', min: 0.05, max: 5, def: 0.631 },
      { key: 'stock_cap_mult', label: 'Предел запаса, × нормы', hint: 'Всё, что сверх нормы × это число, портится или вывозится.', min: 1, max: 20, def: 3 },
    ],
  },
  {
    title: 'Производство',
    intro: 'Сколько регион производит за шаг сверх базовой нормы шаблона.',
    params: [
      { key: 'prod_price_elasticity', label: 'Отклик производства на цену', hint: 'Дорогой товар начинают делать больше, дешёвый — меньше.', min: 0, max: 2, def: 0.15 },
      { key: 'prod_price_min', label: 'Нижний предел отклика', hint: 'Производство не падает ниже этой доли из-за дешевизны.', min: 0.1, max: 1, def: 0.85 },
      { key: 'prod_price_max', label: 'Верхний предел отклика', hint: 'Производство не растёт выше этой доли из-за дороговизны.', min: 1, max: 5, def: 1.3 },
      { key: 'full_stability', label: 'Стабильность для полной выработки', hint: 'Ниже этого уровня регион работает вполсилы (до 50 %).', min: 1, max: 100, def: 60 },
      { key: 'hunger_prod_penalty', label: 'Штраф выработки за голод', hint: 'При полном голоде выработка падает на эту долю.', min: 0, max: 1, def: 0.5 },
    ],
  },
  {
    title: 'Деньги жителей и казна',
    intro: 'Кошелёк жителей платит за товары и налог; казна региона возвращает излишек жалованьем.',
    params: [
      { key: 'afford_days', label: 'Запас кошелька для покупок, дней', hint: 'Если в кошельке меньше потребностей на столько дней — жители покупают меньше.', min: 0.1, max: 30, def: 1 },
      { key: 'treasury_reserve_days', label: 'Резерв казны, дней налога', hint: 'Сколько дней налога казна держит у себя, прежде чем платить сверх налога.', min: 0, max: 60, def: 7 },
      { key: 'treasury_release_ticks', label: 'Возврат излишка казны, шагов', hint: 'За сколько шагов казна раздаёт жалованьем то, что выше резерва.', min: 1, max: 100, def: 8, integer: true },
      { key: 'country_grant_share', label: 'Дотация страны, доля за шаг', hint: 'Какую долю положительного баланса страна отдаёт своим регионам (0,25 = 25 %).', min: 0, max: 1, def: 0.25 },
      { key: 'purse_start_days', label: 'Стартовый кошелёк, дней потребностей', hint: 'До скольких дней потребностей «Заполнить регионы» пополняет кошелёк.', min: 0, max: 60, def: 7 },
    ],
  },
  {
    title: 'Стабильность',
    intro: 'Цель стабильности = база минус штрафы; за шаг стабильность проходит часть пути к цели.',
    params: [
      { key: 'stab_base', label: 'База', hint: 'Стабильность сытого, довольного региона с низким налогом.', min: 0, max: 100, def: 85 },
      { key: 'stab_hunger_w', label: 'Штраф за голод', hint: 'Минус к цели при полном голоде (пропорционально голоду).', min: 0, max: 500, def: 100 },
      { key: 'stab_goods_w', label: 'Штраф за нехватку товаров', hint: 'Минус к цели, если жители не купили ничего, кроме еды.', min: 0, max: 500, def: 15 },
      { key: 'stab_free_tax', label: 'Налог без недовольства', hint: 'Налог до этой ставки не злит жителей (0,12 = 12 %).', min: 0, max: 0.5, def: 0.12 },
      { key: 'stab_tax_w', label: 'Штраф за налог', hint: 'Минус к цели за каждую единицу ставки сверх безопасной (×0,01 = 1 % ставки).', min: 0, max: 1000, def: 200 },
      { key: 'stab_debt_penalty', label: 'Штраф за долг казны', hint: 'Минус к цели, пока казна региона в минусе.', min: 0, max: 100, def: 10 },
      { key: 'stab_rate_up', label: 'Скорость роста', hint: 'Доля разрыва до цели, которую стабильность проходит за шаг вверх.', min: 0, max: 1, def: 0.08 },
      { key: 'stab_rate_down', label: 'Скорость падения', hint: 'То же вниз — обычно быстрее роста.', min: 0, max: 1, def: 0.25 },
    ],
  },
  {
    title: 'Достаток',
    intro: 'Цель достатка складывается из довольства товарами, денег в кошельке и стабильности, минус голод.',
    params: [
      { key: 'prosp_rate', label: 'Скорость изменения', hint: 'Доля разрыва до цели, которую достаток проходит за шаг.', min: 0, max: 1, def: 0.05 },
      { key: 'prosp_w_sat', label: 'Вес довольства товарами', hint: 'Насколько важно, что жители купили всё нужное.', min: 0, max: 1, def: 0.3 },
      { key: 'prosp_w_liq', label: 'Вес денег в кошельке', hint: 'Насколько важен запас денег у жителей.', min: 0, max: 1, def: 0.4 },
      { key: 'prosp_w_stab', label: 'Вес стабильности', hint: 'Насколько важна стабильность.', min: 0, max: 1, def: 0.15 },
      { key: 'prosp_hunger_w', label: 'Штраф за голод', hint: 'Минус к цели при полном голоде.', min: 0, max: 500, def: 60 },
      { key: 'prosp_liq_days', label: '«Полный» кошелёк, дней потребностей', hint: 'Кошелёк на столько дней считается полностью обеспеченным.', min: 0.1, max: 60, def: 14 },
    ],
  },
  {
    title: 'Служебное',
    intro: 'Менять только осознанно.',
    params: [
      { key: 'dt', label: 'Длина шага, суток', hint: 'Доля суток на один шаг: 6 часов = 0,25. Должна совпадать с расписанием.', min: 0.05, max: 1, def: 0.25 },
      { key: 'history_retention_days', label: 'Хранить историю, дней', hint: 'Записи истории регионов старше этого срока удаляются.', min: 1, max: 365, def: 60, integer: true },
    ],
  },
];

const ALL_PARAMS: ParamDef[] = SECTIONS.flatMap((s) => s.params);

/** Pairs that must keep min < max. */
const RANGE_PAIRS: [ParamKey, ParamKey, string][] = [
  ['price_min', 'price_max', 'Минимальный множитель цены должен быть меньше максимального'],
  ['prod_price_min', 'prod_price_max', 'Нижний предел отклика должен быть меньше верхнего'],
];

const PROSP_WEIGHTS: ParamKey[] = ['prosp_w_sat', 'prosp_w_liq', 'prosp_w_stab'];

type FormState = Record<ParamKey, string>;

const fmtNum = (n: number) => String(n).replace('.', ',');

const toForm = (params: EconSimParams): FormState =>
  Object.fromEntries(ALL_PARAMS.map((p) => [p.key, fmtNum(params[p.key])])) as FormState;

const parseNum = (raw: string): number => {
  const v = raw.trim().replace(',', '.');
  return v === '' ? Number.NaN : Number(v);
};

const paramError = (p: ParamDef, raw: string): string | null => {
  const n = parseNum(raw);
  if (!Number.isFinite(n)) return 'Введите число';
  if (p.integer && !Number.isInteger(n)) return 'Только целое число';
  if (n < p.min || n > p.max) return `От ${fmtNum(p.min)} до ${fmtNum(p.max)}`;
  return null;
};

/** ISO from the backend; naive values are UTC (same rule as `formatDateTime`). */
const parseIso = (iso: string): Date => new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`);

const formatDuration = (run: EconTickRun): string => {
  if (!run.finished_at) return '—';
  const ms = parseIso(run.finished_at).getTime() - parseIso(run.started_at).getTime();
  if (!Number.isFinite(ms) || ms < 0) return '—';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec} с`;
  return `${Math.floor(sec / 60)} мин ${sec % 60} с`;
};

const TRIGGER_LABEL: Record<EconTickTrigger, string> = { auto: 'По расписанию', manual: 'Вручную' };

const STATUS_LABEL: Record<EconTickStatus, string> = {
  running: 'Идёт',
  done: 'Готово',
  partial: 'С ошибками',
  failed: 'Сбой',
};

const STATUS_CLASS: Record<EconTickStatus, string> = {
  running: 'text-site-blue',
  done: 'text-stat-energy',
  partial: 'text-gold',
  failed: 'text-site-red',
};

const StatusText = ({ status }: { status: EconTickStatus }) => (
  <span className={STATUS_CLASS[status] ?? 'text-white/70'}>{STATUS_LABEL[status] ?? status}</span>
);

const RegionsCell = ({ run }: { run: EconTickRun }) => (
  <span className="whitespace-nowrap">
    <span className="text-white/80">
      {run.regions_done} / {run.regions_total}
    </span>
    {run.regions_failed > 0 && <span className="text-site-red"> · ошибок {run.regions_failed}</span>}
  </span>
);

interface SwitchProps {
  checked: boolean;
  disabled: boolean;
  onChange: (next: boolean) => void;
  label: string;
}

const Switch = ({ checked, disabled, onChange, label }: SwitchProps) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors duration-200 ease-site disabled:opacity-40 disabled:cursor-not-allowed ${
      checked ? 'bg-gold/30 border-gold/60' : 'bg-white/[0.06] border-white/20'
    }`}
  >
    <span
      className={`inline-block h-4 w-4 rounded-full transition-transform duration-200 ease-site ${
        checked ? 'translate-x-6 bg-gold' : 'translate-x-1 bg-white/50'
      }`}
    />
  </button>
);

interface RunConfirmProps {
  nextSlotAt: string;
  onClose: () => void;
  onDone: (run: EconTickRun) => void;
  onConflict: () => void;
}

/** «Пересчитать сейчас»: a real extra step of the world, so the admin confirms it knowingly. */
const RunConfirm = ({ nextSlotAt, onClose, onDone, onConflict }: RunConfirmProps) => {
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const result = await postEconomySimRun();
      onDone(result);
    } catch (e) {
      if (axios.isAxiosError(e) && e.response?.status === 409) {
        toast.error(RUN_IN_PROGRESS_MESSAGE);
        onConflict();
      } else {
        toast.error(apiErrorMessage(e, 'Не удалось запустить пересчёт'));
      }
      setBusy(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      dismissible={!busy}
      title="Пересчитать сейчас"
      size="md"
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button type="button" className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs" disabled={busy} onClick={run}>
            {busy ? 'Пересчёт...' : 'Сделать шаг'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-sm text-white/80">
        <p>
          Это <span className="text-white">настоящий шаг мира</span>, такой же, как по расписанию. В каждом регионе в
          симуляции будут произведены и потреблены товары, изменятся запасы и цены, стабильность и достаток; жители
          заплатят налог, казна выплатит жалованье, страны раздадут дотации.
        </p>
        <p>Отменить шаг нельзя. Он попадёт в журнал операций и в список пересчётов как ручной.</p>
        <p className="text-white/50">
          Расписание не сдвигается: следующий автоматический пересчёт — {formatDateTime(nextSlotAt)}.
        </p>
        {busy && <p className="text-white/50">Идёт пересчёт регионов, это может занять некоторое время...</p>}
      </div>
    </ModalShell>
  );
};

interface EconomyTickProps {
  canSettings: boolean;
  /** Called after a run — it moves money (tax, wages, grants), so the summary is refreshed. */
  onMoneyChanged?: () => void;
}

/** «Пересчёт» (FEAT-182): tick schedule status, manual step, run history and the global simulation params. */
const EconomyTick = ({ canSettings, onMoneyChanged }: EconomyTickProps) => {
  const [sim, setSim] = useState<EconSimState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);
  const [savingParams, setSavingParams] = useState(false);
  const [togglingTick, setTogglingTick] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [lastResult, setLastResult] = useState<EconTickRun | null>(null);

  const load = useCallback((opts?: { silent?: boolean; resetForm?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    return fetchEconomySim()
      .then((state) => {
        setSim(state);
        setLoadError(null);
        if (opts?.resetForm) setForm(toForm(state.params));
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить состояние пересчёта');
        setLoadError(msg);
        if (!opts?.silent) toast.error(msg);
      })
      .finally(() => {
        if (!opts?.silent) setLoading(false);
      });
  }, []);

  useEffect(() => {
    load({ resetForm: true });
  }, [load]);

  const runningId = sim?.running?.id ?? null;
  useEffect(() => {
    if (runningId === null) return undefined;
    const timer = window.setInterval(() => {
      load({ silent: true });
    }, RUNNING_POLL_MS);
    return () => window.clearInterval(timer);
  }, [runningId, load]);

  const errors = useMemo(() => {
    if (!form) return {} as Partial<Record<ParamKey, string>>;
    const out: Partial<Record<ParamKey, string>> = {};
    ALL_PARAMS.forEach((p) => {
      const err = paramError(p, form[p.key]);
      if (err) out[p.key] = err;
    });
    RANGE_PAIRS.forEach(([lo, hi, msg]) => {
      if (!out[lo] && !out[hi] && parseNum(form[lo]) >= parseNum(form[hi])) out[hi] = msg;
    });
    return out;
  }, [form]);

  if (loadError && !sim) return <p className="text-site-red text-sm">{loadError}</p>;
  if (!sim || !form) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const formValid = Object.keys(errors).length === 0;
  const savedForm = toForm(sim.params);
  const dirty = ALL_PARAMS.some((p) => parseNum(form[p.key]) !== parseNum(savedForm[p.key]));
  const lastRun = sim.runs.find((r) => r.status !== 'running') ?? null;
  const autoActive = sim.env_enabled && sim.tick_enabled;
  const weightsSum = PROSP_WEIGHTS.every((k) => !errors[k])
    ? PROSP_WEIGHTS.reduce((acc, k) => acc + parseNum(form[k]), 0)
    : null;

  const parsedParams = (): EconSimParams =>
    Object.fromEntries(ALL_PARAMS.map((p) => [p.key, parseNum(form[p.key])])) as unknown as EconSimParams;

  const toggleTick = async (next: boolean) => {
    setTogglingTick(true);
    try {
      // Saved params go along unchanged — unsaved form edits are not sent by the toggle.
      const state = await putEconomySim({ tick_enabled: next, params: sim.params });
      setSim(state);
      toast.success(next ? 'Автопересчёт включён' : 'Автопересчёт выключен');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось переключить автопересчёт'));
    } finally {
      setTogglingTick(false);
    }
  };

  const saveParams = async () => {
    setSavingParams(true);
    try {
      const state = await putEconomySim({ tick_enabled: sim.tick_enabled, params: parsedParams() });
      setSim(state);
      setForm(toForm(state.params));
      toast.success('Параметры симуляции сохранены');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить параметры симуляции'));
    } finally {
      setSavingParams(false);
    }
  };

  const resetToDefaults = () => {
    setForm(Object.fromEntries(ALL_PARAMS.map((p) => [p.key, fmtNum(p.def)])) as FormState);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* ---------------------------------------------------------------- status */}
      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em] mr-auto">Расписание</h2>
          <button
            type="button"
            onClick={() => load()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
        </div>

        <p className="text-white/50 text-sm">
          Мир пересчитывается каждые 6 часов: регионы производят и потребляют товары, меняются цены, платятся налоги и
          жалованье.
        </p>

        <div className="flex items-start gap-3">
          <Switch
            checked={sim.tick_enabled}
            disabled={!canSettings || togglingTick}
            onChange={toggleTick}
            label="Автопересчёт по расписанию"
          />
          <span className="flex flex-col gap-0.5 min-w-0">
            <span className="text-white text-sm">Автопересчёт по расписанию {sim.tick_enabled ? 'включён' : 'выключен'}</span>
            {!canSettings && (
              <span className="text-white/40 text-xs">Переключать может администратор с правом «economy:settings».</span>
            )}
          </span>
        </div>

        {!sim.env_enabled && (
          <p className="text-sm text-gold rounded-card border border-gold/30 bg-gold/[0.06] px-4 py-3">
            На этом сервере планировщик не запущен (не задана переменная окружения ECON_TICK_ENABLED), поэтому
            автопересчёт не идёт, даже если переключатель включён. Ручной пересчёт работает.
          </p>
        )}

        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm">
          <div className="flex flex-col gap-0.5 min-w-0">
            <dt className="text-white/50 text-xs uppercase tracking-[0.06em]">Следующий пересчёт</dt>
            <dd className="text-white">
              {autoActive ? formatDateTime(sim.next_slot_at) : <span className="text-white/40">не запланирован</span>}
            </dd>
          </div>
          <div className="flex flex-col gap-0.5 min-w-0">
            <dt className="text-white/50 text-xs uppercase tracking-[0.06em]">Последний пересчёт</dt>
            <dd className="text-white break-words">
              {lastRun ? (
                <>
                  {formatDateTime(lastRun.finished_at ?? lastRun.started_at)}{' '}
                  <span className="text-white/50">· {TRIGGER_LABEL[lastRun.trigger_kind].toLowerCase()} · </span>
                  <StatusText status={lastRun.status} />
                </>
              ) : (
                <span className="text-white/40">ещё не было</span>
              )}
            </dd>
          </div>
          <div className="flex flex-col gap-0.5 min-w-0">
            <dt className="text-white/50 text-xs uppercase tracking-[0.06em]">Сейчас</dt>
            <dd className="text-white">
              {sim.running ? (
                <span className="inline-flex items-center gap-2 text-site-blue">
                  <RefreshCw size={14} className="animate-spin shrink-0" />
                  Идёт пересчёт: {sim.running.regions_done} из {sim.running.regions_total}
                </span>
              ) : (
                <span className="text-white/60">Пересчёт не идёт</span>
              )}
            </dd>
          </div>
        </dl>

        {canSettings && (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <button
              type="button"
              className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs inline-flex items-center justify-center gap-2"
              disabled={sim.running !== null}
              title={sim.running ? RUN_IN_PROGRESS_MESSAGE : undefined}
              onClick={() => setConfirmOpen(true)}
            >
              <Play size={14} />
              Пересчитать сейчас
            </button>
            <span className="text-white/40 text-xs">Дополнительный шаг мира; расписание не сдвигается.</span>
          </div>
        )}

        {lastResult && (
          <div className="text-sm text-white/80 rounded-card border border-stat-energy/30 bg-stat-energy/[0.06] px-4 py-3 flex flex-col gap-1">
            <span>
              Ручной пересчёт №{lastResult.id}: <StatusText status={lastResult.status} />
            </span>
            <span className="text-white/60">
              Регионов пересчитано: {lastResult.regions_done} из {lastResult.regions_total}
              {lastResult.regions_failed > 0 && <span className="text-site-red">, с ошибкой: {lastResult.regions_failed}</span>}
              {lastResult.finished_at && <> · длительность {formatDuration(lastResult)}</>}
            </span>
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------------- runs */}
      <section className="flex flex-col gap-3 min-w-0">
        <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Последние пересчёты</h2>
        {sim.runs.length === 0 ? (
          <p className="text-white/40 text-sm italic">Пересчётов ещё не было.</p>
        ) : (
          <>
            <div className="hidden lg:block bg-site-bg rounded-card border border-white/[0.07] px-4 py-2">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                    <th className="py-2 pr-3 font-normal">№</th>
                    <th className="py-2 pr-3 font-normal">Запуск</th>
                    <th className="py-2 pr-3 font-normal">Начат</th>
                    <th className="py-2 pr-3 font-normal">Длительность</th>
                    <th className="py-2 pr-3 font-normal">Регионы</th>
                    <th className="py-2 pr-3 font-normal">Статус</th>
                    <th className="py-2 font-normal">Ошибка</th>
                  </tr>
                </thead>
                <tbody>
                  {sim.runs.map((r) => (
                    <tr key={r.id} className="border-b border-white/[0.07] last:border-b-0 align-top">
                      <td className="py-2 pr-3 text-white/50">{r.id}</td>
                      <td className="py-2 pr-3 text-white/80 whitespace-nowrap">
                        {TRIGGER_LABEL[r.trigger_kind] ?? r.trigger_kind}
                        {r.trigger_kind === 'manual' && r.actor_user_id != null && (
                          <span className="block text-white/40 text-xs">админ #{r.actor_user_id}</span>
                        )}
                      </td>
                      <td className="py-2 pr-3 text-white/70 whitespace-nowrap">{formatDateTime(r.started_at)}</td>
                      <td className="py-2 pr-3 text-white/70 whitespace-nowrap">{formatDuration(r)}</td>
                      <td className="py-2 pr-3">
                        <RegionsCell run={r} />
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        <StatusText status={r.status} />
                      </td>
                      <td className="py-2 text-site-red text-xs break-words max-w-[320px]">{r.error || <span className="text-white/30">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="lg:hidden grid grid-cols-1 md:grid-cols-2 gap-3">
              {sim.runs.map((r) => (
                <li key={r.id} className="bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-1.5 text-sm min-w-0">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-white/50">№{r.id}</span>
                    <span className="text-white">{TRIGGER_LABEL[r.trigger_kind] ?? r.trigger_kind}</span>
                    <span className="ml-auto">
                      <StatusText status={r.status} />
                    </span>
                  </span>
                  <span className="text-white/60 text-xs">
                    {formatDateTime(r.started_at)} · {formatDuration(r)}
                  </span>
                  <span className="text-xs text-white/50">
                    Регионы: <RegionsCell run={r} />
                  </span>
                  {r.error && <span className="text-site-red text-xs break-words">{r.error}</span>}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {/* ---------------------------------------------------------------- params */}
      <section className="flex flex-col gap-4 min-w-0">
        <div className="flex flex-col gap-1">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Параметры симуляции</h2>
          <p className="text-white/50 text-sm">
            Общие для всех регионов. Изменения действуют со следующего пересчёта. Дробные числа можно писать через
            запятую.
          </p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {SECTIONS.map((section) => (
            <fieldset
              key={section.title}
              className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-5 flex flex-col gap-4 min-w-0"
            >
              <legend className="sr-only">{section.title}</legend>
              <div className="flex flex-col gap-1">
                <h3 className="text-white text-base font-medium uppercase tracking-[0.06em]">{section.title}</h3>
                <p className="text-white/40 text-xs">{section.intro}</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {section.params.map((p) => {
                  const err = errors[p.key];
                  return (
                    <div key={p.key} className="flex flex-col gap-1 min-w-0">
                      <label htmlFor={`econ-sim-${p.key}`} className="text-white/70 text-xs">
                        {p.label}
                      </label>
                      <input
                        id={`econ-sim-${p.key}`}
                        type="text"
                        inputMode={p.integer ? 'numeric' : 'decimal'}
                        className="input-underline w-full"
                        value={form[p.key]}
                        disabled={!canSettings}
                        maxLength={12}
                        onChange={(e) => setForm({ ...form, [p.key]: e.target.value })}
                      />
                      {err ? (
                        <p className="text-site-red text-xs">{err}</p>
                      ) : (
                        <p className="text-white/40 text-xs">
                          {p.hint} <span className="text-white/30">По умолчанию {fmtNum(p.def)}.</span>
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
              {section.title === 'Достаток' && weightsSum !== null && (
                <p className="text-white/50 text-xs">
                  Сумма трёх весов: {fmtNum(Math.round(weightsSum * 100) / 100)} — потолок достатка около{' '}
                  {Math.min(100, Math.round(weightsSum * 100))}.
                </p>
              )}
            </fieldset>
          ))}
        </div>

        {canSettings ? (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <button
              type="button"
              className="btn-blue w-full sm:w-auto !px-6"
              disabled={!formValid || !dirty || savingParams}
              onClick={saveParams}
            >
              {savingParams ? 'Сохранение...' : 'Сохранить параметры'}
            </button>
            <button
              type="button"
              className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5"
              disabled={!dirty || savingParams}
              onClick={() => setForm(savedForm)}
            >
              Отменить изменения
            </button>
            <button
              type="button"
              className="inline-flex items-center justify-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
              disabled={savingParams}
              onClick={resetToDefaults}
            >
              <RotateCcw size={14} />
              Вернуть по умолчанию
            </button>
            {!formValid && <span className="text-site-red text-xs">Исправьте поля, отмеченные красным.</span>}
          </div>
        ) : (
          <p className="field-hint">Изменять параметры может только администратор с правом «economy:settings».</p>
        )}
      </section>

      {confirmOpen && (
        <RunConfirm
          nextSlotAt={sim.next_slot_at}
          onClose={() => setConfirmOpen(false)}
          onConflict={() => {
            setConfirmOpen(false);
            load({ silent: true });
          }}
          onDone={(run) => {
            setConfirmOpen(false);
            setLastResult(run);
            if (run.status === 'done') toast.success(`Пересчёт выполнен: регионов ${run.regions_done}`);
            else if (run.status === 'partial') toast.error(`Пересчёт завершён с ошибками: ${run.regions_failed} из ${run.regions_total}`);
            else if (run.status === 'failed') toast.error('Пересчёт не удался ни в одном регионе');
            else toast.success('Пересчёт запущен');
            load({ silent: true });
            onMoneyChanged?.();
          }}
        />
      )}
    </div>
  );
};

export default EconomyTick;
