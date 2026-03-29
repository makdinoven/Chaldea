import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import type { PrivateMessage } from '../../types/messenger';
import AvatarWithFrame from '../common/AvatarWithFrame';

interface MessageBubbleProps {
  message: PrivateMessage;
  isOwn: boolean;
  onDelete: (messageId: number) => void;
  onReply: (message: PrivateMessage) => void;
  onEdit: (message: PrivateMessage) => void;
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

const truncate = (text: string, maxLen: number): string => {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
};

const MessageBubble = ({ message, isOwn, onDelete, onReply, onEdit }: MessageBubbleProps) => {
  const [showActions, setShowActions] = useState(false);
  const actionBarRef = useRef<HTMLDivElement>(null);
  const bubbleRef = useRef<HTMLDivElement>(null);

  // Close action bar on outside click
  useEffect(() => {
    if (!showActions) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        bubbleRef.current &&
        !bubbleRef.current.contains(e.target as Node)
      ) {
        setShowActions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showActions]);

  if (message.is_deleted) {
    return (
      <div className={`flex gap-3 px-3 py-2 ${isOwn ? 'flex-row-reverse' : ''}`}>
        <div className="w-9 h-9 flex-shrink-0" />
        <div className="bg-white/[0.04] border border-white/[0.06] rounded-lg px-3 py-2 inline-block max-w-[75%]">
          <p className="text-white/30 text-sm italic">
            Сообщение удалено
          </p>
        </div>
      </div>
    );
  }

  const handleBubbleClick = () => {
    setShowActions((prev) => !prev);
  };

  return (
    <div
      ref={bubbleRef}
      className={`flex gap-3 px-3 py-2 relative ${isOwn ? 'flex-row-reverse' : ''}`}
    >
      {/* Avatar */}
      <Link
        to={`/user-profile/${message.sender_id}`}
        className="cursor-pointer flex-shrink-0"
      >
        <AvatarWithFrame
          avatarUrl={message.sender_avatar}
          frameSlug={message.sender_avatar_frame}
          pixelSize={36}
          username={message.sender_username}
          rounded="full"
        />
      </Link>

      {/* Message content */}
      <div className={`flex flex-col max-w-[75%] ${isOwn ? 'items-end' : 'items-start'}`}>
        {/* Sender name + time */}
        <div className={`flex items-baseline gap-2 mb-1 ${isOwn ? 'flex-row-reverse' : ''}`}>
          <Link
            to={`/user-profile/${message.sender_id}`}
            className="gold-text text-xs font-medium truncate hover:underline cursor-pointer"
          >
            {message.sender_username}
          </Link>
          <span className="text-white/30 text-xs flex-shrink-0 flex items-baseline gap-1">
            {formatTime(message.created_at)}
            {message.edited_at && (
              <span className="text-white/25 text-[10px]" title="Сообщение отредактировано">
                (ред.)
              </span>
            )}
          </span>
        </div>

        {/* Reply preview */}
        {message.reply_to && (
          <div
            className={`mb-1 max-w-full rounded px-2 py-1 border-l-2 ${
              isOwn ? 'border-l-site-blue bg-site-blue/5' : 'border-l-gold bg-gold/5'
            }`}
          >
            {message.reply_to.is_deleted ? (
              <p className="text-white/30 text-xs italic">Сообщение удалено</p>
            ) : (
              <>
                <p className="text-white/50 text-xs font-medium truncate">
                  {message.reply_to.sender_username ?? 'Неизвестный'}
                </p>
                <p className="text-white/40 text-xs truncate">
                  {truncate(message.reply_to.content, 80)}
                </p>
              </>
            )}
          </div>
        )}

        {/* Bubble */}
        <div
          onClick={handleBubbleClick}
          className={`bg-white/[0.06] border border-white/[0.08] px-3 py-2 inline-block max-w-full cursor-pointer select-none ${
            isOwn
              ? 'rounded-lg rounded-tr-none bg-site-blue/10 border-site-blue/15'
              : 'rounded-lg rounded-tl-none'
          }`}
        >
          <p className="text-white text-sm break-words whitespace-pre-wrap">
            {message.content}
          </p>
        </div>

        {/* Action bar */}
        {showActions && (
          <div
            ref={actionBarRef}
            className={`mt-1 flex gap-0.5 bg-site-bg/95 rounded-lg px-1 py-0.5 shadow-dropdown border border-white/10 ${
              isOwn ? 'self-end' : 'self-start'
            }`}
          >
            <button
              onClick={() => { onReply(message); setShowActions(false); }}
              className="text-white/50 hover:text-site-blue text-xs px-2 py-1 transition-colors duration-200 ease-site cursor-pointer whitespace-nowrap"
            >
              Ответить
            </button>
            {isOwn && (
              <button
                onClick={() => { onEdit(message); setShowActions(false); }}
                className="text-white/50 hover:text-site-blue text-xs px-2 py-1 transition-colors duration-200 ease-site cursor-pointer whitespace-nowrap"
              >
                Редактировать
              </button>
            )}
            {isOwn && (
              <button
                onClick={() => { onDelete(message.id); setShowActions(false); }}
                className="text-white/50 hover:text-site-red text-xs px-2 py-1 transition-colors duration-200 ease-site cursor-pointer whitespace-nowrap"
              >
                Удалить
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
