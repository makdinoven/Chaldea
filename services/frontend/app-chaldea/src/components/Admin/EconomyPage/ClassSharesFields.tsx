/**
 * FEAT-194: three class-share inputs (percent) with a live sum and a bar preview — region editor and templates.
 * The API takes shares 0..1 that sum to 1 ± 0.001; the UI edits percent.
 */
import type { EconClassKey, EconClassMix } from '../../../types/economy';
import { ClassMixBar } from '../../WorldPage/RegionClassBar';
import { formatDecimal } from './economyLabels';
import { CLASS_LABELS, CLASS_ORDER, sharePct } from './regionBits';

export type ClassSharesDraft = Record<EconClassKey, string>;

const PERCENT = 100;
/** Backend tolerance: sum 1 ± 0.001 → ±0.1 percentage points. */
const SUM_TOLERANCE_PCT = 0.1;
/** Shares are stored with 6 decimals → percent with 4. */
const PCT_DIGITS = 1e4;

export const EMPTY_SHARES: ClassSharesDraft = { poor: '', middling: '', rich: '' };

export const sharesToDraft = (mix: EconClassMix | null | undefined): ClassSharesDraft =>
  mix
    ? {
        poor: String(Math.round(mix.poor * PERCENT * PCT_DIGITS) / PCT_DIGITS),
        middling: String(Math.round(mix.middling * PERCENT * PCT_DIGITS) / PCT_DIGITS),
        rich: String(Math.round(mix.rich * PERCENT * PCT_DIGITS) / PCT_DIGITS),
      }
    : { ...EMPTY_SHARES };

const parsePct = (raw: string): number => {
  const v = raw.trim().replace(',', '.');
  return v === '' ? Number.NaN : Number(v);
};

export const sharesEmpty = (d: ClassSharesDraft): boolean => CLASS_ORDER.every((k) => d[k].trim() === '');

export const sharesSum = (d: ClassSharesDraft): number =>
  CLASS_ORDER.reduce((acc, k) => acc + (Number.isFinite(parsePct(d[k])) ? parsePct(d[k]) : 0), 0);

/** Russian error or null. `allowEmpty` — all three empty means «no classes / keep». */
export const sharesError = (d: ClassSharesDraft, allowEmpty: boolean): string | null => {
  if (sharesEmpty(d)) return allowEmpty ? null : 'Укажите все три доли';
  if (CLASS_ORDER.some((k) => d[k].trim() === '')) return 'Укажите все три доли';
  for (const k of CLASS_ORDER) {
    const n = parsePct(d[k]);
    if (!Number.isFinite(n) || n < 0 || n > PERCENT) return 'Каждая доля — от 0 до 100 %';
  }
  if (Math.abs(sharesSum(d) - PERCENT) > SUM_TOLERANCE_PCT) return 'Сумма долей должна быть 100 %';
  return null;
};

/** Percent draft → API shares (6 decimals). Call only when `sharesError` is null and the draft is not empty. */
export const draftToShares = (d: ClassSharesDraft): EconClassMix => {
  const share = (k: EconClassKey) => Math.round((parsePct(d[k]) / PERCENT) * 1e6) / 1e6;
  return { poor: share('poor'), middling: share('middling'), rich: share('rich') };
};

interface ClassSharesFieldsProps {
  idPrefix: string;
  value: ClassSharesDraft;
  onChange: (next: ClassSharesDraft) => void;
  disabled?: boolean;
  /** Empty draft is valid (region without classes). */
  allowEmpty?: boolean;
  /** Template defaults — shown as a hint with a «как в шаблоне» button. */
  base?: EconClassMix | null;
}

const ClassSharesFields = ({ idPrefix, value, onChange, disabled = false, allowEmpty = false, base }: ClassSharesFieldsProps) => {
  const error = sharesError(value, allowEmpty);
  const empty = sharesEmpty(value);
  const sum = sharesSum(value);
  const preview = !empty && !error ? draftToShares(value) : null;
  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="grid grid-cols-3 gap-3">
        {CLASS_ORDER.map((k) => (
          <div key={k} className="flex flex-col gap-1 min-w-0">
            <label htmlFor={`${idPrefix}-${k}`} className="text-white/60 text-xs uppercase tracking-[0.06em] truncate">
              {CLASS_LABELS[k]}, %
            </label>
            <input
              id={`${idPrefix}-${k}`}
              type="number"
              inputMode="decimal"
              min={0}
              max={100}
              step={0.5}
              className={`input-underline w-full ${error && !empty ? '!border-site-red' : ''}`}
              value={value[k]}
              disabled={disabled}
              onChange={(e) => onChange({ ...value, [k]: e.target.value })}
            />
          </div>
        ))}
      </div>
      {preview && <ClassMixBar poor={preview.poor} middling={preview.middling} rich={preview.rich} heightClass="h-1.5" />}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {!empty && (
          <span className={error ? 'text-site-red' : 'text-white/50'}>
            Сумма: {formatDecimal(sum, 2)} %{error ? ` — ${error}` : ''}
          </span>
        )}
        {empty && error && <span className="text-site-red">{error}</span>}
        {empty && !error && <span className="text-white/40">Без классов</span>}
        {base && (
          <span className="text-white/40">
            как в шаблоне: {CLASS_ORDER.map((k) => sharePct(base[k])).join(' / ')} %
            {!disabled && (
              <button
                type="button"
                onClick={() => onChange(sharesToDraft(base))}
                className="ml-2 text-site-blue hover:text-gold transition-colors duration-200 ease-site"
              >
                подставить
              </button>
            )}
          </span>
        )}
      </div>
    </div>
  );
};

export default ClassSharesFields;
