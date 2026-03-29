import { createSlice } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import type { BPSeason, BPUserProgress, BPMission } from '../../types/battlePass';
import {
  fetchSeason,
  fetchProgress,
  fetchMissions,
  completeMission,
  claimReward,
} from '../actions/battlePassActions';

interface BattlePassState {
  season: BPSeason | null;
  userProgress: BPUserProgress | null;
  missions: BPMission[];
  currentWeek: number;
  loading: boolean;
  error: string | null;
}

const initialState: BattlePassState = {
  season: null,
  userProgress: null,
  missions: [],
  currentWeek: 1,
  loading: false,
  error: null,
};

const battlePassSlice = createSlice({
  name: 'battlePass',
  initialState,
  reducers: {
    clearBattlePassError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    // Fetch season
    builder
      .addCase(fetchSeason.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchSeason.fulfilled, (state, action) => {
        state.loading = false;
        state.season = action.payload;
      })
      .addCase(fetchSeason.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });

    // Fetch progress
    builder
      .addCase(fetchProgress.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchProgress.fulfilled, (state, action) => {
        state.loading = false;
        state.userProgress = action.payload;
      })
      .addCase(fetchProgress.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });

    // Fetch missions
    builder
      .addCase(fetchMissions.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchMissions.fulfilled, (state, action) => {
        state.loading = false;
        state.missions = action.payload.missions;
        state.currentWeek = action.payload.current_week;
      })
      .addCase(fetchMissions.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });

    // Complete mission
    builder
      .addCase(completeMission.fulfilled, (state, action) => {
        if (state.userProgress) {
          state.userProgress.current_xp = action.payload.new_total_xp;
          state.userProgress.current_level = action.payload.new_level;
        }
      })
      .addCase(completeMission.rejected, (state, action) => {
        state.error = action.payload || 'Произошла ошибка';
      });

    // Claim reward
    builder
      .addCase(claimReward.rejected, (state, action) => {
        state.error = action.payload || 'Произошла ошибка';
      });
  },
});

export const { clearBattlePassError } = battlePassSlice.actions;

// Selectors
export const selectBattlePassSeason = (state: RootState) => state.battlePass.season;
export const selectBattlePassProgress = (state: RootState) => state.battlePass.userProgress;
export const selectBattlePassMissions = (state: RootState) => state.battlePass.missions;
export const selectBattlePassCurrentWeek = (state: RootState) => state.battlePass.currentWeek;
export const selectBattlePassLoading = (state: RootState) => state.battlePass.loading;
export const selectBattlePassError = (state: RootState) => state.battlePass.error;

export default battlePassSlice.reducer;
