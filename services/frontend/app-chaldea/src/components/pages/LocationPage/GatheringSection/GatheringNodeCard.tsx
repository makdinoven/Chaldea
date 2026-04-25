/**
 * GatheringNodeCard (FEAT-128, task #21).
 *
 * Renders one row of the "Ресурсы" block on the location page. Shows the
 * node name, the resulting item, the daily-bank counter, the cost summary
 * (stamina × time), and a status-specific call-to-action:
 *
 *  - available  → "Добыть" button (opens <ToolSelectionModal>)
 *  - depleted   → live MM:SS countdown until restore_at
 *  - occupied   → "Занято: <name>" when single-gather slot is held
 *  - disabled   → "Недоступна" stub
 *
 * Active gatherer avatars are shown when the node has any in-flight
 * sessions (regardless of mode) so the player can see who is busy.
 *
 * The actual `startGathering` dispatch lives in the parent
 * `<GatheringSection>` because it knows the location id; this card invokes
 * `onRequestStart(node, toolInventoryItemId)` instead.
 *
 * Tailwind only, no React.FC, mobile responsive (360px+).
 */
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import type {
  GatheringCategory,
  GatheringNode,
} from '../../../../types/gathering';
import type { NodeStatusVm } from './gatheringSection.types';
import ToolSelectionModal from './ToolSelectionModal';

interface GatheringNodeCardProps {
  node: GatheringNode;
  characterId: number | null;
  inventoryId: number | null;
  isCharacterHere: boolean;
  actionsLocked: boolean;
  isStarting: boolean;
  /**
   * Called by the card when the user has picked a tool (or chosen to gather
   * without one). Returns true on success so the card can close its modal,
   * false if the parent's API call failed (modal stays open with the error
   * already displayed via toast/banner).
   */
  onRequestStart: (
    node: GatheringNode,
    toolInventoryItemId: number | null,
  ) => Promise<boolean>;
}

const CATEGORY_LABELS: Record<GatheringCategory, string> = {
  ore: 'Руда',
  herb: 'Травы',
  wood: 'Дерево',
};

