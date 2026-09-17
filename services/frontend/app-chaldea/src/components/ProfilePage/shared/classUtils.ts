// FEAT-166 — helpers for shared primitives.
// Tailwind v3 does not let a later class in `className` beat an earlier one with the
// same CSS property (order is decided by the generated stylesheet), so primitives
// drop their own default when the caller supplies an override.

/** Matches any padding utility (`p-4`, `py-10`, `!pt-2`, `sm:p-6`, `px-[3px]`). */
const PADDING_UTILITY = /(?:^|\s)!?(?:[a-z0-9-]+:)*p[xytblrse]?-/;

/** True when `className` contains a padding utility (any side, any breakpoint). */
export const hasPaddingClass = (className: string | undefined): boolean =>
  !!className && PADDING_UTILITY.test(className);
