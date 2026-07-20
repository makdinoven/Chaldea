/**
 * GatheringSection (FEAT-128, task #21).
 *
 * The "Ресурсы" block on the LocationPage. Renders one
 * <GatheringNodeCard> per node returned from /client/details and owns the
 * `startGathering` dispatch (it has the `locationId` that the cards
 * themselves do not).
 *
 * Behaviour:
 *  - hides itself entirely when the location has no nodes
 *  - on success: closes the per-card modal, fires `onGatherSucceeded` so
 *    the parent can refresh the location payload, and lets
 *    `useGatheringLock`'s polling pick up the new active session
 *  - subscribes to `lastFinishedSession` and shows a one-shot toast on
 *    completion ("Добыто: X железной руды (+1 опыт)")
 *  - errors from start / cancel are routed through toast in Russian per
 *    CLAUDE.md
 *
 * Tailwind only, no React.FC, mobile responsive.
 */
import { useEffect } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import {
  startGathering,
  selectGatheringIsStarting,
  selectLastFinishedSession,
  clearLastFinishedSession,
} from '../../../../redux/slices/gatheringSlice';
import type { GatheringNode } from '../../../../types/gathering';
import GatheringNodeCard from './GatheringNodeCard';

interface GatheringSectionProps {
  locationId: number;
  characterId: number | null;
  /** Inventory key for the tool list endpoint. In this codebase the
   *  /inventory/{id}/items endpoint is keyed by character id, so callers
   *  typically pass the same value as `characterId`. */
  inventoryId: number | null;
  isCharacterHere: boolean;
  /** Combined lock — true when the character is in battle OR already
   *  gathering. The section uses this to disable per-card "Добыть" buttons. */
  actionsLocked: boolean;
  nodes: GatheringNode[];
  /** Optional callback invoked after a successful start; the parent should
   *  re-fetch /client/details so the bank counter and active-sessions list
   *  reflect the new state. */
  onGatherSucceeded?: () => void;
}

/** Russian noun for the resource that was just gathered. We don't have the
 *  item name in `lastFinishedSession`, so we use a per-skill fallback. */
const SKILL_LABELS: Record<string, string> = {
  mining: 'руды',
  herbalism: 'трав',
  woodcutting: 'дерева',
};

const GatheringSection = ({
  locationId,
  characterId,
  inventoryId,
  isCharacterHere,
  actionsLocked,
  nodes,
  onGatherSucceeded,
}: GatheringSectionProps) => {
  const dispatch = useAppDispatch();
  const isStarting = useAppSelector(selectGatheringIsStarting);
  const lastFinished = useAppSelector(selectLastFinishedSession);

  // ── One-shot completion toast ────────────────────────────────────────────
  // The slice stores `lastFinishedSession` exactly once after the next
  // /active_gathering poll that observes a newly-finalised session.
  // We surface it as a toast here and clear it so it never repeats.
  useEffect(() => {
    if (!lastFinished) return;

    const noun = SKILL_LABELS[lastFinished.skill_slug] ?? 'ресурса';

    if (lastFinished.status === 'completed' || lastFinished.status === 'inventory_full') {
      const qty = lastFinished.result_quantity;
      const xp = lastFinished.xp_gained;
      let msg = `Добыто: ${qty} ${noun} (+${xp} опыта)`;
      if (lastFinished.rank_up_to !== null) {
        msg += `. Новый ранг: ${lastFinished.rank_up_to}!`;
      }
      if (lastFinished.tool_broke) {
        msg += ' Инструмент сломался.';
      }
      if (lastFinished.status === 'inventory_full') {
        msg += ' Инвентарь переполнился — добыча завершена досрочно.';
      }
      toast.success(msg);
    } else if (lastFinished.status === 'cancelled') {
      toast('Добыча отменена', { icon: 'ℹ️' });
    } else if (lastFinished.status === 'interrupted_by_battle') {
      toast.error('Добыча прервана боем');
    }

    // Refresh location data so the bank counter / active sessions update.
    onGatherSucceeded?.();
    dispatch(clearLastFinishedSession());
  }, [lastFinished, dispatch, onGatherSucceeded]);

  // ── Start handler — passed down to each <GatheringNodeCard> ──────────────
  const handleRequestStart = async (
    node: GatheringNode,
    toolInventoryItemId: number | null,
  ): Promise<boolean> => {
    if (characterId === null) {
      toast.error('Выберите персонажа, чтобы начать добычу');
      return false;
    }
    const action = await dispatch(
      startGathering({
        locationId,
        nodeId: node.id,
        body: {
          character_id: characterId,
          tool_inventory_item_id: toolInventoryItemId,
        },
      }),
    );
    if (startGathering.rejected.match(action)) {
      const message =
        action.payload ?? 'Не удалось начать добычу. Попробуйте позже.';
      toast.error(message);
      return false;
    }
    toast.success('Добыча началась');
    onGatherSucceeded?.();
    return true;
  };

  // Hide the whole section when there is nothing to render. This mirrors
  // <DungeonEntrance>'s "no dungeons → return null" pattern.
  if (nodes.length === 0) {
    return null;
  }

  // FEAT-153 §3.6: row-3 chrome — fixed 460px box from `sm` up, natural height
  // below it; the node list is the only scrolling part.
  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-stat-energy/20 shadow-card overflow-hidden h-auto sm:h-[460px] flex flex-col">
      {/* Header — green accent per mock («Добыча ресурсов») */}
      <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3.5 border-b border-white/[0.07] shrink-0">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-stat-energy shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M11 20A7 7 0 019.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M2 21c0-3 1.85-5.36 5.08-6" />
        </svg>
        <h2 className="text-stat-energy text-[13px] font-medium uppercase tracking-[0.08em]">
          Добыча ресурсов
        </h2>
        <span className="bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
          {nodes.length}
        </span>
      </div>

      <div className="flex-1 min-h-0 max-h-[320px] sm:max-h-none overflow-y-auto gold-scrollbar space-y-2.5 p-3.5 sm:p-4">
        {nodes.map((node) => (
          <GatheringNodeCard
            key={node.id}
            node={node}
            characterId={characterId}
            inventoryId={inventoryId}
            isCharacterHere={isCharacterHere}
            actionsLocked={actionsLocked}
            isStarting={isStarting}
            onRequestStart={handleRequestStart}
          />
        ))}
      </div>
    </section>
  );
};

export default GatheringSection;
