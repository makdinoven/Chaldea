import axios from 'axios';

/**
 * FEAT-197 admin «Репутация» API (character-service, `/characters/admin/reputation/*`).
 * Auth header comes from axiosSetup. Player endpoints live in `api/reputation.ts`.
 *
 * RBAC: reads need `reputation:read`; settings / actions / NPC-role weights writes need
 * `reputation:settings` (admin only); the per-character adjust needs `reputation:manage`.
 */
const BASE = '/characters/admin/reputation';

/** The 8 fixed tier codes, low → high (`reputation_core.TIER_CODES`). Names / thresholds are editable. */
export const REPUTATION_TIER_CODES = [
  'outlaw',
  'outcast',
  'watched',
  'wanderer',
  'familiar',
  'trusted',
  'defender',
  'legend',
] as const;

export type ReputationTierCode = (typeof REPUTATION_TIER_CODES)[number];

/** Seed names — used only when the live settings cannot be read (no `reputation:read`). */
export const DEFAULT_TIER_NAMES: Record<ReputationTierCode, string> = {
  outlaw: 'Вне закона',
  outcast: 'Изгой',
  watched: 'На заметке',
  wanderer: 'Скиталец',
  familiar: 'Знакомое лицо',
  trusted: 'Свой человек',
  defender: 'Заступник',
  legend: 'Легенда края',
};

/** Fallback weight of a quest without its own «репутация за задание» (built-in action `quest_complete`). */
export const DEFAULT_QUEST_REPUTATION = 10;

export interface ReputationSettingsValues {
  min_value: number;
  max_value: number;
  echo_pct: number;
  decay_per_day: number;
}

export interface ReputationTierAdmin {
  code: string;
  name: string;
  /** null only for the lowest tier */
  min_value: number | null;
  /** + discount, − markup at merchants (−100..+50) */
  price_pct: number;
  /** what merchants pay the player: 0 or negative (−100..0) */
  sell_pct: number;
  trade_refused: boolean;
  sort_order?: number;
}

export interface ReputationSettingsData {
  settings: ReputationSettingsValues;
  tiers: ReputationTierAdmin[];
}

export interface ReputationAction {
  code: string;
  name: string;
  points: number;
  daily_cap: number | null;
  is_builtin: boolean;
  has_source: boolean;
  sort_order: number;
}

export interface ReputationActionUpdateBody {
  name: string;
  points: number;
  daily_cap: number | null;
  sort_order?: number | null;
}

export interface ReputationActionCreateBody extends ReputationActionUpdateBody {
  code: string;
}

export interface ReputationRoleWeight {
  role: string;
  points: number;
}

export interface ReputationAdminRegion {
  region_id: number;
  region_name: string | null;
  country_id: number | null;
  country_name: string | null;
  /** effective value (decay applied) */
  value: number;
  tier_code: string;
  tier_name: string;
  decaying: boolean;
  updated_at: string | null;
}

export interface ReputationAdminHistoryItem {
  id: number;
  created_at: string;
  region_id: number;
  region_name: string | null;
  action: string;
  action_name: string;
  event_key: string;
  is_echo: boolean;
  origin_region_id: number | null;
  origin_region_name: string | null;
  requested_delta: number;
  applied_delta: number;
  value_after: number;
  tier_before: string;
  tier_before_name: string;
  tier_after: string;
  tier_after_name: string;
  reason: string | null;
  actor_user_id: number | null;
  actor_username: string | null;
}

export interface ReputationAdminHistoryPage {
  items: ReputationAdminHistoryItem[];
  total: number;
}

export interface ReputationAdjustBody {
  region_id: number;
  delta?: number;
  action_code?: string;
  reason: string;
  echo: boolean;
  request_id: string;
}

export interface ReputationChange {
  region_id: number;
  is_echo: boolean;
  value_before: number;
  value_after: number;
  tier_before: string;
  tier_after: string;
}

export interface ReputationAdjustResult {
  changes: ReputationChange[];
  duplicate: boolean;
}

export const fetchReputationSettings = async (): Promise<ReputationSettingsData> => {
  const { data } = await axios.get<ReputationSettingsData>(`${BASE}/settings`);
  return data;
};

export const putReputationSettings = async (body: ReputationSettingsData): Promise<ReputationSettingsData> => {
  const { data } = await axios.put<ReputationSettingsData>(`${BASE}/settings`, body);
  return data;
};

export const fetchReputationActions = async (): Promise<ReputationAction[]> => {
  const { data } = await axios.get<ReputationAction[]>(`${BASE}/actions`);
  return data;
};

export const createReputationAction = async (body: ReputationActionCreateBody): Promise<ReputationAction> => {
  const { data } = await axios.post<ReputationAction>(`${BASE}/actions`, body);
  return data;
};

export const updateReputationAction = async (
  code: string,
  body: ReputationActionUpdateBody,
): Promise<ReputationAction> => {
  const { data } = await axios.put<ReputationAction>(`${BASE}/actions/${encodeURIComponent(code)}`, body);
  return data;
};

export const deleteReputationAction = async (code: string): Promise<void> => {
  await axios.delete(`${BASE}/actions/${encodeURIComponent(code)}`);
};

export const fetchReputationNpcRoles = async (): Promise<ReputationRoleWeight[]> => {
  const { data } = await axios.get<ReputationRoleWeight[]>(`${BASE}/npc-roles`);
  return data;
};

export const putReputationNpcRoles = async (body: ReputationRoleWeight[]): Promise<ReputationRoleWeight[]> => {
  const { data } = await axios.put<ReputationRoleWeight[]>(`${BASE}/npc-roles`, body);
  return data;
};

export const fetchCharacterReputationAdmin = async (characterId: number): Promise<ReputationAdminRegion[]> => {
  const { data } = await axios.get<ReputationAdminRegion[]>(`${BASE}/characters/${characterId}`);
  return data;
};

export const fetchCharacterReputationHistoryAdmin = async (
  characterId: number,
  params: { region_id?: number | null; page: number; page_size: number },
): Promise<ReputationAdminHistoryPage> => {
  const query: Record<string, number> = { page: params.page, page_size: params.page_size };
  if (params.region_id) query.region_id = params.region_id;
  const { data } = await axios.get<ReputationAdminHistoryPage>(`${BASE}/characters/${characterId}/history`, {
    params: query,
  });
  return data;
};

export const postCharacterReputationAdjust = async (
  characterId: number,
  body: ReputationAdjustBody,
): Promise<ReputationAdjustResult> => {
  const { data } = await axios.post<ReputationAdjustResult>(`${BASE}/characters/${characterId}/adjust`, body);
  return data;
};

/** A fresh UUID v4 for `request_id` (one per submit — a double click becomes a duplicate, not a second change). */
export const newRequestId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};
