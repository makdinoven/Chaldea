import axios from 'axios';
import type {
  AdminCharacterListParams,
  AdminCharacterListResponse,
  AdminCharacterUpdate,
  AdminCharacterUpdateResponse,
  UnlinkCharacterResponse,
  CharacterAttributes,
  AdminAttributeUpdate,
  InventoryItem,
  EquipmentSlot,
  AddInventoryItemPayload,
  CharacterSkill,
  SkillInfo,
  AddCharacterSkillPayload,
  AdminCharacterSkillUpdatePayload,
  ItemData,
  FullSkillTreeResponse,
} from '../components/Admin/CharactersPage/types';

// --- Character CRUD ---

export const fetchAdminCharacterList = async (
  params: AdminCharacterListParams,
): Promise<AdminCharacterListResponse> => {
  // Strip null/undefined params before sending
  const cleanParams: Record<string, string | number> = {};
  if (params.q) cleanParams.q = params.q;
  if (params.user_id != null) cleanParams.user_id = params.user_id;
  if (params.level_min != null) cleanParams.level_min = params.level_min;
  if (params.level_max != null) cleanParams.level_max = params.level_max;
  if (params.id_race != null) cleanParams.id_race = params.id_race;
  if (params.id_class != null) cleanParams.id_class = params.id_class;
  if (params.page != null) cleanParams.page = params.page;
  if (params.page_size != null) cleanParams.page_size = params.page_size;

  const { data } = await axios.get<AdminCharacterListResponse>(
    '/characters/admin/list',
    { params: cleanParams },
  );
  return data;
};

export const updateAdminCharacter = async (
  characterId: number,
  update: AdminCharacterUpdate,
): Promise<AdminCharacterUpdateResponse> => {
  const { data } = await axios.put<AdminCharacterUpdateResponse>(
    `/characters/admin/${characterId}`,
    update,
  );
  return data;
};

export const unlinkCharacter = async (
  characterId: number,
): Promise<UnlinkCharacterResponse> => {
  const { data } = await axios.post<UnlinkCharacterResponse>(
    `/characters/admin/${characterId}/unlink`,
  );
  return data;
};

export const deleteCharacter = async (
  characterId: number,
): Promise<{ detail: string }> => {
  const { data } = await axios.delete<{ detail: string }>(
    `/characters/${characterId}`,
  );
  return data;
};

// --- Attributes ---

export const fetchCharacterAttributes = async (
  characterId: number,
): Promise<CharacterAttributes> => {
  const { data } = await axios.get<CharacterAttributes>(
    `/attributes/${characterId}`,
  );
  return data;
};

export const updateCharacterAttributes = async (
  characterId: number,
  update: AdminAttributeUpdate,
): Promise<CharacterAttributes> => {
  const { data } = await axios.put<CharacterAttributes>(
    `/attributes/admin/${characterId}`,
    update,
  );
  return data;
};

// --- Inventory ---

export const fetchCharacterInventory = async (
  characterId: number,
): Promise<InventoryItem[]> => {
  const { data } = await axios.get<InventoryItem[]>(
    `/inventory/${characterId}/items`,
  );
  return data;
};

export const fetchCharacterEquipment = async (
  characterId: number,
): Promise<EquipmentSlot[]> => {
  const { data } = await axios.get<EquipmentSlot[]>(
    `/inventory/${characterId}/equipment`,
  );
  return data;
};

export const addInventoryItem = async (
  characterId: number,
  itemId: number,
  quantity: number,
): Promise<InventoryItem> => {
  const payload: AddInventoryItemPayload = { item_id: itemId, quantity };
  const { data } = await axios.post<InventoryItem>(
    `/inventory/${characterId}/items`,
    payload,
  );
  return data;
};

export const removeInventoryItem = async (
  characterId: number,
  itemId: number,
  quantity?: number,
): Promise<void> => {
  await axios.delete(`/inventory/${characterId}/items/${itemId}`, {
    params: quantity != null ? { quantity } : undefined,
  });
};

export const equipItem = async (
  characterId: number,
  itemId: number,
): Promise<void> => {
  await axios.post(`/inventory/${characterId}/equip`, { item_id: itemId });
};

export const unequipItem = async (
  characterId: number,
  slotType: string,
): Promise<void> => {
  await axios.post(`/inventory/${characterId}/unequip`, null, {
    params: { slot_type: slotType },
  });
};

// --- Items catalog ---

export const searchItemsCatalog = async (
  q: string = '',
  page: number = 1,
  pageSize: number = 20,
): Promise<ItemData[]> => {
  const { data } = await axios.get('/inventory/items', {
    params: { q, page, page_size: pageSize },
  });
  return Array.isArray(data) ? data : data.items ?? [];
};

// --- Skills ---

export const fetchCharacterSkills = async (
  characterId: number,
): Promise<CharacterSkill[]> => {
  const { data } = await axios.get<CharacterSkill[]>(
    `/skills/characters/${characterId}/skills`,
  );
  return data;
};

export const fetchAllSkills = async (): Promise<SkillInfo[]> => {
  const { data } = await axios.get<SkillInfo[]>('/skills/admin/skills/');
  return data;
};

export const fetchSkillFullTree = async (
  skillId: number,
): Promise<FullSkillTreeResponse> => {
  const { data } = await axios.get<FullSkillTreeResponse>(
    `/skills/admin/skills/${skillId}/full_tree`,
  );
  return data;
};

export const addCharacterSkill = async (
  characterId: number,
  skillRankId: number,
): Promise<CharacterSkill> => {
  const payload: AddCharacterSkillPayload = {
    character_id: characterId,
    skill_rank_id: skillRankId,
  };
  const { data } = await axios.post<CharacterSkill>(
    '/skills/admin/character_skills/',
    payload,
  );
  return data;
};

export const removeCharacterSkill = async (
  csId: number,
): Promise<void> => {
  await axios.delete(`/skills/admin/character_skills/${csId}`);
};

export const updateCharacterSkillRank = async (
  csId: number,
  skillRankId: number,
): Promise<CharacterSkill> => {
  const payload: AdminCharacterSkillUpdatePayload = { skill_rank_id: skillRankId };
  const { data } = await axios.put<CharacterSkill>(
    `/skills/admin/character_skills/${csId}`,
    payload,
  );
  return data;
};
