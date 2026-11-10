import axios from 'axios';

/**
 * FEAT-209 — admin NPC «Готов» flag (character-service,
 * `PUT /characters/admin/npcs/{id}/ready`, needs `npcs:update`).
 * Country / region options moved to `api/adminGeo.ts`, `readyTooltip` to
 * `components/Admin/ExpandableList/readyMark.ts` (FEAT-210).
 */

export interface NpcReadyResponse {
  id: number;
  npc_ready: boolean;
  npc_ready_at: string | null;
  npc_ready_by: string | null;
}

export const setNpcReady = async (npcId: number, ready: boolean): Promise<NpcReadyResponse> => {
  const { data } = await axios.put<NpcReadyResponse>(`/characters/admin/npcs/${npcId}/ready`, { ready });
  return data;
};
