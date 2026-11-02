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
  /** FEAT-191: the region is a capital with a working mint */
  has_mint?: boolean;
  /** FEAT-192: always empty lists for a hidden region */
  caravans?: RegionCardCaravans;
  /** FEAT-193: always empty for a hidden region */
  guild_wants?: RegionCardGuildWant[];
}

/** FEAT-194 (3.11): coarse word per class — the page turns it into a bar width, no shares leave the API. */
export type RegionClassAmount = 'few' | 'some' | 'many';
export type RegionClassState = 'poor' | 'modest' | 'wealthy' | 'rich';

export interface RegionCardClasses {
  state: RegionClassState;
  /** «Зажиточный город, много бедняков» — also sent as `phrases[0]` */
  label: string;
  bar: {
    poor: RegionClassAmount;
    middling: RegionClassAmount;
    rich: RegionClassAmount;
  };
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
  /** FEAT-191: the region is a capital with a working mint */
  has_mint?: boolean;
  /** FEAT-187: active region events (optional — older backends don't send it) */
  events?: RegionCardEvent[];
  /** FEAT-192: caravans to / from the region (optional — older backends don't send it) */
  caravans?: RegionCardCaravans;
  /** FEAT-193: goods groups the regional guild has open, payable orders for (optional — older backends don't send it) */
  guild_wants?: RegionCardGuildWant[];
  /** FEAT-194: social classes in words (absent / null when classes are off or the region has no shares) */
  classes?: RegionCardClasses | null;
}

/** FEAT-193 (3.9): a goods group the guild of the region is looking for — words only, no units or money. */
export interface RegionCardGuildWant {
  group_code: string;
  group_name: string;
}

/**
 * FEAT-192 (3.12): one caravan line as players see it — goods group and the other region, never units or money.
 * `country_name` / `foreign` are filled only when the other region is in another country.
 */
export interface CaravanCardLine {
  group_code: string;
  group_name: string;
  region_id: number;
  region_name: string;
  country_name: string | null;
  foreign: boolean;
  /** true — still on the road; false — arrived within the last day */
  in_transit: boolean;
}

export interface RegionCardCaravans {
  incoming: CaravanCardLine[];
  outgoing: CaravanCardLine[];
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
