import axios from 'axios';
import { BASE_URL_DEFAULT } from './api';

// Wall Posts
export const fetchWallPosts = (userId: number, page = 1, pageSize = 20) =>
  axios.get(`${BASE_URL_DEFAULT}/users/${userId}/wall/posts`, {
    params: { page, page_size: pageSize },
  });

export const createWallPost = (userId: number, content: string) =>
  axios.post(`${BASE_URL_DEFAULT}/users/${userId}/wall/posts`, { content });

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
