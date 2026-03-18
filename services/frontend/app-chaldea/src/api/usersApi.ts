import axios from 'axios';
import { BASE_URL_DEFAULT } from './api';
import type { UserListResponse, UserStatsResponse } from '../types/users';

export const fetchUserStats = () =>
  axios.get<UserStatsResponse>(`${BASE_URL_DEFAULT}/users/stats`);

export const fetchAllUsers = (page = 1, pageSize = 50) =>
  axios.get<UserListResponse>(`${BASE_URL_DEFAULT}/users/all`, {
    params: { page, page_size: pageSize },
  });

export const fetchOnlineUsers = (page = 1, pageSize = 50) =>
  axios.get<UserListResponse>(`${BASE_URL_DEFAULT}/users/online`, {
    params: { page, page_size: pageSize },
  });
