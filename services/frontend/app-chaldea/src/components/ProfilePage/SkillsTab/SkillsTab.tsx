// ProfilePage SkillsTab — redesigned per Claude Design mock (FEAT-151),
// perk system from FEAT-125. Detail modal (ResolvedSkillCard) kept as-is.
import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import axios from 'axios';
import {
  Network,
  Zap,
  Droplet,
  Clock,
  Swords,
  Shield,
  Sparkles,
  X,
} from 'lucide-react';
import type {
  CharacterSkillState,
  ResolvedSkill,
  SkillWithPerks,
} from '../../SkillTreeView/types';
import FilterChips, { type FilterChipItem } from '../shared/FilterChips';
import EmptyState from '../shared/EmptyState';
import ResolvedSkillCard from './ResolvedSkillCard';

interface SkillsTabProps {
  characterId: number;
}

const MAX_SKILL_LEVEL = 4;

const SKILL_TYPE_LABELS: Record<string, string> = {
  attack: 'Атака',
  defense: 'Защита',
  support: 'Поддержка',
};

const SKILL_TYPE_BADGE: Record<string, string> = {
  attack: 'text-stat-hp bg-stat-hp/10',
  defense: 'text-site-blue bg-site-blue/10',
  support: 'text-stat-energy bg-stat-energy/10',
};

const SKILL_TYPE_FALLBACK_ICON: Record<string, typeof Swords> = {
  attack: Swords,
  defense: Shield,
  support: Sparkles,
};

const TYPE_FILTERS: FilterChipItem[] = [
  { key: 'all', label: 'Все' },
  { key: 'attack', label: 'Атака', dot: 'bg-stat-hp' },
  { key: 'defense', label: 'Защита', dot: 'bg-site-blue' },
  { key: 'support', label: 'Поддержка', dot: 'bg-stat-energy' },
];

/** API returns capitalized skill_type ('Attack'/'Defense'/'Support') — normalize to lowercase map keys */
const normalizeSkillType = (t: string | null | undefined): string => (t ?? '').toLowerCase();

/** Russian pluralization for the perk-points chip */
const perkPointsText = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} очко перка`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} очка перков`;
  return `${n} очков перков`;
};

