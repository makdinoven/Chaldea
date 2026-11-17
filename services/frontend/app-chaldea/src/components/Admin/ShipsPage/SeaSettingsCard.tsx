import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchSeaSettings, saveSeaSettings, seaAdminError, seaRangeText, SEA_LIMITS } from '../../../api/seaAdmin';
import type { SeaSettings } from '../../../types/seaAdmin';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';

type SettingKey = keyof SeaSettings;

interface FieldDef {
  key: SettingKey;
  label: string;
  hint: string;
  step: number;
}

const GROUPS: { title: string; note?: string; fields: FieldDef[] }[] = [
  {
    title: 'Плавание',
    fields: [
      {
        key: 'sailor_post_min_chars',
        label: 'Длина поста матроса, символов',
        hint: 'Сколько нужно отписать на палубе до отплытия, чтобы проезд матросом засчитался (без HTML)',
        step: 1,
      },
      {
        key: 'stowaway_base_pct',
        label: 'Шанс поймать зайца, %',
        hint: 'Базовый шанс команды заметить безбилетника; скрытность персонажа его снижает',
        step: 0.01,
      },
      {
        key: 'stowaway_wanted_points',
        label: 'Очки розыска за пойманного зайца',
        hint: 'Преступление «безбилетный проезд» в крае порта',
        step: 1,
      },
      {
        key: 'path_max_zones',
        label: 'Предел зон на один участок',
        hint: 'Ограничение поиска пути и длины ручного пути между двумя портами',
        step: 1,
      },
    ],
  },
  {
    title: 'Шторма',
    note: 'Шанс появления шторма задаётся для каждого моря на вкладке «Погода».',
    fields: [
      { key: 'storm_min_minutes', label: 'Шторм длится от, мин', hint: 'Нижняя граница случайной длительности', step: 1 },
      { key: 'storm_max_minutes', label: 'Шторм длится до, мин', hint: 'Не меньше нижней границы', step: 1 },
      {
        key: 'storm_move_pct',
        label: 'Шанс сместиться, %',
        hint: 'Когда время шторма выходит, он может перейти в соседнюю зону того же моря и начаться заново',
        step: 0.01,
      },
      { key: 'storm_max_moves', label: 'Смещений за жизнь шторма', hint: 'Сколько раз один шторм может перейти в соседнюю зону', step: 1 },
      {
        key: 'storm_slow_mult',
        label: 'Замедление в шторм, раз',
        hint: 'Во сколько раз дольше корабль проходит зону шторма',
        step: 0.01,
      },
      {
        key: 'storm_drift_pct',
        label: 'Шанс сноса с курса, %',
        hint: 'При входе в зону шторма корабль может отнести в соседнюю зону',
        step: 0.01,
      },
      {
        key: 'storm_hp_pct',
        label: 'Урон здоровью, % от максимума',
        hint: 'Один раз при входе в зону шторма; здоровье не падает ниже 1',
        step: 0.01,
      },
      {
        key: 'storm_stamina_pct',
        label: 'Урон выносливости, % от максимума',
        hint: 'Один раз при входе в зону шторма',
        step: 0.01,
      },
      {
        key: 'storm_postpone_minutes',
        label: 'Перенос отплытия, мин',
        hint: 'На сколько откладывается отплытие, пока над портом шторм',
        step: 1,
      },
      {
        key: 'storm_postpone_max_minutes',
        label: 'Предел переноса отплытия, мин',
        hint: 'Сколько всего корабль готов ждать, затем отплывает в любую погоду (0 — не ждёт)',
        step: 1,
      },
      {
        key: 'storm_sailor_relief_pct',
        label: 'Облегчение от матросов, %',
        hint: 'Какую долю штормовой задержки снимает пост матроса на палубе (раз за зону)',
        step: 0.01,
      },
    ],
  },
  {
    title: 'Сезоны',
    note: 'Множитель шанса штормов по сезону игрового календаря.',
    fields: [
      { key: 'season_mult_spring', label: 'Весна, ×', hint: 'Множитель шанса нового шторма весной', step: 0.01 },
      { key: 'season_mult_summer', label: 'Лето, ×', hint: 'Множитель шанса шторма летом', step: 0.01 },
      { key: 'season_mult_autumn', label: 'Осень, ×', hint: 'Множитель шанса шторма осенью', step: 0.01 },
      { key: 'season_mult_winter', label: 'Зима, ×', hint: 'Множитель шанса шторма зимой', step: 0.01 },
    ],
  },
  {
    title: 'Нападения',
    note: 'Монстры берутся из настроек мобов морской зоны; здесь — общие множители.',
    fields: [
      {
        key: 'raid_chance_mult',
        label: 'Множитель шанса нападения, ×',
        hint: 'Умножает шанс появления мобов зоны (0 — нападений нет)',
        step: 0.01,
      },
      {
        key: 'raid_hold_max_minutes',
        label: 'Стоянка на время боя, мин',
        hint: 'Сколько корабль ждёт, пока на палубе идёт бой (0 — не ждёт)',
        step: 1,
      },
      {
        key: 'raid_repelled_delay_minutes',
        label: 'Задержка после «отбились», мин',
        hint: 'Если сражаться было некому — корабль теряет это время',
        step: 1,
      },
    ],
  },
];

