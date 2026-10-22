import { useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import { selectHierarchyTree, selectWorldMapLoading } from '../../../redux/slices/worldMapSlice';
import TreeNode from './TreeNode';

interface HierarchyTreeProps {
  currentLocationId: number | null;
  open: boolean;
  onClose: () => void;
}

/**
 * The world's hierarchy — areas, countries, regions, zones, locations — in a
 * panel that slides in from the left over the map, on every screen size, so
 * the map itself can take the page's whole width. Opened by the «Навигация»
 * button above the map; going somewhere closes it.
 */
const HierarchyTree = ({ currentLocationId, open, onClose }: HierarchyTreeProps) => {
  const hierarchyTree = useAppSelector(selectHierarchyTree);
  const loading = useAppSelector(selectWorldMapLoading);

  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/60 z-50"
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.aside
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="fixed top-0 left-0 bottom-0 w-[85vw] max-w-[340px] z-50
                       bg-site-dark overflow-y-auto gold-scrollbar"
            aria-label="Навигация по миру"
          >
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="gold-text text-lg font-medium uppercase tracking-wider">
                  Навигация
                </h3>
                <button
                  onClick={onClose}
                  className="w-8 h-8 flex items-center justify-center text-white/60
                             hover:text-white transition-colors duration-200 ease-site"
                  aria-label="Закрыть навигацию"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              {loading && hierarchyTree.length === 0 ? (
                <div className="flex items-center justify-center py-8">
                  <div className="w-6 h-6 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
                </div>
              ) : hierarchyTree.length === 0 ? (
                <p className="text-white/50 text-sm text-center py-4">Игровой мир пуст</p>
              ) : (
                hierarchyTree.map((node) => (
                  <TreeNode
                    key={`${node.type}-${node.id}`}
                    node={node}
                    depth={0}
                    currentLocationId={currentLocationId}
                    onNavigate={onClose}
                  />
                ))
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
};

export default HierarchyTree;