const SkillsTab = ({ characterId }: SkillsTabProps) => {
  const [skills, setSkills] = useState<CharacterSkillState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState('all');
  const [selectedSkill, setSelectedSkill] = useState<CharacterSkillState | null>(null);
  const [resolved, setResolved] = useState<ResolvedSkill | null>(null);
  const [skillWithPerks, setSkillWithPerks] = useState<SkillWithPerks | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const fetchSkills = async () => {
      setLoading(true);
      try {
        const res = await axios.get<CharacterSkillState[]>(
          `/skills/characters/${characterId}/skills`
        );
        setSkills(res.data);
      } catch {
        setError('Не удалось загрузить навыки');
        toast.error('Не удалось загрузить навыки');
      } finally {
        setLoading(false);
      }
    };
    fetchSkills();
  }, [characterId]);

  useEffect(() => {
    if (!selectedSkill) {
      setResolved(null);
      setSkillWithPerks(null);
      return;
    }
    setDetailLoading(true);
    Promise.all([
      axios.get<ResolvedSkill>(`/skills/${selectedSkill.skill_id}/resolved`, {
        params: { character_id: characterId },
      }),
      axios.get<SkillWithPerks>(`/skills/${selectedSkill.skill_id}`),
    ])
      .then(([resolvedRes, skillRes]) => {
        setResolved(resolvedRes.data);
        setSkillWithPerks(skillRes.data);
      })
      .catch(() => {
        toast.error('Не удалось загрузить характеристики навыка');
        setError('Не удалось загрузить характеристики навыка');
      })
      .finally(() => setDetailLoading(false));
  }, [selectedSkill, characterId]);

  const totalPerkPoints = useMemo(
    () => skills.reduce((sum, cs) => sum + cs.free_perk_points, 0),
    [skills]
  );

  const filteredSkills = useMemo(
    () =>
      typeFilter === 'all'
        ? skills
        : skills.filter((cs) => normalizeSkillType(cs.skill?.skill_type) === typeFilter),
    [skills, typeFilter]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error && skills.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-white/50 text-lg">{error}</p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-4"
    >
      {/* Header row: title + counter, perk-points chip, skill-tree button */}
      <div className="flex items-center justify-between flex-wrap gap-3.5">
        <div className="flex items-center gap-3.5 min-w-0">
          <h3 className="gold-text text-sm font-medium uppercase tracking-[0.12em]">
            Изученные навыки
          </h3>
          <span className="font-mono tabular-nums text-[13px] text-white/50">
            {skills.length}
          </span>
        </div>
        <div className="flex items-center gap-3.5 flex-wrap">
          {totalPerkPoints > 0 && (
            <span className="flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-gold/30 bg-gold/[0.08]">
              <span className="w-2 h-2 rounded-full bg-gold shadow-[0_0_8px_rgba(240,217,92,0.8)]" />
              <span className="text-xs font-medium text-gold">
                {perkPointsText(totalPerkPoints)}
              </span>
            </span>
          )}
          <Link
            to="/skill-tree"
            className="btn-blue flex items-center gap-2 px-[18px] py-2.5 text-xs font-medium tracking-[0.04em]"
          >
            <Network size={15} strokeWidth={1.8} className="shrink-0" />
            Дерево навыков
          </Link>
        </div>
      </div>

      {/* Type filter */}
      <FilterChips items={TYPE_FILTERS} active={typeFilter} onChange={setTypeFilter} />

      {/* Cards grid */}
      {skills.length === 0 ? (
        <EmptyState
          icon={<Sparkles size={32} strokeWidth={1.5} className="text-white/20" />}
          message="Нет изученных навыков"
          action={
            <Link to="/skill-tree" className="btn-blue px-6 py-2.5 text-sm">
              Открыть дерево навыков
            </Link>
          }
        />
      ) : filteredSkills.length === 0 ? (
        <EmptyState
          icon={<Sparkles size={32} strokeWidth={1.5} className="text-white/20" />}
          message="Нет навыков выбранного типа"
        />
      ) : (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.05 } },
          }}
          className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3.5"
        >
          {filteredSkills.map((cs) => {
            const skillImage = cs.skill?.skill_image ?? null;
            const skillName = cs.skill?.name ?? `Навык #${cs.skill_id}`;
            const skillType = normalizeSkillType(cs.skill?.skill_type);
            const typeBadge = SKILL_TYPE_BADGE[skillType] ?? 'text-white/70 bg-white/10';
            const typeLabel = SKILL_TYPE_LABELS[skillType] ?? '';
            const FallbackIcon = SKILL_TYPE_FALLBACK_ICON[skillType] ?? Swords;
            const hasPerk = cs.selected_perk_ids.length > 0;
            const costEnergy = cs.skill?.cost_energy ?? 0;
            const costMana = cs.skill?.cost_mana ?? 0;
            const cooldown = cs.skill?.cooldown ?? 0;
            return (
              <motion.button
                key={cs.character_skill_id}
                variants={{
                  hidden: { opacity: 0, y: 10 },
                  visible: { opacity: 1, y: 0 },
                }}
                type="button"
                onClick={() => setSelectedSkill(cs)}
                className="relative rounded-card bg-black/30 border border-gold/[0.16] shadow-card flex gap-4 p-4 text-left cursor-pointer transition-colors duration-200 ease-site hover:border-gold/40"
              >
                {/* 62px icon in gold-gradient frame */}
                <div className="w-[62px] h-[62px] shrink-0 rounded-[14px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
                  <div className="w-full h-full rounded-xl bg-site-dark flex items-center justify-center overflow-hidden">
                    {skillImage ? (
                      <img
                        src={skillImage}
                        alt={skillName}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <FallbackIcon
                        size={26}
                        strokeWidth={1.6}
                        className="text-gold/70"
                      />
                    )}
                  </div>
                </div>

                <div className="flex flex-col gap-2 flex-1 min-w-0">
                  <div className="flex flex-col gap-1">
                    <span
                      className={`text-white text-[15px] font-medium leading-tight truncate ${hasPerk ? 'pr-14' : ''}`}
                    >
                      {skillName}
                    </span>
                    {typeLabel && (
                      <span
                        className={`w-fit text-[10px] font-medium uppercase tracking-[0.06em] px-2 py-0.5 rounded ${typeBadge}`}
                      >
                        {typeLabel}
                      </span>
                    )}
                  </div>

                  {/* Level pips /4 */}
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1">
                      {Array.from({ length: MAX_SKILL_LEVEL }, (_, i) => (
                        <span
                          key={i}
                          className={`w-5 h-1 rounded-full ${i < cs.level ? 'bg-gold' : 'bg-white/15'}`}
                        />
                      ))}
                    </div>
                    <span className="font-mono tabular-nums text-[11px] text-white/50">
                      {cs.level}/{MAX_SKILL_LEVEL}
                    </span>
                  </div>

                  {/* Cost chips: energy / mana / cooldown (always shown, incl. 0) */}
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1.5 text-xs text-white/65">
                      <Zap size={13} strokeWidth={1.8} className="text-stat-energy shrink-0" />
                      <span className="font-mono tabular-nums">{costEnergy}</span>
                    </span>
                    <span className="flex items-center gap-1.5 text-xs text-white/65">
                      <Droplet size={13} strokeWidth={1.8} className="text-site-blue shrink-0" />
                      <span className="font-mono tabular-nums">{costMana}</span>
                    </span>
                    <span className="flex items-center gap-1.5 text-xs text-white/65">
                      <Clock size={13} strokeWidth={1.8} className="text-white/50 shrink-0" />
                      <span className="font-mono tabular-nums">{cooldown}</span>
                    </span>
                  </div>
                </div>

                {/* «перк» badge */}
                {hasPerk && (
                  <span className="absolute top-3 right-3 flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-gold/[0.35] bg-gold/[0.12]">
                    <span className="w-1.5 h-1.5 rounded-full bg-gold shadow-[0_0_6px_rgba(240,217,92,0.9)]" />
                    <span className="text-[9.5px] font-medium uppercase tracking-[0.04em] text-gold">
                      перк
                    </span>
                  </span>
                )}
              </motion.button>
            );
          })}
        </motion.div>
      )}

      {/* Detail modal — existing resolved-skill wiring, kept as-is */}
      <AnimatePresence>
        {selectedSkill && (
          <div className="modal-overlay" onClick={() => setSelectedSkill(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline max-w-md w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-end mb-2">
                <button
                  type="button"
                  onClick={() => setSelectedSkill(null)}
                  className="text-white/40 hover:text-white transition-colors duration-200 ease-site"
                  aria-label="Закрыть"
                >
                  <X size={20} />
                </button>
              </div>

              {detailLoading && !resolved && (
                <div className="flex justify-center py-6">
                  <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                </div>
              )}

              {!detailLoading && !resolved && error && (
                <div className="text-site-red text-sm text-center py-4">{error}</div>
              )}

              {resolved && (
                <ResolvedSkillCard resolved={resolved} skill={skillWithPerks} />
              )}

              <div className="text-white/40 text-xs mt-3 text-center">
                Уровень {selectedSkill.level}/{MAX_SKILL_LEVEL}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default SkillsTab;
