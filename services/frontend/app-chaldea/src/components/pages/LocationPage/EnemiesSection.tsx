import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import {
  fetchMobsByLocation,
  createBattle,
  createPartyMobBattle,
  type MobInLocation,
} from '../../../api/mobs';
import {
  fetchMobPacksByLocation,
  createPackBattle,
  createPartyPackBattle,
  type MobPackInLocation,
  type PackMemberInLocation,
} from '../../../api/mobPacks';
import { getMyParty, type Party } from '../../../api/squads';

interface EnemiesSectionProps {
  locationId: number;
  characterId: number | null;
  // Combat-gate keys the player may attack (FEAT-145 v2):
  // mob.character_id for single mobs, pack.lead_character_id for packs.
  gatedMobIds?: number[];
}

/**
 * FEAT-153 §3.4 — single «Противники» list holding BOTH single mobs and mob
 * packs. Replaces `components/LocationMobs.tsx` + `components/LocationMobPacks.tsx`.
 *
 * The two entity kinds stay a discriminated union on purpose: they have
 * different gate keys and four distinct battle-launch calls, none of which are
 * unified here.
 */
type EnemyEntry =
  | { kind: 'mob'; key: string; mob: MobInLocation }
  | { kind: 'pack'; key: string; pack: MobPackInLocation };

const TIER_CONFIG: Record<string, { label: string; classes: string }> = {
  normal: { label: 'Обычный', classes: 'bg-white/20 text-white/80' },
  elite: { label: 'Элитный', classes: 'bg-purple-600/40 text-purple-200' },
  boss: {
    label: 'Босс',
    classes: 'bg-gradient-to-r from-site-red/50 to-gold/50 text-gold-light',
  },
};

const SwordIcon = ({ className }: { className: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.5 17.5L3 6V3h3l11.5 11.5" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M13 19l6-6" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M16 16l4 4" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 21l2-2" />
  </svg>
);

/**
 * HP bar — rendered only when both values are present (FEAT-152 A5).
 * For an enemy with status "in_battle" the value is the last persisted one;
 * the «В бою» badge signals that.
 */
const HpBar = ({ current, max }: { current: number; max: number }) => {
  const pct = Math.max(0, Math.min(100, (current / max) * 100));
  return (
    <div className="stat-bar" title={`HP ${current} / ${max}`}>
      <div className="stat-bar-fill stat-bar-hp" style={{ width: `${pct}%` }} />
    </div>
  );
};

const InBattleBadge = ({ className = '' }: { className?: string }) => (
  <span
    className={`px-2 py-0.5 rounded-full bg-orange-500/80 text-white text-[9px] font-bold uppercase tracking-[0.04em] ${className}`}
  >
    В бою
  </span>
);

const Spinner = () => (
  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
);

/** Compact composition row of a pack card — the old PackMemberRow without its avatar. */
const PackMemberRow = ({ member }: { member: PackMemberInLocation }) => {
  const hasHp = member.current_hp != null && member.max_hp != null && member.max_hp > 0;

  return (
    <div className="flex flex-col gap-1 rounded-[10px] bg-black/30 border border-white/[0.06] px-2 py-1.5 min-w-0">
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-white text-[11px] font-medium truncate">
          {member.name} ×{member.count}
        </span>
        <span className="text-white/50 text-[9px] font-bold shrink-0 ml-auto">
          LVL {member.level}
        </span>
      </div>
      {hasHp && (
        <HpBar current={member.current_hp as number} max={member.max_hp as number} />
      )}
    </div>
  );
};

/** Level display of a pack — packs carry no `level`, so it is derived from members. */
const packLevelLabel = (pack: MobPackInLocation): string | null => {
  const levels = pack.members.map((m) => m.level).filter((l) => typeof l === 'number');
  if (levels.length === 0) return null;
  const min = Math.min(...levels);
  const max = Math.max(...levels);
  return min === max ? `LVL ${min}` : `LVL ${min}–${max}`;
};

/** Summed HP across the pack members that carry both values. */
const packHp = (pack: MobPackInLocation): { current: number; max: number } | null => {
  let current = 0;
  let max = 0;
  pack.members.forEach((m) => {
    if (m.current_hp != null && m.max_hp != null && m.max_hp > 0) {
      current += m.current_hp;
      max += m.max_hp;
    }
  });
  return max > 0 ? { current, max } : null;
};

const cardVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 },
};

