/**
 * Redux slice for the location resource gathering feature (FEAT-128).
 *
 * Holds:
 *  - `activeSession`: current character's in-flight gathering session (if any)
 *  - `lastFinishedSession`: one-shot result payload for toast on the UI
 *  - `currentNodeList`: cache of nodes returned by /client/details for the
 *    location currently displayed on screen (set by LocationPage)
 *  - `toolsCache`: per-category list populated by the tool-selection modal
 *  - `skills`: 3 gathering skills shown on the "Сбор" profile tab
 *  - admin node list for the AdminLocationsPage editor
 *
 * Errors from any thunk are stored in `state.error` so the consuming
 * component can render them in Russian (CLAUDE.md "Frontend Error Display").
 */
import {
  createSlice,
  createAsyncThunk,
  PayloadAction,
} from '@reduxjs/toolkit';
import type { RootState } from '../store';
import * as api from '../../api/gatheringApi';
import type {
  GatheringNode,
  GatheringTool,
  GatheringSkill,
  ToolCategory,
  ActiveGatheringResponse,
  StartGatheringRequest,
  StartGatheringResponse,
  CancelGatheringResponse,
  GatheringNodeAdminListItem,
  GatheringNodeAdminCreate,
  GatheringNodeAdminUpdate,
  ActiveGatheringSession,
  FinishedGatheringSummary,
} from '../../types/gathering';

// ── State ──────────────────────────────────────────────────────────────────

interface GatheringState {
  activeSession: ActiveGatheringSession | null;
  lastFinishedSession: FinishedGatheringSummary | null;
  currentNodeList: GatheringNode[];
  toolsCache: Partial<Record<ToolCategory, GatheringTool[]>>;
  skills: GatheringSkill[];
  adminNodes: GatheringNodeAdminListItem[];
  isStarting: boolean;
  isCancelling: boolean;
  isPolling: boolean;
  isLoadingTools: boolean;
  isLoadingSkills: boolean;
  isAdminLoading: boolean;
  error: string | null;
}

const initialState: GatheringState = {
  activeSession: null,
  lastFinishedSession: null,
  currentNodeList: [],
  toolsCache: {},
  skills: [],
  adminNodes: [],
  isStarting: false,
  isCancelling: false,
  isPolling: false,
  isLoadingTools: false,
  isLoadingSkills: false,
  isAdminLoading: false,
  error: null,
};

// ── Error helper ───────────────────────────────────────────────────────────

/**
 * Pulls a human-readable Russian message out of an axios error.
 * Falls back to the supplied default text. Mirrors the helper used in
 * dungeonSlice / craftingSlice etc.
 */
function getErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const response = (err as { response?: { data?: { detail?: unknown } } })
      .response;
    const detail = response?.data?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail)) {
      const merged = detail
        .map((e: { msg?: string }) => e.msg ?? '')
        .filter(Boolean)
        .join('; ');
      if (merged) return merged;
    }
  }
  return fallback;
}

// ── Async thunks ───────────────────────────────────────────────────────────

export const startGathering = createAsyncThunk<
  StartGatheringResponse,
  { locationId: number; nodeId: number; body: StartGatheringRequest },
  { rejectValue: string }
>(
  'gathering/start',
  async ({ locationId, nodeId, body }, thunkAPI) => {
    try {
      return await api.startGathering(locationId, nodeId, body);
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось начать добычу'),
      );
    }
  },
);

export const cancelGathering = createAsyncThunk<
  CancelGatheringResponse,
  { locationId: number; nodeId: number; characterId: number },
  { rejectValue: string }
>(
  'gathering/cancel',
  async ({ locationId, nodeId, characterId }, thunkAPI) => {
    try {
      return await api.cancelGathering(locationId, nodeId, characterId);
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось отменить добычу'),
      );
    }
  },
);

export const loadActiveGathering = createAsyncThunk<
  ActiveGatheringResponse,
  number,
  { rejectValue: string }
>(
  'gathering/loadActive',
  async (characterId, thunkAPI) => {
    try {
      return await api.getActiveGathering(characterId);
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось загрузить статус добычи'),
      );
    }
  },
);

export const loadGatheringSkills = createAsyncThunk<
  GatheringSkill[],
  number,
  { rejectValue: string }
>(
  'gathering/loadSkills',
  async (characterId, thunkAPI) => {
    try {
      return await api.getGatheringSkills(characterId);
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось загрузить навыки сбора'),
      );
    }
  },
);

export const loadGatheringTools = createAsyncThunk<
  { category: ToolCategory; tools: GatheringTool[] },
  { inventoryId: number; category: ToolCategory },
  { rejectValue: string }
>(
  'gathering/loadTools',
  async ({ inventoryId, category }, thunkAPI) => {
    try {
      const tools = await api.getToolsByCategory(inventoryId, category);
      return { category, tools };
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось загрузить инструменты'),
      );
    }
  },
);

