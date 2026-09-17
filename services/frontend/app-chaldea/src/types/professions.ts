/* ── Profession & Crafting types ── */

import type { ResourceSubcategory, WhetstoneGroup } from "../constants/professions";

// --- Profession ---

export interface ProfessionRank {
  id: number;
  rank_number: number;
  name: string;
  description: string | null;
  required_experience: number;
  icon: string | null;
}

export interface Profession {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  icon: string | null;
  sort_order: number;
  is_active: boolean;
  ranks: ProfessionRank[];
}

export interface CharacterProfession {
  character_id: number;
  profession: Profession;
  current_rank: number;
  rank_name: string;
  experience: number;
  chosen_at: string;
}

// --- Profession requests ---

export interface ChooseProfessionRequest {
  profession_id: number;
}

export interface ChangeProfessionRequest {
  profession_id: number;
}

export interface ChooseProfessionResponse {
  character_id: number;
  profession_id: number;
  current_rank: number;
  experience: number;
  auto_learned_recipes: { id: number; name: string }[];
}

export interface ChangeProfessionResponse {
  character_id: number;
  old_profession: string;
  new_profession: string;
  current_rank: number;
  experience: number;
  message: string;
  auto_learned_recipes: { id: number; name: string }[];
}

// --- Recipe ---

export interface RecipeIngredient {
  item_id: number;
  item_name: string;
  item_image: string | null;
  quantity: number;
  available: number;
}

export interface RecipeResultItem {
  id: number;
  name: string;
  image: string | null;
  item_type: string;
  item_rarity: string;
}

export interface Recipe {
  id: number;
  name: string;
  description: string | null;
  profession_id: number;
  profession_name: string;
  required_rank: number;
  result_item: RecipeResultItem;
  result_quantity: number;
  rarity: string;
  icon: string | null;
  xp_reward: number | null;
  ingredients: RecipeIngredient[];
  can_craft: boolean;
  /** Always "learned" since FEAT-165 (kept for compatibility). */
  source: "learned";
}

// --- Crafting ---

export interface CraftRequest {
  recipe_id: number;
}

export interface CraftedItem {
  item_id: number;
  name: string;
  image: string | null;
  quantity: number;
}

export interface ConsumedMaterial {
  item_id: number;
  name: string;
  quantity: number;
}

export interface CraftResult {
  success: boolean;
  crafted_item: CraftedItem;
  consumed_materials: ConsumedMaterial[];
  xp_earned: number;
  new_total_xp: number;
  rank_up: boolean;
  new_rank_name: string | null;
  auto_learned_recipes: { id: number; name: string }[];
}

// --- Learn recipe ---

export interface LearnRecipeRequest {
  recipe_id: number;
}

export interface LearnRecipeResponse {
  message: string;
  recipe_id: number;
  recipe_name: string;
}

// --- Admin Recipe (flat structure from RecipeAdminOut) ---

export interface AdminRecipeIngredient {
  item_id: number;
  item_name: string;
  item_image: string | null;
  quantity: number;
  available: number;
}

export interface AdminRecipe {
  id: number;
  name: string;
  description: string | null;
  profession_id: number;
  profession_name: string;
  required_rank: number;
  result_item_id: number;
  result_item_name: string;
  result_quantity: number;
  rarity: string;
  icon: string | null;
  is_active: boolean;
  auto_learn_rank: number | null;
  xp_reward: number | null;
  ingredients: AdminRecipeIngredient[];
  recipe_item_id: number | null;
  recipe_item_name: string | null;
}

// --- Admin ---

export interface AdminSetRankRequest {
  rank_number: number;
}

export interface ProfessionCreateRequest {
  name: string;
  slug: string;
  description?: string | null;
  icon?: string | null;
  sort_order?: number;
}

