import { useCallback } from 'react';
import { useAppSelector } from '../redux/store';
import { selectCurrencyForms } from '../redux/slices/economySlice';
import { formatCurrency, pluralRu, type CurrencyForms } from '../utils/currency';

/**
 * Currency word forms from the server (defaults until loaded) and a formatter
 * bound to them. Components re-render when the forms arrive.
 *
 * `format(1500)` → «1 500 золотых»; `format(1500, true)` → «1 500 зол.»;
 * `word(3)` → «золотых» (when the number is rendered separately).
 */
export const useCurrency = (): {
  forms: CurrencyForms;
  format: (n: number, short?: boolean) => string;
  word: (n: number) => string;
} => {
  const forms = useAppSelector(selectCurrencyForms);
  const format = useCallback(
    (n: number, short = false) => formatCurrency(n, { forms, short }),
    [forms],
  );
  const word = useCallback(
    (n: number) => pluralRu(n, forms.one, forms.few, forms.many),
    [forms],
  );
  return { forms, format, word };
};

export default useCurrency;
