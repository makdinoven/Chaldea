/**
 * FEAT-213 — sea routes, admin side.
 *
 * Ships: character-service `/characters/admin/sea/*` (A1–A7).
 * Ports / sea zones: locations-service `/locations/admin/sea-ports` (L5) and `/locations/admin/sea-zones` (L8).
 * Datetimes are naive UTC strings (project convention, parse with `utils/serverDate`).
 */

export interface SeaRef {
  id: number;
  name: string | null;
}

/** Leg problem codes of the legs preview (A5) and the `legs` of a ship row (A1). */
export type SeaLegProblem = 'no_zone' | 'no_path' | 'bad_override' | 'same_port' | 'not_port';

export interface SeaLeg {
  /** Index of the stop the leg starts from (the loop's closing leg = last index). */
  index: number;
  from: SeaRef | null;
  to: SeaRef | null;
  zones: SeaRef[];
  minutes_per_zone_hint: number | null;
  minutes: number | null;
  /** The manual zone path was used */
  override: boolean;
  ok: boolean;
  problem: SeaLegProblem | null;
  /** Russian text of `problem` */
  problem_text: string | null;
}

export interface SeaShipStopAdmin {
  index: number;
  port_id: number;
  port_name: string | null;
  path_override: number[] | null;
}

export interface SeaCaptainAdmin {
  id: number;
  name: string | null;
  avatar: string | null;
  location_id: number | null;
  location_name: string | null;
}

export interface SeaZoneRef {
  id: number;
  name: string | null;
  /** The zone's region name = the sea */
  sea_name: string | null;
}

/** `sea_ships.blocked_reason` */
export type SeaBlockedReason = 'no_path' | 'no_valid_stop' | 'no_deck';

export type SeaShipStatus = 'docked' | 'sailing';

/** A1 row / A2–A3 response. */
export interface SeaShipAdmin {
  id: number;
  name: string;
  captain_npc_id: number | null;
  captain: SeaCaptainAdmin | null;
  /** Russian «капитана нет» reason (ticket sales closed) */
  captain_problem: string | null;
  deck: SeaRef;
  capacity: number;
  crew_slots: number;
  boarding_minutes: number;
  zone_minutes: number;
  fare_base: number;
  fare_per_zone: number;
  is_loop: boolean;
  is_active: boolean;
  status: SeaShipStatus;
  stop_index: number;
  next_stop_index: number | null;
  direction: number;
  trip_no: number;
  docked_port: SeaRef | null;
  next_port: SeaRef | null;
  current_zone: SeaZoneRef | null;
  leg_path: number[] | null;
  leg_pos: number;
  departs_at: string | null;
  next_zone_at: string | null;
  arrives_at: string | null;
  blocked_reason: SeaBlockedReason | string | null;
  stops: SeaShipStopAdmin[];
  legs: SeaLeg[];
  passengers_count: number;
  active_passes: number;
  server_now: string;
  created_at: string;
  updated_at: string;
}

export interface SeaStopInput {
  port_location_id: number;
  /** Manual zone ids of the leg stops[i] → stops[i + 1] (loop: last → first); null = shortest path */
  path_override: number[] | null;
}

export interface SeaShipCreate {
  name: string;
  captain_npc_id: number | null;
  deck_location_id: number;
  capacity: number;
  crew_slots: number;
  boarding_minutes: number;
  zone_minutes: number;
  fare_base: number;
  fare_per_zone: number;
  is_loop: boolean;
  is_active: boolean;
  stops: SeaStopInput[];
}

/** A3: every field optional; `captain_npc_id: null` unbinds the Captain; the deck is immutable. */
export type SeaShipUpdate = Partial<Omit<SeaShipCreate, 'deck_location_id'>>;

export interface SeaLegsPreviewRequest {
  stops: SeaStopInput[];
  is_loop: boolean;
  zone_minutes?: number | null;
}

export interface SeaDeckCandidate {
  id: number;
  name: string | null;
  region_name: string | null;
  country_name: string | null;
}

export interface SeaCaptainCandidate {
  id: number;
  name: string | null;
  avatar: string | null;
  location_name: string | null;
}

export interface SeaCandidates {
  decks: SeaDeckCandidate[];
  captains: SeaCaptainCandidate[];
}

export interface SeaSettings {
  sailor_post_min_chars: number;
  stowaway_base_pct: number;
  stowaway_wanted_points: number;
  path_max_zones: number;
}

/** L5 row */
export interface SeaPort {
  id: number;
  name: string;
  region_id: number | null;
  region_name: string | null;
  country_id: number | null;
  country_name: string | null;
  area_id: number | null;
  port_sea_zone_id: number | null;
  port_sea_zone_name: string | null;
}

/** L8 row */
export interface SeaZone {
  id: number;
  name: string;
  region_id: number | null;
  /** The sea */
  region_name: string | null;
  country_name: string | null;
  neighbor_ids: number[];
}
