import axios from "axios";

export const BASE_URL = import.meta.env.VITE_BASE_URL || "";

export const BASE_URL_DEFAULT = import.meta.env.VITE_BASE_URL_DEFAULT || "";

export const BASE_URL_BATTLES = import.meta.env.VITE_BASE_URL_BATTLES || "";

export const BASE_URL_AUTOBATTLES = import.meta.env.VITE_BASE_URL_AUTOBATTLES || "/autobattle";

/** A recent roleplay post enriched with its location, for the homepage
 * activity widget. Mirrors the backend `LatestPostResponse` schema. */
export interface LatestRoleplayPost {
  post_id: number;
  character_id: number;
  character_photo: string;
  character_title: string;
  character_title_rarity: string | null;
  character_level: number | null;
  character_name: string | null;
  user_id: number | null;
  user_nickname: string | null;
  content: string;
  length: number;
  created_at: string;
  likes_count: number;
  liked_by: number[];
  location_id: number;
  location_name: string;
}

/** Fetch the latest roleplay posts across all locations (newest first). */
export const getLatestRoleplayPosts = async (
  limit = 5,
): Promise<LatestRoleplayPost[]> => {
  const { data } = await axios.get<LatestRoleplayPost[]>(
    `${BASE_URL}/locations/posts/latest`,
    { params: { limit } },
  );
  return data;
};

export const postAutobattleSpeed = async (
  participantId: number,
  speed: "fast" | "slow",
): Promise<{ ok: boolean; participant_id: number; speed: string }> => {
  const { data } = await axios.post(`${BASE_URL_AUTOBATTLES}/speed`, {
    participant_id: participantId,
    speed,
  });
  return data;
};
