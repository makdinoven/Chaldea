import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import type { PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import type {
  CosmeticFrame,
  CosmeticBackground,
  UserCosmeticItem,
  UserCosmeticBackgroundItem,
} from '../../types/cosmetics';
import {
  getFramesCatalog,
  getBackgroundsCatalog,
  getMyFrames,
  getMyBackgrounds,
  equipFrame as equipFrameApi,
  equipBackground as equipBackgroundApi,
} from '../../api/cosmetics';

/* ── State ── */

interface CosmeticsState {
  frames: CosmeticFrame[];
  backgrounds: CosmeticBackground[];
  myFrames: UserCosmeticItem[];
  myBackgrounds: UserCosmeticBackgroundItem[];
  activeFrameSlug: string | null;
  activeBackgroundSlug: string | null;
  loading: boolean;
  error: string | null;
}

const initialState: CosmeticsState = {
  frames: [],
  backgrounds: [],
  myFrames: [],
  myBackgrounds: [],
  activeFrameSlug: null,
  activeBackgroundSlug: null,
  loading: false,
  error: null,
};

/* ── Async Thunks ── */

export const fetchFrames = createAsyncThunk<
  CosmeticFrame[],
  void,
  { rejectValue: string }
>('cosmetics/fetchFrames', async (_, { rejectWithValue }) => {
  try {
    const { data } = await getFramesCatalog();
    return data.items;
  } catch {
    return rejectWithValue('Не удалось загрузить каталог рамок');
  }
});

export const fetchBackgrounds = createAsyncThunk<
  CosmeticBackground[],
  void,
  { rejectValue: string }
>('cosmetics/fetchBackgrounds', async (_, { rejectWithValue }) => {
  try {
    const { data } = await getBackgroundsCatalog();
    return data.items;
  } catch {
    return rejectWithValue('Не удалось загрузить каталог подложек');
  }
});

export const fetchMyFrames = createAsyncThunk<
  { items: UserCosmeticItem[]; activeSlug: string | null },
  void,
  { rejectValue: string }
>('cosmetics/fetchMyFrames', async (_, { rejectWithValue }) => {
  try {
    const { data } = await getMyFrames();
    return { items: data.items, activeSlug: data.active_slug };
  } catch {
    return rejectWithValue('Не удалось загрузить ваши рамки');
  }
});

export const fetchMyBackgrounds = createAsyncThunk<
  { items: UserCosmeticBackgroundItem[]; activeSlug: string | null },
  void,
  { rejectValue: string }
>('cosmetics/fetchMyBackgrounds', async (_, { rejectWithValue }) => {
  try {
    const { data } = await getMyBackgrounds();
    return { items: data.items, activeSlug: data.active_slug };
  } catch {
    return rejectWithValue('Не удалось загрузить ваши подложки');
  }
});

export const equipFrame = createAsyncThunk<
  string | null,
  string | null,
  { rejectValue: string }
>('cosmetics/equipFrame', async (slug, { rejectWithValue }) => {
  try {
    const { data } = await equipFrameApi(slug);
    return data.active_frame;
  } catch {
    return rejectWithValue('Не удалось установить рамку');
  }
});

export const equipBackground = createAsyncThunk<
  string | null,
  string | null,
  { rejectValue: string }
>('cosmetics/equipBackground', async (slug, { rejectWithValue }) => {
  try {
    const { data } = await equipBackgroundApi(slug);
    return data.active_background;
  } catch {
    return rejectWithValue('Не удалось установить подложку');
  }
});

/* ── Slice ── */

const cosmeticsSlice = createSlice({
  name: 'cosmetics',
  initialState,
  reducers: {
    clearCosmeticsError(state) {
      state.error = null;
    },
    setActiveFrameSlug(state, action: PayloadAction<string | null>) {
      state.activeFrameSlug = action.payload;
    },
    setActiveBackgroundSlug(state, action: PayloadAction<string | null>) {
      state.activeBackgroundSlug = action.payload;
    },
  },
  extraReducers: (builder) => {
    // Fetch frames catalog
    builder
      .addCase(fetchFrames.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchFrames.fulfilled, (state, action) => {
        state.loading = false;
        state.frames = action.payload;
      })
      .addCase(fetchFrames.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });

    // Fetch backgrounds catalog
    builder
      .addCase(fetchBackgrounds.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchBackgrounds.fulfilled, (state, action) => {
        state.loading = false;
        state.backgrounds = action.payload;
      })
      .addCase(fetchBackgrounds.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });

    // Fetch my frames
    builder
      .addCase(fetchMyFrames.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchMyFrames.fulfilled, (state, action) => {
        state.loading = false;
        state.myFrames = action.payload.items;
        state.activeFrameSlug = action.payload.activeSlug;
      })
      .addCase(fetchMyFrames.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });

    // Fetch my backgrounds
    builder
      .addCase(fetchMyBackgrounds.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchMyBackgrounds.fulfilled, (state, action) => {
        state.loading = false;
        state.myBackgrounds = action.payload.items;
        state.activeBackgroundSlug = action.payload.activeSlug;
      })
      .addCase(fetchMyBackgrounds.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });

    // Equip frame
    builder
      .addCase(equipFrame.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(equipFrame.fulfilled, (state, action) => {
        state.loading = false;
        state.activeFrameSlug = action.payload;
      })
      .addCase(equipFrame.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });

    // Equip background
    builder
      .addCase(equipBackground.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(equipBackground.fulfilled, (state, action) => {
        state.loading = false;
        state.activeBackgroundSlug = action.payload;
      })
      .addCase(equipBackground.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Произошла ошибка';
      });
  },
});

/* ── Actions ── */

export const {
  clearCosmeticsError,
  setActiveFrameSlug,
  setActiveBackgroundSlug,
} = cosmeticsSlice.actions;

/* ── Selectors ── */

export const selectFramesCatalog = (state: RootState) =>
  state.cosmetics.frames;
export const selectBackgroundsCatalog = (state: RootState) =>
  state.cosmetics.backgrounds;
export const selectMyFrames = (state: RootState) => state.cosmetics.myFrames;
export const selectMyBackgrounds = (state: RootState) =>
  state.cosmetics.myBackgrounds;
export const selectActiveFrameSlug = (state: RootState) =>
  state.cosmetics.activeFrameSlug;
export const selectActiveBackgroundSlug = (state: RootState) =>
  state.cosmetics.activeBackgroundSlug;
export const selectCosmeticsLoading = (state: RootState) =>
  state.cosmetics.loading;
export const selectCosmeticsError = (state: RootState) =>
  state.cosmetics.error;

export default cosmeticsSlice.reducer;
