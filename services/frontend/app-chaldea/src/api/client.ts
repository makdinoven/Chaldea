import axios, { AxiosError } from 'axios';
import { attachAuthInterceptors } from './axiosSetup';

/**
 * Dedicated axios instance for inventory-service (kept separate from the
 * default instance: consumers in `items.ts` rely on its error-normalization
 * semantics — see the response interceptor below).
 */
/**
 * The normalized error thrown by this instance: a plain `Error` carrying the
 * readable backend message, plus the HTTP status so callers can tell a 403
 * (no permission) from a 500 without parsing the text (FEAT-167).
 */
export interface ApiError extends Error {
  status?: number;
}

const client = axios.create({
  baseURL: '/inventory',
  withCredentials: true,
  timeout: 10000,
});

// Shared auth interceptors (Bearer header + refresh-on-401 + retry) MUST be
// attached FIRST: response interceptors run in registration order, so the
// refresh interceptor sees the raw AxiosError (with `response.status`) before
// the normalizer below converts it into a plain Error.
attachAuthInterceptors(client);

// ── Response interceptor: normalize errors to readable messages ──
client.interceptors.response.use(
  (r) => r,
  (e: AxiosError<{ detail?: string | { msg?: string }[] }>) => {
    if (e.response) {
      // возврат читаемого текста ошибки
      const detail = e.response.data?.detail;
      // FastAPI validation errors (422) come as a list of {loc, msg}
      const text = Array.isArray(detail)
        ? detail.map((d) => d?.msg).filter(Boolean).join('; ')
        : detail;
      const normalized = new Error(text || e.response.statusText) as ApiError;
      normalized.status = e.response.status;
      throw normalized;
    }
    throw e;
  },
);

export default client;
