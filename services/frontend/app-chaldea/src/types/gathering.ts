/**
 * Type definitions for the location resource gathering feature (FEAT-128).
 *
 * All shapes mirror the API contracts in section 3.1 of the feature file.
 * Numeric ids/quantities are plain `number`. Timestamps are ISO-8601 strings
 * as returned by the FastAPI services.
 */

// ── Shared enums ───────────────────────────────────────────────────────────

export type GatheringCategory = 'ore' | 'herb' | 'wood';
export type ToolCategory = 'pickaxe' | 'sickle' | 'axe';
export type GatheringSkillSlug = 'mining' | 'herbalism' | 'woodcutting';

export type GatheringSessionStatus =
  | 'active'
  | 'completed'
  | 'cancelled'
  | 'interrupted_by_battle'
  | 'inventory_full';

export type CancelReason = 'interrupted_by_battle' | 'admin_force';

// ── Player-facing node payload (returned by /client/details) ───────────────

export interface ActiveGatherer {
  session_id: number;
  character_id: number;
  character_name: string;
  character_avatar: string | null;
  started_at: string;
  complete_at: string;
}

export interface GatheringNode {
  id: number;
  node_name: string;
  category: GatheringCategory;
  result_item_id: number;
  result_item_name: string;
  result_item_image: string | null;
  result_item_rarity: string | null;
  result_quantity_per_gather: number;
  stamina_per_gather: number;
  base_seconds_per_gather: number;
  current_bank: number;
  daily_bank_max: number;
  allow_concurrent_gather: boolean;
  is_enabled: boolean;
  depleted_at: string | null;
  restore_at: string | null;
  active_sessions: ActiveGatherer[];
}

// ── Session ────────────────────────────────────────────────────────────────

export interface GatheringSession {
  session_id: number;
  node_id: number;
  character_id: number;
  started_at: string;
  complete_at: string;
  effective_seconds: number;
  effective_stamina_paid: number;
  effective_double_chance_pct: number;
  effective_speed_bonus_pct: number;
  effective_stamina_bonus_pct?: number;
  tool_inventory_item_id: number | null;
  tool_durability_at_start: number | null;
  status: GatheringSessionStatus;
  auto_post_id?: number | null;
  // Filled after finalize:
  result_quantity?: number;
  xp_awarded?: number;
}

// ── Active gathering poll payload ──────────────────────────────────────────

export interface ActiveGatheringSession {
  active: true;
  session_id: number;
  node_id: number;
  node_name: string;
  location_id: number;
  category: GatheringCategory;
  started_at: string;
  complete_at: string;
  now: string;
  remaining_seconds: number;
  result_item_id: number;
  stamina_paid: number;
  tool_inventory_item_id: number | null;
}

export interface FinishedGatheringSummary {
  session_id: number;
  status: GatheringSessionStatus;
  result_quantity: number;
  xp_gained: number;
  skill_slug: GatheringSkillSlug;
  rank_up_to: number | null;
  tool_durability_remaining: number | null;
  tool_broke: boolean;
}

export interface NoActiveGatheringResponse {
  active: false;
  last_finished_session?: FinishedGatheringSummary | null;
}

export type ActiveGatheringResponse =
  | ActiveGatheringSession
  | NoActiveGatheringResponse;

// ── Start / cancel ─────────────────────────────────────────────────────────

export interface StartGatheringRequest {
  character_id: number;
  tool_inventory_item_id: number | null;
}

export interface StartGatheringResponse {
  session_id: number;
  node_id: number;
  character_id: number;
  started_at: string;
  complete_at: string;
  effective_seconds: number;
  effective_stamina_paid: number;
  effective_double_chance_pct: number;
  effective_speed_bonus_pct: number;
  tool_inventory_item_id: number | null;
  tool_durability_at_start: number | null;
  status: GatheringSessionStatus;
  auto_post_id: number | null;
}

export interface CancelGatheringRequest {
  character_id: number;
}

export interface CancelGatheringResponse {
  session_id: number;
  status: GatheringSessionStatus;
  stamina_refunded: number;
  result_quantity: number;
  xp_gained: number;
}

// ── Tools (from inventory-service) ─────────────────────────────────────────

export interface GatheringTool {
  id: number;            // CharacterInventory row id (the player-instance id)
  item_id: number;       // Items template id
  name: string;
  image: string | null;
  item_type: 'gathering_tool';
  tool_category: ToolCategory;
  item_rarity: string;
  max_durability: number;
  current_durability: number | null;
  gather_double_chance_bonus: number;
  gather_speed_bonus_pct: number;
  gather_stamina_bonus_pct: number;
  quantity: number;
}

// ── Gathering skills (Сбор tab) ────────────────────────────────────────────

export interface GatheringRankBonuses {
  double_chance_bonus: number;
  speed_bonus_pct: number;
  stamina_bonus_pct: number;
}

/**
 * Inline preview of the next rank returned alongside `current_rank_bonuses`.
 * Mirrors `inventory-service.schemas.GatheringNextRank`.
 *
 * NOTE: Original FEAT-128 contract (section 3.4) showed `next_rank: 3` as a
 * plain integer, but the actual backend response is an object payload —
 * `next_rank_bonuses` is the dedicated bonus block, while `next_rank` carries
 * the rank metadata (number + required XP). Rendering this object directly
 * in JSX caused a "objects are not valid as a React child" crash and blanked
 * the Сбор tab (FEAT-130).
 */
export interface GatheringNextRank {
  rank_number: number;
  required_experience: number;
  double_chance_bonus: number;
  speed_bonus_pct: number;
  stamina_bonus_pct: number;
}

export interface GatheringSkill {
  skill_id: number;
  slug: GatheringSkillSlug;
  name: string;
  category: GatheringCategory;
  current_rank: number;
  experience: number;          // toward NEXT rank
  experience_total: number;     // lifetime
  next_rank: GatheringNextRank | null;
  experience_to_next: number | null;
  is_max_rank: boolean;
  current_rank_bonuses: GatheringRankBonuses;
  next_rank_bonuses: GatheringRankBonuses | null;
}

export interface GatheringSkillsResponse {
  character_id: number;
  skills: GatheringSkill[];
}

// ── Admin CRUD payloads ────────────────────────────────────────────────────

export interface GatheringNodeAdminListItem {
  id: number;
  location_id: number;
  node_name: string;
  category: GatheringCategory;
  result_item_id: number;
  result_item_name: string | null;
  result_item_image: string | null;
  result_quantity_per_gather: number;
  stamina_per_gather: number;
  daily_bank_max: number;
  current_bank: number;
  allow_concurrent_gather: boolean;
  is_enabled: boolean;
  depleted_at: string | null;
  restore_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GatheringNodeAdminCreate {
  node_name: string;
  category: GatheringCategory;
  result_item_id: number;
  result_quantity_per_gather: number;
  stamina_per_gather: number;
  daily_bank_max: number;
  allow_concurrent_gather: boolean;
  is_enabled: boolean;
}

export interface GatheringNodeAdminUpdate {
  node_name?: string;
  category?: GatheringCategory;
  result_item_id?: number;
  result_quantity_per_gather?: number;
  stamina_per_gather?: number;
  daily_bank_max?: number;
  allow_concurrent_gather?: boolean;
  is_enabled?: boolean;
}
