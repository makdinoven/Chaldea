import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import toast from 'react-hot-toast';
import type { RootState } from '../store';
import * as api from '../../api/mobs';
import type {
  MobTemplateListItem,
  MobTemplateDetail,
  MobTemplate,
  MobLootEntry,
  LocationMobSpawn,
  ActiveMob,
  MobTemplateCreatePayload,
} from '../../api/mobs';

// --- State ---

interface MobsState {
  // Template list
  templates: MobTemplateListItem[];
  total: number;
  page: number;
  pageSize: number;
  search: string;
  tierFilter: string;
  listLoading: boolean;
  listError: string | null;

  // Template detail
  selectedTemplate: MobTemplateDetail | null;
  detailLoading: boolean;
  detailError: string | null;

  // Active mobs
  activeMobs: ActiveMob[];
  activeMobsTotal: number;
  activeMobsPage: number;
  activeMobsPageSize: number;
  activeMobsLoading: boolean;
  activeMobsError: string | null;
  activeMobsFilters: {
    locationId: number | null;
    status: string;
    templateId: number | null;
  };

  // Saving states
  saving: boolean;
}

const initialState: MobsState = {
  templates: [],
  total: 0,
  page: 1,
  pageSize: 20,
  search: '',
  tierFilter: '',
  listLoading: false,
  listError: null,

  selectedTemplate: null,
  detailLoading: false,
  detailError: null,

  activeMobs: [],
  activeMobsTotal: 0,
  activeMobsPage: 1,
  activeMobsPageSize: 20,
  activeMobsLoading: false,
  activeMobsError: null,
  activeMobsFilters: {
    locationId: null,
    status: '',
    templateId: null,
  },

  saving: false,
};

// --- Async Thunks ---

export const fetchMobTemplates = createAsyncThunk<
  api.MobTemplateListResponse,
  void,
  { state: RootState; rejectValue: string }
>(
  'mobs/fetchTemplates',
  async (_, thunkAPI) => {
    try {
      const state = thunkAPI.getState().mobs;
      return await api.fetchMobTemplates({
        q: state.search || undefined,
        tier: state.tierFilter || undefined,
        page: state.page,
        page_size: state.pageSize,
      });
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить список мобов');
    }
  },
);

export const fetchMobTemplate = createAsyncThunk<
  MobTemplateDetail,
  number,
  { rejectValue: string }
>(
  'mobs/fetchTemplate',
  async (id, thunkAPI) => {
    try {
      return await api.fetchMobTemplate(id);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить шаблон моба');
    }
  },
);

export const createMobTemplate = createAsyncThunk<
  MobTemplate,
  MobTemplateCreatePayload,
  { rejectValue: string }
>(
  'mobs/createTemplate',
  async (payload, thunkAPI) => {
    try {
      const result = await api.createMobTemplate(payload);
      toast.success('Шаблон моба создан');
      return result;
    } catch {
      toast.error('Не удалось создать шаблон моба');
      return thunkAPI.rejectWithValue('Не удалось создать шаблон моба');
    }
  },
);

export const updateMobTemplate = createAsyncThunk<
  MobTemplate,
  { id: number; payload: Partial<MobTemplateCreatePayload> },
  { rejectValue: string }
>(
  'mobs/updateTemplate',
  async ({ id, payload }, thunkAPI) => {
    try {
      const result = await api.updateMobTemplate(id, payload);
      toast.success('Шаблон моба обновлён');
      return result;
    } catch {
      toast.error('Не удалось обновить шаблон моба');
      return thunkAPI.rejectWithValue('Не удалось обновить шаблон моба');
    }
  },
);

export const deleteMobTemplate = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'mobs/deleteTemplate',
  async (id, thunkAPI) => {
    try {
      await api.deleteMobTemplate(id);
      toast.success('Шаблон моба удалён');
      return id;
    } catch {
      toast.error('Не удалось удалить шаблон моба');
      return thunkAPI.rejectWithValue('Не удалось удалить шаблон моба');
    }
  },
);

export const updateMobSkills = createAsyncThunk<
  { detail: string; skill_rank_ids: number[] },
  { templateId: number; skillRankIds: number[] },
  { rejectValue: string }
>(
  'mobs/updateSkills',
  async ({ templateId, skillRankIds }, thunkAPI) => {
    try {
      const result = await api.updateMobSkills(templateId, skillRankIds);
      toast.success('Навыки моба обновлены');
      return result;
    } catch {
      toast.error('Не удалось обновить навыки моба');
      return thunkAPI.rejectWithValue('Не удалось обновить навыки моба');
    }
  },
);

export const updateMobLoot = createAsyncThunk<
  { detail: string; entries: MobLootEntry[] },
  { templateId: number; entries: Array<{ item_id: number; drop_chance: number; min_quantity: number; max_quantity: number }> },
  { rejectValue: string }
