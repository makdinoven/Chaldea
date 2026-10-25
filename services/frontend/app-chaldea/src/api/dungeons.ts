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
  /** Per floor below the first: + mob strength, + loot chances, + flee loss (0.2 = +20%). */
  floor_mob_step?: number;
  floor_loot_step?: number;
  floor_flee_step?: number;
  /** What searching a room may turn up by luck (FEAT-176). */
  search_loot?: LootEntryDto[] | null;
  /** How the 3D miniature looks (see DUNGEON_THEMES), and each floor's own look: {"2": "volcano"}. */
  theme?: string;
  floor_themes?: Record<string, string> | null;
  created_at?: string;
  updated_at?: string;
}

/** A loot line: an item, how many, the chance (0..1). */
export interface LootEntryDto {
  item_id: number;
  quantity: number;
  chance: number;
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
  /** Footprint on the 3D miniature, in floor squares; null = the default for its kind. */
  grid_w?: number | null;
  grid_d?: number | null;
  /** 1 = the top floor. */
  floor?: number;
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
  /** A locked door: {key?, lever?, pickable?, difficulty?, stat_check?, pick_cost?}; null = open. */
  lock_config?: LockConfig | null;
  /** corridor (same floor) | stairs | drop (one way down) | lift — the last three join neighbouring floors. */
  passage_type?: PassageType;
  /** A drop's hidden trap: {hidden, stat_check, difficulty, fail_damage}. */
  passage_config?: Record<string, unknown> | null;
  description: string | null;
  source_handle: string | null;
  target_handle: string | null;
}

export type PassageType = 'corridor' | 'stairs' | 'drop' | 'lift';

export interface LockConfig {
  key?: string | null;
  /** Opened by a lever somewhere in the dungeon (room_config.lever_corridor_id). */
  lever?: boolean;
  pickable?: boolean;
  difficulty?: number;
  stat_check?: string;
  pick_cost?: number;
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
  floor_mob_step?: number;
  floor_loot_step?: number;
  floor_flee_step?: number;
  search_loot?: LootEntryDto[] | null;
  /** How the 3D miniature looks (see DUNGEON_THEMES), and each floor's own look: {"2": "volcano"}. */
  theme?: string;
  floor_themes?: Record<string, string> | null;
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
  finished_at?: string | null;
  finalized_at?: string | null;
  last_activity_at?: string | null;
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

// --- Player Gameplay Types (FEAT-175 contract, see docs/services/dungeon-service.md) ---

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
  /** Another group is inside right now — entry is closed for everyone else. */
  is_occupied: boolean;
  image_url: string | null;
}

export interface SessionMember {
  character_id: number;
  name: string;
  user_id: number;
  status: 'alive' | 'dead';
  is_leader: boolean;
  /** Party frames: null when a neighbour service didn't answer. */
  avatar?: string | null;
  level?: number | null;
  /** The miniature on the board: 1 warrior, 2 rogue, 3 mage. */
  class_id?: number | null;
  current_health?: number | null;
  max_health?: number | null;
  current_mana?: number | null;
  max_mana?: number | null;
  current_energy?: number | null;
  max_energy?: number | null;
  current_stamina?: number | null;
  max_stamina?: number | null;
  /** The minigame they are playing right now (its kind), shown over the figurine (FEAT-176). */
  busy?: string | null;
}

export type SessionStatus = 'forming' | 'active' | 'completed' | 'escaped' | 'wiped';

export type SessionPhase =
  | 'exploring'
  | 'resting'
  | 'in_battle'
  | 'battle_pending'
  | 'distributing_loot'
  | 'wiped'
  | 'finished';

export interface SessionCreateResponse {
  session_id: number;
  dungeon_id: number;
  status: SessionStatus;
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
  grid_w?: number | null;
  grid_d?: number | null;
  source_handle: string | null;
  target_handle: string | null;
  /** A locked door: the key kind that opens it; `locked` while still shut in this run. */
  lock_key?: string | null;
  locked?: boolean;
  lock_pickable?: boolean;
  /** Opened by a lever somewhere in the dungeon. */
  lock_lever?: boolean;
  passage?: PassageType;
  to_floor?: number;
  /** A gate still down across the way (FEAT-176): someone has to hold it up and prop it. */
  gate?: GateLook | null;
  /** A magic seal not broken yet: a mage's craft. */
  sealed?: boolean;
  /** What a rogue's scouting learnt of the way (FEAT-176). */
  scout?: ScoutInfo | null;
}

