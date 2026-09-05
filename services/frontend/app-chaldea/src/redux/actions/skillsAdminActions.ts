// Admin skills actions — perk system (FEAT-125)
import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
import type {
  SkillWithPerks,
  SkillPerkRead,
  DamageEntry,
  EffectEntry,
} from '../../components/SkillTreeView/types';

const BASE_URL = '/skills';

const extractError = (err: unknown, fallback: string): string => {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e.response?.data?.detail || e.message || fallback;
};

export interface AdminSkillListItem {
  id: number;
  name: string;
  skill_type: string;
  description: string | null;
  purchase_cost: number;
  min_level: number;
  skill_image: string | null;
  skill_image_preview?: string | null;
  // Category scoping — see AdminSkillsPage/skillCategories.ts
  class_limitations: string | null;
  subclass_limitations: string | null;
  is_mob_skill: boolean;
}

export const fetchSkills = createAsyncThunk<
  AdminSkillListItem[],
  // Category filter (class_id / subclass_key / mob); omitted means every skill.
  Record<string, string | number> | void,
  { rejectValue: string }
>(
  'skills/fetchSkills',
  async (params, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/admin/skills/`, {
        params: params || undefined,
      });
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки списка навыков'));
    }
  }
);

export const fetchSkillAdmin = createAsyncThunk<
  SkillWithPerks,
  number,
  { rejectValue: string }
>(
  'skills/fetchSkillAdmin',
  async (skillId, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/${skillId}`);
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки навыка'));
    }
  }
);

export interface PerkPayload {
  name: string;
  description: string | null;
  perk_image: string | null;
  delta_cost_energy: number | null;
  delta_cost_mana: number | null;
  delta_cooldown: number | null;
  delta_level_requirement: number | null;
  sort_order: number;
  damage_entries: SkillPerkRead['damage_entries'];
  effects: SkillPerkRead['effects'];
}

export const createPerk = createAsyncThunk<
  SkillPerkRead,
  { skillId: number; payload: PerkPayload },
  { rejectValue: string }
>(
  'skills/createPerk',
  async ({ skillId, payload }, { rejectWithValue }) => {
    try {
      const res = await axios.post(`${BASE_URL}/admin/skills/${skillId}/perks`, payload);
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка создания перка'));
    }
  }
);

export const updatePerk = createAsyncThunk<
  SkillPerkRead,
  { perkId: number; payload: PerkPayload },
  { rejectValue: string }
>(
  'skills/updatePerk',
  async ({ perkId, payload }, { rejectWithValue }) => {
    try {
      const res = await axios.put(`${BASE_URL}/admin/skill_perks/${perkId}`, payload);
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка обновления перка'));
    }
  }
);

export const deletePerk = createAsyncThunk<
  { perkId: number },
  number,
  { rejectValue: string }
>(
  'skills/deletePerk',
  async (perkId, { rejectWithValue }) => {
    try {
      await axios.delete(`${BASE_URL}/admin/skill_perks/${perkId}`);
      return { perkId };
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка удаления перка'));
    }
  }
);

// ------------------- Base stats (FEAT-125 follow-up) -------------------

export interface SkillBaseScalarsPayload {
  name: string;
  skill_type: string;
  description: string | null;
  class_limitations: string | null;
  subclass_limitations: string | null;
  is_mob_skill: boolean;
  race_limitations: string | null;
  subrace_limitations: string | null;
  min_level: number;
  purchase_cost: number;
  skill_image: string | null;
  cost_energy: number;
  cost_mana: number;
  cooldown: number;
  level_requirement: number;
}

export const updateSkillBase = createAsyncThunk<
  SkillBaseScalarsPayload & { id: number },
  { skillId: number; payload: SkillBaseScalarsPayload },
  { rejectValue: string }
>(
  'skills/updateSkillBase',
  async ({ skillId, payload }, { rejectWithValue }) => {
    try {
      const res = await axios.put(`${BASE_URL}/admin/skills/${skillId}`, payload);
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка сохранения базовых характеристик'));
    }
  }
);

export const createBaseDamage = createAsyncThunk<
  DamageEntry,
  { skillId: number; payload: DamageEntry },
  { rejectValue: string }
>(
  'skills/createBaseDamage',
  async ({ skillId, payload }, { rejectWithValue }) => {
    try {
      const res = await axios.post(`${BASE_URL}/admin/skills/${skillId}/base_damage`, payload);
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка добавления урона'));
    }
  }
);

export const updateBaseDamage = createAsyncThunk<
  DamageEntry,
  { skillId: number; damageId: number; payload: DamageEntry },
  { rejectValue: string }
>(
  'skills/updateBaseDamage',
  async ({ skillId, damageId, payload }, { rejectWithValue }) => {
    try {
      const res = await axios.put(
        `${BASE_URL}/admin/skills/${skillId}/base_damage/${damageId}`,
        payload
      );
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка обновления урона'));
    }
  }
);

export const deleteBaseDamage = createAsyncThunk<
  { damageId: number },
  { skillId: number; damageId: number },
  { rejectValue: string }
>(
  'skills/deleteBaseDamage',
  async ({ skillId, damageId }, { rejectWithValue }) => {
    try {
      await axios.delete(`${BASE_URL}/admin/skills/${skillId}/base_damage/${damageId}`);
      return { damageId };
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка удаления урона'));
    }
  }
);

export const createBaseEffect = createAsyncThunk<
  EffectEntry,
  { skillId: number; payload: EffectEntry },
  { rejectValue: string }
>(
  'skills/createBaseEffect',
  async ({ skillId, payload }, { rejectWithValue }) => {
    try {
      const res = await axios.post(`${BASE_URL}/admin/skills/${skillId}/base_effects`, payload);
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка добавления эффекта'));
    }
  }
);

export const updateBaseEffect = createAsyncThunk<
  EffectEntry,
  { skillId: number; effectId: number; payload: EffectEntry },
  { rejectValue: string }
>(
  'skills/updateBaseEffect',
  async ({ skillId, effectId, payload }, { rejectWithValue }) => {
    try {
      const res = await axios.put(
        `${BASE_URL}/admin/skills/${skillId}/base_effects/${effectId}`,
        payload
      );
      return res.data;
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка обновления эффекта'));
    }
  }
);

export const deleteBaseEffect = createAsyncThunk<
  { effectId: number },
  { skillId: number; effectId: number },
  { rejectValue: string }
>(
  'skills/deleteBaseEffect',
  async ({ skillId, effectId }, { rejectWithValue }) => {
    try {
      await axios.delete(`${BASE_URL}/admin/skills/${skillId}/base_effects/${effectId}`);
      return { effectId };
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка удаления эффекта'));
    }
  }
);

export const uploadSkillImage = createAsyncThunk<
  { skillId: number; image_url: string },
  { skillId: number; file: File },
  { rejectValue: string }
>(
  'skills/uploadSkillImage',
  async ({ skillId, file }, { rejectWithValue }) => {
    const formData = new FormData();
    formData.append('skill_id', String(skillId));
    formData.append('file', file);
    try {
      const res = await axios.post('/photo/change_skill_image', formData);
      return { skillId, image_url: res.data.image_url };
    } catch (err) {
      return rejectWithValue(extractError(err, 'Ошибка загрузки изображения навыка'));
    }
  }
);