const EnemiesSection = ({
  locationId,
  characterId,
  gatedMobIds = [],
}: EnemiesSectionProps) => {
  const navigate = useNavigate();

  const [mobs, setMobs] = useState<MobInLocation[]>([]);
  const [packs, setPacks] = useState<MobPackInLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [party, setParty] = useState<Party | null>(null);
  // Prefixed keys — mob and pack ids live in independent id spaces.
  const [attackingKey, setAttackingKey] = useState<string | null>(null);
  const [choosingKey, setChoosingKey] = useState<string | null>(null);

  // Toast only on the first failure; the inline message stays visible after that.
  const toastedRef = useRef(false);

  useEffect(() => {
    if (!characterId) {
      setParty(null);
      return;
    }
    getMyParty(characterId)
      .then(setParty)
      .catch(() => setParty(null));
  }, [characterId]);

  // Any co-located accepted squadmate enables the group option (FEAT-144 Ф3 + fix).
  const coLocatedMates = (party?.members ?? []).filter(
    (m) =>
      m.status === 'accepted' &&
      m.character_id !== characterId &&
      m.current_location_id === locationId,
  );
  const canGroup = !!party && coLocatedMates.length >= 1;

  const loadEnemies = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mobData, packData] = await Promise.all([
        fetchMobsByLocation(locationId),
        fetchMobPacksByLocation(locationId),
      ]);
      setMobs(mobData);
      setPacks(packData);
    } catch {
      const msg = 'Не удалось загрузить противников';
      setError(msg);
      if (!toastedRef.current) {
        toastedRef.current = true;
        toast.error(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [locationId]);

  useEffect(() => {
    loadEnemies();
  }, [loadEnemies]);

  // --- Battle launch — four distinct paths, kept strictly separate. ---

  /** Path 1 (solo) / Path 2 (group) — single mob, keyed on mob.character_id. */
  const handleAttackMob = async (mob: MobInLocation, group: boolean) => {
    if (!characterId) {
      toast.error('Выберите персонажа для начала боя');
      return;
    }
    if (mob.status === 'in_battle') {
      toast.error('Этот монстр уже в бою');
      return;
    }

    setChoosingKey(null);
    setAttackingKey(`mob-${mob.active_mob_id}`);
    try {
      const result = group
        ? await createPartyMobBattle(characterId, mob.character_id)
        : await createBattle(characterId, mob.character_id);
      toast.success(group ? 'Групповой бой начинается!' : 'Бой начинается!');
      navigate(`/location/${locationId}/battle/${result.battle_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Не удалось начать бой');
    } finally {
      setAttackingKey(null);
    }
  };

  /** Path 3 (solo) / Path 4 (group) — mob pack, keyed on pack.active_pack_id. */
  const handleAttackPack = async (pack: MobPackInLocation, group: boolean) => {
    if (!characterId) {
      toast.error('Выберите персонажа для начала боя');
      return;
    }
    if (pack.status === 'in_battle') {
      toast.error('Эта стая уже в бою');
      return;
    }

    setChoosingKey(null);
    setAttackingKey(`pack-${pack.active_pack_id}`);
    try {
      const result = group
        ? await createPartyPackBattle(characterId, pack.active_pack_id)
        : await createPackBattle(characterId, pack.active_pack_id);
      toast.success(group ? 'Групповой бой начинается!' : 'Бой начинается!');
      navigate(`/location/${locationId}/battle/${result.battle_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Не удалось начать бой');
    } finally {
      setAttackingKey(null);
    }
  };

  // Packs first — the taller card leads so the 2-column grid stays even at the top.
  const entries: EnemyEntry[] = [
    ...packs.map<EnemyEntry>((pack) => ({
      kind: 'pack',
      key: `pack-${pack.active_pack_id}`,
      pack,
    })),
    ...mobs.map<EnemyEntry>((mob) => ({
      kind: 'mob',
      key: `mob-${mob.active_mob_id}`,
      mob,
    })),
  ];
  const enemyCount = entries.length;

  /** Attack controls — shared chrome, but the caller supplies its own handler. */
  const renderActions = (
    entryKey: string,
    gated: boolean,
    disabled: boolean,
    onAttack: (group: boolean) => void,
  ) => {
    if (!characterId) return null;

    if (!gated) {
      return (
        <span className="text-white/35 text-[10px] text-center leading-tight">
          Нужен боевой пост
        </span>
      );
    }

    const isAttacking = attackingKey === entryKey;

    if (choosingKey === entryKey && !isAttacking) {
      return (
        <div className="flex gap-1.5 w-full">
          <button
            onClick={() => onAttack(true)}
            className="btn-blue text-[11px] px-2 py-1.5 flex-1"
          >
            Группой
          </button>
          <button
            onClick={() => onAttack(false)}
            className="text-[11px] px-2 py-1.5 flex-1 rounded-[9px] border border-white/20 text-white/70 hover:bg-white/5 transition-colors duration-200"
          >
            Соло
          </button>
        </div>
      );
    }

    return (
      <button
        onClick={() => (canGroup ? setChoosingKey(entryKey) : onAttack(false))}
        disabled={disabled || isAttacking}
        className="w-full py-1.5 rounded-[9px] bg-site-red/90 text-white text-[11px] font-medium uppercase tracking-[0.04em] hover:brightness-110 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
      >
        {isAttacking ? <Spinner /> : 'Напасть'}
      </button>
    );
  };

  return (
    // FEAT-153 §3.6: fixed 460px row-3 box from `sm` up; below it the height is
    // natural and the card grid caps at 320px. Error and empty states live
    // INSIDE the flex body so an empty block keeps its box instead of collapsing.
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-site-red/25 shadow-card overflow-hidden h-auto sm:h-[460px] flex flex-col">
      {/* Static header — no collapse toggle (fixed-height row, FEAT-153 §3.4) */}
      <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3.5 border-b border-white/[0.07] shrink-0">
        <SwordIcon className="w-[18px] h-[18px] text-stat-hp shrink-0" />
        <h2 className="text-stat-hp text-[13px] font-medium uppercase tracking-[0.08em]">
          Противники
        </h2>
        {!loading && enemyCount > 0 && (
          <span className="bg-site-red/60 text-white text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
            {enemyCount}
          </span>
        )}
        {loading && (
          <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
        )}
      </div>

      {error ? (
        <div className="flex-1 min-h-0 flex flex-col items-start justify-center gap-3 p-4 sm:p-5">
          <p className="text-site-red text-sm">{error}</p>
          <button onClick={loadEnemies} className="btn-blue text-sm px-4 py-2">
            Повторить
          </button>
        </div>
      ) : enemyCount === 0 && !loading ? (
        <div className="flex-1 min-h-0 flex items-center justify-center p-5 text-center text-white/50 text-sm">
          Противников нет
        </div>
      ) : (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.05 } } }}
          className="flex-1 min-h-0 grid grid-cols-1 sm:grid-cols-2 gap-2 p-3.5 sm:p-4 content-start items-start max-h-[320px] sm:max-h-none overflow-y-auto gold-scrollbar"
        >
          {entries.map((entry) => {
            // --- PACK branch ---
            if (entry.kind === 'pack') {
              const { pack } = entry;
              const packInBattle = pack.status === 'in_battle';
              const gated = gatedMobIds.includes(pack.lead_character_id);
              const totalMobs = pack.members.reduce((sum, m) => sum + m.count, 0);
              const levelLabel = packLevelLabel(pack);
              const hp = packHp(pack);

              return (
                <motion.div
                  key={entry.key}
                  variants={cardVariants}
                  className="flex flex-col items-center gap-2 p-2.5 pb-3 rounded-card bg-site-red/[0.06] border border-site-red/20 min-w-0"
                >
                  <div className="relative w-full h-[72px] rounded-[10px] overflow-hidden bg-black/40 shrink-0">
                    {pack.avatar ? (
                      <img
                        src={pack.avatar}
                        alt={pack.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-white/25 text-2xl">
                        ⚔
                      </div>
                    )}
                    {packInBattle && <InBattleBadge className="absolute top-1.5 right-1.5" />}
                  </div>

                  <div className="flex flex-col items-center gap-1 w-full min-w-0">
                    <span className="text-white text-[13px] font-medium text-center truncate w-full">
                      {pack.name}
                    </span>
                    <div className="flex items-center gap-1.5 flex-wrap justify-center">
                      {levelLabel && (
                        <span className="text-white/50 text-[10px] font-bold">{levelLabel}</span>
                      )}
                      <span className="px-2 py-0.5 rounded-full text-[9px] font-medium bg-purple-600/40 text-purple-200">
                        Стая
                      </span>
                    </div>
                    <span className="text-white/50 text-[10px]">{totalMobs} мобов</span>
                  </div>

                  {hp && <HpBar current={hp.current} max={hp.max} />}

                  {/* Composition */}
                  <div className="flex flex-col gap-1.5 w-full min-w-0">
                    {pack.members.map((m, idx) => (
                      <PackMemberRow key={`${entry.key}-member-${idx}`} member={m} />
                    ))}
                  </div>

                  {renderActions(entry.key, gated, packInBattle, (group) =>
                    handleAttackPack(pack, group),
                  )}
                </motion.div>
              );
            }

            // --- MOB branch ---
            const { mob } = entry;
            const tier = TIER_CONFIG[mob.tier] ?? TIER_CONFIG.normal;
            const mobInBattle = mob.status === 'in_battle';
            const gated = gatedMobIds.includes(mob.character_id);
            const hasHp = mob.current_hp != null && mob.max_hp != null && mob.max_hp > 0;

            return (
              <motion.div
                key={entry.key}
                variants={cardVariants}
                className="flex flex-col items-center gap-2 p-2.5 pb-3 rounded-card bg-site-red/[0.06] border border-site-red/20 min-w-0"
              >
                <div className="relative w-full h-[72px] rounded-[10px] overflow-hidden bg-black/40 shrink-0">
                  {mob.avatar ? (
                    <img
                      src={mob.avatar}
                      alt={mob.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-white/20">
                      <SwordIcon className="w-7 h-7" />
                    </div>
                  )}
                  {mobInBattle && <InBattleBadge className="absolute top-1.5 right-1.5" />}
                </div>

                <div className="flex flex-col items-center gap-1 w-full min-w-0">
                  <span className="text-white text-[13px] font-medium text-center truncate w-full">
                    {mob.name}
                  </span>
                  <div className="flex items-center gap-1.5 flex-wrap justify-center">
                    <span className="text-white/50 text-[10px] font-bold">LVL {mob.level}</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[9px] font-medium ${tier.classes}`}
                    >
                      {tier.label}
                    </span>
                  </div>
                </div>

                {hasHp && (
                  <HpBar current={mob.current_hp as number} max={mob.max_hp as number} />
                )}

                {renderActions(entry.key, gated, mobInBattle, (group) =>
                  handleAttackMob(mob, group),
                )}
              </motion.div>
            );
          })}
        </motion.div>
      )}
    </section>
  );
};

export default EnemiesSection;
