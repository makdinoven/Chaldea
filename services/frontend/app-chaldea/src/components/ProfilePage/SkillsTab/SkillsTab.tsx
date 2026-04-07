// ProfilePage SkillsTab — perk system (FEAT-125)
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import axios from 'axios';
import { useAppSelector } from '../../../redux/store';
import { X } from 'react-feather';
import type {
  CharacterSkillState,
  ResolvedSkill,
} from '../../SkillTreeView/types';
import { ruDamageType, ruEffectName, ruTargetSide } from '../../SkillTreeView/skillLabels';

interface SkillsTabProps {
  characterId: number;
}

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
  attack: 'Атака',
  defense: 'Защита',
  support: 'Поддержка',
};

const SKILL_TYPE_BADGE: Record<string, string> = {
  attack: 'text-red-300 bg-red-400/15',
  defense: 'text-sky-300 bg-sky-400/15',
  support: 'text-emerald-300 bg-emerald-400/15',
};

const SkillsTab = ({ characterId }: SkillsTabProps) => {
  const [skills, setSkills] = useState<CharacterSkillState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<CharacterSkillState | null>(null);
  const [resolved, setResolved] = useState<ResolvedSkill | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const character = useAppSelector((state) => state.user.character);
  const classId = (character as Record<string, unknown>)?.id_class as number | undefined;
  const cardStyle = CLASS_CARD_STYLES[classId ?? 1] ?? DEFAULT_CARD_STYLE;

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
      return;
    }
    setDetailLoading(true);
    axios
      .get<ResolvedSkill>(`/skills/${selectedSkill.skill_id}/resolved`, {
        params: { character_id: characterId },
      })
      .then((res) => setResolved(res.data))
      .catch(() => toast.error('Не удалось загрузить характеристики навыка'))
      .finally(() => setDetailLoading(false));
  }, [selectedSkill, characterId]);

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
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="gold-text text-xl font-medium uppercase">
          Изученные навыки ({skills.length})
        </h3>
        <Link to="/skill-tree" className="btn-line text-sm flex items-center gap-1.5">
          Дерево навыков
        </Link>
      </div>

      {skills.length === 0 ? (
        <div className="gray-bg p-8 text-center">
          <p className="text-white/40 text-lg mb-3">Нет изученных навыков</p>
          <Link to="/skill-tree" className="btn-blue inline-block">
            Открыть дерево навыков
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {skills.map((cs) => {
            const skillImage = cs.skill?.skill_image ?? null;
            const skillName = cs.skill?.name ?? `Навык #${cs.skill_id}`;
            const skillType = cs.skill?.skill_type ?? '';
            const typeBadge = SKILL_TYPE_BADGE[skillType] ?? '';
            const typeLabel = SKILL_TYPE_LABELS[skillType] ?? '';
            return (
              <button
                key={cs.character_skill_id}
                type="button"
                onClick={() => setSelectedSkill(cs)}
                className={`p-4 rounded-card border flex items-center gap-3 text-left transition-all duration-200 ease-site cursor-pointer ${cardStyle.bg} ${cardStyle.border} ${cardStyle.glow}`}
              >
                {skillImage ? (
                  <img
                    src={skillImage}
                    alt={skillName}
                    className="w-14 h-14 rounded-lg object-cover flex-shrink-0 border border-white/10"
                  />
                ) : (
                  <div className="w-14 h-14 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center flex-shrink-0">
                    <span className="text-white/20 text-xl">⚔</span>
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-white font-medium text-sm truncate">{skillName}</p>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    {typeLabel && (
                      <span
                        className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${typeBadge}`}
                      >
                        {typeLabel}
                      </span>
                    )}
                    <span className="text-white/40 text-xs">Уровень {cs.level}/4</span>
                    {cs.free_perk_points > 0 && (
                      <span className="text-gold text-xs">• очко перка</span>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}

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
              <div className="flex items-start justify-between mb-4 gap-3">
                <div className="flex items-center gap-4 min-w-0">
                  {selectedSkill.skill?.skill_image ? (
                    <img
                      src={selectedSkill.skill.skill_image}
                      alt={selectedSkill.skill.name}
                      className="w-16 h-16 rounded-lg object-cover border border-white/10"
                    />
                  ) : (
                    <div className="w-16 h-16 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center">
                      <span className="text-white/20 text-2xl">⚔</span>
                    </div>
                  )}
                  <div className="min-w-0">
                    <h2 className="gold-text text-xl font-medium truncate">
                      {selectedSkill.skill?.name}
                    </h2>
                    <div className="text-white/50 text-xs mt-1">
                      Уровень {selectedSkill.level}/4 · Перков: {selectedSkill.selected_perk_ids.length}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedSkill(null)}
                  className="text-white/40 hover:text-white transition-colors"
                >
                  <X size={20} />
                </button>
              </div>

              {detailLoading && !resolved && (
                <div className="flex justify-center py-6">
                  <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                </div>
              )}

              {resolved && (
                <>
                  <div className="flex flex-wrap gap-3 mb-4 text-sm">
                    <div className="text-white/80">Энергия: {resolved.cost_energy}</div>
                    <div className="text-white/80">Мана: {resolved.cost_mana}</div>
                    <div className="text-white/80">КД: {resolved.cooldown}</div>
                  </div>

                  {resolved.damage_entries.length > 0 && (
                    <div className="mb-3">
                      <h4 className="text-white/50 text-xs uppercase mb-1.5">Урон</h4>
                      <div className="space-y-1">
                        {resolved.damage_entries.map((d, i) => (
                          <div
                            key={i}
                            className="text-sm bg-white/5 rounded px-3 py-1.5 text-white/80"
                          >
                            {d.amount} {ruDamageType(d.damage_type)}
                            {d.target_side ? ` — ${ruTargetSide(d.target_side)}` : ''}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {resolved.effects.length > 0 && (
                    <div className="mb-3">
                      <h4 className="text-white/50 text-xs uppercase mb-1.5">Эффекты</h4>
                      <div className="space-y-1">
                        {resolved.effects.map((e, i) => (
                          <div
                            key={i}
                            className="text-sm bg-white/5 rounded px-3 py-1.5 text-purple-300"
                          >
                            {ruEffectName(e.effect_name, e.attribute_key)}
                            {e.duration ? ` · ${e.duration} ход.` : ''}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default SkillsTab;
