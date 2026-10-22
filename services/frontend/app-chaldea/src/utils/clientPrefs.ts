import { useSyncExternalStore } from 'react';

/*
  Settings that belong to this browser rather than to the account: a weak
  phone and a strong computer want different graphics, and sound and system
  notifications are a matter of the device anyway. Kept in localStorage and
  shared with every component through a tiny subscribe/notify store.
*/

export type SkillTreeViewPref = 'auto' | 'wheel' | 'books';
export type BattleViewPref = '2d' | '3d';
export type GraphicsPref = 'normal' | 'low';
export type TextSizePref = 'normal' | 'large' | 'xlarge';

export interface ClientPrefs {
  soundEnabled: boolean;
  /** 0..1 */
  soundVolume: number;
  browserNotifications: boolean;
  battleView: BattleViewPref;
  graphics: GraphicsPref;
  textSize: TextSizePref;
  /** Ask before selling, dropping or destroying items and buying out lots. */
  confirmDangerous: boolean;
}

const PREFS_KEY = 'chaldea:prefs:v1';
/** The skill tree page has remembered its view under this key since before the settings page. */
const SKILL_TREE_VIEW_KEY = 'skillTree.viewMode';

export const DEFAULT_CLIENT_PREFS: ClientPrefs = {
  soundEnabled: true,
  soundVolume: 0.5,
  browserNotifications: false,
  battleView: '2d',
  graphics: 'normal',
  textSize: 'normal',
  confirmDangerous: true,
};

const oneOf = <T extends string>(value: unknown, allowed: readonly T[], fallback: T): T =>
  allowed.includes(value as T) ? (value as T) : fallback;

const sanitize = (raw: Partial<Record<keyof ClientPrefs, unknown>>): ClientPrefs => {
  const d = DEFAULT_CLIENT_PREFS;
  const volume = Number(raw.soundVolume);
  return {
    soundEnabled: typeof raw.soundEnabled === 'boolean' ? raw.soundEnabled : d.soundEnabled,
    soundVolume: Number.isFinite(volume) ? Math.min(1, Math.max(0, volume)) : d.soundVolume,
    browserNotifications:
      typeof raw.browserNotifications === 'boolean' ? raw.browserNotifications : d.browserNotifications,
    battleView: oneOf(raw.battleView, ['2d', '3d'] as const, d.battleView),
    graphics: oneOf(raw.graphics, ['normal', 'low'] as const, d.graphics),
    textSize: oneOf(raw.textSize, ['normal', 'large', 'xlarge'] as const, d.textSize),
    confirmDangerous: typeof raw.confirmDangerous === 'boolean' ? raw.confirmDangerous : d.confirmDangerous,
  };
};

const read = (): ClientPrefs => {
  try {
    const stored = localStorage.getItem(PREFS_KEY);
    return stored ? sanitize(JSON.parse(stored)) : DEFAULT_CLIENT_PREFS;
  } catch {
    return DEFAULT_CLIENT_PREFS;
  }
};

let current: ClientPrefs = read();
const listeners = new Set<() => void>();

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

/** The current preferences, for code outside React (WebSocket handlers, helpers). */
export const getClientPrefs = (): ClientPrefs => current;

export const setClientPrefs = (patch: Partial<ClientPrefs>) => {
  current = sanitize({ ...current, ...patch });
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(current));
  } catch {
    // Applies for this visit only.
  }
  listeners.forEach((listener) => listener());
};

// Another tab changed them: follow along.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key !== PREFS_KEY) return;
    current = read();
    listeners.forEach((listener) => listener());
  });
}

export const useClientPrefs = (): ClientPrefs => useSyncExternalStore(subscribe, getClientPrefs);

/* The skill tree's view keeps its own key so the page goes on reading it as before. */

export const getSkillTreeViewPref = (): SkillTreeViewPref => {
  try {
    const saved = localStorage.getItem(SKILL_TREE_VIEW_KEY);
    return saved === 'wheel' || saved === 'books' ? saved : 'auto';
  } catch {
    return 'auto';
  }
};

export const setSkillTreeViewPref = (value: SkillTreeViewPref) => {
  try {
    if (value === 'auto') localStorage.removeItem(SKILL_TREE_VIEW_KEY);
    else localStorage.setItem(SKILL_TREE_VIEW_KEY, value);
  } catch {
    // Not remembered; the tree page falls back to its screen-based default.
  }
};
