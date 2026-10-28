import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { adminGetHouseSettings, adminSetHouseSettings, type HouseSettings } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';

interface HouseTaxAdminProps {
  canUpdate: boolean;
}

/** Admin: house tax rates (FEAT-180 stage 4). */
const HouseTaxAdmin = ({ canUpdate }: HouseTaxAdminProps) => {
  const [settings, setSettings] = useState<HouseSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pct, setPct] = useState('');
  const [perLevel, setPerLevel] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    adminGetHouseSettings()
      .then((s) => {
        setSettings(s);
        setPct(String(s.tax_price_pct));
        setPerLevel(String(s.tax_per_room_level));
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить настройки налога');
        setError(msg);
        toast.error(msg);
      });
  }, []);

  useEffect(load, [load]);

  const save = async () => {
    const pctValue = Number(pct);
    const levelValue = Number(perLevel);
    if (pct.trim() === '' || !Number.isFinite(pctValue) || pctValue < 0 || pctValue > 100) {
      toast.error('Процент от цены участка — число от 0 до 100');
      return;
    }
    if (perLevel.trim() === '' || !Number.isInteger(levelValue) || levelValue < 0) {
      toast.error('Плата за уровень комнаты — целое число от 0');
      return;
    }
    setSaving(true);
    try {
      await adminSetHouseSettings({ tax_price_pct: pctValue, tax_per_room_level: levelValue });
      toast.success('Ставки налога сохранены');
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить ставки'));
    } finally {
      setSaving(false);
    }
  };

  if (error) return <p className="text-site-red text-sm">{error}</p>;
  if (!settings) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 p-4 sm:p-5 flex flex-col gap-4 max-w-2xl">
      <p className="text-white/60 text-sm leading-relaxed">
        Налог платится раз в период — игровой сезон с переходом, {settings.tax_period_days} реальных дней.
        Сумма за период = процент от цены участка + плата за каждый уровень построенных комнат.
        Период покупки бесплатный. Один неуплаченный период — предупреждение, два — дом заморожен,
        ещё один — дом изымает город.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Процент от цены участка</span>
          <input type="number" inputMode="decimal" min={0} max={100} step="0.1" value={pct} disabled={!canUpdate}
            onChange={(e) => setPct(e.target.value)} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Золото за уровень комнаты</span>
          <input type="number" inputMode="numeric" min={0} step={1} value={perLevel} disabled={!canUpdate}
            onChange={(e) => setPerLevel(e.target.value)} className={FIELD} />
        </label>
      </div>
      {canUpdate ? (
        <button type="button" onClick={() => void save()} disabled={saving}
          className="btn-blue !w-full sm:!w-auto !px-6 self-end disabled:opacity-50">
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      ) : (
        <p className="text-white/40 text-xs">Изменять ставки может только тот, у кого есть право locations:update.</p>
      )}
    </section>
  );
};

export default HouseTaxAdmin;
