// ── Enums ──────────────────────────────────────────────────────────────────

export type TicketCategory = 'bug' | 'question' | 'suggestion' | 'complaint' | 'other';

export type TicketStatus = 'open' | 'in_progress' | 'awaiting_reply' | 'closed';

// ── Messages ───────────────────────────────────────────────────────────────

export interface TicketMessageItem {
  id: number;
  ticket_id: number;
  sender_id: number;
  sender_username: string;
  sender_avatar: string | null;
  content: string;
  attachment_url: string | null;
  is_admin: boolean;
  created_at: string;
}

export interface TicketLastMessage {
  id: number;
  sender_id: number;
  sender_username: string;
  content: string;
  attachment_url: string | null;
  is_admin: boolean;
  created_at: string;
}

// ── Ticket List Items ──────────────────────────────────────────────────────

export interface TicketListItem {
  id: number;
  user_id: number;
  subject: string;
  category: TicketCategory;
  status: TicketStatus;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  closed_by: number | null;
  last_message: TicketLastMessage | null;
  message_count: number;
}

export interface AdminTicketListItem extends TicketListItem {
  username: string;
}

// ── Ticket Detail ──────────────────────────────────────────────────────────

export interface TicketDetail {
  id: number;
  user_id: number;
  subject: string;
  category: TicketCategory;
  status: TicketStatus;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  closed_by: number | null;
  username: string;
}

// ── Request Payloads ───────────────────────────────────────────────────────

export interface CreateTicketPayload {
  subject: string;
  category: TicketCategory;
  content: string;
  attachment_url?: string | null;
}

export interface SendTicketMessagePayload {
  content: string;
  attachment_url?: string | null;
}

export interface ChangeTicketStatusPayload {
  status: TicketStatus;
}

// ── Paginated Responses ────────────────────────────────────────────────────

export interface PaginatedTickets {
  items: TicketListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface PaginatedAdminTickets {
  items: AdminTicketListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface PaginatedTicketMessages {
  items: TicketMessageItem[];
  total: number;
  page: number;
  page_size: number;
}

// ── Composite Responses ────────────────────────────────────────────────────

export interface TicketDetailResponse {
  ticket: TicketDetail;
  messages: PaginatedTicketMessages;
}

export interface TicketStatusChangeResponse {
  id: number;
  status: TicketStatus;
  closed_at: string | null;
  closed_by: number | null;
}

export interface AdminOpenCountResponse {
  open_count: number;
}

export interface TicketAttachmentResponse {
  image_url: string;
}
