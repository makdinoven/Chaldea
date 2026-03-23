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
