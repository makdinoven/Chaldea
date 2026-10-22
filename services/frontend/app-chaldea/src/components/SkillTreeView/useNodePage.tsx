import { useCallback, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../redux/store';
import { chooseNode, purchaseSkill, resetTree } from '../../redux/actions/playerTreeActions';
import { computeTreeStates } from './utils/computeNodeState';
import { toSameOriginMedia } from '../pages/BattlePage/Arena3D/sameOriginMedia';
import SkillUpgradeModal from './SkillUpgradeModal';
import ModalShell from '../CommonComponents/ModalShell/ModalShell';
import type { NodePageAction, NodePageModel, NodePageTone } from './Books3D/nodePageModel';
import type {
  CharacterTreeProgressResponse,
  FullClassTreeResponse,
  NodeVisualState,
  TreeNodeInTreeResponse,
} from './types';

/*
  Everything a node's page in a book needs from the game: what to write on it,
  and what each control on it does. The same rules and requests as
  NodeDetailPanel, which serves the 2D wheel; the book draws the page in ink
  instead of laying a panel over it.
*/

const NODE_TYPE_LABELS: Record<string, string> = {
  regular: 'Обычный узел',
  root: 'Корневой узел',
  subclass_choice: 'Выбор подкласса',
};

const SKILL_TYPE_LABELS: Record<string, string> = {
  attack: 'Атака',
  defense: 'Защита',
  support: 'Поддержка',
};

interface UseNodePageArgs {
  node: TreeNodeInTreeResponse | null;
  tree: FullClassTreeResponse | null;
  progress: CharacterTreeProgressResponse | null;
  readOnly: boolean;
  characterId: number | null;
  onClose: () => void;
  onRefresh: () => void;
  onNavigateToSubclass?: (nodeId: number) => void;
  /** Opens a learned skill's own page for upgrading; without it, the upgrade window opens instead. */
  onUpgradeSkill?: (skillId: number) => void;
}

const useNodePage = ({
  node,
  tree,
  progress,
  readOnly,
  characterId,
  onClose,
  onRefresh,
  onNavigateToSubclass,
  onUpgradeSkill,
}: UseNodePageArgs) => {
  const dispatch = useAppDispatch();
  const [choosing, setChoosing] = useState(false);
  const [learningSkillId, setLearningSkillId] = useState<number | null>(null);
  const [upgradeSkillId, setUpgradeSkillId] = useState<number | null>(null);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [resetting, setResetting] = useState(false);

  const chosenNodeIds = useMemo(
    () => new Set((progress?.chosen_nodes ?? []).map((cn) => cn.node_id)),
    [progress],
  );

  const model: NodePageModel | null = useMemo(() => {
    if (!node || !tree) return null;
    const state: NodeVisualState = readOnly
      ? 'locked'
      : computeTreeStates(tree.nodes, tree.connections, chosenNodeIds, progress?.character_level ?? 0).state.get(node.id) ??
        'locked';

    const stateText: Record<NodeVisualState, string> = {
      chosen: 'Узел выбран',
      available: 'Доступен для выбора',
      locked: `Требуется уровень ${node.level_ring}`,
      blocked: 'Альтернативная ветка уже выбрана',
      unreachable: 'Путь сюда перекрыт выбранной веткой',
    };
    const tone: NodePageTone = readOnly
      ? 'muted'
      : state === 'chosen'
        ? 'chosen'
        : state === 'available'
          ? 'available'
          : state === 'blocked'
            ? 'blocked'
            : 'muted';

    const purchased = progress?.purchased_skills ?? [];
    const skills = node.skills.map((s) => ({
      skillId: s.skill_id,
      name: s.skill_name ?? `Навык #${s.skill_id}`,
      typeLabel: s.skill_type ? SKILL_TYPE_LABELS[s.skill_type] ?? s.skill_type : null,
      image: toSameOriginMedia(s.skill_image),
      learned: purchased.some((p) => p.skill_id === s.skill_id),
      busy: learningSkillId === s.skill_id,
    }));

    let action: NodePageModel['action'] = null;
    if (state === 'available') action = { kind: 'choose', label: choosing ? 'Выбираю…' : 'Выбрать путь', busy: choosing };
    else if (state === 'chosen' && node.node_type === 'subclass_choice' && onNavigateToSubclass)
      action = { kind: 'subclass', label: 'К дереву подкласса →', busy: false };

    let hint: string | null = null;
    if (readOnly) hint = 'Изучать можно только узлы дерева своего класса.';
    else if ((state === 'locked' || state === 'blocked') && node.skills.length > 0)
      hint = `Выберите этот узел, чтобы получить доступ к навыкам: ${node.skills.length}.`;
    // A subclass node holds no skills by design: its path goes on in the subclass's chapter.
    else if (state === 'chosen' && node.skills.length === 0 && node.node_type !== 'subclass_choice')
      hint = 'В этом узле пока нет навыков.';

    // Reset is withheld once a subclass is chosen — that choice is final.
    const canReset =
      !readOnly &&
      chosenNodeIds.size > 0 &&
      !tree.nodes.some((n) => n.node_type === 'subclass_choice' && chosenNodeIds.has(n.id));

    return {
      nodeId: node.id,
      title: node.name,
      meta: `${NODE_TYPE_LABELS[node.node_type] ?? node.node_type} · Уровень ${node.level_ring}`,
      description: node.description,
      status: { text: readOnly ? `${tree.name} — только просмотр` : stateText[state], tone },
      action,
      skills,
      skillsMode: readOnly ? 'listed' : state === 'chosen' ? 'learnable' : 'hidden',
      hint,
      canReset,
    };
  }, [node, tree, progress, readOnly, chosenNodeIds, choosing, learningSkillId, onNavigateToSubclass]);

  const onAction = useCallback(
    async (action: NodePageAction) => {
      if (!node || !tree || characterId === null) return;
      switch (action.kind) {
        case 'close':
          onClose();
          return;
        case 'subclass':
          onNavigateToSubclass?.(node.id);
          return;
        case 'upgrade':
          if (onUpgradeSkill) onUpgradeSkill(action.skillId);
          else setUpgradeSkillId(action.skillId);
          return;
        case 'reset':
          setResetConfirmOpen(true);
          return;
        case 'choose': {
          if (choosing) return;
          setChoosing(true);
          try {
            await dispatch(chooseNode({ treeId: tree.id, characterId, nodeId: node.id })).unwrap();
            toast.success('Узел выбран!');
            onRefresh();
          } catch (err) {
            toast.error(typeof err === 'string' ? err : 'Ошибка выбора узла');
          } finally {
            setChoosing(false);
          }
          return;
        }
        case 'learn': {
          if (learningSkillId !== null) return;
          setLearningSkillId(action.skillId);
          try {
            await dispatch(purchaseSkill({ characterId, nodeId: node.id, skillId: action.skillId })).unwrap();
            toast.success('Навык изучен!');
            onRefresh();
          } catch (err) {
            toast.error(typeof err === 'string' ? err : 'Ошибка покупки навыка');
          } finally {
            setLearningSkillId(null);
          }
        }
      }
    },
    [node, tree, characterId, choosing, learningSkillId, dispatch, onClose, onRefresh, onNavigateToSubclass, onUpgradeSkill],
  );

  const handleReset = async () => {
    if (!tree || characterId === null) return;
    setResetting(true);
    try {
      const result = await dispatch(resetTree({ treeId: tree.id, characterId })).unwrap();
      toast.success(`Прогресс сброшен: ${result.nodes_reset} узлов, ${result.skills_removed} навыков удалено`);
      setResetConfirmOpen(false);
      onRefresh();
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Ошибка сброса прогресса');
    } finally {
      setResetting(false);
    }
  };

  // The windows a page's controls open are ordinary DOM over everything.
  const modals = (
    <>
      {upgradeSkillId !== null && characterId !== null && (
        <SkillUpgradeModal
          skillId={upgradeSkillId}
          characterId={characterId}
          onClose={() => setUpgradeSkillId(null)}
          onRefresh={onRefresh}
        />
      )}
      <ModalShell
        open={resetConfirmOpen}
        onClose={() => setResetConfirmOpen(false)}
        title="Сбросить прогресс?"
        size="sm"
        footer={
          <>
            <button
              onClick={() => setResetConfirmOpen(false)}
              className="btn-line text-sm w-full sm:w-auto"
            >
              Отмена
            </button>
            <button
              onClick={handleReset}
              disabled={resetting}
              className="w-full sm:w-auto px-6 py-2 rounded-card bg-site-red/80 hover:bg-site-red text-white text-sm font-medium transition-colors duration-200 ease-site disabled:opacity-40"
            >
              {resetting ? 'Сброс...' : 'Подтвердить сброс'}
            </button>
          </>
        }
      >
        <p className="text-white/70 text-sm mb-2">
          Все выбранные узлы будут сброшены (кроме подкласса).
        </p>
        <p className="text-site-red text-sm">
          Купленные навыки из сброшенных узлов будут удалены. Опыт не возвращается!
        </p>
      </ModalShell>
    </>
  );

  return { model, onAction, modals };
};

export default useNodePage;
