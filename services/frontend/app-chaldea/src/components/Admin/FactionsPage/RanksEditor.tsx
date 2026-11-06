import { useState } from 'react';
import toast from 'react-hot-toast';
import { ArrowDown, ArrowUp, Plus } from 'lucide-react';
import { adminDeleteRank, adminReorderRanks, type FactionRankAdmin } from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import RankFormModal from './RankFormModal';

interface RanksEditorProps {
  factionId: number;
  ranks: FactionRankAdmin[];
  canEdit: boolean;
  canDelete: boolean;
  onChanged: () => void;
}

const rewardsSummary = (r: FactionRankAdmin): string => {
  const parts: string[] = [];
  if (r.reward_xp) parts.push(`${r.reward_xp} опыта`);
  if (r.reward_title_id) parts.push('титул');
  if (r.reward_items?.length) parts.push(`предметов: ${r.reward_items.length}`);
  if (r.reward_house_location_id) parts.push('право на дом');
  if (r.reward_plot_location_id) parts.push('право на участок');
  if (r.reward_marks) parts.push(`${r.reward_marks} марок из казны`);
  if (r.qm_discount_pct) parts.push(`скидка у интенданта ${r.qm_discount_pct} %`);
  return parts.length ? parts.join(', ') : 'без наград';
};

const conditionsSummary = (r: FactionRankAdmin, isEntry: boolean): string => {
  if (isEntry) return 'звание при вступлении';
  const parts: string[] = [];
  if (r.min_points) parts.push(`очки от ${r.min_points}`);
  if (r.min_level) parts.push(`уровень от ${r.min_level}`);
  if (r.required_quest_id) parts.push(`задание #${r.required_quest_id}`);
  return parts.length ? parts.join(', ') : 'без условий';
};

/** The rank ladder: lowest = entry rank (no conditions). Up/down rewrites the whole order. */
const RanksEditor = ({ factionId, ranks, canEdit, canDelete, onChanged }: RanksEditorProps) => {
  const ordered = [...ranks].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  const [editing, setEditing] = useState<FactionRankAdmin | 'new' | null>(null);
  const [busy, setBusy] = useState(false);

  const move = async (index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (target < 0 || target >= ordered.length) return;
    const ids = ordered.map((r) => r.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    setBusy(true);
    try {
      await adminReorderRanks(factionId, ids);
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось изменить порядок званий'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (rank: FactionRankAdmin) => {
    if (!window.confirm(`Удалить звание «${rank.name}»?`)) return;
    setBusy(true);
    try {
      await adminDeleteRank(rank.id);
      toast.success('Звание удалено');
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось удалить звание'));
    } finally {
      setBusy(false);
    }
  };

  const editingIsEntry =
    editing === 'new' ? ordered.length === 0 : editing !== null && ordered[0]?.id === editing.id;

  return (
    <section className="gray-bg p-4 sm:p-6 flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Звания ({ordered.length})</h3>
        {canEdit && (
          <button
            type="button"
            className="btn-line !w-full sm:!w-auto !text-sm !px-4 !py-1.5 sm:ml-auto inline-flex items-center justify-center gap-1.5"
            onClick={() => setEditing('new')}
          >
            <Plus size={14} />
            Добавить звание
          </button>
        )}
      </div>
      <p className="text-white/40 text-xs">
        Первое звание дают при вступлении (его условия не проверяются). Повышение автоматическое, как только выполнены
        все условия следующего звания; награды выдаются один раз навсегда.
      </p>
      {ordered.length === 0 && <p className="text-white/50 text-sm">Званий пока нет — участники будут «без звания».</p>}
      <ol className="flex flex-col gap-2">
        {ordered.map((r, i) => (
          <li key={r.id} className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 bg-white/[0.03] rounded-card p-3">
            <span className="text-gold font-mono tabular-nums text-sm w-6 shrink-0">{i + 1}.</span>
            <div className="flex-1 min-w-0 flex flex-col gap-0.5">
              <span className="text-white text-sm font-medium break-words">{r.name}</span>
              <span className="text-white/50 text-xs break-words">{conditionsSummary(r, i === 0)}</span>
              <span className="text-white/40 text-xs break-words">Награда: {rewardsSummary(r)}</span>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              {canEdit && (
                <>
                  <button
                    type="button"
                    disabled={busy || i === 0}
                    onClick={() => void move(i, -1)}
                    className="text-white/60 hover:text-site-blue disabled:opacity-30"
                    aria-label="Выше"
                  >
                    <ArrowUp size={16} />
                  </button>
                  <button
                    type="button"
                    disabled={busy || i === ordered.length - 1}
                    onClick={() => void move(i, 1)}
                    className="text-white/60 hover:text-site-blue disabled:opacity-30"
                    aria-label="Ниже"
                  >
                    <ArrowDown size={16} />
                  </button>
                </>
              )}
              <button type="button" onClick={() => setEditing(r)} className="text-sm text-white hover:text-site-blue transition-colors">
                {canEdit ? 'Изменить' : 'Открыть'}
              </button>
              {canDelete && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void remove(r)}
                  className="text-sm text-site-red hover:text-white transition-colors disabled:opacity-50"
                >
                  Удалить
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>

      {editing !== null && (
        <RankFormModal
          factionId={factionId}
          rank={editing === 'new' ? null : editing}
          isEntry={editingIsEntry}
          canEdit={canEdit}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
    </section>
  );
};

export default RanksEditor;
