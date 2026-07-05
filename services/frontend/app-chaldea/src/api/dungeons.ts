import axios from 'axios';

// --- Types ---

export interface Dungeon {
  id: number;
  name: string;
  description: string;
  lore_text: string | null;
  stability_type: 'static' | 'unstable' | 'chaotic';
  danger_level: 'safe' | 'deadly';
  location_id: number;
  recommended_level: number | null;
  recommended_party_size: number | null;
  cooldown_hours: number;
  is_active: boolean;
  mob_multiplier: number;
  loot_multiplier: number;
  stamina_multiplier: number;
  difficulty_modifier: number;
  disable_rest_rooms: boolean;
  disable_merchants: boolean;
  mana_core_chance: number;
  mana_core_item_id: number | null;
  image_url: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface DungeonRoom {
  id: number;
  dungeon_id: number;
  room_type: 'battle' | 'boss' | 'treasure' | 'trap' | 'event' | 'rest' | 'merchant' | 'fork' | 'teleport' | 'deadend';
  name: string;
  description: string;
  image_url: string | null;
  sort_order: number;
  is_entrance: boolean;
  is_boss_room: boolean;
  is_mana_core_room: boolean;
  room_config: Record<string, unknown>;
  position_x: number | null;
  position_y: number | null;
}

export interface DungeonCorridor {
  id: number;
  dungeon_id: number;
  from_room_id: number;
  to_room_id: number;
  stamina_cost: number;
  is_bidirectional: boolean;
  random_battle_chance: number;
  random_battle_mob_ids: number[] | null;
  trap_chance: number;
  trap_config: Record<string, unknown> | null;
  description: string | null;
  source_handle: string | null;
  target_handle: string | null;
}

export interface DungeonCreate {
  name: string;
  description: string;
  lore_text?: string | null;
  stability_type: 'static' | 'unstable' | 'chaotic';
  danger_level: 'safe' | 'deadly';
  location_id: number;
  recommended_level?: number | null;
  recommended_party_size?: number | null;
  cooldown_hours?: number;
  mob_multiplier?: number;
  loot_multiplier?: number;
  stamina_multiplier?: number;
  difficulty_modifier?: number;
  disable_rest_rooms?: boolean;
  disable_merchants?: boolean;
  mana_core_chance?: number;
  mana_core_item_id?: number | null;
  image_url?: string | null;
}

export type DungeonUpdate = Partial<DungeonCreate>;

export interface DungeonDetail extends Dungeon {
  rooms: DungeonRoom[];
  corridors: DungeonCorridor[];
}

export interface DungeonValidationResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

// --- Admin API calls ---

export const fetchDungeons = async (): Promise<Dungeon[]> => {
  const { data } = await axios.get<Dungeon[]>('/dungeons/admin/dungeons');
  return data;
};

export const fetchDungeonDetail = async (id: number): Promise<DungeonDetail> => {
  const { data } = await axios.get<DungeonDetail>(`/dungeons/admin/dungeons/${id}`);
  return data;
};

export const createDungeon = async (payload: DungeonCreate): Promise<Dungeon> => {
  const { data } = await axios.post<Dungeon>('/dungeons/admin/dungeons', payload);
  return data;
};

export const updateDungeon = async (id: number, payload: DungeonUpdate): Promise<Dungeon> => {
  const { data } = await axios.put<Dungeon>(`/dungeons/admin/dungeons/${id}`, payload);
  return data;
};

export const deleteDungeon = async (id: number): Promise<void> => {
  await axios.delete(`/dungeons/admin/dungeons/${id}`);
};

export const createRoom = async (
  dungeonId: number,
  payload: Omit<DungeonRoom, 'id' | 'dungeon_id'>,
): Promise<DungeonRoom> => {
  const { data } = await axios.post<DungeonRoom>(
    `/dungeons/admin/dungeons/${dungeonId}/rooms`,
    payload,
  );
  return data;
};

export const updateRoom = async (
  roomId: number,
  payload: Partial<Omit<DungeonRoom, 'id' | 'dungeon_id'>>,
): Promise<DungeonRoom> => {
  const { data } = await axios.put<DungeonRoom>(
    `/dungeons/admin/rooms/${roomId}`,
    payload,
  );
  return data;
};

export const deleteRoom = async (roomId: number): Promise<void> => {
  await axios.delete(`/dungeons/admin/rooms/${roomId}`);
};

export const createCorridor = async (
  dungeonId: number,
  payload: Omit<DungeonCorridor, 'id' | 'dungeon_id'>,
): Promise<DungeonCorridor> => {
  const { data } = await axios.post<DungeonCorridor>(
    `/dungeons/admin/dungeons/${dungeonId}/corridors`,
    payload,
  );
  return data;
};

export const updateCorridor = async (
  corridorId: number,
  payload: Partial<Omit<DungeonCorridor, 'id' | 'dungeon_id'>>,
): Promise<DungeonCorridor> => {
  const { data } = await axios.put<DungeonCorridor>(
    `/dungeons/admin/corridors/${corridorId}`,
    payload,
  );
  return data;
};

export const deleteCorridor = async (corridorId: number): Promise<void> => {
  await axios.delete(`/dungeons/admin/corridors/${corridorId}`);
};

export const validateDungeon = async (dungeonId: number): Promise<DungeonValidationResponse> => {
  const { data } = await axios.post<DungeonValidationResponse>(
    `/dungeons/admin/dungeons/${dungeonId}/validate`,
  );
  return data;
};

export const bulkUpdateRoomPositions = async (
  dungeonId: number,
  positions: { room_id: number; position_x: number; position_y: number }[],
): Promise<{ updated: number }> => {
  const { data } = await axios.put<{ updated: number }>(
    `/dungeons/admin/dungeons/${dungeonId}/rooms/positions`,
    { positions },
  );
  return data;
};

// --- Admin Sessions ---

export interface AdminSessionMember {
  character_id: number;
  user_id: number;
  status: string;
}

export interface AdminSession {
  id: number;
  dungeon_id: number;
  dungeon_name: string | null;
  leader_character_id: number;
  status: string;
  current_room_id: number | null;
  started_at: string | null;
  created_at: string | null;
  members: AdminSessionMember[];
}

export interface ForceCleanupResponse {
  message: string;
  session_id: number;
  previous_status: string;
  freed_characters: number[];
}

export const fetchAdminSessions = async (status?: string): Promise<AdminSession[]> => {
  const params = status ? { status } : {};
  const { data } = await axios.get<AdminSession[]>('/dungeons/admin/sessions', { params });
  return data;
};

export const forceCleanupSession = async (sessionId: number): Promise<ForceCleanupResponse> => {
  const { data } = await axios.delete<ForceCleanupResponse>(`/dungeons/admin/sessions/${sessionId}`);
  return data;
};

// --- Player Gameplay Types ---

export interface DungeonAtLocation {
  id: number;
  name: string;
  description: string;
  lore_text: string | null;
  stability_type: 'static' | 'unstable' | 'chaotic';
  danger_level: 'safe' | 'deadly';
  recommended_level: number | null;
  recommended_party_size: number | null;
  is_on_cooldown: boolean;
  cooldown_remaining_seconds: number;
  image_url: string | null;
}

export interface SessionMember {
  character_id: number;
  name: string;
  user_id: number;
  status: 'alive' | 'dead' | 'disconnected';
  is_leader: boolean;
}

export interface SessionCreateResponse {
  session_id: number;
  dungeon_id: number;
  status: 'forming' | 'active' | 'completed' | 'escaped' | 'wiped';
  leader_character_id: number;
  members: SessionMember[];
}

export interface RoomExit {
  corridor_id: number;
  to_room_id: number;
  to_room_name: string;
  stamina_cost: number;
  explored: boolean;
  reliability: 'reliable' | 'uncertain' | 'memory_only';
  position_x: number | null;
  position_y: number | null;
  source_handle: string | null;
  target_handle: string | null;
}

export interface RoomView {
  id: number;
  room_type: string;
  name: string;
  description: string;
  image_url: string | null;
  is_cleared: boolean;
  room_config_visible: Record<string, unknown>;
  exits: RoomExit[];
  position_x: number | null;
  position_y: number | null;
}

export interface ExploredRoomInfo {
  id: number;
  name: string;
  room_type: string;
  is_cleared: boolean;
  position_x: number | null;
  position_y: number | null;
}

export interface ExploredCorridorInfo {
  corridor_id: number;
  from_room_id: number;
  to_room_id: number;
  source_handle: string | null;
  target_handle: string | null;
}

export interface GroupInventoryItem {
  item_id: number;
  item_name: string;
  quantity: number;
}

export interface SessionState {
  session_id: number;
  dungeon_id: number;
  dungeon_name: string;
  location_id: number;
  status: 'forming' | 'active' | 'completed' | 'escaped' | 'wiped';
  phase: 'forming' | 'exploring' | 'in_battle' | 'in_event' | 'distributing_loot' | 'completed' | 'escaped' | 'wiped';
  current_room: RoomView | null;
  members: SessionMember[];
  group_inventory: GroupInventoryItem[];
  active_battle_id: number | null;
  explored_rooms: ExploredRoomInfo[];
  explored_corridors: ExploredCorridorInfo[];
}

// --- Player Gameplay API calls ---

export const fetchDungeonsAtLocation = async (locationId: number): Promise<DungeonAtLocation[]> => {
  const { data } = await axios.get<DungeonAtLocation[]>(`/dungeons/at-location/${locationId}`);
  return data;
};

export interface ActiveSessionCheck {
  in_dungeon: boolean;
  session_id: number | null;
}

export const checkActiveSession = async (characterId: number): Promise<ActiveSessionCheck> => {
  const { data } = await axios.get<ActiveSessionCheck>(`/dungeons/my-session/${characterId}`);
  return data;
};

export const createSession = async (dungeonId: number, characterId: number): Promise<SessionCreateResponse> => {
  const { data } = await axios.post<SessionCreateResponse>(
    `/dungeons/${dungeonId}/sessions`,
    { character_id: characterId },
  );
  return data;
};

// Start a dungeon run straight from the leader's squad (FEAT-144 Ф3-3) — members
// come from the party, no separate invite phase; the run activates immediately.
export const partyRunDungeon = async (
  dungeonId: number,
  characterId: number,
): Promise<{ session_id: number }> => {
  const { data } = await axios.post<{ session_id: number }>(
    `/dungeons/${dungeonId}/party-run`,
    { character_id: characterId },
  );
  return data;
};

export const inviteMember = async (sessionId: number, characterId: number): Promise<SessionCreateResponse> => {
  const { data } = await axios.post<SessionCreateResponse>(
    `/dungeons/sessions/${sessionId}/invite`,
    { character_id: characterId },
  );
  return data;
};

export const leaveSession = async (sessionId: number, characterId: number): Promise<void> => {
  await axios.post(`/dungeons/sessions/${sessionId}/leave`, { character_id: characterId });
};

export const enterDungeon = async (sessionId: number, characterId: number): Promise<SessionState> => {
  const { data } = await axios.post<SessionState>(
    `/dungeons/sessions/${sessionId}/enter`,
    { character_id: characterId },
  );
  return data;
};

export const getSessionState = async (sessionId: number, characterId: number): Promise<SessionState> => {
  const { data } = await axios.get<SessionState>(
    `/dungeons/sessions/${sessionId}/state`,
    { params: { character_id: characterId } },
  );
  return data;
};

// --- Movement + Interaction Types ---

export interface CorridorEvent {
  type: 'battle' | 'trap' | 'safe';
  battle_id?: number;
  stat_check?: string;
  difficulty?: number;
  best_character?: string;
  best_value?: number;
  passed?: boolean;
  message?: string;
  mob_names?: string[];
}

export interface RoomEvent {
  type: 'battle_started' | 'trap_triggered' | 'none';
  battle_id?: number;
  message?: string;
}

export interface MoveResponse {
  corridor_event: CorridorEvent | null;
  new_room: RoomView;
  stamina_consumed: number;
  room_event: RoomEvent | null;
}

export interface FleeResponse {
  status: 'escaped';
  items_lost: GroupInventoryItem[];
  items_remaining: GroupInventoryItem[];
  message: string;
}

export interface InteractResponse {
  action: string;
  success: boolean;
  message: string;
  loot?: GroupInventoryItem[];
  [key: string]: unknown;
}

// --- Movement + Interaction API calls ---

export const moveInDungeon = async (
  sessionId: number,
  characterId: number,
  corridorId: number,
): Promise<MoveResponse> => {
  const { data } = await axios.post<MoveResponse>(
    `/dungeons/sessions/${sessionId}/move`,
    { character_id: characterId, corridor_id: corridorId },
  );
  return data;
};

export const interactWithRoom = async (
  sessionId: number,
  characterId: number,
  action: string,
  extraData?: Record<string, unknown>,
): Promise<InteractResponse> => {
  const { data } = await axios.post<InteractResponse>(
    `/dungeons/sessions/${sessionId}/interact`,
    { character_id: characterId, action, ...extraData },
  );
  return data;
};

export const fleeDungeon = async (
  sessionId: number,
  characterId: number,
): Promise<FleeResponse> => {
  const { data } = await axios.post<FleeResponse>(
    `/dungeons/sessions/${sessionId}/flee`,
    { character_id: characterId },
  );
  return data;
};

// --- Loot Distribution + Finalization Types ---

export interface LootDistribution {
  item_id: number;
  to_character_id: number;
  quantity: number;
}

export interface DistributeLootResponse {
  success: boolean;
  message: string;
  distributed: {
    character_id: number;
    character_name: string;
    items: { item_id: number; item_name: string; quantity: number }[];
  }[];
  remaining_inventory: GroupInventoryItem[];
}

export interface FinalizeResponse {
  success: boolean;
  message: string;
  cooldown_hours: number;
  cooldown_until: string;
}

// --- Loot Distribution + Finalization API calls ---

export const distributeLoot = async (
  sessionId: number,
  characterId: number,
  distributions: LootDistribution[],
): Promise<DistributeLootResponse> => {
  const { data } = await axios.post<DistributeLootResponse>(
    `/dungeons/sessions/${sessionId}/distribute-loot`,
    { character_id: characterId, distributions },
  );
  return data;
};

export const finalizeSession = async (
  sessionId: number,
  characterId: number,
): Promise<FinalizeResponse> => {
  const { data } = await axios.post<FinalizeResponse>(
    `/dungeons/sessions/${sessionId}/finalize`,
    { character_id: characterId },
  );
  return data;
};
