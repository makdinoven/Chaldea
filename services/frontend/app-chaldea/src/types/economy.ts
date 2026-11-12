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
  | 'population_purse'
  /** FEAT-184: the bank's own money and the vault of player deposits (ref = region id) */
  | 'bank'
  | 'bank_deposits'
  /** FEAT-192: singleton «Караваны в пути» — money of caravans on the road (never negative) */
  | 'caravan_escrow'
  /** FEAT-206: a faction's treasury (ref = faction id, never negative) */
  | 'faction_treasury';

export type EconLegType = 'main' | 'refund' | 'commission' | 'tax' | 'trade_tax' | 'interest';

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
  /** FEAT-184: own money of all banks (`bank` accounts) and the vaults of player deposits (`bank_deposits`) */
  banks?: number;
  bank_deposits?: number;
  /** FEAT-192: balance of «Караваны в пути» (already counted in `held`) */
  caravan_escrow?: number;
  /** FEAT-206: all faction treasuries (already counted in `held`) */
  factions?: number;
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
  /** FEAT-184: Σ open deposit rows (amount + interest_accrued) vs Σ vault balances — part of `ok` */
  bank_deposits_expected?: number;
  bank_deposits_actual?: number;
  /** FEAT-192: Σ (paid_purse + paid_treasury) of in-transit caravans vs the escrow balance — part of `ok` */
  caravan_escrow_expected?: number;
  caravan_escrow_actual?: number;
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
  /** FEAT-186: lore population (e.g. 4 000 000); the tick computes with population / `population_scale` */
  population: number;
  /** FEAT-186: the population the tick computes with (read-only, optional — older backends don't send it) */
  sim_population?: number | null;
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
  /** FEAT-184: «Банк есть» (an enabled `econ_banks` row) */
  bank_enabled?: boolean;
  /** FEAT-187: active events of the region (optional — older backends don't send it) */
  active_events?: EconEventBadge[];
  /* FEAT-194 social classes (3.13) — optional, older backends don't send them */
  /** Live shares 0..1; null = the region has no classes */
  class_poor?: number | null;
  class_middling?: number | null;
  class_rich?: number | null;
  /** Default shares of the region's template (what «Применить шаблон» resets to) */
  class_base?: EconClassMix | null;
  /** Shift of the poor / rich share at the last recount (signed share, e.g. −0.0002) */
  class_dpoor?: number | null;
  class_drich?: number | null;
  /** Purse norm of the region (marks) */
  wealth_norm?: number | null;
  /** Wealth tax of the last recount (purse → treasury) */
  last_wealth_tax?: number | null;
  /** purse / wealth_norm; null when the norm is 0 */
  money_vs_norm?: number | null;
}

/** FEAT-194: three class shares, sum 1. */
export interface EconClassMix {
  poor: number;
  middling: number;
  rich: number;
}

export type EconClassKey = keyof EconClassMix;

/** FEAT-194 (3.13): one class row of the region detail report (money in sim units per resident). */
export interface EconClassReportRow {
  share: number;
  base_share: number | null;
  norm_days: number;
  norm_per_resident: number;
  money_per_resident: number;
  needs_per_resident_day: number;
  /** 0..1 — how much of its basket the class can afford at current prices */
  afford: number;
}

/** FEAT-194 (3.13): `classes` of the region detail (`econ_classes.class_report`). */
export interface EconClassReport {
  classes: Record<EconClassKey, EconClassReportRow>;
  wealth_norm: number;
  /** wealth_norm + treasury_target */
  money_norm: number;
  deficit: number;
  /** purse / wealth_norm */
  r: number | null;
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
  /** FEAT-194: class report, null when the region has no classes */
  classes?: EconClassReport | null;
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
  /** FEAT-194: all three or none, each 0..1, sum 1 ± 0.001; omitted → kept */
  class_poor?: number;
  class_middling?: number;
  class_rich?: number;
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
  /** FEAT-184: open banks in capitals and ports (one-time capital seed after the treasury top-up; backend default true) */
  open_banks?: boolean;
  /** FEAT-186: move the purse part above the starting purse back into emission (backend default false) */
  return_purse_excess?: boolean;
  /** FEAT-186: move the treasury part above the wage reserve back into emission (backend default false) */
  return_treasury_excess?: boolean;
  /** FEAT-194: also reset the class shares to the template (rows without shares always get them; default false) */
  reset_classes?: boolean;
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
  /** FEAT-184: regions whose bank this fill switched on */
  banks_opened?: number[];
  /** FEAT-186: returned_purses + returned_treasuries — excess moved back into emission */
  returned?: number;
  returned_purses?: number;
  returned_treasuries?: number;
  /** FEAT-186: residents' bank deposits above the scaled target paid back into the purse */
  resident_deposits_out?: number;
  /** FEAT-186: residents' bank loans above the scaled target repaid from the purse */
  resident_loans_repaid?: number;
  /** FEAT-194: regions whose class shares this fill reset to the template */
  classes_reset?: number[];
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
  /* FEAT-194 — null for rows written before the classes */
  class_poor?: number | null;
  class_middling?: number | null;
  class_rich?: number | null;
  wealth_norm?: number | null;
  wealth_tax?: number | null;
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
  /* FEAT-194: per-capita demand weight of each class (optional — older backends don't send it) */
  class_demand_poor?: number;
  class_demand_middling?: number;
  class_demand_rich?: number;
}

