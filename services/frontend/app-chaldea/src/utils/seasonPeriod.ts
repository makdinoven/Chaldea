import type { MintSeasonPeriod } from '../types/economy';
import { SEGMENT_LABELS } from './gameTime';
import { formatServerDate } from './serverDate';

/**
 * FEAT-191 — the game «сезон» of the mint limit and the season quota: a season with the festival after it
 * (49 real days, 4 per year). The backend sends the season code, the year and the dates; the year is the
 * calendar's own (already in the lore epoch) — never computed here.
 */

const DATE_OPTS: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit', year: 'numeric' };

/** «12.11.2026» */
export const periodDate = (iso: string | null | undefined): string => formatServerDate(iso, DATE_OPTS);

/** «Весна, 4-й год» */
export const seasonName = (season: string | null | undefined, year: number | null | undefined): string => {
  const name = season ? SEGMENT_LABELS[season] ?? season : 'Сезон';
  return year ? `${name}, ${year}-й год` : name;
};

/** «Весна, 4-й год — до 12.11.2026» */
export const seasonText = (period: MintSeasonPeriod): string =>
  `${seasonName(period.season, period.year)} — до ${periodDate(period.ends_at)}`;
