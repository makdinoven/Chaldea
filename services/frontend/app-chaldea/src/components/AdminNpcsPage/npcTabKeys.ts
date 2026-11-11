/* FEAT-208: tabs of the expanded NPC panel. */

export type NpcTabKey =
  | 'general'
  | 'stats'
  | 'equipment'
  | 'dialogues'
  | 'quests'
  | 'shop'
  | 'teleports'
  | 'patrol'
  | 'fence';

export const NPC_TAB_KEYS: readonly NpcTabKey[] = [
  'general',
  'stats',
  'equipment',
  'dialogues',
  'quests',
  'shop',
  'teleports',
  'patrol',
  'fence',
];

export const NPC_TAB_LABELS: Record<NpcTabKey, string> = {
  general: 'Основное',
  stats: 'Характеристики',
  equipment: 'Снаряжение',
  dialogues: 'Диалоги',
  quests: 'Квесты',
  shop: 'Магазин',
  teleports: 'Телепорты',
  patrol: 'Патруль',
  fence: 'Скупка',
};

const BASE_TABS: NpcTabKey[] = ['general', 'stats', 'equipment', 'dialogues', 'quests'];

/** Role-only tabs, keyed by the SAVED npc_role. */
const ROLE_TABS: Record<string, NpcTabKey> = {
  merchant: 'shop',
  teleport_master: 'teleports',
  guard: 'patrol',
  fence: 'fence',
};

export const isNpcTabKey = (value: string | null): value is NpcTabKey =>
  value !== null && (NPC_TAB_KEYS as readonly string[]).includes(value);

export const availableTabs = (role: string | null, isNew: boolean): NpcTabKey[] => {
  if (isNew) return ['general'];
  const roleTab = role ? ROLE_TABS[role] : undefined;
  return roleTab ? [...BASE_TABS, roleTab] : BASE_TABS;
};
