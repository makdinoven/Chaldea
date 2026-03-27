import axios from 'axios';
import { BASE_URL_DEFAULT } from './api';
import type {
  TicketListItem,
  TicketDetailResponse,
  TicketMessageItem,
  TicketStatusChangeResponse,
  PaginatedTickets,
  PaginatedAdminTickets,
  AdminOpenCountResponse,
  TicketAttachmentResponse,
  CreateTicketPayload,
  SendTicketMessagePayload,
  TicketCategory,
  TicketStatus,
} from '../types/ticket';

// ── User endpoints ─────────────────────────────────────────────────────────

export const createTicket = (data: CreateTicketPayload) =>
  axios.post<TicketListItem>(`${BASE_URL_DEFAULT}/notifications/tickets`, data);

export const getMyTickets = (params: { page?: number; status?: TicketStatus }) =>
  axios.get<PaginatedTickets>(`${BASE_URL_DEFAULT}/notifications/tickets`, { params });

export const getTicketDetail = (ticketId: number, params?: { page?: number; page_size?: number }) =>
  axios.get<TicketDetailResponse>(`${BASE_URL_DEFAULT}/notifications/tickets/${ticketId}`, { params });

export const sendTicketMessage = (ticketId: number, data: SendTicketMessagePayload) =>
  axios.post<TicketMessageItem>(
    `${BASE_URL_DEFAULT}/notifications/tickets/${ticketId}/messages`,
    data,
  );

// ── Admin endpoints ────────────────────────────────────────────────────────

export const changeTicketStatus = (ticketId: number, status: TicketStatus) =>
  axios.patch<TicketStatusChangeResponse>(
    `${BASE_URL_DEFAULT}/notifications/tickets/${ticketId}/status`,
    { status },
  );

export const getAdminTickets = (params: {
  page?: number;
  status?: TicketStatus;
  category?: TicketCategory;
}) =>
  axios.get<PaginatedAdminTickets>(`${BASE_URL_DEFAULT}/notifications/tickets/admin/list`, {
    params,
  });

export const getAdminOpenCount = () =>
  axios.get<AdminOpenCountResponse>(`${BASE_URL_DEFAULT}/notifications/tickets/admin/count`);

// ── Attachment upload (photo-service) ──────────────────────────────────────

export const uploadTicketAttachment = (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return axios.post<TicketAttachmentResponse>(
    `${BASE_URL_DEFAULT}/photo/upload_ticket_attachment`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
};
