import axios from "axios";

const rulesClient = axios.create({
  baseURL: "/rules",
  withCredentials: true,
  timeout: 10000,
});

// ── Request interceptor: attach JWT token ──
rulesClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("accessToken");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

rulesClient.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response) {
      throw new Error(e.response.data?.detail || e.response.statusText);
    }
    throw e;
  },
);

// ── Types ──

export interface GameRule {
  id: number;
  title: string;
  image_url: string | null;
  content: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface GameRuleCreate {
  title: string;
  content?: string | null;
  sort_order?: number;
}

export interface GameRuleUpdate {
  title?: string | null;
  content?: string | null;
  sort_order?: number | null;
}

export interface GameRuleReorderItem {
  id: number;
  sort_order: number;
}

// ── API functions ──

export const fetchRules = async (): Promise<GameRule[]> => {
  const { data } = await rulesClient.get("/list");
  return data;
};

export const fetchRule = async (id: number): Promise<GameRule> => {
  const { data } = await rulesClient.get(`/${id}`);
  return data;
};

export const createRule = async (payload: GameRuleCreate): Promise<GameRule> => {
  const { data } = await rulesClient.post("/create", payload);
  return data;
};

export const updateRule = async (id: number, payload: GameRuleUpdate): Promise<GameRule> => {
  const { data } = await rulesClient.put(`/${id}/update`, payload);
  return data;
};

export const deleteRule = async (id: number): Promise<void> => {
  await rulesClient.delete(`/${id}/delete`);
};

export const reorderRules = async (order: GameRuleReorderItem[]): Promise<void> => {
  await rulesClient.put("/reorder", { order });
};

export const uploadRuleImage = async (ruleId: number, file: File): Promise<{ message: string; image_url: string }> => {
  const form = new FormData();
  form.append("rule_id", String(ruleId));
  form.append("file", file);

  const { data } = await axios.post("/photo/change_rule_image", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
};
