import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import * as messengerApi from '../../api/messengerApi';
import type {
  ConversationListItem,
  PrivateMessage,
  Conversation,
  PaginatedConversations,
  PaginatedMessages,
  UnreadCountResponse,
  AddParticipantsResponse,
  UserBlockItem,
  UserBlockListResponse,
  UserBlockCreateResponse,
  MessagePrivacy,
  WsPrivateMessageData,
  WsPrivateMessageDeletedData,
  WsMessageEditedData,
  WsConversationCreatedData,
  WsConversationReadData,
} from '../../types/messenger';
import axios from 'axios';

// --- State ---

interface PaginationInfo {
  page: number;
  totalPages: number;
}

export interface MessengerState {
  conversations: ConversationListItem[];
  activeConversationId: number | null;
  messages: Record<number, PrivateMessage[]>;
  totalUnread: number;
  isLoading: boolean;
  error: string | null;
  conversationsPagination: PaginationInfo;
  messagesPagination: Record<number, PaginationInfo>;
  blocks: UserBlockItem[];
  editingMessage: PrivateMessage | null;
  replyToMessage: PrivateMessage | null;
}

const initialState: MessengerState = {
  conversations: [],
  activeConversationId: null,
  messages: {},
  totalUnread: 0,
  isLoading: false,
  error: null,
  conversationsPagination: { page: 1, totalPages: 1 },
  messagesPagination: {},
  blocks: [],
  editingMessage: null,
  replyToMessage: null,
};

// --- Async Thunks ---

export const fetchConversations = createAsyncThunk<
  PaginatedConversations,
  { page?: number; page_size?: number } | void,
  { rejectValue: string }
>(
  'messenger/fetchConversations',
  async (params, thunkAPI) => {
    try {
      const response = await messengerApi.getConversations(params ?? {});
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить диалоги');
    }
  },
);

export const fetchMessages = createAsyncThunk<
  PaginatedMessages & { conversationId: number },
  { conversationId: number; page?: number; page_size?: number },
  { rejectValue: string }
>(
  'messenger/fetchMessages',
  async ({ conversationId, page, page_size }, thunkAPI) => {
    try {
      const response = await messengerApi.getMessages(conversationId, { page, page_size });
      return { ...response.data, conversationId };
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('Вы не являетесь участником этой беседы');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить сообщения');
    }
  },
);

export const sendMessage = createAsyncThunk<
  PrivateMessage,
  { conversationId: number; content: string; reply_to_id?: number },
  { rejectValue: string }
