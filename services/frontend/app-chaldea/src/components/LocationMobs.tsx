import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import { fetchMobsByLocation, createBattle, createPartyMobBattle } from '../api/mobs';
import type { MobInLocation } from '../api/mobs';
import { getMyParty, type Party } from '../api/squads';

interface LocationMobsProps {
  locationId: number;
  characterId: number | null;
  // Mob character_ids the player may attack (from combat gate posts, FEAT-145 v2).
  gatedMobIds?: number[];
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

/**
 * HP bar (FEAT-152 A5): rendered only when the backend provided both fields.
 * For a mob with status "in_battle" the value is the last persisted one —
 * documented product behavior (§3.3), the «В бою» badge signals that.
 */
const MobHpBar = ({ current, max }: { current: number; max: number }) => {
  const pct = Math.max(0, Math.min(100, (current / max) * 100));
  return (
    <div className="stat-bar" title={`HP ${current} / ${max}`}>
      <div className="stat-bar-fill stat-bar-hp" style={{ width: `${pct}%` }} />
    </div>
  );
};

/**
 * «Противники» — mock-style 2-column mob cards with HP bars (FEAT-152 §3.5).
 * Collapsible kept (B15); combat-gate + solo/party attack logic unchanged;
 * the parent dims the section via `actionsLocked` while in battle/gathering.
 */
const LocationMobs = ({ locationId, characterId, gatedMobIds = [] }: LocationMobsProps) => {
  const navigate = useNavigate();
  const [mobs, setMobs] = useState<MobInLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(true);
  const [attackingMobId, setAttackingMobId] = useState<number | null>(null);
  const [party, setParty] = useState<Party | null>(null);
  const [choosingMobId, setChoosingMobId] = useState<number | null>(null);

  useEffect(() => {
    if (!characterId) {
      setParty(null);
      return;
    }
    getMyParty(characterId).then(setParty).catch(() => setParty(null));
  }, [characterId]);

  // The leader can start a group fight when at least one accepted squadmate is
  // co-located on this location (FEAT-144 Ф3).
  const coLocatedMates = (party?.members ?? []).filter(
    (m) =>
      m.status === 'accepted' &&
      m.character_id !== characterId &&
      m.current_location_id === locationId,
  );
  // Any co-located squad member can start a group fight (party membership is the
  // consent) — not just the leader (FEAT-144 fix).
  const canGroup = !!party && coLocatedMates.length >= 1;

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

  const handleAttack = async (mob: MobInLocation, group: boolean) => {
    if (!characterId) {
      toast.error('Выберите персонажа для начала боя');
      return;
    }
    if (mob.status === 'in_battle') {
      toast.error('Этот монстр уже в бою');
      return;
    }

    setChoosingMobId(null);
    setAttackingMobId(mob.active_mob_id);
    try {
      const result = group
        ? await createPartyMobBattle(characterId, mob.character_id)
        : await createBattle(characterId, mob.character_id);
      toast.success(group ? 'Групповой бой начинается!' : 'Бой начинается!');
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
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-site-red/25 shadow-card overflow-hidden">
      {/* Collapsible header */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`w-full flex items-center gap-2.5 px-4 sm:px-5 py-3.5 cursor-pointer ${
          isOpen ? 'border-b border-white/[0.07]' : ''
        }`}
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-stat-hp shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.5 17.5L3 6V3h3l11.5 11.5" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 19l6-6" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 16l4 4" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 21l2-2" />
        </svg>
        <h2 className="text-stat-hp text-[13px] font-medium uppercase tracking-[0.08em]">
          Противники
        </h2>
        {!loading && mobCount > 0 && (
          <span className="bg-site-red/60 text-white text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
            {mobCount}
          </span>
        )}
        {loading && (
          <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
        )}
        <svg
          className={`w-4 h-4 text-gold ml-auto shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
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
            {error ? (
              <div className="flex flex-col gap-3 px-4 sm:px-5 pb-4 pt-3">
                <p className="text-site-red text-sm">{error}</p>
                <button onClick={loadMobs} className="btn-blue text-sm px-4 py-2 self-start">
                  Повторить
                </button>
              </div>
            ) : mobCount === 0 && !loading ? (
              <p className="text-white/50 text-sm px-4 sm:px-5 pb-4">Противников нет</p>
            ) : (
              <motion.div
                initial="hidden"
                animate="visible"
                variants={{
                  hidden: {},
                  visible: { transition: { staggerChildren: 0.05 } },
                }}
                className="grid grid-cols-2 gap-2 px-3 sm:px-4 pb-4 pt-3 max-h-[320px] lg:max-h-[400px] overflow-y-auto gold-scrollbar content-start"
              >
                {mobs.map((mob) => {
                  const tier = TIER_CONFIG[mob.tier] ?? TIER_CONFIG.normal;
                  const isAttacking = attackingMobId === mob.active_mob_id;
                  const inBattleMob = mob.status === 'in_battle';
                  const hasHp = mob.current_hp != null && mob.max_hp != null && mob.max_hp > 0;

                  return (
                    <motion.div
                      key={mob.active_mob_id}
                      variants={{
                        hidden: { opacity: 0, y: 10 },
                        visible: { opacity: 1, y: 0 },
                      }}
                      className="flex flex-col items-center gap-2 p-2.5 pb-3 rounded-card bg-site-red/[0.06] border border-site-red/20"
                    >
                      {/* Image */}
                      <div className="relative w-full h-[72px] rounded-[10px] overflow-hidden bg-black/40 shrink-0">
                        {mob.avatar ? (
                          <img
                            src={mob.avatar}
                            alt={mob.name}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-white/20">
                            <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M14.5 17.5L3 6V3h3l11.5 11.5" />
                              <path strokeLinecap="round" strokeLinejoin="round" d="M13 19l6-6" />
                            </svg>
                          </div>
                        )}
                        {/* In-battle badge — HP shown below is the last persisted value */}
                        {inBattleMob && (
                          <span className="absolute top-1.5 right-1.5 px-2 py-0.5 rounded-full bg-orange-500/80 text-white text-[9px] font-bold uppercase tracking-[0.04em]">
                            В бою
                          </span>
                        )}
                      </div>

                      {/* Name + level + tier */}
                      <div className="flex flex-col items-center gap-1 w-full min-w-0">
                        <span className="text-white text-[13px] font-medium text-center truncate w-full">
                          {mob.name}
                        </span>
                        <div className="flex items-center gap-1.5 flex-wrap justify-center">
                          <span className="text-white/50 text-[10px] font-bold">
                            LVL {mob.level}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-[9px] font-medium ${tier.classes}`}>
                            {tier.label}
                          </span>
                        </div>
                      </div>

                      {/* HP bar (A5) — hidden gracefully when data is null */}
                      {hasHp && (
                        <MobHpBar current={mob.current_hp as number} max={mob.max_hp as number} />
                      )}

                      {/* Attack — hidden when character is not at this location.
                          A squad member with co-located mates gets a
                          group/solo choice (FEAT-144 Ф3). */}
                      {characterId && (
                        !gatedMobIds.includes(mob.character_id) ? (
                          <span className="text-white/35 text-[10px] text-center leading-tight">
                            Нужен боевой пост
                          </span>
                        ) : choosingMobId === mob.active_mob_id && !isAttacking ? (
                          <div className="flex gap-1.5 w-full">
                            <button
                              onClick={() => handleAttack(mob, true)}
                              className="btn-blue text-[11px] px-2 py-1.5 flex-1"
                            >
                              Группой
                            </button>
                            <button
                              onClick={() => handleAttack(mob, false)}
                              className="text-[11px] px-2 py-1.5 flex-1 rounded-[9px] border border-white/20 text-white/70 hover:bg-white/5 transition-colors duration-200"
                            >
                              Соло
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() =>
                              canGroup
                                ? setChoosingMobId(mob.active_mob_id)
                                : handleAttack(mob, false)
                            }
                            disabled={inBattleMob || isAttacking}
                            className="w-full py-1.5 rounded-[9px] bg-site-red/90 text-white text-[11px] font-medium uppercase tracking-[0.04em] hover:brightness-110 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
                          >
                            {isAttacking ? (
                              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                              'Напасть'
                            )}
                          </button>
                        )
                      )}
                    </motion.div>
                  );
                })}
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
};

export default LocationMobs;
