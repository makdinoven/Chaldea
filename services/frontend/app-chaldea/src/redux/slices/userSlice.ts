import { createAsyncThunk, createSlice, PayloadAction } from "@reduxjs/toolkit";
import { BASE_URL_DEFAULT } from "../../api/api";
import type { RootState } from "../store";

// --- Types ---

interface CharacterData {
  id: number;
  name: string;
  avatar?: string | null;
  current_location?: {
    id: number;
    name: string;
  } | null;
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
};

export const getMe = createAsyncThunk<GetMeResponse, void, { rejectValue: string }>(
  "user/getMe",
  async (_, thunkAPI) => {
    const token = localStorage.getItem("accessToken");

    if (!token) {
      return thunkAPI.rejectWithValue("No token");
    }
    try {
      const response = await fetch(`${BASE_URL_DEFAULT}/users/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error("Unauthorized");
      }

      const data: GetMeResponse = await response.json();
      return data;
    } catch {
      localStorage.removeItem("accessToken");
      return thunkAPI.rejectWithValue("Failed to fetch user");
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

export const { logout } = userSlice.actions;
export default userSlice.reducer;

// --- Selectors ---

export const selectPermissions = (state: RootState) => state.user.permissions;
export const selectRole = (state: RootState) => state.user.role;
export const selectRoleDisplayName = (state: RootState) => state.user.roleDisplayName;
