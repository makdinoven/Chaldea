import axios from 'axios';

/**
 * FEAT-197 — player view of region reputation (character-service, contract 3.5).
 * Private (owner / staff only); the backend never sends the numeric value —
 * only the tier and the position inside it (`progress`, 0..1).
 * Admin endpoints live in `reputationAdmin.ts`.
 */

export interface ReputationTierBrief {
  code: string;
  name: string;
  /** lowest tier first */
  sort_order: number;
}

export interface ReputationRegion {
  region_id: number;
  region_name: string | null;
  country_id: number | null;
  country_name: string | null;
  tier_code: string;
  tier_name: string;
  /** 0..1 inside the tier band (no numbers are shown to the player) */
  progress: number;
  /** merchants of the region refuse to trade (Вне закона) */
  trade_refused: boolean;
}

export interface ReputationView {
  regions: ReputationRegion[];
  tiers: ReputationTierBrief[];
}

export type ReputationDirection = 'up' | 'down';

export interface ReputationHistoryItem {
  created_at: string;
  region_id: number;
  region_name: string | null;
  direction: ReputationDirection;
  action_name: string;
  /** Russian phrase built by the server, no numbers */
  text: string;
  tier_after_name: string;
  tier_changed: boolean;
}

export interface ReputationHistoryPage {
  items: ReputationHistoryItem[];
  total: number;
}

/** Backend limit for `page_size` of the journal. */
export const REPUTATION_HISTORY_PAGE_MAX = 50;

/** All visited regions, or exactly one region (Скиталец when never visited) with `regionId`. */
export const fetchReputation = async (
  characterId: number,
  regionId?: number,
): Promise<ReputationView> => {
  const params: Record<string, number> = {};
  if (regionId != null) params.region_id = regionId;
  const { data } = await axios.get<ReputationView>(`/characters/${characterId}/reputation`, { params });
  return data;
};

export const fetchReputationHistory = async (
  characterId: number,
  page: number,
  pageSize: number,
  regionId?: number,
): Promise<ReputationHistoryPage> => {
  const params: Record<string, number> = {
    page,
    page_size: Math.min(pageSize, REPUTATION_HISTORY_PAGE_MAX),
  };
  if (regionId != null) params.region_id = regionId;
  const { data } = await axios.get<ReputationHistoryPage>(
    `/characters/${characterId}/reputation/history`,
    { params },
  );
  return data;
};

/** Merchant price explanation (locations-service `PriceReason`). */
export interface PriceReason {
  source: 'charisma' | 'reputation';
  /** signed in the player's favour: + discount, − markup / bid cut */
  percent: number;
  label: string;
}
