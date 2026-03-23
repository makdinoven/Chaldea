import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import { fetchBattlesByLocation, fetchJoinRequests } from '../../../api/battles';
import type { LocationBattleItem, JoinRequestListItem } from '../../../api/battles';
import JoinRequestModal from './JoinRequestModal';

interface BattlesSectionProps {
  locationId: number;
  characterId: number | null;
  inBattle: boolean;
}

const POLL_INTERVAL = 10_000;

const BATTLE_TYPE_CONFIG: Record<string, { label: string; classes: string }> = {
  pve: {
    label: 'PvE',
    classes: 'bg-green-600/40 text-green-200',
  },
  pvp: {
    label: 'PvP',
    classes: 'bg-site-red/40 text-orange-200',
  },
  pvp_training: {
    label: 'PvP Тренировка',
    classes: 'bg-site-blue/40 text-blue-200',
  },
  pvp_death: {
    label: 'PvP Смертельный',
    classes: 'bg-site-red/40 text-red-200',
  },
};

const BattlesSection = ({ locationId, characterId, inBattle }: BattlesSectionProps) => {
  const navigate = useNavigate();
  const [battles, setBattles] = useState<LocationBattleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [modalBattleId, setModalBattleId] = useState<number | null>(null);
  const [requestedBattleIds, setRequestedBattleIds] = useState<Set<number>>(new Set());

  const checkExistingRequests = useCallback(
    async (battleList: LocationBattleItem[]) => {
      if (!characterId) return;
      const ids = new Set<number>();
      for (const battle of battleList) {
        try {
          const requests = await fetchJoinRequests(battle.id);
          const hasRequest = requests.some(
            (r: JoinRequestListItem) =>
              r.character_id === characterId &&
              (r.status === 'pending' || r.status === 'rejected'),
          );
          if (hasRequest) ids.add(battle.id);
        } catch {
          // Silently skip — we just won't disable the button
        }
      }
      setRequestedBattleIds(ids);
    },
    [characterId],
  );

  const loadBattles = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const data = await fetchBattlesByLocation(locationId);
      setBattles(data);
      await checkExistingRequests(data);
    } catch {
      const msg = 'Не удалось загрузить список боёв';
      setError(msg);
      if (showLoading) toast.error(msg);
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [locationId, checkExistingRequests]);

  useEffect(() => {
    loadBattles(true);

    intervalRef.current = setInterval(() => {
      loadBattles(false);
    }, POLL_INTERVAL);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [loadBattles]);

  const handleSpectate = (battleId: number) => {
    navigate(`/location/${locationId}/battle/${battleId}/spectate`);
  };

  // Group participants by team
  const getTeams = (battle: LocationBattleItem) => {
    const teams: Record<number, typeof battle.participants> = {};
    for (const p of battle.participants) {
      if (!teams[p.team]) teams[p.team] = [];
      teams[p.team].push(p);
    }
    return teams;
  };

  const battleCount = battles.length;

  return (
    <section className="bg-black/50 rounded-card">
      {/* Collapsible header */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full flex items-center justify-between py-3 px-4 sm:px-6 group cursor-pointer"
      >
        <div className="flex items-center gap-2">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
            Бои на локации
          </h2>
          {!loading && battleCount > 0 && (
            <span className="bg-site-red/60 text-white text-[10px] sm:text-xs font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
              {battleCount}
            </span>
          )}
          {loading && (
            <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
          )}
        </div>
        <svg
          className={`w-5 h-5 text-gold transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Collapsible content */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="px-4 sm:px-6 pb-4 flex flex-col gap-3">
              {error ? (
                <>
                  <p className="text-site-red text-sm">{error}</p>
                  <button onClick={() => loadBattles(true)} className="btn-blue text-sm px-4 py-2 self-start">
                    Повторить
                  </button>
                </>
              ) : battleCount === 0 ? (
                <p className="text-white/50 text-sm">Нет активных боёв</p>
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
                  {battles.map((battle) => {
                    const typeConfig = BATTLE_TYPE_CONFIG[battle.battle_type] ?? {
                      label: battle.battle_type,
                      classes: 'bg-white/20 text-white/80',
                    };
                    const teams = getTeams(battle);

                    return (
                      <motion.div
                        key={battle.id}
                        variants={{
                          hidden: { opacity: 0, y: 10 },
                          visible: { opacity: 1, y: 0 },
                        }}
                        className="flex flex-col gap-3 p-3 sm:p-4 rounded-card bg-white/5 hover:bg-white/10 transition-colors"
                      >
                        {/* Header: badges */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${typeConfig.classes}`}
                          >
                            {typeConfig.label}
                          </span>

                          {battle.is_paused && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium bg-yellow-500/30 text-yellow-200">
                              На паузе
                            </span>
                          )}
                        </div>

                        {/* Teams */}
                        <div className="flex flex-col sm:flex-row gap-2 sm:gap-4">
                          {Object.entries(teams).map(([teamNum, members]) => (
                            <div key={teamNum} className="flex-1 min-w-0">
                              <span className="text-white/40 text-[10px] sm:text-xs font-medium uppercase tracking-wider">
                                Команда {Number(teamNum) + 1}
                              </span>
                              <div className="flex flex-wrap gap-1.5 mt-1">
                                {members.map((p) => (
                                  <span
                                    key={p.participant_id}
                                    className={`px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${
                                      p.is_npc
                                        ? 'bg-purple-600/30 text-purple-200'
                                        : 'bg-white/10 text-white/80'
                                    }`}
                                  >
                                    {p.character_name}
                                    <span className="text-white/40 ml-1">Ур.{p.level}</span>
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* Buttons */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <button
                            onClick={() => handleSpectate(battle.id)}
                            className="btn-blue text-xs sm:text-sm px-3 py-1.5 sm:px-4 sm:py-2"
                          >
                            Наблюдать
                          </button>
                          <button
                            onClick={() => setModalBattleId(battle.id)}
                            disabled={inBattle || !characterId || requestedBattleIds.has(battle.id)}
                            className="btn-line text-xs sm:text-sm px-3 py-1.5 sm:px-4 sm:py-2 disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            {requestedBattleIds.has(battle.id) ? 'Заявка подана' : 'Подать заявку'}
                          </button>
                        </div>
                      </motion.div>
                    );
                  })}
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Join Request Modal */}
      <AnimatePresence>
        {modalBattleId !== null && characterId && (() => {
          const battle = battles.find((b) => b.id === modalBattleId);
          if (!battle) return null;
          return (
            <JoinRequestModal
              battleId={battle.id}
              participants={battle.participants}
              characterId={characterId}
              onClose={() => setModalBattleId(null)}
              onSuccess={() => {
                setRequestedBattleIds((prev) => new Set([...prev, battle.id]));
                loadBattles(false);
              }}
            />
          );
        })()}
      </AnimatePresence>
    </section>
  );
};

export default BattlesSection;
