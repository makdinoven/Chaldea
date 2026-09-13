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
  /**
   * FEAT-159 (Phase B): gates added while editing that are still awaiting a
   * moderator's decision, `{action_type: count}` — the count is the number of
   * targets, exactly like `gates` above. Present only while a request is
   * `pending`; approved gates move into `gates`, rejected/expired ones vanish.
   *
   * They grant NOTHING yet. The UI must never present them as usable rights —
   * they are shown as «на рассмотрении» and they still cost their symbols in
   * the edit counter, because the server charges them toward the post's budget
   * (`crud.edit_post`, section 3.6 rule 2).
   */
  pending_gates?: Record<string, number>;
  /**
   * FEAT-159: set when the post's text was edited after publication.
   * `null` / absent for an untouched post. ISO timestamp from the server.
   */
  edited_at?: string | null;
  /**
   * FEAT-159: the edit was made by an administrator, not by the author.
   * Derived server-side; degrades to `false` when the author's profile could
   * not be resolved, so it never falsely accuses an admin.
   */
  edited_by_admin?: boolean;
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
   * FEAT-153 (§3.8): the ids were already on the wire (locations-service
   * `crud.py` / `schemas.py`) but only `country_id` was declared here. The
   * breadcrumb needs `region_id` to build the region link; `district_id` is
   * declared for completeness and is currently unused (no district route).
   */
  country_id?: number | null;
  region_id?: number | null;
  district_id?: number | null;
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
