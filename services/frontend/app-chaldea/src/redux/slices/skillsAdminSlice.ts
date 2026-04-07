// Admin skills slice — perk system (FEAT-125)
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
  fetchSkills,
  fetchSkillAdmin,
  createPerk,
  updatePerk,
  deletePerk,
  uploadSkillImage,
  type AdminSkillListItem,
} from '../actions/skillsAdminActions';
import type { SkillWithPerks } from '../../components/SkillTreeView/types';

interface SkillsAdminState {
  skillsList: AdminSkillListItem[];
  selectedSkill: SkillWithPerks | null;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
  updateStatus: 'idle' | 'loading' | 'succeeded' | 'failed';
}

const initialState: SkillsAdminState = {
  skillsList: [],
  selectedSkill: null,
  status: 'idle',
  error: null,
  updateStatus: 'idle',
};

const skillsSlice = createSlice({
  name: 'skills',
  initialState,
  reducers: {
    clearSelectedSkill(state) {
      state.selectedSkill = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSkills.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchSkills.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.skillsList = action.payload;
      })
      .addCase(fetchSkills.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload ?? 'Ошибка загрузки навыков';
      })

      .addCase(fetchSkillAdmin.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchSkillAdmin.fulfilled, (state, action: PayloadAction<SkillWithPerks>) => {
        state.status = 'succeeded';
        state.selectedSkill = action.payload;
      })
      .addCase(fetchSkillAdmin.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload ?? 'Ошибка загрузки навыка';
      })

      .addCase(createPerk.pending, (state) => {
        state.updateStatus = 'loading';
      })
      .addCase(createPerk.fulfilled, (state, action) => {
        state.updateStatus = 'succeeded';
        if (state.selectedSkill) {
          state.selectedSkill.perks = [...state.selectedSkill.perks, action.payload];
        }
      })
      .addCase(createPerk.rejected, (state, action) => {
        state.updateStatus = 'failed';
        state.error = action.payload ?? 'Ошибка создания перка';
      })

      .addCase(updatePerk.pending, (state) => {
        state.updateStatus = 'loading';
      })
      .addCase(updatePerk.fulfilled, (state, action) => {
        state.updateStatus = 'succeeded';
        if (state.selectedSkill) {
          state.selectedSkill.perks = state.selectedSkill.perks.map((p) =>
            p.id === action.payload.id ? action.payload : p
          );
        }
      })
      .addCase(updatePerk.rejected, (state, action) => {
        state.updateStatus = 'failed';
        state.error = action.payload ?? 'Ошибка обновления перка';
      })

      .addCase(deletePerk.fulfilled, (state, action) => {
        if (state.selectedSkill) {
          state.selectedSkill.perks = state.selectedSkill.perks.filter(
            (p) => p.id !== action.payload.perkId
          );
        }
      })
      .addCase(deletePerk.rejected, (state, action) => {
        state.error = action.payload ?? 'Ошибка удаления перка';
      })

      .addCase(uploadSkillImage.fulfilled, (state, action) => {
        const skill = state.skillsList.find((s) => s.id === action.payload.skillId);
        if (skill) skill.skill_image_preview = action.payload.image_url;
        if (state.selectedSkill && state.selectedSkill.id === action.payload.skillId) {
          state.selectedSkill.skill_image = action.payload.image_url;
        }
      });
  },
});

export const { clearSelectedSkill } = skillsSlice.actions;
export default skillsSlice.reducer;