// Admin thunks

export const adminListGatheringNodes = createAsyncThunk<
  GatheringNodeAdminListItem[],
  number,
  { rejectValue: string }
>(
  'gathering/adminList',
  async (locationId, thunkAPI) => {
    try {
      return await api.adminListNodes(locationId);
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось загрузить список нод'),
      );
    }
  },
);

export const adminCreateGatheringNode = createAsyncThunk<
  GatheringNodeAdminListItem,
  { locationId: number; body: GatheringNodeAdminCreate },
  { rejectValue: string }
>(
  'gathering/adminCreate',
  async ({ locationId, body }, thunkAPI) => {
    try {
      return await api.adminCreateNode(locationId, body);
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось создать ноду'),
      );
    }
  },
);

export const adminUpdateGatheringNode = createAsyncThunk<
  GatheringNodeAdminListItem,
  {
    locationId: number;
    nodeId: number;
    body: GatheringNodeAdminUpdate;
  },
  { rejectValue: string }
>(
  'gathering/adminUpdate',
  async ({ locationId, nodeId, body }, thunkAPI) => {
    try {
      return await api.adminUpdateNode(locationId, nodeId, body);
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось обновить ноду'),
      );
    }
  },
);

export const adminDeleteGatheringNode = createAsyncThunk<
  number, // returns the deleted nodeId
  { locationId: number; nodeId: number },
  { rejectValue: string }
>(
  'gathering/adminDelete',
  async ({ locationId, nodeId }, thunkAPI) => {
    try {
      await api.adminDeleteNode(locationId, nodeId);
      return nodeId;
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось удалить ноду'),
      );
    }
  },
);

export const adminRestoreGatheringNode = createAsyncThunk<
  GatheringNodeAdminListItem,
  { locationId: number; nodeId: number },
  { rejectValue: string }
>(
  'gathering/adminRestore',
  async ({ locationId, nodeId }, thunkAPI) => {
    try {
      return await api.adminRestoreNode(locationId, nodeId);
    } catch (err) {
      return thunkAPI.rejectWithValue(
        getErrorMessage(err, 'Не удалось восстановить ноду'),
      );
    }
  },
);

// ── Slice ──────────────────────────────────────────────────────────────────

