import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';
import toast from 'react-hot-toast';
import type { RootState } from '../store';

// --- Types ---

export interface RouteWaypoint {
  x: number;
  y: number;
}

export interface FloatingStructure {
  id: number;
  name: string;
  description: string | null;
  icon_url: string | null;
  route_json: RouteWaypoint[];
  speed: number;
  started_at: string; // ISO
  internal_district_id: number | null;
  area_id: number | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * Shape returned by the public `GET /map/floating-structures` endpoint.
 * Same as FloatingStructure, plus a per-item `server_now` used by the client
 * to compute a clock-skew offset for position interpolation.
 */
export interface FloatingStructurePublic extends FloatingStructure {
  server_now: string; // ISO
}

export interface FloatingStructureCreatePayload {
  name: string;
  description?: string | null;
  icon_url?: string | null;
  route_json: RouteWaypoint[];
  speed: number;
  started_at?: string | null;
  internal_district_id?: number | null;
  area_id?: number | null;
}

export type FloatingStructureUpdatePayload = Partial<FloatingStructureCreatePayload>;

// --- State ---

export interface FloatingStructuresState {
  items: FloatingStructure[];
  /** client_now_ms - server_now_ms, used to interpolate positions. */
  serverNowOffsetMs: number;
  loading: boolean;
  error: string | null;
  saving: boolean;
}

const initialState: FloatingStructuresState = {
  items: [],
  serverNowOffsetMs: 0,
  loading: false,
  error: null,
  saving: false,
};

// --- Thunks: public ---

interface FetchFloatingStructuresResult {
  items: FloatingStructure[];
  serverNowOffsetMs: number;
}

export const fetchFloatingStructures = createAsyncThunk<
  FetchFloatingStructuresResult,
  number | undefined,
  { rejectValue: string }
>(
  'floatingStructures/fetch',
  async (areaId, thunkAPI) => {
    try {
      const url = areaId != null
        ? `/locations/map/floating-structures?area_id=${areaId}`
        : '/locations/map/floating-structures';
      const { data } = await axios.get<FloatingStructurePublic[]>(url);
      const list = Array.isArray(data) ? data : [];
      const clientNow = Date.now();
      let offset = 0;
      if (list.length > 0 && list[0].server_now) {
        const serverNow = new Date(list[0].server_now).getTime();
        if (!Number.isNaN(serverNow)) {
          offset = clientNow - serverNow;
        }
      }
      const items: FloatingStructure[] = list.map((it) => ({
        id: it.id,
        name: it.name,
        description: it.description,
        icon_url: it.icon_url,
        route_json: it.route_json ?? [],
        speed: it.speed,
        started_at: it.started_at,
        internal_district_id: it.internal_district_id,
        area_id: it.area_id,
      }));
      return { items, serverNowOffsetMs: offset };
    } catch {
      toast.error('Не удалось загрузить плавающие структуры');
      return thunkAPI.rejectWithValue('Не удалось загрузить плавающие структуры');
    }
  },
);

// --- Thunks: admin ---

export const fetchAdminFloatingStructures = createAsyncThunk<
  FloatingStructure[],
  void,
  { rejectValue: string }
>(
  'floatingStructures/admin/list',
  async (_, thunkAPI) => {
    try {
      const { data } = await axios.get<FloatingStructure[]>(
        '/locations/admin/floating-structures',
      );
      return Array.isArray(data) ? data : [];
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить плавающие структуры');
    }
  },
);

export const createFloatingStructure = createAsyncThunk<
  FloatingStructure,
  FloatingStructureCreatePayload,
  { rejectValue: string }
>(
  'floatingStructures/admin/create',
  async (payload, thunkAPI) => {
    try {
      const { data } = await axios.post<FloatingStructure>(
        '/locations/admin/floating-structures',
        payload,
      );
      toast.success('Плавающая структура создана');
      return data;
    } catch {
      toast.error('Не удалось создать плавающую структуру');
      return thunkAPI.rejectWithValue('Не удалось создать плавающую структуру');
    }
  },
);

export const updateFloatingStructure = createAsyncThunk<
  FloatingStructure,
  { id: number; payload: FloatingStructureUpdatePayload },
  { rejectValue: string }
>(
  'floatingStructures/admin/update',
  async ({ id, payload }, thunkAPI) => {
    try {
      const { data } = await axios.patch<FloatingStructure>(
        `/locations/admin/floating-structures/${id}`,
        payload,
      );
      toast.success('Плавающая структура обновлена');
      return data;
    } catch {
      toast.error('Не удалось обновить плавающую структуру');
      return thunkAPI.rejectWithValue('Не удалось обновить плавающую структуру');
    }
  },
);

export const deleteFloatingStructure = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'floatingStructures/admin/delete',
  async (id, thunkAPI) => {
    try {
      await axios.delete(`/locations/admin/floating-structures/${id}`);
      toast.success('Плавающая структура удалена');
      return id;
    } catch {
      toast.error('Не удалось удалить плавающую структуру');
      return thunkAPI.rejectWithValue('Не удалось удалить плавающую структуру');
    }
  },
);

