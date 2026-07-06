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

export const fetchHomeLeaderboards = async (limit = 3): Promise<HomeLeaderboards> => {
  const { data } = await axios.get<HomeLeaderboards>('/characters/home-leaderboards', {
    params: { limit },
  });
  return data;
};
