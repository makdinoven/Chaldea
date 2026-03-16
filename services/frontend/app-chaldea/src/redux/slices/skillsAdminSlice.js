// src/features/skills/skillsSlice.js
import { createSlice } from '@reduxjs/toolkit'
import { fetchSkills, fetchSkillFullTree, updateSkillFullTree, uploadSkillImage, uploadSkillRankImage } from '../actions/skillsAdminActions'

const skillsSlice = createSlice({
  name: 'skills',
  initialState: {
    skillsList: [],
    selectedSkillTree: null,  // хранит полную структуру выбранного навыка
    status: 'idle',
    error: null,
    updateStatus: 'idle'
  },
  reducers: {
    clearSelectedSkillTree(state) {
      state.selectedSkillTree = null
    }
  },
  extraReducers: builder => {
    builder
      // fetchSkills
      .addCase(fetchSkills.pending, (state) => {
        state.status = 'loading'
      })
      .addCase(fetchSkills.fulfilled, (state, action) => {
        state.status = 'succeeded'
        state.skillsList = action.payload
      })
      .addCase(fetchSkills.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.payload
      })

      // fetchSkillFullTree
      .addCase(fetchSkillFullTree.pending, (state) => {
        state.status = 'loading'
      })
      .addCase(fetchSkillFullTree.fulfilled, (state, action) => {
        state.status = 'succeeded'
        state.selectedSkillTree = action.payload
      })
      .addCase(fetchSkillFullTree.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.payload
      })

      // updateSkillFullTree
      .addCase(updateSkillFullTree.pending, (state) => {
        state.updateStatus = 'loading'
      })
      .addCase(updateSkillFullTree.fulfilled, (state, action) => {
        state.updateStatus = 'succeeded'
      })
      .addCase(updateSkillFullTree.rejected, (state, action) => {
        state.updateStatus = 'failed'
        state.error = action.payload
      })
    .addCase(uploadSkillImage.fulfilled, (state, action) => {
        const skill = state.skillsList.find(s => s.id === action.payload.skillId);
        if (skill) skill.skill_image_preview = action.payload.image_url;
        if (state.selectedSkillTree && state.selectedSkillTree.id === action.payload.skillId) {
          state.selectedSkillTree.skill_image = action.payload.image_url;
        }
      })
        .addCase(uploadSkillRankImage.fulfilled, (state, action) => {
        const rankId = action.payload.skillRankId;
        const updateRankImage = (ranks) => {
          ranks.forEach(rank => {
            if (rank.id === rankId) rank.rank_image = action.payload.image_url;
            if (rank.children) updateRankImage(rank.children);
          });
        };
        if (state.selectedSkillTree && state.selectedSkillTree.ranks) {
          updateRankImage(state.selectedSkillTree.ranks);
        }
      })
  }
})

export const { clearSelectedSkillTree } = skillsSlice.actions
export default skillsSlice.reducer
