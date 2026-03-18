export interface UserPublicItem {
  id: number;
  username: string;
  avatar: string | null;
  registered_at: string | null;
  last_active_at: string | null;
}

export interface UserListResponse {
  items: UserPublicItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserStatsResponse {
  total_users: number;
  online_users: number;
}
