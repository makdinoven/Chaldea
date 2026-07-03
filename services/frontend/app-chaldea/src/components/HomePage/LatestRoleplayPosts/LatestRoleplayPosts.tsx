import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DOMPurify from 'dompurify';
import {
  getLatestRoleplayPosts,
  type LatestRoleplayPost,
} from '../../../api/api';

/** How many recent posts to surface, and how often to silently refresh. */
const POSTS_LIMIT = 5;
const REFRESH_INTERVAL_MS = 30_000;

const formatRelativeTime = (dateStr: string): string => {
  try {
    const date = new Date(dateStr);
    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMin < 1) return 'только что';
    if (diffMin < 60) return `${diffMin} мин. назад`;
    if (diffHours < 24) return `${diffHours} ч. назад`;
    if (diffDays < 7) return `${diffDays} дн. назад`;

    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'short',
      year: diffDays > 365 ? 'numeric' : undefined,
    });
  } catch {
    return dateStr;
  }
};

const getRarityColorClass = (rarity?: string | null): string => {
  switch (rarity) {
    case 'rare':
      return 'text-rarity-rare';
    case 'legendary':
      return 'text-rarity-legendary';
    default:
      return 'text-rarity-common';
  }
};

/** Sanitize post HTML down to plain text for a compact feed preview. */
const toPlainPreview = (html: string): string =>
  DOMPurify.sanitize(html, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] })
    .replace(/\s+/g, ' ')
    .trim();

interface CardProps {
  post: LatestRoleplayPost;
  onOpen: (locationId: number) => void;
}

const RoleplayPostCard = ({ post, onOpen }: CardProps) => {
  const preview = toPlainPreview(post.content);

  return (
    <button
      type="button"
      onClick={() => onOpen(post.location_id)}
      className="
        w-full text-left bg-black/60 hover:bg-black/70 rounded-card
        p-3 sm:p-4 flex gap-3 sm:gap-4 transition-colors
        hover-gold-overlay focus:outline-none focus:ring-1 focus:ring-gold/50
      "
    >
      {/* Left: avatar panel */}
      <div className="flex flex-col items-center gap-1 shrink-0 w-[60px] sm:w-[72px]">
        {post.character_title ? (
          <span
            className={`${getRarityColorClass(
              post.character_title_rarity,
            )} text-[9px] sm:text-[10px] text-center leading-tight w-full line-clamp-1`}
          >
            {post.character_title}
          </span>
        ) : (
          <span className="text-[9px] sm:text-[10px] text-transparent select-none">
            &nbsp;
          </span>
        )}

        <div className="gold-outline relative w-11 h-11 sm:w-14 sm:h-14 rounded-full overflow-hidden bg-black/40">
          {post.character_photo ? (
            <img
              src={post.character_photo}
              alt={post.character_name ?? ''}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-white/20">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                />
              </svg>
            </div>
          )}
        </div>

        <span className="text-white text-[10px] sm:text-xs font-medium text-center truncate w-full">
          {post.character_name}
        </span>
        <span className="gold-text text-[9px] sm:text-[10px] font-medium">
          LVL {post.character_level ?? '?'}
        </span>
      </div>

      {/* Right: location plate + preview + meta */}
      <div className="flex flex-col gap-1.5 flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1 text-site-blue text-[11px] sm:text-xs font-medium min-w-0">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-3 h-3 shrink-0"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M17.657 16.657L13.414 20.9a2 2 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
              />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span className="truncate">{post.location_name}</span>
          </span>
          <span className="text-white/40 text-[10px] sm:text-xs shrink-0">
            {formatRelativeTime(post.created_at)}
          </span>
        </div>

        <p className="text-white/80 text-xs sm:text-sm leading-relaxed line-clamp-3 break-words">
          {preview || <span className="italic text-white/40">(без текста)</span>}
        </p>

        <div className="flex items-center gap-1 text-white/40 text-[10px] sm:text-xs mt-auto">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-3.5 h-3.5"
            viewBox="0 0 24 24"
            fill="currentColor"
          >
            <path d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
          </svg>
          <span>{post.likes_count}</span>
        </div>
      </div>
    </button>
  );
};

const LatestRoleplayPosts = () => {
  const navigate = useNavigate();
  const [posts, setPosts] = useState<LatestRoleplayPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  const load = useCallback(async (initial: boolean) => {
    if (initial) setLoading(true);
    try {
      const data = await getLatestRoleplayPosts(POSTS_LIMIT);
      if (!isMounted.current) return;
      setPosts(data);
      setError(null);
    } catch {
      if (!isMounted.current) return;
      // Only surface the error if we have nothing to show; a failed silent
      // refresh shouldn't wipe the posts already on screen.
      setError('Не удалось загрузить последние посты');
    } finally {
      if (isMounted.current && initial) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(true);
    const interval = setInterval(() => load(false), REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  const handleOpen = (locationId: number) => {
    navigate(`/location/${locationId}`);
  };

  return (
    <section className="w-full">
      <div className="flex items-center justify-between mb-3 sm:mb-4">
        <h2 className="gold-text text-base sm:text-lg font-semibold">
          Последние ролевые посты
        </h2>
        <span className="flex items-center gap-1.5 text-white/40 text-[10px] sm:text-xs">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          Онлайн-лента
        </span>
      </div>

      {loading ? (
        <div className="flex flex-col gap-2 sm:gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="bg-black/40 rounded-card h-20 sm:h-24 animate-pulse"
            />
          ))}
        </div>
      ) : error && posts.length === 0 ? (
        <div className="bg-black/50 rounded-card p-4 text-center">
          <p className="text-site-red text-sm mb-3">{error}</p>
          <button
            type="button"
            onClick={() => load(true)}
            className="btn-line text-xs px-4 py-1.5"
          >
            Повторить
          </button>
        </div>
      ) : posts.length === 0 ? (
        <div className="bg-black/40 rounded-card p-6 text-center text-white/50 text-sm">
          Пока никто ничего не написал. Будь первым!
        </div>
      ) : (
        <div className="flex flex-col gap-2 sm:gap-3">
          {posts.map((post) => (
            <RoleplayPostCard
              key={post.post_id}
              post={post}
              onOpen={handleOpen}
            />
          ))}
        </div>
      )}
    </section>
  );
};

export default LatestRoleplayPosts;
