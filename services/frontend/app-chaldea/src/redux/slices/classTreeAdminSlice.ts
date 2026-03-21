import { createSlice } from '@reduxjs/toolkit';
import type { ClassTreeAdminState } from '../../components/AdminClassTreeEditor/types';
import {
  fetchClassTrees,
  fetchFullClassTree,
  saveFullClassTree,
  createClassTree,
  deleteClassTree,
} from '../actions/classTreeAdminActions';

const initialState: ClassTreeAdminState = {
  treeList: [],
  selectedFullTree: null,
  status: 'idle',
  updateStatus: 'idle',
  error: null,
};

const classTreeAdminSlice = createSlice({
  name: 'classTreeAdmin',
  initialState,
  reducers: {
    clearSelectedTree(state) {
      state.selectedFullTree = null;
    },
    resetUpdateStatus(state) {
      state.updateStatus = 'idle';
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchClassTrees
      .addCase(fetchClassTrees.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchClassTrees.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.treeList = action.payload;
      })
      .addCase(fetchClassTrees.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload ?? 'Неизвестная ошибка';
      })

      // fetchFullClassTree
      .addCase(fetchFullClassTree.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchFullClassTree.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.selectedFullTree = action.payload;
      })
      .addCase(fetchFullClassTree.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload ?? 'Неизвестная ошибка';
      })

      // saveFullClassTree
      .addCase(saveFullClassTree.pending, (state) => {
        state.updateStatus = 'loading';
      })
      .addCase(saveFullClassTree.fulfilled, (state) => {
        state.updateStatus = 'succeeded';
      })
      .addCase(saveFullClassTree.rejected, (state, action) => {
        state.updateStatus = 'failed';
        state.error = action.payload ?? 'Неизвестная ошибка';
      })

      // createClassTree
      .addCase(createClassTree.fulfilled, (state, action) => {
        state.treeList.push(action.payload);
      })

      // deleteClassTree
      .addCase(deleteClassTree.fulfilled, (state, action) => {
        state.treeList = state.treeList.filter((t) => t.id !== action.payload);
        if (state.selectedFullTree?.id === action.payload) {
          state.selectedFullTree = null;
        }
      });
  },
});

export const { clearSelectedTree, resetUpdateStatus } = classTreeAdminSlice.actions;
export default classTreeAdminSlice.reducer;
