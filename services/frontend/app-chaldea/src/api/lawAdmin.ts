import axios from 'axios';

/**
 * FEAT-198 admin «Закон» API (character-service, `/characters/admin/law/*`).
 * Auth header comes from axiosSetup. Player endpoints live in `api/law.ts`.
 *
 * RBAC (no new permissions): reads need `reputation:read`; the settings write needs
 * `reputation:settings` (admin); release / clear wanted need `reputation:manage`.
 */
const BASE = '/characters/admin/law';

/** The 5 fixed wanted level codes, low → high (`law_core.LEVEL_CODES`). Names / numbers are editable. */
export const LAW_LEVEL_CODES = ['suspect', 'offender', 'criminal', 'villain', 'enemy'] as const;

/** Backend limits mirrored for client-side validation (`law_core`, `schemas`). */
export const LAW_JAIL_HOURS_MIN = 1;
export const LAW_JAIL_HOURS_MAX = 168;
export const LAW_HOURS_MAX = 168;
export const LAW_MAX_WANTED_LIMIT = 100_000;
export const LAW_MAX_FINE = 1_000_000;
export const LAW_BAIL_MULTIPLIER_MIN = 1;
export const LAW_BAIL_MULTIPLIER_MAX = 10;
export const LAW_REASON_MIN = 3;
export const LAW_REASON_MAX = 500;

export interface LawSettingsValues {
  max_wanted: number;
  decay_per_day: number;
  heavy_wanted: number;
  outlaw_min_level: string;
  encounter_timeout_hours: number;
  guard_ko_hours: number;
  flee_base_pct: number;
  flee_per_point_pct: number;
  flee_min_pct: number;
  flee_max_pct: number;
  escape_base_pct: number;
  escape_per_point_pct: number;
  escape_min_pct: number;
  escape_max_pct: number;
  escape_cooldown_hours: number;
  escape_fail_extend_pct: number;
  max_remaining_jail_hours: number;
  bail_multiplier: number;
}

export interface LawLevel {
  code: string;
  sort_order?: number | null;
  name: string;
  min_value: number;
  fine: number;
  jail_hours: number;
}

export interface LawSettingsData {
  settings: LawSettingsValues;
  levels: LawLevel[];
}

export interface LawAdminWanted {
  region_id: number;
  region_name: string | null;
  value: number;
  level_code: string | null;
  level_name: string | null;
}

export interface LawAdminEncounter {
  id: number;
  character_id: number;
  region_id: number;
  region_name: string | null;
  location_id: number;
  from_location_id: number | null;
  guard_npc_id: number | null;
  guard_name: string | null;
  guard_avatar: string | null;
  is_outlaw: boolean;
  has_jail: boolean;
  level_code: string;
  level_name: string | null;
  wanted_value: number;
  fine: number;
  jail_hours: number;
  options: string[];
  flee_chance_pct: number | null;
  flee_used: boolean;
  source: string;
  status: string;
  battle_id: number | null;
  expires_at: string;
  created_at: string;
  fight_started_at: string | null;
  resolved_at: string | null;
}

export interface LawAdminJail {
  id: number;
  region_id: number;
  region_name: string | null;
  location_id: number;
  location_name: string | null;
  until: string;
  bail_price: number;
  can_escape_at: string | null;
  escape_chance_pct: number;
  escape_attempts: number;
  status: string;
  level_code: string;
  encounter_id: number | null;
  started_at: string;
}

export interface LawCrime {
  id: number;
  crime_type: string;
  region_id: number;
  region_name: string | null;
  location_id: number | null;
  victim_character_id: number | null;
  battle_id: number | null;
  wanted_points: number;
  wanted_applied: number;
  status: string;
  created_at: string;
  /* FEAT-199 (staff only) */
  masked: boolean;
  witness_chance_pct: number | null;
  witness_roll_pct: number | null;
  reputation_delta: number | null;
  wanted_floor: number | null;
  reveal_attempts: number;
  next_roll_at: string | null;
  reveal_until: string | null;
  revealed_at: string | null;
}

export interface LawLogEntry {
  id: number;
  created_at: string;
  action: string;
  region_id: number | null;
  region_name: string | null;
  wanted_before: number | null;
  wanted_after: number | null;
  amount: number | null;
  chance_pct: number | null;
  roll_pct: number | null;
  ref_id: number | null;
  reason: string | null;
  actor_user_id: number | null;
  actor_username: string | null;
}

/** FEAT-199: hidden numbers of fame / infamy (staff only). */
export interface LawRenownAdmin {
  fame: number;
  fame_tier_name: string;
  infamy: number;
  infamy_tier_name: string;
}

export interface LawRenownLogEntry {
  id: number;
  created_at: string;
  scale: string;
  source: string;
  delta: number;
  value_after: number;
  tier_before: string;
  tier_after: string;
  ref_id: number | null;
  reason: string | null;
  actor_user_id: number | null;
}

export interface LawAdminCharacter {
  wanted: LawAdminWanted[];
  encounter: LawAdminEncounter | null;
  jail: LawAdminJail | null;
  crimes: LawCrime[];
  log: LawLogEntry[];
  /* FEAT-199 */
  renown: LawRenownAdmin | null;
  renown_log: LawRenownLogEntry[];
}

export interface LawReleaseResult {
  message: string;
  released: boolean;
  cancelled: boolean;
  duplicate: boolean;
}

export interface LawClearResult {
  message: string;
  cleared_region_ids: number[];
  duplicate: boolean;
}

export const fetchLawSettings = async (): Promise<LawSettingsData> => {
  const { data } = await axios.get<LawSettingsData>(`${BASE}/settings`);
  return data;
};

export const putLawSettings = async (body: LawSettingsData): Promise<LawSettingsData> => {
  const { data } = await axios.put<LawSettingsData>(`${BASE}/settings`, body);
  return data;
};

export const fetchCharacterLawAdmin = async (characterId: number): Promise<LawAdminCharacter> => {
  const { data } = await axios.get<LawAdminCharacter>(`${BASE}/characters/${characterId}`);
  return data;
};

/** Release from jail and/or cancel an open guard encounter. `request_id` — new per submit. */
export const postLawRelease = async (
  characterId: number,
  body: { reason: string; request_id: string },
): Promise<LawReleaseResult> => {
  const { data } = await axios.post<LawReleaseResult>(`${BASE}/characters/${characterId}/release`, body);
  return data;
};

/** Clear the wanted value in one region, or in every region when `region_id` is null. */
export const postLawClearWanted = async (
  characterId: number,
  body: { region_id: number | null; reason: string; request_id: string },
): Promise<LawClearResult> => {
  const { data } = await axios.post<LawClearResult>(`${BASE}/characters/${characterId}/clear-wanted`, body);
  return data;
};
