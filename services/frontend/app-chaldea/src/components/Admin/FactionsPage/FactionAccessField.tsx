// FEAT-207 — «Только для фракции» of one location / dungeon (used in the location and dungeon editors).
// Loads the rule, lets an editor pick the faction + an optional minimal rank, saves / removes it at once
// (separately from the parent form). Shown only with `factions:read`, editable with `factions:edit`.
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Lock } from 'lucide-react';
import {
  adminDeleteAccessRule,
  adminGetAccessRule,
  adminGetFaction,
  adminPutAccessRule,
  type FactionAccessKind,
  type FactionAccessRule,
  type FactionRankAdmin,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import { FIELD, LABEL, OPTION, useFactionOptions } from './adminShared';

interface FactionAccessFieldProps {
  kind: FactionAccessKind;
  targetId: number;
}

const FactionAccessField = ({ kind, targetId }: FactionAccessFieldProps) => {
  const permissions = useAppSelector(selectPermissions);
  const canRead = hasPermission(permissions, 'factions:read');
  const canEdit = hasPermission(permissions, 'factions:edit');
  if (!canRead) return null;
  return <FactionAccessFieldInner kind={kind} targetId={targetId} canEdit={canEdit} />;
};

const FactionAccessFieldInner = ({ kind, targetId, canEdit }: FactionAccessFieldProps & { canEdit: boolean }) => {
  const { factions, error: factionsError } = useFactionOptions();
  const [rule, setRule] = useState<FactionAccessRule | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [factionId, setFactionId] = useState<number | null>(null);
  const [rankId, setRankId] = useState<number | null>(null);
  const [ranks, setRanks] = useState<FactionRankAdmin[]>([]);
  const [ranksError, setRanksError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ro = !canEdit;

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const r = await adminGetAccessRule(kind, targetId);
      setRule(r);
      setFactionId(r?.faction_id ?? null);
      setRankId(r?.min_rank_id ?? null);
    } catch (e) {
      setLoadError(apiErrorMessage(e, 'Не удалось загрузить ограничение по фракции'));
    }
  }, [kind, targetId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (factionId == null) {
      setRanks([]);
      return;
    }
    let cancelled = false;
    setRanksError(null);
    adminGetFaction(factionId)
      .then((d) => !cancelled && setRanks([...d.ranks].sort((a, b) => a.sort_order - b.sort_order)))
      .catch((e) => !cancelled && setRanksError(apiErrorMessage(e, 'Не удалось загрузить звания фракции')));
    return () => {
      cancelled = true;
    };
  }, [factionId]);

  const save = async () => {
    if (factionId == null) return void toast.error('Выберите фракцию');
    setBusy(true);
    try {
      await adminPutAccessRule(kind, targetId, { faction_id: factionId, min_rank_id: rankId });
      toast.success(kind === 'location' ? 'Локация закрыта для фракции' : 'Подземелье закрыто для фракции');
      await load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить ограничение'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await adminDeleteAccessRule(kind, targetId);
      toast.success('Ограничение по фракции снято');
      await load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось снять ограничение'));
    } finally {
      setBusy(false);
    }
  };

  const dirty = (rule?.faction_id ?? null) !== factionId || (rule?.min_rank_id ?? null) !== rankId;
  const selected = factions.find((f) => f.id === factionId) ?? null;

  return (
    <div className="flex flex-col gap-3 rounded-card border border-white/10 bg-white/[0.02] p-3 sm:p-4 min-w-0">
      <p className="text-white text-sm font-medium flex items-center gap-2">
        <Lock size={15} className="text-gold shrink-0" />
        Только для фракции
      </p>
      {loadError ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-site-red text-sm">{loadError}</p>
          <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      ) : rule === undefined ? (
        <div className="w-5 h-5 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Фракция</span>
              <select
                value={factionId ?? ''}
                disabled={ro || busy}
                onChange={(e) => {
                  setFactionId(e.target.value ? Number(e.target.value) : null);
                  setRankId(null);
                }}
                className={FIELD}
              >
                <option value="" className={OPTION}>
                  — Открыто для всех —
                </option>
                {factions.map((f) => (
                  <option key={f.id} value={f.id} className={OPTION}>
                    {f.name}
                    {f.is_secret ? ' (тайная)' : ''}
                    {f.is_active ? '' : ' (скрыта)'}
                  </option>
                ))}
                {rule && !factions.some((f) => f.id === rule.faction_id) && (
                  <option value={rule.faction_id} className={OPTION}>
                    {rule.faction_name ?? `#${rule.faction_id}`}
                  </option>
                )}
              </select>
              {factionsError && <span className="text-site-red text-xs">{factionsError}</span>}
            </label>
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>От звания</span>
              <select
                value={rankId ?? ''}
                disabled={ro || busy || factionId == null}
                onChange={(e) => setRankId(e.target.value ? Number(e.target.value) : null)}
                className={FIELD}
              >
                <option value="" className={OPTION}>
                  — Любой участник —
                </option>
                {ranks.map((r, i) => (
                  <option key={r.id} value={r.id} className={OPTION}>
                    {i + 1}. {r.name}
                  </option>
                ))}
                {rankId != null && !ranks.some((r) => r.id === rankId) && (
                  <option value={rankId} className={OPTION}>
                    {rule?.min_rank_name ?? `#${rankId}`}
                  </option>
                )}
              </select>
              {ranksError && <span className="text-site-red text-xs">{ranksError}</span>}
            </label>
          </div>
          <p className="text-white/40 text-xs">
            Остальные не войдут: перемещение{kind === 'dungeon' ? ' / вход отряда' : ''} отклоняется, на карте видна отметка
            «Закрыто». Тайная фракция: не-участники видят просто «Закрыто». Скрытая фракция — территория открыта для всех.
            {kind === 'location' && ' Тех, кто уже стоит здесь без права, выдворит в соседнюю локацию.'}
            {selected && !selected.is_active && ' Сейчас фракция скрыта — ограничение не действует.'}
          </p>
          {canEdit && (
            <div className="flex flex-col sm:flex-row gap-2">
              <button
                type="button"
                onClick={() => void save()}
                disabled={busy || factionId == null || !dirty}
                className="btn-blue !w-full sm:!w-auto !text-sm !px-6 disabled:opacity-50"
              >
                {busy ? 'Сохранение...' : 'Сохранить ограничение'}
              </button>
              {rule && (
                <button
                  type="button"
                  onClick={() => void remove()}
                  disabled={busy}
                  className="btn-line !w-full sm:!w-auto !text-sm !px-6 disabled:opacity-50"
                >
                  Открыть для всех
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default FactionAccessField;
