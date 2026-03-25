export interface PerkCondition {
  type: 'cumulative_stat' | 'character_level' | 'attribute' | 'quest' | 'admin_grant';
  stat?: string;
  operator: '>=' | '<=' | '==' | '>';
  value: number;
}

export interface PerkBonuses {
  flat: Record<string, number>;
  percent: Record<string, number>;
  contextual: Record<string, number>;
  passive: Record<string, number>;
}

export interface Perk {
  id: number;
  name: string;
  description: string;
  category: string;
  rarity: 'common' | 'rare' | 'legendary';
  icon: string | null;
  conditions: PerkCondition[];
  bonuses: PerkBonuses;
  sort_order: number;
  is_active: boolean;
}

export interface CharacterPerk extends Perk {
  is_unlocked: boolean;
  unlocked_at: string | null;
  is_custom: boolean;
  progress: Record<string, { current: number; required: number }>;
}

export interface CumulativeStats {
  character_id: number;
  total_damage_dealt: number;
  total_damage_received: number;
  pve_kills: number;
  pvp_wins: number;
  pvp_losses: number;
  total_battles: number;
  max_damage_single_battle: number;
  max_win_streak: number;
  current_win_streak: number;
  total_rounds_survived: number;
  low_hp_wins: number;
}

export interface PerksResponse {
  character_id: number;
  perks: CharacterPerk[];
}

/**
 * A perk is "visually active" when it's either officially unlocked
 * OR all its conditions are met (progress >= required for every condition).
 */
export function isPerkActive(perk: CharacterPerk): boolean {
  if (perk.is_unlocked) return true;
  if (perk.conditions.length === 0) return false;
  return perk.conditions.every((c) => {
    const key = c.stat ?? c.type;
    const entry = perk.progress?.[key];
    if (!entry) return false;
    return entry.current >= entry.required;
  });
}
