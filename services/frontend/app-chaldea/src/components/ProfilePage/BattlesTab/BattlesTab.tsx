import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppSelector } from '../../../redux/store';

/* ── Types ── */

interface BattleHistoryItem {
  battle_id: number;
  opponent_names: string[];
  opponent_character_ids: number[];
  battle_type: string;
  result: 'victory' | 'defeat';
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

const BATTLE_TYPE_LABELS: Record<string, string> = {
  pve: 'PvE',
  pvp_training: 'Тренировочный',
  pvp_death: 'Смертельный',
  pvp_attack: 'Нападение',
};

const BATTLE_TYPE_COLORS: Record<string, string> = {
  pve: 'bg-site-blue/20 text-site-blue',
  pvp_training: 'bg-yellow-500/20 text-yellow-400',
  pvp_death: 'bg-site-red/20 text-site-red',
  pvp_attack: 'bg-purple-500/20 text-purple-400',
};

const RESULT_FILTER_OPTIONS = [
  { value: '', label: 'Все результаты' },
  { value: 'victory', label: 'Победы' },
  { value: 'defeat', label: 'Поражения' },
];

const TYPE_FILTER_OPTIONS = [
  { value: '', label: 'Все типы' },
  { value: 'pve', label: 'PvE' },
  { value: 'pvp_training', label: 'Тренировочный' },
  { value: 'pvp_death', label: 'Смертельный' },
  { value: 'pvp_attack', label: 'Нападение' },
];

const PER_PAGE = 20;

/* ── Helpers ── */

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
  const [inBattle, setInBattle] = useState(false);
  const [battleId, setBattleId] = useState<number | null>(null);
  const [history, setHistory] = useState<BattleHistoryItem[]>([]);
  const [stats, setStats] = useState<BattleStats>({ total: 0, wins: 0, losses: 0, winrate: 0 });
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [filterType, setFilterType] = useState('');
  const [filterResult, setFilterResult] = useState('');

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

