import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import * as chatApi from '../../api/chatApi';
import type {
  ChatMessage,
  ChatChannel,
  ChatBanStatus,
  ChatBanResponse,
  PaginatedChatMessages,
} from '../../types/chat';
import axios from 'axios';

// --- State ---

interface ChannelPagination {
  total: number;
  page: number;
  pageSize: number;
}

export interface ChatState {
  messages: Record<string, ChatMessage[]>;
  activeChannel: ChatChannel;
  isOpen: boolean;
  replyingTo: ChatMessage | null;
  isLoading: boolean;
  error: string | null;
  isBanned: boolean;
  pagination: Record<string, ChannelPagination>;
}

const initialState: ChatState = {
  messages: {
    general: [],
    trade: [],
    help: [],
  },
  activeChannel: 'general',
  isOpen: false,
  replyingTo: null,
  isLoading: false,
  error: null,
  isBanned: false,
  pagination: {
    general: { total: 0, page: 1, pageSize: 50 },
    trade: { total: 0, page: 1, pageSize: 50 },
    help: { total: 0, page: 1, pageSize: 50 },
  },
};

// --- Async Thunks ---

export const fetchMessages = createAsyncThunk<
  PaginatedChatMessages & { channel: ChatChannel },
  { channel: ChatChannel; page?: number; pageSize?: number },
  { rejectValue: string }
>(
  'chat/fetchMessages',
  async ({ channel, page = 1, pageSize = 50 }, thunkAPI) => {
    try {
      const response = await chatApi.getMessages({ channel, page, page_size: pageSize });
      return { ...response.data, channel };
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить сообщения');
    }
  },
);

export const sendMessage = createAsyncThunk<
  ChatMessage,
  { channel: ChatChannel; content: string; reply_to_id: number | null },
  { rejectValue: string }
>(
  'chat/sendMessage',
  async (data, thunkAPI) => {
    try {
      const response = await chatApi.sendMessage(data);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 429) {
          return thunkAPI.rejectWithValue('Подождите перед отправкой следующего сообщения');
        }
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('Вы заблокированы в чате');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось отправить сообщение');
    }
  },
);

export const deleteMessage = createAsyncThunk<
  { messageId: number },
  number,
  { rejectValue: string }
>(
  'chat/deleteMessage',
  async (messageId, thunkAPI) => {
    try {
      await chatApi.deleteMessage(messageId);
      return { messageId };
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('Нет прав для удаления сообщения');
        }
        if (error.response?.status === 404) {
          return thunkAPI.rejectWithValue('Сообщение не найдено');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось удалить сообщение');
    }
  },
);

export const banUser = createAsyncThunk<
  ChatBanResponse,
  { user_id: number; reason?: string | null; expires_at?: string | null },
  { rejectValue: string }
>(
  'chat/banUser',
  async (data, thunkAPI) => {
    try {
      const response = await chatApi.banUser(data);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 409) {
          return thunkAPI.rejectWithValue('Пользователь уже заблокирован');
        }
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('Нет прав для блокировки');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось заблокировать пользователя');
    }
  },
);

export const unbanUser = createAsyncThunk<
  { userId: number },
  number,
  { rejectValue: string }
>(
  'chat/unbanUser',
  async (userId, thunkAPI) => {
    try {
      await chatApi.unbanUser(userId);
      return { userId };
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 404) {
          return thunkAPI.rejectWithValue('Блокировка не найдена');
        }
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('Нет прав для разблокировки');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось разблокировать пользователя');
    }
  },
);

export const checkBan = createAsyncThunk<
  ChatBanStatus,
  number,
  { rejectValue: string }
>(
  'chat/checkBan',
  async (userId, thunkAPI) => {
    try {
      const response = await chatApi.checkBan(userId);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось проверить статус блокировки');
    }
  },
);

// --- Slice ---

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    addMessage(state, action: PayloadAction<ChatMessage>) {
      const channel = action.payload.channel;
      if (!state.messages[channel]) {
        state.messages[channel] = [];
      }
      // Avoid duplicates
      const exists = state.messages[channel].some((m) => m.id === action.payload.id);
      if (!exists) {
        // Messages are newest-first, so prepend
        state.messages[channel].unshift(action.payload);
      }
    },
    removeMessage(state, action: PayloadAction<{ id: number; channel: ChatChannel }>) {
      const { id, channel } = action.payload;
      if (state.messages[channel]) {
        state.messages[channel] = state.messages[channel].filter((m) => m.id !== id);
      }
    },
    setActiveChannel(state, action: PayloadAction<ChatChannel>) {
      state.activeChannel = action.payload;
    },
    toggleChat(state) {
      state.isOpen = !state.isOpen;
    },
    setReplyingTo(state, action: PayloadAction<ChatMessage | null>) {
      state.replyingTo = action.payload;
    },
    clearReply(state) {
      state.replyingTo = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchMessages
      .addCase(fetchMessages.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchMessages.fulfilled, (state, action) => {
        const { channel, items, total, page, page_size } = action.payload;
        state.messages[channel] = items;
        state.pagination[channel] = { total, page, pageSize: page_size };
        state.isLoading = false;
      })
      .addCase(fetchMessages.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // sendMessage
      .addCase(sendMessage.pending, (state) => {
        state.error = null;
      })
      .addCase(sendMessage.fulfilled, (state, action) => {
        // Also add locally for immediate feedback (SSE will deduplicate)
        const channel = action.payload.channel;
        if (!state.messages[channel]) {
          state.messages[channel] = [];
        }
        const exists = state.messages[channel].some((m) => m.id === action.payload.id);
        if (!exists) {
          state.messages[channel].unshift(action.payload);
        }
        state.replyingTo = null;
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // deleteMessage
      .addCase(deleteMessage.fulfilled, (state, action) => {
        // Message removal will happen via SSE event
        void action.payload;
      })
      .addCase(deleteMessage.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // banUser
      .addCase(banUser.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // unbanUser
      .addCase(unbanUser.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })
      // checkBan — silent on error (non-critical, assume not banned)
      .addCase(checkBan.fulfilled, (state, action) => {
        state.isBanned = action.payload.is_banned;
      })
      .addCase(checkBan.rejected, () => {
        // Don't set error — ban check failure is not user-facing
      });
  },
});

export const {
  addMessage,
  removeMessage,
  setActiveChannel,
  toggleChat,
  setReplyingTo,
  clearReply,
} = chatSlice.actions;

// --- Selectors ---

export const selectChatMessages = (state: { chat: ChatState }) =>
  state.chat.messages;
export const selectActiveChannel = (state: { chat: ChatState }) =>
  state.chat.activeChannel;
export const selectChatIsOpen = (state: { chat: ChatState }) =>
  state.chat.isOpen;
export const selectReplyingTo = (state: { chat: ChatState }) =>
  state.chat.replyingTo;
export const selectChatIsLoading = (state: { chat: ChatState }) =>
  state.chat.isLoading;
export const selectChatError = (state: { chat: ChatState }) =>
  state.chat.error;
export const selectChatPagination = (state: { chat: ChatState }) =>
  state.chat.pagination;
export const selectChatIsBanned = (state: { chat: ChatState }) =>
  state.chat.isBanned;

export default chatSlice.reducer;
