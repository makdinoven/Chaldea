import { useState, useMemo, useCallback } from 'react';
import { motion } from 'motion/react';
import ModalShell from '../CommonComponents/ModalShell/ModalShell';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  distributeLootThunk,
  finalizeSessionThunk,
  selectDistributeLoading,
  selectLastDistributeResponse,
  selectFinalizeLoading,
} from '../../redux/slices/dungeonSlice';
import { itemLabel } from '../../api/dungeons';
import type { GroupInventoryItem, SessionMember, LootDistribution } from '../../api/dungeons';

// --- Types ---

interface DungeonLootDistributionProps {
  sessionId: number;
  characterId: number;
  groupInventory: GroupInventoryItem[];
  members: SessionMember[];
  isLeader: boolean;
}

interface AggregatedItem {
  item_id: number;
  name: string;
  quantity: number;
}

/** key = `${item_id}:${character_id}` → quantity */
type Allocations = Record<string, number>;

const allocKey = (itemId: number, characterId: number) => `${itemId}:${characterId}`;

// --- Component ---

/**
 * Sharing the loot of an ended run (completed or escaped). The leader hands
 * items out (partially if wanted); the run is then closed with «Завершить
 * забег». Undivided leftovers are lost only after an explicit confirm
 * (finalize with force=true).
 */
