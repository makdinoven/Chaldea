import { useEffect, useRef, useCallback } from 'react';
import { ArrowLeft } from 'react-feather';
import type { ConversationListItem, PrivateMessage } from '../../types/messenger';
import MessageBubble from './MessageBubble';
import MessageInput from './MessageInput';

interface MessageAreaProps {
  conversation: ConversationListItem | null;
  messages: PrivateMessage[];
  currentUserId: number | null;
  isLoading: boolean;
  error: string | null;
  hasMoreMessages: boolean;
  sending: boolean;
  replyTo: PrivateMessage | null;
  editingMessage: PrivateMessage | null;
  quoteText: string | null;
  onSendMessage: (content: string) => void;
  onDeleteMessage: (messageId: number) => void;
  onLoadMore: () => void;
  onBack: () => void;
  onReply: (message: PrivateMessage) => void;
  onEdit: (message: PrivateMessage) => void;
  onClearReply: () => void;
  onClearEdit: () => void;
  onEditSubmit: (messageId: number, content: string) => void;
  onQuoteInserted: () => void;
}

const MessageArea = ({
  conversation,
  messages,
  currentUserId,
  isLoading,
  error,
  hasMoreMessages,
  sending,
  replyTo,
  editingMessage,
  quoteText,
  onSendMessage,
  onDeleteMessage,
  onLoadMore,
  onBack,
  onReply,
  onEdit,
  onClearReply,
  onClearEdit,
  onEditSubmit,
  onQuoteInserted,
}: MessageAreaProps) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(0);

  // Scroll chat container to bottom when conversation changes
  useEffect(() => {
    if (conversation?.id != null) {
      prevMessageCountRef.current = 0;
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView();
      }, 50);
    }
  }, [conversation?.id]);

  // Scroll chat container to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > prevMessageCountRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    prevMessageCountRef.current = messages.length;
  }, [messages.length]);

  // Load more on scroll up
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container || isLoading || !hasMoreMessages) return;

    if (container.scrollTop < 50) {
      onLoadMore();
    }
  }, [isLoading, hasMoreMessages, onLoadMore]);

  // No conversation selected
  if (!conversation) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-white/30 text-sm">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-12 h-12 mb-3 text-white/15">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <p>Выберите диалог</p>
      </div>
    );
  }

  // Build display name
  const displayName =
    conversation.type === 'group' && conversation.title
      ? conversation.title
      : conversation.participants[0]?.username ?? 'Неизвестный';

  const participantCount = conversation.participants.length;

  // Messages are newest-first from API, reverse for display (oldest at top)
  const displayMessages = [...messages].reverse();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-3 border-b border-white/10 flex items-center gap-3 flex-shrink-0">
        {/* Back button (visible on mobile) */}
        <button
          onClick={onBack}
          className="md:hidden p-1 text-white/60 hover:text-site-blue transition-colors duration-200 ease-site cursor-pointer"
          aria-label="Назад"
        >
          <ArrowLeft size={20} />
        </button>

        <div className="flex-1 min-w-0">
          <h3 className="text-white text-sm font-medium truncate">
            {displayName}
          </h3>
          {conversation.type === 'group' && (
            <span className="text-white/30 text-xs">
              {participantCount} {participantCount === 1 ? 'участник' : participantCount < 5 ? 'участника' : 'участников'}
            </span>
          )}
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="px-3 py-2 bg-site-red/10 border-b border-site-red/20">
          <p className="text-site-red text-xs">{error}</p>
        </div>
      )}

      {/* Messages */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto gold-scrollbar"
      >
        {/* Load more indicator */}
        {isLoading && (
          <div className="flex items-center justify-center py-3">
            <div className="w-5 h-5 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
          </div>
        )}

        {hasMoreMessages && !isLoading && (
          <div className="flex items-center justify-center py-3">
            <button
              onClick={onLoadMore}
              className="text-site-blue text-xs hover:text-gold-light transition-colors duration-200 ease-site cursor-pointer"
            >
              Загрузить ранние сообщения
            </button>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && displayMessages.length === 0 && (
          <div className="flex items-center justify-center h-full text-white/30 text-sm">
            Нет сообщений. Напишите первыми!
          </div>
        )}

        {/* Message list */}
        {displayMessages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isOwn={msg.sender_id === currentUserId}
            onDelete={onDeleteMessage}
            onReply={onReply}
            onEdit={onEdit}
          />
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <MessageInput
        onSend={onSendMessage}
        disabled={!conversation}
        sending={sending}
        replyTo={replyTo}
        editingMessage={editingMessage}
        quoteText={quoteText}
        onClearReply={onClearReply}
        onClearEdit={onClearEdit}
        onEditSubmit={onEditSubmit}
        onQuoteInserted={onQuoteInserted}
      />
    </div>
  );
};

export default MessageArea;
