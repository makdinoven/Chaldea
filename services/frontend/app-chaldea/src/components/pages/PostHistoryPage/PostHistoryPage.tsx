import { useParams, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import PostHistoryTab from '../../ProfilePage/PostHistoryTab/PostHistoryTab';
import EmptyState from '../../ProfilePage/shared/EmptyState';

/**
 * Standalone /post-history/:characterId page.
 * Keeps its own page chrome (Back link) and reuses the profile tab component
 * for the actual content (FEAT-166 T8).
 */
const PostHistoryPage = () => {
  const { characterId } = useParams<{ characterId: string }>();
  const numericId = Number(characterId);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="pb-12"
    >
      <div className="flex items-center gap-4 mb-6">
        <Link
          to="/profile"
          className="text-white/50 hover:text-site-blue transition-colors duration-200 ease-site text-sm"
        >
          &larr; Назад к профилю
        </Link>
      </div>

      {Number.isFinite(numericId) && numericId > 0 ? (
        <PostHistoryTab characterId={numericId} />
      ) : (
        <EmptyState message="Персонаж не найден" className="py-32 px-4" />
      )}
    </motion.div>
  );
};

export default PostHistoryPage;
