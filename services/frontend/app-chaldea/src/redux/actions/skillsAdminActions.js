// src/features/skills/skillsActions.js
import { createAsyncThunk } from '@reduxjs/toolkit'
import axios from 'axios'
import {transformReceivedSkillTree} from "../../components/AdminSkillsPage/utils/transformSkillTree";
 const BASE_URL = '/skills'

// 1) Получить список навыков
export const fetchSkills = createAsyncThunk(
  'skills/fetchSkills',
  async (_, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/admin/skills/`)
      return res.data
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message)
    }
  }
)

// 2) Получить "полное дерево" навыка
export const fetchSkillFullTree = createAsyncThunk(
  'skills/fetchSkillFullTree',
  async (skillId, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/admin/skills/${skillId}/full_tree`)
      return transformReceivedSkillTree(res.data)
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message)
    }
  }
)

// 3) Обновить (PUT) полную структуру
export const updateSkillFullTree = createAsyncThunk(
  'skills/updateSkillFullTree',
  async ({ skillId, payload }, { rejectWithValue }) => {
    console.log(payload)
      try {
      const res = await axios.put(`${BASE_URL}/admin/skills/${skillId}/full_tree`, payload)
      return res.data
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message)
    }
  }
)

// Загрузка изображения навыка
export const uploadSkillImage = createAsyncThunk(
  'skills/uploadSkillImage',
  async ({ skillId, file }, { rejectWithValue }) => {
    const formData = new FormData();
    formData.append('skill_id', skillId);
    formData.append('file', file);
    try {
      const res = await axios.post('/photo/change_skill_image', formData);
      return { skillId, image_url: res.data.image_url };
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);

// Загрузка изображения ранга
export const uploadSkillRankImage = createAsyncThunk(
  'skills/uploadSkillRankImage',
  async ({ skillRankId, file }, { rejectWithValue }) => {
    const formData = new FormData();
    formData.append('skill_rank_id', skillRankId);
    formData.append('file', file);
    try {
      const res = await axios.post('/photo/change_skill_rank_image', formData);
      return { skillRankId, image_url: res.data.image_url };
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);
