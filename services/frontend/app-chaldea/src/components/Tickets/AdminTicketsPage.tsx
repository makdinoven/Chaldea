import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchAdminTickets,
  selectAdminTickets,
  selectAdminTicketsPagination,
  selectTicketsLoading,
  selectTicketsError,
  clearTicketError,
} from '../../redux/slices/ticketSlice';
import type { TicketStatus, TicketCategory } from '../../types/ticket';
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

const CATEGORY_OPTIONS: { value: TicketCategory | ''; label: string }[] = [
  { value: '', label: 'Все категории' },
  { value: 'bug', label: 'Баг / Ошибка' },
  { value: 'question', label: 'Вопрос' },
  { value: 'suggestion', label: 'Предложение' },
  { value: 'complaint', label: 'Жалоба' },
  { value: 'other', label: 'Другое' },
];

const formatDate = (dateStr: string): string => {
  try {
    const date = new Date(dateStr);
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${day}.${month} ${hours}:${minutes}`;
  } catch {
    return '';
  }
};

const AdminTicketsPage = () => {
  const dispatch = useAppDispatch();
  const tickets = useAppSelector(selectAdminTickets);
  const pagination = useAppSelector(selectAdminTicketsPagination);
  const isLoading = useAppSelector(selectTicketsLoading);
  const error = useAppSelector(selectTicketsError);

  const [statusFilter, setStatusFilter] = useState<TicketStatus | ''>('');
  const [categoryFilter, setCategoryFilter] = useState<TicketCategory | ''>('');

  useEffect(() => {
    const params: { status?: TicketStatus; category?: TicketCategory } = {};
    if (statusFilter) params.status = statusFilter;
    if (categoryFilter) params.category = categoryFilter;
    dispatch(fetchAdminTickets(Object.keys(params).length > 0 ? params : undefined));
  }, [dispatch, statusFilter, categoryFilter]);

  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearTicketError());
    }
  }, [error, dispatch]);

  const handlePageChange = useCallback(
    (page: number) => {
      const params: { page: number; status?: TicketStatus; category?: TicketCategory } = { page };
      if (statusFilter) params.status = statusFilter;
      if (categoryFilter) params.category = categoryFilter;
      dispatch(fetchAdminTickets(params));
    },
    [dispatch, statusFilter, categoryFilter],
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="w-full max-w-[1240px] mx-auto"
    >
      <h1 className="gold-text text-3xl font-medium uppercase mb-8">
        Тикеты поддержки
      </h1>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        {/* Status filter */}
        <div className="flex flex-wrap gap-2">
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

        {/* Category filter */}
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value as TicketCategory | '')}
          className="bg-white/[0.06] border border-white/10 rounded-lg px-3 py-1.5 text-white text-xs focus:border-site-blue outline-none transition-colors duration-200 ease-site self-start"
        >
          {CATEGORY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-site-dark text-white">
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Loading */}
      {isLoading && tickets.length === 0 && (
        <p className="text-white/40 text-sm">Загрузка...</p>
      )}

      {/* Empty */}
      {!isLoading && tickets.length === 0 && (
        <p className="text-white/40 text-sm">Нет тикетов</p>
      )}

      {/* Ticket table/cards */}
      <div className="flex flex-col gap-2">
        {/* Desktop header */}
        <div className="hidden md:grid md:grid-cols-[60px_1fr_140px_120px_100px_100px] gap-3 px-4 py-2 text-white/30 text-xs font-medium uppercase tracking-wider">
          <span>#</span>
          <span>Тема</span>
          <span>Пользователь</span>
          <span>Категория</span>
          <span>Статус</span>
          <span>Обновлён</span>
        </div>

        {tickets.map((ticket) => (
          <Link
            key={ticket.id}
            to={`/admin/tickets/${ticket.id}`}
            className="block bg-white/[0.04] border border-white/[0.06] rounded-card hover:bg-white/[0.07] transition-colors duration-200 ease-site"
          >
            {/* Desktop row */}
            <div className="hidden md:grid md:grid-cols-[60px_1fr_140px_120px_100px_100px] gap-3 px-4 py-3 items-center">
              <span className="text-white/30 text-xs">{ticket.id}</span>
              <div className="min-w-0">
                <p className="text-white text-sm font-medium truncate">{ticket.subject}</p>
                {ticket.last_message && (
                  <p className="text-white/30 text-xs truncate mt-0.5">
                    {ticket.last_message.sender_username}: {ticket.last_message.content}
                  </p>
                )}
              </div>
              <span className="text-white/60 text-xs truncate">{ticket.username}</span>
              <span className="text-white/40 text-xs">{CATEGORY_LABELS[ticket.category]}</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider inline-block w-fit ${STATUS_COLORS[ticket.status]}`}>
                {STATUS_LABELS[ticket.status]}
              </span>
              <span className="text-white/25 text-xs">{formatDate(ticket.updated_at)}</span>
            </div>

            {/* Mobile card */}
            <div className="md:hidden p-4">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider ${STATUS_COLORS[ticket.status]}`}>
                  {STATUS_LABELS[ticket.status]}
                </span>
                <span className="text-white/30 text-[10px]">{CATEGORY_LABELS[ticket.category]}</span>
                <span className="text-white/20 text-[10px]">#{ticket.id}</span>
              </div>
              <p className="text-white text-sm font-medium truncate">{ticket.subject}</p>
              <div className="flex items-center justify-between mt-1">
                <span className="text-white/50 text-xs">{ticket.username}</span>
                <span className="text-white/25 text-xs">{formatDate(ticket.updated_at)}</span>
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
    </motion.div>
  );
};

export default AdminTicketsPage;
