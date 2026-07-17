// ProfilePage TitlesTab — redesigned per Claude Design mock (FEAT-151).
// Keeps condition progress bars on locked titles, XP-reward badges and
// select/unselect actions (user decision); adds Все/Полученные/Закрытые filters.
import { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { Lock, Sparkles, Star } from 'lucide-react';
import { fetchCharacterTitles, setActiveTitle, unsetActiveTitle } from '../../../api/titles';
import type { CharacterTitle, TitleCondition } from '../../../types/titles';
import { useAppSelector } from '../../../redux/store';
import FilterChips, { type FilterChipItem } from '../shared/FilterChips';
import EmptyState from '../shared/EmptyState';

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

type TitleFilter = 'all' | 'unlocked' | 'locked';

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
  const [filter, setFilter] = useState<TitleFilter>('all');

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

  const unlockedCount = useMemo(() => titles.filter((t) => t.is_unlocked).length, [titles]);

  const filterItems: FilterChipItem[] = useMemo(
    () => [
      { key: 'all', label: 'Все', count: titles.length },
      { key: 'unlocked', label: 'Полученные', count: unlockedCount },
      { key: 'locked', label: 'Закрытые', count: titles.length - unlockedCount },
    ],
    [titles.length, unlockedCount]
  );

  const filteredTitles = useMemo(() => {
    if (filter === 'unlocked') return titles.filter((t) => t.is_unlocked);
    if (filter === 'locked') return titles.filter((t) => !t.is_unlocked);
    return titles;
  }, [titles, filter]);

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

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-4"
    >
      {/* Header row: title + counter, status filter */}
      <div className="flex items-center justify-between flex-wrap gap-3.5">
        <div className="flex items-center gap-3.5 min-w-0">
          <h3 className="gold-text text-sm font-medium uppercase tracking-[0.12em]">Титулы</h3>
          <span className="font-mono tabular-nums text-[13px] text-white/50">
            {unlockedCount}/{titles.length}
          </span>
        </div>
        <FilterChips
          items={filterItems}
          active={filter}
          onChange={(key) => setFilter(key as TitleFilter)}
        />
      </div>

      {/* Cards grid / empty states */}
      {titles.length === 0 ? (
        <EmptyState
          icon={<Star size={32} strokeWidth={1.5} className="text-white/20" />}
          message="Нет доступных титулов"
        />
      ) : filteredTitles.length === 0 ? (
        <EmptyState
          icon={
            filter === 'locked' ? (
              <Lock size={32} strokeWidth={1.5} className="text-white/20" />
            ) : (
              <Star size={32} strokeWidth={1.5} className="text-white/20" />
            )
          }
          message={
            filter === 'locked'
              ? 'Все титулы уже получены'
              : 'Нет титулов по выбранному фильтру'
          }
        />
      ) : (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.04 } },
          }}
          className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4"
        >
          {filteredTitles.map((title) => {
            const isActive = activeTitle === title.name;
            const isLocked = !title.is_unlocked;
            const hasXpReward = title.reward_passive_exp > 0 || title.reward_active_exp > 0;
            const rarityColor = RARITY_COLOR_CLASS[title.rarity] ?? 'text-white';
            const barColor = RARITY_BAR_CLASS[title.rarity] ?? 'bg-white/60';
            const rarityLabel = RARITY_LABELS[title.rarity] ?? title.rarity;

            const cardChrome = isActive
              ? 'border-gold/40 bg-gold/[0.05] shadow-[0_0_18px_rgba(240,217,92,0.12)]'
              : isLocked
                ? 'border-white/10 bg-black/25 opacity-60'
                : 'border-gold/[0.16] bg-black/30 shadow-card';

            return (
              <motion.div
                key={title.id_title}
                variants={{
                  hidden: { opacity: 0, y: 10 },
                  visible: { opacity: 1, y: 0 },
                }}
                className={`relative rounded-card border p-[18px] flex flex-col gap-2.5 transition-colors duration-200 ease-site ${cardChrome}`}
              >
                {/* Name + lock */}
                <div className="flex items-start justify-between gap-2.5">
                  <h4 className={`text-base font-medium leading-tight ${rarityColor}`}>
                    {title.name}
                  </h4>
                  {isLocked && (
                    <Lock size={15} strokeWidth={2} className="shrink-0 mt-0.5 text-white/40" />
                  )}
                </div>

                {/* Rarity label */}
                <span
                  className={`text-[10px] font-medium uppercase tracking-[0.06em] opacity-80 ${rarityColor}`}
                >
                  {rarityLabel}
                </span>

                {/* Description */}
                {title.description && (
                  <p className="text-xs leading-relaxed text-white/60">{title.description}</p>
                )}

                {/* Condition progress bars (locked titles only — kept per user decision) */}
                {isLocked && title.conditions && title.conditions.length > 0 && (
                  <div className="flex flex-col gap-1.5 mt-0.5">
                    {title.conditions.map((cond, idx) => {
                      const key = cond.stat ?? cond.type ?? `cond-${idx}`;
                      const progKey = cond.type === 'character_level' ? 'level' : key;
                      const prog = title.progress?.[progKey];
                      const pct = prog
                        ? Math.min(100, (prog.current / prog.required) * 100)
                        : 0;
                      const isMet = prog ? prog.current >= prog.required : false;

                      return (
                        <div key={idx}>
                          <div className="flex items-center justify-between text-[10px] mb-1">
                            <span className={isMet ? 'text-stat-energy' : 'text-white/50'}>
                              {getConditionLabel(cond)}
                            </span>
                            {prog && (
                              <span className="font-mono tabular-nums text-white/40">
                                {prog.current}/{prog.required}
                              </span>
                            )}
                          </div>
                          <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                isMet ? 'bg-stat-energy' : barColor
                              }`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* XP-reward badges (kept per user decision) */}
                {hasXpReward && (
                  <div className="flex flex-wrap gap-1.5">
                    {title.reward_passive_exp > 0 && (
                      <span className="flex items-center gap-1 px-2 py-0.5 rounded-full border border-site-blue/30 bg-site-blue/10 text-[10px] font-medium text-site-blue">
                        <Sparkles size={11} strokeWidth={1.8} className="shrink-0" />
                        +{title.reward_passive_exp} опыта
                      </span>
                    )}
                    {title.reward_active_exp > 0 && (
                      <span className="flex items-center gap-1 px-2 py-0.5 rounded-full border border-site-blue/30 bg-site-blue/10 text-[10px] font-medium text-site-blue">
                        <Sparkles size={11} strokeWidth={1.8} className="shrink-0" />
                        +{title.reward_active_exp} акт. опыта
                      </span>
                    )}
                  </div>
                )}

                {/* Status row */}
                <div className="flex items-center gap-2 mt-auto pt-1">
                  {isActive && (
                    <span className="w-[7px] h-[7px] rounded-full bg-gold shadow-[0_0_6px_rgba(240,217,92,0.9)]" />
                  )}
                  <span
                    className={`text-[11px] font-medium uppercase tracking-[0.05em] ${
                      isActive
                        ? 'text-gold'
                        : isLocked
                          ? 'text-white/40'
                          : 'text-stat-energy'
                    }`}
                  >
                    {isActive ? 'Активен' : isLocked ? 'Закрыт' : 'Получен'}
                  </span>
                </div>

                {/* Actions (unlocked titles only) */}
                {title.is_unlocked && (
                  <div className="pt-0.5">
                    {isActive ? (
                      <button
                        type="button"
                        onClick={handleUnsetActive}
                        disabled={actionLoading === -1}
                        className="w-full text-[11px] font-medium py-1.5 rounded-full border border-white/20 text-white/60 hover:text-white hover:border-white/40 transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {actionLoading === -1 ? '...' : 'Снять'}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleSetActive(title.id_title)}
                        disabled={actionLoading === title.id_title}
                        className="w-full text-[11px] font-medium py-1.5 rounded-full border border-gold/30 bg-gold/10 text-gold hover:bg-gold/20 transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed"
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
      )}
    </motion.div>
  );
};

export default TitlesTab;
