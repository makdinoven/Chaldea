import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios, { AxiosError } from 'axios';
import toast from 'react-hot-toast';
import type { RootState } from '../store';

// --- Types ---

export interface TeleportOption {
  link_id: number;
  to_npc_id: number;
  to_npc_name: string;
  to_location_id: number;
  to_location_name: string;
  cost_gold: number;
}

export interface TeleportOptionsResponse {
  from_npc_id: number;
  cooldown_seconds_remaining: number;
  options: TeleportOption[];
}

export interface TeleportResult {
  new_location_id: number;
  new_location_name?: string | null;
  currency_balance: number;
  last_teleport_at: string; // ISO
}

export interface TeleportLink {
  id: number;
  from_npc_id: number;
  to_npc_id: number;
  cost_gold: number;
  created_at?: string;
}

export interface TeleportLinkCreatePayload {
  from_npc_id: number;
  to_npc_id: number;
  cost_gold: number;
  bidirectional?: boolean;
}

export interface TeleportLinkUpdatePayload {
  cost_gold: number;
}

/**
 * Response from `POST /admin/teleport-links`.
 * When `bidirectional=true`, backend creates two rows in one transaction.
 */
export interface TeleportLinkCreateResponse {
  links: TeleportLink[];
}

interface BackendErrorDetail {
  detail?:
    | string
    | {
        detail?: string;
        required?: number;
        balance?: number;
        cooldown_seconds_remaining?: number;
      };
}

// --- State ---

export interface TeleportState {
  optionsByNpcId: Record<number, TeleportOption[]>;
  cooldownSecondsRemaining: number;
  loadingOptions: boolean;
  optionsError: string | null;
  executing: boolean;
  executeError: string | null;
  lastResult: TeleportResult | null;

  // Admin: teleport-links management
  adminLinksByNpcId: Record<number, TeleportLink[]>;
  adminLoading: boolean;
  adminError: string | null;
  adminSaving: boolean;
}

const initialState: TeleportState = {
  optionsByNpcId: {},
  cooldownSecondsRemaining: 0,
  loadingOptions: false,
  optionsError: null,
  executing: false,
  executeError: null,
  lastResult: null,
  adminLinksByNpcId: {},
  adminLoading: false,
  adminError: null,
  adminSaving: false,
};

// --- Helpers ---

/** Map backend error to a Russian human-readable string. */
const mapExecuteError = (err: unknown): string => {
  const axErr = err as AxiosError<BackendErrorDetail>;
  const status = axErr.response?.status;
  const raw = axErr.response?.data?.detail;
  const detailCode =
    typeof raw === 'string' ? raw : raw && typeof raw === 'object' ? raw.detail : undefined;

  if (status === 402 || detailCode === 'insufficient_gold') {
    return 'Недостаточно золота';
  }
  if (status === 409 || detailCode === 'cooldown_active') {
    return 'Телепорт ещё на перезарядке';
  }
  if (status === 404) {
    return 'Телепорт не найден';
  }
  if (status === 422) {
    return 'Связь телепорта недействительна';
  }
  if (status === 401) {
    return 'Требуется авторизация';
  }
  return 'Сетевая ошибка, попробуйте ещё раз';
};

// --- Thunks: player ---

export const fetchTeleportOptions = createAsyncThunk<
  { npcId: number; response: TeleportOptionsResponse },
  number,
  { rejectValue: string }
>(
  'teleport/fetchOptions',
  async (npcId, thunkAPI) => {
    try {
      const { data } = await axios.get<TeleportOptionsResponse>(
        `/characters/npcs/${npcId}/teleport-options`,
      );
      return { npcId, response: data };
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить направления телепорта');
    }
  },
);

export const executeTeleport = createAsyncThunk<
  TeleportResult,
  { npcId: number; linkId: number },
  { rejectValue: string }
>(
  'teleport/execute',
  async ({ npcId, linkId }, thunkAPI) => {
    try {
      const { data } = await axios.post<TeleportResult>(
        `/characters/npcs/${npcId}/teleport`,
        { link_id: linkId },
      );
      toast.success('Телепортация выполнена');
      return data;
    } catch (err) {
      const msg = mapExecuteError(err);
      toast.error(msg);
      return thunkAPI.rejectWithValue(msg);
    }
  },
);

