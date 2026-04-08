// skillConstants.ts

// ---- TypeScript Interfaces ----

export interface DamageEntry {
  damage_type: string;
  amount: number;
  chance: number;
  weapon_slot?: string;
  description?: string;
}

export interface BuffEntry {
  damage_type: string;
  percent: number;
  duration: number;
  chance: number;
}

export interface ResistEntry {
  damage_type: string;
  percent: number;
  duration: number;
  chance: number;
}

export interface VulnerabilityEntry {
  type: string;
  percent: number;
  duration: number;
  chance: number;
}

export interface ComplexEffectEntry {
  effect_name: string;
  chance: number;
  duration: number;
  magnitude: number;
  attribute_key?: string;
}

export interface StatModEntry {
  key: string;
  amount: number;
  duration: number;
  chance: number;
}

export interface RankData {
  id: string | null;
  rank_number: number;
  rank_name?: string;
  left_child_id: string | null;
  right_child_id: string | null;

  cost_energy: number;
  cost_mana: number;
  cooldown: number;
  level_requirement: number;
  upgrade_cost: number;
  rank_description: string;

  rankImageFile: File | null;
  rankImagePreview: string;

  selfDamage: DamageEntry[];
  selfDamageBuff: BuffEntry[];
  selfResist: ResistEntry[];
  selfVulnerability: VulnerabilityEntry[];
  selfComplexEffects: ComplexEffectEntry[];
  selfStatMods: StatModEntry[];

  enemyDamage: DamageEntry[];
  enemyDamageBuff: BuffEntry[];
  enemyResist: ResistEntry[];
  enemyVulnerability: VulnerabilityEntry[];
  enemyComplexEffects: ComplexEffectEntry[];
  enemyStatMods: StatModEntry[];

  class_limitations: string;
  race_limitations: string;
  subrace_limitations: string;

  isNew?: boolean;
  damage_entries?: unknown[];
  effects?: unknown[];
  [key: string]: unknown;
}

export interface SelectOption {
  label: string;
  value: string;
  race?: string;
}

export interface ComplexEffectOption {
  value: string;
  label: string;
  description: string;
  hasAttributeKey: boolean;
  attributeKeyOptions: SelectOption[] | null;
  fixedDuration: number | null;
  allowedSides: string[] | null;
}

export interface StatModifierOption {
  label: string;
  key: string;
}

// ---- Constants ----

// Canonical class list (matches docker/mysql/init/01-seed-data.sql `classes` table)
export const CLASS_OPTIONS: SelectOption[] = [
  { label: "Воин", value: "1" },
  { label: "Плут", value: "2" },
  { label: "Маг", value: "3" },
];

export const RACE_OPTIONS: SelectOption[] = [
  { label: "Человек", value: "1" },
  { label: "Эльф", value: "2" },
  { label: "Драконид", value: "3" },
  { label: "Дворф", value: "4" },
  { label: "Демон", value: "5" },
  { label: "Бистмен", value: "6" },
  { label: "Урук", value: "7" },
];

export const SUBRACE_OPTIONS: SelectOption[] = [
  { label: "Норды", value: "1", race: "1" },
  { label: "Ост", value: "2", race: "1" },
  { label: "Ориентал", value: "3", race: "1" },
  { label: "Лесной", value: "4", race: "2" },
  { label: "Тёмный", value: "5", race: "2" },
  { label: "Малах", value: "6", race: "2" },
  { label: "Равагарт", value: "7", race: "3" },
  { label: "Рорис", value: "8", race: "3" },
  { label: "Ониксовый", value: "9", race: "4" },
  { label: "Левиафан", value: "10", race: "4" },
  { label: "Альб", value: "11", race: "5" },
  { label: "Зверолюд", value: "12", race: "5" },
  { label: "Полукровка", value: "13", race: "6" },
  { label: "Северный", value: "14", race: "6" },
  { label: "Темный", value: "15", race: "7" },
  { label: "Золотой", value: "16", race: "7" },
];

export const SKILL_TYPES: SelectOption[] = [
  { label: "Атакующий", value: "attack" },
  { label: "Защитный", value: "defense" },
  { label: "Поддержка", value: "support" },
];

export const DAMAGE_TYPES: SelectOption[] = [
  { label: "Общий", value: "all" },
  { label: "Физический", value: "physical" },
  { label: "Режущий", value: "catting" },
  { label: "Дробящий", value: "crushing" },
  { label: "Колюще-пронзающий", value: "piercing" },
  { label: "Магический", value: "magic" },
  { label: "Огонь", value: "fire" },
  { label: "Лед", value: "ice" },
  { label: "Вода", value: "watering" },
  { label: "Электричество", value: "electricity" },
  { label: "Ветер", value: "wind" },
  { label: "Святой", value: "sainting" },
  { label: "Проклятие", value: "damning" },
];

export const WEAPON_SLOTS: SelectOption[] = [
  { label: "Основное оружие", value: "main_weapon" },
  { label: "Доп. оружие", value: "additional_weapons" },
];

export const STAT_MODIFIERS: StatModifierOption[] = [
  { label: "Крит.шанс(%)", key: "critical_hit_chance" },
  { label: "Крит.урон(%)", key: "crit_damage" },
  { label: "Шанс уклонения(%)", key: "dodge_chance" },
  { label: "HP(±)", key: "hp" },
  { label: "Mana(±)", key: "mana" },
  { label: "Energy(±)", key: "energy" },
];

