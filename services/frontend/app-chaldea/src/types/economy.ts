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
  | 'adjustment'
  | 'population_purse';

export type EconLegType = 'main' | 'refund' | 'commission' | 'tax' | 'trade_tax';

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
  /** FEAT-182: all population purses (already counted in `held`) */
  population_purses?: number;
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
  /** FEAT-182: the region's population purse, if it exists */
  purse_account_id?: number | null;
  purse_balance?: number | null;
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
  /** FEAT-182: hide one op type (the journal hides `region_tick` by default) */
  exclude_op_type?: string;
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

/* ------------------------------------------------------------------------------------------------
 * FEAT-182 — living regions (character-service, contract: feature file section 3.7).
 * Decimals arrive as JSON numbers, amounts as integers.
 * ---------------------------------------------------------------------------------------------- */

export type EconNounGender = 'm' | 'f' | 'n';

/** One row of `GET /admin/economy/regions` — every `Regions` row, simulated or not. */
export interface EconRegionItem {
  region_id: number;
  name: string | null;
  country_id: number | null;
  country_name: string | null;
  template_code: string | null;
  template_name: string | null;
  population: number;
  tax_rate: number;
  stability: number;
  prosperity: number;
  hunger: number;
  satisfaction: number;
  purse: number;
  treasury: number;
  treasury_target: number;
  last_income: number;
  last_tax: number;
  last_wages: number;
  last_grant: number;
  last_tick_at: string | null;
  simulated: boolean;
}

export interface EconRegionGoods {
  group_code: string;
  name: string;
  production_per_1000: number;
  consumption_mult: number;
  stock: number;
  norm_stock: number;
  price_mult: number;
  prev_price_mult: number;
  last_produced: number;
  last_consumed: number;
  last_demand: number;
  last_spoiled: number;
}

export interface EconRegionDetail extends EconRegionItem {
  goods: EconRegionGoods[];
}

export interface EconRegionGoodsUpdate {
  group_code: string;
  production_per_1000: number;
  consumption_mult: number;
  stock?: number;
}

export interface EconRegionUpdate {
  template_code: string | null;
  population: number;
  tax_rate: number;
  stability?: number;
  prosperity?: number;
  goods?: EconRegionGoodsUpdate[];
}

export interface EconApplyTemplateBody {
  reset_stocks?: boolean;
}

export interface EconFillBody {
  /** Default: every region with a template */
  region_ids?: number[];
  population_from_template?: boolean;
  reset_stocks?: boolean;
  fund_purses?: boolean;
  /** Also top up each region treasury to its wage reserve (backend default true) */
  treasury_to_reserve?: boolean;
  comment: string;
}

export interface EconFillResult {
  regions: number;
  /** Last posted operation (one `admin_emission` per region), null when nothing was emitted */
  operation_id: number | null;
  operation_ids: number[];
  /** emitted_purses + emitted_treasuries */
  emitted: number;
  emitted_purses: number;
  emitted_treasuries: number;
  /** Regions with population 0: goods filled, no money */
  skipped_no_population: number[];
}

/** Per-group snapshot inside a history row. */
export interface EconHistoryGoods {
  stock: number;
  price_mult: number;
  produced: number;
  consumed: number;
}

/** One `econ_region_history` row (newest first). */
export interface EconRegionHistoryRow {
  id: number;
  run_id: number;
  region_id: number;
  created_at: string;
  population: number;
  stability: number;
  prosperity: number;
  hunger: number;
  purse: number;
  treasury: number;
  income: number;
  tax: number;
  wages: number;
  grant_amount: number;
  goods: Record<string, EconHistoryGoods>;
}

export interface EconGroupInput {
  input_code: string;
  ratio: number;
}

export interface EconGoodsGroup {
  code: string;
  name: string;
  sort_order: number;
  is_food: boolean;
  base_price: number;
  norm_per_1000: number;
  norm_days: number;
  prosperity_elasticity: number;
  price_elasticity: number;
  inputs: EconGroupInput[];
  updated_at?: string | null;
}

export interface EconGoodsGroupUpdate {
  name: string;
  base_price: number;
  norm_per_1000: number;
  norm_days: number;
  prosperity_elasticity: number;
  price_elasticity: number;
  inputs: EconGroupInput[];
}

export interface EconTemplateGoods {
  group_code: string;
  production_per_1000: number;
  consumption_mult: number;
}

export interface EconRegionTemplate {
  code: string;
  name: string;
  description: string | null;
  settlement_noun: string;
  noun_gender: EconNounGender;
  default_population: number;
  tax_rate: number;
  sort_order: number;
  goods: EconTemplateGoods[];
  updated_at?: string | null;
}

export interface EconTemplateUpdate {
  name: string;
  description?: string | null;
  settlement_noun: string;
  noun_gender: EconNounGender;
  default_population: number;
  tax_rate: number;
  goods: EconTemplateGoods[];
}

export interface EconItemGroupRow {
  item_id: number;
  name: string;
  item_type: string;
  item_rarity: string | null;
  resource_subcategory: string | null;
  is_food: boolean;
  price: number;
  image: string | null;
  auto_group: string | null;
  auto_off_market: boolean;
  override_group: string | null;
  override_off_market: boolean | null;
  /** Effective group (override, else auto); null = no group */
  group: string | null;
  off_market: boolean;
  in_quests: boolean;
}

export interface EconItemGroupsParams {
  q?: string;
  item_type?: string;
  /** group code or `none` */
  group?: string;
  source?: 'auto' | 'manual';
  off_market?: boolean;
  page?: number;
  page_size?: number;
}

