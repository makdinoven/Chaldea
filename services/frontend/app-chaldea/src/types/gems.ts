/* ── Gem Socket & Smelting types ── */

// --- Socket system ---

export interface SocketGemInfo {
  slot_index: number;
  gem_item_id: number | null;
  gem_name: string | null;
  gem_image: string | null;
  gem_modifiers: Record<string, number>;
}

export interface AvailableGem {
  inventory_item_id: number;
  item_id: number;
  name: string;
  image: string | null;
  quantity: number;
  modifiers: Record<string, number>;
}

export interface SocketInfoResponse {
  item_name: string;
  item_type: string;
  socket_count: number;
  slots: SocketGemInfo[];
  available_gems: AvailableGem[];
}

export interface InsertGemRequest {
  item_row_id: number;
  gem_inventory_id: number;
  slot_index: number;
  source?: string;
}

export interface InsertGemResult {
  success: boolean;
  item_name: string;
  gem_name: string;
  slot_index: number;
  xp_earned: number;
  new_total_xp: number;
  rank_up: boolean;
  new_rank_name: string | null;
}

export interface ExtractGemRequest {
  item_row_id: number;
  slot_index: number;
  source?: string;
}

export interface ExtractGemResult {
  success: boolean;
  item_name: string;
  gem_name: string;
  gem_preserved: boolean;
  preservation_chance: number;
  slot_index: number;
  xp_earned: number;
  new_total_xp: number;
  rank_up: boolean;
  new_rank_name: string | null;
}

// --- Smelting ---

export interface SmeltIngredientInfo {
  item_id: number;
  name: string;
  image: string | null;
  quantity: number;
}

export interface SmeltInfoResponse {
  item_name: string;
  item_type: string;
  has_gems: boolean;
  gem_count: number;
  has_recipe: boolean;
  ingredients: SmeltIngredientInfo[];
}

export interface SmeltRequest {
  inventory_item_id: number;
}

export interface SmeltResult {
  success: boolean;
  item_name: string;
  gems_destroyed: number;
  materials_returned: SmeltIngredientInfo[];
  xp_earned: number;
  new_total_xp: number;
  rank_up: boolean;
  new_rank_name: string | null;
}
