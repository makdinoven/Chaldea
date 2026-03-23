import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import { fetchBestiaryApi } from '../../api/bestiary';
import type { BestiaryEntry } from '../../api/bestiary';

// --- State ---

interface BestiaryState {
  entries: BestiaryEntry[];
  total: number;
  killedCount: number;
  loading: boolean;
  error: string | null;
  currentSpreadIndex: number;
}

const initialState: BestiaryState = {
  entries: [],
  total: 0,
  killedCount: 0,
  loading: false,
  error: null,
  currentSpreadIndex: 0,
};

// --- Async Thunks ---

export const fetchBestiary = createAsyncThunk<
  { entries: BestiaryEntry[]; total: number; killedCount: number },
  number | undefined,
  { rejectValue: string }
>(
  'bestiary/fetchBestiary',
  async (characterId, thunkAPI) => {
    try {
      const response = await fetchBestiaryApi(characterId);
      return {
        entries: response.entries,
        total: response.total,
        killedCount: response.killed_count,
      };
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить бестиарий');
    }
  },
);

// --- Slice ---

const bestiarySlice = createSlice({
  name: 'bestiary',
  initialState,
  reducers: {
    setCurrentSpread(state, action: PayloadAction<number>) {
      const idx = action.payload;
      if (idx >= 0 && idx < state.entries.length) {
        state.currentSpreadIndex = idx;
      }
    },
    nextSpread(state) {
      if (state.currentSpreadIndex < state.entries.length - 1) {
        state.currentSpreadIndex += 1;
      }
    },
    prevSpread(state) {
      if (state.currentSpreadIndex > 0) {
        state.currentSpreadIndex -= 1;
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchBestiary.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchBestiary.fulfilled, (state, action) => {
        state.loading = false;
        state.entries = action.payload.entries;
        state.total = action.payload.total;
        state.killedCount = action.payload.killedCount;
        state.currentSpreadIndex = 0;
      })
      .addCase(fetchBestiary.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      });
  },
});

export const { setCurrentSpread, nextSpread, prevSpread } = bestiarySlice.actions;

// --- Selectors ---

export const selectBestiaryEntries = (state: RootState) => state.bestiary.entries;
export const selectBestiaryTotal = (state: RootState) => state.bestiary.total;
export const selectBestiaryKilledCount = (state: RootState) => state.bestiary.killedCount;
export const selectBestiaryLoading = (state: RootState) => state.bestiary.loading;
export const selectBestiaryError = (state: RootState) => state.bestiary.error;
export const selectCurrentSpreadIndex = (state: RootState) => state.bestiary.currentSpreadIndex;
export const selectCurrentEntry = (state: RootState) => {
  const { entries, currentSpreadIndex } = state.bestiary;
  return entries[currentSpreadIndex] ?? null;
};

export default bestiarySlice.reducer;
