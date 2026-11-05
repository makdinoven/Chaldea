import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  fetchShadowSettings,
  putShadowSettings,
  FAME_TIER_CODES,
  INFAMY_TIER_CODES,
  SHADOW_MAX_DECAY_PER_DAY,
  SHADOW_MAX_FAME_QUEST,
  SHADOW_MAX_INFAMY_MIN_GAIN,
  SHADOW_MAX_PER_POINT,
  SHADOW_MAX_RATIO,
  SHADOW_MAX_REVEAL_DAYS,
  SHADOW_MAX_SUBCLASS_STEALTH,
  SHADOW_MAX_SUSPICION,
  SHADOW_MAX_TIER_VALUE,
  SHADOW_MAX_TIER_WITNESS_PCT,
  type ShadowSettingsData,
  type ShadowSettingsValues,
} from '../../../api/shadowAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { invalidateShadowRefs } from './useShadowRefs';

interface ShadowSettingsTabProps {
  canEdit: boolean;
}

type NumericKey = Exclude<keyof ShadowSettingsValues, 'witness_enabled'>;

/** Numbers are kept as typed strings so a half-typed value does not jump. */
type SettingsForm = Record<NumericKey, string> & { witness_enabled: boolean };

interface TierForm {
  code: string;
  name: string;
  min_value: string;
  /** fame only */
  witness_pct: string;
}

type Scale = 'fame' | 'infamy';

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
  note?: string;
  fields: FieldDef[];
}

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
const NUMBER_RE = /^\d*([.,]\d*)?$/;
const INT_RE = /^\d*$/;
const PCT_MAX = 100;
const NAME_MAX = 60;
const SUBCLASS_STEALTH_HINT = 'Очки скрытности, добавляются до капа; действуют на свидетелей, бегство и побег';

