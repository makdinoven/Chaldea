import { useEffect, useState, useCallback } from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchMessages,
  sendMessage,
  deleteMessage,
  setActiveChannel,
  setReplyingTo,
  clearReply,
  selectChatMessages,
  selectActiveChannel,
  selectReplyingTo,
  selectChatIsLoading,
  selectChatError,
} from '../../redux/slices/chatSlice';
import { selectPermissions } from '../../redux/slices/userSlice';
import type { ChatMessage as ChatMessageType, ChatChannel } from '../../types/chat';
import ChatHeader from './ChatHeader';
import ChatInput from './ChatInput';
import ChatMessages from './ChatMessages';
import ConfirmationModal from '../ui/ConfirmationModal';
import toast from 'react-hot-toast';

interface ChatPanelProps {
  isAuthenticated: boolean;
  isBanned: boolean;
}

const ChatPanel = ({ isAuthenticated, isBanned }: ChatPanelProps) => {
  const dispatch = useAppDispatch();
  const messages = useAppSelector(selectChatMessages);
  const activeChannel = useAppSelector(selectActiveChannel);
  const replyingTo = useAppSelector(selectReplyingTo);
  const isLoading = useAppSelector(selectChatIsLoading);
  const error = useAppSelector(selectChatError);
  const permissions = useAppSelector(selectPermissions);

  const [quoteText, setQuoteText] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  // Fetch messages on mount and channel switch
  useEffect(() => {
    dispatch(fetchMessages({ channel: activeChannel }));
  }, [dispatch, activeChannel]);

  // Show error toast
  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  const handleChannelChange = useCallback(
    (channel: ChatChannel) => {
      dispatch(setActiveChannel(channel));
    },
    [dispatch],
  );

  const handleSend = useCallback(
    (content: string, replyToId: number | null) => {
      dispatch(
        sendMessage({
          channel: activeChannel,
          content,
          reply_to_id: replyToId,
        }),
      );
    },
    [dispatch, activeChannel],
  );

  const handleReply = useCallback(
    (message: ChatMessageType) => {
      dispatch(setReplyingTo(message));
    },
    [dispatch],
  );

  const handleQuote = useCallback((message: ChatMessageType) => {
    setQuoteText(`> ${message.username}: ${message.content}\n`);
  }, []);

  const handleClearQuote = useCallback(() => {
    setQuoteText(null);
  }, []);

  const handleCancelReply = useCallback(() => {
    dispatch(clearReply());
  }, [dispatch]);

  const handleDelete = useCallback(
    (messageId: number) => {
      setDeleteConfirmId(messageId);
    },
    [],
  );

  const activeMessages = messages[activeChannel] ?? [];

  return (
    <div
      className="w-full h-full
        gray-bg shadow-modal border-r border-white/10
        flex flex-col overflow-hidden"
    >
      <ChatHeader
        activeChannel={activeChannel}
        onChannelChange={handleChannelChange}
      />
      <ChatInput
        activeChannel={activeChannel}
        replyingTo={replyingTo}
        isAuthenticated={isAuthenticated}
        isBanned={isBanned}
        onSend={handleSend}
        onCancelReply={handleCancelReply}
        quoteText={quoteText}
        onClearQuote={handleClearQuote}
      />
      <ChatMessages
        messages={activeMessages}
        isLoading={isLoading}
        permissions={permissions}
        onReply={handleReply}
        onQuote={handleQuote}
        onDelete={handleDelete}
      />
      <ConfirmationModal
        isOpen={deleteConfirmId !== null}
        title="Удалить сообщение?"
        message="Это действие нельзя отменить. Сообщение будет удалено для всех пользователей."
        onConfirm={() => {
          if (deleteConfirmId) {
            dispatch(deleteMessage(deleteConfirmId));
          }
          setDeleteConfirmId(null);
        }}
        onCancel={() => setDeleteConfirmId(null)}
      />
    </div>
  );
};

export default ChatPanel;
