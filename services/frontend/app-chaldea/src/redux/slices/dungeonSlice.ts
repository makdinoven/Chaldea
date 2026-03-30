import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import toast from 'react-hot-toast';
import type { RootState } from '../store';
import * as api from '../../api/dungeons';
import type {
  DungeonAtLocation,
  SessionCreateResponse,
  SessionState,
  MoveResponse,
  FleeResponse,
  InteractResponse,
  LootDistribution,
  DistributeLootResponse,
  FinalizeResponse,
} from '../../api/dungeons';

// --- State ---

interface DungeonPlayerState {
  dungeonsAtLocation: DungeonAtLocation[];
  currentSession: SessionCreateResponse | null;
  sessionState: SessionState | null;
  lastMoveResponse: MoveResponse | null;
  lastFleeResponse: FleeResponse | null;
  lastInteractResponse: InteractResponse | null;
  lastDistributeResponse: DistributeLootResponse | null;
  lastFinalizeResponse: FinalizeResponse | null;
  loading: boolean;
  error: string | null;
  sessionLoading: boolean;
  stateLoading: boolean;
  moveLoading: boolean;
  fleeLoading: boolean;
  interactLoading: boolean;
  distributeLoading: boolean;
  finalizeLoading: boolean;
}

const initialState: DungeonPlayerState = {
  dungeonsAtLocation: [],
  currentSession: null,
  sessionState: null,
  lastMoveResponse: null,
  lastFleeResponse: null,
  lastInteractResponse: null,
  lastDistributeResponse: null,
  lastFinalizeResponse: null,
  loading: false,
  error: null,
  sessionLoading: false,
  stateLoading: false,
  moveLoading: false,
  fleeLoading: false,
  interactLoading: false,
  distributeLoading: false,
  finalizeLoading: false,
};

// --- Async Thunks ---

export const fetchDungeonsAtLocation = createAsyncThunk<
  DungeonAtLocation[],
  number,
  { rejectValue: string }
>(
  'dungeon/fetchDungeonsAtLocation',
  async (locationId, thunkAPI) => {
    try {
      return await api.fetchDungeonsAtLocation(locationId);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить список подземелий');
    }
  },
);

