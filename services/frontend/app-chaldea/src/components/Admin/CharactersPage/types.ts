// Types for Admin Character Management

// --- List view ---

export interface AdminCharacterListItem {
  id: number;
  name: string;
  level: number;
  id_race: number;
  id_class: number;
  id_subrace: number;
  user_id: number | null;
  avatar: string | null;
  currency_balance: number;
  stat_points: number;
  current_location_id: number | null;
}

export interface AdminCharacterListResponse {
  items: AdminCharacterListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminCharacterListParams {
  q?: string;
  user_id?: number | null;
  level_min?: number | null;
  level_max?: number | null;
  id_race?: number | null;
  id_class?: number | null;
  page?: number;
  page_size?: number;
}

// --- Character update ---

export interface AdminCharacterUpdate {
  level?: number;
  stat_points?: number;
  currency_balance?: number;
}

export interface AdminCharacterUpdateResponse {
  detail: string;
  character_id: number;
}

// --- Unlink ---

export interface UnlinkCharacterResponse {
  detail: string;
  character_id: number;
  previous_user_id: number;
}

// --- Attributes ---

export interface CharacterAttributes {
  // Resources
  health: number;
  max_health: number;
  current_health: number;
  mana: number;
  max_mana: number;
  current_mana: number;
  energy: number;
  max_energy: number;
  current_energy: number;
  stamina: number;
  max_stamina: number;
  current_stamina: number;
  // Base stats
  strength: number;
  agility: number;
  intelligence: number;
  endurance: number;
  charisma: number;
  luck: number;
  // Combat
  damage: number;
  dodge: number;
  critical_hit_chance: number;
  critical_damage: number;
  // Experience
  passive_experience: number;
  active_experience: number;
  // Resistances
  res_effects: number;
  res_physical: number;
  res_catting: number;
  res_crushing: number;
  res_piercing: number;
  res_magic: number;
  res_fire: number;
  res_ice: number;
  res_watering: number;
  res_electricity: number;
  res_sainting: number;
  res_wind: number;
  res_damning: number;
  // Vulnerabilities
  vul_effects: number;
  vul_physical: number;
  vul_catting: number;
  vul_crushing: number;
  vul_piercing: number;
  vul_magic: number;
  vul_fire: number;
  vul_ice: number;
  vul_watering: number;
  vul_electricity: number;
  vul_sainting: number;
  vul_wind: number;
  vul_damning: number;
}

export type AdminAttributeUpdate = Partial<CharacterAttributes>;

// --- Inventory ---

export interface ItemData {
  id: number;
  name: string;
  image: string | null;
  item_level: number;
  item_type: string;
  item_rarity: string;
  price: number;
  max_stack_size: number;
  is_unique: boolean;
  description: string | null;
  armor_subclass: string | null;
  weapon_subclass: string | null;
  primary_damage_type: string | null;
  // modifiers
  strength_modifier: number;
  agility_modifier: number;
  intelligence_modifier: number;
  endurance_modifier: number;
  health_modifier: number;
  energy_modifier: number;
  mana_modifier: number;
  stamina_modifier: number;
  charisma_modifier: number;
  luck_modifier: number;
  damage_modifier: number;
  dodge_modifier: number;
  // recovery
  health_recovery: number;
  energy_recovery: number;
  mana_recovery: number;
  stamina_recovery: number;
  fast_slot_bonus: number;
}

export interface InventoryItem {
  id: number;
  character_id: number;
  item_id: number;
  quantity: number;
  item: ItemData;
}

export interface EquipmentSlot {
  character_id: number;
  slot_type: string;
  item_id: number | null;
  is_enabled: boolean;
  item: ItemData | null;
}

export interface AddInventoryItemPayload {
  item_id: number;
  quantity: number;
}

// --- Skills ---

export interface SkillRank {
  id: number | string;
  skill_id: number | null;
  rank_number: number;
  rank_name: string | null;
  rank_description: string | null;
  rank_image: string | null;
  cost_energy: number;
  cost_mana: number;
  cooldown: number;
  level_requirement: number;
  upgrade_cost: number;
  class_limitations: string | null;
  race_limitations: string | null;
  subrace_limitations: string | null;
  left_child_id: number | string | null;
  right_child_id: number | string | null;
}

export interface CharacterSkill {
  id: number;
  character_id: number;
  skill_rank_id: number;
  skill_rank: {
    id: number;
    skill_id: number;
    rank_number: number;
    rank_name: string | null;
    rank_image: string | null;
    rank_description: string | null;
    left_child_id: number | null;
    right_child_id: number | null;
    cost_energy: number;
    cost_mana: number;
    cooldown: number;
    level_requirement: number;
    upgrade_cost: number;
    class_limitations: string | null;
    race_limitations: string | null;
    subrace_limitations: string | null;
  };
}

export interface SkillInfo {
  id: number;
  name: string;
  skill_type: string;
  description: string | null;
  skill_image: string | null;
  min_level: number;
  purchase_cost: number;
  class_limitations: string | null;
  race_limitations: string | null;
  subrace_limitations: string | null;
}

export interface FullSkillTreeResponse {
  id: number;
  name: string;
  skill_type: string;
  description: string | null;
  class_limitations: string | null;
  race_limitations: string | null;
  subrace_limitations: string | null;
  min_level: number;
  purchase_cost: number;
  skill_image: string | null;
  ranks: SkillRank[];
}

export interface AdminCharacterSkillUpdatePayload {
  skill_rank_id: number;
}

export interface AddCharacterSkillPayload {
  character_id: number;
  skill_rank_id: number;
}

// --- Catalog search ---

export interface CatalogItemsResponse {
  items: ItemData[];
  total: number;
  page: number;
  page_size: number;
}

// --- Redux state ---

export interface AdminCharacterFilters {
  userId: number | null;
  levelMin: number | null;
  levelMax: number | null;
  raceId: number | null;
  classId: number | null;
}

export interface AdminCharactersState {
  // List view
  characters: AdminCharacterListItem[];
  total: number;
  page: number;
  pageSize: number;
  search: string;
  filters: AdminCharacterFilters;
  listLoading: boolean;
  listError: string | null;

  // Detail view
  selectedCharacter: AdminCharacterListItem | null;
  attributes: CharacterAttributes | null;
  inventory: InventoryItem[];
  equipment: EquipmentSlot[];
  skills: CharacterSkill[];
  detailLoading: boolean;
  detailError: string | null;
}
