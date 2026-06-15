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
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  // Track the newest/oldest message ids to tell apart a freshly arrived
  // message (appended at the bottom) from a "load older" prepend at the top.
  const prevNewestIdRef = useRef<number | null>(null);
  const prevOldestIdRef = useRef<number | null>(null);
  // Snapshot taken right before a "load older" request so we can keep the
  // currently-read message in place once the older page is prepended.
  const loadMoreAnchorRef = useRef<{ scrollHeight: number; scrollTop: number } | null>(null);

  // Distance from the bottom (px) within which we still auto-follow new messages.
  const NEAR_BOTTOM_THRESHOLD = 150;
  // Scroll position (px from top) that triggers loading older messages.
  const LOAD_MORE_THRESHOLD = 50;

  // Reset tracking when switching conversations.
  useEffect(() => {
    prevNewestIdRef.current = null;
    prevOldestIdRef.current = null;
    loadMoreAnchorRef.current = null;
  }, [conversation?.id]);

  // Manage scroll position as the message list changes.
  // IMPORTANT: only the inner container is scrolled — never the page/window
  // (the previous scrollIntoView() pulled the whole page down).
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    if (messages.length === 0) {
      prevNewestIdRef.current = null;
      prevOldestIdRef.current = null;
      return;
    }

    // messages are newest-first: [0] is newest, [last] is oldest
    const newestId = messages[0].id;
    const oldestId = messages[messages.length - 1].id;
    const prevNewest = prevNewestIdRef.current;
    const prevOldest = prevOldestIdRef.current;

    const isFirstLoad = prevNewest === null;
    const newMessageAtBottom = prevNewest !== null && newestId !== prevNewest;
    const loadedOlder =
      prevOldest !== null && oldestId !== prevOldest && newestId === prevNewest;

    if (isFirstLoad) {
      // Jump to the latest message instantly on open.
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    } else if (loadedOlder && loadMoreAnchorRef.current) {
      // Older page prepended — preserve the reading position so the view
      // doesn't jump (this is what made history unreadable before).
      const { scrollHeight, scrollTop } = loadMoreAnchorRef.current;
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight - scrollHeight + scrollTop;
      });
      loadMoreAnchorRef.current = null;
    } else if (newMessageAtBottom) {
      // Only follow a new message if the user is already near the bottom,
      // so we don't yank them away while they read older history.
      const nearBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight <
        NEAR_BOTTOM_THRESHOLD;
      if (nearBottom) {
        requestAnimationFrame(() => {
          container.scrollTop = container.scrollHeight;
        });
      }
    }

    prevNewestIdRef.current = newestId;
    prevOldestIdRef.current = oldestId;
  }, [messages]);

  // Snapshot the scroll metrics, then request the older page.
  const requestLoadMore = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container || isLoading || !hasMoreMessages) return;
    loadMoreAnchorRef.current = {
      scrollHeight: container.scrollHeight,
      scrollTop: container.scrollTop,
    };
    onLoadMore();
  }, [isLoading, hasMoreMessages, onLoadMore]);

  // Load more when scrolled near the top.
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container || isLoading || !hasMoreMessages) return;

    if (container.scrollTop < LOAD_MORE_THRESHOLD) {
      requestLoadMore();
    }
  }, [isLoading, hasMoreMessages, requestLoadMore]);

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
              onClick={requestLoadMore}
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
