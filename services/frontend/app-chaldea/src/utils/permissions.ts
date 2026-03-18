export const hasPermission = (permissions: string[], permission: string): boolean => {
  return permissions.includes(permission);
};

export const hasAnyPermission = (permissions: string[], perms: string[]): boolean => {
  return perms.some(p => permissions.includes(p));
};

export const hasModuleAccess = (permissions: string[], module: string): boolean => {
  return permissions.some(p => p.startsWith(`${module}:`));
};

export const isStaff = (role: string | null): boolean => {
  return role !== null && ['admin', 'moderator', 'editor'].includes(role);
};
