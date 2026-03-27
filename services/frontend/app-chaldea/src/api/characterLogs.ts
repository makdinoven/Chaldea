import axios from "axios";

// --- Types ---

export interface CharacterLogEntry {
  id: number;
  character_id: number;
  event_type: string;
  description: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface CharacterLogsResponse {
  logs: CharacterLogEntry[];
  total: number;
}

export interface PostHistoryItem {
  id: number;
  character_id: number;
  location_id: number;
  location_name: string;
  content: string;
  char_count: number;
  xp_earned: number;
  created_at: string;
}

export interface PostHistoryResponse {
  posts: PostHistoryItem[];
}

// --- API calls ---

export const fetchCharacterLogs = async (
  characterId: number,
  limit?: number,
  offset?: number,
  eventType?: string,
): Promise<CharacterLogsResponse> => {
  const params: Record<string, string | number> = {};
  if (limit != null) params.limit = limit;
  if (offset != null) params.offset = offset;
  if (eventType) params.event_type = eventType;

  const { data } = await axios.get<CharacterLogsResponse>(
    `/characters/${characterId}/logs`,
    { params },
  );
  return data;
};

export const fetchPostHistory = async (
  characterId: number,
): Promise<PostHistoryResponse> => {
  const { data } = await axios.get<PostHistoryResponse>(
    `/characters/${characterId}/post-history`,
  );
  return data;
};
