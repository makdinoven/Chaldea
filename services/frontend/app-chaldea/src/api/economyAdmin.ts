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
  EconMerchantFundBody,
  EconMerchantFundResult,
  EconMerchantsParams,
  EconMerchantsResponse,
  EconBankAdminDetail,
  EconBankAdminItem,
  EconBankCapitalBody,
  EconBankCapitalResult,
  EconBankDebtor,
  EconBankFlagBody,
  EconBankLoan,
  EconBanksResponse,
  EconEventStartBody,
  EconEventStartResult,
  EconEventTemplate,
  EconEventTemplateCreate,
  EconEventTemplateUpdate,
  EconEventsHistoryParams,
  EconRegionEvent,
  EconRegionEventsPage,
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

/* ---------------------------------------------- FEAT-183 — NPC merchants (feature file 3.7) */

export const fetchEconomyMerchants = async (params: EconMerchantsParams = {}): Promise<EconMerchantsResponse> => {
  const { data } = await axios.get<EconMerchantsResponse>(`${BASE}/merchants`, { params: clean(params) });
  return data;
};

/** «Пополнить кассы торговцев» — needs economy:settings + economy:emit; re-click emits 0. */
export const postEconomyMerchantsFund = async (body: EconMerchantFundBody): Promise<EconMerchantFundResult> => {
  const { data } = await axios.post<EconMerchantFundResult>(`${BASE}/merchants/fund`, body);
  return data;
};

/* ---------------------------------------------- FEAT-184 — banks (feature file 3.10) */

export const fetchEconomyBanks = async (): Promise<EconBanksResponse> => {
  const { data } = await axios.get<EconBanksResponse>(`${BASE}/banks`);
  return data;
};

export const fetchEconomyBank = async (regionId: number): Promise<EconBankAdminDetail> => {
  const { data } = await axios.get<EconBankAdminDetail>(`${BASE}/banks/${regionId}`);
  return data;
};

export const fetchEconomyBankDebtors = async (): Promise<EconBankDebtor[]> => {
  const { data } = await axios.get<EconBankDebtor[] | { items: EconBankDebtor[] }>(`${BASE}/banks/debtors`);
  return unwrapList(data);
};

/** «Банк есть»: creates the bank row; the first switch-on seeds the start capital from the treasury once. */
export const putEconomyBankFlag = async (regionId: number, body: EconBankFlagBody): Promise<EconBankAdminItem> => {
  const { data } = await axios.put<EconBankAdminItem>(`${BASE}/banks/${regionId}`, body);
  return data;
};

/** «Капитал из казны» (`in`) / «Вернуть капитал в казну» (`out`). */
export const postEconomyBankCapital = async (
  regionId: number,
  body: EconBankCapitalBody,
): Promise<EconBankCapitalResult> => {
  const { data } = await axios.post<EconBankCapitalResult>(`${BASE}/banks/${regionId}/capital`, body);
  return data;
};

/** «Списать долг» — the bank's loss, no money moves. */
export const postEconomyBankLoanWriteOff = async (loanId: number, comment: string): Promise<EconBankLoan> => {
  const { data } = await axios.post<EconBankLoan>(`${BASE}/banks/loans/${loanId}/write-off`, { comment });
  return data;
};

/* ---------------------------------------------- FEAT-187 — region events (feature file 3.7) */

const EVENTS = `${BASE}/events`;

/** Templates ordered by kind, name; each carries `active_count`. */
export const fetchEconomyEventTemplates = async (): Promise<EconEventTemplate[]> => {
  const { data } = await axios.get<EconEventTemplate[] | { items: EconEventTemplate[] }>(`${EVENTS}/templates`);
  return unwrapList(data);
};

export const postEconomyEventTemplate = async (body: EconEventTemplateCreate): Promise<EconEventTemplate> => {
  const { data } = await axios.post<EconEventTemplate>(`${EVENTS}/templates`, body);
  return data;
};

export const putEconomyEventTemplate = async (
  templateId: number,
  body: EconEventTemplateUpdate,
): Promise<EconEventTemplate> => {
  const { data } = await axios.put<EconEventTemplate>(`${EVENTS}/templates/${templateId}`, body);
  return data;
};

/** 409 when other templates' chains refer to it; running instances keep their snapshot. */
export const deleteEconomyEventTemplate = async (templateId: number): Promise<void> => {
  await axios.delete(`${EVENTS}/templates/${templateId}`);
};

/** Active events (ends_at ascending), optionally of one region. */
export const fetchEconomyActiveEvents = async (regionId?: number): Promise<EconRegionEvent[]> => {
  const { data } = await axios.get<EconRegionEvent[] | { items: EconRegionEvent[] }>(`${EVENTS}/active`, {
    params: clean({ region_id: regionId }),
  });
  return unwrapList(data);
};

/** Manual start on a region (+ scope expansion); one-shot effects apply at the next recount. */
export const postEconomyEventStart = async (body: EconEventStartBody): Promise<EconEventStartResult> => {
  const { data } = await axios.post<EconEventStartResult>(`${EVENTS}/start`, body);
  return data;
};

/** Stops the ongoing effects; one-shot results are not rolled back. */
export const postEconomyEventCancel = async (eventId: number, comment: string): Promise<EconRegionEvent> => {
  const { data } = await axios.post<EconRegionEvent>(`${EVENTS}/${eventId}/cancel`, { comment });
  return data;
};

export const fetchEconomyEventsHistory = async (params: EconEventsHistoryParams): Promise<EconRegionEventsPage> => {
  const { data } = await axios.get<EconRegionEventsPage>(`${EVENTS}/history`, { params: clean(params) });
  return data;
};
