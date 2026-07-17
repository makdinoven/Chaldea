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
  // FEAT-145 item 7: intent gates declared in this post, {action_type: count}.
  gates?: Record<string, number>;
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
  /**
   * FEAT-152 breadcrumb (A1): resolved hierarchy names from locations-service.
   * All optional/nullable — the UI hides missing segments.
   */
  country_id?: number | null;
  country_name?: string | null;
  region_name?: string | null;
  district_name?: string | null;
  image_url: string | null;
  marker_type: string;
  no_quick_move?: boolean;
  is_favorited?: boolean;
  neighbors: NeighborLocation[];
  players: Player[];
  posts: Post[];
  loot: LocationLootItem[];
  npcs: NpcInLocation[];
  /**
   * FEAT-128 resource gathering nodes attached to this location. The field is
   * optional because the backend extension lands in task #11; until then the
   * key may simply be absent and the frontend treats it as an empty list.
   */
  gathering_nodes?: import('../../../types/gathering').GatheringNode[];
}

export type MarkerType = 'safe' | 'dangerous' | 'dungeon' | 'farm';
