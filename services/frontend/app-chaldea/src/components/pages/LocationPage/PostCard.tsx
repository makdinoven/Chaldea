import { useState, useRef, useEffect } from 'react';
import { Post, Player } from './types';

interface PostCardProps {
  post: Post;
  currentCharacterId: number | null;
  currentUserId: number | null;
  players: Player[];
  onLike: (postId: number) => void;
  onUnlike: (postId: number) => void;
  onTagPlayer: (targetUserId: number) => void;
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

const PostCard = ({
  post,
  currentCharacterId,
  currentUserId,
  players,
  onLike,
  onUnlike,
  onTagPlayer,
}: PostCardProps) => {
  const isLiked = currentCharacterId !== null && post.liked_by.includes(currentCharacterId);
  const [animating, setAnimating] = useState(false);
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Filter out the current user from players list (prevent self-tagging)
  const taggablePlayers = players.filter((p) => p.user_id !== currentUserId);

  // Close dropdown on outside click
  useEffect(() => {
    if (!tagDropdownOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setTagDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [tagDropdownOpen]);

  const handleLikeClick = () => {
    setAnimating(true);
    setTimeout(() => setAnimating(false), 300);

    if (isLiked) {
      onUnlike(post.post_id);
    } else {
      onLike(post.post_id);
    }
  };

  const handleTagSelect = (targetUserId: number) => {
    onTagPlayer(targetUserId);
    setTagDropdownOpen(false);
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

      {/* Actions row: like + tag */}
      <div className="flex items-center gap-3">
        {/* Like button */}
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

        {/* Tag player button — only show when user has a character */}
        {currentCharacterId !== null && (
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setTagDropdownOpen((prev) => !prev)}
              className="flex items-center gap-1.5 text-sm text-white/40 hover:text-gold transition-colors"
              aria-label="Уведомить игрока"
              title="Уведомить игрока"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-4 h-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                />
              </svg>
            </button>

            {/* Tag player dropdown */}
            {tagDropdownOpen && (
              <div className="absolute bottom-full left-0 mb-2 w-52 sm:w-60 bg-black/90 border border-white/10 rounded-card shadow-card z-20 max-h-48 overflow-y-auto">
                {taggablePlayers.length === 0 ? (
                  <p className="text-white/50 text-xs p-3">
                    Нет игроков для уведомления
                  </p>
                ) : (
                  <div className="py-1">
                    {taggablePlayers.map((player) => (
                      <button
                        key={player.id}
                        onClick={() => handleTagSelect(player.user_id)}
                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-white/10 transition-colors text-left"
                      >
                        <div className="w-7 h-7 rounded-full overflow-hidden bg-black/40 shrink-0 border border-gold-dark/30">
                          {player.avatar ? (
                            <img
                              src={player.avatar}
                              alt={player.name}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-white/20">
                              <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                              </svg>
                            </div>
                          )}
                        </div>
                        <span className="text-white text-xs truncate">{player.name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default PostCard;