const gatheringSlice = createSlice({
  name: 'gathering',
  initialState,
  reducers: {
    clearGatheringError(state) {
      state.error = null;
    },
    clearLastFinishedSession(state) {
      state.lastFinishedSession = null;
    },
    setCurrentNodeList(state, action: PayloadAction<GatheringNode[]>) {
      state.currentNodeList = action.payload;
    },
    clearCurrentNodeList(state) {
      state.currentNodeList = [];
    },
    clearToolsCache(state) {
      state.toolsCache = {};
    },
    clearActiveSession(state) {
      state.activeSession = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // ── start ──
      .addCase(startGathering.pending, (state) => {
        state.isStarting = true;
        state.error = null;
      })
      .addCase(
        startGathering.fulfilled,
        (state, action: PayloadAction<StartGatheringResponse>) => {
          state.isStarting = false;
          // Synthesise an ActiveGatheringSession from the start response so
          // the lock can engage immediately without waiting for a poll.
          const r = action.payload;
          state.activeSession = {
            active: true,
            session_id: r.session_id,
            node_id: r.node_id,
            // node_name / location_id / category are filled in by the next
            // /active_gathering poll; placeholders are safe defaults until then.
            node_name: '',
            location_id: 0,
            category: 'ore',
            started_at: r.started_at,
            complete_at: r.complete_at,
            now: r.started_at,
            remaining_seconds: r.effective_seconds,
            result_item_id: 0,
            stamina_paid: r.effective_stamina_paid,
            tool_inventory_item_id: r.tool_inventory_item_id,
          };
        },
      )
      .addCase(startGathering.rejected, (state, action) => {
        state.isStarting = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── cancel ──
      .addCase(cancelGathering.pending, (state) => {
        state.isCancelling = true;
        state.error = null;
      })
      .addCase(cancelGathering.fulfilled, (state) => {
        state.isCancelling = false;
        state.activeSession = null;
      })
      .addCase(cancelGathering.rejected, (state, action) => {
        state.isCancelling = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── poll active ──
      .addCase(loadActiveGathering.pending, (state) => {
        state.isPolling = true;
      })
      .addCase(
        loadActiveGathering.fulfilled,
        (state, action: PayloadAction<ActiveGatheringResponse>) => {
          state.isPolling = false;
          const payload = action.payload;
          if (payload.active === true) {
            state.activeSession = payload;
          } else {
            state.activeSession = null;
            const finished = payload.last_finished_session;
            if (finished) {
              state.lastFinishedSession = finished;
            }
          }
        },
      )
      .addCase(loadActiveGathering.rejected, (state, action) => {
        state.isPolling = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── skills ──
      .addCase(loadGatheringSkills.pending, (state) => {
        state.isLoadingSkills = true;
        state.error = null;
      })
      .addCase(loadGatheringSkills.fulfilled, (state, action) => {
        state.isLoadingSkills = false;
        state.skills = action.payload;
      })
      .addCase(loadGatheringSkills.rejected, (state, action) => {
        state.isLoadingSkills = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── tools ──
      .addCase(loadGatheringTools.pending, (state) => {
        state.isLoadingTools = true;
        state.error = null;
      })
      .addCase(loadGatheringTools.fulfilled, (state, action) => {
        state.isLoadingTools = false;
        state.toolsCache[action.payload.category] = action.payload.tools;
      })
      .addCase(loadGatheringTools.rejected, (state, action) => {
        state.isLoadingTools = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── admin: list ──
      .addCase(adminListGatheringNodes.pending, (state) => {
        state.isAdminLoading = true;
        state.error = null;
      })
      .addCase(adminListGatheringNodes.fulfilled, (state, action) => {
        state.isAdminLoading = false;
        state.adminNodes = action.payload;
      })
      .addCase(adminListGatheringNodes.rejected, (state, action) => {
        state.isAdminLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── admin: create ──
      .addCase(adminCreateGatheringNode.pending, (state) => {
        state.isAdminLoading = true;
        state.error = null;
      })
      .addCase(adminCreateGatheringNode.fulfilled, (state, action) => {
        state.isAdminLoading = false;
        state.adminNodes.push(action.payload);
      })
      .addCase(adminCreateGatheringNode.rejected, (state, action) => {
        state.isAdminLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── admin: update ──
      .addCase(adminUpdateGatheringNode.pending, (state) => {
        state.isAdminLoading = true;
        state.error = null;
      })
      .addCase(adminUpdateGatheringNode.fulfilled, (state, action) => {
        state.isAdminLoading = false;
        const idx = state.adminNodes.findIndex(
          (n) => n.id === action.payload.id,
        );
        if (idx >= 0) {
          state.adminNodes[idx] = action.payload;
        } else {
          state.adminNodes.push(action.payload);
        }
      })
      .addCase(adminUpdateGatheringNode.rejected, (state, action) => {
        state.isAdminLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── admin: delete ──
      .addCase(adminDeleteGatheringNode.pending, (state) => {
        state.isAdminLoading = true;
        state.error = null;
      })
      .addCase(adminDeleteGatheringNode.fulfilled, (state, action) => {
        state.isAdminLoading = false;
        state.adminNodes = state.adminNodes.filter(
          (n) => n.id !== action.payload,
        );
      })
      .addCase(adminDeleteGatheringNode.rejected, (state, action) => {
        state.isAdminLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // ── admin: restore ──
      .addCase(adminRestoreGatheringNode.pending, (state) => {
        state.isAdminLoading = true;
        state.error = null;
      })
      .addCase(adminRestoreGatheringNode.fulfilled, (state, action) => {
        state.isAdminLoading = false;
        const idx = state.adminNodes.findIndex(
          (n) => n.id === action.payload.id,
        );
        if (idx >= 0) {
          state.adminNodes[idx] = action.payload;
        }
      })
      .addCase(adminRestoreGatheringNode.rejected, (state, action) => {
        state.isAdminLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      });
  },
});

export const {
  clearGatheringError,
  clearLastFinishedSession,
  setCurrentNodeList,
  clearCurrentNodeList,
  clearToolsCache,
  clearActiveSession,
} = gatheringSlice.actions;

// ── Selectors ──────────────────────────────────────────────────────────────

export const selectActiveSession = (state: RootState) =>
  state.gathering.activeSession;
export const selectIsGathering = (state: RootState) =>
  state.gathering.activeSession !== null;
export const selectLastFinishedSession = (state: RootState) =>
  state.gathering.lastFinishedSession;
export const selectCurrentNodeList = (state: RootState) =>
  state.gathering.currentNodeList;
export const selectGatheringSkills = (state: RootState) =>
  state.gathering.skills;
export const selectToolsByCategory =
  (category: ToolCategory) => (state: RootState) =>
    state.gathering.toolsCache[category] ?? [];
export const selectAdminGatheringNodes = (state: RootState) =>
  state.gathering.adminNodes;
export const selectGatheringIsStarting = (state: RootState) =>
  state.gathering.isStarting;
export const selectGatheringIsCancelling = (state: RootState) =>
  state.gathering.isCancelling;
export const selectGatheringError = (state: RootState) =>
  state.gathering.error;
export const selectGatheringIsLoadingTools = (state: RootState) =>
  state.gathering.isLoadingTools;
export const selectGatheringIsLoadingSkills = (state: RootState) =>
  state.gathering.isLoadingSkills;
export const selectGatheringIsAdminLoading = (state: RootState) =>
  state.gathering.isAdminLoading;

export default gatheringSlice.reducer;
