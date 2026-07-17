import axios from 'axios';

// Mirrors battle-service BATTLE_MAX_TEAM_SIZE — used to warn admins when a pack's
// mob count exceeds what a single battle team can hold (the rest is truncated).
export const BATTLE_MAX_TEAM_SIZE = 5;

// --- Types ---

export interface MobPackListItem {
  id: number;
  name: string;
  avatar: string | null;
  respawn_enabled: boolean;
  respawn_seconds: number | null;
  member_count: number;
  total_mobs: number;
}

export interface MobPackListResponse {
  items: MobPackListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface MobPackMemberInput {
  mob_template_id: number;
  quantity: number;
}

export interface MobPackMemberResponse {
  mob_template_id: number;
  quantity: number;
  template_name?: string | null;
  template_tier?: string | null;
  template_level?: number | null;
  template_avatar?: string | null;
}

export interface MobPackDetail {
  id: number;
  name: string;
  description: string | null;
  avatar: string | null;
  respawn_enabled: boolean;
  respawn_seconds: number | null;
  members: MobPackMemberResponse[];
}

export interface MobPackCreatePayload {
  name: string;
  description?: string;
  avatar?: string;
  respawn_enabled: boolean;
  respawn_seconds: number | null;
  members: MobPackMemberInput[];
}

export interface ActiveMobPack {
  id: number;
  pack_id: number;
  location_id: number;
  status: 'alive' | 'in_battle' | 'dead';
  pack_name: string | null;
  alive_count: number;
  total_count: number;
  spawned_at: string | null;
  killed_at: string | null;
  respawn_at: string | null;
}

export interface ActiveMobPackListResponse {
  items: ActiveMobPack[];
  total: number;
  page: number;
  page_size: number;
}

export interface PackMemberInLocation {
  name: string;
  tier: 'normal' | 'elite' | 'boss';
  level: number;
  avatar: string | null;
  count: number;
  // FEAT-152: SUMMED persisted HP across the group's LIVING members
  // (members are aggregated by template — e.g. 30/60 for two mobs at 15/30).
  // Null/absent when no attributes rows were found — the UI hides the bar.
  current_hp?: number | null;
  max_hp?: number | null;
}

export interface MobPackInLocation {
  active_pack_id: number;
  name: string;
  avatar: string | null;
  status: 'alive' | 'in_battle';
  lead_character_id: number;
  members: PackMemberInLocation[];
}

// --- Admin API calls ---

export const fetchMobPacks = async (params: {
  q?: string;
  page?: number;
  page_size?: number;
}): Promise<MobPackListResponse> => {
  const cleanParams: Record<string, string | number> = {};
  if (params.q) cleanParams.q = params.q;
  if (params.page != null) cleanParams.page = params.page;
  if (params.page_size != null) cleanParams.page_size = params.page_size;

  const { data } = await axios.get<MobPackListResponse>(
    '/characters/admin/mob-packs',
    { params: cleanParams },
  );
  return data;
};

export const fetchMobPackDetail = async (id: number): Promise<MobPackDetail> => {
  const { data } = await axios.get<MobPackDetail>(`/characters/admin/mob-packs/${id}`);
  return data;
};

export const createMobPack = async (payload: MobPackCreatePayload): Promise<MobPackDetail> => {
  const { data } = await axios.post<MobPackDetail>('/characters/admin/mob-packs', payload);
  return data;
};

export const updateMobPack = async (
  id: number,
  payload: Partial<MobPackCreatePayload>,
): Promise<MobPackDetail> => {
  const { data } = await axios.put<MobPackDetail>(`/characters/admin/mob-packs/${id}`, payload);
  return data;
};

export const deleteMobPack = async (id: number): Promise<void> => {
  await axios.delete(`/characters/admin/mob-packs/${id}`);
};

export const placePack = async (
  packId: number,
  locationId: number,
): Promise<{ id: number; spawned_mobs: number }> => {
  const { data } = await axios.post('/characters/admin/mob-packs/place', {
    pack_id: packId,
    location_id: locationId,
  });
  return data;
};

export const fetchActiveMobPacks = async (params: {
  location_id?: number;
  status?: string;
  pack_id?: number;
  page?: number;
  page_size?: number;
}): Promise<ActiveMobPackListResponse> => {
  const cleanParams: Record<string, string | number> = {};
  if (params.location_id != null) cleanParams.location_id = params.location_id;
  if (params.status) cleanParams.status = params.status;
  if (params.pack_id != null) cleanParams.pack_id = params.pack_id;
  if (params.page != null) cleanParams.page = params.page;
  if (params.page_size != null) cleanParams.page_size = params.page_size;

  const { data } = await axios.get<ActiveMobPackListResponse>(
    '/characters/admin/active-mob-packs',
    { params: cleanParams },
  );
  return data;
};

export const deleteActiveMobPack = async (id: number): Promise<void> => {
  await axios.delete(`/characters/admin/active-mob-packs/${id}`);
};

// --- Public API calls ---

export const fetchMobPacksByLocation = async (
  locationId: number,
): Promise<MobPackInLocation[]> => {
  const { data } = await axios.get<MobPackInLocation[]>(
    '/characters/mob-packs/by_location',
    { params: { location_id: locationId } },
  );
  return data;
};

// Solo attack on a whole pack. Gated (FEAT-145) via the pack's lead mob.
export const createPackBattle = async (
  playerCharacterId: number,
  activePackId: number,
): Promise<{ battle_id: number }> => {
  const { data } = await axios.post('/battles/pack-attack', {
    character_id: playerCharacterId,
    active_pack_id: activePackId,
  });
  return data;
};

// Group fight: the party leader pulls co-located squadmates onto team 0 vs the
// whole pack (FEAT-147).
export const createPartyPackBattle = async (
  leaderCharacterId: number,
  activePackId: number,
): Promise<{ battle_id: number }> => {
  const { data } = await axios.post('/battles/party/pack-attack', {
    leader_character_id: leaderCharacterId,
    active_pack_id: activePackId,
  });
  return data;
};