/** A portcullis or a slab across a corridor. */
export type GateLook = 'grate' | 'slab';

export interface RoomView {
  id: number;
  room_type: string;
  name: string;
  description: string;
  image_url: string | null;
  is_entrance: boolean;
  is_boss_room: boolean;
  is_mana_core_room: boolean;
  is_cleared: boolean;
  room_config_visible: Record<string, unknown> | null;
  exits: RoomExit[];
  position_x: number | null;
  position_y: number | null;
  grid_w?: number | null;
  grid_d?: number | null;
  floor?: number;
  /** Secret ways out not found yet, with what hints at each (FEAT-176). */
  secrets?: RoomSecret[];
  /** A dark room (`dark_room`), and whether it is unlit now (`dark`: the ways out are unknown). */
  dark_room?: boolean;
  dark?: boolean;
  /** Searched already in this run (one search a room). */
  searched?: boolean;
  /** Who stands watch over the rest, and whether they are alert. */
  watch?: { character_id: number; passed: boolean } | null;
}

export type SecretKind = 'mechanism' | 'illusion' | 'rubble';

export interface RoomSecret {
  corridor_id: number;
  kind: SecretKind;
  hint: string;
}

export interface ExploredRoomInfo {
  id: number;
  name: string;
  room_type: string;
  is_cleared: boolean;
  is_entrance?: boolean;
  /** Enemies standing in a battle/boss room (figurines on the 3D table). */
  mob_count?: number | null;
  /** Teleport rooms: a blue portal (step in at will) or a red one (a trap). */
  portal?: PortalKind | null;
  floor?: number;
  /** Its one-off use is spent: the chest emptied (treasure) or the rest taken. */
  used?: boolean;
  /** A dark room left unlit. */
  dark?: boolean;
  position_x: number | null;
  position_y: number | null;
  grid_w?: number | null;
  grid_d?: number | null;
}

/** A door seen from a visited room into one not yet entered: where the room lies, not what it is. */
export interface SeenDoorInfo {
  corridor_id: number;
  from_room_id: number;
  to_room_id: number;
  position_x: number | null;
  position_y: number | null;
  grid_w?: number | null;
  grid_d?: number | null;
  lock_key?: string | null;
  locked?: boolean;
  passage?: PassageType;
  floor?: number;
}

export interface ExploredCorridorInfo {
  corridor_id: number;
  from_room_id: number;
  to_room_id: number;
  source_handle: string | null;
  target_handle: string | null;
  lock_key?: string | null;
  locked?: boolean;
  passage?: PassageType;
}

export interface GroupInventoryItem {
  item_id: number;
  item_name: string | null;
  quantity: number;
  source_description?: string | null;
}

export interface ManaCoreInfo {
  revealed: boolean;
  room_id: number | null;
  room_name: string | null;
  /** The party can go there now (boss beaten, core not searched yet). */
  accessible: boolean;
  searched: boolean;
  destroyed: boolean;
}

export interface SkippedMember {
  character_id: number;
  name: string | null;
  reason: string;
}

