import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
import type {
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
  ClassSkillTreeRead,
  SkillWithPerks,
  ResolvedSkill,
  CharacterSkillState,
} from '../../components/SkillTreeView/types';

const BASE_URL = '/skills';

const extractError = (err: unknown, fallback: string): string => {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e.response?.data?.detail || e.message || fallback;
};

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
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки дерева навыков'));
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
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки прогресса'));
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
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка выбора узла'));
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
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка покупки навыка'));
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
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка сброса прогресса'));
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
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки подклассов'));
    }
  }
);

// --- Perk system (FEAT-125) ---

export const fetchSkillWithPerks = createAsyncThunk<
  SkillWithPerks,
  number,
  { rejectValue: string }
>(
  'playerTree/fetchSkillWithPerks',
  async (skillId, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/${skillId}`);
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки навыка'));
    }
  }
);

export const fetchResolvedSkill = createAsyncThunk<
  ResolvedSkill,
  { skillId: number; characterId: number },
  { rejectValue: string }
>(
  'playerTree/fetchResolvedSkill',
  async ({ skillId, characterId }, { rejectWithValue }) => {
    try {
      const res = await axios.get(
        `${BASE_URL}/${skillId}/resolved`,
        { params: { character_id: characterId } }
      );
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки характеристик навыка'));
    }
  }
);

export const fetchCharacterSkills = createAsyncThunk<
  CharacterSkillState[],
  number,
  { rejectValue: string }
>(
  'playerTree/fetchCharacterSkills',
  async (characterId, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/characters/${characterId}/skills`);
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки навыков персонажа'));
    }
  }
);

export const upgradeSkillLevel = createAsyncThunk<
  CharacterSkillState,
  { characterId: number; skillId: number },
  { rejectValue: string }
>(
  'playerTree/upgradeSkillLevel',
  async ({ characterId, skillId }, { rejectWithValue }) => {
    try {
      const res = await axios.post(
        `${BASE_URL}/characters/${characterId}/skills/${skillId}/upgrade`
      );
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка улучшения навыка'));
    }
  }
);

export const pickSkillPerk = createAsyncThunk<
  CharacterSkillState,
  { characterId: number; skillId: number; perkId: number },
  { rejectValue: string }
>(
  'playerTree/pickSkillPerk',
  async ({ characterId, skillId, perkId }, { rejectWithValue }) => {
    try {
      const res = await axios.post(
        `${BASE_URL}/characters/${characterId}/skills/${skillId}/perks/${perkId}`
      );
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка выбора перка'));
    }
  }
);

export const resetSkill = createAsyncThunk<
  CharacterSkillState,
  { characterId: number; skillId: number },
  { rejectValue: string }
>(
  'playerTree/resetSkill',
  async ({ characterId, skillId }, { rejectWithValue }) => {
    try {
      const res = await axios.post(
        `${BASE_URL}/characters/${characterId}/skills/${skillId}/reset`
      );
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка сброса навыка'));
    }
  }
);