>(
  'mobs/updateLoot',
  async ({ templateId, entries }, thunkAPI) => {
    try {
      const result = await api.updateMobLoot(templateId, entries);
      toast.success('Лут-таблица обновлена');
      return result;
    } catch {
      toast.error('Не удалось обновить лут-таблицу');
      return thunkAPI.rejectWithValue('Не удалось обновить лут-таблицу');
    }
  },
);

export const updateMobSpawns = createAsyncThunk<
  { detail: string; spawns: LocationMobSpawn[] },
  { templateId: number; spawns: Array<{ location_id: number; spawn_chance: number; max_active: number; is_enabled: boolean }> },
  { rejectValue: string }
>(
  'mobs/updateSpawns',
  async ({ templateId, spawns }, thunkAPI) => {
    try {
      const result = await api.updateMobSpawns(templateId, spawns);
      toast.success('Спавн-конфигурация обновлена');
      return result;
    } catch {
      toast.error('Не удалось обновить конфигурацию спавна');
      return thunkAPI.rejectWithValue('Не удалось обновить конфигурацию спавна');
    }
  },
);

export const fetchActiveMobs = createAsyncThunk<
  api.ActiveMobListResponse,
  void,
  { state: RootState; rejectValue: string }
>(
  'mobs/fetchActiveMobs',
  async (_, thunkAPI) => {
    try {
      const state = thunkAPI.getState().mobs;
      return await api.fetchActiveMobs({
        location_id: state.activeMobsFilters.locationId ?? undefined,
        status: state.activeMobsFilters.status || undefined,
        template_id: state.activeMobsFilters.templateId ?? undefined,
        page: state.activeMobsPage,
        page_size: state.activeMobsPageSize,
      });
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить активных мобов');
    }
  },
);

export const spawnMob = createAsyncThunk<
  ActiveMob,
  { mobTemplateId: number; locationId: number },
  { rejectValue: string }
>(
  'mobs/spawnMob',
  async ({ mobTemplateId, locationId }, thunkAPI) => {
    try {
      const result = await api.spawnMob(mobTemplateId, locationId);
      toast.success('Моб размещён на локации');
      return result;
    } catch {
      toast.error('Не удалось разместить моба');
      return thunkAPI.rejectWithValue('Не удалось разместить моба');
    }
  },
);

export const deleteActiveMob = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'mobs/deleteActiveMob',
  async (id, thunkAPI) => {
    try {
      await api.deleteActiveMob(id);
      toast.success('Активный моб удалён');
      return id;
    } catch {
      toast.error('Не удалось удалить активного моба');
      return thunkAPI.rejectWithValue('Не удалось удалить активного моба');
    }
  },
);

// --- Slice ---

