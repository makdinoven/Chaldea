// Russian label maps for skill stat display.
// Used by PerkCard / SkillUpgradeModal / the books to render damage_type /
// effect_name / target_side in human-readable Russian instead of raw API codes.
// Effect names themselves come from battleEffects' describeEffect, the one
// place every surface — battle, items, skills — names an effect.

import { describeEffect, FLAT_STAT_KEYS } from '../pages/BattlePage/battleEffects';

// Canonical values: see AdminSkillsPage/skillConstants.ts DAMAGE_TYPES
const DAMAGE_TYPE_RU: Record<string, string> = {
  all: 'Все типы',
  physical: 'Физический',
  catting: 'Режущий',
  crushing: 'Дробящий',
  piercing: 'Колющий',
  magic: 'Магия',
  fire: 'Огонь',
  ice: 'Лёд',
  watering: 'Вода',
  electricity: 'Электричество',
  wind: 'Ветер',
  sainting: 'Святой',
  damning: 'Тёмный',
  // legacy aliases (kept for tolerance with old data)
  slashing: 'Режущий',
  blunt: 'Дробящий',
  cold: 'Лёд',
  frost: 'Лёд',
  lightning: 'Электричество',
  electric: 'Электричество',
  shock: 'Электричество',
  holy: 'Святой',
  light: 'Святой',
  dark: 'Тёмный',
  shadow: 'Тёмный',
  poison: 'Яд',
  acid: 'Кислота',
  arcane: 'Магия',
  nature: 'Природа',
  earth: 'Земля',
  water: 'Вода',
  air: 'Ветер',
  necrotic: 'Некротика',
  psychic: 'Разум',
  true: 'Чистый',
};

// Mobile-friendly target labels for the resolved card.
const TARGET_SIDE_CARD_RU: Record<string, string> = {
  self: 'На себя',
  enemy: 'На врага',
  enemies: 'На всех врагов',
  ally: 'На союзника',
  allies: 'На всех союзников',
  all_allies: 'На всю команду',
  all_enemies: 'На всех врагов',
  all: 'На всех',
};

// Skill type (canonical attack/defense/support).
const SKILL_TYPE_RU: Record<string, string> = {
  attack: 'Атакующий',
  defense: 'Защитный',
  support: 'Поддержки',
};


const TARGET_SIDE_RU: Record<string, string> = {
  self: 'себя',
  enemy: 'враг',
  enemies: 'все враги',
  ally: 'союзник',
  allies: 'все союзники',
  all: 'все цели',
  any: 'любая цель',
  none: '—',
};



const lookup = (map: Record<string, string>, key: string | null | undefined): string | null => {
  if (!key) return null;
  return map[key.toLowerCase().trim()] ?? null;
};

export const ruDamageType = (key: string | null | undefined): string => {
  if (!key) return '';
  return lookup(DAMAGE_TYPE_RU, key) ?? key;
};

export const ruTargetSide = (key: string | null | undefined): string => {
  if (!key) return '';
  return lookup(TARGET_SIDE_RU, key) ?? key;
};

/** An effect_name (+ attribute_key) in Russian, as the battle names it. */
export const ruEffectName = (
  name: string | null | undefined,
  attributeKey?: string | null
): string => {
  if (!name) return '';
  return describeEffect({ name: name.trim(), attribute: attributeKey ?? undefined }).label;
};

// --- New exports for the player skill info card (FEAT-125) ---

export const ruTargetSideCard = (key: string | null | undefined): string => {
  if (!key) return '';
  return TARGET_SIDE_CARD_RU[key.toLowerCase().trim()] ?? key;
};

export const ruSkillType = (key: string | null | undefined): string => {
  if (!key) return '';
  return SKILL_TYPE_RU[key.toLowerCase().trim()] ?? key;
};

export type EffectCategory = 'buff' | 'resist' | 'stat' | 'complex';

export interface ParsedEffect {
  category: EffectCategory;
  friendlyName: string;
  /** If true, magnitude is rendered as percent; otherwise flat number. */
  isPercent: boolean;
}

/**
 * Parse an effect_name (+ optional attribute_key) into a display-friendly
 * shape. See CLAUDE.md FEAT-125 — the admin payload builder emits:
 *   "Buff: fire" / "Debuff: fire" (legacy) / "Resist: cold" /
 *   "Vulnerability: holy" (legacy) / "StatModifier" / raw complex effect keys.
 */
export const parseEffectName = (
  effectName: string | null | undefined,
  attributeKey?: string | null
): ParsedEffect => {
  const name = (effectName ?? '').trim();
  const key = (attributeKey ?? '').trim();
  const friendlyName = describeEffect({ name, attribute: key || undefined }).label || 'Эффект';
  const prefix = name.includes(':') ? name.slice(0, name.indexOf(':')).trim().toLowerCase() : '';

  if (prefix === 'buff' || prefix === 'debuff') return { category: 'buff', friendlyName, isPercent: true };
  if (prefix === 'resist' || prefix === 'vulnerability') return { category: 'resist', friendlyName, isPercent: true };
  if (name === 'StatModifier') return { category: 'stat', friendlyName, isPercent: !FLAT_STAT_KEYS.has(key) };
  return { category: 'complex', friendlyName, isPercent: false };
};

/** Russian turn-count pluralization: 1 ход / 2–4 хода / 5+ ходов. */
export const pluralizeTurns = (n: number): string => {
  const abs = Math.abs(n);
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} ход`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} хода`;
  return `${n} ходов`;
};
