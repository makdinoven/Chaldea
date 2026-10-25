import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import toast from 'react-hot-toast';
import type { RootState } from '../store';
import * as api from '../../api/dungeons';
import { getMe } from './userSlice';
import { playDungeonSound } from '../../utils/dungeonSounds';
import type {
  DungeonAtLocation,
  SessionCreateResponse,
  SessionState,
  MoveResponse,
  FleeResponse,
  InteractAction,
  InteractResponse,
  LootDistribution,
  DistributeLootResponse,
  FinalizeResponse,
  SkippedMember,
} from '../../api/dungeons';

// --- State ---

interface DungeonPlayerState {
  dungeonsAtLocation: DungeonAtLocation[];
  sessionState: SessionState | null;
  /** Squadmates left outside by the last party-run (who and why). */
  lastSkippedMembers: SkippedMember[];
  lastMoveResponse: MoveResponse | null;
  lastFleeResponse: FleeResponse | null;
  lastInteractResponse: InteractResponse | null;
  lastDistributeResponse: DistributeLootResponse | null;
  lastFinalizeResponse: FinalizeResponse | null;
  loading: boolean;
  error: string | null;
  /** Error of the last session-state load (shown on the session page). */
  stateError: string | null;
  /** The latest state load asked for, and when the last move landed: older loads are thrown away. */
  stateRequestId: string | null;
  freshAfter: number;
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
  sessionState: null,
  lastSkippedMembers: [],
  lastMoveResponse: null,
  lastFleeResponse: null,
  lastInteractResponse: null,
  lastDistributeResponse: null,
  lastFinalizeResponse: null,
  loading: false,
  error: null,
  stateError: null,
  stateRequestId: null,
  freshAfter: 0,
  sessionLoading: false,
  stateLoading: false,
  moveLoading: false,
  fleeLoading: false,
  interactLoading: false,
  distributeLoading: false,
  finalizeLoading: false,
};

// --- Helpers ---

const STATUS_FALLBACKS: Record<number, string> = {
  401: 'Сессия истекла — войдите снова',
  403: 'Действие недоступно',
  404: 'Не найдено',
  409: 'Действие уже выполнено или недоступно сейчас',
  502: 'Сервис временно недоступен. Попробуйте позже.',
  503: 'Сервис временно недоступен. Попробуйте позже.',
};

interface ErrorWithResponse {
  response?: { status?: number; data?: { detail?: unknown } };
}

const responseOf = (err: unknown): ErrorWithResponse['response'] | undefined =>
  typeof err === 'object' && err !== null && 'response' in err
    ? (err as ErrorWithResponse).response
    : undefined;

/** Russian message from a backend error: `detail` first, then the HTTP status. */
export function getErrorMessage(err: unknown, fallback: string): string {
  const response = responseOf(err);
  if (!response) {
    return 'Нет связи с сервером. Проверьте подключение.';
  }
  const detail = response.data?.detail;
  if (typeof detail === 'string' && detail) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const joined = detail.map((e: { msg?: string }) => e.msg ?? '').filter(Boolean).join('; ');
    if (joined) return joined;
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const msg = (detail as { message?: unknown }).message;
    if (typeof msg === 'string' && msg) return msg;
  }
  return (response.status && STATUS_FALLBACKS[response.status]) || fallback;
}

/** The server answered (4xx/5xx): our view of the run may be stale. */
const isServerAnswer = (err: unknown): boolean => !!responseOf(err)?.status;

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
    } catch (err: unknown) {
      return thunkAPI.rejectWithValue(getErrorMessage(err, 'Не удалось загрузить список подземелий'));
    }
  },
);

