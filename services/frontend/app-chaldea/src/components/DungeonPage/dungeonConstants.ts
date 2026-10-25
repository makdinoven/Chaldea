export const ROOM_COLORS: Record<string, string> = {
  battle: '#ef4444',
  boss: '#dc2626',
  treasure: '#eab308',
  trap: '#f97316',
  event: '#3b82f6',
  rest: '#22c55e',
  merchant: '#a855f7',
  fork: '#6b7280',
  teleport: '#06b6d4',
  deadend: '#374151',
};

export const ROOM_TYPE_ICONS: Record<string, string> = {
  battle: '⚔️',
  boss: '👑',
  treasure: '💎',
  trap: '🪤',
  event: '📜',
  rest: '🏕️',
  merchant: '🛒',
  fork: '🔀',
  teleport: '🌀',
  deadend: '🚫',
};

export const ROOM_TYPE_LABELS: Record<string, string> = {
  battle: 'Бой',
  boss: 'Босс',
  treasure: 'Сокровищница',
  trap: 'Ловушка',
  event: 'Событие',
  rest: 'Отдых',
  merchant: 'Торговец',
  fork: 'Развилка',
  teleport: 'Телепорт',
  deadend: 'Тупик',
};

/** Keys of locked doors: found and used inside one run; each opens every door of its kind. */
export type DungeonKeyKind = 'copper' | 'silver' | 'gold' | 'bone' | 'obsidian' | 'crimson';

export const DUNGEON_KEYS: Record<DungeonKeyKind, { name: string; color: string }> = {
  copper: { name: 'Медный ключ', color: '#c87533' },
  silver: { name: 'Серебряный ключ', color: '#cfd3da' },
  gold: { name: 'Золотой ключ', color: '#f0c64a' },
  bone: { name: 'Костяной ключ', color: '#e8dfc8' },
  obsidian: { name: 'Обсидиановый ключ', color: '#8a6cc4' },
  crimson: { name: 'Багровый ключ', color: '#d0283a' },
};

export const DUNGEON_KEY_KINDS = Object.keys(DUNGEON_KEYS) as DungeonKeyKind[];

export const keyInfo = (kind: string | null | undefined) =>
  DUNGEON_KEYS[kind as DungeonKeyKind] ?? { name: 'Ключ', color: '#cfd3da' };

/** sessionStorage key: BattlePage returns to this run after a dungeon battle ({battleId, sessionId}). */
export const DUNGEON_BATTLE_RETURN_KEY = 'dungeonBattleReturn';
