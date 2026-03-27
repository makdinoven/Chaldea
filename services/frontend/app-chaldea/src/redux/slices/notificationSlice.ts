import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';
import { BASE_URL_DEFAULT } from '../../api/api';

// --- Types ---

export interface NotificationItem {
  id: number;
  user_id: number;
  message: string;
  status: 'unread' | 'read';
  created_at: string;
  link?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface NotificationState {
  items: NotificationItem[];
  unreadCount: number;
  sseConnected: boolean;
  dropdownOpen: boolean;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

const initialState: NotificationState = {
  items: [],
  unreadCount: 0,
  sseConnected: false,
  dropdownOpen: false,
  status: 'idle',
  error: null,
};

// --- Async Thunks ---

export const fetchUnreadNotifications = createAsyncThunk<
  PaginatedResponse<NotificationItem>,
  number,
  { rejectValue: string }
>(
  'notifications/fetchUnread',
  async (userId, thunkAPI) => {
    try {
      const token = localStorage.getItem('accessToken');
      const response = await axios.get<PaginatedResponse<NotificationItem>>(
        `${BASE_URL_DEFAULT}/notifications/${userId}/unread`,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        // 404 means no unread notifications — not an error
        return { items: [], total: 0, page: 1, page_size: 50 } as PaginatedResponse<NotificationItem>;
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить уведомления');
    }
  },
);

export const markNotificationsAsRead = createAsyncThunk<
  NotificationItem[],
  { userId: number; ids: number[] },
  { rejectValue: string }
>(
  'notifications/markAsRead',
  async ({ userId, ids }, thunkAPI) => {
    try {
      const token = localStorage.getItem('accessToken');
      const response = await axios.put<NotificationItem[]>(
        `${BASE_URL_DEFAULT}/notifications/${userId}/mark-as-read`,
        ids,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      return response.data;
    } catch (error: unknown) {
      return thunkAPI.rejectWithValue('Не удалось отметить уведомления как прочитанные');
    }
  },
);

export const markAllAsRead = createAsyncThunk<
  NotificationItem[],
  number,
  { rejectValue: string }
>(
  'notifications/markAllAsRead',
  async (userId, thunkAPI) => {
    try {
      const token = localStorage.getItem('accessToken');
      const response = await axios.put<NotificationItem[]>(
        `${BASE_URL_DEFAULT}/notifications/${userId}/mark-all-as-read`,
        null,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        // 404 means no unread notifications to mark
        return [] as NotificationItem[];
      }
      return thunkAPI.rejectWithValue('Не удалось отметить все уведомления как прочитанные');
    }
  },
);

// --- Slice ---

const notificationSlice = createSlice({
  name: 'notifications',
  initialState,
  reducers: {
    addNotification(state, action: PayloadAction<NotificationItem>) {
      state.items.unshift(action.payload);
      if (action.payload.status === 'unread') {
        state.unreadCount += 1;
      }
    },
    setSSEConnected(state, action: PayloadAction<boolean>) {
      state.sseConnected = action.payload;
    },
    toggleDropdown(state) {
      state.dropdownOpen = !state.dropdownOpen;
    },
    closeDropdown(state) {
      state.dropdownOpen = false;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchUnreadNotifications
      .addCase(fetchUnreadNotifications.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchUnreadNotifications.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.items = action.payload.items;
        state.unreadCount = action.payload.total;
      })
      .addCase(fetchUnreadNotifications.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // markNotificationsAsRead
      .addCase(markNotificationsAsRead.fulfilled, (state, action) => {
        const readIds = action.payload.map((n) => n.id);
        state.items = state.items.map((item) =>
          readIds.includes(item.id) ? { ...item, status: 'read' as const } : item,
        );
        state.unreadCount = state.items.filter((n) => n.status === 'unread').length;
      })
      .addCase(markNotificationsAsRead.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // markAllAsRead
      .addCase(markAllAsRead.fulfilled, (state) => {
        state.items = state.items.map((item) => ({ ...item, status: 'read' as const }));
        state.unreadCount = 0;
      })
      .addCase(markAllAsRead.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      });
  },
});

export const { addNotification, setSSEConnected, toggleDropdown, closeDropdown } =
  notificationSlice.actions;

// --- Selectors ---

export const selectNotifications = (state: { notifications: NotificationState }) =>
  state.notifications.items;
export const selectUnreadCount = (state: { notifications: NotificationState }) =>
  state.notifications.unreadCount;
export const selectDropdownOpen = (state: { notifications: NotificationState }) =>
  state.notifications.dropdownOpen;
export const selectSSEConnected = (state: { notifications: NotificationState }) =>
  state.notifications.sseConnected;

export default notificationSlice.reducer;
