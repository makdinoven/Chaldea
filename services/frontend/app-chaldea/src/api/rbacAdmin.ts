import axios from 'axios';

// --- Types ---

export interface AdminUserItem {
  id: number;
  username: string;
  email: string;
  avatar: string | null;
  role: string;
  role_id: number;
  role_display_name: string | null;
  registered_at: string;
  last_active_at: string | null;
  permissions: string[];
}

export interface AdminUserListResponse {
  items: AdminUserItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUserListParams {
  page?: number;
  page_size?: number;
  search?: string;
  role_id?: number | null;
}

export interface RoleResponse {
  id: number;
  name: string;
  level: number;
  description: string | null;
}

export interface RoleAssignRequest {
  role_id: number;
  role_display_name?: string | null;
}

export interface UserRoleResponse {
  user_id: number;
  role: string;
  role_id: number;
  role_display_name: string | null;
}

export interface PermissionItem {
  id: number;
  module: string;
  action: string;
  description: string | null;
}

export interface PermissionsGroupedResponse {
  [module: string]: PermissionItem[];
}

export interface EffectivePermissionsResponse {
  user_id: number;
  username: string;
  role: string;
  role_display_name: string | null;
  role_permissions: string[];
  overrides: { grants?: string[]; revokes?: string[] };
  effective_permissions: string[];
}

export interface PermissionOverridesRequest {
  grants: string[];
  revokes: string[];
}

export interface UserPermissionsResponse {
  user_id: number;
  grants: string[];
  revokes: string[];
}

export interface RolePermissionsResponse {
  role_id: number;
  role_name: string;
  permissions: string[];
}

export interface RolePermissionsRequest {
  permissions: string[];
}

// --- API Calls ---

export const getAdminUserList = async (
  params: AdminUserListParams,
): Promise<AdminUserListResponse> => {
  const cleanParams: Record<string, string | number> = {};
  if (params.page != null) cleanParams.page = params.page;
  if (params.page_size != null) cleanParams.page_size = params.page_size;
  if (params.search) cleanParams.search = params.search;
  if (params.role_id != null) cleanParams.role_id = params.role_id;

  const { data } = await axios.get<AdminUserListResponse>('/users/admin/list', {
    params: cleanParams,
  });
  return data;
};

export const getRoles = async (): Promise<RoleResponse[]> => {
  const { data } = await axios.get<RoleResponse[]>('/users/roles');
  return data;
};

export const assignUserRole = async (
  userId: number,
  payload: RoleAssignRequest,
): Promise<UserRoleResponse> => {
  const { data } = await axios.put<UserRoleResponse>(
    `/users/${userId}/role`,
    payload,
  );
  return data;
};

export const getUserPermissions = async (
  userId: number,
): Promise<EffectivePermissionsResponse> => {
  const { data } = await axios.get<EffectivePermissionsResponse>(
    `/users/${userId}/effective-permissions`,
  );
  return data;
};

export const setUserPermissions = async (
  userId: number,
  payload: PermissionOverridesRequest,
): Promise<UserPermissionsResponse> => {
  const { data } = await axios.put<UserPermissionsResponse>(
    `/users/${userId}/permissions`,
    payload,
  );
  return data;
};

export const getRolePermissions = async (
  roleId: number,
): Promise<RolePermissionsResponse> => {
  const { data } = await axios.get<RolePermissionsResponse>(
    `/users/roles/${roleId}/permissions`,
  );
  return data;
};

export const setRolePermissions = async (
  roleId: number,
  payload: RolePermissionsRequest,
): Promise<RolePermissionsResponse> => {
  const { data } = await axios.put<RolePermissionsResponse>(
    `/users/roles/${roleId}/permissions`,
    payload,
  );
  return data;
};

export const getAllPermissions = async (): Promise<PermissionsGroupedResponse> => {
  const { data } = await axios.get<{ modules: PermissionsGroupedResponse }>('/users/permissions');
  return data.modules;
};
