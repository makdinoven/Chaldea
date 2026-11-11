import axios from 'axios';
import { BASE_URL } from './api';
import type { FenceOffer, FenceSellRequest, FenceSellResponse } from '../types/caravans';

/**
 * FEAT-211 — «Скупщик» NPC: selling stolen bales (locations-service, feature file 3.13 A13/A14).
 *
 * 403 = a game gate (no «Диалог с НПС» post, NPC tier) — shown by the modal itself.
 */

const QUIET_403 = { skipForbiddenToast: true };

/** What of the bag this fence buys now and at what price (A13). */
export const fetchFenceOffers = async (npcId: number, characterId: number): Promise<FenceOffer[]> => {
  const { data } = await axios.get<FenceOffer[]>(`${BASE_URL}/locations/npcs/${npcId}/fence/offers`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data ?? [];
};

/** Sells stolen goods to the fence; the money comes from the fence's own cash (A14). */
export const sellToFence = async (npcId: number, body: FenceSellRequest): Promise<FenceSellResponse> => {
  const { data } = await axios.post<FenceSellResponse>(
    `${BASE_URL}/locations/npcs/${npcId}/fence/sell`,
    body,
    QUIET_403,
  );
  return data;
};
