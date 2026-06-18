import axios from 'axios';

// --- Types (mirror battle-service party schemas) ---

export type PartyBattleType = 'pvp_training' | 'pvp_death';
export type PartyMemberStatus = 'invited' | 'accepted' | 'declined';
export type PartyStatus = 'forming' | 'started' | 'cancelled' | 'expired';

export interface PartyMember {
  character_id: number;
  character_name: string;
  character_level: number;
  character_avatar: string | null;
  team: number;
  status: PartyMemberStatus;
  is_leader: boolean;
}

export interface PartyState {
  id: number;
  leader_character_id: number;
  location_id: number;
  battle_type: PartyBattleType;
  status: PartyStatus;
  battle_id: number | null;
  expires_at: string;
  members: PartyMember[];
}

export interface IncomingPartyInvite {
  party_id: number;
  leader_character_id: number;
  leader_name: string;
  battle_type: PartyBattleType;
  team: number;
  member_count: number;
  created_at: string;
  expires_at: string;
}

export interface PartyStartResult {
  ok: boolean;
  battle_id: number;
  battle_url: string;
}

export interface PartyActionResult {
  ok: boolean;
  party_id: number;
  message: string;
}

// --- API calls ---

export const createParty = async (
  leaderCharacterId: number,
  battleType: PartyBattleType,
): Promise<PartyState> => {
  const { data } = await axios.post<PartyState>('/battles/pvp/party', {
    leader_character_id: leaderCharacterId,
    battle_type: battleType,
  });
  return data;
};

export const getParty = async (partyId: number): Promise<PartyState> => {
  const { data } = await axios.get<PartyState>(`/battles/pvp/party/${partyId}`);
  return data;
};

export const inviteToParty = async (
  partyId: number,
  characterId: number,
  team: number,
): Promise<PartyState> => {
  const { data } = await axios.post<PartyState>(
    `/battles/pvp/party/${partyId}/invite`,
    { character_id: characterId, team },
  );
  return data;
};

export const respondToParty = async (
  partyId: number,
  characterId: number,
  action: 'accept' | 'decline',
): Promise<PartyState> => {
  const { data } = await axios.post<PartyState>(
    `/battles/pvp/party/${partyId}/respond`,
    { character_id: characterId, action },
  );
  return data;
};

export const leaveParty = async (
  partyId: number,
  characterId: number,
): Promise<PartyActionResult> => {
  const { data } = await axios.post<PartyActionResult>(
    `/battles/pvp/party/${partyId}/leave`,
    null,
    { params: { character_id: characterId } },
  );
  return data;
};

export const startParty = async (partyId: number): Promise<PartyStartResult> => {
  const { data } = await axios.post<PartyStartResult>(
    `/battles/pvp/party/${partyId}/start`,
  );
  return data;
};

export const fetchIncomingPartyInvites = async (): Promise<IncomingPartyInvite[]> => {
  const { data } = await axios.get<{ invites: IncomingPartyInvite[] }>(
    '/battles/pvp/parties/incoming',
  );
  return data.invites;
};
