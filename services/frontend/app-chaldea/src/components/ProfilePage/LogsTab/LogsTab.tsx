import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { FileText, Shield, Package, Star, Activity } from 'react-feather';
import { Activity as ActivityIcon } from 'lucide-react';
import {
  fetchCharacterLogs,
  CharacterLogEntry,
} from '../../../api/characterLogs';
import { formatRelativeTime } from '../../../utils/serverDate';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import FilterChips, { type FilterChipItem } from '../shared/FilterChips';
import EmptyState from '../shared/EmptyState';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';
import PanelScrollArea from '../shared/PanelScrollArea';
import PanelToolbar from '../shared/PanelToolbar';
import ProfileCard from '../shared/ProfileCard';

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

const FILTER_CHIP_ITEMS: FilterChipItem[] = EVENT_TYPE_FILTER_OPTIONS.map((opt) => ({
  key: opt.value,
  label: opt.label,
}));

const TAB_MOTION = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: 'easeOut' as const },
};

const PANEL_TITLE = 'Логи персонажа';

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
      return 'bg-site-blue/15 text-site-blue';
    case 'pvp_battle':
    case 'mob_kill':
      return 'bg-site-red/15 text-site-red';
    case 'item_acquired':
      return 'bg-gold/15 text-gold';
    case 'level_up':
      return 'bg-stat-energy/15 text-stat-energy';
    default:
      return 'bg-white/10 text-white/60';
  }
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

  const panelIcon = <ActivityIcon size={18} strokeWidth={1.8} className="text-gold shrink-0" />;

  /* ── Loading state ── */

  if (loading) {
    return (
      <motion.div {...TAB_MOTION}>
        <PanelShell title={PANEL_TITLE} icon={panelIcon}>
          <LoadingState />
        </PanelShell>
      </motion.div>
    );
  }

  /* ── Render ── */

  return (
    <motion.div {...TAB_MOTION}>
      <PanelShell
        title={PANEL_TITLE}
        icon={panelIcon}
        headerExtra={
          <PanelCounter>
            {logs.length}/{total}
          </PanelCounter>
        }
        className={PANEL_DESKTOP_HEIGHT_CLASS}
        bodyClassName="flex-1 min-h-0 flex flex-col"
      >
        {/* Filter */}
        <PanelToolbar>
          <FilterChips
            items={FILTER_CHIP_ITEMS}
            active={filterType}
            onChange={handleFilterChange}
            className="min-w-0 max-w-full"
          />
        </PanelToolbar>

        <PanelScrollArea>
          {/* Empty state */}
          {logs.length === 0 ? (
            <EmptyState
              icon={<Activity size={32} strokeWidth={1.5} className="text-white/20" />}
              message={filterType ? 'Нет записей по фильтру' : 'Записей пока нет'}
              hint={
                filterType
                  ? 'Попробуйте изменить параметры фильтрации'
                  : 'Здесь будут отображаться события персонажа'
              }
            />
          ) : (
            <div className="flex flex-col gap-4">
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
                  >
                    <ProfileCard className="p-3 sm:p-4 flex items-start gap-3">
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
                          {formatRelativeTime(entry.created_at, { style: 'long', yesterday: true })}
                        </p>
                      </div>
                    </ProfileCard>
                  </motion.div>
                ))}
              </motion.div>

              {/* Load more */}
              {hasMore && (
                <div className="flex justify-center">
                  <button
                    type="button"
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="btn-line w-full sm:w-auto px-6 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loadingMore ? (
                      <span className="flex items-center justify-center gap-2">
                        <LoadingState size="xs" />
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
            </div>
          )}
        </PanelScrollArea>
      </PanelShell>
    </motion.div>
  );
};

export default LogsTab;
