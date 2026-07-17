import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import {
  fetchMobPacksByLocation,
  createPackBattle,
  createPartyPackBattle,
  type MobPackInLocation,
  type PackMemberInLocation,
} from '../api/mobPacks';
import { getMyParty, type Party } from '../api/squads';

interface LocationMobPacksProps {
  locationId: number;
  characterId: number | null;
  // lead_character_id values the player may attack (combat-post gate, FEAT-145).
  gatedMobIds?: number[];
}

const TIER_CLASSES: Record<string, string> = {
  normal: 'bg-white/20 text-white/80',
  elite: 'bg-purple-600/40 text-purple-200',
  boss: 'bg-gradient-to-r from-site-red/50 to-gold/50 text-gold-light',
};

/**
 * Member-group row of a pack card (FEAT-152). The HP bar uses the SUMMED
 * semantic: `current_hp`/`max_hp` are aggregated across the group's LIVING
 * members (e.g. 30/60 for two mobs at 15/30). Null → the bar is hidden.
 */
const PackMemberRow = ({ member }: { member: PackMemberInLocation }) => {
  const hasHp = member.current_hp != null && member.max_hp != null && member.max_hp > 0;
  const pct = hasHp
    ? Math.max(0, Math.min(100, ((member.current_hp as number) / (member.max_hp as number)) * 100))
    : 0;

  return (
    <div className="flex items-center gap-2.5 rounded-card bg-black/30 border border-white/[0.06] p-2 pr-3 min-w-0">
      {/* Avatar */}
      <div className="w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
        {member.avatar ? (
          <img src={member.avatar} alt={member.name} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-white/25">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.5 17.5L3 6V3h3l11.5 11.5" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 19l6-6" />
            </svg>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1 flex-1 min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-white text-xs font-medium truncate">
            {member.name} ×{member.count}
          </span>
          <span className={`px-1.5 py-px rounded-full text-[9px] font-medium shrink-0 ${
            TIER_CLASSES[member.tier] ?? TIER_CLASSES.normal
          }`}>
            LVL {member.level}
          </span>
        </div>
        {/* Summed group HP (A5) — hidden gracefully when data is null */}
        {hasHp && (
          <div className="flex items-center gap-2">
            <div className="stat-bar" title={`HP ${member.current_hp} / ${member.max_hp}`}>
              <div className="stat-bar-fill stat-bar-hp" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-white/40 text-[9px] whitespace-nowrap shrink-0">
              {member.current_hp} / {member.max_hp}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * «Стаи» — mob packs at the location (FEAT-147), restyled to the FEAT-152
 * card language with per-group summed HP bars. All battle logic unchanged.
 */
const LocationMobPacks = ({ locationId, characterId, gatedMobIds = [] }: LocationMobPacksProps) => {
  const navigate = useNavigate();
  const [packs, setPacks] = useState<MobPackInLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [attackingId, setAttackingId] = useState<number | null>(null);
  const [choosingId, setChoosingId] = useState<number | null>(null);
  const [party, setParty] = useState<Party | null>(null);

  useEffect(() => {
    if (!characterId) {
      setParty(null);
      return;
    }
    getMyParty(characterId).then(setParty).catch(() => setParty(null));
  }, [characterId]);

  const coLocatedMates = (party?.members ?? []).filter(
    (m) =>
      m.status === 'accepted' &&
      m.character_id !== characterId &&
      m.current_location_id === locationId,
  );
  const canGroup = !!party && coLocatedMates.length >= 1;

  const loadPacks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMobPacksByLocation(locationId);
      setPacks(data);
    } catch {
      const msg = 'Не удалось загрузить стаи';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [locationId]);

  useEffect(() => {
    loadPacks();
  }, [loadPacks]);

  const handleAttack = async (pack: MobPackInLocation, group: boolean) => {
    if (!characterId) {
      toast.error('Выберите персонажа для начала боя');
      return;
    }
    if (pack.status === 'in_battle') {
      toast.error('Эта стая уже в бою');
      return;
    }
    setChoosingId(null);
    setAttackingId(pack.active_pack_id);
    try {
      const result = group
        ? await createPartyPackBattle(characterId, pack.active_pack_id)
        : await createPackBattle(characterId, pack.active_pack_id);
      toast.success(group ? 'Групповой бой начинается!' : 'Бой начинается!');
      navigate(`/location/${locationId}/battle/${result.battle_id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось начать бой';
      toast.error(message);
    } finally {
      setAttackingId(null);
    }
  };

  const packCount = packs.length;

  // Hide the section entirely when there are no packs (keep visible on error).
  if (packCount === 0 && !error) return null;

  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-site-red/25 shadow-card overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`w-full flex items-center gap-2.5 px-4 sm:px-5 py-3.5 cursor-pointer ${
          isOpen ? 'border-b border-white/[0.07]' : ''
        }`}
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-stat-hp shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
        </svg>
        <h2 className="text-stat-hp text-[13px] font-medium uppercase tracking-[0.08em]">Стаи</h2>
        {!loading && packCount > 0 && (
          <span className="bg-site-red/60 text-white text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
            {packCount}
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

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="px-3 sm:px-4 pb-4 pt-3 flex flex-col gap-3">
              {error ? (
                <>
                  <p className="text-site-red text-sm">{error}</p>
                  <button onClick={loadPacks} className="btn-blue text-sm px-4 py-2 self-start">
                    Повторить
                  </button>
                </>
              ) : (
                packs.map((pack) => {
                  const isAttacking = attackingId === pack.active_pack_id;
                  const gated = gatedMobIds.includes(pack.lead_character_id);
                  const totalMobs = pack.members.reduce((s, m) => s + m.count, 0);
                  const packInBattle = pack.status === 'in_battle';

                  return (
                    <div
                      key={pack.active_pack_id}
                      className="flex flex-col gap-3 p-3 sm:p-4 rounded-card bg-site-red/[0.05] border border-site-red/15"
                    >
                      <div className="flex items-center gap-3 flex-wrap">
                        <div className="gold-outline relative w-12 h-12 sm:w-14 sm:h-14 rounded-full overflow-hidden bg-black/40 shrink-0">
                          {pack.avatar ? (
                            <img src={pack.avatar} alt={pack.name} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-white/30 text-xl">
                              ⚔
                            </div>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-white text-sm sm:text-base font-medium truncate">
                              {pack.name}
                            </span>
                            {packInBattle && (
                              <span className="px-2 py-0.5 rounded-full bg-orange-500/80 text-white text-[9px] font-bold uppercase tracking-[0.04em] shrink-0">
                                В бою
                              </span>
                            )}
                          </div>
                          <span className="text-white/50 text-xs">{totalMobs} мобов</span>
                        </div>

                        {characterId && (
                          !gated ? (
                            <span className="text-white/35 text-[10px] sm:text-xs shrink-0 text-right max-w-[96px] leading-tight">
                              Нужен боевой пост
                            </span>
                          ) : choosingId === pack.active_pack_id && !isAttacking ? (
                            <div className="flex gap-1.5 shrink-0">
                              <button
                                onClick={() => handleAttack(pack, true)}
                                className="btn-blue text-xs px-2.5 py-1.5"
                              >
                                Группой
                              </button>
                              <button
                                onClick={() => handleAttack(pack, false)}
                                className="text-xs px-2.5 py-1.5 rounded-[9px] border border-white/20 text-white/70 hover:bg-white/5 transition-colors duration-200"
                              >
                                Соло
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() =>
                                canGroup
                                  ? setChoosingId(pack.active_pack_id)
                                  : handleAttack(pack, false)
                              }
                              disabled={packInBattle || isAttacking}
                              className="px-4 py-1.5 sm:py-2 rounded-[9px] bg-site-red/90 text-white text-[11px] sm:text-xs font-medium uppercase tracking-[0.04em] hover:brightness-110 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shrink-0 flex items-center justify-center"
                            >
                              {isAttacking ? (
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                              ) : (
                                'Напасть'
                              )}
                            </button>
                          )
                        )}
                      </div>

                      {/* Composition — member groups with summed HP bars */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                        {pack.members.map((m, idx) => (
                          <PackMemberRow key={`${pack.active_pack_id}-${idx}`} member={m} />
                        ))}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
};

export default LocationMobPacks;
