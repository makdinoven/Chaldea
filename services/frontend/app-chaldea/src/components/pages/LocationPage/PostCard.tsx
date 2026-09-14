import { useState, useRef, useEffect } from 'react';
import { Post, Player } from './types';
import PlayerActionsMenu from './PlayerActionsMenu';
import useNpcAttack from '../../../hooks/useNpcAttack';
import ArchiveLinkPreview from '../../CommonComponents/ArchiveLinkPreview/ArchiveLinkPreview';
import { formatRelativeTime, parseServerDate, serverDateMs } from '../../../utils/serverDate';
import { sanitizePostHtml } from '../../../utils/sanitizePostHtml';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';

interface PostCardProps {
  post: Post;
  currentCharacterId: number | null;
  currentCharacterLevel?: number;
  currentUserId: number | null;
  players: Player[];
  locationId: number;
  locationMarkerType?: string;
  isCharacterHere?: boolean;
  onLike: (postId: number) => void;
  onUnlike: (postId: number) => void;
  onTagPlayer: (targetUserId: number) => void;
  onReport: (postId: number, reason: string) => void;
  onRequestDeletion: (postId: number, reason: string) => void;
  /**
   * FEAT-159: this post is the newest one in the location (index 0 of the
   * `id DESC` feed). One of the two owner-path conditions for editing.
   */
  isLatestPostInLocation?: boolean;
  /** Current user's role — only the literal `admin` may edit someone else's post. */
  currentUserRole?: string | null;
  /** Opens the edit modal. Absent -> the «Редактировать» entry is never shown. */
  onEdit?: (post: Post) => void;
  /**
   * FEAT-160: opens the version-history modal. Absent -> the «История правок»
   * entry is never shown.
   */
  onShowHistory?: (post: Post) => void;
}


/**
 * FEAT-159: the edit window is one hour from PUBLICATION.
 *
 * `posts.created_at` is a naive MySQL `TIMESTAMP` written by the server's own
 * `NOW()` and serialised without an offset, so it must be read as UTC — letting
 * `new Date()` interpret it as *local* time would shift the window by the
 * viewer's offset and hide the button from everyone east of UTC. FEAT-161 moved
 * that reading into the shared `utils/serverDate` helper; the local copy is gone.
 *
 * This is only a convenience check: the server re-decides both limits at save
 * time (section 3.4), and a stale client state degrades into a visible Russian
 * error in the modal, never into a silent no-op.
 */
const EDIT_WINDOW_MS = 60 * 60 * 1000;

const isWithinEditWindow = (createdAt: string): boolean => {
  // `serverDateMs` yields 0 for an absent/unparseable value, i.e. "older than
  // anything" — which closes the window, exactly as the previous NaN guard did.
  const ts = serverDateMs(createdAt);
  if (!ts) return false;
  return Date.now() - ts < EDIT_WINDOW_MS;
};

/** Exact moment of the edit for the marker's `title`. */
const formatExactTime = (dateStr: string): string => {
  const date = parseServerDate(dateStr);
  if (!date) return dateStr;
  return date.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getRarityColorClass = (rarity?: string | null): string => {
  switch (rarity) {
    case 'common': return 'text-rarity-common';
    case 'rare': return 'text-rarity-rare';
    case 'epic': return 'text-rarity-epic';
    case 'mythical': return 'text-rarity-mythical';
    case 'legendary': return 'text-rarity-legendary';
    default: return 'text-rarity-common';
  }
};

// FEAT-152: intent-gate badges are colored per action type (mock language).
const GATE_BADGE_META: Record<string, { icon: string; label: string; cls: string }> = {
  combat: { icon: '⚔', label: 'Нападение на мобов', cls: 'border-stat-hp/40 bg-stat-hp/10 text-stat-hp' },
  npc_dialogue: { icon: '💬', label: 'Диалог с НПС', cls: 'border-site-blue/40 bg-site-blue/10 text-site-blue' },
  gathering: { icon: '⛏', label: 'Сбор', cls: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy' },
  dungeon: { icon: '🏰', label: 'Вход в подземелье', cls: 'border-rarity-epic/40 bg-rarity-epic/10 text-rarity-epic' },
  pvp: { icon: '⚔', label: 'PvP', cls: 'border-gold/20 bg-gold/10 text-gold/90' },
};

const NpcPostAttackButton = ({ npcId, npcName, currentCharacterId }: { npcId: number; npcName: string; currentCharacterId: number }) => {
  const { attacking, handleAttack } = useNpcAttack({
    npcId,
    npcName,
    currentCharacterId,
  });

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        handleAttack();
      }}
      disabled={attacking}
      className="
        text-site-red text-[10px] sm:text-xs font-medium uppercase tracking-wide
        hover:text-white transition-colors duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
        flex items-center gap-1
      "
    >
      {attacking ? (
        <div className="w-3 h-3 border-2 border-site-red/30 border-t-site-red rounded-full animate-spin" />
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      )}
      {attacking ? 'Атака...' : 'Напасть'}
    </button>
  );
};

