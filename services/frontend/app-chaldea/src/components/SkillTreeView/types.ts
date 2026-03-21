// Types for Player Skill Tree View — reuses admin types + player-specific

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
  skill_rank_id: number;
  character_skill_id: number;
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

export type NodeVisualState = 'chosen' | 'available' | 'locked' | 'blocked';

// --- Skill Full Tree (for upgrade modal) ---

export interface SkillRankRead {
  id: number;
  skill_id: number;
  rank_name: string | null;
  rank_image: string | null;
  rank_number: number;
  upgrade_cost: number;
  cost_energy: number;
  cost_mana: number;
  cooldown: number;
  level_requirement: number;
  left_child_id: number | null;
  right_child_id: number | null;
  class_limitations: string | null;
  race_limitations: string | null;
  subrace_limitations: string | null;
  rank_description: string | null;
  damage_entries: DamageEntry[];
  effects: EffectEntry[];
}

export interface DamageEntry {
  id?: number;
  damage_type: string;
  amount: number;
  chance: number;
  target_side: string;
  weapon_slot: string | null;
  description?: string | null;
}

export interface EffectEntry {
  id?: number;
  target_side: string;
  effect_name: string;
  description?: string | null;
  chance: number;
  duration: number;
  magnitude: number;
  attribute_key?: string | null;
}

export interface SkillFullTree {
  id: number;
  name: string;
  skill_type: string;
  description: string | null;
  skill_image: string | null;
  purchase_cost: number;
  min_level: number;
  ranks: SkillRankRead[];
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
