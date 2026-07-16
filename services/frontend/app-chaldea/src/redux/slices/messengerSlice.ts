import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import { sendWsMessage } from '../../hooks/useWebSocket';
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
  WsConversationPinChangedData,
  WsTypingData,
  WsMessageReactionData,
} from '../../types/messenger';
import axios from 'axios';

// --- Ordering helpers (operate on the Immer draft) ---

/** Move an unpinned conversation to the top of the unpinned block (TG-style
 *  bump on new activity). Pinned conversations keep their position. */
const bumpConversationToTop = (
  conversations: ConversationListItem[],
  convId: number,
): void => {
  const idx = conversations.findIndex((c) => c.id === convId);
  if (idx === -1) return;
  const conv = conversations[idx];
  if (conv.is_pinned) return;
  conversations.splice(idx, 1);
  const firstUnpinned = conversations.findIndex((c) => !c.is_pinned);
  const insertAt = firstUnpinned === -1 ? conversations.length : firstUnpinned;
  conversations.splice(insertAt, 0, conv);
};

/** Apply a pin/unpin and reposition: pinned go to the very top, unpinned to the
 *  top of the unpinned block. */
const applyPinState = (
  conversations: ConversationListItem[],
  convId: number,
  pinned: boolean,
): void => {
  const idx = conversations.findIndex((c) => c.id === convId);
  if (idx === -1) return;
  const conv = conversations[idx];
  conv.is_pinned = pinned;
  conversations.splice(idx, 1);
  if (pinned) {
    conversations.unshift(conv);
  } else {
    const firstUnpinned = conversations.findIndex((c) => !c.is_pinned);
    const insertAt = firstUnpinned === -1 ? conversations.length : firstUnpinned;
    conversations.splice(insertAt, 0, conv);
  }
};

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
  // conversationId -> userId -> { username, ts (ms) } of who is currently typing
  typingByConversation: Record<number, Record<number, { username: string; ts: number }>>;
}

// How long a typing signal stays "fresh" before it is pruned (ms).
const TYPING_TTL_MS = 6000;

// Optimistic messages use unique negative ids (real ids are positive) until the
// server confirms them via messenger_send_ok (which echoes back the temp id).
let optimisticIdCounter = -1;
const nextOptimisticId = (): number => optimisticIdCounter--;

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
  typingByConversation: {},
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
      // `void` in ThunkArg (needed for zero-arg dispatch) is not erased by `??` — cast is safe: a void arg is undefined at runtime.
      const response = await messengerApi.getConversations(
        (params ?? {}) as { page?: number; page_size?: number },
      );
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
  void,
  { conversationId: number; content: string; reply_to_id?: number; image_url?: string | null },
  { state: RootState; rejectValue: string }
>(
  'messenger/sendMessage',
  async ({ conversationId, content, reply_to_id, image_url }, thunkAPI) => {
    const user = thunkAPI.getState().user;
    const tempId = nextOptimisticId();

    // Show the message immediately (optimistic). It is reconciled with the real
    // message on messenger_send_ok, or removed on messenger_error / send failure.
    const optimistic: PrivateMessage = {
      id: tempId,
      conversation_id: conversationId,
      sender_id: user.id ?? 0,
      sender_username: user.username ?? '',
      sender_avatar: user.avatar ?? null,
      sender_avatar_frame: null,
      sender_chat_background: null,
      content,
      image_url: image_url ?? null,
      created_at: new Date().toISOString(),
      is_deleted: false,
      edited_at: null,
      reply_to_id: reply_to_id ?? null,
      reply_to: null,
      status: 'sending',
    };
    thunkAPI.dispatch(addOptimisticMessage(optimistic));

    const sent = sendWsMessage('messenger_send', {
      conversation_id: conversationId,
      content,
      temp_id: tempId,
      ...(reply_to_id != null ? { reply_to_id } : {}),
      ...(image_url ? { image_url } : {}),
    });
    if (!sent) {
      thunkAPI.dispatch(removeOptimisticMessage({ tempId }));
      return thunkAPI.rejectWithValue('WebSocket не подключён. Попробуйте позже.');
    }
    // Fire-and-forget: state update happens via messenger_send_ok / private_message WS events
  },
);

export const deleteMessage = createAsyncThunk<
  void,
  number,
  { rejectValue: string }
>(
  'messenger/deleteMessage',
  async (messageId, thunkAPI) => {
    const sent = sendWsMessage('messenger_delete', { message_id: messageId });
    if (!sent) {
      return thunkAPI.rejectWithValue('WebSocket не подключён. Попробуйте позже.');
    }
    // Fire-and-forget: state update happens via private_message_deleted WS event
  },
);

export const editMessage = createAsyncThunk<
  void,
  { messageId: number; content: string },
  { rejectValue: string }