export interface SessionState {
  session_id: number;
  dungeon_id: number;
  dungeon_name: string;
  location_id: number;
  stability_type: 'static' | 'unstable' | 'chaotic';
  danger_level: 'safe' | 'deadly';
  status: SessionStatus;
  phase: SessionPhase;
  current_room: RoomView | null;
  members: SessionMember[];
  group_inventory: GroupInventoryItem[];
  active_battle_id: number | null;
  explored_rooms: ExploredRoomInfo[];
  explored_corridors: ExploredCorridorInfo[];
  /** Doors seen from visited rooms into rooms not yet entered (kept across reloads). */
  seen_doors?: SeenDoorInfo[];
  /** Key kinds found this run (see DUNGEON_KEYS). */
  keys?: string[];
  /** How many floors the dungeon has; the current one is current_room.floor. */
  floors?: number;
  mana_core: ManaCoreInfo | null;
  finalized: boolean;
  /** Naive UTC timestamps (see utils/serverDate). */
  cooldown_until: string | null;
  knocked_out_until: string | null;
  last_activity_at: string | null;
  abandon_at: string | null;
  /** Only filled in the party-run response. */
  skipped_members: SkippedMember[];
  /** The members' say on where to go from the current room (FEAT-176). */
  votes?: PartyVote[];
  /** Living members (not the leader) who have not had their say yet: the leader waits for them. */
  waiting_for?: number[];
  /** The party shield raised in this room until the party moves on. */
  shield?: PartyShield | null;
  /** Each floor's span in room cells (every room, known or not): the 3D table lays its rock under all of it. */
  extents?: { floor: number; min_col: number; max_col: number; min_row: number; max_row: number }[];
  /** How the miniature looks: the dungeon's theme and each floor's own. */
  theme?: string;
  floor_themes?: Record<string, string>;
  /** A corridor ambush being fought: where the party was caught (the 3D table shows it there). */
  ambush?: { corridor_id: number; from_room_id: number; to_room_id: number } | null;
}

/** Who holds the party shield and how firmly (0..1). */
export interface PartyShield {
  character_id: number;
  block: number;
}

/** A door, the blue portal, or neither — "as the leader decides". */
export interface PartyVote {
  character_id: number;
  corridor_id?: number | null;
  portal?: boolean;
}

export interface PartyVotes {
  room_id: number | null;
  votes: PartyVote[];
  waiting_for: number[];
}

/** "go" — this way, "danger" — careful, "look" — look here. */
export type BoardPingKind = 'go' | 'danger' | 'look';

/** Display name of a group-inventory item (names can be missing). */
export const itemLabel = (item: { item_id: number; item_name?: string | null }): string =>
  item.item_name || `Предмет #${item.item_id}`;

// --- Player Gameplay API calls ---

export const fetchDungeonsAtLocation = async (locationId: number): Promise<DungeonAtLocation[]> => {
  const { data } = await axios.get<DungeonAtLocation[]>(`/dungeons/at-location/${locationId}`);
  return data;
};

export interface ActiveSessionCheck {
  in_dungeon: boolean;
  /** Run in progress. */
  session_id: number | null;
  /** Completed (boss chest opened) or escaped run whose loot is still undivided. */
  pending_loot_session_id: number | null;
}

export const checkActiveSession = async (characterId: number): Promise<ActiveSessionCheck> => {
  const { data } = await axios.get<ActiveSessionCheck>(`/dungeons/my-session/${characterId}`);
  return data;
};

/** Solo entry: the run comes back already active. */
export const createSession = async (dungeonId: number, characterId: number): Promise<SessionCreateResponse> => {
  const { data } = await axios.post<SessionCreateResponse>(
    `/dungeons/${dungeonId}/sessions`,
    { character_id: characterId },
    // 403 here is a cooldown or a missing intent post; the entrance shows it.
    { skipForbiddenToast: true },
  );
  return data;
};

