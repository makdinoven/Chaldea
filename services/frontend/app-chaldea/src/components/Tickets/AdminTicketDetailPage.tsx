import { useEffect, useCallback, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { ArrowLeft } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchTicketDetail,
  sendTicketMessage,
  changeTicketStatus,
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

const STATUS_OPTIONS: TicketStatus[] = ['open', 'in_progress', 'awaiting_reply', 'closed'];

const AdminTicketDetailPage = () => {
  const { ticketId } = useParams<{ ticketId: string }>();
  const dispatch = useAppDispatch();
  const ticket = useAppSelector(selectActiveTicket);
  const messages = useAppSelector(selectTicketMessages);
  const isLoading = useAppSelector(selectTicketsLoading);
  const error = useAppSelector(selectTicketsError);
  const currentUserId = useAppSelector((state) => state.user.id) as number | null;

  const [isSending, setIsSending] = useState(false);
  const [isChangingStatus, setIsChangingStatus] = useState(false);
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

  const handleStatusChange = useCallback(
    (newStatus: TicketStatus) => {
      if (!ticketId || !ticket || ticket.status === newStatus) return;
      setIsChangingStatus(true);
      dispatch(changeTicketStatus({ ticketId: Number(ticketId), status: newStatus }))
        .unwrap()
        .then(() => {
          toast.success(`Статус изменён на "${STATUS_LABELS[newStatus]}"`);
        })
        .catch(() => {
          // Error handled by Redux
        })
        .finally(() => setIsChangingStatus(false));
    },
    [dispatch, ticketId, ticket],
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
        <Link to="/admin/tickets" className="site-link text-sm mt-2 inline-block">
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
      className="w-full max-w-[900px] mx-auto flex flex-col"
      style={{ height: 'calc(100vh - 120px)' }}
    >
      {/* Header */}
      <div className="flex-shrink-0 mb-4">
        <Link
          to="/admin/tickets"
          className="inline-flex items-center gap-1.5 text-white/40 hover:text-site-blue text-sm transition-colors duration-200 ease-site mb-3"
        >
          <ArrowLeft size={16} />
          Назад к тикетам
        </Link>

        {ticket && (
          <>
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 mb-3">
              <h1 className="text-white text-lg sm:text-xl font-medium truncate flex-1">
                {ticket.subject}
              </h1>
              <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
                <span className="text-white/30 text-[10px] font-medium uppercase tracking-wider">
                  {CATEGORY_LABELS[ticket.category]}
                </span>
                <span className="text-white/20 text-[10px]">#{ticket.id}</span>
              </div>
            </div>

            {/* User info + Status control */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
              <div className="flex items-center gap-2">
                <span className="text-white/40 text-xs">Автор:</span>
                <Link
                  to={`/user-profile/${ticket.user_id}`}
                  className="text-site-blue text-xs hover:underline"
                >
                  {ticket.username}
                </Link>
              </div>

              {/* Status dropdown */}
              <div className="flex items-center gap-2">
                <span className="text-white/40 text-xs">Статус:</span>
                <select
                  value={ticket.status}
                  onChange={(e) => handleStatusChange(e.target.value as TicketStatus)}
                  disabled={isChangingStatus}
                  className="bg-white/[0.06] border border-white/10 rounded-lg px-2 py-1 text-white text-xs focus:border-site-blue outline-none transition-colors duration-200 ease-site disabled:opacity-50"
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status} className="bg-site-dark text-white">
                      {STATUS_LABELS[status]}
                    </option>
                  ))}
                </select>
                {isChangingStatus && (
                  <span className="text-white/30 text-xs">Сохранение...</span>
                )}
              </div>

              {/* Current status badge */}
              <span className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider ${STATUS_COLORS[ticket.status]}`}>
                {STATUS_LABELS[ticket.status]}
              </span>
            </div>
          </>
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

export default AdminTicketDetailPage;
