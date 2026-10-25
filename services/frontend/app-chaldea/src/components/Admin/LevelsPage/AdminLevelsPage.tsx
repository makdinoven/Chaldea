import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../../../api/errors';

/*
  How much experience each level takes. The table holds the TOTAL experience a
  character needs to reach a level (from level 2); the step from the level
  before is shown next to it. A formula can fill the table, then any cell is
  edited by hand; nothing is stored until «Сохранить».
*/

interface Threshold {
  level_number: number;
  required_experience: number;
}

const URL = '/characters/admin/levels/thresholds';
const MAX_LEVEL = 500;

/** Steps that grow by `growth` % a level: level 2 takes `first`, level 3 `first × (1 + growth)`, … */
const byFormula = (upTo: number, first: number, growthPct: number): Threshold[] => {
  const rows: Threshold[] = [];
  let total = 0;
  for (let level = 2; level <= upTo; level += 1) {
    total += Math.max(1, Math.round(first * (1 + growthPct / 100) ** (level - 2)));
    rows.push({ level_number: level, required_experience: total });
  }
  return rows;
};

const problemOf = (rows: Threshold[]): string | null => {
  for (let i = 0; i < rows.length; i += 1) {
    const xp = rows[i].required_experience;
    if (!Number.isFinite(xp) || xp <= 0) return `Уровень ${rows[i].level_number}: укажите опыт`;
    if (i > 0 && xp <= rows[i - 1].required_experience) {
      return `Уровень ${rows[i].level_number}: опыта должно быть больше, чем для ${rows[i - 1].level_number}-го`;
    }
  }
  return null;
};

const fmt = (n: number) => n.toLocaleString('ru-RU');

