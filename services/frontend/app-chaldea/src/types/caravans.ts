/**
 * FEAT-211 — physical caravans, raids and the fence (feature file 3.13).
 *
 * Player-side shapes only. The location block deliberately has NO origin,
 * destination, route or cargo value — players learn the roads themselves.
 */

/** State of a caravan standing in the character's location (A1). */
export type CaravanHereState = 'on_road' | 'held' | 'under_attack' | 'raided';

export interface CaravanHere {
  id: number;
  group_code: string;
  group_name: string;
  guard_count: number;
  state: CaravanHereState;
  /** Seconds until the caravan moves on; null when unknown (held / in a fight). */
  departs_in_sec: number | null;
  can_attack: boolean;
  /** Why the attack is not possible right now (Russian, from the server). */
  reason: string | null;
}

/** `GET /characters/caravans/here` (A1). */
export interface CaravansHereResponse {
  location_id: number;
  caravans: CaravanHere[];
}

/** `POST /characters/caravans/{id}/raid` body (A2). */
export interface CaravanRaidRequest {
  character_id: number;
  group: boolean;
}

/** `POST /characters/caravans/{id}/raid` 201 response (A2). */
export interface CaravanRaidResponse {
  raid_id: number;
  battle_id: number;
}

/** One sellable stack at a fence (A13). */
export interface FenceOffer {
  item_id: number;
  item_name: string;
  item_image: string | null;
  group_code: string;
  group_name: string;
  unit_price: number;
  max_quantity: number;
}

/** `POST /locations/npcs/{id}/fence/sell` body (A14). */
export interface FenceSellRequest {
  character_id: number;
  item_id: number;
  quantity: number;
}

/** Same shape as the merchant `ShopTransactionResponse` (locations-service). */
export interface FenceSellResponse {
  success: boolean;
  message: string;
  new_balance: number | null;
  item_name: string | null;
  quantity: number;
  total_price: number;
}
