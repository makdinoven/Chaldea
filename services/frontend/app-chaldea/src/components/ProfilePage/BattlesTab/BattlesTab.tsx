// ProfilePage BattlesTab — redesigned per Claude Design mock (FEAT-151).
// Active-battle preview card + 4 stat tiles + chip filters + history rows.
import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { History, Swords } from 'lucide-react';
import { useAppSelector } from '../../../redux/store';
import { fetchBattlePreview, type BattlePreview } from '../../../api/battles';
import FilterChips, { type FilterChipItem } from '../shared/FilterChips';
import StatTile from '../shared/StatTile';
import EmptyState from '../shared/EmptyState';
import ActiveBattleCard from './ActiveBattleCard';

/* ── Types ── */

interface BattleHistoryItem {
  battle_id: number;
  opponent_names: string[];
  opponent_character_ids: number[];
  battle_type: string;
  result: string; // 'victory' | 'defeat' (+ forward-compatible fallback)
  finished_at: string;
}

interface BattleStats {
  total: number;
  wins: number;
  losses: number;
  winrate: number;
}

interface BattleHistoryResponse {
  history: BattleHistoryItem[];
  stats: BattleStats;
  page: number;
  per_page: number;
  total_count: number;
  total_pages: number;
}

interface InBattleResponse {
  in_battle: boolean;
  battle_id: number | null;
}

interface BattlesTabProps {
  characterId: number;
}

/* ── Constants ── */

const ALL_FILTER_KEY = 'all';

const BATTLE_TYPE_LABELS: Record<string, string> = {
  pve: 'PvE',
  pvp_training: 'Тренировочный',
  pvp_death: 'Смертельный',
  pvp_attack: 'Нападение',
};

const BATTLE_TYPE_BADGE: Record<string, string> = {
  pve: 'text-site-blue bg-site-blue/10',
  pvp_training: 'text-gold bg-gold/10',
  pvp_death: 'text-stat-hp bg-stat-hp/10',
  pvp_attack: 'text-site-red bg-site-red/10',
};

const RESULT_LABELS: Record<string, string> = {
  victory: 'Победа',
  defeat: 'Поражение',
  draw: 'Ничья',
};

const RESULT_PILL: Record<string, string> = {
  victory: 'text-stat-energy bg-stat-energy/10',
  defeat: 'text-site-red bg-site-red/10',
};

const TYPE_FILTERS: FilterChipItem[] = [
  { key: ALL_FILTER_KEY, label: 'Все типы' },
  { key: 'pve', label: 'PvE', dot: 'bg-site-blue' },
  { key: 'pvp_training', label: 'Тренировочный', dot: 'bg-gold' },
  { key: 'pvp_death', label: 'Смертельный', dot: 'bg-stat-hp' },
  { key: 'pvp_attack', label: 'Нападение', dot: 'bg-site-red' },
];

const RESULT_FILTERS: FilterChipItem[] = [
  { key: ALL_FILTER_KEY, label: 'Все результаты' },
  { key: 'victory', label: 'Победы', dot: 'bg-stat-energy' },
  { key: 'defeat', label: 'Поражения', dot: 'bg-site-red' },
];

const PER_PAGE = 20;

/* ── Helpers ── */

/** Filter chip key → history-endpoint query param value ('' = no param). */
const toParam = (filterKey: string): string =>
  filterKey === ALL_FILTER_KEY ? '' : filterKey;

