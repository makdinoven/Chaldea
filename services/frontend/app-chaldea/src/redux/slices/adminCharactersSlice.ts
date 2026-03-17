import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import toast from 'react-hot-toast';
import type { RootState, AppDispatch } from '../store';
import * as api from '../../api/adminCharacters';
import type {
  AdminCharacterListItem,
  AdminCharacterUpdate,
  AdminAttributeUpdate,
  CharacterAttributes,
  InventoryItem,
  EquipmentSlot,
  CharacterSkill,
  AdminCharacterFilters,
  AdminCharactersState,
} from '../../components/Admin/CharactersPage/types';

// --- Initial State ---

const initialState: AdminCharactersState = {
  characters: [],
  total: 0,
  page: 1,
  pageSize: 20,
  search: '',
  filters: {
    userId: null,
    levelMin: null,
    levelMax: null,
    raceId: null,
    classId: null,
  },
  listLoading: false,
  listError: null,

  selectedCharacter: null,
  attributes: null,
  inventory: [],
  equipment: [],
  skills: [],
  detailLoading: false,
  detailError: null,
};

// --- Async Thunks ---

export const fetchAdminCharacters = createAsyncThunk<
  { items: AdminCharacterListItem[]; total: number; page: number; page_size: number },
  void,
  { state: RootState; rejectValue: string }
>(
  'adminCharacters/fetchList',
  async (_, thunkAPI) => {
    try {
      const state = thunkAPI.getState().adminCharacters;
      const response = await api.fetchAdminCharacterList({
        q: state.search || undefined,
        user_id: state.filters.userId,
        level_min: state.filters.levelMin,
        level_max: state.filters.levelMax,
        id_race: state.filters.raceId,
        id_class: state.filters.classId,
        page: state.page,
        page_size: state.pageSize,
      });
      return response;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить список персонажей');
    }
  },
);

export const updateAdminCharacter = createAsyncThunk<
  { character_id: number },
  { characterId: number; update: AdminCharacterUpdate },
  { rejectValue: string }
>(
  'adminCharacters/update',
  async ({ characterId, update }, thunkAPI) => {
    try {
      const result = await api.updateAdminCharacter(characterId, update);
      toast.success('Персонаж обновлён');
      return result;
    } catch {
      toast.error('Не удалось обновить персонажа');
      return thunkAPI.rejectWithValue('Не удалось обновить персонажа');
    }
  },
);

export const unlinkAdminCharacter = createAsyncThunk<
  { character_id: number; previous_user_id: number },
  number,
  { rejectValue: string }
>(
  'adminCharacters/unlink',
  async (characterId, thunkAPI) => {
    try {
      const result = await api.unlinkCharacter(characterId);
      toast.success('Персонаж отвязан от аккаунта');
      return result;
    } catch {
      toast.error('Не удалось отвязать персонажа');
      return thunkAPI.rejectWithValue('Не удалось отвязать персонажа');
    }
  },
);

export const deleteAdminCharacter = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'adminCharacters/delete',
  async (characterId, thunkAPI) => {
    try {
      await api.deleteCharacter(characterId);
      toast.success('Персонаж удалён');
      return characterId;
    } catch {
      toast.error('Не удалось удалить персонажа');
      return thunkAPI.rejectWithValue('Не удалось удалить персонажа');
    }
  },
);

// --- Attributes ---

export const fetchAdminAttributes = createAsyncThunk<
  CharacterAttributes,
  number,
  { rejectValue: string }
>(
  'adminCharacters/fetchAttributes',
  async (characterId, thunkAPI) => {
    try {
      return await api.fetchCharacterAttributes(characterId);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить атрибуты персонажа');
    }
  },
);

export const updateAdminAttributes = createAsyncThunk<
  CharacterAttributes,
  { characterId: number; update: AdminAttributeUpdate },
  { rejectValue: string }
>(
  'adminCharacters/updateAttributes',
  async ({ characterId, update }, thunkAPI) => {
    try {
      const result = await api.updateCharacterAttributes(characterId, update);
      toast.success('Атрибуты обновлены');
      return result;
    } catch {
      toast.error('Не удалось обновить атрибуты');
      return thunkAPI.rejectWithValue('Не удалось обновить атрибуты');
    }
  },
);

