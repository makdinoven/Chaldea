import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  fetchLawSettings,
  putLawSettings,
  LAW_BAIL_MULTIPLIER_MAX,
  LAW_BAIL_MULTIPLIER_MIN,
  LAW_HOURS_MAX,
  LAW_JAIL_HOURS_MAX,
  LAW_JAIL_HOURS_MIN,
  LAW_LEVEL_CODES,
  LAW_MAX_FINE,
  LAW_MAX_WANTED_LIMIT,
  type LawLevel,
  type LawSettingsData,
  type LawSettingsValues,
} from '../../../api/lawAdmin';
import { apiErrorMessage } from '../../../api/errors';

interface LawSettingsTabProps {
  canEdit: boolean;
}

type NumericKey = Exclude<keyof LawSettingsValues, 'outlaw_min_level'>;

/** Numbers are kept as typed strings so a half-typed value does not jump. */
type SettingsForm = Record<NumericKey, string> & { outlaw_min_level: string };

interface LevelForm {
  code: string;
  name: string;
  min_value: string;
  fine: string;
  jail_hours: string;
}

interface FieldDef {
  key: NumericKey;
  label: string;
  hint: string;
  /** integer field (otherwise a decimal) */
  int: boolean;
  min: number;
  max: number;
}

interface FieldGroup {
  title: string;
  fields: FieldDef[];
}

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
const NUMBER_RE = /^\d*([.,]\d*)?$/;
const INT_RE = /^\d*$/;
const PCT_MAX = 100;
const EXTEND_PCT_MAX = 1000;
const NAME_MAX = 60;

const GROUPS: FieldGroup[] = [
  {
    title: 'Розыск',
    fields: [
      { key: 'max_wanted', label: 'Максимальный розыск', hint: 'Потолок очков розыска в одном крае', int: true, min: 1, max: LAW_MAX_WANTED_LIMIT },
      { key: 'decay_per_day', label: 'Спад в день', hint: 'Сколько очков розыска уходит за сутки; 0 — не спадает', int: false, min: 0, max: LAW_MAX_WANTED_LIMIT },
      { key: 'heavy_wanted', label: 'Тяжёлый розыск', hint: 'Минимум после нападения на стражу или побега', int: true, min: 1, max: LAW_MAX_WANTED_LIMIT },
    ],
  },
  {
    title: 'Стража',
    fields: [
      { key: 'encounter_timeout_hours', label: 'Время на ответ, ч', hint: 'Не ответил страже — автоматическая сдача (или штраф без тюрьмы)', int: true, min: 1, max: LAW_HOURS_MAX },
      { key: 'guard_ko_hours', label: 'Восстановление стражника, ч', hint: 'Сколько побеждённый стражник лежит без сознания', int: true, min: 1, max: LAW_HOURS_MAX },
      { key: 'flee_base_pct', label: 'Бегство: база, %', hint: 'Базовый шанс убежать от стражи', int: false, min: 0, max: PCT_MAX },
      { key: 'flee_per_point_pct', label: 'Бегство: за очко, %', hint: 'Прибавка за каждое очко ловкости + удачи', int: false, min: 0, max: PCT_MAX },
      { key: 'flee_min_pct', label: 'Бегство: минимум, %', hint: '', int: false, min: 0, max: PCT_MAX },
      { key: 'flee_max_pct', label: 'Бегство: максимум, %', hint: '', int: false, min: 0, max: PCT_MAX },
    ],
  },
  {
    title: 'Тюрьма',
    fields: [
      { key: 'escape_base_pct', label: 'Побег: база, %', hint: 'Базовый шанс побега из тюрьмы', int: false, min: 0, max: PCT_MAX },
      { key: 'escape_per_point_pct', label: 'Побег: за очко, %', hint: 'Прибавка за каждое очко ловкости + удачи', int: false, min: 0, max: PCT_MAX },
      { key: 'escape_min_pct', label: 'Побег: минимум, %', hint: '', int: false, min: 0, max: PCT_MAX },
      { key: 'escape_max_pct', label: 'Побег: максимум, %', hint: '', int: false, min: 0, max: PCT_MAX },
      { key: 'escape_cooldown_hours', label: 'Перерыв между побегами, ч', hint: '', int: true, min: 1, max: LAW_HOURS_MAX },
      { key: 'escape_fail_extend_pct', label: 'Продление после провала, %', hint: 'Процент от оставшегося срока', int: false, min: 0, max: EXTEND_PCT_MAX },
      { key: 'max_remaining_jail_hours', label: 'Предел срока, ч', hint: 'Больше этого после продлений сидеть не придётся', int: true, min: 1, max: LAW_HOURS_MAX },
      { key: 'bail_multiplier', label: 'Множитель залога', hint: 'Залог = штраф ступени × множитель', int: false, min: LAW_BAIL_MULTIPLIER_MIN, max: LAW_BAIL_MULTIPLIER_MAX },
    ],
  },
];

