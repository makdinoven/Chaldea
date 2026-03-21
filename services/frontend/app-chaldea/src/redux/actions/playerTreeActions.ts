import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
import type {
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
  ClassSkillTreeRead,
  SkillFullTree,
} from '../../components/SkillTreeView/types';

const BASE_URL = '/skills';

export const fetchClassTree = createAsyncThunk<
  FullClassTreeResponse,
  number,
  { rejectValue: string }
>(
  'playerTree/fetchClassTree',
  async (classId, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/class_trees/by_class/${classId}`);
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return rejectWithValue(
        error.response?.data?.detail || error.message || 'Ошибка загрузки дерева навыков'
      );
    }
  }
);

export const fetchTreeProgress = createAsyncThunk<
  CharacterTreeProgressResponse,
  { treeId: number; characterId: number },
  { rejectValue: string }
>(
  'playerTree/fetchTreeProgress',
  async ({ treeId, characterId }, { rejectWithValue }) => {
    try {
      const res = await axios.get(
        `${BASE_URL}/class_trees/${treeId}/progress/${characterId}`
      );
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return rejectWithValue(
        error.response?.data?.detail || error.message || 'Ошибка загрузки прогресса'
      );
    }
  }
);

export const chooseNode = createAsyncThunk<
  { detail: string; node_id: number },
  { treeId: number; characterId: number; nodeId: number },
  { rejectValue: string }
>(
  'playerTree/chooseNode',
  async ({ treeId, characterId, nodeId }, { rejectWithValue }) => {
    try {
      const res = await axios.post(`${BASE_URL}/class_trees/${treeId}/choose_node`, {
        character_id: characterId,
        node_id: nodeId,
      });
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return rejectWithValue(
        error.response?.data?.detail || error.message || 'Ошибка выбора узла'
      );
    }
  }
);

export const purchaseSkill = createAsyncThunk<
  { detail: string; character_skill_id: number },
  { characterId: number; nodeId: number; skillId: number },
  { rejectValue: string }
>(
  'playerTree/purchaseSkill',
  async ({ characterId, nodeId, skillId }, { rejectWithValue }) => {
    try {
      const res = await axios.post(`${BASE_URL}/class_trees/purchase_skill`, {
        character_id: characterId,
        node_id: nodeId,
        skill_id: skillId,
      });
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return rejectWithValue(
        error.response?.data?.detail || error.message || 'Ошибка покупки навыка'
      );
    }
  }
);

export const upgradeSkill = createAsyncThunk<
  { detail: string },
  { characterId: number; nextRankId: number },
  { rejectValue: string }
>(
  'playerTree/upgradeSkill',
  async ({ characterId, nextRankId }, { rejectWithValue }) => {
    try {
      const res = await axios.post(`${BASE_URL}/character_skills/upgrade`, {
        character_id: characterId,
        next_rank_id: nextRankId,
      });
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return rejectWithValue(
        error.response?.data?.detail || error.message || 'Ошибка улучшения навыка'
      );
    }
  }
);

export const resetTree = createAsyncThunk<
  { detail: string; nodes_reset: number; skills_removed: number },
  { treeId: number; characterId: number },
  { rejectValue: string }
>(
  'playerTree/resetTree',
  async ({ treeId, characterId }, { rejectWithValue }) => {
    try {
      const res = await axios.post(`${BASE_URL}/class_trees/${treeId}/reset`, {
        character_id: characterId,
      });
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return rejectWithValue(
        error.response?.data?.detail || error.message || 'Ошибка сброса прогресса'
      );
    }
  }
);

export const fetchSubclassTrees = createAsyncThunk<
  ClassSkillTreeRead[],
  number,
  { rejectValue: string }
>(
  'playerTree/fetchSubclassTrees',
  async (classTreeId, { rejectWithValue }) => {
    try {
      const res = await axios.get(
        `${BASE_URL}/class_trees/subclass_trees/${classTreeId}`
      );
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return rejectWithValue(
        error.response?.data?.detail || error.message || 'Ошибка загрузки подклассов'
      );
    }
  }
);

export const fetchSkillFullTree = createAsyncThunk<
  SkillFullTree,
  number,
  { rejectValue: string }
>(
  'playerTree/fetchSkillFullTree',
  async (skillId, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/skills/${skillId}/full_tree`);
      return res.data;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return rejectWithValue(
        error.response?.data?.detail || error.message || 'Ошибка загрузки дерева навыка'
      );
    }
  }
);
