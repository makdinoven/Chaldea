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

export const getToolsByCategory = async (
  inventoryId: number,
  category: ToolCategory,
): Promise<GatheringTool[]> => {
  const { data } = await axios.get<GatheringTool[]>(
    `/inventory/${inventoryId}/items`,
    { params: { item_type: 'gathering_tool', category } },
  );
  return data;
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
