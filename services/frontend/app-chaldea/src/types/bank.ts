/**
 * FEAT-184 — regional banks, player side (character-service, contract 3.9 / 3.11).
 * Mirrors the Pydantic schemas; datetimes are naive UTC strings (use `utils/serverDate`).
 */

export type BankTerm = 7 | 14 | 28;
export const BANK_TERMS: BankTerm[] = [7, 14, 28];

export type BankDepositKind = 'demand' | 'term';

export interface BankTermRate {
  term_days: number;
  rate_day: number;
}

export interface BankRates {
  /** Current demand rate per day (base × factor). */
  demand_rate_day: number;
  /** Rates fixed for new term deposits. */
  term_rates: BankTermRate[];
  loan_rate_day: number;
  penalty_rate_day: number;
  transfer_fee_rate: number;
  transfer_fee_min: number;
  min_amount: number;
}

export interface BankDeposit {
  id: number;
  region_id: number;
  /** `null` → the region was deleted. */
  region_name: string | null;
  kind: BankDepositKind;
  amount: number;
  interest_accrued: number;
  interest_total: number;
  rate_day: number | null;
  term_days: number | null;
  opened_at: string;
  matures_at: string | null;
  matured: boolean;
  /** Lies in the bank of the banker the view was asked from. */
  here: boolean;
}

export type BankLoanStatus = 'active' | 'overdue' | 'closed' | 'written_off' | string;

export interface BankLoan {
  id: number;
  region_id: number;
  region_name: string | null;
  status: BankLoanStatus;
  principal: number;
  /** Projected to now. */
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

export interface BankRegion {
  region_id: number;
  name: string;
  country_name: string | null;
}

export interface BankView {
  npc_id: number;
  npc_name: string;
  region_id: number | null;
  region_name: string | null;
  bank_enabled: boolean;
  rates: BankRates;
  wallet: number;
  /** All own open deposits in any bank, `here` first. */
  deposits: BankDeposit[];
  loan: BankLoan | null;
  debtor: boolean;
  loan_cap: number;
  max_loan_now: number;
  loan_refusal: string | null;
  bank_regions: BankRegion[];
}

export interface BankActionResult {
  message: string;
  operation_id: number | null;
  wallet: number;
  view: BankView;
}

export interface BankSummary {
  character_id: number;
  total_deposits: number;
  deposits: BankDeposit[];
  loan: BankLoan | null;
  debtor: boolean;
}

/* ── Requests ── */

interface BankRequestBase {
  character_id: number;
  request_id?: string;
}

export interface BankDepositRequest extends BankRequestBase {
  kind: BankDepositKind;
  term_days?: BankTerm | null;
  amount: number;
}

export interface BankWithdrawRequest extends BankRequestBase {
  deposit_id: number;
  /** Demand: required; term: ignored (the whole deposit). */
  amount?: number | null;
}

export interface BankTransferRequest extends BankRequestBase {
  deposit_id: number;
  to_region_id: number;
  amount: number;
}

export interface BankSendRequest extends BankRequestBase {
  source: 'wallet' | 'deposit';
  deposit_id?: number | null;
  recipient_name: string;
  to_region_id: number;
  amount: number;
}

export interface BankLoanRequest extends BankRequestBase {
  amount: number;
  term_days: BankTerm;
}

export interface BankRepayRequest extends BankRequestBase {
  amount: number;
}
