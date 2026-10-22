/*
  A skill's spread in a book — its card on the left, its perks on the right —
  and what can be done there. Built outside the 3D scene (see useSkillPage),
  inked onto the pages inside it (see skillPageInk).
*/

export interface SkillStat {
  label: string;
  base: number;
  total: number;
}

export type PerkState = 'selected' | 'available' | 'locked';

export interface SkillPagePerk {
  id: number;
  name: string;
  description: string | null;
  /** What it changes, one short line each: "Мана: −2", "+5 огнём", "Оглушение (1 ход.)". */
  changes: string[];
  state: PerkState;
}

export interface SkillPageModel {
  skillId: number;
  /** Still fetching the skill; the pages show only that the ink is drying. */
  loading: boolean;
  error: string | null;
  title: string;
  /** Same-origin picture URL, if the page can draw it. */
  image: string | null;
  description: string | null;
  level: number;
  maxLevel: number;
  freePerkPoints: number;
  stats: SkillStat[];
  /** The skill's damage and effects as they stand now, one line each. */
  effects: { text: string; tone: 'damage' | 'effect' }[];
  upgrade: { label: string; enabled: boolean; busy: boolean };
  reset: { label: string; enabled: boolean };
  /** Asking whether to really reset, in ink on the page. */
  confirmingReset: boolean;
  perks: SkillPagePerk[];
  /** A note over the perks: a free point to spend, or too few perks set up. */
  perkNote: string | null;
  /** Which page of perks is showing, when they don't all fit. */
  perkPage: number;
}

export type SkillPageAction =
  | { kind: 'back' }
  | { kind: 'upgrade' }
  | { kind: 'reset' }
  | { kind: 'confirmReset' }
  | { kind: 'cancelReset' }
  | { kind: 'pick'; perkId: number }
  | { kind: 'perkPage'; page: number }
  | { kind: 'retry' };

/** Stable key for an action, for hover and hit-testing. */
export const skillActionKey = (a: SkillPageAction) =>
  a.kind === 'pick' ? `pick:${a.perkId}` : a.kind === 'perkPage' ? `perkPage:${a.page}` : a.kind;