const AdminLevelsPage = () => {
  const [rows, setRows] = useState<Threshold[]>([]);
  const [saved, setSaved] = useState<Threshold[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [upTo, setUpTo] = useState('50');
  const [first, setFirst] = useState('100');
  const [growth, setGrowth] = useState('15');

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get<Threshold[]>(URL);
        setRows(data);
        setSaved(data);
      } catch (e) {
        setLoadError(apiErrorMessage(e, 'Не удалось загрузить таблицу уровней'));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const dirty = useMemo(() => JSON.stringify(rows) !== JSON.stringify(saved), [rows, saved]);
  const problem = problemOf(rows);

  const setXp = (idx: number, value: string) =>
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, required_experience: Math.round(Number(value) || 0) } : r)));

  const addLevel = () =>
    setRows((prev) => {
      if (prev.length >= MAX_LEVEL - 1) return prev;
      const last = prev[prev.length - 1];
      const before = prev[prev.length - 2];
      const step = last ? last.required_experience - (before?.required_experience ?? 0) : 100;
      return [...prev, {
        level_number: (last?.level_number ?? 1) + 1,
        required_experience: (last?.required_experience ?? 0) + Math.max(1, step),
      }];
    });

  const applyFormula = () => {
    const n = Math.round(Number(upTo));
    const f = Number(first);
    const g = Number(growth);
    if (!Number.isFinite(n) || n < 2 || n > MAX_LEVEL) {
      toast.error(`Последний уровень — от 2 до ${MAX_LEVEL}`);
      return;
    }
    if (!Number.isFinite(f) || f < 1) {
      toast.error('Опыт на 2-й уровень — от 1');
      return;
    }
    if (!Number.isFinite(g) || g < 0 || g > 100) {
      toast.error('Рост — от 0 до 100%');
      return;
    }
    setRows(byFormula(n, f, g));
    toast('Таблица заполнена по формуле — проверьте и сохраните');
  };

  const save = async () => {
    if (problem) {
      toast.error(problem);
      return;
    }
    setSaving(true);
    try {
      const { data } = await axios.put<Threshold[]>(URL, { thresholds: rows });
      setRows(data);
      setSaved(data);
      toast.success('Таблица уровней сохранена');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить таблицу уровней'));
    } finally {
      setSaving(false);
    }
  };

  const numberField = (label: string, value: string, set: (v: string) => void, suffix?: string) => (
    <label className="flex flex-col gap-1 min-w-0">
      <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">{label}</span>
      <span className="flex items-center gap-1">
        <input type="number" inputMode="numeric" value={value} onChange={(e) => set(e.target.value)}
          className="input-underline w-full" />
        {suffix && <span className="text-white/40 text-sm">{suffix}</span>}
      </span>
    </label>
  );

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-6 px-1">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Уровни и опыт</h1>

      <p className="text-white/60 text-sm max-w-3xl">
        Для каждого уровня указан опыт <span className="text-white">всего</span>: чтобы получить уровень, персонаж должен
        набрать столько опыта с самого начала. Выше последнего уровня таблицы персонажи сами не растут. Уже набранные
        уровни при изменении таблицы не отнимаются. За каждый новый уровень — 10 очков характеристик.
      </p>

      {loading && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {loadError && <p className="text-site-red text-sm">{loadError}</p>}

      {!loading && !loadError && (
        <>
          <section className="gray-bg p-4 sm:p-5 flex flex-col gap-4">
            <h2 className="text-white text-sm font-medium uppercase tracking-[0.06em]">Заполнить по формуле</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {numberField('До уровня', upTo, setUpTo)}
              {numberField('Опыт на 2-й уровень', first, setFirst)}
              {numberField('Рост шага за уровень', growth, setGrowth, '%')}
            </div>
            <p className="text-white/40 text-xs">
              Шаг до следующего уровня растёт на заданный процент: при 100 и 15% — 100, 115, 132… опыта на уровень.
              Таблица заменится целиком, сохраняется кнопкой ниже.
            </p>
            <button type="button" onClick={applyFormula} className="btn-line !w-full sm:!w-auto !px-5 self-start">
              Заполнить таблицу
            </button>
          </section>

          <section className="gray-bg p-4 sm:p-5 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h2 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
                Уровни <span className="text-white/40">({rows.length + 1} с первым)</span>
              </h2>
              {dirty && <span className="text-xs text-yellow-400/80">Есть несохранённые изменения</span>}
            </div>

            <div className="overflow-x-auto max-h-[60vh] overflow-y-auto gold-scrollbar">
              <table className="w-full text-sm min-w-[320px]">
                <thead className="sticky top-0 bg-site-bg/95">
                  <tr className="text-left text-xs uppercase tracking-[0.06em] text-white/50">
                    <th className="px-3 py-2">Уровень</th>
                    <th className="px-3 py-2">Опыт всего</th>
                    <th className="px-3 py-2">Шаг</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-white/5 text-white/40">
                    <td className="px-3 py-2">1</td>
                    <td className="px-3 py-2">0</td>
                    <td className="px-3 py-2">—</td>
                    <td />
                  </tr>
                  {rows.map((r, i) => {
                    const step = r.required_experience - (rows[i - 1]?.required_experience ?? 0);
                    return (
                      <tr key={r.level_number} className="border-t border-white/5">
                        <td className="px-3 py-1.5 text-white">{r.level_number}</td>
                        <td className="px-3 py-1.5">
                          <input type="number" inputMode="numeric" min={1} value={r.required_experience || ''}
                            onChange={(e) => setXp(i, e.target.value)} className="input-underline !text-sm w-28 sm:w-36" />
                        </td>
                        <td className={`px-3 py-1.5 ${step > 0 ? 'text-white/60' : 'text-site-red'}`}>{fmt(step)}</td>
                        <td className="px-3 py-1.5 text-right">
                          {i === rows.length - 1 && (
                            <button type="button" onClick={() => setRows((prev) => prev.slice(0, -1))}
                              className="text-xs text-site-red hover:text-white transition-colors">
                              Убрать
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {problem && <p className="text-site-red text-sm">{problem}</p>}
            <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-between">
              <button type="button" onClick={addLevel} className="btn-line !w-full sm:!w-auto !px-5">
                Добавить уровень
              </button>
              <div className="flex flex-col-reverse sm:flex-row gap-2">
                {dirty && (
                  <button type="button" onClick={() => setRows(saved)} className="btn-line !w-full sm:!w-auto !px-5">
                    Отменить изменения
                  </button>
                )}
                <button type="button" onClick={() => void save()} disabled={!dirty || saving || !!problem}
                  className="btn-blue !w-full sm:!w-auto !px-6 disabled:opacity-40 disabled:cursor-not-allowed">
                  {saving ? 'Сохранение...' : 'Сохранить'}
                </button>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
};

export default AdminLevelsPage;
