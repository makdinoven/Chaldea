// Types for Player Skill Tree View — perk system (FEAT-125)

export type {
  FullClassTreeResponse,
  TreeNodeInTreeResponse,
  TreeNodeConnectionInTree,
  TreeNodeSkillRead,
  ClassSkillTreeRead,
} from '../AdminClassTreeEditor/types';

// --- Player Progress ---

export interface ChosenNodeProgress {
  node_id: number;
  chosen_at: string | null;
}

export interface PurchasedSkillProgress {
  skill_id: number;
  character_skill_id: number;
  level: number;
}

export interface CharacterTreeProgressResponse {
  character_id: number;
  tree_id: number;
  chosen_nodes: ChosenNodeProgress[];
  purchased_skills: PurchasedSkillProgress[];
  active_experience: number;
  character_level: number;
}

// --- Node Visual State ---

export type NodeVisualState =
  | 'chosen'
  | 'available'
  /** Not yet, but still possible. */
  | 'locked'
  /** An alternative at the same fork was taken. */
  | 'blocked'
  /** Cut off further up the chain — every route here runs through a dead node. */
  | 'unreachable';

// --- Damage / Effect shared ---

export interface DamageEntry {
  id?: number;
  damage_type: string;
  amount: number | string;
  chance: number | null;
  target_side: string | null;
  weapon_slot: string | null;
  description?: string | null;
  // AoE (FEAT-146): single | splash | cleave | all | random_n
  aoe_shape?: string | null;
  aoe_falloff?: number | null;
  aoe_max_targets?: number | null;
}

export interface EffectEntry {
  id?: number;
  target_side: string | null;
  effect_name: string;
  description?: string | null;
  chance: number | null;
  duration: number | null;
  magnitude: number | null;
  attribute_key?: string | null;
}

// --- Perk system shape ---

export interface SkillBase {
  cost_energy: number;
  cost_mana: number;
  cooldown: number;
  level_requirement: number;
  damage_entries: DamageEntry[];
  effects: EffectEntry[];
}

export interface SkillPerkRead {
  id: number;
  skill_id?: number;
  name: string;
  description: string | null;
  perk_image: string | null;
  delta_cost_energy: number | null;
  delta_cost_mana: number | null;
  delta_cooldown: number | null;
  delta_level_requirement: number | null;
  sort_order?: number;
  damage_entries: DamageEntry[];
  effects: EffectEntry[];
}

export interface SkillWithPerks {
  id: number;
  name: string;
  skill_type: string;
  description: string | null;
  purchase_cost: number;
  skill_image: string | null;
  min_level?: number;
  class_limitations?: string | null;
  subclass_limitations?: string | null;
  is_mob_skill?: boolean;
  race_limitations?: string | null;
  subrace_limitations?: string | null;
  base: SkillBase;
  perks: SkillPerkRead[];
}

export interface CharacterSkillState {
  character_skill_id: number;
  skill_id: number;
  level: number;
  free_perk_points: number;
  selected_perk_ids: number[];
  reset_available_at: string | null;
  skill: {
    id: number;
    name: string;
    skill_type: string;
    skill_image: string | null;
    // FEAT-151 — base (non-perk-adjusted) costs, added to the list endpoint
    cost_energy: number;
    cost_mana: number;
    cooldown: number;
  };
}

export interface ResolvedSkill {
  skill_id: number;
  character_id: number;
  level: number;
  selected_perk_ids: number[];
  skill_type: string;
  cost_energy: number;
  cost_mana: number;
  cooldown: number;
  level_requirement: number;
  damage_entries: DamageEntry[];
  effects: EffectEntry[];
}

// --- Redux State ---

export interface PlayerTreeState {
  tree: import('../AdminClassTreeEditor/types').FullClassTreeResponse | null;
  progress: CharacterTreeProgressResponse | null;
  selectedNodeId: number | null;
  loading: boolean;
  error: string | null;
  subclassTrees: import('../AdminClassTreeEditor/types').ClassSkillTreeRead[];
}
