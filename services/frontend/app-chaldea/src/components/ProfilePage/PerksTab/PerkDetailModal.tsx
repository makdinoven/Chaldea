// Perk detail dialog. FEAT-166: ModalShell (portaled), shared progress bar,
// design-system tokens.
import { useRef } from 'react';
import { Star } from 'lucide-react';
import type { CharacterPerk } from '../../../types/perks';
import { formatServerDate } from '../../../utils/serverDate';
import ModalShell from '../shared/ModalShell';
import ProfileCard from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';
import ProgressBar from '../shared/ProgressBar';
import SectionHeader from '../shared/SectionHeader';

interface PerkDetailModalProps {
  perk: CharacterPerk | null;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  combat: 'Боевой',
  trade: 'Торговый',
  exploration: 'Исследование',
  progression: 'Прогрессия',
  usage: 'Использование',
};

const RARITY_LABELS: Record<string, string> = {
  common: 'Обычный',
  rare: 'Редкий',
  legendary: 'Легендарный',
};

const RARITY_BADGE_STYLES: Record<string, string> = {
  common: 'text-white/70 bg-white/10',
  rare: 'text-rarity-epic bg-rarity-epic/15',
  legendary: 'text-gold bg-gold/15',
};

const BONUS_KEY_LABELS: Record<string, string> = {
  health: 'здоровью',
  max_health: 'макс. здоровью',
  mana: 'мане',
  max_mana: 'макс. мане',
  energy: 'энергии',
  max_energy: 'макс. энергии',
  stamina: 'выносливости',
  max_stamina: 'макс. выносливости',
  strength: 'силе',
  agility: 'ловкости',
  intelligence: 'интеллекту',
  endurance: 'выносливости',
  charisma: 'харизме',
  luck: 'удаче',
  damage: 'урону',
  armor: 'броне',
  dodge: 'уклонению',
  critical_hit_chance: 'шансу крита',
  critical_hit_multiplier: 'множителю крита',
  hit_chance: 'точности',
  res_physical: 'сопр. физическому',
  res_fire: 'сопр. огню',
  res_ice: 'сопр. льду',
  res_electricity: 'сопр. электричеству',
  res_wind: 'сопр. ветру',
  res_holy: 'сопр. святости',
  res_dark: 'сопр. тьме',
  res_water: 'сопр. воде',
  res_cutting: 'сопр. режущему',
  res_crushing: 'сопр. дробящему',
  res_piercing: 'сопр. колющему',
  res_magic: 'сопр. магии',
};

const CONDITION_DESCRIPTIONS: Record<string, (value: number) => string> = {
  // Кумулятивная статистика — боевая
  pve_kills: (v) => `Убить ${v} мобов`,
  pvp_wins: (v) => `Выиграть ${v} PvP-боёв`,
  pvp_losses: (v) => `Проиграть ${v} PvP-боёв`,
  total_battles: (v) => `Провести ${v} боёв`,
  total_damage_dealt: (v) => `Нанести ${v} урона`,
  total_damage_received: (v) => `Получить ${v} урона`,
  max_damage_single_battle: (v) => `Нанести ${v} урона за один бой`,
  max_win_streak: (v) => `Выиграть ${v} боёв подряд`,
  current_win_streak: (v) => `Текущая серия побед: ${v}`,
  total_rounds_survived: (v) => `Пережить ${v} раундов`,
  // Кумулятивная статистика — экономика
  total_gold_earned: (v) => `Заработать ${v} золота`,
  total_gold_spent: (v) => `Потратить ${v} золота`,
  items_bought: (v) => `Купить ${v} предметов`,
  items_sold: (v) => `Продать ${v} предметов`,
  // Кумулятивная статистика — исследование
  locations_visited: (v) => `Посетить ${v} локаций`,
  total_transitions: (v) => `Совершить ${v} переходов`,
  // Кумулятивная статистика — навыки
  skills_used: (v) => `Прокачать ${v} навыков`,
  items_equipped: (v) => `Экипировать ${v} предметов`,
  // Кумулятивная статистика — социальные / квесты
  total_posts: (v) => `Написать ${v} постов`,
  quests_completed: (v) => `Завершить ${v} квестов`,
  // Основные характеристики
  strength: (v) => `Сила ${v}+`,
  agility: (v) => `Ловкость ${v}+`,
  intelligence: (v) => `Интеллект ${v}+`,
  endurance: (v) => `Выносливость ${v}+`,
  charisma: (v) => `Харизма ${v}+`,
  luck: (v) => `Удача ${v}+`,
  // Ресурсы
  health: (v) => `Здоровье ${v}+`,
  mana: (v) => `Мана ${v}+`,
  energy: (v) => `Энергия ${v}+`,
  stamina: (v) => `Выносливость ${v}+`,
  // Боевые характеристики
  damage: (v) => `Урон ${v}+`,
  dodge: (v) => `Уклонение ${v}%+`,
  critical_hit_chance: (v) => `Шанс крита ${v}%+`,
  critical_damage: (v) => `Крит. урон ${v}+`,
  // Сопротивления
  res_effects: (v) => `Сопр. эффектам ${v}%+`,
  res_physical: (v) => `Сопр. физическому ${v}%+`,
  res_catting: (v) => `Сопр. режущему ${v}%+`,
  res_crushing: (v) => `Сопр. дробящему ${v}%+`,
  res_piercing: (v) => `Сопр. колющему ${v}%+`,
  res_magic: (v) => `Сопр. магии ${v}%+`,
  res_fire: (v) => `Сопр. огню ${v}%+`,
  res_ice: (v) => `Сопр. льду ${v}%+`,
  res_watering: (v) => `Сопр. воде ${v}%+`,
  res_electricity: (v) => `Сопр. электричеству ${v}%+`,
  res_sainting: (v) => `Сопр. святому ${v}%+`,
  res_wind: (v) => `Сопр. ветру ${v}%+`,
  res_damning: (v) => `Сопр. тьме ${v}%+`,
  // Уровень персонажа
  character_level: (v) => `Достичь ${v} уровня`,
  // Специальные типы
  admin_grant: () => 'Выдаётся администратором',
  // Новые типы условий
  perk_count: (v) => `Открыть ${v} перков`,
  gold_balance: (v) => `Иметь ${v} золота`,
  has_perk: () => 'Открыть определённый перк',
};

