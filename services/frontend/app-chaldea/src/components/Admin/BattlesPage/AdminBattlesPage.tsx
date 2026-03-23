import { Fragment, useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import { BASE_URL_BATTLES } from '../../../api/api';

// --- Types ---

interface BattleParticipant {
  participant_id: number;
  character_id: number;
  character_name: string;
  level: number;
  team: number;
  is_npc: boolean;
}

interface BattleListItem {
  id: number;
  status: string;
  battle_type: string;
  created_at: string;
  updated_at: string;
  participants: BattleParticipant[];
}

interface BattleListResponse {
  battles: BattleListItem[];
  total: number;
  page: number;
  per_page: number;
}

interface RuntimeParticipant {
  hp: number;
  mana: number;
  energy: number;
  stamina: number;
  max_hp: number;
  max_mana: number;
  max_energy: number;
  max_stamina: number;
  cooldowns: Record<string, unknown>;
  fast_slots: unknown[];
}

interface BattleRuntime {
  turn_number: number;
  deadline_at: string;
  current_actor: number;
  next_actor: number;
  first_actor: number;
  turn_order: number[];
  total_turns: number;
  last_turn: number;
  participants: Record<string, RuntimeParticipant>;
  active_effects: Record<string, unknown>;
}

interface SnapshotParticipant {
  participant_id: number;
  character_id: number;
  name: string;
  avatar: string | null;
  attributes: Record<string, number>;
}

interface BattleStateResponse {
  battle: {
    id: number;
    status: string;
    battle_type: string;
    created_at: string;
  };
  snapshot: SnapshotParticipant[] | null;
  runtime: BattleRuntime | null;
  has_redis_state: boolean;
}

// --- Constants ---

const BATTLE_TYPE_OPTIONS = [
  { value: '', label: 'Все' },
  { value: 'pve', label: 'PvE' },
  { value: 'pvp_training', label: 'Тренировочный' },
  { value: 'pvp_death', label: 'Смертельный' },
  { value: 'pvp_attack', label: 'Нападение' },
];

const BATTLE_TYPE_BADGES: Record<string, { label: string; classes: string }> = {
  pve: { label: 'PvE', classes: 'bg-white/20 text-white' },
  pvp_training: { label: 'Тренировочный', classes: 'bg-blue-500/30 text-blue-300' },
  pvp_death: { label: 'Смертельный', classes: 'bg-red-500/30 text-red-300' },
  pvp_attack: { label: 'Нападение', classes: 'bg-orange-500/30 text-orange-300' },
};

const STATUS_LABELS: Record<string, string> = {
  pending: 'Ожидание',
  in_progress: 'В бою',
};

const REFRESH_INTERVAL_MS = 10_000;
const PER_PAGE = 20;

// --- Helpers ---

const formatDate = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleString('ru-RU');
  } catch {
    return dateStr;
  }
};

const getHpBarColor = (percent: number) => {
  if (percent < 20) return 'bg-red-500';
  if (percent <= 50) return 'bg-yellow-500';
  return 'bg-green-500';
};

const calcPercent = (current: number, max: number) =>
  max > 0 ? Math.round((current / max) * 100) : 0;

// --- Sub-components ---

interface ResourceBarProps {
  label: string;
  current: number;
  max: number;
  barClass: string;
  dynamicColor?: boolean;
}

const ResourceBar = ({ label, current, max, barClass, dynamicColor }: ResourceBarProps) => {
  const pct = calcPercent(current, max);
  const color = dynamicColor ? getHpBarColor(pct) : barClass;
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between text-xs text-white/60">
        <span>{label}</span>
        <span>{current}/{max}</span>
      </div>
      <div className="h-2 rounded-full bg-white/10 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
};

interface BattleDetailPanelProps {
  battleId: number;
  onForceFinish: () => void;
}

