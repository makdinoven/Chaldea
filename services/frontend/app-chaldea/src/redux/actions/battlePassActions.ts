import { createAsyncThunk } from '@reduxjs/toolkit';
import {
  getCurrentSeason,
  getUserProgress,
  getUserMissions,
  completeMission as completeMissionApi,
  claimReward as claimRewardApi,
} from '../../api/battlePass';
import type {
  BPSeason,
  BPUserProgress,
  BPMissionsResponse,
  BPCompleteMissionResponse,
  BPClaimRewardRequest,
  BPClaimRewardResponse,
} from '../../types/battlePass';

export const fetchSeason = createAsyncThunk<
  BPSeason,
  void,
  { rejectValue: string }
>(
  'battlePass/fetchSeason',
  async (_, thunkAPI) => {
    try {
      const response = await getCurrentSeason();
      return response.data;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      return thunkAPI.rejectWithValue(detail || 'Не удалось загрузить сезон');
    }
  },
);

export const fetchProgress = createAsyncThunk<
  BPUserProgress,
  void,
  { rejectValue: string }
>(
  'battlePass/fetchProgress',
  async (_, thunkAPI) => {
    try {
      const response = await getUserProgress();
      return response.data;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      return thunkAPI.rejectWithValue(detail || 'Не удалось загрузить прогресс');
    }
  },
);

export const fetchMissions = createAsyncThunk<
  BPMissionsResponse,
  void,
  { rejectValue: string }
>(
  'battlePass/fetchMissions',
  async (_, thunkAPI) => {
    try {
      const response = await getUserMissions();
      return response.data;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      return thunkAPI.rejectWithValue(detail || 'Не удалось загрузить задания');
    }
  },
);

export const completeMission = createAsyncThunk<
  BPCompleteMissionResponse,
  number,
  { rejectValue: string }
>(
  'battlePass/completeMission',
  async (missionId, thunkAPI) => {
    try {
      const response = await completeMissionApi(missionId);
      return response.data;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      return thunkAPI.rejectWithValue(detail || 'Не удалось завершить задание');
    }
  },
);

export const claimReward = createAsyncThunk<
  BPClaimRewardResponse,
  BPClaimRewardRequest,
  { rejectValue: string }
>(
  'battlePass/claimReward',
  async (payload, thunkAPI) => {
    try {
      const response = await claimRewardApi(payload);
      return response.data;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      return thunkAPI.rejectWithValue(detail || 'Не удалось забрать награду');
    }
  },
);