export const createSession = createAsyncThunk<
  SessionCreateResponse,
  { dungeonId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/createSession',
  async ({ dungeonId, characterId }, thunkAPI) => {
    try {
      const result = await api.createSession(dungeonId, characterId);
      toast.success('Группа создана');
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось создать группу');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const inviteMember = createAsyncThunk<
  SessionCreateResponse,
  { sessionId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/inviteMember',
  async ({ sessionId, characterId }, thunkAPI) => {
    try {
      const result = await api.inviteMember(sessionId, characterId);
      toast.success('Участник приглашён');
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось пригласить участника');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const leaveSession = createAsyncThunk<
  void,
  { sessionId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/leaveSession',
  async ({ sessionId, characterId }, thunkAPI) => {
    try {
      await api.leaveSession(sessionId, characterId);
      toast.success('Вы покинули группу');
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось покинуть группу');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const enterDungeon = createAsyncThunk<
  SessionState,
  { sessionId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/enterDungeon',
  async ({ sessionId, characterId }, thunkAPI) => {
    try {
      const result = await api.enterDungeon(sessionId, characterId);
      toast.success('Группа вошла в подземелье');
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось войти в подземелье');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const fetchSessionState = createAsyncThunk<
  SessionState,
  { sessionId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/fetchSessionState',
  async ({ sessionId, characterId }, thunkAPI) => {
    try {
      return await api.getSessionState(sessionId, characterId);
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить состояние подземелья');
    }
  },
);

export const moveDungeon = createAsyncThunk<
  MoveResponse,
  { sessionId: number; characterId: number; corridorId: number },
  { rejectValue: string }
>(
  'dungeon/moveDungeon',
  async ({ sessionId, characterId, corridorId }, thunkAPI) => {
    try {
      const result = await api.moveInDungeon(sessionId, characterId, corridorId);
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось переместиться');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const fleeDungeonThunk = createAsyncThunk<
  FleeResponse,
  { sessionId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/fleeDungeon',
  async ({ sessionId, characterId }, thunkAPI) => {
    try {
      const result = await api.fleeDungeon(sessionId, characterId);
      toast.success(result.message);
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось сбежать из подземелья');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const interactRoom = createAsyncThunk<
  InteractResponse,
  { sessionId: number; characterId: number; action: string; extraData?: Record<string, unknown> },
  { rejectValue: string }
>(
  'dungeon/interactRoom',
  async ({ sessionId, characterId, action, extraData }, thunkAPI) => {
    try {
      const result = await api.interactWithRoom(sessionId, characterId, action, extraData);
      if (result.message) {
        if (result.success) {
          toast.success(result.message);
        } else {
          toast.error(result.message);
        }
      }
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось выполнить действие');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const distributeLootThunk = createAsyncThunk<
  DistributeLootResponse,
  { sessionId: number; characterId: number; distributions: LootDistribution[] },
  { rejectValue: string }
>(
  'dungeon/distributeLoot',
  async ({ sessionId, characterId, distributions }, thunkAPI) => {
    try {
      const result = await api.distributeLoot(sessionId, characterId, distributions);
      toast.success(result.message || 'Добыча распределена');
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось распределить добычу');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const finalizeSessionThunk = createAsyncThunk<
  FinalizeResponse,
  { sessionId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/finalizeSession',
  async ({ sessionId, characterId }, thunkAPI) => {
    try {
      const result = await api.finalizeSession(sessionId, characterId);
      toast.success(result.message || 'Подземелье завершено');
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось завершить подземелье');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

// --- Helpers ---

function getErrorMessage(err: unknown, fallback: string): string {
  if (
    typeof err === 'object' &&
    err !== null &&
    'response' in err
  ) {
    const response = (err as { response?: { data?: { detail?: string } } }).response;
    if (response?.data?.detail) {
      return response.data.detail;
    }
  }
  return fallback;
}

// --- Slice ---

const dungeonSlice = createSlice({
  name: 'dungeon',
  initialState,
  reducers: {
    clearDungeonState(state) {
      state.currentSession = null;
      state.sessionState = null;
      state.lastMoveResponse = null;
      state.lastFleeResponse = null;
      state.lastInteractResponse = null;
      state.lastDistributeResponse = null;
      state.lastFinalizeResponse = null;
      state.error = null;
    },
    clearDistributeResponse(state) {
      state.lastDistributeResponse = null;
    },
    clearFinalizeResponse(state) {
      state.lastFinalizeResponse = null;
    },
    clearMoveResponse(state) {
      state.lastMoveResponse = null;
    },
    clearInteractResponse(state) {
      state.lastInteractResponse = null;
    },
    clearDungeonsAtLocation(state) {
      state.dungeonsAtLocation = [];
    },
    updateSessionFromWs(state, action: PayloadAction<SessionState>) {
      state.sessionState = action.payload;
    },
    updateSessionMembers(state, action: PayloadAction<SessionCreateResponse>) {
      state.currentSession = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      // --- Dungeons at location ---
      .addCase(fetchDungeonsAtLocation.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchDungeonsAtLocation.fulfilled, (state, action) => {
        state.loading = false;
        state.dungeonsAtLocation = action.payload;
      })
      .addCase(fetchDungeonsAtLocation.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // --- Create session ---
      .addCase(createSession.pending, (state) => {
        state.sessionLoading = true;
      })
      .addCase(createSession.fulfilled, (state, action) => {
        state.sessionLoading = false;
        state.currentSession = action.payload;
      })
      .addCase(createSession.rejected, (state) => {
        state.sessionLoading = false;
      })

      // --- Invite member ---
      .addCase(inviteMember.pending, (state) => {
        state.sessionLoading = true;
      })
      .addCase(inviteMember.fulfilled, (state, action) => {
        state.sessionLoading = false;
        state.currentSession = action.payload;
      })
      .addCase(inviteMember.rejected, (state) => {
        state.sessionLoading = false;
      })

      // --- Leave session ---
      .addCase(leaveSession.pending, (state) => {
        state.sessionLoading = true;
      })
      .addCase(leaveSession.fulfilled, (state) => {
        state.sessionLoading = false;
        state.currentSession = null;
        state.sessionState = null;
      })
      .addCase(leaveSession.rejected, (state) => {
        state.sessionLoading = false;
      })

      // --- Enter dungeon ---
      .addCase(enterDungeon.pending, (state) => {
        state.sessionLoading = true;
      })
      .addCase(enterDungeon.fulfilled, (state, action) => {
        state.sessionLoading = false;
        state.sessionState = action.payload;
      })
      .addCase(enterDungeon.rejected, (state) => {
        state.sessionLoading = false;
      })

      // --- Fetch session state ---
      .addCase(fetchSessionState.pending, (state) => {
        state.stateLoading = true;
      })
      .addCase(fetchSessionState.fulfilled, (state, action) => {
        state.stateLoading = false;
        state.sessionState = action.payload;
      })
      .addCase(fetchSessionState.rejected, (state, action) => {
        state.stateLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // --- Move ---
      .addCase(moveDungeon.pending, (state) => {
        state.moveLoading = true;
        state.lastMoveResponse = null;
      })
      .addCase(moveDungeon.fulfilled, (state, action) => {
        state.moveLoading = false;
        state.lastMoveResponse = action.payload;
        // Update current room in session state
        if (state.sessionState) {
          state.sessionState.current_room = action.payload.new_room;
          // If a battle started, update phase
          if (
            action.payload.room_event?.type === 'battle_started' ||
            action.payload.corridor_event?.type === 'battle'
          ) {
            state.sessionState.phase = 'in_battle';
            state.sessionState.active_battle_id =
              action.payload.room_event?.battle_id ??
              action.payload.corridor_event?.battle_id ??
              null;
          }
        }
      })
      .addCase(moveDungeon.rejected, (state) => {
        state.moveLoading = false;
      })

      // --- Flee ---
      .addCase(fleeDungeonThunk.pending, (state) => {
        state.fleeLoading = true;
      })
      .addCase(fleeDungeonThunk.fulfilled, (state, action) => {
        state.fleeLoading = false;
        state.lastFleeResponse = action.payload;
        if (state.sessionState) {
          state.sessionState.status = 'escaped';
          state.sessionState.phase = 'escaped';
        }
      })
      .addCase(fleeDungeonThunk.rejected, (state) => {
        state.fleeLoading = false;
      })

      // --- Interact ---
      .addCase(interactRoom.pending, (state) => {
        state.interactLoading = true;
        state.lastInteractResponse = null;
      })
      .addCase(interactRoom.fulfilled, (state, action) => {
        state.interactLoading = false;
        state.lastInteractResponse = action.payload;
      })
      .addCase(interactRoom.rejected, (state) => {
        state.interactLoading = false;
      })

      // --- Distribute Loot ---
      .addCase(distributeLootThunk.pending, (state) => {
        state.distributeLoading = true;
        state.lastDistributeResponse = null;
      })
      .addCase(distributeLootThunk.fulfilled, (state, action) => {
        state.distributeLoading = false;
        state.lastDistributeResponse = action.payload;
        // Update group inventory with remaining items
        if (state.sessionState) {
          state.sessionState.group_inventory = action.payload.remaining_inventory;
        }
      })
      .addCase(distributeLootThunk.rejected, (state) => {
        state.distributeLoading = false;
      })

      // --- Finalize Session ---
      .addCase(finalizeSessionThunk.pending, (state) => {
        state.finalizeLoading = true;
        state.lastFinalizeResponse = null;
      })
      .addCase(finalizeSessionThunk.fulfilled, (state, action) => {
        state.finalizeLoading = false;
        state.lastFinalizeResponse = action.payload;
        if (state.sessionState) {
          state.sessionState.phase = 'completed';
          state.sessionState.status = 'completed';
        }
      })
      .addCase(finalizeSessionThunk.rejected, (state) => {
        state.finalizeLoading = false;
      });
  },
});

export const {
  clearDungeonState,
  clearDungeonsAtLocation,
  clearMoveResponse,
  clearInteractResponse,
  clearDistributeResponse,
  clearFinalizeResponse,
  updateSessionFromWs,
  updateSessionMembers,
} = dungeonSlice.actions;

// --- Selectors ---

export const selectDungeonsAtLocation = (state: RootState) => state.dungeon.dungeonsAtLocation;
export const selectDungeonsLoading = (state: RootState) => state.dungeon.loading;
export const selectDungeonsError = (state: RootState) => state.dungeon.error;
export const selectCurrentSession = (state: RootState) => state.dungeon.currentSession;
export const selectSessionState = (state: RootState) => state.dungeon.sessionState;
export const selectSessionLoading = (state: RootState) => state.dungeon.sessionLoading;
export const selectStateLoading = (state: RootState) => state.dungeon.stateLoading;
export const selectMoveLoading = (state: RootState) => state.dungeon.moveLoading;
export const selectFleeLoading = (state: RootState) => state.dungeon.fleeLoading;
export const selectLastMoveResponse = (state: RootState) => state.dungeon.lastMoveResponse;
export const selectLastFleeResponse = (state: RootState) => state.dungeon.lastFleeResponse;
export const selectInteractLoading = (state: RootState) => state.dungeon.interactLoading;
export const selectLastInteractResponse = (state: RootState) => state.dungeon.lastInteractResponse;
export const selectDistributeLoading = (state: RootState) => state.dungeon.distributeLoading;
export const selectLastDistributeResponse = (state: RootState) => state.dungeon.lastDistributeResponse;
export const selectFinalizeLoading = (state: RootState) => state.dungeon.finalizeLoading;
export const selectLastFinalizeResponse = (state: RootState) => state.dungeon.lastFinalizeResponse;

export default dungeonSlice.reducer;