const BattleDetailPanel = ({ battleId, onForceFinish }: BattleDetailPanelProps) => {
  const [state, setState] = useState<BattleStateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [finishing, setFinishing] = useState(false);

  const fetchState = useCallback(async () => {
    try {
      const { data } = await axios.get<BattleStateResponse>(
        `${BASE_URL_BATTLES}/battles/admin/${battleId}/state`,
      );
      setState(data);
      setError(null);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || 'Не удалось загрузить состояние боя');
    } finally {
      setLoading(false);
    }
  }, [battleId]);

  useEffect(() => {
    fetchState();
    const id = setInterval(fetchState, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchState]);

  const handleForceFinish = async () => {
    setFinishing(true);
    try {
      await axios.post(`${BASE_URL_BATTLES}/battles/admin/${battleId}/force-finish`);
      toast.success('Бой принудительно завершён');
      setConfirmOpen(false);
      onForceFinish();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Ошибка при завершении боя');
    } finally {
      setFinishing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <div className="w-6 h-6 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return <p className="text-site-red text-sm py-4 px-4">{error}</p>;
  }

  if (!state) return null;

  const { runtime, snapshot, has_redis_state } = state;

  // Build participant name map from snapshot
  const nameMap: Record<number, string> = {};
  if (snapshot) {
    for (const p of snapshot) {
      nameMap[p.participant_id] = p.name;
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="overflow-hidden"
    >
      <div className="px-4 pb-4 pt-2 border-t border-white/5">
        {!has_redis_state || !runtime ? (
          <p className="text-white/50 text-sm italic py-2">
            Состояние боя недоступно (истёк таймаут)
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {/* Turn info */}
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <span className="text-white/60">
                Ход: <span className="text-white font-medium">{runtime.turn_number}</span>
              </span>
              <span className="text-white/60">
                Ходит:{' '}
                <span className="text-white font-medium">
                  {nameMap[runtime.current_actor] || `#${runtime.current_actor}`}
                </span>
              </span>
              <span className="text-white/60">
                Дедлайн:{' '}
                <span className="text-white font-medium">
                  {formatDate(runtime.deadline_at)}
                </span>
              </span>
            </div>

            {/* Participants with resource bars */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {Object.entries(runtime.participants).map(([pid, p]) => {
                const participantId = Number(pid);
                const name = nameMap[participantId] || `Участник #${pid}`;
                return (
                  <div key={pid} className="bg-white/[0.03] rounded-card p-3 flex flex-col gap-2">
                    <span className="text-white text-sm font-medium">{name}</span>
                    <ResourceBar
                      label="HP"
                      current={p.hp}
                      max={p.max_hp}
                      barClass="bg-green-500"
                      dynamicColor
                    />
                    <ResourceBar
                      label="Мана"
                      current={p.mana}
                      max={p.max_mana}
                      barClass="bg-blue-500"
                    />
                    <ResourceBar
                      label="Энергия"
                      current={p.energy}
                      max={p.max_energy}
                      barClass="bg-yellow-400"
                    />
                    <ResourceBar
                      label="Стамина"
                      current={p.stamina}
                      max={p.max_stamina}
                      barClass="bg-emerald-400"
                    />
                  </div>
                );
              })}
            </div>

            {/* Active effects */}
            {runtime.active_effects && Object.keys(runtime.active_effects).length > 0 && (
              <div className="text-sm">
                <span className="text-white/60">Активные эффекты: </span>
                <span className="text-white">
                  {Object.keys(runtime.active_effects).join(', ')}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Force finish button */}
        <div className="mt-4 flex flex-col gap-3">
          {!confirmOpen ? (
            <button
              onClick={() => setConfirmOpen(true)}
              className="btn-line !border-red-500/50 !text-red-400 hover:!text-red-300 !w-auto self-start !px-4"
            >
              Принудительно завершить
            </button>
          ) : (
            <div className="bg-red-500/10 border border-red-500/20 rounded-card p-4 flex flex-col gap-3">
              <p className="text-white text-sm">
                Вы уверены? Бой будет завершён без победителя и наград.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handleForceFinish}
                  disabled={finishing}
                  className="btn-line !border-red-500/50 !text-red-400 hover:!text-red-300 !w-auto !px-4 disabled:opacity-50"
                >
                  {finishing ? 'Завершение...' : 'Завершить'}
                </button>
                <button
                  onClick={() => setConfirmOpen(false)}
                  className="btn-line !w-auto !px-4"
                >
                  Отмена
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

// --- Main component ---

const AdminBattlesPage = () => {
  const [battles, setBattles] = useState<BattleListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [battleTypeFilter, setBattleTypeFilter] = useState('');
  const [expandedBattleId, setExpandedBattleId] = useState<number | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchBattles = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    try {
      const params: Record<string, string | number> = {
        page,
        per_page: PER_PAGE,
      };
      if (battleTypeFilter) params.battle_type = battleTypeFilter;

      const { data } = await axios.get<BattleListResponse>(
        `${BASE_URL_BATTLES}/battles/admin/active`,
        { params },
      );
      setBattles(data.battles);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      const msg = e?.response?.data?.detail || 'Не удалось загрузить список боёв';
      setError(msg);
      if (showLoader) toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [page, battleTypeFilter]);

  // Initial load + auto-refresh
  useEffect(() => {
    fetchBattles(true);

    refreshRef.current = setInterval(() => {
      fetchBattles(false);
    }, REFRESH_INTERVAL_MS);

    return () => {
      if (refreshRef.current) clearInterval(refreshRef.current);
    };
  }, [fetchBattles]);

  const handleFilterChange = (value: string) => {
    setBattleTypeFilter(value);
    setPage(1);
    setExpandedBattleId(null);
  };

  const handleRowClick = (battleId: number) => {
    setExpandedBattleId((prev) => (prev === battleId ? null : battleId));
  };

  const handleForceFinishDone = () => {
    setExpandedBattleId(null);
    fetchBattles(false);
  };

  const totalPages = Math.ceil(total / PER_PAGE);

  const renderParticipants = (participants: BattleParticipant[]) =>
    participants.map((p, idx) => (
      <span key={p.participant_id}>
        {idx > 0 && ', '}
        <span className={p.is_npc ? 'text-white/40 italic' : 'text-white'}>
          {p.character_name}
        </span>
        {p.is_npc && <span className="text-white/30 text-[10px] ml-0.5">(NPC)</span>}
      </span>
    ));

  const getBadge = (type: string) => {
    const badge = BATTLE_TYPE_BADGES[type];
    if (!badge) return <span className="text-white/50 text-xs">{type}</span>;
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badge.classes}`}>
        {badge.label}
      </span>
    );
  };

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
        <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
          Мониторинг боёв
        </h1>
        <span className="text-white/50 text-sm">
          Активных: {total}
        </span>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4">
        <select
          className="input-underline max-w-[220px]"
          value={battleTypeFilter}
          onChange={(e) => handleFilterChange(e.target.value)}
        >
          {BATTLE_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-site-dark text-white">
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && <div className="text-site-red text-sm">{error}</div>}

      {/* Content */}
      <div className="gray-bg overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : battles.length === 0 ? (
          <p className="text-center text-white/50 text-sm py-8">Нет активных боёв</p>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                      ID
                    </th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                      Тип
                    </th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                      Статус
                    </th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                      Участники
                    </th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                      Начало
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {battles.map((battle) => (
                    <Fragment key={battle.id}>
                      <tr
                        onClick={() => handleRowClick(battle.id)}
                        className={`border-b border-white/5 cursor-pointer transition-colors duration-200 ${
                          expandedBattleId === battle.id
                            ? 'bg-white/[0.07]'
                            : 'hover:bg-white/[0.05]'
                        }`}
                      >
                        <td className="px-4 py-3 text-sm text-white/70">{battle.id}</td>
                        <td className="px-4 py-3">{getBadge(battle.battle_type)}</td>
                        <td className="px-4 py-3 text-sm text-white/70">
                          {STATUS_LABELS[battle.status] || battle.status}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          {renderParticipants(battle.participants)}
                        </td>
                        <td className="px-4 py-3 text-sm text-white/50">
                          {formatDate(battle.created_at)}
                        </td>
                      </tr>
                      <AnimatePresence>
                        {expandedBattleId === battle.id && (
                          <tr>
                            <td colSpan={5}>
                              <BattleDetailPanel
                                battleId={battle.id}
                                onForceFinish={handleForceFinishDone}
                              />
                            </td>
                          </tr>
                        )}
                      </AnimatePresence>
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden flex flex-col gap-3 p-3">
              {battles.map((battle) => (
                <div key={battle.id} className="flex flex-col">
                  <div
                    onClick={() => handleRowClick(battle.id)}
                    className={`bg-white/[0.03] rounded-card p-4 flex flex-col gap-2 cursor-pointer transition-colors duration-200 ${
                      expandedBattleId === battle.id ? 'bg-white/[0.07]' : ''
                    }`}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-white text-sm font-medium">Бой #{battle.id}</span>
                      {getBadge(battle.battle_type)}
                      <span className="text-white/40 text-xs">
                        {STATUS_LABELS[battle.status] || battle.status}
                      </span>
                    </div>
                    <div className="text-sm">{renderParticipants(battle.participants)}</div>
                    <div className="text-white/40 text-xs">{formatDate(battle.created_at)}</div>
                  </div>
                  <AnimatePresence>
                    {expandedBattleId === battle.id && (
                      <BattleDetailPanel
                        battleId={battle.id}
                        onForceFinish={handleForceFinishDone}
                      />
                    )}
                  </AnimatePresence>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-3">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="text-sm text-white hover:text-site-blue transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Назад
          </button>
          <span className="text-sm text-white/50">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="text-sm text-white hover:text-site-blue transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Вперёд
          </button>
        </div>
      )}
    </div>
  );
};

export default AdminBattlesPage;