>(
  'messenger/editMessage',
  async ({ messageId, content }, thunkAPI) => {
    const sent = sendWsMessage('messenger_edit', { message_id: messageId, content });
    if (!sent) {
      return thunkAPI.rejectWithValue('WebSocket не подключён. Попробуйте позже.');
    }
    // Fire-and-forget: state update happens via private_message_edited WS event
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
  void,
  number,
  { rejectValue: string }
>(
  'messenger/markConversationRead',
  async (conversationId, thunkAPI) => {
    const sent = sendWsMessage('messenger_mark_read', { conversation_id: conversationId });
    if (!sent) {
      return thunkAPI.rejectWithValue('Не удалось отметить как прочитанное');
    }
    // Fire-and-forget: state update happens via conversation_read WS event
  },
);

export const sendTypingSignal = createAsyncThunk<void, number>(
  'messenger/sendTyping',
  async (conversationId) => {
    sendWsMessage('messenger_typing', { conversation_id: conversationId });
  },
);

export const sendReaction = createAsyncThunk<void, { messageId: number; emoji: string }>(
  'messenger/sendReaction',
  async ({ messageId, emoji }) => {
    sendWsMessage('messenger_react', { message_id: messageId, emoji });
  },
);

export const pinConversation = createAsyncThunk<
  { conversationId: number; pinned: boolean },
  { conversationId: number; pinned: boolean },
  { rejectValue: string }
>(
  'messenger/pinConversation',
  async ({ conversationId, pinned }, thunkAPI) => {
    try {
      if (pinned) {
        await messengerApi.pinConversation(conversationId);
      } else {
        await messengerApi.unpinConversation(conversationId);
      }
      return { conversationId, pinned };
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось изменить закрепление');
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
        // Bump the conversation up the list (TG-style live reorder).
        bumpConversationToTop(state.conversations, convId);
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
          avatar: data.avatar,
          created_at: new Date().toISOString(),
          participants: data.participants,
          last_message: null,
          unread_count: 0,
          is_pinned: false,
        };
        state.conversations.unshift(newConv);
      }
    },

    receiveConversationPinChanged(state, action: PayloadAction<WsConversationPinChangedData>) {
      const { conversation_id, is_pinned } = action.payload;
      applyPinState(state.conversations, conversation_id, is_pinned);
    },

    setConversationAvatar(state, action: PayloadAction<{ conversationId: number; avatar: string | null }>) {
      const conv = state.conversations.find((c) => c.id === action.payload.conversationId);
      if (conv) conv.avatar = action.payload.avatar;
    },

    /** Drop a conversation locally (e.g. the user was removed from a group). */
    removeConversation(state, action: PayloadAction<number>) {
      const id = action.payload;
      state.conversations = state.conversations.filter((c) => c.id !== id);
      if (state.activeConversationId === id) {
        state.activeConversationId = null;
      }
      delete state.messages[id];
      delete state.messagesPagination[id];
    },

    receiveReaction(state, action: PayloadAction<WsMessageReactionData & { is_self: boolean }>) {
      const { message_id, conversation_id, emoji, action: act, is_self } = action.payload;
      const arr = state.messages[conversation_id];
      if (!arr) return;
      const msg = arr.find((m) => m.id === message_id);
      if (!msg) return;
      if (!msg.reactions) msg.reactions = [];
      const existing = msg.reactions.find((r) => r.emoji === emoji);
      if (act === 'add') {
        if (existing) {
          existing.count += 1;
          if (is_self) existing.reacted_by_me = true;
        } else {
          msg.reactions.push({ emoji, count: 1, reacted_by_me: is_self });
        }
      } else if (existing) {
        existing.count -= 1;
        if (is_self) existing.reacted_by_me = false;
        if (existing.count <= 0) {
          msg.reactions = msg.reactions.filter((r) => r.emoji !== emoji);
        }
      }
    },

    receiveTyping(state, action: PayloadAction<WsTypingData>) {
      const { conversation_id, user_id, username } = action.payload;
      if (!state.typingByConversation[conversation_id]) {
        state.typingByConversation[conversation_id] = {};
      }
      state.typingByConversation[conversation_id][user_id] = {
        username: username ?? '',
        ts: Date.now(),
      };
    },

    /** Drop typing entries that have gone stale (no signal within the TTL). */
    pruneTyping(state) {
      const now = Date.now();
      for (const convId of Object.keys(state.typingByConversation)) {
        const conv = Number(convId);
        const users = state.typingByConversation[conv];
        for (const uid of Object.keys(users)) {
          if (now - users[Number(uid)].ts > TYPING_TTL_MS) {
            delete users[Number(uid)];
          }
        }
        if (Object.keys(users).length === 0) {
          delete state.typingByConversation[conv];
        }
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

    /** Add an optimistic (not-yet-confirmed) message to the top of the list. */
    addOptimisticMessage(state, action: PayloadAction<PrivateMessage>) {
      const msg = action.payload;
      const convId = msg.conversation_id;
      if (!state.messages[convId]) {
        state.messages[convId] = [];
      }
      state.messages[convId].unshift(msg);

      const conv = state.conversations.find((c) => c.id === convId);
      if (conv) {
        conv.last_message = {
          id: msg.id,
          sender_id: msg.sender_id,
          sender_username: msg.sender_username,
          content: msg.content,
          created_at: msg.created_at,
        };
        bumpConversationToTop(state.conversations, convId);
      }
    },

    /** Remove an optimistic message by its temp id (on send failure / error). */
    removeOptimisticMessage(state, action: PayloadAction<{ tempId: number }>) {
      const { tempId } = action.payload;
      for (const key of Object.keys(state.messages)) {
        const arr = state.messages[Number(key)];
        const idx = arr.findIndex((m) => m.id === tempId);
        if (idx !== -1) {
          arr.splice(idx, 1);
          return;
        }
      }
    },

    /** Handle messenger_send_ok — reconciles the optimistic message (matched by
     *  temp_id) with the confirmed server message. */
    receiveOwnSentMessage(state, action: PayloadAction<PrivateMessage & { temp_id?: number }>) {
      const { temp_id, ...rest } = action.payload;
      const msg: PrivateMessage = { ...rest, status: 'sent' };
      const convId = msg.conversation_id;

      if (!state.messages[convId]) {
        state.messages[convId] = [];
      }
      const arr = state.messages[convId];
      const alreadyReal = arr.some((m) => m.id === msg.id);

      if (temp_id != null) {
        const idx = arr.findIndex((m) => m.id === temp_id);
        if (idx !== -1) {
          // Replace the optimistic placeholder in place (or drop it if the real
          // message somehow already arrived, e.g. via another tab).
          if (alreadyReal) arr.splice(idx, 1);
          else arr[idx] = msg;
        } else if (!alreadyReal) {
          arr.unshift(msg);
        }
      } else if (!alreadyReal) {
        arr.unshift(msg);
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
        bumpConversationToTop(state.conversations, convId);
      }

      // Clear editing state on successful edit confirmation (if applicable)
      state.editingMessage = null;
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
        if (page <= 1) {
          // Fresh load — replace with the newest page.
          state.messages[conversationId] = items;
        } else {
          // Older page — messages are newest-first, so the older items belong
          // at the end. Append them (deduped) instead of replacing, otherwise
          // the newest messages are lost and can't be scrolled back to.
          const existing = state.messages[conversationId] ?? [];
          const seen = new Set(existing.map((m) => m.id));
          const olderUnique = items.filter((m) => !seen.has(m.id));
          state.messages[conversationId] = [...existing, ...olderUnique];
        }
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

      // sendMessage (fire-and-forget via WebSocket; state updated by messenger_send_ok)
      .addCase(sendMessage.pending, (state) => {
        state.error = null;
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // deleteMessage — handled via WebSocket event
      .addCase(deleteMessage.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // editMessage (fire-and-forget via WebSocket; state updated by private_message_edited)
      .addCase(editMessage.fulfilled, (state) => {
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
            avatar: conv.avatar,
            created_at: conv.created_at,
            participants: conv.participants,
            last_message: null,
            unread_count: 0,
            is_pinned: false,
          };
          state.conversations.unshift(newItem);
        }
        state.activeConversationId = conv.id;
      })
      .addCase(createConversation.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // markConversationRead (fire-and-forget via WebSocket; state updated by conversation_read)
      .addCase(markConversationRead.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // pinConversation
      .addCase(pinConversation.fulfilled, (state, action) => {
        applyPinState(state.conversations, action.payload.conversationId, action.payload.pinned);
      })
      .addCase(pinConversation.rejected, (state, action) => {
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
  receiveConversationPinChanged,
  setConversationAvatar,
  removeConversation,
  receiveReaction,
  receiveTyping,
  pruneTyping,
  addOptimisticMessage,
  removeOptimisticMessage,
  receiveOwnSentMessage,
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

/** Usernames currently typing in a conversation (fresh within the TTL). */
export const selectTypingUsernames =
  (conversationId: number | null) =>
  (state: RootState): string[] => {
    if (conversationId === null) return [];
    const users = state.messenger.typingByConversation[conversationId];
    if (!users) return [];
    const now = Date.now();
    return Object.values(users)
      .filter((u) => now - u.ts < TYPING_TTL_MS)
      .map((u) => u.username)
      .filter((name): name is string => Boolean(name));
  };

export default messengerSlice.reducer;
