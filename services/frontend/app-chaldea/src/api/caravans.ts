import axios from 'axios';
import { BASE_URL } from './api';
import type {
  CaravanRaidRequest,
  CaravanRaidResponse,
  CaravanRaidShare,
  CaravansHereResponse,
} from '../types/caravans';

/**
 * FEAT-211 — physical caravans on the location page (character-service, feature file 3.13 A1/A2).
 *
 * A 403 here is a game rule (no «Налёт на караван» post, not your character), not missing rights —
 * the caller shows the server's own text, so the global 403 toast is skipped.
 */

const CARAVANS = `${BASE_URL}/characters/caravans`;
const QUIET_403 = { skipForbiddenToast: true };

/** Caravans standing where the character is now — group and guard count only, never the route (A1). */
export const fetchCaravansHere = async (characterId: number): Promise<CaravansHereResponse> => {
  const { data } = await axios.get<CaravansHereResponse>(`${CARAVANS}/here`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

/** Starts a raid (solo or with the co-located squad); answers with the battle to open (A2). */
export const startCaravanRaid = async (
  caravanId: number,
  body: CaravanRaidRequest,
): Promise<CaravanRaidResponse> => {
  const { data } = await axios.post<CaravanRaidResponse>(`${CARAVANS}/${caravanId}/raid`, body, QUIET_403);
  return data;
};

/** The character's own loot of the raid fought in this battle; `raid: false` for any other battle. */
export const fetchCaravanRaidShare = async (
  battleId: number,
  characterId: number,
): Promise<CaravanRaidShare> => {
  const { data } = await axios.get<CaravanRaidShare>(`${CARAVANS}/raids/by-battle/${battleId}`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};
