import { useEffect, useCallback, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchClassTree,
  fetchTreeProgress,
  fetchSubclassTrees,
} from '../../redux/actions/playerTreeActions';
import {
  setSelectedNodeId,
  clearPlayerTree,
} from '../../redux/slices/playerTreeSlice';
import useMediaQuery from '../../hooks/useMediaQuery';
import PlayerTreeCanvas, { type TreeView } from './PlayerTreeCanvas';
import NodeDetailPanel from './NodeDetailPanel';
import type {
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
} from './types';
import { ArrowLeft } from 'react-feather';

/** DB class ids, in the order they are laid out around the combined wheel. */
const CLASS_IDS = [1, 2, 3] as const;

const CLASS_LABELS: Record<number, string> = {
  1: 'Воин',
  2: 'Плут',
  3: 'Маг',
};

/** Accent per class, matching the node colours in PlayerNodeComponent. */
const CLASS_ACCENTS: Record<number, string> = {
  1: '#f87171',
  2: '#34d399',
  3: '#38bdf8',
};

const SkillTreePage = () => {
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.user);
  const character = user.character;
  const authInitialized = user.authInitialized;
  const characterId = character?.id ?? null;
  const classId = (character as Record<string, unknown>)?.id_class as number | undefined;

  // The combined wheel needs room to breathe; on a phone it would be unreadable,
  // so small screens keep the one-tree-at-a-time view plus a class switcher.
  const isWideScreen = useMediaQuery('(min-width: 768px)');

  const { tree: classTree, progress: classProgress, selectedNodeId, loading, error, subclassTrees } = useAppSelector(
    (state) => state.playerTree
  );

  // Other classes' trees — reference only, never choosable.
  const [otherTrees, setOtherTrees] = useState<FullClassTreeResponse[]>([]);
  // Which class the narrow-screen view is showing.
  const [browsedClassId, setBrowsedClassId] = useState<number | null>(null);

  // Subclass tree state
  const [subclassTree, setSubclassTree] = useState<FullClassTreeResponse | null>(null);
  const [subclassProgress, setSubclassProgress] = useState<CharacterTreeProgressResponse | null>(null);
  const [viewingSubclass, setViewingSubclass] = useState(false);
  const [subclassLoading, setSubclassLoading] = useState(false);

  // Load class tree on mount
  useEffect(() => {
    if (!classId) return;
    dispatch(fetchClassTree(classId));
    setBrowsedClassId(classId);
    return () => {
      dispatch(clearPlayerTree());
    };
  }, [dispatch, classId]);

  // Load the other classes' trees for reference. A class without a tree yet
  // simply drops out — that is not an error worth showing the player.
  useEffect(() => {
    if (!classId) return;
    let cancelled = false;
    const ids = CLASS_IDS.filter((id) => id !== classId);
    Promise.all(
      ids.map((id) =>
        axios
          .get<FullClassTreeResponse>(`/skills/class_trees/by_class/${id}`)
          .then((res) => res.data)
          .catch(() => null),
      ),
    ).then((results) => {
      if (cancelled) return;
      setOtherTrees(results.filter((t): t is FullClassTreeResponse => t !== null));
    });
    return () => {
      cancelled = true;
    };
  }, [classId]);

  // Load progress + subclass trees after class tree loaded
  useEffect(() => {
    if (!classTree || !characterId) return;
    dispatch(fetchTreeProgress({ treeId: classTree.id, characterId }));
    dispatch(fetchSubclassTrees(classTree.id));
  }, [dispatch, classTree?.id, characterId]);

  useEffect(() => {
    if (error) toast.error(error);
  }, [error]);

  /** Every class tree we have, ordered by class id so sectors stay stable. */
  const allTrees = useMemo(() => {
    const trees = classTree ? [classTree, ...otherTrees] : otherTrees;
    return [...trees].sort((a, b) => a.class_id - b.class_id);
  }, [classTree, otherTrees]);

  const views: TreeView[] = useMemo(() => {
    if (viewingSubclass && subclassTree) {
      return [{ tree: subclassTree, progress: subclassProgress, readOnly: false }];
    }
    const asView = (tree: FullClassTreeResponse): TreeView => ({
      tree,
      progress: tree.class_id === classId ? classProgress : null,
      readOnly: tree.class_id !== classId,
    });
    if (isWideScreen) return allTrees.map(asView);
    const browsed = allTrees.find((t) => t.class_id === browsedClassId) ?? allTrees[0];
    return browsed ? [asView(browsed)] : [];
  }, [
    viewingSubclass,
    subclassTree,
    subclassProgress,
    isWideScreen,
    allTrees,
    browsedClassId,
    classId,
    classProgress,
  ]);

  const handleNodeClick = useCallback(
    (nodeId: number) => {
      dispatch(setSelectedNodeId(nodeId));
    },
    [dispatch]
  );

  const handleClosePanel = useCallback(() => {
    dispatch(setSelectedNodeId(null));
  }, [dispatch]);

  const handleRefreshProgress = useCallback(() => {
    if (viewingSubclass && subclassTree && characterId) {
      setSubclassLoading(true);
      axios
        .get(`/skills/class_trees/${subclassTree.id}/progress/${characterId}`)
        .then((res) => setSubclassProgress(res.data))
        .catch(() => toast.error('Ошибка обновления прогресса подкласса'))
        .finally(() => setSubclassLoading(false));
    } else if (classTree && characterId) {
      dispatch(fetchTreeProgress({ treeId: classTree.id, characterId }));
    }
  }, [dispatch, viewingSubclass, subclassTree, classTree, characterId]);

  const handleNavigateToSubclass = useCallback(
    async (subclassNodeId: number) => {
      if (!classTree || !characterId || subclassTrees.length === 0) {
        toast.error('Деревья подклассов ещё не созданы');
        return;
      }
      const chosenNode = classTree.nodes.find((n) => n.id === subclassNodeId);
      const subclassKey = chosenNode?.subclass_key ?? null;
      if (!subclassKey) {
        toast.error('У этого узла не задан подкласс');
        return;
      }
      // Deterministic link: node.subclass_key === tree.subclass_key. No name guessing.
      const matchedTree = subclassTrees.find((st) => st.subclass_key === subclassKey);
      if (!matchedTree) {
        toast.error('Дерево этого подкласса ещё не создано');
        return;
      }
      setSubclassLoading(true);
      try {
        const [treeRes, progressRes] = await Promise.all([
          axios.get(`/skills/admin/class_trees/${matchedTree.id}/full`),
          axios.get(`/skills/class_trees/${matchedTree.id}/progress/${characterId}`).catch(() => ({ data: null })),
        ]);
        setSubclassTree(treeRes.data);
        setSubclassProgress(progressRes.data);
        setViewingSubclass(true);
        dispatch(setSelectedNodeId(null));
      } catch {
        toast.error('Ошибка загрузки дерева подкласса');
      } finally {
        setSubclassLoading(false);
      }
    },
    [classTree, subclassTrees, characterId, dispatch]
  );

  const handleBackToClassTree = useCallback(() => {
    setViewingSubclass(false);
    setSubclassTree(null);
    setSubclassProgress(null);
    dispatch(setSelectedNodeId(null));
  }, [dispatch]);

  const handleBrowseClass = useCallback(
    (id: number) => {
      setBrowsedClassId(id);
      dispatch(setSelectedNodeId(null));
    },
    [dispatch]
  );

  // Auth loading
  if (!authInitialized || user.status === 'loading') {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Not logged in
  if (!user.id) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">Навыки</h2>
        <p className="text-white/50 text-lg">Войдите в аккаунт, чтобы просматривать навыки.</p>
      </div>
    );
  }

  // No character
  if (!characterId || !classId) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">Навыки</h2>
        <p className="text-white/50 text-lg">Создайте персонажа, чтобы открыть дерево навыков.</p>
      </div>
    );
  }

  // Loading tree
  if ((loading || subclassLoading) && views.length === 0) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // No tree
  if (!loading && views.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">Навыки</h2>
        <p className="text-white/50 text-lg">Дерево навыков в разработке</p>
      </div>
    );
  }

  if (views.length === 0) return null;

  const selected = selectedNodeId
    ? views
        .map((view) => {
          const node = view.tree.nodes.find((n) => n.id === selectedNodeId);
          return node ? { node, view } : null;
        })
        .find((hit) => hit !== null) ?? null
    : null;

  const showsWholeWheel = isWideScreen && !viewingSubclass && views.length > 1;
  const headerTree = viewingSubclass ? subclassTree : views[0]?.tree ?? null;

  return (
    <div className="w-full px-2 md:px-6 py-4">
      <div className="w-full">
        {/* Class switcher — narrow screens only, where one tree is shown at a time */}
        {!viewingSubclass && !isWideScreen && (
          <div className="flex gap-2 mb-3">
            {allTrees.map((t) => {
              const active = t.class_id === (browsedClassId ?? classId);
              const own = t.class_id === classId;
              return (
                <button
                  key={t.class_id}
                  onClick={() => handleBrowseClass(t.class_id)}
                  className={`flex-1 rounded-card px-3 py-2 text-sm font-medium uppercase tracking-wide transition-colors duration-200 ${
                    active ? 'text-white' : 'text-white/40 hover:text-white/70'
                  }`}
                  style={{
                    background: active ? `${CLASS_ACCENTS[t.class_id]}22` : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${active ? `${CLASS_ACCENTS[t.class_id]}66` : 'transparent'}`,
                  }}
                >
                  {CLASS_LABELS[t.class_id] ?? t.name}
                  {!own && <span className="block text-[9px] normal-case text-white/40">просмотр</span>}
                </button>
              );
            })}
          </div>
        )}

        {/*
          The wheel gets a round frame instead of the usual panel: a circle of
          content inside a square box left obvious dead corners. The frame is a
          square that never exceeds 80vh, so the circle stays a circle, and the
          canvas is clipped to it while the overlays below sit outside the clip.
        */}
        <div
          className={`relative ${
            showsWholeWheel
              ? 'w-full max-w-[80vh] aspect-square mx-auto'
              : 'w-full h-[65vh] md:h-[80vh]'
          }`}
        >
          <div
            className={`absolute inset-0 overflow-hidden bg-[#12121e] ${
              showsWholeWheel ? 'rounded-full' : 'rounded-card'
            }`}
          >
            <PlayerTreeCanvas views={views} onNodeClick={handleNodeClick} />
          </div>

          {/* Header */}
          <div className="absolute top-3 left-4 z-10 flex items-center gap-3">
            {viewingSubclass && (
              <button
                onClick={handleBackToClassTree}
                className="flex items-center gap-1.5 bg-black/50 backdrop-blur-sm rounded-lg px-3 py-1.5 text-white/70 hover:text-white transition-colors duration-200 text-sm"
              >
                <ArrowLeft size={14} />
                Назад
              </button>
            )}
            <div className="bg-black/40 backdrop-blur-sm rounded-lg px-3 py-1.5">
              <h3 className="gold-text text-sm font-medium uppercase">
                {showsWholeWheel ? 'Древо навыков' : headerTree?.name}
                {viewingSubclass && headerTree?.subclass_name && (
                  <span className="text-white/40 ml-1.5 font-normal normal-case text-xs">
                    — {headerTree.subclass_name}
                  </span>
                )}
              </h3>
              {classProgress && (
                <p className="text-white/40 text-[10px] mt-0.5">
                  Уровень {classProgress.character_level} &middot; Опыт: {classProgress.active_experience}
                </p>
              )}
            </div>
          </div>

          {/* Sector legend — only meaningful when all three classes are on screen */}
          {showsWholeWheel && (
            <div className="absolute top-3 right-4 z-10 bg-black/40 backdrop-blur-sm rounded-lg px-3 py-2 flex flex-col gap-1">
              {views.map((view) => (
                <div key={view.tree.class_id} className="flex items-center gap-2">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{
                      background: CLASS_ACCENTS[view.tree.class_id] ?? '#fff',
                      opacity: view.readOnly ? 0.4 : 1,
                    }}
                  />
                  <span className={`text-[10px] uppercase tracking-wide ${view.readOnly ? 'text-white/35' : 'text-white'}`}>
                    {CLASS_LABELS[view.tree.class_id] ?? view.tree.name}
                  </span>
                  {!view.readOnly && (
                    <span className="text-gold text-[9px] normal-case">ваш класс</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Node detail modal */}
          <AnimatePresence>
            {selected && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="absolute inset-0 z-20 flex items-center justify-center bg-black/50 backdrop-blur-[2px]"
                onClick={handleClosePanel}
              >
                <motion.div
                  initial={{ opacity: 0, scale: 0.9, y: 20 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.9, y: 20 }}
                  transition={{ duration: 0.25, ease: 'easeOut' }}
                  className="w-[90%] max-w-[420px] max-h-[70vh] overflow-y-auto gold-scrollbar"
                  onClick={(e) => e.stopPropagation()}
                >
                  <NodeDetailPanel
                    node={selected.node}
                    tree={selected.view.tree}
                    progress={selected.view.progress}
                    characterId={characterId}
                    readOnly={selected.view.readOnly}
                    onClose={handleClosePanel}
                    onRefresh={handleRefreshProgress}
                    onNavigateToSubclass={
                      !selected.view.readOnly && selected.node.node_type === 'subclass_choice'
                        ? handleNavigateToSubclass
                        : undefined
                    }
                  />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default SkillTreePage;
