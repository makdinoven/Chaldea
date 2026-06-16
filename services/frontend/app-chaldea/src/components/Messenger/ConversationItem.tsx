import type { ConversationListItem } from '../../types/messenger';
import { useAppSelector } from '../../redux/store';
import AvatarWithFrame from '../common/AvatarWithFrame';

interface ConversationItemProps {
  conversation: ConversationListItem;
  isActive: boolean;
  onClick: (id: number) => void;
  onTogglePin: (id: number, pinned: boolean) => void;
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

const PinIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
    <path d="M16 3v2l-1 1v4l3 3v2h-5v5l-1 1-1-1v-5H5v-2l3-3V6L7 5V3h9z" />
  </svg>
);

const ConversationItem = ({ conversation, isActive, onClick, onTogglePin }: ConversationItemProps) => {
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
  const frameSlug = participant?.avatar_frame ?? null;

  const lastMessageTime = conversation.last_message?.created_at;
  const lastMessagePreview = conversation.last_message?.content ?? '';

  return (
    <div className={`relative group ${isActive ? 'bg-white/[0.08]' : 'hover:bg-white/[0.04]'}`}>
      <button
        onClick={() => onClick(conversation.id)}
        className={`w-full flex items-center gap-3 pl-3 pr-9 py-3 text-left transition-colors duration-200 ease-site cursor-pointer border-l-2 ${
          isActive ? 'border-gold' : 'border-transparent'
        }`}
      >
        {/* Avatar */}
        <AvatarWithFrame
          avatarUrl={avatarUrl}
          frameSlug={frameSlug}
          pixelSize={44}
          rounded="full"
          username={displayName}
        />

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1 min-w-0">
              {conversation.is_pinned && (
                <PinIcon className="w-3 h-3 text-gold flex-shrink-0" />
              )}
              <span className="text-white text-sm font-medium truncate">
                {displayName}
              </span>
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

      {/* Pin toggle — appears on hover; stays highlighted when pinned */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onTogglePin(conversation.id, !conversation.is_pinned);
        }}
        className={`absolute top-1 right-1 p-1 rounded transition-opacity duration-200 ease-site cursor-pointer ${
          conversation.is_pinned
            ? 'opacity-0 group-hover:opacity-100 text-gold hover:text-gold-light'
            : 'opacity-0 group-hover:opacity-100 text-white/40 hover:text-gold'
        }`}
        title={conversation.is_pinned ? 'Открепить' : 'Закрепить'}
        aria-label={conversation.is_pinned ? 'Открепить диалог' : 'Закрепить диалог'}
      >
        <PinIcon className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};

export default ConversationItem;
