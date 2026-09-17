/* ── Gem Socket types ── */

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
  /** What goes into the sockets: gems (jewelry) or runes (weapon/armor/helmet/cloak) */
  insertable_type: 'gem' | 'rune';
  /** Anyone may insert (FEAT-165); false for legacy belts that still hold runes */
  can_insert: boolean;
  /** Only the matching profession extracts: jeweler → gems, enchanter → runes */
  can_extract: boolean;
  /** Chance (%) to keep the extracted gem/rune; null when extraction is not allowed */
  extract_preservation_chance: number | null;
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
}
