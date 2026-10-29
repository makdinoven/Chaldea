import axios from 'axios';
import type {
  EconAccount,
  EconAccountsParams,
  EconActionResult,
  EconOperation,
  EconOperationsParams,
  EconPage,
  EconSettings,
  EconSummary,
  EconApplyTemplateBody,
  EconFillBody,
  EconFillResult,
  EconGoodsGroup,
  EconGoodsGroupUpdate,
  EconItemGroupRow,
  EconItemGroupsParams,
  EconItemGroupsUpdate,
  EconRegionDetail,
  EconRegionHistoryRow,
  EconRegionItem,
  EconRegionTemplate,
  EconRegionUpdate,
  EconSimState,
  EconSimUpdate,
  EconTemplateUpdate,
  EconTickRun,
} from '../types/economy';

/** Admin «Экономика» API (FEAT-181, character-service). Auth header comes from axiosSetup. */
const BASE = '/characters/admin/economy';

/** Drops empty values so the backend sees only the filters actually set. */
const clean = (params: object): Record<string, string | number | boolean> => {
  const out: Record<string, string | number | boolean> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') out[key] = value as string | number | boolean;
  });
  return out;
};

export const fetchEconomySummary = async (): Promise<EconSummary> => {
  const { data } = await axios.get<EconSummary>(`${BASE}/summary`);
  return data;
};

export const fetchEconomyAccounts = async (params: EconAccountsParams): Promise<EconPage<EconAccount>> => {
  const { data } = await axios.get<EconPage<EconAccount>>(`${BASE}/accounts`, { params: clean(params) });
  return data;
};

export const fetchEconomyOperations = async (
  params: EconOperationsParams,
): Promise<EconPage<EconOperation>> => {
  const { data } = await axios.get<EconPage<EconOperation>>(`${BASE}/operations`, { params: clean(params) });
  return data;
};

export const postEconomyEmission = async (body: {
  account_id: number;
  amount: number;
  comment: string;
}): Promise<EconActionResult> => {
  const { data } = await axios.post<EconActionResult>(`${BASE}/emission`, body);
  return data;
};

export const postEconomyAdjust = async (body: {
  account_id: number;
  delta: number;
  comment: string;
}): Promise<EconActionResult> => {
  const { data } = await axios.post<EconActionResult>(`${BASE}/adjust`, body);
  return data;
};

export const fetchEconomySettings = async (): Promise<EconSettings> => {
  const { data } = await axios.get<EconSettings>(`${BASE}/settings`);
  return data;
};

export const putEconomySettings = async (body: EconSettings): Promise<EconSettings> => {
  const { data } = await axios.put<EconSettings>(`${BASE}/settings`, body);
  return data;
};

/* ---------------------------------------------- FEAT-182 — living regions (feature file 3.7) */

export const fetchEconomyRegions = async (): Promise<EconRegionItem[]> => {
  const { data } = await axios.get<{ items: EconRegionItem[] }>(`${BASE}/regions`);
  return data.items;
};

export const fetchEconomyRegion = async (regionId: number): Promise<EconRegionDetail> => {
  const { data } = await axios.get<EconRegionDetail>(`${BASE}/regions/${regionId}`);
  return data;
};

export const putEconomyRegion = async (regionId: number, body: EconRegionUpdate): Promise<EconRegionDetail> => {
  const { data } = await axios.put<EconRegionDetail>(`${BASE}/regions/${regionId}`, body);
  return data;
};

export const applyEconomyRegionTemplate = async (
  regionId: number,
  body: EconApplyTemplateBody = {},
): Promise<EconRegionDetail> => {
  const { data } = await axios.post<EconRegionDetail>(`${BASE}/regions/${regionId}/apply-template`, body);
  return data;
};

/** «Заполнить регионы по шаблонам» — needs economy:settings + economy:emit. */
export const postEconomyRegionsFill = async (body: EconFillBody): Promise<EconFillResult> => {
  const { data } = await axios.post<EconFillResult>(`${BASE}/regions/fill`, body);
  return data;
};

export const fetchEconomyRegionHistory = async (regionId: number, limit = 40): Promise<EconRegionHistoryRow[]> => {
  const { data } = await axios.get<{ items: EconRegionHistoryRow[] }>(`${BASE}/regions/${regionId}/history`, {
    params: { limit },
  });
  return data.items;
};

/** The GET answers a bare list or `{ items }` — both are accepted. */
const unwrapList = <T,>(data: T[] | { items: T[] }): T[] => (Array.isArray(data) ? data : data.items);

export const fetchEconomyGoodsGroups = async (): Promise<EconGoodsGroup[]> => {
  const { data } = await axios.get<EconGoodsGroup[] | { items: EconGoodsGroup[] }>(`${BASE}/goods-groups`);
  return unwrapList(data);
};

export const putEconomyGoodsGroup = async (code: string, body: EconGoodsGroupUpdate): Promise<EconGoodsGroup> => {
  const { data } = await axios.put<EconGoodsGroup>(`${BASE}/goods-groups/${encodeURIComponent(code)}`, body);
  return data;
};

export const fetchEconomyTemplates = async (): Promise<EconRegionTemplate[]> => {
  const { data } = await axios.get<EconRegionTemplate[] | { items: EconRegionTemplate[] }>(`${BASE}/templates`);
  return unwrapList(data);
};

export const putEconomyTemplate = async (code: string, body: EconTemplateUpdate): Promise<EconRegionTemplate> => {
  const { data } = await axios.put<EconRegionTemplate>(`${BASE}/templates/${encodeURIComponent(code)}`, body);
  return data;
};

export const fetchEconomyItemGroups = async (params: EconItemGroupsParams): Promise<EconPage<EconItemGroupRow>> => {
  const { data } = await axios.get<EconPage<EconItemGroupRow>>(`${BASE}/item-groups`, { params: clean(params) });
  return data;
};

export const putEconomyItemGroups = async (body: EconItemGroupsUpdate): Promise<{ updated: number }> => {
  const { data } = await axios.put<{ updated: number }>(`${BASE}/item-groups`, body);
  return data;
};

export const fetchEconomySim = async (): Promise<EconSimState> => {
  const { data } = await axios.get<EconSimState>(`${BASE}/sim`);
  return data;
};

export const putEconomySim = async (body: EconSimUpdate): Promise<EconSimState> => {
  const { data } = await axios.put<EconSimState>(`${BASE}/sim`, body);
  return data;
};

/** «Пересчитать сейчас» — a real extra step; 409 «Пересчёт уже идёт» while a run is active. */
export const postEconomySimRun = async (): Promise<EconTickRun> => {
  const { data } = await axios.post<EconTickRun>(`${BASE}/sim/run`);
  return data;
};
