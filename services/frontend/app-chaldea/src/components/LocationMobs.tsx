import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import { fetchMobsByLocation, createBattle } from '../api/mobs';
import type { MobInLocation } from '../api/mobs';

interface LocationMobsProps {
  locationId: number;
  characterId: number | null;
}

const TIER_CONFIG: Record<
  string,
  { label: string; classes: string }
> = {
  normal: {
    label: 'Обычный',
    classes: 'bg-white/20 text-white/80',
  },
  elite: {
    label: 'Элитный',
    classes: 'bg-purple-600/40 text-purple-200',
  },
  boss: {
    label: 'Босс',
    classes: 'bg-gradient-to-r from-site-red/50 to-gold/50 text-gold-light',
  },
};

const STATUS_CONFIG: Record<string, { label: string; dotClass: string }> = {
  alive: { label: 'Готов к бою', dotClass: 'bg-green-500' },
  in_battle: { label: 'В бою', dotClass: 'bg-orange-400' },
};

const LocationMobs = ({ locationId, characterId }: LocationMobsProps) => {
  const navigate = useNavigate();
  const [mobs, setMobs] = useState<MobInLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [attackingMobId, setAttackingMobId] = useState<number | null>(null);

  const loadMobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMobsByLocation(locationId);
      setMobs(data);
    } catch {
      const msg = 'Не удалось загрузить список врагов';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [locationId]);

  useEffect(() => {
    loadMobs();
  }, [loadMobs]);

  const handleAttack = async (mob: MobInLocation) => {
    if (!characterId) {
      toast.error('Выберите персонажа для начала боя');
      return;
    }
    if (mob.status === 'in_battle') {
      toast.error('Этот монстр уже в бою');
      return;
    }

    setAttackingMobId(mob.active_mob_id);
    try {
      const result = await createBattle(characterId, mob.character_id);
      toast.success('Бой начинается!');
      navigate(`/location/${locationId}/battle/${result.battle_id}`);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Не удалось начать бой';
      toast.error(message);
    } finally {
      setAttackingMobId(null);
    }
  };

  const mobCount = mobs.length;

  return (
    <section className="bg-black/50 rounded-card">
      {/* Collapsible header */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full flex items-center justify-between py-3 px-4 sm:px-6 group cursor-pointer"
      >
        <div className="flex items-center gap-2">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
            Монстры
          </h2>
          {!loading && mobCount > 0 && (
            <span className="bg-site-red/60 text-white text-[10px] sm:text-xs font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
              {mobCount}
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
                  <button onClick={loadMobs} className="btn-blue text-sm px-4 py-2 self-start">
                    Повторить
                  </button>
                </>
              ) : mobCount === 0 ? (
                <p className="text-white/50 text-sm">
                  На этой локации нет врагов
                </p>
              ) : (
                <motion.div
                  initial="hidden"
                  animate="visible"
                  variants={{
                    hidden: {},
                    visible: { transition: { staggerChildren: 0.05 } },
                  }}
                  className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4"
                >
                  {mobs.map((mob) => {
                    const tier = TIER_CONFIG[mob.tier] ?? TIER_CONFIG.normal;
                    const status = STATUS_CONFIG[mob.status] ?? STATUS_CONFIG.alive;
                    const isAttacking = attackingMobId === mob.active_mob_id;

                    return (
                      <motion.div
                        key={mob.active_mob_id}
                        variants={{
                          hidden: { opacity: 0, y: 10 },
                          visible: { opacity: 1, y: 0 },
                        }}
                        className="flex items-center gap-3 sm:gap-4 p-3 sm:p-4 rounded-card bg-white/5 hover:bg-white/10 transition-colors"
                      >
                        {/* Avatar */}
                        <div className="gold-outline relative w-14 h-14 sm:w-16 sm:h-16 rounded-full overflow-hidden bg-black/40 shrink-0">
                          {mob.avatar ? (
                            <img
                              src={mob.avatar}
                              alt={mob.name}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-white/20">
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                className="w-8 h-8"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                strokeWidth={1}
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                                />
                              </svg>
                            </div>
                          )}
                        </div>

                        {/* Info */}
                        <div className="flex flex-col gap-1 flex-1 min-w-0">
                          <span className="text-white text-sm sm:text-base font-medium truncate">
                            {mob.name}
                          </span>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="gold-text text-xs font-medium">
                              Ур. {mob.level}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${tier.classes}`}
                            >
                              {tier.label}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className={`w-2 h-2 rounded-full ${status.dotClass}`} />
                            <span className="text-white/50 text-[10px] sm:text-xs">
                              {status.label}
                            </span>
                          </div>
                        </div>

                        {/* Attack button */}
                        <button
                          onClick={() => handleAttack(mob)}
                          disabled={
                            !characterId ||
                            mob.status === 'in_battle' ||
                            isAttacking
                          }
                          className="btn-blue text-xs sm:text-sm px-3 py-1.5 sm:px-4 sm:py-2 shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {isAttacking ? (
                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          ) : (
                            'Атаковать'
                          )}
                        </button>
                      </motion.div>
                    );
                  })}
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
};

export default LocationMobs;
