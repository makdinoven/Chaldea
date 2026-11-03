/**
 * FEAT-197: visual tone of a reputation tier. The 8 tier codes are fixed by the backend
 * (`reputation_core.TIER_CODES`); names / thresholds are editable, so only the code is used here.
 */

export type ReputationTone = 'bad' | 'neutral' | 'good';

const BAD_TIERS = new Set(['outlaw', 'outcast', 'watched']);
const GOOD_TIERS = new Set(['familiar', 'trusted', 'defender', 'legend']);

export const reputationTone = (tierCode: string): ReputationTone => {
  if (BAD_TIERS.has(tierCode)) return 'bad';
  if (GOOD_TIERS.has(tierCode)) return 'good';
  return 'neutral';
};

/** Text colour of the tier name. */
export const REPUTATION_TONE_TEXT: Record<ReputationTone, string> = {
  bad: 'text-site-red',
  neutral: 'text-white/80',
  good: 'text-gold',
};

/** Fill of the tier progress bar. */
export const REPUTATION_TONE_FILL: Record<ReputationTone, string> = {
  bad: 'bg-site-red/80',
  neutral: 'bg-white/60',
  good: 'bg-gradient-to-r from-gold-dark to-gold-light',
};

/** Border / background of a tier chip in the scale legend. */
export const REPUTATION_TONE_CHIP: Record<ReputationTone, string> = {
  bad: 'border-site-red/40 text-site-red',
  neutral: 'border-white/25 text-white/70',
  good: 'border-gold/40 text-gold',
};
