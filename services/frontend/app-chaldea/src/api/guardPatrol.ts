import axios from 'axios';

/**
 * FEAT-204 admin «Патруль стражника» API (character-service `patrol_api.py`).
 * Auth header comes from axiosSetup. GET needs `npcs:read`, PUT / step need `npcs:update`.
 */
const base = (npcId: number) => `/characters/admin/npcs/${npcId}/patrol`;

export type PatrolMode = 'post' | 'route' | 'zone';
export type PatrolRouteStyle = 'loop' | 'pingpong';
export type PatrolZoneKind = 'district' | 'locations';
export type PatrolBlockedReason = 'not_guard' | 'dead' | 'ko' | 'battle' | 'encounter';
export type PatrolStepOutcome = 'moved' | 'stayed' | 'blocked' | 'not_patrolling';

/** Backend limits mirrored for client-side validation (`patrol_core`). */
export const PATROL_INTERVAL_MIN = 5;
export const PATROL_INTERVAL_MAX = 1440;
export const PATROL_JITTER_MIN = 0;
export const PATROL_JITTER_MAX = 50;
export const PATROL_ROUTE_MIN_POINTS = 2;
export const PATROL_ROUTE_MAX_POINTS = 30;
export const PATROL_ZONE_MIN_LOCATIONS = 2;
export const PATROL_ZONE_MAX_LOCATIONS = 100;
export const PATROL_DEFAULT_INTERVAL = 20;
export const PATROL_DEFAULT_JITTER = 25;

export interface PatrolPoint {
  location_id: number;
  name: string | null;
}

export interface PatrolOut {
  npc_id: number;
  npc_role: string | null;
  mode: PatrolMode;
  route_style: PatrolRouteStyle;
  route: PatrolPoint[];
  zone_kind: PatrolZoneKind;
  zone_district_id: number | null;
  zone_district_name: string | null;
  zone_locations: PatrolPoint[];
  interval_min: number;
  jitter_pct: number;
  current_location_id: number | null;
  current_location_name: string | null;
  /** naive-UTC server timestamps */
  next_move_at: string | null;
  last_moved_at: string | null;
  blocked_reason: PatrolBlockedReason | null;
  patrols_enabled: boolean;
  warnings: string[];
}

export interface PatrolIn {
  mode: PatrolMode;
  route_style?: PatrolRouteStyle;
  route_location_ids?: number[];
  zone_kind?: PatrolZoneKind;
  zone_district_id?: number | null;
  zone_location_ids?: number[];
  interval_min?: number;
  jitter_pct?: number;
}

export interface PatrolStepOut {
  outcome: PatrolStepOutcome;
  blocked_reason: PatrolBlockedReason | null;
  from_location_id: number | null;
  to_location_id: number | null;
  checked: number;
  encounters: number;
  slipped: number;
  patrol: PatrolOut;
}

export const fetchGuardPatrol = async (npcId: number): Promise<PatrolOut> =>
  (await axios.get<PatrolOut>(base(npcId))).data;

export const saveGuardPatrol = async (npcId: number, body: PatrolIn): Promise<PatrolOut> =>
  (await axios.put<PatrolOut>(base(npcId), body)).data;

export const stepGuardPatrol = async (npcId: number): Promise<PatrolStepOut> =>
  (await axios.post<PatrolStepOut>(`${base(npcId)}/step`)).data;
