import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { BASE_URL_DEFAULT } from "../../api/api.js";

export const getMe = createAsyncThunk("user/getMe", async (_, thunkAPI) => {
  const token = localStorage.getItem("accessToken");

  if (!token) {
    return thunkAPI.rejectWithValue("No token");
  }
  {
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
    localStorage.setItem("username", data.username);
    return data;
  } catch (error) {
    localStorage.removeItem("accessToken");
    localStorage.removeItem("username");
    return thunkAPI.rejectWithValue("Failed to fetch user");
  }
});

const initialState = {
  id: null,
  email: null,
  username: localStorage.getItem("username") || null,
  role: null,
  avatar: null,
  status: "idle",
  error: null,
};

const userSlice = createSlice({
  name: "user",
  initialState,
  reducers: {
    setUser(state, action) {
      const { id, email, username, role, avatar } = action.payload;
      state.id = id;
      state.email = email;
      state.username = username;
      state.role = role;
      state.avatar = avatar;
      localStorage.setItem("username", username);
    },
    clearUser(state) {
      state.id = null;
      state.email = null;
      state.username = null;
      state.role = null;
      state.avatar = null;
      localStorage.removeItem("username");
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(getMe.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(getMe.fulfilled, (state, action) => {
        const { id, email, username, role, avatar } = action.payload;
        state.status = "succeeded";
        state.id = id;
        state.email = email;
        state.username = username;
        state.role = role;
        state.avatar = avatar;
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

export const { setUser, clearUser } = userSlice.actions;
export default userSlice.reducer;
