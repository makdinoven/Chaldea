import axios, { AxiosError } from 'axios';
import { attachAuthInterceptors } from './axiosSetup';

/**
 * Dedicated axios instance for inventory-service (kept separate from the
 * default instance: consumers in `items.ts` rely on its error-normalization
 * semantics — see the response interceptor below).
 */
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
  (e: AxiosError<{ detail?: string }>) => {
    if (e.response) {
      // возврат читаемого текста ошибки
      throw new Error(e.response.data?.detail || e.response.statusText);
    }
    throw e;
  },
);

export default client;
