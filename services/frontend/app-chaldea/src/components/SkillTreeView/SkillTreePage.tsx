import { useEffect, useCallback, useState } from 'react';
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
import PlayerTreeCanvas from './PlayerTreeCanvas';
import NodeDetailPanel from './NodeDetailPanel';
import type {
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
} from './types';
import { ArrowLeft } from 'react-feather';

const SkillTreePage = () => {
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.user);
  const character = user.character;
  const authInitialized = user.authInitialized;
  const characterId = character?.id ?? null;
  const classId = (character as Record<string, unknown>)?.id_class as number | undefined;

  const { tree: classTree, progress: classProgress, selectedNodeId, loading, error, subclassTrees } = useAppSelector(
    (state) => state.playerTree
  );

  // Subclass tree state
  const [subclassTree, setSubclassTree] = useState<FullClassTreeResponse | null>(null);
  const [subclassProgress, setSubclassProgress] = useState<CharacterTreeProgressResponse | null>(null);
  const [viewingSubclass, setViewingSubclass] = useState(false);
  const [subclassLoading, setSubclassLoading] = useState(false);

  const tree = viewingSubclass ? subclassTree : classTree;
  const progress = viewingSubclass ? subclassProgress : classProgress;

  // Load class tree on mount
  useEffect(() => {
    if (!classId) return;
    dispatch(fetchClassTree(classId));
    return () => {
      dispatch(clearPlayerTree());
    };
  }, [dispatch, classId]);

  // Load progress + subclass trees after class tree loaded
  useEffect(() => {
    if (!classTree || !characterId) return;
    dispatch(fetchTreeProgress({ treeId: classTree.id, characterId }));
    dispatch(fetchSubclassTrees(classTree.id));
  }, [dispatch, classTree?.id, characterId]);

  useEffect(() => {
    if (error) toast.error(error);
  }, [error]);

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
      const nodeName = chosenNode?.name?.toLowerCase() ?? '';
      let matchedTree = subclassTrees.find(
        (st) => st.subclass_name?.toLowerCase() === nodeName || st.name?.toLowerCase().includes(nodeName)
      );
      if (!matchedTree && subclassTrees.length > 0) matchedTree = subclassTrees[0];
      if (!matchedTree) {
        toast.error('Дерево подкласса не найдено');
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
  if ((loading || subclassLoading) && !tree) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // No tree
  if (!loading && !tree && error) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">Навыки</h2>
        <p className="text-white/50 text-lg">Дерево навыков в разработке</p>
      </div>
    );
  }

  if (!tree) return null;

  const selectedNode = selectedNodeId
    ? tree.nodes.find((n) => n.id === selectedNodeId) ?? null
    : null;

  return (
    <div className="w-full px-2 md:px-6 py-4">
      <div className="w-full">
        <div className="relative w-full h-[65vh] md:h-[80vh] rounded-card overflow-hidden bg-[#12121e]">
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
                {tree.name}
                {viewingSubclass && tree.subclass_name && (
                  <span className="text-white/40 ml-1.5 font-normal normal-case text-xs">
                    — {tree.subclass_name}
                  </span>
                )}
              </h3>
              {progress && (
                <p className="text-white/40 text-[10px] mt-0.5">
                  Уровень {progress.character_level} &middot; Опыт: {progress.active_experience}
                </p>
              )}
            </div>
          </div>

          <PlayerTreeCanvas tree={tree} progress={progress} onNodeClick={handleNodeClick} />

          {/* Node detail modal */}
          <AnimatePresence>
            {selectedNode && (
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
                    node={selectedNode}
                    tree={tree}
                    progress={progress}
                    characterId={characterId}
                    onClose={handleClosePanel}
                    onRefresh={handleRefreshProgress}
                    onNavigateToSubclass={
                      selectedNode.node_type === 'subclass_choice'
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
