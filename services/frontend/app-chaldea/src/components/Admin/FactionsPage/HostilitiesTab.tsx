import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  adminCreateHostility,
  adminDeleteHostility,
  adminListHostilities,
  adminUpdateHostility,
  type FactionHostility,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { FIELD, LABEL, OPTION, useFactionOptions } from './adminShared';

/** Hostile pairs: quest points in one take a share from the other; irreconcilable = cannot be in both. */
const HostilitiesTab = ({ canEdit }: { canEdit: boolean }) => {
  const [list, setList] = useState<FactionHostility[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { factions, error: factionsError } = useFactionOptions();
  const [a, setA] = useState<number | ''>('');
  const [b, setB] = useState<number | ''>('');
  const [irreconcilable, setIrreconcilable] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setList(await adminListHostilities());
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить враждебные пары'));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    if (a === '' || b === '') {
      toast.error('Выберите обе фракции');
      return;
    }
    if (a === b) {
      toast.error('Фракция не может враждовать сама с собой');
      return;
    }
    setBusy(true);
    try {
      await adminCreateHostility({ faction_a_id: a, faction_b_id: b, irreconcilable });
      toast.success('Пара добавлена');
      setA('');
      setB('');
      setIrreconcilable(false);
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось добавить пару'));
    } finally {
      setBusy(false);
    }
  };

  const toggleIrreconcilable = async (h: FactionHostility) => {
    setBusy(true);
    try {
      await adminUpdateHostility(h.id, {
        faction_a_id: h.faction_a_id,
        faction_b_id: h.faction_b_id,
        irreconcilable: !h.irreconcilable,
      });
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось изменить пару'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (h: FactionHostility) => {
    if (!window.confirm(`Убрать враждебность «${h.faction_a_name}» — «${h.faction_b_name}»?`)) return;
    setBusy(true);
    try {
      await adminDeleteHostility(h.id);
      toast.success('Пара удалена');
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось удалить пару'));
    } finally {
      setBusy(false);
    }
  };

  const select = (value: number | '', onChange: (v: number | '') => void, label: string) => (
    <label className="flex flex-col gap-1 min-w-0 flex-1">
      <span className={LABEL}>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')} className={FIELD}>
        <option value="" className={OPTION}>— выберите —</option>
        {factions.map((f) => (
          <option key={f.id} value={f.id} className={OPTION}>
            {f.name}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="flex flex-col gap-4">
      <p className="text-white/50 text-sm max-w-3xl">
        Очки, полученные за задание одной фракции, отнимают процент (настройка «Штраф враждебной фракции») у каждой
        враждебной ей фракции, где персонаж состоит. «Непримиримая» пара — состоять в обеих нельзя: вступление во вторую
        запрещено, а тем, кто уже в обеих, проверка вынесет предупреждение.
      </p>

      {canEdit && (
        <div className="gray-bg p-4 flex flex-col sm:flex-row sm:items-end gap-3">
          {select(a, setA, 'Фракция')}
          {select(b, setB, 'Враждует с')}
          <label className="flex items-center gap-2 cursor-pointer select-none shrink-0 sm:pb-2">
            <input type="checkbox" checked={irreconcilable} onChange={(e) => setIrreconcilable(e.target.checked)} className="w-4 h-4 accent-gold" />
            <span className="text-white/80 text-sm">Непримиримая</span>
          </label>
          <button type="button" onClick={() => void create()} disabled={busy} className="btn-blue !w-full sm:!w-auto !text-sm !px-5 !py-2 disabled:opacity-50 shrink-0">
            Добавить
          </button>
        </div>
      )}
      {factionsError && <p className="text-site-red text-sm">{factionsError}</p>}

      {error && <p className="text-site-red text-sm">{error}</p>}
      {!list && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {list?.length === 0 && <p className="text-white/50 text-sm">Враждебных пар нет.</p>}
      <div className="flex flex-col gap-2">
        {list?.map((h) => (
          <div key={h.id} className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 bg-white/[0.03] border border-white/[0.06] rounded-card p-3">
            <span className="text-white text-sm flex-1 min-w-0 break-words">
              {h.faction_a_name ?? `#${h.faction_a_id}`} <span className="text-white/40">⚔</span> {h.faction_b_name ?? `#${h.faction_b_id}`}
              {h.irreconcilable && <span className="text-site-red text-xs ml-2">непримиримая</span>}
            </span>
            {canEdit && (
              <div className="flex gap-4 shrink-0">
                <button type="button" disabled={busy} onClick={() => void toggleIrreconcilable(h)} className="text-sm text-white hover:text-site-blue transition-colors disabled:opacity-50">
                  {h.irreconcilable ? 'Сделать обычной' : 'Сделать непримиримой'}
                </button>
                <button type="button" disabled={busy} onClick={() => void remove(h)} className="text-sm text-site-red hover:text-white transition-colors disabled:opacity-50">
                  Удалить
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default HostilitiesTab;
