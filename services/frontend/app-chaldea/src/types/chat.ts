export type ChatChannel = 'general' | 'trade' | 'help';

export interface ChatMessageReply {
  id: number;
  username: string;
  content: string;
}

export interface ChatMessage {
  id: number;
  channel: ChatChannel;
  user_id: number;
  username: string;
  avatar: string | null;
  avatar_frame: string | null;
  chat_background: string | null;
  content: string;
  reply_to_id: number | null;
  reply_to: ChatMessageReply | null;
  created_at: string;
}

export interface ChatBanStatus {
  is_banned: boolean;
  reason?: string | null;
  expires_at?: string | null;
}

export interface ChatBanResponse {
  id: number;
  user_id: number;
  banned_by: number;
  reason: string | null;
  banned_at: string;
  expires_at: string | null;
}

export interface PaginatedChatMessages {
  items: ChatMessage[];
  total: number;
  page: number;
  page_size: number;
}
