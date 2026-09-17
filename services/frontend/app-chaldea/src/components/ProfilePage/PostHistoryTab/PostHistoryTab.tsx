// FEAT-166 T8 — «История постов» as a regular profile tab.
// Shared by the /profile tab switch and the standalone /post-history/:characterId page.
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { ScrollText } from 'lucide-react';
import { fetchPostHistory, PostHistoryItem } from '../../../api/characterLogs';
import { EMPTY_DATE_PLACEHOLDER, parseServerDate } from '../../../utils/serverDate';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import EmptyState from '../shared/EmptyState';
import ErrorState from '../shared/ErrorState';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';
import PanelScrollArea from '../shared/PanelScrollArea';
import ProfileCard from '../shared/ProfileCard';

/* ── Constants ── */

const PANEL_TITLE = 'История постов';
const PREVIEW_LENGTH = 200;

const TAB_MOTION = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: 'easeOut' as const },
};

const MONTHS = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

/* ── Helpers ── */

const formatDate = (isoDate: string): string => {
  const date = parseServerDate(isoDate);
  if (!date) return EMPTY_DATE_PLACEHOLDER;
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}, ${hours}:${minutes}`;
};

const stripHtmlTags = (html: string): string => html.replace(/<[^>]*>/g, '').trim();

/* ── Post card ── */

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
    >
      <ProfileCard className="p-3.5 sm:p-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-4 mb-2.5">
          <Link
            to={`/location/${post.location_id}`}
            className="gold-text text-sm sm:text-base font-medium hover:underline transition-colors duration-200 ease-site break-words"
          >
            {post.location_name}
          </Link>
          <span className="text-white/40 text-xs shrink-0">
            {formatDate(post.created_at)}
          </span>
        </div>

        <div className="text-white/85 text-sm leading-relaxed mb-2.5 break-words overflow-hidden">
          {expanded || !isLong ? (
            <div dangerouslySetInnerHTML={{ __html: post.content }} />
          ) : (
            <p>{plainText.slice(0, PREVIEW_LENGTH)}...</p>
          )}
        </div>

        {isLong && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-site-blue text-xs sm:text-sm hover:underline transition-colors duration-200 ease-site mb-2.5"
          >
            {expanded ? 'Свернуть' : 'Показать полностью'}
          </button>
        )}

        <div className="flex flex-wrap items-center gap-3 sm:gap-5 text-xs text-white/50">
          <span>{post.char_count} символов</span>
          <span className="text-gold">+{post.xp_earned} XP</span>
        </div>
      </ProfileCard>
    </motion.div>
  );
};

/* ── Component ── */

interface PostHistoryTabProps {
  characterId: number;
}

const PostHistoryTab = ({ characterId }: PostHistoryTabProps) => {
  const [posts, setPosts] = useState<PostHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!characterId) return;

    const loadPosts = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchPostHistory(characterId);
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

  const panelIcon = <ScrollText size={18} strokeWidth={1.8} className="text-gold shrink-0" />;

  if (loading) {
    return (
      <motion.div {...TAB_MOTION}>
        <PanelShell title={PANEL_TITLE} icon={panelIcon}>
          <LoadingState />
        </PanelShell>
      </motion.div>
    );
  }

  return (
    <motion.div {...TAB_MOTION}>
      <PanelShell
        title={PANEL_TITLE}
        icon={panelIcon}
        headerExtra={!error ? <PanelCounter>{posts.length}</PanelCounter> : undefined}
        className={PANEL_DESKTOP_HEIGHT_CLASS}
        bodyClassName="flex-1 min-h-0 flex flex-col"
      >
        <PanelScrollArea className="!pt-4">
          {error ? (
            <ErrorState message={error} />
          ) : posts.length === 0 ? (
            <EmptyState
              icon={<ScrollText size={32} strokeWidth={1.5} className="text-white/20" />}
              message="Постов пока нет"
              hint="Здесь будут отображаться отыгранные посты персонажа"
            />
          ) : (
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{
                hidden: {},
                visible: { transition: { staggerChildren: 0.05 } },
              }}
              className="flex flex-col gap-3"
            >
              {posts.map((post) => (
                <PostCard key={post.id} post={post} />
              ))}
            </motion.div>
          )}
        </PanelScrollArea>
      </PanelShell>
    </motion.div>
  );
};

export default PostHistoryTab;
