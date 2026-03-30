import { useState, useMemo, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  distributeLootThunk,
  finalizeSessionThunk,
  selectDistributeLoading,
  selectLastDistributeResponse,
  selectFinalizeLoading,
  selectLastFinalizeResponse,
} from '../../redux/slices/dungeonSlice';
import type {
  GroupInventoryItem,
  SessionMember,
  LootDistribution,
  DistributeLootResponse,
} from '../../api/dungeons';

// --- Types ---

interface DungeonLootDistributionProps {
  sessionId: number;
  characterId: number;
  groupInventory: GroupInventoryItem[];
  members: SessionMember[];
  isLeader: boolean;
  onFinalized: () => void;
}

interface AllocationEntry {
  item_id: number;
  character_id: number;
  quantity: number;
}

// --- Component ---

const DungeonLootDistribution = ({
  sessionId,
  characterId,
  groupInventory,
  members,
  isLeader,
  onFinalized,
}: DungeonLootDistributionProps) => {
  const dispatch = useAppDispatch();
  const distributeLoading = useAppSelector(selectDistributeLoading);
  const lastDistributeResponse = useAppSelector(selectLastDistributeResponse);
  const finalizeLoading = useAppSelector(selectFinalizeLoading);
  const lastFinalizeResponse = useAppSelector(selectLastFinalizeResponse);

  const [allocations, setAllocations] = useState<AllocationEntry[]>([]);
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  // Only alive members can receive loot
  const aliveMembers = useMemo(
    () => members.filter((m) => m.status === 'alive'),
    [members],
  );

  // Calculate how much of each item is already allocated
  const allocatedByItem = useMemo(() => {
    const map: Record<number, number> = {};
    for (const a of allocations) {
      map[a.item_id] = (map[a.item_id] ?? 0) + a.quantity;
    }
    return map;
  }, [allocations]);

  // Get remaining quantity for an item
  const getRemainingQty = useCallback(
    (item: GroupInventoryItem) => {
      return item.quantity - (allocatedByItem[item.item_id] ?? 0);
    },
    [allocatedByItem],
  );

  // Get allocation for a specific item + member
  const getAllocation = useCallback(
    (itemId: number, charId: number) => {
      return allocations.find(
        (a) => a.item_id === itemId && a.character_id === charId,
      )?.quantity ?? 0;
    },
    [allocations],
  );

  // Set allocation for a specific item + member
  const setAllocation = useCallback(
    (itemId: number, charId: number, qty: number) => {
      setAllocations((prev) => {
        const without = prev.filter(
          (a) => !(a.item_id === itemId && a.character_id === charId),
        );
        if (qty <= 0) return without;
        return [...without, { item_id: itemId, character_id: charId, quantity: qty }];
      });
    },
    [],
  );

  // Increment/decrement helpers
  const incrementAllocation = useCallback(
    (item: GroupInventoryItem, charId: number) => {
      const current = getAllocation(item.item_id, charId);
      const remaining = getRemainingQty(item);
      if (remaining > 0) {
        setAllocation(item.item_id, charId, current + 1);
      }
    },
    [getAllocation, getRemainingQty, setAllocation],
  );

  const decrementAllocation = useCallback(
    (itemId: number, charId: number) => {
      const current = getAllocation(itemId, charId);
      if (current > 0) {
        setAllocation(itemId, charId, current - 1);
      }
    },
    [getAllocation, setAllocation],
  );

  // Build distributions for API
  const buildDistributions = useCallback((): LootDistribution[] => {
    return allocations
      .filter((a) => a.quantity > 0)
      .map((a) => ({ item_id: a.item_id, to_character_id: a.character_id, quantity: a.quantity }));
  }, [allocations]);

  // Total allocated items count
  const totalAllocated = useMemo(
    () => allocations.reduce((sum, a) => sum + a.quantity, 0),
    [allocations],
  );

  const totalAvailable = useMemo(
    () => groupInventory.reduce((sum, item) => sum + item.quantity, 0),
    [groupInventory],
  );

  const hasUnallocated = totalAllocated < totalAvailable;

  // Handlers
  const handleDistribute = useCallback(() => {
    const distributions = buildDistributions();
    if (distributions.length === 0 && groupInventory.length > 0) {
      setShowDiscardConfirm(true);
      return;
    }
    dispatch(distributeLootThunk({ sessionId, characterId, distributions }));
  }, [dispatch, sessionId, characterId, buildDistributions, groupInventory.length]);

  const handleDiscardAndDistribute = useCallback(() => {
    const distributions = buildDistributions();
    dispatch(distributeLootThunk({ sessionId, characterId, distributions }));
    setShowDiscardConfirm(false);
  }, [dispatch, sessionId, characterId, buildDistributions]);

  const handleFinalize = useCallback(() => {
    dispatch(finalizeSessionThunk({ sessionId, characterId }));
  }, [dispatch, sessionId, characterId]);

  // After finalize success — redirect to location
  useEffect(() => {
    if (lastFinalizeResponse) {
      onFinalized();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastFinalizeResponse]);

  // After distribution: show summary
  if (lastDistributeResponse) {
    return (
      <DistributionSummary
        response={lastDistributeResponse}
        isLeader={isLeader}
        finalizeLoading={finalizeLoading}
        onFinalize={handleFinalize}
      />
    );
  }

  // No items to distribute
  if (groupInventory.length === 0) {
    return (
      <div className="bg-black/60 rounded-card p-6 sm:p-8 backdrop-blur-sm flex flex-col items-center gap-4 text-center">
        <div className="w-16 h-16 flex items-center justify-center text-4xl">
          {'\uD83D\uDCE6'}
        </div>
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase">
          Распределение добычи
        </h2>
        <p className="text-white/60 text-sm">
          Групповой инвентарь пуст. Нечего распределять.
        </p>
        {isLeader && (
          <button
            onClick={handleFinalize}
            disabled={finalizeLoading}
            className="btn-blue text-sm sm:text-base px-8 py-3 disabled:opacity-50"
          >
            {finalizeLoading ? 'Завершение...' : 'Завершить подземелье'}
          </button>
        )}
      </div>
    );
  }

  // Main distribution UI
  return (
    <div className="flex flex-col gap-4">
      <div className="bg-black/60 rounded-card p-4 sm:p-6 backdrop-blur-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
            Распределение добычи
          </h2>
          <span className="text-white/40 text-xs">
            Распределено: {totalAllocated} / {totalAvailable}
          </span>
        </div>

        {!isLeader && (
          <div className="bg-white/5 rounded-card p-3 mb-4">
            <p className="text-white/50 text-sm">
              Лидер группы распределяет добычу. Ожидайте.
            </p>
          </div>
        )}

        {/* Item list */}
        <div className="flex flex-col gap-3">
          {groupInventory.map((item) => {
            const remaining = getRemainingQty(item);
            return (
              <div
                key={item.item_id}
                className="bg-white/5 rounded-card p-3 sm:p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-white text-sm font-medium truncate mr-2">
                    {item.item_name}
                  </span>
                  <span className={`text-xs shrink-0 ${remaining > 0 ? 'text-gold' : 'text-white/30'}`}>
                    Осталось: {remaining}
                  </span>
                </div>

                {/* Per-member allocation */}
                {isLeader && (
                  <div className="flex flex-col gap-2">
                    {aliveMembers.map((member) => {
                      const qty = getAllocation(item.item_id, member.character_id);
                      return (
                        <div
                          key={member.character_id}
                          className="flex items-center justify-between gap-2"
                        >
                          <span className="text-white/60 text-xs truncate min-w-0 flex-1">
                            {member.name}
                          </span>
                          <div className="flex items-center gap-1 shrink-0">
                            <button
                              onClick={() => decrementAllocation(item.item_id, member.character_id)}
                              disabled={qty === 0}
                              className="w-7 h-7 flex items-center justify-center rounded bg-white/10 text-white/60 hover:bg-white/20 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed text-sm"
                              aria-label="Уменьшить"
                            >
                              -
                            </button>
                            <span className="w-8 text-center text-white text-xs font-medium">
                              {qty}
                            </span>
                            <button
                              onClick={() => incrementAllocation(item, member.character_id)}
                              disabled={remaining === 0}
                              className="w-7 h-7 flex items-center justify-center rounded bg-white/10 text-white/60 hover:bg-white/20 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed text-sm"
                              aria-label="Увеличить"
                            >
                              +
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Member summary cards */}
      {isLeader && totalAllocated > 0 && (
        <div className="bg-black/40 rounded-card p-4 backdrop-blur-sm">
          <h3 className="gold-text text-sm font-medium uppercase mb-3">
            Итог распределения
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {aliveMembers.map((member) => {
              const memberItems = allocations.filter(
                (a) => a.character_id === member.character_id && a.quantity > 0,
              );
              if (memberItems.length === 0) return null;
              return (
                <div
                  key={member.character_id}
                  className="bg-white/5 rounded-card p-3"
                >
                  <p className="text-white text-xs font-medium mb-1.5 truncate">
                    {member.name}
                  </p>
                  {memberItems.map((a) => {
                    const item = groupInventory.find((i) => i.item_id === a.item_id);
                    return (
                      <p key={a.item_id} className="text-white/50 text-xs">
                        {item?.item_name ?? `#${a.item_id}`} x{a.quantity}
                      </p>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Actions */}
      {isLeader && (
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={handleDistribute}
            disabled={distributeLoading}
            className="btn-blue text-sm px-6 py-2.5 flex-1 disabled:opacity-50"
          >
            {distributeLoading
              ? 'Распределение...'
              : hasUnallocated
                ? 'Распределить (остаток будет выброшен)'
                : 'Распределить'}
          </button>
        </div>
      )}

      {/* Discard confirmation modal */}
      <AnimatePresence>
        {showDiscardConfirm && (
          <div className="modal-overlay" onClick={() => setShowDiscardConfirm(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-sm w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="gold-text text-lg font-medium uppercase mb-3">
                Выбросить всю добычу?
              </h3>
              <p className="text-white/70 text-sm mb-4">
                Вы не назначили ни одного предмета. Все предметы будут потеряны.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handleDiscardAndDistribute}
                  disabled={distributeLoading}
                  className="text-sm px-5 py-2 flex-1 rounded-card bg-site-red/20 border border-site-red/40 text-site-red hover:bg-site-red/30 transition-colors disabled:opacity-50"
                >
                  {distributeLoading ? 'Выполнение...' : 'Выбросить всё'}
                </button>
                <button
                  onClick={() => setShowDiscardConfirm(false)}
                  className="btn-line text-sm px-5 py-2 flex-1"
                >
                  Назад
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

// --- Distribution Summary ---

interface DistributionSummaryProps {
  response: DistributeLootResponse;
  isLeader: boolean;
  finalizeLoading: boolean;
  onFinalize: () => void;
}

const DistributionSummary = ({
  response,
  isLeader,
  finalizeLoading,
  onFinalize,
}: DistributionSummaryProps) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.3, ease: 'easeOut' }}
    className="bg-black/60 rounded-card p-6 sm:p-8 backdrop-blur-sm flex flex-col items-center gap-5"
  >
    <div className="w-14 h-14 flex items-center justify-center text-3xl">
      {'\u2705'}
    </div>
    <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase text-center">
      Добыча распределена
    </h2>

    {(response.distributed ?? []).length > 0 && (
      <div className="w-full max-w-lg">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {response.distributed.map((entry) => (
            <div
              key={entry.character_id}
              className="bg-white/5 rounded-card p-3"
            >
              <p className="text-white text-sm font-medium mb-1 truncate">
                {entry.character_name}
              </p>
              {entry.items.map((item) => (
                <p key={item.item_id} className="text-white/50 text-xs">
                  {item.item_name} x{item.quantity}
                </p>
              ))}
            </div>
          ))}
        </div>
      </div>
    )}

    {(response.remaining_inventory ?? []).length > 0 && (
      <div className="w-full max-w-lg bg-white/5 rounded-card p-3">
        <p className="text-white/40 text-xs font-medium uppercase mb-1">
          Выброшено
        </p>
        {response.remaining_inventory.map((item) => (
          <p key={item.item_id} className="text-white/30 text-xs">
            {item.item_name} x{item.quantity}
          </p>
        ))}
      </div>
    )}

    {isLeader && (
      <button
        onClick={onFinalize}
        disabled={finalizeLoading}
        className="btn-blue text-sm sm:text-base px-8 py-3 disabled:opacity-50"
      >
        {finalizeLoading ? 'Завершение...' : 'Завершить подземелье'}
      </button>
    )}

    {!isLeader && (
      <p className="text-white/40 text-sm italic">
        Ожидание завершения лидером...
      </p>
    )}
  </motion.div>
);

export default DungeonLootDistribution;
