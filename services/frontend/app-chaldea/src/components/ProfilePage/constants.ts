import swordIcon from '../../assets/icons/equipment/sword.svg';
import shieldIcon from '../../assets/icons/equipment/shield.svg';
import necklaceIcon from '../../assets/icons/equipment/necklace.svg';
import ringIcon from '../../assets/icons/equipment/ring.svg';
import helmetIcon from '../../assets/icons/equipment/helmet.svg';
import armorIcon from '../../assets/icons/equipment/armor.svg';
import cloakIcon from '../../assets/icons/equipment/cloak.svg';
import beltIcon from '../../assets/icons/equipment/belt.svg';
import braceletIcon from '../../assets/icons/equipment/bracelet.svg';
import potionIcon from '../../assets/icons/equipment/potion.svg';
import scrollIcon from '../../assets/icons/equipment/scroll.svg';
import resourceIcon from '../../assets/icons/equipment/resource.svg';
import bagIcon from '../../assets/icons/equipment/bag.svg';

// Maps item_type to placeholder SVG icon path
export const ITEM_TYPE_ICONS: Record<string, string> = {
  main_weapon: swordIcon,
  additional_weapons: swordIcon,
  shield: shieldIcon,
  bracelet: braceletIcon,
  necklace: necklaceIcon,
  ring: ringIcon,
  head: helmetIcon,
  body: armorIcon,
  cloak: cloakIcon,
  belt: beltIcon,
  consumable: potionIcon,
  scroll: scrollIcon,
  resource: resourceIcon,
  misc: bagIcon,
};

export const CATEGORY_LIST = [
  { key: 'all', label: 'Все', icon: bagIcon },
  { key: 'main_weapon', label: 'Оружие', icon: swordIcon },
  { key: 'body', label: 'Броня', icon: armorIcon },
  { key: 'head', label: 'Шлем', icon: helmetIcon },
  { key: 'cloak', label: 'Плащ', icon: cloakIcon },
  { key: 'belt', label: 'Пояс', icon: beltIcon },
  { key: 'ring', label: 'Кольцо', icon: ringIcon },
  { key: 'necklace', label: 'Ожерелье', icon: necklaceIcon },
  { key: 'shield', label: 'Щит', icon: shieldIcon },
  { key: 'bracelet', label: 'Браслет', icon: braceletIcon },
  { key: 'consumable', label: 'Зелья', icon: potionIcon },
  { key: 'scroll', label: 'Свитки', icon: scrollIcon },
  { key: 'resource', label: 'Ресурсы', icon: resourceIcon },
  { key: 'misc', label: 'Разное', icon: bagIcon },
] as const;

export const EQUIPMENT_SLOT_ORDER = [
  'head',
  'body',
  'cloak',
  'belt',
  'shield',
  'ring',
  'necklace',
  'bracelet',
  'main_weapon',
  'additional_weapons',
] as const;

export const EQUIPMENT_SLOT_LABELS: Record<string, string> = {
  head: 'Шлем',
  body: 'Броня',
  cloak: 'Плащ',
  belt: 'Пояс',
  shield: 'Щит',
  ring: 'Кольцо',
  necklace: 'Ожерелье',
  bracelet: 'Браслет',
  main_weapon: 'Основное оружие',
  additional_weapons: 'Дополнительное оружие',
};

// Equipment item types that can be equipped
export const EQUIPMENT_TYPES = new Set([
  'head',
  'body',
  'cloak',
  'belt',
  'shield',
  'ring',
  'necklace',
  'bracelet',
  'main_weapon',
  'additional_weapons',
]);

// Minimum cells to display in the item grid
export const MIN_GRID_CELLS = 40;

// --- Race name mapping ---

export const RACE_NAMES: Record<number, string> = {
  1: 'Человек',
  2: 'Эльф',
  3: 'Гном',
  4: 'Орк',
  5: 'Нежить',
  6: 'Зверолюд',
  7: 'Полукровка',
};

// --- Class name mapping ---

export const CLASS_NAMES: Record<number, string> = {
  1: 'Воин',
  2: 'Плут',
  3: 'Маг',
};

// --- Stat labels for StatsPanel ---

export const STAT_LABELS: Record<string, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intelligence: 'Интеллект',
  endurance: 'Выносливость',
  health: 'Здоровье',
  mana: 'Мана',
  energy: 'Энергия',
  stamina: 'Стамина',
  charisma: 'Харизма',
  luck: 'Удача',
  damage: 'Урон',
  dodge: 'Уклонение',
  critical_hit_chance: 'Крит. шанс',
  critical_damage: 'Крит. урон',
};

// --- Stats that display as percentages ---

export const PERCENTAGE_STATS = new Set(['dodge', 'critical_hit_chance']);

// --- Resource bar config ---

export const RESOURCE_BARS = [
  { key: 'health', label: 'Здоровье', colorClass: 'stat-bar-hp' },
  { key: 'mana', label: 'Мана', colorClass: 'stat-bar-mana' },
  { key: 'energy', label: 'Энергия', colorClass: 'stat-bar-energy' },
  { key: 'stamina', label: 'Стамина', colorClass: 'stat-bar-stamina' },
] as const;

// --- Primary stats display order (two-column layout) ---

export const PRIMARY_STATS = [
  'strength',
  'agility',
  'intelligence',
  'endurance',
  'health',
  'mana',
  'energy',
  'stamina',
  'charisma',
  'luck',
  'damage',
  'dodge',
  'critical_hit_chance',
  'critical_damage',
] as const;
