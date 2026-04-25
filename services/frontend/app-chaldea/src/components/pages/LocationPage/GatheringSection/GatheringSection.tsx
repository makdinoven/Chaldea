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

  return (
    <section className="bg-black/60 rounded-card p-4 sm:p-6 backdrop-blur-sm flex flex-col gap-4">
      <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
        Ресурсы
      </h2>

      <div className="flex flex-col gap-3">
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
