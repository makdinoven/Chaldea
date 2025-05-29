// skillConstants.js
export const CLASS_OPTIONS = [
  { label: "Воин", value: "1" },
  { label: "Маг", value: "2" },
  { label: "Разбойник", value: "3" },
];
export const RACE_OPTIONS = [
  { label: "Человек", value: "1" },
  { label: "Эльф", value: "2" },
  { label: "Драконид", value: "3" },
  { label: "Дворф", value: "4" },
  { label: "Демон", value: "5" },
  { label: "Бистмен", value: "6" },
  { label: "Урук", value: "7" },
];
export const SUBRACE_OPTIONS = [
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
export const SKILL_TYPES = [
  { label: "Атакующий", value: "attack" },
  { label: "Защитный", value: "defense" },
  { label: "Поддержка", value: "support" },
];

export const DAMAGE_TYPES = [
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

export const WEAPON_SLOTS = [
  { label: "Основное оружие", value: "main_weapon" },
  { label: "Доп. оружие", value: "additional_weapons" },
];

export const STAT_MODIFIERS = [
  { label: "Крит.шанс(%)", key: "critical_hit_chance" },
  { label: "Крит.урон(%)", key: "crit_damage" },
  { label: "Шанс уклонения(%)", key: "dodge_chance" },
  { label: "HP(±)", key: "hp" },
  { label: "Mana(±)", key: "mana" },
  { label: "Energy(±)", key: "energy" },
];

export const COMPLEX_EFFECTS = [
  { label: "Кровотечение", value: "Bleeding" },
  { label: "Отравление", value: "Poison" },
  { label: "Паралич", value: "Paralysis" },
];

/**
 * У нас только проценты для уязвимостей => используем структуру, похожую на buffDebuff,
 * но назовём "vulnerability" (type, percent, duration, chance).
 */

/**
 * Пустой ранг: 2 вкладки (self, enemy), по 5 секций (damage, buff, resist, vulnerability, complex).
 */
export const EMPTY_RANK_TEMPLATE = {
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

export function cloneRankAsNew(originalRank) {
  const { id, rankImageFile, rankImagePreview, ...rest } = originalRank;
  return {
    ...rest,
    id: null,
    isNew: true,
    rankImageFile: null,
    rankImagePreview: "", // сбрасываем при копировании
  };
}

let rankIdCounter = 1;

export function generateRankId() {
  const newId = String(rankIdCounter++);
  return newId;
}
