import axios from 'axios';
import { BASE_URL_DEFAULT } from './api';

export interface SendMessagePayload {
  channel: 'general' | 'trade' | 'help';
  content: string;
  reply_to_id: number | null;
}

export interface GetMessagesParams {
  channel: 'general' | 'trade' | 'help';
  page?: number;
  page_size?: number;
}

export interface BanUserPayload {
  user_id: number;
  reason?: string | null;
  expires_at?: string | null;
}

export const sendMessage = (data: SendMessagePayload) =>
  axios.post(`${BASE_URL_DEFAULT}/notifications/chat/messages`, data);

export const getMessages = (params: GetMessagesParams) =>
  axios.get(`${BASE_URL_DEFAULT}/notifications/chat/messages`, { params });

export const deleteMessage = (messageId: number) =>
  axios.delete(`${BASE_URL_DEFAULT}/notifications/chat/messages/${messageId}`);

export const banUser = (data: BanUserPayload) =>
  axios.post(`${BASE_URL_DEFAULT}/notifications/chat/bans`, data);

export const unbanUser = (userId: number) =>
  axios.delete(`${BASE_URL_DEFAULT}/notifications/chat/bans/${userId}`);

export const checkBan = (userId: number) =>
  axios.get(`${BASE_URL_DEFAULT}/notifications/chat/bans/${userId}`);
