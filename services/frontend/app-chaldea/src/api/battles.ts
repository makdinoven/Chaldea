import axios from 'axios';

// --- Types ---

export interface LocationBattleParticipant {
  participant_id: number;
  character_id: number;
  character_name: string;
  level: number;
  team: number;
  is_npc: boolean;
}

export interface LocationBattleItem {
  id: number;
  status: string;
  battle_type: string;
  is_paused: boolean;
  created_at: string;
  participants: LocationBattleParticipant[];
}

export interface LocationBattlesResponse {
  battles: LocationBattleItem[];
}

// --- Spectate types ---

export interface SpectateParticipantSnapshot {
  participant_id: number;
  character_id: number;
  name: string;
  avatar: string | null;
  skills: unknown;
  attributes: Record<string, number>;
}

export interface SpectateRuntimeParticipant {
  hp: number;
  mana: number;
  stamina: number;
  energy: number;
  fast_slots: unknown;
  team: number;
}

export interface SpectateRuntimeState {
  participants: Record<number, SpectateRuntimeParticipant>;
  current_actor: number;
  next_actor: number;
  turn_number: number;
  turn_order: number[];
  total_turns: number;
  first_actor: number;
  deadline_at: string;
  is_paused?: boolean;
  paused_reason?: string | null;
}

export interface SpectateStateResponse {
  snapshot: SpectateParticipantSnapshot[];
  runtime: SpectateRuntimeState;
}

// --- Battle preview types (FEAT-151, profile Battles tab) ---

export interface BattlePreviewTurnEntry {
  /** Numeric string, e.g. "12" (see FEAT-151 §6 T2 deviations) */
  participant_id: string;
  name: string;
  is_current: boolean;
}

export interface BattlePreviewParticipant {
  /** Numeric string, e.g. "12" */
  participant_id: string;
  character_id: number | null;
  name: string;
  avatar: string | null;
  /** Numeric string, e.g. "0" — rely on `is_ally` for side logic */
  team: string;
  is_ally: boolean;
  is_alive: boolean;
  hp: number;
  max_hp: number;
  mana: number;
  max_mana: number;
}

export interface BattlePreview {
  battle_id: number;
  battle_type: string | null;
  turn_number: number;
  location_id: number | null;
  location_name: string | null;
  turn_order: BattlePreviewTurnEntry[];
  participants: BattlePreviewParticipant[];
}

// --- Join request types ---

export interface JoinRequestCreate {
  character_id: number;
  team: number;
}

export interface JoinRequestResponse {
  id: number;
  battle_id: number;
  character_id: number;
  team: number;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
}

export interface JoinRequestListItem {
  id: number;
  character_id: number;
  character_name: string;
  character_level: number;
  character_avatar: string | null;
  team: number;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
}

export interface JoinRequestListResponse {
  requests: JoinRequestListItem[];
}

// --- API calls ---

export const fetchBattlesByLocation = async (
  locationId: number,
): Promise<LocationBattleItem[]> => {
  const { data } = await axios.get<LocationBattlesResponse>(
    `/battles/by-location/${locationId}`,
  );
  return data.battles;
};

export const submitJoinRequest = async (
  battleId: number,
  characterId: number,
  team: number,
): Promise<JoinRequestResponse> => {
  const { data } = await axios.post<JoinRequestResponse>(
    `/battles/${battleId}/join-request`,
    { character_id: characterId, team } as JoinRequestCreate,
  );
  return data;
};

export const fetchJoinRequests = async (
  battleId: number,
): Promise<JoinRequestListItem[]> => {
  const { data } = await axios.get<JoinRequestListResponse>(
    `/battles/${battleId}/join-requests`,
  );
  return data.requests;
};

/**
 * Compact active-battle preview for the profile Battles tab (FEAT-151).
 * JWT is attached by the shared axios auth interceptors (axiosSetup.ts) —
 * same authed default-instance pattern as the other battle calls here.
 * 404 = battle finished/missing (expected race after `/in-battle`).
 */
export const fetchBattlePreview = async (
  battleId: number,
): Promise<BattlePreview> => {
  const { data } = await axios.get<BattlePreview>(
    `/battles/${battleId}/preview`,
  );
  return data;
};

export const fetchBattleSpectateState = async (
  battleId: number,
): Promise<SpectateStateResponse> => {
  const { data } = await axios.get<SpectateStateResponse>(
    `/battles/${battleId}/spectate`,
  );
  return data;
};

// --- Admin join request types ---

export interface AdminJoinRequestItem {
  id: number;
  battle_id: number;
  character_id: number;
  character_name: string;
  character_level: number;
  team: number;
  status: string;
  created_at: string;
  battle_type: string;
  battle_participants_count: number;
}

export interface AdminJoinRequestListResponse {
  requests: AdminJoinRequestItem[];
  total: number;
  page: number;
  per_page: number;
}

export interface AdminJoinRequestActionResponse {
  ok: boolean;
  request_id: number;
  message: string;
}

// --- Admin join request API calls ---

export const fetchAdminJoinRequests = async (
  status?: string,
  page?: number,
  perPage?: number,
): Promise<AdminJoinRequestListResponse> => {
  const params: Record<string, string | number> = {};
  if (status) params.status = status;
  if (page) params.page = page;
  if (perPage) params.per_page = perPage;
  const { data } = await axios.get<AdminJoinRequestListResponse>(
    '/battles/admin/join-requests',
    { params },
  );
  return data;
};

export const approveJoinRequest = async (
  requestId: number,
): Promise<AdminJoinRequestActionResponse> => {
  const { data } = await axios.post<AdminJoinRequestActionResponse>(
    `/battles/admin/join-requests/${requestId}/approve`,
  );
  return data;
};

export const rejectJoinRequest = async (
  requestId: number,
): Promise<AdminJoinRequestActionResponse> => {
  const { data } = await axios.post<AdminJoinRequestActionResponse>(
    `/battles/admin/join-requests/${requestId}/reject`,
  );
  return data;
};

// Forced-PvP admin approval (FEAT-145 §7)
export interface PvpRequest {
  id: number;
  attacker_character_id: number;
  victim_character_id: number;
  attacker_name?: string;
  victim_name?: string;
  location_id: number;
  battle_type?: string;
}

export const listPvpRequests = async (): Promise<PvpRequest[]> => {
  const { data } = await axios.get<PvpRequest[]>('/battles/admin/pvp-requests');
  return data;
};

export const approvePvpRequest = async (requestId: number): Promise<{ battle_id: number }> => {
  const { data } = await axios.post(`/battles/admin/pvp-requests/${requestId}/approve`);
  return data;
};

export const rejectPvpRequest = async (requestId: number): Promise<{ detail: string }> => {
  const { data } = await axios.post(`/battles/admin/pvp-requests/${requestId}/reject`);
  return data;
};
