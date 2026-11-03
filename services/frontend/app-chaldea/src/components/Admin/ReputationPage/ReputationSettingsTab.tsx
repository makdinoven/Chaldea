import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  fetchReputationSettings,
  putReputationSettings,
  type ReputationSettingsData,
  type ReputationTierAdmin,
} from '../../../api/reputationAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { invalidateReputationRefs, tierIndex } from './useReputationRefs';

interface ReputationSettingsTabProps {
  canEdit: boolean;
}

/** Form state: numbers are kept as typed strings so a half-typed «-» does not jump. */
interface SettingsForm {
  min_value: string;
  max_value: string;
  echo_pct: string;
  decay_per_day: string;
}

interface TierForm {
  code: string;
  name: string;
  min_value: string;
  price_pct: string;
  sell_pct: string;
  trade_refused: boolean;
}

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
const NUMBER_RE = /^-?\d*([.,]\d*)?$/;

const toSettingsForm = (d: ReputationSettingsData): SettingsForm => ({
  min_value: String(d.settings.min_value),
  max_value: String(d.settings.max_value),
  echo_pct: String(d.settings.echo_pct),
  decay_per_day: String(d.settings.decay_per_day),
});

const toTierForms = (tiers: ReputationTierAdmin[]): TierForm[] =>
  [...tiers]
    .sort((a, b) => tierIndex(a.code) - tierIndex(b.code))
    .map((t) => ({
      code: t.code,
      name: t.name,
      min_value: t.min_value == null ? '' : String(t.min_value),
      price_pct: String(t.price_pct),
      sell_pct: String(t.sell_pct),
      trade_refused: t.trade_refused,
    }));

const parseNum = (v: string): number => Number(v.trim().replace(',', '.'));
const isNum = (v: string): boolean => v.trim() !== '' && Number.isFinite(parseNum(v));

