import { useState } from 'react';
import { Post } from './types';

interface PostCardProps {
  post: Post;
  currentCharacterId: number | null;
  onLike: (postId: number) => void;
  onUnlike: (postId: number) => void;
}

const formatRelativeTime = (dateStr: string): string => {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
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

const PostCard = ({ post, currentCharacterId, onLike, onUnlike }: PostCardProps) => {
  const isLiked = currentCharacterId !== null && post.liked_by.includes(currentCharacterId);
  const [animating, setAnimating] = useState(false);

  const handleLikeClick = () => {
    setAnimating(true);
    setTimeout(() => setAnimating(false), 300);

    if (isLiked) {
      onUnlike(post.post_id);
    } else {
      onLike(post.post_id);
    }
  };

  return (
    <div className="bg-black/30 rounded-card p-3 sm:p-4 flex flex-col gap-3">
      {/* Top row: avatar + info + timestamp */}
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className="gold-outline relative w-10 h-10 rounded-full overflow-hidden bg-black/40 shrink-0">
          {post.character_photo ? (
            <img
              src={post.character_photo}
              alt={post.character_name}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-white/20">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
          )}
        </div>

        {/* Name + title */}
        <div className="flex flex-col flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white text-sm font-medium truncate">
              {post.character_name}
            </span>
          </div>
          {post.character_title && (
            <span className="text-site-blue text-xs italic truncate">
              {post.character_title}
            </span>
          )}
        </div>

        {/* Timestamp */}
        <span className="text-white/40 text-xs shrink-0">
          {formatRelativeTime(post.created_at)}
        </span>
      </div>

      {/* Content */}
      <p className="text-white/90 text-sm leading-relaxed whitespace-pre-wrap break-words">
        {post.content}
      </p>

      {/* Like button */}
      <div className="flex items-center gap-1.5">
        <button
          onClick={handleLikeClick}
          className="flex items-center gap-1.5 text-sm transition-colors hover:text-site-red group"
          aria-label={isLiked ? 'Убрать лайк' : 'Поставить лайк'}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className={`w-4 h-4 transition-transform ${animating ? 'scale-125' : 'scale-100'} ${
              isLiked ? 'text-site-red' : 'text-white/40 group-hover:text-site-red/70'
            }`}
            viewBox="0 0 24 24"
            fill={isLiked ? 'currentColor' : 'none'}
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
            />
          </svg>
          <span className={isLiked ? 'text-site-red' : 'text-white/40 group-hover:text-site-red/70'}>
            {post.likes_count}
          </span>
        </button>
      </div>
    </div>
  );
};

export default PostCard;
