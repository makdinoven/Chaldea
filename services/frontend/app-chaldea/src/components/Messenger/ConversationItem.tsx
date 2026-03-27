import type { ConversationListItem } from '../../types/messenger';
import { AVATAR_FRAMES } from '../../utils/avatarFrames';
import { useAppSelector } from '../../redux/store';

interface ConversationItemProps {
  conversation: ConversationListItem;
  isActive: boolean;
  onClick: (id: number) => void;
}

const formatRelativeTime = (dateStr: string): string => {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffMin < 1) return 'сейчас';
    if (diffMin < 60) return `${diffMin} мин`;
    if (diffHr < 24) return `${diffHr} ч`;
    if (diffDay < 7) return `${diffDay} д`;

    return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
  } catch {
    return '';
  }
};

const ConversationItem = ({ conversation, isActive, onClick }: ConversationItemProps) => {
  const currentUserId = useAppSelector((state) => state.user.id) as number | null;

  const participant =
    conversation.type === 'direct' && currentUserId
      ? conversation.participants.find((p) => p.user_id !== currentUserId) ??
        conversation.participants[0]
      : conversation.participants[0];

  const displayName =
    conversation.type === 'group' && conversation.title
      ? conversation.title
      : participant?.username ?? 'Неизвестный';

  const avatarUrl = participant?.avatar ?? null;
  const avatarFrame = participant?.avatar_frame
    ? AVATAR_FRAMES.find((f) => f.id === participant.avatar_frame)
    : null;

  const lastMessageTime = conversation.last_message?.created_at;
  const lastMessagePreview = conversation.last_message?.content ?? '';

  return (
    <button
      onClick={() => onClick(conversation.id)}
      className={`w-full flex items-center gap-3 px-3 py-3 text-left transition-colors duration-200 ease-site cursor-pointer ${
        isActive
          ? 'bg-white/[0.08] border-l-2 border-gold'
          : 'hover:bg-white/[0.04] border-l-2 border-transparent'
      }`}
    >
      {/* Avatar */}
      <div
        className="w-11 h-11 rounded-full overflow-hidden bg-white/10 flex-shrink-0"
        style={{
          border: avatarFrame?.borderStyle ?? '2px solid rgba(255,255,255,0.15)',
          boxShadow: avatarFrame?.shadow ?? 'none',
        }}
      >
        {avatarUrl ? (
          <img
            src={avatarUrl}
            alt={displayName}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-white/40 text-base font-medium">
            {conversation.type === 'group' ? (
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            ) : (
              displayName.charAt(0).toUpperCase()
            )}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-white text-sm font-medium truncate">
            {displayName}
          </span>
          {lastMessageTime && (
            <span className="text-white/30 text-xs flex-shrink-0">
              {formatRelativeTime(lastMessageTime)}
            </span>
          )}
        </div>
        {lastMessagePreview && (
          <p className="text-white/40 text-xs truncate mt-0.5">
            {conversation.last_message?.sender_username && (
              <span className="text-white/50">
                {conversation.last_message.sender_username}:{' '}
              </span>
            )}
            {lastMessagePreview}
          </p>
        )}
      </div>

      {/* Unread badge */}
      {conversation.unread_count > 0 && (
        <span className="bg-site-red text-white text-xs font-bold rounded-full min-w-[20px] h-5 flex items-center justify-center px-1.5 flex-shrink-0">
          {conversation.unread_count > 99 ? '99+' : conversation.unread_count}
        </span>
      )}
    </button>
  );
};

export default ConversationItem;
