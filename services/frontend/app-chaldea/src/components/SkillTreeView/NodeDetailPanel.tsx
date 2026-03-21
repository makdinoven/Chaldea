import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../redux/store';
import { chooseNode, resetTree } from '../../redux/actions/playerTreeActions';
import { computeNodeState } from './utils/computeNodeState';
import SkillPurchaseCard from './SkillPurchaseCard';
import type {
  TreeNodeInTreeResponse,
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
  NodeVisualState,
} from './types';

interface NodeDetailPanelProps {
  node: TreeNodeInTreeResponse;
  tree: FullClassTreeResponse;
  progress: CharacterTreeProgressResponse | null;
  characterId: number;
  onClose: () => void;
  onRefresh: () => void;
}

const nodeTypeLabels: Record<string, string> = {
  regular: 'Обычный узел',
  root: 'Корневой узел',
  subclass_choice: 'Выбор подкласса',
};

const NodeDetailPanel = ({
  node,
  tree,
  progress,
  characterId,
  onClose,
  onRefresh,
}: NodeDetailPanelProps) => {
  const dispatch = useAppDispatch();
  const [choosing, setChoosing] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [resetting, setResetting] = useState(false);

  const chosenNodeIds = useMemo(() => {
    if (!progress) return new Set<number>();
    return new Set(progress.chosen_nodes.map((cn) => cn.node_id));
  }, [progress]);

  const characterLevel = progress?.character_level ?? 0;
  const activeExperience = progress?.active_experience ?? 0;

  const visualState: NodeVisualState = computeNodeState(
    node,
    tree.connections,
    chosenNodeIds,
    characterLevel,
    tree.nodes
  );

  const handleChooseNode = async () => {
    setChoosing(true);
    try {
      await dispatch(
        chooseNode({
          treeId: tree.id,
          characterId,
          nodeId: node.id,
        })
      ).unwrap();
      toast.success('Узел выбран!');
      onRefresh();
    } catch (err) {
      const message = typeof err === 'string' ? err : 'Ошибка выбора узла';
      toast.error(message);
    } finally {
      setChoosing(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    try {
      const result = await dispatch(
        resetTree({ treeId: tree.id, characterId })
      ).unwrap();
      toast.success(
        `Прогресс сброшен: ${result.nodes_reset} узлов, ${result.skills_removed} навыков удалено`
      );
      setResetConfirmOpen(false);
      onRefresh();
    } catch (err) {
      const message = typeof err === 'string' ? err : 'Ошибка сброса прогресса';
      toast.error(message);
    } finally {
      setResetting(false);
    }
  };

  const stateMessages: Record<NodeVisualState, string> = {
    chosen: 'Узел выбран',
    available: 'Доступен для выбора',
    locked: `Требуется уровень ${node.level_ring}`,
    blocked: 'Альтернативная ветка уже выбрана',
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="gray-bg gold-outline relative rounded-card p-5 flex flex-col gap-4 h-full overflow-hidden"
    >
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-3 right-3 text-white/40 hover:text-white text-lg transition-colors duration-200 ease-site z-10 w-7 h-7 flex items-center justify-center"
      >
        &#10005;
      </button>

      {/* Header */}
      <div>
        <h3 className="gold-text text-lg font-medium uppercase pr-8">
          {node.name}
        </h3>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-white/50 text-xs">
            {nodeTypeLabels[node.node_type] ?? node.node_type}
          </span>
          <span className="text-white/30 text-xs">&middot;</span>
          <span className="text-white/50 text-xs">
            Уровень {node.level_ring}
          </span>
        </div>
      </div>

      {/* Description */}
      {node.description && (
        <p className="text-white/70 text-sm leading-relaxed">
          {node.description}
        </p>
      )}

      {/* Status message */}
      <div
        className={`text-xs font-medium px-3 py-1.5 rounded-full self-start ${
          visualState === 'chosen'
            ? 'bg-green-400/15 text-green-400'
            : visualState === 'available'
              ? 'bg-gold/15 text-gold'
              : visualState === 'blocked'
                ? 'bg-site-red/15 text-site-red'
                : 'bg-white/10 text-white/50'
        }`}
      >
        {stateMessages[visualState]}
      </div>

      {/* Choose node button */}
      {visualState === 'available' && (
        <button
          onClick={handleChooseNode}
          disabled={choosing}
          className="btn-blue w-full text-base disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {choosing ? 'Выбираю...' : 'Выбрать путь'}
        </button>
      )}

      {/* Skills list (only for chosen nodes) */}
      {visualState === 'chosen' && node.skills.length > 0 && (
        <div className="flex flex-col gap-2 flex-1 overflow-hidden">
          <h4 className="text-white text-sm font-medium uppercase tracking-wide">
            Навыки ({node.skills.length})
          </h4>
          <div className="gold-scrollbar overflow-y-auto flex-1 flex flex-col gap-2 pr-1">
            {node.skills.map((skill) => (
              <SkillPurchaseCard
                key={skill.id}
                skill={skill}
                nodeId={node.id}
                characterId={characterId}
                activeExperience={activeExperience}
                purchasedSkills={progress?.purchased_skills ?? []}
                onRefresh={onRefresh}
              />
            ))}
          </div>
        </div>
      )}

      {/* Chosen but no skills */}
      {visualState === 'chosen' && node.skills.length === 0 && (
        <p className="text-white/40 text-sm">В этом узле пока нет навыков</p>
      )}

      {/* Locked/blocked info for skills */}
      {(visualState === 'locked' || visualState === 'blocked') &&
        node.skills.length > 0 && (
          <p className="text-white/30 text-xs">
            Выберите этот узел, чтобы получить доступ к {node.skills.length}{' '}
            навык(ам)
          </p>
        )}

      {/* Reset button at bottom */}
      {chosenNodeIds.size > 0 && (
        <div className="mt-auto pt-3 border-t border-white/10">
          <button
            onClick={() => setResetConfirmOpen(true)}
            className="text-site-red/70 hover:text-site-red text-xs transition-colors duration-200 ease-site"
          >
            Сбросить прогресс
          </button>
        </div>
      )}

      {/* Reset confirmation modal */}
      <AnimatePresence>
        {resetConfirmOpen && (
          <div className="modal-overlay" onClick={() => setResetConfirmOpen(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-md"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-xl uppercase mb-4">
                Сбросить прогресс?
              </h2>
              <p className="text-white/70 text-sm mb-2">
                Все выбранные узлы будут сброшены (кроме подкласса).
              </p>
              <p className="text-site-red text-sm mb-6">
                Купленные навыки из сброшенных узлов будут удалены. Опыт не
                возвращается!
              </p>
              <div className="flex gap-4">
                <button
                  onClick={handleReset}
                  disabled={resetting}
                  className="px-6 py-2 rounded-card bg-site-red/80 hover:bg-site-red text-white text-sm font-medium transition-colors duration-200 ease-site disabled:opacity-40"
                >
                  {resetting ? 'Сброс...' : 'Подтвердить сброс'}
                </button>
                <button
                  onClick={() => setResetConfirmOpen(false)}
                  className="btn-line text-sm"
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default NodeDetailPanel;
