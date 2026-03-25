export interface Player {
  id: number;
  user_id: number;
  name: string;
  avatar: string | null;
  level: number;
  class_name: string | null;
  race_name: string | null;
  character_title?: string;
  character_title_rarity?: string;
}

export interface NeighborLocation {
  id: number;
  name: string;
  energy_cost: number;
  image_url: string | null;
  recommended_level: number;
}

export interface Post {
  post_id: number;
  character_id: number;
  character_photo: string | null;
  character_title: string | null;
  character_title_rarity: string | null;
  character_name: string;
  character_level: number | null;
  user_id: number | null;
  user_nickname: string;
  content: string;
  length: number;
  created_at: string;
  likes_count: number;
  liked_by: number[];
}

export interface LocationLootItem {
  id: number;
  location_id: number;
  item_id: number;
  quantity: number;
  dropped_by_character_id: number | null;
  dropped_at: string;
  item_name: string | null;
  item_image: string | null;
  item_rarity: string | null;
  item_type: string | null;
}

export interface NpcInLocation {
  id: number;
  name: string;
  avatar: string | null;
  level: number;
  class_name: string | null;
  race_name: string | null;
  npc_role: string | null;
}

export interface LocationData {
  id: number;
  name: string;
  description: string;
  type: string;
  recommended_level: number;
  image_url: string | null;
  marker_type: string;
  is_favorited?: boolean;
  neighbors: NeighborLocation[];
  players: Player[];
  posts: Post[];
  loot: LocationLootItem[];
  npcs: NpcInLocation[];
}

export type MarkerType = 'safe' | 'dangerous' | 'dungeon' | 'farm';