  const fetchInBattle = useCallback(async () => {
    try {
      const res = await axios.get<InBattleResponse>(
        `/battles/character/${characterId}/in-battle`,
      );
      setInBattle(res.data.in_battle);
      setBattleId(res.data.battle_id);
    } catch {
      // Non-critical — silently ignore
    }
  }, [characterId]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([
        fetchInBattle(),
        fetchHistory(1, '', ''),
      ]);
      setLoading(false);
    };
    load();
  }, [fetchInBattle, fetchHistory]);

  const handleFilterTypeChange = (value: string) => {
    setFilterType(value);
    setPage(1);
    fetchHistory(1, value, filterResult);
  };

  const handleFilterResultChange = (value: string) => {
    setFilterResult(value);
    setPage(1);
    fetchHistory(1, filterType, value);
  };

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    setPage(newPage);
    fetchHistory(newPage, filterType, filterResult);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

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
      <div className="flex items-center justify-center gap-1 sm:gap-2 mt-6">
        <button
          onClick={() => handlePageChange(page - 1)}
          disabled={page <= 1}
          className="px-2 sm:px-3 py-1.5 rounded-card text-xs sm:text-sm text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-200"
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
              onClick={() => handlePageChange(p)}
              className={`w-7 h-7 sm:w-8 sm:h-8 rounded-card text-xs sm:text-sm font-medium transition-colors duration-200 ${
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
          onClick={() => handlePageChange(page + 1)}
          disabled={page >= totalPages}
          className="px-2 sm:px-3 py-1.5 rounded-card text-xs sm:text-sm text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-200"
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
      {/* Current Battle Card */}
      <div className="bg-black/50 rounded-card border border-gold/20 p-4">
        {inBattle && battleId ? (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h3 className="gold-text text-lg font-medium uppercase mb-1">
                Активный бой
              </h3>
              <p className="text-white/50 text-xs sm:text-sm">
                Вы сейчас участвуете в бою
              </p>
            </div>
            <Link
              to={`/location/${locationId}/battle/${battleId}`}
              className="btn-blue text-center text-sm px-5 py-2.5 shrink-0"
            >
              Перейти к бою
            </Link>
          </div>
        ) : (
          <p className="text-white/40 text-sm text-center py-1">
            Нет активного боя
          </p>
        )}
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-black/50 rounded-card border border-gold/20 p-3 sm:p-4 text-center">
          <p className="gold-text text-xl sm:text-2xl font-bold">{stats.total}</p>
          <p className="text-white/50 text-[10px] sm:text-xs uppercase tracking-wide mt-1">
            Всего боёв
          </p>
        </div>
        <div className="bg-black/50 rounded-card border border-gold/20 p-3 sm:p-4 text-center">
          <p className="gold-text text-xl sm:text-2xl font-bold">{stats.wins}</p>
          <p className="text-white/50 text-[10px] sm:text-xs uppercase tracking-wide mt-1">
            Побед
          </p>
        </div>
        <div className="bg-black/50 rounded-card border border-gold/20 p-3 sm:p-4 text-center">
          <p className="gold-text text-xl sm:text-2xl font-bold">{stats.losses}</p>
          <p className="text-white/50 text-[10px] sm:text-xs uppercase tracking-wide mt-1">
            Поражений
          </p>
        </div>
        <div className="bg-black/50 rounded-card border border-gold/20 p-3 sm:p-4 text-center">
          <p className="gold-text text-xl sm:text-2xl font-bold">{stats.winrate}%</p>
          <p className="text-white/50 text-[10px] sm:text-xs uppercase tracking-wide mt-1">
            Винрейт
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <select
          value={filterType}
          onChange={(e) => handleFilterTypeChange(e.target.value)}
          className="bg-black/60 border border-gold/20 rounded-card px-3 py-2 text-sm text-white appearance-none cursor-pointer hover:border-gold/40 transition-colors duration-200 flex-1"
        >
          {TYPE_FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-[#1a1a2e]">
              {opt.label}
            </option>
          ))}
        </select>
        <select
          value={filterResult}
          onChange={(e) => handleFilterResultChange(e.target.value)}
          className="bg-black/60 border border-gold/20 rounded-card px-3 py-2 text-sm text-white appearance-none cursor-pointer hover:border-gold/40 transition-colors duration-200 flex-1"
        >
          {RESULT_FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-[#1a1a2e]">
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* History List */}
      {history.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-16 h-16 text-white/10 mb-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
          <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase mb-2">
            {filterType || filterResult
              ? 'Нет боёв по фильтру'
              : 'Ещё не участвовал в боях'}
          </h2>
          <p className="text-white/50 text-sm">
            {filterType || filterResult
              ? 'Попробуйте изменить параметры фильтрации'
              : 'Начните свой первый бой, чтобы увидеть историю'}
          </p>
        </div>
      ) : (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.05 } },
          }}
          className="flex flex-col gap-3"
        >
          {history.map((item) => (
            <motion.div
              key={`${item.battle_id}-${item.result}`}
              variants={{
                hidden: { opacity: 0, y: 10 },
                visible: { opacity: 1, y: 0 },
              }}
              className={`bg-black/50 rounded-card p-3 sm:p-4 border transition-colors ${
                item.result === 'victory'
                  ? 'border-green-500/20'
                  : 'border-site-red/20'
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                {/* Date */}
                <span className="text-white/40 text-xs shrink-0 order-2 sm:order-1 sm:w-36">
                  {formatDate(item.finished_at)}
                </span>

                {/* Opponents */}
                <span className="text-white text-sm flex-1 order-1 sm:order-2">
                  {item.opponent_names.length > 0
                    ? item.opponent_names.join(', ')
                    : 'Неизвестный противник'}
                </span>

                {/* Badges */}
                <div className="flex items-center gap-2 shrink-0 order-3">
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium uppercase ${
                      BATTLE_TYPE_COLORS[item.battle_type] ?? 'bg-white/10 text-white/60'
                    }`}
                  >
                    {BATTLE_TYPE_LABELS[item.battle_type] ?? item.battle_type}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${
                      item.result === 'victory'
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-red-500/20 text-site-red'
                    }`}
                  >
                    {item.result === 'victory' ? 'Победа' : 'Поражение'}
                  </span>
                </div>
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