const formatHhMmSs = (totalSeconds: number): string => {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

/** Compute the visual status of the node from its raw data and the current
 *  wall-clock time. Pure — same inputs always yield the same output. */
const deriveStatus = (
  node: GatheringNode,
  nowMs: number,
): NodeStatusVm => {
  if (!node.is_enabled) {
    return { status: 'disabled', restoreRemainingSeconds: 0, occupiedBy: null };
  }
  const restoreMs = node.restore_at ? Date.parse(node.restore_at) : NaN;
  const isOnRestore = Number.isFinite(restoreMs) && restoreMs > nowMs;
  if (isOnRestore || node.current_bank <= 0) {
    return {
      status: 'depleted',
      restoreRemainingSeconds: Number.isFinite(restoreMs)
        ? Math.max(0, Math.floor((restoreMs - nowMs) / 1000))
        : 0,
      occupiedBy: null,
    };
  }
  if (!node.allow_concurrent_gather && node.active_sessions.length > 0) {
    const holder = node.active_sessions[0];
    return {
      status: 'occupied',
      restoreRemainingSeconds: 0,
      occupiedBy: { name: holder.character_name, avatar: holder.character_avatar },
    };
  }
  return { status: 'available', restoreRemainingSeconds: 0, occupiedBy: null };
};

const GatheringNodeCard = ({
  node,
  characterId,
  inventoryId,
  isCharacterHere,
  actionsLocked,
  isStarting,
  onRequestStart,
}: GatheringNodeCardProps) => {
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Re-tick the local clock once per second so the depleted countdown stays
  // accurate without a network round trip.
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  useEffect(() => {
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, []);

  const vm = useMemo(() => deriveStatus(node, nowMs), [node, nowMs]);

  const baseTimeMinutes = Math.max(1, node.stamina_per_gather * 5);
  const baseTimeLabel =
    baseTimeMinutes >= 60
      ? `${Math.floor(baseTimeMinutes / 60)} ч ${baseTimeMinutes % 60} мин`
      : `${baseTimeMinutes} мин`;

  const canGather =
    vm.status === 'available' &&
    !actionsLocked &&
    isCharacterHere &&
    characterId !== null &&
    inventoryId !== null;

  const blockedReason: string | null = (() => {
    if (!isCharacterHere) return 'Перейдите на эту локацию, чтобы добывать';
    if (actionsLocked) return 'Действие заблокировано';
    return null;
  })();

  const handleStartClick = (): void => {
    if (!canGather) {
      if (blockedReason) toast.error(blockedReason);
      return;
    }
    setModalOpen(true);
  };

  const handleConfirm = async (
    toolInventoryItemId: number | null,
  ): Promise<void> => {
    if (characterId === null) return;
    setSubmitting(true);
    try {
      const ok = await onRequestStart(node, toolInventoryItemId);
      if (ok) {
        setModalOpen(false);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="bg-white/5 rounded-card p-3 sm:p-4 flex flex-col gap-3"
    >
      {/* Header row: node name + result item summary */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <h3 className="gold-text text-base sm:text-lg font-medium truncate">
            {node.node_name}
          </h3>
          <span className="text-white/50 text-xs">
            Категория:{' '}
            <span className="text-white/80">{CATEGORY_LABELS[node.category]}</span>
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="gold-outline relative w-10 h-10 sm:w-11 sm:h-11 rounded-card overflow-hidden bg-black/40 shrink-0">
            {node.result_item_image ? (
              <img
                src={node.result_item_image}
                alt={node.result_item_name}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-white/20 text-lg">
                ?
              </div>
            )}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-white text-xs sm:text-sm font-medium truncate max-w-[160px]">
              {node.result_item_name}
            </span>
            <span className="text-white/50 text-xs">
              {`+${node.result_quantity_per_gather} за сбор`}
            </span>
          </div>
        </div>
      </div>

      {/* Bank + cost row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <span className="text-white/50">
          Осталось:{' '}
          <span className="text-white/90 font-mono">
            {`${node.current_bank} / ${node.daily_bank_max}`}
          </span>
        </span>
        <span className="text-white/50">
          Стамина:{' '}
          <span className="text-stat-stamina font-mono">
            {node.stamina_per_gather}
          </span>
        </span>
        <span className="text-white/50">
          Время:{' '}
          <span className="text-white/90 font-mono">{baseTimeLabel}</span>
        </span>
        {node.allow_concurrent_gather && (
          <span className="text-site-blue text-[11px]">Совместная добыча</span>
        )}
      </div>

      {/* Active gatherers list */}
      {node.active_sessions.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-white/50 text-xs shrink-0">
            Сейчас добывают:
          </span>
          <div className="flex items-center gap-1 flex-wrap">
            {node.active_sessions.map((s) => (
              <div
                key={s.session_id}
                className="flex items-center gap-1.5 bg-white/5 rounded-full pl-1 pr-2 py-0.5"
                title={s.character_name}
              >
                <div className="w-5 h-5 rounded-full overflow-hidden bg-black/40 shrink-0 gold-outline relative">
                  {s.character_avatar ? (
                    <img
                      src={s.character_avatar}
                      alt={s.character_name}
                      className="w-full h-full object-cover"
                    />
                  ) : null}
                </div>
                <span className="text-white/80 text-[11px] truncate max-w-[80px]">
                  {s.character_name}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Status-specific footer */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        {vm.status === 'available' && (
          <button
            type="button"
            onClick={handleStartClick}
            disabled={!canGather || isStarting || submitting}
            className="btn-blue text-sm px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label={`Добыть ${node.result_item_name}`}
          >
            {isStarting || submitting ? 'Запуск…' : 'Добыть'}
          </button>
        )}

        {vm.status === 'depleted' && (
          <div className="flex items-center gap-2 text-site-red text-sm font-medium">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4 shrink-0"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span className="break-words">
              {`Истощена. Восстановится через ${formatHhMmSs(
                vm.restoreRemainingSeconds,
              )}`}
            </span>
          </div>
        )}

        {vm.status === 'occupied' && (
          <div className="flex items-center gap-2 text-yellow-300 text-sm font-medium">
            <span>Занято:</span>
            {vm.occupiedBy?.avatar && (
              <img
                src={vm.occupiedBy.avatar}
                alt={vm.occupiedBy.name}
                className="w-6 h-6 rounded-full object-cover gold-outline"
              />
            )}
            <span className="text-white/80 truncate max-w-[160px]">
              {vm.occupiedBy?.name ?? '—'}
            </span>
          </div>
        )}

        {vm.status === 'disabled' && (
          <span className="text-white/40 text-sm">Недоступна</span>
        )}

        {/* Hint when otherwise-available but blocked by user state */}
        {vm.status === 'available' && blockedReason && (
          <span className="text-white/40 text-xs break-words">
            {blockedReason}
          </span>
        )}
      </div>

      {/* Tool-selection modal */}
      {modalOpen && characterId !== null && inventoryId !== null && (
        <ToolSelectionModal
          node={node}
          inventoryId={inventoryId}
          characterId={characterId}
          onClose={() => setModalOpen(false)}
          onConfirm={handleConfirm}
          submitting={submitting || isStarting}
        />
      )}
    </motion.div>
  );
};

export default GatheringNodeCard;
