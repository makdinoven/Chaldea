import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import { selectHierarchyTree, selectWorldMapLoading } from '../../../redux/slices/worldMapSlice';
import TreeNode from './TreeNode';

interface HierarchyTreeProps {
  currentLocationId: number | null;
}

const HierarchyTree = ({ currentLocationId }: HierarchyTreeProps) => {
  const hierarchyTree = useAppSelector(selectHierarchyTree);
  const loading = useAppSelector(selectWorldMapLoading);
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  const treeContent = (
    <div className="gold-scrollbar overflow-y-auto max-h-[calc(100vh-200px)]">
      {loading && hierarchyTree.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : hierarchyTree.length === 0 ? (
        <p className="text-white/50 text-sm text-center py-4">
          Игровой мир пуст
        </p>
      ) : (
        hierarchyTree.map((node) => (
          <TreeNode
            key={`${node.type}-${node.id}`}
            node={node}
            depth={0}
            currentLocationId={currentLocationId}
            onNavigate={() => setIsMobileOpen(false)}
          />
        ))
      )}
    </div>
  );

  return (
    <>
      {/* Mobile toggle button */}
      <button
        onClick={() => setIsMobileOpen(true)}
        className="md:hidden fixed bottom-4 left-4 z-40 w-12 h-12 rounded-full
                   bg-site-bg shadow-card flex items-center justify-center
                   gold-outline transition-shadow duration-200 ease-site hover:shadow-hover"
        aria-label="Открыть навигацию"
      >
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Desktop sidebar */}
      <aside className="hidden md:block w-[280px] shrink-0">
        <div className="gray-bg p-4 sticky top-4">
          <h3 className="gold-text text-lg font-medium uppercase mb-3 tracking-wider">
            Навигация
          </h3>
          {treeContent}
        </div>
      </aside>

      {/* Mobile drawer overlay */}
      <AnimatePresence>
        {isMobileOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="md:hidden fixed inset-0 bg-black/60 z-50"
              onClick={() => setIsMobileOpen(false)}
            />

            {/* Drawer */}
            <motion.div
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="md:hidden fixed top-0 left-0 bottom-0 w-[85vw] max-w-[320px] z-50
                         bg-site-dark overflow-y-auto"
            >
              <div className="p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="gold-text text-lg font-medium uppercase tracking-wider">
                    Навигация
                  </h3>
                  <button
                    onClick={() => setIsMobileOpen(false)}
                    className="w-8 h-8 flex items-center justify-center text-white/60
                               hover:text-white transition-colors duration-200 ease-site"
                    aria-label="Закрыть навигацию"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                {treeContent}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
};

export default HierarchyTree;