/** Squad entry: the leader goes in with every free squadmate on the location. */
export const partyRunDungeon = async (dungeonId: number, characterId: number): Promise<SessionState> => {
  const { data } = await axios.post<SessionState>(
    `/dungeons/${dungeonId}/party-run`,
    { character_id: characterId },
    // 403 here is a cooldown or a missing intent post; the entrance shows it.
    { skipForbiddenToast: true },
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
  message: string;
  details?: Record<string, unknown> | null;
  battle_id?: number | null;
  mob_names?: string[] | null;
  stat_check?: string | null;
  difficulty?: number | null;
  best_character?: string | null;
  best_value?: number | null;
  passed?: boolean | null;
  damage?: number | null;
}

/**
 * What happened in the room the party walked into. The backend sends a plain
 * dict, so every field is optional:
 * - battle_started: battle_id, mob_names, room_type
 * - battle_error: message, can_retry (the battle could not start)
 * - trap_triggered: passed, stat_check, difficulty, best_character, best_value, damage, message
 * - teleported: target_room_id, target_room_name, followup (event of the target room);
 *   a red portal's throw also carries red_portal and its roll (passed, stat_check, ...)
 * - teleport_failed: message
 * - portal_spotted: a red portal's roll that did not throw the party (passed, stat_check, ..., message)
 */
export interface RoomEvent {
  type: 'battle_started' | 'battle_error' | 'trap_triggered' | 'teleported' | 'teleport_failed' | 'portal_spotted' | string;
  battle_id?: number;
  mob_names?: string[];
  room_type?: string;
  message?: string;
  can_retry?: boolean;
  passed?: boolean;
  stat_check?: string;
  difficulty?: number;
  best_character?: string | null;
  best_value?: number | null;
  damage?: number;
  target_room_id?: number;
  target_room_name?: string;
  /** teleported: the rune room the party was thrown from. */
  teleported_from?: number;
  /** teleported: the throw of a red portal the party failed to spot. */
  red_portal?: boolean;
  /** teleported: the party fell through a hidden drop to the floor below. */
  fell?: boolean;
  followup?: RoomEvent | null;
}

export interface MoveResponse {
  corridor_event: CorridorEvent | null;
  /** null when a corridor ambush stopped the party on the way. */
  new_room: RoomView | null;
  stamina_consumed: number;
  room_event: RoomEvent | null;
}

export interface FleeItem {
  item_id: number;
  quantity: number;
  item_name: string | null;
}

export interface FleeResponse {
  status: 'escaped';
  items_lost: FleeItem[];
  items_remaining: FleeItem[];
  message: string;
}

/** Loot entries can also be a plain `{gold}` line (event rewards). */
export interface LootEntry {
  item_id?: number;
  item_name?: string | null;
  quantity?: number;
  gold?: number;
}

export interface InteractResponse {
  action: string;
  success: boolean;
  message: string;
  loot_gained?: LootEntry[] | null;
  damage_taken?: number | null;
  effect_applied?: string | null;
  gold_spent?: number | null;
  teleported_to?: { room_id: number; room_name: string } | null;
  key_found?: string | null;
}

export interface PickLockResponse {
  passed: boolean;
  message: string;
  stat_check: string;
  difficulty: number;
  best_character?: string | null;
  best_value?: number | null;
  stamina_consumed: number;
}

export type InteractAction =
  | 'open_chest'
  | 'event_choice'
  | 'start_rest'
  | 'complete_rest'
  | 'revive_member'
  | 'merchant_buy'
  | 'start_battle'
  | 'enter_mana_core'
  | 'search_mana_core'
  | 'use_portal'
  | 'pull_lever';

export type PortalKind = 'blue' | 'red';

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

/** Try to pick a locked door out of the current room (leader); stamina is spent either way. */
export const voteRoute = async (
  sessionId: number,
  characterId: number,
  choice: { corridorId?: number; portal?: boolean },
): Promise<PartyVotes> => {
  const { data } = await axios.post<PartyVotes>(`/dungeons/sessions/${sessionId}/vote`, {
    character_id: characterId,
    corridor_id: choice.corridorId ?? null,
    portal: !!choice.portal,
  });
  return data;
};

export const pingBoard = async (
  sessionId: number,
  characterId: number,
  kind: BoardPingKind,
  roomId: number,
): Promise<void> => {
  await axios.post(`/dungeons/sessions/${sessionId}/ping`, { character_id: characterId, kind, room_id: roomId });
};

/* ── The run's chat and log (FEAT-176) ── */

/** A line of the run's chat: a member's ("say") or the log's ("log"). */
export interface ChatEntry {
  id: string;
  /** ms since the epoch */
  at: number;
  kind: 'say' | 'log';
  text: string;
  /** The log's colour: what went well, what went badly. */
  tone: 'info' | 'good' | 'bad';
  character_id: number | null;
  name: string | null;
}

/** The run's chat and log so far, oldest first. */
export const getChat = async (sessionId: number, characterId: number): Promise<ChatEntry[]> => {
  const { data } = await axios.get<ChatEntry[]>(`/dungeons/sessions/${sessionId}/chat`, {
    params: { character_id: characterId },
  });
  return data;
};

/** Say something to the party (up to 300 characters, once a second). */
export const sayChat = async (sessionId: number, characterId: number, text: string): Promise<ChatEntry> => {
  const { data } = await axios.post<ChatEntry>(`/dungeons/sessions/${sessionId}/chat`, {
    character_id: characterId,
    text,
  });
  return data;
};

/* ── Class challenges (FEAT-176) ── */

export type ChallengeKind =
  | 'lockpick'
  | SecretKind
  | 'shield'
  | 'gate'
  | 'seal'
  | 'search'
  | 'watch'
  | 'scout'
  | 'disarm'
  | 'insight';

/** A corridor scouted: what waits at its end and on the way. */
export interface ScoutInfo {
  room_type: string;
  room_name?: string | null;
  mob_count?: number | null;
  trap: boolean;
  ambush: boolean;
  disarmed: boolean;
}

/** Scouting: the corridor's cells and the lamps over them (null — a dark cell). */
export interface ShadowParams {
  cells: number;
  lamps: ({ freq: number; phase: number; duty: number } | null)[];
  time_limit_ms: number;
}

/** Disarming: the rods, how many are taut, slips forgiven, and the rods shown at the start ([index, taut neighbours]). */
export interface WiresParams {
  wires: number;
  taut: number;
  mistakes: number;
  shown: [number, number][];
}

/** Reading: geared rings of a star chart, each off its mark by `offsets` steps (of `steps`). */
export interface StarsParams {
  rings: number;
  steps: number;
  offsets: number[];
  time_limit_ms: number;
  seed: number;
}
export type ChallengeMode = 'game' | 'roll';

/** One pin of the lock: how fast it bobs, where it starts, its shear window (on -1..1). */
export interface LockPin {
  freq: number;
  phase: number;
  center: number;
  width: number;
}

export interface LockpickParams {
  pins: LockPin[];
  /** Misses the pick survives; one more and it breaks. */
  strains: number;
  time_limit_ms: number;
}

/** The illusory wall: runes light up in `sequence`; the mage repeats it. */
export interface RunesParams {
  glyphs: number;
  sequence: number[];
  flash_ms: number;
  /** Wrong runes forgiven. */
  mistakes: number;
  time_limit_ms: number;
}

/** The hidden mechanism: a wall of stones, one hiding the lever. */
export interface MechanismParams {
  cols: number;
  rows: number;
  probes: number;
}

/** The cave-in: stones and their cracks (a hint at which hold the pile up). */
export interface RubbleParams {
  cracks: number[];
  to_clear: number;
  braces: number;
}

/** The party shield: blows from the left (0), above (1) or the right (2), each shown `warn_ms` before it lands. */
export interface ShieldParams {
  blows: { at_ms: number; side: number }[];
  warn_ms: number;
  start_side: number;
  time_limit_ms: number;
}

/** The gate: keep it inside `zone` (0 down … 1 up) for `hold_ms`; surges drag it down harder. */
export interface GateParams {
  zone: [number, number];
  hold_ms: number;
  surges: { at_ms: number; dur_ms: number; force: number }[];
  time_limit_ms: number;
  look?: GateLook;
}

/**
 * The magic seal: nodes on a ring; the sigil starts at `start`. The circle beats every `beat_ms`; of the
 * nodes in `pulsing` the true next one pulses in time (offset 0), the false ones off it by `offsets` (share of a beat).
 */
export interface SealParams {
  nodes: number;
  start: number;
  steps: number;
  mistakes: number;
  beat_ms: number;
  pulsing: number[];
  offsets: number[];
}

/** Searching a room: its floor in tiles, and how many may be looked under. */
export interface SearchParams {
  cols: number;
  rows: number;
  probes: number;
}

export type ChallengeParams =
  | SealParams
  | ShadowParams
  | WiresParams
  | StarsParams
  | SearchParams
  | LockpickParams
  | RunesParams
  | MechanismParams
  | RubbleParams
  | ShieldParams
  | GateParams;

export interface ChallengeResult {
  passed: boolean;
  kind: ChallengeKind;
  /** open / broke / time / short (the game) or rolled (a plain roll). */
  outcome: string;
  message: string;
  corridor_id: number | null;
  character_id: number;
  rolled?: number | null;
  difficulty?: number | null;
  /** The party shield: how firmly it is held, 0..1. */
  block?: number | null;
  /** A search: what was found. */
  loot?: { item_id: number; item_name?: string | null; quantity: number }[] | null;
}

export interface ChallengeStart {
  kind: ChallengeKind;
  off_class: boolean;
  stamina_consumed: number;
  challenge_id?: string | null;
  params?: ChallengeParams | null;
  result?: ChallengeResult | null;
}

export interface ChallengeStep {
  kind: ChallengeKind;
  /** The mechanism: steps from the pressed stone to the lever. */
  distance?: number | null;
  /** The cave-in: the stone came out without bringing anything down. */
  safe?: boolean | null;
  /** The seal: the nodes resonating next, and how far off the beat each pulses. */
  pulsing?: number[] | null;
  offsets?: number[] | null;
  /** A search: the way the traces point, 0 up and clockwise by eighths. */
  way?: number | null;
  /** Disarming: how many of the cut rod's neighbours are taut. */
  near?: number | null;
  /** Set once the game is over. */
  result?: ChallengeResult | null;
}

export interface LightResult {
  /** "spell" — a mage's light for the run; "torch" — until the party leaves. */
  how: 'spell' | 'torch';
  message: string;
  stamina_consumed: number;
}

/** Light a dark room (any living member). */
export const lightRoom = async (sessionId: number, characterId: number): Promise<LightResult> => {
  const { data } = await axios.post<LightResult>(`/dungeons/sessions/${sessionId}/light`, {
    character_id: characterId,
  });
  return data;
};

export const stepChallenge = async (
  sessionId: number,
  characterId: number,
  challengeId: string,
  move: { x?: number; y?: number; index?: number },
): Promise<ChallengeStep> => {
  const { data } = await axios.post<ChallengeStep>(`/dungeons/sessions/${sessionId}/challenges/step`, {
    character_id: characterId,
    challenge_id: challengeId,
    ...move,
  });
  return data;
};

export const startChallenge = async (
  sessionId: number,
  characterId: number,
  kind: ChallengeKind,
  /** The corridor it is tried on; none for the party shield. */
  corridorId: number | null,
  mode: ChallengeMode,
): Promise<ChallengeStart> => {
  const { data } = await axios.post<ChallengeStart>(`/dungeons/sessions/${sessionId}/challenges`, {
    character_id: characterId,
    kind,
    corridor_id: corridorId,
    mode,
  });
  return data;
};

export const finishChallenge = async (
  sessionId: number,
  characterId: number,
  challengeId: string,
  presses: number[],
): Promise<ChallengeResult> => {
  const { data } = await axios.post<ChallengeResult>(`/dungeons/sessions/${sessionId}/challenges/finish`, {
    character_id: characterId,
    challenge_id: challengeId,
    presses,
  });
  return data;
};

export const pickLock = async (sessionId: number, characterId: number, corridorId: number): Promise<PickLockResponse> => {
  const { data } = await axios.post<PickLockResponse>(`/dungeons/sessions/${sessionId}/pick-lock`, {
    character_id: characterId,
    corridor_id: corridorId,
  });
  return data;
};

export const interactWithRoom = async (
  sessionId: number,
  characterId: number,
  action: InteractAction,
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

// --- Loot Distribution + Finalization ---

export interface LootDistribution {
  item_id: number;
  to_character_id: number;
  quantity: number;
}

export interface DistributeLootResponse {
  success: boolean;
  message: string;
  remaining_inventory: GroupInventoryItem[];
  /** Deliveries inventory-service refused; those items went back to the group inventory. */
  failed: LootDistribution[];
}

export interface FinalizeResponse {
  message: string;
  cooldown_until: string | null;
  /** Units of loot dropped by a forced close. */
  items_lost: number;
}

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

/** Close a completed/escaped run. Leftover loot needs `force` (it is lost). */
export const finalizeSession = async (
  sessionId: number,
  characterId: number,
  force = false,
): Promise<FinalizeResponse> => {
  const { data } = await axios.post<FinalizeResponse>(
    `/dungeons/sessions/${sessionId}/finalize`,
    { character_id: characterId, force },
  );
  return data;
};
