// src/features/skills/skillsActions.js
import { createAsyncThunk } from '@reduxjs/toolkit'
import axios from 'axios'
 const BASE_URL = 'http://localhost:8003/skills'

// 1) Получить список навыков
export const fetchSkills = createAsyncThunk(
  'skills/fetchSkills',
  async (_, { rejectWithValue }) => {
    try {
      const res = await axios.get(`${BASE_URL}/admin/skills`)
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
      return res.data
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message)
    }
  }
)

// 3) Обновить (PUT) полную структуру
export const updateSkillFullTree = createAsyncThunk(
  'skills/updateSkillFullTree',
  async ({ skillId, payload }, { rejectWithValue }) => {
    try {
      const res = await axios.put(`${BASE_URL}/admin/skills/${skillId}/full_tree`, payload)
      return res.data
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message)
    }
  }
)

