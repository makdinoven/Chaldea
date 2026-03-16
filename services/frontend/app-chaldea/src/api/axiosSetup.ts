/**
 * Global Axios interceptors for authentication.
 *
 * Importing this module adds a request interceptor to the default Axios
 * instance that attaches `Authorization: Bearer <token>` from localStorage
 * on every outgoing request, and a response interceptor that surfaces
 * 401/403 errors to the user via react-hot-toast.
 *
 * Must be imported once, early in the application entry point (main.jsx).
 */
import axios from 'axios';
import toast from 'react-hot-toast';

// ── Request interceptor: attach JWT token ──
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor: surface auth errors ──
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      toast.error('Сессия истекла или вы не авторизованы. Войдите снова.');
    } else if (error.response?.status === 403) {
      toast.error('Недостаточно прав для выполнения этого действия.');
    }
    return Promise.reject(error);
  },
);
