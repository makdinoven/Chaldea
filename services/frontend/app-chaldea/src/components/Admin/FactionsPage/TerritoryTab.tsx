// FEAT-207 — closed territory of a faction: locations and dungeons only its members (from a rank) may enter.
// One faction per target: closing a target that belongs to another faction moves it to this one.
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Lock, X } from 'lucide-react';
import {
  FACTION_ACCESS_KIND_LABEL,
  adminDeleteAccessRule,
  adminFactionTerritory,
  adminPutAccessRule,
  type FactionAccessKind,
  type FactionRankAdmin,
  type FactionTerritoryRow,
} from '../../../api/factions';
import { fetchDungeons, type Dungeon } from '../../../api/dungeons';
import { apiErrorMessage } from '../../../api/errors';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import { EntityPicker } from '../DungeonsPage/editor/pickers';
import { FIELD, LABEL, OPTION } from './adminShared';

interface TerritoryTabProps {
  factionId: number;
  factionName: string;
  isSecret: boolean;
  isActive: boolean;
  ranks: FactionRankAdmin[];
  canEdit: boolean;
}

const SECTION = 'gray-bg p-4 sm:p-6 flex flex-col gap-4 min-w-0';
const H3 = 'gold-text text-lg font-medium uppercase tracking-[0.06em]';

