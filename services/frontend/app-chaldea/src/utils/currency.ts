/**
 * FEAT-181 — the world currency's name is a setting edited by the lore admin
 * («Экономика»), so no component may spell the currency word itself.
 *
 * Forms (Russian needs several):
 *  - `name`     — nominative, for labels: «Золото»
 *  - `genitive` — mass genitive: «Недостаточно золота», «Всего золота на складе»
 *  - `one` / `few` / `many` — counting forms: «1 золотой», «3 золотых», «5 золотых»
 *  - `short`    — abbreviation for tight places: «100 зол.»
 *
 * React code reads the forms through `useCurrency()`; non-React code (Redux
 * slices, plain helpers) reads the module mirror via `getCurrencyForms()`,
 * which `economySlice` keeps in sync once the server forms are loaded.
 */

export interface CurrencyForms {
  name: string;
  genitive: string;
  one: string;
  few: string;
  many: string;
  short: string;
}

/** Used until `GET /characters/economy/currency` answers (and if it fails). */
export const DEFAULT_CURRENCY_FORMS: CurrencyForms = {
  name: 'Золото',
  genitive: 'золота',
  one: 'золотой',
  few: 'золотых',
  many: 'золотых',
  short: 'зол.',
};

let currentForms: CurrencyForms = DEFAULT_CURRENCY_FORMS;

export const getCurrencyForms = (): CurrencyForms => currentForms;

export const setCurrencyForms = (forms: CurrencyForms): void => {
  currentForms = forms;
};

/** Russian plural choice: 1 / 2–4 / 5–20 (and 11–14 always «many»). */
export const pluralRu = (n: number, one: string, few: string, many: string): string => {
  const abs = Math.abs(Math.trunc(n));
  const mod100 = abs % 100;
  const mod10 = abs % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
};

export interface FormatCurrencyOptions {
  /** Use the abbreviation («100 зол.») instead of the counting form. */
  short?: boolean;
  /** Forms to use; defaults to the module mirror (server forms once loaded). */
  forms?: CurrencyForms;
}

/** «1 золотой», «3 золотых», «1 500 золотых»; with `short` — «1 500 зол.». */
export const formatCurrency = (n: number, opts: FormatCurrencyOptions = {}): string => {
  const forms = opts.forms ?? currentForms;
  const amount = n.toLocaleString('ru-RU');
  if (opts.short) return `${amount} ${forms.short}`;
  return `${amount} ${pluralRu(n, forms.one, forms.few, forms.many)}`;
};

/** Upper-cases the first letter — for forms used at the start of a sentence. */
export const capitalize = (s: string): string => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
