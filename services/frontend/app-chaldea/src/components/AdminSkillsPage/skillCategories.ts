import type { Subclass } from '../AdminClassTreeEditor/types';

/**
 * The categories the admin skill list is divided into.
 *
 * They do not overlap. A skill scoped to a subclass belongs to that subclass
 * alone — it is a narrower category than its parent class, not a part of it —
 * and mob skills are split from the players' skills outright. The backend
 * filters on exactly this shape (class_id / subclass_key / mob), so a category
 * is both what you are looking at and what a skill created here becomes.
 */

export type SkillCategory =
  | { kind: 'all' }
  /** No scoping at all: available to everyone. */
  | { kind: 'general' }
  | { kind: 'class'; classId: number }
  | { kind: 'subclass'; classId: number; subclassKey: string }
  | { kind: 'race'; raceId: number }
  | { kind: 'subrace'; raceId: number; subraceId: number }
  | { kind: 'mob' };

/** A race and its subraces, as /characters/races returns them. */
export interface RaceWithSubraces {
  id_race: number;
  name: string;
  subraces: Array<{ id_subrace: number; name: string }>;
}

export const ALL_SKILLS: SkillCategory = { kind: 'all' };

/** DB class ids, with the accent used for them elsewhere in the admin. */
export const SKILL_CLASSES = [
  { id: 1, label: 'Воин', accent: '#f87171' },
  { id: 2, label: 'Плут', accent: '#34d399' },
  { id: 3, label: 'Маг', accent: '#38bdf8' },
] as const;

export const MOB_ACCENT = '#c084fc';
export const RACE_ACCENT = '#fbbf24';
export const GENERAL_ACCENT = '#94a3b8';

export const categoryAccent = (category: SkillCategory): string => {
  switch (category.kind) {
    case 'class':
    case 'subclass':
      return SKILL_CLASSES.find((c) => c.id === category.classId)?.accent ?? '#f0d95c';
    case 'race':
    case 'subrace':
      return RACE_ACCENT;
    case 'general':
      return GENERAL_ACCENT;
    case 'mob':
      return MOB_ACCENT;
    default:
      return '#f0d95c';
  }
};

export const categoryLabel = (
  category: SkillCategory,
  subclasses: Subclass[],
  races: RaceWithSubraces[] = [],
): string => {
  switch (category.kind) {
    case 'class':
      return SKILL_CLASSES.find((c) => c.id === category.classId)?.label ?? 'Класс';
    case 'subclass':
      return subclasses.find((s) => s.key === category.subclassKey)?.name ?? category.subclassKey;
    case 'race':
      return races.find((r) => r.id_race === category.raceId)?.name ?? 'Раса';
    case 'subrace':
      return (
        races
          .flatMap((r) => r.subraces)
          .find((s) => s.id_subrace === category.subraceId)?.name ?? 'Подраса'
      );
    case 'general':
      return 'Общие';
    case 'mob':
      return 'Мобы';
    default:
      return 'Все';
  }
};

export const sameCategory = (a: SkillCategory, b: SkillCategory): boolean => {
  if (a.kind !== b.kind) return false;
  if (a.kind === 'class' && b.kind === 'class') return a.classId === b.classId;
  if (a.kind === 'subclass' && b.kind === 'subclass') return a.subclassKey === b.subclassKey;
  if (a.kind === 'race' && b.kind === 'race') return a.raceId === b.raceId;
  if (a.kind === 'subrace' && b.kind === 'subrace') return a.subraceId === b.subraceId;
  return true;
};

/** Query parameters that narrow GET /skills/admin/skills/ to this category. */
export const categoryParams = (
  category: SkillCategory,
): Record<string, string | number> => {
  switch (category.kind) {
    case 'class':
      return { class_id: category.classId };
    case 'subclass':
      return { subclass_key: category.subclassKey };
    case 'race':
      return { race_id: category.raceId };
    case 'subrace':
      return { subrace_id: category.subraceId };
    case 'general':
      return { general: 'true' };
    case 'mob':
      return { mob: 'true' };
    default:
      return {};
  }
};

/**
 * The scoping a skill gets when it is created inside a category — the point of
 * having sections rather than filters: you no longer pick the class by hand
 * every time.
 */
export const categoryDefaults = (
  category: SkillCategory,
): {
  class_limitations: string | null;
  subclass_limitations: string | null;
  race_limitations: string | null;
  subrace_limitations: string | null;
  is_mob_skill: boolean;
} => {
  const none = {
    class_limitations: null,
    subclass_limitations: null,
    race_limitations: null,
    subrace_limitations: null,
    is_mob_skill: false,
  };
  switch (category.kind) {
    case 'class':
      return { ...none, class_limitations: String(category.classId) };
    case 'subclass':
      return {
        ...none,
        // The parent class is kept alongside the subclass so the game's
        // class checks still pass; the subclass is what narrows the category.
        class_limitations: String(category.classId),
        subclass_limitations: category.subclassKey,
      };
    case 'race':
      return { ...none, race_limitations: String(category.raceId) };
    case 'subrace':
      return {
        ...none,
        race_limitations: String(category.raceId),
        subrace_limitations: String(category.subraceId),
      };
    case 'mob':
      return { ...none, is_mob_skill: true };
    // "Общие" and "Все" both create an unscoped skill: general is what
    // unscoped means, and from "Все" there is no section to inherit.
    default:
      return none;
  }
};