// --- Inventory ---

export const fetchAdminInventory = createAsyncThunk<
  InventoryItem[],
  number,
  { rejectValue: string }
>(
  'adminCharacters/fetchInventory',
  async (characterId, thunkAPI) => {
    try {
      return await api.fetchCharacterInventory(characterId);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить инвентарь');
    }
  },
);

export const fetchAdminEquipment = createAsyncThunk<
  EquipmentSlot[],
  number,
  { rejectValue: string }
>(
  'adminCharacters/fetchEquipment',
  async (characterId, thunkAPI) => {
    try {
      return await api.fetchCharacterEquipment(characterId);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить экипировку');
    }
  },
);

export const addAdminInventoryItem = createAsyncThunk<
  void,
  { characterId: number; itemId: number; quantity: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'adminCharacters/addInventoryItem',
  async ({ characterId, itemId, quantity }, thunkAPI) => {
    try {
      await api.addInventoryItem(characterId, itemId, quantity);
      toast.success('Предмет добавлен');
      thunkAPI.dispatch(fetchAdminInventory(characterId));
    } catch {
      toast.error('Не удалось добавить предмет');
      return thunkAPI.rejectWithValue('Не удалось добавить предмет');
    }
  },
);

export const removeAdminInventoryItem = createAsyncThunk<
  void,
  { characterId: number; itemId: number; quantity?: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'adminCharacters/removeInventoryItem',
  async ({ characterId, itemId, quantity }, thunkAPI) => {
    try {
      await api.removeInventoryItem(characterId, itemId, quantity);
      toast.success('Предмет удалён');
      thunkAPI.dispatch(fetchAdminInventory(characterId));
    } catch {
      toast.error('Не удалось удалить предмет');
      return thunkAPI.rejectWithValue('Не удалось удалить предмет');
    }
  },
);

export const equipAdminItem = createAsyncThunk<
  void,
  { characterId: number; itemId: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'adminCharacters/equipItem',
  async ({ characterId, itemId }, thunkAPI) => {
    try {
      await api.equipItem(characterId, itemId);
      toast.success('Предмет экипирован');
      await Promise.all([
        thunkAPI.dispatch(fetchAdminInventory(characterId)),
        thunkAPI.dispatch(fetchAdminEquipment(characterId)),
      ]);
    } catch {
      toast.error('Не удалось экипировать предмет');
      return thunkAPI.rejectWithValue('Не удалось экипировать предмет');
    }
  },
);

export const unequipAdminItem = createAsyncThunk<
  void,
  { characterId: number; slotType: string },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'adminCharacters/unequipItem',
  async ({ characterId, slotType }, thunkAPI) => {
    try {
      await api.unequipItem(characterId, slotType);
      toast.success('Предмет снят');
      await Promise.all([
        thunkAPI.dispatch(fetchAdminInventory(characterId)),
        thunkAPI.dispatch(fetchAdminEquipment(characterId)),
      ]);
    } catch {
      toast.error('Не удалось снять предмет');
      return thunkAPI.rejectWithValue('Не удалось снять предмет');
    }
  },
);

// --- Skills ---

export const fetchAdminSkills = createAsyncThunk<
  CharacterSkill[],
  number,
  { rejectValue: string }
>(
  'adminCharacters/fetchSkills',
  async (characterId, thunkAPI) => {
    try {
      return await api.fetchCharacterSkills(characterId);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить навыки');
    }
  },
);

export const addAdminCharacterSkill = createAsyncThunk<
  void,
  { characterId: number; skillRankId: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'adminCharacters/addSkill',
  async ({ characterId, skillRankId }, thunkAPI) => {
    try {
      await api.addCharacterSkill(characterId, skillRankId);
      toast.success('Навык добавлен');
      thunkAPI.dispatch(fetchAdminSkills(characterId));
    } catch {
      toast.error('Не удалось добавить навык');
      return thunkAPI.rejectWithValue('Не удалось добавить навык');
    }
  },
);

