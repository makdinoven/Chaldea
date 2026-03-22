import axios from 'axios';

// --- Types ---

export interface PvpInvitation {
  invitation_id: number;
  initiator_character_id: number;
  initiator_name: string;
  initiator_avatar: string | null;
  initiator_level: number;
  battle_type: 'pvp_training' | 'pvp_death';
  created_at: string;
  expires_at: string;
}

export interface OutgoingInvitation {
  invitation_id: number;
  target_character_id: number;
  target_name: string;
  battle_type: 'pvp_training' | 'pvp_death';
  status: string;
  created_at: string;
}

export interface PvpInvitationResponse {
  incoming: PvpInvitation[];
  outgoing: OutgoingInvitation[];
}

export interface SendInvitationResult {
  invitation_id: number;
  initiator_character_id: number;
  target_character_id: number;
  battle_type: 'pvp_training' | 'pvp_death';
  status: string;
  expires_at: string;
}

export interface RespondResult {
  invitation_id: number;
  status: 'accepted' | 'declined';
  battle_id?: number;
  battle_url?: string;
}

export interface CancelResult {
  invitation_id: number;
  status: 'cancelled';
}

export interface AttackResult {
  battle_id: number;
  battle_url: string;
  attacker_character_id: number;
  victim_character_id: number;
}

// --- API calls ---

export const sendPvpInvitation = async (
  initiatorCharacterId: number,
  targetCharacterId: number,
  battleType: 'pvp_training' | 'pvp_death',
): Promise<SendInvitationResult> => {
  const { data } = await axios.post<SendInvitationResult>('/battles/pvp/invite', {
    initiator_character_id: initiatorCharacterId,
    target_character_id: targetCharacterId,
    battle_type: battleType,
  });
  return data;
};

export const respondToInvitation = async (
  invitationId: number,
  action: 'accept' | 'decline',
): Promise<RespondResult> => {
  const { data } = await axios.post<RespondResult>(
    `/battles/pvp/invite/${invitationId}/respond`,
    { action },
  );
  return data;
};

export const getPendingInvitations = async (): Promise<PvpInvitationResponse> => {
  const { data } = await axios.get<PvpInvitationResponse>(
    '/battles/pvp/invitations/pending',
  );
  return data;
};

export const cancelInvitation = async (
  invitationId: number,
): Promise<CancelResult> => {
  const { data } = await axios.delete<CancelResult>(
    `/battles/pvp/invite/${invitationId}`,
  );
  return data;
};

export const attackPlayer = async (
  attackerCharacterId: number,
  victimCharacterId: number,
): Promise<AttackResult> => {
  const { data } = await axios.post<AttackResult>('/battles/pvp/attack', {
    attacker_character_id: attackerCharacterId,
    victim_character_id: victimCharacterId,
  });
  return data;
};
