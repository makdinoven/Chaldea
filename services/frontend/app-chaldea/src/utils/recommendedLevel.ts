/**
 * Level 1 is the default for locations nobody has given a level: it means "not set".
 * Such a level is never shown and does not count towards level ranges
 * (mirrors UNSET_RECOMMENDED_LEVEL in locations-service crud.py).
 */
export const UNSET_RECOMMENDED_LEVEL = 1;

export const hasRecommendedLevel = (level: number | null | undefined): level is number =>
  typeof level === 'number' && level > UNSET_RECOMMENDED_LEVEL;
