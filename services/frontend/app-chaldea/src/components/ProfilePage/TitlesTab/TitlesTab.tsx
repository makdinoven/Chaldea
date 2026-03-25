import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { fetchCharacterTitles, setActiveTitle, unsetActiveTitle } from '../../../api/titles';
import type { CharacterTitle, TitleCondition } from '../../../types/titles';
import { useAppSelector } from '../../../redux/store';

/* ── Dictionaries ── */

const RARITY_LABELS: Record<string, string> = {
  common: 'Обычный',
  rare: 'Редкий',
  legendary: 'Легендарный',
};

const RARITY_COLOR_CLASS: Record<string, string> = {
  common: 'text-rarity-common',
  rare: 'text-rarity-rare',
  legendary: 'text-rarity-legendary',
};

const RARITY_BAR_CLASS: Record<string, string> = {
  common: 'bg-white/60',
  rare: 'bg-site-blue',
  legendary: 'bg-gold',
};

const STAT_LABELS: Record<string, string> = {
  // Cumulative stats
  total_damage_dealt: 'Урон нанесён',
  total_damage_received: 'Урон получен',
  pve_kills: 'Мобов убито',
  pvp_wins: 'PvP побед',
  pvp_losses: 'PvP поражений',
  total_battles: 'Боёв всего',
  max_damage_single_battle: 'Макс. урон за бой',
  max_win_streak: 'Макс. серия побед',
  current_win_streak: 'Текущая серия побед',
  total_rounds_survived: 'Раундов пережито',
  low_hp_wins: 'Побед с HP < 10%',
  total_gold_earned: 'Золота заработано',
  total_gold_spent: 'Золота потрачено',
  items_bought: 'Предметов куплено',
  items_sold: 'Предметов продано',
  locations_visited: 'Локаций посещено',
  total_transitions: 'Переходов',
  skills_used: 'Навыков использовано',
  items_equipped: 'Предметов экипировано',
  // Base attributes
  strength: 'Сила',
  agility: 'Ловкость',
  intelligence: 'Интеллект',
  endurance: 'Выносливость',
  charisma: 'Харизма',
  luck: 'Удача',
  level: 'Уровень',
  // Resources
  health: 'Здоровье',
  mana: 'Мана',
  energy: 'Энергия',
  stamina: 'Стамина',
  max_health: 'Макс. здоровье',
  max_mana: 'Макс. мана',
  max_energy: 'Макс. энергия',
  max_stamina: 'Макс. стамина',
  current_health: 'Тек. здоровье',
  current_mana: 'Тек. мана',
  current_energy: 'Тек. энергия',
  current_stamina: 'Тек. стамина',
  // Combat
  damage: 'Урон',
  dodge: 'Уклонение',
  critical_hit_chance: 'Шанс крит. удара',
  critical_damage: 'Крит. урон',
  // Resistances
  res_effects: 'Сопр. эффектам',
  res_physical: 'Сопр. физ. урону',
  res_catting: 'Сопр. режущему',
  res_crushing: 'Сопр. дробящему',
  res_piercing: 'Сопр. колющему',
  res_magic: 'Сопр. магии',
  res_fire: 'Сопр. огню',
  res_ice: 'Сопр. льду',
  res_watering: 'Сопр. воде',
  res_electricity: 'Сопр. электричеству',
  res_sainting: 'Сопр. святому',
  res_wind: 'Сопр. ветру',
  res_damning: 'Сопр. проклятию',
  // Vulnerabilities
  vul_effects: 'Уязв. к эффектам',
  vul_physical: 'Уязв. к физ. урону',
  vul_catting: 'Уязв. к режущему',
  vul_crushing: 'Уязв. к дробящему',
  vul_piercing: 'Уязв. к колющему',
  vul_magic: 'Уязв. к магии',
  vul_fire: 'Уязв. к огню',
  vul_ice: 'Уязв. к льду',
  vul_watering: 'Уязв. к воде',
  vul_electricity: 'Уязв. к электричеству',
  vul_sainting: 'Уязв. к святому',
  vul_wind: 'Уязв. к ветру',
  vul_damning: 'Уязв. к проклятию',
  // Experience
  passive_experience: 'Пассивный опыт',
  active_experience: 'Активный опыт',
};

/* ── Helpers ── */

const getConditionLabel = (c: TitleCondition): string => {
  if (c.type === 'admin_grant') return 'Ручная выдача';
  if (c.type === 'character_level') return 'Уровень';
  return c.stat ? (STAT_LABELS[c.stat] ?? c.stat) : c.type;
};

/* ── Props ── */

interface TitlesTabProps {
  characterId: number;
}

/* ── Component ── */

