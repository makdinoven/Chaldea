import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
import type {
  ClassSkillTreeRead,
  ClassSkillTreeCreate,
  FullClassTreeResponse,
  FullClassTreeUpdateRequest,
  SaveClassTreeResponse,
} from '../../components/AdminClassTreeEditor/types';

const BASE_URL = '/skills';

export const fetchClassTrees = createAsyncThunk<
  ClassSkillTreeRead[],
  void,
  { rejectValue: string }
>(
  'classTreeAdmin/fetchClassTrees',
  async (_, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/admin/class_trees/`);
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: string }; message?: string };
      return rejectWithValue(error.response?.data as string || error.message || 'Ошибка загрузки деревьев');
    }
  }
);

export const fetchFullClassTree = createAsyncThunk<
  FullClassTreeResponse,
  number,
  { rejectValue: string }
>(
  'classTreeAdmin/fetchFullClassTree',
  async (treeId, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/admin/class_trees/${treeId}/full`);
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: string }; message?: string };
      return rejectWithValue(error.response?.data as string || error.message || 'Ошибка загрузки дерева');
    }
  }
);

export const saveFullClassTree = createAsyncThunk<
  SaveClassTreeResponse,
  { treeId: number; data: FullClassTreeUpdateRequest },
  { rejectValue: string }
>(
  'classTreeAdmin/saveFullClassTree',
  async ({ treeId, data }, { rejectWithValue }) => {
    try {
      const res = await axios.put(`${BASE_URL}/admin/class_trees/${treeId}/full`, data);
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: string }; message?: string };
      return rejectWithValue(error.response?.data as string || error.message || 'Ошибка сохранения дерева');
    }
  }
);

export const createClassTree = createAsyncThunk<
  ClassSkillTreeRead,
  ClassSkillTreeCreate,
  { rejectValue: string }
>(
  'classTreeAdmin/createClassTree',
  async (data, { rejectWithValue }) => {
    try {
      const res = await axios.post(`${BASE_URL}/admin/class_trees/`, data);
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: string }; message?: string };
      return rejectWithValue(error.response?.data as string || error.message || 'Ошибка создания дерева');
    }
  }
);

export const deleteClassTree = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'classTreeAdmin/deleteClassTree',
  async (treeId, { rejectWithValue }) => {
    try {
      await axios.delete(`${BASE_URL}/admin/class_trees/${treeId}`);
      return treeId;
    } catch (err: unknown) {
      const error = err as { response?: { data?: string }; message?: string };
      return rejectWithValue(error.response?.data as string || error.message || 'Ошибка удаления дерева');
    }
  }
);
