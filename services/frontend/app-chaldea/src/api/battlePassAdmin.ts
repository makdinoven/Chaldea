import axios from "axios";

/* ── Axios client for battle-pass-service (admin) ── */

const bpClient = axios.create({
  baseURL: "/battle-pass",
  withCredentials: true,
  timeout: 15000,
});

bpClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("accessToken");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

bpClient.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response) {
      const detail = e.response.data?.detail;
      if (Array.isArray(detail)) {
        const msgs = detail.map((d: { loc?: string[]; msg?: string }) => {
          const field = d.loc?.slice(1).join(" \u2192 ") ?? "";
          return field ? `${field}: ${d.msg}` : (d.msg ?? "");
        });
        throw new Error(msgs.join("; ") || e.response.statusText);
      }
      throw new Error(
        typeof detail === "string"
          ? detail
          : JSON.stringify(detail) || e.response.statusText,
      );
    }
    throw e;
  },
);

/* ── Types ── */

export interface AdminSeason {
  id: number;
  name: string;
  segment_name: string;
  year: number;
  start_date: string;
  end_date: string;
  grace_end_date: string;
  is_active: boolean;
  created_at: string;
}

export interface AdminSeasonsResponse {
  items: AdminSeason[];
  total: number;
}

export interface SeasonCreatePayload {
  name: string;
  segment_name: string;
  year: number;
  start_date: string;
  end_date: string;
}

export interface SeasonUpdatePayload {
  name?: string;
  segment_name?: string;
  year?: number;
  start_date?: string;
  end_date?: string;
  is_active?: boolean;
}

export interface AdminReward {
  id?: number;
  track: "free" | "premium";
  reward_type: "gold" | "xp" | "item" | "diamonds" | "frame" | "chat_background";
  reward_value: number;
  item_id: number | null;
  cosmetic_slug?: string | null;
}

export interface AdminLevel {
  id?: number;
  level_number: number;
  required_xp: number;
  rewards: AdminReward[];
}

export interface AdminLevelInput {
  level_number: number;
  required_xp: number;
  free_rewards: Omit<AdminReward, "id" | "track">[];
  premium_rewards: Omit<AdminReward, "id" | "track">[];
}

export interface AdminMission {
  id?: number;
  week_number: number;
  mission_type: string;
  description: string;
  target_count: number;
  xp_reward: number;
}

export interface AdminMissionsGrouped {
  weeks: Record<string, AdminMission[]>;
}

/* ── Admin API ── */

export const getAdminSeasons = async (): Promise<AdminSeasonsResponse> => {
  const { data } = await bpClient.get("/admin/seasons");
  return data;
};

export const createSeason = async (
  payload: SeasonCreatePayload,
): Promise<AdminSeason> => {
  const { data } = await bpClient.post("/admin/seasons", payload);
  return data;
};

export const updateSeason = async (
  id: number,
  payload: SeasonUpdatePayload,
): Promise<AdminSeason> => {
  const { data } = await bpClient.put(`/admin/seasons/${id}`, payload);
  return data;
};

export const deleteSeason = async (id: number): Promise<{ ok: boolean }> => {
  const { data } = await bpClient.delete(`/admin/seasons/${id}`);
  return data;
};

export const getSeasonLevels = async (
  seasonId: number,
): Promise<AdminLevel[]> => {
  const { data } = await bpClient.get(`/admin/seasons/${seasonId}/levels`);
  return data;
};

export const upsertSeasonLevels = async (
  seasonId: number,
  levels: AdminLevelInput[],
): Promise<AdminLevel[]> => {
  const { data } = await bpClient.put(`/admin/seasons/${seasonId}/levels`, {
    levels,
  });
  return data;
};

export const getSeasonMissions = async (
  seasonId: number,
): Promise<AdminMissionsGrouped> => {
  const { data } = await bpClient.get(`/admin/seasons/${seasonId}/missions`);
  return data;
};

export const upsertSeasonMissions = async (
  seasonId: number,
  missions: Omit<AdminMission, "id">[],
): Promise<AdminMission[]> => {
  const { data } = await bpClient.put(`/admin/seasons/${seasonId}/missions`, {
    missions,
  });
  return data;
};
