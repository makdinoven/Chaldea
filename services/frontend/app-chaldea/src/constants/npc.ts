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
  { value: 1, label: 'Воин' },
  { value: 2, label: 'Плут' },
  { value: 3, label: 'Маг' },
] as const;

export const NPC_RACES = [
  { value: 1, label: 'Человек' },
  { value: 2, label: 'Эльф' },
  { value: 3, label: 'Дварф' },
  { value: 4, label: 'Орк' },
  { value: 5, label: 'Полуэльф' },
  { value: 6, label: 'Тифлинг' },
  { value: 7, label: 'Гном' },
  { value: 8, label: 'Полурослик' },
] as const;
