import { InfoTooltip } from '../../CommonComponents/InfoTooltip';
import { FIELD_HINTS, SIM_PARAM_HINTS, type FieldHintKey, type ParamHintText } from './paramHints';
import type { EconSimParams } from '../../../types/economy';

/** Days in the «≈ в месяц» conversion of daily rates (simple interest, a rough guide). */
const DAYS_IN_MONTH = 30;
const PERCENT = 100;

const fmtNum = (n: number): string =>
  Math.abs(n) >= 10_000 ? n.toLocaleString('ru-RU') : String(n).replace('.', ',');

/** 0.0025 → «0,25 %» (up to 3 decimals). */
const fmtPercent = (share: number): string => `${fmtNum(Math.round(share * PERCENT * 1000) / 1000)} %`;

/** «0,1 % в день ≈ 3 % в месяц» — for a daily rate. */
export const ratePerMonthText = (rate: number): string =>
  `${fmtPercent(rate)} в день ≈ ${fmtPercent(rate * DAYS_IN_MONTH)} в месяц`;

/** Numbers of a simulation param — the same values the «Пересчёт» form validates with. */
export interface SimParamNumbers {
  def: number;
  min: number;
  max: number;
  ratePerDay?: boolean;
}

interface HintBodyProps {
  title: string;
  hint: ParamHintText;
  numbers?: SimParamNumbers;
}

const HintBody = ({ title, hint, numbers }: HintBodyProps) => {
  const def = numbers ? fmtNum(numbers.def) + (numbers.ratePerDay ? ` (${ratePerMonthText(numbers.def)})` : '') : hint.def;
  const range = numbers ? `${fmtNum(numbers.min)}–${fmtNum(numbers.max)}` : hint.range;
  return (
    <span className="flex flex-col gap-1.5">
      <span className="text-gold font-medium">{title}</span>
      <span>{hint.what}</span>
      {hint.up && (
        <span>
          <span className="text-white">Если поднять: </span>
          {hint.up}
        </span>
      )}
      {hint.down && (
        <span>
          <span className="text-white">Если опустить: </span>
          {hint.down}
        </span>
      )}
      {hint.safe && (
        <span>
          <span className="text-stat-energy">Безопасно: </span>
          {hint.safe}
        </span>
      )}
      {(def || range) && (
        <span className="text-white/55">
          {def && <>По умолчанию: {def}. </>}
          {range && <>Допустимо: {range}.</>}
        </span>
      )}
    </span>
  );
};

interface ParamHintProps {
  /** Field label — the hint's title and the button's accessible name. */
  label: string;
  className?: string;
}

/** «?» next to a simulation param of «Пересчёт»: text from `paramHints.ts`, numbers from the param definition. */
export const SimParamHint = ({ param, label, numbers, className = '' }: ParamHintProps & { param: keyof EconSimParams; numbers: SimParamNumbers }) => (
  <InfoTooltip
    icon="help"
    size={13}
    label={`Подсказка: ${label}`}
    className={className}
    content={<HintBody title={label} hint={SIM_PARAM_HINTS[param]} numbers={numbers} />}
  />
);

/** «?» next to any other economy field (region, bank, settings, goods groups, templates). */
export const FieldHint = ({ field, label, className = '' }: ParamHintProps & { field: FieldHintKey }) => (
  <InfoTooltip
    icon="help"
    size={13}
    label={`Подсказка: ${label}`}
    className={className}
    content={<HintBody title={label} hint={FIELD_HINTS[field]} />}
  />
);
