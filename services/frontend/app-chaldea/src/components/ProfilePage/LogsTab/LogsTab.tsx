import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { FileText, Shield, Package, Star, Activity } from 'react-feather';
import {
  fetchCharacterLogs,
  CharacterLogEntry,
} from '../../../api/characterLogs';

/* ── Types ── */

interface LogsTabProps {
  characterId: number;
}

/* ── Constants ── */

const PAGE_SIZE = 50;

const EVENT_TYPE_FILTER_OPTIONS = [
  { value: '', label: 'Все' },
  { value: 'rp_post', label: 'Посты' },
  { value: 'pvp_battle', label: 'Бои' },
  { value: 'item_acquired', label: 'Предметы' },
  { value: 'level_up', label: 'Уровень' },
];

/* ── Helpers ── */

const getEventIcon = (eventType: string) => {
  switch (eventType) {
    case 'rp_post':
      return <FileText size={16} />;
    case 'pvp_battle':
    case 'mob_kill':
      return <Shield size={16} />;
    case 'item_acquired':
      return <Package size={16} />;
    case 'level_up':
      return <Star size={16} />;
    default:
      return <Activity size={16} />;
  }
};

const getEventColor = (eventType: string): string => {
  switch (eventType) {
    case 'rp_post':
      return 'bg-site-blue/20 text-site-blue';
    case 'pvp_battle':
    case 'mob_kill':
      return 'bg-site-red/20 text-site-red';
    case 'item_acquired':
      return 'bg-yellow-500/20 text-yellow-400';
    case 'level_up':
      return 'bg-green-500/20 text-green-400';
    default:
      return 'bg-white/10 text-white/60';
  }
};

const formatRelativeTime = (dateStr: string): string => {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return 'только что';
  if (diffMinutes < 60) {
    if (diffMinutes === 1) return '1 минуту назад';
    if (diffMinutes < 5) return `${diffMinutes} минуты назад`;
    return `${diffMinutes} минут назад`;
  }
  if (diffHours < 24) {
    if (diffHours === 1) return '1 час назад';
    if (diffHours < 5) return `${diffHours} часа назад`;
    return `${diffHours} часов назад`;
  }
  if (diffDays === 1) return 'вчера';
  if (diffDays < 7) {
    if (diffDays < 5) return `${diffDays} дня назад`;
    return `${diffDays} дней назад`;
  }

  const months = [
    'янв', 'фев', 'мар', 'апр', 'май', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
  ];
  const day = date.getDate();
  const month = months[date.getMonth()];
  const year = date.getFullYear();
  const currentYear = now.getFullYear();

  if (year === currentYear) return `${day} ${month}`;
  return `${day} ${month} ${year}`;
};

/* ── Component ── */

const LogsTab = ({ characterId }: LogsTabProps) => {
  const [logs, setLogs] = useState<CharacterLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [filterType, setFilterType] = useState('');

  const loadLogs = useCallback(
    async (newOffset: number, eventType: string, append: boolean) => {
      try {
        const res = await fetchCharacterLogs(
          characterId,
          PAGE_SIZE,
          newOffset,
          eventType || undefined,
        );
        if (append) {
          setLogs((prev) => [...prev, ...res.logs]);
        } else {
          setLogs(res.logs);
        }
        setTotal(res.total);
        setOffset(newOffset + res.logs.length);
      } catch {
        toast.error('Не удалось загрузить логи персонажа');
      }
    },
    [characterId],
  );

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await loadLogs(0, filterType, false);
      setLoading(false);
    };
    init();
  }, [loadLogs, filterType]);

  const handleFilterChange = (value: string) => {
    setFilterType(value);
    setOffset(0);
    setLogs([]);
  };

  const handleLoadMore = async () => {
    setLoadingMore(true);
    await loadLogs(offset, filterType, true);
    setLoadingMore(false);
  };

  const hasMore = logs.length < total;

  /* ── Loading state ── */

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  /* ── Render ── */

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-4"
    >
      {/* Filter */}
      <div className="flex">
        <select
          value={filterType}
          onChange={(e) => handleFilterChange(e.target.value)}
          className="bg-black/60 border border-gold/20 rounded-card px-3 py-2 text-sm text-white appearance-none cursor-pointer hover:border-gold/40 transition-colors duration-200 w-full sm:w-auto sm:min-w-[200px]"
        >
          {EVENT_TYPE_FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-[#1a1a2e]">
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Empty state */}
      {logs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <Activity className="w-16 h-16 text-white/10 mb-4" strokeWidth={1} />
          <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase mb-2">
            {filterType ? 'Нет записей по фильтру' : 'Записей пока нет'}
          </h2>
          <p className="text-white/50 text-sm">
            {filterType
              ? 'Попробуйте изменить параметры фильтрации'
              : 'Здесь будут отображаться события персонажа'}
          </p>
        </div>
      ) : (
        <>
          {/* Log entries */}
          <motion.div
            initial="hidden"
            animate="visible"
            variants={{
              hidden: {},
              visible: { transition: { staggerChildren: 0.04 } },
            }}
            className="flex flex-col gap-2"
          >
            {logs.map((entry) => (
              <motion.div
                key={entry.id}
                variants={{
                  hidden: { opacity: 0, y: 10 },
                  visible: { opacity: 1, y: 0 },
                }}
                className="bg-black/50 rounded-card border border-gold/10 p-3 sm:p-4 flex items-start gap-3 transition-colors hover:border-gold/20"
              >
                {/* Icon */}
                <div
                  className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${getEventColor(entry.event_type)}`}
                >
                  {getEventIcon(entry.event_type)}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm leading-relaxed break-words">
                    {entry.description}
                  </p>
                  <p className="text-white/30 text-xs mt-1">
                    {formatRelativeTime(entry.created_at)}
                  </p>
                </div>
              </motion.div>
            ))}
          </motion.div>

          {/* Load more */}
          {hasMore && (
            <div className="flex justify-center pt-2">
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="btn-line px-6 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loadingMore ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Загрузка...
                  </span>
                ) : (
                  'Загрузить ещё'
                )}
              </button>
            </div>
          )}

          {/* Entry count */}
          <p className="text-white/30 text-xs text-center">
            Показано {logs.length} из {total}
          </p>
        </>
      )}
    </motion.div>
  );
};

export default LogsTab;
