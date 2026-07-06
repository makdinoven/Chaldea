import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import {
  fetchMobPacksByLocation,
  createPackBattle,
  createPartyPackBattle,
  type MobPackInLocation,
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
    <section className="bg-black/60 rounded-card">
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full flex items-center justify-between py-3 px-4 sm:px-6 group cursor-pointer"
      >
        <div className="flex items-center gap-2">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">Стаи</h2>
          {!loading && packCount > 0 && (
            <span className="bg-site-red/60 text-white text-[10px] sm:text-xs font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
              {packCount}
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
                  <button onClick={loadPacks} className="btn-blue text-sm px-4 py-2 self-start">
                    Повторить
                  </button>
                </>
              ) : (
                packs.map((pack) => {
                  const isAttacking = attackingId === pack.active_pack_id;
                  const gated = gatedMobIds.includes(pack.lead_character_id);
                  const totalMobs = pack.members.reduce((s, m) => s + m.count, 0);

                  return (
                    <div
                      key={pack.active_pack_id}
                      className="flex flex-col gap-3 p-3 sm:p-4 rounded-card bg-white/10"
                    >
                      <div className="flex items-center gap-3">
                        <div className="gold-outline relative w-14 h-14 rounded-full overflow-hidden bg-black/40 shrink-0">
                          {pack.avatar ? (
                            <img src={pack.avatar} alt={pack.name} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-white/30 text-xl">
                              ⚔
                            </div>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-white text-sm sm:text-base font-medium truncate block">
                            {pack.name}
                          </span>
                          <span className="text-white/50 text-xs">{totalMobs} мобов</span>
                        </div>

                        {characterId && (
                          !gated ? (
                            <span className="text-white/30 text-[10px] sm:text-xs shrink-0 text-right max-w-[96px] leading-tight">
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
                                className="text-xs px-2.5 py-1.5 rounded border border-white/20 text-white/70 hover:bg-white/5"
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
                              disabled={pack.status === 'in_battle' || isAttacking}
                              className="btn-blue text-xs sm:text-sm px-3 py-1.5 sm:px-4 sm:py-2 shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              {isAttacking ? (
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                              ) : (
                                'Атаковать'
                              )}
                            </button>
                          )
                        )}
                      </div>

                      {/* Composition */}
                      <div className="flex flex-wrap gap-1.5">
                        {pack.members.map((m, idx) => (
                          <span
                            key={`${pack.active_pack_id}-${idx}`}
                            className={`px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${
                              TIER_CLASSES[m.tier] ?? TIER_CLASSES.normal
                            }`}
                          >
                            {m.name} ×{m.count}
                          </span>
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
