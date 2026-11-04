import axios from 'axios';

/**
 * FEAT-199 admin «Тень и слава» API (character-service, `/characters/admin/shadow/*`).
 * Auth header comes from axiosSetup. The player side (renown, fame-tier names on profiles) lives in its own module.
 *
 * RBAC (no new permissions): reads need `reputation:read`; the settings write needs `reputation:settings`
 * (admin); reveal / close / renown adjust need `reputation:manage`.
 */
const BASE = '/characters/admin/shadow';

/** The fixed tier codes, low → high (`shadow_core.FAME_CODES` / `INFAMY_CODES`). Names / thresholds are editable. */
export const FAME_TIER_CODES = ['nameless', 'familiar', 'known', 'famous', 'legend'] as const;
export const INFAMY_TIER_CODES = ['none', 'whispers', 'rumored', 'notorious', 'dreaded'] as const;

/** Seed names — used by the quest editor when the live list cannot be loaded (codes are fixed). */
export const DEFAULT_FAME_TIER_NAMES: Record<string, string> = {
  nameless: 'Безвестный',
  familiar: 'Знакомое имя',
  known: 'Известный',
  famous: 'Знаменитый',
  legend: 'Легенда',
};

/** Backend limits mirrored for client-side validation (`shadow_core`, `schemas`). */
export const SHADOW_PAGE_SIZE = 20;
export const SHADOW_MAX_PER_POINT = 10;
export const SHADOW_MAX_RATIO = 10;
export const SHADOW_MAX_REVEAL_DAYS = 30;
export const SHADOW_MAX_SUSPICION = 10_000;
export const SHADOW_MAX_FAME_QUEST = 1000;
export const SHADOW_MAX_INFAMY_MIN_GAIN = 1000;
export const SHADOW_MAX_TIER_WITNESS_PCT = 50;
export const SHADOW_MAX_TIER_VALUE = 10_000_000;
export const SHADOW_MAX_DECAY_PER_DAY = 100_000;
export const RENOWN_ADJUST_MAX = 10_000;
/** Quest `fame_reward` bounds (locations-service) and the default used when it is empty. */
export const QUEST_FAME_REWARD_MAX = 1000;
export const QUEST_FAME_REWARD_DEFAULT = 5;

export interface ShadowSettingsValues {
  witness_enabled: boolean;
  witness_base_safe_pct: number;
  witness_base_farm_pct: number;
  witness_base_dangerous_pct: number;
  witness_base_dungeon_pct: number;
  witness_base_default_pct: number;
  witness_stealth_per_point_pct: number;
  witness_agent_pct: number;
  witness_assassin_pct: number;
  witness_trickster_pct: number;
  witness_mask_pct: number;
  witness_group_per_extra_pct: number;
  witness_min_pct: number;
  witness_max_pct: number;
  reveal_days: number;
  reveal_base_pct: number;
  reveal_per_suspicion_pct: number;
  reveal_mask_factor_pct: number;
  reveal_min_pct: number;
  reveal_max_pct: number;
  suspicion_max: number;
  suspicion_unwitnessed: number;
  suspicion_masked: number;
  suspicion_decay_per_day: number;
  suspicion_uneasy_at: number;
  suspicion_alarmed_at: number;
  suspicion_fear_at: number;
  infamy_ratio: number;
  infamy_min_gain: number;
  fame_quest_default: number;
  fame_rep_ratio: number;
  fame_guild_ratio: number;
}

export interface FameTierAdmin {
  code: string;
  sort_order?: number | null;
  name: string;
  min_value: number;
  witness_pct: number;
}

export interface InfamyTierAdmin {
  code: string;
  sort_order?: number | null;
  name: string;
  min_value: number;
}

export interface ShadowSettingsData {
  settings: ShadowSettingsValues;
  fame_tiers: FameTierAdmin[];
  infamy_tiers: InfamyTierAdmin[];
}

/** `open` = unwitnessed + masked (default). */
export type ShadowCrimeFilter = 'open' | 'unwitnessed' | 'masked' | 'reported' | 'closed' | 'all';

