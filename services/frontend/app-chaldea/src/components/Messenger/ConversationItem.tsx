import type { ConversationListItem } from '../../types/messenger';
import { useAppSelector } from '../../redux/store';
import AvatarWithFrame from '../common/AvatarWithFrame';

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
  const frameSlug = participant?.avatar_frame ?? null;

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
