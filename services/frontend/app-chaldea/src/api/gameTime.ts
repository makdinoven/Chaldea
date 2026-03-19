import axios from 'axios';

// --- Types ---

export interface GameTimePublicResponse {
  epoch: string;
  offset_days: number;
  server_time: string;
}

export interface ComputedGameTime {
  year: number;
  segment_name: string;
  segment_type: string;
  week: number | null;
  is_transition: boolean;
}

export interface GameTimeAdminResponse {
  id: number;
  epoch: string;
  offset_days: number;
  updated_at: string;
  computed: ComputedGameTime;
  server_time: string;
}

export interface GameTimeAdminUpdate {
  epoch?: string;
  offset_days?: number;
  target_year?: number;
  target_segment?: string;
  target_week?: number;
}

// --- API calls ---

export const getGameTime = () =>
  axios.get<GameTimePublicResponse>('/locations/game-time');

export const getGameTimeAdmin = () =>
  axios.get<GameTimeAdminResponse>('/locations/game-time/admin');

export const updateGameTimeAdmin = (data: GameTimeAdminUpdate) =>
  axios.put<GameTimeAdminResponse>('/locations/game-time/admin', data);
