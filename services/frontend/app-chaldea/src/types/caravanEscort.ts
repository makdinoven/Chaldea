/**
 * FEAT-212 — player caravan escorts (character-service C1–C6, feature file 3.12 + Task 2 notes).
 */

/** C1 item: a caravan preparing at the caravaneer's gate. Never the seat counts (PM decision 1). */
export interface CaravaneerCaravan {
  id: number;
  group_code: string;
  group_name: string | null;
  departs_in_sec: number | null;
  /** «есть места» / «мест нет» */
  has_seats: boolean;
  /** Guaranteed pay per head when every seat is taken. */
  pay_estimate: number;
  can_hire: boolean;
  /** Russian refusal text when `can_hire` is false. */
  reason: string | null;
}

/** C1 response. */
export interface CaravaneerView {
  npc_id: number;
  location_id: number;
  my_escort_caravan_id: number | null;
  seats_enabled: boolean;
  caravans: CaravaneerCaravan[];
}

export interface EscortHireRequest {
  character_id: number;
  npc_id: number;
}

export interface EscortRoutePoint {
  index: number;
  location_id: number;
  name: string | null;
}

export interface EscortMate {
  character_id: number;
  name: string | null;
  avatar: string | null;
}

export type EscortState = 'preparing' | 'on_road' | 'held' | 'under_attack' | 'arrived';

export type EscortRaidStatus = 'starting' | 'fighting' | 'won' | 'repelled' | 'aborted' | 'expired';

/** C3 body (also the C2 201 body). */
export interface EscortJob {
  caravan_id: number;
  group_code: string;
  group_name: string | null;
  from_region_name: string | null;
  to_region_name: string | null;
  route: EscortRoutePoint[];
  route_index: number;
  current_location_id: number | null;
  current_location_name: string | null;
  state: EscortState | string;
  next_move_in_sec: number | null;
  seats_total: number;
  escorts: EscortMate[];
  /** Per head now (fee + bonus when the raid was repelled). */
  pay_estimate: number;
  raid_status: EscortRaidStatus | string | null;
  /** The raid battle when this escort fights in it. */
  battle_id: number | null;
  joined_at: string;
}

export interface EscortJobWrap {
  escort: EscortJob | null;
}

export interface EscortLeaveResponse {
  left: boolean;
  location_id: number | null;
}

export interface EscortMessage {
  id: number;
  character_id: number;
  name: string | null;
  avatar: string | null;
  body: string;
  created_at: string;
}

export interface EscortMessages {
  caravan_id: number;
  messages: EscortMessage[];
}
