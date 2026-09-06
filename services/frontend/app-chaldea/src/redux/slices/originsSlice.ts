import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import {
  fetchOrigins,
  fetchOriginsAdmin,
  createOrigin,
  updateOrigin,
  deleteOrigin,
  type OriginCountry,
  type OriginCountryAdmin,
  type OriginCountryCreatePayload,
  type OriginCountryUpdatePayload,
} from '../../api/origins';

/**
 * FEAT-154 — origin registry (rules 8-11).
 *
 * `list` holds the public, active-only registry used by the wizard and by every
 * origin picker. `adminList` holds the admin view, which — per note N5 —
 * includes soft-deleted rows so a hidden origin can be found and restored.
 *
 * Every rejected branch stores a Russian message; the rendering component MUST
 * display `error` / `adminError` to the user.
 */

interface OriginsState {
  list: OriginCountry[];
  loading: boolean;
  error: string | null;

  adminList: OriginCountryAdmin[];
  adminLoading: boolean;
  adminError: string | null;
}

const initialState: OriginsState = {
  list: [],
  loading: false,
  error: null,
  adminList: [],
  adminLoading: false,
  adminError: null,
};

const message = (error: unknown, fallback: string): string =>
  error instanceof Error && error.message ? error.message : fallback;

// --- Thunks ---

export const fetchOriginsThunk = createAsyncThunk<
  OriginCountry[],
  void,
  { rejectValue: string }
>('origins/fetchPublic', async (_, { rejectWithValue }) => {
  try {
    return await fetchOrigins();
  } catch (error) {
    return rejectWithValue(message(error, 'Не удалось загрузить список происхождений.'));
  }
});

export const fetchOriginsAdminThunk = createAsyncThunk<
  OriginCountryAdmin[],
  boolean | undefined,
  { rejectValue: string }
>('origins/fetchAdmin', async (includeInactive, { rejectWithValue }) => {
  try {
    return await fetchOriginsAdmin(includeInactive ?? true);
  } catch (error) {
    return rejectWithValue(message(error, 'Не удалось загрузить справочник происхождений.'));
  }
});

export const createOriginThunk = createAsyncThunk<
  OriginCountryAdmin,
  OriginCountryCreatePayload,
  { rejectValue: string }
>('origins/create', async (payload, { rejectWithValue }) => {
  try {
    return await createOrigin(payload);
  } catch (error) {
    return rejectWithValue(message(error, 'Не удалось создать происхождение.'));
  }
});

export const updateOriginThunk = createAsyncThunk<
  OriginCountryAdmin,
  { originId: number; data: OriginCountryUpdatePayload },
  { rejectValue: string }
>('origins/update', async ({ originId, data }, { rejectWithValue }) => {
  try {
    return await updateOrigin(originId, data);
  } catch (error) {
    return rejectWithValue(message(error, 'Не удалось обновить происхождение.'));
  }
});

/** Soft delete — the row is hidden, not erased. */
export const deleteOriginThunk = createAsyncThunk<
  { id: number; is_active: boolean },
  number,
  { rejectValue: string }
>('origins/delete', async (originId, { rejectWithValue }) => {
  try {
    return await deleteOrigin(originId);
  } catch (error) {
    return rejectWithValue(message(error, 'Не удалось скрыть происхождение.'));
  }
});

// --- Slice ---

const originsSlice = createSlice({
  name: 'origins',
  initialState,
  reducers: {
    clearOriginsError(state) {
      state.error = null;
      state.adminError = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchOriginsThunk.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(
        fetchOriginsThunk.fulfilled,
        (state, action: PayloadAction<OriginCountry[]>) => {
          state.loading = false;
          state.list = action.payload || [];
        },
      )
      .addCase(fetchOriginsThunk.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Не удалось загрузить список происхождений.';
      })

      .addCase(fetchOriginsAdminThunk.pending, (state) => {
        state.adminLoading = true;
        state.adminError = null;
      })
      .addCase(
        fetchOriginsAdminThunk.fulfilled,
        (state, action: PayloadAction<OriginCountryAdmin[]>) => {
          state.adminLoading = false;
          state.adminList = action.payload || [];
        },
      )
      .addCase(fetchOriginsAdminThunk.rejected, (state, action) => {
        state.adminLoading = false;
        state.adminError = action.payload || 'Не удалось загрузить справочник происхождений.';
      })

      .addCase(createOriginThunk.pending, (state) => {
        state.adminLoading = true;
        state.adminError = null;
      })
      .addCase(
        createOriginThunk.fulfilled,
        (state, action: PayloadAction<OriginCountryAdmin>) => {
          state.adminLoading = false;
          state.adminList = [...state.adminList, action.payload];
        },
      )
      .addCase(createOriginThunk.rejected, (state, action) => {
        state.adminLoading = false;
        state.adminError = action.payload || 'Не удалось создать происхождение.';
      })

      .addCase(updateOriginThunk.pending, (state) => {
        state.adminLoading = true;
        state.adminError = null;
      })
      .addCase(
        updateOriginThunk.fulfilled,
        (state, action: PayloadAction<OriginCountryAdmin>) => {
          state.adminLoading = false;
          state.adminList = state.adminList.map((origin) =>
            origin.id === action.payload.id ? action.payload : origin,
          );
        },
      )
      .addCase(updateOriginThunk.rejected, (state, action) => {
        state.adminLoading = false;
        state.adminError = action.payload || 'Не удалось обновить происхождение.';
      })

      .addCase(deleteOriginThunk.pending, (state) => {
        state.adminLoading = true;
        state.adminError = null;
      })
      .addCase(deleteOriginThunk.fulfilled, (state, action) => {
        state.adminLoading = false;
        // Soft delete: the row stays in the admin list with is_active = false.
        state.adminList = state.adminList.map((origin) =>
          origin.id === action.payload.id
            ? { ...origin, is_active: action.payload.is_active }
            : origin,
        );
        state.list = state.list.filter((origin) => origin.id !== action.payload.id);
      })
      .addCase(deleteOriginThunk.rejected, (state, action) => {
        state.adminLoading = false;
        state.adminError = action.payload || 'Не удалось скрыть происхождение.';
      });
  },
});

// --- Selectors ---

export const selectOrigins = (state: RootState) => state.origins.list;
export const selectOriginsLoading = (state: RootState) => state.origins.loading;
export const selectOriginsError = (state: RootState) => state.origins.error;
export const selectAdminOrigins = (state: RootState) => state.origins.adminList;
export const selectAdminOriginsLoading = (state: RootState) => state.origins.adminLoading;
export const selectAdminOriginsError = (state: RootState) => state.origins.adminError;
/** Origin name by id — for the passport's «{подраса} из {страна}» line. */
export const selectOriginById =
  (originId: number | null | undefined) =>
  (state: RootState): OriginCountry | undefined =>
    originId ? state.origins.list.find((origin) => origin.id === originId) : undefined;

export const { clearOriginsError } = originsSlice.actions;

export default originsSlice.reducer;