export const removeAdminCharacterSkill = createAsyncThunk<
  void,
  { csId: number; characterId: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'adminCharacters/removeSkill',
  async ({ csId, characterId }, thunkAPI) => {
    try {
      await api.removeCharacterSkill(csId);
      toast.success('Навык удалён');
      thunkAPI.dispatch(fetchAdminSkills(characterId));
    } catch {
      toast.error('Не удалось удалить навык');
      return thunkAPI.rejectWithValue('Не удалось удалить навык');
    }
  },
);

export const updateAdminSkillRank = createAsyncThunk<
  void,
  { csId: number; skillRankId: number; characterId: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'adminCharacters/updateSkillRank',
  async ({ csId, skillRankId, characterId }, thunkAPI) => {
    try {
      await api.updateCharacterSkillRank(csId, skillRankId);
      toast.success('Ранг навыка обновлён');
      thunkAPI.dispatch(fetchAdminSkills(characterId));
    } catch {
      toast.error('Не удалось обновить ранг навыка');
      return thunkAPI.rejectWithValue('Не удалось обновить ранг навыка');
    }
  },
);

// --- Slice ---

const adminCharactersSlice = createSlice({
  name: 'adminCharacters',
  initialState,
  reducers: {
    setSearch(state, action: PayloadAction<string>) {
      state.search = action.payload;
      state.page = 1;
    },
    setPage(state, action: PayloadAction<number>) {
      state.page = action.payload;
    },
    setPageSize(state, action: PayloadAction<number>) {
      state.pageSize = action.payload;
      state.page = 1;
    },
    setFilters(state, action: PayloadAction<Partial<AdminCharacterFilters>>) {
      state.filters = { ...state.filters, ...action.payload };
      state.page = 1;
    },
    resetFilters(state) {
      state.filters = initialState.filters;
      state.search = '';
      state.page = 1;
    },
    setSelectedCharacter(state, action: PayloadAction<AdminCharacterListItem | null>) {
      state.selectedCharacter = action.payload;
    },
    clearDetail(state) {
      state.selectedCharacter = null;
      state.attributes = null;
      state.inventory = [];
      state.equipment = [];
      state.skills = [];
      state.detailError = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // --- List ---
      .addCase(fetchAdminCharacters.pending, (state) => {
        state.listLoading = true;
        state.listError = null;
      })
      .addCase(fetchAdminCharacters.fulfilled, (state, action) => {
        state.listLoading = false;
        state.characters = action.payload.items;
        state.total = action.payload.total;
        state.page = action.payload.page;
        state.pageSize = action.payload.page_size;
      })
      .addCase(fetchAdminCharacters.rejected, (state, action) => {
        state.listLoading = false;
        state.listError = action.payload ?? 'Произошла ошибка';
      })

      // --- Update character ---
      .addCase(updateAdminCharacter.fulfilled, (state, action) => {
        // Update the character in list if present
        const idx = state.characters.findIndex((c) => c.id === action.payload.character_id);
        if (idx !== -1 && state.selectedCharacter?.id === action.payload.character_id) {
          // Merge updates into selectedCharacter from the thunk arg
          // (the API only returns id + detail, so we apply local optimistic update)
          state.characters[idx] = { ...state.characters[idx], ...state.selectedCharacter };
        }
      })
      .addCase(updateAdminCharacter.rejected, (state, action) => {
        state.detailError = action.payload ?? 'Не удалось обновить персонажа';
      })

      // --- Unlink ---
      .addCase(unlinkAdminCharacter.fulfilled, (state, action) => {
        const id = action.payload.character_id;
        const idx = state.characters.findIndex((c) => c.id === id);
        if (idx !== -1) {
          state.characters[idx].user_id = null;
        }
        if (state.selectedCharacter?.id === id) {
          state.selectedCharacter.user_id = null;
        }
      })
      .addCase(unlinkAdminCharacter.rejected, (state, action) => {
        state.detailError = action.payload ?? 'Не удалось отвязать персонажа';
      })

      // --- Delete ---
      .addCase(deleteAdminCharacter.fulfilled, (state, action) => {
        state.characters = state.characters.filter((c) => c.id !== action.payload);
        state.total = Math.max(0, state.total - 1);
        if (state.selectedCharacter?.id === action.payload) {
          state.selectedCharacter = null;
        }
      })
      .addCase(deleteAdminCharacter.rejected, (state, action) => {
        state.detailError = action.payload ?? 'Не удалось удалить персонажа';
      })

      // --- Attributes ---
      .addCase(fetchAdminAttributes.pending, (state) => {
        state.detailLoading = true;
        state.detailError = null;
      })
      .addCase(fetchAdminAttributes.fulfilled, (state, action) => {
        state.detailLoading = false;
        state.attributes = action.payload;
      })
      .addCase(fetchAdminAttributes.rejected, (state, action) => {
        state.detailLoading = false;
        state.detailError = action.payload ?? 'Не удалось загрузить атрибуты';
      })

      .addCase(updateAdminAttributes.fulfilled, (state, action) => {
        state.attributes = action.payload;
      })
      .addCase(updateAdminAttributes.rejected, (state, action) => {
        state.detailError = action.payload ?? 'Не удалось обновить атрибуты';
      })

      // --- Inventory ---
      .addCase(fetchAdminInventory.pending, (state) => {
        state.detailLoading = true;
        state.detailError = null;
      })
      .addCase(fetchAdminInventory.fulfilled, (state, action) => {
        state.detailLoading = false;
        state.inventory = action.payload;
      })
      .addCase(fetchAdminInventory.rejected, (state, action) => {
        state.detailLoading = false;
        state.detailError = action.payload ?? 'Не удалось загрузить инвентарь';
      })

      .addCase(fetchAdminEquipment.pending, (state) => {
        state.detailLoading = true;
      })
      .addCase(fetchAdminEquipment.fulfilled, (state, action) => {
        state.detailLoading = false;
        state.equipment = action.payload;
      })
      .addCase(fetchAdminEquipment.rejected, (state, action) => {
        state.detailLoading = false;
        state.detailError = action.payload ?? 'Не удалось загрузить экипировку';
      })

      // --- Skills ---
      .addCase(fetchAdminSkills.pending, (state) => {
        state.detailLoading = true;
        state.detailError = null;
      })
      .addCase(fetchAdminSkills.fulfilled, (state, action) => {
        state.detailLoading = false;
        state.skills = action.payload;
      })
      .addCase(fetchAdminSkills.rejected, (state, action) => {
        state.detailLoading = false;
        state.detailError = action.payload ?? 'Не удалось загрузить навыки';
      });
  },
});

export const {
  setSearch,
  setPage,
  setPageSize,
  setFilters,
  resetFilters,
  setSelectedCharacter,
  clearDetail,
} = adminCharactersSlice.actions;

// --- Selectors ---

export const selectAdminCharacters = (state: RootState) => state.adminCharacters.characters;
export const selectAdminCharactersTotal = (state: RootState) => state.adminCharacters.total;
export const selectAdminCharactersPage = (state: RootState) => state.adminCharacters.page;
export const selectAdminCharactersPageSize = (state: RootState) => state.adminCharacters.pageSize;
export const selectAdminCharactersSearch = (state: RootState) => state.adminCharacters.search;
export const selectAdminCharactersFilters = (state: RootState) => state.adminCharacters.filters;
export const selectAdminCharactersListLoading = (state: RootState) => state.adminCharacters.listLoading;
export const selectAdminCharactersListError = (state: RootState) => state.adminCharacters.listError;

export const selectSelectedCharacter = (state: RootState) => state.adminCharacters.selectedCharacter;
export const selectAdminAttributes = (state: RootState) => state.adminCharacters.attributes;
export const selectAdminInventory = (state: RootState) => state.adminCharacters.inventory;
export const selectAdminEquipment = (state: RootState) => state.adminCharacters.equipment;
export const selectAdminSkills = (state: RootState) => state.adminCharacters.skills;
export const selectAdminDetailLoading = (state: RootState) => state.adminCharacters.detailLoading;
export const selectAdminDetailError = (state: RootState) => state.adminCharacters.detailError;

export default adminCharactersSlice.reducer;
