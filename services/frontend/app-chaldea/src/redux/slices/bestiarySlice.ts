import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import { fetchBestiaryApi } from '../../api/bestiary';
import type { BestiaryEntry } from '../../api/bestiary';

interface BestiaryState {
  entries: BestiaryEntry[];
  total: number;
  killedCount: number;
  loading: boolean;
  error: string | null;
  /** null = scroll index (list view), number = selected mob detail */
  selectedMobId: number | null;
}

const initialState: BestiaryState = {
  entries: [],
  total: 0,
  killedCount: 0,
  loading: false,
  error: null,
  selectedMobId: null,
};

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

const bestiarySlice = createSlice({
  name: 'bestiary',
  initialState,
  reducers: {
    selectMob(state, action: PayloadAction<number>) {
      state.selectedMobId = action.payload;
    },
    clearSelectedMob(state) {
      state.selectedMobId = null;
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
        state.selectedMobId = null;
      })
      .addCase(fetchBestiary.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      });
  },
});

export const { selectMob, clearSelectedMob } = bestiarySlice.actions;

export const selectBestiaryEntries = (state: RootState) => state.bestiary.entries;
export const selectBestiaryTotal = (state: RootState) => state.bestiary.total;
export const selectBestiaryKilledCount = (state: RootState) => state.bestiary.killedCount;
export const selectBestiaryLoading = (state: RootState) => state.bestiary.loading;
export const selectBestiaryError = (state: RootState) => state.bestiary.error;
export const selectSelectedMobId = (state: RootState) => state.bestiary.selectedMobId;
export const selectSelectedMob = (state: RootState) => {
  const { entries, selectedMobId } = state.bestiary;
  if (selectedMobId === null) return null;
  return entries.find((e) => e.id === selectedMobId) ?? null;
};

export default bestiarySlice.reducer;
