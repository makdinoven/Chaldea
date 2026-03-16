import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { BASE_URL_DEFAULT } from "../../api/api";

const initialState = {
  id: null,
  email: null,
  username: null,
  character: null,
  role: null,
  avatar: null,
  status: "idle",
  error: null,
};

const userSlice = createSlice({
  name: "user",
  initialState,
  reducers: {
    logout(state) {
      state.id = null;
      state.email = null;
      state.username = null;
      state.role = null;
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
      .addCase(getMe.fulfilled, (state, action) => {
        const { id, email, username, role, avatar, character } = action.payload;
        state.status = "succeeded";
        state.id = id;
        state.email = email;
        state.username = username;
        state.role = role;
        state.avatar = avatar;
        state.character = character;
      })
      .addCase(getMe.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload;
        state.id = null;
        state.email = null;
        state.username = null;
        state.role = null;
        state.avatar = null;
      });
  },
});

export const { logout } = userSlice.actions;
export default userSlice.reducer;

export const getMe = createAsyncThunk("user/getMe", async (_, thunkAPI) => {
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

    const data = await response.json();
    return data;
  } catch (error) {
    localStorage.removeItem("accessToken");
    return thunkAPI.rejectWithValue("Failed to fetch user");
  }
});
