import axios from 'axios';

/**
 * FEAT-179 — episodes: player-run stories outside the main world
 * (locations-service `/locations/episodes`, pictures through photo-service).
 */

export type EpisodeCategory = 'world' | 'separate';
export type EpisodeMemberRole = 'owner' | 'master' | 'player';

export const CATEGORY_LABEL: Record<EpisodeCategory, string> = {
  world: 'Истории мира',
  separate: 'Отдельные истории',
};

export const MEMBER_ROLE_LABEL: Record<EpisodeMemberRole, string> = {
  owner: 'Владелец',
  master: 'Мастер',
  player: 'Игрок',
};

export interface UserBrief {
  id: number;
  username: string;
  avatar: string | null;
}

export interface Episode {
  id: number;
  owner_user_id: number;
  category: EpisodeCategory;
  title: string;
  description: string;
  image_url: string | null;
  is_private: boolean;
  is_hidden: boolean;
  created_at: string;
}

export interface EpisodeCard extends Episode {
  owner: UserBrief | null;
  members_count: number;
  posts_count: number;
  last_post_at: string | null;
  my_role: EpisodeMemberRole | null;
}

export interface MiniRole {
  id: number;
  user_id: number;
  name: string;
  avatar_url: string | null;
  description: string;
  archived: boolean;
}

export interface EpisodeLocationCard {
  id: number;
  name: string;
  description: string;
  image_url: string | null;
  sort_order: number;
  posts_count: number;
  last_post_at: string | null;
}

export interface EpisodeMember {
  user_id: number;
  role: EpisodeMemberRole;
  username: string | null;
  avatar: string | null;
  roles: MiniRole[];
}

export interface EpisodeDetail extends Episode {
  owner: UserBrief | null;
  my_role: EpisodeMemberRole | null;
  can_manage: boolean;
  is_owner: boolean;
  /** Owner's powers (masters, deleting): the owner or the top admin. */
  can_own: boolean;
  can_moderate: boolean;
  my_request: boolean;
  requests_count: number;
  locations: EpisodeLocationCard[];
  members: EpisodeMember[];
}

export interface EpisodeLocationView {
  episode: Pick<Episode, 'id' | 'title' | 'category' | 'image_url' | 'is_private'>;
  location: Pick<EpisodeLocationCard, 'id' | 'name' | 'description' | 'image_url' | 'sort_order'>;
  locations: { id: number; name: string }[];
  my_roles: MiniRole[];
  is_member: boolean;
  can_manage: boolean;
  can_moderate: boolean;
}

export interface EpisodePost {
  id: number;
  location_id: number;
  user_id: number;
  username: string | null;
  role: MiniRole | null;
  content: string;
  created_at: string;
  edited_at: string | null;
  likes_count: number;
  liked: boolean;
  length: number;
}

export interface JoinRequest {
  id: number;
  user_id: number;
  username: string | null;
  avatar: string | null;
  message: string;
  created_at: string;
}

export interface EpisodeInput {
  category: EpisodeCategory;
  title: string;
  description: string;
  image_url: string | null;
  is_private: boolean;
}

export interface LocationInput {
  name: string;
  description: string;
  image_url: string | null;
  sort_order: number;
}

export interface RoleInput {
  name: string;
  avatar_url: string | null;
  description: string;
}

const BASE = '/locations/episodes';

export const listEpisodes = async (category?: EpisodeCategory) =>
  (await axios.get<EpisodeCard[]>(BASE, { params: category ? { category } : undefined })).data;

export const createEpisode = async (body: EpisodeInput) => (await axios.post<Episode>(BASE, body)).data;
export const getEpisode = async (id: number) => (await axios.get<EpisodeDetail>(`${BASE}/${id}`)).data;
export const updateEpisode = async (id: number, body: EpisodeInput) =>
  (await axios.put<Episode>(`${BASE}/${id}`, body)).data;
export const deleteEpisode = async (id: number) => axios.delete(`${BASE}/${id}`);
export const hideEpisode = async (id: number, hidden: boolean) => axios.post(`${BASE}/${id}/hide`, { hidden });

export const createLocation = async (id: number, body: LocationInput) =>
  (await axios.post<{ id: number }>(`${BASE}/${id}/locations`, body)).data;
export const updateLocation = async (id: number, locationId: number, body: LocationInput) =>
  axios.put(`${BASE}/${id}/locations/${locationId}`, body);
export const deleteLocation = async (id: number, locationId: number) =>
  axios.delete(`${BASE}/${id}/locations/${locationId}`);
export const getLocation = async (id: number, locationId: number) =>
  (await axios.get<EpisodeLocationView>(`${BASE}/${id}/locations/${locationId}`)).data;

export const listPosts = async (id: number, locationId: number, beforeId?: number) =>
  (await axios.get<{ posts: EpisodePost[]; has_more: boolean }>(`${BASE}/${id}/locations/${locationId}/posts`, {
    params: beforeId ? { before_id: beforeId } : undefined,
  })).data;
export const createPost = async (id: number, locationId: number, roleId: number, content: string) =>
  (await axios.post<EpisodePost>(`${BASE}/${id}/locations/${locationId}/posts`, { role_id: roleId, content })).data;
export const editPost = async (id: number, postId: number, content: string) =>
  (await axios.put<EpisodePost>(`${BASE}/${id}/posts/${postId}`, { content })).data;
export const deletePost = async (id: number, postId: number) => axios.delete(`${BASE}/${id}/posts/${postId}`);
export const likePost = async (id: number, postId: number, like: boolean) =>
  like ? axios.post(`${BASE}/${id}/posts/${postId}/like`) : axios.delete(`${BASE}/${id}/posts/${postId}/like`);

export const searchUsers = async (id: number, q: string) =>
  (await axios.get<UserBrief[]>(`${BASE}/${id}/user-search`, { params: { q } })).data;
export const addMember = async (id: number, userId: number) => axios.post(`${BASE}/${id}/members`, { user_id: userId });
export const setMemberRole = async (id: number, userId: number, role: 'master' | 'player') =>
  axios.put(`${BASE}/${id}/members/${userId}`, { role });
export const removeMember = async (id: number, userId: number) => axios.delete(`${BASE}/${id}/members/${userId}`);

export const createRole = async (id: number, userId: number, name = '') =>
  (await axios.post<MiniRole>(`${BASE}/${id}/roles`, { user_id: userId, name })).data;
export const updateRole = async (id: number, roleId: number, body: RoleInput) =>
  (await axios.put<MiniRole>(`${BASE}/${id}/roles/${roleId}`, body)).data;
export const deleteRole = async (id: number, roleId: number) =>
  (await axios.delete<{ ok: boolean; archived: boolean }>(`${BASE}/${id}/roles/${roleId}`)).data;

export const requestToJoin = async (id: number, message: string) => axios.post(`${BASE}/${id}/requests`, { message });
export const withdrawRequest = async (id: number) => axios.delete(`${BASE}/${id}/requests/mine`);
export const listRequests = async (id: number) => (await axios.get<JoinRequest[]>(`${BASE}/${id}/requests`)).data;
export const answerRequest = async (id: number, requestId: number, accept: boolean) =>
  axios.post(`${BASE}/${id}/requests/${requestId}/${accept ? 'accept' : 'decline'}`);

/** Uploads a picture for an episode, its location or a mini-role; returns its URL. */
export const uploadEpisodeImage = async (file: File) => {
  const form = new FormData();
  form.append('file', file);
  const { data } = await axios.post<{ image_url: string }>('/photo/upload_episode_image', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data.image_url;
};
