import { useState, useMemo } from 'react';
import type { ConversationListItem } from '../../types/messenger';
import ConversationItem from './ConversationItem';

interface ConversationListProps {
  conversations: ConversationListItem[];
  activeConversationId: number | null;
  isLoading: boolean;
  onSelectConversation: (id: number) => void;
  onNewConversation: () => void;
  onOpenSettings: () => void;
}

const ConversationList = ({
  conversations,
  activeConversationId,
  isLoading,
  onSelectConversation,
  onNewConversation,
  onOpenSettings,
}: ConversationListProps) => {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return conversations;
    const q = search.toLowerCase();
    return conversations.filter((conv) => {
      if (conv.title?.toLowerCase().includes(q)) return true;
      return conv.participants.some((p) =>
        p.username.toLowerCase().includes(q),
      );
    });
  }, [conversations, search]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-3 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <h2 className="gold-text text-lg font-medium uppercase">
            Сообщения
          </h2>
          <div className="flex items-center gap-2">
            {/* Settings button */}
            <button
              onClick={onOpenSettings}
              className="p-1.5 text-white/50 hover:text-site-blue transition-colors duration-200 ease-site cursor-pointer"
              aria-label="Настройки"
              title="Настройки"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.32 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>

            {/* New conversation button */}
            <button
              onClick={onNewConversation}
              className="btn-blue !px-3 !py-1 !text-sm"
            >
              Новый
            </button>
          </div>
        </div>

        {/* Search */}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск диалогов..."
          className="input-underline w-full text-sm !py-1.5"
        />
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto gold-scrollbar">
        {isLoading && conversations.length === 0 ? (
          <div className="flex items-center justify-center py-10">
            <div className="w-6 h-6 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-10 text-center text-white/40 text-sm">
            {search.trim()
              ? 'Ничего не найдено'
              : 'Нет диалогов. Начните новый!'}
          </div>
        ) : (
          filtered.map((conv) => (
            <ConversationItem
              key={conv.id}
              conversation={conv}
              isActive={conv.id === activeConversationId}
              onClick={onSelectConversation}
            />
          ))
        )}
      </div>
    </div>
  );
};

export default ConversationList;
