/**
 * FEAT-181 — admin «Экономика» (character-service `/characters/admin/economy/*`).
 * Amounts are integers in the world currency; treasuries may be negative.
 */
import type { CurrencyForms } from '../utils/currency';

export type EconAccountKind =
  | 'character'
  | 'region_treasury'
  | 'country_treasury'
  | 'world_treasury'
  | 'auction_escrow'
  | 'auction_storage'
  | 'emission'
  | 'adjustment';

export type EconLegType = 'main' | 'refund' | 'commission' | 'tax';

export interface EconTotals {
  issued: number;
  held: number;
  players: number;
  npcs: number;
  escrow: number;
  auction_storage: number;
  region_treasuries: number;
  country_treasuries: number;
  world_treasury: number;
}

export interface EconDriftingCharacter {
  character_id: number;
  name: string | null;
  balance: number;
  ledger: number;
}

export interface EconInvariant {
  ok: boolean;
  ledger_sum: number;
  escrow_expected: number;
  escrow_actual: number;
  storage_expected: number;
  storage_actual: number;
  drifting_characters: EconDriftingCharacter[];
}

export interface EconRegionTreasury {
  account_id: number;
  region_id: number;
  name: string | null;
  balance: number;
  is_active: boolean;
}

export interface EconCountryTreasury {
  /** null only for the «Без страны» group of regions without a known country */
  account_id: number | null;
  country_id: number | null;
  name: string | null;
  balance: number;
  is_active: boolean;
  regions: EconRegionTreasury[];
}

export interface EconSystemAccount {
  account_id: number;
  kind: EconAccountKind;
  name: string | null;
  balance: number;
}

export interface EconSummary {
  currency: CurrencyForms;
  totals: EconTotals;
  invariant: EconInvariant;
  countries: EconCountryTreasury[];
  system_accounts: EconSystemAccount[];
  settings: { country_tax_rate: number };
}

export interface EconAccount {
  account_id: number;
  kind: EconAccountKind;
  ref_id: number;
  name: string | null;
  balance: number;
  is_active: boolean;
}

export interface EconPage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface EconPostingAccount {
  account_id: number;
  kind: EconAccountKind | null;
  ref_id: number | null;
  name: string | null;
}

export interface EconPosting {
  from: EconPostingAccount;
  to: EconPostingAccount;
  amount: number;
  leg_type: EconLegType;
}

export interface EconOperation {
  id: number;
  op_type: string;
  created_at: string;
  source_service: string;
  location_id: number | null;
  region_id: number | null;
  actor_user_id: number | null;
  comment: string | null;
  metadata: Record<string, unknown> | null;
  postings: EconPosting[];
}

export interface EconAccountsParams {
  kind?: EconAccountKind;
  q?: string;
  page?: number;
  page_size?: number;
}

export interface EconOperationsParams {
  account_id?: number;
  op_type?: string;
  region_id?: number;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export interface EconActionResult {
  operation_id: number | null;
  account_id: number;
  balance: number;
}

export interface EconSettings {
  currency: CurrencyForms;
  country_tax_rate: number;
}
