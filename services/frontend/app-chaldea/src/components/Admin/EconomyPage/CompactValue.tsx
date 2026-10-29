import { useCallback } from 'react';
import { useCurrency } from '../../../hooks/useCurrency';
import { COMPACT_MONEY_FROM, compactNumber, exactNumber } from '../../../utils/compactNumber';

/**
 * FEAT-186 — admin economy money: sums from 100 000 are shown short («4.5 м марок»), the exact amount is in
 * `exact` (for a `title`). Smaller sums are the usual exact «1 500 марок». Admin UI only — player money stays exact.
 */
export const useBigMoney = (): {
  /** `short` uses the currency abbreviation («4.5 м ṃ»), like `format(n, true)`. */
  big: (n: number, short?: boolean) => string;
  exact: (n: number) => string;
} => {
  const { format, forms } = useCurrency();
  const big = useCallback(
    (n: number, short = false) =>
      Math.abs(n) >= COMPACT_MONEY_FROM ? `${compactNumber(n)} ${short ? forms.short : forms.many}` : format(n, short),
    [format, forms],
  );
  const exact = useCallback((n: number) => format(n), [format]);
  return { big, exact };
};

interface BigMoneyProps {
  value: number;
  className?: string;
  /** Currency abbreviation instead of the word. */
  short?: boolean;
}

/** A big admin sum: short text, exact amount on hover (only when it was shortened). */
export const BigMoney = ({ value, className, short = false }: BigMoneyProps) => {
  const { big, exact } = useBigMoney();
  const shortened = Math.abs(value) >= COMPACT_MONEY_FROM;
  return (
    <span className={className} title={shortened ? exact(value) : undefined}>
      {big(value, short)}
    </span>
  );
};

interface PopulationProps {
  value: number;
  /** Population the tick computes with (lore / scale), when the backend reports it. */
  sim?: number | null;
  className?: string;
  /** Text after the number («жит.»), part of the same span. */
  suffix?: string;
}

/** «4 000 000 жит. · в расчёте 40 000» — the hover text of a population. */
export const populationTitle = (value: number, sim?: number | null): string =>
  `${exactNumber(value)} жит.${sim != null ? ` · в расчёте ${exactNumber(sim)}` : ''}`;

/** Lore population, short («4.0 м»), exact on hover. */
export const Population = ({ value, sim, className, suffix }: PopulationProps) => (
  <span className={className} title={populationTitle(value, sim)}>
    {compactNumber(value)}
    {suffix && ` ${suffix}`}
  </span>
);