const GROUPS: FieldGroup[] = [
  {
    title: 'Свидетели',
    note:
      'Шанс, что преступление заметят: база локации × (1 − снижение скрытности) × узнаваемость славы (без маски). ' +
      'База зависит от типа локации; локации без типа считаются поселением («safe»). ' +
      'Шанс группы — самый заметный участник × множитель за каждого следующего.',
    fields: [
      { key: 'witness_base_safe_pct', label: 'База: поселение, %', hint: 'Локации с типом «safe» и без типа; множится на (1 − снижение скрытности)', int: false, min: 0, max: PCT_MAX },
      { key: 'witness_base_farm_pct', label: 'База: угодья, %', hint: 'Тип «farm»; множится на (1 − снижение скрытности)', int: false, min: 0, max: PCT_MAX },
      { key: 'witness_base_dangerous_pct', label: 'База: дикие места, %', hint: 'Тип «dangerous»; множится на (1 − снижение скрытности)', int: false, min: 0, max: PCT_MAX },
      { key: 'witness_base_dungeon_pct', label: 'База: подземелье, %', hint: 'Тип «dungeon»; множится на (1 − снижение скрытности)', int: false, min: 0, max: PCT_MAX },
      { key: 'witness_base_default_pct', label: 'База: прочее, %', hint: 'Нет локации или неизвестный тип; множится на (1 − снижение скрытности)', int: false, min: 0, max: PCT_MAX },
      { key: 'stealth_pct_per_point', label: 'Снижение за очко скрытности, %', hint: 'Шанс × (1 − скрытность × значение / 100); скрытность — эффективная, после капа', int: false, min: 0, max: SHADOW_MAX_PER_POINT },
      { key: 'stealth_max_reduction_pct', label: 'Предел снижения, %', hint: 'Больше этого скрытность шанс не снижает', int: false, min: 0, max: PCT_MAX },
      { key: 'stealth_assassin_points', label: 'Скрытность подкласса «Ассасин»', hint: SUBCLASS_STEALTH_HINT, int: true, min: 0, max: SHADOW_MAX_SUBCLASS_STEALTH },
      { key: 'stealth_trickster_points', label: 'Скрытность подкласса «Фокусник»', hint: SUBCLASS_STEALTH_HINT, int: true, min: 0, max: SHADOW_MAX_SUBCLASS_STEALTH },
      { key: 'stealth_agent_points', label: 'Скрытность подкласса «Агент»', hint: SUBCLASS_STEALTH_HINT, int: true, min: 0, max: SHADOW_MAX_SUBCLASS_STEALTH },
      { key: 'witness_group_per_extra_pct', label: 'За участника группы, %', hint: '+N % к шансу за каждого участника после первого (множитель)', int: false, min: 0, max: PCT_MAX },
      { key: 'witness_min_pct', label: 'Минимум, %', hint: '', int: false, min: 0, max: PCT_MAX },
      { key: 'witness_max_pct', label: 'Максимум, %', hint: 'Не больше 100', int: false, min: 0, max: PCT_MAX },
    ],
  },
  {
    title: 'Раскрытие',
    note:
      'Раз в сутки по каждому нераскрытому делу бросается шанс раскрытия; после срока дело закрывается навсегда. ' +
      'Шанс умножается на (1 − снижение скрытности преступника на момент преступления).',
    fields: [
      { key: 'reveal_days', label: 'Срок раскрытия, дней', hint: 'Сколько суток дело можно раскрыть', int: true, min: 1, max: SHADOW_MAX_REVEAL_DAYS },
      { key: 'reveal_base_pct', label: 'База, %', hint: 'Шанс раскрытия в день', int: false, min: 0, max: PCT_MAX },
      { key: 'reveal_per_suspicion_pct', label: 'За очко подозрения, %', hint: 'Плюс за каждое очко подозрения края', int: false, min: 0, max: SHADOW_MAX_PER_POINT },
      { key: 'reveal_mask_factor_pct', label: 'Множитель для маски, %', hint: 'Шанс в маске × этот процент', int: false, min: 0, max: PCT_MAX },
      { key: 'reveal_min_pct', label: 'Минимум, %', hint: '', int: false, min: 0, max: PCT_MAX },
      { key: 'reveal_max_pct', label: 'Максимум, %', hint: '', int: false, min: 0, max: PCT_MAX },
    ],
  },
  {
    title: 'Подозрение края',
    note: 'Растёт от незамеченных преступлений и спадает со временем. Игроки видят только текст состояния края.',
    fields: [
      { key: 'suspicion_max', label: 'Максимум', hint: 'Потолок подозрения в одном крае', int: true, min: 1, max: SHADOW_MAX_SUSPICION },
      { key: 'suspicion_unwitnessed', label: 'За незамеченное', hint: 'Прибавка за преступление без свидетелей', int: true, min: 0, max: SHADOW_MAX_SUSPICION },
      { key: 'suspicion_masked', label: 'За преступление в маске', hint: 'Прибавка, если видели лишь маску', int: true, min: 0, max: SHADOW_MAX_SUSPICION },
      { key: 'suspicion_decay_per_day', label: 'Спад в день', hint: '0 — не спадает', int: false, min: 0, max: SHADOW_MAX_DECAY_PER_DAY },
      { key: 'suspicion_uneasy_at', label: '«В крае неспокойно» с', hint: '', int: true, min: 1, max: SHADOW_MAX_SUSPICION },
      { key: 'suspicion_alarmed_at', label: '«Край встревожен» с', hint: '', int: true, min: 1, max: SHADOW_MAX_SUSPICION },
      { key: 'suspicion_fear_at', label: '«Край охвачен страхом» с', hint: '', int: true, min: 1, max: SHADOW_MAX_SUSPICION },
    ],
  },
  {
    title: 'Дурная слава',
    note: 'Тайная шкала: растёт за каждое преступление, замеченное или нет. Игрок видит лишь название ступени «слухов».',
    fields: [
      { key: 'infamy_ratio', label: 'Множитель', hint: 'Очки розыска преступления × множитель', int: false, min: 0, max: SHADOW_MAX_RATIO },
      { key: 'infamy_min_gain', label: 'Минимум за преступление', hint: '', int: true, min: 0, max: SHADOW_MAX_INFAMY_MIN_GAIN },
    ],
  },
  {
    title: 'Слава',
    note: 'Публичная шкала: задания и добрые дела. Чем громче имя, тем легче узнать персонажа при преступлении.',
    fields: [
      { key: 'fame_quest_default', label: 'За задание по умолчанию', hint: 'Если у задания не указано своё значение', int: true, min: 0, max: SHADOW_MAX_FAME_QUEST },
      { key: 'fame_rep_ratio', label: 'Доля от репутации', hint: 'Положительная репутация × доля (кроме заданий)', int: false, min: 0, max: SHADOW_MAX_RATIO },
      { key: 'fame_guild_ratio', label: 'Доля от заказов гильдии', hint: '0 — заказы гильдии славы не дают', int: false, min: 0, max: SHADOW_MAX_RATIO },
    ],
  },
];

