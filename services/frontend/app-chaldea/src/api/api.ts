import axios from "axios";

export const BASE_URL = import.meta.env.VITE_BASE_URL || "";

export const BASE_URL_DEFAULT = import.meta.env.VITE_BASE_URL_DEFAULT || "";

export const BASE_URL_BATTLES = import.meta.env.VITE_BASE_URL_BATTLES || "";

export const BASE_URL_AUTOBATTLES = import.meta.env.VITE_BASE_URL_AUTOBATTLES || "/autobattle";

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