const TitlesTab = ({ characterId }: TitlesTabProps) => {
  const [titles, setTitles] = useState<CharacterTitle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const activeTitle = useAppSelector((state) => state.profile.character?.active_title ?? null);

  const loadTitles = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCharacterTitles(characterId);
      setTitles(data);
    } catch {
      const msg = 'Не удалось загрузить титулы';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTitles();
  }, [characterId]);

  const handleSetActive = async (titleId: number) => {
    setActionLoading(titleId);
    try {
      await setActiveTitle(characterId, titleId);
      toast.success('Титул установлен');
      await loadTitles();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Ошибка при установке титула';
      toast.error(msg);
    } finally {
      setActionLoading(null);
    }
  };

  const handleUnsetActive = async () => {
    setActionLoading(-1);
    try {
      await unsetActiveTitle(characterId);
      toast.success('Активный титул снят');
      await loadTitles();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Ошибка при снятии титула';
      toast.error(msg);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error && titles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-white/50 text-lg">{error}</p>
      </div>
    );
  }

  const unlockedCount = titles.filter((t) => t.is_unlocked).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="space-y-3"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="gold-text text-lg font-medium uppercase">
          Титулы ({unlockedCount}/{titles.length})
        </h3>
      </div>

      {titles.length === 0 && (
        <p className="text-white/50 text-sm">Нет доступных титулов</p>
      )}

      {/* Title cards grid */}
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.04 } },
        }}
        className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2"
      >
        {titles.map((title) => {
          const isActive = activeTitle === title.name;
          const hasXpReward = title.reward_passive_exp > 0 || title.reward_active_exp > 0;
          const rarityColor = RARITY_COLOR_CLASS[title.rarity] ?? 'text-white';
          const barColor = RARITY_BAR_CLASS[title.rarity] ?? 'bg-white/60';

          return (
            <motion.div
              key={title.id_title}
              variants={{
                hidden: { opacity: 0, scale: 0.95 },
                visible: { opacity: 1, scale: 1 },
              }}
              className={`relative rounded-lg p-2.5 flex flex-col gap-1.5 transition-all duration-200 ${
                title.is_unlocked
                  ? 'bg-black/50'
                  : 'bg-black/30 opacity-50'
              } ${isActive ? 'gold-outline gold-outline-thick' : ''}`}
            >
              {/* Title name + rarity */}
              <div className="flex items-start justify-between gap-1">
                <h4 className={`text-sm font-medium leading-tight ${rarityColor}`}>
                  {title.name}
                </h4>
                {isActive && (
                  <span className="shrink-0 text-[8px] font-medium uppercase text-gold px-1 py-0.5 rounded bg-gold/20">
                    ✦
                  </span>
                )}
              </div>

              {/* Description */}
              {title.description && (
                <p className="text-white/50 text-[11px] leading-snug line-clamp-2">{title.description}</p>
              )}

              {/* Progress bars */}
              {title.conditions && title.conditions.length > 0 && !title.is_unlocked && (
                <div className="flex flex-col gap-1 mt-0.5">
                  {title.conditions.map((cond, idx) => {
                    const key = cond.stat ?? cond.type ?? `cond-${idx}`;
                    const progKey = cond.type === 'character_level' ? 'level' : key;
                    const prog = title.progress?.[progKey];
                    const pct = prog ? Math.min(100, (prog.current / prog.required) * 100) : 0;
                    const isMet = prog ? prog.current >= prog.required : false;

                    return (
                      <div key={idx}>
                        <div className="flex items-center justify-between text-[10px] mb-0.5">
                          <span className={isMet ? 'text-green-400' : 'text-white/50'}>
                            {getConditionLabel(cond)}
                          </span>
                          {prog && (
                            <span className="text-white/30">
                              {prog.current}/{prog.required}
                            </span>
                          )}
                        </div>
                        <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${
                              isMet ? 'bg-green-400' : barColor
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Unlocked checkmark for completed titles */}
              {title.is_unlocked && title.conditions && title.conditions.length > 0 && (
                <span className="text-green-400 text-[10px]">✓ Получен</span>
              )}

              {/* XP Rewards */}
              {hasXpReward && (
                <div className="flex flex-wrap gap-x-2 text-[10px] text-white/40">
                  {title.reward_passive_exp > 0 && (
                    <span>+{title.reward_passive_exp} опыта</span>
                  )}
                  {title.reward_active_exp > 0 && (
                    <span>+{title.reward_active_exp} акт. опыта</span>
                  )}
                </div>
              )}

              {/* Actions */}
              {title.is_unlocked && (
                <div className="mt-auto pt-1">
                  {isActive ? (
                    <button
                      onClick={handleUnsetActive}
                      disabled={actionLoading === -1}
                      className="w-full text-[10px] py-1 rounded border border-white/20 text-white/50 hover:text-white hover:border-white/40 transition-colors"
                    >
                      {actionLoading === -1 ? '...' : 'Снять'}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleSetActive(title.id_title)}
                      disabled={actionLoading === title.id_title}
                      className="w-full text-[10px] py-1 rounded bg-site-blue/20 text-site-blue hover:bg-site-blue/30 transition-colors"
                    >
                      {actionLoading === title.id_title ? '...' : 'Выбрать'}
                    </button>
                  )}
                </div>
              )}
            </motion.div>
          );
        })}
      </motion.div>
    </motion.div>
  );
};

export default TitlesTab;
