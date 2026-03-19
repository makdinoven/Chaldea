import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { ChatMessage as ChatMessageType } from '../../types/chat';
import { AVATAR_FRAMES } from '../../utils/avatarFrames';
import { hasPermission } from '../../utils/permissions';

interface ChatMessageProps {
  message: ChatMessageType;
  permissions: string[];
  onReply: (message: ChatMessageType) => void;
  onQuote: (message: ChatMessageType) => void;
  onDelete: (messageId: number) => void;
}

const formatTime = (dateStr: string): string => {
  try {
    const date = new Date(dateStr);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
  } catch {
    return '';
  }
};

const ChatMessage = ({
  message,
  permissions,
  onReply,
  onQuote,
  onDelete,
}: ChatMessageProps) => {
  const [showActions, setShowActions] = useState(false);

  const frame = message.avatar_frame
    ? AVATAR_FRAMES.find((f) => f.id === message.avatar_frame)
    : null;

  const canDelete = hasPermission(permissions, 'chat:delete');

  return (
    <div
      className="flex gap-3 px-3 py-2.5 group hover:bg-white/[0.03] transition-colors duration-200 ease-site relative"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Avatar — square with frame, clickable to profile */}
      <Link to={`/user-profile/${message.user_id}`} className="cursor-pointer flex-shrink-0">
        <div
          className="w-[66px] h-[66px] rounded-[10px] overflow-hidden bg-white/10"
          style={{
            border: frame?.borderStyle ?? '2px solid rgba(255,255,255,0.15)',
            boxShadow: frame?.shadow ?? 'none',
          }}
        >
          {message.avatar ? (
            <img
              src={message.avatar}
              alt={message.username}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-white/40 text-2xl font-medium">
              {message.username.charAt(0).toUpperCase()}
            </div>
          )}
        </div>
      </Link>

      {/* Message bubble */}
      <div className="flex-1 min-w-0">
        {/* Username + time */}
        <div className="flex items-baseline gap-2 mb-1">
          <Link to={`/user-profile/${message.user_id}`} className="gold-text text-sm font-medium truncate hover:underline cursor-pointer">
            {message.username}
          </Link>
          <span className="text-white/30 text-xs flex-shrink-0">
            {formatTime(message.created_at)}
          </span>
        </div>

        {/* Content block — dark bubble that wraps the message */}
        <div className="bg-white/[0.06] border border-white/[0.08] rounded-lg rounded-tl-none px-3 py-2 inline-block max-w-full">
          {/* Reply block */}
          {message.reply_to && (
            <div className="mb-1.5 pl-2 border-l-2 border-site-blue/40 bg-white/[0.06] rounded-r py-1 px-2">
              <span className="text-site-blue text-xs font-medium">
                {message.reply_to.username}
              </span>
              <p className="text-white/50 text-xs truncate">
                {message.reply_to.content}
              </p>
            </div>
          )}

          {message.reply_to_id && !message.reply_to && (
            <div className="mb-1.5 pl-2 border-l-2 border-white/20 bg-white/[0.06] rounded-r py-1 px-2">
              <p className="text-white/30 text-xs italic">Сообщение удалено</p>
            </div>
          )}

          <p className="text-white text-sm break-words whitespace-pre-wrap">
            {message.content}
          </p>
        </div>
      </div>

      {/* Hover actions */}
      {showActions && (
        <div className="absolute right-2 top-1 flex gap-1 bg-site-bg/95 rounded-card px-1.5 py-0.5 shadow-dropdown border border-white/10">
          <button
            onClick={() => onReply(message)}
            className="text-white/50 hover:text-site-blue text-xs px-1.5 py-0.5 transition-colors duration-200 ease-site cursor-pointer"
            title="Ответить"
          >
            Ответить
          </button>
          {canDelete && (
            <button
              onClick={() => onDelete(message.id)}
              className="text-white/50 hover:text-site-red text-xs px-1.5 py-0.5 transition-colors duration-200 ease-site cursor-pointer"
              title="Удалить"
            >
              Удалить
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default ChatMessage;
