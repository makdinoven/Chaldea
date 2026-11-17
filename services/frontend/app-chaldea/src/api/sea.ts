import axios from 'axios';
import { BASE_URL } from './api';
import { apiErrorMessage } from './errors';
import type { CaptainView, DeckView, SeaMessage, SeaNoticeData, SeaPass } from '../types/sea';

/**
 * FEAT-213 — sea routes, player side (character-service S1–S5, feature file 3.13).
 *
 * A 403 here is a game rule (no «Диалог с НПС» post, reputation, not your character), not missing rights — the
 * caller shows the server's own text, so the global 403 toast is skipped.
 */

const SEA = `${BASE_URL}/characters/sea`;
const QUIET_403 = { skipForbiddenToast: true };
const HTTP_PAYMENT_REQUIRED = 402;

/** S1 — the Captain dialogue: route, destinations with fares, sailor / stowaway offers, my passes. */
export const fetchCaptain = async (npcId: number, characterId: number): Promise<CaptainView> => {
  const { data } = await axios.get<CaptainView>(`${SEA}/captain/${npcId}`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

/** S2 — buy a ticket up to the stop reached by trip `toTrip`. */
export const buyTicket = async (
  shipId: number,
  body: { character_id: number; npc_id: number; to_trip: number },
): Promise<SeaPass> => {
  const { data } = await axios.post<SeaPass>(`${SEA}/ships/${shipId}/tickets`, body, QUIET_403);
  return data;
};

/** S3 — hire on as a sailor for the next trip. */
export const hireSailor = async (shipId: number, body: { character_id: number; npc_id: number }): Promise<SeaPass> => {
  const { data } = await axios.post<SeaPass>(`${SEA}/ships/${shipId}/sailor`, body, QUIET_403);
  return data;
};

/** S4 — try to sneak aboard (the answer is neutral; the check happens at departure). */
export const sneakAboard = async (shipId: number, characterId: number): Promise<SeaMessage> => {
  const { data } = await axios.post<SeaMessage>(
    `${SEA}/ships/${shipId}/stowaway`,
    { character_id: characterId },
    QUIET_403,
  );
  return data;
};

/** S5 — the deck header; 404 when the location is not a deck. */
export const fetchDeck = async (locationId: number, characterId: number): Promise<DeckView> => {
  const { data } = await axios.get<DeckView>(`${SEA}/decks/${locationId}`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

/** Russian text of a sea API failure; the 402 of a ticket carries an object `{message, required, balance}`. */
export const seaErrorMessage = (err: unknown, fallback: string): string => {
  if (axios.isAxiosError(err) && err.response?.status === HTTP_PAYMENT_REQUIRED) {
    const detail = (err.response.data as { detail?: unknown } | undefined)?.detail;
    if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
      return (detail as { message: string }).message;
    }
  }
  return apiErrorMessage(err, fallback);
};

/* ── `ws_type="sea"` notices → open pages (useWebSocket announces, LocationPage / deck header listen) ── */

export const SEA_EVENT = 'chaldea:sea';

/** Events after which the character stands somewhere else (put ashore by the system). */
export const SEA_MOVED_EVENTS: ReadonlySet<string> = new Set([
  'ashore',
  'sailor_ashore',
  'caught',
  'safe_landing',
  'ship_deleted',
]);

export const announceSeaNotice = (data: SeaNoticeData): void => {
  window.dispatchEvent(new CustomEvent<SeaNoticeData>(SEA_EVENT, { detail: data }));
};

/** Subscribes to sea notices; returns the unsubscribe function. */
export const onSeaNotice = (handler: (data: SeaNoticeData) => void): (() => void) => {
  const listener = (e: Event) => handler((e as CustomEvent<SeaNoticeData>).detail ?? {});
  window.addEventListener(SEA_EVENT, listener);
  return () => window.removeEventListener(SEA_EVENT, listener);
};
