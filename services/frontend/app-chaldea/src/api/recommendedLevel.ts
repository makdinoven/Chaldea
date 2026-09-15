import axios from 'axios';


export type RecommendedLevelTarget = 'country' | 'region';

/** Computed range from the locations inside, and the admin override per bound */
export interface RecommendedLevelInfo {
  auto_min: number | null;
  auto_max: number | null;
  manual_min: number | null;
  manual_max: number | null;
}

// Level 1 means "not set" (utils/recommendedLevel.ts), so a manual bound starts at 2
export const RECOMMENDED_LEVEL_MIN = 2;
export const RECOMMENDED_LEVEL_MAX = 999;

export const fetchRecommendedLevel = async (
  targetType: RecommendedLevelTarget,
  targetId: number,
): Promise<RecommendedLevelInfo> => {
  const { data } = await axios.get<RecommendedLevelInfo>(`/locations/recommended-level/${targetType}/${targetId}`);
  return data;
};

export interface ParsedLevelRange {
  min: number | null;
  max: number | null;
  error: string | null;
}

/** Form strings -> payload values; empty = automatic (null) */
export const parseLevelRange = (minRaw: string, maxRaw: string): ParsedLevelRange => {
  const parse = (raw: string) => (raw.trim() === '' ? null : Number(raw));
  const min = parse(minRaw);
  const max = parse(maxRaw);
  for (const value of [min, max]) {
    if (value !== null && (!Number.isInteger(value) || value < RECOMMENDED_LEVEL_MIN || value > RECOMMENDED_LEVEL_MAX)) {
      return { min, max, error: `Рекомендуемый уровень — целое число от ${RECOMMENDED_LEVEL_MIN} до ${RECOMMENDED_LEVEL_MAX} (пустое поле — автоматически)` };
    }
  }
  if (min !== null && max !== null && min > max) {
    return { min, max, error: 'Рекомендуемый уровень: «от» не может быть больше «до»' };
  }
  return { min, max, error: null };
};
