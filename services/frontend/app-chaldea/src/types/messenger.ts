// ── Conversation & Participants ──────────────────────────────────────────────

export type ConversationType = 'direct' | 'group';

export interface ConversationParticipant {
  user_id: number;
  username: string;
  avatar: string | null;
  avatar_frame: string | null;
}

export interface Conversation {
  id: number;
  type: ConversationType;
  title: string | null;
  created_by: number;
  created_at: string;
  participants: ConversationParticipant[];
}

export interface LastMessage {
  id: number;
  sender_id: number;
  sender_username: string;
  content: string;
  created_at: string;
  edited_at?: string | null;
}

export interface ConversationListItem {
  id: number;
  type: ConversationType;
  title: string | null;
  created_at: string;
  participants: ConversationParticipant[];
  last_message: LastMessage | null;
  unread_count: number;
}

// ── Messages ────────────────────────────────────────────────────────────────

export interface ReplyPreview {
  id: number;
  sender_id: number;
  sender_username: string | null;
  sender_avatar: string | null;
  content: string;
  is_deleted: boolean;
}

export interface PrivateMessage {
  id: number;
  conversation_id: number;
  sender_id: number;
  sender_username: string;
  sender_avatar: string | null;
  sender_avatar_frame: string | null;
  sender_chat_background: string | null;
  content: string;
  created_at: string;
  is_deleted: boolean;
  edited_at?: string | null;
  reply_to_id?: number | null;
  reply_to?: ReplyPreview | null;
}

// ── Pagination ──────────────────────────────────────────────────────────────

export interface PaginatedConversations {
  items: ConversationListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface PaginatedMessages {
  items: PrivateMessage[];
  total: number;
  page: number;
  page_size: number;
}

// ── Payloads ────────────────────────────────────────────────────────────────

export interface CreateConversationPayload {
  type: ConversationType;
  participant_ids: number[];
  title: string | null;
}

export interface SendMessagePayload {
  content: string;
  reply_to_id?: number | null;
}

export interface EditMessagePayload {
  content: string;
}

export interface AddParticipantsPayload {
  user_ids: number[];
}

export interface UpdateMessagePrivacyPayload {
  message_privacy: MessagePrivacyValue;
}

// ── Blocking ────────────────────────────────────────────────────────────────

export interface BlockCheckResponse {
  is_blocked: boolean;
  blocked_by_me: boolean;
  blocked_by_them: boolean;
}

export interface UserBlockItem {
  id: number;
  user_id: number;
  blocked_user_id: number;
  blocked_username: string;
  created_at: string;
}

export interface UserBlockListResponse {
  items: UserBlockItem[];
}

export interface UserBlockCreateResponse {
  id: number;
  user_id: number;
  blocked_user_id: number;
  created_at: string;
}

// ── Privacy ─────────────────────────────────────────────────────────────────

export type MessagePrivacyValue = 'all' | 'friends' | 'nobody';

export interface MessagePrivacy {
  message_privacy: MessagePrivacyValue;
}

// ── Unread ──────────────────────────────────────────────────────────────────

export interface UnreadCountResponse {
  total_unread: number;
}

// ── Friend Check ────────────────────────────────────────────────────────────

export interface FriendCheckResponse {
  is_friend: boolean;
}

// ── Add Participants Response ───────────────────────────────────────────────

export interface AddParticipantsResponse {
  added: number[];
  skipped: number[];
}

// ── WebSocket Event Data ────────────────────────────────────────────────────

export interface WsPrivateMessageData {
  id: number;
  conversation_id: number;
  sender_id: number;
  sender_username: string;
  sender_avatar: string | null;
  sender_avatar_frame: string | null;
  sender_chat_background: string | null;
  content: string;
  created_at: string;
}

export interface WsPrivateMessageDeletedData {
  message_id: number;
  conversation_id: number;
}

export interface WsConversationCreatedData {
  id: number;
  type: ConversationType;
  title: string | null;
  participants: ConversationParticipant[];
}

export interface WsMessageEditedData {
  message_id: number;
  conversation_id: number;
  content: string;
  edited_at: string;
}

export interface WsConversationReadData {
  conversation_id: number;
}
