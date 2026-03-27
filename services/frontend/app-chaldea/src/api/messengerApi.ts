import axios from 'axios';
import { BASE_URL_DEFAULT } from './api';
import type {
  Conversation,
  PaginatedConversations,
  PaginatedMessages,
  PrivateMessage,
  CreateConversationPayload,
  SendMessagePayload,
  EditMessagePayload,
  AddParticipantsPayload,
  AddParticipantsResponse,
  UnreadCountResponse,
  UserBlockCreateResponse,
  UserBlockListResponse,
  BlockCheckResponse,
  MessagePrivacy,
  UpdateMessagePrivacyPayload,
  FriendCheckResponse,
} from '../types/messenger';

// ── Messenger endpoints (notification-service) ─────────────────────────────

export const createConversation = (data: CreateConversationPayload) =>
  axios.post<Conversation>(`${BASE_URL_DEFAULT}/notifications/messenger/conversations`, data);

export const getConversations = (params: { page?: number; page_size?: number }) =>
  axios.get<PaginatedConversations>(`${BASE_URL_DEFAULT}/notifications/messenger/conversations`, { params });

export const getMessages = (conversationId: number, params: { page?: number; page_size?: number }) =>
  axios.get<PaginatedMessages>(
    `${BASE_URL_DEFAULT}/notifications/messenger/conversations/${conversationId}/messages`,
    { params },
  );

export const sendMessage = (conversationId: number, data: SendMessagePayload) =>
  axios.post<PrivateMessage>(
    `${BASE_URL_DEFAULT}/notifications/messenger/conversations/${conversationId}/messages`,
    data,
  );

export const deleteMessage = (messageId: number) =>
  axios.delete<{ detail: string }>(`${BASE_URL_DEFAULT}/notifications/messenger/messages/${messageId}`);

export const editMessage = (messageId: number, data: EditMessagePayload) =>
  axios.put<PrivateMessage>(`${BASE_URL_DEFAULT}/notifications/messenger/messages/${messageId}`, data);

export const markConversationRead = (conversationId: number) =>
  axios.put<{ detail: string }>(
    `${BASE_URL_DEFAULT}/notifications/messenger/conversations/${conversationId}/read`,
  );

export const getUnreadCount = () =>
  axios.get<UnreadCountResponse>(`${BASE_URL_DEFAULT}/notifications/messenger/unread-count`);

export const addParticipants = (conversationId: number, data: AddParticipantsPayload) =>
  axios.post<AddParticipantsResponse>(
    `${BASE_URL_DEFAULT}/notifications/messenger/conversations/${conversationId}/participants`,
    data,
  );

export const leaveConversation = (conversationId: number) =>
  axios.delete<{ detail: string }>(
    `${BASE_URL_DEFAULT}/notifications/messenger/conversations/${conversationId}/leave`,
  );

// ── Blocking endpoints (user-service) ──────────────────────────────────────

export const blockUser = (blockedUserId: number) =>
  axios.post<UserBlockCreateResponse>(`${BASE_URL_DEFAULT}/users/blocks/${blockedUserId}`);

export const unblockUser = (blockedUserId: number) =>
  axios.delete<{ detail: string }>(`${BASE_URL_DEFAULT}/users/blocks/${blockedUserId}`);

export const getBlocks = () =>
  axios.get<UserBlockListResponse>(`${BASE_URL_DEFAULT}/users/blocks`);

export const checkBlock = (otherUserId: number) =>
  axios.get<BlockCheckResponse>(`${BASE_URL_DEFAULT}/users/blocks/check/${otherUserId}`);

// ── Privacy endpoints (user-service) ───────────────────────────────────────

export const getMessagePrivacy = (userId: number) =>
  axios.get<MessagePrivacy>(`${BASE_URL_DEFAULT}/users/${userId}/message-privacy`);

export const updateMessagePrivacy = (data: UpdateMessagePrivacyPayload) =>
  axios.put<MessagePrivacy>(`${BASE_URL_DEFAULT}/users/me/message-privacy`, data);

// ── Friend check (user-service) ────────────────────────────────────────────

export const checkFriendship = (friendId: number) =>
  axios.get<FriendCheckResponse>(`${BASE_URL_DEFAULT}/users/friends/check/${friendId}`);
