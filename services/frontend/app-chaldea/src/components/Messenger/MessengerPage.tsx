import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchConversations,
  fetchMessages,
  sendMessage,
  deleteMessage,
  editMessage,
  createConversation,
  markConversationRead,
  fetchUnreadCount,
  setActiveConversation,
  clearActiveConversation,
  setEditingMessage,
  clearEditingMessage,
  setReplyToMessage,
  clearReplyToMessage,
  selectConversations,
  selectActiveConversation,
  selectActiveMessages,
  selectActiveConversationId,
  selectMessengerLoading,
  selectMessengerError,
  selectMessagesPagination,
  selectEditingMessage,
  selectReplyToMessage,
} from '../../redux/slices/messengerSlice';
import type { ConversationType, PrivateMessage } from '../../types/messenger';
import ConversationList from './ConversationList';
import MessageArea from './MessageArea';
import NewConversationModal from './NewConversationModal';
import MessengerSettings from './MessengerSettings';
import toast from 'react-hot-toast';

const MessengerPage = () => {
  const dispatch = useAppDispatch();

  const conversations = useAppSelector(selectConversations);
  const activeConversation = useAppSelector(selectActiveConversation);
  const activeConversationId = useAppSelector(selectActiveConversationId);
  const messages = useAppSelector(selectActiveMessages);
  const isLoading = useAppSelector(selectMessengerLoading);
  const error = useAppSelector(selectMessengerError);
  const messagesPagination = useAppSelector(selectMessagesPagination);
  const currentUserId = useAppSelector((state) => state.user.id) as number | null;
  const editingMsg = useAppSelector(selectEditingMessage);
  const replyToMsg = useAppSelector(selectReplyToMessage);

  const [showNewModal, setShowNewModal] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isSending, setIsSending] = useState(false);

  // Mobile: which panel is visible
  const [mobileView, setMobileView] = useState<'list' | 'chat'>('list');

  // Fetch conversations on mount
  useEffect(() => {
    dispatch(fetchConversations());
    dispatch(fetchUnreadCount());
  }, [dispatch]);

  // Fetch messages when active conversation changes
  useEffect(() => {
    if (activeConversationId !== null) {
      dispatch(fetchMessages({ conversationId: activeConversationId, page: 1, page_size: 50 }));
      dispatch(markConversationRead(activeConversationId));
    }
  }, [activeConversationId, dispatch]);

  // Clear editing/reply when conversation changes
  useEffect(() => {
    dispatch(clearEditingMessage());
    dispatch(clearReplyToMessage());
  }, [activeConversationId, dispatch]);

  // Show error via toast
  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  const handleSelectConversation = useCallback(
    (id: number) => {
      dispatch(setActiveConversation(id));
      setMobileView('chat');
    },
    [dispatch],
  );

  const handleBack = useCallback(() => {
    dispatch(clearActiveConversation());
    setMobileView('list');
  }, [dispatch]);

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (!activeConversationId) return;
      setIsSending(true);
      try {
        const payload: { conversationId: number; content: string; reply_to_id?: number } = {
          conversationId: activeConversationId,
          content,
        };
        if (replyToMsg) {
          payload.reply_to_id = replyToMsg.id;
        }
        await dispatch(sendMessage(payload)).unwrap();
        dispatch(clearReplyToMessage());
      } catch (err) {
        toast.error(typeof err === 'string' ? err : 'Не удалось отправить сообщение');
      } finally {
        setIsSending(false);
      }
    },
    [activeConversationId, dispatch, replyToMsg],
  );

  const handleDeleteMessage = useCallback(
    async (messageId: number) => {
      try {
        await dispatch(deleteMessage(messageId)).unwrap();
      } catch (err) {
        toast.error(typeof err === 'string' ? err : 'Не удалось удалить сообщение');
      }
    },
    [dispatch],
  );

  const handleLoadMore = useCallback(() => {
    if (!activeConversationId) return;
    const pagination = messagesPagination[activeConversationId];
    if (!pagination) return;
    const nextPage = pagination.page + 1;
    if (nextPage > pagination.totalPages) return;

    dispatch(
      fetchMessages({
        conversationId: activeConversationId,
        page: nextPage,
        page_size: 50,
      }),
    );
  }, [activeConversationId, messagesPagination, dispatch]);

  const handleCreateConversation = useCallback(
    async (type: ConversationType, participantIds: number[], title: string | null) => {
      setIsCreating(true);
      try {
        await dispatch(
          createConversation({ type, participant_ids: participantIds, title }),
        ).unwrap();
        setShowNewModal(false);
        setMobileView('chat');
      } catch (err) {
        toast.error(typeof err === 'string' ? err : 'Не удалось создать диалог');
      } finally {
        setIsCreating(false);
      }
    },
    [dispatch],
  );

  const handleReply = useCallback(
    (msg: PrivateMessage) => {
      dispatch(setReplyToMessage(msg));
    },
    [dispatch],
  );

  const handleEdit = useCallback(
    (msg: PrivateMessage) => {
      dispatch(setEditingMessage(msg));
    },
    [dispatch],
  );

  const handleClearReply = useCallback(() => {
    dispatch(clearReplyToMessage());
  }, [dispatch]);

  const handleClearEdit = useCallback(() => {
    dispatch(clearEditingMessage());
  }, [dispatch]);

  const handleEditSubmit = useCallback(
    async (messageId: number, content: string) => {
      try {
        await dispatch(editMessage({ messageId, content })).unwrap();
      } catch (err) {
        toast.error(typeof err === 'string' ? err : 'Не удалось отредактировать сообщение');
      }
    },
    [dispatch],
  );

  const hasMoreMessages = activeConversationId
    ? (messagesPagination[activeConversationId]?.page ?? 1) <
      (messagesPagination[activeConversationId]?.totalPages ?? 1)
    : false;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="w-full max-w-[1240px] mx-auto px-4 sm:px-6"
    >
      <div className="h-[calc(100vh-220px)] min-h-[400px] flex gap-3">
        {/* Left panel: Conversation list */}
        <div
          className={`w-full md:w-[320px] lg:w-[360px] flex-shrink-0 bg-black/40 rounded-card backdrop-blur-sm border border-white/10 overflow-hidden ${
            mobileView === 'list' ? 'flex flex-col' : 'hidden md:flex md:flex-col'
          }`}
        >
          <ConversationList
            conversations={conversations}
            activeConversationId={activeConversationId}
            isLoading={isLoading}
            onSelectConversation={handleSelectConversation}
            onNewConversation={() => setShowNewModal(true)}
            onOpenSettings={() => setShowSettings(true)}
          />
        </div>

        {/* Right panel: Message area */}
        <div
          className={`flex-1 min-w-0 bg-black/40 rounded-card backdrop-blur-sm border border-white/10 overflow-hidden ${
            mobileView === 'chat' ? 'flex flex-col' : 'hidden md:flex md:flex-col'
          }`}
        >
          <MessageArea
            conversation={activeConversation}
            messages={messages}
            currentUserId={currentUserId}
            isLoading={isLoading}
            error={error}
            hasMoreMessages={hasMoreMessages}
            sending={isSending}
            replyTo={replyToMsg}
            editingMessage={editingMsg}
            quoteText={null}
            onSendMessage={handleSendMessage}
            onDeleteMessage={handleDeleteMessage}
            onLoadMore={handleLoadMore}
            onBack={handleBack}
            onReply={handleReply}
            onEdit={handleEdit}
            onClearReply={handleClearReply}
            onClearEdit={handleClearEdit}
            onEditSubmit={handleEditSubmit}
            onQuoteInserted={() => {}}
          />
        </div>
      </div>

      {/* New conversation modal */}
      <NewConversationModal
        isOpen={showNewModal}
        isCreating={isCreating}
        onClose={() => setShowNewModal(false)}
        onCreate={handleCreateConversation}
      />

      {/* Settings modal */}
      <MessengerSettings
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
      />
    </motion.div>
  );
};

export default MessengerPage;
