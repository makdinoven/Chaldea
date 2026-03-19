// Game time calculation utility — pure functions, no side effects.
// Algorithm must match backend (locations-service) implementation exactly.

export interface GameTimeResult {
  year: number;
  segmentName: string;
  segmentType: 'season' | 'transition';
  week: number | null;
  isTransition: boolean;
}

interface YearSegment {
  readonly name: string;
  readonly type: 'season' | 'transition';
  readonly realDays: number;
}

export const YEAR_SEGMENTS: readonly YearSegment[] = [
  { name: 'spring', type: 'season', realDays: 39 },
  { name: 'beltane', type: 'transition', realDays: 10 },
  { name: 'summer', type: 'season', realDays: 39 },
  { name: 'lughnasad', type: 'transition', realDays: 10 },
  { name: 'autumn', type: 'season', realDays: 39 },
  { name: 'samhain', type: 'transition', realDays: 10 },
  { name: 'winter', type: 'season', realDays: 39 },
  { name: 'imbolc', type: 'transition', realDays: 10 },
] as const;

export const DAYS_PER_YEAR = 196;
export const DAYS_PER_WEEK = 3;

export const SEGMENT_LABELS: Record<string, string> = {
  spring: 'Весна',
  summer: 'Лето',
  autumn: 'Осень',
  winter: 'Зима',
  beltane: 'Белтайн',
  lughnasad: 'Лугнасад',
  samhain: 'Самайн',
  imbolc: 'Имболк',
};

/**
 * Maps segment names to react-feather icon component names.
 * Import the actual components from react-feather using these keys.
 */
export const SEGMENT_ICONS: Record<string, string> = {
  spring: 'Droplet',
  summer: 'Sun',
  autumn: 'Wind',
  winter: 'CloudSnow',
  beltane: 'Zap',
  lughnasad: 'Award',
  samhain: 'Moon',
  imbolc: 'Star',
};

const MS_PER_DAY = 86400000;

/**
 * Compute the current in-game time from epoch, offset, and server time.
 *
 * @param epoch   - ISO datetime string of the epoch (day 1, week 1, spring, year 1)
 * @param offsetDays - admin-configured day offset (positive = advance, negative = rewind)
 * @param serverTime - ISO datetime string of the current server time
 */
export function computeGameTime(
  epoch: string,
  offsetDays: number,
  serverTime: string,
): GameTimeResult {
  const epochMs = new Date(epoch).getTime();
  const serverMs = new Date(serverTime).getTime();

  let elapsed = Math.floor((serverMs - epochMs) / MS_PER_DAY) + offsetDays;

  if (elapsed < 0) {
    elapsed = 0;
  }

  const year = Math.floor(elapsed / DAYS_PER_YEAR) + 1;
  const dayInYear = elapsed % DAYS_PER_YEAR;

  let cumulative = 0;
  for (const segment of YEAR_SEGMENTS) {
    if (dayInYear < cumulative + segment.realDays) {
      const dayInSegment = dayInYear - cumulative;

      if (segment.type === 'season') {
        return {
          year,
          segmentName: segment.name,
          segmentType: 'season',
          week: Math.floor(dayInSegment / DAYS_PER_WEEK) + 1,
          isTransition: false,
        };
      }

      return {
        year,
        segmentName: segment.name,
        segmentType: 'transition',
        week: null,
        isTransition: true,
      };
    }
    cumulative += segment.realDays;
  }

  // Fallback (should never reach here with correct DAYS_PER_YEAR)
  return {
    year,
    segmentName: 'spring',
    segmentType: 'season',
    week: 1,
    isTransition: false,
  };
}
