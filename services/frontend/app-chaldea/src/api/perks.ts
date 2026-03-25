import axios from "axios";
import type { Perk } from "../types/perks";

/* ── Axios client for character-attributes-service (admin perks) ── */

const attrClient = axios.create({
  baseURL: "/attributes",
  withCredentials: true,
  timeout: 10000,
});

attrClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("accessToken");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

attrClient.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response) {
      const detail = e.response.data?.detail;
      if (Array.isArray(detail)) {
        const msgs = detail.map((d: { loc?: string[]; msg?: string }) => {
          const field = d.loc?.slice(1).join(" → ") ?? "";
          return field ? `${field}: ${d.msg}` : (d.msg ?? "");
        });
        throw new Error(msgs.join("; ") || e.response.statusText);
      }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail) || e.response.statusText);
    }
    throw e;
  },
);

/* ── Paginated response ── */

export interface PerksPaginatedResponse {
  items: Perk[];
  total: number;
  page: number;
  per_page: number;
}

/* ── Admin CRUD ── */

export const fetchPerks = async (params: {
  page?: number;
  per_page?: number;
  search?: string;
  category?: string;
  rarity?: string;
}): Promise<PerksPaginatedResponse> => {
  const { data } = await attrClient.get("/admin/perks", { params });
  return data;
};

export const fetchPerk = async (id: number): Promise<Perk> => {
  const { data } = await attrClient.get(`/admin/perks`, {
    params: { search: "", page: 1, per_page: 1000 },
  });
  // The admin list endpoint returns paginated data — find the perk by id
  const perks: Perk[] = data.items ?? [];
  const perk = perks.find((p: Perk) => p.id === id);
  if (!perk) throw new Error("Перк не найден");
  return perk;
};

export const createPerk = async (payload: Omit<Perk, "id" | "is_active">): Promise<Perk> => {
  const { data } = await attrClient.post("/admin/perks", payload);
  return data;
};

export const updatePerk = async (
  id: number,
  payload: Partial<Omit<Perk, "id">>,
): Promise<Perk> => {
  const { data } = await attrClient.put(`/admin/perks/${id}`, payload);
  return data;
};

export const deletePerk = async (id: number): Promise<void> => {
  await attrClient.delete(`/admin/perks/${id}`);
};

/* ── Grant / Revoke ── */

export const grantPerk = async (
  characterId: number,
  perkId: number,
): Promise<{ detail: string }> => {
  const { data } = await attrClient.post("/admin/perks/grant", {
    character_id: characterId,
    perk_id: perkId,
  });
  return data;
};

export const revokePerk = async (
  characterId: number,
  perkId: number,
): Promise<{ detail: string }> => {
  const { data } = await attrClient.delete(
    `/admin/perks/grant/${characterId}/${perkId}`,
  );
  return data;
};
