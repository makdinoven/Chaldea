import axios from 'axios';
import type {
  BPSeason,
  BPUserProgress,
  BPMissionsResponse,
  BPCompleteMissionResponse,
  BPClaimRewardRequest,
  BPClaimRewardResponse,
} from '../types/battlePass';

export const getCurrentSeason = () =>
  axios.get<BPSeason>('/battle-pass/seasons/current');

export const getUserProgress = () =>
  axios.get<BPUserProgress>('/battle-pass/me/progress');

export const getUserMissions = () =>
  axios.get<BPMissionsResponse>('/battle-pass/me/missions');

export const completeMission = (missionId: number) =>
  axios.post<BPCompleteMissionResponse>(`/battle-pass/me/missions/${missionId}/complete`);

export const claimReward = (payload: BPClaimRewardRequest) =>
  axios.post<BPClaimRewardResponse>('/battle-pass/me/rewards/claim', payload);

export const activatePremium = () =>
  axios.post('/battle-pass/me/premium/activate');
