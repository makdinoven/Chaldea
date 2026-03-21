import { useEffect, useCallback } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchClassTree,
  fetchTreeProgress,
} from '../../../redux/actions/playerTreeActions';
import {
  setSelectedNodeId,
  clearPlayerTree,
} from '../../../redux/slices/playerTreeSlice';
import PlayerTreeCanvas from '../../SkillTreeView/PlayerTreeCanvas';
import NodeDetailPanel from '../../SkillTreeView/NodeDetailPanel';

interface SkillsTabProps {
  characterId: number;
}

const SkillsTab = ({ characterId }: SkillsTabProps) => {
  const dispatch = useAppDispatch();
  const character = useAppSelector((state) => state.user.character);
  const { tree, progress, selectedNodeId, loading, error } = useAppSelector(
    (state) => state.playerTree
  );

  const classId = (character as Record<string, unknown>)?.id_class as
    | number
    | undefined;

  // Load tree on mount
  useEffect(() => {
    if (!classId) return;
    dispatch(fetchClassTree(classId));

    return () => {
      dispatch(clearPlayerTree());
    };
  }, [dispatch, classId]);

  // Load progress after tree is loaded
  useEffect(() => {
    if (!tree) return;
    dispatch(fetchTreeProgress({ treeId: tree.id, characterId }));
  }, [dispatch, tree?.id, characterId]);

  // Show errors
  useEffect(() => {
    if (error) {
      toast.error(error);
    }
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
    if (!tree) return;
    dispatch(fetchTreeProgress({ treeId: tree.id, characterId }));
  }, [dispatch, tree?.id, characterId]);

  // No class
  if (!classId) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-32"
      >
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">
          Навыки
        </h2>
        <p className="text-white/50 text-lg">
          Создайте персонажа, чтобы открыть дерево навыков.
        </p>
      </motion.div>
    );
  }

  // Loading
  if (loading && !tree) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // No tree for this class (404 from backend)
  if (!loading && !tree && error) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-32"
      >
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">
          Навыки
        </h2>
        <p className="text-white/50 text-lg">
          Дерево навыков в разработке
        </p>
      </motion.div>
    );
  }

  if (!tree) return null;

  // Find selected node data
  const selectedNode = selectedNodeId
    ? tree.nodes.find((n) => n.id === selectedNodeId) ?? null
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col md:flex-row gap-4 w-full"
    >
      {/* Tree canvas */}
      <div
        className={`
          relative w-full
          ${selectedNode ? 'md:w-[65%] lg:w-[70%]' : 'md:w-full'}
          h-[60vh] md:h-[75vh] rounded-card overflow-hidden
          transition-all duration-300 ease-site
        `}
        style={{ background: 'rgba(0,0,0,0.2)' }}
      >
        {/* Tree name header */}
        <div className="absolute top-3 left-4 z-10">
          <h3 className="gold-text text-lg font-medium uppercase">
            {tree.name}
          </h3>
          {progress && (
            <p className="text-white/50 text-xs mt-0.5">
              Уровень {progress.character_level} &middot; Опыт:{' '}
              {progress.active_experience}
            </p>
          )}
        </div>

        <PlayerTreeCanvas
          tree={tree}
          progress={progress}
          onNodeClick={handleNodeClick}
        />
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <div className="w-full md:w-[35%] lg:w-[30%] md:max-h-[75vh]">
          <NodeDetailPanel
            node={selectedNode}
            tree={tree}
            progress={progress}
            characterId={characterId}
            onClose={handleClosePanel}
            onRefresh={handleRefreshProgress}
          />
        </div>
      )}
    </motion.div>
  );
};

export default SkillsTab;
