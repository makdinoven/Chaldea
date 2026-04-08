// Russian label maps for skill stat display.
// Used by PerkCard / SkillUpgradeModal to render damage_type / effect_name / target_side
// in human-readable Russian instead of raw API codes.

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
  all: 'На всех',
};

// Skill type (canonical attack/defense/support).
const SKILL_TYPE_RU: Record<string, string> = {
  attack: 'Атакующий',
  defense: 'Защитный',
  support: 'Поддержки',
};

// StatModifier attribute_key → Russian label (see skillConstants STAT_MODIFIERS).
const STAT_LABELS: Record<string, string> = {
  critical_hit_chance: 'Шанс крита',
  crit_damage: 'Урон крита',
  dodge_chance: 'Уклонение',
  hp: 'Здоровье',
  mana: 'Мана',
  energy: 'Энергия',
};

// Complex effect key → Russian label (see skillConstants COMPLEX_EFFECTS).
const COMPLEX_EFFECT_LABELS: Record<string, string> = {
  Bleeding: 'Кровотечение',
  Burn: 'Возгорание',
  Poison: 'Отравление',
  Stun: 'Оглушение',
  Freeze: 'Обледенение',
  Knockdown: 'Сбитие с ног',
  Daze: 'Ошеломление',
  MagicImpact: 'Магическое воздействие',
  Wet: 'Мокрый',
  Electrify: 'Электролизация',
  Windburn: 'Обветрение',
  Holy: 'Святость',
  Curse: 'Проклятие',
  ArmorBreak: 'Раскол брони',
};

// Stats that are FLAT (not percent) when rendered.
const FLAT_STAT_KEYS = new Set(['hp', 'mana', 'energy']);

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

const ATTRIBUTE_KEY_RU: Record<string, string> = {
  hp: 'здоровье',
  health: 'здоровье',
  mp: 'мана',
  mana: 'мана',
  energy: 'энергия',
  stamina: 'выносливость',
  strength: 'сила',
  agility: 'ловкость',
  dexterity: 'ловкость',
  intelligence: 'интеллект',
  wisdom: 'мудрость',
  endurance: 'стойкость',
  constitution: 'телосложение',
  charisma: 'харизма',
  luck: 'удача',
  defense: 'защита',
  armor: 'броня',
  attack: 'атака',
  speed: 'скорость',
  crit: 'крит',
  critical: 'крит',
};

const EFFECT_NAME_RU: Record<string, string> = {
  bleeding: 'кровотечение',
  bleed: 'кровотечение',
  poison: 'отравление',
  poisoned: 'отравление',
  burn: 'горение',
  burning: 'горение',
  freeze: 'заморозка',
  frozen: 'заморозка',
  chill: 'охлаждение',
  shock: 'оглушение разрядом',
  stun: 'оглушение',
  stunned: 'оглушение',
  sleep: 'сон',
  silence: 'немота',
  blind: 'ослепление',
  fear: 'страх',
  charm: 'очарование',
  root: 'корни',
  slow: 'замедление',
  haste: 'ускорение',
  regen: 'регенерация',
  regeneration: 'регенерация',
  heal: 'лечение',
  shield: 'щит',
  barrier: 'барьер',
  buff: 'усиление',
  debuff: 'ослабление',
  dot: 'периодический урон',
  hot: 'периодическое лечение',
  statmodifier: 'модификатор характеристики',
  magicimpact: 'магический удар',
  taunt: 'провокация',
  invisible: 'невидимость',
  stealth: 'скрытность',
  reflect: 'отражение',
  lifesteal: 'вампиризм',
  vulnerability: 'уязвимость',
  resist: 'сопротивление',
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

export const ruAttributeKey = (key: string | null | undefined): string => {
  if (!key) return '';
  return lookup(ATTRIBUTE_KEY_RU, key) ?? key;
};

/**
 * Translates an effect_name to Russian. Handles prefixed forms used by
 * the admin payload builder (`Buff: fire`, `Resist: cold`, `Vulnerability: holy`)
 * by translating the prefix and the damage-type suffix independently.
 */
export const ruEffectName = (
  name: string | null | undefined,
  attributeKey?: string | null
): string => {
  if (!name) return '';
  const trimmed = name.trim();

  // Prefixed forms: "Buff: fire", "Resist: cold", "Vulnerability: holy"
  const colonIdx = trimmed.indexOf(':');
  if (colonIdx > 0) {
    const prefix = trimmed.slice(0, colonIdx).trim().toLowerCase();
    const suffix = trimmed.slice(colonIdx + 1).trim();
    const prefixRu = EFFECT_NAME_RU[prefix];
    if (prefixRu) {
      const suffixRu = ruDamageType(suffix);
      return `${prefixRu}: ${suffixRu}`;
    }
  }

  // StatModifier with attribute_key
  if (trimmed.toLowerCase() === 'statmodifier' && attributeKey) {
    return `${EFFECT_NAME_RU.statmodifier}: ${ruAttributeKey(attributeKey)}`;
  }

  return lookup(EFFECT_NAME_RU, trimmed) ?? trimmed;
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

  const colonIdx = name.indexOf(':');
  if (colonIdx > 0) {
    const prefix = name.slice(0, colonIdx).trim().toLowerCase();
    const suffix = name.slice(colonIdx + 1).trim();
    const dmgRu = ruDamageType(suffix);

    if (prefix === 'buff' || prefix === 'debuff') {
      return { category: 'buff', friendlyName: `Бафф ${dmgRu.toLowerCase()}`, isPercent: true };
    }
    if (prefix === 'resist' || prefix === 'vulnerability') {
      const label = prefix === 'vulnerability' ? 'Уязвимость' : 'Резист';
      return { category: 'resist', friendlyName: `${label} ${dmgRu.toLowerCase()}`, isPercent: true };
    }
  }

  if (name === 'StatModifier') {
    const key = (attributeKey ?? '').trim();
    const friendly = STAT_LABELS[key] ?? key ?? 'Характеристика';
    return {
      category: 'stat',
      friendlyName: friendly,
      isPercent: !FLAT_STAT_KEYS.has(key),
    };
  }

  const complex = COMPLEX_EFFECT_LABELS[name];
  return {
    category: 'complex',
    friendlyName: complex ?? name ?? 'Эффект',
    isPercent: false,
  };
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
