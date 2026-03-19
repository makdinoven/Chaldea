import type { ChatMessage as ChatMessageType } from '../../types/chat';
import ChatMessage from './ChatMessage';

interface ChatMessagesProps {
  messages: ChatMessageType[];
  isLoading: boolean;
  permissions: string[];
  onReply: (message: ChatMessageType) => void;
  onQuote: (message: ChatMessageType) => void;
  onDelete: (messageId: number) => void;
}

const ChatMessages = ({
  messages,
  isLoading,
  permissions,
  onReply,
  onQuote,
  onDelete,
}: ChatMessagesProps) => {
  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-white/40 text-sm">Загрузка...</span>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-white/40 text-sm">Нет сообщений</span>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto gold-scrollbar">
      {messages.map((message) => (
        <ChatMessage
          key={message.id}
          message={message}
          permissions={permissions}
          onReply={onReply}
          onQuote={onQuote}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
};

export default ChatMessages;
