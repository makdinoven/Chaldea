/**
 * FEAT-186 — short numbers for big populations and admin economy sums.
 *
 * Rule (dot as the decimal separator, a non-breaking space before the unit):
 *  - |n| < 1 000           → as is, rounded to an integer: «950», «-12»
 *  - thousands  («к»)      → n / 1 000
 *  - millions   («м»)      → n / 1 000 000
 *  - billions   («млрд»)   → n / 1 000 000 000
 *  - a scaled value under 100 keeps exactly one decimal: «1.0 к», «12.5 к», «4.0 м», «4.5 м»;
 *    from 100 it is a whole number: «120 к», «250 м».
 *  - values are rounded, not cut; a value that rounds up to 1 000 of a unit moves to the next one
 *    (999 960 → «1.0 м», not «1000 к»), and one that rounds up to 100 drops its decimal (99 960 → «100 к»).
 *  - negative numbers get a leading minus: «-1.5 м».
 *
 * The exact value goes into a `title` / hint via `exactNumber`.
 */

const UNITS: { size: number; label: string }[] = [
  { size: 1_000_000_000, label: 'млрд' },
  { size: 1_000_000, label: 'м' },
  { size: 1_000, label: 'к' },
];

/** Scaled values from this one on are shown without a decimal. */
const WHOLE_FROM = 100;
const NBSP = ' ';

const scaled = (abs: number, unitIndex: number): string | null => {
  const { size, label } = UNITS[unitIndex];
  const value = abs / size;
  const oneDecimal = Math.round(value * 10) / 10;
  if (oneDecimal < WHOLE_FROM) return `${oneDecimal.toFixed(1)}${NBSP}${label}`;
  const whole = Math.round(value);
  // 999.6 к → move up to «1.0 м» (there is no unit above billions, so those just grow).
  if (whole >= 1000 && unitIndex > 0) return null;
  return `${whole}${NBSP}${label}`;
};

/** «4 000 000» → «4.0 м», «120 000» → «120 к», «950» → «950». */
export const compactNumber = (n: number): string => {
  if (!Number.isFinite(n)) return String(n);
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  if (Math.round(abs) < 1000) return `${sign}${Math.round(abs)}`;
  // The largest unit that fits; 999.6 (rounds to 1 000) falls through to thousands.
  const found = UNITS.findIndex((u) => abs >= u.size);
  const i = found === -1 ? UNITS.length - 1 : found;
  // `scaled` returns null only for i > 0, so the unit above always exists.
  const text = scaled(abs, i) ?? scaled(abs, i - 1);
  return `${sign}${text}`;
};

/** The exact value with Russian digit grouping: «4 000 000». */
export const exactNumber = (n: number): string => n.toLocaleString('ru-RU');

/** Admin economy sums from this size on are shown compact (with the exact value in the title). */
export const COMPACT_MONEY_FROM = 100_000;
