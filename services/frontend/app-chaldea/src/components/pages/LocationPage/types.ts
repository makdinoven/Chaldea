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

/**
 * FEAT-160: one entry of a post's edit history.
 *
 * Mirrors the backend `PostVersionEntry` (locations-service `app/schemas.py`),
 * verified field-for-field against the live `/openapi.json`. Pydantic v1 does
 * not mark `Optional` fields nullable in the schema, so nullability here comes
 * from the documented contract (section 3.6), not from the generated types.
 *
 * The server has **already resolved** the off-by-one described in 3.4: this
 * entry's `author_user_id` / `created_at` describe the edit that *produced*
 * this text, not the one that destroyed it. The client never re-derives that.
 */
export interface PostVersionEntry {
  /** 1-based, ascending. The current text is the highest. */
  version_no: number;
  /** Raw stored HTML of this version. Rendered as TEXT in the history modal. */
  content: string;
  /**
   * When this text became the post's text. `null` is meaningful: the post was
   * edited before the feature shipped, so the moment is unrecoverable.
   */
  created_at: string | null;
  /** Who wrote it. `null` for the post's own untouched original. */
  author_user_id: number | null;
  /** `null` when the account could not be resolved (deleted, lookup failed). */
  author_username: string | null;
  /** This entry is `posts.content` as it stands right now. */
  is_current: boolean;
}

/** FEAT-160: response of `GET /locations/posts/{id}/versions`. */
export interface PostVersionHistory {
  post_id: number;
  /** `null` for a post that was never edited. */
  post_edited_at: string | null;
  /**
   * `false` — the post was edited before the history existed, so the earliest
   * surviving entry is NOT the original wording. The modal must say so instead
   * of implying the post was untouched.
   */
  original_available: boolean;
  /** Ascending by `version_no`; the current text is last. */
  versions: PostVersionEntry[];
}
