export interface TitleCondition {
  type: string;
  stat?: string;
  operator: string;
  value: number | string;
}

export interface Title {
  id_title: number;
  name: string;
  description: string;
  rarity: 'common' | 'rare' | 'legendary';
  conditions: TitleCondition[] | null;
  reward_passive_exp: number;
  reward_active_exp: number;
  icon: string | null;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  holders_count: number;
}

export interface CharacterTitle extends Omit<Title, 'holders_count'> {
  is_unlocked: boolean;
  unlocked_at: string | null;
  is_custom: boolean;
  progress: Record<string, { current: number; required: number }> | null;
}

/**
 * A title is "visually active" when it's either officially unlocked
 * OR all its conditions are met (progress >= required for every condition).
 */
export function isTitleActive(title: CharacterTitle): boolean {
  if (title.is_unlocked) return true;
  if (!title.conditions || title.conditions.length === 0) return false;
  return title.conditions.every((c) => {
    const key = c.stat ?? c.type;
    const entry = title.progress?.[key];
    if (!entry) return false;
    return entry.current >= entry.required;
  });
}
