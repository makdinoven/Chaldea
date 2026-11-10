/* FEAT-210: tabs of the expanded mob-template panel. */

export type MobTabKey = 'general' | 'stats' | 'skills' | 'loot' | 'spawns';

export const MOB_TAB_KEYS: readonly MobTabKey[] = ['general', 'stats', 'skills', 'loot', 'spawns'];

export const MOB_TAB_LABELS: Record<MobTabKey, string> = {
  general: 'Основное',
  stats: 'Характеристики',
  skills: 'Навыки',
  loot: 'Лут',
  spawns: 'Спавны',
};

export const isMobTabKey = (value: string | null): value is MobTabKey =>
  value !== null && (MOB_TAB_KEYS as readonly string[]).includes(value);

/** A new (unsaved) template has only «Основное»; a saved one has every tab. */
export const availableMobTabs = (isNew: boolean): MobTabKey[] => (isNew ? ['general'] : [...MOB_TAB_KEYS]);

export const TIER_LABELS: Record<string, string> = {
  normal: 'Обычный',
  elite: 'Элитный',
  boss: 'Босс',
};

export const TIER_COLORS: Record<string, string> = {
  normal: 'bg-white/20 text-white',
  elite: 'bg-purple-500/30 text-purple-300',
  boss: 'bg-site-red/30 text-site-red',
};