const TerritoryTab = ({ factionId, factionName, isSecret, isActive, ranks, canEdit }: TerritoryTabProps) => {
  const [rows, setRows] = useState<FactionTerritoryRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<FactionAccessKind>('location');
  const [targetId, setTargetId] = useState<number | null>(null);
  const [rankId, setRankId] = useState<number | null>(null);
  const [dungeons, setDungeons] = useState<Dungeon[] | null>(null);
  const [dungeonsError, setDungeonsError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<FactionTerritoryRow | null>(null);
  const sortedRanks = [...ranks].sort((a, b) => a.sort_order - b.sort_order);

  const load = useCallback(async () => {
    setError(null);
    try {
      setRows(await adminFactionTerritory(factionId));
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить территорию фракции'));
    }
  }, [factionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadDungeons = useCallback(() => {
    setDungeonsError(null);
    fetchDungeons()
      .then((list) => setDungeons([...list].sort((a, b) => a.name.localeCompare(b.name, 'ru'))))
      .catch((e) => setDungeonsError(apiErrorMessage(e, 'Не удалось загрузить список подземелий')));
  }, []);

  useEffect(() => {
    if (kind === 'dungeon' && dungeons === null && canEdit) loadDungeons();
  }, [kind, dungeons, canEdit, loadDungeons]);

  const add = async () => {
    if (targetId == null) return void toast.error(kind === 'location' ? 'Выберите локацию' : 'Выберите подземелье');
    setBusy(true);
    try {
      await adminPutAccessRule(kind, targetId, { faction_id: factionId, min_rank_id: rankId });
      toast.success(`${kind === 'location' ? 'Локация закрыта' : 'Подземелье закрыто'} для «${factionName}»`);
      setTargetId(null);
      setRankId(null);
      await load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось закрыть территорию'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: FactionTerritoryRow) => {
    setRemoving(null);
    setBusy(true);
    try {
      await adminDeleteAccessRule(row.kind, row.target_id);
      toast.success('Ограничение снято — территория открыта для всех');
      await load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось снять ограничение'));
    } finally {
      setBusy(false);
    }
  };

  const targetLink = (row: FactionTerritoryRow) =>
    row.kind === 'location' ? `/location/${row.target_id}` : `/admin/dungeons/${row.target_id}/edit`;

  return (
    <section className={SECTION}>
      <h3 className={H3}>Территория</h3>
      <p className="text-white/40 text-xs">
        Закрытые локации и подземелья: войти могут только участники фракции (от выбранного звания). В подземелье отряд
        входит, только если проходит каждый.
        {isSecret ? ' Фракция тайная — не-участники видят просто «Закрыто», без её имени.' : ''}
        {!isActive ? ' Сейчас фракция скрыта — её территория открыта для всех.' : ''} Уже идущий забег не прерывается.
      </p>

      {error && !rows ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      ) : !rows ? (
        <div className="w-6 h-6 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
      ) : rows.length === 0 ? (
        <p className="text-white/50 text-sm">Закрытой территории нет.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((r) => (
            <div key={`${r.kind}-${r.target_id}`} className="flex items-center gap-2 bg-white/[0.03] rounded-card p-2.5 min-w-0">
              <Lock size={14} className="text-gold shrink-0" />
              <div className="flex-1 min-w-0 flex flex-col">
                <span className="text-white/85 text-sm break-words">
                  <span className="text-white/45 text-xs">{FACTION_ACCESS_KIND_LABEL[r.kind]}: </span>
                  <Link to={targetLink(r)} className="site-link">
                    {r.target_name ?? `#${r.target_id}`}
                  </Link>
                </span>
                <span className="text-white/45 text-xs">{r.min_rank ? `от звания «${r.min_rank.name}»` : 'любой участник'}</span>
              </div>
              {canEdit && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setRemoving(r)}
                  className="text-site-red hover:text-white transition-colors p-1 shrink-0 disabled:opacity-50"
                  aria-label="Открыть для всех"
                  title="Открыть для всех"
                >
                  <X size={16} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {canEdit && (
        <div className="flex flex-col gap-3 border-t border-white/10 pt-4">
          <span className={LABEL}>Закрыть ещё</span>
          <div className="grid grid-cols-1 sm:grid-cols-[160px_1fr_200px] gap-3 sm:items-end">
            <label className="flex flex-col gap-1 min-w-0">
              <span className="text-white/50 text-xs">Что</span>
              <select
                value={kind}
                disabled={busy}
                onChange={(e) => {
                  setKind(e.target.value as FactionAccessKind);
                  setTargetId(null);
                }}
                className={FIELD}
              >
                <option value="location" className={OPTION}>
                  Локация
                </option>
                <option value="dungeon" className={OPTION}>
                  Подземелье
                </option>
              </select>
            </label>
            <div className="flex flex-col gap-1 min-w-0">
              <span className="text-white/50 text-xs">{kind === 'location' ? 'Локация' : 'Подземелье'}</span>
              {kind === 'location' ? (
                <EntityPicker kind="location" value={targetId} onChange={setTargetId} />
              ) : (
                <>
                  <select
                    value={targetId ?? ''}
                    disabled={busy || dungeons === null}
                    onChange={(e) => setTargetId(e.target.value ? Number(e.target.value) : null)}
                    className={FIELD}
                  >
                    <option value="" className={OPTION}>
                      {dungeons === null && !dungeonsError ? 'Загрузка...' : '— Подземелье —'}
                    </option>
                    {(dungeons ?? []).map((d) => (
                      <option key={d.id} value={d.id} className={OPTION}>
                        {d.name} (#{d.id})
                      </option>
                    ))}
                  </select>
                  {dungeonsError && (
                    <span className="text-site-red text-xs flex flex-wrap gap-2">
                      {dungeonsError}
                      <button type="button" className="site-link" onClick={loadDungeons}>
                        Повторить
                      </button>
                    </span>
                  )}
                </>
              )}
            </div>
            <label className="flex flex-col gap-1 min-w-0">
              <span className="text-white/50 text-xs">От звания</span>
              <select
                value={rankId ?? ''}
                disabled={busy}
                onChange={(e) => setRankId(e.target.value ? Number(e.target.value) : null)}
                className={FIELD}
              >
                <option value="" className={OPTION}>
                  — Любой участник —
                </option>
                {sortedRanks.map((r, i) => (
                  <option key={r.id} value={r.id} className={OPTION}>
                    {i + 1}. {r.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="text-white/40 text-xs">
            Если цель уже закрыта для другой фракции — она перейдёт к этой. Игроков без права, стоящих в закрытой локации,
            выдворит в соседнюю.
          </p>
          <button
            type="button"
            onClick={() => void add()}
            disabled={busy || targetId == null}
            className="btn-blue !w-full sm:!w-auto !text-sm !px-6 self-start disabled:opacity-50"
          >
            {busy ? 'Сохранение...' : 'Закрыть для фракции'}
          </button>
        </div>
      )}

      {removing && (
        <ConfirmDialog
          title="Открыть территорию"
          message={`Открыть «${removing.target_name ?? `#${removing.target_id}`}» для всех?`}
          confirmLabel="Открыть"
          onConfirm={() => void remove(removing)}
          onCancel={() => setRemoving(null)}
        />
      )}
    </section>
  );
};

export default TerritoryTab;