const ALL_FIELDS = GROUPS.flatMap((g) => g.fields);

const SCALE_CODES: Record<Scale, readonly string[]> = { fame: FAME_TIER_CODES, infamy: INFAMY_TIER_CODES };
const SCALE_TITLES: Record<Scale, string> = { fame: 'Ступени славы', infamy: 'Ступени дурной славы' };
const SCALE_GENITIVE: Record<Scale, string> = { fame: 'славы', infamy: 'дурной славы' };

const parseNum = (v: string): number => Number(v.trim().replace(',', '.'));
const isNum = (v: string): boolean => v.trim() !== '' && Number.isFinite(parseNum(v));

const toSettingsForm = (s: ShadowSettingsValues): SettingsForm => {
  const form = { witness_enabled: s.witness_enabled } as SettingsForm;
  ALL_FIELDS.forEach((f) => {
    form[f.key] = String(s[f.key]);
  });
  return form;
};

const toTierForms = (scale: Scale, tiers: { code: string; name: string; min_value: number; witness_pct?: number }[]): TierForm[] => {
  const codes = SCALE_CODES[scale];
  return [...tiers]
    .sort((a, b) => codes.indexOf(a.code) - codes.indexOf(b.code))
    .map((t) => ({ code: t.code, name: t.name, min_value: String(t.min_value), witness_pct: String(t.witness_pct ?? 0) }));
};

