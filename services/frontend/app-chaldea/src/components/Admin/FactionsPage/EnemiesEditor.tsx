// FEAT-207 — enemies of a faction: whom its members beat for faction points (mob templates, NPCs, open members
// of hostile factions) + the faction's own daily kill-point cap. PUT replaces the whole list.
// FEAT-212 — caravan deeds as «дело фракции»: «Охрана караванов» / «Налёты на караваны» (singletons, no target;
// points per delivered escort / won raid under the same daily cap).
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { X } from 'lucide-react';
import {
  FACTION_ENEMIES_MAX,
  FACTION_ENEMY_KINDS,
  FACTION_ENEMY_KIND_LABEL,
  FACTION_ENEMY_POINTS_MAX,
  FACTION_KILL_CAP_MAX,
  adminFactionEnemies,
  adminPutFactionEnemies,
  isSingletonEnemyKind,
  type FactionEnemiesData,
  type FactionEnemy,
  type FactionEnemyKind,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { EntityPicker } from '../DungeonsPage/editor/pickers';
import { FIELD, INT_RE, LABEL, OPTION, toInt } from './adminShared';

interface EnemiesEditorProps {
  factionId: number;
  canEdit: boolean;
}

interface Row {
  key: number;
  kind: FactionEnemyKind;
  ref_id: number | null;
  points: string;
}

const SECTION = 'gray-bg p-4 sm:p-6 flex flex-col gap-4 min-w-0';
const H3 = 'gold-text text-lg font-medium uppercase tracking-[0.06em]';

let rowKey = 0;
const rowsOf = (enemies: FactionEnemy[]): Row[] =>
  enemies.map((e) => ({ key: ++rowKey, kind: e.kind, ref_id: isSingletonEnemyKind(e.kind) ? null : e.ref_id, points: String(e.points) }));

/** What a singleton row means (no target picker). */
const SINGLETON_HINT: Partial<Record<FactionEnemyKind, string>> = {
  hostile: 'Открытые участники фракций из пар враждебности (PvP)',
  escort: 'Очки за каждый караван, доставленный под охраной участника',
  raid: 'Очки за каждый удачный налёт участника на караван',
};

const EnemiesEditor = ({ factionId, canEdit }: EnemiesEditorProps) => {
  const [data, setData] = useState<FactionEnemiesData | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [cap, setCap] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const ro = !canEdit;

  const apply = (d: FactionEnemiesData) => {
    setData(d);
    setRows(rowsOf(d.enemies ?? []));
    setCap(d.kill_points_daily_cap == null ? '' : String(d.kill_points_daily_cap));
  };

  const load = useCallback(async () => {
    setError(null);
    try {
      apply(await adminFactionEnemies(factionId));
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить врагов фракции'));
    }
  }, [factionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const update = (key: number, patch: Partial<Row>) => setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const save = async () => {
    const enemies: FactionEnemy[] = [];
    const seen = new Set<string>();
    for (const r of rows) {
      const single = isSingletonEnemyKind(r.kind);
      if (!single && r.ref_id == null) {
        return void toast.error(`${FACTION_ENEMY_KIND_LABEL[r.kind]}: выберите, кого именно`);
      }
      const pts = toInt(r.points);
      if (pts == null || pts < 1 || pts > FACTION_ENEMY_POINTS_MAX) {
        return void toast.error(`Очки за победу: от 1 до ${FACTION_ENEMY_POINTS_MAX}`);
      }
      const id = `${r.kind}:${single ? 0 : r.ref_id}`;
      if (seen.has(id)) {
        return void toast.error(
          single ? `Строка «${FACTION_ENEMY_KIND_LABEL[r.kind]}» может быть только одна` : 'Один и тот же враг указан дважды',
        );
      }
      seen.add(id);
      enemies.push({ kind: r.kind, ref_id: single ? null : r.ref_id, points: pts });
    }
    if (enemies.length > FACTION_ENEMIES_MAX) return void toast.error(`Врагов — не больше ${FACTION_ENEMIES_MAX}`);
    const capValue = cap.trim() === '' ? null : toInt(cap);
    if (cap.trim() !== '' && (capValue == null || capValue < 0 || capValue > FACTION_KILL_CAP_MAX)) {
      return void toast.error(`Лимит очков в день: от 0 до ${FACTION_KILL_CAP_MAX} или пусто`);
    }
    setSaving(true);
    try {
      apply(await adminPutFactionEnemies(factionId, { enemies, kill_points_daily_cap: capValue }));
      toast.success('Враги фракции сохранены');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить врагов фракции'));
    } finally {
      setSaving(false);
    }
  };

  if (error && !data) {
    return (
      <section className={SECTION}>
        <h3 className={H3}>Враги фракции</h3>
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      </section>
    );
  }

  /** Singleton kinds already used by some row (offered to no other row). */
  const usedSingletons = new Set(rows.filter((r) => isSingletonEnemyKind(r.kind)).map((r) => r.kind));

  return (
    <section className={SECTION}>
      <h3 className={H3}>Враги фракции</h3>
      <p className="text-white/40 text-xs">
        Очки получают все участники фракции с победившей стороны (и павшие в бою). За одного и того же игрока — не чаще
        срока из настроек; тайные участники враждебных фракций врагами не считаются; учебные бои не в счёт.
      </p>
      {!data ? (
        <div className="w-6 h-6 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
      ) : (
        <>
          <div className="flex flex-col gap-2">
            <span className={LABEL}>
              Враги ({rows.length}/{FACTION_ENEMIES_MAX})
            </span>
            {rows.length === 0 && <p className="text-white/50 text-sm">Врагов нет — победы очков не дают.</p>}
            {rows.map((r) => {
              const original = data.enemies.find((e) => e.kind === r.kind && (isSingletonEnemyKind(e.kind) || e.ref_id === r.ref_id));
              return (
                <div key={r.key} className="flex flex-col sm:flex-row sm:items-center gap-2 bg-white/[0.03] rounded-card p-2.5 min-w-0">
                  <select
                    value={r.kind}
                    disabled={ro}
                    onChange={(e) => update(r.key, { kind: e.target.value as FactionEnemyKind, ref_id: null })}
                    className={`${FIELD} sm:!w-56 shrink-0`}
                    aria-label="Тип врага"
                  >
                    {FACTION_ENEMY_KINDS.map((k) => (
                      <option key={k} value={k} className={OPTION} disabled={isSingletonEnemyKind(k) && usedSingletons.has(k) && r.kind !== k}>
                        {FACTION_ENEMY_KIND_LABEL[k]}
                      </option>
                    ))}
                  </select>
                  <div className="flex-1 min-w-0">
                    {isSingletonEnemyKind(r.kind) ? (
                      <span className="text-white/50 text-xs">{SINGLETON_HINT[r.kind]}</span>
                    ) : ro ? (
                      <span className="text-white/80 text-sm">{original?.name ?? (r.ref_id ? `#${r.ref_id}` : '—')}</span>
                    ) : (
                      <EntityPicker kind={r.kind === 'mob' ? 'mob' : 'npc'} value={r.ref_id} onChange={(id) => update(r.key, { ref_id: id })} />
                    )}
                  </div>
                  <label className="flex items-center gap-1.5 shrink-0">
                    <span className="text-white/50 text-xs">очков</span>
                    <input
                      inputMode="numeric"
                      value={r.points}
                      disabled={ro}
                      onChange={(e) => INT_RE.test(e.target.value) && update(r.key, { points: e.target.value })}
                      className="input-underline !text-sm w-20"
                    />
                  </label>
                  {!ro && (
                    <button
                      type="button"
                      onClick={() => setRows((prev) => prev.filter((x) => x.key !== r.key))}
                      className="text-site-red hover:text-white transition-colors p-1 self-end sm:self-center"
                      aria-label="Убрать врага"
                    >
                      <X size={16} />
                    </button>
                  )}
                </div>
              );
            })}
            {!ro && rows.length < FACTION_ENEMIES_MAX && (
              <button
                type="button"
                onClick={() => setRows((prev) => [...prev, { key: ++rowKey, kind: 'mob', ref_id: null, points: '1' }])}
                className="text-sm text-site-blue hover:text-white transition-colors self-start"
              >
                + Добавить врага
              </button>
            )}
            <p className="text-white/40 text-xs">НПС — только не-мобы (мобов добавляйте как «Моб» по шаблону).</p>
            <p className="text-white/40 text-xs">
              «Охрана караванов» и «Налёты на караваны» — дела фракции: очки за доставленный под охраной караван и за
              удачный налёт идут в тот же дневной лимит, что и победы.
            </p>
          </div>

          <label className="flex flex-col gap-1 max-w-xs">
            <span className={LABEL}>Лимит очков за победы в день</span>
            <input
              inputMode="numeric"
              value={cap}
              disabled={ro}
              onChange={(e) => INT_RE.test(e.target.value) && setCap(e.target.value)}
              className={FIELD}
              placeholder="по умолчанию (из настроек)"
            />
            <span className="text-white/40 text-xs">на участника, от 0 до {FACTION_KILL_CAP_MAX}; пусто — общий из настроек</span>
          </label>

          {canEdit && (
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="btn-blue !w-full sm:!w-auto !text-sm !px-6 self-start disabled:opacity-50"
            >
              {saving ? 'Сохранение...' : 'Сохранить врагов'}
            </button>
          )}
        </>
      )}
    </section>
  );
};

export default EnemiesEditor;