/** Solo entry. */
export const createSession = createAsyncThunk<
  SessionCreateResponse,
  { dungeonId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/createSession',
  async ({ dungeonId, characterId }, thunkAPI) => {
    try {
      const result = await api.createSession(dungeonId, characterId);
      toast.success('Вы вошли в подземелье');
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось войти в подземелье');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

/** Squad entry (leader + free squadmates on the location). */
export const partyRunThunk = createAsyncThunk<
  SessionState,
  { dungeonId: number; characterId: number },
  { rejectValue: string }
>(
  'dungeon/partyRun',
  async ({ dungeonId, characterId }, thunkAPI) => {
    try {
      const result = await api.partyRunDungeon(dungeonId, characterId);
      toast.success('Отряд вошёл в подземелье');
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось войти отрядом');
      toast.error(message);
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const fetchSessionState = createAsyncThunk<
  SessionState,
  { sessionId: number; characterId: number },
  { rejectValue: string; fulfilledMeta: { startedAt: number } }
>(
  'dungeon/fetchSessionState',
  async ({ sessionId, characterId }, thunkAPI) => {
    // When it was asked for: a load asked for before a move landed shows the party where it was.
    const startedAt = Date.now();
    try {
      return thunkAPI.fulfillWithValue(await api.getSessionState(sessionId, characterId), { startedAt });
    } catch (err: unknown) {
      return thunkAPI.rejectWithValue(getErrorMessage(err, 'Не удалось загрузить состояние подземелья'));
    }
  },
);

export const moveDungeon = createAsyncThunk<
  MoveResponse,
  { sessionId: number; characterId: number; corridorId: number },
  { rejectValue: string; fulfilledMeta: { at: number } }
>(
  'dungeon/moveDungeon',
  async ({ sessionId, characterId, corridorId }, thunkAPI) => {
    try {
      return thunkAPI.fulfillWithValue(await api.moveInDungeon(sessionId, characterId, corridorId), { at: Date.now() });
    } catch (err: unknown) {
      // A failed move spends nothing (e.g. a battle that could not start).
      const message = getErrorMessage(err, 'Не удалось переместиться');
      toast.error(message);
      if (isServerAnswer(err)) thunkAPI.dispatch(fetchSessionState({ sessionId, characterId }));
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
      thunkAPI.dispatch(fetchSessionState({ sessionId, characterId }));
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось сбежать из подземелья');
      toast.error(message);
      if (isServerAnswer(err)) thunkAPI.dispatch(fetchSessionState({ sessionId, characterId }));
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const interactRoom = createAsyncThunk<
  InteractResponse,
  { sessionId: number; characterId: number; action: InteractAction; extraData?: Record<string, unknown> },
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
          toast(result.message);
        }
      }
      if (result.success && action === 'open_chest') playDungeonSound('chest');
      if (result.success && action === 'merchant_buy') playDungeonSound('coins');
      if (result.success && action === 'use_portal') playDungeonSound('teleport');
      thunkAPI.dispatch(fetchSessionState({ sessionId, characterId }));
      // Events and the trader move the leader's gold: keep the header's purse honest.
      thunkAPI.dispatch(getMe());
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось выполнить действие');
      toast.error(message);
      if (isServerAnswer(err)) thunkAPI.dispatch(fetchSessionState({ sessionId, characterId }));
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
      if (result.failed.length > 0) {
        toast.error(result.message);
      } else {
        toast.success(result.message || 'Добыча распределена');
      }
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось распределить добычу');
      toast.error(message);
      if (isServerAnswer(err)) thunkAPI.dispatch(fetchSessionState({ sessionId, characterId }));
      return thunkAPI.rejectWithValue(message);
    }
  },
);

export const finalizeSessionThunk = createAsyncThunk<
  FinalizeResponse,
  { sessionId: number; characterId: number; force?: boolean },
  { rejectValue: string }
>(
  'dungeon/finalizeSession',
  async ({ sessionId, characterId, force = false }, thunkAPI) => {
    try {
      const result = await api.finalizeSession(sessionId, characterId, force);
      toast.success(result.message || 'Забег завершён');
      thunkAPI.dispatch(fetchSessionState({ sessionId, characterId }));
      return result;
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Не удалось завершить забег');
      toast.error(message);
      if (isServerAnswer(err)) thunkAPI.dispatch(fetchSessionState({ sessionId, characterId }));
      return thunkAPI.rejectWithValue(message);
    }
  },
);

// --- Slice ---

const dungeonSlice = createSlice({
  name: 'dungeon',
  initialState,
  reducers: {
    clearDungeonState(state) {
      state.sessionState = null;
      state.lastSkippedMembers = [];
      state.lastMoveResponse = null;
      state.lastFleeResponse = null;
      state.lastInteractResponse = null;
      state.lastDistributeResponse = null;
      state.lastFinalizeResponse = null;
      state.stateError = null;
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
    clearSkippedMembers(state) {
      state.lastSkippedMembers = [];
    },
    clearDungeonsAtLocation(state) {
      state.dungeonsAtLocation = [];
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

      // --- Solo entry ---
      .addCase(createSession.pending, (state) => {
        state.sessionLoading = true;
      })
      .addCase(createSession.fulfilled, (state) => {
        state.sessionLoading = false;
        state.lastSkippedMembers = [];
      })
      .addCase(createSession.rejected, (state) => {
        state.sessionLoading = false;
      })

      // --- Squad entry ---
      .addCase(partyRunThunk.pending, (state) => {
        state.sessionLoading = true;
      })
      .addCase(partyRunThunk.fulfilled, (state, action) => {
        state.sessionLoading = false;
        state.sessionState = action.payload;
        state.lastSkippedMembers = action.payload.skipped_members ?? [];
      })
      .addCase(partyRunThunk.rejected, (state) => {
        state.sessionLoading = false;
      })

      // --- Fetch session state ---
      .addCase(fetchSessionState.pending, (state, action) => {
        state.stateLoading = true;
        state.stateRequestId = action.meta.requestId;
      })
      .addCase(fetchSessionState.fulfilled, (state, action) => {
        // Only the latest load counts, and not one asked for before the last move landed.
        if (action.meta.requestId !== state.stateRequestId) return;
        state.stateLoading = false;
        if (action.meta.startedAt < state.freshAfter) return;
        state.stateError = null;
        state.sessionState = action.payload;
      })
      .addCase(fetchSessionState.rejected, (state, action) => {
        if (action.meta.requestId !== state.stateRequestId) return;
        state.stateLoading = false;
        state.stateError = action.payload ?? 'Произошла ошибка';
      })

      // --- Move ---
      .addCase(moveDungeon.pending, (state) => {
        state.moveLoading = true;
        state.lastMoveResponse = null;
      })
      .addCase(moveDungeon.fulfilled, (state, action) => {
        state.moveLoading = false;
        state.freshAfter = action.meta.at;
        state.lastMoveResponse = action.payload;
        if (state.sessionState) {
          if (action.payload.new_room) {
            state.sessionState.current_room = action.payload.new_room;
          }
          const battleId =
            (action.payload.room_event?.type === 'battle_started' ? action.payload.room_event.battle_id : null) ??
            (action.payload.corridor_event?.type === 'battle' ? action.payload.corridor_event.battle_id : null);
          if (battleId) {
            state.sessionState.phase = 'in_battle';
            state.sessionState.active_battle_id = battleId;
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
          const remaining = action.payload.items_remaining;
          state.sessionState.status = 'escaped';
          state.sessionState.phase = remaining.length > 0 ? 'distributing_loot' : 'finished';
          state.sessionState.finalized = remaining.length === 0;
          state.sessionState.group_inventory = remaining.map((i) => ({
            item_id: i.item_id,
            item_name: i.item_name,
            quantity: i.quantity,
          }));
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
          state.sessionState.phase = 'finished';
          state.sessionState.finalized = true;
          state.sessionState.group_inventory = [];
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
  clearSkippedMembers,
} = dungeonSlice.actions;

// --- Selectors ---

export const selectDungeonsAtLocation = (state: RootState) => state.dungeon.dungeonsAtLocation;
export const selectDungeonsLoading = (state: RootState) => state.dungeon.loading;
export const selectDungeonsError = (state: RootState) => state.dungeon.error;
export const selectSessionState = (state: RootState) => state.dungeon.sessionState;
export const selectSessionStateError = (state: RootState) => state.dungeon.stateError;
export const selectLastSkippedMembers = (state: RootState) => state.dungeon.lastSkippedMembers;
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
