import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';

// --- Types ---

export interface StatPreset {
  strength: number;
  agility: number;
  intelligence: number;
  endurance: number;
  health: number;
  energy: number;
  mana: number;
  stamina: number;
  charisma: number;
  luck: number;
}

export interface Subrace {
  id_subrace: number;
  id_race: number;
  name: string;
  description: string;
  image: string | null;
  stat_preset: StatPreset | null;
}

export interface Race {
  id_race: number;
  name: string;
  description: string;
  image: string | null;
  subraces: Subrace[];
}

export interface RaceCreateData {
  name: string;
  description: string;
}

export interface RaceUpdateData {
  name?: string;
  description?: string;
}

export interface SubraceCreateData {
  id_race: number;
  name: string;
  description: string;
  stat_preset: StatPreset;
}

export interface SubraceUpdateData {
  id_race?: number;
  name?: string;
  description?: string;
  stat_preset?: StatPreset;
}

interface RacesState {
  races: Race[];
  loading: boolean;
  error: string | null;
}

const initialState: RacesState = {
  races: [],
  loading: false,
  error: null,
};

// --- Thunks ---

export const fetchRaces = createAsyncThunk<
  Race[],
  void,
  { rejectValue: string }
>(
  'races/fetchRaces',
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.get('/characters/races');
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки списка рас');
    }
  }
);

export const createRace = createAsyncThunk<
  Race,
  RaceCreateData,
  { rejectValue: string }
>(
  'races/createRace',
  async (data, { rejectWithValue }) => {
    try {
      const response = await axios.post('/characters/admin/races', data);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка создания расы');
    }
  }
);

export const updateRace = createAsyncThunk<
  Race,
  { raceId: number; data: RaceUpdateData },
  { rejectValue: string }
>(
  'races/updateRace',
  async ({ raceId, data }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`/characters/admin/races/${raceId}`, data);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка обновления расы');
    }
  }
);

export const deleteRace = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'races/deleteRace',
  async (raceId, { rejectWithValue }) => {
    try {
      await axios.delete(`/characters/admin/races/${raceId}`);
      return raceId;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        return rejectWithValue(
          error.response.data?.detail || 'Невозможно удалить расу: существуют связанные подрасы или персонажи'
        );
      }
      return rejectWithValue('Ошибка удаления расы');
    }
  }
);

export const createSubrace = createAsyncThunk<
  Subrace,
  SubraceCreateData,
  { rejectValue: string }
>(
  'races/createSubrace',
  async (data, { rejectWithValue }) => {
    try {
      const response = await axios.post('/characters/admin/subraces', data);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка создания подрасы');
    }
  }
);

export const updateSubrace = createAsyncThunk<
  Subrace,
  { subraceId: number; data: SubraceUpdateData },
  { rejectValue: string }
>(
  'races/updateSubrace',
  async ({ subraceId, data }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`/characters/admin/subraces/${subraceId}`, data);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка обновления подрасы');
    }
  }
);

export const deleteSubrace = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'races/deleteSubrace',
  async (subraceId, { rejectWithValue }) => {
    try {
      await axios.delete(`/characters/admin/subraces/${subraceId}`);
      return subraceId;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        return rejectWithValue(
          error.response.data?.detail || 'Невозможно удалить подрасу: существуют связанные персонажи'
        );
      }
      return rejectWithValue('Ошибка удаления подрасы');
    }
  }
);

export const uploadRaceImage = createAsyncThunk<
  { message: string; image_url: string },
  { raceId: number; file: File },
  { rejectValue: string }
>(
  'races/uploadRaceImage',
  async ({ raceId, file }, { rejectWithValue }) => {
    try {
      const formData = new FormData();
      formData.append('race_id', String(raceId));
      formData.append('file', file);
      const response = await axios.post('/photo/change_race_image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки изображения расы');
    }
  }
);

export const uploadSubraceImage = createAsyncThunk<
  { message: string; image_url: string },
  { subraceId: number; file: File },
  { rejectValue: string }
>(
  'races/uploadSubraceImage',
  async ({ subraceId, file }, { rejectWithValue }) => {
    try {
      const formData = new FormData();
      formData.append('subrace_id', String(subraceId));
      formData.append('file', file);
      const response = await axios.post('/photo/change_subrace_image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки изображения подрасы');
    }
  }
);

// --- Slice ---

const racesSlice = createSlice({
  name: 'races',
  initialState,
  reducers: {
    clearRacesError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchRaces
      .addCase(fetchRaces.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchRaces.fulfilled, (state, action: PayloadAction<Race[]>) => {
        state.races = action.payload || [];
        state.loading = false;
      })
      .addCase(fetchRaces.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка загрузки рас';
      })

      // createRace
      .addCase(createRace.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createRace.fulfilled, (state) => {
        state.loading = false;
      })
      .addCase(createRace.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка создания расы';
      })

      // updateRace
      .addCase(updateRace.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateRace.fulfilled, (state) => {
        state.loading = false;
      })
      .addCase(updateRace.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка обновления расы';
      })

      // deleteRace
      .addCase(deleteRace.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteRace.fulfilled, (state, action: PayloadAction<number>) => {
        state.races = state.races.filter((r) => r.id_race !== action.payload);
        state.loading = false;
      })
      .addCase(deleteRace.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка удаления расы';
      })

      // createSubrace
      .addCase(createSubrace.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createSubrace.fulfilled, (state) => {
        state.loading = false;
      })
      .addCase(createSubrace.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка создания подрасы';
      })

      // updateSubrace
      .addCase(updateSubrace.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateSubrace.fulfilled, (state) => {
        state.loading = false;
      })
      .addCase(updateSubrace.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка обновления подрасы';
      })

      // deleteSubrace
      .addCase(deleteSubrace.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteSubrace.fulfilled, (state, action: PayloadAction<number>) => {
        state.races = state.races.map((race) => ({
          ...race,
          subraces: race.subraces.filter((s) => s.id_subrace !== action.payload),
        }));
        state.loading = false;
      })
      .addCase(deleteSubrace.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка удаления подрасы';
      })

      // uploadRaceImage
      .addCase(uploadRaceImage.rejected, (state, action) => {
        state.error = action.payload || 'Ошибка загрузки изображения расы';
      })

      // uploadSubraceImage
      .addCase(uploadSubraceImage.rejected, (state, action) => {
        state.error = action.payload || 'Ошибка загрузки изображения подрасы';
      });
  },
});

export const { clearRacesError } = racesSlice.actions;

export default racesSlice.reducer;
