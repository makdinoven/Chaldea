import { createSlice, createAsyncThunk, createSelector, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';
import type { RootState, AppDispatch } from '../store';
import { getMe } from './userSlice';

// --- Types ---

export interface ItemData {
  id: number;
  name: string;
  image: string | null;
  item_level: number;
  item_type: string;
  item_rarity: string;
  price: number;
  max_stack_size: number;
  is_unique: boolean;
  description: string | null;
  armor_subclass: string | null;
  weapon_subclass: string | null;
  primary_damage_type: string | null;
  // modifiers
  strength_modifier: number;
  agility_modifier: number;
  intelligence_modifier: number;
  endurance_modifier: number;
  health_modifier: number;
  energy_modifier: number;
  mana_modifier: number;
  stamina_modifier: number;
  charisma_modifier: number;
  luck_modifier: number;
  damage_modifier: number;
  dodge_modifier: number;
  // recovery
  health_recovery: number;
  energy_recovery: number;
  mana_recovery: number;
  stamina_recovery: number;
  fast_slot_bonus: number;
}

export interface InventoryItem {
  id: number;
  character_id: number;
  item_id: number;
  quantity: number;
  item: ItemData;
}

export interface EquipmentSlotData {
  character_id: number;
  slot_type: string;
  item_id: number | null;
  is_enabled: boolean;
  item: ItemData | null;
}

export interface FastSlotData {
  slot_type: string;
  item_id: number;
  quantity: number;
  name: string;
  image: string | null;
}

export interface CharacterProfile {
  name: string;
  level: number;
  stat_points: number;
  currency_balance: number;
  avatar: string | null;
  active_title: string | null;
  level_progress: {
    current_exp_in_level: number;
    exp_to_next_level: number;
    progress_fraction: number;
  };
  attributes: {
    current_health: number;
    max_health: number;
    current_mana: number;
    max_mana: number;
    current_energy: number;
    max_energy: number;
    current_stamina: number;
    max_stamina: number;
  };
}

export interface CharacterAttributes {
  strength: number;
  agility: number;
  intelligence: number;
  endurance: number;
  health: number;
  mana: number;
  energy: number;
  stamina: number;
  charisma: number;
  luck: number;
  damage: number;
  dodge: number;
  critical_hit_chance: number;
  critical_damage: number;
  current_health: number;
  max_health: number;
  current_mana: number;
  max_mana: number;
  current_energy: number;
  max_energy: number;
  current_stamina: number;
  max_stamina: number;
  res_effects: number;
  res_physical: number;
  res_catting: number;
  res_crushing: number;
  res_piercing: number;
  res_magic: number;
  res_fire: number;
  res_ice: number;
  res_watering: number;
  res_electricity: number;
  res_sainting: number;
  res_wind: number;
  res_damning: number;
}

export interface UpgradeStatsPayload {
  strength?: number;
  agility?: number;
  intelligence?: number;
  endurance?: number;
  health?: number;
  mana?: number;
  energy?: number;
  stamina?: number;
  charisma?: number;
  luck?: number;
}

export interface CharacterRaceInfo {
  id: number;
  id_class: number;
  id_race: number;
  id_subrace: number;
  level: number;
}

export interface ContextMenuState {
  isOpen: boolean;
  x: number;
  y: number;
  item: InventoryItem | null;
  slotType?: string;
}

export interface RaceNamesMap {
  [raceId: number]: string;
}

export interface ProfileState {
  character: CharacterProfile | null;
  raceInfo: CharacterRaceInfo | null;
  attributes: CharacterAttributes | null;
  inventory: InventoryItem[];
  equipment: EquipmentSlotData[];
  fastSlots: FastSlotData[];
  selectedCategory: string;
  contextMenu: ContextMenuState;
  loading: boolean;
  error: string | null;
  avatarUploading: boolean;
  raceNamesMap: RaceNamesMap;
}

// --- Initial State ---

const initialState: ProfileState = {
  character: null,
  raceInfo: null,
  attributes: null,
  inventory: [],
  equipment: [],
  fastSlots: [],
  selectedCategory: 'all',
  contextMenu: {
    isOpen: false,
    x: 0,
    y: 0,
    item: null,
  },
  loading: false,
  error: null,
  avatarUploading: false,
  raceNamesMap: {},
};

// --- Async Thunks ---

export const fetchProfile = createAsyncThunk<
  CharacterProfile,
  number,
  { rejectValue: string }
>(
  'profile/fetchProfile',
  async (characterId, thunkAPI) => {
    try {
      const response = await axios.get(`/characters/${characterId}/full_profile`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить профиль персонажа');
    }
  },
);

export const fetchRaceInfo = createAsyncThunk<
  CharacterRaceInfo,
  number,
  { rejectValue: string }
>(
  'profile/fetchRaceInfo',
  async (characterId, thunkAPI) => {
    try {
      const response = await axios.get(`/characters/${characterId}/race_info`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить информацию о расе');
    }
  },
);

interface RaceApiItem {
  id_race: number;
  name: string;
}

export const fetchRaceNames = createAsyncThunk<
  RaceNamesMap,
  void,
  { rejectValue: string }
>(
  'profile/fetchRaceNames',
  async (_, thunkAPI) => {
    try {
      const response = await axios.get<RaceApiItem[]>('/characters/races');
      const map: RaceNamesMap = {};
      for (const race of response.data) {
        map[race.id_race] = race.name;
      }
      return map;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить названия рас');
    }
  },
);

export const fetchAttributes = createAsyncThunk<
  CharacterAttributes,
  number,
  { rejectValue: string }
>(
  'profile/fetchAttributes',
  async (characterId, thunkAPI) => {
    try {
      const response = await axios.get(`/attributes/${characterId}`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить характеристики персонажа');
    }
  },
);

export const fetchInventory = createAsyncThunk<
  InventoryItem[],
  number,
  { rejectValue: string }
>(
  'profile/fetchInventory',
  async (characterId, thunkAPI) => {
    try {
      const response = await axios.get(`/inventory/${characterId}/items`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить инвентарь');
    }
  },
);

export const fetchEquipment = createAsyncThunk<
  EquipmentSlotData[],
  number,
  { rejectValue: string }
>(
  'profile/fetchEquipment',
  async (characterId, thunkAPI) => {
    try {
      const response = await axios.get(`/inventory/${characterId}/equipment`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить экипировку');
    }
  },
);

export const fetchFastSlots = createAsyncThunk<
  FastSlotData[],
  number,
  { rejectValue: string }
>(
  'profile/fetchFastSlots',
  async (characterId, thunkAPI) => {
    try {
      const response = await axios.get(`/inventory/characters/${characterId}/fast_slots`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить быстрые слоты');
    }
  },
);

export const equipItem = createAsyncThunk<
  void,
  { characterId: number; itemId: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'profile/equipItem',
  async ({ characterId, itemId }, thunkAPI) => {
    try {
      await axios.post(`/inventory/${characterId}/equip`, { item_id: itemId });
      // Re-fetch inventory and equipment after successful equip
      await Promise.all([
        thunkAPI.dispatch(fetchInventory(characterId)),
        thunkAPI.dispatch(fetchEquipment(characterId)),
        thunkAPI.dispatch(fetchFastSlots(characterId)),
      ]);
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось экипировать предмет');
    }
  },
);

export const unequipItem = createAsyncThunk<
  void,
  { characterId: number; slotType: string },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'profile/unequipItem',
  async ({ characterId, slotType }, thunkAPI) => {
    try {
      await axios.post(`/inventory/${characterId}/unequip`, null, {
        params: { slot_type: slotType },
      });
      // Re-fetch inventory and equipment after successful unequip
      await Promise.all([
        thunkAPI.dispatch(fetchInventory(characterId)),
        thunkAPI.dispatch(fetchEquipment(characterId)),
        thunkAPI.dispatch(fetchFastSlots(characterId)),
      ]);
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось снять предмет');
    }
  },
);

export const useItem = createAsyncThunk<
  void,
  { characterId: number; itemId: number; quantity: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'profile/useItem',
  async ({ characterId, itemId, quantity }, thunkAPI) => {
    try {
      await axios.post(`/inventory/${characterId}/use_item`, {
        item_id: itemId,
        quantity,
      });
      // Re-fetch inventory, equipment, fast slots, and attributes after use
      await Promise.all([
        thunkAPI.dispatch(fetchInventory(characterId)),
        thunkAPI.dispatch(fetchEquipment(characterId)),
        thunkAPI.dispatch(fetchFastSlots(characterId)),
        thunkAPI.dispatch(fetchAttributes(characterId)),
      ]);
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось использовать предмет');
    }
  },
);

export const dropItem = createAsyncThunk<
  void,
  { characterId: number; itemId: number; quantity: number },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'profile/dropItem',
  async ({ characterId, itemId, quantity }, thunkAPI) => {
    try {
      await axios.delete(`/inventory/${characterId}/items/${itemId}`, {
        params: { quantity },
      });
      // Re-fetch inventory after drop
      await Promise.all([
        thunkAPI.dispatch(fetchInventory(characterId)),
        thunkAPI.dispatch(fetchFastSlots(characterId)),
      ]);
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось удалить предмет');
    }
  },
);

// --- Composite Thunk ---

export const loadProfileData = createAsyncThunk<
  void,
  number,
  { dispatch: AppDispatch; rejectValue: string }
>(
  'profile/loadProfileData',
  async (characterId, thunkAPI) => {
    try {
      await Promise.all([
        thunkAPI.dispatch(fetchProfile(characterId)),
        thunkAPI.dispatch(fetchRaceInfo(characterId)),
        thunkAPI.dispatch(fetchAttributes(characterId)),
        thunkAPI.dispatch(fetchInventory(characterId)),
        thunkAPI.dispatch(fetchEquipment(characterId)),
        thunkAPI.dispatch(fetchFastSlots(characterId)),
        thunkAPI.dispatch(fetchRaceNames()),
      ]);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить данные профиля');
    }
  },
);

export const uploadCharacterAvatar = createAsyncThunk<
  string,
  { characterId: number; userId: number; file: File },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'profile/uploadCharacterAvatar',
  async ({ characterId, userId, file }, thunkAPI) => {
    try {
      const formData = new FormData();
      formData.append('character_id', String(characterId));
      formData.append('user_id', String(userId));
      formData.append('file', file);

      const response = await axios.post('/photo/change_character_avatar_photo', formData);

      const avatarUrl: string = response.data.avatar_url;

      // Refresh header avatar via userSlice
      thunkAPI.dispatch(getMe());

      return avatarUrl;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить аватарку');
    }
  },
);

export const upgradeStats = createAsyncThunk<
  void,
  { characterId: number; stats: UpgradeStatsPayload },
  { rejectValue: string; dispatch: AppDispatch }
>(
  'profile/upgradeStats',
  async ({ characterId, stats }, thunkAPI) => {
    try {
      await axios.post(`/attributes/${characterId}/upgrade`, stats);
      await Promise.all([
        thunkAPI.dispatch(fetchProfile(characterId)),
        thunkAPI.dispatch(fetchAttributes(characterId)),
      ]);
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось распределить очки характеристик');
    }
  },
);

// --- Slice ---

const profileSlice = createSlice({
  name: 'profile',
  initialState,
  reducers: {
    setSelectedCategory(state, action: PayloadAction<string>) {
      state.selectedCategory = action.payload;
    },
    openContextMenu(state, action: PayloadAction<{ x: number; y: number; item: InventoryItem; slotType?: string }>) {
      state.contextMenu = {
        isOpen: true,
        x: action.payload.x,
        y: action.payload.y,
        item: action.payload.item,
        slotType: action.payload.slotType,
      };
    },
    closeContextMenu(state) {
      state.contextMenu = {
        isOpen: false,
        x: 0,
        y: 0,
        item: null,
        slotType: undefined,
      };
    },
  },
  extraReducers: (builder) => {
    builder
      // loadProfileData
      .addCase(loadProfileData.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadProfileData.fulfilled, (state) => {
        state.loading = false;
      })
      .addCase(loadProfileData.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Не удалось загрузить данные профиля';
      })
      // fetchProfile
      .addCase(fetchProfile.fulfilled, (state, action) => {
        state.character = action.payload;
      })
      .addCase(fetchProfile.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось загрузить профиль персонажа';
      })
      // fetchRaceInfo
      .addCase(fetchRaceInfo.fulfilled, (state, action) => {
        state.raceInfo = action.payload;
      })
      .addCase(fetchRaceInfo.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось загрузить информацию о расе';
      })
      // fetchAttributes
      .addCase(fetchAttributes.fulfilled, (state, action) => {
        state.attributes = action.payload;
      })
      .addCase(fetchAttributes.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось загрузить характеристики';
      })
      // fetchInventory
      .addCase(fetchInventory.fulfilled, (state, action) => {
        state.inventory = action.payload;
      })
      .addCase(fetchInventory.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось загрузить инвентарь';
      })
      // fetchEquipment
      .addCase(fetchEquipment.fulfilled, (state, action) => {
        state.equipment = action.payload;
      })
      .addCase(fetchEquipment.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось загрузить экипировку';
      })
      // fetchFastSlots
      .addCase(fetchFastSlots.fulfilled, (state, action) => {
        state.fastSlots = action.payload;
      })
      .addCase(fetchFastSlots.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось загрузить быстрые слоты';
      })
      // equipItem
      .addCase(equipItem.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось экипировать предмет';
      })
      // unequipItem
      .addCase(unequipItem.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось снять предмет';
      })
      // useItem
      .addCase(useItem.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось использовать предмет';
      })
      // dropItem
      .addCase(dropItem.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось удалить предмет';
      })
      // upgradeStats
      .addCase(upgradeStats.rejected, (state, action) => {
        state.error = action.payload ?? 'Не удалось распределить очки характеристик';
      })
      // fetchRaceNames
      .addCase(fetchRaceNames.fulfilled, (state, action) => {
        state.raceNamesMap = action.payload;
      })
      // uploadCharacterAvatar
      .addCase(uploadCharacterAvatar.pending, (state) => {
        state.avatarUploading = true;
      })
      .addCase(uploadCharacterAvatar.fulfilled, (state, action) => {
        state.avatarUploading = false;
        if (state.character) {
          state.character.avatar = action.payload;
        }
      })
      .addCase(uploadCharacterAvatar.rejected, (state) => {
        state.avatarUploading = false;
      });
  },
});

