import { motion, AnimatePresence } from 'motion/react';
import { X } from 'react-feather';
import type { CharacterPerk } from '../../../types/perks';

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
  rare: 'text-purple-300 bg-purple-400/15',
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

const CONDITION_LABELS: Record<string, string> = {
  pve_kills: 'Мобов убито',
  pvp_wins: 'PvP побед',
  pvp_losses: 'PvP поражений',
  total_battles: 'Всего боёв',
  total_damage_dealt: 'Урона нанесено',
  total_damage_received: 'Урона получено',
  max_damage_single_battle: 'Макс. урон за бой',
  max_win_streak: 'Макс. серия побед',
  total_rounds_survived: 'Раундов пережито',
  low_hp_wins: 'Побед с низким HP',
  total_gold_earned: 'Золота заработано',
  total_gold_spent: 'Золота потрачено',
  items_bought: 'Предметов куплено',
  items_sold: 'Предметов продано',
  locations_visited: 'Локаций посещено',
  total_transitions: 'Переходов совершено',
  skills_used: 'Навыков использовано',
  items_equipped: 'Предметов экипировано',
  strength: 'Сила',
  agility: 'Ловкость',
  intelligence: 'Интеллект',
  endurance: 'Выносливость',
  charisma: 'Харизма',
  luck: 'Удача',
};

const formatBonusValue = (key: string, value: number): string => {
  const label = BONUS_KEY_LABELS[key] ?? key;
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value} к ${label}`;
};

const PerkDetailModal = ({ perk, onClose }: PerkDetailModalProps) => {
  if (!perk) return null;

  const isLegendaryLocked = perk.rarity === 'legendary' && !perk.is_unlocked;
  const isRareLocked = perk.rarity === 'rare' && !perk.is_unlocked;

  const rarityBadge = RARITY_BADGE_STYLES[perk.rarity] ?? RARITY_BADGE_STYLES.common;
  const rarityLabel = RARITY_LABELS[perk.rarity] ?? perk.rarity;
  const categoryLabel = CATEGORY_LABELS[perk.category] ?? perk.category;

  const flatBonuses = Object.entries(perk.bonuses?.flat ?? {}).filter(([, v]) => v !== 0);
  const percentBonuses = Object.entries(perk.bonuses?.percent ?? {}).filter(([, v]) => v !== 0);

  return (
    <AnimatePresence>
      <div className="modal-overlay" onClick={onClose}>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="modal-content gold-outline max-w-md w-full mx-4"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              {perk.icon ? (
                <img
                  src={perk.icon}
                  alt={isLegendaryLocked ? '???' : perk.name}
                  className="w-14 h-14 rounded-full object-cover border border-white/10"
                />
              ) : (
                <div className={`
                  w-14 h-14 rounded-full flex items-center justify-center border
                  ${perk.rarity === 'legendary'
                    ? 'border-gold/30 bg-gold/5'
                    : perk.rarity === 'rare'
                      ? 'border-purple-400/30 bg-purple-400/5'
                      : 'border-white/10 bg-white/5'
                  }
                `}>
                  <span className="text-white/30 text-xl">
                    {isLegendaryLocked ? '?' : '★'}
                  </span>
                </div>
              )}
              <div>
                <h2 className="gold-text text-xl font-medium">
                  {isLegendaryLocked ? '???' : perk.name}
                </h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${rarityBadge}`}>
                    {rarityLabel}
                  </span>
                  <span className="text-white/40 text-xs">{categoryLabel}</span>
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-white/40 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Description */}
          {!isLegendaryLocked && !isRareLocked && perk.description && (
            <p className="text-white/70 text-sm mb-4 leading-relaxed">
              {perk.description}
            </p>
          )}

          {/* Legendary locked placeholder */}
          {isLegendaryLocked && (
            <div className="text-center py-6">
              <p className="text-gold/50 text-sm italic">
                Легендарный перк. Его свойства скрыты до разблокировки.
              </p>
            </div>
          )}

          {/* Conditions */}
          {!isLegendaryLocked && perk.conditions.length > 0 && (
            <div className="mb-4">
              <h4 className="text-white/50 text-xs font-medium uppercase tracking-wider mb-2">
                Условия
              </h4>
              <div className="space-y-2">
                {perk.conditions.map((condition, idx) => {
                  const statKey = condition.stat ?? condition.type;
                  const progressEntry = perk.progress?.[statKey];
                  const current = progressEntry?.current ?? 0;
                  const required = progressEntry?.required ?? condition.value;
                  const progressPct = required > 0
                    ? Math.min(100, Math.round((current / required) * 100))
                    : 0;
                  const isMet = current >= required;

                  return (
                    <div key={idx} className="bg-white/5 rounded-card px-3 py-2">
                      {/* For rare locked: show progress bar but no text */}
                      {isRareLocked ? (
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-white/30 text-xs italic">Скрытое условие</span>
                            <span className="text-white/40 text-xs">{progressPct}%</span>
                          </div>
                          <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                isMet ? 'bg-emerald-400' : 'bg-purple-400/60'
                              }`}
                              style={{ width: `${progressPct}%` }}
                            />
                          </div>
                        </div>
                      ) : (
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-white/70 text-sm">
                              {CONDITION_LABELS[statKey] ?? statKey}{' '}
                              <span className="text-white/40">{condition.operator} {condition.value}</span>
                            </span>
                            <span className={`text-xs font-medium ${isMet ? 'text-emerald-400' : 'text-white/40'}`}>
                              {current} / {required}
                            </span>
                          </div>
                          <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                isMet ? 'bg-emerald-400' : 'bg-site-blue/60'
                              }`}
                              style={{ width: `${progressPct}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Bonuses */}
          {!isLegendaryLocked && !isRareLocked && (flatBonuses.length > 0 || percentBonuses.length > 0) && (
            <div className="mb-4">
              <h4 className="text-white/50 text-xs font-medium uppercase tracking-wider mb-2">
                Бонусы
              </h4>
              <div className="space-y-1.5">
                {flatBonuses.map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-center text-sm bg-white/5 rounded px-3 py-1.5"
                  >
                    <span className="text-emerald-300">{formatBonusValue(key, value)}</span>
                  </div>
                ))}
                {percentBonuses.map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-center text-sm bg-white/5 rounded px-3 py-1.5"
                  >
                    <span className="text-site-blue">
                      {value >= 0 ? '+' : ''}{value}% к {BONUS_KEY_LABELS[key] ?? key}
                    </span>
                    <span className="text-white/30 text-xs ml-2">(Фаза 2)</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Unlock status */}
          <div className="border-t border-white/5 pt-3 mt-3">
            {perk.is_unlocked ? (
              <div className="flex items-center gap-2">
                <span className="text-emerald-400 text-sm font-medium">Разблокирован</span>
                {perk.unlocked_at && (
                  <span className="text-white/30 text-xs">
                    {new Date(perk.unlocked_at).toLocaleDateString('ru-RU')}
                  </span>
                )}
                {perk.is_custom && (
                  <span className="text-gold/60 text-xs ml-auto">Выдан администратором</span>
                )}
              </div>
            ) : (
              <span className="text-white/30 text-sm">Заблокирован</span>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default PerkDetailModal;