const DungeonLootDistribution = ({
  sessionId,
  characterId,
  groupInventory,
  members,
  isLeader,
}: DungeonLootDistributionProps) => {
  const dispatch = useAppDispatch();
  const distributeLoading = useAppSelector(selectDistributeLoading);
  const lastDistributeResponse = useAppSelector(selectLastDistributeResponse);
  const finalizeLoading = useAppSelector(selectFinalizeLoading);

  const [allocations, setAllocations] = useState<Allocations>({});
  const [showForceConfirm, setShowForceConfirm] = useState(false);
  // Loot goes to the living only (the backend refuses the fallen).
  const recipients = useMemo(() => members.filter((m) => m.status !== 'dead'), [members]);

  // The same item can sit in several rows (different sources) — share by item.
  const items = useMemo<AggregatedItem[]>(() => {
    const map = new Map<number, AggregatedItem>();
    for (const row of groupInventory) {
      const existing = map.get(row.item_id);
      if (existing) {
        existing.quantity += row.quantity;
      } else {
        map.set(row.item_id, { item_id: row.item_id, name: itemLabel(row), quantity: row.quantity });
      }
    }
    return Array.from(map.values());
  }, [groupInventory]);

  const allocatedFor = useCallback(
    (itemId: number) =>
      recipients.reduce((sum, m) => sum + (allocations[allocKey(itemId, m.character_id)] ?? 0), 0),
    [allocations, recipients],
  );

  const setQty = useCallback((itemId: number, charId: number, qty: number) => {
    setAllocations((prev) => {
      const next = { ...prev };
      if (qty <= 0) delete next[allocKey(itemId, charId)];
      else next[allocKey(itemId, charId)] = qty;
      return next;
    });
  }, []);

  /** Everything still unassigned goes to one member. */
  const giveAllTo = useCallback(
    (charId: number) => {
      setAllocations(() => {
        const next: Allocations = {};
        for (const item of items) next[allocKey(item.item_id, charId)] = item.quantity;
        return next;
      });
    },
    [items],
  );

  const distributions = useMemo<LootDistribution[]>(
    () =>
      Object.entries(allocations)
        .filter(([, qty]) => qty > 0)
        .map(([key, qty]) => {
          const [itemId, charId] = key.split(':').map(Number);
          return { item_id: itemId, to_character_id: charId, quantity: qty };
        }),
    [allocations],
  );

  const totalAllocated = distributions.reduce((s, d) => s + d.quantity, 0);
  const totalAvailable = items.reduce((s, i) => s + i.quantity, 0);
  const failedNames = (lastDistributeResponse?.failed ?? []).map((f) => {
    const item = items.find((i) => i.item_id === f.item_id);
    const member = members.find((m) => m.character_id === f.to_character_id);
    return `${item?.name ?? `Предмет #${f.item_id}`} ×${f.quantity} → ${member?.name ?? `#${f.to_character_id}`}`;
  });

  const handleDistribute = () => {
    if (distributions.length === 0) return;
    dispatch(distributeLootThunk({ sessionId, characterId, distributions }))
      .unwrap()
      .then(() => setAllocations({}))
      .catch(() => {
        // Error toast + state refresh happen in the thunk.
      });
  };

  const handleFinalize = (force: boolean) => {
    setShowForceConfirm(false);
    dispatch(finalizeSessionThunk({ sessionId, characterId, force }));
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-4"
    >
      <div className="bg-black/50 rounded-card p-4 sm:p-6 backdrop-blur-sm flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">Дележ добычи</h2>
          {items.length > 0 && (
            <span className="text-white/40 text-xs">
              Назначено: {totalAllocated} / {totalAvailable}
            </span>
          )}
        </div>

        {!isLeader && (
          <p className="text-white/60 text-sm bg-white/5 rounded-card p-3">
            Добычу делит лидер группы. Предметы придут в инвентарь, как только он их раздаст.
          </p>
        )}

        {failedNames.length > 0 && (
          <div className="bg-site-red/10 border border-site-red/30 rounded-card p-3" role="alert">
            <p className="text-site-red text-sm font-medium mb-1">
              Не удалось выдать — предметы вернулись в общий инвентарь:
            </p>
            {failedNames.map((line, i) => (
              <p key={i} className="text-site-red/80 text-xs">{line}</p>
            ))}
          </div>
        )}

        {items.length === 0 ? (
          <p className="text-white/60 text-sm">Общий инвентарь пуст — делить нечего.</p>
        ) : (
          <>
            {isLeader && recipients.length > 1 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-white/40 text-xs">Отдать всё:</span>
                {recipients.map((m) => (
                  <button
                    key={m.character_id}
                    onClick={() => giveAllTo(m.character_id)}
                    className="chip-outline rounded-full px-3 py-1 text-xs"
                  >
                    {m.name}
                  </button>
                ))}
              </div>
            )}

            <div className="flex flex-col gap-3">
              {items.map((item) => {
                const remaining = item.quantity - allocatedFor(item.item_id);
                return (
                  <div key={item.item_id} className="bg-white/5 rounded-card p-3 sm:p-4">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <span className="text-white text-sm font-medium truncate">{item.name}</span>
                      <span className={`text-xs shrink-0 ${remaining > 0 ? 'text-gold' : 'text-white/30'}`}>
                        {isLeader ? `Свободно: ${remaining}` : `×${item.quantity}`}
                      </span>
                    </div>

                    {isLeader && (
                      <div className="flex flex-col gap-2">
                        {recipients.map((member) => {
                          const qty = allocations[allocKey(item.item_id, member.character_id)] ?? 0;
                          return (
                            <div key={member.character_id} className="flex items-center justify-between gap-2">
                              <span className="text-white/60 text-xs truncate min-w-0 flex-1">
                                {member.name}
                              </span>
                              <div className="flex items-center gap-1 shrink-0">
                                <button
                                  onClick={() => setQty(item.item_id, member.character_id, qty - 1)}
                                  disabled={qty === 0}
                                  className="w-8 h-8 flex items-center justify-center rounded-card bg-white/10 text-white/60 hover:bg-white/20 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed text-sm"
                                  aria-label="Уменьшить"
                                >
                                  −
                                </button>
                                <span className="w-8 text-center text-white text-xs font-medium">{qty}</span>
                                <button
                                  onClick={() => setQty(item.item_id, member.character_id, qty + 1)}
                                  disabled={remaining <= 0}
                                  className="w-8 h-8 flex items-center justify-center rounded-card bg-white/10 text-white/60 hover:bg-white/20 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed text-sm"
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
          </>
        )}

        {isLeader && (
          <div className="flex flex-col sm:flex-row gap-3">
            {items.length > 0 && (
              <button
                onClick={handleDistribute}
                disabled={distributeLoading || distributions.length === 0}
                className="btn-blue text-sm px-6 py-2.5 flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {distributeLoading ? 'Раздаём...' : 'Раздать назначенное'}
              </button>
            )}
            {items.length === 0 ? (
              <button
                onClick={() => handleFinalize(false)}
                disabled={finalizeLoading}
                className="btn-blue text-sm px-6 py-2.5 flex-1 disabled:opacity-50"
              >
                {finalizeLoading ? 'Завершение...' : 'Завершить забег'}
              </button>
            ) : (
              <button
                onClick={() => setShowForceConfirm(true)}
                disabled={finalizeLoading || distributeLoading}
                className="text-sm px-6 py-2.5 flex-1 rounded-card border border-site-red/40 text-site-red hover:bg-site-red/10 transition-colors disabled:opacity-50"
              >
                Закрыть забег, остаток пропадёт
              </button>
            )}
          </div>
        )}
      </div>

      <ModalShell
        open={showForceConfirm}
        onClose={() => setShowForceConfirm(false)}
        title="Закрыть забег?"
        size="sm"
        footer={
          <>
            <button onClick={() => setShowForceConfirm(false)} className="btn-line text-sm w-full sm:w-auto">
              Назад
            </button>
            <button
              onClick={() => handleFinalize(true)}
              disabled={finalizeLoading}
              className="text-sm px-5 py-2 w-full sm:w-auto rounded-card bg-site-red/20 border border-site-red/40 text-site-red hover:bg-site-red/30 transition-colors disabled:opacity-50"
            >
              {finalizeLoading ? 'Закрываем...' : 'Закрыть, остаток пропадёт'}
            </button>
          </>
        }
      >
        <p className="text-white/70 text-sm mb-2">
          В общем инвентаре ещё {totalAvailable} шт. нерозданной добычи. Если закрыть забег сейчас, она
          пропадёт навсегда.
        </p>
        <div className="text-white/50 text-xs flex flex-wrap gap-x-3">
          {items.map((i) => (
            <span key={i.item_id}>{i.name} ×{i.quantity}</span>
          ))}
        </div>
      </ModalShell>
    </motion.div>
  );
};

export default DungeonLootDistribution;
