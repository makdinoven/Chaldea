// Battle Pass types — based on API contracts in FEAT-102 Section 3.2

export interface BPReward {
  id: number;
  reward_type: 'gold' | 'xp' | 'item' | 'diamonds' | 'frame' | 'chat_background';
  reward_value: number;
  item_id: number | null;
  item_name: string | null;
  cosmetic_slug?: string | null;
}

export interface BPLevel {
  level_number: number;
  required_xp: number;
  free_rewards: BPReward[];
  premium_rewards: BPReward[];
}

export interface BPSeason {
  id: number;
  name: string;
  segment_name: string;
  year: number;
  start_date: string;
  end_date: string;
  grace_end_date: string;
  is_active: boolean;
  status: 'active' | 'grace' | 'ended';
  days_remaining: number;
  current_week: number;
  total_weeks: number;
  levels: BPLevel[];
}

export interface BPClaimedReward {
  level_number: number;
  track: 'free' | 'premium';
  claimed_at: string;
  character_id: number;
}

export interface BPUserProgress {
  season_id: number;
  current_level: number;
  current_xp: number;
  xp_to_next_level: number;
  is_premium: boolean;
  claimed_rewards: BPClaimedReward[];
}

export interface BPMission {
  id: number;
  week_number: number;
  mission_type: string;
  description: string;
  target_count: number;
  current_count: number;
  is_completed: boolean;
  completed_at: string | null;
  xp_reward: number;
}

export interface BPMissionsResponse {
  season_id: number;
  current_week: number;
  missions: BPMission[];
}

export interface BPCompleteMissionResponse {
  ok: boolean;
  xp_awarded: number;
  new_total_xp: number;
  new_level: number;
  leveled_up: boolean;
}

export interface BPClaimRewardRequest {
  level_number: number;
  track: 'free' | 'premium';
}

export interface BPClaimRewardResponse {
  ok: boolean;
  reward_type: string;
  reward_value: number;
  delivered_to_character_id: number;
  delivered_to_character_name: string;
}
