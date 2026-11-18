/**
 * FEAT-213 — sea routes, player side (character-service S1–S5, feature file 3.13).
 * Times are naive-UTC server strings (parse with `parseServerDate`).
 */

export type ShipStatus = 'docked' | 'sailing';
export type SeaPassKind = 'ticket' | 'sailor' | 'stowaway';

export interface SeaCaptainRef {
  id: number;
  name: string | null;
  avatar: string | null;
}

export interface SeaLocationRef {
  id: number;
  name: string | null;
}

export interface SeaZoneRef {
  id: number;
  name: string | null;
  /** The zone's region — a sea of the hidden «Моря» country. */
  sea_name: string | null;
}

export interface SeaStop {
  index: number;
  port_id: number;
  port_name: string | null;
}

/** FEAT-214: the active storm over the ship's current zone. */
export interface StormRef {
  zone_id: number;
  zone_name: string | null;
  ends_at: string;
}

/** FEAT-214: the ship's active monster raid — one or more deck battles (none yet right after the roll). */
export interface RaidState {
  monster_name: string | null;
  /** The ship holds (does not sail on) until then; null — it sails on. */
  hold_until: string | null;
  battles: { battle_id: number }[];
}

export interface ShipPublic {
  id: number;
  name: string;
  captain: SeaCaptainRef | null;
  deck_location_id: number;
  status: ShipStatus;
  is_active: boolean;
  docked_port: SeaLocationRef | null;
  next_port: SeaLocationRef | null;
  current_zone: SeaZoneRef | null;
  departs_at: string | null;
  arrives_at: string | null;
  stops: SeaStop[];
  direction: number;
  is_loop: boolean;
  server_now: string;
  /** FEAT-214 */
  storm?: StormRef | null;
  departure_postponed?: boolean;
  raid?: RaidState | null;
}

export interface SeaPass {
  id: number;
  ship_id: number;
  kind: SeaPassKind;
  status: string;
  first_trip: number;
  last_trip: number;
  from_port_id: number;
  from_name: string | null;
  to_port_id: number;
  to_name: string | null;
  fare: number;
  created_at: string;
  /** The current trip while sailing, the next trip while docked. */
  valid_now: boolean;
}

export interface SeaDestination {
  to_trip: number;
  stop_index: number;
  port_id: number;
  port_name: string | null;
  region_name: string | null;
  country_name: string | null;
  zones: number;
  fare: number;
  eta: string | null;
  seats_left: number;
  can_buy: boolean;
  reason: string | null;
}

export interface SeaSailorOffer {
  slots_left: number;
  min_chars: number;
  can_hire: boolean;
  reason: string | null;
}

export interface SeaStowawayOffer {
  can_try: boolean;
  reason: string | null;
}

export interface CaptainView {
  npc_id: number;
  ship: ShipPublic;
  balance: number;
  destinations: SeaDestination[];
  sailor: SeaSailorOffer;
  stowaway: SeaStowawayOffer;
  my_passes: SeaPass[];
}

/** FEAT-215: one caravan in the ship's hold (S5). */
export interface SeaDeckCargo {
  caravan_id: number;
  group_name: string | null;
  alight_port_name: string | null;
}

export interface DeckView {
  ship: ShipPublic;
  /** Sailing: ships in the same sea zone; docked: ships at the same pier. */
  ships_nearby: { id: number; name: string }[];
  /** FEAT-215: hidden caravan escorts are not counted. */
  passengers_count: number;
  /** FEAT-215: caravans in the hold — optional on an older backend */
  cargo?: SeaDeckCargo[];
  my_passes: SeaPass[];
  /** Minimum plain length of the sailor's deck post. */
  sailor_post_min_chars: number;
}

export interface SeaMessage {
  message: string;
}

/** 402 body of a ticket purchase. */
export interface SeaInsufficientGold {
  error: 'insufficient_gold';
  message: string;
  required: number;
  balance: number;
}

/** `data` of a `ws_type="sea"` notice. */
export interface SeaNoticeData {
  character_id?: number;
  ship_id?: number;
  event?: string;
  message?: string;
  notification_id?: number;
  silent?: boolean;
  /** FEAT-214: a deck battle with monsters — the notice leads to it. */
  battle_id?: number;
  location_id?: number;
  [key: string]: unknown;
}
