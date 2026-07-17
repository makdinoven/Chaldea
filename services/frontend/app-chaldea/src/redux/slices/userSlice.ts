import { createAsyncThunk, createSlice, PayloadAction } from "@reduxjs/toolkit";
import axios, { AxiosError } from "axios";
import { BASE_URL_DEFAULT } from "../../api/api";
import { getAccessToken } from "../../api/authToken";
import type { RootState } from "../store";

// --- Types ---

interface CharacterData {
  id: number;
  name: string;
  avatar?: string | null;
  level?: number | null;
  /** Character gold (FEAT-148); null/undefined until backend exposes it */
  currency_balance?: number | null;
  current_location?: {
    id: number;
    name: string;
  } | null;
  travel_cooldown_until?: string | null;
  [key: string]: unknown;
}

interface GetMeResponse {
  id: number;
  email: string;
  username: string;
  role: string | null;
  role_display_name: string | null;
  permissions: string[];
  avatar: string | null;
  character: CharacterData | null;
}

interface UserState {
  id: number | null;
  email: string | null;
  username: string | null;
  character: CharacterData | null;
  role: string | null;
  roleDisplayName: string | null;
  permissions: string[];
  avatar: string | null;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
  authInitialized: boolean;
}

const initialState: UserState = {
  id: null,
  email: null,
  username: null,
  character: null,
  role: null,
  roleDisplayName: null,
  permissions: [],
  avatar: null,
  status: "idle",
  error: null,
  authInitialized: false,
};

/**
 * getMe reject reasons (FEAT-150):
 * - 'unauthorized' — definitive 401 (the axios interceptor already tried a
 *   token refresh and it did not recover the session);
 * - 'transient' — network error / 5xx (e.g. deploy window). Tokens are KEPT:
 *   this thunk never touches localStorage — token deletion happens only in
 *   `handleAuthFailure()` (src/api/authToken.ts).
 */
type GetMeRejectReason = "unauthorized" | "transient";

/** Bounded retry for transient errors during deploy windows (section 3). */
const GET_ME_TRANSIENT_RETRIES = 2;
const GET_ME_RETRY_DELAY_MS = 1500;

const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

export const getMe = createAsyncThunk<GetMeResponse, void, { rejectValue: GetMeRejectReason }>(
  "user/getMe",
  async (_, thunkAPI) => {
    if (!getAccessToken()) {
      return thunkAPI.rejectWithValue("unauthorized");
    }

    // The default axios instance carries the auth interceptors
    // (Bearer header + refresh-on-401 + single retry) — see axiosSetup.ts.
    for (let attempt = 0; ; attempt++) {
      try {
        const { data } = await axios.get<GetMeResponse>(
          `${BASE_URL_DEFAULT}/users/me`
        );
        return data;
      } catch (err) {
        const status = (err as AxiosError).response?.status;

        if (status === 401) {
          // Refresh already failed (or was fatal) inside the interceptor.
          return thunkAPI.rejectWithValue("unauthorized");
        }

        const isTransient = status === undefined || status >= 500;
        if (isTransient && attempt < GET_ME_TRANSIENT_RETRIES) {
          await delay(GET_ME_RETRY_DELAY_MS);
          continue;
        }
        // Transient failure (or unexpected non-401 4xx): do NOT log out,
        // tokens survive — the next navigation/reload recovers the session.
        return thunkAPI.rejectWithValue("transient");
      }
    }
  }
);

const userSlice = createSlice({
  name: "user",
  initialState,
  reducers: {
    logout(state) {
      state.id = null;
      state.email = null;
      state.username = null;
      state.role = null;
      state.roleDisplayName = null;
      state.permissions = [];
      state.character = null;
      state.avatar = null;
    },
    setAuthInitialized(state) {
      state.authInitialized = true;
    },
    setCharacterAfterTeleport(
      state,
      action: PayloadAction<{
        new_location_id: number;
        new_location_name?: string | null;
        currency_balance: number;
      }>
    ) {
      if (!state.character) return;
      state.character.current_location = {
        id: action.payload.new_location_id,
        name: action.payload.new_location_name ?? state.character.current_location?.name ?? '',
      };
      (state.character as { currency_balance?: number }).currency_balance =
        action.payload.currency_balance;
    },
    setCharacterLocation(
      state,
      action: PayloadAction<{ id: number; name: string }>
    ) {
      if (!state.character) return;
      state.character.current_location = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(getMe.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(getMe.fulfilled, (state, action: PayloadAction<GetMeResponse>) => {
        const { id, email, username, role, role_display_name, permissions, avatar, character } = action.payload;
        state.status = "succeeded";
        state.authInitialized = true;
        state.id = id;
        state.email = email;
        state.username = username;
        state.role = role;
        state.roleDisplayName = role_display_name || null;
        state.permissions = permissions || [];
        state.avatar = avatar;
        state.character = character;
      })
      .addCase(getMe.rejected, (state, action) => {
        state.status = "failed";
        state.authInitialized = true;
        state.error = action.payload ?? null;
        state.id = null;
        state.email = null;
        state.username = null;
        state.role = null;
        state.roleDisplayName = null;
        state.permissions = [];
        state.avatar = null;
      });
  },
});

export const { logout, setAuthInitialized, setCharacterAfterTeleport, setCharacterLocation } = userSlice.actions;
export default userSlice.reducer;

// --- Selectors ---

export const selectPermissions = (state: RootState) => state.user.permissions;
export const selectRole = (state: RootState) => state.user.role;
export const selectRoleDisplayName = (state: RootState) => state.user.roleDisplayName;
export const selectAuthInitialized = (state: RootState) => state.user.authInitialized;