const ALL_FIELDS = GROUPS.flatMap((g) => g.fields);

const levelIndex = (code: string): number => (LAW_LEVEL_CODES as readonly string[]).indexOf(code);

const toSettingsForm = (s: LawSettingsValues): SettingsForm => {
  const form = { outlaw_min_level: s.outlaw_min_level } as SettingsForm;
  ALL_FIELDS.forEach((f) => {
    form[f.key] = String(s[f.key]);
  });
  return form;
};

const toLevelForms = (levels: LawLevel[]): LevelForm[] =>
  [...levels]
    .sort((a, b) => levelIndex(a.code) - levelIndex(b.code))
    .map((l) => ({
      code: l.code,
      name: l.name,
      min_value: String(l.min_value),
      fine: String(l.fine),
      jail_hours: String(l.jail_hours),
    }));

const parseNum = (v: string): number => Number(v.trim().replace(',', '.'));
const isNum = (v: string): boolean => v.trim() !== '' && Number.isFinite(parseNum(v));
const isIntIn = (v: string, min: number, max: number): boolean =>
  isNum(v) && Number.isInteger(parseNum(v)) && parseNum(v) >= min && parseNum(v) <= max;

/** «Закон» (FEAT-198): wanted, guards, jail settings and the 5 wanted levels. */
const LawSettingsTab = ({ canEdit }: LawSettingsTabProps) => {
  const [settings, setSettings] = useState<SettingsForm | null>(null);
  const [levels, setLevels] = useState<LevelForm[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = (d: LawSettingsData) => {
    setSettings(toSettingsForm(d.settings));
    setLevels(toLevelForms(d.levels));
  };

  useEffect(() => {
    let cancelled = false;
    fetchLawSettings()
      .then((d) => {
        if (!cancelled) apply(d);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить настройки закона');
        setLoadError(msg);
        toast.error(msg);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setField = (f: FieldDef, value: string) => {
    if (!(f.int ? INT_RE : NUMBER_RE).test(value)) return;
    setSettings((s) => (s ? { ...s, [f.key]: value } : s));
  };

  const setLevel = (index: number, key: keyof LevelForm, value: string) => {
    if (key !== 'name' && !INT_RE.test(value)) return;
    setLevels((list) => list.map((l, i) => (i === index ? { ...l, [key]: value } : l)));
  };

  const validate = (): string | null => {
    if (!settings) return 'Настройки ещё не загружены';
    for (const f of ALL_FIELDS) {
      const v = settings[f.key];
      if (!isNum(v)) return `Поле «${f.label}» — число`;
      if (f.int && !Number.isInteger(parseNum(v))) return `Поле «${f.label}» — целое число`;
      if (parseNum(v) < f.min || parseNum(v) > f.max) return `Поле «${f.label}»: от ${f.min} до ${f.max}`;
    }
    if (parseNum(settings.heavy_wanted) > parseNum(settings.max_wanted)) {
      return 'Тяжёлый розыск не может быть больше максимального';
    }
    if (parseNum(settings.flee_min_pct) > parseNum(settings.flee_max_pct)) return 'Бегство: минимум больше максимума';
    if (parseNum(settings.escape_min_pct) > parseNum(settings.escape_max_pct)) return 'Побег: минимум больше максимума';
    if (levelIndex(settings.outlaw_min_level) < 0) return 'Выберите ступень для «Вне закона»';

    let previous = 0;
    for (const l of levels) {
      const name = l.name.trim();
      if (!name || name.length > NAME_MAX) return `Название ступени — от 1 до ${NAME_MAX} символов`;
      if (!isIntIn(l.min_value, 1, LAW_MAX_WANTED_LIMIT)) return `Порог ступени «${name}» — целое число от 1`;
      if (parseNum(l.min_value) <= previous) return 'Пороги ступеней должны строго возрастать';
      if (parseNum(l.min_value) > parseNum(settings.max_wanted)) {
        return `Порог ступени «${name}» больше максимального розыска`;
      }
      if (!isIntIn(l.fine, 0, LAW_MAX_FINE)) return `Штраф ступени «${name}» — от 0 до ${LAW_MAX_FINE}`;
      if (!isIntIn(l.jail_hours, LAW_JAIL_HOURS_MIN, LAW_JAIL_HOURS_MAX)) {
        return `Срок ступени «${name}» — от ${LAW_JAIL_HOURS_MIN} до ${LAW_JAIL_HOURS_MAX} часов`;
      }
      previous = parseNum(l.min_value);
    }
    return null;
  };

  const save = async () => {
    const error = validate();
    if (error || !settings) {
      setSaveError(error ?? 'Проверьте поля');
      toast.error(error ?? 'Проверьте поля');
      return;
    }
    setSaveError(null);
    const values = { outlaw_min_level: settings.outlaw_min_level } as LawSettingsValues;
    ALL_FIELDS.forEach((f) => {
      values[f.key] = f.int ? Math.trunc(parseNum(settings[f.key])) : parseNum(settings[f.key]);
    });
    const body: LawSettingsData = {
      settings: values,
      levels: levels.map((l) => ({
        code: l.code,
        name: l.name.trim(),
        min_value: Math.trunc(parseNum(l.min_value)),
        fine: Math.trunc(parseNum(l.fine)),
        jail_hours: Math.trunc(parseNum(l.jail_hours)),
      })),
    };
    setSaving(true);
    try {
      apply(await putLawSettings(body));
      toast.success('Настройки закона сохранены');
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось сохранить настройки закона');
      setSaveError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  if (loadError && !settings) return <p className="text-site-red text-sm">{loadError}</p>;
  if (!settings) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const disabled = !canEdit || saving;
  const upperBound = (i: number): string => {
    const next = levels[i + 1];
    if (!next) return settings.max_wanted;
    return isNum(next.min_value) ? String(Math.trunc(parseNum(next.min_value)) - 1) : '…';
  };

  return (
    <div className="flex flex-col gap-5">
      {!canEdit && (
        <p className="text-white/50 text-sm">Только просмотр: менять настройки может администратор (право reputation:settings).</p>
      )}

      {GROUPS.map((g) => (
        <section key={g.title} className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">{g.title}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {g.fields.map((f) => (
              <label key={f.key} className="flex flex-col gap-1 min-w-0">
                <span className={LABEL}>{f.label}</span>
                <input className="input-underline w-full" inputMode={f.int ? 'numeric' : 'decimal'} value={settings[f.key]}
                  disabled={disabled} onChange={(e) => setField(f, e.target.value)} />
                {f.hint && <span className="text-white/40 text-xs">{f.hint}</span>}
              </label>
            ))}
            {g.title === 'Розыск' && (
              <label className="flex flex-col gap-1 min-w-0">
                <span className={LABEL}>«Вне закона» со ступени</span>
                <select className="input-underline w-full" value={settings.outlaw_min_level} disabled={disabled}
                  onChange={(e) => setSettings((s) => (s ? { ...s, outlaw_min_level: e.target.value } : s))}>
                  {levels.map((l) => (
                    <option key={l.code} value={l.code} className="bg-site-dark text-white">{l.name || l.code}</option>
                  ))}
                </select>
                <span className="text-white/40 text-xs">С этой ступени штраф не принимают: только сдаться или драться</span>
              </label>
            )}
          </div>
        </section>
      ))}

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <div className="flex flex-col gap-1">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Ступени розыска</h2>
          <p className="text-white/50 text-sm">
            Пять ступеней снизу вверх; порядок и коды фиксированы. Порог — с какого числа очков розыска действует
            ступень (строго по возрастанию, первый — от 1). Срок заключения — от {LAW_JAIL_HOURS_MIN} до{' '}
            {LAW_JAIL_HOURS_MAX} часов.
          </p>
        </div>

        <div className="hidden lg:grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 px-3">
          <span className={LABEL}>Название</span>
          <span className={LABEL}>Порог</span>
          <span className={LABEL}>Диапазон</span>
          <span className={LABEL}>Штраф</span>
          <span className={LABEL}>Срок, ч</span>
        </div>

        <div className="flex flex-col gap-2">
          {levels.map((l, i) => (
            <div key={l.code}
              className="grid grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 items-end lg:items-center p-3 rounded-card border border-white/[0.07] bg-white/[0.02]">
              <label className="flex flex-col gap-1 col-span-2 lg:col-span-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Название</span>
                <input className="input-underline w-full" maxLength={NAME_MAX} value={l.name} disabled={disabled}
                  onChange={(e) => setLevel(i, 'name', e.target.value)} />
                <span className="text-white/30 text-[11px]">{l.code}</span>
              </label>
              <label className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Порог</span>
                <input className="input-underline w-full" inputMode="numeric" value={l.min_value} disabled={disabled}
                  onChange={(e) => setLevel(i, 'min_value', e.target.value)} />
              </label>
              <div className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Диапазон</span>
                <span className="text-white/60 text-sm py-1 break-words">{l.min_value || '…'} … {upperBound(i)}</span>
              </div>
              <label className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Штраф</span>
                <input className="input-underline w-full" inputMode="numeric" value={l.fine} disabled={disabled}
                  onChange={(e) => setLevel(i, 'fine', e.target.value)} />
              </label>
              <label className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Срок, ч</span>
                <input className="input-underline w-full" inputMode="numeric" value={l.jail_hours} disabled={disabled}
                  onChange={(e) => setLevel(i, 'jail_hours', e.target.value)} />
              </label>
            </div>
          ))}
        </div>
      </section>

      {saveError && <p className="text-site-red text-sm">{saveError}</p>}

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

export default LawSettingsTab;
