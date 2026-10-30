import axios from 'axios';

/**
 * Public player region card (FEAT-182, character-service, contract 3.7).
 * Qualitative states only — the backend never sends balances or raw prices.
 */

export interface RegionCardState {
  state: string;
  label: string;
}

export type RegionGroupLevel = 'very_low' | 'low' | 'normal' | 'high' | 'very_high';
export type RegionGroupTrend = 'up' | 'down' | 'flat';

export interface RegionCardGroup {
  code: string;
  name: string;
  level: RegionGroupLevel;
  trend: RegionGroupTrend;
}

interface RegionCardHidden {
  region_id: number;
  participating: false;
  /** FEAT-184: the region has an enabled bank */
  has_bank?: boolean;
}

export interface RegionCardData {
  region_id: number;
  participating: true;
  updated_at: string | null;
  food: RegionCardState;
  treasury: RegionCardState;
  stability: RegionCardState;
  prosperity: RegionCardState;
  price_level: RegionCardState;
  shortages: string[];
  surpluses: string[];
  phrases: string[];
  groups: RegionCardGroup[];
  /** FEAT-184: the region has an enabled bank */
  has_bank?: boolean;
  /** FEAT-187: active region events (optional — older backends don't send it) */
  events?: RegionCardEvent[];
}

/** FEAT-187: an active region event as players see it — no effect numbers. */
export interface RegionCardEvent {
  code: string;
  name: string;
  icon: string;
  kind: 'good' | 'bad';
  text: string;
  started_at: string;
  ends_at: string;
}

export type RegionCardResponse = RegionCardHidden | RegionCardData;

export const fetchRegionEconomyCard = async (regionId: number): Promise<RegionCardResponse> => {
  const { data } = await axios.get<RegionCardResponse>(`/characters/economy/regions/${regionId}/card`);
  return data;
};
