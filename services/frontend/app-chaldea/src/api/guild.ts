import axios from 'axios';
import { BASE_URL } from './api';
import type { GuildActionOut, GuildAdminOut, GuildAdminQuery, GuildHandInRequest, GuildView } from '../types/economy';

/**
 * FEAT-193 — guild orders API (character-service, feature file 3.10).
 *
 * Player side: a 403 is a game rule (no «Диалог с НПС» post, not your character), not missing rights —
 * the caller toasts the server's own text, so the global 403 toast is skipped (same as the bank and the mint).
 */

const GUILD = `${BASE_URL}/characters/economy/guild`;
const ADMIN_GUILD = '/characters/admin/economy/guild';
const QUIET_403 = { skipForbiddenToast: true };

/* ------------------------------------------------------------------------------------------------ player */

export const getGuildView = async (npcId: number, characterId: number): Promise<GuildView> => {
  const { data } = await axios.get<GuildView>(`${GUILD}/npc/${npcId}`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

/** Hands items to the «Гильдия торговцев»; the same `request_id` twice → one posting, the second gets 409. */
export const postGuildHandIn = async (npcId: number, body: GuildHandInRequest): Promise<GuildActionOut> => {
  const { data } = await axios.post<GuildActionOut>(`${GUILD}/npc/${npcId}/hand-in`, body, QUIET_403);
  return data;
};

/* ------------------------------------------------------------------------------------------------- admin */

/** Params, totals, regions with budgets / guild masters and one page of orders (`economy:read`). */
export const fetchGuildAdmin = async (query: GuildAdminQuery = {}): Promise<GuildAdminOut> => {
  const { data } = await axios.get<GuildAdminOut>(ADMIN_GUILD, { params: query });
  return data;
};
