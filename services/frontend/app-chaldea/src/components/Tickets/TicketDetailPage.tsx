import { useEffect, useCallback, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { ArrowLeft } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchTicketDetail,
  sendTicketMessage,
  selectActiveTicket,
  selectTicketMessages,
  selectTicketsLoading,
  selectTicketsError,
  clearTicketDetail,
  clearTicketError,
} from '../../redux/slices/ticketSlice';
import type { TicketStatus, TicketCategory } from '../../types/ticket';
import TicketMessage from './TicketMessage';
import TicketInput from './TicketInput';
import toast from 'react-hot-toast';

const STATUS_LABELS: Record<TicketStatus, string> = {
  open: 'Открыт',
  in_progress: 'В работе',
  awaiting_reply: 'Ожидает ответа',
  closed: 'Закрыт',
};

const STATUS_COLORS: Record<TicketStatus, string> = {
  open: 'bg-green-500/20 text-green-400',
  in_progress: 'bg-site-blue/20 text-site-blue',
  awaiting_reply: 'bg-yellow-500/20 text-yellow-400',
  closed: 'bg-white/10 text-white/40',
};

const CATEGORY_LABELS: Record<TicketCategory, string> = {
  bug: 'Баг / Ошибка',
  question: 'Вопрос',
  suggestion: 'Предложение',
  complaint: 'Жалоба',
  other: 'Другое',
};

const TicketDetailPage = () => {
  const { ticketId } = useParams<{ ticketId: string }>();
  const dispatch = useAppDispatch();
  const ticket = useAppSelector(selectActiveTicket);
  const messages = useAppSelector(selectTicketMessages);
  const isLoading = useAppSelector(selectTicketsLoading);
  const error = useAppSelector(selectTicketsError);
  const currentUserId = useAppSelector((state) => state.user.id) as number | null;

  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ticketId) {
      dispatch(fetchTicketDetail({ ticketId: Number(ticketId) }));
    }
    return () => {
      dispatch(clearTicketDetail());
    };
  }, [ticketId, dispatch]);

  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearTicketError());
    }
  }, [error, dispatch]);

  // Scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback(
    (content: string, attachmentUrl: string | null) => {
      if (!ticketId) return;
      setIsSending(true);
      dispatch(
        sendTicketMessage({
          ticketId: Number(ticketId),
          data: { content, attachment_url: attachmentUrl },
        }),
      )
        .unwrap()
        .catch(() => {
          // Error handled by Redux
        })
        .finally(() => setIsSending(false));
    },
    [dispatch, ticketId],
  );

  const isClosed = ticket?.status === 'closed';

  if (isLoading && !ticket) {
    return (
      <div className="w-full max-w-[900px] mx-auto">
        <p className="text-white/40 text-sm">Загрузка...</p>
      </div>
    );
  }

  if (!ticket && !isLoading) {
    return (
      <div className="w-full max-w-[900px] mx-auto">
        <p className="text-white/40 text-sm">Тикет не найден</p>
        <Link to="/support" className="site-link text-sm mt-2 inline-block">
          Вернуться к списку
        </Link>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="w-full max-w-[900px] mx-auto flex flex-col rounded-card border border-white/10 bg-black/50 p-4 sm:p-6"
      style={{ height: 'calc(100vh - 120px)' }}
    >
      {/* Header */}
      <div className="flex-shrink-0 mb-4">
        <Link
          to="/support"
          className="inline-flex items-center gap-1.5 text-white/40 hover:text-site-blue text-sm transition-colors duration-200 ease-site mb-3"
        >
          <ArrowLeft size={16} />
          Назад к тикетам
        </Link>

        {ticket && (
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
            <h1 className="text-white text-lg sm:text-xl font-medium truncate flex-1">
              {ticket.subject}
            </h1>
            <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
              <span className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider ${STATUS_COLORS[ticket.status]}`}>
                {STATUS_LABELS[ticket.status]}
              </span>
              <span className="text-white/30 text-[10px] font-medium uppercase tracking-wider">
                {CATEGORY_LABELS[ticket.category]}
              </span>
              <span className="text-white/20 text-[10px]">#{ticket.id}</span>
            </div>
          </div>
        )}
      </div>

      {/* Messages area */}
      <div className="flex-1 min-h-0 overflow-y-auto gold-scrollbar bg-white/[0.02] border border-white/[0.06] rounded-card">
        <div className="py-2">
          {messages.map((msg) => (
            <TicketMessage
              key={msg.id}
              message={msg}
              isOwn={msg.sender_id === currentUserId}
            />
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      {isClosed ? (
        <div className="flex-shrink-0 mt-2 px-3 py-3 text-center text-white/30 text-sm border-t border-white/10">
          Тикет закрыт. Отправка сообщений невозможна.
        </div>
      ) : (
        <div className="flex-shrink-0 mt-2">
          <TicketInput
            onSend={handleSend}
            disabled={isClosed}
            sending={isSending}
          />
        </div>
      )}
    </motion.div>
  );
};

export default TicketDetailPage;
