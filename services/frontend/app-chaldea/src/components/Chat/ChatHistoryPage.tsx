import { useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchMessages,
  deleteMessage,
  setActiveChannel,
  setReplyingTo,
  selectChatMessages,
  selectActiveChannel,
  selectChatIsLoading,
  selectChatError,
  selectChatPagination,
} from '../../redux/slices/chatSlice';
import { selectPermissions } from '../../redux/slices/userSlice';
import type { ChatChannel, ChatMessage as ChatMessageType } from '../../types/chat';
import ChatMessage from './ChatMessage';
import toast from 'react-hot-toast';

const CHANNEL_LABELS: Record<ChatChannel, string> = {
  general: 'Общий',
  trade: 'Торговля',
  help: 'Помощь',
};

const CHANNELS: ChatChannel[] = ['general', 'trade', 'help'];

const ChatHistoryPage = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const messages = useAppSelector(selectChatMessages);
  const activeChannel = useAppSelector(selectActiveChannel);
  const isLoading = useAppSelector(selectChatIsLoading);
  const error = useAppSelector(selectChatError);
  const pagination = useAppSelector(selectChatPagination);
  const permissions = useAppSelector(selectPermissions);

  const currentMessages = messages[activeChannel] ?? [];
  const currentPagination = pagination[activeChannel] ?? {
    total: 0,
    page: 1,
    pageSize: 50,
  };

  const totalPages = Math.max(
    1,
    Math.ceil(currentPagination.total / currentPagination.pageSize),
  );

  const loadPage = useCallback(
    (page: number) => {
      dispatch(fetchMessages({ channel: activeChannel, page, pageSize: 50 }));
    },
    [dispatch, activeChannel],
  );

  useEffect(() => {
    loadPage(1);
  }, [loadPage]);

  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  const handleChannelChange = (channel: ChatChannel) => {
    dispatch(setActiveChannel(channel));
  };

  const handleReply = (message: ChatMessageType) => {
    dispatch(setReplyingTo(message));
    toast('Ответ выбран. Перейдите в виджет чата для отправки.', {
      icon: '\u2709\uFE0F',
    });
  };

  const handleQuote = (message: ChatMessageType) => {
    dispatch(setReplyingTo(message));
    toast('Цитата выбрана. Перейдите в виджет чата для отправки.', {
      icon: '\u2709\uFE0F',
    });
  };

  const handleDelete = (messageId: number) => {
    dispatch(deleteMessage(messageId))
      .unwrap()
      .then(() => {
        toast.success('Сообщение удалено');
      })
      .catch((err: string) => {
        toast.error(err);
      });
  };

  const handlePrevPage = () => {
    if (currentPagination.page > 1) {
      loadPage(currentPagination.page - 1);
    }
  };

  const handleNextPage = () => {
    if (currentPagination.page < totalPages) {
      loadPage(currentPagination.page + 1);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="mt-10"
    >
      {/* Back link */}
      <button
        onClick={() => navigate(-1)}
        className="text-site-blue hover:text-white transition-colors duration-200 ease-site text-sm mb-6 cursor-pointer"
      >
        &larr; Назад
      </button>

      {/* Title */}
      <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase mb-6">
        История чата
      </h1>

      {/* Channel tabs */}
      <div className="flex flex-wrap gap-2 mb-6">
        {CHANNELS.map((channel) => (
          <button
            key={channel}
            onClick={() => handleChannelChange(channel)}
            className={`px-4 py-2 text-sm font-medium rounded-card transition-colors duration-200 ease-site cursor-pointer
              ${
                activeChannel === channel
                  ? 'gold-text bg-white/10'
                  : 'text-white/60 hover:text-white hover:bg-white/5'
              }`}
          >
            {CHANNEL_LABELS[channel]}
          </button>
        ))}
      </div>

      {/* Messages area */}
      <div className="gray-bg p-4 sm:p-6 min-h-[400px] flex flex-col">
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <span className="text-white/40 text-sm">Загрузка...</span>
          </div>
        ) : currentMessages.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <span className="text-white/40 text-sm">Нет сообщений</span>
          </div>
        ) : (
          <div className="flex-1 gold-scrollbar overflow-y-auto">
            {currentMessages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                permissions={permissions}
                onReply={handleReply}
                onQuote={handleQuote}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-4 mt-4 pt-4 border-t border-white/10">
            <button
              onClick={handlePrevPage}
              disabled={currentPagination.page <= 1}
              className={`btn-line px-4 py-2 text-sm ${
                currentPagination.page <= 1
                  ? 'opacity-30 cursor-not-allowed'
                  : 'cursor-pointer'
              }`}
            >
              Назад
            </button>
            <span className="text-white/60 text-sm">
              {currentPagination.page} / {totalPages}
            </span>
            <button
              onClick={handleNextPage}
              disabled={currentPagination.page >= totalPages}
              className={`btn-line px-4 py-2 text-sm ${
                currentPagination.page >= totalPages
                  ? 'opacity-30 cursor-not-allowed'
                  : 'cursor-pointer'
              }`}
            >
              Вперёд
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default ChatHistoryPage;
