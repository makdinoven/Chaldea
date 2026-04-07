// Admin skills actions — perk system (FEAT-125)
import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
import type { SkillWithPerks, SkillPerkRead } from '../../components/SkillTreeView/types';

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
}

export const fetchSkills = createAsyncThunk<
  AdminSkillListItem[],
  void,
  { rejectValue: string }
>(
  'skills/fetchSkills',
  async (_, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/admin/skills/`);
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
