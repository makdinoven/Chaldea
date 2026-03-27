import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchMyTickets,
  createTicket,
  selectTickets,
  selectTicketsPagination,
  selectTicketsLoading,
  selectTicketsError,
  clearTicketError,
} from '../../redux/slices/ticketSlice';
import type { TicketStatus, TicketCategory, CreateTicketPayload } from '../../types/ticket';
import CreateTicketModal from './CreateTicketModal';
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

const formatDate = (dateStr: string): string => {
  try {
    const date = new Date(dateStr);
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${day}.${month}.${year} ${hours}:${minutes}`;
  } catch {
    return '';
  }
};

const TicketListPage = () => {
  const dispatch = useAppDispatch();
  const tickets = useAppSelector(selectTickets);
  const pagination = useAppSelector(selectTicketsPagination);
  const isLoading = useAppSelector(selectTicketsLoading);
  const error = useAppSelector(selectTicketsError);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [statusFilter, setStatusFilter] = useState<TicketStatus | ''>('');

  useEffect(() => {
    dispatch(fetchMyTickets(statusFilter ? { status: statusFilter } : undefined));
  }, [dispatch, statusFilter]);

  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearTicketError());
    }
  }, [error, dispatch]);

  const handleCreateTicket = useCallback(
    (data: CreateTicketPayload) => {
      dispatch(createTicket(data))
        .unwrap()
        .then(() => {
          setShowCreateModal(false);
          toast.success('Тикет создан');
        })
        .catch(() => {
          // Error handled by Redux rejected case
        });
    },
    [dispatch],
  );

  const handlePageChange = useCallback(
    (page: number) => {
      dispatch(fetchMyTickets({ page, ...(statusFilter ? { status: statusFilter } : {}) }));
    },
    [dispatch, statusFilter],
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="w-full max-w-[900px] mx-auto rounded-card border border-white/10 bg-black/50 p-4 sm:p-6"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <h1 className="gold-text text-3xl font-medium uppercase">Поддержка</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-blue !px-5 !py-2.5 !text-sm self-start sm:self-auto"
        >
          Создать тикет
        </button>
      </div>

      {/* Status filter */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={() => setStatusFilter('')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium uppercase tracking-wider transition-colors duration-200 ease-site cursor-pointer ${
            statusFilter === '' ? 'bg-white/15 text-white' : 'bg-white/[0.05] text-white/40 hover:text-white/70'
          }`}
        >
          Все
        </button>
        {(Object.keys(STATUS_LABELS) as TicketStatus[]).map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium uppercase tracking-wider transition-colors duration-200 ease-site cursor-pointer ${
              statusFilter === status ? 'bg-white/15 text-white' : 'bg-white/[0.05] text-white/40 hover:text-white/70'
            }`}
          >
            {STATUS_LABELS[status]}
          </button>
        ))}
      </div>

      {/* Loading state */}
      {isLoading && tickets.length === 0 && (
        <p className="text-white/40 text-sm">Загрузка...</p>
      )}

      {/* Empty state */}
      {!isLoading && tickets.length === 0 && (
        <div className="text-center py-16">
          <p className="text-white/40 text-base mb-2">У вас пока нет тикетов</p>
          <p className="text-white/25 text-sm">Создайте тикет, чтобы обратиться в поддержку</p>
        </div>
      )}

      {/* Ticket list */}
      <div className="flex flex-col gap-3">
        {tickets.map((ticket) => (
          <Link
            key={ticket.id}
            to={`/support/${ticket.id}`}
            className="block bg-white/[0.04] border border-white/[0.06] rounded-card p-4 hover:bg-white/[0.07] transition-colors duration-200 ease-site"
          >
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider ${STATUS_COLORS[ticket.status]}`}>
                    {STATUS_LABELS[ticket.status]}
                  </span>
                  <span className="text-white/30 text-[10px] font-medium uppercase tracking-wider">
                    {CATEGORY_LABELS[ticket.category]}
                  </span>
                  <span className="text-white/20 text-[10px]">#{ticket.id}</span>
                </div>
                <h3 className="text-white text-sm font-medium truncate">
                  {ticket.subject}
                </h3>
                {ticket.last_message && (
                  <p className="text-white/35 text-xs mt-1 truncate">
                    <span className={ticket.last_message.is_admin ? 'text-site-blue/60' : 'text-white/40'}>
                      {ticket.last_message.sender_username}:
                    </span>{' '}
                    {ticket.last_message.content}
                  </p>
                )}
              </div>
              <div className="flex sm:flex-col items-center sm:items-end gap-2 sm:gap-1 flex-shrink-0">
                <span className="text-white/25 text-xs">
                  {formatDate(ticket.updated_at)}
                </span>
                {ticket.message_count > 0 && (
                  <span className="text-white/20 text-xs">
                    {ticket.message_count} {ticket.message_count === 1 ? 'сообщение' : 'сообщений'}
                  </span>
                )}
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Pagination */}
      {pagination.totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-6">
          {Array.from({ length: pagination.totalPages }, (_, i) => i + 1).map((page) => (
            <button
              key={page}
              onClick={() => handlePageChange(page)}
              className={`w-8 h-8 rounded-lg text-xs font-medium transition-colors duration-200 ease-site cursor-pointer ${
                page === pagination.page
                  ? 'bg-white/15 text-white'
                  : 'bg-white/[0.05] text-white/40 hover:text-white/70'
              }`}
            >
              {page}
            </button>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <CreateTicketModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSubmit={handleCreateTicket}
        isLoading={isLoading}
      />
    </motion.div>
  );
};

export default TicketListPage;