export interface ProfessionUpdateRequest {
  name?: string;
  slug?: string;
  description?: string | null;
  icon?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

export interface ProfessionRankCreateRequest {
  rank_number: number;
  name: string;
  description?: string | null;
  required_experience?: number;
  icon?: string | null;
}

export interface ProfessionRankUpdateRequest {
  rank_number?: number;
  name?: string;
  description?: string | null;
  required_experience?: number;
  icon?: string | null;
}

export interface RecipeIngredientInput {
  item_id: number;
  quantity: number;
}

export interface RecipeCreateRequest {
  name: string;
  description?: string | null;
  profession_id: number;
  required_rank?: number;
  result_item_id: number;
  result_quantity?: number;
  icon?: string | null;
  auto_learn_rank?: number | null;
  xp_reward?: number | null;
  ingredients: RecipeIngredientInput[];
}

export interface RecipeUpdateRequest {
  name?: string;
  description?: string | null;
  profession_id?: number;
  required_rank?: number;
  result_item_id?: number;
  result_quantity?: number;
  icon?: string | null;
  auto_learn_rank?: number | null;
  xp_reward?: number | null;
  is_active?: boolean;
  ingredients?: RecipeIngredientInput[];
}

export interface RecipesPaginatedResponse {
  items: AdminRecipe[];
  total: number;
  page: number;
  per_page: number;
}

// --- Repair ---

export interface RepairItemRequest {
  item_row_id: number;
  repair_kit_item_id: number;
  source?: string;
}
export interface RepairItemResult {
  success: boolean;
  item_name: string;
  old_durability: number;
  new_durability: number;
  max_durability: number;
  repair_kit_used: string;
}

// --- Item Detail ---

export interface ItemDetailSocketInfo {
  slot_index: number;
  item_id: number | null;
  name: string | null;
  image: string | null;
  item_type: string | null;
  modifiers: Record<string, number>;
}

export interface ItemDetailResponse {
  id: number;
  name: string;
  image: string | null;
  description: string | null;
  item_type: string;
  item_rarity: string;
  item_level: number;
  price: number;
  quantity: number;
  is_identified: boolean;
  max_durability: number;
  current_durability: number | null;
  enhancement_points_spent: number;
  enhancement_bonuses: Record<string, number>;
  socket_count: number;
  socketed_items: ItemDetailSocketInfo[];
  base_modifiers: Record<string, number>;
  total_modifiers: Record<string, number>;
}

// --- Sharpening ---

export interface SharpenStatInfo {
  field: string;
  name: string;
  base_value: number;
  sharpened_count: number;
  max: number;
  is_existing: boolean;
  point_cost: number;
  can_sharpen: boolean;
}

export interface SharpenWhetstoneInfo {
  inventory_item_id: number;
  name: string;
  quantity: number;
  success_chance: number;
  whetstone_group: WhetstoneGroup;
}

export interface SharpenInfoResponse {
  item_name: string;
  item_type: string;
  sharpen_group: WhetstoneGroup;
  points_spent: number;
  points_remaining: number;
  stats: SharpenStatInfo[];
  whetstones: SharpenWhetstoneInfo[];
}

export interface SharpenRequest {
  inventory_item_id: number;
  whetstone_item_id: number;
  stat_field: string;
  source?: string; // "inventory" | "equipment"
}

export interface SharpenResult {
  success: boolean;
  item_name: string;
  stat_field: string;
  stat_display_name: string;
  old_value: number;
  new_value: number;
  points_spent: number;
  points_remaining: number;
  point_cost: number;
  whetstone_consumed: boolean;
}

// --- Refining (FEAT-165) ---

export interface RefineResultItem {
  id: number;
  name: string;
  image: string | null;
  item_rarity: string;
}

export interface AutoLearnedRecipe {
  id: number;
  name: string;
}

/** GET /inventory/crafting/refining-rules */
export interface RefiningRule {
  profession_id: number;
  profession_slug: string;
  profession_name: string;
  source_subcategory: ResourceSubcategory;
  result_subcategory: ResourceSubcategory;
}

export interface RefineSource {
  source_item_id: number;
  name: string;
  image: string | null;
  item_rarity: string;
  owned_quantity: number;
  source_quantity: number;
  max_batches: number;
  result_item: RefineResultItem;
  result_quantity: number;
  xp_per_batch: number;
}

/** GET /inventory/crafting/{cid}/refine-info */
export interface RefineInfo {
  can_refine: boolean;
  profession_slug: string | null;
  source_subcategory: ResourceSubcategory | null;
  result_subcategory: ResourceSubcategory | null;
  double_chance_pct: number | null;
  sources: RefineSource[];
}

export interface RefineRequest {
  source_item_id: number;
  quantity: number;
}

export interface RefineResult {
  success: boolean;
  source_item_id: number;
  consumed_quantity: number;
  leftover_quantity: number;
  batches: number;
  doubled_batches: number;
  result_item: RefineResultItem;
  result_quantity: number;
  xp_earned: number;
  new_total_xp: number;
  rank_up: boolean;
  new_rank_name: string | null;
  auto_learned_recipes: AutoLearnedRecipe[];
}

// --- Admin: item conversions (FEAT-165) ---

export interface ItemConversionInput {
  profession_id: number;
  source_quantity: number;
  result_item_id: number;
  result_quantity: number;
}

export interface ItemConversionsPayload {
  conversions: ItemConversionInput[];
}

export interface ItemConversion {
  id: number;
  profession_id: number;
  profession_name: string;
  source_quantity: number;
  result_item: RefineResultItem;
  result_quantity: number;
}

export interface ItemConversionsResponse {
  source_item_id: number;
  conversions: ItemConversion[];
}
