import axios from 'axios';

export interface LeaderboardEntry {
  character_id: number;
  name: string;
  avatar: string;
  value: number;
}

export interface HomeLeaderboards {
  symbols_daily: LeaderboardEntry[]; // characters written in the last 24h
  pvp: LeaderboardEntry[]; // PvP wins (all-time)
  pve: LeaderboardEntry[]; // PvE points = sum of defeated mob levels (all-time)
}

/** Hall of Fame shows a top-3 podium + ranks 4-6 list (API supports limit up to 10). */
export const HOME_LEADERBOARDS_LIMIT = 6;

export const fetchHomeLeaderboards = async (
  limit = HOME_LEADERBOARDS_LIMIT
): Promise<HomeLeaderboards> => {
  const { data } = await axios.get<HomeLeaderboards>('/characters/home-leaderboards', {
    params: { limit },
  });
  return data;
};