const FIELDS: FieldDef[] = GROUPS.flatMap((g) => g.fields);

interface SeaSettingsCardProps {
  canUpdate: boolean;
}

/** Admin: global sea settings (A7) + FEAT-214 storms, seasons and monster raids. */
const SeaSettingsCard = ({ canUpdate }: SeaSettingsCardProps) => {
  const [values, setValues] = useState<Record<SettingKey, string> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = (s: SeaSettings) =>
    setValues(Object.fromEntries(FIELDS.map(({ key }) => [key, String(s[key])])) as Record<SettingKey, string>);

  useEffect(() => {
    fetchSeaSettings()
      .then(apply)
      .catch((e) => setLoadError(seaAdminError(e, 'Не удалось загрузить настройки моря')));
  }, []);

  const submit = async () => {
    if (!values) return;
    for (const { key, step } of FIELDS) {
      const raw = values[key].trim();
      const value = Number(raw);
      const [min, max] = SEA_LIMITS[key];
      if (raw === '' || Number.isNaN(value) || value < min || value > max || (step === 1 && !Number.isInteger(value))) {
        setError(`Неверное значение: ${seaRangeText(key)}`);
        return;
      }
    }
    if (Number(values.storm_max_minutes) < Number(values.storm_min_minutes)) {
      setError('Максимальная длительность шторма меньше минимальной');
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const saved = await saveSeaSettings(
        Object.fromEntries(FIELDS.map(({ key }) => [key, Number(values[key])])) as unknown as SeaSettings,
      );
      apply(saved);
      toast.success('Настройки моря сохранены');
    } catch (e) {
      const message = seaAdminError(e, 'Не удалось сохранить настройки моря');
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  if (loadError) return <p className="text-site-red text-sm">{loadError}</p>;
  if (!values) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 sm:p-5 flex flex-col gap-4">
      <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Настройки моря</h2>
      {GROUPS.map((group) => (
        <fieldset key={group.title} className="flex flex-col gap-3 min-w-0">
          <legend className="text-white/70 text-sm uppercase tracking-[0.06em] mb-1">{group.title}</legend>
          {group.note && <p className="text-white/40 text-xs -mt-1">{group.note}</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {group.fields.map(({ key, label, hint, step }) => (
              <label key={key} className="flex flex-col gap-1.5 min-w-0">
                <span className={LABEL}>{label}</span>
                <input
                  type="number"
                  inputMode="decimal"
                  min={SEA_LIMITS[key][0]}
                  max={SEA_LIMITS[key][1]}
                  step={step}
                  value={values[key]}
                  disabled={!canUpdate}
                  onChange={(e) => setValues((prev) => (prev ? { ...prev, [key]: e.target.value } : prev))}
                  className={FIELD}
                />
                <span className="text-white/40 text-xs">
                  {hint} ({SEA_LIMITS[key][0]}–{SEA_LIMITS[key][1].toLocaleString('ru-RU')})
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      {error && <p className="text-site-red text-sm">{error}</p>}
      {canUpdate && (
        <div className="flex sm:justify-end">
          <button type="button" onClick={() => void submit()} disabled={saving} className="btn-blue w-full sm:w-auto">
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
        </div>
      )}
    </section>
  );
};

export default SeaSettingsCard;
