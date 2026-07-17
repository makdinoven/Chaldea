/**
 * Shared Axios auth interceptors (FEAT-150).
 *
 * `attachAuthInterceptors(instance)`:
 *  - request interceptor: attaches `Authorization: Bearer <token>` from
 *    localStorage on every outgoing request;
 *  - response interceptor: on 401 (except auth endpoints) performs a
 *    single-flight token refresh via `refreshAccessToken()` and retries the
 *    original request exactly once (`_retried` flag). A definitively failed
 *    refresh triggers `handleAuthFailure()` (logout + Russian toast +
 *    redirect); a transient refresh failure (5xx/network) propagates the
 *    ORIGINAL error and keeps the tokens intact. 403 keeps its toast.
 *
 * The interceptors are applied to the default Axios instance below; the
 * module must be imported once, early in the application entry point
 * (main.jsx). Secondary instances (e.g. `client.ts`) call
 * `attachAuthInterceptors()` themselves.
 */
import axios, {
  AxiosError,
  AxiosInstance,
  InternalAxiosRequestConfig,
} from 'axios';
import toast from 'react-hot-toast';
import {
  getAccessToken,
  handleAuthFailure,
  refreshAccessToken,
} from './authToken';

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  /** Set after the single refresh-and-retry cycle to prevent retry loops. */
  _retried?: boolean;
}

/** Endpoints whose 401 means "bad credentials", never "expired session". */
const AUTH_ENDPOINTS = ['/users/login', '/users/register', '/users/refresh'];

const isAuthEndpoint = (url: string): boolean =>
  AUTH_ENDPOINTS.some((endpoint) => url.includes(endpoint));

/** Extract the Bearer token the failed request was actually sent with. */
const extractRequestToken = (
  config: RetriableRequestConfig,
): string | null => {
  const authHeader: unknown = config.headers?.Authorization;
  if (typeof authHeader === 'string' && authHeader.startsWith('Bearer ')) {
    return authHeader.slice('Bearer '.length);
  }
  return null;
};

export const attachAuthInterceptors = (instance: AxiosInstance): void => {
  // ── Request interceptor: attach JWT token ──
  instance.interceptors.request.use((config) => {
    const token = getAccessToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // ── Response interceptor: refresh-on-401 + single retry ──
  instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const status = error.response?.status;
      const config = error.config as RetriableRequestConfig | undefined;

      if (status === 403) {
        toast.error('Недостаточно прав для выполнения этого действия.');
        return Promise.reject(error);
      }

      if (
        status !== 401 ||
        !config ||
        config._retried ||
        isAuthEndpoint(config.url || '')
      ) {
        return Promise.reject(error);
      }

      const result = await refreshAccessToken(extractRequestToken(config));

      if (result.status === 'ok') {
        config._retried = true;
        if (config.headers) {
          config.headers.Authorization = `Bearer ${result.token}`;
        }
        return instance(config);
      }

      if (result.status === 'fatal') {
        // Refresh token definitively rejected — the only logout path.
        handleAuthFailure();
      }
      // 'transient' (or fatal, for the caller's own error UI): propagate the
      // ORIGINAL error; tokens are never deleted here.
      return Promise.reject(error);
    },
  );
};

// Apply to the default Axios instance (used by most src/api/* modules).
attachAuthInterceptors(axios);
