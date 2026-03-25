import axios from "axios";
import type { Title, CharacterTitle } from "../types/titles";

/* ── Axios client for character-service (titles) ── */

const charClient = axios.create({
  baseURL: "/characters",
  withCredentials: true,
  timeout: 10000,
});

charClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("accessToken");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

charClient.interceptors.response.use(
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

export interface TitlesPaginatedResponse {
  items: Title[];
  total: number;
  page: number;
  per_page: number;
}

/* ── Admin CRUD ── */

export const fetchTitles = async (params: {
  page?: number;
  per_page?: number;
  search?: string;
  rarity?: string;
}): Promise<TitlesPaginatedResponse> => {
  const { data } = await charClient.get("/admin/titles", { params });
  return data;
};

export const fetchTitle = async (id: number): Promise<Title> => {
  const { data } = await charClient.get("/admin/titles", {
    params: { search: "", page: 1, per_page: 1000 },
  });
  const titles: Title[] = data.items ?? [];
  const title = titles.find((t: Title) => t.id_title === id);
  if (!title) throw new Error("Титул не найден");
  return title;
};

export const createTitle = async (payload: Omit<Title, "id_title" | "is_active" | "created_at" | "updated_at" | "holders_count">): Promise<Title> => {
  const { data } = await charClient.post("/admin/titles", payload);
  return data;
};

export const updateTitle = async (
  id: number,
  payload: Partial<Omit<Title, "id_title">>,
): Promise<Title> => {
  const { data } = await charClient.put(`/admin/titles/${id}`, payload);
  return data;
};

export const deleteTitle = async (id: number): Promise<void> => {
  await charClient.delete(`/admin/titles/${id}`);
};

/* ── Grant / Revoke ── */

export const grantTitle = async (
  characterId: number,
  titleId: number,
): Promise<{ detail: string }> => {
  const { data } = await charClient.post("/admin/titles/grant", {
    character_id: characterId,
    title_id: titleId,
  });
  return data;
};

export const revokeTitle = async (
  characterId: number,
  titleId: number,
): Promise<{ detail: string }> => {
  const { data } = await charClient.delete(
    `/admin/titles/grant/${characterId}/${titleId}`,
  );
  return data;
};

/* ── Player endpoints ── */

export const fetchCharacterTitles = async (
  characterId: number,
): Promise<CharacterTitle[]> => {
  const { data } = await charClient.get(`/${characterId}/titles`);
  return data;
};

export const setActiveTitle = async (
  characterId: number,
  titleId: number,
): Promise<{ message: string }> => {
  const { data } = await charClient.post(
    `/${characterId}/current-title/${titleId}`,
  );
  return data;
};

export const unsetActiveTitle = async (
  characterId: number,
): Promise<{ message: string }> => {
  const { data } = await charClient.delete(`/${characterId}/current-title`);
  return data;
};
