import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { fetchPostHistory, PostHistoryItem } from '../../../api/characterLogs';

const formatDate = (isoDate: string): string => {
  const date = new Date(isoDate);
  const months = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
  ];
  const day = date.getDate();
  const month = months[date.getMonth()];
  const year = date.getFullYear();
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${day} ${month} ${year}, ${hours}:${minutes}`;
};

const PREVIEW_LENGTH = 200;

const stripHtmlTags = (html: string): string =>
  html.replace(/<[^>]*>/g, '').trim();

interface PostCardProps {
  post: PostHistoryItem;
}

const PostCard = ({ post }: PostCardProps) => {
  const [expanded, setExpanded] = useState(false);
  const plainText = stripHtmlTags(post.content);
  const isLong = plainText.length > PREVIEW_LENGTH;

  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
      className="gray-bg p-4 sm:p-6 rounded-card"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-4 mb-3">
        <Link
          to={`/location/${post.location_id}`}
          className="gold-text text-lg sm:text-xl font-medium hover:underline transition-colors duration-200 ease-site"
        >
          {post.location_name}
        </Link>
        <span className="text-white/40 text-xs sm:text-sm shrink-0">
          {formatDate(post.created_at)}
        </span>
      </div>

      <div className="text-white text-sm sm:text-base leading-relaxed mb-3 break-words overflow-hidden">
        {expanded || !isLong ? (
          <div dangerouslySetInnerHTML={{ __html: post.content }} />
        ) : (
          <p>{plainText.slice(0, PREVIEW_LENGTH)}...</p>
        )}
      </div>

      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-site-blue text-sm hover:underline transition-colors duration-200 ease-site mb-3"
        >
          {expanded ? 'Свернуть' : 'Показать полностью'}
        </button>
      )}

      <div className="flex flex-wrap items-center gap-3 sm:gap-5 text-xs sm:text-sm text-white/50">
        <span>{post.char_count} символов</span>
        <span className="text-gold">+{post.xp_earned} XP</span>
      </div>
    </motion.div>
  );
};

const PostHistoryPage = () => {
  const { characterId } = useParams<{ characterId: string }>();
  const [posts, setPosts] = useState<PostHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!characterId) return;

    const loadPosts = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchPostHistory(Number(characterId));
        setPosts(response.posts);
      } catch {
        const message = 'Не удалось загрузить историю постов';
        setError(message);
        toast.error(message);
      } finally {
        setLoading(false);
      }
    };

    loadPosts();
  }, [characterId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="pb-12"
    >
      <div className="flex items-center gap-4 mb-8">
        <Link
          to="/profile"
          className="text-white/50 hover:text-site-blue transition-colors duration-200 ease-site text-sm"
        >
          &larr; Назад к профилю
        </Link>
      </div>

      <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase mb-8">
        История постов
      </h1>

      {error && (
        <div className="text-site-red text-base mb-6">{error}</div>
      )}

      {!error && posts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20">
          <p className="text-white/50 text-lg">Постов пока нет</p>
        </div>
      )}

      {posts.length > 0 && (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.05 } },
          }}
          className="flex flex-col gap-4"
        >
          {posts.map((post) => (
            <PostCard key={post.id} post={post} />
          ))}
        </motion.div>
      )}
    </motion.div>
  );
};

export default PostHistoryPage;
