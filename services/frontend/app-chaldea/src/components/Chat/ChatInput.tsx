import { useState, useCallback, useEffect } from 'react';
import type { ChatMessage, ChatChannel } from '../../types/chat';

interface ChatInputProps {
  activeChannel: ChatChannel;
  replyingTo: ChatMessage | null;
  isAuthenticated: boolean;
  isBanned: boolean;
  onSend: (content: string, replyToId: number | null) => void;
  onCancelReply: () => void;
  quoteText: string | null;
  onClearQuote: () => void;
}

const ChatInput = ({
  activeChannel,
  replyingTo,
  isAuthenticated,
  isBanned,
  onSend,
  onCancelReply,
  quoteText,
  onClearQuote,
}: ChatInputProps) => {
  const [text, setText] = useState('');

  // When quote text arrives, place it in the input
  useEffect(() => {
    if (quoteText !== null) {
      setText(quoteText);
      onClearQuote();
    }
  }, [quoteText, onClearQuote]);

  const handleSubmit = useCallback(() => {
    const content = text.trim();
    if (!content) return;
    onSend(content, replyingTo?.id ?? null);
    setText('');
  }, [text, replyingTo, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  // Unauthenticated state
  if (!isAuthenticated) {
    return (
      <div className="px-3 py-3 border-b border-white/10">
        <div className="text-white/40 text-sm text-center py-2">
          Войдите, чтобы писать
        </div>
      </div>
    );
  }

  // Banned state
  if (isBanned) {
    return (
      <div className="px-3 py-3 border-b border-white/10">
        <div className="text-site-red text-sm text-center py-2">
          Вы заблокированы в чате
        </div>
      </div>
    );
  }

  return (
    <div className="px-3 py-2 border-b border-white/10">
      {/* Reply preview */}
      {replyingTo && (
        <div className="flex items-center gap-2 mb-2 pl-2 border-l-2 border-site-blue/40 bg-white/5 rounded-r py-1 px-2">
          <div className="flex-1 min-w-0">
            <span className="text-site-blue text-xs font-medium">
              {replyingTo.username}
            </span>
            <p className="text-white/50 text-xs truncate">
              {replyingTo.content}
            </p>
          </div>
          <button
            onClick={onCancelReply}
            className="text-white/40 hover:text-white text-xs flex-shrink-0 cursor-pointer transition-colors duration-200 ease-site"
            aria-label="Отменить ответ"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              className="w-3.5 h-3.5"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {/* Textarea */}
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={`Сообщение в #${activeChannel === 'general' ? 'общий' : activeChannel === 'trade' ? 'торговля' : 'помощь'}...`}
        maxLength={500}
        rows={3}
        className="input-underline w-full text-sm !py-2 resize-none gold-scrollbar"
      />

      {/* Bottom row: emoji stub + send */}
      <div className="flex items-center justify-between mt-2">
        {/* Emoji stub */}
        <button
          disabled
          className="text-white/20 cursor-not-allowed"
          title="Скоро"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-5 h-5"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M8 14s1.5 2 4 2 4-2 4-2" />
            <line x1="9" y1="9" x2="9.01" y2="9" />
            <line x1="15" y1="9" x2="15.01" y2="9" />
          </svg>
        </button>

        {/* Send button */}
        <button
          onClick={handleSubmit}
          disabled={!text.trim()}
          className="btn-blue !px-3 !py-1.5 !text-sm disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Отправить
        </button>
      </div>
    </div>
  );
};

export default ChatInput;
