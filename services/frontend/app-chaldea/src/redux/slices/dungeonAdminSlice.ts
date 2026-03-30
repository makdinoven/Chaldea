import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import toast from 'react-hot-toast';
import type { RootState } from '../store';
import * as api from '../../api/dungeons';
import type { Dungeon, DungeonDetail, DungeonCreate, DungeonUpdate } from '../../api/dungeons';

// --- State ---

interface DungeonAdminState {
  dungeons: Dungeon[];
  currentDungeon: DungeonDetail | null;
  loading: boolean;
  error: string | null;
  saving: boolean;
  detailLoading: boolean;
  detailError: string | null;
}

const initialState: DungeonAdminState = {
  dungeons: [],
  currentDungeon: null,
  loading: false,
  error: null,
  saving: false,
  detailLoading: false,
  detailError: null,
};

// --- Async Thunks ---

export const fetchDungeons = createAsyncThunk<
  Dungeon[],
  void,
  { rejectValue: string }
>(
  'dungeonAdmin/fetchDungeons',
  async (_, thunkAPI) => {
    try {
      return await api.fetchDungeons();
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить список подземелий');
    }
  },
);

export const fetchDungeonDetail = createAsyncThunk<
  DungeonDetail,
  number,
  { rejectValue: string }
>(
  'dungeonAdmin/fetchDungeonDetail',
  async (id, thunkAPI) => {
    try {
      return await api.fetchDungeonDetail(id);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить подземелье');
    }
  },
);

export const createDungeon = createAsyncThunk<
  Dungeon,
  DungeonCreate,
  { rejectValue: string }
>(
  'dungeonAdmin/createDungeon',
  async (payload, thunkAPI) => {
    try {
      const result = await api.createDungeon(payload);
      toast.success('Подземелье создано');
      return result;
    } catch {
      toast.error('Не удалось создать подземелье');
      return thunkAPI.rejectWithValue('Не удалось создать подземелье');
    }
  },
);

export const updateDungeon = createAsyncThunk<
  Dungeon,
  { id: number; payload: DungeonUpdate },
  { rejectValue: string }
>(
  'dungeonAdmin/updateDungeon',
  async ({ id, payload }, thunkAPI) => {
    try {
      const result = await api.updateDungeon(id, payload);
      toast.success('Подземелье обновлено');
      return result;
    } catch {
      toast.error('Не удалось обновить подземелье');
      return thunkAPI.rejectWithValue('Не удалось обновить подземелье');
    }
  },
);

export const deleteDungeon = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'dungeonAdmin/deleteDungeon',
  async (id, thunkAPI) => {
    try {
      await api.deleteDungeon(id);
      toast.success('Подземелье удалено');
      return id;
    } catch {
      toast.error('Не удалось удалить подземелье');
      return thunkAPI.rejectWithValue('Не удалось удалить подземелье');
    }
  },
);

// --- Slice ---

const dungeonAdminSlice = createSlice({
  name: 'dungeonAdmin',
  initialState,
  reducers: {
    clearCurrentDungeon(state) {
      state.currentDungeon = null;
      state.detailError = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // --- List ---
      .addCase(fetchDungeons.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchDungeons.fulfilled, (state, action) => {
        state.loading = false;
        state.dungeons = action.payload;
      })
      .addCase(fetchDungeons.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // --- Detail ---
      .addCase(fetchDungeonDetail.pending, (state) => {
        state.detailLoading = true;
        state.detailError = null;
      })
      .addCase(fetchDungeonDetail.fulfilled, (state, action) => {
        state.detailLoading = false;
        state.currentDungeon = action.payload;
      })
      .addCase(fetchDungeonDetail.rejected, (state, action) => {
        state.detailLoading = false;
        state.detailError = action.payload ?? 'Произошла ошибка';
      })

      // --- Create ---
      .addCase(createDungeon.pending, (state) => {
        state.saving = true;
      })
      .addCase(createDungeon.fulfilled, (state) => {
        state.saving = false;
      })
      .addCase(createDungeon.rejected, (state) => {
        state.saving = false;
      })

      // --- Update ---
      .addCase(updateDungeon.pending, (state) => {
        state.saving = true;
      })
      .addCase(updateDungeon.fulfilled, (state) => {
        state.saving = false;
      })
      .addCase(updateDungeon.rejected, (state) => {
        state.saving = false;
      })

      // --- Delete ---
      .addCase(deleteDungeon.fulfilled, (state, action) => {
        state.dungeons = state.dungeons.filter((d) => d.id !== action.payload);
        if (state.currentDungeon?.id === action.payload) {
          state.currentDungeon = null;
        }
      });
  },
});

export const { clearCurrentDungeon } = dungeonAdminSlice.actions;

// --- Selectors ---

export const selectDungeons = (state: RootState) => state.dungeonAdmin.dungeons;
export const selectDungeonsLoading = (state: RootState) => state.dungeonAdmin.loading;
export const selectDungeonsError = (state: RootState) => state.dungeonAdmin.error;
export const selectCurrentDungeon = (state: RootState) => state.dungeonAdmin.currentDungeon;
export const selectDetailLoading = (state: RootState) => state.dungeonAdmin.detailLoading;
export const selectDetailError = (state: RootState) => state.dungeonAdmin.detailError;
export const selectDungeonSaving = (state: RootState) => state.dungeonAdmin.saving;

export default dungeonAdminSlice.reducer;
