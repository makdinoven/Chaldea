import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import axios from 'axios';
import { useAppSelector } from '../../../redux/store';
import { X } from 'react-feather';

interface SkillEffect {
  id: number;
  effect_name: string;
  target_side: string;
  chance: number;
  duration: number;
  magnitude: number;
  attribute_key: string | null;
}

interface SkillDamage {
  id: number;
  damage_type: string;
  amount: number;
  chance: number;
  target_side: string;
  weapon_slot: string | null;
}

interface SkillRank {
  id: number;
  skill_id: number;
  rank_number: number;
  rank_name: string;
  cost_energy: number;
  cost_mana: number;
  cooldown: number;
  rank_image: string | null;
  rank_description: string | null;
  damage_entries: SkillDamage[];
  effects: SkillEffect[];
}

interface CharacterSkill {
  id: number;
  character_id: number;
  skill_rank_id: number;
  skill_rank: SkillRank;
  skill_name: string | null;
  skill_type: string | null;
  skill_image: string | null;
  skill_description: string | null;
  skill_min_level: number | null;
}

interface SkillsTabProps {
  characterId: number;
}

/* DB class IDs: 1=Warrior, 2=Rogue, 3=Mage */
const CLASS_CARD_STYLES: Record<number, { bg: string; border: string; glow: string }> = {
  1: {
    bg: 'bg-red-950/30',
    border: 'border-red-500/20',
    glow: 'hover:bg-red-950/40 hover:border-red-500/30',
  },
  2: {
    bg: 'bg-emerald-950/30',
    border: 'border-emerald-500/20',
    glow: 'hover:bg-emerald-950/40 hover:border-emerald-500/30',
  },
  3: {
    bg: 'bg-sky-950/30',
    border: 'border-sky-500/20',
    glow: 'hover:bg-sky-950/40 hover:border-sky-500/30',
  },
};

const DEFAULT_CARD_STYLE = CLASS_CARD_STYLES[1];

const SKILL_TYPE_LABELS: Record<string, string> = {
  attack: 'Атака', Attack: 'Атака',
  defense: 'Защита', Defense: 'Защита',
  support: 'Поддержка', Support: 'Поддержка',
};

const SKILL_TYPE_BADGE: Record<string, string> = {
  attack: 'text-red-300 bg-red-400/15', Attack: 'text-red-300 bg-red-400/15',
  defense: 'text-sky-300 bg-sky-400/15', Defense: 'text-sky-300 bg-sky-400/15',
  support: 'text-emerald-300 bg-emerald-400/15', Support: 'text-emerald-300 bg-emerald-400/15',
};

const EFFECT_NAMES: Record<string, string> = {
  Bleeding: 'Кровотечение',
  Poison: 'Отравление',
  Stun: 'Оглушение',
  Knockdown: 'Сбитие с ног',
  Daze: 'Ошеломление',
  Burn: 'Возгорание',
  Freeze: 'Обледенение',
  Wet: 'Мокрый',
  Electrify: 'Электролизация',
  Windburn: 'Обветрение',
  Holy: 'Святость',
  Curse: 'Проклятие',
  StatModifier: 'Модификатор',
  ArmorBreak: 'Раскол брони',
  MagicImpact: 'Магическое воздействие',
};

const DAMAGE_TYPES: Record<string, string> = {
  physical: 'физический', catting: 'режущий', crushing: 'дробящий',
  piercing: 'колющий', magic: 'магический', fire: 'огненный',
  ice: 'ледяной', watering: 'водный', electricity: 'электрический',
  wind: 'воздушный', sainting: 'святой', damning: 'тёмный', all: 'общий',
};

const TARGET_SIDE: Record<string, string> = {
  self: 'на себя', enemy: 'на врага',
};

