import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../redux/store';
import {
  fetchSkillFullTree,
  upgradeSkill,
} from '../../redux/actions/playerTreeActions';
import type { SkillFullTree, SkillRankRead } from './types';

interface SkillUpgradeModalProps {
  skillId: number;
  characterId: number;
  currentRankId: number;
  onClose: () => void;
  onRefresh: () => void;
}

/**
 * Builds a set of rank IDs that the character has already acquired,
 * starting from rank 1 and following the path to currentRankId.
 */
const buildOwnedRankIds = (
  ranks: SkillRankRead[],
  currentRankId: number
): Set<number> => {
  const owned = new Set<number>();
  owned.add(currentRankId);

  // Walk up from current to find ancestry (rank tree is small, brute force is fine)
  // A rank is "owned" if it's an ancestor of currentRankId
  const rankMap = new Map(ranks.map((r) => [r.id, r]));

  // Find all ancestors by checking who points to whom
  const findAncestors = (id: number) => {
    for (const rank of ranks) {
      if (rank.left_child_id === id || rank.right_child_id === id) {
        owned.add(rank.id);
        findAncestors(rank.id);
      }
    }
  };
  findAncestors(currentRankId);

  return owned;
};

/**
 * Get available next ranks (direct children of current rank that are not yet owned).
 */
const getAvailableUpgrades = (
  ranks: SkillRankRead[],
  currentRankId: number,
  ownedIds: Set<number>
): SkillRankRead[] => {
  const current = ranks.find((r) => r.id === currentRankId);
  if (!current) return [];

  const available: SkillRankRead[] = [];
  if (current.left_child_id && !ownedIds.has(current.left_child_id)) {
    const left = ranks.find((r) => r.id === current.left_child_id);
    if (left) available.push(left);
  }
  if (current.right_child_id && !ownedIds.has(current.right_child_id)) {
    const right = ranks.find((r) => r.id === current.right_child_id);
    if (right) available.push(right);
  }
  return available;
};

/**
 * Simple DFS layout for rank mini-tree.
 */
interface LayoutNode {
  rank: SkillRankRead;
  x: number;
  y: number;
}

const layoutRankTree = (ranks: SkillRankRead[]): LayoutNode[] => {
  if (ranks.length === 0) return [];

  const rankMap = new Map(ranks.map((r) => [r.id, r]));

  // Find roots (ranks that are not children of anyone)
  const childIds = new Set<number>();
  for (const r of ranks) {
    if (r.left_child_id) childIds.add(r.left_child_id);
    if (r.right_child_id) childIds.add(r.right_child_id);
  }
  const roots = ranks.filter((r) => !childIds.has(r.id));

  const result: LayoutNode[] = [];
  const visited = new Set<number>();

  const dfs = (rank: SkillRankRead, x: number, y: number, spread: number) => {
    if (visited.has(rank.id)) return;
    visited.add(rank.id);
    result.push({ rank, x, y });

    if (rank.left_child_id) {
      const left = rankMap.get(rank.left_child_id);
      if (left) dfs(left, x - spread, y + 100, spread * 0.6);
    }
    if (rank.right_child_id) {
      const right = rankMap.get(rank.right_child_id);
      if (right) dfs(right, x + spread, y + 100, spread * 0.6);
    }
  };

  let startY = 0;
  for (const root of roots) {
    dfs(root, 250, startY, 120);
    startY += 200;
  }

  return result;
};