/** «Тень и слава» (FEAT-199): witnesses, reveal, region suspicion, infamy, fame + the two 5-tier ladders. */
const ShadowSettingsTab = ({ canEdit }: ShadowSettingsTabProps) => {
  const [settings, setSettings] = useState<SettingsForm | null>(null);
  const [tiers, setTiers] = useState<Record<Scale, TierForm[]>>({ fame: [], infamy: [] });
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = (d: ShadowSettingsData) => {
    setSettings(toSettingsForm(d.settings));
    setTiers({ fame: toTierForms('fame', d.fame_tiers), infamy: toTierForms('infamy', d.infamy_tiers) });
  };

  useEffect(() => {
    let cancelled = false;
    fetchShadowSettings()
      .then((d) => {
        if (!cancelled) apply(d);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить настройки тени и славы');
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

  const setTier = (scale: Scale, index: number, key: keyof TierForm, value: string) => {
    if (key === 'min_value' && !INT_RE.test(value)) return;
    if (key === 'witness_pct' && !NUMBER_RE.test(value)) return;
    setTiers((all) => ({ ...all, [scale]: all[scale].map((t, i) => (i === index ? { ...t, [key]: value } : t)) }));
  };

  const validate = (): string | null => {
    if (!settings) return 'Настройки ещё не загружены';
    for (const f of ALL_FIELDS) {
      const v = settings[f.key];
      if (!isNum(v)) return `Поле «${f.label}» — число`;
      if (f.int && !Number.isInteger(parseNum(v))) return `Поле «${f.label}» — целое число`;
      if (parseNum(v) < f.min || parseNum(v) > f.max) return `Поле «${f.label}»: от ${f.min} до ${f.max}`;
    }
    const n = (k: NumericKey) => parseNum(settings[k]);
    if (n('witness_min_pct') > n('witness_max_pct')) return 'Шанс свидетелей: минимум больше максимума';
    if (n('reveal_min_pct') > n('reveal_max_pct')) return 'Шанс раскрытия: минимум больше максимума';
    if (n('suspicion_unwitnessed') > n('suspicion_max') || n('suspicion_masked') > n('suspicion_max')) {
      return 'Прибавка подозрения не может быть больше максимального подозрения';
    }
    if (!(n('suspicion_uneasy_at') < n('suspicion_alarmed_at') && n('suspicion_alarmed_at') < n('suspicion_fear_at')
      && n('suspicion_fear_at') <= n('suspicion_max'))) {
      return 'Пороги подозрения должны строго возрастать и не превышать максимум';
    }
    for (const scale of ['fame', 'infamy'] as Scale[]) {
      let previous = -1;
      for (const [i, t] of tiers[scale].entries()) {
        const name = t.name.trim();
        if (!name || name.length > NAME_MAX) return `Название ступени ${SCALE_GENITIVE[scale]} — от 1 до ${NAME_MAX} символов`;
        if (!isNum(t.min_value) || !Number.isInteger(parseNum(t.min_value))) return `Порог ступени «${name}» — целое число`;
        const min = parseNum(t.min_value);
        if (i === 0 && min !== 0) return `Первая ступень ${SCALE_GENITIVE[scale]} должна начинаться с 0`;
        if (i > 0 && min <= previous) return `Пороги ступеней ${SCALE_GENITIVE[scale]} должны строго возрастать`;
        if (min > SHADOW_MAX_TIER_VALUE) return `Порог ступени «${name}» слишком большой`;
        if (scale === 'fame') {
          if (!isNum(t.witness_pct) || parseNum(t.witness_pct) < 0 || parseNum(t.witness_pct) > SHADOW_MAX_TIER_WITNESS_PCT) {
            return `Узнаваемость ступени «${name}» (множитель): от 0 до ${SHADOW_MAX_TIER_WITNESS_PCT} %`;
          }
        }
        previous = min;
      }
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
    const values = { witness_enabled: settings.witness_enabled } as ShadowSettingsValues;
    ALL_FIELDS.forEach((f) => {
      values[f.key] = f.int ? Math.trunc(parseNum(settings[f.key])) : parseNum(settings[f.key]);
    });
    const body: ShadowSettingsData = {
      settings: values,
      fame_tiers: tiers.fame.map((t) => ({
        code: t.code,
        name: t.name.trim(),
        min_value: Math.trunc(parseNum(t.min_value)),
        witness_pct: parseNum(t.witness_pct),
      })),
      infamy_tiers: tiers.infamy.map((t) => ({ code: t.code, name: t.name.trim(), min_value: Math.trunc(parseNum(t.min_value)) })),
    };
    setSaving(true);
    try {
      apply(await putShadowSettings(body));
      invalidateShadowRefs();
      toast.success('Настройки тени и славы сохранены');
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось сохранить настройки тени и славы');
      setSaveError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  if (loadError && !settings) return <p className="text-site-red text-sm">{loadError}</p>;
  if (!settings) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const disabled = !canEdit || saving;

  const tierTable = (scale: Scale) => {
    const fame = scale === 'fame';
    const cols = fame
      ? 'lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]'
      : 'lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]';
    const list = tiers[scale];
    const upper = (i: number): string => {
      const next = list[i + 1];
      if (!next) return '∞';
      return isNum(next.min_value) ? String(Math.trunc(parseNum(next.min_value)) - 1) : '…';
    };
    return (
      <section key={scale} className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <div className="flex flex-col gap-1">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">{SCALE_TITLES[scale]}</h2>
          <p className="text-white/50 text-sm">
            Пять ступеней снизу вверх; порядок и коды фиксированы. Первая начинается с 0, пороги строго возрастают.
            {fame
              ? ` Узнаваемость — множитель шанса свидетелей у персонажа без маски: шанс × (1 + N / 100), до ${SHADOW_MAX_TIER_WITNESS_PCT} %.`
              : ' Игрок видит название ступени как «слухи в подполье», без чисел.'}
          </p>
        </div>

        <div className={`hidden lg:grid ${cols} gap-3 px-3`}>
          <span className={LABEL}>Название</span>
          <span className={LABEL}>Порог</span>
          <span className={LABEL}>Диапазон</span>
          {fame && <span className={LABEL}>Узнаваемость, % (множитель)</span>}
        </div>

        <div className="flex flex-col gap-2">
          {list.map((t, i) => (
            <div key={t.code}
              className={`grid grid-cols-2 ${cols} gap-3 items-end lg:items-center p-3 rounded-card border border-white/[0.07] bg-white/[0.02]`}>
              <label className="flex flex-col gap-1 col-span-2 lg:col-span-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Название</span>
                <input className="input-underline w-full" maxLength={NAME_MAX} value={t.name} disabled={disabled}
                  onChange={(e) => setTier(scale, i, 'name', e.target.value)} />
                <span className="text-white/30 text-[11px]">{t.code}</span>
              </label>
              <label className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Порог</span>
                <input className="input-underline w-full" inputMode="numeric" value={t.min_value}
                  disabled={disabled || i === 0} onChange={(e) => setTier(scale, i, 'min_value', e.target.value)} />
              </label>
              <div className="flex flex-col gap-1 min-w-0">
                <span className={`${LABEL} lg:hidden`}>Диапазон</span>
                <span className="text-white/60 text-sm py-1 break-words">{t.min_value || '…'} … {upper(i)}</span>
              </div>
              {fame && (
                <label className="flex flex-col gap-1 min-w-0">
                  <span className={`${LABEL} lg:hidden`}>Узнаваемость, % (множитель)</span>
                  <input className="input-underline w-full" inputMode="decimal" value={t.witness_pct} disabled={disabled}
                    onChange={(e) => setTier(scale, i, 'witness_pct', e.target.value)} />
                </label>
              )}
            </div>
          ))}
        </div>
      </section>
    );
  };

  return (
    <div className="flex flex-col gap-5">
      {!canEdit && (
        <p className="text-white/50 text-sm">Только просмотр: менять настройки может администратор (право reputation:settings).</p>
      )}

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-2 min-w-0">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="w-5 h-5 mt-0.5 accent-site-blue shrink-0" checked={settings.witness_enabled}
            disabled={disabled} onChange={(e) => setSettings((s) => (s ? { ...s, witness_enabled: e.target.checked } : s))} />
          <span className="flex flex-col gap-0.5">
            <span className="text-white text-sm">Бросок свидетелей включён</span>
            <span className="text-white/40 text-xs">
              Выключено — каждое преступление сразу «замечено», как до появления тени (репутация и розыск применяются сразу).
            </span>
          </span>
        </label>
      </section>

      {GROUPS.map((g) => (
        <section key={g.title} className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
          <div className="flex flex-col gap-1">
            <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">{g.title}</h2>
            {g.note && <p className="text-white/50 text-sm">{g.note}</p>}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {g.fields.map((f) => (
              <label key={f.key} className="flex flex-col gap-1 min-w-0">
                <span className={LABEL}>{f.label}</span>
                <input className="input-underline w-full" inputMode={f.int ? 'numeric' : 'decimal'} value={settings[f.key]}
                  disabled={disabled} onChange={(e) => setField(f, e.target.value)} />
                {f.hint && <span className="text-white/40 text-xs">{f.hint}</span>}
              </label>
            ))}
          </div>
        </section>
      ))}

      {tierTable('fame')}
      {tierTable('infamy')}

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

export default ShadowSettingsTab;
