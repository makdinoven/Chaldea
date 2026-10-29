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
} from '../types/economy';

/** Admin «Экономика» API (FEAT-181, character-service). Auth header comes from axiosSetup. */
const BASE = '/characters/admin/economy';

/** Drops empty values so the backend sees only the filters actually set. */
const clean = (params: object): Record<string, string | number> => {
  const out: Record<string, string | number> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') out[key] = value as string | number;
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
