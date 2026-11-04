import axios from 'axios';

/**
 * FEAT-199 — player side of renown (character-service `shadow_api.py`, contract §3.7).
 * Fame is public (the passport carries only its tier name); «Слухи в подполье» (infamy)
 * is private — owner or staff only. The backend never sends numbers to players:
 * only tier names and the position inside the fame tier (`progress`, 0..1).
 * Admin endpoints live elsewhere.
 */

export interface RenownFame {
  tier_code: string;
  tier_name: string;
  /** 0..1 inside the current tier band */
  progress: number;
  /** null on the top tier */
  next_tier_name: string | null;
}

export interface RenownRumors {
  tier_code: string;
  tier_name: string;
}

export interface RenownView {
  fame: RenownFame;
  rumors: RenownRumors;
}

export interface FameTierPublic {
  code: string;
  name: string;
  /** lowest tier first */
  sort_order: number;
}

/** Private: 403 for a stranger, 404 for an unknown character. */
export const fetchRenown = async (characterId: number): Promise<RenownView> => {
  const { data } = await axios.get<RenownView>(`/characters/${characterId}/renown`);
  return data;
};

/** Public fame ladder (names only). */
export const fetchFameTiers = async (): Promise<FameTierPublic[]> => {
  const { data } = await axios.get<FameTierPublic[]>('/characters/renown/fame-tiers');
  return data;
};
