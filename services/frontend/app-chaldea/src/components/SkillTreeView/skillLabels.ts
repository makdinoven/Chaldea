// Russian label maps for skill stat display.
// Used by PerkCard / SkillUpgradeModal to render damage_type / effect_name / target_side
// in human-readable Russian instead of raw API codes.

const DAMAGE_TYPE_RU: Record<string, string> = {
  all: 'все типы',
  physical: 'физический',
  slashing: 'рубящий',
  piercing: 'колющий',
  blunt: 'дробящий',
  crushing: 'дробящий',
  fire: 'огонь',
  cold: 'холод',
  ice: 'лёд',
  frost: 'мороз',
  lightning: 'молния',
  electric: 'электричество',
  shock: 'разряд',
  holy: 'свет',
  light: 'свет',
  dark: 'тьма',
  shadow: 'тень',
  poison: 'яд',
  acid: 'кислота',
  arcane: 'магия',
  magic: 'магия',
  nature: 'природа',
  earth: 'земля',
  water: 'вода',
  wind: 'воздух',
  air: 'воздух',
  necrotic: 'некротика',
  psychic: 'разум',
  true: 'чистый',
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
