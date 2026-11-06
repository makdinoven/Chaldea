import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  FACTION_ECON_SETTINGS_FIELDS,
  FACTION_SETTINGS_FIELDS,
  FACTION_TERRITORY_SETTINGS_FIELDS,
  adminGetFactionSettings,
  adminPutFactionSettings,
  type FactionNumericSettingKey,
  type FactionSettingField,
  type FactionSettings,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { FIELD, INT_RE, LABEL, toInt } from './adminShared';

type Form = Record<FactionNumericSettingKey, string> & { econ_enabled: boolean };

const ALL_FIELDS: FactionSettingField[] = [
  ...FACTION_SETTINGS_FIELDS,
  ...FACTION_ECON_SETTINGS_FIELDS,
  ...FACTION_TERRITORY_SETTINGS_FIELDS,
];

const toForm = (s: FactionSettings): Form => ({
  ...(Object.fromEntries(ALL_FIELDS.map((f) => [f.key, String(s[f.key] ?? '')])) as Record<FactionNumericSettingKey, string>),
  econ_enabled: Boolean(s.econ_enabled),
});

/** Terms of the faction rules (days / percents / hours) and the faction economy (FEAT-206). Editing needs `factions:settings`. */
const FactionSettingsTab = ({ canEdit }: { canEdit: boolean }) => {
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setError(null);
    adminGetFactionSettings()
      .then((s) => setForm(toForm(s)))
      .catch((e) => setError(apiErrorMessage(e, 'Не удалось загрузить настройки фракций')));
  };

  useEffect(load, []);

  const save = async () => {
    if (!form) return;
    const body = { econ_enabled: form.econ_enabled } as FactionSettings;
    for (const f of ALL_FIELDS) {
      const v = toInt(form[f.key]);
      if (v == null || v < f.min || v > f.max) {
        toast.error(`${f.label}: от ${f.min} до ${f.max}`);
        return;
      }
      body[f.key] = v;
    }
    setSaving(true);
    try {
      setForm(toForm(await adminPutFactionSettings(body)));
      toast.success('Настройки фракций сохранены');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить настройки'));
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-site-red text-sm">{error}</p>
        <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={load}>
          Повторить
        </button>
      </div>
    );
  }
  if (!form) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const field = (f: FactionSettingField) => (
    <label key={f.key} className="flex flex-col gap-1">
      <span className={LABEL}>{f.label}</span>
      <input
        inputMode="numeric"
        value={form[f.key]}
        disabled={!canEdit}
        onChange={(e) => INT_RE.test(e.target.value) && setForm((prev) => (prev ? { ...prev, [f.key]: e.target.value } : prev))}
        className={FIELD}
      />
      <span className="text-white/40 text-xs">
        от {f.min} до {f.max}
      </span>
    </label>
  );

  return (
    <div className="gray-bg p-4 sm:p-6 flex flex-col gap-5 max-w-3xl">
      <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Правила членства</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{FACTION_SETTINGS_FIELDS.map(field)}</div>

      <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Экономика фракций</h3>
      <label className="flex items-start gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={form.econ_enabled}
          disabled={!canEdit}
          onChange={(e) => setForm((prev) => (prev ? { ...prev, econ_enabled: e.target.checked } : prev))}
          className="w-4 h-4 mt-0.5 accent-gold shrink-0"
        />
        <span className="flex flex-col">
          <span className="text-white/85 text-sm">Фракции живут в экономическом пересчёте</span>
          <span className="text-white/40 text-xs">
            Выключено — взносы, жалованье, закупки интенданта и рост числа участников стоят у всех фракций. Пожертвования,
            покупки у интенданта и выплаты долгов продолжают работать.
          </span>
        </span>
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{FACTION_ECON_SETTINGS_FIELDS.map(field)}</div>

      <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Враги, запреты и предметы</h3>
      <p className="text-white/40 text-xs">
        Лимит очков за победы — общий для всех фракций (у фракции может быть свой во вкладке «Территория и враги»).
        Продажа пожертвованных предметов идёт в пересчёт из кошелька жителей края штаба.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{FACTION_TERRITORY_SETTINGS_FIELDS.map(field)}</div>

      {canEdit ? (
        <button type="button" onClick={() => void save()} disabled={saving} className="btn-blue !w-full sm:!w-auto !text-base !px-8 !py-2 self-start disabled:opacity-50">
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      ) : (
        <p className="text-white/40 text-xs">Изменять настройки может только администратор (право factions:settings).</p>
      )}
    </div>
  );
};

export default FactionSettingsTab;
