import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { ArrowLeft, ArrowDown, Search, X } from 'react-feather';
import type { ConversationListItem, PrivateMessage } from '../../types/messenger';
import { getPresence, searchMessages } from '../../api/messengerApi';
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
  typingUsernames: string[];
  onTyping: () => void;
  replyTo: PrivateMessage | null;
  editingMessage: PrivateMessage | null;
  quoteText: string | null;
  onSendMessage: (content: string, imageUrl?: string | null) => void;
  onDeleteMessage: (messageId: number) => void;
  onLoadMore: () => void;
  onBack: () => void;
  onReply: (message: PrivateMessage) => void;
  onEdit: (message: PrivateMessage) => void;
  onReact: (messageId: number, emoji: string) => void;
  onClearReply: () => void;
  onClearEdit: () => void;
  onEditSubmit: (messageId: number, content: string) => void;
  onQuoteInserted: () => void;
}

// Distance from the bottom (px) within which we still auto-follow new messages.
const NEAR_BOTTOM_THRESHOLD = 150;
// Scroll position (px from top) that triggers loading older messages.
const LOAD_MORE_THRESHOLD = 50;

const dayKey = (d: Date): string => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

const formatDateLabel = (dateStr: string): string => {
  const d = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dayKey(d) === dayKey(today)) return 'Сегодня';
  if (dayKey(d) === dayKey(yesterday)) return 'Вчера';
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
};

const pluralNew = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'новое сообщение';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'новых сообщения';
  return 'новых сообщений';
};

type RenderItem =
  | { kind: 'date'; key: string; label: string }
  | { kind: 'unread'; key: string }
  | { kind: 'message'; key: string; message: PrivateMessage };

