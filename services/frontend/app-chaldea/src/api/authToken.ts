/**
 * Single source of truth for auth tokens and the refresh flow (FEAT-150).
 *
 * - localStorage wrappers (`getAccessToken` / `getRefreshToken` / `setTokens`
 *   / `clearTokens`) — keys unchanged (`accessToken`, `refreshToken`).
 * - `refreshAccessToken()` — single-flight refresh: N concurrent callers
 *   share one in-flight `POST /users/refresh`; includes a multi-tab
 *   short-circuit (another tab may have refreshed already).
 * - `handleAuthFailure()` — the ONLY place in the app where tokens are
 *   deleted: clears storage, shows a Russian toast and redirects to login.
 */
import axios, { AxiosError } from 'axios';
import toast from 'react-hot-toast';

const ACCESS_TOKEN_KEY = 'accessToken';
const REFRESH_TOKEN_KEY = 'refreshToken';

export type RefreshResult =
  | { status: 'ok'; token: string }
  | { status: 'fatal' }
  | { status: 'transient' };

interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// ── localStorage wrappers ──────────────────────────────────────────────────

export const getAccessToken = (): string | null =>
  localStorage.getItem(ACCESS_TOKEN_KEY);

export const getRefreshToken = (): string | null =>
  localStorage.getItem(REFRESH_TOKEN_KEY);

export const setTokens = (accessToken: string, refreshToken: string): void => {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
};

export const clearTokens = (): void => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
};

// ── Refresh flow ───────────────────────────────────────────────────────────

/**
 * Bare axios instance created with `axios.create()`: no interceptors are ever
 * attached to it, so the refresh call itself can never recurse into the
 * refresh-on-401 interceptor.
 */
const bareAxios = axios.create();

/** Statuses meaning the refresh token itself is definitively rejected. */
const FATAL_REFRESH_STATUSES = [401, 403, 422];

let refreshInFlight: Promise<RefreshResult> | null = null;

const doRefresh = async (
  failedAccessToken?: string | null,
): Promise<RefreshResult> => {
  // Multi-tab short-circuit: if the access token in localStorage differs from
  // the one the failed request used, another tab already refreshed — reuse it
  // without a network call.
  const currentToken = getAccessToken();
  if (
    currentToken &&
    failedAccessToken != null &&
    currentToken !== failedAccessToken
  ) {
    return { status: 'ok', token: currentToken };
  }

  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return { status: 'fatal' };
  }

  try {
    const { data } = await bareAxios.post<RefreshResponse>('/users/refresh', {
      refresh_token: refreshToken,
    });
    setTokens(data.access_token, data.refresh_token);
    return { status: 'ok', token: data.access_token };
  } catch (err) {
    const responseStatus = (err as AxiosError).response?.status;
    if (
      responseStatus !== undefined &&
      FATAL_REFRESH_STATUSES.includes(responseStatus)
    ) {
      // The refresh token is invalid/expired — session cannot be recovered.
      return { status: 'fatal' };
    }
    // Network error / 5xx — the server may be restarting (deploy window).
    // Tokens are NOT cleared; the caller keeps its session for a later retry.
    return { status: 'transient' };
  }
};

/**
 * Single-flight refresh: concurrent callers (N parallel 401s) await the same
 * in-flight request; exactly one `POST /users/refresh` hits the network.
 *
 * @param failedAccessToken — the access token the failed request was sent
 *   with; used for the multi-tab short-circuit comparison.
 */
export const refreshAccessToken = (
  failedAccessToken?: string | null,
): Promise<RefreshResult> => {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh(failedAccessToken).finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
};

// ── Auth failure (the ONLY place tokens are deleted) ──────────────────────

let authFailureHandled = false;

/**
 * Definitive auth failure: clear tokens, notify the user (in Russian) and
 * redirect to the login page. Idempotent — N parallel fatal failures produce
 * one toast and one redirect. The full-page navigation naturally resets the
 * Redux store (and this module's state).
 */
export const handleAuthFailure = (): void => {
  if (authFailureHandled) {
    return;
  }
  authFailureHandled = true;
  clearTokens();
  toast.error('Сессия истекла. Войдите снова.');
  window.location.assign('/');
};