const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr);
  const months = [
    'янв', 'фев', 'мар', 'апр', 'май', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
  ];
  const day = date.getDate();
  const month = months[date.getMonth()];
  const year = date.getFullYear();
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${day} ${month} ${year}, ${hours}:${minutes}`;
};

/* ── Component ── */

const BattlesTab = ({ characterId }: BattlesTabProps) => {
  const character = useAppSelector((state) => state.user.character);
  const locationId = character?.current_location?.id ?? 0;

  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<BattlePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [history, setHistory] = useState<BattleHistoryItem[]>([]);
  const [stats, setStats] = useState<BattleStats>({ total: 0, wins: 0, losses: 0, winrate: 0 });
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [filterType, setFilterType] = useState(ALL_FILTER_KEY);
  const [filterResult, setFilterResult] = useState(ALL_FILTER_KEY);

  const fetchHistory = useCallback(async (
    pageNum: number,
    battleType: string,
    result: string,
  ) => {
    try {
      const params: Record<string, string | number> = {
        page: pageNum,
        per_page: PER_PAGE,
      };
      if (battleType) params.battle_type = battleType;
      if (result) params.result = result;

      const res = await axios.get<BattleHistoryResponse>(
        `/battles/history/${characterId}`,
        { params },
      );
      setHistory(res.data.history);
      setStats(res.data.stats);
      setPage(res.data.page);
      setTotalPages(res.data.total_pages);
      setTotalCount(res.data.total_count);
    } catch {
      toast.error('Не удалось загрузить историю боёв');
    }
  }, [characterId]);

  // Mount flow: /in-battle → if in battle, fetch /preview once (no polling).
  const loadActiveBattle = useCallback(async (): Promise<{
    preview: BattlePreview | null;
    error: string | null;
  }> => {
    let inBattleRes: InBattleResponse;
    try {
      const res = await axios.get<InBattleResponse>(
        `/battles/character/${characterId}/in-battle`,
      );
      inBattleRes = res.data;
    } catch {
      return { preview: null, error: 'Не удалось проверить статус боя' };
    }

    if (!inBattleRes.in_battle || !inBattleRes.battle_id) {
      return { preview: null, error: null };
    }

    try {
      const data = await fetchBattlePreview(inBattleRes.battle_id);
      return { preview: data, error: null };
    } catch (err) {
      // 404 = battle finished between /in-battle and /preview (expected race)
      // → silent fallback to the «Нет активного боя» row, no toast.
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        return { preview: null, error: null };
      }
      return { preview: null, error: 'Не удалось загрузить данные активного боя' };
    }
  }, [characterId]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const [activeBattle] = await Promise.all([
        loadActiveBattle(),
        fetchHistory(1, '', ''),
      ]);
      setPreview(activeBattle.preview);
      setPreviewError(activeBattle.error);
      setLoading(false);
    };
    load();
  }, [loadActiveBattle, fetchHistory]);

  const handleFilterTypeChange = (key: string) => {
    setFilterType(key);
    setPage(1);
    fetchHistory(1, toParam(key), toParam(filterResult));
  };

  const handleFilterResultChange = (key: string) => {
    setFilterResult(key);
    setPage(1);
    fetchHistory(1, toParam(filterType), toParam(key));
  };

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    setPage(newPage);
    fetchHistory(newPage, toParam(filterType), toParam(filterResult));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const hasActiveFilter = filterType !== ALL_FILTER_KEY || filterResult !== ALL_FILTER_KEY;
  const battleUrl = preview
    ? `/location/${preview.location_id ?? locationId}/battle/${preview.battle_id}`
    : '';

  const renderPagination = () => {
    if (totalPages <= 1) return null;

    const pages: (number | string)[] = [];
    const maxVisible = 5;

    if (totalPages <= maxVisible + 2) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (page > 3) pages.push('...');
      const start = Math.max(2, page - 1);
      const end = Math.min(totalPages - 1, page + 1);
      for (let i = start; i <= end; i++) pages.push(i);
      if (page < totalPages - 2) pages.push('...');
      pages.push(totalPages);
    }

    return (
      <div className="flex items-center justify-center gap-1 sm:gap-2 mt-2">
        <button
          type="button"
          onClick={() => handlePageChange(page - 1)}
          disabled={page <= 1}
          className="px-2 sm:px-3 py-1.5 rounded-card text-xs sm:text-sm text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-200 ease-site"
        >
          Назад
        </button>
        {pages.map((p, idx) =>
          typeof p === 'string' ? (
            <span key={`ellipsis-${idx}`} className="px-1 text-white/30 text-xs sm:text-sm">
              ...
            </span>
          ) : (
            <button
              key={p}
              type="button"
              onClick={() => handlePageChange(p)}
              className={`w-7 h-7 sm:w-8 sm:h-8 rounded-card text-xs sm:text-sm font-medium transition-colors duration-200 ease-site ${
                p === page
                  ? 'bg-gold/20 text-gold border border-gold/40'
                  : 'text-white/60 hover:text-white hover:bg-white/10'
              }`}
            >
              {p}
            </button>
          ),
        )}
        <button
          type="button"
          onClick={() => handlePageChange(page + 1)}
          disabled={page >= totalPages}
          className="px-2 sm:px-3 py-1.5 rounded-card text-xs sm:text-sm text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-200 ease-site"
        >
          Далее
        </button>
      </div>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-4"
    >
      {/* Header */}
      <div className="flex items-center gap-3.5">
        <h3 className="gold-text text-sm font-medium uppercase tracking-[0.12em]">
          Бои
        </h3>
        <span className="font-mono tabular-nums text-[13px] text-white/50">
          {stats.total}
        </span>
      </div>

      {/* Active battle: full preview card / error row / slim empty row */}
      {preview ? (
        <ActiveBattleCard preview={preview} battleUrl={battleUrl} />
      ) : previewError ? (
        <div className="flex items-center px-5 py-4 rounded-card bg-site-bg border border-site-red/30">
          <span className="text-sm text-site-red">{previewError}</span>
        </div>
      ) : (
        <div className="flex items-center px-5 py-4 rounded-card bg-site-bg border border-gold/[0.16]">
          <span className="text-sm text-white/40">Нет активного боя</span>
        </div>
      )}

      {/* Stats tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile value={stats.total} label="Всего боёв" />
        <StatTile value={stats.wins} label="Победы" />
        <StatTile value={stats.losses} label="Поражения" />
        <StatTile value={`${stats.winrate}%`} label="Винрейт" />
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-2.5">
        <FilterChips
          items={TYPE_FILTERS}
          active={filterType}
          onChange={handleFilterTypeChange}
        />
        <FilterChips
          items={RESULT_FILTERS}
          active={filterResult}
          onChange={handleFilterResultChange}
        />
      </div>

      {/* History */}
      {history.length === 0 ? (
        <EmptyState
          icon={
            hasActiveFilter ? (
              <Swords size={32} strokeWidth={1.5} className="text-white/20" />
            ) : (
              <History size={32} strokeWidth={1.5} className="text-white/20" />
            )
          }
          message={
            hasActiveFilter
              ? 'Нет боёв по фильтру — попробуйте изменить параметры'
              : 'Ещё не участвовал в боях — начните свой первый бой, чтобы увидеть историю'
          }
        />
      ) : (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.05 } },
          }}
          className="flex flex-col gap-2.5"
        >
          {history.map((item) => (
            <motion.div
              key={`${item.battle_id}-${item.result}`}
              variants={{
                hidden: { opacity: 0, y: 10 },
                visible: { opacity: 1, y: 0 },
              }}
              className={`flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 px-4 py-3.5 sm:px-[18px] rounded-card bg-site-bg border ${
                item.result === 'victory'
                  ? 'border-stat-energy/20'
                  : item.result === 'defeat'
                    ? 'border-site-red/20'
                    : 'border-white/10'
              }`}
            >
              {/* Date */}
              <span className="font-mono tabular-nums text-xs text-white/40 shrink-0 order-2 sm:order-1 sm:w-[132px]">
                {formatDate(item.finished_at)}
              </span>

              {/* Opponents */}
              <span className="text-sm text-white flex-1 min-w-0 truncate order-1 sm:order-2">
                {item.opponent_names.length > 0
                  ? item.opponent_names.join(', ')
                  : 'Неизвестный противник'}
              </span>

              {/* Type badge + result pill */}
              <div className="flex items-center gap-2 shrink-0 order-3">
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-[0.04em] ${
                    BATTLE_TYPE_BADGE[item.battle_type] ?? 'text-white/60 bg-white/10'
                  }`}
                >
                  {BATTLE_TYPE_LABELS[item.battle_type] ?? item.battle_type}
                </span>
                <span
                  className={`sm:w-[104px] text-center px-2.5 py-1 rounded-full text-[11px] font-medium uppercase tracking-[0.04em] ${
                    RESULT_PILL[item.result] ?? 'text-white/60 bg-white/10'
                  }`}
                >
                  {RESULT_LABELS[item.result] ?? item.result}
                </span>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* Pagination */}
      {renderPagination()}

      {/* Page info */}
      {totalCount > 0 && (
        <p className="text-white/30 text-xs text-center">
          Страница {page} из {totalPages} ({totalCount} записей)
        </p>
      )}
    </motion.div>
  );
};

export default BattlesTab;
