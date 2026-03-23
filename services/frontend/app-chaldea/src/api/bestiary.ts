import axios from 'axios';

// --- Types ---

export interface BestiarySkillEntry {
  skill_rank_id: number;
  skill_name: string | null;
}

export interface BestiaryLootEntry {
  item_id: number;
  item_name: string | null;
  drop_chance: number;
  min_quantity: number;
  max_quantity: number;
}

export interface BestiarySpawnEntry {
  location_id: number;
  location_name: string | null;
}

export interface BestiaryEntry {
  id: number;
  name: string;
  tier: 'normal' | 'elite' | 'boss';
  level: number;
  avatar: string | null;
  killed: boolean;
  description: string | null;
  base_attributes: Record<string, number> | null;
  skills: BestiarySkillEntry[] | null;
  loot_entries: BestiaryLootEntry[] | null;
  spawn_locations: BestiarySpawnEntry[] | null;
}

export interface BestiaryResponse {
  entries: BestiaryEntry[];
  total: number;
  killed_count: number;
}

// --- API calls ---

export const fetchBestiaryApi = async (
  characterId?: number,
): Promise<BestiaryResponse> => {
  const params: Record<string, number> = {};
  if (characterId != null) {
    params.character_id = characterId;
  }
  const { data } = await axios.get<BestiaryResponse>('/characters/bestiary', {
    params,
  });
  return data;
};