>(
  'messenger/sendMessage',
  async ({ conversationId, content, reply_to_id }, thunkAPI) => {
    try {
      const response = await messengerApi.sendMessage(conversationId, { content, reply_to_id });
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 429) {
          return thunkAPI.rejectWithValue('Подождите перед отправкой следующего сообщения');
        }
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('Вы не можете отправлять сообщения в эту беседу');
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
  'messenger/deleteMessage',
  async (messageId, thunkAPI) => {
    try {
      await messengerApi.deleteMessage(messageId);
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

export const editMessage = createAsyncThunk<
  PrivateMessage,
  { messageId: number; content: string },
  { rejectValue: string }
>(
  'messenger/editMessage',
  async ({ messageId, content }, thunkAPI) => {
    try {
      const response = await messengerApi.editMessage(messageId, { content });
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('Нет прав для редактирования сообщения');
        }
        if (error.response?.status === 404) {
          return thunkAPI.rejectWithValue('Сообщение не найдено');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось отредактировать сообщение');
    }
  },
);

export const createConversation = createAsyncThunk<
  Conversation,
  { type: 'direct' | 'group'; participant_ids: number[]; title: string | null },
  { rejectValue: string }
>(
  'messenger/createConversation',
  async (data, thunkAPI) => {
    try {
      const response = await messengerApi.createConversation(data);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue(
            error.response.data?.detail ?? 'Невозможно создать беседу с этим пользователем',
          );
        }
        if (error.response?.status === 400) {
          return thunkAPI.rejectWithValue(
            error.response.data?.detail ?? 'Неверные параметры для создания беседы',
          );
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось создать беседу');
    }
  },
);

export const markConversationRead = createAsyncThunk<
  { conversationId: number },
  number,
  { rejectValue: string }
>(
  'messenger/markConversationRead',
  async (conversationId, thunkAPI) => {
    try {
      await messengerApi.markConversationRead(conversationId);
      return { conversationId };
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось отметить как прочитанное');
    }
  },
);

export const fetchUnreadCount = createAsyncThunk<
  UnreadCountResponse,
  void,
  { rejectValue: string }
>(
  'messenger/fetchUnreadCount',
  async (_, thunkAPI) => {
    try {
      const response = await messengerApi.getUnreadCount();
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить счётчик непрочитанных');
    }
  },
);

export const addParticipants = createAsyncThunk<
  AddParticipantsResponse,
  { conversationId: number; user_ids: number[] },
  { rejectValue: string }
>(
  'messenger/addParticipants',
  async ({ conversationId, user_ids }, thunkAPI) => {
    try {
      const response = await messengerApi.addParticipants(conversationId, { user_ids });
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 400) {
          return thunkAPI.rejectWithValue('Нельзя добавить участников в личную беседу');
        }
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('Вы не являетесь участником этой беседы');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось добавить участников');
    }
  },
);

export const leaveConversation = createAsyncThunk<
  { conversationId: number },
  number,
  { rejectValue: string }
>(
  'messenger/leaveConversation',
  async (conversationId, thunkAPI) => {
    try {
      await messengerApi.leaveConversation(conversationId);
      return { conversationId };
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 400) {
          return thunkAPI.rejectWithValue('Нельзя покинуть личную беседу');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось покинуть беседу');
    }
  },
);

export const fetchBlocks = createAsyncThunk<
  UserBlockListResponse,
  void,
  { rejectValue: string }
>(
  'messenger/fetchBlocks',
  async (_, thunkAPI) => {
    try {
      const response = await messengerApi.getBlocks();
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить список заблокированных');
    }
  },
);

export const blockUser = createAsyncThunk<
  UserBlockCreateResponse,
  number,
  { rejectValue: string }
>(
  'messenger/blockUser',
  async (blockedUserId, thunkAPI) => {
    try {
      const response = await messengerApi.blockUser(blockedUserId);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 400) {
          return thunkAPI.rejectWithValue('Нельзя заблокировать самого себя');
        }
        if (error.response?.status === 409) {
          return thunkAPI.rejectWithValue('Пользователь уже заблокирован');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось заблокировать пользователя');
    }
  },
);

export const unblockUser = createAsyncThunk<
  { blockedUserId: number },
  number,
  { rejectValue: string }
>(
  'messenger/unblockUser',
  async (blockedUserId, thunkAPI) => {
    try {
      await messengerApi.unblockUser(blockedUserId);
      return { blockedUserId };
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 404) {
          return thunkAPI.rejectWithValue('Блокировка не найдена');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось разблокировать пользователя');
    }
  },
);

export const updateMessagePrivacy = createAsyncThunk<
  MessagePrivacy,
  { message_privacy: 'all' | 'friends' | 'nobody' },
  { rejectValue: string }
>(
  'messenger/updateMessagePrivacy',
  async (data, thunkAPI) => {
    try {
      const response = await messengerApi.updateMessagePrivacy(data);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось обновить настройки приватности');
    }
  },
);

// --- Slice ---

const messengerSlice = createSlice({
  name: 'messenger',
  initialState,
  reducers: {
    receivePrivateMessage(state, action: PayloadAction<WsPrivateMessageData>) {
      const msg = action.payload;
      const convId = msg.conversation_id;

      // Add message to messages list (avoid duplicates)
      if (!state.messages[convId]) {
        state.messages[convId] = [];
      }
      const exists = state.messages[convId].some((m) => m.id === msg.id);
      if (!exists) {
        const privateMessage: PrivateMessage = {
          ...msg,
          is_deleted: false,
        };
        // Messages are newest-first, so prepend
        state.messages[convId].unshift(privateMessage);
      }

      // Update last_message in conversation list
      const conv = state.conversations.find((c) => c.id === convId);
      if (conv) {
        conv.last_message = {
          id: msg.id,
          sender_id: msg.sender_id,
          sender_username: msg.sender_username,
          content: msg.content,
          created_at: msg.created_at,
        };
        // Increment unread if not the active conversation
        if (state.activeConversationId !== convId) {
          conv.unread_count += 1;
          state.totalUnread += 1;
        }
      }
    },

    receiveMessageDeleted(state, action: PayloadAction<WsPrivateMessageDeletedData>) {
      const { message_id, conversation_id } = action.payload;
      const msgs = state.messages[conversation_id];
      if (msgs) {
        const msg = msgs.find((m) => m.id === message_id);
        if (msg) {
          msg.is_deleted = true;
          msg.content = '';
        }
      }
    },

    receiveMessageEdited(state, action: PayloadAction<WsMessageEditedData>) {
      const { message_id, conversation_id, content, edited_at } = action.payload;
      const msgs = state.messages[conversation_id];
      if (msgs) {
        const msg = msgs.find((m) => m.id === message_id);
        if (msg) {
          msg.content = content;
          msg.edited_at = edited_at;
        }
      }
    },

    setEditingMessage(state, action: PayloadAction<PrivateMessage>) {
      state.editingMessage = action.payload;
      state.replyToMessage = null;
    },

    clearEditingMessage(state) {
      state.editingMessage = null;
    },

    setReplyToMessage(state, action: PayloadAction<PrivateMessage>) {
      state.replyToMessage = action.payload;
      state.editingMessage = null;
    },

    clearReplyToMessage(state) {
      state.replyToMessage = null;
    },

    receiveConversationCreated(state, action: PayloadAction<WsConversationCreatedData>) {
      const data = action.payload;
      // Avoid duplicates
      const exists = state.conversations.some((c) => c.id === data.id);
      if (!exists) {
        const newConv: ConversationListItem = {
          id: data.id,
          type: data.type,
          title: data.title,
          created_at: new Date().toISOString(),
          participants: data.participants,
          last_message: null,
          unread_count: 0,
        };
        state.conversations.unshift(newConv);
      }
    },

    receiveConversationRead(state, action: PayloadAction<WsConversationReadData>) {
      const { conversation_id } = action.payload;
      const conv = state.conversations.find((c) => c.id === conversation_id);
      if (conv) {
        state.totalUnread -= conv.unread_count;
        if (state.totalUnread < 0) state.totalUnread = 0;
        conv.unread_count = 0;
      }
    },

    setActiveConversation(state, action: PayloadAction<number>) {
      state.activeConversationId = action.payload;
    },

    clearActiveConversation(state) {
      state.activeConversationId = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchConversations
      .addCase(fetchConversations.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchConversations.fulfilled, (state, action) => {
        const { items, total, page, page_size } = action.payload;
        state.conversations = items;
        state.conversationsPagination = {
          page,
          totalPages: Math.max(1, Math.ceil(total / page_size)),
        };
        state.isLoading = false;
      })
      .addCase(fetchConversations.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // fetchMessages
      .addCase(fetchMessages.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchMessages.fulfilled, (state, action) => {
        const { conversationId, items, total, page, page_size } = action.payload;
        state.messages[conversationId] = items;
        state.messagesPagination[conversationId] = {
          page,
          totalPages: Math.max(1, Math.ceil(total / page_size)),
        };
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
        const msg = action.payload;
        const convId = msg.conversation_id;
        if (!state.messages[convId]) {
          state.messages[convId] = [];
        }
        // Avoid duplicates (WebSocket may deliver the same message)
        const exists = state.messages[convId].some((m) => m.id === msg.id);
        if (!exists) {
          state.messages[convId].unshift(msg);
        }
        // Update last_message in conversation list
        const conv = state.conversations.find((c) => c.id === convId);
        if (conv) {
          conv.last_message = {
            id: msg.id,
            sender_id: msg.sender_id,
            sender_username: msg.sender_username,
            content: msg.content,
            created_at: msg.created_at,
          };
        }
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // deleteMessage — handled via WebSocket event
      .addCase(deleteMessage.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // editMessage
      .addCase(editMessage.fulfilled, (state, action) => {
        const msg = action.payload;
        const convId = msg.conversation_id;
        const msgs = state.messages[convId];
        if (msgs) {
          const idx = msgs.findIndex((m) => m.id === msg.id);
          if (idx !== -1) {
            msgs[idx] = msg;
          }
        }
        state.editingMessage = null;
      })
      .addCase(editMessage.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // createConversation
      .addCase(createConversation.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(createConversation.fulfilled, (state, action) => {
        state.isLoading = false;
        const conv = action.payload;
        // Add to conversations list if not already present
        const exists = state.conversations.some((c) => c.id === conv.id);
        if (!exists) {
          const newItem: ConversationListItem = {
            id: conv.id,
            type: conv.type,
            title: conv.title,
            created_at: conv.created_at,
            participants: conv.participants,
            last_message: null,
            unread_count: 0,
          };
          state.conversations.unshift(newItem);
        }
        state.activeConversationId = conv.id;
      })
      .addCase(createConversation.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // markConversationRead
      .addCase(markConversationRead.fulfilled, (state, action) => {
        const { conversationId } = action.payload;
        const conv = state.conversations.find((c) => c.id === conversationId);
        if (conv) {
          state.totalUnread -= conv.unread_count;
          if (state.totalUnread < 0) state.totalUnread = 0;
          conv.unread_count = 0;
        }
      })
      .addCase(markConversationRead.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // fetchUnreadCount
      .addCase(fetchUnreadCount.fulfilled, (state, action) => {
        state.totalUnread = action.payload.total_unread;
      })
      // Silent on error — non-critical for unread count fetch
      .addCase(fetchUnreadCount.rejected, () => {})

      // addParticipants
      .addCase(addParticipants.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // leaveConversation
      .addCase(leaveConversation.fulfilled, (state, action) => {
        const { conversationId } = action.payload;
        state.conversations = state.conversations.filter((c) => c.id !== conversationId);
        if (state.activeConversationId === conversationId) {
          state.activeConversationId = null;
        }
        delete state.messages[conversationId];
        delete state.messagesPagination[conversationId];
      })
      .addCase(leaveConversation.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // fetchBlocks
      .addCase(fetchBlocks.fulfilled, (state, action) => {
        state.blocks = action.payload.items;
      })
      .addCase(fetchBlocks.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // blockUser
      .addCase(blockUser.fulfilled, (state, action) => {
        const block = action.payload;
        state.blocks.push({
          id: block.id,
          user_id: block.user_id,
          blocked_user_id: block.blocked_user_id,
          blocked_username: '',
          created_at: block.created_at,
        });
      })
      .addCase(blockUser.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // unblockUser
      .addCase(unblockUser.fulfilled, (state, action) => {
        const { blockedUserId } = action.payload;
        state.blocks = state.blocks.filter((b) => b.blocked_user_id !== blockedUserId);
      })
      .addCase(unblockUser.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // updateMessagePrivacy — silent on success (UI handles feedback)
      .addCase(updateMessagePrivacy.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      });
  },
});

export const {
  receivePrivateMessage,
  receiveMessageDeleted,
  receiveMessageEdited,
  receiveConversationCreated,
  receiveConversationRead,
  setActiveConversation,
  clearActiveConversation,
  setEditingMessage,
  clearEditingMessage,
  setReplyToMessage,
  clearReplyToMessage,
} = messengerSlice.actions;

// --- Selectors ---

export const selectConversations = (state: RootState) =>
  state.messenger.conversations;

export const selectActiveConversation = (state: RootState) => {
  const id = state.messenger.activeConversationId;
  if (id === null) return null;
  return state.messenger.conversations.find((c) => c.id === id) ?? null;
};

export const selectActiveMessages = (state: RootState) => {
  const id = state.messenger.activeConversationId;
  if (id === null) return [];
  return state.messenger.messages[id] ?? [];
};

export const selectTotalUnread = (state: RootState) =>
  state.messenger.totalUnread;

export const selectMessengerLoading = (state: RootState) =>
  state.messenger.isLoading;

export const selectMessengerError = (state: RootState) =>
  state.messenger.error;

export const selectActiveConversationId = (state: RootState) =>
  state.messenger.activeConversationId;

export const selectConversationsPagination = (state: RootState) =>
  state.messenger.conversationsPagination;

export const selectMessagesPagination = (state: RootState) =>
  state.messenger.messagesPagination;

export const selectBlocks = (state: RootState) =>
  state.messenger.blocks;

export const selectEditingMessage = (state: RootState) =>
  state.messenger.editingMessage;

export const selectReplyToMessage = (state: RootState) =>
  state.messenger.replyToMessage;

export default messengerSlice.reducer;