const mobsSlice = createSlice({
  name: 'mobs',
  initialState,
  reducers: {
    setSearch(state, action: PayloadAction<string>) {
      state.search = action.payload;
      state.page = 1;
    },
    setTierFilter(state, action: PayloadAction<string>) {
      state.tierFilter = action.payload;
      state.page = 1;
    },
    setPage(state, action: PayloadAction<number>) {
      state.page = action.payload;
    },
    setPageSize(state, action: PayloadAction<number>) {
      state.pageSize = action.payload;
      state.page = 1;
    },
    clearSelectedTemplate(state) {
      state.selectedTemplate = null;
      state.detailError = null;
    },
    setActiveMobsPage(state, action: PayloadAction<number>) {
      state.activeMobsPage = action.payload;
    },
    setActiveMobsFilters(state, action: PayloadAction<Partial<MobsState['activeMobsFilters']>>) {
      state.activeMobsFilters = { ...state.activeMobsFilters, ...action.payload };
      state.activeMobsPage = 1;
    },
    resetActiveMobsFilters(state) {
      state.activeMobsFilters = initialState.activeMobsFilters;
      state.activeMobsPage = 1;
    },
  },
  extraReducers: (builder) => {
    builder
      // --- Template list ---
      .addCase(fetchMobTemplates.pending, (state) => {
        state.listLoading = true;
        state.listError = null;
      })
      .addCase(fetchMobTemplates.fulfilled, (state, action) => {
        state.listLoading = false;
        state.templates = action.payload.items;
        state.total = action.payload.total;
        state.page = action.payload.page;
        state.pageSize = action.payload.page_size;
      })
      .addCase(fetchMobTemplates.rejected, (state, action) => {
        state.listLoading = false;
        state.listError = action.payload ?? 'Произошла ошибка';
      })

      // --- Template detail ---
      .addCase(fetchMobTemplate.pending, (state) => {
        state.detailLoading = true;
        state.detailError = null;
      })
      .addCase(fetchMobTemplate.fulfilled, (state, action) => {
        state.detailLoading = false;
        state.selectedTemplate = action.payload;
      })
      .addCase(fetchMobTemplate.rejected, (state, action) => {
        state.detailLoading = false;
        state.detailError = action.payload ?? 'Произошла ошибка';
      })

      // --- Create template ---
      .addCase(createMobTemplate.pending, (state) => {
        state.saving = true;
      })
      .addCase(createMobTemplate.fulfilled, (state) => {
        state.saving = false;
      })
      .addCase(createMobTemplate.rejected, (state) => {
        state.saving = false;
      })

      // --- Update template ---
      .addCase(updateMobTemplate.pending, (state) => {
        state.saving = true;
      })
      .addCase(updateMobTemplate.fulfilled, (state) => {
        state.saving = false;
      })
      .addCase(updateMobTemplate.rejected, (state) => {
        state.saving = false;
      })

      // --- Delete template ---
      .addCase(deleteMobTemplate.fulfilled, (state, action) => {
        state.templates = state.templates.filter((t) => t.id !== action.payload);
        state.total = Math.max(0, state.total - 1);
        if (state.selectedTemplate?.id === action.payload) {
          state.selectedTemplate = null;
        }
      })

      // --- Update skills ---
      .addCase(updateMobSkills.pending, (state) => {
        state.saving = true;
      })
      .addCase(updateMobSkills.fulfilled, (state) => {
        state.saving = false;
      })
      .addCase(updateMobSkills.rejected, (state) => {
        state.saving = false;
      })

      // --- Update loot ---
      .addCase(updateMobLoot.pending, (state) => {
        state.saving = true;
      })
      .addCase(updateMobLoot.fulfilled, (state) => {
        state.saving = false;
      })
      .addCase(updateMobLoot.rejected, (state) => {
        state.saving = false;
      })

      // --- Update spawns ---
      .addCase(updateMobSpawns.pending, (state) => {
        state.saving = true;
      })
      .addCase(updateMobSpawns.fulfilled, (state) => {
        state.saving = false;
      })
      .addCase(updateMobSpawns.rejected, (state) => {
        state.saving = false;
      })

      // --- Active mobs ---
      .addCase(fetchActiveMobs.pending, (state) => {
        state.activeMobsLoading = true;
        state.activeMobsError = null;
      })
      .addCase(fetchActiveMobs.fulfilled, (state, action) => {
        state.activeMobsLoading = false;
        state.activeMobs = action.payload.items;
        state.activeMobsTotal = action.payload.total;
        state.activeMobsPage = action.payload.page;
        state.activeMobsPageSize = action.payload.page_size;
      })
      .addCase(fetchActiveMobs.rejected, (state, action) => {
        state.activeMobsLoading = false;
        state.activeMobsError = action.payload ?? 'Произошла ошибка';
      })

      // --- Spawn mob ---
      .addCase(spawnMob.pending, (state) => {
        state.saving = true;
      })
      .addCase(spawnMob.fulfilled, (state) => {
        state.saving = false;
      })
      .addCase(spawnMob.rejected, (state) => {
        state.saving = false;
      })

      // --- Delete active mob ---
      .addCase(deleteActiveMob.fulfilled, (state, action) => {
        state.activeMobs = state.activeMobs.filter((m) => m.id !== action.payload);
        state.activeMobsTotal = Math.max(0, state.activeMobsTotal - 1);
      });
  },
});

export const {
  setSearch,
  setTierFilter,
  setPage,
  setPageSize,
  clearSelectedTemplate,
  setActiveMobsPage,
  setActiveMobsFilters,
  resetActiveMobsFilters,
} = mobsSlice.actions;

// --- Selectors ---

export const selectMobTemplates = (state: RootState) => state.mobs.templates;
export const selectMobTemplatesTotal = (state: RootState) => state.mobs.total;
export const selectMobTemplatesPage = (state: RootState) => state.mobs.page;
export const selectMobTemplatesPageSize = (state: RootState) => state.mobs.pageSize;
export const selectMobTemplatesSearch = (state: RootState) => state.mobs.search;
export const selectMobTemplatesTierFilter = (state: RootState) => state.mobs.tierFilter;
export const selectMobTemplatesListLoading = (state: RootState) => state.mobs.listLoading;
export const selectMobTemplatesListError = (state: RootState) => state.mobs.listError;

export const selectSelectedTemplate = (state: RootState) => state.mobs.selectedTemplate;
export const selectDetailLoading = (state: RootState) => state.mobs.detailLoading;
export const selectDetailError = (state: RootState) => state.mobs.detailError;

export const selectActiveMobs = (state: RootState) => state.mobs.activeMobs;
export const selectActiveMobsTotal = (state: RootState) => state.mobs.activeMobsTotal;
export const selectActiveMobsPage = (state: RootState) => state.mobs.activeMobsPage;
export const selectActiveMobsPageSize = (state: RootState) => state.mobs.activeMobsPageSize;
export const selectActiveMobsLoading = (state: RootState) => state.mobs.activeMobsLoading;
export const selectActiveMobsError = (state: RootState) => state.mobs.activeMobsError;
export const selectActiveMobsFilters = (state: RootState) => state.mobs.activeMobsFilters;

export const selectMobsSaving = (state: RootState) => state.mobs.saving;

export default mobsSlice.reducer;
