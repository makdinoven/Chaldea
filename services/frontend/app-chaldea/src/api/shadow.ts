import axios from 'axios';

/**
 * FEAT-201 — player side of «Скрытность» (character-service `shadow_api.py`, contract §3.4).
 * Private: owner or staff only (403 for a stranger, 404 for an unknown character).
 */
export interface StealthInfo {
  /** Stored total: points + gear + food + perks (the number the profile shows) */
  stealth: number;
  /** Out-of-battle subclass points (Ассасин / Фокусник / Агент), added before the cap */
  subclass_bonus: number;
  subclass_name: string | null;
  /** FEAT-195 cap of (stealth + subclass_bonus) */
  effective: number;
  /** «−X % к шансу быть замеченным» */
  reduction_pct: number;
  pct_per_point: number;
  max_reduction_pct: number;
}

export const getStealth = async (characterId: number): Promise<StealthInfo> => {
  const { data } = await axios.get<StealthInfo>(`/characters/${characterId}/stealth`);
  return data;
};