const PostCard = ({
  post,
  currentCharacterId,
  currentCharacterLevel = 0,
  currentUserId,
  players,
  locationId,
  locationMarkerType = 'safe',
  isCharacterHere = false,
  onLike,
  onUnlike,
  onTagPlayer,
  onReport,
  onRequestDeletion,
  isLatestPostInLocation = false,
  currentUserRole = null,
  onEdit,
  onShowHistory,
}: PostCardProps) => {
  const permissions = useAppSelector(selectPermissions);
  const isLiked = currentCharacterId !== null && post.liked_by.includes(currentCharacterId);
  const [animating, setAnimating] = useState(false);
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [modalType, setModalType] = useState<'report' | 'deletion' | null>(null);
  const [modalReason, setModalReason] = useState('');
  const [modalSubmitting, setModalSubmitting] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const isAuthor = currentCharacterId !== null && post.character_id === currentCharacterId;
  // System / NPC-authored posts have no user account behind them.
  const isNpcPost = !post.user_id;

  // FEAT-159: «Редактировать» is offered to the author while the post is the
  // location's newest and still inside the hour, and to role `admin` always
  // (moderators are NOT admins here — the server answers them 403).
  const canEdit =
    !!onEdit &&
    (currentUserRole === 'admin' ||
      (isAuthor && isLatestPostInLocation && isWithinEditWindow(post.created_at)));

  /**
   * FEAT-160: «История правок» is gated on the `posts:history` PERMISSION, never
   * on `role === 'admin'`.
   *
   * That permission is deliberately granted to no role (user-service migration
   * 0029): admins hold it implicitly through `get_effective_permissions`,
   * moderators do not, and it can be handed to one named person through
   * `user_permissions` **without a deploy**. A role check would quietly break
   * that delegation — the entry would stay hidden for someone the server would
   * happily answer 200. The server guards the endpoint with the same
   * permission, so the two can never disagree.
   *
   * There is nothing to show for a post that was never edited, hence
   * `post.edited_at`.
   */
  const canViewHistory =
    !!onShowHistory && !!post.edited_at && hasPermission(permissions, 'posts:history');

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

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpen]);

  const openModal = (type: 'report' | 'deletion') => {
    setModalType(type);
    setModalReason('');
    setMenuOpen(false);
  };

  const closeModal = () => {
    setModalType(null);
    setModalReason('');
    setModalSubmitting(false);
  };

  const handleModalSubmit = async () => {
    if (!modalType) return;
    setModalSubmitting(true);
    try {
      if (modalType === 'report') {
        await onReport(post.post_id, modalReason);
      } else {
        await onRequestDeletion(post.post_id, modalReason);
      }
      closeModal();
    } catch {
      setModalSubmitting(false);
    }
  };

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
    <article
      className={`bg-site-bg backdrop-blur-sm rounded-card border transition-colors duration-200 ease-site p-4 sm:p-5 flex flex-col gap-3.5 ${
        isNpcPost
          ? 'border-gold-dark/25 hover:border-gold-dark/40'
          : 'border-white/[0.07] hover:border-gold-dark/30'
      }`}
    >
      {/* Header: avatar + author info + actions */}
      <div className="flex items-start gap-3 sm:gap-3.5">
        {/* Avatar */}
        <div className="gold-outline relative w-12 h-12 sm:w-[52px] sm:h-[52px] rounded-full overflow-hidden bg-black/40 shrink-0">
          {post.character_photo ? (
            <img
              src={post.character_photo}
              alt={post.character_name}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-white/20">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6 sm:w-7 sm:h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
          )}
        </div>

        {/* Author info */}
        <div className="flex flex-col gap-0.5 min-w-0 flex-1">
          {/* Title above the name (rarity-colored) */}
          {post.character_title && (
            <span className={`${getRarityColorClass(post.character_title_rarity)} text-[10px] sm:text-[10.5px] font-medium tracking-[0.04em] truncate`}>
              {post.character_title}
            </span>
          )}
          <div className="flex items-center gap-2 sm:gap-2.5 flex-wrap min-w-0">
            <span className="text-white text-sm sm:text-[15px] font-medium truncate max-w-full">
              {post.character_name}
            </span>
            <span className="bg-gold/15 text-gold text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0">
              LVL {post.character_level ?? '?'}
            </span>
            {isNpcPost && (
              <span className="bg-white/10 text-white/60 text-[9px] font-bold uppercase tracking-[0.06em] px-2 py-0.5 rounded-full shrink-0">
                НПС
              </span>
            )}
            <span className="text-white/40 text-[11px] shrink-0">
              {formatRelativeTime(post.created_at)}
            </span>
            {/* FEAT-159: an edit must be visible — a line may have been quoted
                before it was changed. The exact moment lives in the tooltip. */}
            {post.edited_at && (
              <span
                className="text-white/35 text-[11px] italic shrink-0"
                title={`Отредактировано: ${formatExactTime(post.edited_at)}`}
              >
                · {post.edited_by_admin ? 'изменено администратором' : 'изменено'}
              </span>
            )}
          </div>
        </div>

        {/* Header actions: NPC attack / player actions menu + kebab */}
        <div className="flex items-center gap-2 shrink-0">
          {currentCharacterId !== null && isNpcPost && isCharacterHere && (
            <NpcPostAttackButton
              npcId={post.character_id}
              npcName={post.character_name}
              currentCharacterId={currentCharacterId}
            />
          )}
          {currentCharacterId !== null && currentUserId !== null && !!post.user_id && post.user_id !== currentUserId && (
            <PlayerActionsMenu
              targetCharacterId={post.character_id}
              targetUserId={post.user_id as number}
              targetName={post.character_name}
              targetLevel={post.character_level ?? 1}
              currentCharacterId={currentCharacterId}
              currentCharacterLevel={currentCharacterLevel}
              locationId={locationId}
              locationMarkerType={locationMarkerType}
              isCharacterHere={isCharacterHere}
            />
          )}

          {/* Post actions menu (report / request deletion) */}
          {currentCharacterId !== null && (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen((prev) => !prev)}
                className="w-8 h-8 flex items-center justify-center rounded-[8px] text-white/35 hover:text-white transition-colors duration-200"
                aria-label="Действия с постом"
                title="Действия с постом"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="5" r="1.6" />
                  <circle cx="12" cy="12" r="1.6" />
                  <circle cx="12" cy="19" r="1.6" />
                </svg>
              </button>

              {menuOpen && (
                <div className="absolute top-full right-0 mt-2 w-48 bg-black/90 border border-white/10 rounded-card shadow-card z-20">
                  <div className="py-1">
                    <button
                      onClick={() => openModal('report')}
                      className="w-full flex items-center gap-2 px-3 py-2 text-white/70 hover:bg-white/10 hover:text-white transition-colors text-left text-xs"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-site-red/70 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2z" />
                      </svg>
                      Пожаловаться
                    </button>
                    {canEdit && (
                      <button
                        onClick={() => {
                          setMenuOpen(false);
                          onEdit?.(post);
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-white/70 hover:bg-white/10 hover:text-white transition-colors text-left text-xs"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-site-blue/70 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                        Редактировать
                      </button>
                    )}
                    {canViewHistory && (
                      <button
                        onClick={() => {
                          setMenuOpen(false);
                          onShowHistory?.(post);
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-white/70 hover:bg-white/10 hover:text-white transition-colors text-left text-xs"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-gold/70 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        История правок
                      </button>
                    )}
                    {isAuthor && (
                      <button
                        onClick={() => openModal('deletion')}
                        className="w-full flex items-center gap-2 px-3 py-2 text-white/70 hover:bg-white/10 hover:text-white transition-colors text-left text-xs"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-site-red/70 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                        Запросить удаление
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Content — RP body styling per mock: gold quotes. Bold/italic carry no colour
          of their own (FEAT-157): they inherit the post colour unless the author
          coloured them, so a player-chosen colour is never overridden. */}
      <ArchiveLinkPreview>
        <div
          className="text-white/[0.88] text-sm sm:text-[14.5px] leading-relaxed whitespace-pre-wrap break-words prose-rules
            [&_blockquote]:border-l-2 [&_blockquote]:border-gold/50 [&_blockquote]:pl-3.5 [&_blockquote]:my-2 [&_blockquote]:italic [&_blockquote]:text-white/75
            [&_em]:italic"
          dangerouslySetInnerHTML={{
            // Player-written HTML. `sanitizePostHtml` is the project-wide post
            // policy (allow-list of the editor's own tags/attributes/CSS
            // properties) — never inline a DOMPurify config here instead.
            __html: sanitizePostHtml(post.content),
          }}
        />
      </ArchiveLinkPreview>

      {/* FEAT-145 item 7: intent-gate marks declared in this post.
          FEAT-159 (T12): gates added during an edit sit in `pending_gates` until
          a moderator rules on them. They are rendered in the same row but must
          read as *not yet granted* — dashed outline, hourglass, «на
          рассмотрении» — because they unlock nothing until approval. */}
      {((post.gates && Object.keys(post.gates).length > 0) ||
        (post.pending_gates && Object.keys(post.pending_gates).length > 0)) && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(post.gates ?? {}).map(([at, count]) => {
            const m = GATE_BADGE_META[at] ?? { icon: '•', label: at, cls: 'border-gold/20 bg-gold/10 text-gold/90' };
            return (
              <span
                key={at}
                className={`flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full border ${m.cls}`}
              >
                {m.icon} {m.label}
                {(count as number) > 1 ? ` ×${count}` : ''}
              </span>
            );
          })}
          {Object.entries(post.pending_gates ?? {}).map(([at, count]) => {
            const m = GATE_BADGE_META[at] ?? { icon: '•', label: at, cls: '' };
            return (
              <span
                key={`pending-${at}`}
                title="Намерение добавлено при редактировании и ждёт решения администратора — действие пока недоступно"
                className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full
                           border border-dashed border-gold/40 bg-gold/[0.06] text-gold/80 break-words"
              >
                <span aria-hidden="true">⏳</span>
                {m.icon} {m.label}
                {(count as number) > 1 ? ` ×${count}` : ''}
                <span className="text-white/45">· на рассмотрении</span>
              </span>
            );
          })}
        </div>
      )}

      {/* Footer: like + tag + length counter */}
      <div className="flex items-center gap-4 pt-3 border-t border-white/[0.06]">
        {/* Like button */}
        <button
          onClick={handleLikeClick}
          className="flex items-center gap-1.5 text-sm transition-colors hover:text-site-red group"
          aria-label={isLiked ? 'Убрать лайк' : 'Поставить лайк'}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className={`w-[18px] h-[18px] transition-transform ${animating ? 'scale-125' : 'scale-100'} ${
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
          <span className={`font-medium ${isLiked ? 'text-site-red' : 'text-white/40 group-hover:text-site-red/70'}`}>
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
              <div className="absolute bottom-full left-0 mb-2 w-52 sm:w-60 bg-black/90 border border-white/10 rounded-card shadow-card z-20 max-h-48 overflow-y-auto gold-scrollbar">
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

        {/* Char length counter — the number a player uses to judge whether the
            post pays for its intent gates, so it MUST equal what the server
            counts. `post.length` now IS that figure: the backend builds it with
            `crud.strip_html_tags`, the same helper behind post XP and the gate
            budgets, so the count lives in exactly one place. */}
        <span className="ml-auto text-white/30 text-[11px] shrink-0">
          {post.length} симв.
        </span>
      </div>

      {/* Report / Deletion request modal */}
      {modalType && (
        <div className="modal-overlay" onClick={closeModal}>
          <div
            className="modal-content max-w-md w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="gold-text text-base font-medium mb-3">
              {modalType === 'report' ? 'Пожаловаться на пост' : 'Запрос на удаление поста'}
            </h3>

            <p className="text-white/50 text-xs mb-3 line-clamp-2">
              {post.content}
            </p>

            <textarea
              value={modalReason}
              onChange={(e) => setModalReason(e.target.value)}
              placeholder="Причина (необязательно)"
              className="w-full bg-black/40 border border-white/10 rounded-card text-white text-sm p-3 resize-none h-20 focus:outline-none focus:border-site-blue/50 placeholder:text-white/30"
            />

            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={closeModal}
                className="btn-line text-xs px-4 py-1.5"
              >
                Отмена
              </button>
              <button
                onClick={handleModalSubmit}
                disabled={modalSubmitting}
                className="btn-blue text-xs px-4 py-1.5 disabled:opacity-50"
              >
                {modalSubmitting
                  ? 'Отправка...'
                  : modalType === 'report'
                    ? 'Отправить жалобу'
                    : 'Отправить запрос'}
              </button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
};

export default PostCard;