export interface EconGoodsGroupUpdate {
  name: string;
  base_price: number;
  norm_per_1000: number;
  norm_days: number;
  prosperity_elasticity: number;
  price_elasticity: number;
  inputs: EconGroupInput[];
  /** FEAT-194: 0..20 each, omitted → kept */
  class_demand_poor?: number;
  class_demand_middling?: number;
  class_demand_rich?: number;
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
  /* FEAT-194: default class shares of the template (optional — older backends don't send them) */
  class_poor?: number;
  class_middling?: number;
  class_rich?: number;
}

export interface EconTemplateUpdate {
  name: string;
  description?: string | null;
  settlement_noun: string;
  noun_gender: EconNounGender;
  default_population: number;
  tax_rate: number;
  goods: EconTemplateGoods[];
  /** FEAT-194: all three or none, sum 1 ± 0.001; omitted → kept */
  class_poor?: number;
  class_middling?: number;
  class_rich?: number;
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
  /* FEAT-184 banks */
  bank_demand_rate_day: number;
  bank_term_rate_day_7: number;
  bank_term_rate_day_14: number;
  bank_term_rate_day_28: number;
  bank_loan_rate_day: number;
  bank_penalty_rate_day: number;
  bank_debt_cap_mult: number;
  bank_loan_cap_base: number;
  bank_loan_cap_per_level: number;
  bank_min_amount: number;
  bank_transfer_fee_rate: number;
  bank_transfer_fee_min: number;
  bank_start_capital: number;
  bank_reserve_ratio: number;
  bank_rate_cover: number;
  bank_rate_factor_min: number;
  bank_rate_smoothing: number;
  bank_resident_deposit_share: number;
  bank_resident_loan_share: number;
  bank_resident_adjust: number;
  /* bank fix: share of the bank's realized net interest income sent to the region treasury each pass */
  bank_profit_to_treasury_share: number;
  /* FEAT-186 lore population scale: the tick computes with population / population_scale */
  population_scale: number;
  /* FEAT-187 region events (feature file 3.5) */
  events_enabled: number;
  event_rate_per_season: number;
  event_season_days: number;
  event_max_active: number;
  event_mult_min: number;
  event_mult_max: number;
  event_delta_max: number;
  event_spread_max_depth: number;
  event_riot_stability: number;
  event_riot_after_days: number;
  /* FEAT-191 mint and season quota (feature file 3.5) — older backends may not send them yet */
  quota_season_amount: number;
  mint_season_limit: number;
  mint_court_marks_per_unit: number;
  mint_court_threshold_pct: number;
  /* FEAT-192 caravans (feature file 3.10) — older backends may not send them yet */
  caravans_enabled: number;
  caravan_surplus_share: number;
  caravan_purse_share: number;
  caravan_treasury_food_share: number;
  caravan_travel_domestic: number;
  caravan_travel_foreign: number;
  caravan_min_value: number;
  caravan_max_per_run: number;
  /* FEAT-211 physical caravans and raids (feature file 3.14) — older backends may not send them yet */
  caravan_physical_enabled: number;
  caravan_physical_min_value: number;
  caravan_physical_small_chance: number;
  caravan_physical_max_active: number;
  caravan_step_minutes: number;
  caravan_route_max_steps: number;
  caravan_post_hold_max_min: number;
  caravan_raid_battle_max_hours: number;
  caravan_raid_marks_share: number;
  caravan_raid_goods_share: number;
  caravan_guard_count_base: number;
  caravan_guard_value_per_extra: number;
  caravan_guard_count_max: number;
  caravan_guard_mult_per_1000: number;
  caravan_guard_mult_max: number;
  caravan_guard_mult_dangerous: number;
  caravan_rep_trade_share: number;
  fence_purse_share: number;
  /* FEAT-212 player caravan escorts (feature file 3.4) */
  caravan_departure_minutes: number;
  caravan_escort_seats: number;
  caravan_escort_fee_share: number;
  caravan_escort_bonus_share: number;
  caravan_escort_defense_fame: number;
  /* FEAT-193 guild orders (feature file 3.4) — older backends may not send them yet */
  guild_enabled: number;
  guild_markup_pct: number;
  guild_open_threshold_pct: number;
  guild_min_order_value: number;
  guild_purse_share: number;
  guild_treasury_food_share: number;
  guild_xp_per_mark: number;
  guild_xp_per_mark_merchant_items: number;
  guild_xp_daily_cap: number;
  /* FEAT-194 social classes and the wealth norm (feature file 3.14) — older backends may not send them yet */
  classes_enabled: number;
  class_norm_days_poor: number;
  class_norm_days_middling: number;
  class_norm_days_rich: number;
  wealth_tax_rate: number;
  class_tax_w_poor: number;
  class_tax_w_middling: number;
  class_tax_w_rich: number;
  class_stab_poor_threshold: number;
  class_stab_poor_w: number;
  class_stab_poor_hunger_w: number;
  class_stab_rich_free_tax: number;
  class_stab_rich_tax_w: number;
  mob_rate_up: number;
  mob_rate_down: number;
  mob_rich_factor: number;
  mob_dead_zone: number;
  mob_w_prosperity: number;
  mob_w_money: number;
  mob_w_stability: number;
  mob_w_hunger: number;
  class_share_min: number;
  class_share_max: number;
  grant_deficit_share: number;
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
  /** FEAT-184: bank pass counters — the run-now summary has all of them; the runs list may derive only some */
  banks_processed?: number;
  bank_ops_posted?: number;
  bank_failures?: number;
  bank_failed_region_ids?: number[];
  bank_interest_paid?: number;
  loans_overdue?: number;
  loans_collected?: number;
  collected_amount?: number;
  banks_closed?: number;
  /** FEAT-187: events pass counters (`RunSummary`, 3.6 step 7) — the run-now summary; the runs list may carry some */
  events_ended?: number;
  events_started?: number;
  events_spread?: number;
  events_chained?: number;
  riots_started?: number;
  events_applied?: number;
  event_expense_ops?: number;
  events_failed?: number;
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
  /** The backend merges the body into the stored params: keys left out keep their stored values. */
  params: Partial<EconSimParams>;
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

/* ---------------------------------------------- FEAT-184 — banks (feature file 3.10 / 3.11) */

export interface EconBankTermRate {
  term_days: number;
  rate_day: number;
}

/** A living banker of the region (when the backend lists them instead of a count). */
export interface EconBankBanker {
  npc_id: number;
  name: string | null;
}

/** Counters of the last bank pass (`econ_bank.bank_step` stats); unknown keys are shown as is. */
export type EconBankStats = Record<string, number | string | boolean | null | Record<string, number>>;

export interface EconBankAdminItem {
  region_id: number;
  region_name: string | null;
  country_name: string | null;
  /** «Банк есть» */
  enabled: boolean;
  /** the region's economy is simulated (residents use the bank) */
  simulated: boolean;
  /** living NPC bankers of the region — a count or a list (contract 3.10 does not fix the shape) */
  bankers: number | EconBankBanker[];
  /** balance of the `bank` account */
  own_funds: number;
  /** balance of the `bank_deposits` account */
  vault: number;
  /** Σ amount + interest_accrued of the open player deposit rows */
  deposits_sum: number;
  vault_ok: boolean;
  deposits_count: number;
  term_count: number;
  resident_deposits: number;
  resident_loans: number;
  reserve: number;
  lendable: number;
  loans_count: number;
  loans_debt: number;
  overdue_count: number;
  rate_factor: number;
  demand_rate_day: number;
  term_rates: EconBankTermRate[];
  capital_seeded_at: string | null;
  last_tick_at: string | null;
  last_stats: EconBankStats | null;
  /** FEAT-197: loans need this reputation tier in the bank's region (null = none) */
  loan_min_reputation_tier?: string | null;
}

export interface EconBanksTotals {
  banks: number;
  enabled: number;
  own_funds: number;
  player_deposits: number;
  resident_deposits: number;
  player_loans_debt: number;
  resident_loans: number;
  debtors: number;
}

export interface EconBanksResponse {
  items: EconBankAdminItem[];
  totals: EconBanksTotals;
}

export type EconBankDepositKind = 'demand' | 'term';
export type EconBankLoanStatus = 'active' | 'overdue' | 'closed' | 'written_off';

export interface EconBankAdminDeposit {
  id: number;
  character_id: number;
  character_name: string | null;
  status: string;
  region_id: number;
  region_name: string | null;
  kind: EconBankDepositKind | string;
  amount: number;
  interest_accrued: number;
  interest_total: number;
  rate_day: number | null;
  term_days: number | null;
  opened_at: string;
  matures_at: string | null;
  matured: boolean;
}

export interface EconBankLoan {
  id: number;
  region_id: number;
  region_name: string | null;
  status: EconBankLoanStatus | string;
  principal: number;
  /** projected to now */
  debt: number;
  interest_total: number;
  penalty_total: number;
  paid_total: number;
  collected_total: number;
  rate_day: number;
  penalty_rate_day: number;
  term_days: number;
  issued_at: string;
  due_at: string;
  overdue: boolean;
}

export interface EconBankAdminLoan extends EconBankLoan {
  character_id: number;
  character_name: string | null;
}

export interface EconBankAdminDetail {
  item: EconBankAdminItem;
  /** open deposits, at most 500 newest */
  deposits: EconBankAdminDeposit[];
  /** open loans */
  loans: EconBankAdminLoan[];
}

export interface EconBankDebtor {
  loan_id: number;
  character_id: number;
  character_name: string | null;
  region_id: number;
  region_name: string | null;
  debt: number;
  principal: number;
  due_at: string;
  overdue_days: number;
  penalty_total: number;
}

export interface EconBankFlagBody {
  is_enabled: boolean;
  /** first switch-on takes the start capital from the region treasury once */
  seed_capital?: boolean;
  /** FEAT-197: sent → stored (null clears); omitted → unchanged */
  loan_min_reputation_tier?: string | null;
}

export type EconBankCapitalDirection = 'in' | 'out';

export interface EconBankCapitalBody {
  direction: EconBankCapitalDirection;
  amount: number;
  comment: string;
}

export interface EconBankCapitalResult {
  operation_id: number;
  bank_balance: number;
  treasury_balance: number;
}

/* ---------------------------------------------- FEAT-187 — region events (feature file 3.7 / 3.8) */

export type EconEventEffectType =
  | 'production'
  | 'consumption'
  | 'labor'
  | 'price'
  | 'tax_income'
  | 'stability'
  | 'prosperity'
  | 'merchants_halt'
  | 'bank_panic'
  | 'loan_boom'
  | 'stock_loss'
  | 'treasury_expense'
  | 'population'
  /* FEAT-194: one-shot shift of the class shares, `delta` −0.3…0.3 (>0 up, <0 down) */
  | 'class_shift';

/** One effect of an event template: only the fields of its type are sent (the backend rejects extra ones). */
export interface EconEventEffect {
  type: EconEventEffectType;
  /** Goods group codes, `["*"]` = every group. */
  groups?: string[] | null;
  mult?: number | null;
  share?: number | null;
  delta?: number | null;
  pct?: number | null;
}

export type EconEventKind = 'good' | 'bad';
export type EconEventTrigger = 'random' | 'low_stability' | 'manual';
export type EconEventScope = 'region' | 'neighbours' | 'country' | 'world';
export type EconEventOrigin = 'random' | 'manual' | 'spread' | 'chain' | 'riot';
export type EconEventStatus = 'active' | 'ended' | 'cancelled';

export interface EconEventChain {
  code: string;
  /** 0..1 — chance over the source event's lifetime */
  chance: number;
}

/** Body of `PUT /admin/economy/events/templates/{id}` (`EventTemplateUpdate`): everything except the code. */
export interface EconEventTemplateUpdate {
  name: string;
  icon: string;
  kind: EconEventKind;
  player_text: string;
  admin_note: string | null;
  trigger_kind: EconEventTrigger;
  weight: number;
  duration_min_days: number;
  duration_max_days: number;
  scope: EconEventScope;
  /** 0..1 */
  spread_chance: number;
  /** Region template codes; [] = any */
  region_templates: string[];
  /** Calendar segment names; [] = any */
  seasons: string[];
  effects: EconEventEffect[];
  chains: EconEventChain[];
  is_enabled: boolean;
}

/** Body of `POST /admin/economy/events/templates` (`EventTemplateIn`). */
export interface EconEventTemplateCreate extends EconEventTemplateUpdate {
  code: string;
}

export interface EconEventTemplate extends EconEventTemplateCreate {
  id: number;
  /** Running instances of this template */
  active_count: number;
  updated_at: string | null;
}

/** One `econ_region_events` row (`RegionEventOut`) — active or history. */
export interface EconRegionEvent {
  id: number;
  region_id: number;
  region_name: string | null;
  country_id: number | null;
  template_id: number | null;
  template_code: string;
  name: string;
  icon: string;
  kind: EconEventKind;
  player_text: string;
  trigger_kind: EconEventTrigger;
  effects: EconEventEffect[];
  origin: EconEventOrigin;
  parent_event_id: number | null;
  root_event_id: number | null;
  generation: number;
  status: EconEventStatus;
  started_at: string;
  ends_at: string;
  ended_at: string | null;
  game_segment: string | null;
  started_by_user_id: number | null;
  cancelled_by_user_id: number | null;
  cancel_comment: string | null;
  applied_at: string | null;
  population_before: number | null;
  population_after: number | null;
  /** `{"stock_lost": {code: units}, "treasury_expense": n, "operation_id": id}` once the one-shots applied */
  outcome: EconRegionEventOutcome | null;
}

export interface EconRegionEventOutcome {
  stock_lost?: Record<string, number> | null;
  treasury_expense?: number | null;
  operation_id?: number | null;
  /** FEAT-194: class shares [poor, middling, rich] before / after the one-shot `class_shift` */
  class_shift?: { before: number[]; after: number[] } | null;
}

export interface EconEventStartBody {
  template_id: number;
  region_id: number;
  /** Overrides the template scope */
  scope?: EconEventScope | null;
  /** Overrides the rolled duration */
  duration_days?: number | null;
  /** One per submit — a repeated request answers 409 «Событие уже запущено» */
  request_id?: string | null;
}

export interface EconEventSkip {
  region_id: number;
  region_name: string | null;
  reason: string;
}

export interface EconEventStartResult {
  started: EconRegionEvent[];
  skipped: EconEventSkip[];
}

export interface EconRegionEventsPage {
  items: EconRegionEvent[];
  total: number;
  page: number;
  page_size: number;
}

export interface EconEventsHistoryParams {
  region_id?: number;
  template_code?: string;
  kind?: EconEventKind;
  status?: EconEventStatus;
  origin?: EconEventOrigin;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

/** Small marker of an active event (`EventBadge` — admin regions list, F2). */
export interface EconEventBadge {
  name: string;
  icon: string;
  kind: EconEventKind;
}

/* ---------------------------------------------- FEAT-191 — mint and season quota (feature file 3.10) */

/** Game «сезон» = a season with the festival after it (49 real days, 4 per year). */
export interface MintSeasonPeriod {
  /** Absolute period number (monotonic across years) */
  index: number;
  year: number;
  /** spring | summer | autumn | winter */
  season: string;
  starts_at: string;
  ends_at: string;
}

/** Ore the Монетчик accepts, with what the character has in plain stacks. */
export interface MintViewItem {
  item_id: number;
  name: string;
  image: string | null;
  marks_per_item: number;
  /** Sum of plain stacks in the bag */
  have: number;
  /** floor(remaining / marks_per_item) */
  max_by_limit: number;
}

/** `GET /characters/economy/mint/npc/{npc_id}` */
export interface MintView {
  npc_id: number;
  npc_name: string;
  country_id: number | null;
  country_name: string | null;
  region_id: number | null;
  region_name: string | null;
  working: boolean;
  closed_reason: string | null;
  /** null when the world calendar is unavailable */
  period: MintSeasonPeriod | null;
  limit: number;
  minted_court: number;
  minted_players: number;
  remaining: number;
  items: MintViewItem[];
  wallet: number;
  /** FEAT-197: minting is refused with this text (NPC reputation gate) */
  reputation_lock?: string | null;
}

export interface MintRequest {
  character_id: number;
  item_id: number;
  quantity: number;
  request_id: string;
}

export interface MintActionOut {
  message: string;
  operation_id: number;
  /** Marks actually paid (for the accepted pieces). */
  marks: number;
  /** Pieces actually accepted — fewer than requested when the season limit runs out. */
  quantity: number;
  /** Pieces the player asked to mint. */
  requested: number;
  /** True when only part was accepted; the rest of the ore stayed in the bag. */
  partial: boolean;
  wallet: number;
  view: MintView;
}

export type MintCapitalSource = 'auto' | 'manual' | 'none';

export interface MintCandidate {
  region_id: number;
  name: string;
  template_code: string | null;
}

export interface MintMinter {
  npc_id: number;
  name: string | null;
  npc_status: string | null;
  location_name: string | null;
  in_capital: boolean;
}

/** One country of `GET /characters/admin/economy/mint`. */
export interface MintCountry {
  country_id: number;
  country_name: string | null;
  is_enabled: boolean;
  capital_region_id: number | null;
  capital_region_name: string | null;
  capital_source: MintCapitalSource;
  /** The admin's manual choice (`econ_mints.capital_region_id`), null = auto */
  capital_override_id: number | null;
  /** The manual choice points at a deleted region or one of another country */
  override_stale: boolean;
  candidates: MintCandidate[];
  working: boolean;
  closed_reason: string | null;
  /** Per-country limit, null = the default param */
  season_limit_override: number | null;
  /** Effective limit of this season */
  season_limit: number;
  minted_court: number;
  minted_players: number;
  remaining: number;
  ore_stock: number | null;
  ore_norm: number | null;
  minters: MintMinter[];
}

export interface MintAdminParams {
  mint_season_limit: number;
  mint_court_marks_per_unit: number;
  mint_court_threshold_pct: number;
  quota_season_amount: number;
}

export interface MintAdminOut {
  period: MintSeasonPeriod | null;
  params: MintAdminParams;
  countries: MintCountry[];
}

/** Full replace; `capital_region_id: null` = auto, `season_limit: null` = the default param. */
export interface MintCountryIn {
  capital_region_id: number | null;
  season_limit: number | null;
  is_enabled: boolean;
}

export interface MintItem {
  item_id: number;
  name: string;
  image: string | null;
  item_type: string | null;
  resource_subcategory: string | null;
  effective_group: string | null;
  marks_per_item: number;
  is_enabled: boolean;
  /** effective_group == 'ore_metal'; invalid rows are ignored by the Монетчик */
  valid: boolean;
}

export interface MintItemIn {
  marks_per_item: number;
  is_enabled: boolean;
}

/** One issued season quota (`econ_operations`, op_type `season_quota`). */
export interface QuotaEntry {
  operation_id: number;
  created_at: string;
  period_index: number;
  year: number | null;
  season: string | null;
  amount: number;
  /** How many region treasuries got a share */
  regions: number;
}

/* ============================================================================ FEAT-192 caravans (3.11) */

export type CaravanStatus = 'in_transit' | 'delivered' | 'cancelled';
export type CaravanStatusFilter = CaravanStatus | 'all';

export interface CaravanParams {
  caravans_enabled: number;
  caravan_surplus_share: number;
  caravan_purse_share: number;
  caravan_treasury_food_share: number;
  caravan_travel_domestic: number;
  caravan_travel_foreign: number;
  caravan_min_value: number;
  caravan_max_per_run: number;
  /* FEAT-211 (feature file 3.14) — optional: an older backend does not send them */
  caravan_physical_enabled?: number;
  caravan_physical_min_value?: number;
  caravan_physical_small_chance?: number;
  caravan_physical_max_active?: number;
  caravan_step_minutes?: number;
  caravan_route_max_steps?: number;
  caravan_post_hold_max_min?: number;
  caravan_raid_battle_max_hours?: number;
  caravan_raid_marks_share?: number;
  caravan_raid_goods_share?: number;
  caravan_guard_count_base?: number;
  caravan_guard_value_per_extra?: number;
  caravan_guard_count_max?: number;
  caravan_guard_mult_per_1000?: number;
  caravan_guard_mult_max?: number;
  caravan_guard_mult_dangerous?: number;
  caravan_rep_trade_share?: number;
  fence_purse_share?: number;
  /* FEAT-212 player caravan escorts (feature file 3.4) — optional: an older backend does not send them */
  caravan_departure_minutes?: number;
  caravan_escort_seats?: number;
  caravan_escort_fee_share?: number;
  caravan_escort_bonus_share?: number;
  caravan_escort_defense_fame?: number;
}

export interface CaravanCountry {
  country_id: number;
  name: string;
  participating_regions: number;
}

/** Symmetric pair, `country_a < country_b`; a missing DB row comes as `is_enabled=false, duty_pct=10`. */
export interface TradePair {
  country_a: number;
  country_b: number;
  name_a: string | null;
  name_b: string | null;
  is_enabled: boolean;
  duty_pct: number;
  updated_at: string | null;
}

export interface TradePairIn {
  country_a: number;
  country_b: number;
  is_enabled: boolean;
  duty_pct: number;
}

export interface CaravanOverview {
  params: CaravanParams;
  escrow: { balance: number; expected: number; ok: boolean };
  in_transit: { count: number; value: number; duty: number };
  last_run: { run_id: number; dispatched: number; delivered: number; cancelled: number } | null;
  countries: CaravanCountry[];
  pairs: TradePair[];
}

export interface CaravanRow {
  id: number;
  status: CaravanStatus;
  group_code: string;
  group_name: string | null;
  from_region_id: number;
  from_region_name: string | null;
  from_country_id: number;
  from_country_name: string | null;
  to_region_id: number;
  to_region_name: string | null;
  to_country_id: number;
  to_country_name: string | null;
  units: number;
  unit_price: number;
  value: number;
  duty: number;
  duty_pct: number;
  paid_purse: number;
  paid_treasury: number;
  travel_runs: number;
  runs_left: number;
  dispatch_run_id: number;
  finished_run_id: number | null;
  cancel_reason: string | null;
  goods_returned: boolean | null;
  created_at: string;
  finished_at: string | null;
  /* FEAT-211 physical caravans (A4) — optional: absent on an older backend */
  is_physical?: boolean;
  current_location_id?: number | null;
  current_location_name?: string | null;
  route_index?: number;
  route_len?: number;
  next_move_at?: string | null;
  arrived_at?: string | null;
  hold_started_at?: string | null;
  guard_count?: number;
  stolen_units?: number;
  raid_paid?: number;
  raid_status?: CaravanRaidStatus | null;
  /** FEAT-212 (A4): active player escorts — optional on an older backend */
  escort_count?: number;
}

export interface CaravanList {
  total: number;
  items: CaravanRow[];
}

export interface CaravanListQuery {
  status?: CaravanStatusFilter;
  /** FEAT-211: physical / abstract / all */
  kind?: CaravanKindFilter;
  region_id?: number;
  group_code?: string;
  limit?: number;
  offset?: number;
}

/* ============================================================================ FEAT-211 physical caravans (3.13) */

export type CaravanKindFilter = 'all' | 'physical' | 'abstract';

export type CaravanRaidStatus = 'starting' | 'fighting' | 'won' | 'repelled' | 'aborted' | 'expired';

export interface CaravanRoutePoint {
  index: number;
  location_id: number;
  name: string | null;
  region_id: number | null;
  region_name: string | null;
}

export interface CaravanRaidAttacker {
  id: number;
  name: string | null;
  marks: number;
  bales: number;
}

export interface CaravanRaidAdmin {
  id: number;
  status: CaravanRaidStatus;
  leader_id: number;
  leader_name: string | null;
  is_group: boolean;
  battle_id: number | null;
  attackers: CaravanRaidAttacker[];
  marks: number;
  stolen_units: number;
  stolen_value: number;
  bales: number;
  guard_template_id: number | null;
  guard_template_name: string | null;
  guard_mult: number | null;
  created_at: string;
  finished_at: string | null;
  /** FEAT-212: player escorts placed on the guard team */
  escort_ids?: number[];
}

/** FEAT-212 (A5): escort row status. */
export type CaravanEscortStatus = 'active' | 'left' | 'fallen' | 'delivered' | 'cancelled' | 'released';

/** FEAT-212 (A5): one player escort of a caravan (admin only). */
export interface CaravanEscortAdmin {
  character_id: number;
  name: string | null;
  status: CaravanEscortStatus | string;
  joined_at: string;
  ended_at: string | null;
  fee: number;
  bonus: number;
  in_raid: boolean;
}

/** A5 — one caravan with its route and raid. */
export interface CaravanDetail extends CaravanRow {
  route: CaravanRoutePoint[];
  held_by: 'post' | 'raid' | null;
  raid: CaravanRaidAdmin | null;
  /** FEAT-212 — optional on an older backend */
  escorts?: CaravanEscortAdmin[];
}

export type CaravanGateSource = 'override' | 'station' | 'none';

export interface CaravanRoadRegion {
  region_id: number;
  name: string | null;
  country_name: string | null;
  station_location_id: number | null;
  station_location_name: string | null;
  gate_override_id: number | null;
  gate_override_name: string | null;
  gate_location_id: number | null;
  gate_location_name: string | null;
  gate_source: CaravanGateSource;
}

export type CaravanNoRoadReason = 'no_gate' | 'no_path' | 'too_long';

export interface CaravanNoRoad {
  from_region_id: number;
  from_name: string | null;
  to_region_id: number;
  to_name: string | null;
  reason: CaravanNoRoadReason;
}

/** A6 — trade gates of the participating regions and the pairs with no road. */
export interface CaravanRoads {
  regions: CaravanRoadRegion[];
  no_road: CaravanNoRoad[];
}

export interface CaravanGuardTemplate {
  mob_template_id: number;
  name: string | null;
  level: number | null;
}

/** A8/A9 — pool of mob templates that guard caravans. */
export interface CaravanGuards {
  templates: CaravanGuardTemplate[];
}

/* ============================================================================ FEAT-193 guild orders (3.10) */

/** An open order of the region as the player sees it — no money numbers. */
export interface GuildOrder {
  order_id: number;
  group_code: string;
  group_name: string;
  is_food: boolean;
  units_total: number;
  units_left: number;
  /** 0…100 */
  filled_pct: number;
  /** false — the residents have no money for it until the next recount */
  payable: boolean;
}

/** A plain bag stack the guild accepts now. */
export interface GuildOffer {
  item_id: number;
  name: string;
  image: string | null;
  group_code: string;
  order_id: number;
  have: number;
  /** Marks per piece */
  unit_price: number;
  units_per_item: number;
  /** min(have, by volume, by money, 10000) — pieces the guild takes now */
  max_accept: number;
  /** The price was lowered to what the region's merchants sell the item for */
  capped_by_merchants: boolean;
  /** XP per mark for this item: lower when a merchant of the region sells it (3.6a) */
  xp_rate: number;
}

/** A bag item of a wanted group that the guild refuses (reason in Russian). */
export interface GuildRefused {
  item_id: number;
  name: string;
  image: string | null;
  group_code: string;
  have: number;
  reason: string;
}

export interface GuildXpInfo {
  per_mark: number;
  per_mark_merchant_items: number;
  daily_cap: number;
  /** Base XP (before the XP book) still available today (UTC day) */
  left_today: number;
  /** Quest XP book multiplier */
  multiplier: number;
}

export interface GuildView {
  npc_id: number;
  npc_name: string;
  region_id: number | null;
  region_name: string | null;
  working: boolean;
  closed_reason: string | null;
  markup_pct: number;
  orders: GuildOrder[];
  offers: GuildOffer[];
  refused: GuildRefused[];
  xp: GuildXpInfo;
  wallet: number;
  /** FEAT-197: NPC reputation gate / «Вне закона» (then `working` is false too) */
  reputation_lock?: string | null;
}

export interface GuildHandInRequest {
  character_id: number;
  item_id: number;
  quantity: number;
  request_id: string;
}

export interface GuildActionOut {
  message: string;
  operation_id: number;
  /** Accepted pieces */
  quantity: number;
  requested: number;
  partial: boolean;
  unit_price: number;
  total: number;
  /** XP granted (after the XP book) */
  xp: number;
  /** Base XP was cut by the daily cap */
  xp_capped: boolean;
  wallet: number;
  view: GuildView;
}

export type GuildOrderStatus = 'open' | 'filled' | 'closed';
export type GuildStatusFilter = 'open' | 'closed' | 'all';

export interface GuildAdminParams {
  guild_enabled: number;
  guild_markup_pct: number;
  guild_open_threshold_pct: number;
  guild_min_order_value: number;
  guild_purse_share: number;
  guild_treasury_food_share: number;
  guild_xp_per_mark: number;
  guild_xp_per_mark_merchant_items: number;
  guild_xp_daily_cap: number;
}

export interface GuildAdminTotals {
  open: number;
  units_left_value: number;
  paid_last_7d: number;
  hand_ins_last_7d: number;
  xp_last_7d: number;
}

export interface GuildMaster {
  npc_id: number;
  name: string;
  npc_status: string | null;
  location_name: string | null;
}

export interface GuildRegionRow {
  region_id: number;
  region_name: string | null;
  guild_budget: number;
  guild_food_budget: number;
  open_orders: number;
  masters: GuildMaster[];
}

export interface GuildOrderRow {
  id: number;
  region_id: number;
  region_name: string | null;
  group_code: string;
  group_name: string | null;
  status: GuildOrderStatus | string;
  close_reason: string | null;
  units_total: number;
  units_left: number;
  units_filled: number;
  price_mult: number;
  markup_pct: number;
  pieces: number;
  paid_total: number;
  paid_treasury: number;
  hand_ins: number;
  opened_at: string;
  updated_at: string | null;
  closed_at: string | null;
}

export interface GuildAdminOut {
  params: GuildAdminParams;
  totals: GuildAdminTotals;
  regions: GuildRegionRow[];
  total: number;
  items: GuildOrderRow[];
}

export interface GuildAdminQuery {
  status?: GuildStatusFilter;
  region_id?: number;
  group_code?: string;
  limit?: number;
  offset?: number;
}