const SkillsTab = ({ characterId }: SkillsTabProps) => {
  const [skills, setSkills] = useState<CharacterSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<CharacterSkill | null>(null);

  const character = useAppSelector((state) => state.user.character);
  const classId = (character as Record<string, unknown>)?.id_class as number | undefined;
  const cardStyle = CLASS_CARD_STYLES[classId ?? 1] ?? DEFAULT_CARD_STYLE;

  useEffect(() => {
    const fetchSkills = async () => {
      setLoading(true);
      try {
        const res = await axios.get(`/skills/characters/${characterId}/skills`);
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
      className="space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="gold-text text-xl font-medium uppercase">
          Изученные навыки ({skills.length})
        </h3>
        <Link
          to="/skill-tree"
          className="btn-line text-sm flex items-center gap-1.5"
        >
          Дерево навыков
        </Link>
      </div>

      {/* Skills grouped by level */}
      {skills.length === 0 ? (
        <div className="gray-bg p-8 text-center">
          <p className="text-white/40 text-lg mb-3">Нет изученных навыков</p>
          <Link to="/skill-tree" className="btn-blue inline-block">
            Открыть дерево навыков
          </Link>
        </div>
      ) : (
        <div className="space-y-6">
          {(() => {
            // Group skills by level tier (1, 5, 10, 15, ... 50)
            const TIERS = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50];
            const getTier = (lvl: number): number => {
              for (let i = TIERS.length - 1; i >= 0; i--) {
                if (lvl >= TIERS[i]) return TIERS[i];
              }
              return 1;
            };

            const grouped = new Map<number, CharacterSkill[]>();
            for (const cs of skills) {
              const lvl = cs.skill_min_level ?? cs.skill_rank.level_requirement ?? 1;
              const tier = getTier(lvl);
              if (!grouped.has(tier)) grouped.set(tier, []);
              grouped.get(tier)!.push(cs);
            }

            const sortedTiers = [...grouped.keys()].sort((a, b) => a - b);

            return sortedTiers.map((tier) => {
              const tierSkills = grouped.get(tier)!;
              return (
                <div key={tier}>
                  {/* Tier header */}
                  <div className="flex items-center gap-3 mb-3">
                    <div className="h-px flex-1 bg-white/10" />
                    <span className="text-white/40 text-xs font-medium uppercase tracking-wider">
                      Уровень {tier}
                    </span>
                    <div className="h-px flex-1 bg-white/10" />
                  </div>

                  {/* Skills in this tier */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {tierSkills.map((cs) => {
                      const rank = cs.skill_rank;
                      const skillImage = cs.skill_image || rank.rank_image;
                      const skillName = cs.skill_name || rank.rank_name;
                      const skillType = cs.skill_type;
                      const typeBadge = SKILL_TYPE_BADGE[skillType ?? ''] ?? '';
                      const typeLabel = SKILL_TYPE_LABELS[skillType ?? ''] ?? '';

                      return (
                        <button
                          key={cs.id}
                          onClick={() => setSelectedSkill(cs)}
                          className={`
                            p-4 rounded-card border flex items-center gap-3 text-left
                            transition-all duration-200 ease-site cursor-pointer
                            ${cardStyle.bg} ${cardStyle.border} ${cardStyle.glow}
                          `}
                        >
                          {skillImage ? (
                            <img
                              src={skillImage}
                              alt={skillName ?? ''}
                              className="w-14 h-14 rounded-lg object-cover flex-shrink-0 border border-white/10"
                            />
                          ) : (
                            <div className="w-14 h-14 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center flex-shrink-0">
                              <span className="text-white/20 text-xl">⚔</span>
                            </div>
                          )}
                          <div className="min-w-0 flex-1">
                            <p className="text-white font-medium text-sm truncate">
                              {skillName}
                            </p>
                            <div className="flex items-center gap-2 mt-1">
                              {typeLabel && (
                                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${typeBadge}`}>
                                  {typeLabel}
                                </span>
                              )}
                              <span className="text-white/40 text-xs">
                                Ранг {rank.rank_number}
                              </span>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            });
          })()}
        </div>
      )}

      {/* Skill detail modal */}
      <AnimatePresence>
        {selectedSkill && (
          <div
            className="modal-overlay"
            onClick={() => setSelectedSkill(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline max-w-md w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              {(() => {
                const cs = selectedSkill;
                const rank = cs.skill_rank;
                const skillImage = cs.skill_image || rank.rank_image;
                const skillName = cs.skill_name || rank.rank_name;
                const skillType = cs.skill_type;
                const typeBadge = SKILL_TYPE_BADGE[skillType ?? ''] ?? '';
                const typeLabel = SKILL_TYPE_LABELS[skillType ?? ''] ?? '';

                return (
                  <>
                    {/* Header */}
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-center gap-4">
                        {skillImage ? (
                          <img
                            src={skillImage}
                            alt={skillName ?? ''}
                            className="w-16 h-16 rounded-lg object-cover border border-white/10"
                          />
                        ) : (
                          <div className="w-16 h-16 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center">
                            <span className="text-white/20 text-2xl">⚔</span>
                          </div>
                        )}
                        <div>
                          <h2 className="gold-text text-xl font-medium">
                            {skillName}
                          </h2>
                          <div className="flex items-center gap-2 mt-1">
                            {typeLabel && (
                              <span className={`text-xs font-medium px-2 py-0.5 rounded ${typeBadge}`}>
                                {typeLabel}
                              </span>
                            )}
                            <span className="text-white/50 text-xs">
                              Ранг {rank.rank_number}
                            </span>
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => setSelectedSkill(null)}
                        className="text-white/40 hover:text-white transition-colors"
                      >
                        <X size={20} />
                      </button>
                    </div>

                    {/* Skill description */}
                    {cs.skill_description && (
                      <p className="text-white/70 text-sm mb-3 leading-relaxed">
                        {cs.skill_description}
                      </p>
                    )}

                    {/* Rank description */}
                    {rank.rank_description && rank.rank_description !== cs.skill_description && (
                      <p className="text-white/50 text-xs mb-3 leading-relaxed italic">
                        {rank.rank_description}
                      </p>
                    )}

                    {/* Costs */}
                    {(rank.cost_energy > 0 || rank.cost_mana > 0 || rank.cooldown > 0) && (
                      <div className="flex flex-wrap gap-3 mb-4">
                        {rank.cost_energy > 0 && (
                          <div className="flex items-center gap-1.5 text-sm">
                            <span className="text-yellow-400">⚡</span>
                            <span className="text-white/60">Энергия:</span>
                            <span className="text-white font-medium">{rank.cost_energy}</span>
                          </div>
                        )}
                        {rank.cost_mana > 0 && (
                          <div className="flex items-center gap-1.5 text-sm">
                            <span className="text-blue-400">💧</span>
                            <span className="text-white/60">Мана:</span>
                            <span className="text-white font-medium">{rank.cost_mana}</span>
                          </div>
                        )}
                        {rank.cooldown > 0 && (
                          <div className="flex items-center gap-1.5 text-sm">
                            <span className="text-white/40">⏱</span>
                            <span className="text-white/60">Перезарядка:</span>
                            <span className="text-white font-medium">{rank.cooldown} ход.</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Damage entries */}
                    {rank.damage_entries.length > 0 && (
                      <div className="mb-4">
                        <h4 className="text-white/50 text-xs font-medium uppercase tracking-wider mb-2">
                          Урон
                        </h4>
                        <div className="space-y-1.5">
                          {rank.damage_entries.map((d) => (
                            <div key={d.id} className="flex items-center justify-between text-sm bg-white/5 rounded px-3 py-1.5">
                              <span className="text-white/80">
                                {DAMAGE_TYPES[d.damage_type] ?? d.damage_type}
                              </span>
                              <div className="flex items-center gap-2">
                                <span className="text-red-300 font-medium">{d.amount}</span>
                                {d.chance < 100 && (
                                  <span className="text-white/40 text-xs">({d.chance}%)</span>
                                )}
                                <span className="text-white/30 text-xs">
                                  {TARGET_SIDE[d.target_side] ?? d.target_side}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Effects */}
                    {rank.effects.length > 0 && (
                      <div className="mb-4">
                        <h4 className="text-white/50 text-xs font-medium uppercase tracking-wider mb-2">
                          Эффекты
                        </h4>
                        <div className="space-y-1.5">
                          {rank.effects.map((e) => (
                            <div key={e.id} className="flex items-center justify-between text-sm bg-white/5 rounded px-3 py-1.5">
                              <span className="text-purple-300">
                                {EFFECT_NAMES[e.effect_name] ?? e.effect_name}
                              </span>
                              <div className="flex items-center gap-2 text-xs text-white/50">
                                {e.magnitude > 0 && <span>×{e.magnitude}</span>}
                                {e.duration > 0 && <span>{e.duration} ход.</span>}
                                {e.chance < 100 && <span>{e.chance}%</span>}
                                <span className="text-white/30">
                                  {TARGET_SIDE[e.target_side] ?? e.target_side}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* No damage/effects */}
                    {rank.damage_entries.length === 0 && rank.effects.length === 0 && (
                      <p className="text-white/30 text-sm mb-4">
                        Нет данных об уроне и эффектах для этого ранга
                      </p>
                    )}
                  </>
                );
              })()}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default SkillsTab;
