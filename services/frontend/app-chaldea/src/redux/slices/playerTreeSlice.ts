import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { PlayerTreeState } from '../../components/SkillTreeView/types';
import {
  fetchClassTree,
  fetchTreeProgress,
  chooseNode,
  purchaseSkill,
  upgradeSkill,
  resetTree,
  fetchSubclassTrees,
} from '../actions/playerTreeActions';

const initialState: PlayerTreeState = {
  tree: null,
  progress: null,
  selectedNodeId: null,
  loading: false,
  error: null,
  subclassTrees: [],
};

const playerTreeSlice = createSlice({
  name: 'playerTree',
  initialState,
  reducers: {
    setSelectedNodeId(state, action: PayloadAction<number | null>) {
      state.selectedNodeId = action.payload;
    },
    clearPlayerTree(state) {
      state.tree = null;
      state.progress = null;
      state.selectedNodeId = null;
      state.error = null;
      state.subclassTrees = [];
    },
    clearPlayerTreeError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchClassTree
      .addCase(fetchClassTree.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchClassTree.fulfilled, (state, action) => {
        state.loading = false;
        state.tree = action.payload;
      })
      .addCase(fetchClassTree.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Неизвестная ошибка';
      })

      // fetchTreeProgress
      .addCase(fetchTreeProgress.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchTreeProgress.fulfilled, (state, action) => {
        state.loading = false;
        state.progress = action.payload;
      })
      .addCase(fetchTreeProgress.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Неизвестная ошибка';
      })

      // chooseNode
      .addCase(chooseNode.pending, (state) => {
        state.error = null;
      })
      .addCase(chooseNode.rejected, (state, action) => {
        state.error = action.payload ?? 'Ошибка выбора узла';
      })

      // purchaseSkill
      .addCase(purchaseSkill.pending, (state) => {
        state.error = null;
      })
      .addCase(purchaseSkill.rejected, (state, action) => {
        state.error = action.payload ?? 'Ошибка покупки навыка';
      })

      // upgradeSkill
      .addCase(upgradeSkill.pending, (state) => {
        state.error = null;
      })
      .addCase(upgradeSkill.rejected, (state, action) => {
        state.error = action.payload ?? 'Ошибка улучшения навыка';
      })

      // resetTree
      .addCase(resetTree.pending, (state) => {
        state.error = null;
      })
      .addCase(resetTree.rejected, (state, action) => {
        state.error = action.payload ?? 'Ошибка сброса прогресса';
      })

      // fetchSubclassTrees
      .addCase(fetchSubclassTrees.fulfilled, (state, action) => {
        state.subclassTrees = action.payload;
      })
      .addCase(fetchSubclassTrees.rejected, (state, action) => {
        state.error = action.payload ?? 'Ошибка загрузки подклассов';
      });
  },
});

export const { setSelectedNodeId, clearPlayerTree, clearPlayerTreeError } =
  playerTreeSlice.actions;
export default playerTreeSlice.reducer;
