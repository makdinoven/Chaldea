import axios from 'axios';

/** FEAT-184 — formatting and small maths of the player bank modal (no state). */

/** Bank passes per day: interest of a loan compounds at the 6-hour tick. */
const TICKS_PER_DAY = 4;

/** Percent with up to 2 Russian decimals: 0.0123 → «1,23». */
export const percent = (fraction: number): string =>
  (fraction * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 });

/** Demand deposit: «0,7 % в неделю». */
export const demandRateText = (rateDay: number): string => `${percent(rateDay * 7)} % в неделю`;

/** Term deposit / loan: «3,5 % за 14 дней». */
export const termRateText = (rateDay: number, termDays: number): string =>
  `${percent(rateDay * termDays)} % за ${termDays} дней`;

/** Interest of a term deposit held to maturity (the bank rounds what it pays down). */
export const termInterest = (amount: number, rateDay: number, termDays: number): number =>
  Math.max(0, Math.floor(amount * rateDay * termDays));

/** Approximate demand interest over a week at the current rate. */
export const weekInterest = (amount: number, rateDay: number): number =>
  Math.max(0, Math.floor(amount * rateDay * 7));

/** Approximate debt at the due date (interest compounds every 6 hours). */
export const loanTotal = (amount: number, rateDay: number, termDays: number): number =>
  Math.ceil(amount * (1 + rateDay / TICKS_PER_DAY) ** (termDays * TICKS_PER_DAY));

/** Commission of a transfer / send: max(min, ceil(amount × rate)). */
export const transferFee = (amount: number, feeRate: number, feeMin: number): number =>
  amount > 0 ? Math.max(feeMin, Math.ceil(amount * feeRate)) : 0;

/** Integer amount from an input; empty / garbage → 0. */
export const parseAmount = (raw: string): number => {
  const n = parseInt(raw.replace(/\s/g, ''), 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

/** Idempotency key of one submit (server: `^[A-Za-z0-9-]{8,64}$`). */
export const newRequestId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  const hex = Math.floor(Math.random() * 0xffffffff).toString(16).padStart(8, '0');
  return `${Date.now()}-${hex}`;
};

/** Russian error text: server `detail` as is; 422 / network have fixed texts. */
export const bankErrorText = (err: unknown, fallback: string): string => {
  if (axios.isAxiosError(err)) {
    if (!err.response) return 'Нет связи с сервером';
    const detail: unknown = err.response.data?.detail;
    if (err.response.status === 422) return 'Проверьте введённые данные';
    if (typeof detail === 'string' && detail) return detail;
  }
  return fallback;
};

/** Region name; `null` means the region was deleted. */
export const regionLabel = (name: string | null): string => name ?? 'удалённый регион';
