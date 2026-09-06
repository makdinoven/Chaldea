/**
 * FEAT-154 — derived values printed next to the stat preset (rule 6).
 *
 * These constants and formulas MIRROR the backend, which is the single source
 * of truth: `services/character-attributes-service/app/constants.py` and
 * `crud.py::compute_derived_stats`. Initiative mirrors the battle engine
 * (FEAT-143), as already displayed by `ProfilePage/StatsTab/DerivedStatsSection`.
 *
 * Kept in this folder so the wizard's `StatExplainer` (task #17) can reuse the
 * exact same numbers the passport prints — the two must never disagree.
 */

import type { DerivedStats, PassportStats } from './types';

// Mirrors character-attributes-service/app/constants.py
const BASE_HEALTH = 100;
const BASE_MANA = 75;
const BASE_ENERGY = 50;
const BASE_STAMINA = 100;
const BASE_DODGE = 5.0;
const BASE_CRIT = 20.0;
const BASE_CRIT_DMG = 125;

const HEALTH_MULTIPLIER = 10;
const MANA_MULTIPLIER = 10;
const ENERGY_MULTIPLIER = 5;
const STAMINA_MULTIPLIER = 5;

const STAT_BONUS_PER_POINT = 0.1;

// Initiative weights (FEAT-143): agility ×1.0 + (strength + intelligence) ×0.75.
const INITIATIVE_AGILITY_WEIGHT = 1.0;
const INITIATIVE_MIND_BODY_WEIGHT = 0.75;

/** Total points every subrace preset is worth (rule 5). */
export const PRESET_TOTAL_POINTS = 100;

/** Points a character gains per level (rule 5). */
export const POINTS_PER_LEVEL = 10;

const num = (stats: PassportStats | null | undefined, key: string): number => {
  const value = stats?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
};

const round2 = (value: number): number => Math.round(value * 100) / 100;

/**
 * Computes the values a player actually feels: resource pools, dodge, crit and
 * initiative. Missing stats count as 0, so a partial preset still renders.
 */
export const computeDerivedStats = (stats: PassportStats | null | undefined): DerivedStats => {
  const agility = num(stats, 'agility');
  const luck = num(stats, 'luck');
  const strength = num(stats, 'strength');
  const intelligence = num(stats, 'intelligence');

  return {
    maxHealth: Math.trunc(BASE_HEALTH + num(stats, 'health') * HEALTH_MULTIPLIER),
    maxMana: Math.trunc(BASE_MANA + num(stats, 'mana') * MANA_MULTIPLIER),
    maxEnergy: Math.trunc(BASE_ENERGY + num(stats, 'energy') * ENERGY_MULTIPLIER),
    maxStamina: Math.trunc(BASE_STAMINA + num(stats, 'stamina') * STAMINA_MULTIPLIER),
    dodge: round2(BASE_DODGE + agility * STAT_BONUS_PER_POINT + luck * STAT_BONUS_PER_POINT),
    criticalHitChance: round2(BASE_CRIT + luck * STAT_BONUS_PER_POINT),
    criticalDamage: BASE_CRIT_DMG,
    initiative: round2(
      agility * INITIATIVE_AGILITY_WEIGHT +
        (strength + intelligence) * INITIATIVE_MIND_BODY_WEIGHT,
    ),
  };
};

/**
 * Russian labels for the preset stats. Duplicated from
 * `ProfilePage/constants.ts` on purpose: that module imports a dozen SVG
 * assets, and the passport must not drag them into every bundle that shows a
 * character card.
 */
export const PASSPORT_STAT_LABELS: Record<string, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intelligence: 'Интеллект',
  endurance: 'Живучесть',
  health: 'Здоровье',
  mana: 'Мана',
  energy: 'Энергия',
  stamina: 'Выносливость',
  charisma: 'Харизма',
  luck: 'Удача',
};

/** Derived rows in display order: label + how to read the value. */
export const PASSPORT_DERIVED_ROWS: {
  key: keyof DerivedStats;
  label: string;
  isPercent: boolean;
}[] = [
  { key: 'maxHealth', label: 'Здоровье', isPercent: false },
  { key: 'maxMana', label: 'Мана', isPercent: false },
  { key: 'maxEnergy', label: 'Энергия', isPercent: false },
  { key: 'maxStamina', label: 'Выносливость', isPercent: false },
  { key: 'dodge', label: 'Уклонение', isPercent: true },
  { key: 'criticalHitChance', label: 'Шанс крита', isPercent: true },
  { key: 'criticalDamage', label: 'Урон крита', isPercent: true },
  { key: 'initiative', label: 'Инициатива', isPercent: false },
];

/** Formats a derived value: integers plain, fractions to one decimal. */
export const formatDerivedValue = (value: number, isPercent: boolean): string => {
  const text = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return isPercent ? `${text}%` : text;
};
