import axios from 'axios';

/**
 * FEAT-209 — admin NPC «Готов» flag (character-service,
 * `PUT /characters/admin/npcs/{id}/ready`, needs `npcs:update`).
 * Country / region options moved to `api/adminGeo.ts`, `readyTooltip` to
 * `components/Admin/ExpandableList/readyMark.ts` (FEAT-210).
 */

export interface NpcReadyResponse {
  id: number;
  npc_ready: boolean;
  npc_ready_at: string | null;
  npc_ready_by: string | null;
}

export const setNpcReady = async (npcId: number, ready: boolean): Promise<NpcReadyResponse> => {
  const { data } = await axios.put<NpcReadyResponse>(`/characters/admin/npcs/${npcId}/ready`, { ready });
  return data;
};

/* ---------------------------------------------------------------- FEAT-211 «Скупщик» settings (A11/A12) */

/** Bounds of the fence settings — mirror `fence_schemas.py` (feature file 3.11). */
export const FENCE_PRICE_PCT_MIN = 1;
export const FENCE_PRICE_PCT_MAX = 100;
export const FENCE_PRICE_PCT_DEFAULT = 40;
export const FENCE_CASH_TARGET_MAX = 10_000_000;
export const FENCE_CASH_TARGET_DEFAULT = 2000;

export interface FenceSettingsIn {
  is_active: boolean;
  /** % of the region market value paid per bale */
  price_pct: number;
  /** goods group codes; empty = all 12 groups */
  accepted_groups: string[];
  /** the 6 h refill tops the fence's cash up to this */
  cash_target: number;
}

export interface FenceSettingsOut extends FenceSettingsIn {
  npc_id: number;
  /** current cash of the fence NPC */
  cash: number;
  region_id: number | null;
  region_name: string | null;
  /** the fence's region takes part in the economy tick (its cash is refilled) */
  refill_active: boolean;
}

/** `GET /characters/admin/npcs/{id}/fence` (npcs:read) — defaults when nothing is saved yet. */
export const fetchFenceSettings = async (npcId: number): Promise<FenceSettingsOut> => {
  const { data } = await axios.get<FenceSettingsOut>(`/characters/admin/npcs/${npcId}/fence`);
  return data;
};

/** `PUT /characters/admin/npcs/{id}/fence` (npcs:update); 409 when the NPC is not a fence. */
export const saveFenceSettings = async (npcId: number, body: FenceSettingsIn): Promise<FenceSettingsOut> => {
  const { data } = await axios.put<FenceSettingsOut>(`/characters/admin/npcs/${npcId}/fence`, body);
  return data;
};