export interface ShadowCrime {
  id: number;
  character_id: number;
  character_name: string | null;
  crime_type: string;
  region_id: number;
  region_name: string | null;
  location_id: number | null;
  location_name: string | null;
  victim_id: number | null;
  victim_name: string | null;
  status: string;
  masked: boolean;
  witness_chance_pct: number | null;
  witness_roll_pct: number | null;
  reputation_delta: number | null;
  wanted_points: number;
  wanted_floor: number | null;
  reveal_attempts: number;
  next_roll_at: string | null;
  reveal_until: string | null;
  created_at: string;
  resolved_at: string | null;
  revealed_at: string | null;
}

export interface ShadowCrimesPage {
  items: ShadowCrime[];
  total: number;
}

export interface ShadowCrimesQuery {
  status: ShadowCrimeFilter;
  region_id?: number | null;
  character_id?: number | null;
  page: number;
  page_size?: number;
}

export interface ShadowCrimeActionResult {
  message: string;
  crime: ShadowCrime;
}

export interface RegionSuspicion {
  region_id: number;
  region_name: string | null;
  value: number;
  code: string;
  label: string;
}

export type RenownScale = 'fame' | 'infamy';

export interface RenownAdjustResult {
  scale: RenownScale;
  value_before: number;
  value_after: number;
  tier_before: string;
  tier_after: string;
  duplicate: boolean;
}

export interface FameTierPublic {
  code: string;
  name: string;
  sort_order: number;
}

export const fetchShadowSettings = async (): Promise<ShadowSettingsData> => {
  const { data } = await axios.get<ShadowSettingsData>(`${BASE}/settings`);
  return data;
};

export const putShadowSettings = async (body: ShadowSettingsData): Promise<ShadowSettingsData> => {
  const { data } = await axios.put<ShadowSettingsData>(`${BASE}/settings`, body);
  return data;
};

export const fetchShadowCrimes = async (q: ShadowCrimesQuery): Promise<ShadowCrimesPage> => {
  const params: Record<string, string | number> = {
    status: q.status,
    page: q.page,
    page_size: q.page_size ?? SHADOW_PAGE_SIZE,
  };
  if (q.region_id) params.region_id = q.region_id;
  if (q.character_id) params.character_id = q.character_id;
  const { data } = await axios.get<ShadowCrimesPage>(`${BASE}/crimes`, { params });
  return data;
};

/** Staff reveal: applies the stored reputation + wanted once and notifies the player. `request_id` — new per submit. */
export const postShadowReveal = async (
  crimeId: number,
  body: { reason: string; request_id: string },
): Promise<ShadowCrimeActionResult> => {
  const { data } = await axios.post<ShadowCrimeActionResult>(`${BASE}/crimes/${crimeId}/reveal`, body);
  return data;
};

/** Staff close: the case is closed forever without consequences (no player notification). */
export const postShadowClose = async (
  crimeId: number,
  body: { reason: string; request_id: string },
): Promise<ShadowCrimeActionResult> => {
  const { data } = await axios.post<ShadowCrimeActionResult>(`${BASE}/crimes/${crimeId}/close`, body);
  return data;
};

export const fetchRegionsSuspicion = async (): Promise<RegionSuspicion[]> => {
  const { data } = await axios.get<RegionSuspicion[]>(`${BASE}/regions/suspicion`);
  return data;
};

export const postRenownAdjust = async (
  characterId: number,
  body: { scale: RenownScale; delta: number; reason: string; request_id: string },
): Promise<RenownAdjustResult> => {
  const { data } = await axios.post<RenownAdjustResult>(`${BASE}/characters/${characterId}/renown-adjust`, body);
  return data;
};

/** Public fame tier names (no auth) — for the quest editor's «Мин. слава». */
export const fetchFameTierNames = async (): Promise<FameTierPublic[]> => {
  const { data } = await axios.get<FameTierPublic[]>('/characters/renown/fame-tiers');
  return data;
};
