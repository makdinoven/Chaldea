import { createAsyncThunk } from '@reduxjs/toolkit';
import {
  getGameTime,
  getGameTimeAdmin,
  updateGameTimeAdmin,
  GameTimePublicResponse,
  GameTimeAdminResponse,
  GameTimeAdminUpdate,
} from '../../api/gameTime';

export const fetchGameTime = createAsyncThunk<
  GameTimePublicResponse,
  void,
  { rejectValue: string }
>(
  'gameTime/fetchPublic',
  async (_, thunkAPI) => {
    try {
      const response = await getGameTime();
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить игровое время');
    }
  },
);

export const fetchGameTimeAdmin = createAsyncThunk<
  GameTimeAdminResponse,
  void,
  { rejectValue: string }
>(
  'gameTime/fetchAdmin',
  async (_, thunkAPI) => {
    try {
      const response = await getGameTimeAdmin();
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить настройки игрового времени');
    }
  },
);

export const updateGameTimeAdminThunk = createAsyncThunk<
  GameTimeAdminResponse,
  GameTimeAdminUpdate,
  { rejectValue: string }
>(
  'gameTime/updateAdmin',
  async (data, thunkAPI) => {
    try {
      const response = await updateGameTimeAdmin(data);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось обновить игровое время');
    }
  },
);