const SkillUpgradeModal = ({
  skillId,
  characterId,
  currentRankId,
  onClose,
  onRefresh,
}: SkillUpgradeModalProps) => {
  const dispatch = useAppDispatch();
  const [skillTree, setSkillTree] = useState<SkillFullTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState(false);

  useEffect(() => {
    setLoading(true);
    dispatch(fetchSkillFullTree(skillId))
      .unwrap()
      .then((data) => {
        setSkillTree(data);
      })
      .catch((err) => {
        const message = typeof err === 'string' ? err : 'Ошибка загрузки дерева навыка';
        toast.error(message);
      })
      .finally(() => setLoading(false));
  }, [dispatch, skillId]);

  const handleUpgrade = useCallback(
    async (nextRankId: number) => {
      setUpgrading(true);
      try {
        await dispatch(
          upgradeSkill({ characterId, nextRankId })
        ).unwrap();
        toast.success('Навык улучшен!');
        onRefresh();
        onClose();
      } catch (err) {
        const message = typeof err === 'string' ? err : 'Ошибка улучшения навыка';
        toast.error(message);
      } finally {
        setUpgrading(false);
      }
    },
    [dispatch, characterId, onRefresh, onClose]
  );

  const ranks = skillTree?.ranks ?? [];
  const ownedIds = buildOwnedRankIds(ranks, currentRankId);
  const availableUpgrades = getAvailableUpgrades(ranks, currentRankId, ownedIds);
  const availableIds = new Set(availableUpgrades.map((r) => r.id));
  const layoutNodes = layoutRankTree(ranks);

  return (
    <AnimatePresence>
      <div className="modal-overlay" onClick={onClose}>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="modal-content gold-outline gold-outline-thick max-w-2xl max-h-[85vh] overflow-hidden flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="gold-text text-xl font-medium uppercase">
              {skillTree?.name ?? 'Улучшение навыка'}
            </h2>
            <button
              onClick={onClose}
              className="text-white/50 hover:text-white text-xl transition-colors duration-200 ease-site w-8 h-8 flex items-center justify-center"
            >
              &#10005;
            </button>
          </div>

          {skillTree?.description && (
            <p className="text-white/60 text-sm mb-4">{skillTree.description}</p>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
            </div>
          ) : ranks.length === 0 ? (
            <p className="text-white/50 text-sm text-center py-8">
              Ранги навыка не найдены
            </p>
          ) : (
            <div className="gold-scrollbar overflow-y-auto flex-1">
              {/* Rank tree visual */}
              <div
                className="relative mx-auto"
                style={{
                  width: '500px',
                  height: `${Math.max(...layoutNodes.map((n) => n.y)) + 140}px`,
                  maxWidth: '100%',
                }}
              >
                {/* Connection lines */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none">
                  {ranks.map((rank) => {
                    const parentLayout = layoutNodes.find(
                      (n) => n.rank.id === rank.id
                    );
                    if (!parentLayout) return null;

                    const lines: JSX.Element[] = [];
                    const drawLine = (childId: number | null, key: string) => {
                      if (!childId) return;
                      const childLayout = layoutNodes.find(
                        (n) => n.rank.id === childId
                      );
                      if (!childLayout) return;

                      const bothOwned =
                        ownedIds.has(rank.id) && ownedIds.has(childId);

                      lines.push(
                        <line
                          key={key}
                          x1={parentLayout.x}
                          y1={parentLayout.y + 36}
                          x2={childLayout.x}
                          y2={childLayout.y}
                          stroke={bothOwned ? '#f0d95c' : 'rgba(255,255,255,0.15)'}
                          strokeWidth={bothOwned ? 2 : 1}
                        />
                      );
                    };

                    drawLine(rank.left_child_id, `${rank.id}-left`);
                    drawLine(rank.right_child_id, `${rank.id}-right`);
                    return lines;
                  })}
                </svg>

                {/* Rank nodes */}
                {layoutNodes.map(({ rank, x, y }) => {
                  const isOwned = ownedIds.has(rank.id);
                  const isCurrent = rank.id === currentRankId;
                  const isAvailable = availableIds.has(rank.id);

                  return (
                    <div
                      key={rank.id}
                      className={`
                        absolute flex flex-col items-center justify-center
                        w-[72px] h-[72px] rounded-full border-2
                        transition-all duration-200 ease-site
                        ${
                          isCurrent
                            ? 'border-green-400 bg-green-400/15 shadow-[0_0_10px_rgba(74,222,128,0.4)]'
                            : isOwned
                              ? 'border-green-400/60 bg-green-400/10'
                              : isAvailable
                                ? 'border-gold bg-gold/10 cursor-pointer hover:shadow-[0_0_10px_rgba(240,217,92,0.4)]'
                                : 'border-white/15 bg-white/5 opacity-40'
                        }
                      `}
                      style={{
                        left: `${x - 36}px`,
                        top: `${y}px`,
                      }}
                      onClick={
                        isAvailable && !upgrading
                          ? () => handleUpgrade(rank.id)
                          : undefined
                      }
                      title={
                        isCurrent
                          ? 'Текущий ранг'
                          : isAvailable
                            ? `Улучшить (${rank.upgrade_cost} опыта)`
                            : isOwned
                              ? 'Изучено'
                              : 'Недоступно'
                      }
                    >
                      <span className="text-white text-[10px] font-medium text-center leading-tight px-1 line-clamp-2">
                        {rank.rank_name}
                      </span>
                      {rank.upgrade_cost > 0 && (
                        <span className="text-white/40 text-[9px] mt-0.5">
                          {rank.upgrade_cost} оп.
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Selected rank details (current rank info) */}
              {(() => {
                const current = ranks.find((r) => r.id === currentRankId);
                if (!current) return null;
                return (
                  <div className="mt-4 p-3 rounded-card bg-white/[0.04] space-y-2">
                    <h4 className="text-white text-sm font-medium">
                      Текущий ранг: {current.rank_name}
                    </h4>
                    <div className="flex flex-wrap gap-3 text-xs text-white/60">
                      {current.cost_energy > 0 && (
                        <span>Энергия: {current.cost_energy}</span>
                      )}
                      {current.cost_mana > 0 && (
                        <span>Мана: {current.cost_mana}</span>
                      )}
                      {current.cooldown > 0 && (
                        <span>Перезарядка: {current.cooldown}</span>
                      )}
                    </div>
                    {current.damage_entries.length > 0 && (
                      <div className="text-xs text-white/50">
                        <span className="text-white/70">Урон: </span>
                        {current.damage_entries.map((d, i) => (
                          <span key={i}>
                            {d.damage_type} {d.amount}
                            {i < current.damage_entries.length - 1 ? ', ' : ''}
                          </span>
                        ))}
                      </div>
                    )}
                    {current.effects.length > 0 && (
                      <div className="text-xs text-white/50">
                        <span className="text-white/70">Эффекты: </span>
                        {current.effects.map((e, i) => (
                          <span key={i}>
                            {e.effect_name} ({e.magnitude}, {e.duration} ход.)
                            {i < current.effects.length - 1 ? ', ' : ''}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          )}
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default SkillUpgradeModal;