// --- Slice ---

const floatingStructuresSlice = createSlice({
  name: 'floatingStructures',
  initialState,
  reducers: {
    clearFloatingStructuresError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // public fetch
      .addCase(fetchFloatingStructures.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(
        fetchFloatingStructures.fulfilled,
        (state, action: PayloadAction<FetchFloatingStructuresResult>) => {
          state.loading = false;
          state.items = action.payload.items;
          state.serverNowOffsetMs = action.payload.serverNowOffsetMs;
        },
      )
      .addCase(fetchFloatingStructures.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // admin list
      .addCase(fetchAdminFloatingStructures.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(
        fetchAdminFloatingStructures.fulfilled,
        (state, action: PayloadAction<FloatingStructure[]>) => {
          state.loading = false;
          state.items = action.payload;
        },
      )
      .addCase(fetchAdminFloatingStructures.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // create
      .addCase(createFloatingStructure.pending, (state) => {
        state.saving = true;
      })
      .addCase(
        createFloatingStructure.fulfilled,
        (state, action: PayloadAction<FloatingStructure>) => {
          state.saving = false;
          state.items.push(action.payload);
        },
      )
      .addCase(createFloatingStructure.rejected, (state, action) => {
        state.saving = false;
        state.error = action.payload ?? null;
      })
      // update
      .addCase(updateFloatingStructure.pending, (state) => {
        state.saving = true;
      })
      .addCase(
        updateFloatingStructure.fulfilled,
        (state, action: PayloadAction<FloatingStructure>) => {
          state.saving = false;
          const idx = state.items.findIndex((it) => it.id === action.payload.id);
          if (idx !== -1) {
            state.items[idx] = action.payload;
          } else {
            state.items.push(action.payload);
          }
        },
      )
      .addCase(updateFloatingStructure.rejected, (state, action) => {
        state.saving = false;
        state.error = action.payload ?? null;
      })
      // delete
      .addCase(deleteFloatingStructure.pending, (state) => {
        state.saving = true;
      })
      .addCase(
        deleteFloatingStructure.fulfilled,
        (state, action: PayloadAction<number>) => {
          state.saving = false;
          state.items = state.items.filter((it) => it.id !== action.payload);
        },
      )
      .addCase(deleteFloatingStructure.rejected, (state, action) => {
        state.saving = false;
        state.error = action.payload ?? null;
      });
  },
});

export const { clearFloatingStructuresError } = floatingStructuresSlice.actions;

// --- Selectors ---

export const selectFloatingStructures = (state: RootState): FloatingStructure[] =>
  state.floatingStructures.items;

export const selectFloatingStructuresLoading = (state: RootState): boolean =>
  state.floatingStructures.loading;

export const selectFloatingStructuresError = (state: RootState): string | null =>
  state.floatingStructures.error;

export const selectFloatingStructuresSaving = (state: RootState): boolean =>
  state.floatingStructures.saving;

export const selectServerNowOffsetMs = (state: RootState): number =>
  state.floatingStructures.serverNowOffsetMs;

export const selectFloatingStructureById = (id: number) =>
  (state: RootState): FloatingStructure | undefined =>
    state.floatingStructures.items.find((it) => it.id === id);

export default floatingStructuresSlice.reducer;
