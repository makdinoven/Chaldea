import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import type { ComputedGameTime } from '../../api/gameTime';
import {
  fetchGameTime,
  fetchGameTimeAdmin,
  updateGameTimeAdminThunk,
} from '../actions/gameTimeActions';

// --- Types ---

interface GameTimeAdminState {
  id: number | null;
  epoch: string | null;
  offsetDays: number;
  updatedAt: string | null;
  computed: ComputedGameTime | null;
  serverTime: string | null;
  loading: boolean;
  error: string | null;
}

interface GameTimeState {
  epoch: string | null;
  offsetDays: number;
  serverTime: string | null;
  loading: boolean;
  error: string | null;
  admin: GameTimeAdminState;
}

const initialState: GameTimeState = {
  epoch: null,
  offsetDays: 0,
  serverTime: null,
  loading: false,
  error: null,
  admin: {
    id: null,
    epoch: null,
    offsetDays: 0,
    updatedAt: null,
    computed: null,
    serverTime: null,
    loading: false,
    error: null,
  },
};

// --- Slice ---

const gameTimeSlice = createSlice({
  name: 'gameTime',
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    // Public game time
    builder
      .addCase(fetchGameTime.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchGameTime.fulfilled, (state, action) => {
        state.loading = false;
        state.epoch = action.payload.epoch;
        state.offsetDays = action.payload.offset_days;
        state.serverTime = action.payload.server_time;
      })
      .addCase(fetchGameTime.rejected, (state, action) => {
        state.loading = false;
        state.error = (action.payload as string) || 'Произошла ошибка';
      });

    // Admin game time (fetch)
    builder
      .addCase(fetchGameTimeAdmin.pending, (state) => {
        state.admin.loading = true;
        state.admin.error = null;
      })
      .addCase(fetchGameTimeAdmin.fulfilled, (state, action) => {
        state.admin.loading = false;
        state.admin.id = action.payload.id;
        state.admin.epoch = action.payload.epoch;
        state.admin.offsetDays = action.payload.offset_days;
        state.admin.updatedAt = action.payload.updated_at;
        state.admin.computed = action.payload.computed;
        state.admin.serverTime = action.payload.server_time;
      })
      .addCase(fetchGameTimeAdmin.rejected, (state, action) => {
        state.admin.loading = false;
        state.admin.error = (action.payload as string) || 'Произошла ошибка';
      });

    // Admin game time (update)
    builder
      .addCase(updateGameTimeAdminThunk.pending, (state) => {
        state.admin.loading = true;
        state.admin.error = null;
      })
      .addCase(updateGameTimeAdminThunk.fulfilled, (state, action) => {
        state.admin.loading = false;
        state.admin.id = action.payload.id;
        state.admin.epoch = action.payload.epoch;
        state.admin.offsetDays = action.payload.offset_days;
        state.admin.updatedAt = action.payload.updated_at;
        state.admin.computed = action.payload.computed;
        state.admin.serverTime = action.payload.server_time;
      })
      .addCase(updateGameTimeAdminThunk.rejected, (state, action) => {
        state.admin.loading = false;
        state.admin.error = (action.payload as string) || 'Произошла ошибка';
      });
  },
});

// --- Selectors ---

export const selectGameTimePublic = (state: RootState) => state.gameTime;
export const selectGameTimeAdmin = (state: RootState) => state.gameTime.admin;

export default gameTimeSlice.reducer;
