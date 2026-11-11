import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchCaravanGuards, putCaravanGuards } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import type { CaravanGuardTemplate } from '../../../types/economy';
import { SearchBox, type Option } from '../DungeonsPage/editor/pickers';

/*
  FEAT-211 — «Охрана караванов» (A8/A9): the pool of mob templates guards are
  spawned from. For a raid the template whose level is closest to the
  location's recommended level is taken. An empty pool = raids impossible.
*/

/** Backend cap of the pool (A9). */
const POOL_MAX = 20;

const sameIds = (a: CaravanGuardTemplate[], b: CaravanGuardTemplate[]) =>
  a.length === b.length && a.every((t, i) => t.mob_template_id === b[i].mob_template_id);

const levelOf = (o: Option): number | null => {
  const m = /ур\.\s*(\d+)/.exec(o.sub ?? '');
  return m ? Number(m[1]) : null;
};

const CaravanGuardsCard = ({ canEdit }: { canEdit: boolean }) => {
  const [saved, setSaved] = useState<CaravanGuardTemplate[] | null>(null);
  const [draft, setDraft] = useState<CaravanGuardTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = (list: CaravanGuardTemplate[]) => {
    setSaved(list);
    setDraft(list);
  };

  const load = useCallback(() => {
    fetchCaravanGuards()
      .then((d) => {
        apply(d.templates);
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить охрану караванов');
        setError(msg);
        toast.error(msg);
      });
  }, []);

  useEffect(load, [load]);

  const dirty = saved !== null && !sameIds(saved, draft);

  const add = (o: Option) => {
    setSaveError(null);
    setDraft((list) => {
      if (list.some((t) => t.mob_template_id === o.id)) return list;
      if (list.length >= POOL_MAX) {
        toast.error(`В пуле не больше ${POOL_MAX} шаблонов`);
        return list;
      }
      return [...list, { mob_template_id: o.id, name: o.label, level: levelOf(o) }];
    });
  };

  const remove = (id: number) => {
    setSaveError(null);
    setDraft((list) => list.filter((t) => t.mob_template_id !== id));
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await putCaravanGuards(draft.map((t) => t.mob_template_id));
      apply(res.templates);
      toast.success('Охрана караванов сохранена');
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось сохранить охрану караванов');
      setSaveError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const sorted = [...draft].sort((a, b) => (a.level ?? 0) - (b.level ?? 0));

  return (
    <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
      <div className="flex flex-col gap-1">
        <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Охрана караванов</h2>
        <p className="text-white/50 text-sm">
          Шаблоны мобов, из которых собирается охрана. При налёте берётся шаблон с уровнем, ближайшим к рекомендуемому
          уровню локации; число стражей и их сила зависят от стоимости груза. Награды за стражей — как за обычных мобов.
        </p>
      </div>

      {error && saved === null ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !text-sm" onClick={load}>
            Повторить
          </button>
        </div>
      ) : saved === null ? (
        <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      ) : (
        <>
          {draft.length === 0 ? (
            <p className="text-gold/90 text-xs sm:text-sm rounded-card border border-gold/30 bg-gold/[0.06] px-3 py-2">
              Пул пуст — напасть на караван нельзя.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {sorted.map((t) => (
                <li
                  key={t.mob_template_id}
                  className="flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.03] pl-3 pr-1.5 py-1 min-w-0"
                >
                  <span className="text-sm text-white break-words">
                    {t.name ?? `Шаблон #${t.mob_template_id}`}
                    <span className="text-white/40 text-xs">
                      {' '}
                      · #{t.mob_template_id}
                      {t.level !== null && t.level !== undefined ? ` · ур. ${t.level}` : ''}
                    </span>
                  </span>
                  {canEdit && (
                    <button
                      type="button"
                      aria-label="Убрать из пула"
                      disabled={saving}
                      onClick={() => remove(t.mob_template_id)}
                      className="w-6 h-6 rounded-full text-white/50 hover:text-site-red hover:bg-white/5 disabled:opacity-40 transition-colors duration-200"
                    >
                      ×
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {canEdit && (
            <div className="flex flex-col gap-3">
              {draft.length < POOL_MAX && (
                <div className="w-full sm:max-w-[420px]">
                  <SearchBox kind="mob" onPick={add} />
                </div>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className="btn-blue !px-6"
                  disabled={!dirty || saving}
                  onClick={() => void save()}
                >
                  {saving ? 'Сохранение...' : 'Сохранить'}
                </button>
                {dirty && !saving && (
                  <button
                    type="button"
                    className="text-sm text-white/50 hover:text-white transition-colors duration-200"
                    onClick={() => {
                      setDraft(saved);
                      setSaveError(null);
                    }}
                  >
                    Отменить изменения
                  </button>
                )}
                <span className="text-white/40 text-xs">
                  {draft.length} из {POOL_MAX}
                </span>
              </div>
              {saveError && <p className="text-site-red text-xs sm:text-sm">{saveError}</p>}
            </div>
          )}
        </>
      )}
      {!canEdit && <p className="field-hint">Менять охрану может администратор с правом «economy:settings».</p>}
    </section>
  );
};

export default CaravanGuardsCard;
