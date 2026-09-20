/**
 * REST client for the location resource gathering feature (FEAT-128).
 *
 * Mirrors API contracts from feature file section 3.1. Auth is supplied by
 * the global axios request interceptor in `axiosSetup.ts` — no explicit
 * `Authorization` header is set here. Errors are propagated to callers
 * (Redux thunks) which must surface a Russian-language message to the user
 * (see CLAUDE.md "Frontend Error Display" mandate).
 */
import axios from 'axios';
import type {
  StartGatheringRequest,
  StartGatheringResponse,
  CancelGatheringResponse,
  ActiveGatheringResponse,
  GatheringSkill,
  GatheringSkillsResponse,
  GatheringTool,
  ToolCategory,
  GatheringNodeAdminListItem,
  GatheringNodeAdminCreate,
  GatheringNodeAdminUpdate,
} from '../types/gathering';

// ── Player-facing endpoints (locations-service) ────────────────────────────

export const startGathering = async (
  locationId: number,
  nodeId: number,
  body: StartGatheringRequest,
): Promise<StartGatheringResponse> => {
  const { data } = await axios.post<StartGatheringResponse>(
    `/locations/${locationId}/gathering-nodes/${nodeId}/start`,
    body,
  );
  return data;
};

export const cancelGathering = async (
  locationId: number,
  nodeId: number,
  characterId: number,
): Promise<CancelGatheringResponse> => {
  const { data } = await axios.post<CancelGatheringResponse>(
    `/locations/${locationId}/gathering-nodes/${nodeId}/cancel`,
    { character_id: characterId },
  );
  return data;
};

export const getActiveGathering = async (
  characterId: number,
): Promise<ActiveGatheringResponse> => {
  const { data } = await axios.get<ActiveGatheringResponse>(
    `/locations/characters/${characterId}/active_gathering`,
  );
  return data;
};

// ── Inventory-service endpoints (skills + tools) ───────────────────────────

export const getGatheringSkills = async (
  characterId: number,
): Promise<GatheringSkill[]> => {
  const { data } = await axios.get<GatheringSkillsResponse>(
    `/inventory/characters/${characterId}/gathering-skills`,
  );
  return data.skills;
};

/**
 * One row of `GET /inventory/{id}/items`: the per-character instance, with the
 * shared item template nested under `item`. `GatheringTool` is flat, so the
 * two shapes must be reconciled here — casting the response straight to
 * `GatheringTool[]` left `max_durability`, `tool_category` and the bonuses
 * `undefined`, which made `ToolSelectionModal` drop every tool as unusable.
 */
interface InventoryToolRow {
  id: number;
  item_id: number;
  quantity: number;
  current_durability: number | null;
  item: {
    name: string;
    image: string | null;
    item_type: string;
    item_rarity: string;
    tool_category: ToolCategory;
    max_durability: number | null;
    gather_double_chance_bonus: number | null;
    gather_speed_bonus_pct: number | null;
    gather_stamina_bonus_pct: number | null;
  };
}

const toGatheringTool = (row: InventoryToolRow): GatheringTool => ({
  id: row.id,
  item_id: row.item_id,
  quantity: row.quantity,
  name: row.item.name,
  image: row.item.image,
  item_type: 'gathering_tool',
  item_rarity: row.item.item_rarity,
  tool_category: row.item.tool_category,
  max_durability: row.item.max_durability ?? 0,
  current_durability: row.current_durability,
  gather_double_chance_bonus: row.item.gather_double_chance_bonus ?? 0,
  gather_speed_bonus_pct: row.item.gather_speed_bonus_pct ?? 0,
  gather_stamina_bonus_pct: row.item.gather_stamina_bonus_pct ?? 0,
});

export const getToolsByCategory = async (
  inventoryId: number,
  category: ToolCategory,
): Promise<GatheringTool[]> => {
  const { data } = await axios.get<InventoryToolRow[]>(
    `/inventory/${inventoryId}/items`,
    { params: { item_type: 'gathering_tool', category } },
  );
  return data.map(toGatheringTool);
};

// ── Admin CRUD (locations-service) ─────────────────────────────────────────

export const adminListNodes = async (
  locationId: number,
): Promise<GatheringNodeAdminListItem[]> => {
  const { data } = await axios.get<GatheringNodeAdminListItem[]>(
    `/locations/admin/locations/${locationId}/gathering-nodes`,
  );
  return data;
};

export const adminCreateNode = async (
  locationId: number,
  body: GatheringNodeAdminCreate,
): Promise<GatheringNodeAdminListItem> => {
  const { data } = await axios.post<GatheringNodeAdminListItem>(
    `/locations/admin/locations/${locationId}/gathering-nodes`,
    body,
  );
  return data;
};

export const adminUpdateNode = async (
  _locationId: number,
  nodeId: number,
  body: GatheringNodeAdminUpdate,
): Promise<GatheringNodeAdminListItem> => {
  // Per spec 3.1.2, the update path is keyed by node_id only:
  //   PUT /locations/admin/gathering-nodes/{node_id}
  // The locationId arg is kept in the signature for symmetry with create/list.
  const { data } = await axios.put<GatheringNodeAdminListItem>(
    `/locations/admin/gathering-nodes/${nodeId}`,
    body,
  );
  return data;
};

export const adminDeleteNode = async (
  _locationId: number,
  nodeId: number,
): Promise<void> => {
  await axios.delete(`/locations/admin/gathering-nodes/${nodeId}`);
};

export const adminRestoreNode = async (
  _locationId: number,
  nodeId: number,
): Promise<GatheringNodeAdminListItem> => {
  const { data } = await axios.post<GatheringNodeAdminListItem>(
    `/locations/admin/gathering-nodes/${nodeId}/restore`,
  );
  return data;
};
