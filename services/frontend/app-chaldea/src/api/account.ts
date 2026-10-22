import axios from 'axios';
import { BASE_URL_DEFAULT } from './api';

/* The account's own credentials and sessions (user-service). */

export interface AccountSession {
  id: string;
  created_at: string;
  last_used_at: string | null;
  user_agent: string | null;
  /** The session this browser is using. */
  current: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export const fetchSessions = () =>
  axios.get<{ sessions: AccountSession[] }>(`${BASE_URL_DEFAULT}/users/me/sessions`);

export const revokeSession = (sessionId: string) =>
  axios.delete(`${BASE_URL_DEFAULT}/users/me/sessions/${sessionId}`);

export const revokeOtherSessions = () =>
  axios.post(`${BASE_URL_DEFAULT}/users/me/sessions/revoke-others`);

/** No interceptors: a logout that meets an already-ended session must not try to refresh. */
const bareAxios = axios.create();

/**
 * Ends this browser's session on the server. Identified by the refresh token,
 * so it works even after the access token has expired; the caller clears
 * storage right away.
 */
export const logoutSession = (refreshToken: string) =>
  bareAxios.post(`${BASE_URL_DEFAULT}/users/logout`, { refresh_token: refreshToken });

export const changePassword = (currentPassword: string, newPassword: string) =>
  axios.put<{ detail: string }>(`${BASE_URL_DEFAULT}/users/me/password`, {
    current_password: currentPassword,
    new_password: newPassword,
  });

export const changeEmail = (newEmail: string, password: string) =>
  axios.put<TokenPair>(`${BASE_URL_DEFAULT}/users/me/email`, {
    new_email: newEmail,
    password,
  });

/** The server's Russian reason when it gave one. */
export const accountError = (err: unknown, fallback: string): string => {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (err.response?.status === 422) return 'Проверьте введённые данные';
  }
  return fallback;
};
