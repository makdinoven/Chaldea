import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchSeaSettings, saveSeaSettings, seaAdminError, seaRangeText, SEA_LIMITS } from '../../../api/seaAdmin';
import type { SeaSettings } from '../../../types/seaAdmin';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';

type SettingKey = keyof SeaSettings;

const FIELDS: { key: SettingKey; label: string; hint: string; step: number }[] = [
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
];

interface SeaSettingsCardProps {
  canUpdate: boolean;
}

/** Admin: global sea settings (A7). */
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
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {FIELDS.map(({ key, label, hint, step }) => (
          <label key={key} className="flex flex-col gap-1.5">
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