// --- Thunks: admin ---

export const fetchAdminTeleportLinks = createAsyncThunk<
  { npcId: number; links: TeleportLink[] },
  number,
  { rejectValue: string }
>(
  'teleport/admin/list',
  async (npcId, thunkAPI) => {
    try {
      const { data } = await axios.get<TeleportLink[]>(
        `/characters/admin/teleport-links`,
        { params: { npc_id: npcId } },
      );
      return { npcId, links: Array.isArray(data) ? data : [] };
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить связи телепорта');
    }
  },
);

export const createTeleportLink = createAsyncThunk<
  TeleportLinkCreateResponse,
  TeleportLinkCreatePayload,
  { rejectValue: string }
>(
  'teleport/admin/create',
  async (payload, thunkAPI) => {
    try {
      const { data } = await axios.post<TeleportLinkCreateResponse | TeleportLink[] | TeleportLink>(
        `/characters/admin/teleport-links`,
        payload,
      );
      // Normalize: backend may return {links: [...]} or an array or a single row
      let links: TeleportLink[];
      if (Array.isArray(data)) {
        links = data;
      } else if (data && typeof data === 'object' && 'links' in data) {
        links = (data as TeleportLinkCreateResponse).links;
      } else {
        links = [data as TeleportLink];
      }
      toast.success('Связь телепорта создана');
      return { links };
    } catch {
      toast.error('Не удалось создать связь телепорта');
      return thunkAPI.rejectWithValue('Не удалось создать связь телепорта');
    }
  },
);

export const updateTeleportLink = createAsyncThunk<
  TeleportLink,
  { id: number; payload: TeleportLinkUpdatePayload },
  { rejectValue: string }
>(
  'teleport/admin/update',
  async ({ id, payload }, thunkAPI) => {
    try {
      const { data } = await axios.patch<TeleportLink>(
        `/characters/admin/teleport-links/${id}`,
        payload,
      );
      toast.success('Связь телепорта обновлена');
      return data;
    } catch {
      toast.error('Не удалось обновить связь телепорта');
      return thunkAPI.rejectWithValue('Не удалось обновить связь телепорта');
    }
  },
);

export const deleteTeleportLink = createAsyncThunk<
  { id: number },
  { id: number; deleteReverse?: boolean },
  { rejectValue: string }
>(
  'teleport/admin/delete',
  async ({ id, deleteReverse = true }, thunkAPI) => {
    try {
      await axios.delete(`/characters/admin/teleport-links/${id}`, {
        params: { delete_reverse: deleteReverse },
      });
      toast.success('Связь телепорта удалена');
      return { id };
    } catch {
      toast.error('Не удалось удалить связь телепорта');
      return thunkAPI.rejectWithValue('Не удалось удалить связь телепорта');
    }
  },
);

// --- Slice ---