export const SKILL_TYPE_OPTIONS: SelectOption[] = [
  { label: "Атака", value: "attack" },
  { label: "Поддержка", value: "support" },
  { label: "Защита", value: "defense" },
  { label: "Случайно", value: "random" },
];

export const PRIMARY_ATTR_OPTIONS: SelectOption[] = [
  { label: "Сила", value: "strength" },
  { label: "Ловкость", value: "agility" },
  { label: "Интеллект", value: "intelligence" },
  { label: "Выносливость", value: "endurance" },
];

export const POISON_SUBTYPE_OPTIONS: SelectOption[] = [
  { label: "Периодический урон", value: "periodic_damage" },
  { label: "Снижение характеристик", value: "stat_reduction" },
  { label: "Снижение защит", value: "defense_reduction" },
  { label: "Паралич", value: "paralysis" },
];

export const COMPLEX_EFFECTS: ComplexEffectOption[] = [
  {
    value: "Bleeding",
    label: "Кровотечение",
    description: "Периодический урон HP каждый ход",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: null,
  },
  {
    value: "ArmorBreak",
    label: "Раскол брони",
    description: "Снижает все физические сопротивления",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: null,
  },
  {
    value: "Stun",
    label: "Оглушение",
    description: "Блокирует все действия на 1 ход",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: 1,
    allowedSides: null,
  },
  {
    value: "Knockdown",
    label: "Сбитие с ног",
    description: "Блокирует один тип навыков на 1 ход",
    hasAttributeKey: true,
    attributeKeyOptions: SKILL_TYPE_OPTIONS,
    fixedDuration: 1,
    allowedSides: null,
  },
  {
    value: "Daze",
    label: "Ошеломление",
    description: "Снижает исходящий урон",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: null,
  },
  {
    value: "MagicImpact",
    label: "Магическое воздействие",
    description: "Модифицирует первичный атрибут (+ = бафф, - = дебафф)",
    hasAttributeKey: true,
    attributeKeyOptions: PRIMARY_ATTR_OPTIONS,
    fixedDuration: null,
    allowedSides: null,
  },
  {
    value: "Burn",
    label: "Возгорание",
    description: "Периодический урон HP + снижение уклонения",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: null,
  },
  {
    value: "Freeze",
    label: "Обледенение",
    description: "Снижает ВСЕ сопротивления урону",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: null,
  },
  {
    value: "Wet",
    label: "Мокрый",
    description: "Снижает весь исходящий магический урон",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: null,
  },
  {
    value: "Electrify",
    label: "Электролизация",
    description: "Увеличивает весь входящий урон",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: null,
  },
  {
    value: "Windburn",
    label: "Обветрение",
    description: "Блокирует один тип навыков на 1 ход",
    hasAttributeKey: true,
    attributeKeyOptions: SKILL_TYPE_OPTIONS,
    fixedDuration: 1,
    allowedSides: null,
  },
  {
    value: "Holy",
    label: "Святость",
    description: "Повышает все 4 первичных атрибута (только на себя)",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: ["self"],
  },
  {
    value: "Curse",
    label: "Проклятие",
    description: "Снижает все 4 первичных атрибута (только на врага)",
    hasAttributeKey: false,
    attributeKeyOptions: null,
    fixedDuration: null,
    allowedSides: ["enemy"],
  },
  {
    value: "Poison",
    label: "Отравление",
    description: "Подтип определяет поведение: урон, снижение стат, защит или паралич",
    hasAttributeKey: true,
    attributeKeyOptions: POISON_SUBTYPE_OPTIONS,
    fixedDuration: null,
    allowedSides: null,
  },
];

/**
 * У нас только проценты для уязвимостей => используем структуру, похожую на buffDebuff,
 * но назовём "vulnerability" (type, percent, duration, chance).
 */

/**
 * Пустой ранг: 2 вкладки (self, enemy), по 5 секций (damage, buff, resist, vulnerability, complex).
 */
export const EMPTY_RANK_TEMPLATE: RankData = {
  id: null,
  rank_number: 1,
  left_child_id: null,
  right_child_id: null,

  cost_energy: 0,
  cost_mana: 0,
  cooldown: 0,
  level_requirement: 1,
  upgrade_cost: 0,
  rank_description: "",

  // Локальное хранение изображения ранга (base64 / blob)
  rankImageFile: null, // сам File
  rankImagePreview: "", // base64 или blob url

  // 5 секций (self)
  selfDamage: [],
  selfDamageBuff: [],
  selfResist: [],
  selfVulnerability: [], // [{type, percent, duration, chance} ...]
  selfComplexEffects: [],
  selfStatMods: [],

  // 5 секций (enemy)
  enemyDamage: [],
  enemyDamageBuff: [],
  enemyResist: [],
  enemyVulnerability: [],
  enemyComplexEffects: [],
  enemyStatMods: [],

  // Доп. ограничения
  class_limitations: "",
  race_limitations: "",
  subrace_limitations: "",
};

export function cloneRankAsNew(originalRank: RankData): RankData {
  // Extract rankImageFile before structuredClone — File objects are not cloneable
  const { rankImageFile, ...rest } = originalRank;
  const cloned = structuredClone(rest);
  return {
    ...cloned,
    id: null,
    isNew: true,
    rankImageFile: null,
    rankImagePreview: "",
    left_child_id: null,
    right_child_id: null,
  };
}

let rankIdCounter = 1;

export function generateRankId(): string {
  const newId = String(rankIdCounter++);
  return newId;
}
