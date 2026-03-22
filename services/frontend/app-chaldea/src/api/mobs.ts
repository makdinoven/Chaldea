import axios from 'axios';

// --- Types ---

export interface MobTemplate {
  id: number;
  name: string;
  description: string;
  tier: 'normal' | 'elite' | 'boss';
  level: number;
  avatar: string;
  id_race: number;
  id_subrace: number;
  id_class: number;
  sex: 'male' | 'female' | 'genderless';
  base_attributes: Record<string, number>;
  xp_reward: number;
  gold_reward: number;
  respawn_enabled: boolean;
  respawn_seconds: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface MobTemplateListItem {
  id: number;
  name: string;
  tier: 'normal' | 'elite' | 'boss';
  level: number;
  avatar: string;
  xp_reward: number;
  gold_reward: number;
  respawn_enabled: boolean;
  respawn_seconds: number | null;
}

export interface MobTemplateListResponse {
  items: MobTemplateListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface MobTemplateDetail extends MobTemplate {
  skills: MobSkillEntry[];
  loot_entries: MobLootEntry[];
  spawn_locations: LocationMobSpawn[];
}

export interface MobSkillEntry {
  id: number;
  skill_rank_id: number;
  skill_name?: string;
  skill_type?: string;
  rank_name?: string;
}

export interface MobLootEntry {
  id: number;
  item_id: number;
  item_name?: string;
  drop_chance: number;
  min_quantity: number;
  max_quantity: number;
}

export interface LocationMobSpawn {
  id: number;
  mob_template_id: number;
  location_id: number;
  location_name?: string;
  spawn_chance: number;
  max_active: number;
  is_enabled: boolean;
}

export interface ActiveMob {
  id: number;
  mob_template_id: number;
  character_id: number;
  location_id: number;
  status: 'alive' | 'in_battle' | 'dead';
  name: string;
  level: number;
  tier: 'normal' | 'elite' | 'boss';
  avatar: string;
  spawn_type: 'random' | 'manual';
  spawned_at: string;
  killed_at: string | null;
  location_name?: string;
  template_name?: string;
}

export interface ActiveMobListResponse {
  items: ActiveMob[];
  total: number;
  page: number;
  page_size: number;
}

export interface MobTemplateCreatePayload {
  name: string;
  description: string;
  tier: 'normal' | 'elite' | 'boss';
  level: number;
  avatar?: string;
  id_race: number;
  id_subrace: number;
  id_class: number;
  sex: 'male' | 'female' | 'genderless';
  base_attributes: Record<string, number>;
  xp_reward: number;
  gold_reward: number;
  respawn_enabled: boolean;
  respawn_seconds: number | null;
}

export interface MobInLocation {
  active_mob_id: number;
  character_id: number;
  name: string;
  level: number;
  tier: 'normal' | 'elite' | 'boss';
  avatar: string | null;
  status: 'alive' | 'in_battle';
}

export interface BattleRewardItem {
  item_id: number;
  item_name: string | null;
  quantity: number;
}

export interface BattleRewards {
  xp: number;
  gold: number;
  items: BattleRewardItem[];
}

// --- Public API calls ---

export const fetchMobsByLocation = async (locationId: number): Promise<MobInLocation[]> => {
  const { data } = await axios.get<MobInLocation[]>(
    '/characters/mobs/by_location',
    { params: { location_id: locationId } },
  );
  return data;
};

export const createBattle = async (
  playerCharacterId: number,
  mobCharacterId: number,
): Promise<{ battle_id: number }> => {
  const { data } = await axios.post('/battles/', {
    players: [
      { character_id: playerCharacterId, team: 0 },
      { character_id: mobCharacterId, team: 1 },
    ],
  });
  return data;
};

// --- Admin API calls ---

export const fetchMobTemplates = async (params: {
  q?: string;
  tier?: string;
  page?: number;
  page_size?: number;
}): Promise<MobTemplateListResponse> => {
  const cleanParams: Record<string, string | number> = {};
  if (params.q) cleanParams.q = params.q;
  if (params.tier) cleanParams.tier = params.tier;
  if (params.page != null) cleanParams.page = params.page;
  if (params.page_size != null) cleanParams.page_size = params.page_size;

  const { data } = await axios.get<MobTemplateListResponse>(
    '/characters/admin/mob-templates',
    { params: cleanParams },
  );
  return data;
};

export const fetchMobTemplate = async (id: number): Promise<MobTemplateDetail> => {
  const { data } = await axios.get<MobTemplateDetail>(
    `/characters/admin/mob-templates/${id}`,
  );
  return data;
};

export const createMobTemplate = async (
  payload: MobTemplateCreatePayload,
): Promise<MobTemplate> => {
  const { data } = await axios.post<MobTemplate>(
    '/characters/admin/mob-templates',
    payload,
  );
  return data;
};

export const updateMobTemplate = async (
  id: number,
  payload: Partial<MobTemplateCreatePayload>,
): Promise<MobTemplate> => {
  const { data } = await axios.put<MobTemplate>(
    `/characters/admin/mob-templates/${id}`,
    payload,
  );
  return data;
};

export const deleteMobTemplate = async (id: number): Promise<void> => {
  await axios.delete(`/characters/admin/mob-templates/${id}`);
};

export const updateMobSkills = async (
  templateId: number,
  skillRankIds: number[],
): Promise<{ detail: string; skill_rank_ids: number[] }> => {
  const { data } = await axios.put(
    `/characters/admin/mob-templates/${templateId}/skills`,
    { skill_rank_ids: skillRankIds },
  );
  return data;
};

export const updateMobLoot = async (
  templateId: number,
  entries: Array<{ item_id: number; drop_chance: number; min_quantity: number; max_quantity: number }>,
): Promise<{ detail: string; entries: MobLootEntry[] }> => {
  const { data } = await axios.put(
    `/characters/admin/mob-templates/${templateId}/loot`,
    { entries },
  );
  return data;
};

export const updateMobSpawns = async (
  templateId: number,
  spawns: Array<{ location_id: number; spawn_chance: number; max_active: number; is_enabled: boolean }>,
): Promise<{ detail: string; spawns: LocationMobSpawn[] }> => {
  const { data } = await axios.put(
    `/characters/admin/mob-templates/${templateId}/spawns`,
    { spawns },
  );
  return data;
};

export const fetchActiveMobs = async (params: {
  location_id?: number;
  status?: string;
  template_id?: number;
  page?: number;
  page_size?: number;
}): Promise<ActiveMobListResponse> => {
  const cleanParams: Record<string, string | number> = {};
  if (params.location_id != null) cleanParams.location_id = params.location_id;
  if (params.status) cleanParams.status = params.status;
  if (params.template_id != null) cleanParams.template_id = params.template_id;
  if (params.page != null) cleanParams.page = params.page;
  if (params.page_size != null) cleanParams.page_size = params.page_size;

  const { data } = await axios.get<ActiveMobListResponse>(
    '/characters/admin/active-mobs',
    { params: cleanParams },
  );
  return data;
};

export const spawnMob = async (
  mobTemplateId: number,
  locationId: number,
): Promise<ActiveMob> => {
  const { data } = await axios.post<ActiveMob>(
    '/characters/admin/active-mobs/spawn',
    { mob_template_id: mobTemplateId, location_id: locationId },
  );
  return data;
};

export const deleteActiveMob = async (id: number): Promise<void> => {
  await axios.delete(`/characters/admin/active-mobs/${id}`);
};

export const uploadMobAvatar = async (templateId: number, file: File): Promise<string> => {
  const formData = new FormData();
  formData.append('character_id', String(templateId));
  formData.append('file', file);
  const { data } = await axios.post('/photo/change_npc_avatar', formData);
  return data.avatar_url as string;
};