/** «Ступени и общие»: range, echo, decay and the 8 tiers (names, thresholds, price / bid modifiers, refusal). */
const ReputationSettingsTab = ({ canEdit }: ReputationSettingsTabProps) => {
  const [settings, setSettings] = useState<SettingsForm | null>(null);
  const [tiers, setTiers] = useState<TierForm[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = (d: ReputationSettingsData) => {
    setSettings(toSettingsForm(d));
    setTiers(toTierForms(d.tiers));
  };

  useEffect(() => {
    let cancelled = false;
    fetchReputationSettings()
      .then((d) => {
        if (!cancelled) apply(d);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить настройки репутации');
        setLoadError(msg);
        toast.error(msg);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setField = (key: keyof SettingsForm, value: string) => {
    if (!NUMBER_RE.test(value)) return;
    setSettings((s) => (s ? { ...s, [key]: value } : s));
  };

  const setTier = <K extends keyof TierForm>(index: number, key: K, value: TierForm[K]) => {
    if (typeof value === 'string' && key !== 'name' && !NUMBER_RE.test(value)) return;
    setTiers((list) => list.map((t, i) => (i === index ? { ...t, [key]: value } : t)));
  };

  const validate = (): string | null => {
    if (!settings) return 'Настройки ещё не загружены';
    const fields: [keyof SettingsForm, string][] = [
      ['min_value', 'Минимум'],
      ['max_value', 'Максимум'],
      ['echo_pct', 'Отголосок'],
      ['decay_per_day', 'Забывание'],
    ];
    for (const [key, label] of fields) {
      if (!isNum(settings[key])) return `Поле «${label}» — число`;
    }
    for (let i = 0; i < tiers.length; i += 1) {
      const t = tiers[i];
      if (!t.name.trim()) return 'У каждой ступени должно быть название';
      if (t.name.trim().length > 60) return `Название «${t.name}» — не длиннее 60 символов`;
      if (i > 0 && !isNum(t.min_value)) return `У ступени «${t.name}» должен быть нижний порог`;
      if (!isNum(t.price_pct) || !isNum(t.sell_pct)) return `У ступени «${t.name}» проценты должны быть числами`;
    }
    return null;
  };

  const save = async () => {
    const error = validate();
    if (error || !settings) {
      toast.error(error ?? 'Проверьте поля');
      return;
    }
    const body: ReputationSettingsData = {
      settings: {
        min_value: Math.trunc(parseNum(settings.min_value)),
        max_value: Math.trunc(parseNum(settings.max_value)),
        echo_pct: parseNum(settings.echo_pct),
        decay_per_day: parseNum(settings.decay_per_day),
      },
      tiers: tiers.map((t, i) => ({
        code: t.code,
        name: t.name.trim(),
        min_value: i === 0 ? null : Math.trunc(parseNum(t.min_value)),
        price_pct: parseNum(t.price_pct),
        sell_pct: parseNum(t.sell_pct),
        trade_refused: t.trade_refused,
      })),
    };
    setSaving(true);
    try {
      const saved = await putReputationSettings(body);
      apply(saved);
      invalidateReputationRefs();
      toast.success('Настройки репутации сохранены');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить настройки репутации'));
    } finally {
      setSaving(false);
    }
  };

  if (loadError && !settings) return <p className="text-site-red text-sm">{loadError}</p>;
  if (!settings) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const disabled = !canEdit || saving;
  const upperBound = (i: number): string => {
    const next = tiers[i + 1];
    if (!next) return settings.max_value;
    return isNum(next.min_value) ? String(Math.trunc(parseNum(next.min_value)) - 1) : '…';
  };

  return (
    <div className="flex flex-col gap-5">
      {!canEdit && (
        <p className="text-white/50 text-sm">Только просмотр: менять настройки может администратор (право reputation:settings).</p>
      )}

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Общие</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <label className="flex flex-col gap-1">
            <span className={LABEL}>Минимум</span>
            <input className="input-underline" inputMode="numeric" value={settings.min_value} disabled={disabled}
              onChange={(e) => setField('min_value', e.target.value)} />
            <span className="text-white/40 text-xs">Нижняя граница репутации (меньше 0)</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={LABEL}>Максимум</span>
            <input className="input-underline" inputMode="numeric" value={settings.max_value} disabled={disabled}
              onChange={(e) => setField('max_value', e.target.value)} />
            <span className="text-white/40 text-xs">Верхняя граница (больше 0)</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={LABEL}>Отголосок, %</span>
            <input className="input-underline" inputMode="decimal" value={settings.echo_pct} disabled={disabled}
              onChange={(e) => setField('echo_pct', e.target.value)} />
            <span className="text-white/40 text-xs">Доля изменения в остальных регионах той же страны (0–100)</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={LABEL}>Забывание, очков в день</span>
            <input className="input-underline" inputMode="decimal" value={settings.decay_per_day} disabled={disabled}
              onChange={(e) => setField('decay_per_day', e.target.value)} />
            <span className="text-white/40 text-xs">Только отрицательная репутация ползёт к нулю; 0 — не забывается</span>
          </label>
        </div>
      </section>

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <div className="flex flex-col gap-1">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Ступени</h2>
          <p className="text-white/50 text-sm">
            Восемь ступеней снизу вверх; порядок и коды фиксированы, «Скиталец» должен включать 0. Цена: «+» — скидка у
            торговцев (до 50 %), «−» — наценка (до 100 %). Скупка: сколько меньше торговцы платят игроку (0 или
            отрицательное). «Не торгуют» — обычные торговцы и гильдия отказывают.
          </p>
        </div>

        <div className="hidden lg:grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] gap-3 px-3">
          <span className={LABEL}>Название</span>
          <span className={LABEL}>Нижний порог</span>
          <span className={LABEL}>Диапазон</span>
          <span className={LABEL}>Цена, %</span>
          <span className={LABEL}>Скупка, %</span>
          <span className={LABEL}>Не торгуют</span>
        </div>

        <div className="flex flex-col gap-2">
          {tiers.map((t, i) => (
            <div key={t.code}
              className="grid grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] gap-3 items-end lg:items-center p-3 rounded-card border border-white/[0.07] bg-white/[0.02]">
              <label className="flex flex-col gap-1 col-span-2 lg:col-span-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Название</span>
                <input className="input-underline w-full" maxLength={60} value={t.name} disabled={disabled}
                  onChange={(e) => setTier(i, 'name', e.target.value)} />
                <span className="text-white/30 text-[11px]">{t.code}</span>
              </label>
              <label className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Нижний порог</span>
                {i === 0 ? (
                  <span className="text-white/40 text-sm py-1">— (минимум)</span>
                ) : (
                  <input className="input-underline w-full" inputMode="numeric" value={t.min_value} disabled={disabled}
                    onChange={(e) => setTier(i, 'min_value', e.target.value)} />
                )}
              </label>
              <div className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Диапазон</span>
                <span className="text-white/60 text-sm py-1 break-words">
                  {i === 0 ? settings.min_value : t.min_value || '…'} … {upperBound(i)}
                </span>
              </div>
              <label className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Цена, %</span>
                <input className="input-underline w-full" inputMode="decimal" value={t.price_pct} disabled={disabled}
                  onChange={(e) => setTier(i, 'price_pct', e.target.value)} />
              </label>
              <label className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Скупка, %</span>
                <input className="input-underline w-full" inputMode="decimal" value={t.sell_pct} disabled={disabled}
                  onChange={(e) => setTier(i, 'sell_pct', e.target.value)} />
              </label>
              <label className="flex items-center gap-2 cursor-pointer select-none col-span-2 lg:col-span-1 lg:justify-center">
                <input type="checkbox" className="w-4 h-4 accent-gold" checked={t.trade_refused} disabled={disabled}
                  onChange={(e) => setTier(i, 'trade_refused', e.target.checked)} />
                <span className="text-white/70 text-sm lg:hidden">Обычные торговцы не торгуют</span>
              </label>
            </div>
          ))}
        </div>
      </section>

      {canEdit && (
        <div>
          <button type="button" className="btn-blue w-full sm:w-auto !px-8 disabled:opacity-50" disabled={saving}
            onClick={() => void save()}>
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      )}
    </div>
  );
};

export default ReputationSettingsTab;