const teleportSlice = createSlice({
  name: 'teleport',
  initialState,
  reducers: {
    clearTeleportError(state) {
      state.optionsError = null;
      state.executeError = null;
    },
    clearTeleportOptionsForNpc(state, action: PayloadAction<number>) {
      delete state.optionsByNpcId[action.payload];
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchTeleportOptions
      .addCase(fetchTeleportOptions.pending, (state) => {
        state.loadingOptions = true;
        state.optionsError = null;
      })
      .addCase(fetchTeleportOptions.fulfilled, (state, action) => {
        state.loadingOptions = false;
        state.optionsByNpcId[action.payload.npcId] = action.payload.response.options;
        state.cooldownSecondsRemaining =
          action.payload.response.cooldown_seconds_remaining;
      })
      .addCase(fetchTeleportOptions.rejected, (state, action) => {
        state.loadingOptions = false;
        state.optionsError = action.payload ?? 'Произошла ошибка';
      })
      // executeTeleport
      .addCase(executeTeleport.pending, (state) => {
        state.executing = true;
        state.executeError = null;
      })
      .addCase(executeTeleport.fulfilled, (state, action: PayloadAction<TeleportResult>) => {
        state.executing = false;
        state.lastResult = action.payload;
      })
      .addCase(executeTeleport.rejected, (state, action) => {
        state.executing = false;
        state.executeError = action.payload ?? 'Произошла ошибка';
      })
      // admin list
      .addCase(fetchAdminTeleportLinks.pending, (state) => {
        state.adminLoading = true;
        state.adminError = null;
      })
      .addCase(fetchAdminTeleportLinks.fulfilled, (state, action) => {
        state.adminLoading = false;
        state.adminLinksByNpcId[action.payload.npcId] = action.payload.links;
      })
      .addCase(fetchAdminTeleportLinks.rejected, (state, action) => {
        state.adminLoading = false;
        state.adminError = action.payload ?? 'Произошла ошибка';
      })
      // admin create
      .addCase(createTeleportLink.pending, (state) => {
        state.adminSaving = true;
      })
      .addCase(createTeleportLink.fulfilled, (state, action) => {
        state.adminSaving = false;
        for (const link of action.payload.links) {
          const bucket = state.adminLinksByNpcId[link.from_npc_id] ?? [];
          bucket.push(link);
          state.adminLinksByNpcId[link.from_npc_id] = bucket;
        }
      })
      .addCase(createTeleportLink.rejected, (state, action) => {
        state.adminSaving = false;
        state.adminError = action.payload ?? null;
      })
      // admin update
      .addCase(updateTeleportLink.pending, (state) => {
        state.adminSaving = true;
      })
      .addCase(updateTeleportLink.fulfilled, (state, action: PayloadAction<TeleportLink>) => {
        state.adminSaving = false;
        const link = action.payload;
        const bucket = state.adminLinksByNpcId[link.from_npc_id];
        if (bucket) {
          const idx = bucket.findIndex((l) => l.id === link.id);
          if (idx !== -1) bucket[idx] = link;
        }
      })
      .addCase(updateTeleportLink.rejected, (state, action) => {
        state.adminSaving = false;
        state.adminError = action.payload ?? null;
      })
      // admin delete
      .addCase(deleteTeleportLink.pending, (state) => {
        state.adminSaving = true;
      })
      .addCase(deleteTeleportLink.fulfilled, (state, action) => {
        state.adminSaving = false;
        const removedId = action.payload.id;
        for (const key of Object.keys(state.adminLinksByNpcId)) {
          const npcId = Number(key);
          state.adminLinksByNpcId[npcId] = state.adminLinksByNpcId[npcId].filter(
            (l) => l.id !== removedId,
          );
        }
      })
      .addCase(deleteTeleportLink.rejected, (state, action) => {
        state.adminSaving = false;
        state.adminError = action.payload ?? null;
      });
  },
});

export const { clearTeleportError, clearTeleportOptionsForNpc } = teleportSlice.actions;

// --- Selectors ---

export const selectTeleportOptions = (npcId: number) =>
  (state: RootState): TeleportOption[] | undefined =>
    state.teleport.optionsByNpcId[npcId];

export const selectTeleportCooldown = (state: RootState): number =>
  state.teleport.cooldownSecondsRemaining;

export const selectTeleportLoadingOptions = (state: RootState): boolean =>
  state.teleport.loadingOptions;

export const selectTeleportOptionsError = (state: RootState): string | null =>
  state.teleport.optionsError;

export const selectTeleportExecuting = (state: RootState): boolean =>
  state.teleport.executing;

export const selectTeleportExecuteError = (state: RootState): string | null =>
  state.teleport.executeError;

export const selectTeleportLastResult = (state: RootState): TeleportResult | null =>
  state.teleport.lastResult;

export const selectAdminTeleportLinks = (npcId: number) =>
  (state: RootState): TeleportLink[] | undefined =>
    state.teleport.adminLinksByNpcId[npcId];

export const selectAdminTeleportLoading = (state: RootState): boolean =>
  state.teleport.adminLoading;

export const selectAdminTeleportSaving = (state: RootState): boolean =>
  state.teleport.adminSaving;

export const selectAdminTeleportError = (state: RootState): string | null =>
  state.teleport.adminError;

export default teleportSlice.reducer;