/** Fields left out stay unchanged; `null` returns the field to the auto rule; `reset` deletes overrides. */
export interface EconItemGroupsUpdate {
  item_ids: number[];
  group_code?: string | null;
  off_market?: boolean | null;
  reset?: boolean;
}

/** Global simulation params — keys of `econ_sim.SimParams` (the backend source of truth). */
export interface EconSimParams {
  dt: number;
  price_min: number;
  price_max: number;
  price_exponent: number;
  stock_cap_mult: number;
  prod_price_elasticity: number;
  prod_price_min: number;
  prod_price_max: number;
  full_stability: number;
  hunger_prod_penalty: number;
  afford_days: number;
  treasury_reserve_days: number;
  treasury_release_ticks: number;
  country_grant_share: number;
  purse_start_days: number;
  stab_base: number;
  stab_hunger_w: number;
  stab_goods_w: number;
  stab_free_tax: number;
  stab_tax_w: number;
  stab_debt_penalty: number;
  stab_rate_up: number;
  stab_rate_down: number;
  prosp_rate: number;
  prosp_w_sat: number;
  prosp_w_liq: number;
  prosp_w_stab: number;
  prosp_hunger_w: number;
  prosp_liq_days: number;
  history_retention_days: number;
  /* FEAT-183 NPC merchants */
  merchant_bid_share: number;
  merchant_wholesale_share: number;
  merchant_resident_share: number;
  merchant_resident_share_max: number;
  merchant_purse_share: number;
  merchant_take_share: number;
  merchant_cash_target_mult: number;
  merchant_cash_cap_mult: number;
  merchant_cash_release: number;
}

export type EconTickTrigger = 'auto' | 'manual';
export type EconTickStatus = 'running' | 'done' | 'partial' | 'failed';

export interface EconTickRun {
  id: number;
  trigger_kind: EconTickTrigger;
  status: EconTickStatus;
  regions_total: number;
  regions_done: number;
  regions_failed: number;
  started_at: string;
  finished_at: string | null;
  /** Columns of `econ_tick_runs` the runs list may carry; the run-now summary may omit them. */
  slot?: number | null;
  actor_user_id?: number | null;
  error?: string | null;
  heartbeat_at?: string | null;
  /** Only in the «Пересчитать сейчас» summary (`RunSummary.to_dict`) */
  resumed?: boolean;
  operations_posted?: number;
  failed_region_ids?: number[];
  /** FEAT-183: in both the runs list (derived) and the run-now summary */
  merchant_ops_posted?: number;
  merchant_failures?: number;
  /** FEAT-183: only in the run-now summary */
  merchants_processed?: number;
  merchant_items_sold?: number;
  merchant_items_restocked?: number;
  merchant_failed_region_ids?: number[];
  shop_rows_purged?: number;
}

export interface EconSimState {
  tick_enabled: boolean;
  env_enabled: boolean;
  params: EconSimParams;
  current_slot_start: string;
  next_slot_at: string;
  running: EconTickRun | null;
  runs: EconTickRun[];
}

export interface EconSimUpdate {
  tick_enabled: boolean;
  params: EconSimParams;
}

/* ---------------------------------------------- FEAT-183 — NPC merchants (feature file 3.7) */

/** Why a merchant is not living (`econ_core.merchant_status`); null for a living one. */
export type EconMerchantReason = 'not_npc' | 'dead' | 'no_location' | 'dungeon' | 'no_region' | 'not_simulated';

export interface EconMerchantRow {
  row_id: number;
  item_id: number;
  item_name: string | null;
  group: string | null;
  off_market: boolean;
  /** 'admin' | 'player' (bought from players) */
  origin: string;
  is_active: boolean;
  base_buy: number;
  base_sell: number;
  /** Current prices; null when the row is not on the market */
  ask: number | null;
  bid: number | null;
  market: boolean;
  /** null = unlimited (legacy merchant) */
  stock: number | null;
  restock_target: number;
}

export interface EconMerchantLastTrade {
  operation_id: number;
  run_id: number | null;
  at: string;
  sold_items: number;
  sold_value: number;
  tax: number;
  restock_items: number;
  restock_value: number;
  upkeep: number;
}

export interface EconMerchant {
  npc_id: number;
  /** null when the character is gone (reason not_npc) */
  name: string | null;
  location_id: number | null;
  region_id: number | null;
  region_name: string | null;
  living: boolean;
  reason: EconMerchantReason | string | null;
  tax_rate: number | null;
  cash: number;
  /** 0 for a legacy merchant */
  cash_target: number;
  rows: EconMerchantRow[];
  stock_value: number;
  last_trade: EconMerchantLastTrade | null;
}

export interface EconMerchantsResponse {
  items: EconMerchant[];
  totals: { merchants: number; living: number; cash: number };
}

export interface EconMerchantsParams {
  region_id?: number;
  living?: boolean;
}

export interface EconMerchantFundBody {
  region_ids?: number[];
  npc_ids?: number[];
  comment: string;
}

export type EconMerchantFundSkipReason =
  | EconMerchantReason
  | 'at_target'
  | 'no_target'
  | 'not_merchant'
  | 'region_filtered';

export interface EconMerchantFundResult {
  merchants: number;
  funded: number;
  operation_ids: number[];
  emitted: number;
  skipped: { npc_id: number; reason: EconMerchantFundSkipReason | string }[];
}

/* The public player card (`GET /characters/economy/regions/{id}/card`) is typed next to its fetch in
 * `api/regionEconomy.ts` (task F4). */