const MessageArea = ({
  conversation,
  messages,
  currentUserId,
  isLoading,
  error,
  hasMoreMessages,
  sending,
  typingUsernames,
  onTyping,
  replyTo,
  editingMessage,
  quoteText,
  onSendMessage,
  onDeleteMessage,
  onLoadMore,
  onBack,
  onReply,
  onEdit,
  onReact,
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

  // Count of new messages that arrived while the user was reading history
  // (i.e. not near the bottom). Drives the "jump to new messages" pill.
  const [newCount, setNewCount] = useState(0);
  // Snapshot of the conversation's unread count at open time, used to place
  // the "unread messages" divider before it gets cleared by mark-read.
  const [unreadSnapshot, setUnreadSnapshot] = useState(0);

  const conversationId = conversation?.id ?? null;

  // In-conversation message search.
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<PrivateMessage[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    setSearchOpen(false);
    setSearchQuery('');
    setSearchResults([]);
  }, [conversationId]);

  useEffect(() => {
    if (!searchOpen || conversationId === null || !searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const handle = setTimeout(() => {
      setSearching(true);
      searchMessages(conversationId, searchQuery.trim(), 1, 20)
        .then((resp) => setSearchResults(resp.data.items))
        .catch(() => setSearchResults([]))
        .finally(() => setSearching(false));
    }, 350);
    return () => clearTimeout(handle);
  }, [searchOpen, conversationId, searchQuery]);

  // Online status of the other party in a direct chat (polled).
  const [otherOnline, setOtherOnline] = useState<boolean | null>(null);
  const otherUserId =
    conversation?.type === 'direct' ? conversation.participants[0]?.user_id ?? null : null;

  useEffect(() => {
    if (otherUserId === null) {
      setOtherOnline(null);
      return;
    }
    let cancelled = false;
    const fetchPresence = () => {
      getPresence(otherUserId)
        .then((resp) => {
          if (!cancelled) setOtherOnline(resp.data.online);
        })
        .catch(() => {
          if (!cancelled) setOtherOnline(null);
        });
    };
    fetchPresence();
    const interval = setInterval(fetchPresence, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [otherUserId]);

  // Reset tracking when switching conversations.
  useEffect(() => {
    prevNewestIdRef.current = null;
    prevOldestIdRef.current = null;
    loadMoreAnchorRef.current = null;
    setNewCount(0);
    setUnreadSnapshot(conversation?.unread_count ?? 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  const scrollToBottom = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
    setNewCount(0);
  }, []);

  // Manage scroll position as the message list changes.
  // IMPORTANT: only the inner container is scrolled — never the page/window.
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    if (messages.length === 0) {
      prevNewestIdRef.current = null;
      prevOldestIdRef.current = null;
      return;
    }

    // messages are newest-first: [0] is newest, [last] is oldest
    const newest = messages[0];
    const newestId = newest.id;
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
      const nearBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight <
        NEAR_BOTTOM_THRESHOLD;
      const isOwnNewest = newest.sender_id === currentUserId;
      if (nearBottom || isOwnNewest) {
        // Follow when already near the bottom, or when it's our own message.
        requestAnimationFrame(() => {
          container.scrollTop = container.scrollHeight;
        });
        setNewCount(0);
      } else {
        // Reading history — don't yank; surface a "jump to new" pill instead.
        setNewCount((c) => c + 1);
      }
    }

    prevNewestIdRef.current = newestId;
    prevOldestIdRef.current = oldestId;
  }, [messages, currentUserId]);

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

  // React to scrolling: load older near the top, clear the pill near the bottom.
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    if (container.scrollTop < LOAD_MORE_THRESHOLD && hasMoreMessages && !isLoading) {
      requestLoadMore();
    }

    const nearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <
      NEAR_BOTTOM_THRESHOLD;
    if (nearBottom) {
      setNewCount((c) => (c === 0 ? c : 0));
    }
  }, [hasMoreMessages, isLoading, requestLoadMore]);

  // Messages are newest-first from API, reverse for display (oldest at top).
  const displayMessages = useMemo(() => [...messages].reverse(), [messages]);

  // Build the render list with date separators and the unread divider.
  const renderItems = useMemo<RenderItem[]>(() => {
    const items: RenderItem[] = [];
    const firstUnreadIndex =
      unreadSnapshot > 0 ? Math.max(0, displayMessages.length - unreadSnapshot) : -1;

    let lastDay: string | null = null;
    displayMessages.forEach((msg, idx) => {
      const msgDay = dayKey(new Date(msg.created_at));
      if (msgDay !== lastDay) {
        items.push({ kind: 'date', key: `date-${msg.id}`, label: formatDateLabel(msg.created_at) });
        lastDay = msgDay;
      }
      if (idx === firstUnreadIndex) {
        items.push({ kind: 'unread', key: `unread-${msg.id}` });
      }
      items.push({ kind: 'message', key: `msg-${msg.id}`, message: msg });
    });
    return items;
  }, [displayMessages, unreadSnapshot]);

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
          {conversation.type === 'direct' && otherOnline !== null && (
            <span className={`text-xs ${otherOnline ? 'text-green-400' : 'text-white/30'}`}>
              {otherOnline ? 'в сети' : 'не в сети'}
            </span>
          )}
        </div>

        {/* Search toggle */}
        <button
          onClick={() => setSearchOpen((o) => !o)}
          className={`p-1 transition-colors duration-200 ease-site cursor-pointer ${
            searchOpen ? 'text-site-blue' : 'text-white/50 hover:text-site-blue'
          }`}
          aria-label="Поиск по сообщениям"
          title="Поиск по сообщениям"
        >
          <Search size={18} />
        </button>
      </div>

      {/* Search bar + results */}
      {searchOpen && (
        <div className="relative px-3 py-2 border-b border-white/10 flex-shrink-0">
          <div className="flex items-center gap-2">
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск по сообщениям..."
              className="input-underline w-full text-sm !py-1.5"
              autoFocus
            />
            <button
              onClick={() => { setSearchOpen(false); setSearchQuery(''); }}
              className="text-white/40 hover:text-white/70 cursor-pointer flex-shrink-0"
              aria-label="Закрыть поиск"
            >
              <X size={16} />
            </button>
          </div>
          {searchQuery.trim() && (
            <div className="absolute left-0 right-0 top-full z-20 max-h-64 overflow-y-auto gold-scrollbar bg-site-bg/98 backdrop-blur-sm border-b border-white/10 shadow-dropdown">
              {searching ? (
                <div className="px-3 py-3 text-white/40 text-xs">Поиск…</div>
              ) : searchResults.length === 0 ? (
                <div className="px-3 py-3 text-white/40 text-xs">Ничего не найдено</div>
              ) : (
                searchResults.map((m) => (
                  <div key={m.id} className="px-3 py-2 border-b border-white/5">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-site-blue text-xs font-medium truncate">{m.sender_username}</span>
                      <span className="text-white/30 text-[10px] flex-shrink-0">{formatDateLabel(m.created_at)}</span>
                    </div>
                    <p className="text-white/70 text-xs truncate">{m.content || '📷 Изображение'}</p>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="px-3 py-2 bg-site-red/10 border-b border-site-red/20">
          <p className="text-site-red text-xs">{error}</p>
        </div>
      )}

      {/* Messages area (relative wrapper anchors the "new messages" pill) */}
      <div className="relative flex-1 min-h-0">
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="absolute inset-0 overflow-y-auto overscroll-contain gold-scrollbar"
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

          {/* Message list with date / unread separators */}
          {renderItems.map((item) => {
            if (item.kind === 'date') {
              return (
                <div key={item.key} className="flex items-center justify-center py-2">
                  <span className="text-white/40 text-xs bg-white/5 rounded-full px-3 py-1">
                    {item.label}
                  </span>
                </div>
              );
            }
            if (item.kind === 'unread') {
              return (
                <div key={item.key} className="flex items-center gap-2 px-3 py-1.5">
                  <span className="flex-1 h-px bg-site-blue/30" />
                  <span className="text-site-blue text-xs whitespace-nowrap">
                    непрочитанные сообщения
                  </span>
                  <span className="flex-1 h-px bg-site-blue/30" />
                </div>
              );
            }
            return (
              // content-visibility lets the browser skip rendering/layout of
              // off-screen messages (lightweight virtualization, no JS windowing).
              <div
                key={item.key}
                style={{ contentVisibility: 'auto', containIntrinsicSize: 'auto 64px' }}
              >
                <MessageBubble
                  message={item.message}
                  isOwn={item.message.sender_id === currentUserId}
                  onDelete={onDeleteMessage}
                  onReply={onReply}
                  onEdit={onEdit}
                  onReact={onReact}
                />
              </div>
            );
          })}
        </div>

        {/* Jump-to-new-messages pill */}
        {newCount > 0 && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10
              flex items-center gap-1.5
              bg-site-bg/95 backdrop-blur-sm border border-gold/40 text-gold
              text-xs rounded-full px-3 py-1.5 shadow-card
              hover:bg-white/10 transition-colors duration-200 ease-site cursor-pointer"
          >
            <ArrowDown size={14} />
            {newCount} {pluralNew(newCount)}
          </button>
        )}
      </div>

      {/* Typing indicator */}
      {typingUsernames.length > 0 && (
        <div className="px-3 py-1 text-xs text-white/50 italic flex-shrink-0">
          {typingUsernames.length === 1
            ? `${typingUsernames[0]} печатает…`
            : `${typingUsernames.slice(0, 2).join(', ')} печатают…`}
        </div>
      )}

      {/* Input */}
      <MessageInput
        onSend={onSendMessage}
        onTyping={onTyping}
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
