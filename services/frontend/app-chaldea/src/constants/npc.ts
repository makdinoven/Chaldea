export const NPC_ROLES = [
  { value: 'merchant', label: 'Торговец' },
  { value: 'guard', label: 'Стражник' },
  { value: 'hero', label: 'Народный герой' },
  { value: 'king', label: 'Король' },
  { value: 'ruler', label: 'Правитель' },
  { value: 'sage', label: 'Мудрец' },
  { value: 'blacksmith', label: 'Кузнец' },
  { value: 'alchemist', label: 'Алхимик' },
  { value: 'mercenary', label: 'Наёмник' },
  { value: 'priest', label: 'Жрец' },
  { value: 'bandit', label: 'Разбойник' },
  { value: 'wanderer', label: 'Странник' },
  { value: 'healer', label: 'Целитель' },
  { value: 'bard', label: 'Бард' },
  { value: 'hunter', label: 'Охотник' },
] as const;

export const NPC_ROLE_LABELS: Record<string, string> = Object.fromEntries(
  NPC_ROLES.map((r) => [r.value, r.label])
);

export const NPC_SEXES = [
  { value: 'male', label: 'Мужской' },
  { value: 'female', label: 'Женский' },
  { value: 'genderless', label: 'Бесполый' },
] as const;

export const NPC_CLASSES = [
  { value: 'Воин', label: 'Воин' },
  { value: 'Плут', label: 'Плут' },
  { value: 'Маг', label: 'Маг' },
] as const;

export const NPC_RACES = [
  { value: 'Человек', label: 'Человек' },
  { value: 'Эльф', label: 'Эльф' },
  { value: 'Дварф', label: 'Дварф' },
  { value: 'Орк', label: 'Орк' },
  { value: 'Полуэльф', label: 'Полуэльф' },
  { value: 'Тифлинг', label: 'Тифлинг' },
  { value: 'Гном', label: 'Гном' },
  { value: 'Полурослик', label: 'Полурослик' },
] as const;
