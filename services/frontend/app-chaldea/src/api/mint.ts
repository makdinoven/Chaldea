import axios from 'axios';
import { BASE_URL } from './api';
import type {
  MintActionOut,
  MintAdminOut,
  MintCountry,
  MintCountryIn,
  MintItem,
  MintItemIn,
  MintRequest,
  MintView,
  QuotaEntry,
} from '../types/economy';

/**
 * FEAT-191 — mint and season quota API (character-service, feature file 3.10).
 *
 * Player side: a 403 is a game rule (no «Диалог с НПС» post, not your character), not missing rights —
 * the caller toasts the server's own text, so the global 403 toast is skipped (same as the bank).
 */

const MINT = `${BASE_URL}/characters/economy/mint`;
const ADMIN_MINT = '/characters/admin/economy/mint';
const QUIET_403 = { skipForbiddenToast: true };

/* ------------------------------------------------------------------------------------------------ player */

export const getMintView = async (npcId: number, characterId: number): Promise<MintView> => {
  const { data } = await axios.get<MintView>(`${MINT}/npc/${npcId}`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

/** Hands ore to the Монетчик; the same `request_id` twice → one posting, the second gets 409. */
export const postMint = async (npcId: number, body: MintRequest): Promise<MintActionOut> => {
  const { data } = await axios.post<MintActionOut>(`${MINT}/npc/${npcId}/mint`, body, QUIET_403);
  return data;
};

/* ------------------------------------------------------------------------------------------------- admin */

/** Unwraps a bare list or `{ items }`. */
const unwrapList = <T,>(data: T[] | { items: T[] }): T[] => (Array.isArray(data) ? data : data.items);

export const fetchMintAdmin = async (): Promise<MintAdminOut> => {
  const { data } = await axios.get<MintAdminOut>(ADMIN_MINT);
  return data;
};

/** Capital, per-country limit and the enabled flag — needs economy:settings + economy:emit. */
export const putMintCountry = async (countryId: number, body: MintCountryIn): Promise<MintCountry> => {
  const { data } = await axios.put<MintCountry>(`${ADMIN_MINT}/countries/${countryId}`, body);
  return data;
};

export const fetchMintItems = async (): Promise<MintItem[]> => {
  const { data } = await axios.get<MintItem[] | { items: MintItem[] }>(`${ADMIN_MINT}/items`);
  return unwrapList(data);
};

/** Adds or updates an accepted ore (rate per piece) — needs economy:settings + economy:emit. */
export const putMintItem = async (itemId: number, body: MintItemIn): Promise<MintItem> => {
  const { data } = await axios.put<MintItem>(`${ADMIN_MINT}/items/${itemId}`, body);
  return data;
};

export const deleteMintItem = async (itemId: number): Promise<void> => {
  await axios.delete(`${ADMIN_MINT}/items/${itemId}`);
};

export const fetchMintQuotas = async (limit = 20): Promise<QuotaEntry[]> => {
  const { data } = await axios.get<QuotaEntry[] | { items: QuotaEntry[] }>(`${ADMIN_MINT}/quotas`, {
    params: { limit },
  });
  return unwrapList(data);
};
