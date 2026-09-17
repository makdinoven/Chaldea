// ProfilePage TitlesTab — single title card (extracted from TitlesTab in FEAT-166,
// no logic change). Keeps condition progress bars on locked titles, XP-reward
// badges and select/unselect actions (FEAT-151 user decision).
import { motion } from 'motion/react';
import { Lock, Sparkles } from 'lucide-react';
import type { CharacterTitle, TitleCondition } from '../../../types/titles';
import ProfileCard from '../shared/ProfileCard';
import ProgressBar, { type ProgressBarVariant } from '../shared/ProgressBar';

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

// Condition bar fill per rarity (FEAT-166: ProgressBar variants).
const RARITY_BAR_VARIANT: Record<string, ProgressBarVariant> = {
  common: 'neutral',
  rare: 'mana',
  legendary: 'gold',
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

const CARD_VARIANTS = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 },
};

const ACTIVE_GLOW_CLASS = 'shadow-[0_0_18px_rgba(240,217,92,0.12)]';

/* ── Props ── */

interface TitleCardProps {
  title: CharacterTitle;
  isActive: boolean;
  actionLoading: number | null;
  onSetActive: (titleId: number) => void;
  onUnsetActive: () => void;
}

/* ── Component ── */

const TitleCard = ({
  title,
  isActive,
  actionLoading,
  onSetActive,
  onUnsetActive,
}: TitleCardProps) => {
  const isLocked = !title.is_unlocked;
  const hasXpReward = title.reward_passive_exp > 0 || title.reward_active_exp > 0;
  const rarityColor = RARITY_COLOR_CLASS[title.rarity] ?? 'text-white';
  const barVariant = RARITY_BAR_VARIANT[title.rarity] ?? 'gold';
  const rarityLabel = RARITY_LABELS[title.rarity] ?? title.rarity;

  // Card chrome (1:1 with the former `cardChrome`):
  // active → `active` + soft glow, locked → `locked`, earned → gold `accent`.
  return (
    <motion.div variants={CARD_VARIANTS} className="flex">
      <ProfileCard
        variant={!isActive && !isLocked ? 'accent' : 'default'}
        active={isActive}
        locked={isLocked && !isActive}
        className={`w-full p-[18px] flex flex-col gap-2.5 ${isActive ? ACTIVE_GLOW_CLASS : ''}`}
      >
        {/* Name + lock */}
        <div className="flex items-start justify-between gap-2.5">
          <h4 className={`text-base font-medium leading-tight break-words min-w-0 ${rarityColor}`}>
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
              const isMet = prog ? prog.current >= prog.required : false;

              return (
                <ProgressBar
                  key={idx}
                  size="sm"
                  value={prog ? prog.current : 0}
                  max={prog ? prog.required : 0}
                  variant={isMet ? 'energy' : barVariant}
                  showValues={Boolean(prog)}
                  label={
                    <span className={`text-[10px] ${isMet ? 'text-stat-energy' : 'text-white/50'}`}>
                      {getConditionLabel(cond)}
                    </span>
                  }
                />
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
              isActive ? 'text-gold' : isLocked ? 'text-white/40' : 'text-stat-energy'
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
                onClick={onUnsetActive}
                disabled={actionLoading === -1}
                className="w-full min-h-[36px] text-[11px] font-medium py-1.5 rounded-full border border-white/20 text-white/60 hover:text-white hover:border-white/40 transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading === -1 ? '...' : 'Снять'}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onSetActive(title.id_title)}
                disabled={actionLoading === title.id_title}
                className="w-full min-h-[36px] text-[11px] font-medium py-1.5 rounded-full border border-gold/30 bg-gold/10 text-gold hover:bg-gold/20 transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading === title.id_title ? '...' : 'Выбрать'}
              </button>
            )}
          </div>
        )}
      </ProfileCard>
    </motion.div>
  );
};

export default TitleCard;