export const { setSelectedCategory, openContextMenu, closeContextMenu } = profileSlice.actions;

// --- Selectors ---

export const selectProfile = (state: RootState) => state.profile.character;
export const selectRaceInfo = (state: RootState) => state.profile.raceInfo;
export const selectAttributes = (state: RootState) => state.profile.attributes;
export const selectInventory = (state: RootState) => state.profile.inventory;
export const selectEquipment = (state: RootState) => state.profile.equipment;
export const selectFastSlots = (state: RootState) => state.profile.fastSlots;
export const selectSelectedCategory = (state: RootState) => state.profile.selectedCategory;
export const selectContextMenu = (state: RootState) => state.profile.contextMenu;
export const selectProfileLoading = (state: RootState) => state.profile.loading;
export const selectProfileError = (state: RootState) => state.profile.error;
export const selectAvatarUploading = (state: RootState) => state.profile.avatarUploading;
export const selectRaceNamesMap = (state: RootState) => state.profile.raceNamesMap;

export const selectFilteredInventory = createSelector(
  [selectInventory, selectSelectedCategory],
  (inventory, selectedCategory): InventoryItem[] => {
    if (selectedCategory === 'all') {
      return inventory;
    }
    return inventory.filter((item) => item.item.item_type === selectedCategory);
  },
);

export const selectEquipmentSlots = createSelector(
  [selectEquipment],
  (equipment): EquipmentSlotData[] => {
    return equipment.filter(
      (slot) => !slot.slot_type.startsWith('fast_slot_'),
    );
  },
);

export default profileSlice.reducer;