/**
 * Format a human-readable condition description from condition data.
 * Handles both simple stat-key lookups and complex condition types
 * (quest with sub-types, has_perk, skill_level, etc.).
 */
const formatConditionText = (
  statKey: string,
  value: number,
  condition?: { type?: string; stat?: string; label?: string },
): string => {
  const condType = condition?.type;
  const condStat = condition?.stat;

  // Quest conditions — route by stat sub-type
  if (condType === 'quest') {
    if (condStat === 'completed_count') return `Завершить ${value} квестов`;
    if (condStat === 'quest_id') {
      const label = condition?.label;
      return label ? `Завершить квест «${label}»` : 'Завершить определённый квест';
    }
    return `Квестовое условие`;
  }

  // has_perk — value is the perk ID
  if (condType === 'has_perk') {
    const label = condition?.label;
    return label ? `Открыть перк «${label}»` : 'Открыть определённый перк';
  }

  // gold_balance
  if (condType === 'gold_balance') return `Иметь ${value} золота`;

  // perk_count
  if (condType === 'perk_count') return `Открыть ${value} перков`;

  // Standard lookup by stat key
  const formatter = CONDITION_DESCRIPTIONS[statKey];
  return formatter ? formatter(value) : `${statKey} ≥ ${value}`;
};

const formatBonusValue = (key: string, value: number): string => {
  const label = BONUS_KEY_LABELS[key] ?? key;
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value} к ${label}`;
};

const PerkDetailModal = ({ perk, onClose }: PerkDetailModalProps) => {
  // Keep the last perk so the content stays in place during the exit animation.
  const lastPerkRef = useRef<CharacterPerk | null>(perk);
  if (perk) lastPerkRef.current = perk;
  const shown = perk ?? lastPerkRef.current;

  if (!shown) return null;

  const isLegendaryLocked = shown.rarity === 'legendary' && !shown.is_unlocked;
  const isRareLocked = shown.rarity === 'rare' && !shown.is_unlocked;

  const rarityBadge = RARITY_BADGE_STYLES[shown.rarity] ?? RARITY_BADGE_STYLES.common;
  const rarityLabel = RARITY_LABELS[shown.rarity] ?? shown.rarity;
  const categoryLabel = CATEGORY_LABELS[shown.category] ?? shown.category;

  const flatBonuses = Object.entries(shown.bonuses?.flat ?? {}).filter(([, v]) => v !== 0);
  const percentBonuses = Object.entries(shown.bonuses?.percent ?? {}).filter(([, v]) => v !== 0);

  return (
    <ModalShell
      open={perk !== null}
      onClose={onClose}
      title={isLegendaryLocked ? '???' : shown.name}
      icon={<Star size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      size="md"
      bodyClassName="flex flex-col gap-5"
    >
      {/* Identity row */}
      <div className="flex items-center gap-3">
        <GoldIconFrame
          size={56}
          shape="circle"
          glow={shown.is_unlocked}
          src={shown.icon}
          alt={isLegendaryLocked ? '???' : shown.name}
          fallback={
            <span className="text-white/30 text-xl">{isLegendaryLocked ? '?' : '★'}</span>
          }
        />
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span className={`text-[10px] font-medium uppercase tracking-[0.06em] px-2 py-0.5 rounded ${rarityBadge}`}>
            {rarityLabel}
          </span>
          <span className="text-white/40 text-xs">{categoryLabel}</span>
        </div>
      </div>

      {/* Description */}
      {!isLegendaryLocked && !isRareLocked && shown.description && (
        <p className="text-white/70 text-sm leading-relaxed">{shown.description}</p>
      )}

      {/* Legendary locked placeholder */}
      {isLegendaryLocked && (
        <div className="text-center py-4">
          <p className="text-gold/50 text-sm italic">
            Легендарный перк. Его свойства скрыты до разблокировки.
          </p>
        </div>
      )}

      {/* Conditions */}
      {!isLegendaryLocked && shown.conditions.length > 0 && (
        <div className="flex flex-col gap-2.5">
          <SectionHeader title="Условия" />
          <div className="flex flex-col gap-2">
            {shown.conditions.map((condition, idx) => {
              const statKey = condition.stat ?? condition.type;
              const progressEntry = shown.progress?.[statKey];
              const current = progressEntry?.current ?? 0;
              const required = progressEntry?.required ?? condition.value;
              const progressPct = required > 0
                ? Math.min(100, Math.round((current / required) * 100))
                : 0;
              const isMet = current >= required;

              return (
                <ProfileCard key={idx} className="px-3 py-2.5 flex flex-col gap-1.5">
                  {/* For rare locked: show progress bar but no text */}
                  {isRareLocked ? (
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-white/30 text-xs italic">Скрытое условие</span>
                      <span className="text-white/40 text-xs font-mono tabular-nums">{progressPct}%</span>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-white/70 text-sm min-w-0">
                        {formatConditionText(statKey, condition.value, {
                          ...condition,
                          label: (progressEntry as Record<string, unknown>)?.label as string | undefined,
                        })}
                      </span>
                      <span className={`text-xs font-medium font-mono tabular-nums shrink-0 ${isMet ? 'text-stat-energy' : 'text-white/40'}`}>
                        {current} / {required}
                      </span>
                    </div>
                  )}
                  <ProgressBar
                    value={current}
                    max={required}
                    size="sm"
                    variant={isMet ? 'energy' : isRareLocked ? 'epic' : 'mana'}
                  />
                </ProfileCard>
              );
            })}
          </div>
        </div>
      )}

      {/* Bonuses */}
      {!isLegendaryLocked && !isRareLocked && (flatBonuses.length > 0 || percentBonuses.length > 0) && (
        <div className="flex flex-col gap-2.5">
          <SectionHeader title="Бонусы" />
          <div className="flex flex-col gap-1.5">
            {flatBonuses.map(([key, value]) => (
              <ProfileCard key={key} className="flex items-center text-sm px-3 py-1.5">
                <span className="text-stat-energy">{formatBonusValue(key, value)}</span>
              </ProfileCard>
            ))}
            {percentBonuses.map(([key, value]) => (
              <ProfileCard key={key} className="flex items-center text-sm px-3 py-1.5">
                <span className="text-site-blue">
                  {value >= 0 ? '+' : ''}{value}% к {BONUS_KEY_LABELS[key] ?? key}
                </span>
                <span className="text-white/30 text-xs ml-2">(Фаза 2)</span>
              </ProfileCard>
            ))}
          </div>
        </div>
      )}

      {/* Unlock status */}
      <div className="border-t border-white/10 pt-3">
        {shown.is_unlocked ? (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-stat-energy text-sm font-medium">Разблокирован</span>
            {shown.unlocked_at && (
              <span className="text-white/30 text-xs">
                {formatServerDate(shown.unlocked_at, {})}
              </span>
            )}
            {shown.is_custom && (
              <span className="text-gold/60 text-xs ml-auto">Выдан администратором</span>
            )}
          </div>
        ) : (
          <span className="text-white/30 text-sm">Заблокирован</span>
        )}
      </div>
    </ModalShell>
  );
};

export default PerkDetailModal;
