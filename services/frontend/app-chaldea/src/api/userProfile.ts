import axios from 'axios';
import { BASE_URL_DEFAULT } from './api';

// Wall Posts
export const fetchWallPosts = (userId: number, page = 1, pageSize = 20) =>
  axios.get(`${BASE_URL_DEFAULT}/users/${userId}/wall/posts`, {
    params: { page, page_size: pageSize },
  });

export const createWallPost = (userId: number, content: string) =>
  axios.post(`${BASE_URL_DEFAULT}/users/${userId}/wall/posts`, { content });

export const updateWallPost = (postId: number, content: string) =>
  axios.put(`${BASE_URL_DEFAULT}/users/wall/posts/${postId}`, { content });

export const deleteWallPost = (postId: number) =>
  axios.delete(`${BASE_URL_DEFAULT}/users/wall/posts/${postId}`);

// Friends
export const sendFriendRequest = (friendId: number) =>
  axios.post(`${BASE_URL_DEFAULT}/users/friends/request`, { friend_id: friendId });

export const acceptFriendRequest = (friendshipId: number) =>
  axios.put(`${BASE_URL_DEFAULT}/users/friends/request/${friendshipId}/accept`);

export const rejectFriendRequest = (friendshipId: number) =>
  axios.delete(`${BASE_URL_DEFAULT}/users/friends/request/${friendshipId}`);

export const fetchFriends = (userId: number) =>
  axios.get(`${BASE_URL_DEFAULT}/users/${userId}/friends`);

export const fetchIncomingRequests = () =>
  axios.get(`${BASE_URL_DEFAULT}/users/friends/requests/incoming`);

export const fetchOutgoingRequests = () =>
  axios.get(`${BASE_URL_DEFAULT}/users/friends/requests/outgoing`);

export const removeFriend = (friendId: number) =>
  axios.delete(`${BASE_URL_DEFAULT}/users/friends/${friendId}`);

// User Profile
export const fetchUserProfile = (userId: number) =>
  axios.get(`${BASE_URL_DEFAULT}/users/${userId}/profile`);

// User Avatar Upload (via photo-service)
export const uploadUserAvatar = (userId: number, file: File) => {
  const formData = new FormData();
  formData.append('user_id', String(userId));
  formData.append('file', file);
  return axios.post(`${BASE_URL_DEFAULT}/photo/change_user_avatar_photo`, formData);
};

// Profile Settings
export interface ProfileSettingsPayload {
  profile_bg_color?: string | null;
  nickname_color?: string | null;
  avatar_frame?: string | null;
  status_text?: string | null;
  profile_bg_position?: string | null;
  post_color?: string | null;
  profile_style_settings?: {
    post_color_opacity?: number;
    post_color_blur?: number;
    post_color_glow?: number;
    post_color_saturation?: number;
    bg_color_opacity?: number;
    bg_color_blur?: number;
    bg_color_glow?: number;
    bg_color_saturation?: number;
    nickname_color_2?: string;
    nickname_gradient_angle?: number;
    nickname_brightness?: number;
    nickname_contrast?: number;
    nickname_shimmer?: boolean;
    text_shadow_enabled?: boolean;
    text_backdrop_enabled?: boolean;
  } | null;
}

export const updateProfileSettings = (data: ProfileSettingsPayload) =>
  axios.put(`${BASE_URL_DEFAULT}/users/me/settings`, data);

// Username Change
export const updateUsername = (username: string) =>
  axios.put(`${BASE_URL_DEFAULT}/users/me/username`, { username });

// User Characters
export const fetchUserCharacters = (userId: number) =>
  axios.get(`${BASE_URL_DEFAULT}/users/${userId}/characters`);

// Profile Background (via photo-service)
export const uploadProfileBackground = (userId: number, file: File) => {
  const formData = new FormData();
  formData.append('user_id', String(userId));
  formData.append('file', file);
  return axios.post(`${BASE_URL_DEFAULT}/photo/change_profile_background`, formData);
};

export const deleteProfileBackground = (userId: number) =>
  axios.delete(`${BASE_URL_DEFAULT}/photo/delete_profile_background`, {
    params: { user_id: userId },
  });
